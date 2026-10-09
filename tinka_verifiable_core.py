#!/usr/bin/env python3
import os, sys, json, sqlite3, hashlib, datetime
from pathlib import Path
from typing import Dict, Any, Tuple

ROOT_DIR = Path(__file__).resolve().parent
CORE_DB_PATH = ROOT_DIR / "tinka_verifiable.db"

class VerifiableCoreDB:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(str(db_path), timeout=30.0)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA foreign_keys=ON;")
        self._init_schema()

    def _init_schema(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS financial_accounts (
                    account_id TEXT PRIMARY KEY,
                    account_type TEXT NOT NULL CHECK(account_type IN ('ESCROW_RESERVE', 'REWARD_PAYABLE', 'SETTLED_CASH', 'OPERATING_EXPENSE')),
                    balance_cents INTEGER NOT NULL CHECK(balance_cents >= 0)
                );
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS financial_journal (
                    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    source_account TEXT NOT NULL REFERENCES financial_accounts(account_id),
                    dest_account TEXT NOT NULL REFERENCES financial_accounts(account_id),
                    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                    quest_id TEXT NOT NULL,
                    evidence_hash TEXT NOT NULL,
                    entry_signature TEXT NOT NULL
                );
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS player_gameplay (
                    player_id TEXT PRIMARY KEY,
                    xp INTEGER NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 1,
                    reputation_score REAL NOT NULL DEFAULT 1.0,
                    verified_quests_completed INTEGER NOT NULL DEFAULT 0
                );
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS quests (
                    quest_id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    problem_statement TEXT NOT NULL,
                    baseline_metric REAL NOT NULL,
                    target_metric REAL NOT NULL,
                    observation_window_seconds INTEGER NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('DISCOVERED', 'SCOPED', 'ACCEPTED', 'EXECUTED', 'VERIFIED', 'SETTLED', 'REJECTED', 'DISPUTED')),
                    created_at TEXT NOT NULL,
                    pre_evidence_hash TEXT NOT NULL,
                    post_evidence_hash TEXT,
                    realized_value_cents INTEGER DEFAULT 0,
                    reward_pool_cents INTEGER DEFAULT 0
                );
            """)
            for acc_id, acc_type in [('ESCROW_RESERVE', 'ESCROW_RESERVE'), ('REWARD_PAYABLE', 'REWARD_PAYABLE'), ('SETTLED_CASH', 'SETTLED_CASH'), ('OPERATING_EXPENSE', 'OPERATING_EXPENSE')]:
                self.conn.execute("INSERT OR IGNORE INTO financial_accounts VALUES (?, ?, 0);", (acc_id, acc_type))

class VerificationEngine:
    @staticmethod
    def verify_intervention(baseline_metric: float, observed_metric: float, target_metric: float, is_cost_metric: bool = True) -> Tuple[bool, float]:
        if is_cost_metric:
            improvement = (baseline_metric - observed_metric) / max(0.0001, baseline_metric)
            success = observed_metric <= target_metric and improvement > 0
        else:
            improvement = (observed_metric - baseline_metric) / max(0.0001, baseline_metric)
            success = observed_metric >= target_metric and improvement > 0
        return success, improvement

class QuestLifecycleManager:
    def __init__(self, db: VerifiableCoreDB):
        self.db = db

    def inject_external_escrow(self, amount_cents: int, source_ref: str) -> str:
        if amount_cents <= 0:
            raise ValueError("Escrow injection must be positive.")
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        sig = hashlib.sha256(f"INJECT:{timestamp}:{amount_cents}:{source_ref}".encode()).hexdigest()
        with self.db.conn:
            self.db.conn.execute("UPDATE financial_accounts SET balance_cents = balance_cents + ? WHERE account_id = 'ESCROW_RESERVE';", (amount_cents,))
        return sig

    def create_quest(self, quest_id: str, domain: str, problem: str, baseline_metric: float, target_metric: float, window_seconds: int, pre_evidence: Dict[str, Any]) -> str:
        evidence_hash = hashlib.sha256(json.dumps(pre_evidence, sort_keys=True).encode()).hexdigest()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db.conn:
            self.db.conn.execute("""
                INSERT INTO quests (quest_id, domain, problem_statement, baseline_metric, target_metric, observation_window_seconds, state, created_at, pre_evidence_hash)
                VALUES (?, ?, ?, ?, ?, ?, 'DISCOVERED', ?, ?);
            """, (quest_id, domain, problem, baseline_metric, target_metric, window_seconds, now, evidence_hash))
        return quest_id

    def verify_and_allocate_reward(self, quest_id: str, post_evidence: Dict[str, Any], observed_metric: float, verified_savings_cents: int, revenue_share_pct: float = 0.20) -> Dict[str, Any]:
        cur = self.db.conn.cursor()
        cur.execute("SELECT baseline_metric, target_metric, state FROM quests WHERE quest_id = ?;", (quest_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Quest {quest_id} not found.")
        baseline_metric, target_metric, current_state = row
        
        success, improvement = VerificationEngine.verify_intervention(baseline_metric, observed_metric, target_metric, is_cost_metric=True)
        post_hash = hashlib.sha256(json.dumps(post_evidence, sort_keys=True).encode()).hexdigest()
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if not success:
            with self.db.conn:
                self.db.conn.execute("UPDATE quests SET state = 'REJECTED', post_evidence_hash = ? WHERE quest_id = ?;", (post_hash, quest_id))
            return {"verdict": "REJECTED", "reason": "Target not achieved", "improvement": improvement}

        earned_reward_cents = int(verified_savings_cents * revenue_share_pct)

        with self.db.conn:
            cur.execute("SELECT balance_cents FROM financial_accounts WHERE account_id = 'ESCROW_RESERVE';")
            escrow_available = cur.fetchone()[0]
            if earned_reward_cents > escrow_available:
                raise ValueError(f"INVARIANT VIOLATION: Reward {earned_reward_cents} cents exceeds available Escrow {escrow_available} cents.")

            sig = hashlib.sha256(f"TX:{timestamp}:{quest_id}:{earned_reward_cents}:{post_hash}".encode()).hexdigest()
            self.db.conn.execute("UPDATE financial_accounts SET balance_cents = balance_cents - ? WHERE account_id = 'ESCROW_RESERVE';", (earned_reward_cents,))
            self.db.conn.execute("UPDATE financial_accounts SET balance_cents = balance_cents + ? WHERE account_id = 'REWARD_PAYABLE';", (earned_reward_cents,))
            self.db.conn.execute("""
                INSERT INTO financial_journal (timestamp, source_account, dest_account, amount_cents, quest_id, evidence_hash, entry_signature)
                VALUES (?, 'ESCROW_RESERVE', 'REWARD_PAYABLE', ?, ?, ?, ?);
            """, (timestamp, earned_reward_cents, quest_id, post_hash, sig))

            self.db.conn.execute("""
                UPDATE quests SET state = 'VERIFIED', post_evidence_hash = ?, realized_value_cents = ?, reward_pool_cents = ? WHERE quest_id = ?;
            """, (post_hash, verified_savings_cents, earned_reward_cents, quest_id))

            earned_xp = int(earned_reward_cents / 10)
            self.db.conn.execute("""
                INSERT INTO player_gameplay (player_id, xp, level, verified_quests_completed)
                VALUES ('bambiblack808-art', ?, 1, 1)
                ON CONFLICT(player_id) DO UPDATE SET
                    xp = xp + excluded.xp,
                    verified_quests_completed = verified_quests_completed + 1,
                    level = 1 + ((xp + excluded.xp) / 500);
            """, (earned_xp,))

        return {
            "verdict": "VERIFIED_AND_FUNDED",
            "earned_reward_cents": earned_reward_cents,
            "realized_savings_cents": verified_savings_cents,
            "earned_xp": earned_xp
        }

if __name__ == "__main__":
    db = VerifiableCoreDB(CORE_DB_PATH)
    lifecycle = QuestLifecycleManager(db)
    print("[+] Initializing Verifiable Invariant Test...")
    lifecycle.inject_external_escrow(10000, "Initial Reserve Clearing")
    qid = f"Q-{datetime.datetime.now().strftime('%H%M%S')}"
    lifecycle.create_quest(qid, "Cloud Ops", "Reduce unattached disk waste", 200.0, 50.0, 3600, {"telemetry": "raw"})
    res = lifecycle.verify_and_allocate_reward(qid, {"telemetry": "post_audit"}, 42.0, 15000, 0.20)
    print("[✓] Execution Complete. Result:", res)
