"""
SQLite helper functions for the CFPB complaints pipeline.

Two tables:
- complaints: one row per complaint, keyed by complaint_id so re-running
  the pipeline never creates duplicates.
- sync_state: one row per company, remembering the date_received of the
  newest complaint we've already saved, so the next run only asks the
  API for complaints newer than that.
"""

import sqlite3

CREATE_COMPLAINTS_TABLE = """
CREATE TABLE IF NOT EXISTS complaints (
    complaint_id TEXT PRIMARY KEY,
    date_received TEXT,
    company TEXT,
    product TEXT,
    sub_product TEXT,
    issue TEXT,
    sub_issue TEXT,
    state TEXT,
    consumer_complaint_narrative TEXT,
    company_response TEXT,
    timely_response TEXT
);
"""

CREATE_SYNC_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS sync_state (
    company TEXT PRIMARY KEY,
    last_date_received TEXT
);
"""


def get_connection(db_path):
    """Open a connection to the SQLite database, creating tables if needed."""
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_COMPLAINTS_TABLE)
    conn.execute(CREATE_SYNC_STATE_TABLE)
    conn.commit()
    return conn


def get_last_date_received(conn, company):
    """Return the newest date_received we've stored for this company, or None."""
    row = conn.execute(
        "SELECT last_date_received FROM sync_state WHERE company = ?", (company,)
    ).fetchone()
    return row[0] if row else None


def set_last_date_received(conn, company, date_received):
    """Save the newest date_received we've seen for this company."""
    conn.execute(
        """
        INSERT INTO sync_state (company, last_date_received)
        VALUES (?, ?)
        ON CONFLICT(company) DO UPDATE SET last_date_received = excluded.last_date_received
        """,
        (company, date_received),
    )
    conn.commit()


def insert_complaints(conn, rows):
    """
    Insert complaint rows, skipping any complaint_id already in the table.
    Returns the number of rows actually added.
    """
    cursor = conn.executemany(
        """
        INSERT OR IGNORE INTO complaints (
            complaint_id, date_received, company, product, sub_product,
            issue, sub_issue, state, consumer_complaint_narrative,
            company_response, timely_response
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return cursor.rowcount
