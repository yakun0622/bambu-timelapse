import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.storage.database import db


class AuthService:
    COOKIE_NAME = "bambu_timelapse_session"
    SESSION_DAYS = 30
    PBKDF2_ITERATIONS = 240_000

    def __init__(self):
        self.ensure_default_admin()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    @classmethod
    def hash_password(cls, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            cls.PBKDF2_ITERATIONS,
        )
        return (
            "pbkdf2_sha256$"
            + str(cls.PBKDF2_ITERATIONS)
            + "$"
            + base64.b64encode(salt).decode("ascii")
            + "$"
            + base64.b64encode(digest).decode("ascii")
        )

    @classmethod
    def verify_password(cls, password: str, encoded: str) -> bool:
        try:
            algorithm, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False

            salt = base64.b64decode(salt_b64)
            expected = base64.b64decode(digest_b64)
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                int(iterations),
            )
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def ensure_default_admin(self):
        if db.user_count() == 0:
            db.create_user(
                "admin",
                self.hash_password("admin"),
                must_change_password=True,
            )

    def login(self, username: str, password: str):
        user = db.get_user_by_username(username)

        if not user or not self.verify_password(password, user["password_hash"]):
            return None, None

        token = secrets.token_urlsafe(48)
        token_hash = self._token_hash(token)
        now = self._now()
        expires = now + timedelta(days=self.SESSION_DAYS)

        db.cleanup_expired_sessions(now.isoformat())
        db.create_session(
            user["id"],
            token_hash,
            now.isoformat(),
            expires.isoformat(),
        )

        return token, self.public_user(user)

    def authenticate(self, token: str | None):
        if not token:
            return None

        now = self._now()
        user = db.get_session_user(
            self._token_hash(token),
            now.isoformat(),
        )
        return self.public_user(user) if user else None

    def change_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
    ):
        user = db.get_user(user_id)

        if not user:
            return False, "用户不存在"

        if not self.verify_password(
            current_password,
            user["password_hash"],
        ):
            return False, "当前密码错误"

        if len(new_password) < 8:
            return False, "新密码至少需要 8 个字符"

        if new_password == current_password:
            return False, "新密码不能与当前密码相同"

        db.update_user_password(
            user_id,
            self.hash_password(new_password),
            must_change_password=False,
        )
        db.delete_user_sessions(user_id)

        return True, None

    def logout(self, token: str | None):
        if token:
            db.delete_session(self._token_hash(token))

    @staticmethod
    def public_user(user):
        if not user:
            return None

        return {
            "id": user["id"],
            "username": user["username"],
            "must_change_password": bool(user["must_change_password"]),
        }


auth_service = AuthService()
