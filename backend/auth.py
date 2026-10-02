import os
import secrets
import datetime
import jwt as pyjwt
from fastapi import HTTPException
from models import User

JWT_SECRET    = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"

ACCESS_TOKEN_MINUTES  = int(os.environ.get("ACCESS_TOKEN_MINUTES", "15"))
REFRESH_TOKEN_DAYS    = int(os.environ.get("REFRESH_TOKEN_DAYS", "30"))


def make_access_token(user: User) -> str:
    return pyjwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "type": "access",
            "iat": datetime.datetime.utcnow(),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_MINUTES),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def make_refresh_token_value() -> str:
    """Opaque random token stored in DB."""
    return secrets.token_urlsafe(64)


def refresh_token_expiry() -> datetime.datetime:
    return datetime.datetime.utcnow() + datetime.timedelta(days=REFRESH_TOKEN_DAYS)


def decode_access_token(token: str) -> dict:
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Access token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
