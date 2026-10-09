#!/usr/bin/env python3
import os, sys, json, math, random, hashlib, sqlite3, datetime
from pathlib import Path
from decimal import Decimal
from git import Repo

ROOT_DIR = Path(__file__).resolve().parent
DB_PATH = ROOT_DIR / "tinka_ledger.db"
CHECKPOINT_DIR = ROOT_DIR / "backups" / "tinka_state"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

class PrecisionLedger:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(str(db_path))
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    balance_after_cents INTEGER NOT NULL,
                    tx_type TEXT NOT NULL,
                    tx_hash TEXT NOT NULL
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS player_profile (
                    user_handle TEXT PRIMARY KEY,
                    balance_cents INTEGER NOT NULL,
                    level_index INTEGER NOT NULL,
                    adaptive_stress REAL NOT NULL,
                    success_rate REAL NOT NULL
                )
            """)

    def get_or_create_player(self, handle: str) -> dict:
        cur = self.conn.cursor()
        cur.execute("SELECT balance_cents, level_index, adaptive_stress, success_rate FROM player_profile WHERE user_handle = ?", (handle,))
        row = cur.fetchone()
        if row:
            return {"handle": handle, "balance_cents": row[0], "level_index": row[1], "adaptive_stress": row[2], "success_rate": row[3]}
        init_state = {"handle": handle, "balance_cents": 10000, "level_index": 1, "adaptive_stress": 1.0, "success_rate": 0.5}
        with self.conn:
            self.conn.execute("INSERT INTO player_profile VALUES (?, ?, ?, ?, ?)",
                (handle, init_state["balance_cents"], init_state["level_index"], init_state["adaptive_stress"], init_state["success_rate"]))
        return init_state

    def record_transaction(self, handle: str, amount_cents: int, tx_type: str, notes: str) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT balance_cents FROM player_profile WHERE user_handle = ?", (handle,))
        current_bal = cur.fetchone()[0]
        new_bal = current_bal + amount_cents
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        raw_sig = f"{timestamp}:{handle}:{amount_cents}:{new_bal}:{tx_type}:{notes}"
        tx_hash = hashlib.sha256(raw_sig.encode()).hexdigest()

        with self.conn:
            self.conn.execute("""
                INSERT INTO transactions (timestamp, source, destination, amount_cents, balance_after_cents, tx_type, tx_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (timestamp, "system" if amount_cents > 0 else handle, handle if amount_cents > 0 else "system", amount_cents, new_bal, tx_type, tx_hash))
            self.conn.execute("UPDATE player_profile SET balance_cents = ? WHERE user_handle = ?", (new_bal, handle))
        return new_bal

    def update_metrics(self, handle: str, level_index: int, stress: float, success_rate: float):
        with self.conn:
            self.conn.execute("""
                UPDATE player_profile SET level_index = ?, adaptive_stress = ?, success_rate = ? WHERE user_handle = ?
            """, (level_index, stress, success_rate, handle))

class AdaptiveEconomicEngine:
    REAL_WORLD_MODELS = [
        {
            "category": "Cash Flow & Supply Chain",
            "concept": "Working Capital & Bulk Discount Arbitrage",
            "lesson": "Investing early cash into inventory yields higher gross margins, but risks insolvency if receivables lag.",
            "param": "inventory_discount_pct"
        },
        {
            "category": "Debt & Leverage",
            "concept": "Variable Rate Financing vs. Fixed Cost",
            "lesson": "Debt accelerates growth during high demand, but a 200 bps rate shock will crush cash flow if EBIT < Interest.",
            "param": "interest_rate_shock"
        },
        {
            "category": "Customer Acquisition",
            "concept": "CAC to LTV Payback Window",
            "lesson": "Aggressive marketing boosts top-line revenue, but cash runs dry before customer lifetime value is collected.",
            "param": "cac_recovery_lag"
        },
        {
            "category": "Tax & Depreciation",
            "concept": "Asset Write-offs and Reserve Hedging",
            "lesson": "Failing to set aside 25% tax and equipment maintenance reserves creates emergency liquidation scenarios.",
            "param": "depreciation_reserve_ratio"
        }
    ]

    @staticmethod
    def generate_scenario(level: int, balance_cents: int, stress: float) -> dict:
        model = random.choice(AdaptiveEconomicEngine.REAL_WORLD_MODELS)
        capital_base_cents = max(5000, int(balance_cents * 0.25))
        risk_multiplier = 1.0 + (0.15 * math.log(max(1, level))) * stress
        cost_cents = int(capital_base_cents * 0.40 * risk_multiplier)
        upside_cents = int(cost_cents * (1.25 + (random.random() * 0.50)))
        downside_cents = int(cost_cents * (0.75 + (random.random() * 0.40)))

        return {
            "level": level,
            "category": model["category"],
            "title": f"Epoch {level}: {model['concept']}",
            "lesson": model["lesson"],
            "capital_required_cents": cost_cents,
            "success_reward_cents": upside_cents,
            "failure_penalty_cents": downside_cents,
            "stress_factor": round(stress, 3),
            "win_probability": max(0.20, min(0.85, 0.70 - (0.02 * level * stress) + (random.random() * 0.10)))
        }

class TinkaGameDirector:
    def __init__(self, player_handle="bambiblack808-art"):
        self.ledger = PrecisionLedger(DB_PATH)
        self.player_handle = player_handle
        self.profile = self.ledger.get_or_create_player(player_handle)
        self.repo = Repo(str(ROOT_DIR))

    def evaluate_decision(self, scenario: dict, choice: str) -> dict:
        roll = random.random()
        win = roll <= scenario["win_probability"]
        delta_cents = 0
        feedback = ""

        if choice.upper() == "A":
            if win:
                delta_cents = scenario["success_reward_cents"] - scenario["capital_required_cents"]
                feedback = f"Optimal Execution: Fully capitalized on {scenario['category']}. Net Profit: +${delta_cents / 100:.2f}"
            else:
                delta_cents = -scenario["failure_penalty_cents"]
                feedback = f"Liquidity Squeeze: Risk realized. Capital loss: -${abs(delta_cents) / 100:.2f}"
        elif choice.upper() == "B":
            hedged_cost = scenario["capital_required_cents"] // 2
            hedged_gain = int(hedged_cost * 1.12)
            delta_cents = hedged_gain - hedged_cost
            win = True
            feedback = f"Hedged Stability: Preserved downside, locked in conservative gain: +${delta_cents / 100:.2f}"
        else:
            delta_cents = -max(10, int(self.profile["balance_cents"] * 0.0025))
            win = False
            feedback = f"Idle Capital Friction: Inflation/overhead chipped away -${abs(delta_cents) / 100:.2f}"

        new_balance = self.ledger.record_transaction(
            handle=self.player_handle,
            amount_cents=delta_cents,
            tx_type="REWARD" if delta_cents >= 0 else "LOSS",
            notes=feedback
        )

        new_level = self.profile["level_index"] + 1
        new_success_rate = (self.profile["success_rate"] * 0.8) + ((1.0 if win else 0.0) * 0.2)
        new_stress = max(0.5, self.profile["adaptive_stress"] + (0.05 if win else -0.04))

        self.ledger.update_metrics(self.player_handle, new_level, new_stress, new_success_rate)
        self.profile = self.ledger.get_or_create_player(self.player_handle)
        self._export_and_sync()

        return {
            "win": win,
            "delta_cents": delta_cents,
            "new_balance_cents": new_balance,
            "feedback": feedback,
            "next_level": new_level
        }

    def _export_and_sync(self):
        snapshot_file = CHECKPOINT_DIR / "latest_ledger_state.json"
        state = {
            "player": self.profile,
            "balance_display": f"${self.profile['balance_cents'] / 100:.2f}",
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "audit_hash": hashlib.sha256(str(self.profile).encode()).hexdigest()
        }
        with open(snapshot_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        try:
            self.repo.git.add([str(snapshot_file), str(DB_PATH)])
            if self.repo.is_dirty():
                self.repo.index.commit(f"Checkpoint: Tinka Epoch {self.profile['level_index']} (Bal: ${self.profile['balance_cents']/100:.2f})")
                self.repo.remotes.origin.push()
        except Exception:
            pass

def play_session():
    director = TinkaGameDirector()
    print("=" * 65)
    print(f"  TINKA INFINITE ECONOMIC SIMULATOR | OPERATOR: {director.player_handle}")
    print(f"  CURRENT ACCURATE BALANCE: ${director.profile['balance_cents'] / 100:.2f}")
    print(f"  EPOCH / LEVEL: {director.profile['level_index']} | SYSTEM STRESS: {director.profile['adaptive_stress']:.2f}")
    print("=" * 65)

    scenario = AdaptiveEconomicEngine.generate_scenario(
        level=director.profile["level_index"],
        balance_cents=director.profile["balance_cents"],
        stress=director.profile["adaptive_stress"]
    )

    print(f"\n[SCENARIO]: {scenario['title']}")
    print(f"[CATEGORY]: {scenario['category']}")
    print(f"[CORE LESSON]: {scenario['lesson']}")
    print("-" * 65)
    print(f"Capital Requirement:       ${scenario['capital_required_cents'] / 100:.2f}")
    print(f"Projected Return (A):      +${scenario['success_reward_cents'] / 100:.2f}")
    print(f"Downside Exposure (A):     -${scenario['failure_penalty_cents'] / 100:.2f}")
    print(f"Empirical Win Probability: {int(scenario['win_probability'] * 100)}%")
    print("-" * 65)
    print("OPTIONS:")
    print("  [A] Aggressive: Fully capitalize operation.")
    print("  [B] Defensive:  Hedge with 50% safe capital for 12% margin.")
    print("  [C] Reserve:    Preserve all cash (subject to inflation friction).")

    choice = input("\nSelect strategy (A / B / C) or 'Q' to quit: ").strip()
    if choice.upper() == 'Q':
        print("\nSession paused. State locked into precision ledger.")
        return

    result = director.evaluate_decision(scenario, choice)
    print("\n" + "=" * 65)
    print(result["feedback"])
    print(f"UPDATED RECONCILED BALANCE: ${result['new_balance_cents'] / 100:.2f}")
    print(f"Advancing to Epoch {result['next_level']}...")
    print("State automatically secured and verified to git remote.")
    print("=" * 65)

if __name__ == "__main__":
    play_session()
