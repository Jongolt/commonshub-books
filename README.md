# Commons Hub books

Open vendor bills for [Commons Hub Brussels](https://commonshub.brussels), and the card payments that came in through Stripe. The two lists are separate. Incoming card payments are not payments of the bills.

The site is at [commonshub-books.vercel.app](https://commonshub-books.vercel.app). It asks for a username and password before it shows the books. Those values stay on the host. They are not in this repository.

The desk ranks open bills by how late they are and how much they are. Copy the reference, then donate to the Hub. Pay the Hub, not the vendor. [commonshub.brussels/donate](https://commonshub.brussels/donate)

Proximus and KBC stay in Check first. A direct debit can already have left, and the bill stays open until it is reconciled.

Private individuals are not named.

## Stripe

Two things here are Stripe.

The hosting. The Vercel plan and project were provisioned with the Stripe Projects CLI, not by hand. `stripe projects add vercel/hobby` then `stripe projects add vercel/project`. The stack is at [projects.dev/s#v1:Vercel~project](https://projects.dev/s#v1:Vercel~project). `.projects/state.json` is the Stripe Projects record of that stack. Credentials stay in the ignored `.env` and vault.

The card book. The desk shows what came into the Hub through Stripe from January 2024 through October 2026: gross charges, Stripe fees, refunds, and what is left. These are the Hub's public Stripe rows from the open data, not a new payment flow. They are shown apart from the bills on purpose, because incoming card money does not close a vendor bill.

## Data

The numbers come from the public read-only API at [commonshub.brussels/opendata](https://commonshub.brussels/opendata). No key is required. The dataset is under the Open Database License (ODbL).

`data/pending-bills.json` is the open bill list. `data/stripe-rows.json` is the public Stripe rows from January 2024 through October 2026, with payer names and application ids removed. Payouts to the bank are the same money leaving Stripe, so they are not added again.

`python3 site.py` rebuilds the desk from those two files. The bill list is served only after a signed session cookie. The password is compared on the server and is not in the page.

Contains data from Commons Hub Brussels, available under the Open Database License (ODbL): https://commonshub.brussels/opendata
