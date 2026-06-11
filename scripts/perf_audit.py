"""
Xenia CRM - Full API Performance Audit
Measures response times for every endpoint.
"""
import httpx
import time
import json

BASE = "http://localhost:8000"

def measure(label, method, url, **kwargs):
    start = time.perf_counter()
    try:
        if method == "GET":
            r = httpx.get(url, timeout=30, **kwargs)
        else:
            r = httpx.post(url, timeout=30, **kwargs)
        ms = (time.perf_counter() - start) * 1000
        status = r.status_code
        try:
            body = r.json()
            size = len(r.content)
            if isinstance(body, list):
                detail = f"{len(body)} records"
            elif isinstance(body, dict):
                detail = f"keys={list(body.keys())[:4]}"
            else:
                detail = str(body)[:80]
        except:
            detail = r.text[:80]
            size = len(r.content)
        print(f"  {'✅' if status < 400 else '❌'} {label:<45} {ms:>8.0f}ms  [{status}] {detail[:70]}")
        return ms, status
    except Exception as e:
        ms = (time.perf_counter() - start) * 1000
        print(f"  ❌ {label:<45} {ms:>8.0f}ms  [ERR] {e}")
        return ms, 0

print("\n" + "="*90)
print("  XENIA CRM - FULL API PERFORMANCE AUDIT")
print("="*90)

timings = {}

# ── Health ──────────────────────────────────────────────────────────────────
print("\n📌 HEALTH & SYSTEM")
t, _ = measure("Health Check", "GET", f"{BASE}/health")
timings["health"] = t

# ── Daily Briefing ───────────────────────────────────────────────────────────
print("\n📌 DAILY BRIEFING (Home Page dependency)")
t, s = measure("GET /api/briefing/latest", "GET", f"{BASE}/api/briefing/latest")
timings["briefing_latest"] = t
if t > 500:
    print(f"     ⚠️  SLOW! This blocks the Home Page. Root cause: Gemini call if no today's briefing.")

# ── Opportunities (Suggested Actions) ───────────────────────────────────────
print("\n📌 SUGGESTED ACTIONS (Opportunities)")
t, _ = measure("GET /api/opportunities", "GET", f"{BASE}/api/opportunities")
timings["opportunities"] = t

# ── Campaigns ───────────────────────────────────────────────────────────────
print("\n📌 CAMPAIGNS")
t, _ = measure("GET /api/campaigns", "GET", f"{BASE}/api/campaigns")
timings["campaigns_all"] = t
t, _ = measure("GET /api/campaigns?status=draft", "GET", f"{BASE}/api/campaigns", params={"status":"draft"})
timings["campaigns_draft"] = t
t, _ = measure("GET /api/campaigns?status=launched", "GET", f"{BASE}/api/campaigns", params={"status":"launched"})
timings["campaigns_launched"] = t

# ── Promotions ───────────────────────────────────────────────────────────────
print("\n📌 PROMOTIONS")
t, _ = measure("GET /api/promotions", "GET", f"{BASE}/api/promotions")
timings["promotions"] = t

# ── Customers (Shoppers) ─────────────────────────────────────────────────────
print("\n📌 SHOPPERS / CUSTOMERS")
t, _ = measure("GET /api/customers (page 1, 20 rows)", "GET", f"{BASE}/api/customers", params={"page":1,"limit":20})
timings["customers_p1"] = t
t, _ = measure("GET /api/customers/segments", "GET", f"{BASE}/api/customers/segments")
timings["customers_segments"] = t

# Get one customer ID for deep tests
try:
    customers = httpx.get(f"{BASE}/api/customers", params={"limit":1}).json()
    cid = customers[0]["customer_id"] if customers else None
except:
    cid = None

if cid:
    t, _ = measure(f"GET /api/customers/{{id}}/metrics", "GET", f"{BASE}/api/customers/{cid}/metrics")
    timings["customer_metrics"] = t
    t, s = measure(f"GET /api/customers/{{id}}/insights (Gemini!)", "GET", f"{BASE}/api/customers/{cid}/insights")
    timings["customer_insights"] = t
    if t > 1000:
        print(f"     ⚠️  SLOW! Gemini call on every shopper detail open.")
    t, _ = measure(f"GET /api/customers/{{id}}/story", "GET", f"{BASE}/api/customers/{cid}/story")
    timings["customer_story"] = t

# ── Analytics ────────────────────────────────────────────────────────────────
print("\n📌 ANALYTICS")
t, _ = measure("GET /api/analytics/history", "GET", f"{BASE}/api/analytics/history")
timings["analytics_history"] = t

# ── Planner Prepare Context ──────────────────────────────────────────────────
print("\n📌 PLANNER - PREPARE CONTEXT")
try:
    opps = httpx.get(f"{BASE}/api/opportunities").json()
    opp_id = opps[0]["opportunity_id"] if opps else None
except:
    opp_id = None

if opp_id:
    t, s = measure("GET /api/planner/prepare-context", "GET", f"{BASE}/api/planner/prepare-context", params={"opportunity_id": opp_id})
    timings["planner_prepare"] = t
    if t > 500:
        print(f"     ⚠️  SLOW! This runs on every opportunity selection in Prepare Campaign.")
else:
    print("  ⚠️  No opportunity found to test prepare-context")

# ── Planner Generate (Gemini) ─────────────────────────────────────────────────
print("\n📌 PLANNER - GENERATE (INTENTIONAL Gemini Call)")
t, s = measure("POST /api/planner/generate (Gemini)", "POST", f"{BASE}/api/planner/generate",
               json={"goal": "Re-engage inactive sports shoppers in Chennai"})
timings["planner_generate"] = t
print(f"     ℹ️  Expected: 2000-5000ms (AI generation is intentional)")

# ── Campaign Analytics ────────────────────────────────────────────────────────
print("\n📌 CAMPAIGN ANALYTICS (if launched campaigns exist)")
try:
    camps = httpx.get(f"{BASE}/api/campaigns", params={"status":"launched"}).json()
    camp_id = camps[0]["campaign_id"] if camps else None
except:
    camp_id = None

if camp_id:
    t, s = measure("GET /api/campaigns/{id}/analytics", "GET", f"{BASE}/api/campaigns/{camp_id}/analytics")
    timings["campaign_analytics"] = t
    if t > 500:
        print(f"     ⚠️  SLOW! analytics runs attribution pipeline on every load.")
    t, _ = measure("GET /api/campaigns/{id}/recipients", "GET", f"{BASE}/api/campaigns/{camp_id}/recipients")
    timings["campaign_recipients"] = t
else:
    print("  ℹ️  No launched campaigns to test analytics")

# ── SUMMARY ──────────────────────────────────────────────────────────────────
print("\n" + "="*90)
print("  PERFORMANCE SUMMARY")
print("="*90)
print(f"  {'Endpoint':<50} {'Time':>10}  {'Status'}")
print(f"  {'-'*50} {'-'*10}  {'-'*15}")

targets = {
    "briefing_latest":    (500,  "Home page load - MUST be fast"),
    "opportunities":      (300,  "Suggested Actions list"),
    "campaigns_all":      (300,  "Campaigns list"),
    "promotions":         (200,  "Promotions list"),
    "customers_p1":       (300,  "Shoppers list"),
    "customers_segments": (200,  "Segment filter"),
    "customer_metrics":   (200,  "Shopper metrics"),
    "customer_insights":  (3000, "Shopper AI persona (Gemini ok)"),
    "customer_story":     (500,  "Shopper story page"),
    "planner_prepare":    (800,  "Audience review (DB only)"),
    "planner_generate":   (5000, "Campaign generation (Gemini ok)"),
    "campaign_analytics": (800,  "Campaign analytics"),
}

issues = []
for key, (target, label) in targets.items():
    if key not in timings:
        continue
    t = timings[key]
    status = "✅ OK" if t < target else f"❌ SLOW (target <{target}ms)"
    print(f"  {label:<50} {t:>8.0f}ms  {status}")
    if t >= target:
        issues.append((key, t, target, label))

print(f"\n  Found {len(issues)} performance issue(s):")
for key, t, target, label in sorted(issues, key=lambda x: x[1], reverse=True):
    print(f"    🔴 {label}: {t:.0f}ms (target <{target}ms, {t/target:.1f}x over)")

print("\n" + "="*90)
