# Findings so far

Based on 42,932 credit card complaints filed with the CFPB against 5 banks
over the last 12 months (Sept 2025 - Sept 2026). Percentages below are fair
to compare across banks regardless of size, since they're all rates, not
raw counts. Any rate built from fewer than 100 complaints is called out as
a small sample, since a handful of complaints can swing a percentage a lot.

## 1. How much does each bank get complained about?

| Bank | Complaints |
|---|---|
| Capital One | 12,907 |
| Citibank | 11,581 |
| Chase | 6,906 |
| Bank of America | 5,863 |
| American Express | 5,675 |

Raw counts mostly track how many cardholders each bank has, so this number
alone doesn't say much about which bank treats people worse. The more
useful comparison is what happens *after* someone complains.

## 2. Some banks resolve complaints with relief far more often than others

"Relief" means the bank's official response was "Closed with monetary
relief" or "Closed with non-monetary relief" (as opposed to "Closed with
explanation," which usually means the bank didn't change anything).

| Bank | Any relief | Monetary relief specifically |
|---|---|---|
| Citibank | 42.3% | 28.7% |
| Bank of America | 35.0% | 31.3% |
| American Express | 22.4% | 15.5% |
| Capital One | 20.8% | 12.2% |
| Chase | 18.9% | 10.7% |

Citibank and Bank of America give relief roughly **twice as often** as
Chase and Capital One. Everyone responds "on time" 98.6-100% of the time,
so timeliness doesn't differentiate banks — the real difference is in what
banks *do* when they respond, not whether they respond.

## 3. That gap holds even for the same type of complaint — it isn't just issue mix

We checked whether Citibank/BofA's higher relief rate was just because
they happen to get an easier mix of complaints. It isn't. Relief rate by
bank, within the 6 most common issue types:

| Issue (complaint count) | Amex | BofA | Cap One | Citi | Chase |
|---|---|---|---|---|---|
| Problem with purchase on statement (15,406) | 26.4% | **47.3%** | 20.5% | 45.0% | **16.2%** |
| Other features/terms/problems (6,026) | 21.3% | 29.8% | 28.8% | 39.4% | 29.7% |
| Fees or interest (3,797) | 32.1% | 41.3% | 24.7% | 46.2% | 23.9% |
| Getting a credit card (3,531) | 16.2% | 22.6% | 26.7% | 38.8% | 16.3% |
| Closing your account (3,320) | 17.3% | 12.3% | 16.8% | **39.4%** | **8.4%** |
| Advertising/marketing/promos (2,335) | 15.5% | 26.0% | 31.6% | 27.9% | 25.0% |

Citibank and BofA are consistently high, and Chase is consistently low or
near-low, across almost every issue category — not just on average. This
looks like a genuine difference in how each bank handles complaints, not
an artifact of what people happen to complain to them about.

Capital One and Amex are more inconsistent: Capital One is *best* of all 5
banks on advertising/marketing complaints (31.6%, based on 561 complaints
— a solid sample, not a fluke) but *worst* on purchase disputes (20.5%),
the single biggest complaint category. Their relief behavior seems to
depend more on the specific issue than Citibank/BofA's or Chase's does.

## 4. What people are complaining about, overall

The single biggest complaint type by far is **"Problem with a purchase
shown on your statement"** — 15,406 complaints, over a third of all
credit card complaints across these 5 banks. This is largely billing
disputes and unauthorized-charge fights. The next-largest categories
("other features/terms," "fees or interest," "getting a credit card,"
"closing your account") are each much smaller, in the 3,000-6,000 range.

## What this suggests for the project

The data supports the "compare credit card issuers" framing well:
relief rate (both overall and broken down by issue) is a real,
issue-independent signal that differentiates banks, and it's an easy
percentage for a general audience to understand. Issue mix is a good
secondary cut — it shows what each bank's complaints are actually about,
which adds context to the headline relief numbers.

## Known limitations to keep in mind

- **No complaint narrative text.** The CFPB search API this pipeline uses
  never returns the free-text narrative — confirmed directly against live
  API responses, including CFPB's own complaint-detail page's own request.
  Only CFPB's separate full-database bulk CSV download has it. The
  `consumer_complaint_narrative` column exists in the database (keyed by
  `complaint_id`, same primary key as everything else) specifically so
  that a future step can backfill real narrative text with a simple join,
  for AI theme tagging later.
- **Raw complaint counts aren't normalized by bank size** (number of
  cardholders, card balances, etc.), so they're not a fair "which bank is
  worse" comparison on their own — the percentage-based tables (relief
  rate, issue mix) are the fair comparisons, and are what the dashboard
  should lead with.
- **First and last calendar months in the data are partial** (the 12-month
  window starts and ends mid-month), so any future month-by-month
  trend table should exclude those two months rather than show them as
  artificially low.
