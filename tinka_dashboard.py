#!/usr/bin/env python3
import json
import sqlite3
import sys
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

ROOT_DIR = Path(__file__).resolve().parent
VERIFIABLE_DB = ROOT_DIR / "tinka_verifiable.db"
SIMULATED_DB = ROOT_DIR / "tinka_ledger.db"

HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Tinka Dual-Ledger Mission Control</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { background: #0b0f19; color: #f8fafc; font-family: system-ui, sans-serif; margin: 0; padding: 24px; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 16px; margin-bottom: 24px; }
    .badge { background: #064e3b; color: #34d399; padding: 4px 12px; border-radius: 999px; font-weight: 600; font-size: 0.8rem; border: 1px solid #059669; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .card { background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 16px; }
    .card.escrow { border-color: #059669; background: #06241b; }
    .title { font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; margin-bottom: 8px; }
    .val { font-size: 1.75rem; font-weight: 700; color: #f8fafc; }
    .sub { font-size: 0.8rem; color: #34d399; margin-top: 4px; }
    .chart-box { background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 16px; margin-bottom: 24px; height: 320px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; background: #111827; border-radius: 8px; border: 1px solid #1f2937; margin-top: 12px; }
    th, td { padding: 10px 14px; text-align: left; }
    th { background: #1e293b; color: #94a3b8; }
    tr:not(:last-child) td { border-bottom: 1px solid #1f2937; }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1 style="margin: 0; font-size: 1.4rem;">Tinka Autonomous Economic Engine</h1>
      <small style="color: #64748b;">Project: venture-engine-1411e | Dual-Ledger Architecture</small>
    </div>
    <div class="badge">VERIFIED CAPITAL ESCROW</div>
  </div>

  <div class="grid">
    <div class="card escrow">
      <div class="title">Liquid Escrow Reserve</div>
      <div class="val" id="escrow">$0.00</div>
      <div class="sub" id="inflow">+$0.00 External Inflow</div>
    </div>
    <div class="card">
      <div class="title">Reward Liability Payable</div>
      <div class="val" id="payable">$0.00</div>
      <div class="sub" style="color:#38bdf8;">Backed by Real Escrow</div>
    </div>
    <div class="card">
      <div class="title">Simulated Macro Equity</div>
      <div class="val" id="sim-bal">$0.00</div>
      <div class="sub" style="color:#94a3b8;" id="epoch">Epoch 0</div>
    </div>
    <div class="card">
      <div class="title">Verified Quests & XP</div>
      <div class="val" id="xp">0 XP</div>
      <div class="sub" id="quests">0 Completed</div>
    </div>
  </div>

  <div class="chart-box">
    <canvas id="chart"></canvas>
  </div>

  <h3 style="color:#38bdf8; margin: 0;">Simulated Macroeconomic Transactions</h3>
  <table>
    <thead><tr><th>ID</th><th>Type</th><th>Amount</th><th>Balance After</th><th>Audit Hash</th></tr></thead>
    <tbody id="tx-rows"></tbody>
  </table>

  <script>
    async function init() {
      const res = await fetch("/api/state");
      const data = await res.json();
      
      document.getElementById("escrow").innerText = "$" + (data.verifiable.escrow_cents / 100).toFixed(2);
      document.getElementById("inflow").innerText = "+$" + (data.verifiable.cleared_inflow_cents / 100).toFixed(2) + " External Inflow";
      document.getElementById("payable").innerText = "$" + (data.verifiable.payable_cents / 100).toFixed(2);
      document.getElementById("sim-bal").innerText = "$" + (data.simulated.profile.balance_cents / 100).toFixed(2);
      document.getElementById("epoch").innerText = "Epoch " + data.simulated.profile.level_index + " (Stress: " + data.simulated.profile.adaptive_stress.toFixed(2) + ")";
      document.getElementById("xp").innerText = data.verifiable.gameplay.xp + " XP";
      document.getElementById("quests").innerText = data.verifiable.gameplay.verified_quests + " Verified Quests";

      const tbody = document.getElementById("tx-rows");
      tbody.innerHTML = "";
      data.simulated.recent_tx.forEach(tx => {
        const pos = tx.amount_cents >= 0;
        tbody.innerHTML += `<tr>
          <td>#${tx.id}</td>
          <td>${tx.tx_type}</td>
          <td style="color:${pos ? '#34d399' : '#f87171'}">${pos ? '+' : ''}$${(tx.amount_cents / 100).toFixed(2)}</td>
          <td>$${(tx.balance_after_cents / 100).toFixed(2)}</td>
          <td style="font-family: monospace; color: #94a3b8;">${tx.tx_hash.substring(0, 10)}...</td>
        </tr>`;
      });

      new Chart(document.getElementById("chart"), {
        type: "line",
        data: {
          labels: data.simulated.chart.map(p => "E" + p.id),
          datasets: [{
            label: "Macro Cycle Equity ($)",
            data: data.simulated.chart.map(p => p.balance_after_cents / 100),
            borderColor: "#38bdf8",
            backgroundColor: "rgba(56, 189, 248, 0.1)",
            fill: true,
            tension: 0.2
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: { grid: { color: "#1f2937" } },
            y: { grid: { color: "#1f2937" }, ticks: { callback: v => "$" + v } }
          }
        }
      });
    }
    init();
  </script>
</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/state":
            verifiable = {
                "escrow_cents": 0, "payable_cents": 0, "cleared_inflow_cents": 0,
                "gameplay": {"xp": 0, "level": 1, "verified_quests": 0}
            }
            if VERIFIABLE_DB.exists():
                c = sqlite3.connect(str(VERIFIABLE_DB))
                cur = c.cursor()
                cur.execute("SELECT account_id, balance_cents FROM financial_accounts;")
                accs = dict(cur.fetchall())
                verifiable["escrow_cents"] = accs.get("ESCROW_RESERVE", 0)
                verifiable["payable_cents"] = accs.get("REWARD_PAYABLE", 0)

                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='external_deposits';")
                if cur.fetchone():
                    cur.execute("SELECT IFNULL(SUM(amount_cents), 0) FROM external_deposits;")
                    verifiable["cleared_inflow_cents"] = cur.fetchone()[0]

                cur.execute("SELECT xp, level, verified_quests_completed FROM player_gameplay WHERE player_id = 'bambiblack808-art';")
                gp = cur.fetchone() or (0, 1, 0)
                verifiable["gameplay"] = {"xp": gp[0], "level": gp[1], "verified_quests": gp[2]}
                c.close()

            simulated = {
                "profile": {"balance_cents": 0, "level_index": 0, "adaptive_stress": 1.0, "success_rate": 0.5},
                "recent_tx": [],
                "chart": []
            }
            if SIMULATED_DB.exists():
                c = sqlite3.connect(str(SIMULATED_DB))
                cur = c.cursor()
                cur.execute("SELECT balance_cents, level_index, adaptive_stress, success_rate FROM player_profile WHERE user_handle = 'bambiblack808-art';")
                r = cur.fetchone() or (0, 0, 1.0, 0.5)
                simulated["profile"] = {"balance_cents": r[0], "level_index": r[1], "adaptive_stress": r[2], "success_rate": r[3]}

                cur.execute("SELECT id, timestamp, amount_cents, balance_after_cents, tx_type, tx_hash FROM transactions ORDER BY id DESC LIMIT 8;")
                simulated["recent_tx"] = [
                    {"id": x[0], "timestamp": x[1], "amount_cents": x[2], "balance_after_cents": x[3], "tx_type": x[4], "tx_hash": x[5]}
                    for x in cur.fetchall()
                ]

                cur.execute("SELECT id, balance_after_cents FROM transactions ORDER BY id ASC;")
                simulated["chart"] = [{"id": x[0], "balance_after_cents": x[1]} for x in cur.fetchall()]
                c.close()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"verifiable": verifiable, "simulated": simulated}).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML.encode())

def run(port=8080):
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"[✓] Mission Control serving on http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run(p)
