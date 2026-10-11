"""Lets `python scripts/<name>.py` import the `facility` package from the repo root."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)  # data/ paths are relative to the repo root
