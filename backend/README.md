# Codgen Backend — Phase 3

FastAPI proxy with PostgreSQL auth, credit quotas, generation history, and S3/R2 file storage.

## Setup (local dev)

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # fill in required values
uvicorn main:app --reload --port 8000
```

PostgreSQL must be running locally. Quickest way:
```bash
docker run -d --name codgen-pg \
  -e POSTGRES_USER=codgen \
  -e POSTGRES_PASSWORD=codgen_secret \
  -e POSTGRES_DB=codgen \
  -p 5432:5432 postgres:16-alpine
```

Tables are created automatically on first startup via `init_db()`.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `MUAPI_API_KEY` | ✅ | Your Muapi server-side key |
| `JWT_SECRET` | ✅ | Long random string (min 32 chars) |
| `DATABASE_URL` | ✅ | `postgresql://user:pass@host:5432/db` |
| `ALLOWED_ORIGINS` | — | Comma-separated frontend URLs |
| `DEFAULT_CREDITS` | — | Credits given to new users (default 100) |
| `JWT_EXPIRE_DAYS` | — | Token lifetime in days (default 7) |
| `S3_BUCKET` | — | S3 or R2 bucket name |
| `S3_REGION` | — | `us-east-1` or `auto` for R2 |
| `S3_ACCESS_KEY` | — | S3/R2 access key |
| `S3_SECRET_KEY` | — | S3/R2 secret key |
| `S3_ENDPOINT` | — | Custom endpoint (R2: `https://<id>.r2.cloudflarestorage.com`) |
| `CDN_BASE_URL` | — | Public CDN URL prefix for uploaded files |

## API endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | None | Register → returns JWT + credits |
| POST | `/auth/login` | None | Login → returns JWT + credits |
| GET | `/auth/me` | JWT | Current user email + credits |
| GET | `/history` | JWT | Generation history (`?studio=image&limit=50&offset=0`) |
| POST | `/api/v1/{endpoint}` | JWT | Proxy to muapi, deducts 1 credit, saves generation |
| GET | `/api/v1/{path}` | JWT | Poll proxy to muapi |
