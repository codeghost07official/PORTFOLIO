"""Generate a secure ADMIN_PASSWORD_HASH for your .env / Render environment.

Usage:  python scripts/hash_password.py
The password is read interactively (never stored, never echoed).
"""
import getpass

from werkzeug.security import generate_password_hash

if __name__ == "__main__":
    pw = getpass.getpass("New admin password: ")
    if len(pw) < 12:
        raise SystemExit("Use at least 12 characters.")
    if pw != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    print("\nADMIN_PASSWORD_HASH=" + generate_password_hash(pw, method="scrypt"))
    print("\nTip: on Render, paste the value (everything after the '=') into the environment variable.")
