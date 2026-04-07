# cafeina.py
import ctypes
import time
import sys
import argparse
import yaml
import logging
import os
import signal
import subprocess
from logging.handlers import RotatingFileHandler
from pathlib import Path

"""
=== Audit Documentation: Windows API ===
- Function: SetThreadExecutionState
- Official URL: https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate
- Description: Prevents the system from entering sleep or turning off the display while the current thread is running. No admin privileges required.
"""

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

PID_FILE_NAME = "cafeina.pid"
MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3
CREATE_NO_WINDOW = 0x08000000

def get_pid_file_path() -> Path:
    return Path(__file__).parent / PID_FILE_NAME

def write_pid_file() -> int:
    pid = os.getpid()
    pid_file = get_pid_file_path()
    try:
        pid_file.write_text(str(pid), encoding='utf-8')
    except OSError:
        pass
    return pid

def remove_pid_file() -> None:
    pid_file = get_pid_file_path()
    try:
        if pid_file.exists():
            pid_file.unlink()
    except OSError:
        pass

def stop_existing_instance(logger: logging.Logger = None) -> bool:
    pid_file = get_pid_file_path()
    if not pid_file.exists():
        return True

    try:
        pid = int(pid_file.read_text(encoding='utf-8').strip())
    except (ValueError, OSError):
        remove_pid_file()
        return True

    try:
        if sys.platform == "win32":
            # Aciona o taskkill cegamente. /F = Force, /T = Tree (mata a árvore de processos filhos)
            result = subprocess.run(
                ["taskkill.exe", "/F", "/T", "/PID", str(pid)], 
                capture_output=True, 
                text=True,
                creationflags=CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                msg = f"Log: Instância anterior do Cafeina finalizada (PID {pid})."
                if logger: logger.info(msg)
                else: print(msg)
            else:
                # Retorno indicando que o processo não foi encontrado (provavelmente já morreu)
                if "128" not in result.stderr:
                    msg = f"Log: Aviso ao tentar finalizar PID {pid}: {result.stderr.strip()}"
                    if logger: logger.warning(msg)
        else:
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
                
    except Exception as e:
        if logger: logger.error(f"Erro inesperado ao matar PID {pid}: {e}")
    finally:
        remove_pid_file()
        
    return True

def detect_background_mode() -> bool:
    # A verificação pelo pythonw.exe continua sendo a principal
    if sys.executable and sys.executable.lower().endswith("pythonw.exe"):
        return True
    return False

def setup_file_logger() -> logging.Logger:
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
    yaml_path = Path(__file__).parent / "i18n.yaml"
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
    if force_mode == "bg":
        is_background = True
    elif force_mode == "fg":
        is_background = False
    else:
        is_background = detect_background_mode()

    logger = setup_file_logger() if is_background else None
    msgs = load_i18n(lang, logger, is_background)

    stop_existing_instance(logger)

    if is_background:
        write_pid_file()

    def emit_log(key: str, **kwargs) -> None:
        msg = msgs[key].format(**kwargs) if kwargs else msgs[key]
        if is_background:
            logger.info(msg)
        else:
            print(msg)

    emit_log("start", duration=duration_minutes)

    if is_background:
        logger.info("Log: Modo background. Use 'cafeina --stop' para encerrar.")
    else:
        print(msgs["interrupt_hint"])

    try:
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )

        elapsed_minutes = 0
        while elapsed_minutes < duration_minutes:
            remaining_minutes = duration_minutes - elapsed_minutes

            if is_background:
                if elapsed_minutes > 0 and elapsed_minutes % 15 == 0:
                    logger.info(msgs["progress"].format(elapsed=elapsed_minutes, remaining=remaining_minutes))
            else:
                sys.stdout.write("\r" + msgs["progress"].format(elapsed=elapsed_minutes, remaining=remaining_minutes))
                sys.stdout.flush()

            time.sleep(60)
            elapsed_minutes += 1

        if not is_background:
            print()
        emit_log("completed", duration=duration_minutes)

    except KeyboardInterrupt:
        if not is_background:
            print()
        emit_log("interrupted")
    except Exception as e:
        if is_background:
            logger.error(f"Erro inesperado: {e}")
        else:
            print(f"\nErro inesperado: {e}")
    finally:
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        emit_log("restored")
        if is_background:
            remove_pid_file()

def shield_streams() -> None:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')

def main():
    shield_streams()
    
    parser = argparse.ArgumentParser(description="Prevents the system from hibernating/sleeping.")
    parser.add_argument("--duration", "-d", type=int, default=180, help="Time in minutes (default: 180).")
    parser.add_argument("--lang", "-l", type=str, default=None, help="Language code (e.g., en, pt).")
    parser.add_argument("--background", "-b", action="store_true", default=False, help="Force background mode.")
    parser.add_argument("--foreground", "-f", action="store_true", default=False, help="Force foreground mode.")
    parser.add_argument("--stop", "-s", action="store_true", default=False, help="Stop running instance.")

    args = parser.parse_args()

    if args.stop:
        logger = setup_file_logger()
        logger.info("Log: Recebido comando '--stop'. Tentando encerrar instância em background.")
        
        if stop_existing_instance(logger):
            msg = "Log: Processo de encerramento concluído."
        else:
            msg = "Log: Falha ao tentar encerrar a instância."
            
        logger.info(msg)
        print(msg)
        return

    force_mode = None
    if args.background:
        force_mode = "bg"
    elif args.foreground:
        force_mode = "fg"

    is_target_bg = (force_mode == "bg") or (force_mode is None and detect_background_mode())

    if is_target_bg and not os.environ.get("CAFEINA_DETACHED"):
        cmd = [sys.executable, sys.argv[0]]
        cmd.extend(["--duration", str(args.duration)])
        if args.lang:
            cmd.extend(["--lang", args.lang])
        cmd.append("--background")

        env = os.environ.copy()
        env["CAFEINA_DETACHED"] = "1"

        creationflags = 0x00000008 if sys.platform == "win32" else 0
        
        subprocess.Popen(cmd, env=env, creationflags=creationflags, close_fds=True)
        sys.exit(0)

    keep_awake(args.duration, args.lang, force_mode)

if __name__ == "__main__":
    main()