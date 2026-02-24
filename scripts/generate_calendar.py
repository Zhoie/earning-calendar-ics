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
from datetime import date, timedelta, datetime, timezone

import requests

# ────────────────────────────────────────────────────────────────────────────────
# Config
API = "https://finnhub.io/api/v1/calendar/earnings"
TOKEN = os.getenv("FINNHUB_TOKEN")
LOOKBEHIND_DAYS = 15                          # past earnings window
LOOKAHEAD_DAYS  = 15                          # upcoming earnings window

TODAY = date.today()
FROM = (TODAY - timedelta(days=LOOKBEHIND_DAYS)).isoformat()
TO   = (TODAY + timedelta(days=LOOKAHEAD_DAYS)).isoformat()

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
        return f"{n / 1_000_000_000:.2f} B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f} M"
    return f"{n:.0f}"


def fetch_earnings() -> list[dict]:
    """Call Finnhub and return raw earnings list."""
    if not TOKEN:
        raise RuntimeError("FINNHUB_TOKEN env-var is missing.")
    params = {"from": FROM, "to": TO, "token": TOKEN}
    resp = requests.get(API, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("earningsCalendar", [])


def escape_ics_text(value: str) -> str:
    """Escape text according to RFC5545."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\n", r"\n")
    )


def fold_ics_line(line: str, width: int = 75) -> list[str]:
    """Fold long iCalendar lines (continuation starts with one space)."""
    if len(line) <= width:
        return [line]
    folded = [line[:width]]
    rest = line[width:]
    while rest:
        folded.append(f" {rest[: width - 1]}")
        rest = rest[width - 1 :]
    return folded


def to_event_lines(item: dict, dtstamp: str) -> list[str]:
    """Convert one Finnhub record into RFC5545 VEVENT lines."""
    symbol = item.get("symbol", "UNKNOWN")
    event_date = datetime.fromisoformat(item["date"]).date()
    end_date = event_date + timedelta(days=1)  # all-day events use exclusive end
    uid = f"{symbol}-{event_date.isoformat()}@earning-calendar-ics"

    description = "\n".join(
        [
            f"Ticker: {symbol}",
            f"Fiscal Qtr: {item.get('quarter', '-')}",
            f"Estimate EPS: {item.get('epsEstimate', '-')}",
            f"Est. Revenue: {fmt_number(item.get('revenueEstimate'))}",
            "Source: Finnhub (non-GAAP)",
        ]
    )

    return [
        "BEGIN:VEVENT",
        f"UID:{escape_ics_text(uid)}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART;VALUE=DATE:{event_date.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{end_date.strftime('%Y%m%d')}",
        f"SUMMARY:{escape_ics_text(f'{symbol} Earnings')}",
        f"DESCRIPTION:{escape_ics_text(description)}",
        "END:VEVENT",
    ]


def build_calendar(records: list[dict]) -> str:
    """Build a full iCalendar payload with all records."""
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//earning-calendar-ics//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Earnings Calendar",
    ]

    for rec in sorted(records, key=lambda r: (r.get("date", ""), r.get("symbol", ""))):
        if not rec.get("date"):
            continue
        lines.extend(to_event_lines(rec, dtstamp))

    lines.append("END:VCALENDAR")

    folded_lines: list[str] = []
    for line in lines:
        folded_lines.extend(fold_ics_line(line))

    return "\r\n".join(folded_lines) + "\r\n"


# ────────────────────────────────────────────────────────────────────────────────
def main() -> None:
    records = fetch_earnings()

    out_path = "earnings_calendar.ics"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(build_calendar(records))
    print(f"✅  Calendar refreshed ({len(records)} events) → {out_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("💥  Script failed:", exc)
        sys.exit(1)
