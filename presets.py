"""
SingerPro - Vocal Presets Manager
Provides factory presets and custom profile saving/loading (JSON).
"""

import json
import os

FACTORY_PRESETS = {
    "🎙️ Clean Studio Mic": {
        "description": "Transparent, clean vocal monitoring with background noise elimination and gentle leveling.",
        "input_gain": 1.0,
        "output_volume": 1.0,
        "rumble_hpf": True,
        "noise_gate": True,
        "gate_thresh_db": -54.0,
        "gate_attack_ms": 4.0,
        "gate_release_ms": 60.0,
        "denoise": False,
        "denoise_strength": 0.35,
        "eq_enabled": True,
        "eq_low_db": -1.0,
        "eq_mid_db": 1.5,
        "eq_high_db": 2.5,
        "comp_enabled": True,
        "comp_thresh_db": -18.0,
        "comp_ratio": 3.0,
        "comp_makeup_db": 2.0,
        "echo_enabled": False,
        "echo_time_ms": 250.0,
        "echo_feedback": 0.30,
        "echo_damping": 0.30,
        "echo_wet": 0.15,
        "echo_pingpong": True,
        "reverb_enabled": False,
        "reverb_room_size": 0.60,
        "reverb_damping": 0.30,
        "reverb_width": 1.0,
        "reverb_wet": 0.15
    },
    "🎤 Warm Pop / Ballad Vocal": {
        "description": "Lush singing monitoring with smooth studio plate reverb and warm tape echo.",
        "input_gain": 1.1,
        "output_volume": 1.0,
        "rumble_hpf": True,
        "noise_gate": True,
        "gate_thresh_db": -52.0,
        "gate_attack_ms": 4.0,
        "gate_release_ms": 80.0,
        "denoise": False,
        "denoise_strength": 0.30,
        "eq_enabled": True,
        "eq_low_db": 1.0,
        "eq_mid_db": 2.0,
        "eq_high_db": 3.5,
        "comp_enabled": True,
        "comp_thresh_db": -20.0,
        "comp_ratio": 3.8,
        "comp_makeup_db": 3.0,
        "echo_enabled": True,
        "echo_time_ms": 280.0,
        "echo_feedback": 0.30,
        "echo_damping": 0.40,
        "echo_wet": 0.22,
        "echo_pingpong": True,
        "reverb_enabled": True,
        "reverb_room_size": 0.78,
        "reverb_damping": 0.25,
        "reverb_width": 1.0,
        "reverb_wet": 0.30
    },
    "🏟️ Concert Arena / Stadium": {
        "description": "Massive stage reverb and wide ping-pong stereo echo for rock & live performance.",
        "input_gain": 1.0,
        "output_volume": 1.0,
        "rumble_hpf": True,
        "noise_gate": True,
        "gate_thresh_db": -48.0,
        "gate_attack_ms": 3.0,
        "gate_release_ms": 100.0,
        "denoise": False,
        "denoise_strength": 0.30,
        "eq_enabled": True,
        "eq_low_db": 2.0,
        "eq_mid_db": 3.0,
        "eq_high_db": 4.0,
        "comp_enabled": True,
        "comp_thresh_db": -22.0,
        "comp_ratio": 4.5,
        "comp_makeup_db": 3.5,
        "echo_enabled": True,
        "echo_time_ms": 375.0,
        "echo_feedback": 0.45,
        "echo_damping": 0.20,
        "echo_wet": 0.35,
        "echo_pingpong": True,
        "reverb_enabled": True,
        "reverb_room_size": 0.94,
        "reverb_damping": 0.15,
        "reverb_width": 1.0,
        "reverb_wet": 0.48
    },
    "🎸 Slapback Rock Vocal": {
        "description": "Classic 50s-70s rockabilly & modern indie slapback delay with tight room ambience.",
        "input_gain": 1.1,
        "output_volume": 1.0,
        "rumble_hpf": True,
        "noise_gate": True,
        "gate_thresh_db": -50.0,
        "gate_attack_ms": 2.0,
        "gate_release_ms": 50.0,
        "denoise": False,
        "denoise_strength": 0.25,
        "eq_enabled": True,
        "eq_low_db": -0.5,
        "eq_mid_db": 3.5,
        "eq_high_db": 2.0,
        "comp_enabled": True,
        "comp_thresh_db": -16.0,
        "comp_ratio": 4.0,
        "comp_makeup_db": 2.5,
        "echo_enabled": True,
        "echo_time_ms": 115.0,
        "echo_feedback": 0.15,
        "echo_damping": 0.50,
        "echo_wet": 0.40,
        "echo_pingpong": False,
        "reverb_enabled": True,
        "reverb_room_size": 0.40,
        "reverb_damping": 0.50,
        "reverb_width": 0.70,
        "reverb_wet": 0.15
    },
    "📻 Broadcast / Podcast Host": {
        "description": "Radio-ready vocal presence, aggressive noise gating, background hum removal, and punchy dynamics.",
        "input_gain": 1.2,
        "output_volume": 1.0,
        "rumble_hpf": True,
        "noise_gate": True,
        "gate_thresh_db": -46.0,
        "gate_attack_ms": 2.0,
        "gate_release_ms": 50.0,
        "denoise": True,
        "denoise_strength": 0.40,
        "eq_enabled": True,
        "eq_low_db": 3.0,
        "eq_mid_db": 2.5,
        "eq_high_db": 4.0,
        "comp_enabled": True,
        "comp_thresh_db": -18.0,
        "comp_ratio": 5.0,
        "comp_makeup_db": 4.0,
        "echo_enabled": False,
        "echo_time_ms": 200.0,
        "echo_feedback": 0.20,
        "echo_damping": 0.30,
        "echo_wet": 0.0,
        "echo_pingpong": False,
        "reverb_enabled": False,
        "reverb_room_size": 0.30,
        "reverb_damping": 0.60,
        "reverb_width": 0.5,
        "reverb_wet": 0.0
    },
    "🌌 Dreamy Ambient Vocal": {
        "description": "Long atmospheric spatial reflections with endless evolving stereo echo for meditative or synth vocals.",
        "input_gain": 1.0,
        "output_volume": 1.0,
        "rumble_hpf": True,
        "noise_gate": True,
        "gate_thresh_db": -55.0,
        "gate_attack_ms": 5.0,
        "gate_release_ms": 120.0,
        "denoise": False,
        "denoise_strength": 0.30,
        "eq_enabled": True,
        "eq_low_db": 0.0,
        "eq_mid_db": 1.0,
        "eq_high_db": 5.0,
        "comp_enabled": True,
        "comp_thresh_db": -22.0,
        "comp_ratio": 3.0,
        "comp_makeup_db": 2.5,
        "echo_enabled": True,
        "echo_time_ms": 480.0,
        "echo_feedback": 0.65,
        "echo_damping": 0.25,
        "echo_wet": 0.45,
        "echo_pingpong": True,
        "reverb_enabled": True,
        "reverb_room_size": 0.98,
        "reverb_damping": 0.10,
        "reverb_width": 1.0,
        "reverb_wet": 0.55
    },
    "⚡ Raw Direct Monitor (Bypass)": {
        "description": "Zero-latency pure pass-through for monitoring raw microphone input directly.",
        "input_gain": 1.0,
        "output_volume": 1.0,
        "rumble_hpf": False,
        "noise_gate": False,
        "gate_thresh_db": -70.0,
        "gate_attack_ms": 5.0,
        "gate_release_ms": 50.0,
        "denoise": False,
        "denoise_strength": 0.0,
        "eq_enabled": False,
        "eq_low_db": 0.0,
        "eq_mid_db": 0.0,
        "eq_high_db": 0.0,
        "comp_enabled": False,
        "comp_thresh_db": 0.0,
        "comp_ratio": 1.0,
        "comp_makeup_db": 0.0,
        "echo_enabled": False,
        "echo_time_ms": 200.0,
        "echo_feedback": 0.0,
        "echo_damping": 0.0,
        "echo_wet": 0.0,
        "echo_pingpong": False,
        "reverb_enabled": False,
        "reverb_room_size": 0.5,
        "reverb_damping": 0.5,
        "reverb_width": 1.0,
        "reverb_wet": 0.0
    }
}


def apply_preset_to_pipeline(pipeline, preset_dict):
    """Update all DSP pipeline variables from a preset dictionary."""
    pipeline.input_gain = preset_dict.get("input_gain", 1.0)
    pipeline.output_volume = preset_dict.get("output_volume", 1.0)
    
    # Noise filter
    pipeline.noise_filter.rumble_filter_enabled = preset_dict.get("rumble_hpf", True)
    pipeline.noise_filter.gate_enabled = preset_dict.get("noise_gate", True)
    pipeline.noise_filter.threshold_db = preset_dict.get("gate_thresh_db", -50.0)
    pipeline.noise_filter.attack_ms = preset_dict.get("gate_attack_ms", 4.0)
    pipeline.noise_filter.release_ms = preset_dict.get("gate_release_ms", 70.0)
    pipeline.noise_filter.denoise_enabled = preset_dict.get("denoise", False)
    pipeline.noise_filter.denoise_strength = preset_dict.get("denoise_strength", 0.35)
    
    # EQ
    pipeline.eq.enabled = preset_dict.get("eq_enabled", True)
    pipeline.eq.update_gains(
        preset_dict.get("eq_low_db", 0.0),
        preset_dict.get("eq_mid_db", 0.0),
        preset_dict.get("eq_high_db", 0.0)
    )
    
    # Dynamics / Compressor
    pipeline.dynamics.comp_enabled = preset_dict.get("comp_enabled", True)
    pipeline.dynamics.threshold_db = preset_dict.get("comp_thresh_db", -18.0)
    pipeline.dynamics.ratio = preset_dict.get("comp_ratio", 3.0)
    pipeline.dynamics.makeup_gain_db = preset_dict.get("comp_makeup_db", 2.0)
    
    # Echo
    pipeline.echo.enabled = preset_dict.get("echo_enabled", False)
    pipeline.echo.delay_ms = preset_dict.get("echo_time_ms", 250.0)
    pipeline.echo.feedback = preset_dict.get("echo_feedback", 0.35)
    pipeline.echo.damping = preset_dict.get("echo_damping", 0.30)
    pipeline.echo.wet = preset_dict.get("echo_wet", 0.20)
    pipeline.echo.pingpong = preset_dict.get("echo_pingpong", True)
    
    # Reverb
    pipeline.reverb.enabled = preset_dict.get("reverb_enabled", False)
    pipeline.reverb.room_size = preset_dict.get("reverb_room_size", 0.75)
    pipeline.reverb.damping = preset_dict.get("reverb_damping", 0.25)
    pipeline.reverb.width = preset_dict.get("reverb_width", 1.0)
    pipeline.reverb.wet = preset_dict.get("reverb_wet", 0.25)


def export_preset_file(filepath, preset_dict):
    """Save preset to JSON file."""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(preset_dict, f, indent=4)


def import_preset_file(filepath):
    """Load preset from JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)
