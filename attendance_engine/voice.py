import threading
import subprocess
import os

_voice_lock = threading.Lock()
_last_spoken_time = 0

def _speak_worker(text):
    try:
        # Use PowerShell SAPI speech synthesis for guaranteed Windows native speech
        clean_text = text.replace("'", "").replace('"', "")
        cmd = f"Add-Type -AssemblyName System.Speech; $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; $synth.Rate = 1; $synth.Speak('{clean_text}')"
        subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=5)
    except Exception:
        # Fallback to simple console beep if audio fails
        try:
            import winsound
            winsound.Beep(1000, 200)
        except Exception:
            pass

def announce_attendance(name):
    """
    Asynchronously announces attendance confirmation without blocking video stream.
    """
    msg = f"Attendance confirmed for {name}. Welcome!"
    t = threading.Thread(target=_speak_worker, args=(msg,), daemon=True)
    t.start()
