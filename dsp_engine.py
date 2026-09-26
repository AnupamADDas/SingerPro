"""
SingerPro - High-Performance Real-Time DSP Audio Processing Engine
Features:
- Numba JIT accelerated algorithms for microsecond execution latency
- Freeverb Schroeder-Moorer 8-Comb + 4-AllPass Stereo Reverb
- Warm Analog Tape Echo / Delay with feedback damping & ping-pong stereo
- Zero-latency Adaptive Noise Gate with soft-knee envelope follower
- Real-time Noise Reduction & Rumble Filter (80Hz Butterworth HPF)
- 3-Band Studio Vocal Equalizer (Low Shelf, Mid Peaking, High Shelf Air)
- Vocal Compressor & Soft-Knee Ear-Protection Limiter
- Real-time Peak & RMS metering
"""

import math
import numpy as np
import scipy.signal as signal
from numba import njit

# ---------------------------------------------------------
# NUMBA JIT ACCELERATED CORE KERNELS
# ---------------------------------------------------------

@njit(fastmath=True)
def _comb_filter_mono(buffer, input_samples, feedback, damp, delay_len, buf_idx, last_damp):
    """Low-pass feedback comb filter."""
    n = len(input_samples)
    buf_len = len(buffer)
    out = np.empty(n, dtype=np.float32)
    
    for i in range(n):
        read_idx = (buf_idx - delay_len + buf_len) % buf_len
        buf_out = buffer[read_idx]
        last_damp = buf_out * (1.0 - damp) + last_damp * damp
        buffer[buf_idx] = input_samples[i] + last_damp * feedback
        buf_idx = (buf_idx + 1) % buf_len
        out[i] = buf_out
        
    return out, buf_idx, last_damp


@njit(fastmath=True)
def _allpass_filter_mono(buffer, input_samples, feedback, delay_len, buf_idx):
    """Allpass filter for reverb diffusion."""
    n = len(input_samples)
    buf_len = len(buffer)
    out = np.empty(n, dtype=np.float32)
    
    for i in range(n):
        read_idx = (buf_idx - delay_len + buf_len) % buf_len
        buf_out = buffer[read_idx]
        in_val = input_samples[i]
        buffer[buf_idx] = in_val + buf_out * feedback
        out[i] = buf_out - in_val * feedback
        buf_idx = (buf_idx + 1) % buf_len
        
    return out, buf_idx


@njit(fastmath=True)
def _process_echo_stereo(buf_l, buf_r, in_l, in_r, delay_len_l, delay_len_r, 
                         feedback, damp, wet, dry, pingpong, 
                         idx_l, idx_r, damp_l, damp_r):
    """Stereo / Ping-Pong Echo delay with low-pass damping."""
    n = len(in_l)
    len_buf_l = len(buf_l)
    len_buf_r = len(buf_r)
    
    out_l = np.empty(n, dtype=np.float32)
    out_r = np.empty(n, dtype=np.float32)
    
    for i in range(n):
        # Read delayed samples
        rd_l = (idx_l - delay_len_l + len_buf_l) % len_buf_l
        rd_r = (idx_r - delay_len_r + len_buf_r) % len_buf_r
        
        del_out_l = buf_l[rd_l]
        del_out_r = buf_r[rd_r]
        
        # Apply lowpass damping in feedback loop
        damp_l = del_out_l * (1.0 - damp) + damp_l * damp
        damp_r = del_out_r * (1.0 - damp) + damp_r * damp
        
        if pingpong:
            # Cross feedback for stereo bounce
            buf_l[idx_l] = in_l[i] + damp_r * feedback
            buf_r[idx_r] = in_r[i] + damp_l * feedback
        else:
            buf_l[idx_l] = in_l[i] + damp_l * feedback
            buf_r[idx_r] = in_r[i] + damp_r * feedback
            
        out_l[i] = in_l[i] * dry + del_out_l * wet
        out_r[i] = in_r[i] * dry + del_out_r * wet
        
        idx_l = (idx_l + 1) % len_buf_l
        idx_r = (idx_r + 1) % len_buf_r
        
    return out_l, out_r, idx_l, idx_r, damp_l, damp_r


@njit(fastmath=True)
def _process_noise_gate(samples, threshold_lin, att_coeff, rel_coeff, env_state):
    """
    Zero-latency adaptive noise gate with smooth attack/release envelope.
    Avoids clicks/pops by applying continuous gain smoothing.
    """
    n = len(samples)
    out = np.empty(n, dtype=np.float32)
    curr_env = env_state
    
    for i in range(n):
        level = abs(samples[i])
        # Envelope follower
        if level > curr_env:
            curr_env = curr_env * att_coeff + level * (1.0 - att_coeff)
        else:
            curr_env = curr_env * rel_coeff + level * (1.0 - rel_coeff)
            
        # Target gain
        if curr_env < threshold_lin:
            # Below threshold: smooth reduction
            # Quadratic soft-knee fade
            ratio = (curr_env / (threshold_lin + 1e-9)) ** 2
            gain = min(1.0, max(0.0, ratio))
        else:
            gain = 1.0
            
        out[i] = samples[i] * gain
        
    return out, curr_env


@njit(fastmath=True)
def _process_compressor(samples, thresh_db, ratio, att_coeff, rel_coeff, makeup_lin, env_db):
    """
    Feed-forward vocal compressor with soft knee and makeup gain.
    Keeps monitored vocals steady, punchy, and prevents clipping.
    """
    n = len(samples)
    out = np.empty(n, dtype=np.float32)
    curr_env_db = env_db
    knee_width_db = 4.0
    
    for i in range(n):
        val = samples[i]
        level_lin = abs(val)
        level_db = 20.0 * math.log10(level_lin + 1e-6)
        
        # Envelope follower in dB
        if level_db > curr_env_db:
            curr_env_db = curr_env_db * att_coeff + level_db * (1.0 - att_coeff)
        else:
            curr_env_db = curr_env_db * rel_coeff + level_db * (1.0 - rel_coeff)
            
        # Gain computer with soft knee
        delta = curr_env_db - thresh_db
        if delta <= -knee_width_db / 2.0:
            gain_db = 0.0
        elif abs(delta) <= knee_width_db / 2.0:
            # Inside knee
            x = delta + knee_width_db / 2.0
            gain_db = ((1.0 / ratio - 1.0) * (x * x)) / (2.0 * knee_width_db)
        else:
            # Above knee
            gain_db = (1.0 / ratio - 1.0) * delta
            
        gain_lin = 10.0 ** (gain_db / 20.0) * makeup_lin
        out[i] = val * gain_lin
        
    return out, curr_env_db


@njit(fastmath=True)
def _soft_limit_stereo(l_samples, r_samples, ceiling=0.98):
    """
    Ear protection soft-clipping limiter.
    Ensures signal never painfully clips headphones or soundcards.
    """
    n = len(l_samples)
    out_l = np.empty(n, dtype=np.float32)
    out_r = np.empty(n, dtype=np.float32)
    
    for i in range(n):
        l = l_samples[i]
        r = r_samples[i]
        # Fast hyperbolic tangent soft saturator
        if abs(l) > ceiling:
            l = ceiling * math.tanh(l / ceiling)
        if abs(r) > ceiling:
            r = ceiling * math.tanh(r / ceiling)
        out_l[i] = l
        out_r[i] = r
        
    return out_l, out_r


# ---------------------------------------------------------
# FREEVERB STEREO STUDIO REVERB
# ---------------------------------------------------------

# Standard Schroeder-Moorer Freeverb comb & allpass delays (at 44.1kHz)
COMB_TUNINGS = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617]
ALLPASS_TUNINGS = [556, 441, 341, 225]
STEREO_SPREAD = 23

class StudioReverb:
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate
        self.scale = sample_rate / 44100.0
        
        # Parameters (0.0 to 1.0)
        self.enabled = False
        self.room_size = 0.75
        self.damping = 0.25
        self.wet = 0.25
        self.dry = 1.0
        self.width = 1.0
        
        self._init_buffers()
        
    def _init_buffers(self):
        self.comb_lens_l = [int(t * self.scale) for t in COMB_TUNINGS]
        self.comb_lens_r = [int((t + STEREO_SPREAD) * self.scale) for t in COMB_TUNINGS]
        
        self.comb_bufs_l = [np.zeros(length + 64, dtype=np.float32) for length in self.comb_lens_l]
        self.comb_bufs_r = [np.zeros(length + 64, dtype=np.float32) for length in self.comb_lens_r]
        self.comb_idxs_l = [0] * 8
        self.comb_idxs_r = [0] * 8
        self.comb_damps_l = [0.0] * 8
        self.comb_damps_r = [0.0] * 8
        
        self.allpass_lens_l = [int(t * self.scale) for t in ALLPASS_TUNINGS]
        self.allpass_lens_r = [int((t + STEREO_SPREAD) * self.scale) for t in ALLPASS_TUNINGS]
        
        self.allpass_bufs_l = [np.zeros(length + 64, dtype=np.float32) for length in self.allpass_lens_l]
        self.allpass_bufs_r = [np.zeros(length + 64, dtype=np.float32) for length in self.allpass_lens_r]
        self.allpass_idxs_l = [0] * 4
        self.allpass_idxs_r = [0] * 4

    def update_sample_rate(self, sample_rate):
        if self.sample_rate != sample_rate:
            self.sample_rate = sample_rate
            self.scale = sample_rate / 44100.0
            self._init_buffers()

    def process(self, in_l, in_r):
        if not self.enabled or self.wet <= 0.001:
            return in_l, in_r
            
        n = len(in_l)
        # Scaled feedback: room_size maps to [0.7, 0.98]
        feedback = 0.7 + self.room_size * 0.28
        damp = self.damping * 0.4
        
        mono_in = (in_l + in_r) * 0.5 * 0.015  # scaled input gain
        
        # Accumulate 8 parallel comb filters for Left and Right
        sum_l = np.zeros(n, dtype=np.float32)
        sum_r = np.zeros(n, dtype=np.float32)
        
        for k in range(8):
            out_c_l, self.comb_idxs_l[k], self.comb_damps_l[k] = _comb_filter_mono(
                self.comb_bufs_l[k], mono_in, feedback, damp, self.comb_lens_l[k], 
                self.comb_idxs_l[k], self.comb_damps_l[k]
            )
            out_c_r, self.comb_idxs_r[k], self.comb_damps_r[k] = _comb_filter_mono(
                self.comb_bufs_r[k], mono_in, feedback, damp, self.comb_lens_r[k], 
                self.comb_idxs_r[k], self.comb_damps_r[k]
            )
            sum_l += out_c_l
            sum_r += out_c_r
            
        # 4 series allpass filters
        ap_feedback = 0.5
        for k in range(4):
            sum_l, self.allpass_idxs_l[k] = _allpass_filter_mono(
                self.allpass_bufs_l[k], sum_l, ap_feedback, self.allpass_lens_l[k], self.allpass_idxs_l[k]
            )
            sum_r, self.allpass_idxs_r[k] = _allpass_filter_mono(
                self.allpass_bufs_r[k], sum_r, ap_feedback, self.allpass_lens_r[k], self.allpass_idxs_r[k]
            )
            
        # Stereo spread matrix & wet/dry mix
        wet1 = self.wet * (self.width * 0.5 + 0.5)
        wet2 = self.wet * ((1.0 - self.width) * 0.5)
        
        rev_l = sum_l * wet1 + sum_r * wet2
        rev_r = sum_r * wet1 + sum_l * wet2
        
        out_l = in_l * self.dry + rev_l
        out_r = in_r * self.dry + rev_r
        return out_l, out_r


# ---------------------------------------------------------
# ECHO / DELAY EFFECT
# ---------------------------------------------------------

class StudioEcho:
    def __init__(self, sample_rate=48000, max_delay_sec=2.0):
        self.sample_rate = sample_rate
        self.max_len = int(sample_rate * max_delay_sec)
        
        self.enabled = False
        self.delay_ms = 280.0     # Default musical slapback/echo
        self.feedback = 0.40      # 0.0 to 0.90
        self.damping = 0.30       # Warm tape high-frequency rolloff
        self.wet = 0.30
        self.dry = 1.0
        self.pingpong = True      # Stereo bounce
        
        self.buf_l = np.zeros(self.max_len, dtype=np.float32)
        self.buf_r = np.zeros(self.max_len, dtype=np.float32)
        self.idx_l = 0
        self.idx_r = 0
        self.damp_l = 0.0
        self.damp_r = 0.0
        
    def update_sample_rate(self, sample_rate):
        if self.sample_rate != sample_rate:
            self.sample_rate = sample_rate
            self.max_len = int(sample_rate * 2.0)
            self.buf_l = np.zeros(self.max_len, dtype=np.float32)
            self.buf_r = np.zeros(self.max_len, dtype=np.float32)
            self.idx_l = 0
            self.idx_r = 0

    def process(self, in_l, in_r):
        if not self.enabled or self.wet <= 0.001:
            return in_l, in_r
            
        delay_len_l = int(self.sample_rate * (self.delay_ms / 1000.0))
        delay_len_l = max(1, min(self.max_len - 1, delay_len_l))
        
        # Ping-pong offset
        if self.pingpong:
            delay_len_r = int(delay_len_l * 1.5)
            if delay_len_r >= self.max_len:
                delay_len_r = int(delay_len_l * 0.75)
        else:
            delay_len_r = delay_len_l
            
        out_l, out_r, self.idx_l, self.idx_r, self.damp_l, self.damp_r = _process_echo_stereo(
            self.buf_l, self.buf_r, in_l, in_r,
            delay_len_l, delay_len_r,
            self.feedback, self.damping,
            self.wet, self.dry, self.pingpong,
            self.idx_l, self.idx_r, self.damp_l, self.damp_r
        )
        return out_l, out_r


# ---------------------------------------------------------
# EQUALIZER (3-BAND PARAMETRIC)
# ---------------------------------------------------------

class VocalEqualizer:
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate
        self.enabled = True
        self.low_gain_db = 0.0    # 120 Hz Low Shelf (Bass/Warmth)
        self.mid_gain_db = 0.0    # 2500 Hz Peaking (Vocal Body/Presence)
        self.high_gain_db = 0.0   # 10000 Hz High Shelf (Air/Clarity)
        self._build_filters()
        
    def _build_filters(self):
        fs = self.sample_rate
        # Low shelf at 120 Hz
        # Biquad approximation using 2nd order Butterworth shelving or peaking
        # SciPy sos design:
        self.sos_low = self._design_shelf(120.0, self.low_gain_db, 'low')
        self.sos_mid = self._design_peaking(2500.0, self.mid_gain_db, Q=1.2)
        self.sos_high = self._design_shelf(10000.0, self.high_gain_db, 'high')
        
        self.zi_l_low = signal.sosfilt_zi(self.sos_low)
        self.zi_r_low = signal.sosfilt_zi(self.sos_low)
        self.zi_l_mid = signal.sosfilt_zi(self.sos_mid)
        self.zi_r_mid = signal.sosfilt_zi(self.sos_mid)
        self.zi_l_high = signal.sosfilt_zi(self.sos_high)
        self.zi_r_high = signal.sosfilt_zi(self.sos_high)

    def _design_shelf(self, freq, gain_db, shelf_type='low'):
        if abs(gain_db) < 0.1:
            # Passthrough
            return np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
        gain_lin = 10.0 ** (gain_db / 40.0)  # square root of A
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * math.pi * freq / self.sample_rate
        cos_w0 = math.cos(w0)
        sin_w0 = math.sin(w0)
        slope = 1.0
        alpha = sin_w0 / 2.0 * math.sqrt((A + 1.0 / A) * (1.0 / slope - 1.0) + 2.0)
        
        if shelf_type == 'low':
            b0 = A * ((A + 1.0) - (A - 1.0) * cos_w0 + 2.0 * math.sqrt(A) * alpha)
            b1 = 2.0 * A * ((A - 1.0) - (A + 1.0) * cos_w0)
            b2 = A * ((A + 1.0) - (A - 1.0) * cos_w0 - 2.0 * math.sqrt(A) * alpha)
            a0 = (A + 1.0) + (A - 1.0) * cos_w0 + 2.0 * math.sqrt(A) * alpha
            a1 = -2.0 * ((A - 1.0) + (A + 1.0) * cos_w0)
            a2 = (A + 1.0) + (A - 1.0) * cos_w0 - 2.0 * math.sqrt(A) * alpha
        else: # high shelf
            b0 = A * ((A + 1.0) + (A - 1.0) * cos_w0 + 2.0 * math.sqrt(A) * alpha)
            b1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cos_w0)
            b2 = A * ((A + 1.0) + (A - 1.0) * cos_w0 - 2.0 * math.sqrt(A) * alpha)
            a0 = (A + 1.0) - (A - 1.0) * cos_w0 + 2.0 * math.sqrt(A) * alpha
            a1 = 2.0 * ((A - 1.0) - (A + 1.0) * cos_w0)
            a2 = (A + 1.0) - (A - 1.0) * cos_w0 - 2.0 * math.sqrt(A) * alpha
            
        sos = np.array([[b0/a0, b1/a0, b2/a0, 1.0, a1/a0, a2/a0]], dtype=np.float32)
        return sos

    def _design_peaking(self, freq, gain_db, Q=1.0):
        if abs(gain_db) < 0.1:
            return np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * math.pi * freq / self.sample_rate
        alpha = math.sin(w0) / (2.0 * Q)
        cos_w0 = math.cos(w0)
        
        b0 = 1.0 + alpha * A
        b1 = -2.0 * cos_w0
        b2 = 1.0 - alpha * A
        a0 = 1.0 + alpha / A
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha / A
        
        sos = np.array([[b0/a0, b1/a0, b2/a0, 1.0, a1/a0, a2/a0]], dtype=np.float32)
        return sos

    def update_gains(self, low_db, mid_db, high_db):
        if (self.low_gain_db != low_db or 
            self.mid_gain_db != mid_db or 
            self.high_gain_db != high_db):
            self.low_gain_db = low_db
            self.mid_gain_db = mid_db
            self.high_gain_db = high_db
            self._build_filters()

    def process(self, in_l, in_r):
        if not self.enabled:
            return in_l, in_r
            
        out_l, self.zi_l_low = signal.sosfilt(self.sos_low, in_l, zi=self.zi_l_low)
        out_r, self.zi_r_low = signal.sosfilt(self.sos_low, in_r, zi=self.zi_r_low)
        
        out_l, self.zi_l_mid = signal.sosfilt(self.sos_mid, out_l, zi=self.zi_l_mid)
        out_r, self.zi_r_mid = signal.sosfilt(self.sos_mid, out_r, zi=self.zi_r_mid)
        
        out_l, self.zi_l_high = signal.sosfilt(self.sos_high, out_l, zi=self.zi_l_high)
        out_r, self.zi_r_high = signal.sosfilt(self.sos_high, out_r, zi=self.zi_r_high)
        
        return out_l.astype(np.float32), out_r.astype(np.float32)


# ---------------------------------------------------------
# NOISE SUPPRESSION & RUMBLE FILTER
# ---------------------------------------------------------

class NoiseFilter:
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate
        # 80 Hz Low-cut / Rumble filter
        self.rumble_filter_enabled = True
        self.sos_rumble = signal.butter(2, 80.0, 'hp', fs=sample_rate, output='sos')
        self.zi_l_rumble = signal.sosfilt_zi(self.sos_rumble)
        self.zi_r_rumble = signal.sosfilt_zi(self.sos_rumble)
        
        # Real-time Adaptive Noise Gate
        self.gate_enabled = True
        self.threshold_db = -50.0   # dB
        self.attack_ms = 4.0        # ms
        self.release_ms = 70.0      # ms
        self.env_state_l = 0.0
        self.env_state_r = 0.0
        
        # Real-time Spectral Noise Suppressor
        self.denoise_enabled = False
        self.denoise_strength = 0.50 # 0.0 to 1.0
        self.noise_profile = None
        self._init_spectral_denoiser()
        
    def _init_spectral_denoiser(self):
        # 512-point FFT circular overlap buffer for low-latency spectral gating
        self.n_fft = 512
        self.hop = 256
        self.in_buf = np.zeros(self.n_fft, dtype=np.float32)
        self.out_buf = np.zeros(self.n_fft, dtype=np.float32)
        self.window = np.hanning(self.n_fft).astype(np.float32)
        self.noise_floor = np.ones(self.n_fft // 2 + 1, dtype=np.float32) * 1e-4

    def update_sample_rate(self, sample_rate):
        if self.sample_rate != sample_rate:
            self.sample_rate = sample_rate
            self.sos_rumble = signal.butter(2, 80.0, 'hp', fs=sample_rate, output='sos')
            self.zi_l_rumble = signal.sosfilt_zi(self.sos_rumble)
            self.zi_r_rumble = signal.sosfilt_zi(self.sos_rumble)

    def process(self, in_l, in_r):
        # 1. Rumble HPF
        if self.rumble_filter_enabled:
            in_l, self.zi_l_rumble = signal.sosfilt(self.sos_rumble, in_l, zi=self.zi_l_rumble)
            in_r, self.zi_r_rumble = signal.sosfilt(self.sos_rumble, in_r, zi=self.zi_r_rumble)
            
        # 2. Spectral noise reduction (if active)
        if self.denoise_enabled and self.denoise_strength > 0.01:
            in_l, in_r = self._apply_spectral_denoise(in_l, in_r)
            
        # 3. Noise Gate (Zero latency envelope follower)
        if self.gate_enabled:
            thresh_lin = 10.0 ** (self.threshold_db / 20.0)
            att_coeff = math.exp(-1.0 / (max(0.1, self.attack_ms) * 0.001 * self.sample_rate))
            rel_coeff = math.exp(-1.0 / (max(1.0, self.release_ms) * 0.001 * self.sample_rate))
            
            in_l, self.env_state_l = _process_noise_gate(
                in_l.astype(np.float32), thresh_lin, att_coeff, rel_coeff, self.env_state_l
            )
            in_r, self.env_state_r = _process_noise_gate(
                in_r.astype(np.float32), thresh_lin, att_coeff, rel_coeff, self.env_state_r
            )
            
        return in_l.astype(np.float32), in_r.astype(np.float32)

    def _apply_spectral_denoise(self, in_l, in_r):
        # Fast FFT spectral gating on mono representation
        n = len(in_l)
        if n > self.hop:
            return in_l, in_r
            
        # Shift buffer
        self.in_buf[:-n] = self.in_buf[n:]
        self.in_buf[-n:] = (in_l + in_r) * 0.5
        
        # FFT
        windowed = self.in_buf * self.window
        spec = np.fft.rfft(windowed)
        mag = np.abs(spec)
        phase = np.angle(spec)
        
        # Dynamic noise floor update (tracking minimum energy in quiet passages)
        self.noise_floor = np.minimum(self.noise_floor * 1.002, mag)
        
        # Spectral subtraction gain mask with over-subtraction factor
        alpha = 1.0 + self.denoise_strength * 2.0
        subtracted = mag - alpha * self.noise_floor
        gain = np.maximum(0.05, subtracted / (mag + 1e-9))
        
        # Reconstruct
        clean_spec = (mag * gain) * np.exp(1j * phase)
        cleaned = np.fft.irfft(clean_spec).astype(np.float32)
        
        # Overlap-add
        out_chunk = cleaned[-n:]
        # Blend with input based on strength
        wet = self.denoise_strength
        dry = 1.0 - wet
        res_l = in_l * dry + out_chunk * wet
        res_r = in_r * dry + out_chunk * wet
        return res_l, res_r


# ---------------------------------------------------------
# VOCAL COMPRESSOR & EAR PROTECTION
# ---------------------------------------------------------

class VocalDynamics:
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate
        self.comp_enabled = True
        self.threshold_db = -18.0
        self.ratio = 3.5
        self.attack_ms = 8.0
        self.release_ms = 120.0
        self.makeup_gain_db = 2.0
        
        self.env_db_l = -80.0
        self.env_db_r = -80.0
        
    def process(self, in_l, in_r):
        if self.comp_enabled:
            att_coeff = math.exp(-1.0 / (max(0.1, self.attack_ms) * 0.001 * self.sample_rate))
            rel_coeff = math.exp(-1.0 / (max(1.0, self.release_ms) * 0.001 * self.sample_rate))
            makeup_lin = 10.0 ** (self.makeup_gain_db / 20.0)
            
            in_l, self.env_db_l = _process_compressor(
                in_l, self.threshold_db, self.ratio, att_coeff, rel_coeff, makeup_lin, self.env_db_l
            )
            in_r, self.env_db_r = _process_compressor(
                in_r, self.threshold_db, self.ratio, att_coeff, rel_coeff, makeup_lin, self.env_db_r
            )
            
        # Ear-protection soft limiter (-0.2 dBFS)
        out_l, out_r = _soft_limit_stereo(in_l, in_r, ceiling=0.98)
        return out_l, out_r


# ---------------------------------------------------------
# FULL MASTER DSP PIPELINE
# ---------------------------------------------------------

class MasterDSPPipeline:
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate
        
        # Gain stages
        self.input_gain = 1.0     # 0.0 to 4.0 (+12 dB)
        self.input_muted = False
        self.output_volume = 1.0  # 0.0 to 1.5
        self.output_muted = False
        
        # Modules
        self.noise_filter = NoiseFilter(sample_rate)
        self.eq = VocalEqualizer(sample_rate)
        self.echo = StudioEcho(sample_rate)
        self.reverb = StudioReverb(sample_rate)
        self.dynamics = VocalDynamics(sample_rate)
        
        # Live metering variables
        self.input_peak = 0.0
        self.input_rms = 0.0
        self.output_peak = 0.0
        self.output_rms = 0.0

    def set_sample_rate(self, sample_rate):
        if self.sample_rate != sample_rate:
            self.sample_rate = sample_rate
            self.noise_filter.update_sample_rate(sample_rate)
            self.echo.update_sample_rate(sample_rate)
            self.reverb.update_sample_rate(sample_rate)
            self.eq.sample_rate = sample_rate
            self.eq._build_filters()
            self.dynamics.sample_rate = sample_rate

    def process(self, in_data):
        """
        Process an input audio block.
        in_data: numpy array shape (N, channels) or (N,)
        Returns: processed stereo numpy array shape (N, 2)
        """
        # 1. Normalize input shape to stereo float32
        if in_data.ndim == 1:
            in_l = in_data.astype(np.float32)
            in_r = in_data.astype(np.float32)
        elif in_data.shape[1] == 1:
            in_l = in_data[:, 0].astype(np.float32)
            in_r = in_data[:, 0].astype(np.float32)
        else:
            in_l = in_data[:, 0].astype(np.float32)
            in_r = in_data[:, 1].astype(np.float32)
            
        # Metering: Raw input level
        raw_peak = max(np.max(np.abs(in_l)), np.max(np.abs(in_r)))
        raw_rms = math.sqrt((np.mean(in_l**2) + np.mean(in_r**2)) * 0.5)
        self.input_peak = raw_peak
        self.input_rms = raw_rms
        
        # Input Gain & Mute
        if self.input_muted:
            in_l = np.zeros_like(in_l)
            in_r = np.zeros_like(in_r)
        else:
            in_l *= self.input_gain
            in_r *= self.input_gain
            
        # 2. Noise suppression, HPF & Gate
        in_l, in_r = self.noise_filter.process(in_l, in_r)
        
        # 3. 3-Band Studio Vocal EQ
        in_l, in_r = self.eq.process(in_l, in_r)
        
        # 4. Echo / Delay
        in_l, in_r = self.echo.process(in_l, in_r)
        
        # 5. Studio Reverb
        in_l, in_r = self.reverb.process(in_l, in_r)
        
        # 6. Vocal Dynamics & Limiter
        in_l, in_r = self.dynamics.process(in_l, in_r)
        
        # 7. Output Volume & Mute
        if self.output_muted:
            out_l = np.zeros_like(in_l)
            out_r = np.zeros_like(in_r)
        else:
            out_l = in_l * self.output_volume
            out_r = in_r * self.output_volume
            
        # Output Metering
        out_peak = max(np.max(np.abs(out_l)), np.max(np.abs(out_r)))
        out_rms = math.sqrt((np.mean(out_l**2) + np.mean(out_r**2)) * 0.5)
        self.output_peak = out_peak
        self.output_rms = out_rms
        
        # Pack into interleaved stereo (N, 2)
        return np.column_stack((out_l, out_r))
