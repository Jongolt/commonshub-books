#!/usr/bin/env python3
"""Accounting page: open vendor bills plus public Stripe card payments.

Reads Commons Hub open data. No Stripe account.
"""

import json
import urllib.request
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

API = "https://commonshub.brussels/opendata"
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "index.html"
BILLS_CACHE = ROOT / "data" / "pending-bills.json"
STRIPE_CACHE = ROOT / "data" / "stripe-rows.json"
SKIP_KINDS = {"payout", "payout_reversal"}

LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in · Commons Hub books</title>
<style>
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f3f0e8; color: #1c1915; font: 16px/1.45 ui-sans-serif, system-ui, sans-serif; }
  main { width: min(380px, calc(100% - 32px)); }
  h1 { font-size: 28px; font-weight: 650; letter-spacing: -0.03em; margin: 0 0 8px; }
  p { margin: 0 0 20px; color: #3f3a33; }
  form { display: grid; gap: 12px; }
  label { display: grid; gap: 6px; font-size: 14px; }
  input { font: inherit; padding: 10px 12px; border: 1px solid #cfc6b8; border-radius: 8px; background: #fffdf8; color: inherit; }
  input:focus { outline: 2px solid #1c1915; outline-offset: 2px; }
  button { font: inherit; margin-top: 4px; padding: 10px 14px; border: 0; border-radius: 8px; background: #1c1915; color: #f3f0e8; cursor: pointer; }
  button:hover { background: #3a342c; }
  button:active { transform: scale(0.98); }
  button:disabled { opacity: 0.6; cursor: wait; }
  .err { min-height: 1.45em; margin: 0; color: #8a3a1e; font-size: 14px; }
  ::selection { background: #e4d3a8; color: #1c1915; }
  @media (prefers-reduced-motion: reduce) { button:active { transform: none; } }
</style>
</head>
<body>
<main>
  <h1>Commons Hub books</h1>
  <p>Sign in to open the bills.</p>
  <form id="in">
    <label>Username
      <input name="username" autocomplete="username" required>
    </label>
    <label>Password
      <input name="password" type="password" autocomplete="current-password" required>
    </label>
    <button type="submit">Sign in</button>
    <p class="err" id="err" hidden>That username or password is wrong.</p>
  </form>
</main>
<script>
  const form = document.getElementById("in");
  const err = document.getElementById("err");
  const button = form.querySelector("button");
  fetch("/api/login").then((res) => {
    if (res.ok) location.replace("/books");
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    err.hidden = true;
    button.disabled = true;
    const data = new FormData(form);
    let res;
    try {
      res = await fetch("/api/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          username: data.get("username"),
          password: data.get("password"),
        }),
      });
    } catch (e) {
      res = null;
    }
    button.disabled = false;
    if (res && res.ok) location.assign("/books");
    else err.hidden = false;
  });
</script>
</body>
</html>
"""


def get(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def money(amount, currency="EUR"):
    sign = "-" if amount < 0 else ""
    number = f"{abs(amount):,.2f}"
    if currency == "USD":
        return sign + "$" + number
    return sign + "€" + number


def escape(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def first_line(text):
    line = (text or "").split("\n")[0].strip()
    if len(line) > 90:
        return line[:87] + "..."
    return line


def load_bills():
    if BILLS_CACHE.exists():
        return json.loads(BILLS_CACHE.read_text())
    payload = get(f"{API}/latest/pending-bills.json")
    BILLS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    BILLS_CACHE.write_text(json.dumps(payload))
    return payload


def stripe_summary():
    payload = json.loads(STRIPE_CACHE.read_text())
    totals = defaultdict(lambda: {"n": 0, "gross": 0.0, "fee": 0.0, "net": 0.0})
    by_month = defaultdict(lambda: {"net": 0.0})
    status = {}
    for row in payload["rows"]:
        kind = row["kind"]
        status[row["month"]] = row.get("status")
        if kind in SKIP_KINDS:
            continue
        bucket = totals[kind]
        bucket["n"] += 1
        bucket["net"] += row["net"]
        if kind == "charge":
            bucket["gross"] += row["gross"]
            bucket["fee"] += row["fee"]
        by_month[row["month"]]["net"] += row["net"]
    net = sum(bucket["net"] for bucket in totals.values())
    return {
        "generatedAt": payload["generatedAt"],
        "charge": totals["charge"],
        "refund": totals["refund"],
        "net": net,
        "months": sorted(by_month),
        "by_month": by_month,
        "status": status,
    }


def vendor_label(bill):
    vendor = bill.get("vendor") or {}
    if vendor.get("type") == "individual" or not vendor.get("name"):
        return "individual"
    return vendor["name"]


def what_label(bill):
    if vendor_label(bill) == "individual":
        return "individual"
    line = ""
    lines = bill.get("lines") or []
    if lines:
        line = first_line(lines[0].get("description") or "")
    if not line:
        line = first_line(bill.get("description") or "")
    return line or vendor_label(bill)


def build():
    bills_payload = load_bills()
    stripe = stripe_summary()
    as_of = date.fromisoformat(bills_payload["generatedAt"][:10])
    bills = bills_payload["bills"]
    eur = [b for b in bills if b.get("currency") == "EUR"]
    usd = [b for b in bills if b.get("currency") == "USD"]
    eur.sort(key=lambda b: -(b.get("amountDue") or 0))
    usd.sort(key=lambda b: -(b.get("amountDue") or 0))

    by_vendor = defaultdict(lambda: {"n": 0, "due": 0.0})
    for bill in eur:
        name = vendor_label(bill)
        if name == "individual":
            continue
        by_vendor[name]["n"] += 1
        by_vendor[name]["due"] += bill.get("amountDue") or 0
    vendor_rows = sorted(by_vendor.items(), key=lambda item: -item[1]["due"])

    def bill_rows(items, currency):
        lines = []
        for bill in items:
            due = bill.get("dueDate") or ""
            overdue = ""
            late = ""
            if due:
                y, m, d = map(int, due.split("-"))
                days = (as_of - date(y, m, d)).days
                overdue = str(days)
                if days >= 90:
                    late = " late"
            lines.append(
                "<tr>"
                f"<td class='keep'>{escape(due)}</td>"
                f"<td class='num keep{late}'>{overdue}</td>"
                f"<td>{escape(vendor_label(bill))}</td>"
                f"<td>{escape(what_label(bill))}</td>"
                f"<td class='num'>{money(bill.get('amountDue') or 0, currency)}</td>"
                f"<td><code>{escape(bill.get('number') or '')}</code></td>"
                "</tr>"
            )
        return "\n".join(lines)

    vendor_html = []
    for name, bucket in vendor_rows:
        if bucket["due"] < 100:
            continue
        vendor_html.append(
            "<tr>"
            f"<td>{escape(name)}</td>"
            f"<td class='num'>{bucket['n']}</td>"
            f"<td class='num'>{money(bucket['due'])}</td>"
            "</tr>"
        )

    max_net = max((stripe["by_month"][m]["net"] for m in stripe["months"]), default=1) or 1
    bars = []
    for month in stripe["months"]:
        net = stripe["by_month"][month]["net"]
        width = max(2, round(net / max_net * 100)) if net > 0 else 2
        mark = " current" if stripe["status"].get(month) == "current" else ""
        label = month + (" (open)" if stripe["status"].get(month) == "current" else "")
        bars.append(
            "<div class='month'>"
            f"<span class='mname'>{escape(label)}</span>"
            f"<span class='track'><span class='fill{mark}' style='width:{width}%'></span></span>"
            f"<span class='mnet'>{money(net)}</span>"
            "</div>"
        )

    charge = stripe["charge"]
    eur_due = bills_payload["totalsByCurrency"]["EUR"]["amountDue"]
    usd_due = bills_payload["totalsByCurrency"]["USD"]["amountDue"]
    generated = bills_payload["generatedAt"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Commons Hub books</title>
<style>
  body {{ margin: 0; background: #f3f0e8; color: #1c1915; font: 16px/1.45 ui-sans-serif, system-ui, sans-serif; }}
  main {{ max-width: 980px; margin: 0 auto; padding: 40px 20px 64px; }}
  h1 {{ font-size: 32px; font-weight: 650; letter-spacing: -0.03em; margin: 0 0 8px; }}
  h2 {{ font-size: 18px; margin: 36px 0 12px; }}
  p {{ margin: 0 0 12px; }}
  .lede {{ max-width: 68ch; color: #3f3a33; }}
  .figures {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 28px; }}
  .figure {{ background: #fffdf8; border: 1px solid #e2dcd0; border-radius: 12px; padding: 14px 14px 12px; }}
  .figure span {{ display: block; color: #6d665c; font-size: 13px; }}
  .figure strong {{ display: block; margin-top: 6px; font-size: 22px; font-variant-numeric: tabular-nums; letter-spacing: -0.03em; }}
  .wrap {{ overflow-x: auto; border: 1px solid #e2dcd0; border-radius: 12px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fffdf8; }}
  td.keep, th.keep, code {{ white-space: nowrap; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #efeae1; font-variant-numeric: tabular-nums; vertical-align: top; }}
  th {{ font-size: 12px; color: #6d665c; font-weight: 600; }}
  td.num, th.num {{ text-align: right; }}
  tr:last-child td {{ border-bottom: 0; }}
  code {{ font-size: 12px; }}
  .chart {{ background: #fffdf8; border: 1px solid #e2dcd0; border-radius: 12px; padding: 8px 12px; }}
  .month {{ display: grid; grid-template-columns: 108px 1fr 110px; gap: 10px; align-items: center; padding: 3px 0; }}
  .mname, .mnet {{ font-size: 13px; font-variant-numeric: tabular-nums; }}
  .mnet {{ text-align: right; }}
  .track {{ height: 8px; background: #efeae1; border-radius: 99px; }}
  .fill {{ display: block; height: 8px; background: #1f6b4a; border-radius: 99px; }}
  .fill.current {{ background: #c4a15a; }}
  .note {{ margin-top: 28px; color: #6d665c; font-size: 14px; max-width: 70ch; }}
  .session {{ margin: 0 0 12px; text-align: right; font-size: 14px; }}
  td.late {{ color: #8a3a1e; }}
  a {{ color: inherit; }}
  @media (max-width: 720px) {{
    .figures {{ grid-template-columns: 1fr 1fr; }}
  }}
</style>
</head>
<body>
<main>
  <p class="session"><a href="/api/logout">Sign out</a></p>
  <h1>Commons Hub books</h1>
  <p class="lede">Open vendor bills, and the card payments that came in through Stripe. A bill stays on this list until the books are reconciled with the payment, so a direct debit can sit here after the money has already left.</p>
  <section class="figures">
    <div class="figure"><span>Still to pay, euro</span><strong>{money(eur_due)}</strong></div>
    <div class="figure"><span>Euro bills</span><strong>{bills_payload['totalsByCurrency']['EUR']['count']}</strong></div>
    <div class="figure"><span>Still to pay, dollar</span><strong>{money(usd_due, 'USD')}</strong></div>
    <div class="figure"><span>Card charges, gross</span><strong>{money(charge['gross'])}</strong></div>
  </section>

  <h2>Who is owed</h2>
  <p class="lede">Euro bills from companies, grouped. Private individuals are not named.</p>
  <div class="wrap"><table>
    <thead><tr><th>Vendor</th><th class="num">Bills</th><th class="num">Due</th></tr></thead>
    <tbody>
    {''.join(vendor_html)}
    </tbody>
  </table></div>

  <h2>Euro bills</h2>
  <p class="lede">Days are counted from the due date to {as_of.isoformat()}. To pay one, donate to the Hub and put the bill number in the message. Do not pay the vendor.</p>
  <div class="wrap"><table>
    <thead><tr><th>Due</th><th class="num">Days</th><th>Vendor</th><th>What</th><th class="num">Due amount</th><th>Reference</th></tr></thead>
    <tbody>
    {bill_rows(eur, "EUR")}
    </tbody>
  </table></div>

  <h2>Dollar bills</h2>
  <div class="wrap"><table>
    <thead><tr><th>Due</th><th class="num">Days</th><th>Vendor</th><th>What</th><th class="num">Due amount</th><th>Reference</th></tr></thead>
    <tbody>
    {bill_rows(usd, "USD")}
    </tbody>
  </table></div>

  <h2>Card payments</h2>
  <p class="lede">Stripe charges from January 2024 through October 2026. October is still open. Payouts to the bank are the same money leaving Stripe, so they are not added again. This incoming money is not a payment of the bills above. Exact amounts of the large bills do not appear in the public transactions from March to October 2026.</p>
  <section class="figures">
    <div class="figure"><span>Card charges, gross</span><strong>{money(charge['gross'])}</strong></div>
    <div class="figure"><span>Stripe fees on those charges</span><strong>{money(charge['fee'])}</strong></div>
    <div class="figure"><span>Refunds</span><strong>{money(stripe['refund']['net'])}</strong></div>
    <div class="figure"><span>Left after fees and refunds</span><strong>{money(stripe['net'])}</strong></div>
  </section>
  <div class="chart">
    {''.join(bars)}
  </div>

  <p class="note">Donate: <a href="https://commonshub.brussels/donate">commonshub.brussels/donate</a>. The message should be the bill reference from the table.</p>
  <p class="note">Contains data from Commons Hub Brussels, available under the Open Database License (ODbL): <a href="{API}">{API}</a>. Bills generated at {escape(generated)}. Stripe rows generated at {escape(stripe['generatedAt'])}.</p>
</main>
</body>
</html>
"""
    api = ROOT / "api"
    api.mkdir(exist_ok=True)
    (api / "books.js").write_text(
        'const { readSession } = require("./auth");\n'
        "const html = " + json.dumps(html) + ";\n"
        "module.exports = function books(req, res) {\n"
        "  if (!readSession(req)) {\n"
        "    res.statusCode = 302;\n"
        '    res.setHeader("Location", "/");\n'
        "    res.end();\n"
        "    return;\n"
        "  }\n"
        "  res.statusCode = 200;\n"
        '  res.setHeader("Content-Type", "text/html; charset=utf-8");\n'
        '  res.setHeader("Cache-Control", "private, no-store");\n'
        "  res.end(html);\n"
        "};\n"
    )
    OUT.write_text(LOGIN_PAGE)
    print("wrote", OUT, "and", api / "books.js")
    print("eur", eur_due, "usd", usd_due, "stripe gross", round(charge["gross"], 2), "net", round(stripe["net"], 2))


if __name__ == "__main__":
    build()
