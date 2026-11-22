"""Diagnose a local ASTRA setup without starting the web server.

Usage (from the project folder):   python scripts/check_setup.py
Checks .env, credentials, the database (non-destructive self-test) and Gemini.
Never prints secret values.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

try:
    from dotenv import load_dotenv
except ImportError:
    raise SystemExit("python-dotenv is not installed. Activate your venv and run: pip install -r requirements.txt")
load_dotenv(os.path.join(ROOT, ".env"))

from flask import Flask  # noqa: E402

from astra.config import Config  # noqa: E402
from astra.db import db  # noqa: E402
from astra.diagnostics import run_all  # noqa: E402


def main():
    app = Flask("astra-check")
    app.config.from_object(Config)
    db.init(Config)
    print("\nASTRA setup check\n" + "-" * 60)
    failed = 0
    with app.app_context():
        for c in run_all(app.config):
            mark = "OK  " if c["ok"] and not c.get("warn") else ("WARN" if c["ok"] or c.get("warn") else "FAIL")
            print(f"[{mark}] {c['name']}: {c['detail']}")
            if (not c["ok"] or c.get("warn")) and c.get("hint"):
                print(f"       -> {c['hint']}")
            failed += 0 if c["ok"] or c.get("warn") else 1
    print("-" * 60)
    print("All good — start with: python app.py" if not failed else f"{failed} problem(s) found.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
