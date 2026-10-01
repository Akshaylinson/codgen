"""
Codgen Proxy Backend — Phase 2
Browser → Codgen backend (JWT auth) → api.muapi.ai (server-side Muapi key)
"""

import os
import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt as pyjwt
from dotenv import load_dotenv

load_dotenv()

MUAPI_KEY = os.environ["MUAPI_API_KEY"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
MUAPI_BASE = "https://api.muapi.ai"

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app = FastAPI(title="Codgen Proxy")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


def verify_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = pyjwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── Auth endpoints ────────────────────────────────────────────────────────────

@app.post("/auth/login")
async def login(request: Request):
    """
    Minimal login — validates credentials against your user store.
    Replace the stub below with real DB lookup + password check.
    """
    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")

    # TODO: replace with real user lookup
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    # Stub: accept any non-empty credentials for now
    # In production: verify against DB, hash-check password
    import datetime
    token = pyjwt.encode(
        {
            "sub": email,
            "email": email,
            "iat": datetime.datetime.utcnow(),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return {"token": token, "email": email}


@app.post("/auth/register")
async def register(request: Request):
    """
    Minimal register stub — replace with real DB insert.
    """
    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    # TODO: hash password, insert into DB, check for duplicates
    import datetime
    token = pyjwt.encode(
        {
            "sub": email,
            "email": email,
            "iat": datetime.datetime.utcnow(),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return {"token": token, "email": email}


@app.get("/auth/me")
async def me(user: dict = Depends(verify_jwt)):
    return {"email": user.get("email"), "sub": user.get("sub")}


# ── Proxy: POST /api/v1/{endpoint} ───────────────────────────────────────────

@app.post("/api/v1/{endpoint:path}")
async def proxy_post(endpoint: str, request: Request, user: dict = Depends(verify_jwt)):
    content_type = request.headers.get("content-type", "")
    upstream_url = f"{MUAPI_BASE}/api/v1/{endpoint}"

    async with httpx.AsyncClient(timeout=300) as client:
        if "multipart/form-data" in content_type:
            # File upload — forward as multipart
            form = await request.form()
            files = {}
            data = {}
            for key, value in form.items():
                if hasattr(value, "read"):
                    files[key] = (value.filename, await value.read(), value.content_type)
                else:
                    data[key] = value

            resp = await client.post(
                upstream_url,
                headers={"x-api-key": MUAPI_KEY},
                files=files,
                data=data,
            )
        else:
            body = await request.body()
            resp = await client.post(
                upstream_url,
                headers={"Content-Type": "application/json", "x-api-key": MUAPI_KEY},
                content=body,
            )

    return JSONResponse(content=resp.json(), status_code=resp.status_code)


# ── Proxy: GET /api/v1/{path} (polling) ──────────────────────────────────────

@app.get("/api/v1/{path:path}")
async def proxy_get(path: str, request: Request, user: dict = Depends(verify_jwt)):
    upstream_url = f"{MUAPI_BASE}/api/v1/{path}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            upstream_url,
            headers={"x-api-key": MUAPI_KEY},
            params=dict(request.query_params),
        )
    return JSONResponse(content=resp.json(), status_code=resp.status_code)
