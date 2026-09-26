"""
SingerPro - Live Vocal Monitoring & Effects Studio
Windows Native Application Entrypoint
"""

import sys
import os
import ctypes

def enable_windows_dpi_awareness():
    """Enable Per-Monitor V2 High DPI awareness on Windows for crisp typography."""
    if sys.platform == 'win32':
        try:
            # Per-monitor DPI awareness
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

def main():
    enable_windows_dpi_awareness()
    from app_ui import run_app
    run_app()

if __name__ == "__main__":
    main()
