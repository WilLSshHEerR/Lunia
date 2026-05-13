import os
import time
import secrets
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
import bcrypt
import pyotp
from fastapi import HTTPException, status
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60

_failed_attempts: dict = {}


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def check_rate_limit(ip: str):
    now = time.time()
    record = _failed_attempts.get(ip)
    if record:
        if now - record["since"] < LOCKOUT_SECONDS:
            if record["count"] >= MAX_ATTEMPTS:
                remaining = int((LOCKOUT_SECONDS - (now - record["since"])) / 60) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Cuenta bloqueada. Intenta en {remaining} minuto(s).",
                )
        else:
            del _failed_attempts[ip]


def record_failure(ip: str):
    now = time.time()
    if ip not in _failed_attempts or now - _failed_attempts[ip]["since"] >= LOCKOUT_SECONDS:
        _failed_attempts[ip] = {"count": 1, "since": now}
    else:
        _failed_attempts[ip]["count"] += 1


def clear_failures(ip: str):
    _failed_attempts.pop(ip, None)


def create_token(data: dict, expires_delta: timedelta) -> str:
    payload = {
        **data,
        "exp": datetime.now(timezone.utc) + expires_delta,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token() -> str:
    return create_token(
        {"sub": "lunia", "type": "access"},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token() -> str:
    return create_token(
        {"sub": "lunia", "type": "refresh"},
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: str) -> bool:
    if not SECRET_KEY:
        return False
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("type") == expected_type and payload.get("sub") == "lunia"
    except JWTError:
        return False


def verify_totp(code: str) -> bool:
    secret = os.getenv("TOTP_SECRET", "")
    if not secret:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code.strip(), valid_window=1)
