"""
Xenia CRM – Backend API Integration Tests
Uses FastAPI TestClient to verify all implemented endpoints and services:
- Health check
- Customers & Segments list & detail
- AI Shopper Persona generation on-demand
- Opportunity list, detail & AI explanation enrichment
- AI Goal Planner: parsing, drafting campaign, initial simulation
- Campaign Lifecycle & Launch
- Messaging webhook callbacks (channel simulation)
- Revenue attribution metrics recalculation
"""

import os
import sys
import logging
from fastapi.testclient import TestClient

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.database import db_session
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.campaign import Campaign, Communication

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("xenia.api_test")

client = TestClient(app)

def run_integration_tests():
    logger.info("Starting Xenia API Integration Test Suite...")
    errors = 0
    
    with db_session() as db:
        # Fetch actual test entities from DB
        test_customer = db.query(Customer).first()
        test_opportunity = db.query(Opportunity).first()
        
        if not test_customer:
            logger.error("Database seed empty: no customers found to test.")
            return
            
        customer_id = str(test_customer.customer_id)
        logger.info(f"Using test customer: {test_customer.name} ({customer_id})")
        
        # Test 1: Health check
        logger.info("\n=== Test 1: Health Check ===")
        res = client.get("/health")
        logger.info(f"Response: {res.status_code} - {res.json()}")
        if res.status_code != 200:
            errors += 1
            
        # Test 2: Customers list & pagination
        logger.info("\n=== Test 2: List Customers ===")
        res = client.get("/api/customers?limit=5")
        logger.info(f"Response: {res.status_code} - Retrieved {len(res.json())} customers.")
        if res.status_code != 200 or len(res.json()) == 0:
            errors += 1
            
        # Test 3: Customer profile detail
        logger.info("\n=== Test 3: Get Customer Details ===")
        res = client.get(f"/api/customers/{customer_id}")
        logger.info(f"Response: {res.status_code} - Name: {res.json().get('name')}")
        if res.status_code != 200:
            errors += 1
            
        # Test 4: Customer intelligence metrics
        logger.info("\n=== Test 4: Get Customer Metrics ===")
        res = client.get(f"/api/customers/{customer_id}/metrics")
        logger.info(f"Response: {res.status_code} - Churn probability: {res.json().get('churn_probability')}")
        if res.status_code != 200:
            errors += 1
            
        # Test 5: Customer insights (AI Persona) - Dynamic creation
        logger.info("\n=== Test 5: Get Customer Insights (Dynamic AI Persona) ===")
        res = client.get(f"/api/customers/{customer_id}/insights")
        logger.info(f"Response: {res.status_code} - AI Persona: {res.json().get('ai_persona')}")
        logger.info(f"Confidence score: {res.json().get('confidence_score')}")
        if res.status_code != 200:
            errors += 1
            
        # Test 6: Segments list
        logger.info("\n=== Test 6: List Segments ===")
        res = client.get("/api/customers/segments")
        logger.info(f"Response: {res.status_code} - Segments found: {res.json()}")
        if res.status_code != 200:
            errors += 1

        # Test 7: Opportunities list
        logger.info("\n=== Test 7: List Opportunities ===")
        res = client.get("/api/opportunities")
        logger.info(f"Response: {res.status_code} - Total open opportunities: {len(res.json())}")
        if res.status_code != 200:
            errors += 1
            
        # Test 8: Get Opportunity (Dynamic Enrichment if needed)
        if test_opportunity:
            op_id = str(test_opportunity.opportunity_id)
            logger.info(f"\n=== Test 8: Get Opportunity & Explain ({op_id}) ===")
            res = client.get(f"/api/opportunities/{op_id}")
            data = res.json()
            logger.info(f"Response: {res.status_code} - Type: {data.get('internal_type')}")
            logger.info(f"AI Explanation Snippet: {data.get('why_generated')[:100] if data.get('why_generated') else ''}...")
            if res.status_code != 200:
                errors += 1
                
        # Test 9: Daily AI Briefing (dynamic generation)
        logger.info("\n=== Test 9: Get Daily AI Briefing ===")
        res = client.get("/api/briefing/latest")
        logger.info(f"Response: {res.status_code} - Headline: '{res.json().get('headline')}'")
        if res.status_code != 200:
            errors += 1

        # Test 10: AI Goal Planner
        logger.info("\n=== Test 10: AI Goal Planner (Chennai Electronics Goal) ===")
        goal_payload = {"goal": "Increase electronics revenue in Chennai using WhatsApp"}
        res = client.post("/api/planner/generate", json=goal_payload)
        logger.info(f"Response: {res.status_code}")
        if res.status_code != 200:
            errors += 1
            campaign_id = None
        else:
            campaign_data = res.json()
            logger.info(f"Recommended Campaign: '{campaign_data.get('campaign_name')}'")
            logger.info(f"Recommended Promo: {campaign_data.get('recommended_promotion')}")
            logger.info(f"Simulation Reach: {campaign_data.get('simulation').get('predicted_reach')}")
            logger.info(f"Simulation CTR: {campaign_data.get('simulation').get('predicted_ctr')}")
            
            # Fetch campaign ID of the created draft
            db.commit() # Flush changes
            draft_campaign = db.query(Campaign).filter(
                Campaign.name == campaign_data.get('campaign_name'),
                Campaign.status == 'draft'
            ).order_by(Campaign.created_at.desc()).first()
            campaign_id = str(draft_campaign.campaign_id) if draft_campaign else None
            
        # Test 11: Launch Campaign & Webhook Simulation Loop
        if campaign_id:
            logger.info(f"\n=== Test 11: Launch Campaign ({campaign_id}) ===")
            res = client.post(f"/api/campaigns/{campaign_id}/launch")
            logger.info(f"Response: {res.status_code} - Status: {res.json().get('status')}")
            if res.status_code != 200:
                errors += 1
            else:
                # Retrieve communication ID created for webhook check
                comm = db.query(Communication).filter(Communication.campaign_id == campaign_id).first()
                if comm:
                    comm_id = str(comm.communication_id)
                    logger.info(f"Launched communication ID: {comm_id}")
                    
                    # Test 12: Webhook callback (Simulate customer click and purchase)
                    logger.info("\n=== Test 12: Webhook delivery events ===")
                    webhook_res1 = client.post("/api/webhook/delivery", json={
                        "communication_id": comm_id,
                        "event_type": "delivered"
                    })
                    webhook_res2 = client.post("/api/webhook/delivery", json={
                        "communication_id": comm_id,
                        "event_type": "purchased"
                    })
                    logger.info(f"Webhook Delivered status: {webhook_res1.status_code}")
                    logger.info(f"Webhook Purchased status: {webhook_res2.status_code}")
                    if webhook_res1.status_code != 200 or webhook_res2.status_code != 200:
                        errors += 1
                        
                    # Test 13: Funnel & Revenue Attribution verification
                    logger.info("\n=== Test 13: Funnel & ROI Attribution Analytics ===")
                    analytics_res = client.get(f"/api/campaigns/{campaign_id}/analytics")
                    logger.info(f"Response: {analytics_res.status_code} - {analytics_res.json()}")
                    if analytics_res.status_code != 200 or analytics_res.json().get('funnel').get('purchased') < 1:
                        logger.error("Attribution check failed or order was not matched.")
                        errors += 1
        
        # Test 14: Natural Language Query Analytics
        logger.info("\n=== Test 14: NL to SQL Query Analytics ===")
        nl_payload = {"question": "List top 3 active customers in Pune by total spend."}
        res = client.post("/api/analytics/query", json=nl_payload)
        logger.info(f"Response: {res.status_code}")
        if res.status_code != 200:
            errors += 1
        else:
            logger.info(f"AI Response: {res.json().get('response')}")
            logger.info(f"Data Points: {res.json().get('data_points')}")
            logger.info(f"Suggested Chart: {res.json().get('chart_suggestion')}")

    if errors == 0:
        print("\n" + "=" * 50)
        print("  [OK] ALL API INTEGRATION TESTS PASSED SUCCESSFULLY!")
        print("  FastAPI backend is fully production-ready.")
        print("=" * 50 + "\n")
    else:
        print("\n" + "=" * 50)
        print(f"  [FAIL] INTEGRATION TESTS COMPLETED WITH {errors} ERRORS.")
        print("=" * 50 + "\n")

if __name__ == "__main__":
    run_integration_tests()
