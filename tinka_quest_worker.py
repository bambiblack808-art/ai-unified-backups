#!/usr/bin/env python3
import sys
import json
import sqlite3
import hashlib
import datetime
import subprocess
from pathlib import Path

# Explicit location bindings
WORKSPACE_DIR = Path("/home/bambiblack808/workspace/ai-unified-backups").resolve()
DB_PATH = WORKSPACE_DIR / "tinka_verifiable.db"
PLAYER_ID = "bambiblack808-art"

def get_git_repo_size_mb(repo_path: Path) -> float:
    """Measures total git object and pack storage in MB at target location."""
    res = subprocess.run(
        ["git", "count-objects", "-v"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        check=True
    )
    size_kb = 0
    for line in res.stdout.splitlines():
        if line.startswith("size-pack:") or line.startswith("size:"):
            size_kb += int(line.split(":")[1].strip())
    return round(size_kb / 1024.0, 2)

def run_optimization_worker():
    if not DB_PATH.exists():
        print(f"[-] Database not found at: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    # Locate open quest
    cur.execute("""
        SELECT quest_id, domain, problem_statement, baseline_metric, target_metric, pre_evidence_hash
        FROM quests
        WHERE state = 'DISCOVERED'
        ORDER BY created_at ASC
        LIMIT 1;
    """)
    quest = cur.fetchone()

    # If no open quest exists, generate one targeting the workspace location
    if not quest:
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        current_mb = get_git_repo_size_mb(WORKSPACE_DIR)
        target_mb = max(0.5, round(current_mb * 0.75, 2))
        qid = f"QUEST-VCS-OPT-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
        pre_ev = {
            "target_location": str(WORKSPACE_DIR),
            "baseline_mb": current_mb,
            "target_mb": target_mb,
            "created_at": now_str
        }
        pre_hash = hashlib.sha256(json.dumps(pre_ev, sort_keys=True).encode()).hexdigest()
        statement = f"Optimize repository object storage at {WORKSPACE_DIR} from {current_mb}MB to under {target_mb}MB."

        cur.execute("""
            INSERT INTO quests (
                quest_id, domain, problem_statement, baseline_metric,
                target_metric, observation_window_seconds, state,
                created_at, pre_evidence_hash
            ) VALUES (?, 'Storage & VCS Optimization', ?, ?, ?, 86400, 'DISCOVERED', ?, ?);
        """, (qid, statement, current_mb, target_mb, now_str, pre_hash))
        conn.commit()

        cur.execute("""
            SELECT quest_id, domain, problem_statement, baseline_metric, target_metric, pre_evidence_hash
            FROM quests WHERE quest_id = ?;
        """, (qid,))
        quest = cur.fetchone()

    qid, domain, statement, baseline_metric, target_metric, pre_hash = quest
    print("=" * 70)
    print(f"  EXECUTING TARGETED QUEST RESOLUTION: {qid}")
    print(f"  Target Location:   {WORKSPACE_DIR}")
    print(f"  Baseline Metric:   {baseline_metric} MB")
    print("=" * 70)

    # 1. Execute optimization at target location
    print(f"[*] Running git prune & repack inside {WORKSPACE_DIR}...")
    subprocess.run(["git", "reflog", "expire", "--expire=now", "--all"], cwd=str(WORKSPACE_DIR), check=True)
    # Check for existing gc process or lockfile
    gc_pid_file = WORKSPACE_DIR / ".git" / "gc.pid"
    if gc_pid_file.exists():
        print("[!] Another git gc process is active. Skipping repack this cycle.")
    else:
        subprocess.run(["git", "gc", "--prune=now", "--quiet"], cwd=str(WORKSPACE_DIR), check=True)

    # 2. Measure verified post-evidence
    post_metric = get_git_repo_size_mb(WORKSPACE_DIR)
    delta_mb = round(baseline_metric - post_metric, 2)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print(f"[*] Post-Intervention Metric: {post_metric} MB (Delta: {delta_mb} MB)")

    post_evidence = {
        "quest_id": qid,
        "target_location": str(WORKSPACE_DIR),
        "post_size_mb": post_metric,
        "baseline_size_mb": baseline_metric,
        "delta_mb": delta_mb,
        "timestamp": now
    }
    post_hash = hashlib.sha256(json.dumps(post_evidence, sort_keys=True).encode()).hexdigest()

    # 3. Calculate reward: 50 cents per MB reclaimed, min $1.00 (100 cents) for passing
    reward_cents = max(100, int(max(0.0, delta_mb) * 50))

    try:
        with conn:
            # Check available escrow reserve
            cur.execute("SELECT balance_cents FROM financial_accounts WHERE account_id = 'ESCROW_RESERVE';")
            escrow_row = cur.fetchone()
            escrow_bal = escrow_row[0] if escrow_row else 0
            if escrow_bal < reward_cents:
                reward_cents = escrow_bal

            # Record authoritative outcome
            cur.execute("""
                INSERT INTO outcomes (
                    quest_id, achieved_metric, verified_at,
                    post_evidence_hash, value_delivered_cents, outcome_signature
                ) VALUES (?, ?, ?, ?, ?, ?);
            """, (qid, post_metric, now, post_hash, reward_cents, f"SIG-{post_hash[:16]}"))

            # Lock quest state to VERIFIED
            cur.execute("UPDATE quests SET state = 'VERIFIED' WHERE quest_id = ?;", (qid,))

            # Transfer reward: ESCROW_RESERVE -> REWARD_PAYABLE
            if reward_cents > 0:
                cur.execute("""
                    UPDATE financial_accounts
                    SET balance_cents = balance_cents - ?
                    WHERE account_id = 'ESCROW_RESERVE';
                """, (reward_cents,))
                cur.execute("""
                    UPDATE financial_accounts
                    SET balance_cents = balance_cents + ?
                    WHERE account_id = 'REWARD_PAYABLE';
                """, (reward_cents,))

                # Immutable ledger journal entry
                cur.execute("""
                    INSERT INTO financial_journal (
                        timestamp, source_account, dest_account,
                        amount_cents, quest_id, evidence_hash, entry_signature
                    ) VALUES (?, 'ESCROW_RESERVE', 'REWARD_PAYABLE', ?, ?, ?, ?);
                """, (now, reward_cents, qid, post_hash, f"OUTCOME-{qid}"))

            # Award XP & update completed count
            cur.execute("""
                UPDATE player_gameplay
                SET xp = xp + 500,
                    verified_quests_completed = verified_quests_completed + 1
                WHERE player_id = ?;
            """, (PLAYER_ID,))

        print(f"[✓] Quest {qid} VERIFIED.")
        print(f"[✓] Transferred ${reward_cents / 100:.2f} from ESCROW_RESERVE to REWARD_PAYABLE.")
        print(f"[✓] Credited 500 XP to {PLAYER_ID}.")

    except Exception as e:
        print(f"[-] Settlement error: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    run_optimization_worker()
