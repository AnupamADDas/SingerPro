"""
SingerPro - Modern Native Windows Live Vocal Monitoring & Effects Studio UI
Built with CustomTkinter for a slick Windows 11 Fluent dark experience.
"""

import os
import sys
import math
import time
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import numpy as np

from dsp_engine import MasterDSPPipeline
from audio_engine import AudioEngine
from presets import FACTORY_PRESETS, apply_preset_to_pipeline, export_preset_file, import_preset_file

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class SingerProApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("SingerPro — Live Vocal Monitor & Studio Effects")
        self.geometry("1180x860")
        self.minsize(1040, 780)
        
        # Initialize Audio Engine & DSP
        self.dsp = MasterDSPPipeline(sample_rate=48000)
        self.engine = AudioEngine(self.dsp)
        
        # Cached device lists
        self.input_devices = []
        self.output_devices = []
        
        # Visualizer animation state
        self._vis_running = True
        
        # Build UI
        self._setup_layout()
        self._refresh_audio_devices()
        
        # Load default preset ("Warm Pop / Ballad Vocal")
        self._load_preset_by_name("🎤 Warm Pop / Ballad Vocal")
        
        # Start periodic UI update timer (VU meters + waveform)
        self.after(40, self._update_meters_and_vis)
        
        # Clean shutdown handler
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_layout(self):
        # Main Grid Layout:
        # Row 0: Header with Status, Latency & Big Start/Stop Button
        # Row 1: Visualizer & Live VU Meters Section
        # Row 2: Main Workspace (Left: Hardware & Master, Right: FX Studio Tabs)
        # Row 3: Bottom Status Bar
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_metering_and_visualizer()
        self._build_workspace()
        self._build_statusbar()

    # -------------------------------------------------------------
    # 1. HEADER BAR
    # -------------------------------------------------------------
    def _build_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="#181920", corner_radius=10, height=75)
        header_frame.grid(row=0, column=0, padx=16, pady=(12, 8), sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)

        # Branding
        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=18, pady=10, sticky="w")
        
        app_title = ctk.CTkLabel(
            title_box, 
            text="🎙️ SINGERPRO", 
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#38bdf8"
        )
        app_title.pack(anchor="w")
        
        app_sub = ctk.CTkLabel(
            title_box, 
            text="Live Ultra-Low Latency Vocal Studio & FX", 
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        )
        app_sub.pack(anchor="w")

        # Live Latency & Engine Badges
        badge_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        badge_box.grid(row=0, column=1, padx=10, pady=10)

        self.lbl_status_badge = ctk.CTkLabel(
            badge_box,
            text="⚪ IDLE",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#334155",
            text_color="#cbd5e1",
            corner_radius=6,
            padx=12,
            pady=4
        )
        self.lbl_status_badge.pack(side="left", padx=6)

        self.lbl_latency_badge = ctk.CTkLabel(
            badge_box,
            text="⚡ Est. Latency: -- ms",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#1e293b",
            text_color="#38bdf8",
            corner_radius=6,
            padx=12,
            pady=4
        )
        self.lbl_latency_badge.pack(side="left", padx=6)

        self.lbl_limiter_badge = ctk.CTkLabel(
            badge_box,
            text="🛡️ Ear Protect Active",
            font=ctk.CTkFont(size=11),
            fg_color="#064e3b",
            text_color="#6ee7b7",
            corner_radius=6,
            padx=10,
            pady=4
        )
        self.lbl_limiter_badge.pack(side="left", padx=6)

        # Action Buttons (Start/Stop + Recording)
        btn_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_box.grid(row=0, column=2, padx=18, pady=10, sticky="e")

        self.btn_record = ctk.CTkButton(
            btn_box,
            text="🔴 Record",
            width=100,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._toggle_recording
        )
        self.btn_record.pack(side="left", padx=(0, 10))

        self.btn_monitor_toggle = ctk.CTkButton(
            btn_box,
            text="▶ START MONITORING",
            width=190,
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self._toggle_monitoring
        )
        self.btn_monitor_toggle.pack(side="left")

    # -------------------------------------------------------------
    # 2. REAL-TIME OSCILLOSCOPE & VU METERS
    # -------------------------------------------------------------
    def _build_metering_and_visualizer(self):
        vis_frame = ctk.CTkFrame(self, fg_color="#111318", corner_radius=10, height=115)
        vis_frame.grid(row=1, column=0, padx=16, pady=4, sticky="ew")
        vis_frame.grid_columnconfigure(1, weight=1)

        # Input Meter Column
        in_meter_box = ctk.CTkFrame(vis_frame, fg_color="transparent", width=140)
        in_meter_box.grid(row=0, column=0, padx=16, pady=8, sticky="ns")
        
        lbl_in = ctk.CTkLabel(in_meter_box, text="MIC INPUT", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8")
        lbl_in.pack(anchor="w")

        self.bar_in_peak = ctk.CTkProgressBar(in_meter_box, width=130, height=12, progress_color="#10b981", fg_color="#1e293b")
        self.bar_in_peak.pack(pady=(4, 2))
        self.bar_in_peak.set(0.0)

        self.lbl_in_db = ctk.CTkLabel(in_meter_box, text="-∞ dB", font=ctk.CTkFont(size=11), text_color="#cbd5e1")
        self.lbl_in_db.pack(anchor="w")

        # Center: Waveform & Spectrum Oscilloscope Canvas
        canvas_box = ctk.CTkFrame(vis_frame, fg_color="#0a0c10", corner_radius=8)
        canvas_box.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")
        canvas_box.grid_columnconfigure(0, weight=1)
        canvas_box.grid_rowconfigure(0, weight=1)

        self.vis_canvas = tk.Canvas(
            canvas_box,
            bg="#090b10",
            highlightthickness=0,
            height=90
        )
        self.vis_canvas.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        # Output Meter Column
        out_meter_box = ctk.CTkFrame(vis_frame, fg_color="transparent", width=140)
        out_meter_box.grid(row=0, column=2, padx=16, pady=8, sticky="ns")

        lbl_out = ctk.CTkLabel(out_meter_box, text="OUTPUT MONITOR", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8")
        lbl_out.pack(anchor="w")

        self.bar_out_peak = ctk.CTkProgressBar(out_meter_box, width=130, height=12, progress_color="#38bdf8", fg_color="#1e293b")
        self.bar_out_peak.pack(pady=(4, 2))
        self.bar_out_peak.set(0.0)

        self.lbl_out_db = ctk.CTkLabel(out_meter_box, text="-∞ dB", font=ctk.CTkFont(size=11), text_color="#cbd5e1")
        self.lbl_out_db.pack(anchor="w")

    # -------------------------------------------------------------
    # 3. MAIN WORKSPACE (LEFT: HARDWARE, RIGHT: FX STUDIO)
    # -------------------------------------------------------------
    def _build_workspace(self):
        work_frame = ctk.CTkFrame(self, fg_color="transparent")
        work_frame.grid(row=2, column=0, padx=16, pady=6, sticky="nsew")
        work_frame.grid_columnconfigure(0, weight=4)
        work_frame.grid_columnconfigure(1, weight=7)
        work_frame.grid_rowconfigure(0, weight=1)

        self._build_left_hardware_panel(work_frame)
        self._build_right_fx_panel(work_frame)

    # ----------------------- LEFT PANEL --------------------------
    def _build_left_hardware_panel(self, parent):
        left_box = ctk.CTkScrollableFrame(parent, fg_color="#181920", corner_radius=10, label_text="🎧 Audio Devices & Latency Setup")
        left_box.grid(row=0, column=0, padx=(0, 8), pady=0, sticky="nsew")

        # 1. Host API Filter
        lbl_api = ctk.CTkLabel(left_box, text="Preferred Audio Driver:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#cbd5e1")
        lbl_api.pack(anchor="w", padx=12, pady=(8, 2))

        self.opt_driver_filter = ctk.CTkSegmentedButton(
            left_box,
            values=["WASAPI (Fast)", "All Drivers", "DirectSound", "MME"],
            command=self._on_driver_filter_changed
        )
        self.opt_driver_filter.set("WASAPI (Fast)")
        self.opt_driver_filter.pack(fill="x", padx=12, pady=(0, 10))

        # 2. Input Device (Mic)
        row_in = ctk.CTkFrame(left_box, fg_color="transparent")
        row_in.pack(fill="x", padx=12, pady=(4, 2))
        
        lbl_in_dev = ctk.CTkLabel(row_in, text="Microphone (Input):", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_in_dev.pack(side="left")
        
        btn_refresh = ctk.CTkButton(row_in, text="🔄 Refresh", width=70, height=22, font=ctk.CTkFont(size=11), command=self._refresh_audio_devices)
        btn_refresh.pack(side="right")

        self.combo_input = ctk.CTkComboBox(left_box, values=["Detecting..."], height=32, state="readonly", command=self._on_device_selection_changed)
        self.combo_input.pack(fill="x", padx=12, pady=(0, 10))

        # 3. Output Device (Headphones)
        lbl_out_dev = ctk.CTkLabel(left_box, text="Headphones / Speakers (Output):", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_out_dev.pack(anchor="w", padx=12, pady=(4, 2))

        self.combo_output = ctk.CTkComboBox(left_box, values=["Detecting..."], height=32, state="readonly", command=self._on_device_selection_changed)
        self.combo_output.pack(fill="x", padx=12, pady=(0, 12))

        # 4. Latency / Buffer Size
        lbl_buf = ctk.CTkLabel(left_box, text="Buffer Size (Latency Control):", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_buf.pack(anchor="w", padx=12, pady=(2, 2))

        self.combo_buffer = ctk.CTkComboBox(
            left_box,
            values=[
                "128 samples (~2.7 ms) - Ultra Low",
                "256 samples (~5.3 ms) - Fast (Recommended)",
                "512 samples (~10.7 ms) - Balanced",
                "1024 samples (~21.3 ms) - Safe"
            ],
            height=30,
            state="readonly",
            command=self._on_buffer_changed
        )
        self.combo_buffer.set("256 samples (~5.3 ms) - Fast (Recommended)")
        self.combo_buffer.pack(fill="x", padx=12, pady=(0, 10))

        # 5. Sample Rate
        lbl_sr = ctk.CTkLabel(left_box, text="Sample Rate:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_sr.pack(anchor="w", padx=12, pady=(2, 2))

        self.combo_samplerate = ctk.CTkComboBox(
            left_box,
            values=["48000 Hz (Studio Standard)", "44100 Hz (CD Audio)", "96000 Hz (High Res)"],
            height=30,
            state="readonly",
            command=self._on_samplerate_changed
        )
        self.combo_samplerate.set("48000 Hz (Studio Standard)")
        self.combo_samplerate.pack(fill="x", padx=12, pady=(0, 14))

        # Divider
        sep = ctk.CTkProgressBar(left_box, height=2, fg_color="#334155", progress_color="#334155")
        sep.set(1.0)
        sep.pack(fill="x", padx=12, pady=8)

        # 6. Mic Input Gain Stage
        lbl_gain_header = ctk.CTkLabel(left_box, text="Gain & Volume Controls", font=ctk.CTkFont(size=13, weight="bold"), text_color="#38bdf8")
        lbl_gain_header.pack(anchor="w", padx=12, pady=(4, 6))

        box_gain = ctk.CTkFrame(left_box, fg_color="#111318", corner_radius=8)
        box_gain.pack(fill="x", padx=12, pady=(0, 10))

        row_gain = ctk.CTkFrame(box_gain, fg_color="transparent")
        row_gain.pack(fill="x", padx=10, pady=(6, 2))
        lbl_g = ctk.CTkLabel(row_gain, text="Mic Input Gain:", font=ctk.CTkFont(size=12))
        lbl_g.pack(side="left")
        self.lbl_gain_val = ctk.CTkLabel(row_gain, text="1.00x (0 dB)", font=ctk.CTkFont(size=11), text_color="#38bdf8")
        self.lbl_gain_val.pack(side="right")

        self.slider_input_gain = ctk.CTkSlider(box_gain, from_=0.0, to=3.0, number_of_steps=60, command=self._on_input_gain_slider)
        self.slider_input_gain.set(1.0)
        self.slider_input_gain.pack(fill="x", padx=10, pady=(0, 6))

        self.chk_mic_mute = ctk.CTkCheckBox(box_gain, text="Mute Microphone", font=ctk.CTkFont(size=11), command=self._on_mic_mute_toggled)
        self.chk_mic_mute.pack(anchor="w", padx=10, pady=(0, 8))

        # 7. Monitor Output Volume Stage
        box_vol = ctk.CTkFrame(left_box, fg_color="#111318", corner_radius=8)
        box_vol.pack(fill="x", padx=12, pady=(0, 10))

        row_vol = ctk.CTkFrame(box_vol, fg_color="transparent")
        row_vol.pack(fill="x", padx=10, pady=(6, 2))
        lbl_v = ctk.CTkLabel(row_vol, text="Monitor Output Volume:", font=ctk.CTkFont(size=12))
        lbl_v.pack(side="left")
        self.lbl_vol_val = ctk.CTkLabel(row_vol, text="100%", font=ctk.CTkFont(size=11), text_color="#38bdf8")
        self.lbl_vol_val.pack(side="right")

        self.slider_output_vol = ctk.CTkSlider(box_vol, from_=0.0, to=1.5, number_of_steps=60, command=self._on_output_vol_slider)
        self.slider_output_vol.set(1.0)
        self.slider_output_vol.pack(fill="x", padx=10, pady=(0, 6))

        self.chk_out_mute = ctk.CTkCheckBox(box_vol, text="Mute Output Headphones", font=ctk.CTkFont(size=11), command=self._on_out_mute_toggled)
        self.chk_out_mute.pack(anchor="w", padx=10, pady=(0, 8))

    # ----------------------- RIGHT PANEL (TABS) -------------------
    def _build_right_fx_panel(self, parent):
        self.tabview = ctk.CTkTabview(parent, fg_color="#181920", corner_radius=10)
        self.tabview.grid(row=0, column=1, padx=(8, 0), pady=0, sticky="nsew")

        tab_spatial = self.tabview.add("🌌 Echo & Reverb")
        tab_noise = self.tabview.add("🛡️ Noise Cancellation")
        tab_eq_comp = self.tabview.add("🎚️ Studio EQ & Dynamics")
        tab_presets = self.tabview.add("📁 Presets & Recordings")

        self._build_spatial_tab(tab_spatial)
        self._build_noise_tab(tab_noise)
        self._build_eq_comp_tab(tab_eq_comp)
        self._build_presets_tab(tab_presets)

    # ------------------- TAB 1: ECHO & REVERB ---------------------
    def _build_spatial_tab(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        # --- ECHO / DELAY SECTION ---
        echo_card = ctk.CTkFrame(scroll, fg_color="#111318", corner_radius=10)
        echo_card.pack(fill="x", pady=(4, 12), padx=4)

        echo_hdr = ctk.CTkFrame(echo_card, fg_color="transparent")
        echo_hdr.pack(fill="x", padx=14, pady=10)

        self.sw_echo = ctk.CTkSwitch(
            echo_hdr, 
            text="Warm Studio Echo / Delay", 
            font=ctk.CTkFont(size=14, weight="bold"),
            progress_color="#38bdf8",
            command=self._on_echo_params_changed
        )
        self.sw_echo.pack(side="left")

        self.sw_echo_pingpong = ctk.CTkSwitch(
            echo_hdr,
            text="Ping-Pong Stereo",
            font=ctk.CTkFont(size=12),
            command=self._on_echo_params_changed
        )
        self.sw_echo_pingpong.pack(side="right")
        self.sw_echo_pingpong.select()

        # Sliders grid
        echo_grid = ctk.CTkFrame(echo_card, fg_color="transparent")
        echo_grid.pack(fill="x", padx=14, pady=(0, 12))
        echo_grid.grid_columnconfigure((0, 1), weight=1)

        # Delay Time
        col1 = ctk.CTkFrame(echo_grid, fg_color="transparent")
        col1.grid(row=0, column=0, padx=8, pady=4, sticky="ew")
        
        lbl_dt_row = ctk.CTkFrame(col1, fg_color="transparent")
        lbl_dt_row.pack(fill="x")
        ctk.CTkLabel(lbl_dt_row, text="Delay Time:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.lbl_echo_time = ctk.CTkLabel(lbl_dt_row, text="280 ms", font=ctk.CTkFont(size=11), text_color="#38bdf8")
        self.lbl_echo_time.pack(side="right")

        self.sl_echo_time = ctk.CTkSlider(col1, from_=20, to=800, number_of_steps=78, command=self._on_echo_params_changed)
        self.sl_echo_time.set(280)
        self.sl_echo_time.pack(fill="x", pady=2)

        # Quick Slapback buttons
        btn_row = ctk.CTkFrame(col1, fg_color="transparent")
        btn_row.pack(fill="x", pady=2)
        ctk.CTkButton(btn_row, text="Slapback (110ms)", width=95, height=20, font=ctk.CTkFont(size=10), command=lambda: self._set_echo_time(110)).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="Medium (260ms)", width=95, height=20, font=ctk.CTkFont(size=10), command=lambda: self._set_echo_time(260)).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="Long (420ms)", width=90, height=20, font=ctk.CTkFont(size=10), command=lambda: self._set_echo_time(420)).pack(side="left", padx=2)

        # Feedback
        col2 = ctk.CTkFrame(echo_grid, fg_color="transparent")
        col2.grid(row=0, column=1, padx=8, pady=4, sticky="ew")

        lbl_fb_row = ctk.CTkFrame(col2, fg_color="transparent")
        lbl_fb_row.pack(fill="x")
        ctk.CTkLabel(lbl_fb_row, text="Feedback (Repeats):", font=ctk.CTkFont(size=12)).pack(side="left")
        self.lbl_echo_feedback = ctk.CTkLabel(lbl_fb_row, text="35%", font=ctk.CTkFont(size=11), text_color="#38bdf8")
        self.lbl_echo_feedback.pack(side="right")

        self.sl_echo_feedback = ctk.CTkSlider(col2, from_=0.0, to=0.85, number_of_steps=85, command=self._on_echo_params_changed)
        self.sl_echo_feedback.set(0.35)
        self.sl_echo_feedback.pack(fill="x", pady=2)

        # Tone Damping & Wet Mix
        row_damp_wet = ctk.CTkFrame(echo_card, fg_color="transparent")
        row_damp_wet.pack(fill="x", padx=14, pady=(0, 12))
        row_damp_wet.grid_columnconfigure((0, 1), weight=1)

        c3 = ctk.CTkFrame(row_damp_wet, fg_color="transparent")
        c3.grid(row=0, column=0, padx=8, sticky="ew")
        lbl_damp_row = ctk.CTkFrame(c3, fg_color="transparent")
        lbl_damp_row.pack(fill="x")
        ctk.CTkLabel(lbl_damp_row, text="Tape Warmth (Damping):", font=ctk.CTkFont(size=12)).pack(side="left")
        self.lbl_echo_damp = ctk.CTkLabel(lbl_damp_row, text="30%", font=ctk.CTkFont(size=11), text_color="#38bdf8")
        self.lbl_echo_damp.pack(side="right")
        self.sl_echo_damp = ctk.CTkSlider(c3, from_=0.0, to=0.8, number_of_steps=40, command=self._on_echo_params_changed)
        self.sl_echo_damp.set(0.30)
        self.sl_echo_damp.pack(fill="x", pady=2)

        c4 = ctk.CTkFrame(row_damp_wet, fg_color="transparent")
        c4.grid(row=0, column=1, padx=8, sticky="ew")
        lbl_wet_row = ctk.CTkFrame(c4, fg_color="transparent")
        lbl_wet_row.pack(fill="x")
        ctk.CTkLabel(lbl_wet_row, text="Echo Wet Mix:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.lbl_echo_wet = ctk.CTkLabel(lbl_wet_row, text="22%", font=ctk.CTkFont(size=11), text_color="#38bdf8")
        self.lbl_echo_wet.pack(side="right")
        self.sl_echo_wet = ctk.CTkSlider(c4, from_=0.0, to=1.0, number_of_steps=50, command=self._on_echo_params_changed)
        self.sl_echo_wet.set(0.22)
        self.sl_echo_wet.pack(fill="x", pady=2)

        # --- STUDIO REVERB SECTION ---
        rev_card = ctk.CTkFrame(scroll, fg_color="#111318", corner_radius=10)
        rev_card.pack(fill="x", pady=6, padx=4)

        rev_hdr = ctk.CTkFrame(rev_card, fg_color="transparent")
        rev_hdr.pack(fill="x", padx=14, pady=10)

        self.sw_reverb = ctk.CTkSwitch(
            rev_hdr,
            text="High-Definition Studio Reverb",
            font=ctk.CTkFont(size=14, weight="bold"),
            progress_color="#818cf8",
            command=self._on_reverb_params_changed
        )
        self.sw_reverb.pack(side="left")

        rev_grid = ctk.CTkFrame(rev_card, fg_color="transparent")
        rev_grid.pack(fill="x", padx=14, pady=(0, 12))
        rev_grid.grid_columnconfigure((0, 1), weight=1)

        # Room Size
        rc1 = ctk.CTkFrame(rev_grid, fg_color="transparent")
        rc1.grid(row=0, column=0, padx=8, pady=4, sticky="ew")
        r_sz_row = ctk.CTkFrame(rc1, fg_color="transparent")
        r_sz_row.pack(fill="x")
        ctk.CTkLabel(r_sz_row, text="Room Size (Decay Length):", font=ctk.CTkFont(size=12)).pack(side="left")
        self.lbl_rev_room = ctk.CTkLabel(r_sz_row, text="75%", font=ctk.CTkFont(size=11), text_color="#818cf8")
        self.lbl_rev_room.pack(side="right")
        self.sl_rev_room = ctk.CTkSlider(rc1, from_=0.05, to=0.98, number_of_steps=50, command=self._on_reverb_params_changed)
        self.sl_rev_room.set(0.75)
        self.sl_rev_room.pack(fill="x", pady=2)

        # Reverb Damping
        rc2 = ctk.CTkFrame(rev_grid, fg_color="transparent")
        rc2.grid(row=0, column=1, padx=8, pady=4, sticky="ew")
        r_damp_row = ctk.CTkFrame(rc2, fg_color="transparent")
        r_damp_row.pack(fill="x")
        ctk.CTkLabel(r_damp_row, text="High Frequency Absorption:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.lbl_rev_damp = ctk.CTkLabel(r_damp_row, text="25%", font=ctk.CTkFont(size=11), text_color="#818cf8")
        self.lbl_rev_damp.pack(side="right")
        self.sl_rev_damp = ctk.CTkSlider(rc2, from_=0.0, to=0.9, number_of_steps=45, command=self._on_reverb_params_changed)
        self.sl_rev_damp.set(0.25)
        self.sl_rev_damp.pack(fill="x", pady=2)

        # Stereo Width & Wet Mix
        rev_row2 = ctk.CTkFrame(rev_card, fg_color="transparent")
        rev_row2.pack(fill="x", padx=14, pady=(0, 14))
        rev_row2.grid_columnconfigure((0, 1), weight=1)

        rc3 = ctk.CTkFrame(rev_row2, fg_color="transparent")
        rc3.grid(row=0, column=0, padx=8, sticky="ew")
        r_w_row = ctk.CTkFrame(rc3, fg_color="transparent")
        r_w_row.pack(fill="x")
        ctk.CTkLabel(r_w_row, text="Stereo Spatial Width:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.lbl_rev_width = ctk.CTkLabel(r_w_row, text="100%", font=ctk.CTkFont(size=11), text_color="#818cf8")
        self.lbl_rev_width.pack(side="right")
        self.sl_rev_width = ctk.CTkSlider(rc3, from_=0.0, to=1.0, number_of_steps=50, command=self._on_reverb_params_changed)
        self.sl_rev_width.set(1.0)
        self.sl_rev_width.pack(fill="x", pady=2)

        rc4 = ctk.CTkFrame(rev_row2, fg_color="transparent")
        rc4.grid(row=0, column=1, padx=8, sticky="ew")
        r_wet_row = ctk.CTkFrame(rc4, fg_color="transparent")
        r_wet_row.pack(fill="x")
        ctk.CTkLabel(r_wet_row, text="Reverb Wet Mix:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.lbl_rev_wet = ctk.CTkLabel(r_wet_row, text="25%", font=ctk.CTkFont(size=11), text_color="#818cf8")
        self.lbl_rev_wet.pack(side="right")
        self.sl_rev_wet = ctk.CTkSlider(rc4, from_=0.0, to=1.0, number_of_steps=50, command=self._on_reverb_params_changed)
        self.sl_rev_wet.set(0.25)
        self.sl_rev_wet.pack(fill="x", pady=2)

    def _set_echo_time(self, ms):
        self.sl_echo_time.set(ms)
        self._on_echo_params_changed()

    def _on_echo_params_changed(self, *args):
        self.dsp.echo.enabled = self.sw_echo.get() == 1
        self.dsp.echo.pingpong = self.sw_echo_pingpong.get() == 1
        
        t = self.sl_echo_time.get()
        self.dsp.echo.delay_ms = t
        self.lbl_echo_time.configure(text=f"{int(t)} ms")

        fb = self.sl_echo_feedback.get()
        self.dsp.echo.feedback = fb
        self.lbl_echo_feedback.configure(text=f"{int(fb*100)}%")

        damp = self.sl_echo_damp.get()
        self.dsp.echo.damping = damp
        self.lbl_echo_damp.configure(text=f"{int(damp*100)}%")

        wet = self.sl_echo_wet.get()
        self.dsp.echo.wet = wet
        self.lbl_echo_wet.configure(text=f"{int(wet*100)}%")

    def _on_reverb_params_changed(self, *args):
        self.dsp.reverb.enabled = self.sw_reverb.get() == 1

        room = self.sl_rev_room.get()
        self.dsp.reverb.room_size = room
        self.lbl_rev_room.configure(text=f"{int(room*100)}%")

        damp = self.sl_rev_damp.get()
        self.dsp.reverb.damping = damp
        self.lbl_rev_damp.configure(text=f"{int(damp*100)}%")

        width = self.sl_rev_width.get()
        self.dsp.reverb.width = width
        self.lbl_rev_width.configure(text=f"{int(width*100)}%")

        wet = self.sl_rev_wet.get()
        self.dsp.reverb.wet = wet
        self.lbl_rev_wet.configure(text=f"{int(wet*100)}%")

    # ------------------- TAB 2: NOISE CANCELLATION ----------------
    def _build_noise_tab(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        # 1. Rumble HPF
        card_rumble = ctk.CTkFrame(scroll, fg_color="#111318", corner_radius=10)
        card_rumble.pack(fill="x", pady=6, padx=4)

        self.sw_rumble = ctk.CTkSwitch(
            card_rumble,
            text="80 Hz Low-Cut Rumble Filter (Desk bumps & 50/60Hz AC Hum Removal)",
            font=ctk.CTkFont(size=13, weight="bold"),
            progress_color="#10b981",
            command=self._on_noise_params_changed
        )
        self.sw_rumble.pack(anchor="w", padx=14, pady=12)
        self.sw_rumble.select()

        # 2. Adaptive Noise Gate
        card_gate = ctk.CTkFrame(scroll, fg_color="#111318", corner_radius=10)
        card_gate.pack(fill="x", pady=6, padx=4)

        gate_hdr = ctk.CTkFrame(card_gate, fg_color="transparent")
        gate_hdr.pack(fill="x", padx=14, pady=10)

        self.sw_gate = ctk.CTkSwitch(
            gate_hdr,
            text="Adaptive Vocal Noise Gate (Zero Latency Room Silence)",
            font=ctk.CTkFont(size=14, weight="bold"),
            progress_color="#10b981",
            command=self._on_noise_params_changed
        )
        self.sw_gate.pack(side="left")
        self.sw_gate.select()

        # Gate controls
        gate_grid = ctk.CTkFrame(card_gate, fg_color="transparent")
        gate_grid.pack(fill="x", padx=14, pady=(0, 14))
        gate_grid.grid_columnconfigure((0, 1), weight=1)

        # Threshold
        gc1 = ctk.CTkFrame(gate_grid, fg_color="transparent")
        gc1.grid(row=0, column=0, padx=8, pady=4, sticky="ew")
        g_th_row = ctk.CTkFrame(gc1, fg_color="transparent")
        g_th_row.pack(fill="x")
        ctk.CTkLabel(g_th_row, text="Threshold (Open level):", font=ctk.CTkFont(size=12)).pack(side="left")
        self.lbl_gate_thresh = ctk.CTkLabel(g_th_row, text="-52.0 dB", font=ctk.CTkFont(size=11), text_color="#10b981")
        self.lbl_gate_thresh.pack(side="right")
        self.sl_gate_thresh = ctk.CTkSlider(gc1, from_=-75.0, to=-20.0, number_of_steps=55, command=self._on_noise_params_changed)
        self.sl_gate_thresh.set(-52.0)
        self.sl_gate_thresh.pack(fill="x", pady=2)

        # Release
        gc2 = ctk.CTkFrame(gate_grid, fg_color="transparent")
        gc2.grid(row=0, column=1, padx=8, pady=4, sticky="ew")
        g_rel_row = ctk.CTkFrame(gc2, fg_color="transparent")
        g_rel_row.pack(fill="x")
        ctk.CTkLabel(g_rel_row, text="Release Fade Speed:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.lbl_gate_rel = ctk.CTkLabel(g_rel_row, text="70 ms", font=ctk.CTkFont(size=11), text_color="#10b981")
        self.lbl_gate_rel.pack(side="right")
        self.sl_gate_rel = ctk.CTkSlider(gc2, from_=10.0, to=250.0, number_of_steps=48, command=self._on_noise_params_changed)
        self.sl_gate_rel.set(70.0)
        self.sl_gate_rel.pack(fill="x", pady=2)

        # 3. Spectral Background Denoising
        card_denoise = ctk.CTkFrame(scroll, fg_color="#111318", corner_radius=10)
        card_denoise.pack(fill="x", pady=6, padx=4)

        denoise_hdr = ctk.CTkFrame(card_denoise, fg_color="transparent")
        denoise_hdr.pack(fill="x", padx=14, pady=10)

        self.sw_denoise = ctk.CTkSwitch(
            denoise_hdr,
            text="Spectral Noise Suppressor (Fan & PC Continuous Noise Cancellation)",
            font=ctk.CTkFont(size=14, weight="bold"),
            progress_color="#06b6d4",
            command=self._on_noise_params_changed
        )
        self.sw_denoise.pack(side="left")

        den_grid = ctk.CTkFrame(card_denoise, fg_color="transparent")
        den_grid.pack(fill="x", padx=14, pady=(0, 14))

        den_lbl_row = ctk.CTkFrame(den_grid, fg_color="transparent")
        den_lbl_row.pack(fill="x")
        ctk.CTkLabel(den_lbl_row, text="Noise Reduction Intensity:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.lbl_den_str = ctk.CTkLabel(den_lbl_row, text="35%", font=ctk.CTkFont(size=11), text_color="#06b6d4")
        self.lbl_den_str.pack(side="right")

        self.sl_denoise_str = ctk.CTkSlider(den_grid, from_=0.0, to=1.0, number_of_steps=50, command=self._on_noise_params_changed)
        self.sl_denoise_str.set(0.35)
        self.sl_denoise_str.pack(fill="x", pady=2)

    def _on_noise_params_changed(self, *args):
        self.dsp.noise_filter.rumble_filter_enabled = self.sw_rumble.get() == 1
        self.dsp.noise_filter.gate_enabled = self.sw_gate.get() == 1
        
        th = self.sl_gate_thresh.get()
        self.dsp.noise_filter.threshold_db = th
        self.lbl_gate_thresh.configure(text=f"{th:.1f} dB")

        rel = self.sl_gate_rel.get()
        self.dsp.noise_filter.release_ms = rel
        self.lbl_gate_rel.configure(text=f"{int(rel)} ms")

        self.dsp.noise_filter.denoise_enabled = self.sw_denoise.get() == 1
        d_str = self.sl_denoise_str.get()
        self.dsp.noise_filter.denoise_strength = d_str
        self.lbl_den_str.configure(text=f"{int(d_str*100)}%")

    # ------------------- TAB 3: STUDIO EQ & COMPRESSOR ------------
    def _build_eq_comp_tab(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        # 1. 3-Band Parametric Vocal EQ
        eq_card = ctk.CTkFrame(scroll, fg_color="#111318", corner_radius=10)
        eq_card.pack(fill="x", pady=6, padx=4)

        eq_hdr = ctk.CTkFrame(eq_card, fg_color="transparent")
        eq_hdr.pack(fill="x", padx=14, pady=10)

        self.sw_eq = ctk.CTkSwitch(
            eq_hdr,
            text="3-Band Studio Vocal Equalizer",
            font=ctk.CTkFont(size=14, weight="bold"),
            progress_color="#38bdf8",
            command=self._on_eq_params_changed
        )
        self.sw_eq.pack(side="left")
        self.sw_eq.select()

        btn_reset_eq = ctk.CTkButton(eq_hdr, text="Flat (Reset)", width=80, height=22, font=ctk.CTkFont(size=11), command=self._reset_eq)
        btn_reset_eq.pack(side="right")

        eq_grid = ctk.CTkFrame(eq_card, fg_color="transparent")
        eq_grid.pack(fill="x", padx=14, pady=(0, 14))
        eq_grid.grid_columnconfigure((0, 1, 2), weight=1)

        # Low Shelf (120 Hz)
        e1 = ctk.CTkFrame(eq_grid, fg_color="transparent")
        e1.grid(row=0, column=0, padx=6, sticky="ew")
        r_l = ctk.CTkFrame(e1, fg_color="transparent")
        r_l.pack(fill="x")
        ctk.CTkLabel(r_l, text="Low / Warmth (120Hz):", font=ctk.CTkFont(size=11)).pack(side="left")
        self.lbl_eq_low = ctk.CTkLabel(r_l, text="+0.0 dB", font=ctk.CTkFont(size=11), text_color="#38bdf8")
        self.lbl_eq_low.pack(side="right")
        self.sl_eq_low = ctk.CTkSlider(e1, from_=-12.0, to=12.0, number_of_steps=48, command=self._on_eq_params_changed)
        self.sl_eq_low.set(0.0)
        self.sl_eq_low.pack(fill="x", pady=2)

        # Mid Peaking (2.5 kHz)
        e2 = ctk.CTkFrame(eq_grid, fg_color="transparent")
        e2.grid(row=0, column=1, padx=6, sticky="ew")
        r_m = ctk.CTkFrame(e2, fg_color="transparent")
        r_m.pack(fill="x")
        ctk.CTkLabel(r_m, text="Presence (2.5kHz):", font=ctk.CTkFont(size=11)).pack(side="left")
        self.lbl_eq_mid = ctk.CTkLabel(r_m, text="+2.0 dB", font=ctk.CTkFont(size=11), text_color="#38bdf8")
        self.lbl_eq_mid.pack(side="right")
        self.sl_eq_mid = ctk.CTkSlider(e2, from_=-12.0, to=12.0, number_of_steps=48, command=self._on_eq_params_changed)
        self.sl_eq_mid.set(2.0)
        self.sl_eq_mid.pack(fill="x", pady=2)

        # High Shelf (10 kHz)
        e3 = ctk.CTkFrame(eq_grid, fg_color="transparent")
        e3.grid(row=0, column=2, padx=6, sticky="ew")
        r_h = ctk.CTkFrame(e3, fg_color="transparent")
        r_h.pack(fill="x")
        ctk.CTkLabel(r_h, text="Air Sheen (10kHz):", font=ctk.CTkFont(size=11)).pack(side="left")
        self.lbl_eq_high = ctk.CTkLabel(r_h, text="+3.0 dB", font=ctk.CTkFont(size=11), text_color="#38bdf8")
        self.lbl_eq_high.pack(side="right")
        self.sl_eq_high = ctk.CTkSlider(e3, from_=-12.0, to=12.0, number_of_steps=48, command=self._on_eq_params_changed)
        self.sl_eq_high.set(3.0)
        self.sl_eq_high.pack(fill="x", pady=2)

        # 2. Vocal Compressor & Leveler
        comp_card = ctk.CTkFrame(scroll, fg_color="#111318", corner_radius=10)
        comp_card.pack(fill="x", pady=6, padx=4)

        comp_hdr = ctk.CTkFrame(comp_card, fg_color="transparent")
        comp_hdr.pack(fill="x", padx=14, pady=10)

        self.sw_comp = ctk.CTkSwitch(
            comp_hdr,
            text="Studio Vocal Dynamics Compressor",
            font=ctk.CTkFont(size=14, weight="bold"),
            progress_color="#f59e0b",
            command=self._on_comp_params_changed
        )
        self.sw_comp.pack(side="left")
        self.sw_comp.select()

        comp_grid = ctk.CTkFrame(comp_card, fg_color="transparent")
        comp_grid.pack(fill="x", padx=14, pady=(0, 14))
        comp_grid.grid_columnconfigure((0, 1, 2), weight=1)

        # Threshold
        c1 = ctk.CTkFrame(comp_grid, fg_color="transparent")
        c1.grid(row=0, column=0, padx=6, sticky="ew")
        r_ct = ctk.CTkFrame(c1, fg_color="transparent")
        r_ct.pack(fill="x")
        ctk.CTkLabel(r_ct, text="Threshold:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.lbl_comp_th = ctk.CTkLabel(r_ct, text="-20.0 dB", font=ctk.CTkFont(size=11), text_color="#f59e0b")
        self.lbl_comp_th.pack(side="right")
        self.sl_comp_th = ctk.CTkSlider(c1, from_=-40.0, to=0.0, number_of_steps=40, command=self._on_comp_params_changed)
        self.sl_comp_th.set(-20.0)
        self.sl_comp_th.pack(fill="x", pady=2)

        # Ratio
        c2 = ctk.CTkFrame(comp_grid, fg_color="transparent")
        c2.grid(row=0, column=1, padx=6, sticky="ew")
        r_cr = ctk.CTkFrame(c2, fg_color="transparent")
        r_cr.pack(fill="x")
        ctk.CTkLabel(r_cr, text="Ratio:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.lbl_comp_ratio = ctk.CTkLabel(r_cr, text="3.5:1", font=ctk.CTkFont(size=11), text_color="#f59e0b")
        self.lbl_comp_ratio.pack(side="right")
        self.sl_comp_ratio = ctk.CTkSlider(c2, from_=1.0, to=8.0, number_of_steps=35, command=self._on_comp_params_changed)
        self.sl_comp_ratio.set(3.5)
        self.sl_comp_ratio.pack(fill="x", pady=2)

        # Makeup Gain
        c3 = ctk.CTkFrame(comp_grid, fg_color="transparent")
        c3.grid(row=0, column=2, padx=6, sticky="ew")
        r_cm = ctk.CTkFrame(c3, fg_color="transparent")
        r_cm.pack(fill="x")
        ctk.CTkLabel(r_cm, text="Makeup Gain:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.lbl_comp_makeup = ctk.CTkLabel(r_cm, text="+2.5 dB", font=ctk.CTkFont(size=11), text_color="#f59e0b")
        self.lbl_comp_makeup.pack(side="right")
        self.sl_comp_makeup = ctk.CTkSlider(c3, from_=0.0, to=12.0, number_of_steps=24, command=self._on_comp_params_changed)
        self.sl_comp_makeup.set(2.5)
        self.sl_comp_makeup.pack(fill="x", pady=2)

    def _reset_eq(self):
        self.sl_eq_low.set(0.0)
        self.sl_eq_mid.set(0.0)
        self.sl_eq_high.set(0.0)
        self._on_eq_params_changed()

    def _on_eq_params_changed(self, *args):
        self.dsp.eq.enabled = self.sw_eq.get() == 1
        l = self.sl_eq_low.get()
        m = self.sl_eq_mid.get()
        h = self.sl_eq_high.get()
        self.dsp.eq.update_gains(l, m, h)
        self.lbl_eq_low.configure(text=f"{l:+.1f} dB")
        self.lbl_eq_mid.configure(text=f"{m:+.1f} dB")
        self.lbl_eq_high.configure(text=f"{h:+.1f} dB")

    def _on_comp_params_changed(self, *args):
        self.dsp.dynamics.comp_enabled = self.sw_comp.get() == 1
        th = self.sl_comp_th.get()
        r = self.sl_comp_ratio.get()
        mk = self.sl_comp_makeup.get()
        self.dsp.dynamics.threshold_db = th
        self.dsp.dynamics.ratio = r
        self.dsp.dynamics.makeup_gain_db = mk
        self.lbl_comp_th.configure(text=f"{th:.1f} dB")
        self.lbl_comp_ratio.configure(text=f"{r:.1f}:1")
        self.lbl_comp_makeup.configure(text=f"+{mk:.1f} dB")

    # ------------------- TAB 4: PRESETS & RECORDINGS --------------
    def _build_presets_tab(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        # 1. Preset Selector Card
        p_card = ctk.CTkFrame(scroll, fg_color="#111318", corner_radius=10)
        p_card.pack(fill="x", pady=6, padx=4)

        ctk.CTkLabel(p_card, text="Factory Vocal Styles & Presets", font=ctk.CTkFont(size=14, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=14, pady=(10, 4))

        row_p = ctk.CTkFrame(p_card, fg_color="transparent")
        row_p.pack(fill="x", padx=14, pady=6)

        self.combo_presets = ctk.CTkComboBox(
            row_p,
            values=list(FACTORY_PRESETS.keys()),
            width=320,
            height=32,
            state="readonly",
            command=self._on_preset_dropdown_selected
        )
        self.combo_presets.set("🎤 Warm Pop / Ballad Vocal")
        self.combo_presets.pack(side="left", padx=(0, 10))

        btn_save = ctk.CTkButton(row_p, text="💾 Save Custom...", width=120, height=32, command=self._export_custom_preset)
        btn_save.pack(side="left", padx=4)

        btn_load = ctk.CTkButton(row_p, text="📂 Load Custom...", width=120, height=32, command=self._import_custom_preset)
        btn_load.pack(side="left", padx=4)

        self.lbl_preset_desc = ctk.CTkLabel(
            p_card, 
            text=FACTORY_PRESETS["🎤 Warm Pop / Ballad Vocal"]["description"],
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color="#94a3b8",
            wraplength=600,
            justify="left"
        )
        self.lbl_preset_desc.pack(anchor="w", padx=14, pady=(4, 12))

        # 2. Recording & Session Management
        rec_card = ctk.CTkFrame(scroll, fg_color="#111318", corner_radius=10)
        rec_card.pack(fill="x", pady=6, padx=4)

        ctk.CTkLabel(rec_card, text="🎙️ Live Practice Recording Session", font=ctk.CTkFont(size=14, weight="bold"), text_color="#f43f5e").pack(anchor="w", padx=14, pady=(10, 4))

        rec_row = ctk.CTkFrame(rec_card, fg_color="transparent")
        rec_row.pack(fill="x", padx=14, pady=8)

        self.lbl_rec_status = ctk.CTkLabel(rec_row, text="Status: Ready to Record", font=ctk.CTkFont(size=12))
        self.lbl_rec_status.pack(side="left", padx=(0, 15))

        btn_open_folder = ctk.CTkButton(rec_row, text="📁 Open Recordings Folder", width=180, height=30, command=self._open_recordings_folder)
        btn_open_folder.pack(side="right")

    def _load_preset_by_name(self, name):
        if name in FACTORY_PRESETS:
            p = FACTORY_PRESETS[name]
            apply_preset_to_pipeline(self.dsp, p)
            self._sync_ui_from_pipeline(p)
            self.lbl_preset_desc.configure(text=p.get("description", ""))

    def _sync_ui_from_pipeline(self, p):
        """Reflect loaded preset settings into UI sliders and switches."""
        # Gain
        self.slider_input_gain.set(p.get("input_gain", 1.0))
        self.slider_output_vol.set(p.get("output_volume", 1.0))
        self._on_input_gain_slider(p.get("input_gain", 1.0))
        self._on_output_vol_slider(p.get("output_volume", 1.0))
        
        # Noise
        if p.get("rumble_hpf", True): self.sw_rumble.select()
        else: self.sw_rumble.deselect()
        
        if p.get("noise_gate", True): self.sw_gate.select()
        else: self.sw_gate.deselect()
        self.sl_gate_thresh.set(p.get("gate_thresh_db", -52.0))
        self.sl_gate_rel.set(p.get("gate_release_ms", 70.0))

        if p.get("denoise", False): self.sw_denoise.select()
        else: self.sw_denoise.deselect()
        self.sl_denoise_str.set(p.get("denoise_strength", 0.35))
        self._on_noise_params_changed()

        # EQ
        if p.get("eq_enabled", True): self.sw_eq.select()
        else: self.sw_eq.deselect()
        self.sl_eq_low.set(p.get("eq_low_db", 0.0))
        self.sl_eq_mid.set(p.get("eq_mid_db", 0.0))
        self.sl_eq_high.set(p.get("eq_high_db", 0.0))
        self._on_eq_params_changed()

        # Comp
        if p.get("comp_enabled", True): self.sw_comp.select()
        else: self.sw_comp.deselect()
        self.sl_comp_th.set(p.get("comp_thresh_db", -18.0))
        self.sl_comp_ratio.set(p.get("comp_ratio", 3.0))
        self.sl_comp_makeup.set(p.get("comp_makeup_db", 2.0))
        self._on_comp_params_changed()

        # Echo
        if p.get("echo_enabled", False): self.sw_echo.select()
        else: self.sw_echo.deselect()
        if p.get("echo_pingpong", True): self.sw_echo_pingpong.select()
        else: self.sw_echo_pingpong.deselect()
        self.sl_echo_time.set(p.get("echo_time_ms", 280.0))
        self.sl_echo_feedback.set(p.get("echo_feedback", 0.35))
        self.sl_echo_damp.set(p.get("echo_damping", 0.30))
        self.sl_echo_wet.set(p.get("echo_wet", 0.22))
        self._on_echo_params_changed()

        # Reverb
        if p.get("reverb_enabled", False): self.sw_reverb.select()
        else: self.sw_reverb.deselect()
        self.sl_rev_room.set(p.get("reverb_room_size", 0.75))
        self.sl_rev_damp.set(p.get("reverb_damping", 0.25))
        self.sl_rev_width.set(p.get("reverb_width", 1.0))
        self.sl_rev_wet.set(p.get("reverb_wet", 0.25))
        self._on_reverb_params_changed()

    def _on_preset_dropdown_selected(self, choice):
        self._load_preset_by_name(choice)

    def _export_custom_preset(self):
        f = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("SingerPro Preset JSON", "*.json")],
            title="Save Current Preset As..."
        )
        if f:
            data = {
                "description": "User Custom Preset",
                "input_gain": self.slider_input_gain.get(),
                "output_volume": self.slider_output_vol.get(),
                "rumble_hpf": self.sw_rumble.get() == 1,
                "noise_gate": self.sw_gate.get() == 1,
                "gate_thresh_db": self.sl_gate_thresh.get(),
                "gate_release_ms": self.sl_gate_rel.get(),
                "denoise": self.sw_denoise.get() == 1,
                "denoise_strength": self.sl_denoise_str.get(),
                "eq_enabled": self.sw_eq.get() == 1,
                "eq_low_db": self.sl_eq_low.get(),
                "eq_mid_db": self.sl_eq_mid.get(),
                "eq_high_db": self.sl_eq_high.get(),
                "comp_enabled": self.sw_comp.get() == 1,
                "comp_thresh_db": self.sl_comp_th.get(),
                "comp_ratio": self.sl_comp_ratio.get(),
                "comp_makeup_db": self.sl_comp_makeup.get(),
                "echo_enabled": self.sw_echo.get() == 1,
                "echo_time_ms": self.sl_echo_time.get(),
                "echo_feedback": self.sl_echo_feedback.get(),
                "echo_damping": self.sl_echo_damp.get(),
                "echo_wet": self.sl_echo_wet.get(),
                "echo_pingpong": self.sw_echo_pingpong.get() == 1,
                "reverb_enabled": self.sw_reverb.get() == 1,
                "reverb_room_size": self.sl_rev_room.get(),
                "reverb_damping": self.sl_rev_damp.get(),
                "reverb_width": self.sl_rev_width.get(),
                "reverb_wet": self.sl_rev_wet.get()
            }
            export_preset_file(f, data)
            messagebox.showinfo("Preset Saved", f"Preset saved successfully to:\n{f}")

    def _import_custom_preset(self):
        f = filedialog.askopenfilename(
            filetypes=[("SingerPro Preset JSON", "*.json")],
            title="Load Custom Preset"
        )
        if f and os.path.exists(f):
            try:
                data = import_preset_file(f)
                apply_preset_to_pipeline(self.dsp, data)
                self._sync_ui_from_pipeline(data)
                self.lbl_preset_desc.configure(text=f"Loaded from: {os.path.basename(f)}")
                messagebox.showinfo("Preset Loaded", f"Loaded custom preset: {os.path.basename(f)}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load preset: {e}")

    def _open_recordings_folder(self):
        folder = os.path.abspath("recordings")
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)

    # -------------------------------------------------------------
    # 4. STATUSBAR
    # -------------------------------------------------------------
    def _build_statusbar(self):
        status_frame = ctk.CTkFrame(self, fg_color="#0f1117", height=28, corner_radius=0)
        status_frame.grid(row=3, column=0, sticky="ew", padx=0, pady=0)

        self.lbl_status_text = ctk.CTkLabel(
            status_frame,
            text="SingerPro Studio Ready. Select your Microphone and Output Headphones, then click Start Monitoring.",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        )
        self.lbl_status_text.pack(side="left", padx=16, pady=2)

    # -------------------------------------------------------------
    # DEVICE HANDLING & MONITORING STREAM
    # -------------------------------------------------------------
    def _refresh_audio_devices(self):
        all_in, all_out = self.engine.get_devices()
        filter_mode = self.opt_driver_filter.get()

        if "WASAPI" in filter_mode:
            in_list = [d for d in all_in if "WASAPI" in d["api"]] or all_in
            out_list = [d for d in all_out if "WASAPI" in d["api"]] or all_out
        elif "DirectSound" in filter_mode:
            in_list = [d for d in all_in if "DirectSound" in d["api"]] or all_in
            out_list = [d for d in all_out if "DirectSound" in d["api"]] or all_out
        elif "MME" in filter_mode:
            in_list = [d for d in all_in if "MME" in d["api"]] or all_in
            out_list = [d for d in all_out if "MME" in d["api"]] or all_out
        else:
            in_list = all_in
            out_list = all_out

        self.input_devices = in_list
        self.output_devices = out_list

        in_names = [d["display_name"] for d in in_list]
        out_names = [d["display_name"] for d in out_list]

        self.combo_input.configure(values=in_names)
        self.combo_output.configure(values=out_names)

        if in_names:
            self.combo_input.set(in_names[0])
        if out_names:
            # Prefer headphones or second device if available
            headphone_match = [name for name in out_names if "Headphone" in name or "Headset" in name]
            if headphone_match:
                self.combo_output.set(headphone_match[0])
            else:
                self.combo_output.set(out_names[0])

    def _on_driver_filter_changed(self, value):
        was_running = self.engine.is_running
        if was_running:
            self._toggle_monitoring()
        self._refresh_audio_devices()
        if was_running:
            self._toggle_monitoring()

    def _on_device_selection_changed(self, *args):
        if self.engine.is_running:
            # Restart stream with new devices
            self._restart_stream()

    def _on_buffer_changed(self, *args):
        if self.engine.is_running:
            self._restart_stream()

    def _on_samplerate_changed(self, *args):
        if self.engine.is_running:
            self._restart_stream()

    def _get_selected_device_ids(self):
        in_sel = self.combo_input.get()
        out_sel = self.combo_output.get()
        
        in_id = None
        out_id = None
        for d in self.input_devices:
            if d["display_name"] == in_sel:
                in_id = d["id"]
                break
        for d in self.output_devices:
            if d["display_name"] == out_sel:
                out_id = d["id"]
                break
                
        return in_id, out_id

    def _get_buffer_size(self):
        val = self.combo_buffer.get()
        if "128" in val: return 128
        if "256" in val: return 256
        if "512" in val: return 512
        if "1024" in val: return 1024
        return 256

    def _get_samplerate(self):
        val = self.combo_samplerate.get()
        if "44100" in val: return 44100
        if "96000" in val: return 96000
        return 48000

    def _toggle_monitoring(self):
        if self.engine.is_running:
            # Stop monitoring
            self.engine.stop()
            self.btn_monitor_toggle.configure(text="▶ START MONITORING", fg_color="#2563eb", hover_color="#1d4ed8")
            self.lbl_status_badge.configure(text="⚪ IDLE", fg_color="#334155", text_color="#cbd5e1")
            self.lbl_latency_badge.configure(text="⚡ Est. Latency: -- ms", text_color="#94a3b8")
            self.lbl_status_text.configure(text="Monitoring stopped.")
        else:
            in_id, out_id = self._get_selected_device_ids()
            if in_id is None or out_id is None:
                messagebox.showwarning("Device Selection", "Please select valid Input and Output devices first.")
                return

            bs = self._get_buffer_size()
            sr = self._get_samplerate()

            success = self.engine.start(in_id, out_id, sample_rate=sr, block_size=bs)
            if success:
                self.btn_monitor_toggle.configure(text="⏹ STOP MONITORING", fg_color="#e11d48", hover_color="#be123c")
                self.lbl_status_badge.configure(text="🟢 LIVE MONITORING", fg_color="#065f46", text_color="#34d399")
                lat = self.engine.estimated_latency_ms
                self.lbl_latency_badge.configure(text=f"⚡ Latency: {lat:.1f} ms ({bs} smp @ {sr}Hz)", text_color="#38bdf8")
                self.lbl_status_text.configure(text=f"Active duplex stream: Input {in_id} -> Output {out_id} | Latency: ~{lat:.1f} ms")
            else:
                messagebox.showerror("Audio Stream Error", f"Failed to start stream with selected devices.\n{self.engine.last_status_msg}")

    def _restart_stream(self):
        if self.engine.is_running:
            self._toggle_monitoring()
            self.after(100, self._toggle_monitoring)

    def _toggle_recording(self):
        if not self.engine.is_recording:
            if not self.engine.is_running:
                messagebox.showinfo("Start Monitoring First", "Please click 'Start Monitoring' before recording live audio.")
                return
            path = self.engine.start_recording()
            if path:
                self.btn_record.configure(text="⏹ Stop Rec", fg_color="#e11d48", hover_color="#be123c")
                self.lbl_rec_status.configure(text=f"Recording to: {os.path.basename(path)}")
        else:
            path = self.engine.stop_recording()
            self.btn_record.configure(text="🔴 Record", fg_color="#374151", hover_color="#4b5563")
            self.lbl_rec_status.configure(text=f"Saved recording: {os.path.basename(path)}")
            messagebox.showinfo("Recording Saved", f"Session saved successfully to:\n{path}")

    # Gain / Volume Sliders
    def _on_input_gain_slider(self, val):
        self.dsp.input_gain = float(val)
        db = 20.0 * math.log10(max(0.001, float(val)))
        self.lbl_gain_val.configure(text=f"{float(val):.2f}x ({db:+.1f} dB)")

    def _on_mic_mute_toggled(self):
        self.dsp.input_muted = self.chk_mic_mute.get() == 1

    def _on_output_vol_slider(self, val):
        self.dsp.output_volume = float(val)
        self.lbl_vol_val.configure(text=f"{int(float(val)*100)}%")

    def _on_out_mute_toggled(self):
        self.dsp.output_muted = self.chk_out_mute.get() == 1

    # -------------------------------------------------------------
    # REAL-TIME VISUALIZER & VU METER ANIMATION LOOP
    # -------------------------------------------------------------
    def _update_meters_and_vis(self):
        if not self._vis_running:
            return

        if self.engine.is_running:
            # 1. Update In/Out Peak Meters
            in_pk = self.dsp.input_peak
            out_pk = self.dsp.output_peak

            self.bar_in_peak.set(min(1.0, in_pk))
            self.bar_out_peak.set(min(1.0, out_pk))

            if in_pk > 0.0001:
                in_db = 20.0 * math.log10(in_pk)
                self.lbl_in_db.configure(text=f"{in_db:.1f} dB")
                if in_db > -0.5:
                    self.bar_in_peak.configure(progress_color="#ef4444") # Red clip
                elif in_db > -6.0:
                    self.bar_in_peak.configure(progress_color="#f59e0b") # Yellow
                else:
                    self.bar_in_peak.configure(progress_color="#10b981") # Green
            else:
                self.lbl_in_db.configure(text="-∞ dB")
                self.bar_in_peak.configure(progress_color="#10b981")

            if out_pk > 0.0001:
                out_db = 20.0 * math.log10(out_pk)
                self.lbl_out_db.configure(text=f"{out_db:.1f} dB")
                if out_db > -0.5:
                    self.bar_out_peak.configure(progress_color="#ef4444")
                elif out_db > -6.0:
                    self.bar_out_peak.configure(progress_color="#f59e0b")
                else:
                    self.bar_out_peak.configure(progress_color="#38bdf8")
            else:
                self.lbl_out_db.configure(text="-∞ dB")
                self.bar_out_peak.configure(progress_color="#38bdf8")

            # 2. Render Oscilloscope Waveform & Spectrum
            self._render_canvas_oscilloscope()
        else:
            self.bar_in_peak.set(0.0)
            self.bar_out_peak.set(0.0)
            self.lbl_in_db.configure(text="-∞ dB")
            self.lbl_out_db.configure(text="-∞ dB")
            self._render_idle_canvas()

        # Schedule next animation frame (~30 FPS)
        self.after(33, self._update_meters_and_vis)

    def _render_canvas_oscilloscope(self):
        w = self.vis_canvas.winfo_width()
        h = self.vis_canvas.winfo_height()
        if w < 10 or h < 10:
            return

        self.vis_canvas.delete("all")
        mid_y = h / 2.0

        # Background grid lines
        self.vis_canvas.create_line(0, mid_y, w, mid_y, fill="#1e293b", width=1, dash=(4, 4))
        self.vis_canvas.create_line(0, mid_y - h*0.35, w, mid_y - h*0.35, fill="#131b26", width=1)
        self.vis_canvas.create_line(0, mid_y + h*0.35, w, mid_y + h*0.35, fill="#131b26", width=1)

        wave_data, fft_data = self.engine.get_visualizer_data()
        
        # 1. Draw subtle background FFT frequency bars
        num_bars = 48
        bar_w = w / num_bars
        fft_sub = fft_data[:num_bars]
        max_fft = np.max(fft_sub) + 1e-6
        for i in range(min(num_bars, len(fft_sub))):
            norm_val = min(1.0, fft_sub[i] / max_fft * (1.0 + i*0.05))
            bh = norm_val * (h * 0.7)
            x0 = i * bar_w
            x1 = x0 + bar_w - 2
            y0 = h - bh
            y1 = h
            self.vis_canvas.create_rectangle(x0, y0, x1, y1, fill="#0f2b38", outline="")

        # 2. Draw glowing waveform line
        pts = []
        step = max(1, len(wave_data) // w)
        downsampled = wave_data[::step]
        dx = w / max(1, len(downsampled) - 1)

        scale_y = (h * 0.42)
        for i, val in enumerate(downsampled):
            x = i * dx
            y = mid_y - val * scale_y
            pts.extend([x, y])

        if len(pts) >= 4:
            # Glow shadow
            self.vis_canvas.create_line(pts, fill="#0369a1", width=3, smooth=True)
            # Main neon trace
            self.vis_canvas.create_line(pts, fill="#38bdf8", width=1.5, smooth=True)

    def _render_idle_canvas(self):
        w = self.vis_canvas.winfo_width()
        h = self.vis_canvas.winfo_height()
        if w < 10 or h < 10:
            return
        self.vis_canvas.delete("all")
        mid_y = h / 2.0
        self.vis_canvas.create_line(0, mid_y, w, mid_y, fill="#1e293b", width=1, dash=(4, 4))
        self.vis_canvas.create_text(
            w / 2.0, mid_y, 
            text="[ Monitoring Idle — Click 'START MONITORING' to Begin Live Vocal Monitoring ]", 
            fill="#475569", 
            font=("Segoe UI", 10)
        )

    def _on_close(self):
        self._vis_running = False
        if self.engine.is_recording:
            self.engine.stop_recording()
        if self.engine.is_running:
            self.engine.stop()
        self.destroy()


def run_app():
    app = SingerProApp()
    app.mainloop()

if __name__ == "__main__":
    run_app()
