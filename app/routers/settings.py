"""
Xenia CRM – Settings Router
Allows reading and live-updating API keys (GROQ, ElevenLabs) from the frontend.
Writes changes directly to the backend .env file and invalidates the settings cache
so the new key is active immediately — no server restart required.
"""

import os
import re
import logging
from pathlib import Path
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("xenia.settings")
router = APIRouter(prefix="/api/settings", tags=["Settings"])

# Resolve .env relative to this file: backend/app/routers/ → backend/.env
ENV_FILE = Path(__file__).parent.parent.parent / ".env"


# ── Pydantic Schemas ───────────────────────────────────────────────────────────

class ApiKeyPayload(BaseModel):
    groq_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None


class ApiKeyStatus(BaseModel):
    groq_api_key_set: bool
    groq_api_key_preview: str       # e.g. "gsk_****...KRN6E"
    elevenlabs_api_key_set: bool
    elevenlabs_api_key_preview: str  # e.g. "sk_****...0367"
    env_file_path: str


def _mask(value: str) -> str:
    """Show first 4 + last 4 chars only, rest as ****"""
    if not value or len(value) < 10:
        return "Not set"
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def _read_env() -> dict:
    """Parse .env file into key→value dict."""
    result = {}
    if not ENV_FILE.exists():
        return result
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _write_key(key: str, value: str):
    """Update or insert a key in the .env file, preserving all comments and structure."""
    if not ENV_FILE.exists():
        raise FileNotFoundError(f".env not found at {ENV_FILE}")

    content = ENV_FILE.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)

    if pattern.search(content):
        # Replace existing value
        new_content = pattern.sub(f"{key}={value}", content)
    else:
        # Append at end
        new_content = content.rstrip() + f"\n{key}={value}\n"

    ENV_FILE.write_text(new_content, encoding="utf-8")
    logger.info(f"[Settings] Updated {key} in .env")


def _reload_settings():
    """Invalidate the lru_cache on get_settings so next access reads the new .env."""
    try:
        from app.config import get_settings
        get_settings.cache_clear()
        logger.info("[Settings] Settings cache cleared — new values active")
    except Exception as e:
        logger.warning(f"[Settings] Cache clear failed: {e}")

    # Also push new values into the live Groq client if GROQ key changed
    try:
        from app.services.xenia_ai import XeniaAIService
        from app.config import Settings
        fresh = Settings()
        if fresh.groq_api_key:
            import groq
            XeniaAIService._client = groq.Groq(api_key=fresh.groq_api_key)
            logger.info("[Settings] Groq client reinitialized with new key")
    except Exception as e:
        logger.warning(f"[Settings] Groq client refresh failed: {e}")


# ── GET /api/settings/api-keys ────────────────────────────────────────────────

@router.get("/api-keys", response_model=ApiKeyStatus)
def get_api_key_status():
    """Returns masked previews of the current API keys stored in .env."""
    env = _read_env()
    groq_key = env.get("GROQ_API_KEY", "")
    eleven_key = env.get("ELEVENLABS_API_KEY", "")
    return ApiKeyStatus(
        groq_api_key_set=bool(groq_key),
        groq_api_key_preview=_mask(groq_key),
        elevenlabs_api_key_set=bool(eleven_key),
        elevenlabs_api_key_preview=_mask(eleven_key),
        env_file_path=str(ENV_FILE),
    )


# ── POST /api/settings/api-keys ───────────────────────────────────────────────

@router.post("/api-keys", response_model=ApiKeyStatus)
def update_api_keys(payload: ApiKeyPayload):
    """
    Updates GROQ_API_KEY and/or ELEVENLABS_API_KEY in the .env file.
    Immediately invalidates the settings cache so new keys are active without restart.
    """
    if not payload.groq_api_key and not payload.elevenlabs_api_key:
        raise HTTPException(status_code=400, detail="At least one key must be provided")

    updated = []
    try:
        if payload.groq_api_key and payload.groq_api_key.strip():
            _write_key("GROQ_API_KEY", payload.groq_api_key.strip())
            updated.append("GROQ_API_KEY")

        if payload.elevenlabs_api_key and payload.elevenlabs_api_key.strip():
            _write_key("ELEVENLABS_API_KEY", payload.elevenlabs_api_key.strip())
            updated.append("ELEVENLABS_API_KEY")

        _reload_settings()
        logger.info(f"[Settings] Successfully updated: {', '.join(updated)}")

    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"[Settings] Update failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update keys: {str(e)}")

    # Return fresh status after update
    return get_api_key_status()
