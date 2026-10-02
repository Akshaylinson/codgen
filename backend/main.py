"""
Codgen Proxy Backend — Phase 5
- Email verification (send on register, block unverified on proxy)
- OAuth (Google / GitHub via Authlib)
- Usage analytics (per-model generation counts)
- Team/org accounts (shared credit pools, invite members)
- Webhook notifications (notify users when jobs complete)
"""

import os
import json
import hmac
import hashlib
import secrets
import datetime
import httpx
import bcrypt
import stripe
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from dotenv import load_dotenv
from authlib.integrations.httpx_client import AsyncOAuth2Client

from database import get_db, init_db
from models import (
    User, Generation, RefreshToken, PasswordResetToken,
    EmailVerification, OAuthAccount, Team, TeamMembership, TeamInvite,
    WebhookSubscription,
)
from storage import upload_to_storage, storage_enabled
from auth import (
    make_access_token,
    make_refresh_token_value,
    refresh_token_expiry,
    decode_access_token,
)
from mailer import send_password_reset, send_verification_email, send_team_invite

load_dotenv()

MUAPI_KEY       = os.environ["MUAPI_API_KEY"]
MUAPI_BASE      = "https://api.muapi.ai"
DEFAULT_CREDITS = int(os.environ.get("DEFAULT_CREDITS", "100"))
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
FRONTEND_URL    = os.environ.get("FRONTEND_URL", "http://localhost:3000")
BACKEND_URL     = os.environ.get("BACKEND_URL", "http://localhost:8000")
REQUIRE_EMAIL_VERIFICATION = os.environ.get("REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true"

stripe.api_key              = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET       = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID             = os.environ.get("STRIPE_PRICE_ID", "")   # price_xxx for 100 credits

# OAuth
GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GITHUB_CLIENT_ID     = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

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
    expose_headers=["*"],
)

# Ensure CORS headers are present even on error responses
@app.middleware("http")
async def cors_on_errors(request: Request, call_next):
    origin = request.headers.get("origin", "")
    response = await call_next(request)
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

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
        "is_verified":   user.is_verified,
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

    # Send verification email
    ev_token = secrets.token_urlsafe(32)
    db.add(EmailVerification(
        user_id    = user.id,
        token      = ev_token,
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=24),
    ))
    await db.commit()
    send_verification_email(email, ev_token)

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
    return {"email": user.email, "credits": user.credits, "id": user.id, "is_admin": user.is_admin, "is_verified": user.is_verified}


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
    endpoint:         str,
    request:          Request,
    background_tasks: BackgroundTasks,
    user:             User = Depends(get_current_user),
    db:               AsyncSession = Depends(get_db),
):
    content_type = request.headers.get("content-type", "")
    upstream_url = f"{MUAPI_BASE}/api/v1/{endpoint}"

    # File uploads bypass credit/verification checks — they don't generate content
    is_upload = "multipart/form-data" in content_type

    if not is_upload:
        if user.credits <= 0:
            raise HTTPException(status_code=429, detail="Credit quota exhausted. Top up to continue.")
        if REQUIRE_EMAIL_VERIFICATION and not user.is_verified:
            raise HTTPException(status_code=403, detail="Please verify your email before generating.")

    async with httpx.AsyncClient(timeout=300) as client:
        if is_upload:
            form = await request.form()
            files, data = {}, {}
            for key, value in form.items():
                if hasattr(value, "read"):
                    file_bytes = await value.read()
                    files[key] = (value.filename, file_bytes, value.content_type)
                else:
                    data[key] = value
            resp = await client.post(
                upstream_url, headers={"x-api-key": MUAPI_KEY}, files=files, data=data
            )
            if resp.status_code >= 400:
                try:
                    err = resp.json()
                    detail = err.get("error") or err.get("detail") or err.get("message") or str(err)
                except Exception:
                    detail = resp.text
                raise HTTPException(status_code=resp.status_code, detail=f"Muapi upload error: {detail}")
            return JSONResponse(content=resp.json(), status_code=resp.status_code)

        body_bytes = await request.body()
        try:
            body_json = json.loads(body_bytes)
        except Exception:
            pass
        resp = await client.post(
            upstream_url,
            headers={"Content-Type": "application/json", "x-api-key": MUAPI_KEY},
            content=body_bytes,
        )

    resp_data = resp.json()

    if resp.status_code < 300 and "predictions" not in endpoint:
        user.credits = max(0, user.credits - 1)
        gen = Generation(
            user_id    = user.id,
            studio     = _infer_studio(endpoint),
            model      = endpoint,
            prompt     = body_json.get("prompt"),
            output_url = (resp_data.get("outputs") or [None])[0] or resp_data.get("url"),
        )
        db.add(gen)
        await db.commit()
        background_tasks.add_task(_fire_webhooks, user.id, {
            "event":      "generation.completed",
            "studio":     gen.studio,
            "model":      gen.model,
            "output_url": gen.output_url,
        }, db)

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


# ── Phase 5: Email verification ──────────────────────────────────────────────

@app.get("/auth/verify-email")
async def verify_email(token: str = Query(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EmailVerification).where(EmailVerification.token == token))
    ev = result.scalar_one_or_none()
    if not ev or ev.used or ev.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    ev.used = True
    user_result = await db.execute(select(User).where(User.id == ev.user_id))
    user = user_result.scalar_one_or_none()
    if user:
        user.is_verified = True
    await db.commit()
    return RedirectResponse(url=f"{FRONTEND_URL}/?verified=1")


@app.post("/auth/resend-verification")
@limiter.limit("3/minute")
async def resend_verification(request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.is_verified:
        return {"ok": True, "message": "Already verified"}
    ev_token = secrets.token_urlsafe(32)
    db.add(EmailVerification(
        user_id    = user.id,
        token      = ev_token,
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=24),
    ))
    await db.commit()
    send_verification_email(user.email, ev_token)
    return {"ok": True, "message": "Verification email sent"}


# ── Phase 5: OAuth ────────────────────────────────────────────────────────────

async def _oauth_get_or_create_user(provider: str, provider_user_id: str, email: str, db: AsyncSession):
    """Find existing OAuth account or create new user + link."""
    result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == provider_user_id,
        )
    )
    oa = result.scalar_one_or_none()
    if oa:
        user_result = await db.execute(select(User).where(User.id == oa.user_id))
        return user_result.scalar_one()

    # Check if email already registered
    user_result = await db.execute(select(User).where(User.email == email))
    user = user_result.scalar_one_or_none()
    if not user:
        user = User(email=email, hashed_password=None, credits=DEFAULT_CREDITS, is_verified=True)
        db.add(user)
        await db.flush()
    db.add(OAuthAccount(user_id=user.id, provider=provider, provider_user_id=str(provider_user_id)))
    await db.commit()
    await db.refresh(user)
    return user


@app.get("/auth/oauth/google")
async def oauth_google_redirect():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    redirect_uri = f"{BACKEND_URL}/auth/oauth/google/callback"
    client = AsyncOAuth2Client(client_id=GOOGLE_CLIENT_ID, client_secret=GOOGLE_CLIENT_SECRET, redirect_uri=redirect_uri)
    uri, state = client.create_authorization_url("https://accounts.google.com/o/oauth2/v2/auth", scope="openid email profile")
    return RedirectResponse(url=uri)


@app.get("/auth/oauth/google/callback")
async def oauth_google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    redirect_uri = f"{BACKEND_URL}/auth/oauth/google/callback"
    client = AsyncOAuth2Client(client_id=GOOGLE_CLIENT_ID, client_secret=GOOGLE_CLIENT_SECRET, redirect_uri=redirect_uri)
    token = await client.fetch_token("https://oauth2.googleapis.com/token", authorization_response=str(request.url))
    userinfo = await client.get("https://www.googleapis.com/oauth2/v3/userinfo")
    info = userinfo.json()
    user = await _oauth_get_or_create_user("google", info["sub"], info["email"], db)
    rv = make_refresh_token_value()
    db.add(RefreshToken(user_id=user.id, token=rv, expires_at=refresh_token_expiry()))
    await db.commit()
    resp = _token_response(user, rv)
    return RedirectResponse(url=f"{FRONTEND_URL}/?access_token={resp['access_token']}&refresh_token={rv}")


@app.get("/auth/oauth/github")
async def oauth_github_redirect():
    if not GITHUB_CLIENT_ID:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")
    redirect_uri = f"{BACKEND_URL}/auth/oauth/github/callback"
    client = AsyncOAuth2Client(client_id=GITHUB_CLIENT_ID, client_secret=GITHUB_CLIENT_SECRET, redirect_uri=redirect_uri)
    uri, state = client.create_authorization_url("https://github.com/login/oauth/authorize", scope="user:email")
    return RedirectResponse(url=uri)


@app.get("/auth/oauth/github/callback")
async def oauth_github_callback(request: Request, db: AsyncSession = Depends(get_db)):
    if not GITHUB_CLIENT_ID:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")
    redirect_uri = f"{BACKEND_URL}/auth/oauth/github/callback"
    client = AsyncOAuth2Client(client_id=GITHUB_CLIENT_ID, client_secret=GITHUB_CLIENT_SECRET, redirect_uri=redirect_uri)
    await client.fetch_token("https://github.com/login/oauth/access_token", authorization_response=str(request.url))
    gh_user = (await client.get("https://api.github.com/user")).json()
    emails  = (await client.get("https://api.github.com/user/emails")).json()
    primary = next((e["email"] for e in emails if e.get("primary") and e.get("verified")), gh_user.get("email", ""))
    user = await _oauth_get_or_create_user("github", str(gh_user["id"]), primary, db)
    rv = make_refresh_token_value()
    db.add(RefreshToken(user_id=user.id, token=rv, expires_at=refresh_token_expiry()))
    await db.commit()
    resp = _token_response(user, rv)
    return RedirectResponse(url=f"{FRONTEND_URL}/?access_token={resp['access_token']}&refresh_token={rv}")


# ── Phase 5: Usage analytics ──────────────────────────────────────────────────

@app.get("/analytics/usage")
async def usage_analytics(
    days:   int = Query(30, le=365),
    studio: str | None = Query(None),
    user:   User = Depends(get_current_user),
    db:     AsyncSession = Depends(get_db),
):
    since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    q = select(Generation.model, Generation.studio, func.count(Generation.id).label("count")) \
        .where(Generation.user_id == user.id, Generation.created_at >= since)
    if studio:
        q = q.where(Generation.studio == studio)
    q = q.group_by(Generation.model, Generation.studio).order_by(desc("count"))
    rows = (await db.execute(q)).all()
    return {"days": days, "by_model": [{"model": r.model, "studio": r.studio, "count": r.count} for r in rows]}


@app.get("/analytics/daily")
async def daily_analytics(
    days: int = Query(30, le=365),
    user: User = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    q = select(
        func.date(Generation.created_at).label("date"),
        func.count(Generation.id).label("count"),
    ).where(Generation.user_id == user.id, Generation.created_at >= since) \
     .group_by(func.date(Generation.created_at)) \
     .order_by("date")
    rows = (await db.execute(q)).all()
    return {"days": days, "daily": [{"date": str(r.date), "count": r.count} for r in rows]}


@app.get("/admin/analytics")
async def admin_analytics(
    days:  int = Query(30, le=365),
    admin: User = Depends(get_admin_user),
    db:    AsyncSession = Depends(get_db),
):
    since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    total_gens = (await db.execute(
        select(func.count(Generation.id)).where(Generation.created_at >= since)
    )).scalar()
    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    by_model = (await db.execute(
        select(Generation.model, func.count(Generation.id).label("count"))
        .where(Generation.created_at >= since)
        .group_by(Generation.model)
        .order_by(desc("count"))
        .limit(20)
    )).all()
    return {
        "days": days,
        "total_generations": total_gens,
        "total_users": total_users,
        "top_models": [{"model": r.model, "count": r.count} for r in by_model],
    }


# ── Phase 5: Teams ────────────────────────────────────────────────────────────

@app.post("/teams")
async def create_team(request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Team name required")
    team = Team(name=name, owner_id=user.id)
    db.add(team)
    await db.flush()
    db.add(TeamMembership(team_id=team.id, user_id=user.id, role="owner"))
    await db.commit()
    await db.refresh(team)
    return {"id": team.id, "name": team.name, "credits": team.credits}


@app.get("/teams")
async def list_teams(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Team).join(TeamMembership, TeamMembership.team_id == Team.id)
        .where(TeamMembership.user_id == user.id)
    )
    teams = result.scalars().all()
    return [{"id": t.id, "name": t.name, "credits": t.credits, "owner_id": t.owner_id} for t in teams]


@app.get("/teams/{team_id}")
async def get_team(team_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _require_team_member(team_id, user.id, db)
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    members_result = await db.execute(
        select(TeamMembership, User).join(User, User.id == TeamMembership.user_id)
        .where(TeamMembership.team_id == team_id)
    )
    members = [{"user_id": m.user_id, "email": u.email, "role": m.role} for m, u in members_result.all()]
    return {"id": team.id, "name": team.name, "credits": team.credits, "members": members}


@app.post("/teams/{team_id}/invite")
async def invite_member(
    team_id: int, request: Request,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _require_team_role(team_id, user.id, ["owner", "admin"], db)
    body  = await request.json()
    email = body.get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    token = secrets.token_urlsafe(32)
    db.add(TeamInvite(
        team_id    = team_id,
        email      = email,
        token      = token,
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=7),
    ))
    await db.commit()
    send_team_invite(email, team.name, token)
    return {"ok": True}


@app.post("/teams/accept")
async def accept_invite(
    request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    body  = await request.json()
    token = body.get("token", "")
    result = await db.execute(select(TeamInvite).where(TeamInvite.token == token))
    invite = result.scalar_one_or_none()
    if not invite or invite.accepted or invite.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired invite")
    invite.accepted = True
    db.add(TeamMembership(team_id=invite.team_id, user_id=user.id, role="member"))
    await db.commit()
    return {"ok": True, "team_id": invite.team_id}


@app.patch("/teams/{team_id}/credits")
async def add_team_credits(
    team_id: int, request: Request,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Transfer credits from user pool to team pool."""
    await _require_team_role(team_id, user.id, ["owner", "admin"], db)
    body   = await request.json()
    amount = int(body.get("credits", 0))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="credits must be positive")
    if user.credits < amount:
        raise HTTPException(status_code=400, detail="Insufficient credits")
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    user.credits  -= amount
    team.credits  += amount
    await db.commit()
    return {"team_credits": team.credits, "user_credits": user.credits}


async def _require_team_member(team_id: int, user_id: int, db: AsyncSession):
    result = await db.execute(
        select(TeamMembership).where(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a team member")


async def _require_team_role(team_id: int, user_id: int, roles: list[str], db: AsyncSession):
    result = await db.execute(
        select(TeamMembership).where(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
    )
    m = result.scalar_one_or_none()
    if not m or m.role not in roles:
        raise HTTPException(status_code=403, detail="Insufficient team permissions")


# ── Phase 5: Webhooks ─────────────────────────────────────────────────────────

@app.get("/webhooks")
async def list_webhooks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebhookSubscription).where(WebhookSubscription.user_id == user.id))
    subs = result.scalars().all()
    return [{"id": s.id, "url": s.url, "active": s.active, "created_at": s.created_at.isoformat()} for s in subs]


@app.post("/webhooks")
async def create_webhook(
    request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    url  = body.get("url", "").strip()
    if not url or not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="A valid HTTPS URL is required")
    sub = WebhookSubscription(user_id=user.id, url=url, secret=secrets.token_hex(32))
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return {"id": sub.id, "url": sub.url, "secret": sub.secret}


@app.delete("/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WebhookSubscription).where(WebhookSubscription.id == webhook_id, WebhookSubscription.user_id == user.id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(sub)
    await db.commit()
    return {"ok": True}


async def _fire_webhooks(user_id: int, payload: dict, db: AsyncSession):
    """Send signed POST to all active webhooks for a user (background task)."""
    result = await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.user_id == user_id,
            WebhookSubscription.active == True,
        )
    )
    subs = result.scalars().all()
    body = json.dumps(payload).encode()
    async with httpx.AsyncClient(timeout=10) as client:
        for sub in subs:
            sig = hmac.new(sub.secret.encode(), body, hashlib.sha256).hexdigest()
            try:
                await client.post(sub.url, content=body, headers={
                    "Content-Type": "application/json",
                    "X-Codgen-Signature": f"sha256={sig}",
                })
            except Exception:
                pass  # best-effort delivery


# ── Utility ───────────────────────────────────────────────────────────────────

def _infer_studio(endpoint: str) -> str:
    e = endpoint.lower()
    if any(x in e for x in ["video", "i2v", "t2v", "wan", "kling", "sora", "veo", "runway", "seedance"]):
        return "video"
    if any(x in e for x in ["lipsync", "infinitetalk", "latentsync", "creatify", "veed", "speech"]):
        return "lipsync"
    return "image"
