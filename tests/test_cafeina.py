"""Unit tests for cafeina.py

Covers: PID file management, process detection, i18n loading, background mode detection,
CLI argument parsing, and logger setup. The main keep_awake() loop is not exercised
end-to-end because it calls Windows-only ctypes APIs and sleeps for minutes; instead,
its mode-selection logic is verified indirectly through integration-style assertions.

Run with:
    python -m pytest tests/test_cafeina.py -v
"""

import os
import signal
import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

# We import the module under test so that patching targets the correct namespace.
import cafeina


class TestPIDFileManagement(unittest.TestCase):
    """Tests for write_pid_file, remove_pid_file, get_pid_file_path."""

    def setUp(self):
        # Point the PID file to a temp directory so real files aren't touched.
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.pid_file = Path(self.tmp_dir.name) / "cafeina.pid"
        cafeina.PID_FILE_NAME = self.pid_file.name
        # Monkey-patch get_pid_file_path to return our temp location.
        self.original_get_pid_file_path = cafeina.get_pid_file_path

        def tmp_pid_path():
            return self.pid_file

        cafeina.get_pid_file_path = tmp_pid_path

    def tearDown(self):
        self.tmp_dir.cleanup()
        cafeina.get_pid_file_path = self.original_get_pid_file_path

    def test_write_pid_file_creates_file(self):
        pid = cafeina.write_pid_file()
        self.assertEqual(self.pid_file.read_text(), str(pid))
        self.assertEqual(pid, os.getpid())

    def test_remove_pid_file_deletes_file(self):
        cafeina.write_pid_file()
        self.assertTrue(self.pid_file.exists())
        cafeina.remove_pid_file()
        self.assertFalse(self.pid_file.exists())

    def test_remove_pid_file_no_op_when_missing(self):
        # Should not raise even when file doesn't exist
        cafeina.remove_pid_file()
        self.assertFalse(self.pid_file.exists())


class TestIsProcessRunning(unittest.TestCase):
    """Tests for is_process_running()."""

    def test_current_process_is_running(self):
        self.assertTrue(cafeina.is_process_running(os.getpid()))

    def test_nonexistent_pid_is_not_running(self):
        # PID 1 might exist on some systems; use a very high unlikely PID.
        fake_pid = 999999999
        self.assertFalse(cafeina.is_process_running(fake_pid))

    @patch("os.kill")
    def test_oserror_means_not_running(self, mock_kill):
        mock_kill.side_effect = OSError("No such process")
        self.assertFalse(cafeina.is_process_running(12345))

    @patch("os.kill")
    def test_process_lookup_error_means_not_running(self, mock_kill):
        mock_kill.side_effect = ProcessLookupError()
        self.assertFalse(cafeina.is_process_running(12345))


class TestStopExistingInstance(unittest.TestCase):
    """Tests for stop_existing_instance()."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.pid_file = Path(self.tmp_dir.name) / "cafeina.pid"

        def tmp_pid_path():
            return self.pid_file

        self.orig_get_pid_file_path = cafeina.get_pid_file_path
        cafeina.get_pid_file_path = tmp_pid_path

    def tearDown(self):
        self.tmp_dir.cleanup()
        cafeina.get_pid_file_path = self.orig_get_pid_file_path

    def test_no_pid_file_returns_true(self):
        self.assertTrue(cafeina.stop_existing_instance())

    def test_stale_pid_file_is_cleaned(self):
        # Write a PID for a non-existent process.
        self.pid_file.write_text("999999999", encoding="utf-8")
        result = cafeina.stop_existing_instance()
        self.assertTrue(result)
        self.assertFalse(self.pid_file.exists())

    def test_corrupt_pid_file_is_cleaned(self):
        self.pid_file.write_text("not-a-number", encoding="utf-8")
        result = cafeina.stop_existing_instance()
        self.assertTrue(result)
        self.assertFalse(self.pid_file.exists())

    @patch("cafeina.is_process_running")
    @patch("os.kill")
    def test_stops_running_process(self, mock_kill, mock_is_running):
        mock_is_running.side_effect = [True, False]  # Running initially, then stopped after SIGTERM
        self.pid_file.write_text("54321", encoding="utf-8")
        result = cafeina.stop_existing_instance()
        self.assertTrue(result)
        mock_kill.assert_any_call(54321, signal.SIGTERM)
        self.assertFalse(self.pid_file.exists())

    @patch("cafeina.is_process_running")
    @patch("os.kill")
    def test_escalates_to_sigkill(self, mock_kill, mock_is_running):
        # Process still running after SIGTERM -> escalate to SIGKILL
        mock_is_running.side_effect = [True, True, False]
        self.pid_file.write_text("54321", encoding="utf-8")
        result = cafeina.stop_existing_instance()
        self.assertTrue(result)
        calls = [
            mock.call(54321, signal.SIGTERM),
            mock.call(54321, signal.SIGKILL),
        ]
        mock_kill.assert_has_calls(calls)


class TestDetectBackgroundMode(unittest.TestCase):
    """Tests for detect_background_mode()."""

    def test_stdout_none_means_background(self):
        with patch.object(cafeina.sys, "stdout", None):
            self.assertTrue(cafeina.detect_background_mode())

    def test_pythonw_exe_means_background(self):
        with patch.object(cafeina.sys, "executable", r"C:\Python\pythonw.exe"):
            with patch.object(cafeina.sys, "stdout", mock.MagicMock()):
                self.assertTrue(cafeina.detect_background_mode())

    def test_python_exe_means_foreground(self):
        with patch.object(cafeina.sys, "executable", r"C:\Python\python.exe"):
            with patch.object(cafeina.sys, "stdout", mock.MagicMock()):
                self.assertFalse(cafeina.detect_background_mode())

    def test_executable_none_means_foreground(self):
        with patch.object(cafeina.sys, "executable", None):
            with patch.object(cafeina.sys, "stdout", mock.MagicMock()):
                self.assertFalse(cafeina.detect_background_mode())


class TestSetupFileLogger(unittest.TestCase):
    """Tests for setup_file_logger()."""

    def test_returns_logger_instance(self):
        logger = cafeina.setup_file_logger()
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.level, logging.INFO)
        # Verify it has at least one handler using RotatingFileHandler
        self.assertTrue(
            any(isinstance(h, logging.handlers.RotatingFileHandler) for h in logger.handlers)
        )


class TestLoadI18n(unittest.TestCase):
    """Tests for load_i18n()."""

    def test_loads_default_english(self):
        msgs = cafeina.load_i18n(None, None, False)
        self.assertIn("start", msgs)
        self.assertIn("restored", msgs)

    def test_loads_portuguese(self):
        msgs = cafeina.load_i18n("pt", None, False)
        self.assertIn("Iniciando", msgs["start"])

    def test_loads_spanish(self):
        msgs = cafeina.load_i18n("es", None, False)
        self.assertIn("Iniciando monitoreo", msgs["start"])

    def test_falls_back_to_default_language_on_unknown(self):
        # Requesting a non-existent language falls back to i18n.yaml default (en).
        msgs = cafeina.load_i18n("xx", None, False)
        self.assertIn("Starting", msgs["start"])

    def test_missing_yaml_file_returns_fallback(self):
        with patch.object(Path, "exists", return_value=False):
            msgs = cafeina.load_i18n(None, None, False)
            self.assertIn("Iniciando monitoramento", msgs["start"])


class TestMainCLI(unittest.TestCase):
    """Tests for the CLI argument parsing in main()."""

    def test_default_arguments(self):
        with patch.object(cafeina, "keep_awake") as mock_keep:
            with patch.object(cafeina, "stop_existing_instance"):
                with patch("sys.argv", ["cafeina"]):
                    cafeina.main()
                    mock_keep.assert_called_once_with(180, None, None)

    def test_custom_duration(self):
        with patch.object(cafeina, "keep_awake") as mock_keep:
            with patch.object(cafeina, "stop_existing_instance"):
                with patch("sys.argv", ["cafeina", "-d", "60"]):
                    cafeina.main()
                    mock_keep.assert_called_once_with(60, None, None)

    def test_force_background(self):
        with patch.object(cafeina, "keep_awake") as mock_keep:
            with patch.object(cafeina, "stop_existing_instance"):
                with patch("sys.argv", ["cafeina", "-b"]):
                    cafeina.main()
                    mock_keep.assert_called_once_with(180, None, "bg")

    def test_force_foreground(self):
        with patch.object(cafeina, "keep_awake") as mock_keep:
            with patch.object(cafeina, "stop_existing_instance"):
                with patch("sys.argv", ["cafeina", "-f"]):
                    cafeina.main()
                    mock_keep.assert_called_once_with(180, None, "fg")

    def test_stop_flag(self):
        with patch.object(cafeina, "stop_existing_instance", return_value=True) as mock_stop:
            with patch.object(cafeina, "keep_awake") as mock_keep:
                with patch("sys.argv", ["cafeina", "--stop"]):
                    with patch("builtins.print"):
                        cafeina.main()
                        mock_stop.assert_called_once()
                        # keep_awake should NOT be called when --stop is used
                        mock_keep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
