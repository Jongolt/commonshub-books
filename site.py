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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #e7ebf0; color: #14181f; font: 16px/1.45 "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif; }
  main { width: min(380px, calc(100% - 32px)); }
  h1 { font-size: 28px; font-weight: 650; letter-spacing: -0.03em; margin: 0 0 8px; }
  p { margin: 0 0 20px; color: #3e4856; }
  form { display: grid; gap: 12px; }
  label { display: grid; gap: 6px; font-size: 14px; }
  input { font: inherit; padding: 10px 12px; border: 1px solid #cfd6e0; border-radius: 8px; background: #f7f8fa; color: inherit; }
  input:focus { outline: 2px solid #1c1915; outline-offset: 2px; }
  button { font: inherit; margin-top: 4px; padding: 10px 14px; border: 0; border-radius: 8px; background: #16324f; color: #f4f7fb; cursor: pointer; }
  button:hover { background: #10263c; }
  button:active { transform: scale(0.98); }
  button:disabled { opacity: 0.6; cursor: wait; }
  .err { min-height: 1.45em; margin: 0; color: #8a3a1e; font-size: 14px; }
  .built { margin: 24px 0 0; color: #3e4856; font-size: 13px; }
  .built a { color: inherit; }
  ::selection { background: #d5e0ec; color: #14181f; }
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
  <p class="built">Built with <a href="https://projects.dev/s#v1:Vercel~project">Stripe Projects</a>. Hosted on Vercel. Books from <a href="https://commonshub.brussels/opendata">Commons Hub open data</a>.</p>
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


INDIVIDUAL = "Private individual"


def vendor_label(bill):
    vendor = bill.get("vendor") or {}
    if vendor.get("type") == "individual" or not vendor.get("name"):
        return INDIVIDUAL
    return vendor["name"]


def what_label(bill):
    if vendor_label(bill) == INDIVIDUAL:
        return "Name withheld in the open data"
    line = ""
    lines = bill.get("lines") or []
    if lines:
        line = first_line(lines[0].get("description") or "")
    if not line:
        line = first_line(bill.get("description") or "")
    if not line.strip("? ."):
        return "No description on the bill"
    return line


DESK_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Commons Hub books</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
  :root {
    --bg: #e7ebf0;
    --ink: #14181f;
    --muted: #3e4856;
    --line: #cfd6e0;
    --paper: #f7f8fa;
    --action: #16324f;
    --late: #8c341c;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.45 "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif; }
  a { color: inherit; }
  button, input { font: inherit; color: inherit; }
  ::selection { background: #d5e0ec; }
  :focus-visible { outline: 2px solid var(--action); outline-offset: 2px; }
  header { display: flex; align-items: baseline; gap: 16px; padding: 20px 24px 0; }
  header h1 { font-size: 1.25rem; font-weight: 600; letter-spacing: -0.02em; margin: 0; }
  header p { margin: 0; color: var(--muted); font-size: 14px; }
  header .stack { margin-left: auto; font-size: 14px; color: var(--action); }
  header .out { font-size: 14px; }
  .desk { display: grid; grid-template-columns: minmax(280px, 1fr) minmax(300px, 420px); gap: 20px; padding: 20px 24px 48px; align-items: start; }
  .queue, .slip, .cardbook { background: var(--paper); border: 1px solid var(--line); }
  .queue { min-height: 420px; }
  .bar { display: flex; gap: 8px; padding: 12px; border-bottom: 1px solid var(--line); }
  .bar input { flex: 1; border: 1px solid var(--line); background: #fff; padding: 8px 10px; }
  .list { list-style: none; margin: 0; padding: 0; }
  .lane { margin: 0; padding: 12px 12px 4px; font-size: 13px; color: var(--muted); }
  .lane + .list { border-top: 1px solid var(--line); }
  #list { max-height: 70vh; overflow: auto; }
  .list button { width: 100%; text-align: left; border: 0; border-bottom: 1px solid var(--line); background: transparent; padding: 10px 12px; display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; cursor: pointer; }
  .list button:hover { background: #eef2f6; }
  .list button[aria-current="true"] { background: #e4ebf3; }
  .list button:active { transform: scale(0.995); }
  .who { font-weight: 500; }
  .what, .meta { color: var(--muted); font-size: 13px; }
  .amt { font-variant-numeric: tabular-nums; text-align: right; }
  .days { font-variant-numeric: tabular-nums; text-align: right; font-size: 13px; }
  .days.late { color: var(--late); }
  .empty { padding: 16px 12px; color: var(--muted); }
  .slip { position: sticky; top: 16px; padding: 20px; }
  .slip .kicker { margin: 0; color: var(--muted); font-size: 13px; }
  .slip h2 { margin: 8px 0 4px; font-size: 1.35rem; font-weight: 600; letter-spacing: -0.02em; }
  .ref { font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 1.05rem; margin: 16px 0; }
  .slip dl { display: grid; grid-template-columns: 88px 1fr; gap: 6px 10px; margin: 0 0 16px; }
  .slip dt { color: var(--muted); font-size: 13px; }
  .slip dd { margin: 0; font-variant-numeric: tabular-nums; }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .actions button, .actions a { background: var(--action); color: #f4f7fb; text-decoration: none; border: 0; padding: 10px 14px; cursor: pointer; }
  .actions button:hover, .actions a:hover { background: #10263c; }
  .actions button:active, .actions a:active { transform: scale(0.98); }
  .actions .ghost { background: transparent; color: var(--ink); border: 1px solid var(--line); }
  .hint { margin: 14px 0 0; color: var(--muted); font-size: 14px; max-width: 42ch; }
  .cardbook { grid-column: 1 / -1; padding: 16px 20px 8px; }
  .cardbook h2 { font-size: 1rem; margin: 0 0 6px; }
  .cardbook p { margin: 0 0 12px; color: var(--muted); max-width: 70ch; }
  .totals { display: flex; flex-wrap: wrap; gap: 16px 28px; font-variant-numeric: tabular-nums; margin-bottom: 8px; }
  .totals span { display: block; color: var(--muted); font-size: 12px; }
  .foot { grid-column: 1 / -1; color: var(--muted); font-size: 13px; max-width: 70ch; }
  @media (max-width: 800px) {
    header { flex-wrap: wrap; }
    .desk { grid-template-columns: 1fr; padding: 16px; }
    .slip { position: static; order: -1; }
    .list { max-height: none; }
  }
  @media (prefers-reduced-motion: reduce) {
    .list button:active, .actions button:active, .actions a:active { transform: none; }
  }
</style>
</head>
<body>
<header>
  <h1>Commons Hub books</h1>
  <p id="asof"></p>
  <a class="stack" href="https://projects.dev/s#v1:Vercel~project">Built with Stripe Projects</a>
  <a class="out" href="/api/logout">Sign out</a>
</header>
<div class="desk">
  <section class="queue">
    <div class="bar">
      <input id="q" type="search" placeholder="Vendor or reference" aria-label="Filter bills">
    </div>
    <div id="list"></div>
  </section>
  <aside class="slip" id="slip"></aside>
  <section class="cardbook" id="cardbook"></section>
  <p class="foot" id="foot"></p>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>
const data = JSON.parse(document.getElementById("data").textContent);
const list = document.getElementById("list");
const slip = document.getElementById("slip");
const q = document.getElementById("q");
const ASIDE_KEY = "chb_aside";
let current = null;
let aside = readAside();

function money(amount, currency) {
  const sign = amount < 0 ? "-" : "";
  const number = Math.abs(amount).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency === "USD" ? sign + "$" + number : sign + "€" + number;
}

function daysLabel(days) {
  if (days === null || days === undefined) return "";
  if (days < 0) return "due in " + Math.abs(days) + " days";
  if (days === 0) return "due today";
  return days + " days open";
}

function filtered() {
  const needle = q.value.trim().toLowerCase();
  return data.bills.filter((bill) => {
    if (!needle) return true;
    return (bill.vendor + " " + bill.what + " " + bill.number).toLowerCase().includes(needle);
  });
}

function pickDefault(bills) {
  const ranked = bills.slice().sort((a, b) => (b.score || 0) - (a.score || 0));
  return ranked[0] || null;
}

function billKey(bill) {
  return bill.number + "|" + bill.amount + "|" + bill.due;
}

function readAside() {
  try {
    const raw = JSON.parse(sessionStorage.getItem(ASIDE_KEY) || "[]");
    return new Set(Array.isArray(raw) ? raw : []);
  } catch (err) {
    return new Set();
  }
}

function writeAside() {
  try {
    sessionStorage.setItem(ASIDE_KEY, JSON.stringify(Array.from(aside)));
  } catch (err) {}
}

function nextBill() {
  if (!current) return;
  aside.add(billKey(current));
  writeAside();
  const left = filtered().filter((bill) => !aside.has(billKey(bill)));
  current = pickDefault(left.filter((bill) => bill.lane === "pay")) || pickDefault(left);
  renderList();
}

function renderSlip(bill) {
  if (!bill) {
    slip.innerHTML = "<p class='hint'>No bill matches.</p>";
    return;
  }
  const late = bill.days >= 90 ? " late" : "";
  slip.innerHTML =
    "<p class='kicker'>" + (bill.lane === "check" ? "Check before you pay" : "Pay the Hub, not the vendor") + "</p>" +
    "<h2>" + escapeHtml(bill.vendor) + "</h2>" +
    "<p class='what'>" + escapeHtml(bill.what) + "</p>" +
    "<p class='ref' id='ref'>" + escapeHtml(bill.number) + "</p>" +
    "<dl>" +
    "<dt>Amount</dt><dd>" + money(bill.amount, bill.currency) + "</dd>" +
    "<dt>Due</dt><dd>" + escapeHtml(bill.due || "no date") + "</dd>" +
    "<dt>Age</dt><dd class='days" + late + "'>" + escapeHtml(daysLabel(bill.days)) + "</dd>" +
    "</dl>" +
    "<div class='actions'>" +
    "<button type='button' id='copy'>Copy reference</button>" +
    "<a href='https://commonshub.brussels/donate'>Pay the Hub</a>" +
    "<button type='button' class='ghost' id='next'>Next bill</button>" +
    "</div>" +
    "<p class='hint'>" + (bill.lane === "check" ? "Confirm the debit left before you send this reference." : "Put the reference in the donation message.") + "</p>";
  document.getElementById("copy").addEventListener("click", async () => {
    const button = document.getElementById("copy");
    try {
      await navigator.clipboard.writeText(bill.number);
      button.textContent = "Copied";
    } catch (err) {
      button.textContent = "Select the reference";
    }
  });
  document.getElementById("next").addEventListener("click", nextBill);
}

function sameBill(a, b) {
  return a && b && a.number === b.number && a.amount === b.amount && a.due === b.due;
}

function renderGroup(title, note, bills, restore) {
  const head = document.createElement("p");
  head.className = "lane";
  head.textContent = title;
  list.appendChild(head);
  if (note) {
    const extra = document.createElement("p");
    extra.className = "what";
    extra.style.padding = "0 12px 8px";
    extra.textContent = note;
    list.appendChild(extra);
  }
  const group = document.createElement("ul");
  group.className = "list";
  if (!bills.length) {
    const item = document.createElement("li");
    item.className = "empty";
    item.textContent = "None.";
    group.appendChild(item);
  }
  for (const bill of bills) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    if (sameBill(current, bill)) button.setAttribute("aria-current", "true");
    button.innerHTML =
      "<span class='who'>" + escapeHtml(bill.vendor) + "</span>" +
      "<span class='amt'>" + money(bill.amount, bill.currency) + "</span>" +
      "<span class='what'>" + escapeHtml(bill.what) + "</span>" +
      "<span class='days" + (bill.days >= 90 ? " late" : "") + "'>" + escapeHtml(daysLabel(bill.days)) + "</span>";
    button.addEventListener("click", () => {
      if (restore) {
        aside.delete(billKey(bill));
        writeAside();
      }
      current = bill;
      renderList();
    });
    item.appendChild(button);
    group.appendChild(item);
  }
  list.appendChild(group);
}

function renderList() {
  const bills = filtered();
  const active = bills.filter((bill) => !aside.has(billKey(bill)));
  const held = bills.filter((bill) => aside.has(billKey(bill)));
  if (!bills.some((bill) => sameBill(current, bill))) {
    current = pickDefault(active.filter((bill) => bill.lane === "pay")) || pickDefault(active) || pickDefault(held);
  }
  list.innerHTML = "";
  if (!bills.length) {
    const item = document.createElement("p");
    item.className = "empty";
    item.textContent = "No bill matches.";
    list.appendChild(item);
  } else {
    renderGroup("Pay next", "", active.filter((bill) => bill.lane === "pay"));
    renderGroup("Check first", "A direct debit can already have left. The bill stays open until it is reconciled.", active.filter((bill) => bill.lane === "check"));
    if (held.length) {
      renderGroup("Set aside", "Skipped in this browser only. The Hub books are unchanged.", held, true);
    }
  }
  renderSlip(current);
}

function escapeHtml(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

document.getElementById("asof").textContent =
  money(data.open.EUR.due, "EUR") + " still open across " + data.open.EUR.count + " euro bills. " +
  money(data.open.USD.due, "USD") + " still open across " + data.open.USD.count + " dollar bills. As of " + data.asOf + ".";
q.addEventListener("input", renderList);
renderList();

const stripe = data.stripe;
document.getElementById("cardbook").innerHTML =
  "<h2>Stripe card book</h2>" +
  "<p>What came into the Hub through Stripe from January 2024 through October 2026, from the public open data. Payouts to the bank are the same money leaving Stripe, so they are not counted again. This money does not close the bills on the desk.</p>" +
  "<div class='totals'>" +
  "<div><span>Gross</span>" + money(stripe.gross, "EUR") + "</div>" +
  "<div><span>Fees</span>" + money(stripe.fee, "EUR") + "</div>" +
  "<div><span>Refunds</span>" + money(stripe.refund, "EUR") + "</div>" +
  "<div><span>Left</span>" + money(stripe.net, "EUR") + "</div>" +
  "</div>";
document.getElementById("foot").innerHTML =
  "Contains data from Commons Hub Brussels, available under the Open Database License (ODbL): <a href='https://commonshub.brussels/opendata'>commonshub.brussels/opendata</a>. Bills generated at " +
  escapeHtml(data.billsGeneratedAt) + ". Stripe rows generated at " + escapeHtml(data.stripeGeneratedAt) + ". " +
  "Built with <a href='https://projects.dev/s#v1:Vercel~project'>Stripe Projects</a>, hosted on Vercel.";
</script>
</body>
</html>
"""


def build():
    bills_payload = load_bills()
    stripe = stripe_summary()
    as_of = date.fromisoformat(bills_payload["generatedAt"][:10])
    bills = bills_payload["bills"]
    CHECK_VENDORS = {"Proximus SA de droit public", "KBC Bank NV"}

    def pack(bill):
        due = bill.get("dueDate") or ""
        days = None
        if due:
            y, m, d = map(int, due.split("-"))
            days = (as_of - date(y, m, d)).days
        amount = round(bill.get("amountDue") or 0, 2)
        vendor = vendor_label(bill)
        lane = "check" if vendor in CHECK_VENDORS else "pay"
        return {
            "number": bill.get("number") or "",
            "vendor": vendor,
            "what": what_label(bill),
            "due": due,
            "days": days if days is not None else 0,
            "amount": amount,
            "currency": bill.get("currency") or "EUR",
            "lane": lane,
            "score": max(days or 0, 0) * amount,
        }

    packed = [pack(bill) for bill in bills]
    packed.sort(key=lambda item: -item["score"])
    charge = stripe["charge"]
    payload = {
        "asOf": as_of.isoformat(),
        "billsGeneratedAt": bills_payload["generatedAt"],
        "stripeGeneratedAt": stripe["generatedAt"],
        "bills": packed,
        "open": {
            "EUR": {
                "count": bills_payload["totalsByCurrency"]["EUR"]["count"],
                "due": bills_payload["totalsByCurrency"]["EUR"]["amountDue"],
            },
            "USD": {
                "count": bills_payload["totalsByCurrency"]["USD"]["count"],
                "due": bills_payload["totalsByCurrency"]["USD"]["amountDue"],
            },
        },
        "stripe": {
            "gross": round(charge["gross"], 2),
            "fee": round(charge["fee"], 2),
            "refund": round(stripe["refund"]["net"], 2),
            "net": round(stripe["net"], 2),
        },
    }
    raw = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    html = DESK_PAGE.replace("__DATA__", raw)
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
        '  res.setHeader("X-Content-Type-Options", "nosniff");\n'
        '  res.setHeader("X-Frame-Options", "DENY");\n'
        '  res.setHeader("Referrer-Policy", "no-referrer");\n'
        "  res.end(html);\n"
        "};\n"
    )
    OUT.write_text(LOGIN_PAGE)
    pay = [item for item in packed if item["lane"] == "pay"]
    print("wrote", OUT, "and", api / "books.js")
    print("pay", len(pay), "check", len(packed) - len(pay), "first", pay[0]["vendor"] if pay else None)


if __name__ == "__main__":
    build()
