"""
Build dashboard-ready summary tables from the raw complaints data.

This is a separate step from fetch_complaints.py on purpose: fetching
collects raw complaint rows, this script derives aggregated views on top of
them. Re-run it any time after fetch_complaints.py to refresh the summaries.

Produces four summary tables, saved both as tables in the SQLite database
(for later reuse, e.g. by a Google Sheets export step) and as CSV files in
data/summaries/ (for easy inspection now):

1. relief_by_bank            - overall relief rate per bank
2. issue_mix_by_bank         - each bank's complaints broken down by issue, as a percentage
3. relief_by_bank_and_issue  - relief rate per bank, within each issue
4. credit_card_subissues     - sub-issues under "Getting a credit card", per bank, as a percentage

Every percentage is reported alongside its underlying complaint count, and
any bank/issue combination built from fewer than SMALL_SAMPLE_THRESHOLD
complaints is flagged, since a rate computed from a handful of complaints
can be misleading.

NOTE on monthly tables: none of the four tables here group by month, but if
a future summary does, exclude the first and last calendar months from the
date range first -- those are partial months (the pipeline's 12-month
window starts and ends mid-month), and including them would understate
volume for those months and make trends look misleading.
"""

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "complaints.db"
SUMMARIES_DIR = PROJECT_ROOT / "data" / "summaries"

SMALL_SAMPLE_THRESHOLD = 100

RELIEF_RESPONSES = {"Closed with monetary relief", "Closed with non-monetary relief"}
MONETARY_RELIEF_RESPONSE = "Closed with monetary relief"


def load_complaints(conn):
    df = pd.read_sql_query("SELECT * FROM complaints", conn)
    df["got_relief"] = df["company_response"].isin(RELIEF_RESPONSES)
    df["got_monetary_relief"] = df["company_response"] == MONETARY_RELIEF_RESPONSE
    return df


def flag_small_sample(df, count_col="complaint_count"):
    df["small_sample"] = df[count_col] < SMALL_SAMPLE_THRESHOLD
    return df


def build_relief_by_bank(df):
    """Overall relief rate per bank, any relief and monetary relief specifically."""
    summary = df.groupby("company").agg(
        complaint_count=("complaint_id", "count"),
        any_relief_rate=("got_relief", "mean"),
        monetary_relief_rate=("got_monetary_relief", "mean"),
    ).reset_index()
    summary["any_relief_rate"] = summary["any_relief_rate"].round(3)
    summary["monetary_relief_rate"] = summary["monetary_relief_rate"].round(3)
    return flag_small_sample(summary).sort_values("any_relief_rate", ascending=False)


def build_issue_mix_by_bank(df):
    """Each bank's complaints broken down by issue, as a percentage of that bank's total."""
    counts = df.groupby(["company", "issue"]).size().reset_index(name="complaint_count")
    bank_totals = df.groupby("company").size().rename("bank_total")
    counts = counts.join(bank_totals, on="company")
    counts["pct_of_bank_complaints"] = (counts["complaint_count"] / counts["bank_total"]).round(3)
    counts = counts.drop(columns="bank_total")
    return flag_small_sample(counts).sort_values(["company", "pct_of_bank_complaints"], ascending=[True, False])


def build_relief_by_bank_and_issue(df):
    """Relief rate per bank, within each issue."""
    summary = df.groupby(["company", "issue"]).agg(
        complaint_count=("complaint_id", "count"),
        any_relief_rate=("got_relief", "mean"),
        monetary_relief_rate=("got_monetary_relief", "mean"),
    ).reset_index()
    summary["any_relief_rate"] = summary["any_relief_rate"].round(3)
    summary["monetary_relief_rate"] = summary["monetary_relief_rate"].round(3)
    return flag_small_sample(summary).sort_values(["issue", "any_relief_rate"], ascending=[True, False])


def build_credit_card_subissues(df):
    """Sub-issues under 'Getting a credit card', per bank, as a percentage of that bank's complaints in this issue."""
    subset = df[df["issue"] == "Getting a credit card"].copy()
    counts = subset.groupby(["company", "sub_issue"]).size().reset_index(name="complaint_count")
    bank_totals = subset.groupby("company").size().rename("bank_total_for_issue")
    counts = counts.join(bank_totals, on="company")
    counts["pct_of_bank_complaints_in_issue"] = (counts["complaint_count"] / counts["bank_total_for_issue"]).round(3)
    counts = counts.drop(columns="bank_total_for_issue")
    return flag_small_sample(counts).sort_values(["company", "pct_of_bank_complaints_in_issue"], ascending=[True, False])


def save(name, df, conn):
    df.to_sql(name, conn, if_exists="replace", index=False)
    csv_path = SUMMARIES_DIR / f"{name}.csv"
    df.to_csv(csv_path, index=False)
    print(f"{name}: {len(df)} rows -> table '{name}' in complaints.db and {csv_path}")


def run():
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    df = load_complaints(conn)

    save("relief_by_bank", build_relief_by_bank(df), conn)
    save("issue_mix_by_bank", build_issue_mix_by_bank(df), conn)
    save("relief_by_bank_and_issue", build_relief_by_bank_and_issue(df), conn)
    save("credit_card_subissues", build_credit_card_subissues(df), conn)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    run()
