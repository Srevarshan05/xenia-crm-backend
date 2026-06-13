# AWS Elastic Beanstalk Deployment Report

This report provides complete instructions and configuration parameters for deploying the **Xenia CRM Backend** and **Channel Simulator Stub Service** on AWS Elastic Beanstalk.

---

## 1. Services Overview

| Service Name | Source Path | Target Deployment ZIP | Port | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Xenia CRM Backend** | `backend/` | `backend-v1-2.zip` | 8000 | FastAPI core backend with CRM APIs, AI planners, and DB connection. |
| **Channel Simulator** | `channel-service/` | `channel_v1.zip` | 8000 | FastAPI stub service that simulates channels (Email, SMS, WhatsApp) and triggers webhook callbacks. |

---

## 2. Python Environment & Startup Configurations

Both services are configured to run on the standard **AWS Elastic Beanstalk Python 3.12** platform.

### Main Backend (`backend-v1-2.zip`)
- **Runtime**: Python 3.12 (defined in `runtime.txt`)
- **Entry Point**: `application.py`
- **Procfile command**: 
  ```procfile
  web: uvicorn app.main:app --host 0.0.0.0 --port 8000
  ```

### Channel Simulator (`channel_v1.zip`)
- **Runtime**: Python 3.12 (defined in `runtime.txt`)
- **Entry Point**: `application.py`
- **Procfile command**: 
  ```procfile
  web: uvicorn main:app --host 0.0.0.0 --port 8000
  ```

---

## 3. Required Environment Variables

Configure these variables in the **Configuration -> Updates, monitoring, and logging -> Platform properties** section of each Elastic Beanstalk environment.

### Main Backend Environment Variables
| Variable Name | Description | Example / Recommended Value |
| :--- | :--- | :--- |
| `DATABASE_URL` | Neon PostgreSQL connection string. Must include SSL parameter. | `postgresql://user:password@ep-xxxx.neon.tech/xenia_db?sslmode=require` |
| `GROQ_API_KEY` | Groq AI LLM API Key. | `gsk_xxxxxxxxxxxxxxxxxxxx` |
| `GEMINI_API_KEY` | Gemini LLM API Key (optional / backward compatibility). | `AIzaSyxxxxxxxxxxxxxxxxxx` |
| `ELEVENLABS_API_KEY`| ElevenLabs Speech Synthesis API Key (optional for mock voice simulation). | `el_xxxxxxxxxxxxxxxxxxxx` |
| `APP_NAME` | Name of the FastAPI application. | `Xenia CRM` |
| `APP_ENV` | Application environment. | `production` |
| `DEBUG` | Enable or disable developer features (such as auto table creation). | `false` |
| `SECRET_KEY` | Secret key for JWT hashing and security. | `a-secure-randomly-generated-string` |
| `CHANNEL_SERVICE_URL`| Public HTTPS URL of the deployed Channel Simulator. | `https://channel-sim.us-east-1.elasticbeanstalk.com` |
| `CRM_WEBHOOK_URL` | Own public webhook URL for receiving callbacks. | `https://xenia-api.us-east-1.elasticbeanstalk.com/api/webhook/delivery` |
| `ALLOWED_ORIGINS` | CORS allowed origins (include your frontend domain). | `https://xenia-app.netlify.app` |
| `BRAND_NAME` | Default brand name for marketing templates. | `Xenia` |

### Channel Simulator Environment Variables
| Variable Name | Description | Example / Recommended Value |
| :--- | :--- | :--- |
| `CRM_WEBHOOK_URL` | Public webhook callback URL on the Main Backend. | `https://xenia-api.us-east-1.elasticbeanstalk.com/api/webhook/delivery` |

---

## 4. Step-by-Step Deployment Order

To establish the correct network bindings, follow this deployment sequence:

### Step 1: Deploy the Channel Simulator
1. Create a new application in AWS Elastic Beanstalk: `xenia-channel-simulator`.
2. Create an environment with the **Python 3.12** platform.
3. Upload the `channel_v1.zip` package.
4. Once created, copy the environment's public URL (e.g. `https://channel-sim.us-east-1.elasticbeanstalk.com`).

### Step 2: Deploy the Main Backend
1. Create a new application in AWS Elastic Beanstalk: `xenia-backend`.
2. Create an environment with the **Python 3.12** platform.
3. Upload the `backend-v1.zip` package.
4. Copy the backend environment's public URL (e.g. `https://xenia-api.us-east-1.elasticbeanstalk.com`).

### Step 3: Configure Main Backend Environment Properties
1. Go to the **Main Backend environment** console -> **Configuration** -> **Platform properties**.
2. Add all variables listed in Section 3, specifically pointing:
   - `CHANNEL_SERVICE_URL` to the **Channel Simulator URL** from Step 1.
   - `CRM_WEBHOOK_URL` to the **Main Backend URL** (e.g., `https://xenia-api.us-east-1.elasticbeanstalk.com/api/webhook/delivery`).
3. Apply changes and wait for environment update.

### Step 4: Configure Channel Simulator Environment Properties
1. Go to the **Channel Simulator environment** console -> **Configuration** -> **Platform properties**.
2. Set `CRM_WEBHOOK_URL` to `https://xenia-api.us-east-1.elasticbeanstalk.com/api/webhook/delivery`.
3. Apply changes and wait for environment update.

---

## 5. Verification of Event Lifecycle & Security

1. **SSL / Database connection**: Verify connection to Neon PostgreSQL works cleanly with `sslmode=require` embedded in `DATABASE_URL`.
2. **Lifecycle Flow**: Triggering a voice or digital campaign from the frontend will hit the Main Backend, which will queue message payloads to the Channel Simulator (`/send`).
3. **Simulation Callbacks**: The Channel Simulator will cycle through `delivered` -> `opened` -> `clicked` -> `promo_applied` -> `purchased` using background tasks, issuing secure POST requests to `CRM_WEBHOOK_URL`.
4. **Retry & Backoff**: If the Main Backend is temporarily rate-limited or busy, the simulator log will track and report hook delivery.
