# cafeina.py
import ctypes
import time
import sys
import argparse
import yaml
from pathlib import Path

"""
=== Audit Documentation: Windows API ===
- Function: SetThreadExecutionState
- Official URL: https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate
- Description: Prevents the system from entering sleep or turning off the display while the current thread is running. No admin privileges required.
- Constants:
  - ES_CONTINUOUS (0x80000000): Informs the system that the state being set should remain in effect until the next call that uses ES_CONTINUOUS.
  - ES_SYSTEM_REQUIRED (0x00000001): Forces the system to be in the working state.
  - ES_DISPLAY_REQUIRED (0x00000002): Forces the display to be on.
"""

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

def load_i18n(lang_override: str) -> dict:
    yaml_path = Path(__file__).parent / "i18n.yaml"
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            default_lang = data.get("default_language", "en")
            target_lang = lang_override if lang_override else default_lang
            
            if target_lang not in data:
                target_lang = default_lang
                
            return data.get(target_lang, data.get("en"))
    except Exception as e:
        print(f"Error loading i18n.yaml: {e}. Falling back to default English.")
        return {
            "start": "Log: Starting monitoring... {duration} min.",
            "interrupt_hint": "Log: Press Ctrl+C to interrupt.",
            "progress": "Log: Elapsed: {elapsed} min | Remaining: {remaining} min",
            "completed": "\nLog: Completed {duration} min.",
            "interrupted": "\nLog: Interrupted.",
            "restored": "Log: Restored."
        }

def keep_awake(duration_minutes: int, lang: str) -> None:
    msgs = load_i18n(lang)
    
    print(msgs["start"].format(duration=duration_minutes))
    print(msgs["interrupt_hint"])
    
    try:
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )
        
        elapsed_minutes = 0
        while elapsed_minutes < duration_minutes:
            remaining_minutes = duration_minutes - elapsed_minutes
            
            sys.stdout.write("\r" + msgs["progress"].format(elapsed=elapsed_minutes, remaining=remaining_minutes))
            sys.stdout.flush()
            
            time.sleep(60)
            elapsed_minutes += 1
            
        print(msgs["completed"].format(duration=duration_minutes))
        
    except KeyboardInterrupt:
        print(msgs["interrupted"])
    finally:
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        print(msgs["restored"])

def main():
    parser = argparse.ArgumentParser(description="Prevents the system from hibernating/sleeping.")
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=180,
        help="Time in minutes the program should keep running (default: 180)."
    )
    parser.add_argument(
        "--lang", "-l",
        type=str,
        default=None,
        help="Force a specific language code (e.g., en, pt, es, fr, de, ru, zh)."
    )
    
    args = parser.parse_args()
    keep_awake(args.duration, args.lang)

if __name__ == "__main__":
    main()