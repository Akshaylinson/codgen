# CodeGen — AI Generation Platform

## Master Build & Architecture Prompt

## 1. Project Objective

Clone and extend the existing open-source Open-Higgsfield-style AI generation frontend.

The existing project provides a mature user interface for:

* Image generation
* Video generation
* Lip-sync generation
* Cinema/creative workflows
* Model selection
* Generation history
* File upload
* Downloading generated media
* Responsive studio interfaces

The goal is to transform this project into an independently branded AI generation platform powered by a new backend layer called **CodeGen**.

The existing frontend should be retained as much as possible.

Do NOT perform an unnecessary frontend rewrite.

Do NOT build or host AI inference models locally.

Do NOT introduce GPU infrastructure.

Do NOT make the application dependent on Muapi.

Instead, introduce a secure **CodeGen backend/API layer** between the frontend and the Higgsfield API.

The final architecture should be:

```text
User
  │
  ▼
CodeGen Frontend
(existing Open-Higgsfield-style UI)
  │
  ▼
CodeGen Backend/API
  │
  ├── Authentication
  ├── User management
  ├── Higgsfield credential management
  ├── Usage quotas
  ├── Generation jobs
  ├── Project/history management
  ├── File management
  └── Higgsfield API adapter
          │
          ▼
     Higgsfield API
          │
          ▼
   Higgsfield AI infrastructure
          │
          ▼
    Generated media
          │
          ▼
         S3
```

The Higgsfield API performs the actual AI inference.

CodeGen must not attempt to download, host, or execute Higgsfield's AI models.

---

# 2. Core Product Concept

CodeGen is a **BYOK — Bring Your Own Key — AI generation workspace**.

Each user supplies their own valid Higgsfield API credentials.

The user's Higgsfield account remains responsible for:

* Higgsfield API balance
* Higgsfield Units/credits
* Higgsfield model costs
* Higgsfield API billing
* Higgsfield-side generation limits

CodeGen must NOT become the user's AI-generation billing provider.

CodeGen only provides the software interface and its own application-level usage limits.

Therefore there are two completely independent accounting systems.

### Higgsfield side

```text
Higgsfield API Balance
        │
        ├── Model costs
        ├── Image generation
        ├── Video generation
        └── Other Higgsfield API operations
```

### CodeGen side

```text
CodeGen Usage Quota
        │
        ├── Monthly generations
        ├── Monthly requests
        └── Subscription-based application limits
```

Do not merge these two systems.

Do not attempt to convert Higgsfield Units into CodeGen credits.

Do not calculate Higgsfield generation pricing as CodeGen credits.

Do not charge users for individual Higgsfield generations.

---

# 3. CodeGen Subscription Model

CodeGen may optionally provide application-level subscriptions.

Example:

```text
Free
    20 generations/month

Basic
    100 generations/month

Pro
    500 generations/month
```

These numbers are configurable and must NOT be hardcoded into generation logic.

The CodeGen quota controls how many generation operations a user can initiate through the CodeGen application.

The Higgsfield API independently determines whether the user's Higgsfield account has sufficient balance and whether the requested generation can be performed.

Example:

```text
User:

Higgsfield balance:
1,000 Units

CodeGen quota:
100 generations/month
```

If CodeGen quota is exhausted:

```text
CodeGen → reject request
```

If CodeGen quota remains but Higgsfield balance is exhausted:

```text
CodeGen → forward request
Higgsfield → reject due to insufficient balance
```

These conditions must remain independent.

---

# 4. Existing Frontend

Use the cloned Open-Higgsfield-style repository as the starting point.

Preserve the existing:

* Next.js architecture
* React components
* Tailwind CSS
* Studio layouts
* Image Studio
* Video Studio
* Lip Sync Studio
* Cinema Studio
* Model-selection UX
* Generation UX
* History UX
* Upload UX
* Download UX
* Responsive behavior

Do not rebuild the UI from scratch.

Do not replace the existing studio architecture unless technically necessary.

The existing project uses a dedicated API integration layer and model configuration layer.

The current Muapi integration must be abstracted/replaced rather than spreading Higgsfield-specific logic throughout UI components.

The target architecture should be:

```text
Frontend Components
       │
       ▼
CodeGen Client SDK/API Client
       │
       ▼
CodeGen Backend
       │
       ▼
Higgsfield Adapter
```

The frontend should communicate only with CodeGen.

The frontend should NOT directly call Higgsfield.

---

# 5. Remove Muapi Dependency

The existing Muapi integration must be completely isolated and replaced.

Identify and refactor all Muapi-specific:

* API clients
* API endpoints
* API key handling
* request builders
* response parsers
* polling logic
* upload logic
* model definitions
* environment variables
* UI references
* documentation
* error handling

Do not leave hidden Muapi dependencies in the production application.

Create a clean CodeGen abstraction.

For example:

```text
frontend/
    CodeGen API client
          │
          ▼
backend/
    Higgsfield adapter
          │
          ▼
    Higgsfield API
```

The frontend must never know whether CodeGen is internally using Higgsfield or another provider.

---

# 6. CodeGen API Abstraction

Create a provider-independent internal API.

Example:

```http
POST /api/v1/generations
```

Request:

```json
{
  "type": "video",
  "model": "higgsfield-model-id",
  "prompt": "A cinematic futuristic city",
  "parameters": {
    "aspect_ratio": "16:9",
    "duration": 5
  }
}
```

Response:

```json
{
  "id": "codegen-job-id",
  "status": "queued"
}
```

Then:

```http
GET /api/v1/generations/{id}
```

Response:

```json
{
  "id": "codegen-job-id",
  "status": "processing"
}
```

Eventually:

```json
{
  "id": "codegen-job-id",
  "status": "completed",
  "result": {
    "url": "https://..."
  }
}
```

The exact Higgsfield request/response schema must be implemented inside the backend adapter.

Do not expose provider-specific implementation details to frontend components.

---

# 7. Higgsfield Adapter

Create a dedicated service:

```text
HiggsfieldAdapter
```

Responsibilities:

* Authenticate against Higgsfield API
* Map CodeGen model IDs to Higgsfield model IDs
* Translate CodeGen request parameters into Higgsfield request parameters
* Submit generations
* Receive Higgsfield request/job IDs
* Poll or process asynchronous generation status
* Handle successful results
* Handle failed generations
* Handle cancellation where supported
* Normalize provider responses
* Normalize provider errors

Example:

```text
CodeGen Request
      │
      ▼
HiggsfieldAdapter
      │
      ├── translate request
      ├── authenticate
      ├── call Higgsfield
      └── normalize response
              │
              ▼
       CodeGen Job System
```

Never place Higgsfield API-specific code directly inside React components.

---

# 8. Higgsfield Credentials — BYOK

Users must be able to provide their own Higgsfield API credentials.

Do NOT store Higgsfield credentials in:

```text
localStorage
sessionStorage
React state
frontend source code
public environment variables
```

The browser must never directly call Higgsfield.

Preferred flow:

```text
User
 │
 ▼
CodeGen frontend
 │
 │ HTTPS
 ▼
CodeGen backend
 │
 ▼
Encrypted credential storage
 │
 ▼
Higgsfield API
```

Credentials must be encrypted at rest.

Use a secure secret-management approach appropriate for AWS.

Possible architecture:

```text
AWS Secrets Manager
```

for platform-level secrets, combined with encrypted database storage for per-user credentials where required.

Never log:

* API keys
* Authorization headers
* secrets
* complete credential objects

When a user views their settings, never return the complete stored API key.

Display only a masked representation.

Example:

```text
hf_********************92KD
```

---

# 9. User Credential Validation

Provide a CodeGen endpoint such as:

```http
POST /api/v1/integrations/higgsfield/test
```

The backend should securely test the user's credentials against an appropriate Higgsfield API operation.

Return normalized results such as:

```json
{
  "connected": true
}
```

or:

```json
{
  "connected": false,
  "error": "Invalid credentials"
}
```

Do not expose raw Higgsfield errors containing sensitive information.

---

# 10. Generation Job Architecture

Generation is asynchronous.

Do not keep an HTTP request open while waiting for a long video generation operation.

Use a job-based architecture.

```text
POST /generations
        │
        ▼
Create CodeGen Job
        │
        ▼
Submit to Higgsfield
        │
        ▼
Store Higgsfield Job ID
        │
        ▼
Return CodeGen Job ID
```

Example database record:

```text
codegen_job_id
user_id
provider
provider_job_id
generation_type
model
status
request_metadata
result_metadata
created_at
completed_at
error_code
```

Statuses should be normalized:

```text
queued
submitted
processing
completed
failed
cancelled
```

---

# 11. Polling / Webhooks

Where supported by the Higgsfield API, prefer webhook/event-based completion.

If webhook functionality is unavailable or unsuitable for a specific generation:

```text
CodeGen backend
      │
      ▼
poll Higgsfield
      │
      ▼
update CodeGen job
```

Do not make the browser directly poll Higgsfield.

The browser should poll CodeGen:

```http
GET /api/v1/generations/{id}
```

or use a CodeGen WebSocket/SSE mechanism if appropriate.

---

# 12. Model Registry

Create a CodeGen model registry.

Example:

```json
{
  "id": "video-model-1",
  "provider": "higgsfield",
  "provider_model": "actual-higgsfield-model-id",
  "type": "video",
  "enabled": true,
  "capabilities": {
    "text_to_video": true,
    "image_to_video": true
  }
}
```

The frontend should consume CodeGen's model registry instead of hardcoding provider-specific information wherever possible.

Create an endpoint:

```http
GET /api/v1/models
```

Return available models and capabilities.

This allows future providers to be added without redesigning the frontend.

---

# 13. Provider Abstraction

Although the first provider is Higgsfield, do not hardwire the entire architecture around Higgsfield.

Create:

```text
AIProvider
```

interface/abstraction.

Example:

```text
AIProvider
   │
   ├── HiggsfieldProvider
   │
   ├── FutureProviderA
   │
   └── FutureProviderB
```

The current production implementation should use:

```text
HiggsfieldProvider
```

But CodeGen should remain capable of supporting another provider later.

---

# 14. CodeGen Quota System

Implement a separate CodeGen usage system.

Example database:

```text
plans
users
subscriptions
usage_quotas
usage_events
```

Example:

```text
usage_quotas

user_id
period_start
period_end
generation_limit
generation_used
```

Every generation request must pass through:

```text
Quota Check
```

before being submitted to Higgsfield.

Flow:

```text
User requests generation
        │
        ▼
Authenticated?
        │
        ▼
Quota available?
        │
   ┌────┴────┐
   │         │
  YES        NO
   │         │
   ▼         ▼
Higgsfield  Reject
```

Only successful submission should consume the appropriate CodeGen quota unit.

Define clearly what counts as a generation.

Do not confuse CodeGen quota units with Higgsfield Units.

---

# 15. Failed Generation Handling

Do not blindly consume a CodeGen quota for requests that never reach Higgsfield.

Define transaction states.

Example:

```text
quota_reserved
      │
      ▼
submitted
      │
      ├── success
      │
      └── failure
```

If the generation fails because of an internal CodeGen error before submission, release the reservation.

If Higgsfield accepts the request but later reports a generation failure, follow a clearly defined quota policy.

Keep this policy configurable.

---

# 16. S3 Storage

Use Amazon S3 for application-managed media.

Potential structure:

```text
s3://codegen-production/

users/
    {user_id}/

        uploads/
        generated/
        projects/
        thumbnails/
```

Do not store large generated videos inside the application server filesystem.

Use S3 for:

* User uploads
* Generated videos
* Generated images
* Audio files
* Thumbnails
* Temporary assets where appropriate

Use signed URLs for private content.

Do not expose private S3 buckets publicly.

---

# 17. Storage Lifecycle

Generated media should not necessarily remain forever.

Implement configurable S3 lifecycle policies.

Example:

```text
Generated media
      │
      ├── 0–7 days → standard storage
      ├── 7–30 days → optional cheaper storage
      └── expiration → deletion
```

The retention policy must be configurable.

Do not hardcode a permanent storage assumption.

---

# 18. Projects and History

Maintain CodeGen-side generation history independently of Higgsfield.

A generation record should contain:

```text
id
user_id
project_id
type
model
prompt
parameters
provider
provider_job_id
status
result_location
thumbnail_location
created_at
completed_at
```

The user should be able to see:

```text
My Projects
   │
   ├── Project A
   │      ├── Generation 1
   │      ├── Generation 2
   │      └── Generation 3
   │
   └── Project B
          ├── Generation 1
          └── Generation 2
```

---

# 19. AWS Architecture

The application must be designed for AWS deployment without GPU infrastructure.

Preferred architecture:

```text
                         AWS

                    CloudFront
                        │
                        ▼
                  Next.js Frontend
                        │
                        ▼
                  API Gateway
                        │
                        ▼
              CodeGen Backend
                        │
        ┌───────────────┼────────────────┐
        │               │                │
        ▼               ▼                ▼
    Database           S3          Secrets Manager
        │
        ▼
   CodeGen Jobs
        │
        ▼
 Higgsfield API
        │
        ▼
 Higgsfield GPU infrastructure
```

The backend can be implemented using an AWS-compatible serverless/container architecture.

Keep the backend stateless wherever possible.

Do not require:

```text
GPU EC2
CUDA
local AI models
large persistent disks
24/7 inference servers
```

---

# 20. Frontend Hosting

The frontend should be deployable through AWS.

Prefer:

```text
Next.js
   │
   ▼
AWS-compatible deployment
   │
   ▼
CloudFront
```

If the application can be statically exported without losing required functionality:

```text
Next.js static output
        ↓
S3
        ↓
CloudFront
```

If the application requires server-side Next.js functionality, use an appropriate AWS Next.js runtime instead.

Do not force static export if the application depends on server-side rendering or server actions.

---

# 21. Backend Hosting

The CodeGen backend should be deployable without GPU infrastructure.

Suitable options include:

```text
API Gateway + Lambda
```

for lightweight serverless endpoints, or:

```text
API Gateway / ALB
        ↓
ECS/Fargate
        ↓
CodeGen backend
```

for a persistent containerized backend.

Keep the implementation portable.

Docker support should be retained.

The same backend should be runnable locally:

```bash
docker compose up
```

and deployable to AWS.

---

# 22. Database

Do not use SQLite as the production database.

Use an AWS-compatible relational database such as PostgreSQL.

Store:

* Users
* Authentication data
* Encrypted Higgsfield credentials
* Plans
* Subscriptions
* Quotas
* Usage events
* Projects
* Generations
* Provider job IDs
* Result metadata

Do not store large video files inside PostgreSQL.

Use S3 for media.

---

# 23. Security

Implement:

* HTTPS everywhere
* Secure authentication
* Password hashing
* Session/token security
* Rate limiting
* Request validation
* Input sanitization
* CORS configuration
* CSRF protection where applicable
* Secure cookies where applicable
* API-key encryption
* Secret management
* Audit logging
* No credential logging

Never expose:

```text
Higgsfield API key
Database password
AWS credentials
JWT signing secret
Encryption keys
```

to the frontend.

---

# 24. API Rate Limiting

There are two different rate-limit systems.

### CodeGen application rate limit

Example:

```text
10 requests/minute
100 generations/month
```

### Higgsfield API limitations

Controlled by Higgsfield.

Do not attempt to fake or override Higgsfield-side limits.

CodeGen should gracefully surface provider-side rate-limit errors.

Normalize errors:

```json
{
  "error": {
    "code": "PROVIDER_RATE_LIMITED",
    "message": "The generation provider temporarily rate-limited this request."
  }
}
```

Never expose raw provider internals unnecessarily.

---

# 25. Error Handling

Create a normalized CodeGen error system.

Examples:

```text
INVALID_CREDENTIALS
QUOTA_EXCEEDED
PROVIDER_AUTH_ERROR
PROVIDER_RATE_LIMITED
PROVIDER_INSUFFICIENT_BALANCE
INVALID_MODEL
INVALID_PARAMETER
GENERATION_FAILED
GENERATION_TIMEOUT
STORAGE_ERROR
INTERNAL_ERROR
```

Frontend components should consume normalized errors rather than parsing raw Higgsfield errors.

---

# 26. Logging and Monitoring

Log:

```text
request ID
user ID
CodeGen job ID
provider job ID
model
generation type
status
duration
error category
```

Never log:

```text
API keys
Authorization headers
passwords
secret tokens
```

Make logs suitable for AWS CloudWatch or an equivalent logging service.

---

# 27. No AI Model Hosting

This is a strict architectural requirement.

Do NOT add:

```text
Stable Diffusion server
Flux server
Kling server
Wan server
Hunyuan server
CUDA worker
PyTorch inference server
GPU EC2
```

unless explicitly requested in a future phase.

The first implementation uses Higgsfield as the external inference provider.

CodeGen is the orchestration, security, quota, storage, and product layer.

---

# 28. Frontend UX Changes

Modify the existing API-key/settings experience.

Replace Muapi-specific language with:

```text
Higgsfield API
```

Provide:

```text
Settings
   ↓
AI Provider
   ↓
Higgsfield
   ↓
Connect API
```

The user should be able to:

* Add credentials
* Test credentials
* Remove credentials
* Replace credentials
* See connection status
* See masked credentials
* See CodeGen quota
* See CodeGen usage

Do not display the actual secret after it has been stored.

---

# 29. User Experience

The main generation flow should remain simple:

```text
Select Studio
       ↓
Select Model
       ↓
Enter Prompt
       ↓
Configure Parameters
       ↓
Generate
       ↓
CodeGen checks quota
       ↓
CodeGen calls Higgsfield
       ↓
Generation begins
       ↓
CodeGen tracks job
       ↓
Result available
       ↓
Store/serve through S3
       ↓
Display result
```

The user should not have to understand the backend architecture.

---

# 30. Maintainability

Use clear modules.

Suggested backend:

```text
backend/

  app/
    api/
      auth.py
      users.py
      models.py
      generations.py
      projects.py
      integrations.py
      usage.py

    providers/
      base.py
      higgsfield.py

    services/
      auth_service.py
      generation_service.py
      quota_service.py
      storage_service.py
      credential_service.py
      project_service.py

    models/
      user.py
      project.py
      generation.py
      subscription.py
      usage.py
      credential.py

    schemas/
      generation.py
      model.py
      user.py
      provider.py

    core/
      config.py
      security.py
      logging.py

    workers/
      generation_worker.py
```

Adapt this structure to the existing repository rather than blindly creating duplicate architecture.

---

# 31. Frontend Architecture

Create a provider-neutral client:

```text
lib/
    codegen/
        client.ts
        generations.ts
        models.ts
        projects.ts
        integrations.ts
        usage.ts
```

Do not use:

```text
muapi.js
```

in the final production implementation.

The frontend should communicate with:

```text
/api/v1/...
```

of CodeGen.

---

# 32. Environment Variables

Never put private credentials into `NEXT_PUBLIC_*`.

Frontend configuration may contain:

```text
NEXT_PUBLIC_API_URL
```

Backend configuration may contain:

```text
DATABASE_URL
AWS_REGION
S3_BUCKET
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
HIGGSFIELD_API_BASE_URL
ENCRYPTION_KEY
JWT_SECRET
```

Use AWS Secrets Manager or an equivalent secure secret system in production.

Never commit `.env` files containing real secrets.

---

# 33. Local Development

The project must remain easy to run locally.

Preferred:

```bash
git clone <repository>

npm install

npm run dev
```

Backend:

```bash
docker compose up
```

or the project's appropriate development command.

Provide:

```text
.env.example
```

containing placeholders only.

Example:

```text
DATABASE_URL=
AWS_REGION=
S3_BUCKET=
HIGGSFIELD_API_BASE_URL=
ENCRYPTION_KEY=
JWT_SECRET=
```

Never include real credentials.

---

# 34. AWS Deployment Requirements

Prepare the application for:

```text
AWS
 ├── CloudFront
 ├── S3
 ├── API Gateway
 ├── Lambda or ECS/Fargate
 ├── PostgreSQL-compatible database
 ├── Secrets Manager
 ├── CloudWatch
 └── IAM
```

Use IAM least privilege.

The frontend should not receive unrestricted AWS credentials.

S3 access should use signed URLs or backend-controlled access.

---

# 35. Cost Optimization

The architecture must optimize for very low infrastructure cost.

The application should have:

```text
No GPU
No always-on inference server
No local model hosting
No unnecessary persistent compute
```

Prefer:

```text
serverless compute
S3
CloudFront
managed database
usage-based services
```

The major AI inference cost is intentionally externalized to the user's own Higgsfield account.

---

# 36. Important Business Model Constraint

This is a BYOK application.

CodeGen does not purchase Higgsfield generation Units on behalf of users.

CodeGen does not resell Higgsfield Units.

CodeGen does not deduct Higgsfield Units from a CodeGen wallet.

CodeGen only provides the application and its own usage quota/subscription.

However, before commercial launch, verify that the intended BYOK/end-user application model is permitted under the current Higgsfield API terms and obtain written confirmation if necessary.

The application must comply with Higgsfield's current API terms, credential requirements, end-user requirements, and any applicable restrictions on resale or API access.

---

# 37. Licensing

The source repository is described as MIT licensed.

Before production release:

1. Verify the repository's actual LICENSE file.
2. Preserve required MIT copyright/license notices.
3. Review dependency licenses.
4. Review any third-party assets.
5. Review Higgsfield API terms separately.
6. Do not assume the MIT license grants rights to third-party AI models or APIs.

The open-source frontend license and Higgsfield API rights are separate matters.

---

# 38. Do Not Over-Engineer the First Version

The first objective is NOT to build a giant AI infrastructure platform.

The first objective is:

```text
Existing frontend
       ↓
CodeGen backend
       ↓
Higgsfield API
       ↓
Generated result
```

Get this working first.

Then add:

```text
Authentication
       ↓
BYOK credentials
       ↓
Quota system
       ↓
Projects
       ↓
S3 storage
       ↓
Subscriptions
       ↓
Admin dashboard
       ↓
Analytics
```

Do not introduce unnecessary technologies unless they solve a concrete requirement.

---

# 39. Migration Strategy

Implement the project in phases.

## Phase 1 — Repository Analysis

Before changing code:

* Inspect the complete repository.
* Identify all Muapi integration points.
* Identify all model definitions.
* Identify all API request/response structures.
* Identify all upload flows.
* Identify all generation polling flows.
* Identify all authentication/API-key storage.
* Identify all pages/components dependent on Muapi.

Create a migration map.

Do not modify the project blindly.

---

## Phase 2 — CodeGen API Contract

Design the provider-neutral CodeGen API.

Document:

```text
Authentication
Models
Generations
Projects
Uploads
Results
Usage
Higgsfield integration
```

---

## Phase 3 — Higgsfield Adapter

Implement:

```text
CodeGen
   ↓
HiggsfieldAdapter
   ↓
Higgsfield API
```

Test:

* Authentication
* Image generation
* Video generation
* Supported model parameters
* Status tracking
* Results
* Failures
* Provider rate limits

Only implement model capabilities actually supported by the current Higgsfield API documentation.

Do not invent unsupported parameters.

---

## Phase 4 — Frontend Migration

Replace:

```text
Muapi client
```

with:

```text
CodeGen client
```

Preserve existing UI components wherever possible.

---

## Phase 5 — Secure BYOK

Implement:

```text
User
 ↓
Higgsfield API credentials
 ↓
CodeGen backend
 ↓
Encrypted storage
```

Add:

```text
Connect
Test
Disconnect
Replace
```

---

## Phase 6 — Quota System

Implement CodeGen-only application quotas.

Keep them independent from Higgsfield Units.

---

## Phase 7 — S3

Move generated media and uploads to S3.

Implement signed URLs and lifecycle policies.

---

## Phase 8 — AWS Deployment

Deploy:

```text
Frontend → CloudFront/S3 or suitable Next.js runtime

Backend → Lambda or ECS/Fargate

Database → managed PostgreSQL

Media → S3

Secrets → Secrets Manager

Logs → CloudWatch
```

---

# 40. Final Architectural Principle

The most important rule of the entire project is:

```text
             CODEGEN
                │
                │ owns
                ▼
       ┌─────────────────┐
       │ Application     │
       │ UX              │
       │ Users           │
       │ Projects        │
       │ Quotas          │
       │ Storage         │
       │ API abstraction │
       └────────┬────────┘
                │
                │ uses
                ▼
          HIGGSFIELD API
                │
                │ owns
                ▼
       ┌─────────────────┐
       │ AI Models       │
       │ GPU inference   │
       │ API balance     │
       │ Model costs     │
       │ Generation      │
       └─────────────────┘
```

CodeGen should **not** become an AI inference server.

CodeGen should become the **secure application and orchestration layer** around the user's own Higgsfield API access.

The existing Open-Higgsfield-style frontend should remain the foundation of the user experience, while the Muapi-specific integration is replaced with the CodeGen provider abstraction.

Build for AWS from the beginning, but keep the architecture portable and locally runnable.

Do not perform a major rewrite unless required by the existing codebase.

The final application should feel like a complete standalone CodeGen product to the user, while internally using the user's Higgsfield API credentials for the actual AI generation.
