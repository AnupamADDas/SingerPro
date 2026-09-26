"""
SingerPro - Robust Real-Time Audio Engine
Manages:
- Audio device enumeration (WASAPI, DirectSound, MME)
- Low-latency duplex stream management with automatic fallback
- Asynchronous dual-rate streaming with JIT linear resampling (e.g. 16kHz Bluetooth Mic -> 48kHz Headphones)
- Thread-safe ring buffer for oscilloscope waveform & spectrum visualizer
- Non-blocking live audio recorder (WAV)
- Latency calculations and audio status monitoring
"""

import time
import queue
import wave
import os
import threading
import sounddevice as sd
import numpy as np
from numba import njit


@njit(fastmath=True)
def _resample_linear(in_data, target_len):
    """Ultra-fast Numba linear resampler for cross-rate streaming (e.g. 16kHz -> 48kHz)."""
    n, c = in_data.shape
    out = np.empty((target_len, c), dtype=np.float32)
    if n <= 1 or target_len <= 1:
        out[:] = 0.0
        return out
    ratio = (n - 1) / (target_len - 1)
    for i in range(target_len):
        pos = i * ratio
        idx = int(pos)
        frac = pos - idx
        if idx >= n - 1:
            for ch in range(c):
                out[i, ch] = in_data[n - 1, ch]
        else:
            for ch in range(c):
                out[i, ch] = in_data[idx, ch] * (1.0 - frac) + in_data[idx + 1, ch] * frac
    return out


class AudioEngine:
    def __init__(self, dsp_pipeline):
        self.dsp = dsp_pipeline
        self.is_running = False
        self.stream = None
        self.in_stream = None
        self.out_stream = None
        
        # Audio Configuration
        self.sample_rate = 48000
        self.in_sr = 48000
        self.out_sr = 48000
        self.block_size = 256  # ~5.3 ms at 48kHz
        self.input_device_id = None
        self.output_device_id = None
        
        # Latency statistics
        self.estimated_latency_ms = 0.0
        self.last_status_msg = "Idle"
        
        # Visualizer circular ring buffer for UI (mono downmixed samples)
        self.visualizer_buffer_len = 1024
        self.visualizer_buffer = np.zeros(self.visualizer_buffer_len, dtype=np.float32)
        self.vis_lock = threading.Lock()
        
        # Live Recording
        self.is_recording = False
        self.record_queue = queue.Queue(maxsize=200)
        self.recorder_thread = None
        self.record_filepath = None
        self.record_frames_count = 0
        self.record_start_time = 0.0
        
        # Ring buffer for dual-stream fallback mode
        self._dual_buffer = None
        self._dual_lock = threading.Lock()
        self._dual_write_idx = 0
        self._dual_read_idx = 0
        self._dual_available = 0

    @staticmethod
    def get_devices():
        """
        Enumerate all input and output devices grouped by host API.
        Returns dict with structured device info.
        """
        host_apis = sd.query_hostapis()
        devices = sd.query_devices()
        
        input_devs = []
        output_devs = []
        
        for idx, dev in enumerate(devices):
            api_info = host_apis[dev['hostapi']]
            api_name = api_info['name']
            name = dev['name']
            
            item = {
                'id': idx,
                'name': name,
                'api': api_name,
                'max_in': dev['max_input_channels'],
                'max_out': dev['max_output_channels'],
                'default_rate': int(dev['default_samplerate']),
                'display_name': f"[{api_name}] {name} (ID: {idx})"
            }
            
            if dev['max_input_channels'] > 0:
                input_devs.append(item)
            if dev['max_output_channels'] > 0:
                output_devs.append(item)
                
        # Sort so WASAPI appears first (recommended)
        def sort_key(d):
            if 'WASAPI' in d['api']:
                return 0
            elif 'DirectSound' in d['api']:
                return 1
            return 2
            
        input_devs.sort(key=sort_key)
        output_devs.sort(key=sort_key)
        
        return input_devs, output_devs

    @staticmethod
    def get_supported_samplerates(input_id, output_id):
        """
        Determine which sample rates are natively supported by both selected devices.
        If devices have differing native rates (e.g. Bluetooth Mic at 16kHz and Headphones at 48kHz),
        the dual-rate engine handles them seamlessly by resampling input to output rate.
        """
        candidate_rates = [48000, 44100, 96000, 88200]
        supported = []
        
        in_default = 48000
        out_default = 48000
        if input_id is not None:
            try:
                in_default = int(sd.query_devices(input_id).get('default_samplerate', 48000))
            except Exception:
                pass
        if output_id is not None:
            try:
                out_default = int(sd.query_devices(output_id).get('default_samplerate', 48000))
            except Exception:
                pass

        # Check which rates are supported by both
        for sr in candidate_rates:
            in_ok = True
            out_ok = True
            if input_id is not None:
                try:
                    sd.check_input_settings(device=input_id, samplerate=sr)
                except Exception:
                    in_ok = False
            if output_id is not None:
                try:
                    sd.check_output_settings(device=output_id, samplerate=sr)
                except Exception:
                    out_ok = False
            if in_ok and out_ok:
                supported.append(sr)

        if not supported:
            # Mismatched devices (e.g. Bluetooth mic @ 16kHz + Headphones @ 48kHz)
            supported = [out_default]
            recommended = out_default
        else:
            recommended = 48000 if 48000 in supported else supported[0]
            
        return supported, recommended

    def start(self, input_id, output_id, sample_rate=48000, block_size=256):
        """Start live monitoring stream with requested devices and parameters."""
        if self.is_running:
            self.stop()
            
        self.input_device_id = input_id
        self.output_device_id = output_id
        self.block_size = block_size
        
        in_info = sd.query_devices(self.input_device_id)
        out_info = sd.query_devices(self.output_device_id)
        
        in_default = int(in_info.get('default_samplerate', 48000))
        out_default = int(out_info.get('default_samplerate', 48000))
        
        # Test input support
        try:
            sd.check_input_settings(device=self.input_device_id, samplerate=sample_rate)
            self.in_sr = sample_rate
        except Exception:
            self.in_sr = in_default
            
        # Test output support
        try:
            sd.check_output_settings(device=self.output_device_id, samplerate=sample_rate)
            self.out_sr = sample_rate
        except Exception:
            self.out_sr = out_default
            
        # DSP and master engine operate at out_sr
        self.sample_rate = self.out_sr
        self.dsp.set_sample_rate(self.out_sr)
        
        success = False
        # If both devices share the exact same sample rate, attempt low-latency unified duplex stream
        if self.in_sr == self.out_sr:
            success = self._start_duplex_stream()
            
        # If duplex failed or if rates differ (e.g. Bluetooth 16kHz Mic -> 48kHz Headphones)
        if not success:
            success = self._start_dual_stream(self.in_sr, self.out_sr)
            
        if success:
            self.is_running = True
            if self.in_sr != self.out_sr:
                self.last_status_msg = f"Dual-Rate Active ({self.in_sr//1000}k In -> {self.out_sr//1000}k Out)"
            else:
                self.last_status_msg = f"Monitoring Active ({self.sample_rate} Hz)"
        return success

    def _start_duplex_stream(self):
        """Unified full duplex single-callback stream (lowest latency when rates match)."""
        try:
            in_info = sd.query_devices(self.input_device_id)
            out_info = sd.query_devices(self.output_device_id)
            
            in_ch = min(2, in_info['max_input_channels'])
            out_ch = min(2, out_info['max_output_channels'])
            
            self.stream = sd.Stream(
                device=(self.input_device_id, self.output_device_id),
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                channels=(in_ch, out_ch),
                dtype=np.float32,
                latency='low',
                callback=self._duplex_callback
            )
            self.stream.start()
            
            in_lat = self.stream.latency[0] * 1000.0
            out_lat = self.stream.latency[1] * 1000.0
            dsp_lat = (self.block_size / self.sample_rate) * 1000.0
            self.estimated_latency_ms = in_lat + out_lat + dsp_lat
            return True
        except Exception as e:
            print(f"Duplex stream start failed ({e}), attempting dual stream fallback...")
            self.stream = None
            return False

    def _start_dual_stream(self, in_sr, out_sr):
        """Dual stream with independent sample rates & Numba JIT resampler."""
        try:
            self.in_sr = in_sr
            self.out_sr = out_sr
            
            in_info = sd.query_devices(self.input_device_id)
            out_info = sd.query_devices(self.output_device_id)
            
            in_ch = min(2, in_info['max_input_channels'])
            out_ch = min(2, out_info['max_output_channels'])
            
            # Input block size proportional to rate
            in_block = max(64, int(self.block_size * in_sr / out_sr))
            out_block = self.block_size
            
            # Circular ring buffer (16 blocks capacity)
            buf_len = max(out_block * 16, 8192)
            self._dual_buffer = np.zeros((buf_len, 2), dtype=np.float32)
            self._dual_write_idx = 0
            self._dual_read_idx = 0
            self._dual_available = out_block * 2  # pre-fill 2 blocks
            
            self.in_stream = sd.InputStream(
                device=self.input_device_id,
                samplerate=in_sr,
                blocksize=in_block,
                channels=in_ch,
                dtype=np.float32,
                latency='low',
                callback=self._in_stream_callback
            )
            
            self.out_stream = sd.OutputStream(
                device=self.output_device_id,
                samplerate=out_sr,
                blocksize=out_block,
                channels=out_ch,
                dtype=np.float32,
                latency='low',
                callback=self._out_stream_callback
            )
            
            self.in_stream.start()
            self.out_stream.start()
            
            in_lat = self.in_stream.latency * 1000.0
            out_lat = self.out_stream.latency * 1000.0
            dsp_lat = (out_block / out_sr) * 1000.0
            self.estimated_latency_ms = in_lat + out_lat + dsp_lat
            return True
        except Exception as e:
            print(f"Dual stream start failed: {e}")
            self.last_status_msg = f"Error: {e}"
            self.in_stream = None
            self.out_stream = None
            return False

    def _duplex_callback(self, indata, outdata, frames, time_info, status):
        """Zero-copy duplex audio callback."""
        if status:
            self.last_status_msg = f"Audio: {status}"
            
        processed = self.dsp.process(indata)
        
        if outdata.shape[1] == 1:
            outdata[:, 0] = (processed[:, 0] + processed[:, 1]) * 0.5
        else:
            outdata[:] = processed
            
        self._push_to_visualizer(processed)
        
        if self.is_recording:
            try:
                self.record_queue.put_nowait(processed.copy())
            except queue.Full:
                pass

    def _in_stream_callback(self, indata, frames, time_info, status):
        """Input stream callback for dual mode with automatic cross-rate resampling."""
        if status:
            self.last_status_msg = f"Audio In: {status}"
            
        # Ensure stereo float32
        if indata.shape[1] == 1:
            stereo = np.column_stack((indata[:, 0], indata[:, 0])).astype(np.float32)
        else:
            stereo = indata.astype(np.float32)
            
        # Resample to output rate if different
        if self.in_sr != self.out_sr:
            target_len = int(round(frames * self.out_sr / self.in_sr))
            stereo = _resample_linear(stereo, target_len)
            frames = target_len
            
        processed = self.dsp.process(stereo)
        
        # Write to circular dual buffer
        with self._dual_lock:
            buf_len = len(self._dual_buffer)
            w_idx = self._dual_write_idx
            end_idx = w_idx + frames
            
            if end_idx <= buf_len:
                self._dual_buffer[w_idx:end_idx] = processed
            else:
                part1 = buf_len - w_idx
                part2 = frames - part1
                self._dual_buffer[w_idx:] = processed[:part1]
                self._dual_buffer[:part2] = processed[part1:]
                
            self._dual_write_idx = (w_idx + frames) % buf_len
            self._dual_available = min(buf_len, self._dual_available + frames)
            
        self._push_to_visualizer(processed)
        if self.is_recording:
            try:
                self.record_queue.put_nowait(processed.copy())
            except queue.Full:
                pass

    def _out_stream_callback(self, outdata, frames, time_info, status):
        """Output stream callback for dual mode with jitter/drift compensation."""
        with self._dual_lock:
            buf_len = len(self._dual_buffer)
            r_idx = self._dual_read_idx
            
            # Drift compensation: if buffer is filling up too much (> 8 blocks), discard excess
            max_drift = frames * 8
            if self._dual_available > max_drift:
                skip = self._dual_available - frames * 3
                self._dual_read_idx = (self._dual_read_idx + skip) % buf_len
                self._dual_available -= skip
                r_idx = self._dual_read_idx
            
            if self._dual_available >= frames:
                end_idx = r_idx + frames
                if end_idx <= buf_len:
                    data = self._dual_buffer[r_idx:end_idx]
                else:
                    part1 = buf_len - r_idx
                    part2 = frames - part1
                    data = np.vstack((self._dual_buffer[r_idx:], self._dual_buffer[:part2]))
                self._dual_read_idx = (r_idx + frames) % buf_len
                self._dual_available -= frames
            else:
                # Underflow concealment
                data = np.zeros((frames, 2), dtype=np.float32)
                
        if outdata.shape[1] == 1:
            outdata[:, 0] = (data[:, 0] + data[:, 1]) * 0.5
        else:
            outdata[:] = data

    def _push_to_visualizer(self, processed):
        """Push latest mono downmix samples to visualizer ring buffer."""
        mono = (processed[:, 0] + processed[:, 1]) * 0.5
        n = len(mono)
        if n >= self.visualizer_buffer_len:
            with self.vis_lock:
                self.visualizer_buffer[:] = mono[-self.visualizer_buffer_len:]
        else:
            with self.vis_lock:
                self.visualizer_buffer[:-n] = self.visualizer_buffer[n:]
                self.visualizer_buffer[-n:] = mono

    def get_visualizer_data(self):
        """Fetch visualizer waveform and spectral FFT data."""
        with self.vis_lock:
            wave_data = self.visualizer_buffer.copy()
            
        fft_data = np.abs(np.fft.rfft(wave_data * np.hanning(len(wave_data))))
        return wave_data, fft_data

    def stop(self):
        """Stop all active audio streams."""
        self.is_running = False
        
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
            
        if self.in_stream is not None:
            try:
                self.in_stream.stop()
                self.in_stream.close()
            except Exception:
                pass
            self.in_stream = None
            
        if self.out_stream is not None:
            try:
                self.out_stream.stop()
                self.out_stream.close()
            except Exception:
                pass
            self.out_stream = None
            
        self.last_status_msg = "Monitoring Stopped"

    # -----------------------------------------------------
    # LIVE AUDIO RECORDING
    # -----------------------------------------------------

    def start_recording(self, save_dir="recordings"):
        """Start recording monitored output to a WAV file."""
        if self.is_recording:
            return None
            
        os.makedirs(save_dir, exist_ok=True)
        filename = f"SingerPro_{time.strftime('%Y%m%d_%H%M%S')}.wav"
        self.record_filepath = os.path.join(save_dir, filename)
        
        while not self.record_queue.empty():
            try:
                self.record_queue.get_nowait()
            except queue.Empty:
                break
                
        self.is_recording = True
        self.record_frames_count = 0
        self.record_start_time = time.time()
        
        self.recorder_thread = threading.Thread(target=self._record_worker, daemon=True)
        self.recorder_thread.start()
        return self.record_filepath

    def _record_worker(self):
        """Background thread writing chunks to disk."""
        try:
            with wave.open(self.record_filepath, 'wb') as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2) # 16-bit PCM
                wf.setframerate(self.sample_rate)
                
                while self.is_recording or not self.record_queue.empty():
                    try:
                        chunk = self.record_queue.get(timeout=0.1)
                        int16_chunk = np.clip(chunk * 32767.0, -32768, 32767).astype(np.int16)
                        wf.writeframes(int16_chunk.tobytes())
                        self.record_frames_count += len(chunk)
                    except queue.Empty:
                        continue
        except Exception as e:
            print(f"Recording error: {e}")

    def stop_recording(self):
        """Stop recording and finalize the WAV file."""
        if not self.is_recording:
            return None
        self.is_recording = False
        if self.recorder_thread:
            self.recorder_thread.join(timeout=1.0)
            self.recorder_thread = None
        return self.record_filepath
