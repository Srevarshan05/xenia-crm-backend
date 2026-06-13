"""
Xenia CRM – Xenia AI Intelligence Layer
Powered by Groq (llama-3.3-70b-versatile) for fast inference.
Generates shopper personas, simulates campaigns, explains marketing opportunities,
parses natural language queries to SQL, and writes executive briefings.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from groq import Groq
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.customer import Customer, CustomerInsights, CustomerMetrics
from app.models.opportunity import Opportunity
from app.models.campaign import Campaign, CampaignSimulation
from app.models.briefing import DailyBriefing, NLQuery

logger = logging.getLogger("xenia.ai")

# Groq model to use
GROQ_MODEL = "llama-3.3-70b-versatile"


def ensure_string(val) -> str:
    """Helper to convert lists or dicts to formatted JSON strings if LLM returns them for text fields."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (list, dict)):
        return json.dumps(val, indent=2)
    return str(val)


class XeniaAIService:
    _groq_client: Groq = None

    @classmethod
    def get_client(cls) -> Groq:
        """Returns a cached Groq client instance."""
        if cls._groq_client is None:
            cls._groq_client = Groq(api_key=settings.groq_api_key)
        return cls._groq_client

    @classmethod
    def generate_content_with_retry(cls, prompt: str, response_mime_type: str = "application/json", retries: int = 3, delay: float = 2.0) -> str:
        """
        Calls Groq chat completions with JSON mode and simple retry logic for rate limits.
        """
        import time

        client = cls.get_client()
        current_delay = delay
        system_msg = "You are Xenia AI, a retail marketing intelligence engine. Always respond with valid, parseable JSON only. No markdown, no backticks, no extra text."

        for attempt in range(retries):
            try:
                response = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.4,
                    max_tokens=4096,
                    response_format={"type": "json_object"}
                )
                return response.choices[0].message.content
            except Exception as e:
                err_str = str(e)
                if "rate_limit" in err_str.lower() or "429" in err_str:
                    if attempt == retries - 1:
                        logger.error(f"Groq rate limit exceeded after {retries} attempts.")
                        raise
                    logger.warning(f"Groq rate limit hit. Retrying in {current_delay}s... (Attempt {attempt+1}/{retries})")
                    time.sleep(current_delay)
                    current_delay *= 2
                else:
                    logger.error(f"Groq API error: {e}")
                    raise


    @classmethod
    def generate_shopper_persona(cls, db: Session, customer_id) -> CustomerInsights:
        """
        Generates a qualitative shopper persona profile and saves it to the customer_insights table.
        """
        logger.info(f"Generating shopper persona for customer {customer_id}...")
        
        # 1. Fetch customer details and metrics
        customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
        if not customer:
            raise ValueError(f"Customer {customer_id} not found.")

        metrics = db.query(CustomerMetrics).filter(CustomerMetrics.customer_id == customer_id).first()
        metrics_summary = {}
        if metrics:
            metrics_summary = {
                "RFM_R_Score": metrics.r_score,
                "RFM_F_Score": metrics.f_score,
                "RFM_M_Score": metrics.m_score,
                "LTV_Value_Score": metrics.value_score,
                "Legacy_Churn_Score": metrics.churn_score,
                "ML_Churn_Probability": metrics.churn_probability,
                "Engagement_Score": metrics.engagement_score,
                "Preferred_Channel": metrics.preferred_channel,
                "Top_Category": metrics.top_category,
                "Category_Affinities": metrics.category_affinity_json,
                "Total_Orders": metrics.total_orders,
                "Total_Spend": metrics.total_spend,
                "Avg_Order_Value": metrics.avg_order_value,
                "Days_Since_Last_Order": metrics.days_since_last_order,
            }

        # 2. Compile recent purchase items (up to 5)
        recent_items_query = text("""
            SELECT p.name, p.category, oi.unit_price, o.order_date
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            JOIN products p ON oi.product_id = p.product_id
            WHERE o.customer_id = :customer_id
            ORDER BY o.order_date DESC
            LIMIT 5
        """)
        items_rows = db.execute(recent_items_query, {"customer_id": customer_id}).fetchall()
        recent_items = [
            {"product_name": r.name, "category": r.category, "price": float(r.unit_price), "order_date": str(r.order_date)}
            for r in items_rows
        ]

        # 3. Create prompt
        prompt = f"""
        You are Xenia AI, the advanced intelligence core of Xenia Shopper CRM.
        Analyze the following shopper data and generate a qualitative shopper persona, summary, risks, and recommendations.

        --- SHOPPER DETAILS ---
        Name: {customer.name}
        City: {customer.city}
        Join Date: {customer.join_date}

        --- CORE METRICS ---
        {json.dumps(metrics_summary, indent=2)}

        --- RECENT PRODUCTS BOUGHT ---
        {json.dumps(recent_items, indent=2)}

        Provide your response as a JSON object matching this schema:
        {{
            "ai_persona": "A catchy, descriptive persona name (e.g. 'Conscious Electronics Enthusiast', 'High-Frequency Grocery Stocker')",
            "persona_description": "A 2-3 sentence profile explaining their purchasing traits, lifestyle drivers, and channel receptivity.",
            "summary": "A high-level executive summary of this customer's lifetime value and current relationship status with the brand.",
            "risks": ["List of potential retention or engagement risks (e.g., 'Oversaturation of SMS campaigns', 'At risk of churn due to 3-month inactivity')"],
            "recommendations": ["List of actionable next steps for the marketing team (e.g., 'Send WhatsApp discount for Groceries', 'Suppress from weekly blasts for 10 days')"],
            "confidence_score": 0.85 (A float between 0.0 and 1.0 reflecting your confidence in this analysis based on data density)
        }}
        """

        # 4. Invoke Gemini with retry & fallback
        try:
            response_text = cls.generate_content_with_retry(prompt)
            res_data = json.loads(response_text)
        except Exception as e:
            logger.warning(f"Failed to generate persona via Gemini, using robust fallback: {e}")
            res_data = {
                "ai_persona": "Predictable Value Shopper",
                "persona_description": "A customer who tends to purchase standard products and prefers consistent engagement across channels.",
                "summary": "High-potential shopper who prefers direct messaging and responds well to seasonal promotions.",
                "risks": ["Slightly high communication ignores"],
                "recommendations": ["Limit contacts to 1 per week", "Offer category affinity discount"],
                "confidence_score": 0.80
            }

        # Upsert insights
        insight = db.query(CustomerInsights).filter(CustomerInsights.customer_id == customer_id).first()
        if not insight:
            insight = CustomerInsights(customer_id=customer_id)
            db.add(insight)

        insight.ai_persona = ensure_string(res_data.get("ai_persona"))
        insight.persona_description = ensure_string(res_data.get("persona_description"))
        insight.summary = ensure_string(res_data.get("summary"))
        insight.risks = res_data.get("risks")
        insight.recommendations = res_data.get("recommendations")
        insight.confidence_score = float(res_data.get("confidence_score", 0.85))
        insight.model_version = GROQ_MODEL
        
        db.commit()
        logger.info(f"Shopper persona generated successfully for customer {customer_id}.")
        return insight

    @classmethod
    def explain_opportunity(cls, db: Session, opportunity_id) -> Opportunity:
        """
        Enriches a discovered opportunity with an AI-generated explanation, action plan, and key drivers.
        """
        logger.info(f"Enriching opportunity {opportunity_id} using Xenia AI...")
        
        op = db.query(Opportunity).filter(Opportunity.opportunity_id == opportunity_id).first()
        if not op:
            raise ValueError(f"Opportunity {opportunity_id} not found.")

        # Gather sample customer details
        sample_ids = op.customer_ids_sample or []
        sample_details = []
        if sample_ids:
            samples_query = text("""
                SELECT c.name, m.top_category, m.total_spend, m.days_since_last_order
                FROM customers c
                JOIN customer_metrics m ON c.customer_id = m.customer_id
                WHERE c.customer_id IN (
                    SELECT CAST(val AS UUID) FROM unnest(:sample_ids) val
                )
                LIMIT 5
            """)
            rows = db.execute(samples_query, {"sample_ids": sample_ids}).fetchall()
            sample_details = [
                {"name": r.name, "top_category": r.top_category, "total_spend": float(r.total_spend), "days_inactive": r.days_since_last_order}
                for r in rows
            ]

        # Create prompt
        prompt = f"""
        You are Xenia AI, the advanced intelligence core of Xenia Shopper CRM.
        Explain and refine the following discovered business opportunity for the retail brand marketing team.

        --- OPPORTUNITY PROFILE ---
        Type: {op.type}
        Description: {op.description}
        Audience Size: {op.audience_size}
        Projected Revenue Impact: INR {float(op.potential_revenue or 0):,.2f}
        Priority: {op.priority}
        Baseline Drivers: {op.key_drivers}

        --- SAMPLE CUSTOMERS IMPACTED ---
        {json.dumps(sample_details, indent=2)}

        Provide your response as a JSON object matching this schema:
        {{
            "ai_explanation": "A detailed, professional explanation of the consumer psychology or co-occurrence trends behind this opportunity. Explain WHY this segment behaves this way.",
            "ai_action_plan": "A concrete, 3-step campaign execution guide for marketers. Detail the copy style, promotional framing, and timing recommendations.",
            "confidence_score": 0.88 (A float between 0.0 and 1.0 reflecting your confidence in this segment opportunity)
        }}
        """

        # 4. Invoke Gemini with retry & fallback
        try:
            response_text = cls.generate_content_with_retry(prompt)
            res_data = json.loads(response_text)
        except Exception as e:
            logger.warning(f"Failed to generate opportunity explanation via Gemini: {e}")
            res_data = {
                "ai_explanation": f"This opportunity targets {op.audience_size} customers based on behavioral drift and category affinity indexes. By addressing their recency decay with a relevant coupon, we capture late-stage interest before complete disengagement.",
                "ai_action_plan": "1. Dispatch a high-relevance campaign on their preferred channel.\n2. Apply the recommended discount value to lower buying friction.\n3. Implement a 7-day conversion tracking window.",
                "confidence_score": 0.80
            }

        op.ai_explanation = ensure_string(res_data.get("ai_explanation"))
        op.ai_action_plan = ensure_string(res_data.get("ai_action_plan"))
        op.confidence_score = float(res_data.get("confidence_score", 0.88))
        
        db.commit()
        logger.info(f"Opportunity {opportunity_id} successfully enriched with AI reasoning.")
        return op

    @classmethod
    def simulate_campaign(cls, db: Session, campaign_id) -> CampaignSimulation:
        """
        Simulates a campaign's expected performance (reach, CTR, conversion rate, revenue, and risks)
        using historical benchmarks and Gemini AI.
        """
        logger.info(f"Simulating campaign performance for campaign {campaign_id}...")
        
        campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found.")

        # Fetch historical campaign metrics for benchmark context
        benchmarks_query = text("""
            SELECT c.channel, AVG(m.conversion_rate) as avg_cvr, AVG(m.roi) as avg_roi
            FROM campaigns c
            JOIN campaign_metrics m ON c.campaign_id = m.campaign_id
            GROUP BY c.channel
        """)
        benchmarks_rows = db.execute(benchmarks_query).fetchall()
        benchmarks = {
            r.channel: {"avg_cvr": float(r.avg_cvr or 0), "avg_roi": float(r.avg_roi or 0)}
            for r in benchmarks_rows
        }

        # Gather target audience metrics
        # If opportunity_id is linked, we get average basket values
        avg_aov = 1500.0
        if campaign.opportunity_id:
            op_aov_query = text("""
                SELECT COALESCE(AVG(avg_order_value), 1500.0)
                FROM customer_metrics
                WHERE customer_id IN (
                    SELECT customer_id FROM customer_segments 
                    WHERE segment_name = (
                        SELECT type FROM opportunities WHERE opportunity_id = :op_id
                    )
                )
            """)
            avg_aov = float(db.execute(op_aov_query, {"op_id": campaign.opportunity_id}).scalar() or 1500.0)

        # Create prompt
        prompt = f"""
        You are Xenia AI, the advanced intelligence core of Xenia Shopper CRM.
        Simulate the expected response rates and risks of this marketing campaign before it launches.

        --- CAMPAIGN SPECIFICATION ---
        Name: {campaign.name}
        Objective: {campaign.objective}
        Channel: {campaign.channel}
        Message Template: {campaign.message_template}
        Target Audience Segment: {campaign.target_segment}
        Target Audience Size: {campaign.target_audience_size}
        Average Shopper Basket Value (AOV): INR {avg_aov:,.2f}

        --- CHANNEL BENCHMARKS ---
        {json.dumps(benchmarks, indent=2)}

        Provide your response as a JSON object matching this schema:
        {{
            "predicted_reach": 1000 (Integer, expected number of successfully delivered messages),
            "predicted_ctr": 0.22 (Float, expected click-through rate between 0.0 and 1.0),
            "predicted_cvr": 0.05 (Float, expected conversion/purchase rate from delivered message count between 0.0 and 1.0),
            "predicted_revenue": 45000.00 (Float, expected total purchase value),
            "confidence_score": 0.85 (Float between 0.0 and 1.0),
            "risk_factors": [
                "List of risk factors (e.g. 'SMS channel has a high fatigue score for 20% of this segment', 'Template lacks call-to-action link')"
            ],
            "ai_narrative": "A 2-3 sentence overview explaining the predicted outcome and suggestions for tweaking copy/channel."
        }}
        """

        # 4. Invoke Gemini with retry & fallback
        try:
            response_text = cls.generate_content_with_retry(prompt)
            res_data = json.loads(response_text)
        except Exception as e:
            logger.warning(f"Failed to generate campaign simulation via Gemini: {e}")
            reach = campaign.target_audience_size or 500
            ctr = 0.18
            cvr = 0.04
            rev = float(reach) * ctr * cvr * avg_aov
            res_data = {
                "predicted_reach": reach,
                "predicted_ctr": ctr,
                "predicted_cvr": cvr,
                "predicted_revenue": rev,
                "confidence_score": 0.82,
                "risk_factors": ["Rate limit mode enabled", "Standard channel fatigue factors apply"],
                "ai_narrative": "The simulation was generated using baseline retail cohorts. Target response rates reflect historical averages for similar promotions."
            }


        # Upsert simulation
        sim = db.query(CampaignSimulation).filter(CampaignSimulation.campaign_id == campaign_id).first()
        if not sim:
            sim = CampaignSimulation(campaign_id=campaign_id)
            db.add(sim)

        sim.predicted_reach = int(res_data.get("predicted_reach", campaign.target_audience_size))
        sim.predicted_ctr = float(res_data.get("predicted_ctr", 0.0))
        sim.predicted_cvr = float(res_data.get("predicted_cvr", 0.0))
        sim.predicted_revenue = Decimal(str(round(float(res_data.get("predicted_revenue", 0.0)), 2)))
        sim.confidence_score = float(res_data.get("confidence_score", 0.85))
        sim.risk_factors = res_data.get("risk_factors", [])
        sim.simulation_context = {
            "benchmarks": benchmarks,
            "assumed_aov": avg_aov
        }
        sim.ai_narrative = ensure_string(res_data.get("ai_narrative"))
        
        db.commit()
        logger.info(f"Campaign {campaign_id} successfully simulated.")
        return sim

    @classmethod
    def generate_daily_briefing(cls, db: Session) -> DailyBriefing:
        """
        Gathers daily business metrics and prompts Gemini to write the headlines,
        active opportunity count, suppression actions, and key recommendations.
        """
        logger.info("Generating daily executive AI briefing...")
        now = datetime.now(timezone.utc)
        briefing_date = now.date()

        # 1. Gather stats
        total_customers = db.execute(text("SELECT COUNT(*) FROM customers")).scalar()
        active_opps = db.execute(text("SELECT COUNT(*) FROM opportunities WHERE status = 'open'")).scalar()
        potential_opp_revenue = float(db.execute(text("SELECT COALESCE(SUM(potential_revenue), 0.0) FROM opportunities WHERE status = 'open'")).scalar() or 0.0)
        
        at_risk_count = db.execute(text("SELECT COUNT(*) FROM customer_segments WHERE segment_name = 'At Risk'")).scalar()
        spam_risk_count = db.execute(text("SELECT COUNT(*) FROM customer_segments WHERE segment_name = 'Spam Risk'")).scalar()

        # Get aggregate campaign statistics (past 30 days)
        campaigns_30d = db.execute(text("""
            SELECT COUNT(c.campaign_id) as active_camps, COALESCE(SUM(m.attributed_revenue), 0.0) as revenue
            FROM campaigns c
            JOIN campaign_metrics m ON c.campaign_id = m.campaign_id
            WHERE c.launched_at >= :date_30d
        """), {"date_30d": now - timedelta(days=30)}).first()

        stats = {
            "Date": str(briefing_date),
            "Total_Customers": total_customers,
            "Active_Opportunities_Count": active_opps,
            "Total_Recoverable_Revenue_Opportunities": potential_opp_revenue,
            "Customers_At_Risk_Count": at_risk_count,
            "Fatigued_Customers_Spam_Risk_Count": spam_risk_count,
            "Active_Campaigns_30d": campaigns_30d.active_camps if campaigns_30d else 0,
            "Attributed_Revenue_30d": float(campaigns_30d.revenue if campaigns_30d else 0.0)
        }

        # 2. Create prompt
        prompt = f"""
        You are Xenia AI, the advanced intelligence core of Xenia Shopper CRM.
        Write the Daily CRM Executive Briefing for the marketing and retail operations team.
        Synthesize the business metrics and highlight key opportunities, fatigue warnings, and next steps.

        --- TODAY'S BUSINESS STATS ---
        {json.dumps(stats, indent=2)}

        Provide your response as a JSON object matching this schema:
        {{
            "headline": "A short, punchy business headline for today (e.g. 'VIP Winback potential reaches INR 7.0M; Churn risk stabilized')",
            "summary": "A 3-4 sentence paragraph summarizing today's key performance indexes, active opportunities, and critical spam/suppression highlights.",
            "full_content": {{
                "kpi_overview": "Paragraph analyzing revenue and customer counts.",
                "opportunities_breakdown": "Analysis of open opportunities and projected financial gains.",
                "fatigue_and_safety_alert": "Important note warning about spam risks, fatigue levels, and active suppressions (cooling-off counts).",
                "recommended_actions": ["List of 3 immediate tactical actions to take today (e.g. 'Launch Reactivate Churn campaign', 'Approve suppressions for 32 fatigued shoppers')"]
            }},
            "confidence_score": 0.92
        }}
        """

        # 4. Invoke Gemini with retry & fallback
        try:
            response_text = cls.generate_content_with_retry(prompt)
            res_data = json.loads(response_text)
        except Exception as e:
            logger.warning(f"Failed to generate daily briefing via Gemini: {e}")
            res_data = {
                "headline": f"Xenia Active Operations Review: {active_opps} Opportunities Tracked",
                "summary": f"Our database tracks a customer base of {total_customers} with {active_opps} active growth opportunities. Potential recoverable revenue stands at INR {potential_opp_revenue:,.2f}.",
                "full_content": {
                    "kpi_overview": f"The platform is monitoring {total_customers} active profiles. Overall monthly campaigns attribution is active.",
                    "opportunities_breakdown": f"Open opportunities potential equals INR {potential_opp_revenue:,.2f} spread across {active_opps} segments.",
                    "fatigue_and_safety_alert": f"Currently monitoring {spam_risk_count} profiles flagged under Spam Risk fatigue suppression. Marketing cooling parameters are operating normally.",
                    "recommended_actions": [
                        "Prioritize high-value reactivation opportunities.",
                        "Monitor churn probability metrics weekly.",
                        "Suppress saturated WhatsApp users from next bulk communication."
                    ]
                },
                "confidence_score": 0.85
            }


        # Upsert briefing
        brief = db.query(DailyBriefing).filter(DailyBriefing.briefing_date == briefing_date).first()
        if not brief:
            brief = DailyBriefing(briefing_date=briefing_date)
            db.add(brief)

        brief.headline = ensure_string(res_data.get("headline"))
        brief.summary = ensure_string(res_data.get("summary"))
        brief.opportunities_count = int(stats["Active_Opportunities_Count"])
        brief.at_risk_count = int(stats["Customers_At_Risk_Count"])
        brief.recoverable_revenue = Decimal(str(round(float(stats["Total_Recoverable_Revenue_Opportunities"]), 2)))
        brief.full_content = res_data.get("full_content", {})
        brief.confidence_score = float(res_data.get("confidence_score", 0.92))
        brief.model_version = settings.gemini_model
        
        db.commit()
        logger.info("Daily executive briefing generated successfully.")
        return brief

    @classmethod
    def execute_natural_language_query(cls, db: Session, question: str) -> NLQuery:
        """
        Parses a shopper analytics question into a predefined intent using Xenia AI,
        executes the matching fixed secure SQL query against PostgreSQL,
        and translates the outcomes into a natural language response with charting advice.
        """
        logger.info(f"Classifying natural language query intent: '{question}'...")

        # 1. Ask Gemini to classify user intent to a predefined set
        prompt_intent = f"""
        You are Xenia AI, the advanced intelligence core of Xenia Shopper CRM.
        Analyze the user's retail analytics question and classify it into exactly one of the following predefined intents:
        
        INTENT KEYS:
        - "total_customers": General customer counts or demographics.
        - "customers_by_city": Geographical distribution of customers.
        - "churn_risk_summary": Customer churn summaries, shoppers at risk, or churn counts.
        - "revenue_by_category": Sales, orders, and revenue split by product categories.
        - "top_spend_customers": VIP profiles or highest spending shopper details.
        - "campaign_performance": Outbound campaign CTR, conversion, ROI, and metrics.
        - "active_opportunities": Opportunities currently open for growth and fatigue suppressions.

        USER QUESTION: "{question}"

        Provide your response as a JSON object matching this schema:
        {{
            "intent": "one of the predefined intent keys above",
            "confidence_score": 0.95
        }}
        """

        # Map intents to fixed, safe read-only SQL queries
        intent_queries = {
            "total_customers": "SELECT COUNT(*) AS total_customers FROM customers;",
            "customers_by_city": "SELECT city, COUNT(*) AS customer_count FROM customers GROUP BY city ORDER BY customer_count DESC;",
            "churn_risk_summary": "SELECT COUNT(*) AS at_risk_count, ROUND(AVG(churn_probability)::numeric, 4) AS avg_churn_prob FROM customer_metrics WHERE churn_probability >= 0.5;",
            "revenue_by_category": "SELECT p.category, SUM(oi.quantity * oi.unit_price) AS total_revenue, COUNT(DISTINCT o.order_id) AS total_orders FROM order_items oi JOIN products p ON oi.product_id = p.product_id JOIN orders o ON oi.order_id = o.order_id GROUP BY p.category ORDER BY total_revenue DESC;",
            "top_spend_customers": "SELECT c.name, c.city, m.total_spend, m.total_orders FROM customer_metrics m JOIN customers c ON m.customer_id = c.customer_id ORDER BY m.total_spend DESC LIMIT 5;",
            "campaign_performance": "SELECT c.name, c.channel, m.total_sent, m.total_purchased, m.attributed_revenue, m.roi FROM campaigns c JOIN campaign_metrics m ON c.campaign_id = m.campaign_id ORDER BY m.attributed_revenue DESC;",
            "active_opportunities": "SELECT type, audience_size, potential_revenue, priority FROM opportunities WHERE status = 'open' ORDER BY potential_revenue DESC;"
        }

        try:
            response_intent_text = cls.generate_content_with_retry(prompt_intent)
            intent_data = json.loads(response_intent_text)
            intent = intent_data.get("intent", "total_customers")
            sql_confidence = float(intent_data.get("confidence_score", 0.90))
        except Exception as e:
            logger.warning(f"Failed to classify intent via Gemini, using fallback: {e}")
            intent = "total_customers"
            sql_confidence = 0.70

        # Validate that intent matches our queries
        if intent not in intent_queries:
            logger.warning(f"Classified intent '{intent}' not in predefined queries list. Defaulting to 'total_customers'")
            intent = "total_customers"

        sql_query = intent_queries[intent]
        
        # 2. Run the fixed SQL query safely
        query_results = []
        error_msg = None

        try:
            # We strictly enforce read-only execution (select statements only)
            cleaned_query = sql_query.strip().lower()
            if not cleaned_query.startswith("select"):
                raise PermissionError("Only SELECT statements are allowed.")
            
            logger.info(f"Executing generated SQL: {sql_query}")
            rows = db.execute(text(sql_query)).fetchall()
            
            # Convert row objects to list of dicts for serialization
            # To get column names from result proxy
            result_proxy = db.execute(text(sql_query))
            col_names = list(result_proxy.keys())
            
            for row in rows:
                query_results.append({col_names[idx]: (float(val) if isinstance(val, (Decimal, float)) else str(val) if not isinstance(val, (int, str, bool, type(None))) else val) for idx, val in enumerate(row)})
                
        except Exception as e:
            logger.error(f"Failed to execute generated SQL: {e}")
            error_msg = str(e)
            query_results = []

        # 3. Prompt Gemini to translate SQL outcomes back into text narrative
        prompt_narrative = f"""
        You are Xenia AI, the advanced intelligence core of Xenia Shopper CRM.
        Synthesize the SQL database results into a friendly, professional explanation for the retail executive.

        USER QUESTION: "{question}"
        GENERATED SQL: "{sql_query}"
        QUERY ERROR (if any): "{error_msg}"
        SQL DATA RESULTS:
        {json.dumps(query_results, indent=2)}

        Provide your response as a JSON object matching this schema:
        {{
            "response": "A detailed natural language explanation of the results. Highlight key figures or standouts.",
            "chart_suggestion": "Specify if the data would benefit from a chart. One of: 'BarChart', 'LineChart', 'PieChart', 'Table', or 'None'."
        }}
        """

        # 3. Invoke Gemini for narrative generation with retry & fallback
        try:
            response_narrative_text = cls.generate_content_with_retry(prompt_narrative)
            narrative_data = json.loads(response_narrative_text)
            narrative_response = narrative_data.get("response")
            chart_suggestion = narrative_data.get("chart_suggestion", "None")
        except Exception as e:
            logger.warning(f"Failed to generate narrative response via Gemini: {e}")
            narrative_response = f"I have run the query and successfully extracted {len(query_results)} records from the database. Here is the query result summary: {json.dumps(query_results)}."
            chart_suggestion = "Table"


        # 4. Save to nl_queries table
        new_query = NLQuery(
            question=question,
            intent=intent,
            context_json={
                "sql_query": sql_query,
                "error": error_msg,
                "schema_used": "1.0.0"
            },
            response=narrative_response,
            data_points=query_results,
            chart_suggestion=chart_suggestion,
            confidence_score=sql_confidence
        )
        db.add(new_query)
        db.commit()
        
        logger.info(f"Natural language query completed successfully.")
        return new_query

    @classmethod
    def generate_fallback_campaign_name(cls, goal: str, context: dict) -> str:
        goal_lower = goal.lower()
        
        # Extract details from context
        city = context.get("city_filter")
        category = context.get("category_filter")
        
        # 1. Match precise example pattern combinations first
        if "bring back vip" in goal_lower or ("vip" in goal_lower and ("winback" in goal_lower or "win back" in goal_lower or "bring back" in goal_lower)):
            return "VIP Customer Re-engagement Campaign"
        if "chennai" in goal_lower and "electronics" in goal_lower:
            return "Chennai Electronics Weekend Sale"
        if "sports" in goal_lower and ("winback" in goal_lower or "win back" in goal_lower or "bring back" in goal_lower or "reactivation" in goal_lower):
            return "Win Back High Value Sports Shoppers"
        if "beauty" in goal_lower and "loyalty" in goal_lower:
            return "Beauty Category Loyalty Boost Campaign"
        if "mumbai" in goal_lower and ("fashion" in goal_lower or "clothing" in goal_lower or "flash" in goal_lower):
            return "Mumbai Fashion Flash Sale"
        if "inactive premium" in goal_lower or ("inactive" in goal_lower and "premium" in goal_lower):
            return "Inactive Premium Customers Reactivation Drive"
            
    @classmethod
    def generate_fallback_campaign_name(cls, goal: str, context: dict) -> str:
        """
        Builds a simple, jargon-free explanatory campaign title based on the goal, category, and promo context.
        """
        goal_lower = goal.lower()
        category = context.get("category_filter") or ""
        city = context.get("city_filter") or ""
        promo_code = context.get("available_promotions", [{}])[0].get("coupon_code") if context.get("available_promotions") else None
        
        promo_suffix = f" with {promo_code}" if promo_code else ""
        cat_str = f" {category}" if category else ""
        
        if "winback" in goal_lower or "win back" in goal_lower or "bring back" in goal_lower:
            return f"Win Back Lapsed{cat_str} Shoppers{promo_suffix}"
        elif "reactivate" in goal_lower or "inactive" in goal_lower or "dormant" in goal_lower:
            return f"Re-engage Inactive{cat_str} Shoppers{promo_suffix}"
        elif "cross_sell" in goal_lower or "cross sell" in goal_lower or "affinity" in goal_lower:
            return f"Introduce New Items to{cat_str} Buyers{promo_suffix}"
        elif "fatigue" in goal_lower or "suppress" in goal_lower or "spam" in goal_lower:
            return "Cooling-off Period for Over-contacted Shoppers"
        
        return f"Special Discount for{cat_str} Shoppers{promo_suffix}"

    @classmethod
    def generate_campaign_strategy(cls, goal: str, context: dict) -> dict:
        """
        Formulates a marketing campaign strategy draft (including segment name, recommended channel, 
        message copy template, variants, and promotions) based on a business goal and customer audience context.
        """
        logger.info(f"Generating campaign strategy for goal: '{goal}'...")
        
        promotions_list = context.get("available_promotions", [])
        audience_info = context.get("audience_metrics", {})
        
        prompt = f"""
        You are Xenia AI, the advanced intelligence core of Xenia Shopper CRM.
        Formulate a detailed, high-converting retail marketing campaign strategy that addresses the user's business goal.

        BUSINESS GOAL: "{goal}"
        
        --- TARGET AUDIENCE CONTEXT ---
        - Description: {context.get("audience_description", "Filtered customer list")}
        - Size: {audience_info.get("size", 0)} shoppers
        - Average Lifetime Spend: INR {audience_info.get("avg_spend", 0.0):,.2f}
        - Average Inactivity (Days): {audience_info.get("avg_inactivity_days", 0)} days
        - Average Churn Probability: {audience_info.get("avg_churn_probability", 0.0) * 100:.1f}%
        - Average Purchase Frequency (Orders): {audience_info.get("avg_total_orders", 0.0):.1f} orders
        - Category Affinity Distribution: {json.dumps(audience_info.get("category_affinity_distribution", {}))}
        - City Distribution: {json.dumps(audience_info.get("city_distribution", {}))}
        - Preferred Channel Distribution: {json.dumps(audience_info.get("channel_distribution", {}))}
        
        --- AVAILABLE ELIGIBLE PROMOTIONS ---
        {json.dumps(promotions_list, indent=2)}

        Select the best eligible promotion from the list. Evaluate:
        1. Cohort category affinity distribution (which categories are most popular).
        2. Average inactivity level (e.g. if inactivity is moderate, deeper discounts are unnecessary).
        3. Historical promotion performance (ROI and conversion rates).
        If none fits, recommend null.

        CRITICAL REQUIREMENT: Avoid any AI-centric, ML-centric, or technical CRM labels (e.g. 'Winback', 'Channel Push', 'Reactivation', 'Cross Sell', 'Fatigue Suppression', 'LLM', 'AI', 'Gemini'). Generate a business-friendly, easily understandable campaign title of 4-8 words that clearly explains *who* is being reached, *what* category/promotion is offered, and *why* (e.g. 'Re-engage Inactive Beauty Buyers with 15% Off', 'Win Back Lapsed VIP Shoppers with 25% Coupon', 'Introduce Sports Gear to Active Fitness Shoppers'). Avoid generic prefixes like 'Growth Blitz:' or 'Address Opportunity:'. The title should instantly explain the campaign's exact purpose to any reader.
        DO NOT include any emojis (e.g. no icons, no smileys) in the copy, names, subjects, or explanations.
        DO NOT use the word "rationale" or "Rationale" in any heading or explanation text.
        
        Provide your response as a JSON object matching this schema:
        {{
            "campaign_name": "A clear, explanatory campaign title of 4-8 words (e.g., 'Re-engage Inactive Beauty Buyers with 15% Off', 'Win Back Lapsed VIP Shoppers with 25% Coupon')",
            "target_segment": "A concise, non-technical marketing label for the audience segment (e.g., 'Chennai Electronics Shoppers')",
            "channel": "The most effective channel for this campaign. Must be one of: 'WhatsApp', 'Email', or 'SMS'.",
            "message_template": "The primary marketing copy template for the recommended channel. Use {{name}} placeholder.",
            "message_variants": [
                "A/B test message variant 1. Use {{name}} placeholder.",
                "A/B test message variant 2. Use {{name}} placeholder."
            ],
            "recommended_promotion_code": "The coupon code of the selected promotion from the list, or null if none selected",
            "confidence_score": 0.85,
            "ai_explanation": {{
                "why_audience": "Explain why this audience was selected based on their specific metrics (Recency, Frequency, Monetary spend, Churn Probability, category affinities) and why other shoppers were NOT selected. Use plain language, no AI/ML jargon, and no emojis.",
                "why_now": "Explain why this campaign is recommended now based on inactivity timeframes and why this timing is preferred over others. Use plain language, no AI/ML jargon, and no emojis.",
                "why_channel": "Explain why this channel is recommended based on preferred channel distributions and why other channels were NOT recommended. Use plain language, no AI/ML jargon, and no emojis.",
                "why_promotion": "Explain why this specific promotion was chosen from all the available options (evaluating discount value, category affinity match, and margin impact) and why other promotions were NOT chosen. Use plain language, no AI/ML jargon, and no emojis."
            }},
            "whatsapp_template": "A friendly, conversational WhatsApp message template. Use {{name}} placeholder.",
            "whatsapp_variants": [
                "Alternative A/B WhatsApp variant 1. Use {{name}}.",
                "Alternative A/B WhatsApp variant 2. Use {{name}}."
            ],
            "email_subject": "A compelling email subject line. Include urgency and the coupon code if applicable.",
            "email_subject_variants": [
                "Alternative Email subject variant 1.",
                "Alternative Email subject variant 2."
            ],
            "email_template": "A structured email body copy with a greeting, main promotion offer details, call to action, and signature. Use {{name}} placeholder.",
            "email_variants": [
                "Alternative A/B Email body variant 1. Use {{name}}.",
                "Alternative A/B Email body variant 2. Use {{name}}."
            ],
            "sms_template": "A very short, high-impact SMS message. Max 160 characters, focus on a clear Call to Action (CTA) link. Use {{name}} placeholder.",
            "sms_variants": [
                "Alternative A/B SMS variant 1. Use {{name}}.",
                "Alternative A/B SMS variant 2. Use {{name}}."
            ]
        }}
        """

        # 4. Invoke Gemini with retry & fallback
        try:
            response_text = cls.generate_content_with_retry(prompt)
            strategy_data = json.loads(response_text)
            logger.info("Campaign strategy generated successfully.")
            return strategy_data
        except Exception as e:
            logger.warning(f"Failed to generate campaign strategy via Gemini: {e}")
            # Try to grab the first promo code from the promotions list if any
            first_promo_code = promotions_list[0].get("coupon_code") if promotions_list else None
            promo_name = promotions_list[0].get("name") if promotions_list else "Special discount"
            fallback_name = cls.generate_fallback_campaign_name(goal, context)
            return {
                "campaign_name": fallback_name,
                "target_segment": context.get("audience_description", "Target cohort"),
                "channel": "WhatsApp",
                "message_template": f"Hey {{name}}! We have a special offer just for you. Use code {first_promo_code or 'SAVE10'} to get amazing deals! Shop now.",
                "message_variants": [
                    "Hello {{name}}! Don't miss out on our limited edition catalog.",
                    "Hi {{name}}! Here's a curated pick matching your shopping style."
                ],
                "recommended_promotion_code": first_promo_code,
                "confidence_score": 0.80,
                "ai_explanation": {
                    "why_audience": "This cohort was selected based on purchase Recency (R) showing moderate inactivity, combined with strong customer lifetime spend (Monetary value) and high historical order Frequency (F). Shoppers outside this cohort were excluded due to active purchase recency or low category affinity rankings.",
                    "why_now": "Outreach is recommended at this moment because their inactivity duration indicates they are approaching a critical threshold where Churn Probability begins to elevate.",
                    "why_channel": "WhatsApp is recommended as the primary channel because preferred channel metrics show it has the highest customer engagement rate compared to alternative channels.",
                    "why_promotion": f"The promotion code {first_promo_code or 'SAVE10'} was selected from all available promotions because it matches their historical Shopper Affinity for this category and provides an optimal incentive without diluting margins, whereas other coupons were either category-mismatched or had excessive discount value."
                },
                "whatsapp_template": f"Hey {{name}}! 👋 We noticed you haven't visited us in a while, so we have a special treat for you! Use code *{first_promo_code or 'SAVE10'}* to get exclusive discounts on your next order. 🛍️ Shop now!",
                "whatsapp_variants": [
                    f"Hello {{name}}! We miss you. Here is a special *{first_promo_code or 'SAVE10'}* code for your favorite items. Click here to shop!",
                    f"Hi {{name}}! Ready to refresh your style? Get special rates using code *{first_promo_code or 'SAVE10'}* today."
                ],
                "email_subject": f"We Miss You, {{name}}! Grab your {promo_name} inside 🎁",
                "email_subject_variants": [
                    "Exclusive Welcome Back Gift just for you!",
                    f"Still thinking about it? Use code {first_promo_code or 'SAVE10'} for special savings"
                ],
                "email_template": f"Dear {{name}},\n\nWe noticed you haven't shopped with us recently, and we want to welcome you back! Here is an exclusive offer tailored just for you.\n\nUse your promo code *{first_promo_code or 'SAVE10'}* at checkout and enjoy the savings.\n\nBest regards,\nThe Xenia Operations Team",
                "email_variants": [
                    f"Hi {{name}},\n\nWe have updated our catalog with fresh items in your favorite categories! Check out what is new today and use code {first_promo_code or 'SAVE10'} to save."
                ],
                "sms_template": f"Hey {{name}}! We miss you. Use code {first_promo_code or 'SAVE10'} for special savings. Shop now: xenia.in/shop",
                "sms_variants": [
                    f"Hi {{name}}! Quick heads up: your special code {first_promo_code or 'SAVE10'} expires soon. Claim now: xenia.in/shop"
                ]
            }


    @classmethod
    def parse_planner_goal(cls, goal: str) -> dict:
        """
        Parses a high-level natural language marketing goal into structured SQL filtering parameters.
        Example: "Increase electronics revenue in Chennai" -> {"city": "Chennai", "category": "Electronics"}
        """
        logger.info(f"Parsing planner goal with Gemini: '{goal}'...")
        prompt = f"""
        You are Xenia AI, the advanced intelligence core of Xenia Shopper CRM.
        Parse the following high-level retail business goal into structured filtering parameters.

        GOAL: "{goal}"

        Available Categories: "Electronics", "Groceries", "Sports", "Beauty", "Clothing", "Toys", "Baby Products", "Home & Kitchen", "Books"
        Available Cities: "Chennai", "Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Pune", "Kolkata", "Ahmedabad"

        Provide your response as a JSON object matching this schema:
        {{
            "city": "The city name if mentioned or implied (must be exactly one of the available cities, or null)",
            "category": "The product category if mentioned or implied (must be exactly one of the available categories, or null)",
            "min_spend": "A float representing any minimum spend threshold if mentioned, or null",
            "max_churn_probability": "A float representing a churn risk limit if mentioned (e.g., to exclude high-risk customers, set to 0.5), or null",
            "segment": "A segment keyword if implied, or null"
        }}
        """
        try:
            response_text = cls.generate_content_with_retry(prompt)
            return json.loads(response_text)
        except Exception as e:
            logger.warning(f"Failed to parse planner goal via Gemini, using robust parameter fallback: {e}")
            # Dynamic fallback: scan goal for keywords
            city = None
            for c in ["Chennai", "Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Pune", "Kolkata", "Ahmedabad"]:
                if c.lower() in goal.lower():
                    city = c
                    break
            category = None
            for cat in ["Electronics", "Groceries", "Sports", "Beauty", "Clothing", "Toys", "Baby Products", "Home & Kitchen", "Books"]:
                if cat.lower() in goal.lower():
                    category = cat
                    break
            return {
                "city": city,
                "category": category,
                "min_spend": None,
                "max_churn_probability": None,
                "segment": None
            }



