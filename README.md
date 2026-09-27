# CFPB Bank Complaints Tracker

An automated data pipeline that pulls credit card complaints against major
U.S. banks from the CFPB's public complaint database, stores them
incrementally with no duplicates, and turns them into a comparison of how
issuers actually treat cardholders who complain.

## Headline finding

**Some issuers resolve complaints with real relief roughly twice as often
as others — and the gap holds even when comparing the exact same type of
complaint.** Citibank and Bank of America give monetary or non-monetary
relief in ~35-42% of credit card complaints; Chase and Capital One do so
in ~19-21%. Checked against issue mix (maybe some banks just get easier
complaints?) — no: Citibank/BofA are consistently higher and Chase is
consistently lower across nearly every major complaint category, including
the single largest one (billing/purchase disputes, over a third of all
complaints in the dataset). Full write-up with numbers: [FINDINGS.md](FINDINGS.md).

## How it works

1. **`src/fetch_complaints.py`** pulls complaints from the [CFPB Consumer
   Complaint Database API](https://cfpb.github.io/api/ccdb/) for a
   configurable list of banks (`config/companies.json`), filtered to
   credit card complaints only (`config/products.json`). First run grabs
   the last 12 months; every run after that only fetches complaints
   received since the last run. Complaints are stored in SQLite
   (`data/complaints.db`), keyed by the CFPB's own complaint ID, so
   re-running never creates duplicates.
2. **`src/build_summaries.py`** derives four aggregated summary tables
   (relief rate by bank, issue mix by bank, relief rate by bank within
   each issue, and sub-issues for "getting a credit card") — each with a
   sample-size flag so a percentage from a handful of complaints doesn't
   get mistaken for a real signal.
3. Findings from those tables are written up in plain language in
   [FINDINGS.md](FINDINGS.md).

Notable implementation detail: the CFPB API's documented pagination
(`frm`/`page`) is currently broken in production — requesting "page 2"
silently returns the same results as page 1 (verified against the live
API and against CFPB's own site making the same request). The fetch
script works around this with date-range bisection, splitting each
company's date range until every window is small enough to fetch in a
single request, rather than trusting multi-page pagination at all.

## Fields collected

Complaint ID, date received, company, product/sub-product, issue/sub-issue,
state, company response, timely-response flag, and a `consumer_complaint_narrative`
column reserved for future use (see Limitations).

## Limitations

- **No complaint narrative text yet.** The CFPB search API used here never
  returns the free-text narrative consumers submit — confirmed directly
  against live API responses, including CFPB's own complaint-detail page's
  own request. That text only exists in CFPB's separate full-database bulk
  CSV download, which isn't filterable by company/product/date. The
  `consumer_complaint_narrative` column is kept in the schema, keyed by the
  same `complaint_id` as everything else, so a future step can backfill
  real narrative text with a simple join.
- **Raw complaint counts aren't normalized** by number of cardholders or
  card balances per bank, so they're not a fair size-adjusted comparison
  on their own. The percentage-based tables (relief rate, issue mix) are
  the fair comparisons and are what the analysis leads with.
- **First and last calendar months of any pull are partial** (the 12-month
  window starts/ends mid-month) — exclude them from any future month-over-month
  trend view.

## Planned next steps

- Push the summary tables to Google Sheets so a Tableau Public dashboard
  can auto-refresh from them.
- Backfill real complaint narratives (via CFPB's bulk CSV download, joined
  by complaint ID) and use them for AI-based complaint theme tagging.

## Project structure

```
cfpb_bank_complaints/
├── config/
│   ├── companies.json      # list of banks to track (edit this to add/remove banks)
│   └── products.json       # product/sub-product filters that narrow the pull to credit cards
├── data/                    # created on first run; raw db/CSV are gitignored
│   ├── complaints.db
│   ├── complaints_export.csv
│   └── summaries/           # small aggregated CSVs, committed to the repo
├── src/
│   ├── db.py                # SQLite table setup and helper functions
│   ├── fetch_complaints.py  # main script: calls the API, saves data, exports CSV
│   └── build_summaries.py   # derives dashboard-ready summary tables from the raw data
├── requirements.txt
├── FINDINGS.md              # plain-language write-up of what the data shows
└── README.md
```

## Setup

```bash
cd cfpb_bank_complaints
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running it

```bash
python src/fetch_complaints.py   # pull/update raw complaint data
python src/build_summaries.py    # (re)build the summary tables
```

The first run of `fetch_complaints.py` takes a few minutes since it's
pulling a full year of credit card complaints for five large banks. Later
runs are much faster since they only fetch new complaints.

## Checking that it worked

- Watch the console output: it logs, per bank, how many complaints were
  fetched from the API and how many new rows were actually added to the
  database (should be the same on the first run, and close to the number
  of new complaints since your last run on later runs).
- Run `fetch_complaints.py` a second time immediately after the first —
  the log should show 0 (or very few) new rows added per bank, since
  nearly everything was already saved.
- Inspect the database directly:

```bash
sqlite3 data/complaints.db "SELECT company, COUNT(*) FROM complaints GROUP BY company;"
```

## Adding or removing banks

Edit `config/companies.json`. Company names must match the CFPB API's exact
`company` field spelling (e.g. `"CITIBANK, N.A."`, not `"Citibank"`) — the
easiest way to find the exact name is to search for the bank on the
[CFPB complaint search page](https://www.consumerfinance.gov/data-research/consumer-complaints/search/)
and copy the name shown in the results, or query the API directly with
`?company=<your search text>` and check the `company` value on returned
complaints.
