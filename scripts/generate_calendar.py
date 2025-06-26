#!/usr/bin/env python3
import os, sys, json
from datetime import date, timedelta, datetime
from dateutil import tz
import requests
from ics import Calendar, Event

API = "https://finnhub.io/api/v1/calendar/earnings"
TOKEN = os.environ["FINNHUB_TOKEN"]

TODAY = date.today()
FROM  = TODAY.isoformat()
TO    = (TODAY + timedelta(days=30)).isoformat()  # 免费版最大区间 1 个月

def fetch_earnings():
    params = {"from": FROM, "to": TO, "token": TOKEN}
    r = requests.get(API, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("earningsCalendar", [])

def to_event(item):
    ev = Event()
    # 统一用美国东部时间（FINNHub 返回也是 ET）
    event_date = datetime.fromisoformat(item["date"]).date()
    ev.name  = f"{item['symbol']}  Earnings"
    ev.begin = datetime.combine(event_date, datetime.min.time(), tz.gettz("America/New_York"))
    ev.make_all_day()             # 财报日直接用全天事件
    # 在描述里放 EPS / Revenue 预估 vs 实际
    lines   = [
        f"Ticker: {item['symbol']}",
        f"Fiscal Qtr: {item.get('quarter', '-')}",
        f"Estimate EPS: {item.get('epsEstimate', '-')}",
        f"Est. Revenue: {item.get('revenueEstimate', '-')}",
        "Source: Finnhub (non-GAAP)"
    ]
    ev.description = "\n".join(lines)
    return ev

def main():
    cal = Calendar()
    for raw in fetch_earnings():
        cal.events.add(to_event(raw))
    out = "earnings_calendar.ics"
    with open(out, "w", encoding="utf-8") as f:
        f.writelines(cal)
    print(f"✅  Calendar refreshed → {out}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("💥  Script failed:", e)
        sys.exit(1)
