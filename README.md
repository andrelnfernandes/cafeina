# Cafeina (Windows CLI)

A command-line utility written in Python to prevent the host operating system (Windows) from entering sleep mode or hibernating. Designed for corporate environments where administrative privileges are not available to install third-party software.

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
