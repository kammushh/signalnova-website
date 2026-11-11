"""
manage.py — maintenance commands for the whitepaper records.

    python3 manage.py stats                       # counts: requests, verified, downloads
    python3 manage.py export > leads.csv          # all verified leads as CSV
    python3 manage.py export --all > leads.csv    # include unverified addresses
    python3 manage.py delete --email a@b.com      # GDPR erasure request: removes everything
    python3 manage.py purge                       # retention clean-up (run daily from cron)

Retention (purge):
    - codes and download links older than 7 days are deleted
    - addresses that never verified are deleted after UNVERIFIED_RETENTION_DAYS (default 30)
"""

import argparse
import csv
import os
import sys

from dotenv import load_dotenv

load_dotenv()

import psycopg2
import psycopg2.extras

DB_DSN = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "dbname":   os.getenv("DB_NAME", "signalnova"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}
UNVERIFIED_DAYS = int(os.getenv("UNVERIFIED_RETENTION_DAYS", "30"))


def get_conn():
    return psycopg2.connect(**DB_DSN, cursor_factory=psycopg2.extras.RealDictCursor)


def stats(cur):
    cur.execute("""SELECT
        (SELECT count(*) FROM leads)                                   AS addresses,
        (SELECT count(*) FROM leads WHERE verified_at IS NOT NULL)      AS verified,
        (SELECT count(*) FROM leads WHERE download_count > 0)          AS downloaded,
        (SELECT count(*) FROM downloads)                                AS downloads,
        (SELECT count(*) FROM verification_codes
            WHERE created_at > now() - interval '24 hours')             AS codes_24h,
        (SELECT count(*) FROM verification_codes
            WHERE mail_error IS NOT NULL
              AND created_at > now() - interval '7 days')               AS mail_errors_7d""")
    for k, v in cur.fetchone().items():
        print(f"{k:16} {v}")


def export(cur, include_all: bool):
    cur.execute(f"""SELECT name, email, verified_at, created_at, consent_at, consent_text,
                           download_count, last_download_at
                    FROM leads {'' if include_all else 'WHERE verified_at IS NOT NULL'}
                    ORDER BY created_at""")
    rows = cur.fetchall()
    w = csv.writer(sys.stdout)
    w.writerow(["name", "email", "verified_at", "first_request_at", "consent_at", "consent_text",
                "downloads", "last_download_at"])
    for r in rows:
        w.writerow([r["name"], r["email"], r["verified_at"], r["created_at"], r["consent_at"],
                    r["consent_text"], r["download_count"], r["last_download_at"]])
    print(f"{len(rows)} rows", file=sys.stderr)


def delete(cur, email: str):
    cur.execute("DELETE FROM leads WHERE email = %s RETURNING id", (email.strip().lower(),))
    print("deleted (codes, links and downloads too)" if cur.fetchone() else "no such address")


def purge(cur):
    cur.execute("DELETE FROM verification_codes WHERE created_at < now() - interval '7 days'")
    codes = cur.rowcount
    cur.execute("DELETE FROM download_tokens WHERE expires_at < now() - interval '7 days'")
    links = cur.rowcount
    cur.execute("DELETE FROM leads WHERE verified_at IS NULL AND updated_at < now() - %s * interval '1 day'",
                (UNVERIFIED_DAYS,))
    print(f"purged: {codes} codes, {links} links, {cur.rowcount} unverified addresses")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    e = sub.add_parser("export"); e.add_argument("--all", action="store_true")
    d = sub.add_parser("delete"); d.add_argument("--email", required=True)
    sub.add_parser("purge")
    a = p.parse_args()

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            if a.cmd == "stats":
                stats(cur)
            elif a.cmd == "export":
                export(cur, a.all)
            elif a.cmd == "delete":
                delete(cur, a.email)
            elif a.cmd == "purge":
                purge(cur)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
