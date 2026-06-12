# Xenia CRM — Backend API

A FastAPI + PostgreSQL backend powering the Xenia Retail CRM platform. Handles customer intelligence, AI-driven campaign planning, promotion management, and revenue attribution — all backed by Groq (Llama 3.3 70B) for fast AI inference.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI (Python 3.11+) |
| Database | PostgreSQL via SQLAlchemy ORM |
| AI / LLM | Groq API — `llama-3.3-70b-versatile` |
| ML | scikit-learn (churn prediction model) |
| Migrations | Alembic |
| Server | Uvicorn (ASGI) |

---

## Core Modules

### `/api/opportunities` — Suggested Actions
Auto-detected revenue opportunities (win-back, cross-sell, re-engage) generated nightly from customer RFM signals. Each opportunity has an audience size, potential revenue, recommended channel, and promotion.

### `/api/planner` — AI Campaign Planner
- `GET /prepare-context` — Fetches audience cohort, suppression data, and best-matching promotion for a given opportunity. Pure DB read, no AI.
- `POST /generate` — Calls Groq to generate WhatsApp / Email / SMS message copies, simulation projections, and explainable rationale.

### `/api/campaigns` — Campaign Lifecycle
Full campaign lifecycle: `draft → reviewed → awaiting_approval → approved → launched → completed`.
- `GET /` — List all campaigns with status filter
- `POST /` — Create a new campaign
- `GET /{id}/analytics` — Funnel metrics (sent / delivered / opened / clicked / purchased)
- `GET /{id}/recipients` — Individual communication logs
- `POST /{id}/launch` — Dispatch campaign to all recipients

### `/api/promotions` — Promotions Engine
CRUD for promotions with category/city targeting, date validity, max usage limits, and discount types (Percentage / Fixed).

### `/api/customers` — Shoppers
Paginated customer list, segment filtering, RFM metrics, and per-shopper story endpoint.

### `/api/briefing/latest` — Daily Executive Brief
Returns the latest AI-generated executive briefing instantly from cache. If today's briefing is missing, returns the most recent one and generates today's in the background (non-blocking).

### `/api/analytics` — NL Query Engine
Natural language → SQL via Groq. Analysts can ask questions in plain English and get structured data results.

### `/api/voice` — Voice Campaigns (ElevenLabs)
Premium outreach channel restricted to Champions and Lost Champions only.
- `GET /voices` — Fetch available ElevenLabs voice models (filters for "premade" free category voices).
- `GET /eligible-audience` — Verify customer cohort size and count eligible participants.
- `POST /generate-script` — Generate personalized voice scripts using Groq based on segment history.
- `POST /generate-audio` — Text-To-Speech (TTS) voice generation via ElevenLabs API (returns base64 audio).
- `POST /simulate-calls` — Synthetic voice call simulator and outcome status logging.

### `/api/settings` — API Configuration
System settings configuration and credentials.
- `GET /api-keys` — Fetch current API status (Groq and Elevenlabs keys).
- `POST /api-keys` — Store and validate new credentials in real-time.

### `/api/webhook/delivery` — Attribution Webhooks
Simulates carrier delivery callbacks (delivered / opened / clicked / promo_applied / purchased) for attribution tracking.

---

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app entry point, lifespan, CORS
│   ├── config.py            # Pydantic settings (reads from .env)
│   ├── database.py          # SQLAlchemy engine + session
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic request/response schemas
│   ├── routers/             # Route handlers (one file per domain)
│   │   ├── campaigns.py
│   │   ├── planner.py
│   │   ├── promotions.py
│   │   ├── customers.py
│   │   ├── opportunities.py
│   │   ├── analytics.py
│   │   ├── briefing.py
│   │   └── webhooks.py
│   ├── services/
│   │   ├── xenia_ai.py      # Groq LLM integration (all AI calls)
│   │   ├── simulation.py    # Campaign simulation engine
│   │   ├── attribution.py   # Revenue attribution pipeline
│   │   └── basket_affinity.py
│   └── ml/
│       ├── train_churn.py   # scikit-learn churn model training
│       └── feature_engineering.py
├── scripts/
│   ├── init_db.py           # Seed initial data
│   └── compute_segments.py  # RFM + segment computation
├── alembic/                 # Database migrations
├── requirements.txt
└── .env                     # Local config (not committed)
```

---

## Setup & Run

### 1. Clone & create virtual environment
```bash
git clone https://github.com/Srevarshan05/xenia-crm-backend.git
cd xenia-crm-backend
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

### 2. Configure environment
Create a `.env` file:
```env
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/xeno_crm
GROQ_API_KEY=your_groq_api_key_here
APP_ENV=development
DEBUG=true
SECRET_KEY=change-me-in-production
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

### 3. Set up database
```bash
# Create DB in PostgreSQL, then run:
python scripts/init_db.py
python scripts/compute_segments.py
```

### 4. Start the server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API docs available at: `http://localhost:8000/docs`

---

## Key Design Decisions

- **Groq over Gemini** — Switched to Groq (Llama 3.3 70B) for significantly faster inference (~500ms vs 3–8s). All AI calls use JSON mode for reliable structured output.
- **Non-blocking briefing** — The daily briefing endpoint always returns instantly from cache. If today's briefing is missing, Groq generation is dispatched as a background task.
- **Attribution via webhooks** — Revenue attribution runs only on delivery/purchase webhook events, not on every analytics GET request.
- **Lazy audience loading** — `prepare-context` runs only on explicit user action, not automatically on page load.

---

## API Reference

Full interactive docs: `http://localhost:8000/docs` (Swagger UI)

---

## License

MIT
