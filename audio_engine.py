"""
SingerPro - Robust Real-Time Audio Engine
Manages:
- Audio device enumeration (WASAPI, DirectSound, MME)
- Low-latency duplex stream management with automatic fallback
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

class AudioEngine:
    def __init__(self, dsp_pipeline):
        self.dsp = dsp_pipeline
        self.is_running = False
        self.stream = None
        self.in_stream = None
        self.out_stream = None
        
        # Audio Configuration
        self.sample_rate = 48000
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
            
            # Clean up device name
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

    def start(self, input_id, output_id, sample_rate=48000, block_size=256):
        """Start live monitoring stream with requested devices and parameters."""
        if self.is_running:
            self.stop()
            
        self.input_device_id = input_id
        self.output_device_id = output_id
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.dsp.set_sample_rate(sample_rate)
        
        # Try unified duplex stream first (lowest latency)
        success = self._start_duplex_stream()
        if not success:
            # Fallback to dual stream mode
            success = self._start_dual_stream()
            
        if success:
            self.is_running = True
            self.last_status_msg = "Monitoring Active"
        return success

    def _start_duplex_stream(self):
        """Unified full duplex single-callback stream."""
        try:
            # Determine channels
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
            
            # Latency estimate
            in_lat = self.stream.latency[0] * 1000.0
            out_lat = self.stream.latency[1] * 1000.0
            dsp_lat = (self.block_size / self.sample_rate) * 1000.0
            self.estimated_latency_ms = in_lat + out_lat + dsp_lat
            return True
        except Exception as e:
            print(f"Duplex stream start failed ({e}), attempting dual stream fallback...")
            self.stream = None
            return False

    def _start_dual_stream(self):
        """Dual stream (separate Input and Output streams with circular jitter buffer)."""
        try:
            in_info = sd.query_devices(self.input_device_id)
            out_info = sd.query_devices(self.output_device_id)
            
            in_ch = min(2, in_info['max_input_channels'])
            out_ch = min(2, out_info['max_output_channels'])
            
            # Initialize circular dual buffer (4 blocks capacity)
            buf_len = self.block_size * 6
            self._dual_buffer = np.zeros((buf_len, 2), dtype=np.float32)
            self._dual_write_idx = 0
            self._dual_read_idx = 0
            self._dual_available = self.block_size * 2  # pre-fill half block
            
            self.in_stream = sd.InputStream(
                device=self.input_device_id,
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                channels=in_ch,
                dtype=np.float32,
                latency='low',
                callback=self._in_stream_callback
            )
            
            self.out_stream = sd.OutputStream(
                device=self.output_device_id,
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                channels=out_ch,
                dtype=np.float32,
                latency='low',
                callback=self._out_stream_callback
            )
            
            self.in_stream.start()
            self.out_stream.start()
            
            in_lat = self.in_stream.latency * 1000.0
            out_lat = self.out_stream.latency * 1000.0
            dsp_lat = (self.block_size / self.sample_rate) * 1000.0
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
            
        # Run DSP pipeline
        processed = self.dsp.process(indata)
        
        # Copy to output buffer
        if outdata.shape[1] == 1:
            # Mono output
            outdata[:, 0] = (processed[:, 0] + processed[:, 1]) * 0.5
        else:
            outdata[:] = processed
            
        # Feed visualizer
        self._push_to_visualizer(processed)
        
        # Feed recorder if active
        if self.is_recording:
            try:
                self.record_queue.put_nowait(processed.copy())
            except queue.Full:
                pass

    def _in_stream_callback(self, indata, frames, time_info, status):
        """Input stream callback for dual mode."""
        processed = self.dsp.process(indata)
        
        # Write to dual buffer
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
        """Output stream callback for dual mode."""
        with self._dual_lock:
            buf_len = len(self._dual_buffer)
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
            
        # Fast FFT for frequency spectrum
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
        
        # Clear queue
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
                        # Convert float32 [-1.0, 1.0] to int16
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
