# Codgen — Deployment Guide

## Option 1 — Docker Compose (single server / VPS)

Runs frontend + backend + PostgreSQL in one command. Works on any Linux VPS (DigitalOcean, Hetzner, EC2, etc.).

```bash
# 1. Clone and enter the repo
git clone https://github.com/your-org/codgen.git
cd codgen

# 2. Create root .env
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD, NEXT_PUBLIC_BACKEND_URL, ALLOWED_ORIGINS

# 3. Create backend .env
cp backend/.env.example backend/.env
# Edit backend/.env — set MUAPI_API_KEY, JWT_SECRET, DATABASE_URL
# DATABASE_URL must match: postgresql://codgen:<POSTGRES_PASSWORD>@db:5432/codgen

# 4. Build and start
docker compose up -d --build

# 5. Check logs
docker compose logs -f
```

Frontend → http://your-server:3000
Backend  → http://your-server:8000

### Add nginx reverse proxy (recommended)

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location /api/    { proxy_pass http://localhost:8000; proxy_set_header Host $host; }
    location /auth/   { proxy_pass http://localhost:8000; proxy_set_header Host $host; }
    location /history { proxy_pass http://localhost:8000; proxy_set_header Host $host; }
    location /        { proxy_pass http://localhost:3000; proxy_set_header Host $host; }
}
```

Then set `NEXT_PUBLIC_BACKEND_URL=https://yourdomain.com` and `ALLOWED_ORIGINS=https://yourdomain.com`.

---

## Option 2 — AWS ECS + RDS (production-grade)

Docker is fully supported by AWS. The recommended path:

| Component | AWS Service |
|---|---|
| Frontend container | ECS Fargate (or App Runner) |
| Backend container | ECS Fargate |
| PostgreSQL | RDS PostgreSQL (managed) |
| File storage | S3 |
| CDN | CloudFront in front of S3 |
| Secrets | AWS Secrets Manager or Parameter Store |
| Load balancer | ALB (Application Load Balancer) |

### Steps

**1. Push images to ECR**
```bash
aws ecr create-repository --repository-name codgen-frontend
aws ecr create-repository --repository-name codgen-backend

# Authenticate
aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com

# Build and push
docker build -t codgen-frontend .
docker tag codgen-frontend <account>.dkr.ecr.<region>.amazonaws.com/codgen-frontend:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/codgen-frontend:latest

docker build -t codgen-backend ./backend
docker tag codgen-backend <account>.dkr.ecr.<region>.amazonaws.com/codgen-backend:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/codgen-backend:latest
```

**2. Create RDS PostgreSQL**
- Engine: PostgreSQL 16
- Instance: db.t4g.micro (free tier eligible)
- Set DB name: `codgen`, username: `codgen`
- Note the endpoint — use as `DATABASE_URL` in backend env

**3. Create ECS Cluster + Task Definitions**
- Create a Fargate cluster
- Create two task definitions: `codgen-frontend` and `codgen-backend`
- Inject env vars via Secrets Manager or ECS environment variables
- Backend task: expose port 8000; Frontend task: expose port 3000

**4. Create ALB**
- Listener on port 443 (HTTPS via ACM certificate)
- Target group for frontend (port 3000)
- Path-based routing: `/api/*`, `/auth/*`, `/history/*` → backend target group

**5. Set environment variables**
```
# Backend task
MUAPI_API_KEY        → from Secrets Manager
JWT_SECRET           → from Secrets Manager
DATABASE_URL         → postgresql://codgen:<pass>@<rds-endpoint>:5432/codgen
ALLOWED_ORIGINS      → https://yourdomain.com
S3_BUCKET            → your-codgen-bucket
S3_REGION            → us-east-1
S3_ACCESS_KEY        → IAM user key with S3 PutObject permission
S3_SECRET_KEY        → IAM user secret
CDN_BASE_URL         → https://your-cloudfront-distribution.cloudfront.net

# Frontend task
NEXT_PUBLIC_BACKEND_URL → https://yourdomain.com
```

---

## Option 3 — Railway (easiest managed deploy)

Railway supports Docker and PostgreSQL natively.

1. Push repo to GitHub
2. New project → Deploy from GitHub repo
3. Add a PostgreSQL plugin — Railway injects `DATABASE_URL` automatically
4. Set all other env vars in the Railway dashboard
5. Railway builds from `Dockerfile` (backend) and root `Dockerfile` (frontend) automatically

---

## Updating in production

```bash
# Docker Compose on VPS
git pull
docker compose up -d --build

# ECS
docker build + push new image → ECS rolling deploy (zero downtime)
```
