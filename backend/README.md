# Codgen Backend — Phase 2 Proxy

Thin FastAPI proxy: validates user JWT → forwards to api.muapi.ai with server-side Muapi key.

## Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # fill in MUAPI_API_KEY and JWT_SECRET
```

## Run

```bash
uvicorn main:app --reload --port 8000
```

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | None | Register (stub — add DB) |
| POST | `/auth/login` | None | Login → returns JWT |
| GET | `/auth/me` | JWT | Get current user |
| POST | `/api/v1/{endpoint}` | JWT | Proxy to muapi (JSON or multipart) |
| GET | `/api/v1/{path}` | JWT | Proxy poll to muapi |

## Production

- Replace the auth stubs in `main.py` with real DB (PostgreSQL + SQLAlchemy recommended)
- Set `ALLOWED_ORIGINS` to your production frontend domain
- Deploy with `uvicorn main:app --host 0.0.0.0 --port 8000` behind nginx/caddy
