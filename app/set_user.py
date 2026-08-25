"""Add or update a login user. The password is hashed; never stored in plain text."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from werkzeug.security import generate_password_hash

_HERE = os.path.dirname(os.path.abspath(__file__))


def users_path(local: bool = False) -> str:
    if local:
        return os.path.join(_HERE, "users.json")
    runs = os.environ.get("RUNS_DIR") or os.path.join(_HERE, "runs")
    os.makedirs(runs, exist_ok=True)
    return os.path.join(runs, "users.json")


def save_user(username: str, password: str, path: str) -> None:
    username = username.strip().lower()
    if not username or not password:
        raise SystemExit("username and password are required")
    data = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    data[username] = generate_password_hash(password)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def main() -> None:
    p = argparse.ArgumentParser(description="Hash and save a Screenshot Tool login.")
    p.add_argument("username", nargs="?", help="login name, e.g. sagar")
    p.add_argument("--local", action="store_true", help="write app/users.json instead of runs/users.json")
    args = p.parse_args()
    username = args.username or input("Username: ").strip()
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("passwords do not match")
    path = users_path(local=args.local)
    save_user(username, password, path)
    print(f"saved hashed password for {username.strip().lower()} -> {path}")


if __name__ == "__main__":
    main()
