#!/usr/bin/env python3
"""
TINKA EXTERNAL CAPITAL INFLOW WEBHOOK LISTENER
Ingests authenticated clearing callbacks (Stripe, AU Bank Inflows)
and credits ESCROW_RESERVE via double-entry journal entries.
"""

import sys
import hmac
import json
import sqlite3
import hashlib
import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

ROOT_DIR = Path(__file__).resolve().parent
DB_PATH = ROOT_DIR / "tinka_verifiable.db"
WEBHOOK_SECRET = "whsec_tinka_verifiable_2026_prod"

def init_inflow_tables(conn: sqlite3.Connection):
    """Ensures external_deposits table is ready for intake."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS external_deposits (
            deposit_id TEXT PRIMARY KEY,
            source_rail TEXT NOT NULL,
            clearing_ref TEXT NOT NULL UNIQUE,
            amount_cents INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            payload_hash TEXT NOT NULL
        );
    """)

def process_inflow_deposit(source_rail: str, clearing_ref: str, amount_cents: int, raw_payload: str) -> dict:
    if amount_cents <= 0:
        return {"status": "REJECTED", "reason": "Amount must be strictly positive."}

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    try:
        init_inflow_tables(conn)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        deposit_id = f"DEP-{source_rail[:4].upper()}-{hashlib.sha256(clearing_ref.encode()).hexdigest()[:10].upper()}"
        payload_hash = hashlib.sha256(raw_payload.encode()).hexdigest()

        with conn:
            # 1. Idempotency Check & Inflow Logging
            cur.execute("""
                INSERT INTO external_deposits (
                    deposit_id, source_rail, clearing_ref, amount_cents, created_at, payload_hash, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (deposit_id, source_rail, clearing_ref, amount_cents, now, payload_hash, raw_payload))

            # 2. Credit ESCROW_RESERVE
            cur.execute("""
                UPDATE financial_accounts
                SET balance_cents = balance_cents + ?
                WHERE account_id = 'ESCROW_RESERVE';
            """, (amount_cents,))

            # 3. Create Immutable Journal Entry
            entry_sig = hashlib.sha256(f"INFLOW:{now}:{deposit_id}:{amount_cents}".encode()).hexdigest()
            cur.execute("""
                INSERT INTO financial_journal (
                    timestamp, source_account, dest_account,
                    amount_cents, quest_id, evidence_hash, entry_signature
                ) VALUES (?, 'EXTERNAL_INFLOW', 'ESCROW_RESERVE', ?, ?, ?, ?);
            """, (now, amount_cents, f"INFLOW-{deposit_id}", payload_hash, entry_sig))

        cur.execute("SELECT balance_cents FROM financial_accounts WHERE account_id = 'ESCROW_RESERVE';")
        new_escrow = cur.fetchone()[0]

        return {
            "status": "CREDITED",
            "deposit_id": deposit_id,
            "rail": source_rail,
            "clearing_ref": clearing_ref,
            "amount_cents": amount_cents,
            "amount_usd": amount_cents / 100.0,
            "updated_escrow_reserve_usd": new_escrow / 100.0,
            "evidence_hash": payload_hash
        }

    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed: external_deposits.clearing_ref" in str(e):
            return {
                "status": "REJECTED_DUPLICATE",
                "reason": f"Clearing reference '{clearing_ref}' was already cleared. Inflow replay blocked."
            }
        return {"status": "INTEGRITY_ERROR", "reason": str(e)}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}
    finally:
        conn.close()

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/webhook/inflow":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        signature = self.headers.get("X-Tinka-Signature", "")

        # HMAC-SHA256 signature verification
        expected_sig = hmac.new(WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid HMAC signature."}).encode())
            return

        try:
            data = json.loads(body)
            rail = data.get("rail", "GENERIC_BANK")
            clearing_ref = data.get("clearing_ref")
            amount_cents = int(data.get("amount_cents", 0))

            if not clearing_ref or amount_cents <= 0:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing clearing_ref or invalid amount_cents."}).encode())
                return

            result = process_inflow_deposit(rail, clearing_ref, amount_cents, body)
            code = 200 if result["status"] == "CREDITED" else 409
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

def run(port=8081):
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    print(f"[✓] Tinka Webhook Ingestion Listener active on port {port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
    run(p)
