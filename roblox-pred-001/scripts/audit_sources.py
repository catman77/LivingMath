"""Thin repository CLI; install the editable package first."""
from pathlib import Path
from roblox_pred.cli import main

if __name__ == '__main__':
    raise SystemExit(main(Path(__file__).stem))
