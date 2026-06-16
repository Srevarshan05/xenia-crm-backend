# Xenia CRM Backend

Xenia CRM Backend is a FastAPI-based backend service powering the Xenia Retail Marketing Platform.

The platform helps marketing teams identify customer opportunities, create targeted campaigns, generate AI-assisted marketing content, manage promotions, execute voice campaigns, track customer engagement, and measure campaign effectiveness through attribution analytics.

---

# Live Services

## Core CRM Backend

Base URL:

```text
http://xenia-backend-v2-env.eba-mymksz3y.ap-south-1.elasticbeanstalk.com
```

Swagger Documentation:

```text
http://xenia-backend-v2-env.eba-mymksz3y.ap-south-1.elasticbeanstalk.com/docs
```

OpenAPI Schema:

```text
http://xenia-backend-v2-env.eba-mymksz3y.ap-south-1.elasticbeanstalk.com/openapi.json
```

---

## Channel Simulator Service

Base URL:

```text
http://xenia-channel-simulator-env.eba-wjgmxqpw.ap-south-1.elasticbeanstalk.com
```

Swagger Documentation:

```text
http://xenia-channel-simulator-env.eba-wjgmxqpw.ap-south-1.elasticbeanstalk.com/docs
```

The Channel Simulator is responsible for simulating customer engagement events and campaign lifecycle tracking, including:

```text
Sent
→ Delivered
→ Opened
→ Clicked
→ Promo Applied
→ Purchased
```

These simulated events are sent back to the Core CRM Backend through webhook callbacks, enabling attribution analytics, campaign reporting, and lifecycle tracking.

---

# Architecture Overview

```text
Frontend (Vercel)
        ↓
Core CRM Backend
(AWS Elastic Beanstalk)

        ↓
Neon PostgreSQL

External Integrations
├── Groq (Llama 3.3 70B)
├── ElevenLabs
└── Channel Simulator Service
   (AWS Elastic Beanstalk)
```

---

# Core Capabilities

## Shopper Intelligence

- Customer segmentation
- RFM-based audience analysis
- Churn prediction
- Customer lifecycle insights
- Shopper journey tracking
- Customer profile management

---

## Suggested Actions

Automatically identifies marketing opportunities such as:

- VIP Shopper Re-engagement
- Customer Reactivation
- Cross-Sell Opportunities
- Channel Promotion Campaigns

Each recommendation includes:

- Target audience
- Estimated reach
- Revenue opportunity
- Recommended promotion
- Suggested channel
- Campaign rationale

---

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

- Audience targeting
- Promotion selection
- Campaign content generation
- Approval workflow
- Campaign tracking
- Attribution reporting

---

## Campaign Content Generation

Powered by Groq Llama 3.3 70B.

Generates:

- WhatsApp campaign content
- Email campaign content
- SMS campaign content
- Campaign recommendations
- Marketing copy variations
- Explainable campaign rationale

---

## Voice Campaigns

Powered by ElevenLabs.

Features:

- AI-generated voice scripts
- Voice advertisement generation
- Multi-voice selection
- Multi-language support
- Voice campaign simulation
- Audience eligibility validation
- Campaign approval workflow
- Voice campaign reporting

Eligible Segments:

- Champions
- Lost Champions

---

## Promotion Management

Supports:

- Percentage Discounts
- Fixed Amount Discounts
- Category Targeting
- City Targeting
- Segment Targeting
- Promotion Validity Controls
- Usage Limits
- Priority Management

---

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

- Campaign attribution
- Revenue attribution
- Conversion analytics
- Customer engagement timelines
- Campaign performance tracking

---

## Reporting

- Campaign performance reports
- Voice campaign reports
- PDF report generation
- Historical campaign analysis
- Revenue attribution summaries

---

# Technology Stack

| Layer | Technology |
|---------|---------|
| Framework | FastAPI |
| Language | Python 3.12 |
| Database | PostgreSQL (Neon) |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| AI Platform | Groq |
| Model | Llama 3.3 70B |
| Voice AI | ElevenLabs |
| Machine Learning | scikit-learn |
| PDF Generation | ReportLab |
| Server | Uvicorn |
| Hosting | AWS Elastic Beanstalk |

---

# Integrations

## Groq

Used for:

- Campaign content generation
- Voice script generation
- Campaign recommendations
- Explainable AI outputs
- Marketing content drafting

Model:

```text
llama-3.3-70b-versatile
```

---

## ElevenLabs

Used for:

- Text-to-Speech synthesis
- Voice advertisement generation
- Voice campaign creation
- Multi-language voice output
- Voice selection and customization

---

## Channel Simulator Service

The Channel Simulator mimics real communication providers and customer behavior.

Simulated Events:

```text
Sent
Delivered
Opened
Clicked
Promo Applied
Purchased
```

Generated events are delivered back to the Core CRM Backend through webhook callbacks.

This allows Xenia CRM to demonstrate:

- Lifecycle tracking
- Attribution analytics
- Campaign reporting
- Revenue attribution

without requiring real SMS, Email, WhatsApp, or Voice providers.

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
├── application.py
└── deployment_report.md
```

---

# Local Development

## Clone Repository

```bash
git clone <repository-url>
cd backend
```

---

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

---

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

# Running the Server

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

- Python 3.12
- Single Instance (t3.micro)
- AWS Elastic Beanstalk
- Uvicorn Application Server
- Environment Variable Based Configuration

Required Environment Variables:

```env
DATABASE_URL
GROQ_API_KEY
ELEVENLABS_API_KEY
SECRET_KEY
```

---

# Key Design Decisions

## PostgreSQL

Chosen for:

- Relational data modeling
- Strong consistency
- ACID transactions
- SQL analytics
- Campaign attribution queries

---

## Neon

Chosen for:

- Serverless PostgreSQL
- Automatic scaling
- Connection pooling
- Low operational overhead
- Cost efficiency

---

## Groq

Chosen for:

- Fast inference
- Low latency generation
- Structured JSON outputs
- Efficient campaign content generation

---

## ElevenLabs

Chosen for:

- High-quality speech synthesis
- Natural voice generation
- Multi-language support
- Voice campaign creation

---

## AWS Elastic Beanstalk

Chosen for:

- Managed deployment
- Simplified infrastructure management
- Easy scaling
- Integrated monitoring and logging

---

## Webhook-Based Attribution

Engagement events are processed through webhook callbacks rather than polling.

Benefits:

- Event-driven architecture
- Real-time attribution updates
- Reduced server load
- Realistic marketing workflow simulation

---

# API Documentation

Core CRM Backend:

```text
http://xenia-backend-v2-env.eba-mymksz3y.ap-south-1.elasticbeanstalk.com/docs
```

Channel Simulator Service:

```text
http://xenia-channel-simulator-env.eba-wjgmxqpw.ap-south-1.elasticbeanstalk.com/docs
```

---

# License

MIT License
