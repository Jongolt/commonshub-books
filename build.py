#!/usr/bin/env python3
"""Pull public Stripe rows from Commons Hub open data and write index.html.

Reads https://commonshub.brussels/opendata. No Stripe key.
Drops fields that point at a person (Open Collective profile URLs).
"""

import json
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

API = "https://commonshub.brussels/opendata"
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "index.html"
CACHE = ROOT / "data" / "stripe-rows.json"

# Bank payouts move the same money out of Stripe. They are not new income.
SKIP_KINDS = {"payout", "payout_reversal"}


def get(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def load_rows():
    if CACHE.exists():
        return json.loads(CACHE.read_text())

    index = get(f"{API}/index.json")
    monthly = get(f"{API}/monthly.json")
    status = {row["month"]: row.get("status") for row in monthly.get("months") or []}
    rows = []
    generated = []
    for period in index["periods"]:
        year = period["year"]
        for month in period["months"]:
            mm = month["month"]
            key = f"{year}-{mm}"
            payload = get(f"{API}/{year}/{mm}/transactions.json")
            generated.append(payload.get("generatedAt"))
            for tx in payload.get("transactions") or []:
                if tx.get("provider") != "stripe":
                    continue
                meta = tx.get("metadata") or {}
                rows.append(
                    {
                        "month": key,
                        "status": status.get(key),
                        "kind": meta.get("kind") or tx.get("type"),
                        "category": meta.get("category") or "uncategorised",
                        "collective": meta.get("collective") or "unassigned",
                        "application": meta.get("application") or "",
                        "product": meta.get("product") or "",
                        "description": meta.get("description") or "",
                        "amount": tx.get("amount") or 0,
                        "fee": tx.get("fee") or 0,
                        "gross": tx.get("grossAmount") or 0,
                        "net": tx.get("netAmount") or 0,
                    }
                )
    stamp = sorted(g for g in generated if g)[-1]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"generatedAt": stamp, "rows": rows}))
    return json.loads(CACHE.read_text())


def money(n):
    sign = "-" if n < 0 else ""
    return sign + "€" + f"{abs(n):,.2f}"


def add(bucket, row, gross=False):
    bucket["n"] += 1
    bucket["net"] += row["net"]
    if gross:
        bucket["gross"] += row["gross"]
        bucket["fee"] += row["fee"]


def blank():
    return {"n": 0, "net": 0.0, "gross": 0.0, "fee": 0.0}


def build():
    payload = load_rows()
    rows = payload["rows"]
    generated_at = payload["generatedAt"]

    totals = {k: blank() for k in ("charge", "refund", "dispute", "fee")}
    by_month = defaultdict(blank)
    by_category = defaultdict(blank)
    by_collective = defaultdict(blank)
    by_channel = defaultdict(blank)
    by_product = defaultdict(blank)
    month_status = {}

    for row in rows:
        kind = row["kind"]
        month_status[row["month"]] = row["status"]
        if kind in SKIP_KINDS:
            continue
        if kind not in totals:
            totals[kind] = blank()
        add(totals[kind], row, gross=(kind == "charge"))
        add(by_month[row["month"]], row, gross=True)
        if kind in ("charge", "refund", "dispute"):
            add(by_category[row["category"]], row, gross=(kind == "charge"))
            add(by_collective[row["collective"]], row, gross=(kind == "charge"))
            app = row["application"]
            if not app:
                channel = "payment link or direct"
            elif app.startswith("ca_") or len(app) > 24:
                channel = "other"
            else:
                channel = app
            add(by_channel[channel], row, gross=(kind == "charge"))
            if row["product"]:
                add(by_product[row["product"]], row, gross=(kind == "charge"))

    net = sum(totals[k]["net"] for k in totals)
    months = sorted(by_month)
    max_net = max((by_month[m]["net"] for m in months), default=1) or 1

    def rows_html(mapping, limit=None):
        items = sorted(mapping.items(), key=lambda item: item[1]["net"], reverse=True)
        if limit:
            items = items[:limit]
        lines = []
        for name, bucket in items:
            lines.append(
                "<tr>"
                f"<td>{escape(name)}</td>"
                f"<td class='num'>{bucket['n']}</td>"
                f"<td class='num'>{money(bucket['gross'])}</td>"
                f"<td class='num'>{money(bucket['fee'])}</td>"
                f"<td class='num'>{money(bucket['net'])}</td>"
                "</tr>"
            )
        return "\n".join(lines)

    bars = []
    for month in months:
        bucket = by_month[month]
        width = max(2, round(bucket["net"] / max_net * 100)) if bucket["net"] > 0 else 2
        mark = " current" if month_status.get(month) == "current" else ""
        label = month + (" (open)" if month_status.get(month) == "current" else "")
        bars.append(
            "<div class='month'>"
            f"<span class='mname'>{escape(label)}</span>"
            f"<span class='track'><span class='fill{mark}' style='width:{width}%'></span></span>"
            f"<span class='mnet'>{money(bucket['net'])}</span>"
            "</div>"
        )

    charge = totals["charge"]
    refund = totals["refund"]
    dispute = totals["dispute"]
    adjust = totals["fee"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Commons Hub Stripe</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; background: #f3f0e8; color: #1c1915; font: 16px/1.45 ui-sans-serif, system-ui, sans-serif; }}
  main {{ max-width: 920px; margin: 0 auto; padding: 40px 20px 64px; }}
  h1 {{ font-size: 32px; font-weight: 650; letter-spacing: -0.03em; margin: 0 0 8px; }}
  h2 {{ font-size: 18px; margin: 36px 0 12px; }}
  p {{ margin: 0 0 12px; }}
  .lede {{ max-width: 62ch; color: #3f3a33; }}
  .figures {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 28px; }}
  .figure {{ background: #fffdf8; border: 1px solid #e2dcd0; border-radius: 12px; padding: 14px 14px 12px; }}
  .figure span {{ display: block; color: #6d665c; font-size: 13px; }}
  .figure strong {{ display: block; margin-top: 6px; font-size: 22px; font-variant-numeric: tabular-nums; letter-spacing: -0.03em; }}
  .chart {{ background: #fffdf8; border: 1px solid #e2dcd0; border-radius: 12px; padding: 8px 12px; }}
  .month {{ display: grid; grid-template-columns: 108px 1fr 110px; gap: 10px; align-items: center; padding: 3px 0; }}
  .mname, .mnet {{ font-size: 13px; font-variant-numeric: tabular-nums; }}
  .mnet {{ text-align: right; }}
  .track {{ height: 8px; background: #efeae1; border-radius: 99px; }}
  .fill {{ display: block; height: 8px; background: #1f6b4a; border-radius: 99px; }}
  .fill.current {{ background: #c4a15a; }}
  table {{ width: 100%; border-collapse: collapse; background: #fffdf8; border: 1px solid #e2dcd0; border-radius: 12px; overflow: hidden; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #efeae1; font-variant-numeric: tabular-nums; }}
  th {{ font-size: 12px; color: #6d665c; font-weight: 600; }}
  td.num, th.num {{ text-align: right; }}
  tr:last-child td {{ border-bottom: 0; }}
  .note {{ margin-top: 28px; color: #6d665c; font-size: 14px; max-width: 70ch; }}
  a {{ color: inherit; }}
  @media (max-width: 720px) {{
    .figures {{ grid-template-columns: 1fr 1fr; }}
  }}
</style>
</head>
<body>
<main>
  <h1>Stripe at Commons Hub</h1>
  <p class="lede">Card payments the Hub published in its open books. January 2024 through October 2026. October is still open, so that month will grow. Payouts to the bank are the same money leaving Stripe, so they are not added again.</p>
  <section class="figures">
    <div class="figure"><span>Card charges, gross</span><strong>{money(charge['gross'])}</strong></div>
    <div class="figure"><span>Stripe fees on those charges</span><strong>{money(charge['fee'])}</strong></div>
    <div class="figure"><span>Refunds</span><strong>{money(refund['net'])}</strong></div>
    <div class="figure"><span>Left after fees and refunds</span><strong>{money(net)}</strong></div>
  </section>
  <h2>Net by month</h2>
  <p class="lede">Each row is charges, refunds, disputes and Stripe adjustments for that month. The gold row is the current month.</p>
  <div class="chart">
    {''.join(bars)}
  </div>
  <h2>What people paid for</h2>
  <table>
    <thead><tr><th>Category</th><th class="num">Payments</th><th class="num">Gross</th><th class="num">Fees</th><th class="num">Net</th></tr></thead>
    <tbody>
    {rows_html(by_category)}
    </tbody>
  </table>
  <h2>Which collective</h2>
  <table>
    <thead><tr><th>Collective</th><th class="num">Payments</th><th class="num">Gross</th><th class="num">Fees</th><th class="num">Net</th></tr></thead>
    <tbody>
    {rows_html(by_collective)}
    </tbody>
  </table>
  <h2>Where the checkout ran</h2>
  <table>
    <thead><tr><th>Channel</th><th class="num">Payments</th><th class="num">Gross</th><th class="num">Fees</th><th class="num">Net</th></tr></thead>
    <tbody>
    {rows_html(by_channel)}
    </tbody>
  </table>
  <h2>Named products</h2>
  <table>
    <thead><tr><th>Product</th><th class="num">Payments</th><th class="num">Gross</th><th class="num">Fees</th><th class="num">Net</th></tr></thead>
    <tbody>
    {rows_html(by_product, limit=12)}
    </tbody>
  </table>
  <p class="note">Left after fees and refunds is {money(charge['net'])} of charge net, {money(refund['net'])} of refunds, {money(dispute['net'])} from one dispute, and {money(adjust['net'])} of Stripe fee adjustments. {charge['n']} charges, {refund['n']} refunds.</p>
  <p class="note">Contains data from Commons Hub Brussels, available under the Open Database License (ODbL): <a href="{API}">{API}</a>. Files generated at {escape(generated_at)}. Private individuals are not listed.</p>
</main>
</body>
</html>
"""
    OUT.write_text(html)
    print("wrote", OUT)
    print("generatedAt", generated_at)
    print("charges", round(charge["gross"], 2), "fees", round(charge["fee"], 2), "net left", round(net, 2))
    print("rows", len(rows), "months", len(months))


def escape(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


if __name__ == "__main__":
    build()
