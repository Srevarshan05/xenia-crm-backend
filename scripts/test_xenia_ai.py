import os
import sys
import logging

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import db_session
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.campaign import Campaign
from app.services.xenia_ai import XeniaAIService

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("xenia.test_ai")

def main():
    logger.info("Initializing Xenia AI Gemini 2.5 Flash Tests...")
    
    with db_session() as db:
        try:
            # 1. Test Shopper Persona Generation
            logger.info("Test 1: Generating Shopper Persona (AI Memory Layer)...")
            cust = db.query(Customer).first()
            if cust:
                logger.info(f"Selected Customer: {cust.name} ({cust.customer_id})")
                insight = XeniaAIService.generate_shopper_persona(db, cust.customer_id)
                logger.info(f"SUCCESS! Persona: {insight.ai_persona}")
                logger.info(f"Narrative Profile: {insight.persona_description}")
                logger.info(f"Confidence Score: {insight.confidence_score}")
                logger.info(f"Risks: {insight.risks}")
                logger.info(f"Recommendations: {insight.recommendations}")
            else:
                logger.warning("No customers found in database to test persona generation.")
                
            # 2. Test Opportunity Explanation Enrichment
            logger.info("\nTest 2: Enriching Discovered Opportunity...")
            op = db.query(Opportunity).first()
            if op:
                logger.info(f"Selected Opportunity: {op.type} ({op.opportunity_id})")
                enriched_op = XeniaAIService.explain_opportunity(db, op.opportunity_id)
                logger.info("SUCCESS! AI Explanation:")
                logger.info(enriched_op.ai_explanation)
                logger.info("AI Action Plan:")
                logger.info(enriched_op.ai_action_plan)
                logger.info(f"Confidence Score: {enriched_op.confidence_score}")
            else:
                logger.warning("No opportunities found in database to test explanation.")

            # 3. Test Daily Briefing Generation
            logger.info("\nTest 3: Generating Daily Executive Briefing...")
            briefing = XeniaAIService.generate_daily_briefing(db)
            logger.info("SUCCESS! Briefing Headline:")
            logger.info(briefing.headline)
            logger.info(f"Summary: {briefing.summary}")
            logger.info(f"KPI Details: {briefing.full_content}")
            logger.info(f"Confidence: {briefing.confidence_score}")

            # 4. Test Natural Language Query execution
            logger.info("\nTest 4: Executing Natural Language Query (NL to SQL to Text)...")
            question = "How many customers are in Mumbai and what is their total spend?"
            logger.info(f"User Question: '{question}'")
            nl_query = XeniaAIService.execute_natural_language_query(db, question)
            logger.info("SUCCESS! Parsed Intent:")
            logger.info(nl_query.intent)
            logger.info("Executed SQL:")
            logger.info(nl_query.context_json.get("sql_query"))
            logger.info("SQL Data Outcomes:")
            logger.info(nl_query.data_points)
            logger.info("AI Explanation:")
            logger.info(nl_query.response)
            logger.info(f"Suggested Chart: {nl_query.chart_suggestion}")

        except Exception as e:
            logger.error(f"Error during Gemini AI testing: {e}", exc_info=True)

if __name__ == "__main__":
    main()
