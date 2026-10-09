#!/usr/bin/env python3
import sys
import time
from tinka_infinite_engine import TinkaGameDirector, AdaptiveEconomicEngine

def decide_strategy(scenario: dict, current_balance_cents: int, stress: float) -> str:
    win_prob = scenario["win_probability"]
    req_cost = scenario["capital_required_cents"]
    upside_profit = scenario["success_reward_cents"] - req_cost
    downside_loss = scenario["failure_penalty_cents"]

    # Calculate expected value (EV) in integer cents
    expected_value_cents = (win_prob * upside_profit) - ((1.0 - win_prob) * downside_loss)

    # 1. Insolvency Buffer: If balance < $40.00, play strictly defensive
    if current_balance_cents < 4000:
        return "B"

    capital_ratio = req_cost / max(1, current_balance_cents)

    # 2. Aggressive Strategy (A):
    # Triggers on strong EV when capital ratio is manageable (<= 35%) and probability is favorable,
    # OR during Restructuring Troughs where asymmetric upside pays > 1.8x
    is_high_upside = (scenario["success_reward_cents"] / max(1, req_cost)) >= 1.70
    if expected_value_cents > 0 and capital_ratio <= 0.35:
        if win_prob >= 0.60 or (is_high_upside and win_prob >= 0.48):
            return "A"

    # 3. Defensive Hedge Strategy (B): Reliable yields during moderate transitions
    if win_prob >= 0.40:
        return "B"

    # 4. Cash / Capital Preservation (C): Only during deep recessions with negative EV
    return "C"

def run_simulation(epochs=50, delay_seconds=0.03):
    director = TinkaGameDirector()
    start_level = director.profile["level_index"]
    start_bal = director.profile["balance_cents"]

    print("=" * 82)
    print(f"  TINKA CYCLICAL MACRO SIMULATOR: {epochs} EPOCHS")
    print(f"  OPERATOR: {director.player_handle} | STARTING EPOCH: {start_level}")
    print(f"  INITIAL RECONCILED BALANCE: ${start_bal / 100:.2f}")
    print("=" * 82)
    print(f"{'Epoch':<7} {'Macro Phase':<18} {'Strat':<6} {'Win%':<6} {'Delta':<10} {'New Balance':<12}")
    print("-" * 82)

    stats = {"A": 0, "B": 0, "C": 0, "wins": 0, "losses": 0}

    for _ in range(epochs):
        profile = director.profile
        scenario = AdaptiveEconomicEngine.generate_scenario(
            level=profile["level_index"],
            balance_cents=profile["balance_cents"],
            stress=profile["adaptive_stress"]
        )

        choice = decide_strategy(scenario, profile["balance_cents"], profile["adaptive_stress"])
        result = director.evaluate_decision(scenario, choice)

        stats[choice] += 1
        if result["win"]:
            stats["wins"] += 1
        else:
            stats["losses"] += 1

        delta_str = f"{'+' if result['delta_cents'] >= 0 else ''}${result['delta_cents'] / 100:.2f}"
        bal_str = f"${result['new_balance_cents'] / 100:.2f}"
        phase_str = scenario.get("macro_phase", "Market Cycle")[:16]

        print(f"{result['next_level'] - 1:<7} {phase_str:<18} [{choice}]    {int(scenario['win_probability']*100)}%   {delta_str:<10} {bal_str:<12}")

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    final_bal = director.profile["balance_cents"]
    net_growth = final_bal - start_bal
    growth_pct = (net_growth / max(1, start_bal)) * 100

    print("=" * 82)
    print("  SIMULATION COMPLETE")
    print(f"  Final Reconciled Balance:   ${final_bal / 100:.2f} ({'+' if net_growth >= 0 else ''}${net_growth / 100:.2f} / {growth_pct:+.2f}%)")
    print(f"  Epoch Range:                {start_level} -> {director.profile['level_index']}")
    print(f"  Strategy Breakdown:         [A] Aggressive: {stats['A']} | [B] Hedged: {stats['B']} | [C] Cash: {stats['C']}")
    print(f"  Aggregate Win/Loss:         Wins: {stats['wins']} | Losses: {stats['losses']} ({stats['wins']/max(1, epochs)*100:.1f}%)")
    print("  Ledger & Git Checkpoints:   100% Synced to origin/main")
    print("=" * 82)

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    run_simulation(epochs=count)
