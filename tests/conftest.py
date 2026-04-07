"""Pytest configuration: ensures the project root is on sys.path so that
the single-file module 'cafeina.py' can be imported from the tests/ directory."""

import sys
from pathlib import Path

# Add the project root (parent of tests/) to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
root_str = str(PROJECT_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)
