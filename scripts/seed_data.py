"""
Xenia CRM – Synthetic Data Generator
Generates realistic shopper CRM data for 10,000 customers, 500 products,
80,000+ orders, campaigns, communications, and delivery events.
"""

import os
import sys
import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import insert, text
from faker import Faker

from app.database import db_session
from app.models.customer import Customer
from app.models.product import Product
from app.models.promotion import Promotion
from app.models.order import Order, OrderItem
from app.models.campaign import Campaign, Communication, CommunicationEvent, CampaignMetrics

# Configuration
NUM_CUSTOMERS = 10000
NUM_PRODUCTS = 500
TARGET_ORDERS_COUNT = 80000

print("=" * 60)
print("  Xenia CRM – Synthetic Data Generator")
print("=" * 60)

# Initialize Faker with Indian locale for realistic names and addresses
fake = Faker('en_IN')

# Seed random number generators for reproducibility
random.seed(42)
Faker.seed(42)

# Helper: Random date between start and end
def random_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    random_days = random.randint(0, max(0, delta.days))
    random_seconds = random.randint(0, 86400)
    return start + timedelta(days=random_days, seconds=random_seconds)

def seed_data():
    now = datetime.now(timezone.utc)
    two_years_ago = now - timedelta(days=730)
    one_year_ago = now - timedelta(days=365)

    with db_session() as db:
        # ──────────────────────────────────────────────────────────────────────
        # 1. SEED PROMOTIONS
        # ──────────────────────────────────────────────────────────────────────
        print("\nStep 1: Seeding promotions...")
        promotions_data = [
            {
                "promotion_id": uuid.uuid4(),
                "name": "Diwali Electronics Flash",
                "description": "20% off all Electronics items",
                "category": "Electronics",
                "discount_percentage": Decimal("20.00"),
                "min_order_value": Decimal("5000.00"),
                "active": True,
                "promo_code": "DIWALI20",
                "discount_type": "Percentage",
                "discount_value": Decimal("20.00"),
                "applicable_categories": "Electronics",
                "applicable_cities": "ALL",
                "start_date": now - timedelta(days=60),
                "end_date": now + timedelta(days=120),
                "max_usage_limit": 1000
            },
            {
                "promotion_id": uuid.uuid4(),
                "name": "Supermarket Essentials BOGO",
                "description": "10% off groceries",
                "category": "Groceries",
                "discount_percentage": Decimal("10.00"),
                "min_order_value": Decimal("1000.00"),
                "active": True,
                "promo_code": "GROCERY10",
                "discount_type": "Percentage",
                "discount_value": Decimal("10.00"),
                "applicable_categories": "Groceries",
                "applicable_cities": "ALL",
                "start_date": now - timedelta(days=60),
                "end_date": now + timedelta(days=120),
                "max_usage_limit": 5000
            },
            {
                "promotion_id": uuid.uuid4(),
                "name": "Beauty Glow Days",
                "description": "15% off skin care and cosmetics",
                "category": "Beauty",
                "discount_percentage": Decimal("15.00"),
                "min_order_value": Decimal("1500.00"),
                "active": True,
                "promo_code": "BEAUTY15",
                "discount_type": "Percentage",
                "discount_value": Decimal("15.00"),
                "applicable_categories": "Beauty",
                "applicable_cities": "ALL",
                "start_date": now - timedelta(days=60),
                "end_date": now + timedelta(days=120),
                "max_usage_limit": 2000
            },
            {
                "promotion_id": uuid.uuid4(),
                "name": "Fit India Gear Sale",
                "description": "12% off sports gear and fitness supplements",
                "category": "Sports",
                "discount_percentage": Decimal("12.00"),
                "min_order_value": Decimal("2000.00"),
                "active": True,
                "promo_code": "FITNESS12",
                "discount_type": "Percentage",
                "discount_value": Decimal("12.00"),
                "applicable_categories": "Sports",
                "applicable_cities": "ALL",
                "start_date": now - timedelta(days=60),
                "end_date": now + timedelta(days=120),
                "max_usage_limit": 1500
            },
            {
                "promotion_id": uuid.uuid4(),
                "name": "Sports Weekend Reactivation",
                "description": "5% off Sports products",
                "category": "Sports",
                "discount_percentage": Decimal("5.00"),
                "min_order_value": Decimal("0.00"),
                "active": True,
                "promo_code": "SPORT5",
                "discount_type": "Percentage",
                "discount_value": Decimal("5.00"),
                "applicable_categories": "Sports",
                "applicable_cities": "Chennai,Mumbai,Bengaluru",
                "start_date": now - timedelta(days=30),
                "end_date": now + timedelta(days=60),
                "max_usage_limit": 500
            },
            {
                "promotion_id": uuid.uuid4(),
                "name": "Baby & Toy Carnival",
                "description": "8% off diapers, toys, and baby care",
                "category": "Baby Products",
                "discount_percentage": Decimal("8.00"),
                "min_order_value": Decimal("1200.00"),
                "active": True,
                "promo_code": "BABY8",
                "discount_type": "Percentage",
                "discount_value": Decimal("8.00"),
                "applicable_categories": "Baby Products",
                "applicable_cities": "ALL",
                "start_date": now - timedelta(days=60),
                "end_date": now + timedelta(days=120),
                "max_usage_limit": 800
            },
            {
                "promotion_id": uuid.uuid4(),
                "name": "Welcome shoppers discount",
                "description": "15% off first purchase",
                "category": None,
                "discount_percentage": Decimal("15.00"),
                "min_order_value": Decimal("500.00"),
                "active": True,
                "promo_code": "WELCOME15",
                "discount_type": "Percentage",
                "discount_value": Decimal("15.00"),
                "applicable_categories": "ALL",
                "applicable_cities": "ALL",
                "start_date": now - timedelta(days=365),
                "end_date": now + timedelta(days=365),
                "max_usage_limit": 10000
            },
            {
                "promotion_id": uuid.uuid4(),
                "name": "Exclusive Win-Back Deal",
                "description": "25% off storewide for reactivated members",
                "category": None,
                "discount_percentage": Decimal("25.00"),
                "min_order_value": Decimal("1000.00"),
                "active": True,
                "promo_code": "WINBACK25",
                "discount_type": "Percentage",
                "discount_value": Decimal("25.00"),
                "applicable_categories": "ALL",
                "applicable_cities": "ALL",
                "start_date": now - timedelta(days=180),
                "end_date": now + timedelta(days=180),
                "max_usage_limit": 5000
            }
        ]

        # Delete existing data to avoid conflicts on re-runs
        print("Clearing old data...")
        db.execute(text("TRUNCATE TABLE customers, products, promotions, opportunities, campaigns, communications, orders, order_items, communication_events, customer_metrics, customer_segments, customer_insights, campaign_simulations, campaign_metrics, daily_briefings, nl_queries RESTART IDENTITY CASCADE;"))
        db.commit()

        db.execute(insert(Promotion), promotions_data)
        print(f"[OK] Seeded {len(promotions_data)} promotions.")

        # Save promo dict for mapping later
        promos_by_code = {p["promo_code"]: p for p in promotions_data}

        # ──────────────────────────────────────────────────────────────────────
        # 2. SEED PRODUCTS
        # ──────────────────────────────────────────────────────────────────────
        print("\nStep 2: Seeding products...")
        product_categories = [
            ("Electronics", 1500, 95000, ["Phone", "Laptop", "Headphones", "Smartwatch", "Tablet", "Charger", "Keyboard", "Mouse", "Monitor"]),
            ("Groceries", 30, 800, ["Milk", "Bread", "Rice 5kg", "Atta 5kg", "Sugar 1kg", "Tea", "Coffee", "Cooking Oil 1L", "Butter", "Biscuits"]),
            ("Beauty", 100, 3000, ["Shampoo", "Face Wash", "Moisturizer", "Lipstick", "Sunscreen", "Serum", "Hair Oil", "Conditioner"]),
            ("Fashion", 300, 8000, ["Jeans", "T-Shirt", "Shirt", "Sneakers", "Kurta", "Dress", "Socks", "Jacket", "Watch"]),
            ("Sports", 200, 12000, ["Football", "Cricket Bat", "Badminton Racket", "Yoga Mat", "Dumbbells", "Running Shoes", "Water Bottle"]),
            ("Home & Kitchen", 150, 15000, ["Bedsheet", "Pressure Cooker", "Toaster", "Air Fryer", "Dinner Set", "Water Purifier", "Kettle"]),
            ("Baby Products", 100, 4000, ["Diapers", "Baby Lotion", "Baby Food", "Wipes", "Baby Toy", "Stroller"]),
            ("Books", 150, 1500, ["Novel", "Biography", "Self-Help Book", "Textbook", "Comic Book", "Sci-Fi Novel"]),
            ("Health", 50, 5000, ["Multivitamins", "Protein Powder 1kg", "BP Monitor", "Masks Pack", "Sanitizer", "Omega 3 Capsule"]),
            ("Pet Supplies", 100, 4000, ["Dog Food 3kg", "Cat Food 1kg", "Pet Shampoo", "Chew Toy", "Leash", "Cat Litter"])
        ]

        brands_by_cat = {
            "Electronics": ["Apple", "Samsung", "Sony", "Dell", "OnePlus", "HP", "Lenovo", "Logitech", "Xiaomi", "boAt", "Noise", "LG", "Philips"],
            "Groceries": ["Amul", "Aashirvaad", "Fortune", "Tata", "Surf Excel", "Tropicana", "Nescafe", "Britannia", "Haldiram's", "Catch", "Dabur"],
            "Beauty": ["L'Oreal", "Maybelline", "Nivea", "Mamaearth", "Cetaphil", "Lakme", "Plum", "The Derma Co", "Clinique", "Neutrogena"],
            "Fashion": ["Levi's", "Allen Solly", "Adidas", "Puma", "Biba", "Titan", "Zara", "H&M", "USPA", "Tommy Hilfiger"],
            "Sports": ["Nivia", "SG", "Yonex", "Decathlon", "Fitbit", "Adidas", "Puma", "Nike", "Cosco", "Speedo"],
            "Home & Kitchen": ["Pigeon", "Philips", "Prestige", "Milton", "Solimo", "Usha", "Kent", "Bajaj", "Wonderchef", "Hawkins"],
            "Baby Products": ["Pampers", "Himalaya", "Nestle", "Sebamed", "Johnson's", "Fisher-Price", "Mee Mee", "LuvLap"],
            "Books": ["Penguin", "HarperCollins", "Rupa", "Westland", "Bloomsbury", "Scholastic", "Vintage"],
            "Health": ["Revital", "Optimum Nutrition", "Dettol", "Himalaya", "Dr. Trust", "Apollo", "MuscleBlaze", "GNC"],
            "Pet Supplies": ["Pedigree", "Whiskas", "Drools", "Royal Canin", "Pet Head", "Kong", "Purina", "Meat Up"]
        }

        products_data = []
        sku_set = set()
        
        # We need 500 products, let's generate exactly 50 per category
        for cat_name, min_p, max_p, noun_list in product_categories:
            cat_brands = brands_by_cat[cat_name]
            for i in range(50):
                brand = random.choice(cat_brands)
                noun = random.choice(noun_list)
                name = f"{brand} {noun} v{random.randint(1, 9)}" if cat_name == "Electronics" else f"{brand} {noun}"
                
                # Check SKU uniqueness
                sku = f"{cat_name[:3].upper()}-{brand[:3].upper()}-{random.randint(1000, 9999)}"
                while sku in sku_set:
                    sku = f"{cat_name[:3].upper()}-{brand[:3].upper()}-{random.randint(1000, 9999)}"
                sku_set.add(sku)

                # Price distribution: exponentially skewed towards lower prices for realism
                price = Decimal(str(round(random.uniform(min_p, min_p + (max_p - min_p) * random.random()**2), 2)))

                products_data.append({
                    "product_id": uuid.uuid4(),
                    "name": name,
                    "category": cat_name,
                    "price": price,
                    "brand": brand,
                    "sku": sku
                })

        db.execute(insert(Product), products_data)
        print(f"[OK] Seeded {len(products_data)} products.")

        # Group products by category for easy selection during order generation
        products_by_category = {}
        for p in products_data:
            products_by_category.setdefault(p["category"], []).append(p)

        # ──────────────────────────────────────────────────────────────────────
        # 3. SEED CUSTOMERS
        # ──────────────────────────────────────────────────────────────────────
        print("\nStep 3: Seeding customers...")
        cities = ["Chennai", "Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Pune", "Kolkata", "Ahmedabad", "Jaipur", "Lucknow"]
        personas = [
            "Champion", "High Value", "At Risk", "Lost", "Electronics Enthusiast",
            "Grocery Loyalist", "Fitness Shopper", "Young Family", "Discount Hunter"
        ]
        persona_weights = [10, 15, 12, 8, 10, 15, 8, 10, 12] # sums to 100

        customers_data = []
        customer_personas = {} # customer_id -> persona

        for _ in range(NUM_CUSTOMERS):
            customer_id = uuid.uuid4()
            name = fake.name()
            # unique email generation
            email = name.lower().replace(" ", "").replace(".", "") + str(random.randint(10, 99999)) + "@example.com"
            phone = "+91 " + str(random.randint(6, 9)) + str(random.randint(100000000, 999999999))
            city = random.choice(cities)
            
            # Join date between 24 and 12 months ago
            join_date = random_date(two_years_ago, one_year_ago)
            
            persona = random.choices(personas, weights=persona_weights, k=1)[0]
            customer_personas[customer_id] = persona

            customers_data.append({
                "customer_id": customer_id,
                "name": name,
                "email": email,
                "phone": phone,
                "city": city,
                "join_date": join_date
            })

        # Insert in batches of 2000
        for i in range(0, len(customers_data), 2000):
            db.execute(insert(Customer), customers_data[i:i+2000])
        print(f"[OK] Seeded {len(customers_data)} customers.")

        # Save customer dict for mapping
        customers_by_id = {c["customer_id"]: c for c in customers_data}

        # ──────────────────────────────────────────────────────────────────────
        # 4. SEED ORDERS & ORDER ITEMS
        # ──────────────────────────────────────────────────────────────────────
        print("\nStep 4: Seeding orders...")
        orders_data = []
        order_items_data = []
        
        # Keep track of last order date per customer to help with Churn/At Risk labeling
        customer_last_order_date = {}

        for c_id, persona in customer_personas.items():
            customer = customers_by_id[c_id]
            join_date = customer["join_date"]

            # Set order frequency and count based on persona
            if persona == "Champion":
                num_orders = random.randint(12, 24)
                avg_interval_days = 20
                cats_weights = {"Electronics": 0.15, "Groceries": 0.15, "Beauty": 0.1, "Fashion": 0.2, "Sports": 0.1, "Home & Kitchen": 0.1, "Baby Products": 0.05, "Books": 0.05, "Health": 0.05, "Pet Supplies": 0.05}
                order_date_limit = now - timedelta(days=random.randint(1, 14)) # recency < 15 days
            elif persona == "High Value":
                num_orders = random.randint(8, 15)
                avg_interval_days = 35
                cats_weights = {"Electronics": 0.2, "Groceries": 0.1, "Beauty": 0.1, "Fashion": 0.2, "Sports": 0.1, "Home & Kitchen": 0.1, "Baby Products": 0.05, "Books": 0.05, "Health": 0.05, "Pet Supplies": 0.05}
                order_date_limit = now - timedelta(days=random.randint(1, 28)) # recency < 30 days
            elif persona == "At Risk":
                num_orders = random.randint(6, 12)
                avg_interval_days = 45
                cats_weights = {"Electronics": 0.1, "Groceries": 0.15, "Beauty": 0.1, "Fashion": 0.15, "Sports": 0.1, "Home & Kitchen": 0.1, "Baby Products": 0.1, "Books": 0.05, "Health": 0.05, "Pet Supplies": 0.1}
                # Last order is 45-90 days ago
                order_date_limit = now - timedelta(days=random.randint(45, 90))
            elif persona == "Lost":
                num_orders = random.randint(3, 6)
                avg_interval_days = 60
                cats_weights = {"Electronics": 0.1, "Groceries": 0.2, "Beauty": 0.1, "Fashion": 0.1, "Sports": 0.05, "Home & Kitchen": 0.1, "Baby Products": 0.1, "Books": 0.05, "Health": 0.1, "Pet Supplies": 0.1}
                # Last order is 90-360 days ago
                order_date_limit = now - timedelta(days=random.randint(91, 360))
            elif persona == "Electronics Enthusiast":
                num_orders = random.randint(5, 10)
                avg_interval_days = 60
                cats_weights = {"Electronics": 0.70, "Fashion": 0.1, "Sports": 0.05, "Home & Kitchen": 0.05, "Books": 0.05, "Groceries": 0.05}
                order_date_limit = now - timedelta(days=random.randint(1, 45))
            elif persona == "Grocery Loyalist":
                num_orders = random.randint(25, 45)
                avg_interval_days = 7
                cats_weights = {"Groceries": 0.85, "Home & Kitchen": 0.05, "Health": 0.05, "Baby Products": 0.05}
                order_date_limit = now - timedelta(days=random.randint(1, 7))
            elif persona == "Fitness Shopper":
                num_orders = random.randint(6, 12)
                avg_interval_days = 30
                cats_weights = {"Sports": 0.50, "Health": 0.30, "Fashion": 0.1, "Groceries": 0.05, "Pet Supplies": 0.05}
                order_date_limit = now - timedelta(days=random.randint(1, 30))
            elif persona == "Young Family":
                num_orders = random.randint(8, 15)
                avg_interval_days = 25
                cats_weights = {"Baby Products": 0.40, "Groceries": 0.30, "Books": 0.20, "Home & Kitchen": 0.10}
                order_date_limit = now - timedelta(days=random.randint(1, 20))
            else: # Discount Hunter
                num_orders = random.randint(6, 12)
                avg_interval_days = 40
                cats_weights = {"Fashion": 0.2, "Beauty": 0.2, "Groceries": 0.2, "Electronics": 0.1, "Home & Kitchen": 0.1, "Sports": 0.1, "Books": 0.1}
                order_date_limit = now - timedelta(days=random.randint(1, 45))

            # Generate individual order dates starting from join_date up to order_date_limit
            order_dates = []
            current_date = join_date
            
            # Generate historical times up to limit
            for i in range(num_orders):
                if current_date > order_date_limit:
                    break
                order_dates.append(current_date)
                # Next order in average interval
                current_date += timedelta(days=max(1, int(random.normalvariate(avg_interval_days, avg_interval_days / 4))))
            
            if not order_dates:
                order_dates.append(join_date)

            # Ensure the last order date is set exactly to the target recency if needed (At Risk / Lost)
            if persona in ["At Risk", "Lost"] and len(order_dates) > 1:
                # Force last date to be within range
                order_dates[-1] = order_date_limit

            customer_last_order_date[c_id] = order_dates[-1]

            # Generate order records
            for order_date in order_dates:
                order_id = uuid.uuid4()
                
                # Select categories based on persona weights
                cat_choices = list(cats_weights.keys())
                cat_weights = list(cats_weights.values())
                
                num_items = random.choices([1, 2, 3, 4], weights=[40, 30, 20, 10], k=1)[0]
                
                # Pick unique items for this order
                chosen_products = []
                selected_cats = random.choices(cat_choices, weights=cat_weights, k=num_items)
                
                for cat in selected_cats:
                    if cat in products_by_category and products_by_category[cat]:
                        chosen_products.append(random.choice(products_by_category[cat]))

                order_total = Decimal("0.00")
                
                # Create Order Items
                for prod in chosen_products:
                    qty = 1 if prod["category"] == "Electronics" else random.choices([1, 2, 3, 5], weights=[60, 20, 10, 10], k=1)[0]
                    price = prod["price"]
                    subtotal = price * qty
                    order_total += subtotal

                    order_items_data.append({
                        "order_item_id": uuid.uuid4(),
                        "order_id": order_id,
                        "product_id": prod["product_id"],
                        "quantity": qty,
                        "unit_price": price
                    })
                
                # Apply simulated discount code for Discount Hunter (or with 20% probability for others)
                discount_percentage = Decimal("0.00")
                if (persona == "Discount Hunter" and random.random() < 0.85) or (random.random() < 0.20):
                    # Pick a promotion
                    rel_promo = None
                    # Try to match category
                    primary_cat = chosen_products[0]["category"] if chosen_products else None
                    matching_promos = [p for p in promotions_data if p["category"] == primary_cat]
                    if matching_promos:
                        rel_promo = random.choice(matching_promos)
                    else:
                        rel_promo = random.choice([p for p in promotions_data if p["category"] is None])
                    
                    if rel_promo and order_total >= rel_promo["min_order_value"]:
                        discount_percentage = rel_promo["discount_percentage"]
                        order_total = order_total * (Decimal("100.00") - discount_percentage) / Decimal("100.00")

                orders_data.append({
                    "order_id": order_id,
                    "customer_id": c_id,
                    "order_date": order_date,
                    "total_amount": Decimal(str(round(order_total, 2))),
                    "attributed_communication_id": None # Attributed later in step 5
                })

        # Insert orders in batches of 5000
        print(f"Bulk inserting {len(orders_data)} orders...")
        for i in range(0, len(orders_data), 5000):
            db.execute(insert(Order), orders_data[i:i+5000])

        # Insert order items in batches of 10000
        print(f"Bulk inserting {len(order_items_data)} order items...")
        for i in range(0, len(order_items_data), 10000):
            db.execute(insert(OrderItem), order_items_data[i:i+10000])

        print(f"[OK] Seeded {len(orders_data)} orders and {len(order_items_data)} items.")

        # ──────────────────────────────────────────────────────────────────────
        # 5. SEED CAMPAIGNS & COMMUNICATIONS & ENGAGEMENT EVENTS
        # ──────────────────────────────────────────────────────────────────────
        print("\nStep 5: Seeding campaign engagement history...")
        
        # Campaigns definition
        campaign_definitions = [
            {
                "name": "Diwali Mega Electronics Fest",
                "objective": "Increase repeat electronics sales in high-value clusters",
                "promo_code": "DIWALI20",
                "channel": "WhatsApp",
                "launch_days_ago": 240, # Oct 2025
                "target_persona_subset": ["Champion", "High Value", "Electronics Enthusiast"],
                "base_open_rate": 0.82,
                "base_click_rate": 0.45,
                "base_cvr_rate": 0.28,
            },
            {
                "name": "New Year Healthy Habits Push",
                "objective": "Target fitness enthusiasts and health buyers",
                "promo_code": "FITNESS12",
                "channel": "Email",
                "launch_days_ago": 160, # Jan 2026
                "target_persona_subset": ["Fitness Shopper", "Champion", "Grocery Loyalist"],
                "base_open_rate": 0.45,
                "base_click_rate": 0.20,
                "base_cvr_rate": 0.12,
            },
            {
                "name": "Weekly Grocery Restock Club",
                "objective": "Encourage high-frequency grocery loyalist purchases",
                "promo_code": "GROCERY10",
                "channel": "WhatsApp",
                "launch_days_ago": 120, # Feb 2026
                "target_persona_subset": ["Grocery Loyalist", "Young Family"],
                "base_open_rate": 0.88,
                "base_click_rate": 0.52,
                "base_cvr_rate": 0.38,
            },
            {
                "name": "Spring Style & Apparel Launch",
                "objective": "Promote new fashion arrivals",
                "promo_code": "WELCOME15",
                "channel": "SMS",
                "launch_days_ago": 90, # Mar 2026
                "target_persona_subset": ["Discount Hunter", "Champion", "High Value"],
                "base_open_rate": 0.35,
                "base_click_rate": 0.15,
                "base_cvr_rate": 0.08,
            },
            {
                "name": "Toddler Care & Toy Carnival",
                "objective": "Drive sales in baby and books categories",
                "promo_code": "BABY8",
                "channel": "Email",
                "launch_days_ago": 60, # Apr 2026
                "target_persona_subset": ["Young Family", "High Value"],
                "base_open_rate": 0.55,
                "base_click_rate": 0.28,
                "base_cvr_rate": 0.15,
            },
            {
                "name": "Win Back Silent Champions",
                "objective": "Re-engage champions that have drifted",
                "promo_code": "WINBACK25",
                "channel": "WhatsApp",
                "launch_days_ago": 30, # May 2026
                "target_persona_subset": ["At Risk", "Lost", "Discount Hunter"],
                "base_open_rate": 0.65,
                "base_click_rate": 0.32,
                "base_cvr_rate": 0.22,
            },
            {
                "name": "Summer Glow Beauty Days",
                "objective": "Target cosmetics and personal care buyers",
                "promo_code": "BEAUTY15",
                "channel": "SMS",
                "launch_days_ago": 15, # May 2026
                "target_persona_subset": ["Champion", "High Value", "Discount Hunter"],
                "base_open_rate": 0.38,
                "base_click_rate": 0.18,
                "base_cvr_rate": 0.10,
            },
            {
                "name": "Weekend Cookout Flash Sale",
                "objective": "Promote cookers and airfryers",
                "promo_code": "FRESH5",
                "channel": "Email",
                "launch_days_ago": 5, # Jun 2026
                "target_persona_subset": ["Grocery Loyalist", "Young Family", "Home & Kitchen"],
                "base_open_rate": 0.40,
                "base_click_rate": 0.15,
                "base_cvr_rate": 0.05,
            }
        ]

        campaigns_created = []
        all_communications = []
        all_events = []

        # Find orders locally to link attribution quickly without hitting SQL in loops
        orders_by_customer = {}
        for o in orders_data:
            orders_by_customer.setdefault(o["customer_id"], []).append(o)

        for cdef in campaign_definitions:
            campaign_id = uuid.uuid4()
            launch_date = now - timedelta(days=cdef["launch_days_ago"])
            
            # Map promo code
            promo = promos_by_code.get(cdef["promo_code"])
            promo_id = promo["promotion_id"] if promo else None
            
            campaigns_created.append({
                "campaign_id": campaign_id,
                "name": cdef["name"],
                "objective": cdef["objective"],
                "promotion_id": promo_id,
                "channel": cdef["channel"],
                "status": "completed",
                "ai_strategy": {
                    "audience_description": f"Targeting {', '.join(cdef['target_persona_subset'])} segment",
                    "priority": "High",
                    "expected_impact": "High ROI",
                    "confidence_score": 0.85
                },
                "message_template": f"Exclusive offer for you! Use code {cdef['promo_code']} to save more on your favorite items. Valid for 7 days only!",
                "message_variants": [
                    f"Hey {{name}}, don't miss out! Use code {cdef['promo_code']} for special savings.",
                    f"Hi {{name}}, handpicked deals just for you. Save extra with {cdef['promo_code']}."
                ],
                "target_segment": f"Personas: {', '.join(cdef['target_persona_subset'])}",
                "target_audience_size": 0, # Calculated dynamically below
                "opportunity_id": None,
                "created_at": launch_date - timedelta(days=3),
                "launched_at": launch_date,
                "completed_at": launch_date + timedelta(days=7)
            })

            # Select targeted customers
            subset_personas = set(cdef["target_persona_subset"])
            targeted_customers = [
                cust for cust in customers_data
                if customer_personas[cust["customer_id"]] in subset_personas
            ]
            
            # Limit audience size to a max of 2500 per campaign to keep seed data balanced
            if len(targeted_customers) > 2500:
                targeted_customers = random.sample(targeted_customers, 2500)
            
            # Update audience size in campaign mapping
            campaigns_created[-1]["target_audience_size"] = len(targeted_customers)

            for cust in targeted_customers:
                c_id = cust["customer_id"]
                comm_id = uuid.uuid4()

                # Personalize template
                personalized_message = campaigns_created[-1]["message_template"].replace("{name}", cust["name"])

                # Determine individual channel status (delivered/failed)
                delivered = random.random() < 0.92
                status = "delivered" if delivered else "failed"

                all_communications.append({
                    "communication_id": comm_id,
                    "campaign_id": campaign_id,
                    "customer_id": c_id,
                    "channel": cdef["channel"],
                    "message_sent": personalized_message,
                    "status": status,
                    "created_at": launch_date
                })

                # Event timestamp offsets
                delivered_time = launch_date + timedelta(minutes=random.randint(1, 15))
                opened_time = delivered_time + timedelta(minutes=random.randint(5, 120))
                clicked_time = opened_time + timedelta(minutes=random.randint(2, 30))
                purchased_time = clicked_time + timedelta(days=random.randint(0, 5))

                if delivered:
                    all_events.append({
                        "event_id": uuid.uuid4(),
                        "communication_id": comm_id,
                        "event_type": "delivered",
                        "event_timestamp": delivered_time,
                        "metadata_json": {}
                    })

                    # Open probability adjusted by customer persona
                    c_persona = customer_personas[c_id]
                    persona_open_mod = 1.0
                    if c_persona == "Champion":
                        persona_open_mod = 1.2
                    elif c_persona == "Lost":
                        persona_open_mod = 0.2
                    elif c_persona == "At Risk":
                        persona_open_mod = 0.5
                    
                    opened = random.random() < (cdef["base_open_rate"] * persona_open_mod)
                    if opened:
                        all_events.append({
                            "event_id": uuid.uuid4(),
                            "communication_id": comm_id,
                            "event_type": "opened",
                            "event_timestamp": opened_time,
                            "metadata_json": {}
                        })

                        # Click probability
                        clicked = random.random() < (cdef["base_click_rate"] * (1.2 if c_persona == "Champion" else 0.8))
                        if clicked:
                            all_events.append({
                                "event_id": uuid.uuid4(),
                                "communication_id": comm_id,
                                "event_type": "clicked",
                                "event_timestamp": clicked_time,
                                "metadata_json": {}
                            })

                            # Purchase probability within 7 days
                            purchased = random.random() < (cdef["base_cvr_rate"] * (1.3 if c_persona == "Champion" else 0.7))
                            if purchased:
                                # Find if customer placed any order in the 7 days after clicked_time
                                customer_orders = orders_by_customer.get(c_id, [])
                                window_start = clicked_time
                                window_end = clicked_time + timedelta(days=7)
                                
                                matching_orders = [
                                    ord for ord in customer_orders
                                    if window_start <= ord["order_date"] <= window_end
                                ]
                                
                                if matching_orders:
                                    # Select the first matching order and link it
                                    order_to_attribute = matching_orders[0]
                                    order_to_attribute["attributed_communication_id"] = comm_id
                                    
                                    all_events.append({
                                        "event_id": uuid.uuid4(),
                                        "communication_id": comm_id,
                                        "event_type": "purchased",
                                        "event_timestamp": order_to_attribute["order_date"],
                                        "metadata_json": {
                                            "order_id": str(order_to_attribute["order_id"]),
                                            "revenue": float(order_to_attribute["total_amount"])
                                        }
                                    })
                else:
                    # Failed event
                    all_events.append({
                        "event_id": uuid.uuid4(),
                        "communication_id": comm_id,
                        "event_type": "failed",
                        "event_timestamp": launch_date,
                        "metadata_json": {"error": "Provider Timeout"}
                    })

        # Bulk Insert Campaigns
        db.execute(insert(Campaign), campaigns_created)
        
        # Bulk Insert Communications in batches of 5000
        print(f"Bulk inserting {len(all_communications)} communications...")
        for i in range(0, len(all_communications), 5000):
            db.execute(insert(Communication), all_communications[i:i+5000])

        # Bulk Insert Events in batches of 10000
        print(f"Bulk inserting {len(all_events)} communication events...")
        for i in range(0, len(all_events), 10000):
            db.execute(insert(CommunicationEvent), all_events[i:i+10000])

        print(f"[OK] Seeded {len(campaigns_created)} campaigns, {len(all_communications)} communications, and {len(all_events)} events.")

        # Update attributed order references in the database
        print("Saving attributed order relations...")
        # Since we modified the dictionaries in orders_data, we need to batch update the Order records in DB
        # To do this quickly, we will execute updates in batches
        attributed_orders = [o for o in orders_data if o["attributed_communication_id"] is not None]
        print(f"Updating {len(attributed_orders)} orders with attribution links...")
        
        # In SQLAlchemy 2.0, we can use bulk update mappings or bulk update statements
        # Since it is a list of orders, we can update them
        for o in attributed_orders:
            db.query(Order).filter(Order.order_id == o["order_id"]).update(
                {"attributed_communication_id": o["attributed_communication_id"]}
            )
        db.commit()

        # ──────────────────────────────────────────────────────────────────────
        # 6. COMPUTE HISTORICAL CAMPAIGN METRICS
        # ──────────────────────────────────────────────────────────────────────
        print("\nStep 6: Computing campaign performance metrics...")
        cost_per_channel = {"WhatsApp": Decimal("0.50"), "SMS": Decimal("0.15"), "Email": Decimal("0.05")}

        metrics_data = []
        for camp in campaigns_created:
            c_id = camp["campaign_id"]
            channel = camp["channel"]
            
            # Count statuses
            comm_list = [c for c in all_communications if c["campaign_id"] == c_id]
            sent_count = len(comm_list)
            
            # Count events from this campaign's communications
            comm_ids = {c["communication_id"] for c in comm_list}
            camp_events = [e for e in all_events if e["communication_id"] in comm_ids]
            
            delivered_count = sum(1 for e in camp_events if e["event_type"] == "delivered")
            opened_count = sum(1 for e in camp_events if e["event_type"] == "opened")
            clicked_count = sum(1 for e in camp_events if e["event_type"] == "clicked")
            purchased_count = sum(1 for e in camp_events if e["event_type"] == "purchased")
            failed_count = sum(1 for e in camp_events if e["event_type"] == "failed")

            # Sum revenue from attributed purchases
            revenue = Decimal("0.00")
            for e in camp_events:
                if e["event_type"] == "purchased" and e["metadata_json"]:
                    revenue += Decimal(str(e["metadata_json"].get("revenue", 0.00)))

            # Estimated campaign cost
            cost = Decimal(str(sent_count)) * cost_per_channel.get(channel, Decimal("0.10"))
            
            # ROI
            roi = None
            if cost > 0:
                roi = float((revenue - cost) / cost * Decimal("100.00"))
            
            conversion_rate = 0.0
            if sent_count > 0:
                conversion_rate = float(purchased_count / sent_count)

            metrics_data.append({
                "campaign_id": c_id,
                "total_sent": sent_count,
                "total_delivered": delivered_count,
                "total_opened": opened_count,
                "total_clicked": clicked_count,
                "total_purchased": purchased_count,
                "total_failed": failed_count,
                "attributed_revenue": Decimal(str(round(revenue, 2))),
                "estimated_cost": Decimal(str(round(cost, 2))),
                "roi": roi,
                "conversion_rate": conversion_rate
            })

        db.execute(insert(CampaignMetrics), metrics_data)
        db.commit()
        print(f"[OK] Computed performance metrics for all {len(metrics_data)} campaigns.")

    print("\n" + "=" * 60)
    print("  [OK] SEEDING COMPLETE!")
    print(f"  Summary:")
    print(f"    - Customers: {NUM_CUSTOMERS}")
    print(f"    - Products: {NUM_PRODUCTS}")
    print(f"    - Orders: {len(orders_data)}")
    print(f"    - Campaigns: {len(campaign_definitions)}")
    print(f"    - Communications: {len(all_communications)}")
    print(f"    - Events: {len(all_events)}")
    print("=" * 60)

if __name__ == "__main__":
    seed_data()
