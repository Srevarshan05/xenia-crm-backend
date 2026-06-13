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
from uuid import UUID
import io
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.services.xenia_ai import XeniaAIService
from app.config import settings
from app.models.campaign import Campaign, CampaignMetrics, CampaignSimulation
from app.models.promotion import Promotion
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

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
            opening = f"வணக்கம்! நான் {brand} பிராண்டில் இருந்து பேசுகிறேன். எங்களின் வி.ஐ.பி வாடிக்கையாளரான உங்களை தொடர்பு கொள்வதில் மிக்க மகிழ்ச்சி."
            main_offer = f"உங்களின் ஆதரவிற்கு நன்றி செலுத்தும் வகையில், எங்களின் புதிய {category}-க்கு விளம்பர குறியீடு {promo}-ஐ பயன்படுத்தி {discount:.0f}% சிறப்பு தள்ளுபடி வழங்குகிறோம்."
            cta = f"உடனே எங்களின் மொபைல் செயலியைப் பயன்படுத்தி, செக்அவுட்டில் {promo} என்ற விளம்பர குறியீட்டைப் போடுங்கள்."
            closing = "எங்கள் மீது வைத்துள்ள நம்பிக்கைக்கு நன்றி, வணக்கம்."
        else:
            objective = "Win back high-value Tamil customers"
            opening = f"வணக்கம்! நான் {brand} பிராண்டில் இருந்து பேசுகிறேன். உங்களை போன்ற ஒரு சிறந்த வாடிக்கையாளரை நாங்கள் மிகவும் இழக்கிறோம்."
            main_offer = f"உங்களை மீண்டும் வரவேற்கும் முகமாக, {category}-க்கு விளம்பர குறியீடு {promo}-ஐ பயன்படுத்தி {discount:.0f}% தள்ளுபடி தருகிறோம்."
            cta = f"இன்றே எங்களின் மொபைல் செயலியைத் திறந்து, ஆர்டர் செய்யும்போது {promo} குறியீட்டைப் பயன்படுத்துங்கள்."
            closing = "நன்றி, மீண்டும் வாருங்கள்!"
        full_script = f"{opening} {main_offer} {cta} {closing}"

    elif lang == "Hindi":
        if seg == "Champion":
            objective = "Reward loyal Hindi VIP customers"
            opening = f"नमस्ते! मैं {brand} से बात कर रहा हूँ। हमारे सबसे खास वी.आई.पी ग्राहक होने के नाते, आज आपसे संपर्क करके हमें बेहद खुशी हो रही है।"
            main_offer = f"हमारे साथ जुड़े रहने के लिए धन्यवाद देने के लिए, हम आपको {category} पर प्रोमो कोड {promo} का उपयोग करके {discount:.0f}% की विशेष छूट दे रहे हैं।"
            cta = f"कृपया अभी हमारे मोबाइल ऐप पर जाएं और ऑर्डर करते समय {promo} कोड का उपयोग करें।"
            closing = "हमारे साथ जुड़े रहने के लिए धन्यवाद, नमस्ते।"
        else:
            objective = "Win back high-value Hindi customers"
            opening = f"नमस्ते! मैं {brand} से बात कर रहा हूँ। हम आपको बहुत याद कर रहे हैं और आशा करते हैं कि आप स्वस्थ होंगे।"
            main_offer = f"स्वागत उपहार के रूप में, आपको प्रोमो कोड {promo} का उपयोग करके {category} पर {discount:.0f}% की छूट मिल रही है।"
            cta = f"आज ही हमारी मोबाइल ऐप खोलें, अपने पसंदीदा उत्पाद चुनें और {promo} कोड का उपयोग करके ऑर्डर करें।"
            closing = "धन्यवाद, आपका दिन शुभ हो।"
        full_script = f"{opening} {main_offer} {cta} {closing}"

    elif lang == "English + Tamil":
        if seg == "Champion":
            objective = "Reward loyal VIP customers in Tanglish"
            opening = f"Hello! Naanga {brand}-la irundhu call panrom. Namma active and loyal VIP customer-a irukkuradhuku ungaluku namma nandri."
            main_offer = f"Ungaloda support-a celebrate panna, ungaluku pidicha {category}-la {discount:.0f}% special discount tharrom. Adhuku promo code {promo} use pannunga."
            cta = f"Checkout la promo code {promo} apply panni order pannunga."
            closing = "Thanks for shopping with us. Nandri!"
        else:
            objective = "Win back high-value customers in Tanglish"
            opening = f"Hello! Naanga {brand}-la irundhu call panrom. We really missed you and romba naala ungaluku call பண்ண முடியல."
            main_offer = f"Ungala welcome back panna, oru special gift-a ungaluku pidicha {category}-la {discount:.0f}% discount tharrom. Namma promo code {promo}-ஐ use pannunga."
            cta = f"Namma app open panni, {promo} code use panni order pannunga."
            closing = "Thank you so much. Nandri!"
        full_script = f"{opening} {main_offer} {cta} {closing}"

    elif lang == "English + Hindi":
        if seg == "Champion":
            objective = "Reward loyal VIP customers in Hinglish"
            opening = f"Hello! Hum {brand} se baat kar rahe hain. Aap hamare loyal VIP customer hain aur aapka support hamare liye bahut special hai."
            main_offer = f"Aapki shopping ko aur behtar banane ke liye, hum aapko {category} par {discount:.0f}% ki special discount de rahe hain. Iske liye aap promo code {promo} use kar sakte hain."
            cta = f"Bas app par jaake checkout ke waqt promo code {promo} apply karein."
            closing = "Humare saath bane rehne ke liye dhanyavaad!"
        else:
            objective = "Win back high-value customers in Hinglish"
            opening = f"Hello! Hum {brand} se baat kar rahe hain. Hum aapko bahut miss kar rahe hain aur aasha karte hain ki aap thik honge."
            main_offer = f"Aapke liye special welcome back gift hai, {category} par {discount:.0f}% discount promo code {promo} use karke."
            cta = f"Aaj hi hamari app par jaakar promo code {promo} use karke order karein."
            closing = "Thank you and dhanyavaad!"
        full_script = f"{opening} {main_offer} {cta} {closing}"

    else:
        if seg == "Champion":
            objective = f"Reward loyal {brand} shoppers with an exclusive VIP offer"
            opening = f"Hello! This is {brand} calling. As one of our most valued VIP customers, we want to personally thank you for your loyalty."
            main_offer = f"To celebrate our relationship, we are offering you a special {discount:.0f}% discount on {category} using the promo code {promo}."
            cta = f"Visit our mobile app and apply the code {promo} at checkout."
            closing = "Thank you for being a valued customer!"
        else:
            objective = f"Win back high-value {brand} customers with a personalized incentive"
            opening = f"Hello! This is {brand} calling. We have missed you lately and wanted to reach out to welcome you back to our community."
            main_offer = f"As a welcome-back gift, we are offering you a special {discount:.0f}% discount on {category} using the promo code {promo}."
            cta = f"Visit our app and apply {promo} during checkout."
            closing = "Thank you for choosing us, and we hope to see you shopping soon."
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
        f"Write an engaging, natural voice call advertisement script optimized for ElevenLabs Text-to-Speech. "
        f"AUDIENCE: {payload.audience_segment} customers, avg LTV Rs {payload.avg_ltv:,.0f}, "
        f"avg inactivity {payload.avg_inactivity_days:.0f} days, "
        f"top category: {payload.top_category or 'general retail'}. "
        f"GOAL: {payload.campaign_goal}. "
        f"PROMOTION: {discount_str if discount_str else 'exclusive offer'}. "
        f"TONE: {tone_guidance}. LANGUAGE: {payload.language}. {lang_constraints} "
        f"REQUIREMENTS: The script MUST be exactly between 45 and 65 words (this corresponds to exactly 3-4 lines of text in the user interface, or 20-25 seconds of speech). "
        f"The full script MUST be between 45 and 65 words, natural, and friendly. No aggressive sales language. "
        f"One offer, one clear call to action. Keep brand name like '{payload.brand_name}' and promo code '{payload.promo_code}' in English/Latin script, but EVERYTHING ELSE MUST BE STRICTLY TRANSLATED AND WRITTEN IN THE SELECTED LANGUAGE ({payload.language}). "
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


class VoiceCampaignSaveRequest(BaseModel):
    name: str
    objective: str
    target_segment: str
    target_audience_size: int
    voice_tone: str
    voice_model_name: str
    promo_code: Optional[str] = None
    script_text: str
    sim_data: dict


@router.post("/campaigns", response_model=dict)
def save_voice_campaign(payload: VoiceCampaignSaveRequest, db: Session = Depends(get_db)):
    """
    POST /api/voice/campaigns
    Saves a completed Voice campaign to the PostgreSQL database.
    """
    try:
        # Find promotion if code is provided
        promotion_id = None
        if payload.promo_code:
            promo = db.query(Promotion).filter(Promotion.promo_code == payload.promo_code).first()
            if promo:
                promotion_id = promo.promotion_id
                
        # Create Campaign
        campaign = Campaign(
            name=payload.name,
            objective=payload.objective,
            promotion_id=promotion_id,
            channel="Voice Call",
            status="completed",
            message_template=payload.script_text,
            target_segment=payload.target_segment,
            target_audience_size=payload.target_audience_size,
            launched_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc)
        )
        db.add(campaign)
        db.flush() # get campaign ID
        
        # Save metrics
        sim = payload.sim_data
        metrics = CampaignMetrics(
            campaign_id=campaign.campaign_id,
            total_sent=sim.get("total_calls_initiated", 0),
            total_delivered=sim.get("calls_answered", 0),
            total_opened=sim.get("calls_completed", 0),
            total_clicked=sim.get("interested_customers", 0),
            total_promo_applied=sim.get("promo_sent", 0),
            total_purchased=sim.get("attributed_purchases", 0),
            attributed_revenue=sim.get("total_revenue_generated", 0.0),
            estimated_cost=sim.get("estimated_cost_inr", 0.0),
            roi=sim.get("estimated_roi", 0.0) * 100, # ROI is percentage
            conversion_rate=sim.get("attributed_purchases", 0) / max(1, sim.get("total_calls_initiated", 1))
        )
        db.add(metrics)
        
        # Save voice-specific info inside CampaignSimulation simulation_context
        # E.g. voice_model, voice_tone, and full shopper_events list
        sim_context = {
            "voice_model": payload.voice_model_name,
            "voice_tone": payload.voice_tone,
            "shopper_events": sim.get("shopper_events", [])
        }
        
        simulation = CampaignSimulation(
            campaign_id=campaign.campaign_id,
            predicted_reach=payload.target_audience_size,
            predicted_ctr=sim.get("calls_completed", 0) / max(1, sim.get("total_calls_initiated", 1)),
            predicted_cvr=sim.get("attributed_purchases", 0) / max(1, sim.get("total_calls_initiated", 1)),
            predicted_revenue=sim.get("total_revenue_generated", 0.0),
            confidence_score=0.95,
            simulation_context=sim_context,
            why_channel=payload.voice_model_name,
            why_promotion=payload.promo_code or "None",
            why_audience=payload.target_segment,
            ai_narrative=payload.voice_tone
        )
        db.add(simulation)
        
        db.commit()
        return {"campaign_id": str(campaign.campaign_id), "status": "success"}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save voice campaign: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save voice campaign: {str(e)}")


@router.get("/history", response_model=List[dict])
def get_voice_campaigns_history(db: Session = Depends(get_db)):
    """
    GET /api/voice/history
    List all completed voice campaigns.
    """
    campaigns = db.query(Campaign).filter(
        Campaign.channel == "Voice Call",
        Campaign.status == "completed"
    ).order_by(Campaign.created_at.desc()).all()
    
    res = []
    for c in campaigns:
        metrics_dict = {}
        if c.metrics:
            metrics_dict = {
                "total_sent": c.metrics.total_sent,
                "total_delivered": c.metrics.total_delivered,
                "total_opened": c.metrics.total_opened,
                "total_clicked": c.metrics.total_clicked,
                "total_promo_applied": c.metrics.total_promo_applied,
                "total_purchased": c.metrics.total_purchased,
                "attributed_revenue": float(c.metrics.attributed_revenue),
                "estimated_cost": float(c.metrics.estimated_cost),
                "roi": c.metrics.roi,
                "conversion_rate": c.metrics.conversion_rate
            }
            
        sim_context = {}
        if c.simulation and c.simulation.simulation_context:
            sim_context = c.simulation.simulation_context
            
        res.append({
            "campaign_id": str(c.campaign_id),
            "name": c.name,
            "objective": c.objective,
            "target_segment": c.target_segment,
            "target_audience_size": c.target_audience_size,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "completed_at": c.completed_at.isoformat() if c.completed_at else None,
            "message_template": c.message_template,
            "promotion_code": c.promotion.promo_code if c.promotion else None,
            "voice_model_name": c.simulation.why_channel if c.simulation else "Custom Voice",
            "voice_tone": c.simulation.ai_narrative if c.simulation else "Professional",
            "metrics": metrics_dict,
            "simulation_context": sim_context
        })
    return res


def generate_voice_executive_summary(campaign, metrics, sim_context):
    if not metrics:
        return "This voice campaign has not been launched yet. No performance metrics are available to summarize."
    
    sent = metrics.total_sent or 0
    answered = metrics.total_delivered or 0
    completed = metrics.total_opened or 0
    interested = metrics.total_clicked or 0
    purchases = metrics.total_purchased or 0
    revenue = float(metrics.attributed_revenue or 0)
    cost = float(metrics.estimated_cost or 0)
    roi = float(metrics.roi or 0)
    
    voice_model = sim_context.get("voice_model", "Xenia Voice")
    voice_tone = sim_context.get("voice_tone", "Professional")
    promo_code = campaign.promotion.promo_code if campaign.promotion else "None"
    
    summary = (
        f"Outbound AI Voice campaign '{campaign.name}' was executed targeting {sent} Champion and Lost Champion shoppers. "
        f"Calls were synthesized using the ElevenLabs '{voice_model}' profile with a {voice_tone.lower()} tone. "
    )
    
    if answered > 0:
        answer_pct = answered / max(1, sent) * 100
        interest_pct = interested / max(1, completed) * 100
        summary += (
            f"The outbound dialer successfully connected with {answered} shoppers ({answer_pct:.1f}% answer rate), with {completed} calls completing full audio play. "
            f"Following the voice pitch, {interested} customers showed purchase interest and were sent SMS promotions containing '{promo_code}' ({interest_pct:.1f}% positive response rate). "
        )
    else:
        summary += "No calls were successfully answered during the simulation."
        
    if purchases > 0:
        summary += (
            f"This campaign successfully generated INR {revenue:,.2f} in attributed revenue from {purchases} conversions. "
            f"Against a voice synthesis cost of INR {cost:,.2f}, the campaign returned a healthy ROI of {roi:.1f}%."
        )
    
    return summary


def build_voice_pdf_report(campaign, metrics, simulation, filename_or_stream):
    c = canvas.Canvas(filename_or_stream, pagesize=letter)
    width, height = letter # 612 x 792
    
    primary_color = colors.HexColor("#0f172a") # Navy Dark Slate
    accent_color = colors.HexColor("#7c3aed") # Purple
    text_color = colors.HexColor("#334155") # Gray
    light_bg = colors.HexColor("#f8fafc") # Slate Light
    border_color = colors.HexColor("#e2e8f0") # Border gray
    
    # Header banner
    c.setFillColor(primary_color)
    c.rect(0, 720, 612, 72, fill=True, stroke=False)
    
    # Header Title
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(36, 750, "XENIA CRM — VOICE OUTBOUND PERFORMANCE REPORT")
    c.setFont("Helvetica", 9)
    c.drawString(36, 735, "OUTBOUND AI DIALER LOG & ELEVENLABS AUDIO SUMMARY")
    c.drawRightString(576, 745, f"Date: {datetime.now().strftime('%b %d, %Y')}")
    
    # Section 1: Campaign Metadata
    c.setFillColor(primary_color)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(36, 685, "CAMPAIGN OVERVIEW")
    c.setStrokeColor(border_color)
    c.setLineWidth(1)
    c.line(36, 678, 576, 678)
    
    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(36, 655, "Campaign Name:")
    c.drawString(36, 635, "Goal/Objective:")
    c.drawString(36, 600, "Audience Cohort:")
    c.drawString(36, 580, "Outbound Script:")
    
    c.setFont("Helvetica", 9)
    c.drawString(140, 655, campaign.name or "N/A")
    obj_text = campaign.objective or "N/A"
    if len(obj_text) > 80:
        c.drawString(140, 635, obj_text[:80] + "...")
    else:
        c.drawString(140, 635, obj_text)
    c.drawString(140, 600, campaign.target_segment or "VIP Segment")
    script_snippet = campaign.message_template or "N/A"
    if len(script_snippet) > 85:
        c.drawString(140, 580, f'"{script_snippet[:85]}..."')
    else:
        c.drawString(140, 580, f'"{script_snippet}"')
        
    c.setFont("Helvetica-Bold", 9)
    c.drawString(340, 655, "ElevenLabs Voice:")
    c.drawString(340, 635, "Voice Tone Guidance:")
    c.drawString(340, 600, "Total Targets:")
    c.drawString(340, 580, "Campaign Status:")
    
    c.setFont("Helvetica", 9)
    sim_context = simulation.simulation_context if simulation else {}
    voice_model = sim_context.get("voice_model", "Xenia Signature Voice")
    voice_tone = sim_context.get("voice_tone", "Professional")
    c.drawString(440, 655, voice_model)
    c.drawString(440, 635, voice_tone)
    c.drawString(440, 600, str(campaign.target_audience_size or 0))
    status_str = (campaign.status or "completed").upper()
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(accent_color)
    c.drawString(440, 580, status_str)
    
    # Section 2: Outbound Call Funnel Metrics
    c.setFillColor(primary_color)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(36, 545, "CALL ENGAGEMENT FUNNEL")
    c.line(36, 538, 576, 538)
    
    c.setFillColor(light_bg)
    c.rect(36, 435, 540, 90, fill=True, stroke=True)
    c.setStrokeColor(border_color)
    
    c.line(126, 435, 126, 525)
    c.line(216, 435, 216, 525)
    c.line(306, 435, 306, 525)
    c.line(396, 435, 396, 525)
    c.line(486, 435, 486, 525)
    
    c.setFillColor(primary_color)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(81, 510, "DIALED")
    c.drawCentredString(171, 510, "ANSWERED")
    c.drawCentredString(261, 510, "COMPLETED")
    c.drawCentredString(351, 510, "INTERESTED")
    c.drawCentredString(441, 510, "SMS SENT")
    c.drawCentredString(531, 510, "PURCHASES")
    
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(text_color)
    sent_val = metrics.total_sent if metrics else 0
    deliv_val = metrics.total_delivered if metrics else 0
    open_val = metrics.total_opened if metrics else 0
    click_val = metrics.total_clicked if metrics else 0
    promo_val = metrics.total_promo_applied if metrics else 0
    purch_val = metrics.total_purchased if metrics else 0
    
    c.drawCentredString(81, 470, str(sent_val))
    c.drawCentredString(171, 470, str(deliv_val))
    c.drawCentredString(261, 470, str(open_val))
    c.drawCentredString(351, 470, str(click_val))
    c.drawCentredString(441, 470, str(promo_val))
    c.drawCentredString(531, 470, str(purch_val))
    
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawCentredString(81, 450, "100.0%")
    c.drawCentredString(171, 450, f"{(deliv_val/max(1, sent_val)*100):.1f}%")
    c.drawCentredString(261, 450, f"{(open_val/max(1, sent_val)*100):.1f}%")
    c.drawCentredString(351, 450, f"{(click_val/max(1, open_val)*100):.1f}%")
    c.drawCentredString(441, 450, f"{(promo_val/max(1, sent_val)*100):.1f}%")
    c.drawCentredString(531, 450, f"{(purch_val/max(1, sent_val)*100):.1f}%")
    
    # Section 3: Financial Performance
    c.setFillColor(primary_color)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(36, 400, "REVENUE & VOICE SYNTHESIS ROI")
    c.line(36, 393, 576, 393)
    
    revenue_val = float(metrics.attributed_revenue or 0) if metrics else 0.0
    cost_val = float(metrics.estimated_cost or 0) if metrics else 0.0
    roi = float(metrics.roi or 0) if metrics else 0.0
    
    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(36, 370, "Total Attributed Revenue:")
    c.drawString(36, 350, "Voice Synthesis & Telecom Cost:")
    c.drawString(36, 330, "Call Conversion Rate:")
    c.drawString(36, 310, "Voice Campaign ROI:")
    
    c.setFont("Helvetica-Bold", 9)
    c.drawString(240, 370, f"INR {revenue_val:,.2f}")
    c.drawString(240, 350, f"INR {cost_val:,.2f}")
    conv_rate = purch_val / max(1, sent_val) * 100
    c.drawString(240, 330, f"{conv_rate:.2f}%")
    c.setFillColor(colors.HexColor("#16a34a") if roi >= 0 else colors.HexColor("#dc2626"))
    c.drawString(240, 310, f"{roi:.2f}%")
    
    # Section 4: Promotion Claim & Incentive Details
    c.setFillColor(primary_color)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(36, 275, "INCENTIVE CAMPAIGN DETAILED LOG")
    c.line(36, 268, 576, 268)
    
    promo_code = campaign.promotion.promo_code if campaign.promotion else "None"
    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(36, 245, "Promo Code Dispatched:")
    c.drawString(36, 225, "SMS Offers Dispatched:")
    c.drawString(36, 205, "Promo Redemption Count:")
    
    c.setFont("Helvetica-Bold", 9)
    c.drawString(200, 245, promo_code)
    c.setFont("Helvetica", 9)
    c.drawString(200, 225, str(promo_val))
    c.drawString(200, 205, str(purch_val))
    
    # Section 5: Plain-English Executive Summary
    c.setFillColor(primary_color)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(36, 170, "EXECUTIVE OUTCOME SUMMARY")
    c.line(36, 163, 576, 163)
    
    summary_text = generate_voice_executive_summary(campaign, metrics, sim_context)
    c.setFillColor(light_bg)
    c.rect(36, 60, 540, 85, fill=True, stroke=True)
    
    c.setFillColor(text_color)
    c.setFont("Helvetica", 9)
    lines = []
    words = summary_text.split(" ")
    curr_line = ""
    for w in words:
        if len(curr_line + " " + w) > 95:
            lines.append(curr_line)
            curr_line = w
        else:
            curr_line = (curr_line + " " + w).strip()
    if curr_line:
        lines.append(curr_line)
        
    y_pos = 130
    for line in lines[:5]:
        c.drawString(46, y_pos, line)
        y_pos -= 14
        
    # Footer
    c.setStrokeColor(border_color)
    c.line(36, 40, 576, 40)
    c.setFillColor(colors.HexColor("#94a3b8"))
    c.setFont("Helvetica", 8)
    c.drawString(36, 26, "Xenia CRM Platform © 2026. Generated Automatically.")
    c.drawRightString(576, 26, "Page 1 of 1")
    
    c.showPage()
    c.save()


@router.get("/campaigns/{campaign_id}/report")
def export_voice_report(campaign_id: UUID, db: Session = Depends(get_db)):
    """
    GET /api/voice/campaigns/{campaign_id}/report
    Generates and downloads a premium PDF performance report for a voice campaign.
    """
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    metrics = campaign.metrics
    simulation = campaign.simulation
    
    buffer = io.BytesIO()
    build_voice_pdf_report(campaign, metrics, simulation, buffer)
    buffer.seek(0)
    
    sanitized_name = "".join(x for x in campaign.name if x.isalnum() or x in " -_").strip()
    filename = f"voice_campaign_report_{sanitized_name or 'export'}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
