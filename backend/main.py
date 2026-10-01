"""
Codgen Proxy Backend — Phase 3
- Real PostgreSQL auth (bcrypt passwords, duplicate email check)
- Per-user credit quotas (429 when exhausted)
- Generation history stored in DB
- File uploads proxied to S3/R2 (falls back to muapi upload if storage not configured)
- JWT auth on all /api/* and /history/* routes
"""

import os
import datetime
import httpx
import bcrypt
import jwt as pyjwt
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from dotenv import load_dotenv

from database import get_db, init_db
from models import User, Generation
from storage import upload_to_storage, storage_enabled

load_dotenv()

MUAPI_KEY     = os.environ["MUAPI_API_KEY"]
JWT_SECRET    = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = int(os.environ.get("JWT_EXPIRE_DAYS", "7"))
MUAPI_BASE    = "https://api.muapi.ai"
DEFAULT_CREDITS = int(os.environ.get("DEFAULT_CREDITS", "100"))
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Codgen API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_token(user: User) -> str:
    return pyjwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "iat": datetime.datetime.utcnow(),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=JWT_EXPIRE_DAYS),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def verify_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        return pyjwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    payload: dict = Depends(verify_jwt),
    db: AsyncSession = Depends(get_db),
) -> User:
    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/auth/register")
async def register(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    email    = body.get("email", "").strip().lower()
    password = body.get("password", "")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = User(email=email, hashed_password=hashed, credits=DEFAULT_CREDITS)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"token": make_token(user), "email": user.email, "credits": user.credits}


@app.post("/auth/login")
async def login(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    email    = body.get("email", "").strip().lower()
    password = body.get("password", "")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not bcrypt.checkpw(password.encode(), user.hashed_password.encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {"token": make_token(user), "email": user.email, "credits": user.credits}


@app.get("/auth/me")
async def me(user: User = Depends(get_current_user)):
    return {"email": user.email, "credits": user.credits, "id": user.id}


# ── Generation history ────────────────────────────────────────────────────────

@app.get("/history")
async def get_history(
    studio: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Generation).where(Generation.user_id == user.id)
    if studio:
        q = q.where(Generation.studio == studio)
    q = q.order_by(desc(Generation.created_at)).limit(limit).offset(offset)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "studio": r.studio,
            "model": r.model,
            "prompt": r.prompt,
            "output_url": r.output_url,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


# ── Proxy: POST /api/v1/{endpoint} ───────────────────────────────────────────

@app.post("/api/v1/{endpoint:path}")
async def proxy_post(
    endpoint: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Quota check
    if user.credits <= 0:
        raise HTTPException(status_code=429, detail="Credit quota exhausted. Please upgrade your plan.")

    content_type = request.headers.get("content-type", "")
    upstream_url = f"{MUAPI_BASE}/api/v1/{endpoint}"

    async with httpx.AsyncClient(timeout=300) as client:
        if "multipart/form-data" in content_type:
            form = await request.form()
            files, data = {}, {}
            for key, value in form.items():
                if hasattr(value, "read"):
                    file_bytes = await value.read()

                    # Try S3/R2 first; fall back to forwarding to muapi
                    if storage_enabled():
                        cdn_url = await upload_to_storage(
                            file_bytes, value.filename, value.content_type or "application/octet-stream"
                        )
                        if cdn_url:
                            # Return CDN URL directly — no need to forward to muapi upload
                            return JSONResponse({"url": cdn_url})

                    files[key] = (value.filename, file_bytes, value.content_type)
                else:
                    data[key] = value

            resp = await client.post(
                upstream_url,
                headers={"x-api-key": MUAPI_KEY},
                files=files,
                data=data,
            )
        else:
            body_bytes = await request.body()
            resp = await client.post(
                upstream_url,
                headers={"Content-Type": "application/json", "x-api-key": MUAPI_KEY},
                content=body_bytes,
            )

    resp_data = resp.json()

    # Deduct 1 credit and record generation (only on successful submit, not polls)
    if resp.status_code < 300 and endpoint != f"predictions/{endpoint.split('/')[-1]}/result":
        import json
        try:
            body_json = json.loads(body_bytes) if "body_bytes" in dir() else {}
        except Exception:
            body_json = {}

        user.credits = max(0, user.credits - 1)
        gen = Generation(
            user_id=user.id,
            studio=_infer_studio(endpoint),
            model=endpoint,
            prompt=body_json.get("prompt"),
            output_url=resp_data.get("outputs", [None])[0] or resp_data.get("url"),
        )
        db.add(gen)
        await db.commit()

    return JSONResponse(content=resp_data, status_code=resp.status_code)


# ── Proxy: GET /api/v1/{path} (polling) ──────────────────────────────────────

@app.get("/api/v1/{path:path}")
async def proxy_get(
    path: str,
    request: Request,
    user: User = Depends(get_current_user),
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
    if any(x in e for x in ["video", "i2v", "t2v", "cinema", "wan", "kling", "sora", "veo", "runway", "seedance"]):
        return "video"
    if any(x in e for x in ["lipsync", "lipsync", "infinitetalk", "latentsync", "creatify", "veed", "speech"]):
        return "lipsync"
    return "image"
