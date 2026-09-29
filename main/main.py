"""Compatibility launcher for the terminal interface."""

from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bilibili_ds.cli.menu import run_menu


if __name__ == "__main__":
    run_menu()
