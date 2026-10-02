"""
Codgen Proxy Backend — Phase 4
- Refresh tokens (15-min access + 30-day refresh, rotation on every use)
- Password reset via email (/auth/forgot-password → /auth/reset-password)
- Admin panel (/admin/users, /admin/users/{id}/credits)
- Stripe credit top-up (/billing/checkout, /billing/webhook)
- Rate limiting via slowapi
"""

import os
import json
import datetime
import httpx
import bcrypt
import stripe
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from dotenv import load_dotenv

from database import get_db, init_db
from models import User, Generation, RefreshToken, PasswordResetToken
from storage import upload_to_storage, storage_enabled
from auth import (
    make_access_token,
    make_refresh_token_value,
    refresh_token_expiry,
    decode_access_token,
)
from email import send_password_reset

load_dotenv()

MUAPI_KEY       = os.environ["MUAPI_API_KEY"]
MUAPI_BASE      = "https://api.muapi.ai"
DEFAULT_CREDITS = int(os.environ.get("DEFAULT_CREDITS", "100"))
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
FRONTEND_URL    = os.environ.get("FRONTEND_URL", "http://localhost:3000")

stripe.api_key              = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET       = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID             = os.environ.get("STRIPE_PRICE_ID", "")   # price_xxx for 100 credits

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Codgen API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _verify_bearer(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    return decode_access_token(credentials.credentials)


async def get_current_user(
    payload: dict = Depends(_verify_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    result = await db.execute(select(User).where(User.id == int(payload["sub"])))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _token_response(user: User, refresh_value: str) -> dict:
    return {
        "access_token":  make_access_token(user),
        "refresh_token": refresh_value,
        "token_type":    "bearer",
        "email":         user.email,
        "credits":       user.credits,
    }


# ── Auth: register ────────────────────────────────────────────────────────────

@app.post("/auth/register")
@limiter.limit("10/minute")
async def register(request: Request, db: AsyncSession = Depends(get_db)):
    body     = await request.json()
    email    = body.get("email", "").strip().lower()
    password = body.get("password", "")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user   = User(email=email, hashed_password=hashed, credits=DEFAULT_CREDITS)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    rv = make_refresh_token_value()
    db.add(RefreshToken(user_id=user.id, token=rv, expires_at=refresh_token_expiry()))
    await db.commit()

    return _token_response(user, rv)


# ── Auth: login ───────────────────────────────────────────────────────────────

@app.post("/auth/login")
@limiter.limit("20/minute")
async def login(request: Request, db: AsyncSession = Depends(get_db)):
    body     = await request.json()
    email    = body.get("email", "").strip().lower()
    password = body.get("password", "")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    result = await db.execute(select(User).where(User.email == email))
    user   = result.scalar_one_or_none()

    if not user or not bcrypt.checkpw(password.encode(), user.hashed_password.encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    rv = make_refresh_token_value()
    db.add(RefreshToken(user_id=user.id, token=rv, expires_at=refresh_token_expiry()))
    await db.commit()

    return _token_response(user, rv)


# ── Auth: refresh ─────────────────────────────────────────────────────────────

@app.post("/auth/refresh")
@limiter.limit("30/minute")
async def refresh(request: Request, db: AsyncSession = Depends(get_db)):
    body  = await request.json()
    token = body.get("refresh_token", "")
    if not token:
        raise HTTPException(status_code=400, detail="refresh_token required")

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == token)
    )
    rt = result.scalar_one_or_none()

    if not rt or rt.revoked or rt.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Rotate — revoke old, issue new
    rt.revoked = True
    user_result = await db.execute(select(User).where(User.id == rt.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    new_rv = make_refresh_token_value()
    db.add(RefreshToken(user_id=user.id, token=new_rv, expires_at=refresh_token_expiry()))
    await db.commit()

    return _token_response(user, new_rv)


# ── Auth: logout ──────────────────────────────────────────────────────────────

@app.post("/auth/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    body  = await request.json()
    token = body.get("refresh_token", "")
    if token:
        result = await db.execute(select(RefreshToken).where(RefreshToken.token == token))
        rt = result.scalar_one_or_none()
        if rt:
            rt.revoked = True
            await db.commit()
    return {"ok": True}


# ── Auth: me ──────────────────────────────────────────────────────────────────

@app.get("/auth/me")
async def me(user: User = Depends(get_current_user)):
    return {"email": user.email, "credits": user.credits, "id": user.id, "is_admin": user.is_admin}


# ── Password reset: request ───────────────────────────────────────────────────

@app.post("/auth/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, db: AsyncSession = Depends(get_db)):
    body  = await request.json()
    email = body.get("email", "").strip().lower()

    result = await db.execute(select(User).where(User.email == email))
    user   = result.scalar_one_or_none()

    # Always return 200 — don't leak whether email exists
    if user:
        from auth import make_refresh_token_value as _rand
        token_value = _rand()
        db.add(PasswordResetToken(
            user_id    = user.id,
            token      = token_value,
            expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=1),
        ))
        await db.commit()
        send_password_reset(email, token_value)

    return {"ok": True, "message": "If that email exists, a reset link has been sent."}


# ── Password reset: confirm ───────────────────────────────────────────────────

@app.post("/auth/reset-password")
@limiter.limit("10/minute")
async def reset_password(request: Request, db: AsyncSession = Depends(get_db)):
    body         = await request.json()
    token_value  = body.get("token", "")
    new_password = body.get("password", "")

    if not token_value or not new_password:
        raise HTTPException(status_code=400, detail="token and password required")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == token_value)
    )
    prt = result.scalar_one_or_none()

    if not prt or prt.used or prt.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user_result = await db.execute(select(User).where(User.id == prt.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    user.hashed_password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    prt.used = True

    # Revoke all existing refresh tokens for security
    await db.execute(
        RefreshToken.__table__.update()
        .where(RefreshToken.user_id == user.id)
        .values(revoked=True)
    )
    await db.commit()

    return {"ok": True, "message": "Password updated. Please log in again."}


# ── Admin: list users ─────────────────────────────────────────────────────────

@app.get("/admin/users")
async def admin_list_users(
    limit:  int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    admin:  User = Depends(get_admin_user),
    db:     AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).order_by(desc(User.created_at)).limit(limit).offset(offset)
    )
    users = result.scalars().all()

    total = (await db.execute(select(func.count()).select_from(User))).scalar()

    return {
        "total": total,
        "users": [
            {
                "id":         u.id,
                "email":      u.email,
                "credits":    u.credits,
                "is_admin":   u.is_admin,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
    }


# ── Admin: adjust credits ─────────────────────────────────────────────────────

@app.patch("/admin/users/{user_id}/credits")
async def admin_adjust_credits(
    user_id: int,
    request: Request,
    admin:   User = Depends(get_admin_user),
    db:      AsyncSession = Depends(get_db),
):
    body   = await request.json()
    amount = body.get("credits")
    if amount is None:
        raise HTTPException(status_code=400, detail="credits field required")

    result = await db.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.credits = max(0, int(amount))
    await db.commit()
    return {"id": user.id, "email": user.email, "credits": user.credits}


# ── Admin: promote to admin ───────────────────────────────────────────────────

@app.patch("/admin/users/{user_id}/promote")
async def admin_promote(
    user_id: int,
    admin:   User = Depends(get_admin_user),
    db:      AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_admin = True
    await db.commit()
    return {"id": user.id, "email": user.email, "is_admin": user.is_admin}


# ── Billing: Stripe checkout ──────────────────────────────────────────────────

@app.post("/billing/checkout")
async def create_checkout(
    request: Request,
    user:    User = Depends(get_current_user),
):
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Billing not configured")

    body     = await request.json()
    quantity = max(1, int(body.get("quantity", 1)))   # packs of 100 credits

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": quantity}],
        mode="payment",
        success_url=f"{FRONTEND_URL}/?payment=success",
        cancel_url=f"{FRONTEND_URL}/?payment=cancelled",
        metadata={"user_id": str(user.id), "credits_per_pack": "100", "quantity": str(quantity)},
    )
    return {"checkout_url": session.url}


# ── Billing: Stripe webhook ───────────────────────────────────────────────────

@app.post("/billing/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload   = await request.body()
    sig       = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    if event["type"] == "checkout.session.completed":
        session  = event["data"]["object"]
        meta     = session.get("metadata", {})
        user_id  = int(meta.get("user_id", 0))
        qty      = int(meta.get("quantity", 1))
        per_pack = int(meta.get("credits_per_pack", 100))

        if user_id:
            result = await db.execute(select(User).where(User.id == user_id))
            user   = result.scalar_one_or_none()
            if user:
                user.credits += qty * per_pack
                await db.commit()

    return {"ok": True}


# ── Generation history ────────────────────────────────────────────────────────

@app.get("/history")
async def get_history(
    studio: str | None = Query(None),
    limit:  int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    user:   User = Depends(get_current_user),
    db:     AsyncSession = Depends(get_db),
):
    q = select(Generation).where(Generation.user_id == user.id)
    if studio:
        q = q.where(Generation.studio == studio)
    q = q.order_by(desc(Generation.created_at)).limit(limit).offset(offset)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id":         r.id,
            "studio":     r.studio,
            "model":      r.model,
            "prompt":     r.prompt,
            "output_url": r.output_url,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


# ── Proxy: POST /api/v1/{endpoint} ───────────────────────────────────────────

@app.post("/api/v1/{endpoint:path}")
@limiter.limit("60/minute")
async def proxy_post(
    endpoint: str,
    request:  Request,
    user:     User = Depends(get_current_user),
    db:       AsyncSession = Depends(get_db),
):
    if user.credits <= 0:
        raise HTTPException(status_code=429, detail="Credit quota exhausted. Top up to continue.")

    content_type = request.headers.get("content-type", "")
    upstream_url = f"{MUAPI_BASE}/api/v1/{endpoint}"
    body_json    = {}

    async with httpx.AsyncClient(timeout=300) as client:
        if "multipart/form-data" in content_type:
            form = await request.form()
            files, data = {}, {}
            for key, value in form.items():
                if hasattr(value, "read"):
                    file_bytes = await value.read()
                    if storage_enabled():
                        cdn_url = await upload_to_storage(
                            file_bytes,
                            value.filename,
                            value.content_type or "application/octet-stream",
                        )
                        if cdn_url:
                            return JSONResponse({"url": cdn_url})
                    files[key] = (value.filename, file_bytes, value.content_type)
                else:
                    data[key] = value
            resp = await client.post(
                upstream_url, headers={"x-api-key": MUAPI_KEY}, files=files, data=data
            )
        else:
            body_bytes = await request.body()
            try:
                body_json = json.loads(body_bytes)
            except Exception:
                body_json = {}
            resp = await client.post(
                upstream_url,
                headers={"Content-Type": "application/json", "x-api-key": MUAPI_KEY},
                content=body_bytes,
            )

    resp_data = resp.json()

    if resp.status_code < 300 and "predictions" not in endpoint:
        user.credits = max(0, user.credits - 1)
        db.add(Generation(
            user_id    = user.id,
            studio     = _infer_studio(endpoint),
            model      = endpoint,
            prompt     = body_json.get("prompt"),
            output_url = (resp_data.get("outputs") or [None])[0] or resp_data.get("url"),
        ))
        await db.commit()

    return JSONResponse(content=resp_data, status_code=resp.status_code)


# ── Proxy: GET /api/v1/{path} (polling) ──────────────────────────────────────

@app.get("/api/v1/{path:path}")
async def proxy_get(
    path:    str,
    request: Request,
    user:    User = Depends(get_current_user),
):
    upstream_url = f"{MUAPI_BASE}/api/v1/{path}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            upstream_url,
            headers={"x-api-key": MUAPI_KEY},
            params=dict(request.query_params),
        )
    return JSONResponse(content=resp.json(), status_code=resp.status_code)


# ── Utility ───────────────────────────────────────────────────────────────────

def _infer_studio(endpoint: str) -> str:
    e = endpoint.lower()
    if any(x in e for x in ["video", "i2v", "t2v", "wan", "kling", "sora", "veo", "runway", "seedance"]):
        return "video"
    if any(x in e for x in ["lipsync", "infinitetalk", "latentsync", "creatify", "veed", "speech"]):
        return "lipsync"
    return "image"
