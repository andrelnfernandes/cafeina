# cafeina.py
import ctypes
import time
import sys
import argparse
import yaml
import logging
import os
import signal
from logging.handlers import RotatingFileHandler
from pathlib import Path

"""
=== Audit Documentation: Windows API ===
- Function: SetThreadExecutionState
- Official URL: https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate
- Description: Prevents the system from entering sleep or turning off the display while the current thread is running. No admin privileges required.
"""

# Windows API flags for SetThreadExecutionState
ES_CONTINUOUS = 0x80000000       # Maintains the active state until explicitly reset
ES_SYSTEM_REQUIRED = 0x00000001  # Prevents system sleep
ES_DISPLAY_REQUIRED = 0x00000002 # Prevents the monitor from turning off

# PID file constants for background process management
PID_FILE_NAME = "cafeina.pid"
# Max log file size before rotation (5 MB)
MAX_LOG_BYTES = 5 * 1024 * 1024
# Number of rotated log files to keep
LOG_BACKUP_COUNT = 3


def get_pid_file_path() -> Path:
    """Return the path to the PID file."""
    return Path(__file__).parent / PID_FILE_NAME


def is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    try:
        os.kill(pid, 0)  # Signal 0 checks process existence without affecting it
        return True
    except (OSError, ProcessLookupError):
        return False


def write_pid_file() -> int:
    """Write the current process PID to the PID file.

    Returns:
        The current process PID.
    """
    pid = os.getpid()
    pid_file = get_pid_file_path()
    try:
        pid_file.write_text(str(pid), encoding='utf-8')
    except OSError:
        pass  # Non-critical; continue even if PID file can't be written
    return pid


def remove_pid_file() -> None:
    """Remove the PID file if it exists."""
    pid_file = get_pid_file_path()
    try:
        if pid_file.exists():
            pid_file.unlink()
    except OSError:
        pass  # Non-critical cleanup


def stop_existing_instance(logger: logging.Logger = None) -> bool:
    """Check for a running Cafeina instance and stop it if found.

    Args:
        logger: Optional logger for status messages.

    Returns:
        True if an existing instance was stopped or none was found.
        False if the existing process couldn't be stopped.
    """
    pid_file = get_pid_file_path()
    if not pid_file.exists():
        return True

    try:
        pid = int(pid_file.read_text(encoding='utf-8').strip())
    except (ValueError, OSError):
        # Stale or corrupted PID file; clean it up
        remove_pid_file()
        return True

    if not is_process_running(pid):
        # Stale PID file; process is no longer running
        remove_pid_file()
        return True

    # Attempt to gracefully terminate the existing process
    try:
        os.kill(pid, signal.SIGTERM)
        # Wait briefly for the process to exit
        time.sleep(1)
        if is_process_running(pid):
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)
        remove_pid_file()
        if logger:
            logger.info(f"Log: Stopped previous Cafeina instance (PID {pid}).")
        else:
            print(f"Log: Stopped previous Cafeina instance (PID {pid}).")
        return True
    except (OSError, ProcessLookupError):
        remove_pid_file()
        return True


def detect_background_mode() -> bool:
    """Detect if the script is running without a console window.

    Returns True when:
    - Executed via pythonw.exe (Windows GUI Python interpreter)
    - sys.stdout is None (no console attached)
    """
    if sys.stdout is None:
        return True
    if sys.executable and sys.executable.lower().endswith("pythonw.exe"):
        return True
    return False


def setup_file_logger() -> logging.Logger:
    """Configure a file-based logger with rotation for background mode execution.

    Writes to cafeina.log in the same directory as this script.
    Automatically rotates the log file when it reaches MAX_LOG_BYTES.
    """
    log_file = Path(__file__).parent / "cafeina.log"
    logger = logging.getLogger("Cafeina")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=MAX_LOG_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

def load_i18n(lang_override: str, logger: logging.Logger, is_bg: bool) -> dict:
    """Load internationalization messages from i18n.yaml.

    Args:
        lang_override: Language code to force (e.g., 'en', 'pt'). None uses YAML default.
        logger: File logger instance (only used when is_bg is True).
        is_bg: Whether we're running in background mode.

    Returns:
        Dictionary of translated message strings.
    """
    yaml_path = Path(__file__).parent / "i18n.yaml"
    # Fallback messages in case i18n.yaml is missing or fails to parse
    fallback_msgs = {
        "start": "Log: Iniciando monitoramento... {duration} min.",
        "interrupt_hint": "Log: Pressione Ctrl+C para interromper.",
        "progress": "Log: Decorrido: {elapsed} min | Restante: {remaining} min",
        "completed": "Log: Concluído {duration} min.",
        "interrupted": "Log: Interrompido.",
        "restored": "Log: Restaurado."
    }

    try:
        if not yaml_path.exists():
            return fallback_msgs

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            default_lang = data.get("default_language", "en")
            target_lang = lang_override if lang_override else default_lang

            if target_lang not in data:
                target_lang = default_lang

            return data.get(target_lang, data.get("en", fallback_msgs))
    except Exception as e:
        msg = f"Erro ao carregar i18n.yaml: {e}. Usando fallback."
        if is_bg and logger:
            logger.error(msg)
        elif not is_bg:
            print(msg)
        return fallback_msgs

def keep_awake(duration_minutes: int, lang: str, force_mode: str = None) -> None:
    """Main loop that keeps the system awake for the specified duration.

    Runs in either foreground mode (console output with live progress updates)
    or background mode (file-based logging with throttled progress entries).

    Args:
        duration_minutes: How long to keep the system awake, in minutes.
        lang: Language code for i18n messages. None uses the YAML default.
        force_mode: Explicit mode override. 'bg' forces background, 'fg' forces
                    foreground. None auto-detects based on console availability.
    """
    # Detect mode or use explicit override
    if force_mode == "bg":
        is_background = True
    elif force_mode == "fg":
        is_background = False
    else:
        is_background = detect_background_mode()

    # In background mode, use a file logger; otherwise, log to stdout
    logger = setup_file_logger() if is_background else None
    msgs = load_i18n(lang, logger, is_background)

    # Stop any previously running Cafeina instance before starting a new one
    stop_existing_instance(logger)

    # Write current PID to file for background process management
    if is_background:
        write_pid_file()

    def emit_log(key: str, **kwargs) -> None:
        """Format and emit a log message. Sends to file or stdout based on mode."""
        msg = msgs[key].format(**kwargs) if kwargs else msgs[key]
        if is_background:
            logger.info(msg)
        else:
            print(msg)

    emit_log("start", duration=duration_minutes)

    if is_background:
        logger.info("Log: Modo background. Use 'cafeina --stop' to terminate.")
    else:
        print(msgs["interrupt_hint"])

    try:
        # Activate Windows thread execution state to prevent sleep
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )

        elapsed_minutes = 0
        while elapsed_minutes < duration_minutes:
            remaining_minutes = duration_minutes - elapsed_minutes

            if is_background:
                # Throttle log entries in background mode (every 15 minutes)
                # to avoid bloating the log file
                if elapsed_minutes > 0 and elapsed_minutes % 15 == 0:
                    logger.info(msgs["progress"].format(elapsed=elapsed_minutes, remaining=remaining_minutes))
            else:
                # In foreground mode, update the same line in place using \r
                sys.stdout.write("\r" + msgs["progress"].format(elapsed=elapsed_minutes, remaining=remaining_minutes))
                sys.stdout.flush()

            time.sleep(60)
            elapsed_minutes += 1

        if not is_background:
            print()  # Newline after the in-place progress line
        emit_log("completed", duration=duration_minutes)

    except KeyboardInterrupt:
        if not is_background:
            print()  # Newline for clean output on Ctrl+C
        emit_log("interrupted")
    except Exception as e:
        if is_background:
            logger.error(f"Erro inesperado: {e}")
        else:
            print(f"\nErro inesperado: {e}")
    finally:
        # Always restore default power management state
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        emit_log("restored")
        # Clean up PID file on exit
        if is_background:
            remove_pid_file()

def main():
    """Entry point for the CLI. Parses arguments and delegates to keep_awake."""
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
        help="Force a specific language code (e.g., en, pt, es)."
    )
    parser.add_argument(
        "--background", "-b",
        action="store_true",
        default=False,
        help="Force background mode (no console output, log to file)."
    )
    parser.add_argument(
        "--foreground", "-f",
        action="store_true",
        default=False,
        help="Force foreground mode (console output, even if launched via pythonw.exe)."
    )
    parser.add_argument(
        "--stop", "-s",
        action="store_true",
        default=False,
        help="Stop any running Cafeina background instance and exit."
    )

    args = parser.parse_args()

    # Handle --stop flag: terminate existing instance and exit
    if args.stop:
        if stop_existing_instance():
            print("Log: Cafeina background instance stopped (if one was running).")
        else:
            print("Log: Could not stop existing Cafeina instance.")
        return

    # Determine force_mode from explicit flags
    force_mode = None
    if args.background:
        force_mode = "bg"
    elif args.foreground:
        force_mode = "fg"

    keep_awake(args.duration, args.lang, force_mode)

if __name__ == "__main__":
    main()