# Commons Hub books

Open vendor bills for [Commons Hub Brussels](https://commonshub.brussels), and the card payments that came in through Stripe. The two lists are separate. Incoming card payments are not payments of the bills.

The site is at [commonshub-books.vercel.app](https://commonshub-books.vercel.app). It asks for a username and password before it shows the books. Those values stay on the host. They are not in this repository.

A bill stays on the list until the books are reconciled with the payment, so a direct debit can sit there after the money has already left. To pay one, donate to the Hub and put the bill reference in the message. Pay the Hub, not the vendor. [commonshub.brussels/donate](https://commonshub.brussels/donate)

Private individuals are not named.

## Data

The numbers come from the public read-only API at [commonshub.brussels/opendata](https://commonshub.brussels/opendata). No key is required. The dataset is under the Open Database License (ODbL).

`data/pending-bills.json` is the open bill list. `data/stripe-rows.json` is the public Stripe rows from January 2024 through October 2026, with payer names and application ids removed. Payouts to the bank are the same money leaving Stripe, so they are not added again.

`python3 site.py` rebuilds the books page from those two files.

Contains data from Commons Hub Brussels, available under the Open Database License (ODbL): https://commonshub.brussels/opendata
