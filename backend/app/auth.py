import base64
import binascii
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from app.core import RoleBindingRecord, UserRecord


AUTH_COOKIE_NAME = "emata_session"
DEMO_SIGNED_OUT_COOKIE_NAME = "emata_demo_signed_out"


@dataclass
class AuthSettings:
    enabled: bool
    session_secret: str
    session_ttl_seconds: int
    cookie_secure: bool


def load_auth_settings() -> AuthSettings:
    return AuthSettings(
        enabled=_env_bool("EMATA_AUTH_ENABLED", False),
        session_secret=os.getenv("EMATA_SESSION_SECRET", "").strip(),
        session_ttl_seconds=_env_int("EMATA_SESSION_TTL_SECONDS", 86400),
        cookie_secure=_env_bool("EMATA_AUTH_COOKIE_SECURE", False),
    )


def load_bootstrap_users() -> Tuple[Dict[str, UserRecord], Dict[str, str]]:
    raw = os.getenv("EMATA_BOOTSTRAP_USERS_JSON", "").strip()
    if not raw:
        raise RuntimeError("auth_not_configured: EMATA_BOOTSTRAP_USERS_JSON is required")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("auth_not_configured: EMATA_BOOTSTRAP_USERS_JSON is invalid JSON") from exc
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("auth_not_configured: at least one bootstrap user is required")

    users: Dict[str, UserRecord] = {}
    password_hashes: Dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            raise RuntimeError("auth_not_configured: bootstrap user entries must be objects")
        user_id = str(item.get("id") or "").strip()
        username = str(item.get("username") or "").strip()
        organization_id = str(item.get("organization_id") or "").strip()
        display_name = str(item.get("display_name") or username).strip()
        password_hash = str(item.get("password_hash") or "").strip()
        if not user_id or not username or not organization_id or not password_hash:
            raise RuntimeError("auth_not_configured: bootstrap users require id, username, organization_id, password_hash")

        bindings: List[RoleBindingRecord] = []
        for binding in item.get("role_bindings") or []:
            workspace_id = str(binding.get("workspace_id") or "").strip()
            role = str(binding.get("role") or "").strip()
            binding_org = str(binding.get("organization_id") or organization_id).strip()
            if not workspace_id or not role:
                raise RuntimeError("auth_not_configured: role bindings require workspace_id and role")
            bindings.append(
                RoleBindingRecord(
                    user_id=user_id,
                    organization_id=binding_org,
                    workspace_id=workspace_id,
                    role=role,
                )
            )

        users[user_id] = UserRecord(
            id=user_id,
            organization_id=organization_id,
            username=username,
            display_name=display_name,
            role_bindings=bindings,
        )
        password_hashes[user_id] = password_hash
    return users, password_hashes


def validate_launch_config(settings: AuthSettings) -> None:
    if not settings.enabled:
        return
    if len(settings.session_secret) < 16:
        raise RuntimeError("auth_not_configured: EMATA_SESSION_SECRET must be at least 16 characters")
    if settings.session_ttl_seconds <= 0:
        raise RuntimeError("auth_not_configured: EMATA_SESSION_TTL_SECONDS must be positive")
    if not os.getenv("EMATA_INTERNAL_API_KEY", "").strip():
        raise RuntimeError("auth_not_configured: EMATA_INTERNAL_API_KEY must be configured for team trial launch")

    for key in ("EMATA_MODEL_API_KEY", "EMATA_RERANK_API_KEY", "EMATA_EMBEDDING_API_KEY"):
        value = os.getenv(key, "").strip()
        if not value or value == "replace-me":
            raise RuntimeError(f"auth_not_configured: {key} must be configured for team trial launch")


def find_user_by_username(users: Dict[str, UserRecord], username: str) -> Optional[UserRecord]:
    normalized = username.strip().lower()
    for user in users.values():
        if user.username.lower() == normalized:
            return user
    return None


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt, expected_raw = encoded_hash.split("$", 3)
        iterations = int(iterations_raw)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256" or iterations <= 0 or not salt or not expected_raw:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    try:
        expected = _b64decode(expected_raw)
    except (binascii.Error, ValueError):
        return False
    return hmac.compare_digest(digest, expected)


def create_session_token(user_id: str, settings: AuthSettings) -> Tuple[str, str]:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=settings.session_ttl_seconds)
    payload = {
        "sub": user_id,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_part = _b64encode(payload_bytes)
    signature = _sign(payload_part, settings.session_secret)
    return f"{payload_part}.{signature}", _format_timestamp(expires_at)


def read_session_user_id(token: str, settings: AuthSettings) -> Optional[str]:
    if not token or "." not in token:
        return None
    payload_part, signature = token.rsplit(".", 1)
    expected_signature = _sign(payload_part, settings.session_secret)
    if not hmac.compare_digest(signature, expected_signature):
        return None
    try:
        payload = json.loads(_b64decode(payload_part).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None
    user_id = str(payload.get("sub") or "").strip()
    expires_at = int(payload.get("exp") or 0)
    if not user_id or expires_at <= int(datetime.now(timezone.utc).timestamp()):
        return None
    return user_id


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"auth_not_configured: {key} must be an integer") from exc


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _sign(payload_part: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_part.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def _format_timestamp(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")
