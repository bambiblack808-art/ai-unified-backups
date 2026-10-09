#!/usr/bin/env python3
import os
import sys
import json
import sqlite3
import hashlib
import datetime
import subprocess
from pathlib import Path

PROJECT_ID = "venture-engine-1411e"
DB_PATH = Path(__file__).resolve().parent / "tinka_verifiable.db"

def register_verifiable_quest(quest_id: str, domain: str, statement: str, baseline: float, target: float, window_sec: int, evidence: dict):
    if not DB_PATH.exists():
        return False
    evidence_str = json.dumps(evidence, sort_keys=True)
    h = hashlib.sha256(evidence_str.encode("utf-8")).hexdigest()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    try:
        with conn:
            conn.execute("""
                INSERT OR IGNORE INTO quests (
                    quest_id, domain, problem_statement, baseline_metric,
                    target_metric, observation_window_seconds, state,
                    created_at, pre_evidence_hash
                ) VALUES (?, ?, ?, ?, ?, ?, 'DISCOVERED', ?, ?);
            """, (quest_id, domain, statement, baseline, target, window_sec, now, h))
        print(f"[+] Registered verifiable quest: {quest_id}")
        return True
    finally:
        conn.close()

def scan_local_storage_waste():
    """Scans local Cloud Shell workspace for dead blobs and disk waste."""
    print("\n[Scanning Local Infrastructure: Disk Bloat & Large Files]...")
    home = Path.home()
    workspace = home / "workspace"
    
    # 1. Check Git packfile / dangling blob bloat in repository
    try:
        res = subprocess.run(["git", "count-objects", "-v"], cwd=str(workspace / "ai-unified-backups"), capture_output=True, text=True)
        size_kb = 0
        for line in res.stdout.splitlines():
            if line.startswith("size-pack:"):
                size_kb += int(line.split(":")[1].strip())
            elif line.startswith("size:"):
                size_kb += int(line.split(":")[1].strip())
        
        size_mb = size_kb / 1024.0
        if size_mb > 10.0:  # If git repo bloat > 10MB
            qid = f"QUEST-LOCAL-GIT-BLOAT-{datetime.datetime.now().strftime('%Y%m%d')}"
            evidence = {
                "source": "local_git_telemetry",
                "repo": "ai-unified-backups",
                "pack_size_mb": round(size_mb, 2),
                "threshold_mb": 10.0
            }
            statement = f"Repository ai-unified-backups has accumulated {size_mb:.2f}MB of git packfile/loose object bloat. Optimization via git gc / repack needed."
            register_verifiable_quest(qid, "Storage & VCS Optimization", statement, size_mb, 5.0, 86400, evidence)
    except Exception as e:
        print(f"[-] Local scan warning: {e}")

def main():
    print("=" * 65)
    print("  TINKA TELEMETRY HARVESTER: GCP + ENVIRONMENT WASTE")
    print("=" * 65)
    scan_local_storage_waste()
    print("=" * 65)

if __name__ == "__main__":
    main()
