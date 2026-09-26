# 🎙️ SingerPro — Live Vocal Monitoring & Effects Studio

A high-performance Windows native application for live microphone monitoring, vocal processing, and low-latency studio effects. Built for singers, streamers, podcasters, and voice actors who need real-time zero-delay sidetone feedback with studio-quality DSP effects.

![SingerPro Banner](https://img.shields.io/badge/Platform-Windows%2011%20%7C%2010-0078D6?logo=windows)
![Audio Engine](https://img.shields.io/badge/Audio-WASAPI%20Low%20Latency-10b981)
![DSP Engine](https://img.shields.io/badge/DSP-Numba%20JIT%20Accelerated-38bdf8)
![GUI](https://img.shields.io/badge/UI-CustomTkinter%20Dark%20Fluent-f59e0b)

---

## ✨ Features

### 1. ⚡ Ultra-Low Latency Audio Monitoring

- **Windows WASAPI Support**: Direct interface with Windows Audio Session API for sub-5ms roundtrip latency without needing ASIO.
- **Selectable Buffer Sizes**:
  - `128 samples` (~2.7 ms) — Ultra Low (fastest response for singing)
  - `256 samples` (~5.3 ms) — Fast / Recommended (optimal stability)
  - `512 samples` (~10.7 ms) — Balanced
  - `1024 samples` (~21.3 ms) — Safe / Legacy
- **Flexible Device Routing**: Choose any microphone for input and any headphones or speakers for output. Supports unified duplex streaming and dual-stream fallback with lock-free jitter buffers.
- **Live Latency & Status Readout**: Real-time measurement of input, output, and DSP roundtrip latency in milliseconds.

### 2. 🌌 Spatial Effects (Echo & Reverb)

- **Warm Tape Echo / Delay**:
  - Millisecond-accurate delay time (20 ms to 800 ms) with quick shortcuts (Slapback 110ms, Medium 260ms, Long 420ms).
  - Feedback control (0% to 85% repeats).
  - High-frequency tape damping for warm analog decays.
  - Stereo Ping-Pong bounce option.
  - Wet / Dry mix blend.
- **High-Definition Studio Reverb**:
  - Schroeder-Moorer 8-Comb + 4-AllPass Freeverb architecture.
  - Room Size control (Vocal booth to Cathedral).
  - High-frequency absorption damping.
  - Stereo Spatial Width control (Mono to Ultra-Wide).
  - Wet / Dry mix blend.

### 3. 🛡️ Multi-Stage Noise Cancellation & Cleaning

- **80 Hz Low-Cut Rumble Filter**: 2nd order Butterworth high-pass filter that eliminates desk bumps, mic handling noise, and 50/60 Hz electrical hum.
- **Adaptive Vocal Noise Gate (Zero-Latency)**: High-speed envelope follower with soft-knee fade that completely silences room fan noise and breathing pauses when not singing.
- **Spectral Noise Suppressor**: Real-time spectral gating designed to eliminate continuous background noise like computer fans and air conditioning hum.

### 4. 🎚️ Studio Vocal Dynamics & EQ

- **3-Band Parametric Vocal Equalizer**:
  - **Low / Warmth Shelf (120 Hz)**: Adds vocal body or trims proximity mud ($\pm 12 \text{ dB}$).
  - **Mid Presence (2.5 kHz)**: Shapes vocal clarity and speech intelligibility ($\pm 12 \text{ dB}$).
  - **Air Sheen Shelf (10 kHz)**: Studio top-end brightness and sparkle ($\pm 12 \text{ dB}$).
- **Vocal Compressor**:
  - Feed-forward soft-knee compressor to prevent volume spikes when projecting loudly into the mic.
  - Adjustable Threshold, Ratio (1:1 to 8:1), and Makeup Gain.
- **Ear-Protection Limiter**: Built-in soft saturation limiter at -0.2 dBFS prevents acoustic feedback loops or accidental loud pops from hurting your ears.

### 5. 📊 Real-Time Oscilloscope & Metering

- **Glowing Oscilloscope**: Smooth Canvas-rendered live waveform with underlying FFT frequency spectrum bars.
- **Stereo VU Meters**: Fast peak and RMS meters for Mic Input and Output Monitor with clip detection LEDs.

### 6. 📁 Factory Presets & Custom Profiles

- **Built-in Presets**:
  - 🎙️ Clean Studio Mic
  - 🎤 Warm Pop / Ballad Vocal
  - 🏟️ Concert Arena / Stadium
  - 🎸 Slapback Rock Vocal
  - 📻 Broadcast / Podcast Host
  - 🌌 Dreamy Ambient Vocal
  - ⚡ Raw Direct Monitor (Bypass)
- **JSON Export & Import**: Save your custom vocal FX chains and load them anytime.

### 7. 🔴 Live Practice Session Recorder

- Record the monitored audio output directly to high-fidelity 16-bit PCM `.wav` files.
- Thread-safe background writer guarantees zero audio stuttering during recording.
- One-click button to open the `recordings/` folder.

---

## 🚀 Quick Start

### Option A: 1-Click Launch

Double-click `run_singerpro.bat` or run:

```bash
python main.py
```

### Option B: Build Standalone Windows Executable (.exe)

Run the build script:

```bash
build_exe.bat
```

The compiled standalone executable will be created in `dist\SingerPro\SingerPro.exe`.

---

## 🎧 Latency Optimization Tips for Singers

1. **Use Headphones**: Always wear closed-back headphones while monitoring to avoid acoustic feedback loops into the microphone.
2. **Select WASAPI**: Choose the `[Windows WASAPI]` driver for both your microphone and headphones for the lowest latency.
3. **Buffer Size**:
   - Start with **128 samples** or **256 samples**.
   - If your system experiences crackles or buffer underruns, increase the buffer to **512 samples**.
4. **Noise Gate**:
   - Adjust the Gate Threshold until background room hiss is completely silent when you stop speaking, but opens effortlessly as soon as you whisper or sing.

---

## 🏗️ Architecture & Technology Stack

- **Audio I/O**: `sounddevice` / PortAudio (WASAPI, DirectSound, MME)
- **DSP Engine**: Numba JIT (compiles Python DSP kernels to native machine code executing in microseconds) & `scipy.signal`
- **GUI**: `customtkinter` with Windows 11 Fluent dark theme and Per-Monitor High-DPI scaling
- **Threading**: Dedicated lock-free real-time audio callback thread decoupled from UI rendering
