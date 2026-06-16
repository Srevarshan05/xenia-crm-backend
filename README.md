# Xenia CRM Backend

Xenia CRM Backend is a FastAPI-based backend service powering the Xenia Retail Marketing Platform.

The platform helps marketing teams identify customer opportunities, create targeted campaigns, generate AI-assisted marketing content, manage promotions, execute voice campaigns, track customer engagement, and measure campaign effectiveness through attribution analytics.

---

# Architecture Overview

```text
Frontend (Vercel)
        ↓
FastAPI Backend (AWS Elastic Beanstalk)
        ↓
Neon PostgreSQL

Integrations
├── Groq (Llama 3.3 70B)
├── ElevenLabs
└── Channel Simulator Service
```

---

# Core Capabilities

## Shopper Intelligence

* Customer segmentation
* RFM-based audience analysis
* Churn prediction
* Customer lifecycle insights
* Shopper journey tracking

## Suggested Actions

Automatically identifies marketing opportunities such as:

* VIP shopper re-engagement
* Customer reactivation
* Cross-sell opportunities
* Channel-based campaigns

Each recommendation includes:

* Target audience
* Estimated reach
* Recommended promotion
* Campaign rationale

## Campaign Management

Supports the complete campaign lifecycle:

```text
Draft
→ Review
→ Awaiting Approval
→ Approved
→ Active
→ Completed
```

Features include:

* Audience targeting
* Promotion selection
* Campaign content generation
* Approval workflow
* Campaign tracking

## Campaign Content Generation

Powered by Groq Llama 3.3 70B.

Generates:

* WhatsApp campaigns
* Email campaigns
* SMS campaigns
* Campaign explanations
* Marketing copy

## Voice Campaigns

Powered by ElevenLabs.

Features:

* AI-generated voice scripts
* Voice advertisement creation
* Multi-voice support
* Voice campaign simulation
* Audience eligibility validation

Restricted to:

* Champions
* Lost Champions

customer segments.

## Promotion Management

Supports:

* Percentage discounts
* Fixed amount discounts
* Category targeting
* City targeting
* Segment targeting
* Promotion validity controls
* Usage limits

## Attribution & Lifecycle Tracking

Tracks the complete customer engagement lifecycle:

```text
Sent
→ Delivered
→ Opened
→ Clicked
→ Promo Applied
→ Purchased
```

Provides:

* Campaign attribution
* Revenue attribution
* Engagement tracking
* Conversion analytics

## Reporting

* Campaign reports
* Voice campaign reports
* PDF report generation
* Historical campaign summaries

---

# Technology Stack

| Layer       | Technology         |
| ----------- | ------------------ |
| Framework   | FastAPI            |
| Language    | Python 3.12        |
| Database    | PostgreSQL (Neon)  |
| ORM         | SQLAlchemy         |
| Migrations  | Alembic            |
| AI Platform | Groq               |
| Model       | Llama 3.3 70B      |
| Voice AI    | ElevenLabs         |
| ML          | scikit-learn       |
| PDF Engine  | ReportLab          |
| Server      | Uvicorn / Gunicorn |

---

# Integrations

## Groq

Used for:

* Campaign content generation
* Voice script generation
* Campaign recommendations
* Explainable AI outputs

Model:

```text
llama-3.3-70b-versatile
```

---

## ElevenLabs

Used for:

* Text-to-speech synthesis
* Voice advertisement generation
* Voice campaign creation

---

## Channel Simulator Service

The Channel Simulator mimics real communication providers and generates engagement events for testing.

Simulated Events:

```text
Sent
Delivered
Opened
Clicked
Promo Applied
Purchased
```

Generated events are sent back to the backend through webhook callbacks, allowing attribution and reporting to function similarly to real-world marketing systems.

---

# Project Structure

```text
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   ├── schemas/
│   ├── routers/
│   ├── services/
│   └── ml/
├── scripts/
├── alembic/
├── requirements.txt
├── Procfile
├── runtime.txt
└── application.py
```

---

# Local Development

## Clone Repository

```bash
git clone <repository-url>
cd backend
```

## Create Virtual Environment

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

Linux / macOS:

```bash
source venv/bin/activate
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Environment Variables

Create a `.env` file:

```env
DATABASE_URL=<postgres-connection-string>

GROQ_API_KEY=<groq-api-key>

ELEVENLABS_API_KEY=<elevenlabs-api-key>

APP_ENV=development

DEBUG=true

SECRET_KEY=<secret-key>
```

---

# Database Setup

Initialize and seed the database:

```bash
python scripts/init_db.py
python scripts/compute_segments.py
```

---

# Running The Server

Development:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Application:

```text
http://localhost:8000
```

Interactive API Documentation:

```text
http://localhost:8000/docs
```

OpenAPI Schema:

```text
http://localhost:8000/openapi.json
```

---

# Deployment

## AWS Elastic Beanstalk

Deployment Configuration:

* Python 3.12
* Single Instance (t3.micro)
* Gunicorn + Uvicorn Workers

Environment Variables:

```env
DATABASE_URL
GROQ_API_KEY
ELEVENLABS_API_KEY
SECRET_KEY
```

Backend API Base URL:

```text
https://your-backend-domain.amazonaws.com
```

Health Check Endpoint:

```text
GET /health
```

---

# Key Design Decisions

### PostgreSQL

Chosen for:

* Relational data modeling
* Strong consistency
* SQL analytics
* Campaign attribution queries

### Neon

Chosen for:

* Serverless PostgreSQL
* Automatic scaling
* Connection pooling
* Low operational overhead

### Groq

Chosen for:

* Fast inference
* Structured JSON outputs
* Low latency campaign generation

### Elastic Beanstalk

Chosen for:

* Managed deployment
* Easy scaling
* Simplified infrastructure management

### Webhook-Based Attribution

Engagement events are processed through webhook callbacks rather than polling, providing a realistic event-driven marketing architecture.

---

# API Documentation

Swagger UI:

```text
http://localhost:8000/docs
```

OpenAPI Specification:

```text
http://localhost:8000/openapi.json
```

---

# License

MIT License
