"""Immutable project constants for the Iveel × Dealy container.

Single source of truth. Anything in this file is a CONSTANT — changing a
value here means re-seeding the database. Runtime code must NEVER mutate
these objects (treat them as frozen). The container service reads these
on every request so a server restart picks up any change.

Read order:
    CONTAINER_TARGET  -> the goal (1B tugrik)
    MEMBERS           -> who is doing the work
    PROJECTS          -> the 7 sheet projects (parallel to SHEET_PROJECTS in team service)
    MILESTONES        -> 27 milestones with date / track / DoD / KPI / owner refs
    TASK_ASSIGNMENTS  -> (member, project) -> task title + weight
    SCENARIOS         -> Bear / Base / Bull simulation inputs
"""
from __future__ import annotations

from typing import Final


# ─────────────────────────────────────────────────────────────
# CONTAINER — the goal
# ─────────────────────────────────────────────────────────────

CONTAINER_TARGET: Final[int] = 1_000_000_000          # 1 billion MNT
CONTAINER_CURRENCY: Final[str] = "MNT"
CONTAINER_START: Final[str] = "2026-05-22"
CONTAINER_END: Final[str] = "2026-07-20"
CONTAINER_AGENT_HANDLE: Final[str] = "container_agent"   # the one monitor

# ─────────────────────────────────────────────────────────────
# MEMBERS — 13 humans + 1 monitoring agent
# ─────────────────────────────────────────────────────────────
# (name, handle, role, track, base_salary_mnt, load)
# load: ratio of full-time; used for KPI normalization.

MEMBERS: Final[tuple[dict, ...]] = (
    {"name": "Авидхүү",        "handle": "avidkhuu",   "role": "E-com Lead / Architecture",     "track": "tech", "base_salary": 3_500_000, "load": 1.00},
    {"name": "Тэмүүлэн",       "handle": "temuulen",   "role": "Backend / API integration",     "track": "tech", "base_salary": 3_000_000, "load": 1.00},
    {"name": "Мишээл",         "handle": "mishel",     "role": "E-com Data / Inventory",        "track": "tech", "base_salary": 2_800_000, "load": 0.90},
    {"name": "Anandochir",     "handle": "anandochir", "role": "Chatbot development",           "track": "tech", "base_salary": 2_800_000, "load": 0.90},

    {"name": "Содбаяр",        "handle": "sodbaayar",  "role": "Marketing lead / Web design",   "track": "mkt",  "base_salary": 3_000_000, "load": 1.00},
    {"name": "Нямдагва",       "handle": "nymka",      "role": "Content / Social media",        "track": "mkt",  "base_salary": 2_500_000, "load": 1.00},
    {"name": "Төрбатжин",      "handle": "turbatjin",  "role": "Photographer",                  "track": "mkt",  "base_salary": 2_000_000, "load": 0.70},
    {"name": "Мөнх-Очир",      "handle": "munkhochir", "role": "Designer / Content",            "track": "mkt",  "base_salary": 2_200_000, "load": 0.80},
    {"name": "Erkhme",         "handle": "erkhme",     "role": "Marketing execute (ops)",       "track": "mkt",  "base_salary": 2_300_000, "load": 1.00},

    {"name": "Эрхэмтөгс",      "handle": "erkhemtugs", "role": "Business / Unit economics",     "track": "biz",  "base_salary": 3_200_000, "load": 1.00},
    {"name": "Өлзийбадрах",    "handle": "ulziibadrakh","role": "DDDM / Analytics",             "track": "biz",  "base_salary": 2_800_000, "load": 0.80},
    {"name": "Ариун-Эрдэнэ",   "handle": "ariunerdene","role": "Project manager / Event lead",  "track": "biz",  "base_salary": 3_000_000, "load": 1.00},
    {"name": "Obama",          "handle": "obama",      "role": "Site QA / Boost ops",           "track": "mkt",  "base_salary": 2_000_000, "load": 0.80},

    # The one monitoring agent — non-human, no salary, no login.
    {"name": "Container Agent","handle": CONTAINER_AGENT_HANDLE, "role": "Container fill monitor (single agent)", "track": "biz", "base_salary": 0, "load": 1.00, "is_agent": True},
)

# ─────────────────────────────────────────────────────────────
# PROJECTS — these mirror SHEET_PROJECTS in the team service.
# The container service does NOT redefine them; it references by name.
# ─────────────────────────────────────────────────────────────

PROJECTS: Final[tuple[str, ...]] = (
    "Marketing campaign",
    "Social media",
    "Sells / amount",
    "IT / performance",
    "KPI rate",
    "Salary",
    "Rate / weight",
)

# ─────────────────────────────────────────────────────────────
# MILESTONES — frozen 27-item plan
# ─────────────────────────────────────────────────────────────
# (id, date, track, title, dod, kpi, owner_handles, critical, expected_revenue_mnt)
# expected_revenue is the share of the 1B container each milestone is forecast
# to ship when delivered on time. Sum is NOT exactly 1B — milestones can
# overlap or feed each other; this is a per-milestone contribution estimate.

MILESTONES: Final[tuple[dict, ...]] = (
    # ── Phase 1: Setup & MVP ──
    {"id": "M01", "date": "2026-05-24", "track": "tech", "phase": 1, "critical": False,
     "title": "Project repo setup",
     "dod": "Github repo, CI/CD, dev/staging/prod environments live.",
     "kpi": "All devs push code successfully",
     "owners": ("avidkhuu", "temuulen"),
     "expected_revenue_mnt": 0},

    {"id": "M02", "date": "2026-05-25", "track": "mkt", "phase": 1, "critical": False,
     "title": "Mother's Day poster ready",
     "dod": "3 sizes (FB feed, IG story, Zaisan window). B-side approved.",
     "kpi": "Poster live by 5.29",
     "owners": ("nymka", "munkhochir"),
     "expected_revenue_mnt": 0},

    {"id": "M03", "date": "2026-05-27", "track": "tech", "phase": 1, "critical": True,
     "title": "Data migration plan approved",
     "dod": "Zochil.shop export ready (products/orders/customers). Schema mapping doc.",
     "kpi": "~84 SKU + customer DB count documented",
     "owners": ("avidkhuu", "mishel"),
     "expected_revenue_mnt": 0},

    {"id": "M04", "date": "2026-05-28", "track": "biz", "phase": 1, "critical": False,
     "title": "Inventory split decision",
     "dod": "Frozen list: Zaisan 70%-off SKUs vs Online 50%-off SKUs. B-side approved.",
     "kpi": "SKU list per channel",
     "owners": ("erkhemtugs",),
     "expected_revenue_mnt": 0},

    {"id": "M05", "date": "2026-05-29", "track": "mkt", "phase": 1, "critical": True,
     "title": "Mother's Day campaign live",
     "dod": "Post + reel + story live 5.29. Boost $200 first day.",
     "kpi": "50K reach, 100 orders",
     "owners": ("nymka", "erkhme"),
     "expected_revenue_mnt": 30_000_000},

    {"id": "M06", "date": "2026-05-31", "track": "tech", "phase": 1, "critical": False,
     "title": "QPay sandbox integration",
     "dod": "Sandbox account, test invoice, callback handling. 10+ test txns.",
     "kpi": "Sandbox QR payment passes",
     "owners": ("temuulen",),
     "expected_revenue_mnt": 0},

    {"id": "M07", "date": "2026-06-01", "track": "biz", "phase": 1, "critical": True,
     "title": "Tumbaa branch closed",
     "dod": "Inventory transferred to Zaisan. Closure notice on FB / Google Maps.",
     "kpi": "Zaisan inventory full",
     "owners": ("erkhemtugs", "nymka"),
     "expected_revenue_mnt": 0},

    {"id": "M08", "date": "2026-06-03", "track": "tech", "phase": 1, "critical": False,
     "title": "Papa Logistics API verification",
     "dod": "Papa small-package capability verified. Backup (TopX/Sloono) ready if not.",
     "kpi": "Working delivery API call",
     "owners": ("mishel", "sodbaayar"),
     "expected_revenue_mnt": 0},

    {"id": "M09", "date": "2026-06-05", "track": "tech", "phase": 1, "critical": True,
     "title": "E-commerce MVP live",
     "dod": "New Dealy-based site live: catalog (84 SKU), cart, checkout, QPay, delivery.",
     "kpi": "Uptime 99%+, first 10 orders",
     "owners": ("avidkhuu", "temuulen", "mishel"),
     "expected_revenue_mnt": 80_000_000},

    # ── Phase 2: Growth ──
    {"id": "M10", "date": "2026-06-07", "track": "mkt", "phase": 2, "critical": False,
     "title": "Zaisan 70% off launch event",
     "dod": "Offline launch event. Boost budget 5M MNT.",
     "kpi": "500 walk-in first day",
     "owners": ("erkhme", "nymka"),
     "expected_revenue_mnt": 90_000_000},

    {"id": "M11", "date": "2026-06-10", "track": "biz", "phase": 2, "critical": True,
     "title": "Tour partnership outreach",
     "dod": "10+ tour companies contacted. Proposals sent.",
     "kpi": "3+ replied, 1+ in discussion",
     "owners": ("erkhemtugs", "ariunerdene"),
     "expected_revenue_mnt": 0},

    {"id": "M12", "date": "2026-06-12", "track": "tech", "phase": 2, "critical": False,
     "title": "820 Limited Edition landing",
     "dod": "Separate URL, numbered serial DB, QR-cert system, premium photography.",
     "kpi": "Landing live, first pre-order",
     "owners": ("munkhochir", "avidkhuu"),
     "expected_revenue_mnt": 0},

    {"id": "M13", "date": "2026-06-14", "track": "mkt", "phase": 2, "critical": False,
     "title": "820 anniversary launch teaser",
     "dod": "Heritage video (60s). \"820 он. 820 загвар. 820 түүх\" concept. Boost 5M.",
     "kpi": "200K view, 5K engagement",
     "owners": ("turbatjin", "munkhochir"),
     "expected_revenue_mnt": 0},

    {"id": "M14", "date": "2026-06-15", "track": "tech", "phase": 2, "critical": True,
     "title": "FB Messenger chatbot v1 live",
     "dod": "FB Catalog sync, recommendation, lead capture, handoff to human inbox.",
     "kpi": "First чат-order, 100 sessions",
     "owners": ("sodbaayar", "temuulen"),
     "expected_revenue_mnt": 60_000_000},

    {"id": "M15", "date": "2026-06-18", "track": "mkt", "phase": 2, "critical": False,
     "title": "820 Limited Edition official launch",
     "dod": "Numbered 820 series. Premium pricing 350-500K MNT.",
     "kpi": "First 100 units sold first week",
     "owners": ("sodbaayar", "nymka", "turbatjin"),
     "expected_revenue_mnt": 200_000_000},

    {"id": "M16", "date": "2026-06-20", "track": "biz", "phase": 2, "critical": True,
     "title": "Month-1 review + month-2 commission decision",
     "dod": "Per contract 5.3.2. If month-1 ≥400M, set month-2 commission 12–15%.",
     "kpi": "Month-1 actual revenue, signed amendment",
     "owners": ("erkhemtugs", "ariunerdene"),
     "expected_revenue_mnt": 0},

    {"id": "M17", "date": "2026-06-22", "track": "biz", "phase": 2, "critical": False,
     "title": "Tour partnership 1+ signed",
     "dod": "First tour-company contract signed. Commission (10-15%) set.",
     "kpi": "1+ signed contract",
     "owners": ("erkhemtugs", "ariunerdene"),
     "expected_revenue_mnt": 150_000_000},

    {"id": "M18", "date": "2026-06-25", "track": "tech", "phase": 2, "critical": False,
     "title": "Chatbot recommendation engine v2",
     "dod": "Personalized recommendations from browsing history.",
     "kpi": "Conv 4% → 6%+",
     "owners": ("sodbaayar", "anandochir"),
     "expected_revenue_mnt": 40_000_000},

    {"id": "M19", "date": "2026-06-28", "track": "biz", "phase": 2, "critical": False,
     "title": "Power BI analytics dashboard live",
     "dod": "Daily revenue, channel breakdown, AOV, conv rate. Auto-refresh.",
     "kpi": "Live dashboard shared with B-side",
     "owners": ("ulziibadrakh", "erkhemtugs"),
     "expected_revenue_mnt": 0},

    {"id": "M20", "date": "2026-07-01", "track": "biz", "phase": 2, "critical": True,
     "title": "Pricing transition (50% → 30% off)",
     "dod": "Online discount drops to 30%. First step out of permanent-sale habit.",
     "kpi": "Margin up, conv rate held",
     "owners": ("avidkhuu", "erkhemtugs"),
     "expected_revenue_mnt": 0},

    # ── Phase 3: Last Dance ──
    {"id": "M21", "date": "2026-07-08", "track": "mkt", "phase": 3, "critical": False,
     "title": "New collection teaser",
     "dod": "5-10 new designs, premium photoshoot. Pre-Last-Dance hype.",
     "kpi": "500K reach",
     "owners": ("turbatjin", "munkhochir", "nymka"),
     "expected_revenue_mnt": 0},

    {"id": "M22", "date": "2026-07-10", "track": "tech", "phase": 3, "critical": False,
     "title": "Gift card system",
     "dod": "Gift card create, QR delivery, balance tracking.",
     "kpi": "50+ gift cards sold",
     "owners": ("avidkhuu",),
     "expected_revenue_mnt": 15_000_000},

    {"id": "M23", "date": "2026-07-12", "track": "mkt", "phase": 3, "critical": True,
     "title": "New collection launch (full price)",
     "dod": "New collection live 7.12. Premium pricing (no discount). Influencer launch.",
     "kpi": "300 orders first week",
     "owners": ("sodbaayar", "nymka", "turbatjin"),
     "expected_revenue_mnt": 180_000_000},

    {"id": "M24", "date": "2026-07-15", "track": "tech", "phase": 3, "critical": False,
     "title": "Chatbot handoff to B-side",
     "dod": "Chatbot code delivered to B-side. Production access, admin, docs.",
     "kpi": "B-side can manage chatbot",
     "owners": ("sodbaayar", "avidkhuu"),
     "expected_revenue_mnt": 0},

    {"id": "M25", "date": "2026-07-18", "track": "biz", "phase": 3, "critical": False,
     "title": "Final analytics & report",
     "dod": "Full 2-month performance report. Channel breakdown, ROI, recommendations.",
     "kpi": "Final report delivered",
     "owners": ("ulziibadrakh", "erkhemtugs"),
     "expected_revenue_mnt": 0},

    {"id": "M26", "date": "2026-07-19", "track": "mkt", "phase": 3, "critical": True,
     "title": "\"Last Dance\" event",
     "dod": "Zaisan offline event. Live music, fashion show, VIP customers.",
     "kpi": "200+ attendees, 30M+ onsite sales",
     "owners": ("ariunerdene", "nymka", "erkhme"),
     "expected_revenue_mnt": 50_000_000},

    {"id": "M27", "date": "2026-07-20", "track": "biz", "phase": 3, "critical": True,
     "title": "Contract closed + acceptance act",
     "dod": "All deliverables transferred. Acceptance act signed. Final commission paid.",
     "kpi": "Signed acceptance act",
     "owners": ("erkhemtugs", "ariunerdene"),
     "expected_revenue_mnt": 0},
)

# ─────────────────────────────────────────────────────────────
# TASK ASSIGNMENTS — (project_name, member_handle) -> (title, weight, status)
# These are seeded once. Members can re-status them but the assignment is frozen.
# ─────────────────────────────────────────────────────────────

TASK_ASSIGNMENTS: Final[tuple[dict, ...]] = (
    # Marketing campaign
    {"project": "Marketing campaign", "member": "sodbaayar",   "title": "Marketing strategy ownership",        "weight": 10},
    {"project": "Marketing campaign", "member": "nymka",       "title": "Content + Mother's Day + 820 hype",  "weight": 9},
    {"project": "Marketing campaign", "member": "erkhme",      "title": "Boost ops + campaign execution",      "weight": 8},
    {"project": "Marketing campaign", "member": "munkhochir",  "title": "Poster + brand identity",             "weight": 7},
    {"project": "Marketing campaign", "member": "turbatjin",   "title": "Photo / video production",            "weight": 6},

    # Social media
    {"project": "Social media", "member": "nymka",      "title": "Daily FB + IG posting",                "weight": 9},
    {"project": "Social media", "member": "sodbaayar",  "title": "Channel strategy + analytics review",  "weight": 7},
    {"project": "Social media", "member": "obama",      "title": "Boost campaign post-checks",           "weight": 5},

    # Sells / amount
    {"project": "Sells / amount", "member": "erkhemtugs",   "title": "Unit economics + commission negotiation","weight": 10},
    {"project": "Sells / amount", "member": "ariunerdene",  "title": "Tour partnership + Last Dance event",   "weight": 9},
    {"project": "Sells / amount", "member": "ulziibadrakh", "title": "Channel revenue attribution",            "weight": 7},

    # IT / performance
    {"project": "IT / performance", "member": "avidkhuu",   "title": "E-com architecture + MVP + handoff",  "weight": 10},
    {"project": "IT / performance", "member": "temuulen",   "title": "QPay + Papa + chatbot backend",       "weight": 9},
    {"project": "IT / performance", "member": "mishel",     "title": "Data migration + inventory sync",     "weight": 8},
    {"project": "IT / performance", "member": "anandochir", "title": "Chatbot NLP + recommendations",       "weight": 7},

    # KPI rate
    {"project": "KPI rate", "member": "ulziibadrakh", "title": "Power BI + daily KPI",                   "weight": 10},
    {"project": "KPI rate", "member": "erkhemtugs",   "title": "KPI target setting + B-side reporting",  "weight": 8},
    {"project": "KPI rate", "member": "ariunerdene",  "title": "Weekly stand-up + blocker tracking",     "weight": 6},

    # Salary
    {"project": "Salary", "member": "erkhemtugs",   "title": "Salary distribution + bonus rules",  "weight": 9},

    # Rate / weight
    {"project": "Rate / weight", "member": "erkhemtugs", "title": "Task weight calibration",         "weight": 7},
    {"project": "Rate / weight", "member": "sodbaayar",  "title": "Marketing rate calibration",      "weight": 6},
    {"project": "Rate / weight", "member": "avidkhuu",   "title": "Tech rate calibration",           "weight": 6},
)

# ─────────────────────────────────────────────────────────────
# SCENARIOS — three pre-baked simulation inputs.
# Channel mix x (orders, AOV) per scenario. Margin same across.
# Used by /scenarios/simulate. Inputs are CONST — runtime can vary
# only the scenario name and recompute, not edit numbers.
# ─────────────────────────────────────────────────────────────

CHANNELS: Final[tuple[str, ...]] = (
    "ecom_site_50off",
    "zaisan_offline_70off",
    "fb_messenger_chatbot",
    "tourist_channel",
    "limited_820_edition",
)

SCENARIOS: Final[dict[str, dict]] = {
    "bear": {
        "label": "Bear (60% execution)",
        "channels": {
            "ecom_site_50off":      {"orders": 2600, "aov_mnt": 70000,  "gross_margin": 0.10},
            "zaisan_offline_70off": {"orders": 1300, "aov_mnt": 52000,  "gross_margin": 0.05},
            "fb_messenger_chatbot": {"orders":  600, "aov_mnt": 80000,  "gross_margin": 0.20},
            "tourist_channel":      {"orders":  900, "aov_mnt": 240000, "gross_margin": 0.55},
            "limited_820_edition":  {"orders":  250, "aov_mnt": 420000, "gross_margin": 0.65},
        },
        "operating_expense_mnt": 110_000_000,
        "marketing_budget_mnt":  25_000_000,
        "a_commission_pct":      0.05,    # month-1 simple rate
    },
    "base": {
        "label": "Base (full execution)",
        "channels": {
            "ecom_site_50off":      {"orders": 4400, "aov_mnt": 82000,  "gross_margin": 0.18},
            "zaisan_offline_70off": {"orders": 3000, "aov_mnt": 54000,  "gross_margin": 0.05},
            "fb_messenger_chatbot": {"orders": 1850, "aov_mnt": 88000,  "gross_margin": 0.25},
            "tourist_channel":      {"orders": 1490, "aov_mnt": 265000, "gross_margin": 0.55},
            "limited_820_edition":  {"orders":  490, "aov_mnt": 420000, "gross_margin": 0.65},
        },
        "operating_expense_mnt": 145_000_000,
        "marketing_budget_mnt":  45_000_000,
        "a_commission_pct":      0.075,
    },
    "bull": {
        "label": "Bull (over-execution)",
        "channels": {
            "ecom_site_50off":      {"orders": 7000, "aov_mnt": 90000,  "gross_margin": 0.20},
            "zaisan_offline_70off": {"orders": 4000, "aov_mnt": 56000,  "gross_margin": 0.05},
            "fb_messenger_chatbot": {"orders": 3300, "aov_mnt": 95000,  "gross_margin": 0.30},
            "tourist_channel":      {"orders": 2235, "aov_mnt": 290000, "gross_margin": 0.55},
            "limited_820_edition":  {"orders":  820, "aov_mnt": 450000, "gross_margin": 0.65},
        },
        "operating_expense_mnt": 200_000_000,
        "marketing_budget_mnt":  80_000_000,
        "a_commission_pct":      0.10,
    },
}


def all_handles() -> tuple[str, ...]:
    return tuple(m["handle"] for m in MEMBERS)


def milestone_by_id(mid: str) -> dict | None:
    for m in MILESTONES:
        if m["id"] == mid:
            return m
    return None


def total_expected_revenue() -> int:
    return sum(m["expected_revenue_mnt"] for m in MILESTONES)
