"""
Xenia CRM – Voice Campaigns Router
Premium outreach channel restricted to Champions and Lost Champions only.

Phase 1: Groq-powered AI script generation + simulated call lifecycle tracking.
Phase 2: ElevenLabs TTS integration (config slot pre-wired, see config.py).
"""

import json
import logging
import base64
import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.services.xenia_ai import XeniaAIService
from app.config import settings

logger = logging.getLogger("xenia.voice")
router = APIRouter(prefix="/api/voice", tags=["Voice Campaigns"])

# ── Eligibility Config ─────────────────────────────────────────────────────────
VOICE_ELIGIBLE_SEGMENTS = {"Champion", "Lost Champion"}
LARGE_AUDIENCE_THRESHOLD = 1000

# ── ElevenLabs Phase-2 Config (pre-wired, not active yet) ─────────────────────
# Set ELEVENLABS_API_KEY in .env to enable real TTS in Phase 2.
ELEVENLABS_VOICE_MODELS = {
    "xenia_voice":      {"name": "Xenia Voice",       "voice_id": "EXAVITQu4vr4xnSDxMaL", "gender": "female"},
    "premium_female":   {"name": "Premium Female",    "voice_id": "21m00Tcm4TlvDq8ikWAM", "gender": "female"},
    "premium_male":     {"name": "Premium Male",      "voice_id": "VR6AewLTigWG4xSOukaG", "gender": "male"},
    "regional_female":  {"name": "Regional Female",   "voice_id": "pNInz6obpgDQGcFmaJgB", "gender": "female"},
    "regional_male":    {"name": "Regional Male",     "voice_id": "yoZ06aMxZJJ28mfd3POQ", "gender": "male"},
}

# Cost estimate: ~$0.001 per second of audio (ElevenLabs Starter plan approx)
ELEVENLABS_COST_PER_SECOND_INR = 0.084   # ₹0.084 per second (~$0.001 USD)


def _get_voices_list(api_key: Optional[str]) -> List[dict]:
    fallback = [
        {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Xenia Voice", "gender": "female", "description": "Our signature brand voice (Bella)", "category": "premade"},
        {"voice_id": "21m00Tcm4TlvDq8ikWAM", "name": "Premium Female", "gender": "female", "description": "Warm, professional, authoritative (Rachel)", "category": "premade"},
        {"voice_id": "VR6AewLTigWG4xSOukaG", "name": "Premium Male", "gender": "male", "description": "Deep, confident, trustworthy (Arnold)", "category": "premade"},
        {"voice_id": "pNInz6obpgDQGcFmaJgB", "name": "Regional Female", "gender": "female", "description": "South Indian accent, relatable (Adam)", "category": "premade"},
        {"voice_id": "yoZ06aMxZJJ28mfd3POQ", "name": "Regional Male", "gender": "male", "description": "South Indian accent, friendly (Mimi)", "category": "premade"},
    ]
    if api_key:
        try:
            url = "https://api.elevenlabs.io/v1/voices"
            headers = {"xi-api-key": api_key}
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                voices = resp.json().get("voices", [])
                if voices:
                    res = []
                    for v in voices:
                        cat = v.get("category", "premade")
                        # Keep only free voices (premade category)
                        if cat != "premade":
                            continue
                        gender = v.get("labels", {}).get("gender", "unknown")
                        accent = v.get("labels", {}).get("accent", "")
                        use_case = v.get("labels", {}).get("use_case", "")
                        desc = f"{accent} accent, {use_case}" if accent and use_case else v.get("description", "")
                        if not desc:
                            desc = f"ElevenLabs voice model ({cat})"
                        res.append({
                            "voice_id": v.get("voice_id"),
                            "name": v.get("name"),
                            "gender": gender,
                            "description": desc,
                            "category": cat
                        })
                    return res
        except Exception as e:
            logger.error(f"Failed to fetch ElevenLabs voices: {e}")
    return fallback


# ── Pydantic Schemas ───────────────────────────────────────────────────────────

class VoiceModelInfo(BaseModel):
    voice_id: str
    name: str
    gender: str
    description: str
    category: str


class VoiceEligibleShopper(BaseModel):
    customer_id: str
    name: str
    city: str
    segment_name: str
    lifetime_value: float
    last_purchase_days: int
    total_orders: int
    top_category: Optional[str] = None
    churn_probability: Optional[float] = None
    reason_selected: str


class VoiceAudienceSummary(BaseModel):
    total_identified: int
    avg_ltv: float
    avg_inactivity_days: float
    potential_recovery_value: float
    city_distribution: dict
    segment_distribution: dict
    is_large_audience: bool
    large_audience_warning: Optional[str] = None


class VoiceEligibleAudienceResponse(BaseModel):
    summary: VoiceAudienceSummary
    shoppers: List[VoiceEligibleShopper]


class VoiceScriptRequest(BaseModel):
    campaign_goal: str
    audience_segment: str          # "Champion" | "Lost Champion"
    audience_size: int
    avg_ltv: float
    avg_inactivity_days: float
    voice_tone: str                # Professional | Friendly | Luxury | Conversational | Urgent Win-back
    language: str                  # English | Tamil | Hindi | English + Tamil | English + Hindi
    voice_model: str               # key from ELEVENLABS_VOICE_MODELS or dynamic voice_id
    promo_code: Optional[str] = None
    discount_value: Optional[float] = None
    discount_type: Optional[str] = None   # Percentage | Fixed Amount
    brand_name: str = "Xenia"
    top_category: Optional[str] = None


class VoiceScriptSection(BaseModel):
    call_objective: str
    opening: str
    main_offer: str
    closing: str
    cta: str
    full_script: str


class VoiceScriptResponse(BaseModel):
    script: VoiceScriptSection
    estimated_duration_sec: int
    estimated_cost_per_call_inr: float
    estimated_total_cost_inr: float
    voice_model_name: str
    language: str
    word_count: int
    notes: str


class SimulatedCallEvent(BaseModel):
    shopper_name: str
    customer_id: str
    city: str
    segment: str
    ltv: float
    call_status: str          # completed | no_answer | busy | dropped
    duration_sec: Optional[int] = None
    promo_sent: bool = False
    purchase_attributed: bool = False
    attributed_revenue: Optional[float] = None
    timeline: List[dict]


class VoiceSimulationResponse(BaseModel):
    campaign_id: str
    total_calls_initiated: int
    calls_answered: int
    calls_completed: int
    calls_no_answer: int
    calls_dropped: int
    interested_customers: int
    promo_sent: int
    attributed_purchases: int
    total_revenue_generated: float
    estimated_roi: float
    estimated_cost_inr: float
    shopper_events: List[SimulatedCallEvent]


# ── GET /api/voice/voices ─────────────────────────────────────────────────────

@router.get("/voices", response_model=List[VoiceModelInfo])
def get_voice_models():
    """
    Fetches available voices from ElevenLabs API (or falls back to high-quality premade list).
    """
    from app.config import get_settings
    fresh_settings = get_settings()
    api_key = fresh_settings.elevenlabs_api_key
    return _get_voices_list(api_key)



# ── GET /api/voice/eligible-audience ──────────────────────────────────────────

@router.get("/eligible-audience", response_model=VoiceEligibleAudienceResponse)
def get_voice_eligible_audience(db: Session = Depends(get_db)):
    """
    Returns only Champion and Lost Champion customers, ordered by LTV descending.
    Excludes High Value, At-Risk, and all other segments — voice is premium-only.
    """
    try:
        rows = db.execute(text("""
            SELECT
                c.customer_id::text,
                c.name,
                c.city,
                cs.segment_name,
                COALESCE(m.total_spend, 0)              AS lifetime_value,
                COALESCE(m.days_since_last_order, 0)    AS last_purchase_days,
                COALESCE(m.total_orders, 0)             AS total_orders,
                m.top_category,
                m.churn_probability
            FROM customers c
            JOIN customer_segments cs
                ON cs.customer_id = c.customer_id
                AND cs.segment_name IN ('Champion', 'Lost Champion')
            LEFT JOIN customer_metrics m
                ON m.customer_id = c.customer_id
            ORDER BY COALESCE(m.total_spend, 0) DESC
            LIMIT 500
        """)).fetchall()

        if not rows:
            # Return empty but valid response
            return VoiceEligibleAudienceResponse(
                summary=VoiceAudienceSummary(
                    total_identified=0, avg_ltv=0, avg_inactivity_days=0,
                    potential_recovery_value=0, city_distribution={},
                    segment_distribution={}, is_large_audience=False
                ),
                shoppers=[]
            )

        shoppers = []
        city_dist: dict = {}
        seg_dist: dict = {}
        total_ltv = 0.0
        total_inactivity = 0.0

        for row in rows:
            ltv = float(row.lifetime_value or 0)
            days = int(row.last_purchase_days or 0)
            seg = row.segment_name or "Champion"
            city = row.city or "Unknown"

            city_dist[city] = city_dist.get(city, 0) + 1
            seg_dist[seg] = seg_dist.get(seg, 0) + 1
            total_ltv += ltv
            total_inactivity += days

            # Build reason string
            if seg == "Champion":
                reason = f"Top-tier champion with ₹{ltv:,.0f} LTV · {row.total_orders} orders"
            else:
                churn_pct = int((row.churn_probability or 0) * 100)
                reason = f"Previously high-value · inactive {days}d · {churn_pct}% churn risk"

            shoppers.append(VoiceEligibleShopper(
                customer_id=row.customer_id,
                name=row.name,
                city=city,
                segment_name=seg,
                lifetime_value=ltv,
                last_purchase_days=days,
                total_orders=int(row.total_orders or 0),
                top_category=row.top_category,
                churn_probability=float(row.churn_probability or 0),
                reason_selected=reason
            ))

        n = len(shoppers)
        avg_ltv = total_ltv / n if n else 0
        avg_inactivity = total_inactivity / n if n else 0
        potential_recovery = avg_ltv * 0.28 * n   # 28% recovery rate assumption

        is_large = n > LARGE_AUDIENCE_THRESHOLD
        warning = (
            f"Large audience detected ({n:,} shoppers). "
            "Voice campaigns above 1,000 shoppers are very expensive. "
            "Consider segmenting further or using WhatsApp instead."
        ) if is_large else None

        summary = VoiceAudienceSummary(
            total_identified=n,
            avg_ltv=round(avg_ltv, 2),
            avg_inactivity_days=round(avg_inactivity, 1),
            potential_recovery_value=round(potential_recovery, 2),
            city_distribution=city_dist,
            segment_distribution=seg_dist,
            is_large_audience=is_large,
            large_audience_warning=warning
        )

        return VoiceEligibleAudienceResponse(summary=summary, shoppers=shoppers)

    except Exception as e:
        logger.error(f"Voice eligible audience query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load voice audience: {str(e)}")


def _build_fallback_script(payload: "VoiceScriptRequest") -> dict:
    """
    Generates a professional, context-aware voice script without Groq.
    Triggered when Groq API is unavailable (rate limit / network error).
    Uses audience data, tone, language, and promo to build a natural script.
    """
    brand = payload.brand_name or "Xenia"
    seg = payload.audience_segment
    promo = payload.promo_code or "SPECIAL"
    discount = payload.discount_value or 20
    category = payload.top_category or "your favorite products"
    lang = payload.language or "English"

    if lang == "Tamil":
        if seg == "Champion":
            objective = "Reward loyal Tamil VIP customers"
            opening = f"வணக்கம்! நான் {brand} பிராண்டில் இருந்து பேசுகிறேன்."
            main_offer = f"எங்கள் மிகச் சிறந்த வாடிக்கையாளரான உங்களுக்கு, {category}-க்கு விளம்பர குறியீடு {promo}-ஐ பயன்படுத்தி {discount:.0f}% தள்ளுபடி வழங்குகிறோம்."
            cta = f"உடனே எங்கள் செயலியைப் பயன்படுத்தி {promo} குறியீட்டைப் போடுங்கள்."
            closing = "எங்கள் மீது வைத்துள்ள நம்பிக்கைக்கு நன்றி, வணக்கம்."
        else:
            objective = "Win back high-value Tamil customers"
            opening = f"வணக்கம்! நான் {brand} பிராண்டில் இருந்து பேசுகிறேன். உங்களை மிகவும் இழக்கிறோம்."
            main_offer = f"மீண்டும் உங்களை வரவேற்க, {category}-க்கு விளம்பர குறியீடு {promo}-ஐ பயன்படுத்தி {discount:.0f}% தள்ளுபடி தருகிறோம்."
            cta = f"இன்றே எங்கள் செயலியைப் பயன்படுத்தி ஆர்டர் செய்யுங்கள்."
            closing = "நன்றி, மீண்டும் வாருங்கள்!"
        full_script = f"{opening} {main_offer} {cta} {closing}"

    elif lang == "Hindi":
        if seg == "Champion":
            objective = "Reward loyal Hindi VIP customers"
            opening = f"नमस्ते! मैं {brand} से बात कर रहा हूँ।"
            main_offer = f"हमारे सबसे खास ग्राहक होने के नाते, आपको प्रोमो कोड {promo} का उपयोग करके {category} पर {discount:.0f}% की विशेष छूट मिल रही है।"
            cta = f"कृपया अभी हमारे ऐप पर जाएं और ऑर्डर करते समय {promo} कोड का उपयोग करें।"
            closing = "हमारे साथ जुड़े रहने के लिए धन्यवाद, नमस्ते।"
        else:
            objective = "Win back high-value Hindi customers"
            opening = f"नमस्ते! मैं {brand} से बात कर रहा हूँ। हम आपको बहुत याद कर रहे हैं।"
            main_offer = f"स्वागत उपहार के रूप में, आपको प्रोमो कोड {promo} का उपयोग करके {category} पर {discount:.0f}% की छूट मिल रही है।"
            cta = f"आज ही हमारी ऐप खोलें और इस विशेष ऑफर का लाभ उठाएं।"
            closing = "धन्यवाद, आपका दिन शुभ हो।"
        full_script = f"{opening} {main_offer} {cta} {closing}"

    elif lang == "English + Tamil":
        if seg == "Champion":
            objective = "Reward loyal VIP customers in Tanglish"
            opening = f"Hello! Naanga {brand}-la irundhu call panrom."
            main_offer = f"Neenga namma VIP customer. Adhaan ungaluku {category}-la {discount:.0f}% discount tharrom."
            cta = f"Checkout la promo code {promo} apply panni order pannunga."
            closing = "Thanks for shopping with us. Nandri!"
        else:
            objective = "Win back high-value customers in Tanglish"
            opening = f"Hello! Naanga {brand}-la irundhu call panrom. We missed you!"
            main_offer = f"Special welcome-back gift-a {category}-la {discount:.0f}% discount tharrom."
            cta = f"Namma app open panni, {promo} code use panni order pannunga."
            closing = "Thank you so much. Nandri!"
        full_script = f"{opening} {main_offer} {cta} {closing}"

    elif lang == "English + Hindi":
        if seg == "Champion":
            objective = "Reward loyal VIP customers in Hinglish"
            opening = f"Hello! Hum {brand} se baat kar rahe hain."
            main_offer = f"Aap hamare VIP customer hain. Isiliye hum aapko {category} par {discount:.0f}% ki special discount de rahe hain."
            cta = f"Bas app par jaake checkout ke waqt promo code {promo} apply karein."
            closing = "Humare saath bane rehne ke liye dhanyavaad!"
        else:
            objective = "Win back high-value customers in Hinglish"
            opening = f"Hello! Hum {brand} se baat kar rahe hain. We miss you!"
            main_offer = f"Aapke liye special welcome back gift hai, {category} par {discount:.0f}% discount."
            cta = f"Aaj hi hamari app par jaakar promo code {promo} use karke order karein."
            closing = "Thank you and dhanyavaad!"
        full_script = f"{opening} {main_offer} {cta} {closing}"

    else:
        if seg == "Champion":
            objective = f"Reward loyal {brand} shoppers with an exclusive VIP offer"
            opening = f"Hello! This is {brand} calling."
            main_offer = f"As a loyal VIP customer, we want to offer you {discount:.0f}% off on {category} using promo code {promo}."
            cta = f"Visit our app and apply {promo} at checkout."
            closing = "Thank you for being a valued customer!"
        else:
            objective = f"Win back high-value {brand} customers with a personalized incentive"
            opening = f"Hello! This is {brand} calling. We miss you!"
            main_offer = f"As a welcome-back gift, we are offering you {discount:.0f}% off on {category} using promo code {promo}."
            cta = f"Visit our app and apply {promo} at checkout."
            closing = "Thank you for choosing us."
        full_script = f"{opening} {main_offer} {cta} {closing}"

    return {
        "call_objective": objective,
        "opening": opening,
        "main_offer": main_offer,
        "closing": closing,
        "cta": cta,
        "full_script": full_script,
    }


# ── POST /api/voice/generate-script ───────────────────────────────────────────

@router.post("/generate-script", response_model=VoiceScriptResponse)
def generate_voice_script(payload: VoiceScriptRequest):
    """
    Uses Groq Llama 70b to generate a SHORT (2-3 lines, 25-35 words) ElevenLabs-optimized
    voice advertisement script. Falls back to a deterministic professional script
    if Groq is rate-limited or unavailable — no 500 errors.
    """
    discount_str = ""
    if payload.promo_code and payload.discount_value:
        if payload.discount_type == "Percentage":
            discount_str = f"a {payload.discount_value:.0f}% discount using code {payload.promo_code}"
        else:
            discount_str = f"rupees {payload.discount_value:.0f} off using code {payload.promo_code}"

    tone_guidance = {
        "Professional":      "formal, confident, polished corporate tone",
        "Friendly":          "warm, approachable, conversational and kind",
        "Luxury":            "premium, exclusive, refined and aspirational",
        "Conversational":    "natural, relaxed, like a friend calling",
        "Urgent Win-back":   "sincere, urgent but respectful, emphasize limited time",
    }.get(payload.voice_tone, "professional and friendly")

    lang_constraints = ""
    if payload.language == "Tamil":
        lang_constraints = (
            "LANGUAGE CONSTRAINT: The language is strictly Tamil. The script values for all JSON fields (including 'opening', 'main_offer', 'closing', 'cta', and 'full_script') "
            "MUST be written ONLY using native Tamil script characters (e.g., தமிழ், வணக்கம்). DO NOT write in English/Latin letters. "
            "Do not transliterate Tamil into English letters. All outputs in the JSON fields (except keys) must be strictly in Tamil script characters."
        )
    elif payload.language == "Hindi":
        lang_constraints = (
            "LANGUAGE CONSTRAINT: The language is strictly Hindi. The script values for all JSON fields (including 'opening', 'main_offer', 'closing', 'cta', and 'full_script') "
            "MUST be written ONLY using native Hindi Devanagari script characters (e.g., हिन्दी, नमस्ते). DO NOT write in English/Latin letters. "
            "Do not transliterate Hindi into English letters. All outputs in the JSON fields (except keys) must be strictly in Devanagari characters."
        )
    elif payload.language == "English + Tamil":
        lang_constraints = (
            "LANGUAGE CONSTRAINT: The language is English + Tamil (Tanglish). Write a natural spoken combination/blend of English and Tamil. "
            "Write the script using English/Latin characters, but with the vocabulary and sentence structure being a mix of English and Tamil as spoken in daily life."
        )
    elif payload.language == "English + Hindi":
        lang_constraints = (
            "LANGUAGE CONSTRAINT: The language is English + Hindi (Hinglish). Write a natural spoken combination/blend of English and Hindi. "
            "Write the script using English/Latin characters, but with the vocabulary and sentence structure being a mix of English and Hindi as spoken in daily life."
        )
    else:
        lang_constraints = (
            "LANGUAGE CONSTRAINT: The language is strictly English. The values for all JSON fields MUST be in English."
        )

    prompt = (
        f"You are a voice script writer for a retail brand called {payload.brand_name}. "
        f"Write a VERY CONCISE voice call advertisement script optimized for ElevenLabs Text-to-Speech. "
        f"AUDIENCE: {payload.audience_segment} customers, avg LTV Rs {payload.avg_ltv:,.0f}, "
        f"avg inactivity {payload.avg_inactivity_days:.0f} days, "
        f"top category: {payload.top_category or 'general retail'}. "
        f"GOAL: {payload.campaign_goal}. "
        f"PROMOTION: {discount_str if discount_str else 'exclusive offer'}. "
        f"TONE: {tone_guidance}. LANGUAGE: {payload.language}. {lang_constraints} "
        f"REQUIREMENTS: Exactly between 25 and 35 words (this corresponds to exactly 2-3 lines of text, or 10-15 seconds of speech). "
        f"The full script MUST be between 25 and 35 words. Natural human speech. No aggressive sales language. "
        f"One offer, one clear call to action. Keep brand name like '{payload.brand_name}' and promo code '{payload.promo_code}' in English/Latin script. "
        f"Return ONLY valid JSON: "
        f'{"{"}"call_objective": "...", "opening": "...", "main_offer": "...", "closing": "...", "cta": "...", "full_script": "..."{"}"}'
    )

    data = None
    used_fallback = False
    fallback_reason = ""

    # ── Try Groq first ─────────────────────────────────────────────────────────
    try:
        raw = XeniaAIService.generate_content_with_retry(prompt)
        parsed = json.loads(raw)
        # Validate all required keys exist
        required = {"call_objective", "opening", "main_offer", "closing", "cta", "full_script"}
        if required.issubset(parsed.keys()):
            data = parsed
        else:
            logger.warning("Groq returned incomplete JSON keys — using fallback")
            used_fallback = True
            fallback_reason = "Groq returned incomplete response"
    except Exception as e:
        err_str = str(e).lower()
        if "rate_limit" in err_str or "429" in err_str or "tokens per day" in err_str:
            logger.warning(f"Groq TPD rate limit hit — using deterministic fallback script")
            fallback_reason = "Groq daily token limit reached — using pre-built script"
        else:
            logger.warning(f"Groq unavailable ({type(e).__name__}) — using deterministic fallback script")
            fallback_reason = f"Groq unavailable — using pre-built script"
        used_fallback = True

    # ── Fallback: build script without AI ─────────────────────────────────────
    if data is None:
        data = _build_fallback_script(payload)

    script = VoiceScriptSection(
        call_objective=data.get("call_objective", "Re-engage valued customer with exclusive offer"),
        opening=data.get("opening", f"Hello! This is {payload.brand_name} calling."),
        main_offer=data.get("main_offer", "We have a special offer just for you."),
        closing=data.get("closing", "Thank you for being a valued customer."),
        cta=data.get("cta", "Visit our app to claim your offer today."),
        full_script=data.get("full_script", "")
    )

    # Estimate duration: ~130 words per minute for a calm, clear speaking pace
    full_text = script.full_script or f"{script.opening} {script.main_offer} {script.closing} {script.cta}"
    word_count = len(full_text.split())
    duration_sec = max(20, min(45, int((word_count / 130) * 60)))

    cost_per_call = round(duration_sec * ELEVENLABS_COST_PER_SECOND_INR, 2)
    total_cost = round(cost_per_call * payload.audience_size, 2)

    # Resolve voice name dynamically
    from app.config import get_settings
    fresh_settings = get_settings()
    api_key = fresh_settings.elevenlabs_api_key

    voices = _get_voices_list(api_key)
    voice_name = "Custom Voice"
    for v in voices:
        if v["voice_id"] == payload.voice_model or v["name"] == payload.voice_model:
            voice_name = v["name"]
            break

    notes = (
        f"⚠️ {fallback_reason}. Script is professionally crafted and ready for review."
        if used_fallback
        else "Script generated by Groq AI. Optimized for ElevenLabs TTS."
    )

    return VoiceScriptResponse(
        script=script,
        estimated_duration_sec=duration_sec,
        estimated_cost_per_call_inr=cost_per_call,
        estimated_total_cost_inr=total_cost,
        voice_model_name=voice_name,
        language=payload.language,
        word_count=word_count,
        notes=notes
    )


# ── POST /api/voice/generate-audio ────────────────────────────────────────────

class AudioRequest(BaseModel):
    text: str
    voice_model: str = "xenia_voice"
    stability: float = 0.55
    similarity_boost: float = 0.75
    style: float = 0.0
    use_speaker_boost: bool = True


class AudioResponse(BaseModel):
    audio_base64: str       # base64-encoded MP3
    content_type: str       # "audio/mpeg"
    duration_estimate_sec: int
    voice_model_name: str
    generated_by: str       # "elevenlabs" | "mock"


@router.post("/generate-audio", response_model=AudioResponse)
async def generate_audio(payload: AudioRequest):
    """
    Converts a script to audio using ElevenLabs TTS API.
    Returns base64-encoded MP3 audio for the frontend audio player.
    Falls back to a mock response if ELEVENLABS_API_KEY is not set.
    """
    # Re-read settings fresh in case key was updated via /api/settings/api-keys
    from app.config import get_settings
    fresh_settings = get_settings()
    api_key = fresh_settings.elevenlabs_api_key

    voice_id = payload.voice_model
    voice_name = "Custom Voice"

    voice_map = {
        "xenia_voice":     "EXAVITQu4vr4xnSDxMaL",
        "premium_female":  "21m00Tcm4TlvDq8ikWAM",
        "premium_male":    "VR6AewLTigWG4xSOukaG",
        "regional_female": "pNInz6obpgDQGcFmaJgB",
        "regional_male":   "yoZ06aMxZJJ28mfd3POQ",
    }
    voice_name_map = {
        "xenia_voice":     "Xenia Voice",
        "premium_female":  "Premium Female",
        "premium_male":    "Premium Male",
        "regional_female": "Regional Female",
        "regional_male":   "Regional Male",
    }

    if voice_id in voice_map:
        voice_id = voice_map[voice_id]
        voice_name = voice_name_map[payload.voice_model]
    else:
        # Resolve via dynamic voices list
        voices = _get_voices_list(api_key)
        for v in voices:
            if v["voice_id"] == voice_id or v["name"] == voice_id:
                voice_id = v["voice_id"]
                voice_name = v["name"]
                break

    word_count = len(payload.text.split())
    duration_est = max(20, min(60, int((word_count / 130) * 60)))

    # ── Real ElevenLabs TTS ────────────────────────────────────────────────────
    if api_key:
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            }
            body = {
                "text": payload.text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": payload.stability,
                    "similarity_boost": payload.similarity_boost,
                    "style": payload.style,
                    "use_speaker_boost": payload.use_speaker_boost,
                },
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=body)

            if resp.status_code == 200:
                audio_b64 = base64.b64encode(resp.content).decode("utf-8")
                logger.info(f"[ElevenLabs] Audio generated: {len(resp.content)} bytes, voice={voice_id}")
                return AudioResponse(
                    audio_base64=audio_b64,
                    content_type="audio/mpeg",
                    duration_estimate_sec=duration_est,
                    voice_model_name=voice_name,
                    generated_by="elevenlabs",
                )
            else:
                err = resp.text[:200]
                logger.error(f"[ElevenLabs] API error {resp.status_code}: {err}")
                # Fall through to mock
        except Exception as e:
            logger.error(f"[ElevenLabs] Request failed: {e}")
            # Fall through to mock

    # ── Mock fallback (no API key or ElevenLabs error) ─────────────────────────
    logger.info("[ElevenLabs] Using mock audio response (no API key or TTS error)")
    return AudioResponse(
        audio_base64="",
        content_type="audio/mpeg",
        duration_estimate_sec=duration_est,
        voice_model_name=voice_name,
        generated_by="mock",
    )



@router.post("/simulate-calls", response_model=VoiceSimulationResponse)
def simulate_voice_calls(payload: dict):
    """
    Simulates outbound call lifecycle events for the approved voice campaign.
    Generates realistic call journey: Initiated → Ringing → Answered → Voice Played
    → Completed → Promo Sent → Purchase Attributed.
    
    Uses seeded randomization for deterministic demo data.
    """
    shoppers = payload.get("shoppers", [])
    promo_code = payload.get("promo_code", "VIPWIN25")
    campaign_id = str(uuid.uuid4())

    if not shoppers:
        raise HTTPException(status_code=400, detail="No shoppers provided for simulation")

    rng = random.Random(42)  # Seeded for consistent demo results

    events: List[SimulatedCallEvent] = []
    total_answered = 0
    total_completed = 0
    total_no_answer = 0
    total_dropped = 0
    total_interested = 0
    total_promo_sent = 0
    total_purchases = 0
    total_revenue = 0.0

    base_time = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)

    for i, shopper in enumerate(shoppers[:200]):  # Cap at 200 for simulation
        ltv = float(shopper.get("lifetime_value", 20000))
        seg = shopper.get("segment_name", "Champion")
        days_inactive = int(shopper.get("last_purchase_days", 90))

        # Answer probability: Champions answer more, Lost Champions slightly less
        answer_prob = 0.72 if seg == "Champion" else 0.58
        complete_prob = 0.85   # Of answered calls, % that complete
        interest_prob = 0.35   # Of completed, % that show interest
        purchase_prob = 0.18   # Of interested, % that purchase

        rand_val = rng.random()
        call_time = base_time + timedelta(minutes=i * 2 + rng.randint(0, 4))

        timeline = [
            {"event": "Call Initiated",  "time": (call_time).strftime("%I:%M %p"),           "icon": "📞"},
            {"event": "Ringing",         "time": (call_time + timedelta(seconds=2)).strftime("%I:%M %p"), "icon": "🔔"},
        ]

        if rand_val < answer_prob:
            total_answered += 1
            timeline.append({"event": "Answered",    "time": (call_time + timedelta(seconds=5)).strftime("%I:%M %p"),  "icon": "✅"})

            if rng.random() < complete_prob:
                total_completed += 1
                duration = rng.randint(22, 42)
                timeline.append({"event": "Voice Played",    "time": (call_time + timedelta(seconds=8)).strftime("%I:%M %p"),            "icon": "🔊"})
                timeline.append({"event": "Call Completed",  "time": (call_time + timedelta(seconds=8+duration)).strftime("%I:%M %p"),   "icon": "📋"})

                if rng.random() < interest_prob:
                    total_interested += 1
                    total_promo_sent += 1
                    sms_time = call_time + timedelta(seconds=8 + duration + 30)
                    timeline.append({"event": f"Promo Code Sent via SMS ({promo_code})", "time": sms_time.strftime("%I:%M %p"), "icon": "💌"})

                    if rng.random() < purchase_prob:
                        total_purchases += 1
                        avg_order = ltv / max(1, shopper.get("total_orders", 5))
                        revenue = round(avg_order * rng.uniform(0.8, 1.3), 2)
                        total_revenue += revenue
                        purchase_time = call_time + timedelta(hours=rng.randint(1, 8))
                        timeline.append({"event": "Purchase Completed", "time": purchase_time.strftime("%I:%M %p"), "icon": "🛍️"})
                        timeline.append({"event": f"Revenue Attributed: ₹{revenue:,.0f}", "time": purchase_time.strftime("%I:%M %p"), "icon": "💰"})

                        events.append(SimulatedCallEvent(
                            shopper_name=shopper.get("name", "Customer"),
                            customer_id=shopper.get("customer_id", str(uuid.uuid4())),
                            city=shopper.get("city", "Chennai"),
                            segment=seg,
                            ltv=ltv,
                            call_status="completed",
                            duration_sec=duration,
                            promo_sent=True,
                            purchase_attributed=True,
                            attributed_revenue=revenue,
                            timeline=timeline
                        ))
                        continue

                events.append(SimulatedCallEvent(
                    shopper_name=shopper.get("name", "Customer"),
                    customer_id=shopper.get("customer_id", str(uuid.uuid4())),
                    city=shopper.get("city", "Chennai"),
                    segment=seg,
                    ltv=ltv,
                    call_status="completed",
                    duration_sec=duration,
                    promo_sent=total_promo_sent > 0,
                    purchase_attributed=False,
                    attributed_revenue=None,
                    timeline=timeline
                ))
            else:
                total_dropped += 1
                timeline.append({"event": "Call Dropped", "time": (call_time + timedelta(seconds=8)).strftime("%I:%M %p"), "icon": "❌"})
                events.append(SimulatedCallEvent(
                    shopper_name=shopper.get("name", "Customer"),
                    customer_id=shopper.get("customer_id", str(uuid.uuid4())),
                    city=shopper.get("city", "Chennai"),
                    segment=seg,
                    ltv=ltv,
                    call_status="dropped",
                    promo_sent=False,
                    purchase_attributed=False,
                    timeline=timeline
                ))
        else:
            total_no_answer += 1
            timeline.append({"event": "No Answer", "time": (call_time + timedelta(seconds=30)).strftime("%I:%M %p"), "icon": "📵"})
            events.append(SimulatedCallEvent(
                shopper_name=shopper.get("name", "Customer"),
                customer_id=shopper.get("customer_id", str(uuid.uuid4())),
                city=shopper.get("city", "Chennai"),
                segment=seg,
                ltv=ltv,
                call_status="no_answer",
                promo_sent=False,
                purchase_attributed=False,
                timeline=timeline
            ))

    n = len(shoppers[:200])
    duration_avg = 30
    estimated_cost = round(n * duration_avg * ELEVENLABS_COST_PER_SECOND_INR, 2)
    roi = round(total_revenue / max(estimated_cost, 1), 2)

    return VoiceSimulationResponse(
        campaign_id=campaign_id,
        total_calls_initiated=n,
        calls_answered=total_answered,
        calls_completed=total_completed,
        calls_no_answer=total_no_answer,
        calls_dropped=total_dropped,
        interested_customers=total_interested,
        promo_sent=total_promo_sent,
        attributed_purchases=total_purchases,
        total_revenue_generated=round(total_revenue, 2),
        estimated_roi=roi,
        estimated_cost_inr=estimated_cost,
        shopper_events=events
    )
