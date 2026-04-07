# Cafeina (Windows CLI)

A command-line utility written in Python to prevent the host operating system (Windows) from entering sleep mode or hibernating. Designed for corporate environments where administrative privileges are not available to install third-party software.

## Motivation (Why I built this)

You know the drill: corporate IT policies mandate a 13+ character password and aggressively lock your screen after just a few minutes of inactivity. It's incredibly frustrating when you're just monitoring a long-running batch process on the console or reading a dense technical document, and you're forced to constantly jiggle the mouse just to keep your session alive. 

Changing the Windows power settings usually doesn't work because Active Directory GPOs (Group Policy Objects) or MDM profiles silently override your local preferences. I needed a solution. While I liked the original *Caffeine* utility, I thought it would be an interesting challenge to build my own lightweight, Python-based CLI tool tailored to these exact restrictions. Thus, **Cafeina** was born.

## Installation (Local Environment)

To avoid polluting your global Python environment and to ensure the CLI command `cafeina` is mapped correctly, install the utility inside a Virtual Environment.

```powershell
# 1. Create the virtual environment
python -m venv .venv

# 2. Activate the virtual environment (Windows PowerShell)
.\.venv\Scripts\Activate.ps1
# Note: If corporate policies block script execution, run this first:
# Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy Unrestricted

# Alternative: Activate using Command Prompt (cmd.exe)
.\.venv\Scripts\activate.bat

# 3. Install the package and dependencies in editable mode
pip install -e .
```

## Usage

Once installed and with the virtual environment active, you can call the utility directly from anywhere in your terminal without typing `python cafeina.py`.

```bash
# Run with default time (180 minutes) and default language from i18n.yaml
cafeina

# Run with custom time (e.g., 60 minutes)
cafeina -d 60

# Force a specific language (e.g., Portuguese)
cafeina --lang pt
```

During execution, the script performs an in-place terminal update (no extra line breaks) displaying elapsed and remaining time. Pressing `Ctrl+C` immediately aborts the execution and restores the original power settings.

### CLI Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--duration N` | `-d N` | Duration in minutes (default: 180) |
| `--lang CODE` | `-l CODE` | Force a language (e.g., `en`, `pt`, `es`) |
| `--background` | `-b` | Force background mode (no console output, log to file) |
| `--foreground` | `-f` | Force foreground mode (console output) |
| `--stop` | `-s` | Stop any running background instance and exit |

### Background Mode

Cafeina can run silently in the background without a console window. Use the `--background` flag or launch via `pythonw.exe`:

```powershell
# Force background mode from the CLI
cafeina -b -d 120

# Launch without a console window
pythonw.exe cafeina.py -d 120

# Or use a .vbs script for a completely silent launch:
# Create a file `start_cafeina.vbs`:
#   CreateObject("Wscript.Shell").Run "pythonw.exe cafeina.py -d 120", 0, False
# Then double-click the .vbs file.
```

**Background mode features:**
- **No console window** — the process runs silently.
- **File logging with rotation** — output is written to `cafeina.log` (rotated at 5 MB, keeping 3 backups).
- **Throttled progress logs** — progress entries are written every 15 minutes.
- **Automatic process management** — starting a new instance automatically stops the previous one via a PID file (`cafeina.pid`).

### Stopping a Background Instance

```bash
# Gracefully stop any running background instance
cafeina --stop

# Or manually via Task Manager: end the pythonw.exe process
```

When stopped, power settings are automatically restored and the PID file is cleaned up.

## 🌍 Internationalization (i18n)

Translations are managed via the `i18n.yaml` file. The default language is defined inside the YAML structure (`default_language: en`). Currently supported:
* `en` (English)
* `pt` (Portuguese)
* `es` (Spanish)
* `fr` (French)
* `de` (German)
* `ru` (Russian)
* `zh` (Mandarin)

## Architecture & Audit

The script acts as a wrapper for the native Windows `kernel32.dll`. Injection is done via Python's `ctypes` module, invoking the `SetThreadExecutionState` function. 

The following API flags are combined (bitwise OR):
* `ES_CONTINUOUS` (`0x80000000`): Maintains the active state until explicitly reset.
* `ES_SYSTEM_REQUIRED` (`0x00000001`): Prevents system sleep.
* `ES_DISPLAY_REQUIRED` (`0x00000002`): Prevents the monitor from turning off.
