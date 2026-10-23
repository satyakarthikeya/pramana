"""Email-and-password accounts with server-side sessions, stored in the run database.

Passwords are kept only as salted scrypt hashes (standard library, no extra dependency).
A session is a random token whose SHA-256 is stored; the browser holds the token in an
HttpOnly cookie, so signing out really ends it. Nothing here decides a verdict or touches
verification.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

SESSION_COOKIE = "pramana_session"
SESSION_DAYS = 7
MIN_PASSWORD = 8
MAX_PASSWORD = 128  # bounds the work an attacker can force per request
MAX_EMAIL = 254
LOGIN_FAILURES = 5  # per email and address
ADDRESS_FAILURES = 30  # per address, across all emails (password spraying)
SIGNUPS = 10  # per address per window
LOCKOUT_SECONDS = 15 * 60
MAX_TRACKED = 5000  # bound on remembered keys, so an attacker cannot grow the map

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


class AuthError(ValueError):
    """A fixed, safe-to-display message for the person signing in."""


class TooManyAttempts(AuthError):
    """Too many failed sign-ins for this email and address."""


class User(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    user_id: UUID
    email: str


def normalise_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > MAX_EMAIL or not _EMAIL.match(email):
        raise AuthError("Enter a valid email address.")
    return email


def check_password(value: str) -> None:
    if len(value) < MIN_PASSWORD:
        raise AuthError(f"Use at least {MIN_PASSWORD} characters for the password.")
    if len(value) > MAX_PASSWORD:
        raise AuthError(f"Use at most {MAX_PASSWORD} characters for the password.")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return "scrypt${n}${r}${p}${salt}${digest}".format(
        **_SCRYPT,
        salt=base64.b64encode(salt).decode(),
        digest=base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Verified against when the email is unknown, so timing does not reveal which emails exist.
_DUMMY_HASH = hash_password("not-a-real-password")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    """Users and sessions in SQLite, plus a small in-memory brake on repeated failures."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, created_at TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TEXT NOT NULL)""")
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    def user_count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def signup(
        self, email: str, password: str, *, allow_signup: bool, client: str = "?"
    ) -> tuple[User, bool]:
        """Create an account. Returns the user and whether they are the first account.

        The first-account decision and the insert happen in one write transaction, so two
        simultaneous sign-ups on an empty server cannot both become "the first".
        """
        email = normalise_email(email)
        check_password(password)
        key = f"signup|{client}"
        if self._blocked(key, SIGNUPS):
            raise TooManyAttempts("Too many sign-ups from this address. Try again later.")
        self._fail(key)
        user_id = uuid4()
        digest = hash_password(password)
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            connection.execute("BEGIN IMMEDIATE")
            first = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            if not first and not allow_signup:
                connection.execute("ROLLBACK")
                raise AuthError("Sign-up is closed on this server. Ask the owner for an account.")
            try:
                connection.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?)",
                    (str(user_id), email, digest, datetime.now(UTC).isoformat()),
                )
            except sqlite3.IntegrityError:
                connection.execute("ROLLBACK")
                raise AuthError(
                    "An account with this email already exists. Sign in instead."
                ) from None
            connection.execute("COMMIT")
        finally:
            connection.close()
        return User(user_id=user_id, email=email), first

    def _blocked(self, key: str, limit: int = LOGIN_FAILURES) -> bool:
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._failures.get(key, []) if now - t < LOCKOUT_SECONDS]
            if recent:
                self._failures[key] = recent
            else:
                self._failures.pop(key, None)
            return len(recent) >= limit

    def _fail(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._failures) >= MAX_TRACKED and key not in self._failures:
                # Forget keys whose failures have all aged out; if that is not enough, the
                # oldest half, so the map stays bounded whatever an attacker sends.
                self._failures = {
                    k: v for k, v in self._failures.items() if v and now - v[-1] < LOCKOUT_SECONDS
                }
                if len(self._failures) >= MAX_TRACKED:
                    keep = sorted(self._failures.items(), key=lambda item: item[1][-1])
                    self._failures = dict(keep[len(keep) // 2 :])
            self._failures.setdefault(key, []).append(now)

    def login(self, email: str, password: str, *, client: str) -> User:
        """Verify credentials with one generic failure message and a per-address brake."""
        email = email.strip().lower()[:MAX_EMAIL]
        key, address = f"{email}|{client}", f"address|{client}"
        if self._blocked(key) or self._blocked(address, ADDRESS_FAILURES):
            raise TooManyAttempts("Too many failed attempts. Try again in a few minutes.")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id, password_hash FROM users WHERE email = ?", (email,)
            ).fetchone()
        stored = row[1] if row else _DUMMY_HASH
        ok = verify_password(password[:MAX_PASSWORD], stored) and row is not None
        if not ok:
            self._fail(key)
            self._fail(address)
            raise AuthError("Incorrect email or password.")
        with self._lock:
            self._failures.pop(key, None)
        return User(user_id=UUID(row[0]), email=email)

    def open_session(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(UTC) + timedelta(days=SESSION_DAYS)
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE expires_at < ?", (datetime.now(UTC).isoformat(),)
            )
            connection.execute(
                "INSERT INTO sessions VALUES (?, ?, ?)",
                (_token_hash(token), str(user.user_id), expires.isoformat()),
            )
        return token

    def user_for(self, token: str | None) -> User | None:
        if not token:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT u.user_id, u.email, s.expires_at FROM sessions s "
                "JOIN users u ON u.user_id = s.user_id WHERE s.token_hash = ?",
                (_token_hash(token),),
            ).fetchone()
        if row is None or datetime.fromisoformat(row[2]) < datetime.now(UTC):
            return None
        return User(user_id=UUID(row[0]), email=row[1])

    def close_session(self, token: str | None) -> None:
        if token:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),)
                )
