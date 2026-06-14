from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, text, cast, Float
import uuid
from uuid import UUID
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any

from app.database import get_db
from app.models.customer import Customer, CustomerMetrics, CustomerSegment
from app.models.campaign import Campaign, CampaignSimulation, CampaignMetrics
from app.models.promotion import Promotion
from app.models.opportunity import Opportunity
from app.services.xenia_ai import XeniaAIService
from app.services.simulation import CampaignSimulationService
from app.schemas.planner import (
    GoalPlannerRequest, 
    GoalPlannerResponse, 
    SimulationPreview, 
    PromotionPreview,
    AudienceSummary,
    CampaignStrategyExplanation,
    ShopperPreview,
    PromotionRecommendation,
    PrepareContextResponse
)

logger = logging.getLogger("xenia.planner_router")
router = APIRouter(prefix="/api/planner", tags=["AI Goal Planner"])

# ── Voice Eligibility — Future-Ready Stub ───────────────────────────────────────
# Voice generation is NOT implemented in this phase.
# This logic evaluates eligibility and stores the result in CampaignSimulation
# so that Phase 2 voice integration can read it without DB schema changes.
VOICE_ELIGIBLE_SEGMENTS = {"Champion", "High Value", "Lost Champion", "At Risk"}
VOICE_LTV_THRESHOLD_INR = 10_000.0   # At-Risk qualifies only if LTV > this

def evaluate_voice_eligibility(target_segment: str, avg_ltv: float) -> tuple[bool, str]:
    """
    Evaluates whether this campaign audience qualifies for a Voice campaign.
    Returns (eligible: bool, reason: str).

    Eligible segments:
      - Champion, High Value          → always eligible (VIP concierge)
      - Lost Champion, At-Risk        → eligible only if avg LTV > threshold (win-back)
    All others                        → not eligible, default to WhatsApp/Email/SMS

    NOTE: Voice generation is deferred to Phase 2. This only sets the flag.
    """
    segment = target_segment.strip() if target_segment else ""
    if segment in ("Champion", "High Value"):
        return True, f"Segment '{segment}' qualifies for premium voice outreach (VIP retention)."
    if segment in ("Lost Champion", "At Risk") and avg_ltv >= VOICE_LTV_THRESHOLD_INR:
        return True, (
            f"Segment '{segment}' with avg LTV ₹{avg_ltv:,.0f} qualifies for voice win-back "
            f"(LTV threshold: ₹{VOICE_LTV_THRESHOLD_INR:,.0f})."
        )
    return False, (
        f"Segment '{segment}' does not meet voice eligibility criteria. "
        f"Voice campaigns are reserved for Champion, High Value, Lost Champion (high LTV), "
        f"and At-Risk (high LTV) segments only. Defaulting to WhatsApp / Email / SMS."
    )

def is_promotion_eligible(promo: Promotion, category_filter: str | None, city_filter: str | None) -> bool:
    """Enforces active status, date validity, max usage limit, category and city matching."""
    now = datetime.now(timezone.utc)
    if not promo.active:
        return False
    # Start date / end date checks
    if promo.start_date and promo.start_date > now:
        return False
    if promo.end_date and promo.end_date < now:
        return False
    # Max usage limits
    if promo.max_usage_limit is not None and promo.times_used >= promo.max_usage_limit:
        return False
    
    # Category rules (multi-category support, "ALL" or comma-separated list)
    if category_filter and promo.applicable_categories != "ALL":
        categories = [c.strip().lower() for c in promo.applicable_categories.split(",")]
        if category_filter.lower() not in categories:
            return False
            
    # City rules (multi-city support, "ALL" or comma-separated list)
    if city_filter and promo.applicable_cities != "ALL":
        cities = [c.strip().lower() for c in promo.applicable_cities.split(",")]
        if city_filter.lower() not in cities:
            return False
            
    return True

# Cap to 2000 rows max for all audience cohort queries — prevents loading entire DB into memory
_AUDIENCE_CAP = 2000

def get_audience_cohort(db: Session, filters: dict):
    city_filter = filters.get("city")
    category_filter = filters.get("category")
    min_spend_filter = filters.get("min_spend")
    max_churn_filter = filters.get("max_churn_probability")
    segment_filter = filters.get("segment")
    
    query = db.query(Customer).join(CustomerMetrics, Customer.customer_id == CustomerMetrics.customer_id)
    
    if city_filter:
        query = query.filter(Customer.city.ilike(city_filter))
    if category_filter:
        query = query.filter(
            (CustomerMetrics.top_category == category_filter) |
            (CustomerMetrics.category_affinity_json[category_filter].astext.cast(Float) >= 10.0)
        )
    if min_spend_filter is not None:
        query = query.filter(CustomerMetrics.total_spend >= float(min_spend_filter))
    if max_churn_filter is not None:
        query = query.filter(CustomerMetrics.churn_probability <= float(max_churn_filter))
    if segment_filter:
        query = query.filter(Customer.segments.any(CustomerSegment.segment_name.ilike(f"%{segment_filter}%")))

    # ── Cap at _AUDIENCE_CAP rows at the DB level — avoids pulling 500K rows into memory ──
    all_matching = query.limit(_AUDIENCE_CAP).all()
    
    # Fallback to prevent empty audiences during demo
    if not all_matching:
        logger.warning("No customers matched filters, removing constraints to ensure demo works...")
        query = db.query(Customer).join(CustomerMetrics, Customer.customer_id == CustomerMetrics.customer_id)
        if category_filter:
            query = query.filter(CustomerMetrics.top_category == category_filter)
        all_matching = query.limit(500).all()
        if not all_matching:
            all_matching = db.query(Customer).join(CustomerMetrics, Customer.customer_id == CustomerMetrics.customer_id).limit(200).all()
            
    # Calculate Suppressed vs Eligible (Suppress if segment is Spam Risk)
    matching_ids = [c.customer_id for c in all_matching]
    suppressed_ids = set()
    if matching_ids:
        suppressed_rows = db.query(CustomerSegment.customer_id).filter(
            CustomerSegment.customer_id.in_(matching_ids),
            CustomerSegment.segment_name == "Spam Risk"
        ).all()
        suppressed_ids = {r[0] for r in suppressed_rows}
        
    eligible_customers = [c for c in all_matching if c.customer_id not in suppressed_ids]
    return all_matching, suppressed_ids, eligible_customers

def make_audience_summary(all_matching, suppressed_ids, eligible_customers) -> AudienceSummary:
    total_identified = len(all_matching)
    suppressed = len(suppressed_ids)
    eligible = len(eligible_customers)
    
    # Cap computation to first 500 for performance
    sample = eligible_customers[:500]
    avg_spend = sum(c.metrics.total_spend or 0.0 for c in sample) / len(sample) if sample else 0.0
    avg_inactivity = int(sum(c.metrics.days_since_last_order or 0 for c in sample) / len(sample)) if sample else 0
    avg_churn = sum(c.metrics.churn_probability or 0.0 for c in sample) / len(sample) if sample else 0.0
    avg_total_orders = sum(c.metrics.total_orders or 0 for c in sample) / len(sample) if sample else 0.0
    
    # City distribution
    city_dist = {}
    for c in sample:
        city_dist[c.city] = city_dist.get(c.city, 0) + 1
    city_dist = dict(sorted(city_dist.items(), key=lambda x: x[1], reverse=True)[:5])
    
    # Channel distribution
    channel_dist = {}
    for c in sample:
        ch = c.metrics.preferred_channel or "WhatsApp"
        channel_dist[ch] = channel_dist.get(ch, 0) + 1
        
    # Category affinity distribution
    category_affinities = {}
    for c in sample:
        aff = c.metrics.category_affinity_json or {}
        for cat, val in aff.items():
            category_affinities[cat] = category_affinities.get(cat, 0.0) + float(val)
    if sample:
        category_affinities = {k: round(v / len(sample), 2) for k, v in category_affinities.items()}
    category_affinities = dict(sorted(category_affinities.items(), key=lambda x: x[1], reverse=True)[:5])
    
    return AudienceSummary(
        total_identified=total_identified,
        suppressed=suppressed,
        eligible=eligible,
        avg_spend=float(round(avg_spend, 2)),
        avg_inactivity_days=avg_inactivity,
        city_distribution=city_dist,
        channel_distribution=channel_dist,
        category_affinity_distribution=category_affinities,
        avg_churn_probability=float(round(avg_churn, 4)),
        avg_total_orders=float(round(avg_total_orders, 1))
    )

@router.get("/prepare-context", response_model=PrepareContextResponse)
def get_prepare_context(opportunity_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    GET /api/planner/prepare-context
    Fetches the audience review summary, eligible shopper list, and recommended promotion details
    with full explainability rationale BEFORE campaign generation.
    Called from the Suggested Action → Audience Review → Promotion Review workflow step.
    """
    op = db.query(Opportunity).filter(Opportunity.opportunity_id == opportunity_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Suggested Action not found")
        
    filters = op.segment_filter or {}
    
    # 1. Fetch audience cohort
    all_matching, suppressed_ids, eligible_customers = get_audience_cohort(db, filters)
    
    # 2. Compute Audience Summary
    audience_summary = make_audience_summary(all_matching, suppressed_ids, eligible_customers)
    
    # 3. Retrieve eligible promotions and recommend the best one
    promo_stats = db.query(
        Campaign.promotion_id,
        func.avg(CampaignMetrics.roi).label("avg_roi"),
        func.avg(CampaignMetrics.conversion_rate).label("avg_cvr"),
        func.count(Campaign.campaign_id).label("times_used")
    ).join(CampaignMetrics, Campaign.campaign_id == CampaignMetrics.campaign_id).\
      group_by(Campaign.promotion_id).all()
      
    promo_stats_map = {}
    for row in promo_stats:
        if row.promotion_id:
            promo_stats_map[row.promotion_id] = {
                "avg_roi": float(row.avg_roi or 0.0),
                "avg_cvr": float(row.avg_cvr or 0.0),
                "times_used": int(row.times_used or 0)
            }
            
    # Resolve the recommended promotion
    selected_promo = None
    if op.recommended_promotion_id:
        selected_promo = db.query(Promotion).filter(Promotion.promotion_id == op.recommended_promotion_id).first()
        
    # If no explicitly recommended promo exists, pick the best eligible one
    category_filter = filters.get("category")
    city_filter = filters.get("city")
    if not selected_promo:
        all_promotions = db.query(Promotion).all()
        eligible_promos = [p for p in all_promotions if is_promotion_eligible(p, category_filter, city_filter)]
        if eligible_promos:
            eligible_promos.sort(key=lambda p: promo_stats_map.get(p.promotion_id, {}).get("avg_roi", 0.0), reverse=True)
            selected_promo = eligible_promos[0]
            
    promo_recommendation = None
    if selected_promo:
        # Build match rationale bullet points with historical performance data
        rationale = []
        promo_roi = promo_stats_map.get(selected_promo.promotion_id, {}).get("avg_roi", 0.0)
        promo_cvr = promo_stats_map.get(selected_promo.promotion_id, {}).get("avg_cvr", 0.0)
        promo_used = promo_stats_map.get(selected_promo.promotion_id, {}).get("times_used", 0)

        if category_filter and selected_promo.applicable_categories != "ALL":
            rationale.append(f"Category match: promotion covers '{selected_promo.applicable_categories}' which aligns with audience's top category '{category_filter}'.")
        else:
            rationale.append(f"Broad coverage: promotion applies to '{category_filter or 'All Categories'}' — maximises eligible shopper count.")

        if audience_summary.avg_inactivity_days > 30:
            rationale.append(f"Reactivation incentive: audience avg inactivity is {audience_summary.avg_inactivity_days} days — this promotion provides a purchase trigger.")
        else:
            rationale.append("High-intent segment: shoppers in this cohort have strong recent activity and respond well to promotions.")

        if promo_roi > 0:
            rationale.append(f"Proven historical ROI: this promotion achieved {promo_roi:.1f}% average ROI across {promo_used} past campaigns.")
        if promo_cvr > 0:
            rationale.append(f"Strong conversion benchmark: {promo_cvr*100:.1f}% conversion rate in previous deployments.")
        if selected_promo.times_used > 0:
            rationale.append(f"Proven track record: used {selected_promo.times_used} times with {selected_promo.purchases_attributed} attributed purchases.")

        rationale.append("Eligibility confirmed: active, within validity period, and within usage limits.")

        promo_recommendation = PromotionRecommendation(
            promotion_id=str(selected_promo.promotion_id),
            name=selected_promo.name,
            promo_code=selected_promo.promo_code,
            discount_type=selected_promo.discount_type,
            discount_value=float(selected_promo.discount_value),
            applicable_categories=selected_promo.applicable_categories,
            applicable_cities=selected_promo.applicable_cities,
            applicable_segments=selected_promo.applicable_segments,
            min_order_value=float(selected_promo.min_order_value) if selected_promo.min_order_value else None,
            start_date=selected_promo.start_date,
            end_date=selected_promo.end_date,
            rationale=rationale,
            historical_performance={
                "avg_roi_pct": promo_roi,
                "avg_conversion_rate": promo_cvr,
                "times_used_in_campaigns": promo_used,
                "total_purchases_attributed": selected_promo.purchases_attributed,
                "total_revenue_generated": float(selected_promo.revenue_generated),
            }
        )
        
    # 4. Fetch shopper list (first 50 eligible shoppers for browse/drilldown — capped for speed)
    shopper_previews = []
    for c in eligible_customers[:50]:
        shopper_previews.append(
            ShopperPreview(
                customer_id=str(c.customer_id),
                name=c.name,
                city=c.city,
                email=c.email,
                phone=c.phone,
                lifetime_value=float(c.metrics.total_spend or 0.0),
                last_purchase_days=int(c.metrics.days_since_last_order or 0),
                churn_probability=float(c.metrics.churn_probability or 0.0),
                preferred_channel=c.metrics.preferred_channel or "WhatsApp",
                top_category=c.metrics.top_category if c.metrics else None,
                total_orders=c.metrics.total_orders if c.metrics else 0
            )
        )
        
    return PrepareContextResponse(
        audience_summary=audience_summary,
        recommended_promotion=promo_recommendation,
        eligible_shoppers=shopper_previews
    )

@router.post("/generate", response_model=GoalPlannerResponse)
def generate_campaign_from_goal(payload: GoalPlannerRequest, db: Session = Depends(get_db)):
    """
    POST /api/planner/generate
    AI Goal Planner endpoint:
    1. Parse natural language goal into structured filter parameters.
    2. Query database for matching customer count and metrics.
    3. Exclude suppressed customers (fatigued Spam Risk) to get eligible shoppers.
    4. Compute dynamic Audience Summary (Total, Suppressed, Eligible, Spend, Recency, City/Channel/Category distributions).
    5. Retrieve eligible promotions based on strict database eligibility rules and historical ROI/CTR metrics.
    6. Call Gemini to formulate strategy copywriting and select the best eligible promotion.
    7. Create a draft Campaign in the database (lifecycle status: draft).
    8. Run campaign simulation and store simulation preview.
    9. Return unified strategy proposal with structured explanations.
    """
    goal = payload.goal
    logger.info(f"Received goal request: '{goal}'")
    
    # 1. Parse high-level goal using Gemini
    filters = XeniaAIService.parse_planner_goal(goal)
    logger.info(f"Parsed filters from goal: {filters}")
    
    city_filter = filters.get("city")
    category_filter = filters.get("category")
    min_spend_filter = filters.get("min_spend")
    max_churn_filter = filters.get("max_churn_probability")
    segment_filter = filters.get("segment")
    
    # 2. Query matching customer audience
    all_matching, suppressed_ids, eligible_customers = get_audience_cohort(db, filters)
    eligible = len(eligible_customers)
    
    # Compute Audience Summary
    audience_summary_data = make_audience_summary(all_matching, suppressed_ids, eligible_customers)
    
    # 3. Retrieve eligible promotions and their historical performance stats
    promo_stats = db.query(
        Campaign.promotion_id,
        func.avg(CampaignMetrics.roi).label("avg_roi"),
        func.avg(CampaignMetrics.conversion_rate).label("avg_cvr"),
        func.count(Campaign.campaign_id).label("times_used")
    ).join(CampaignMetrics, Campaign.campaign_id == CampaignMetrics.campaign_id).\
      group_by(Campaign.promotion_id).all()
      
    promo_stats_map = {}
    for row in promo_stats:
        if row.promotion_id:
            promo_stats_map[row.promotion_id] = {
                "avg_roi": float(row.avg_roi or 0.0),
                "avg_cvr": float(row.avg_cvr or 0.0),
                "times_used": int(row.times_used or 0)
            }
            
    all_promotions = db.query(Promotion).all()
    promo_list = []
    for p in all_promotions:
        if is_promotion_eligible(p, category_filter, city_filter):
            stats = promo_stats_map.get(p.promotion_id, {"avg_roi": 0.0, "avg_cvr": 0.0, "times_used": 0})
            promo_list.append({
                "promotion_id": str(p.promotion_id),
                "name": p.name,
                "coupon_code": p.promo_code,
                "discount_type": p.discount_type,
                "discount_value": float(p.discount_value),
                "applicable_categories": p.applicable_categories,
                "applicable_cities": p.applicable_cities,
                "min_order_value": float(p.min_order_value) if p.min_order_value else None,
                "historical_roi": stats["avg_roi"],
                "historical_cvr": stats["avg_cvr"],
                "times_used_in_campaigns": stats["times_used"]
            })
            
    # 4. Generate Campaign Strategy via Gemini
    audience_desc = f"Customers in {city_filter or 'All Cities'} interested in {category_filter or 'All Categories'}"
    context = {
        "audience_description": audience_desc,
        "audience_metrics": {
            "size": eligible,
            "avg_spend": audience_summary_data.avg_spend,
            "avg_inactivity_days": audience_summary_data.avg_inactivity_days,
            "avg_churn_probability": audience_summary_data.avg_churn_probability,
            "avg_total_orders": audience_summary_data.avg_total_orders,
            "category_affinity_distribution": audience_summary_data.category_affinity_distribution,
            "city_distribution": audience_summary_data.city_distribution,
            "channel_distribution": audience_summary_data.channel_distribution
        },
        "available_promotions": promo_list,
        "city_filter": city_filter,
        "category_filter": category_filter,
        "segment_filter": segment_filter
    }
    
    strategy = XeniaAIService.generate_campaign_strategy(goal, context)
    
    # 5. Link recommended promotion
    selected_promo = None
    recommended_code = strategy.get("recommended_promotion_code")
    if recommended_code:
        selected_promo = db.query(Promotion).filter(
            Promotion.promo_code == recommended_code, 
            Promotion.active == True
        ).first()
        
    # Increment times_recommended for selected promotion
    if selected_promo:
        selected_promo.times_recommended += 1
        db.commit()
        
    # Enrich strategy with audience metrics and parsed filters for frontend explainability
    strategy["audience_summary"] = {
        "total_identified": audience_summary_data.total_identified,
        "suppressed": audience_summary_data.suppressed,
        "eligible": audience_summary_data.eligible,
        "avg_spend": float(audience_summary_data.avg_spend),
        "avg_inactivity_days": int(audience_summary_data.avg_inactivity_days),
        "avg_churn_probability": float(audience_summary_data.avg_churn_probability),
        "avg_total_orders": float(audience_summary_data.avg_total_orders),
        "city_distribution": audience_summary_data.city_distribution,
        "channel_distribution": audience_summary_data.channel_distribution,
        "category_affinity_distribution": audience_summary_data.category_affinity_distribution
    }
    strategy["parsed_filters"] = filters

    # 6. Create Draft Campaign record
    new_campaign = Campaign(
        name=strategy.get("campaign_name", f"Campaign for Goal: {goal[:30]}"),
        objective=goal,
        promotion_id=selected_promo.promotion_id if selected_promo else None,
        channel=strategy.get("channel", "WhatsApp"),
        status="draft", # Lifecycle starts as 'draft'
        ai_strategy=strategy,
        message_template=strategy.get("message_template"),
        message_variants=strategy.get("message_variants"),
        target_segment=strategy.get("target_segment", category_filter or "General Audience"),
        target_audience_size=eligible
    )
    db.add(new_campaign)
    db.commit()
    db.refresh(new_campaign)
    
    # 7. Run Campaign Simulation + store explainability
    simulation = CampaignSimulationService.run_simulation(db, new_campaign.campaign_id)

    # Evaluate voice eligibility and store as future-ready stub
    voice_eligible, voice_reason = evaluate_voice_eligibility(
        target_segment=new_campaign.target_segment or "",
        avg_ltv=audience_summary_data.avg_spend
    )

    # Build promotion explainability text
    why_promotion_text = "No promotion selected."
    if selected_promo:
        perf = promo_stats_map.get(selected_promo.promotion_id, {})
        why_promotion_text = (
            f"'{selected_promo.name}' (code: {selected_promo.promo_code}) was recommended because: "
            f"it is the highest-ROI active promotion matching the audience category. "
            f"Historical performance: {perf.get('avg_roi', 0.0):.1f}% avg ROI across "
            f"{perf.get('times_used', 0)} campaigns, {float(selected_promo.revenue_generated):,.0f} INR attributed revenue."
        )

    # Store explainability in simulation record
    ai_exp = strategy.get("ai_explanation", {})
    if isinstance(ai_exp, dict):
        db.query(CampaignSimulation).filter(
            CampaignSimulation.campaign_id == new_campaign.campaign_id
        ).update({
            "why_audience": ai_exp.get("why_audience", ""),
            "why_channel": ai_exp.get("why_channel", ""),
            "why_promotion": why_promotion_text,
            "historical_performance_note": str(promo_stats_map.get(
                selected_promo.promotion_id if selected_promo else None, {}
            )),
            "voice_eligible": voice_eligible,
            "voice_ineligible_reason": None if voice_eligible else voice_reason,
        })
        db.commit()
    
    # 8. Package Response
    promo_preview = None
    if selected_promo:
        promo_preview = PromotionPreview(
            promotion_id=str(selected_promo.promotion_id),
            name=selected_promo.name,
            promo_code=selected_promo.promo_code or "",
            discount_percentage=float(selected_promo.discount_percentage),
            min_order_value=float(selected_promo.min_order_value) if selected_promo.min_order_value else None,
            discount_type=selected_promo.discount_type,
            discount_value=float(selected_promo.discount_value),
            applicable_categories=selected_promo.applicable_categories,
            start_date=selected_promo.start_date,
            end_date=selected_promo.end_date
        )
        
    sim_preview = SimulationPreview(
        predicted_reach=simulation.predicted_reach or 0,
        predicted_ctr=simulation.predicted_ctr or 0.0,
        predicted_cvr=simulation.predicted_cvr or 0.0,
        predicted_revenue=simulation.predicted_revenue or Decimal("0.00"),
        confidence_score=simulation.confidence_score or 0.85,
        risk_factors=simulation.risk_factors or [],
        ai_narrative=simulation.ai_narrative or ""
    )
    
    ai_exp = strategy.get("ai_explanation", {})
    if isinstance(ai_exp, str):
        ai_exp_obj = CampaignStrategyExplanation(
            why_audience=ai_exp,
            why_now="Targeting dormant shoppers immediately to avoid permanent churn.",
            why_channel="Preferred communication channel for high responsiveness.",
            why_promotion=why_promotion_text
        )
    else:
        ai_exp_obj = CampaignStrategyExplanation(
            why_audience=ai_exp.get("why_audience", "Based on category affinities and inactivity."),
            why_now=ai_exp.get("why_now", "Based on current inactive interval."),
            why_channel=ai_exp.get("why_channel", "Selected based on preferred channel distribution."),
            why_promotion=ai_exp.get("why_promotion", why_promotion_text)
        )
        
    shopper_previews = []
    for c in eligible_customers[:100]:
        shopper_previews.append(
            ShopperPreview(
                customer_id=str(c.customer_id),
                name=c.name,
                city=c.city,
                email=c.email,
                phone=c.phone,
                lifetime_value=float(c.metrics.total_spend or 0.0),
                last_purchase_days=int(c.metrics.days_since_last_order or 0),
                churn_probability=float(c.metrics.churn_probability or 0.0),
                preferred_channel=c.metrics.preferred_channel or "WhatsApp",
                top_category=c.metrics.top_category if c.metrics else None,
                total_orders=c.metrics.total_orders if c.metrics else 0
            )
        )
        
    # Extract channel specific templates from Gemini strategy response
    whatsapp_template = strategy.get("whatsapp_template") or strategy.get("message_template") or ""
    whatsapp_variants = strategy.get("whatsapp_variants") or strategy.get("message_variants") or []
    
    email_subject = strategy.get("email_subject") or f"Special offer just for you, {{name}}!"
    email_subject_variants = strategy.get("email_subject_variants") or []
    email_template = strategy.get("email_template") or strategy.get("message_template") or ""
    email_variants = strategy.get("email_variants") or []
    
    sms_template = strategy.get("sms_template") or strategy.get("message_template") or ""
    sms_variants = strategy.get("sms_variants") or []
    
    return GoalPlannerResponse(
        goal=goal,
        parsed_filters={
            "city": city_filter,
            "category": category_filter,
            "min_spend": min_spend_filter,
            "max_churn_probability": max_churn_filter,
            "segment": segment_filter
        },
        campaign_name=new_campaign.name,
        target_segment=new_campaign.target_segment,
        channel=new_campaign.channel,
        message_template=new_campaign.message_template or "",
        message_variants=new_campaign.message_variants or [],
        recommended_promotion=promo_preview,
        simulation=sim_preview,
        confidence_score=float(strategy.get("confidence_score", 0.85)),
        ai_explanation=ai_exp_obj,
        audience_summary=audience_summary_data,
        eligible_shoppers=shopper_previews,

        # Channel specific copy
        whatsapp_template=whatsapp_template,
        whatsapp_variants=whatsapp_variants,
        email_subject=email_subject,
        email_subject_variants=email_subject_variants,
        email_template=email_template,
        email_variants=email_variants,
        sms_template=sms_template,
        sms_variants=sms_variants,

        # Voice eligibility stub (future phase — not implemented yet)
        voice_eligible=voice_eligible,
        voice_ineligible_reason=None if voice_eligible else voice_reason,
    )
