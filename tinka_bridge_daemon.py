#!/usr/bin/env python3
import os
import sys
import json
import hmac
import hashlib
import sqlite3
import datetime
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DB_PATH = ROOT_DIR / "tinka_verifiable.db"

# Configuration (defaults to mock test secrets if not in environment)
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret_key_12345")
TARGET_TREASURY_EVM = os.getenv("TARGET_TREASURY_EVM", "0x742d35Cc6634C0532925a3b844Bc454e4438f44e").lower()
EVM_RPC_URL = os.getenv("EVM_RPC_URL", "https://ethereum-rpc.publicnode.com")

def init_bridge_tables():
    """Ensures deduplication tables exist to prevent transaction replay attacks."""
    conn = sqlite3.connect(str(DB_PATH))
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS external_deposits (
                deposit_id TEXT PRIMARY KEY,
                source_rail TEXT NOT NULL,
                clearing_ref TEXT NOT NULL UNIQUE,
                amount_cents INTEGER NOT NULL,
                raw_payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
    conn.close()

def credit_escrow_reserve(clearing_ref: str, source_rail: str, amount_cents: int, raw_payload: str) -> dict:
    """Double-entry transaction that credits ESCROW_RESERVE with atomic replay protection."""
    if amount_cents <= 0:
        raise ValueError("Deposit amount must be strictly positive.")

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA foreign_keys=ON;")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    dep_id = f"DEP-{hashlib.sha256(clearing_ref.encode()).hexdigest()[:12].upper()}"

    try:
        with conn:
            # 1. Record deposit in idempotent deduplication table
            conn.execute("""
                INSERT INTO external_deposits (deposit_id, source_rail, clearing_ref, amount_cents, raw_payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (dep_id, source_rail, clearing_ref, amount_cents, raw_payload, now))

            # 2. Credit the authoritative ESCROW_RESERVE account
            conn.execute("""
                UPDATE financial_accounts
                SET balance_cents = balance_cents + ?
                WHERE account_id = 'ESCROW_RESERVE';
            """, (amount_cents,))

            # 3. Log into financial journal for end-to-end auditability
            sig = hashlib.sha256(f"INGEST:{now}:{clearing_ref}:{amount_cents}".encode()).hexdigest()
            conn.execute("""
                INSERT INTO financial_journal (
                    timestamp, source_account, dest_account, 
                    amount_cents, quest_id, evidence_hash, entry_signature
                ) VALUES (?, 'EXTERNAL_INFLOW', 'ESCROW_RESERVE', ?, ?, ?, ?);
            """, (now, amount_cents, f"FUNDING-{source_rail}", clearing_ref, sig))

        cur = conn.cursor()
        cur.execute("SELECT balance_cents FROM financial_accounts WHERE account_id = 'ESCROW_RESERVE';")
        new_escrow = cur.fetchone()[0]
        conn.close()
        return {
            "status": "SUCCESS",
            "deposit_id": dep_id,
            "amount_cents": amount_cents,
            "new_escrow_balance_cents": new_escrow,
            "clearing_ref": clearing_ref
        }
    except sqlite3.IntegrityError as e:
        conn.close()
        if "UNIQUE constraint failed" in str(e):
            return {"status": "DUPLICATE_REJECTED", "reason": f"Ref {clearing_ref} has already been credited."}
        raise

def verify_stripe_signature(payload_bytes: bytes, sig_header: str, secret: str) -> bool:
    """Validates Stripe HMAC-SHA256 signature scheme (t=...,v1=...)."""
    if not sig_header:
        return False
    pairs = dict(item.split("=", 1) for item in sig_header.split(",") if "=" in item)
    t = pairs.get("t")
    v1 = pairs.get("v1")
    if not t or not v1:
        return False

    signed_payload = f"{t}.".encode("utf-8") + payload_bytes
    computed = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, v1)

def verify_evm_transaction(tx_hash: str) -> dict:
    """Queries an EVM node to verify that a transaction is confirmed and sent to our treasury."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_getTransactionReceipt",
        "params": [tx_hash],
        "id": 1
    }).encode("utf-8")

    req = urllib.request.Request(
        EVM_RPC_URL,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "TinkaBridge/1.0"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10.0) as res:
            data = json.loads(res.read().decode("utf-8"))
            receipt = data.get("result")
            if not receipt:
                return {"valid": False, "reason": "Transaction pending or not found"}
            if receipt.get("status") != "0x1":
                return {"valid": False, "reason": "Transaction execution reverted"}
            
            # Simple direct transfer validation
            to_addr = (receipt.get("to") or "").lower()
            if to_addr != TARGET_TREASURY_EVM:
                return {"valid": False, "reason": f"Recipient {to_addr} does not match treasury {TARGET_TREASURY_EVM}"}
            
            return {"valid": True, "block_number": receipt.get("blockNumber")}
    except Exception as e:
        return {"valid": False, "reason": f"RPC Failure: {str(e)}"}


class TinkaBridgeHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_len)

        # -------------------------------------------------------------
        # Route 1: Stripe Webhook Receiver
        # -------------------------------------------------------------
        if self.path == "/webhook/stripe":
            sig_header = self.headers.get("Stripe-Signature", "")
            
            # Signature Check (Skipped if testing in dry-run with test header)
            is_valid = verify_stripe_signature(raw_body, sig_header, STRIPE_WEBHOOK_SECRET)
            if not is_valid and self.headers.get("X-Tinka-Test") != "sandbox":
                self._send_json(400, {"error": "Invalid Stripe signature"})
                return

            try:
                event = json.loads(raw_body.decode("utf-8"))
                ev_type = event.get("type")

                # Handle successful payment intent
                if ev_type in ("payment_intent.succeeded", "checkout.session.completed"):
                    obj = event["data"]["object"]
                    clearing_ref = obj.get("id")
                    amount_cents = int(obj.get("amount") or obj.get("amount_total") or 0)

                    result = credit_escrow_reserve(
                        clearing_ref=clearing_ref,
                        source_rail="STRIPE",
                        amount_cents=amount_cents,
                        raw_payload=raw_body.decode("utf-8")
                    )
                    self._send_json(200 if result["status"] == "SUCCESS" else 409, result)
                    return
                else:
                    self._send_json(200, {"status": "IGNORED", "message": f"Unhandled event type {ev_type}"})
                    return
            except Exception as e:
                self._send_json(500, {"error": str(e)})
                return

        # -------------------------------------------------------------
        # Route 2: On-Chain RPC Settlement Listener
        # -------------------------------------------------------------
        elif self.path == "/webhook/crypto":
            try:
                payload = json.loads(raw_body.decode("utf-8"))
                tx_hash = payload.get("tx_hash", "").strip()
                amount_cents = int(payload.get("amount_cents", 0))

                if not tx_hash or amount_cents <= 0:
                    self._send_json(400, {"error": "tx_hash and positive amount_cents required."})
                    return

                # If test mode is enabled, accept mock hashes; otherwise query RPC
                if payload.get("sandbox") is True:
                    verification = {"valid": True, "block_number": "mock_block_0x1"}
                else:
                    verification = verify_evm_transaction(tx_hash)

                if not verification["valid"]:
                    self._send_json(422, {"error": "On-chain verification failed", "details": verification})
                    return

                result = credit_escrow_reserve(
                    clearing_ref=tx_hash,
                    source_rail="EVM_ONCHAIN",
                    amount_cents=amount_cents,
                    raw_payload=raw_body.decode("utf-8")
                )
                self._send_json(200 if result["status"] == "SUCCESS" else 409, result)
                return
            except Exception as e:
                self._send_json(500, {"error": str(e)})
                return

        else:
            self._send_json(404, {"error": "Endpoint not found"})


def run_server(port=8085):
    init_bridge_tables()
    server = HTTPServer(("0.0.0.0", port), TinkaBridgeHandler)
    print("=" * 65)
    print(f"  TINKA AUTHORITATIVE CLEARING BRIDGE ACTIVE ON PORT {port}")
    print(f"  Target DB:              {DB_PATH}")
    print(f"  Stripe Endpoint:        POST /webhook/stripe")
    print(f"  Crypto RPC Endpoint:    POST /webhook/crypto")
    print("=" * 65)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Daemon stopped.")

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8085
    run_server(port)
