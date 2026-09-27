"""
Pull credit card consumer complaints about a list of banks from the CFPB
Consumer Complaint Database API, save them into a local SQLite database (no
duplicates), and export the full table to a CSV file. This powers a project
that helps people compare credit card issuers based on real complaint data.

First run: pulls the last 12 months of complaints for each company.
Every run after that: only pulls complaints received since the last run.

Run it with:
    python src/fetch_complaints.py
"""

import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

import db

# --- File locations -------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPANIES_CONFIG_PATH = PROJECT_ROOT / "config" / "companies.json"
PRODUCTS_CONFIG_PATH = PROJECT_ROOT / "config" / "products.json"
DB_PATH = PROJECT_ROOT / "data" / "complaints.db"
CSV_PATH = PROJECT_ROOT / "data" / "complaints_export.csv"

# --- CFPB API settings ------------------------------------------------------

API_URL = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"

# The CFPB API blocks requests that don't look like they come from a browser,
# so we send a normal browser User-Agent. This is set here in the script
# itself (not just in ad-hoc testing) so scheduled/unattended runs work too.
HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

PAGE_SIZE = 100  # max results per request the API allows
# As of this writing, the CFPB API's page-2-and-beyond pagination (both the
# documented `frm` param and the `page` param the CFPB website itself uses)
# is broken: requesting page 2 silently returns the same results as page 1
# (verified directly against the live API and against CFPB's own site).
# So instead of paging within a date window, we recursively bisect each
# company's date range until every window holds at most PAGE_SIZE results,
# then fetch each window with a single un-paginated request.
MAX_RESULTS_PER_WINDOW = PAGE_SIZE
MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_companies():
    """Read the list of company names to track from the config file."""
    with open(COMPANIES_CONFIG_PATH) as f:
        config = json.load(f)
    return config["companies"]


def load_product_filters():
    """
    Read the product/sub-product filters from the config file and turn them
    into the values the CFPB API's `product` query param expects: either a
    bare product name, or "Product•SubProduct" to narrow to one sub-product.
    """
    with open(PRODUCTS_CONFIG_PATH) as f:
        config = json.load(f)

    filters = []
    for entry in config["products"]:
        product = entry["product"]
        sub_products = entry.get("sub_products")
        if not sub_products:
            filters.append(product)
        else:
            for sub_product in sub_products:
                filters.append(f"{product}•{sub_product}")
    return filters


def request_with_retries(params):
    """
    Call the CFPB API with retries and exponential backoff for rate
    limiting (HTTP 429) and server errors (5xx).
    """
    backoff = INITIAL_BACKOFF_SECONDS
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
        except requests.RequestException as e:
            logger.warning("Request failed (%s), attempt %d/%d", e, attempt, MAX_RETRIES)
        else:
            if response.status_code == 200:
                return response.json()
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning(
                    "API returned %d, attempt %d/%d", response.status_code, attempt, MAX_RETRIES
                )
            else:
                response.raise_for_status()

        if attempt < MAX_RETRIES:
            time.sleep(backoff)
            backoff *= 2

    raise RuntimeError(f"CFPB API request failed after {MAX_RETRIES} attempts: {params}")


def base_params(company, product_filters, start_date, end_date):
    """
    Build the list of query params shared by every request for a company:
    the company name, one entry per allowed product/sub-product, and the
    date window. A list of tuples (not a dict) is used because `product`
    needs to be repeated once per allowed value.
    """
    params = [
        ("company", company),
        ("date_received_min", start_date.isoformat()),
        ("date_received_max", end_date.isoformat()),
    ]
    for product_filter in product_filters:
        params.append(("product", product_filter))
    return params


def count_complaints(company, product_filters, start_date, end_date):
    """Return how many matching complaints exist for a company/date range."""
    params = base_params(company, product_filters, start_date, end_date)
    params += [("size", 0), ("no_aggs", "true")]
    result = request_with_retries(params)
    return result["hits"]["total"]["value"]


def split_into_safe_windows(company, product_filters, start_date, end_date):
    """
    Break [start_date, end_date] into a list of (start, end) windows, each
    small enough that its complaint count stays under the API's 10,000
    result pagination limit. Uses a simple date-bisection: if a window has
    too many results, split it in half and check each half.
    """
    if start_date > end_date:
        return []

    total = count_complaints(company, product_filters, start_date, end_date)
    if total == 0:
        return []
    if total <= MAX_RESULTS_PER_WINDOW or start_date == end_date:
        return [(start_date, end_date)]

    midpoint = start_date + (end_date - start_date) // 2
    left = split_into_safe_windows(company, product_filters, start_date, midpoint)
    right = split_into_safe_windows(company, product_filters, midpoint + timedelta(days=1), end_date)
    return left + right


def fetch_window(company, product_filters, start_date, end_date):
    """
    Fetch every matching complaint for a company within a date window, in
    a single request. This relies on split_into_safe_windows() having
    already bisected the range so each window holds at most PAGE_SIZE
    results -- see the note on MAX_RESULTS_PER_WINDOW above for why we
    don't page within a window.
    """
    params = base_params(company, product_filters, start_date, end_date)
    params += [
        ("size", PAGE_SIZE),
        ("sort", "created_date_asc"),
        ("no_aggs", "true"),
    ]
    result = request_with_retries(params)
    total = result["hits"]["total"]["value"]
    if total > PAGE_SIZE:
        logger.warning(
            "Window %s to %s for %s has %d results, more than fit in one page "
            "(%d) -- some complaints in this window may be missed",
            start_date, end_date, company, total, PAGE_SIZE,
        )
    return [hit["_source"] for hit in result["hits"]["hits"]]


def fetch_company_complaints(company, product_filters, start_date, end_date):
    """Fetch every matching complaint for a company received in [start_date, end_date]."""
    windows = split_into_safe_windows(company, product_filters, start_date, end_date)
    complaints = []
    for window_start, window_end in windows:
        complaints.extend(fetch_window(company, product_filters, window_start, window_end))
    return complaints


def complaint_to_row(complaint):
    """Convert one CFPB API complaint record into a database row tuple."""
    return (
        complaint.get("complaint_id"),
        complaint.get("date_received"),
        complaint.get("company"),
        complaint.get("product"),
        complaint.get("sub_product"),
        complaint.get("issue"),
        complaint.get("sub_issue"),
        complaint.get("state"),
        # The CFPB search API does not return narrative text (only its
        # separate full-database bulk CSV download does), so this is
        # always empty for now. The column is kept, keyed by complaint_id,
        # so a future run can backfill real narratives via a join -- see
        # the README.
        complaint.get("complaint_what_happened", ""),
        complaint.get("company_response"),
        complaint.get("timely"),
    )


def run():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    companies = load_companies()
    product_filters = load_product_filters()
    conn = db.get_connection(DB_PATH)
    today = date.today()

    for company in companies:
        last_date_received = db.get_last_date_received(conn, company)
        if last_date_received:
            # Re-pull the last day too, in case more complaints came in
            # for that same date after our previous run.
            start_date = date.fromisoformat(last_date_received[:10])
        else:
            start_date = today - timedelta(days=365)

        logger.info("Fetching %s credit card complaints from %s to %s", company, start_date, today)
        complaints = fetch_company_complaints(company, product_filters, start_date, today)

        rows = [complaint_to_row(c) for c in complaints]
        added = db.insert_complaints(conn, rows)
        logger.info("%s: %d complaints fetched, %d new rows added", company, len(rows), added)

        if complaints:
            newest_date = max(c["date_received"] for c in complaints)
            db.set_last_date_received(conn, company, newest_date)

    export_to_csv(conn)
    conn.close()


def export_to_csv(conn):
    """Dump the full complaints table to a CSV file for easy inspection."""
    df = pd.read_sql_query("SELECT * FROM complaints", conn)
    df.to_csv(CSV_PATH, index=False)
    logger.info("Exported %d total rows to %s", len(df), CSV_PATH)


if __name__ == "__main__":
    run()
