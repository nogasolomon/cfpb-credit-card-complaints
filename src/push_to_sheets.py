"""
Push the summary tables (built by build_summaries.py) to a Google Sheet, so
Tableau Public can connect to that Sheet and auto-refresh from it.

Each summary CSV in data/summaries/ gets its own tab in the Sheet, named
after the CSV. Every run replaces that tab's contents entirely, so the
Sheet always matches the latest local summary data -- it never accumulates
duplicate or stale rows.

Setup required before running this (see README.md for the full walkthrough):
1. A Google Cloud service account with a downloaded JSON key.
2. A Google Sheet you've created and shared with that service account's
   email address (as Editor).
3. config/sheets_config.json (copy config/sheets_config.example.json and
   fill in your spreadsheet ID and key file path). This file is
   gitignored -- never commit it, since the spreadsheet ID can be
   considered sensitive if the sheet isn't meant to be widely known.

Run it with:
    python src/push_to_sheets.py
"""

import json
import logging
from pathlib import Path

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHEETS_CONFIG_PATH = PROJECT_ROOT / "config" / "sheets_config.json"
SUMMARIES_DIR = PROJECT_ROOT / "data" / "summaries"

# A Google service account only needs this one scope to read/write Sheets.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_sheets_config():
    if not SHEETS_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"{SHEETS_CONFIG_PATH} not found. Copy config/sheets_config.example.json "
            "to config/sheets_config.json and fill in your own values -- see README.md."
        )
    with open(SHEETS_CONFIG_PATH) as f:
        return json.load(f)


def get_client(key_file_path):
    key_path = PROJECT_ROOT / key_file_path
    if not key_path.exists():
        raise FileNotFoundError(
            f"Service account key file not found at {key_path}. "
            "See README.md for how to create one in Google Cloud."
        )
    credentials = Credentials.from_service_account_file(str(key_path), scopes=SCOPES)
    return gspread.authorize(credentials)


def get_or_create_worksheet(spreadsheet, title, rows, cols):
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def push_summary_csv(spreadsheet, csv_path):
    """Replace one worksheet's contents with the contents of one summary CSV."""
    df = pd.read_csv(csv_path)
    tab_name = csv_path.stem

    worksheet = get_or_create_worksheet(spreadsheet, tab_name, rows=len(df) + 1, cols=len(df.columns))
    worksheet.clear()

    values = [df.columns.tolist()] + df.astype(str).values.tolist()
    worksheet.update(values, "A1")
    logger.info("Pushed %d rows to tab '%s'", len(df), tab_name)


def run():
    config = load_sheets_config()
    client = get_client(config["service_account_key_file"])
    spreadsheet = client.open_by_key(config["spreadsheet_id"])

    csv_paths = sorted(SUMMARIES_DIR.glob("*.csv"))
    if not csv_paths:
        raise FileNotFoundError(
            f"No summary CSVs found in {SUMMARIES_DIR}. Run src/build_summaries.py first."
        )

    for csv_path in csv_paths:
        push_summary_csv(spreadsheet, csv_path)

    logger.info("Done. Spreadsheet: %s", spreadsheet.url)


if __name__ == "__main__":
    run()
