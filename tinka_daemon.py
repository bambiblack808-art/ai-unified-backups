#!/usr/bin/env python3
"""
TINKA AUTONOMOUS CRON DAEMON
Executes continuous telemetry collection, resolution verification,
and scheduled settlement batching in a background loop.
"""

import time
import subprocess
import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

def run_step(cmd, desc):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")
    print(f"[{now}] [DAEMON] Starting {desc}...")
    try:
        res = subprocess.run(
            ["python3", str(ROOT_DIR / cmd)],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=120
        )
        if res.returncode == 0:
            print(f"[{now}] [DAEMON] [✓] {desc} completed successfully.")
        else:
            print(f"[{now}] [DAEMON] [-] {desc} warning: {res.stderr.strip() or res.stdout.strip()}")
    except Exception as e:
        print(f"[{now}] [DAEMON] [!] {desc} error: {e}")

def main():
    print("=" * 65)
    print("  TINKA AUTONOMOUS ECONOMIC DAEMON ACTIVE")
    print("  Interval: 60s | Telemetry -> Verification -> Accounting")
    print("=" * 65)

    cycle = 0
    while True:
        cycle += 1
        print(f"\n--- [CYCLE #{cycle}] ---")
        
        # 1. Harvest telemetry
        run_step("tinka_telemetry_collector.py", "Telemetry Ingestion")
        
        # 2. Resolve open quests & record double-entry journal entries
        run_step("tinka_quest_worker.py", "Quest Verification Worker")

        # 3. Check liability threshold and auto-disburse via NPP/Osko
        try:
            import sqlite3
            conn = sqlite3.connect(str(ROOT_DIR / "tinka_verifiable.db"))
            cur = conn.cursor()
            cur.execute("SELECT balance_cents FROM financial_accounts WHERE account_id = 'REWARD_PAYABLE';")
            row = cur.fetchone()
            payable_cents = row[0] if row else 0
            conn.close()

            if payable_cents >= 1000:
                now_tag = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
                auto_ref = f"OSKO{now_tag}AUTO99"
                print(f"[{datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%S')}] [DAEMON] Liability threshold reached (${payable_cents/100:.2f}). Triggering auto-settlement: {auto_ref}")
                subprocess.run(["python3", str(ROOT_DIR / "tinka_osko_clearing.py"), auto_ref], cwd=str(ROOT_DIR), check=True)
        except Exception as e:
            print(f"[DAEMON] Auto-settlement warning: {e}")
        
        # Wait 60 seconds before next scan
        time.sleep(60)

if __name__ == "__main__":
    main()
