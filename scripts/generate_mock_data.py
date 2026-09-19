"""Seeded mock-data generator. Produces data/raw/*.csv with three explicitly seeded demo scenarios.

Scenario accounts:
  ACC-00001 Alpha AI        -> Q-00001 Starter plan, 5% discount, Net 30  -> Auto-Approved
  ACC-00002 EnterpriseGen   -> Q-00002 Enterprise, 25%, Net 60, custom overage -> RevOps + Finance + VP Sales
  ACC-00003 FastScale AI    -> intent 90, usage 90, engagement 80, firmographic 80 -> priority 87.0, Tier 1
"""
from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

from src.config import PROJECT_ROOT, settings

RAW = PROJECT_ROOT / "data" / "raw"

INDUSTRIES = ["AI/ML", "SaaS", "Developer Tools", "Fintech", "Healthcare", "E-commerce", "Media", "Logistics"]
STAGES = ["Seed", "Series A", "Series B", "Series C", "Series D", "Public"]
OWNERS = ["Priya Natarajan", "Marcus Lee", "Elena Petrova", "Jordan Alvarez", "Sam Okafor", "Wei Zhang"]
PREFIX = ["Nimbus", "Vector", "Quanta", "Lumen", "Orbit", "Signal", "Helix", "Kepler", "Atlas", "Delta", "Pixel",
          "Forge", "Beacon", "Cobalt", "Ember", "Zenith", "Harbor", "Meridian", "Summit", "Ridge", "Cinder", "Nova"]
SUFFIX = ["AI", "Labs", "Systems", "Cloud", "Data", "Analytics", "Health", "Pay", "Works", "Logic", "Networks", "Robotics"]
TECH = ["python", "pytorch", "aws", "gcp", "kubernetes", "snowflake", "databricks", "postgres", "react", "go", "spark", "huggingface"]
CAMPAIGNS = ["Q3 Inference Launch", "Enterprise Webinar", "Pricing Update", "Open Models Newsletter", "Developer Digest"]

PRODUCTS = [
    ("PRD-API-STARTER", "Starter API Commitment", "usage", 5000, 5_000_000, 0.0000012),
    ("PRD-API-BASE", "Base API Commitment", "usage", 10000, 10_000_000, 0.0000012),
    ("PRD-ENT-PLATFORM", "Enterprise Platform", "usage", 50000, 50_000_000, 0.0000012),
    ("PRD-SUPPORT-PREM", "Premium Support", "subscription", 2000, None, None),
]


def _write(name: str, header: list[str], rows: list[list]) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    with open(RAW / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def generate(seed: int | None = None, n_accounts: int = 200, n_signals: int = 2000, n_quotes: int = 50) -> dict[str, int]:
    rng = random.Random(seed if seed is not None else settings.random_seed)
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    ts = lambda d: d.strftime("%Y-%m-%d %H:%M:%S")

    # ---------------- accounts ----------------
    accounts: list[list] = []
    names_used: set[str] = set()

    def add_account(aid, name, domain, industry, emp, stage, owner, created_days=200):
        accounts.append([aid, name, domain, industry, emp, stage, owner, None, ts(now - timedelta(days=created_days)), ts(now)])

    add_account("ACC-00001", "Alpha AI", "alpha.ai", "AI/ML", 85, "Series A", "Priya Natarajan")
    add_account("ACC-00002", "EnterpriseGen", "enterprisegen.com", "SaaS", 4200, "Public", "Marcus Lee")
    add_account("ACC-00003", "FastScale AI", "fastscale.ai", "AI/ML", 3200, "Series B", "Elena Petrova")
    names_used.update({"Alpha AI", "EnterpriseGen", "FastScale AI"})

    i = 4
    while len(accounts) < n_accounts:
        name = f"{rng.choice(PREFIX)} {rng.choice(SUFFIX)}"
        if name in names_used:
            name = f"{name} {rng.choice(['Inc', 'Co', 'Group', 'Tech'])}"
            if name in names_used:
                continue
        names_used.add(name)
        aid = f"ACC-{i:05d}"
        domain = name.lower().replace(" ", "") + rng.choice([".com", ".io", ".ai", ".co"])
        industry = rng.choices(INDUSTRIES, weights=[4, 4, 3, 2, 2, 2, 1, 1])[0]
        emp = rng.choice([12, 25, 40, 60, 120, 200, 320, 500, 800, 1500, 2600, 4000, 8000])
        stage = rng.choices(STAGES, weights=[2, 3, 3, 2, 1, 1])[0]
        owner = rng.choice(OWNERS)
        add_account(aid, name, domain, industry, emp, stage, owner, rng.randint(30, 700))
        i += 1

    # seeded data-quality defects
    accounts[10][2] = None                        # missing domain
    accounts[11][2] = None
    accounts[12][2] = accounts[13][2]              # duplicate domain
    accounts[14][2] = accounts[15][2]
    accounts[16][6] = None                         # missing owner
    accounts[17][6] = None

    _write("accounts.csv",
           ["account_id", "account_name", "domain", "industry", "employee_count", "funding_stage", "account_owner",
            "sf_account_id", "created_at", "updated_at"], accounts)

    # ---------------- Clay-shaped enrichment (most accounts; a few missing -> DQ warning) ----------------
    enrich: list[list] = []
    for idx, a in enumerate(accounts):
        aid, name, domain, industry, emp, stage, owner = a[:7]
        if aid not in ("ACC-00001", "ACC-00002", "ACC-00003") and rng.random() < 0.06:
            continue
        ml_roles = rng.choice([0, 0, 1, 2, 3, 5])
        di_roles = rng.choice([0, 0, 1, 2, 4])
        funding = rng.choice([0, 0, 2_000_000, 8_000_000, 25_000_000, 60_000_000, 150_000_000])
        if aid == "ACC-00003":
            ml_roles, di_roles, funding = 2, 3, 45_000_000
            summary = "FastScale AI builds inference infrastructure for mid-market ML teams; product usage grew 40% month over month."
            hook = "your recent push into multi-region inference and the open ML platform roles you're hiring for"
        else:
            summary = f"{name} is a {stage} {industry} company with roughly {emp} employees."
            hook = f"your {industry.lower()} roadmap and recent {stage} momentum"
        stack = ",".join(sorted(rng.sample(TECH, k=rng.randint(2, 5))))
        enrich.append([f"ENR-{idx+1:05d}", aid, domain, emp, stage, funding, stack, ml_roles, di_roles, summary, hook,
                       "clay_csv", ts(now - timedelta(days=rng.randint(0, 20)))])
    _write("clay_enrichment.csv",
           ["enrichment_id", "account_id", "domain", "employee_count", "funding_stage", "funding_amount_usd", "tech_stack",
            "open_ml_roles", "open_data_infra_roles", "company_summary", "personalization_hook", "enrichment_source", "enriched_at"],
           enrich)

    # ---------------- intent signals ----------------
    signals: list[list] = []
    sid = 1
    scenario_ids = {"ACC-00001", "ACC-00002", "ACC-00003"}

    def add_signal(aid, stype, value, source, days_ago):
        nonlocal sid
        signals.append([f"SIG-{sid:06d}", aid, stype, value, source, ts(now - timedelta(days=days_ago, hours=rng.randint(0, 23)))])
        sid += 1

    # FastScale AI (exact): 3 pricing visits, ml job postings 2 (Clay), website visits totalling 15
    for d in (3, 9, 21):
        add_signal("ACC-00003", "pricing_page_visit", 1, "web_analytics", d)
    add_signal("ACC-00003", "job_posting_ml_engineer", 2, "clay", 12)
    for d, v in ((2, 5), (15, 5), (40, 5)):
        add_signal("ACC-00003", "website_visit", v, "web_analytics", d)
    add_signal("ACC-00003", "product_usage_growth", 40, "product_telemetry", 1)
    # Alpha AI and EnterpriseGen: modest signals
    add_signal("ACC-00001", "website_visit", 4, "web_analytics", 6)
    add_signal("ACC-00001", "pricing_page_visit", 1, "web_analytics", 5)
    add_signal("ACC-00002", "website_visit", 6, "web_analytics", 10)
    add_signal("ACC-00002", "demo_request", 1, "web_analytics", 30)

    pool = [a[0] for a in accounts if a[0] not in scenario_ids]
    hot = set(rng.sample(pool, 25))  # a subset of accounts with concentrated activity
    stype_weights = {"website_visit": 30, "pricing_page_visit": 12, "email_engagement": 18, "demo_request": 4,
                     "job_posting_ml_engineer": 8, "funding_event": 3, "product_usage_growth": 10, "open_source_model_interest": 8}
    source_for = {"website_visit": "web_analytics", "pricing_page_visit": "web_analytics", "email_engagement": "email_platform",
                  "demo_request": "web_analytics", "job_posting_ml_engineer": "clay", "funding_event": "news_feed",
                  "product_usage_growth": "product_telemetry", "open_source_model_interest": "job_boards"}
    types, weights = list(stype_weights), list(stype_weights.values())
    while len(signals) < n_signals - 60:  # leave room for HubSpot-derived rows
        aid = rng.choice(pool) if rng.random() > 0.45 else rng.choice(sorted(hot))
        st = rng.choices(types, weights=weights)[0]
        value = {"website_visit": rng.randint(1, 8), "pricing_page_visit": 1, "email_engagement": 1, "demo_request": 1,
                 "job_posting_ml_engineer": rng.randint(1, 4), "funding_event": 1,
                 "product_usage_growth": rng.randint(-10, 60), "open_source_model_interest": 1}[st]
        add_signal(aid, st, value, source_for[st], rng.randint(0, 130))
    _write("intent_signals.csv", ["signal_id", "account_id", "signal_type", "signal_value", "signal_source", "signal_timestamp"], signals)

    # ---------------- HubSpot-shaped engagement export ----------------
    hs: list[list] = []
    hid = 1

    def add_hs(email, domain, etype, days_ago, campaign):
        nonlocal hid
        hs.append([f"HS-{hid:06d}", email, domain, etype, ts(now - timedelta(days=days_ago, hours=rng.randint(0, 23))), campaign])
        hid += 1

    # FastScale AI (exact): 1 meeting booked -> demo_request, 5 email events -> email_engagement
    add_hs("cto@fastscale.ai", "fastscale.ai", "meeting_booked", 4, "Enterprise Webinar")
    for d, et in ((1, "email_open"), (3, "email_click"), (8, "email_open"), (14, "email_click"), (22, "email_open")):
        add_hs("cto@fastscale.ai", "fastscale.ai", et, d, rng.choice(CAMPAIGNS))
    domain_of = {a[0]: a[2] for a in accounts if a[2]}
    for _ in range(320):
        aid = rng.choice(pool)
        dom = domain_of.get(aid)
        if not dom:
            continue
        et = rng.choices(["email_open", "email_click", "form_submit", "page_view", "meeting_booked"], weights=[40, 20, 8, 25, 3])[0]
        add_hs(f"{rng.choice(['ops', 'cto', 'vp.eng', 'data'])}@{dom}", dom, et, rng.randint(0, 120), rng.choice(CAMPAIGNS))
    _write("hubspot_engagement.csv", ["event_id", "contact_email", "domain", "event_type", "event_timestamp", "campaign"], hs)

    # ---------------- usage signals: 6 months per account ----------------
    usage: list[list] = []
    uid = 1
    for a in accounts:
        aid = a[0]
        base = rng.choice([50_000, 200_000, 1_000_000, 4_000_000, 12_000_000])
        users = rng.randint(3, 140)
        growth_profile = rng.choice([-5, 0, 3, 8, 15, 25, 45])
        for m in range(5, -1, -1):
            month = (now.replace(day=1) - timedelta(days=30 * m)).replace(day=1)
            g = growth_profile + rng.randint(-4, 4)
            base = int(base * (1 + g / 100))
            users = max(1, users + rng.randint(-3, 6))
            if aid == "ACC-00003":
                g = 40 if m == 0 else 30 + rng.randint(-3, 3)
                users = 260 if m == 0 else 200 + m * 8
            usage.append([f"USG-{uid:06d}", aid, month.strftime("%Y-%m-%d"), base, users, g])
            uid += 1
    _write("usage_signals.csv", ["usage_id", "account_id", "month", "api_calls", "active_users", "mom_growth_pct"], usage)

    # ---------------- products ----------------
    _write("products.csv", ["product_id", "product_name", "pricing_model", "list_price_monthly", "included_units", "overage_price_per_unit"],
           [list(p) for p in PRODUCTS])

    # ---------------- quote requests ----------------
    quotes: list[list] = []
    quotes.append(["Q-00001", "ACC-00001", "Alpha AI", "PRD-API-STARTER", 5000, 1, 12, 5, "Net 30", False, 4_000_000, None, ts(now - timedelta(days=1))])
    quotes.append(["Q-00002", "ACC-00002", "EnterpriseGen", "PRD-ENT-PLATFORM", 50000, 1, 12, 25, "Net 60", False, 45_000_000, 0.0000010, ts(now - timedelta(days=1))])
    prod_by_id = {p[0]: p for p in PRODUCTS}
    qi = 3
    while len(quotes) < n_quotes:
        a = rng.choice(accounts[3:])
        p = rng.choices(PRODUCTS, weights=[4, 4, 1, 2])[0]
        custom = rng.random() < 0.12
        commitment = p[3] if not custom else int(p[3] * rng.choice([0.8, 1.2, 1.5]))
        disc = rng.choices([0, 5, 8, 10, 12, 15, 18, 20, 22, 25, 30], weights=[6, 8, 5, 6, 4, 4, 3, 2, 2, 2, 1])[0]
        terms = rng.choices(["Net 30", "Annual Prepaid", "Net 60", "Net 90"], weights=[10, 4, 3, 1])[0]
        term = rng.choice([12, 12, 12, 24, 36, 6])
        forecast = int((p[4] or 0) * rng.choice([0.5, 0.9, 1.0, 1.3, 1.8])) if p[2] == "usage" else None
        cor = rng.choice([None, None, None, None, None, 0.0000010]) if p[2] == "usage" else None
        days_ago = rng.choice([0, 0, 0, 0, 1, 1, 1, 2, 3, 5])
        quotes.append([f"Q-{qi:05d}", a[0], a[1], p[0], commitment, 1, term, disc, terms, custom, forecast, cor,
                       ts(now - timedelta(days=days_ago, hours=rng.randint(1, 20)))])
        qi += 1
    # seeded validation defects
    quotes[47][7] = 120                    # invalid discount
    quotes[48][4] = 7000; quotes[48][9] = False; quotes[48][3] = "PRD-API-BASE"; quotes[48][11] = None  # commitment mismatch, not custom
    quotes[49][8] = "Net 45"               # payment terms not allowed
    _write("quote_requests.csv",
           ["quote_id", "account_id", "account_name", "product_id", "monthly_commitment", "quantity", "contract_term_months",
            "discount_percent", "payment_terms", "custom_pricing", "forecasted_units", "custom_overage_rate", "requested_at"], quotes)

    return {"accounts": len(accounts), "enrichment": len(enrich), "intent_signals": len(signals),
            "hubspot_events": len(hs), "usage_rows": len(usage), "products": len(PRODUCTS), "quote_requests": len(quotes)}


if __name__ == "__main__":
    counts = generate()
    for k, v in counts.items():
        print(f"{k:16s} {v}")
