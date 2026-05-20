"""
admin/auth.py
JWT authentication for the admin dashboard.
"""

import os
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

_bearer = HTTPBearer()

_ALGORITHM = "HS256"
_TOKEN_EXPIRE_HOURS = 24


def _secret() -> str:
    s = os.getenv("JWT_SECRET")
    if not s:
        raise RuntimeError("JWT_SECRET environment variable is not set")
    return s


def _admin_password() -> str:
    p = os.getenv("ADMIN_PASSWORD")
    if not p:
        raise RuntimeError("ADMIN_PASSWORD environment variable is not set")
    return p


def create_access_token() -> str:
    payload = {
        "sub": "admin",
        "exp": datetime.utcnow() + timedelta(hours=_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def verify_password(plain: str) -> bool:
    return plain == _admin_password()


def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
        if payload.get("sub") != "admin":
            raise ValueError("invalid subject")
        return "admin"
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
