# Face Anonymization System

A privacy-compliant (COPPA / FERPA / GDPR-oriented) media processing pipeline. It
cross-references uploaded **group photos** against a **"No-Social-Media-Consent"
student registry**, automatically blurs the faces of opted-out students, and
exposes a **human-in-the-loop review portal** where a reviewer confirms or
overrides every decision before an anonymized copy is finalized.

This repository is a complete, runnable implementation of the
[architecture blueprint](#architecture): a FastAPI + Celery backend with a real
OpenCV vision pipeline, a Next.js/TypeScript review console, and a Docker Compose
stack (PostgreSQL + pgvector, Redis).

---

## Table of contents
- [Quick start](#quick-start)
- [What actually happens](#what-actually-happens)
- [Architecture](#architecture)
- [Backend](#backend)
- [Frontend](#frontend)
- [Testing](#testing)
- [Configuration](#configuration)
- [Design notes & honesty about the vision model](#design-notes)
- [Security](#security)

---

## Quick start

### Option 0 — One command

```bash
./start.sh          # full Docker stack, built, started, seeded
./start.sh --local  # no Docker: SQLite + in-process worker + dev servers
./start.sh --stop   # stop either mode
```

### Option A — Docker Compose (full stack: Postgres + Redis + API + worker + web)

```bash
cp .env.example .env            # optional: edit secrets
docker compose up --build       # builds and starts everything

# In another shell, seed demo data (admin + opt-out students + one processed upload):
docker compose exec api python -m app.scripts.seed_demo
```

**Restricted networks:** if Docker Hub is unreachable, set the `*_IMAGE`
variables in `.env` to a mirror (examples in `.env.example`). If your network
intercepts TLS with a private CA, pass it to the builds:
`EXTRA_CA_BUNDLE="$(cat your-ca.pem)" docker compose build`.

Then open:
- **Web console:** http://localhost:3000  (log in with `admin` / `admin123`)
- **API docs (Swagger):** http://localhost:8000/docs

### Option B — Run locally without Docker (SQLite + in-process worker)

The stack is designed to run with **zero external infrastructure** for
development: SQLite for the database, the local filesystem for object storage,
and Celery in *eager* (synchronous) mode so no broker is required.

```bash
# --- Backend ---
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.scripts.download_models  # verified YuNet + SFace ONNX assets
python -m app.scripts.seed_demo        # creates ./face_blur.db + demo data
uvicorn app.main:app --reload          # http://localhost:8000

# --- Frontend (in a second shell) ---
cd frontend
npm install
cp .env.local.example .env.local       # NEXT_PUBLIC_API_BASE=http://localhost:8000
npm run dev                            # http://localhost:3000
```

Log in as `admin` / `admin123`. If you did not run the seeder, click
**"Generate demo image"** on the Review Queue to create a synthetic group photo
and watch the full detect → match → blur → review flow — no photos required.

---

## What actually happens

1. **Enroll opt-out students.** Under *Opt-Out Registry*, add each student whose
   parents did **not** consent, with a single-face reference photo. A face
   embedding is computed and stored; the photo lives in the private bucket only.
2. **Upload a group photo.** It is streamed to private storage, a tracking record
   is created, and the anonymization job is queued (Redis + Celery in production,
   inline in dev).
3. **Automated pass.** The worker uses a high-recall YuNet pass plus localized
   refinement around additional face proposals, aligns each crop from five
   landmarks, computes an SFace embedding, and searches all quality-checked
   templates in the opt-out registry. Confirmed and ambiguous near-matches are
   conservatively flagged (`is_blurred_by_system = true`).
4. **Human review.** The reviewer opens the image, sees every detection as a
   colored box (red = will be blurred), and clicks any box to override the
   decision. If a difficult pose is still missed, **Add missed face** lets the
   reviewer drag a server-rendered blur region directly over it. The final
   decision is `XOR(system_flag, human_override)` — so the
   reviewer can both **clear false positives** and **catch false negatives**.
5. **Finalize.** On commit, the server re-renders the image applying an
   irreversible Gaussian blur to every finally-flagged face and writes the
   anonymized, distributable copy to the public bucket. Raw originals are never
   exposed — only short-lived signed URLs are ever handed out.

---

## Architecture

```
Browser (Next.js)  ──JWT──▶  FastAPI gateway  ──▶  PostgreSQL (+pgvector)
                                   │                    ▲
                                   ├── private bucket ──┘  (raw originals)
                                   │
                                   └── Redis queue ──▶ Celery worker
                                                          │  OpenCV: detect →
                                                          │  embed → match → blur
                                                          └──▶ public bucket
                                                               (anonymized copies)
```

- **Raw, unblurred originals** live only in the private bucket and are reachable
  exclusively via short-lived signed URLs.
- **The worker is a pass-through**: it writes results to the DB and the public
  bucket, holding no durable local state.
- **Final rendering is server-side** and driven strictly by the database's blur
  flags, so no client-side manipulation can reveal a face that should be hidden.

---

## Backend

FastAPI + SQLAlchemy + Celery. Key modules (`backend/app/`):

| Module | Responsibility |
|---|---|
| `config.py` | Environment-driven settings with safe defaults |
| `models.py` | ORM: `User`, `Student`, `MediaUpload`, `DetectedFace` (+ XOR `is_final_blurred`) |
| `vision/pipeline.py` | YuNet detection, SFace alignment/embeddings, enrollment quality gates, padded redaction |
| `vision/synthetic.py` | Detectable synthetic faces for demo/tests (no real people) |
| `matching.py` | Cosine-distance search + confidence banding |
| `storage.py` | Pluggable object storage: local (signed URLs) or S3 (presigned) |
| `services.py` | Enrollment, processing, review/finalize orchestration |
| `tasks.py` / `celery_app.py` | Async processing (eager fallback when no broker) |
| `routers/` | `auth`, `students`, `media`, `assets` HTTP endpoints |

Selected endpoints (full list at `/docs`):

```
POST /api/v1/auth/login            → JWT
GET  /api/v1/students              → list opt-out registry
POST /api/v1/students              → enroll student (multipart: fields + reference_image)
POST /api/v1/media/upload          → upload group photo, queue processing
POST /api/v1/media/upload/batch    → upload up to 25 group photos in one request
POST /api/v1/media/demo            → generate + process a synthetic demo photo
DELETE /api/v1/media               → permanently delete all uploaded media
GET  /api/v1/media/{id}            → detail incl. detected faces + signed URLs
DELETE /api/v1/media/{id}          → permanently delete one upload + stored copies
POST /api/v1/media/{id}/review     → apply overrides, (optionally) finalize
GET  /api/v1/assets/{bucket}/{k}   → signed-URL object access (local backend)
```

## Frontend

Next.js 15 App Router + TypeScript (`frontend/`):
`login`, `dashboard` (review queue), `upload`, `students`, and
`review/[id]` (the interactive overlay editor). API access and JWT handling live
in `lib/`; the `evaluateFinalBlur` XOR helper mirrors the backend exactly.

---

## Testing

**Backend — 56 tests**, exercising the vision pipeline
(detection, embeddings, blur), matching, the XOR override logic, auth, signed-URL
access control, and the full upload → process → review → finalize workflow.

```bash
cd backend
pip install -r requirements-dev.txt
pytest --cov=app --cov-report=term-missing
```

**Frontend — typecheck + unit/component tests + production build:**

```bash
cd frontend
npm run typecheck
npm test          # blur XOR logic + ReviewQueue interaction (Testing Library)
npm run build
```

CI runs all of the above on every push (`.github/workflows/ci.yml`).

---

## Configuration

All backend settings are environment variables (see `backend/app/config.py`).
Highlights:

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./face_blur.db` | Use `postgresql+psycopg2://…` in prod |
| `STORAGE_BACKEND` | `local` | or `s3` |
| `STORAGE_LOCAL_DIR` | `./storage` | local object root |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | used to build signed asset URLs |
| `CELERY_TASK_ALWAYS_EAGER` | `true` | set `false` + run a worker in prod |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker/result backend |
| `MATCH_THRESHOLD` | `0.10` | max cosine distance for a match (see design notes) |
| `YUNET_SCORE_THRESHOLD` | `0.60` | primary detector confidence cutoff |
| `YUNET_REFINE_SCORE_THRESHOLD` | `0.40` | localized high-recall refinement cutoff |
| `DETECTOR_REFINEMENT_ENABLED` | `true` | refine small/tilted face proposals |
| `SFACE_MATCH_THRESHOLD` | `0.45` | conservative starter distance; calibrate locally |
| `MATCH_MIN_MARGIN` | `0.08` | required separation from the runner-up identity |
| `REDACTION_PADDING_RATIO` | `0.25` | expands coverage around the detector box |
| `REDACTION_MODE` | `hybrid` | `hybrid`, `pixelate`, `blur`, or `solid` |
| `JWT_SECRET` / `ADMIN_PASSWORD` | dev values | **change for any real deployment** |

---

<a name="design-notes"></a>
## Design notes & honesty about the vision model

The production path uses OpenCV's YuNet detector and SFace recognizer. The
download script verifies pinned SHA-256 checksums; inference stays local and runs
on CPU through OpenCV DNN. A Haar/pixel descriptor remains only as a degraded
fallback and for deterministic synthetic tests.

- **Alignment.** YuNet's five landmarks are passed through SFace `alignCrop`
  before feature extraction, reducing sensitivity to face-box shifts and pose.
- **Detection recall.** A conservative primary cutoff is supplemented by a
  lower-threshold YuNet pass limited to Haar-proposed crops. Overlapping results
  are merged, tiny weak boxes are rejected, and the reviewer can re-run the
  detector or draw a manual redaction for poses no automated model finds.
- **Multiple references.** Enrollment accepts one to five single-face photos.
  Each is checked for face count, size, sharpness, brightness, and detector
  confidence, then stored as an independent matching template.
- **Open-set safety.** Matching requires a threshold and a minimum margin from
  the runner-up. Low-margin candidates are blurred for privacy but are not
  assigned a student identity; the review UI labels them as ambiguous.
- **Redaction.** Final redaction expands the face box by 25% and defaults to a
  pixelation-plus-blur hybrid. Solid and other modes are configurable.
- **Calibration.** Generic thresholds are not a substitute for validation on
  authorized, representative school imagery. Put local images under
  `references/<student-id>/` and `queries/<student-id>/` (with unknown people in
  `queries/_unknown/`), then run:

  ```bash
  cd backend
  python -m app.scripts.evaluate_vision /path/to/dataset --output report.json
  ```
- **Vector search.** Embeddings are stored portably (JSON) and matched in NumPy,
  so the identical schema runs on SQLite and PostgreSQL. The Compose stack uses
  `pgvector` and enables the extension so you can migrate to an indexed
  `vector(512)` column and `<=>` search without changing the app's interface.

The evaluator reports detection failures, known-student identification rate,
unknown-person false matches, ambiguous cases, and genuine/impostor distance
distributions without sending images off the machine.

---

## Security

- JWT-authenticated API; bcrypt-hashed credentials.
- Raw originals are never publicly served — only short-lived HMAC-signed
  (local) or S3-presigned URLs.
- Final blur is applied server-side and irreversibly (Gaussian blur on pixels).
- **Before deploying:** set a strong `JWT_SECRET`, change `ADMIN_PASSWORD`,
  restrict `CORS_ORIGINS`, and put the API behind TLS.
