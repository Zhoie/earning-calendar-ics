#!/usr/bin/env python3
"""
Generate an earnings-calendar ICS file using Finnhub API.

1. Fetch earnings for the coming 30 days (free-tier limit).
2. Convert each record to an all-day iCalendar event.
3. Abbreviate long revenue numbers (e.g. 12 345 678 901 → '12.35 B').
4. Write/overwrite earnings_calendar.ics in repository root.

Prerequisites:
  • FINNHUB_TOKEN must be provided as env var.
  • pip install -r requirements.txt
"""

import os
import sys
from datetime import date, timedelta, datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dateutil import tz
from ics import Calendar, Event

# ────────────────────────────────────────────────────────────────────────────────
# Config
API = "https://finnhub.io/api/v1/calendar/earnings"
TOKEN = os.getenv("FINNHUB_TOKEN")
LOOKBEHIND_DAYS = 15                          # past earnings window
LOOKAHEAD_DAYS  = 15                          # upcoming earnings window

TODAY = date.today()
FROM = (TODAY - timedelta(days=LOOKBEHIND_DAYS)).isoformat()
TO   = (TODAY + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
TZ_NY = tz.gettz("America/New_York")

# Set up retry strategy with exponential backoff for API resilience
_retry_strategy = Retry(
    total=3,
    backoff_factor=1,  # 1s, 2s, 4s between retries
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
_session = requests.Session()
_adapter = HTTPAdapter(max_retries=_retry_strategy)
_session.mount("https://", _adapter)

# ────────────────────────────────────────────────────────────────────────────────
# Helpers
def fmt_number(num):
    """
    Abbreviate big numbers with B/M.
    e.g. 1_234_567_890 -> '1.23 B', 456_000_000 -> '456 M'
    Returns '-' if value is None/invalid/zero.
    """
    if num in (None, 0, "0"):
        return "-"
    try:
        n = float(num)
    except (ValueError, TypeError):
        return "-"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}\u202fB"   # narrow-space
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f}\u202fM"
    return f"{n:.0f}"


def fetch_earnings() -> list[dict]:
    """Call Finnhub and return raw earnings list with retry logic."""
    if not TOKEN:
        raise RuntimeError("FINNHUB_TOKEN env-var is missing.")
    
    params = {"from": FROM, "to": TO, "token": TOKEN}
    resp = _session.get(API, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("earningsCalendar", [])


def to_event(item: dict) -> Event:
    """Convert one Finnhub record to an ics Event."""
    ev = Event()
    ev.name = f"{item['symbol']} Earnings"
    ev.begin = datetime.combine(
        datetime.fromisoformat(item["date"]).date(),
        datetime.min.time(),
        TZ_NY,
    )
    ev.make_all_day()

    lines = [
        f"Ticker: {item['symbol']}",
        f"Fiscal Qtr: {item.get('quarter', '-')}",
        f"Estimate EPS: {item.get('epsEstimate', '-')}",
        f"Est. Revenue: {fmt_number(item.get('revenueEstimate'))}",
        "Source: Finnhub (non-GAAP)",
    ]
    ev.description = "\n".join(lines)
    return ev


# ────────────────────────────────────────────────────────────────────────────────
def main() -> None:
    cal = Calendar()
    for rec in fetch_earnings():
        cal.events.add(to_event(rec))

    out_path = "earnings_calendar.ics"
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(cal)
    print(f"✅  Calendar refreshed → {out_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("💥  Script failed:", exc)
        sys.exit(1)
