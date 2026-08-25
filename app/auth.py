"""Username/password login. Passwords in users.json are hashed (pbkdf2)."""
from __future__ import annotations

import hmac
import json
import os
from functools import wraps

from flask import redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

_HERE = os.path.dirname(os.path.abspath(__file__))
_HASH_PREFIXES = ("pbkdf2:", "scrypt:", "argon2:")


def _is_hash(secret: str) -> bool:
    return secret.startswith(_HASH_PREFIXES)


def _users_file_paths() -> list[str]:
    runs_dir = os.environ.get("RUNS_DIR") or os.path.join(_HERE, "runs")
    return [
        os.path.join(runs_dir, "users.json"),
        os.path.join(_HERE, "users.json"),
    ]


def _load_json_users(path: str) -> dict[str, str]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    users: dict[str, str] = {}
    changed = False
    for name, secret in data.items():
        if isinstance(secret, dict):
            secret = secret.get("password", "")
        if not name or not secret:
            continue
        secret = str(secret)
        key = str(name).strip().lower()
        if not _is_hash(secret):
            secret = generate_password_hash(secret)
            changed = True
        users[key] = secret
        data[name] = secret
    if changed:
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp, path)
            os.chmod(path, 0o600)
        except OSError:
            pass
    return users


def _parse_auth_users_env(raw: str) -> dict[str, str]:
    users: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        name, password = part.split(":", 1)
        name = name.strip().lower()
        if name and password:
            users[name] = password
    return users


def load_users() -> dict[str, str]:
    """username(lowercase) -> password or hash. .env AUTH_USERS plus users.json."""
    users: dict[str, str] = {}
    env = os.environ.get("AUTH_USERS", "").strip()
    if env:
        users.update(_parse_auth_users_env(env))
    for path in _users_file_paths():
        if os.path.isfile(path):
            users.update(_load_json_users(path))
    # Local (./run.sh or docker without AUTH_USERS). Hosting sets ENVIRONMENT=production.
    if not users and os.environ.get("ENVIRONMENT", "").lower() != "production":
        users = {"user": "user"}
    return users


def verify_password(username: str, password: str) -> str | None:
    """Return the canonical username on success, else None."""
    key = (username or "").strip().lower()
    secret = load_users().get(key)
    if not secret or not password:
        return None
    if _is_hash(secret):
        ok = check_password_hash(secret, password)
    else:
        ok = hmac.compare_digest(secret, password)
    return key if ok else None


def current_user() -> str | None:
    return session.get("user")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped
