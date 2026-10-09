#!/usr/bin/env python3
import json
import sqlite3
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

ROOT_DIR = Path(__file__).resolve().parent
VERIFIABLE_DB = ROOT_DIR / "tinka_verifiable.db"
SIMULATED_DB = ROOT_DIR / "tinka_ledger.db"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Tinka Infinite Engine - Verified Economic Mission Control</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { background-color: #0b0f19; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 24px; }
    .container { max-width: 1280px; margin: 0 auto; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 16px; margin-bottom: 24px; }
    .badges { display: flex; gap: 8px; }
    .badge-verified { background: #064e3b; color: #34d399; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 0.8rem; border: 1px solid #059669; }
    .badge-sim { background: #1e293b; color: #38bdf8; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 0.8rem; border: 1px solid #334155; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .card { background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 16px; }
    .card.highlight { border-color: #059669; background: #06241b; }
    .card-title { font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.05em; margin-bottom: 8px; }
    .card-value { font-size: 1.75rem; font-weight: 700; color: #f8fafc; }
    .card-sub { font-size: 0.8rem; color: #10b981; margin-top: 4px; font-weight: 500; }
    .dual-tables { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 24px; }
    @media (max-width: 900px) { .dual-tables { grid-template-columns: 1fr; } }
    .chart-container { background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 20px; margin-bottom: 24px; height: 320px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.825rem; background: #111827; border-radius: 8px; overflow: hidden; border: 1px solid #1f2937; }
    th, td { padding: 10px 14px; text-align: left; }
    th { background: #1e293b; color: #94a3b8; font-weight: 600; }
    tr:not(:last-child) td { border-bottom: 1px solid #1f2937; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #94a3b8; }
    .profit { color: #34d399; font-weight: 600; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <h1 style="margin: 0; font-size: 1.5rem;">Tinka Autonomous Economic Engine</h1>
        <small style="color: #64748b;">Project: venture-engine-1411e | Operator: bambiblack808-art</small>
      </div>
      <div class="badges">
        <div class="badge-verified">REAL ASSET VERIFIED (SQLITE WAL)</div>
        <div class="badge-sim">155 MACRO EPOCHS ACTIVE</div>
      </div>
    </div>

    <!-- Top Key Metrics Cards -->
    <div class="grid">
      <div class="card highlight">
        <div class="card-title">Verified Liquid Escrow</div>
        <div class="card-value" id="val-escrow">$0.00</div>
        <div class="card-sub" id="val-inflow">+$0.00 external inflows cleared</div>
      </div>
      <div class="card">
        <div class="card-title">Reward Liability Payable</div>
        <div class="card-value" id="val-payable">$0.00</div>
        <div class="card-sub" style="color: #38bdf8;">Backed by Escrow Reserve</div>
      </div>
      <div class="card">
        <div class="card-title">Simulated Gameplay Equity</div>
        <div class="card-value" id="val-sim-bal">$0.00</div>
        <div class="card-sub" style="color: #94a3b8;" id="val-epoch">Epoch 0 / Stress 0.00</div>
      </div>
      <div class="card">
        <div class="card-title">Verified Missions & XP</div>
        <div class="card-value" id="val-xp">0 XP</div>
        <div class="card-sub" id="val-missions">0 Quests Completed</div>
      </div>
    </div>

    <!-- Chart -->
    <div class="chart-container">
      <canvas id="equityChart"></canvas>
    </div>

    <!-- Dual Tables: Real Inflows vs Simulated Journal -->
    <div class="dual-tables">
      <div>
        <h3 style="font-size: 1rem; margin-bottom: 10px; color: #34d399;">Authoritative Clearing Inflows (Stripe / On-Chain)</h3>
        <table>
          <thead>
            <tr>
              <th>Deposit ID</th>
              <th>Rail</th>
              <th>Clearing Ref</th>
              <th>Amount</th>
            </tr>
          </thead>
          <tbody id="inflow-table"></tbody>
        </table>
      </div>

      <div>
        <h3 style="font-size: 1rem; margin-bottom: 10px; color: #38bdf8;">Simulation Macroeconomic Transactions</h3>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Type</th>
              <th>Delta</th>
              <th>Balance</th>
              <th>Audit Hash</th>
            </tr>
          </thead>
          <tbody id="tx-table"></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    async function loadData() {
      try {
        const res = await fetch('/api/state');
        const d = await res.json();

        // Cards
        document.getElementById('val-escrow').innerText = '$' + (d.verifiable.escrow_cents / 100).toFixed(2);
        document.getElementById('val-inflow').innerText = '+$' + (d.verifiable.total_cleared_inflow_cents / 100).toFixed(2) + ' external inflows';
        document.getElementById('val-payable').innerText = '$' + (d.verifiable.payable_cents / 100).toFixed(2);
        
        document.getElementById('val-sim-bal').innerText = '$' + (d.simulated.profile.balance_cents / 100).toFixed(2);
        document.getElementById('val-epoch').innerText = 'Epoch ' + d.simulated.profile.level_index + ' | Stress: ' + d.simulated.profile.adaptive_stress.toFixed(2);

        document.getElementById('val-xp').innerText = d.verifiable.gameplay.xp + ' XP';
        document.getElementById('val-missions').innerText = d.verifiable.gameplay.verified_quests + ' Verified Missions';

        // Inflow Table
        const inTbody = document.getElementById('inflow-table');
        inTbody.innerHTML = '';
        if (d.verifiable.deposits.length === 0) {
          inTbody.innerHTML = '<tr><td colspan="4" style="color: #64748b;">No external clearing deposits recorded yet.</td></tr>';
        } else {
          d.verifiable.deposits.forEach(dep => {
            inTbody.innerHTML += `<tr>
              <td class="mono">${dep.deposit_id}</td>
              <td><span style="color:#34d399; font-weight:600;">${dep.source_rail}</span></td>
              <td class="mono">${dep.clearing_ref.substring(0, 16)}...</td>
              <td class="profit">+$${(dep.amount_cents / 100).toFixed(2)}</td>
            </tr>`;
          });
        }

        // Sim TX Table
        const simTbody = document.getElementById('tx-table');
        simTbody.innerHTML = '';
        d.simulated.recent_tx.forEach(tx => {
          const isPos = tx.amount_cents >= 0;
          simTbody.innerHTML += `<tr>
            <td>#${tx.id}</td>
            <td>${tx.tx_type}</td>
            <td style="color:${isPos ? '#34d399' : '#f87171'}">${isPos ? '+' : ''}$${(tx.amount_cents / 100).toFixed(2)}</td>
            <td>$${(tx.balance_after_cents / 100).toFixed(2)}</td>
            <td class="mono">${tx.tx_hash.substring(0, 10)}...</td>
          </tr>`;
        });

        // Chart
        const ctx = document.getElementById('equityChart').getContext('2d');
        new Chart(ctx, {
          type: 'line',
          data: {
            labels: d.simulated.chart.map(p => 'E' + p.id),
            datasets: [{
              label: 'Macro Cycle Simulation Equity ($)',
              data: d.simulated.chart.map(p => p.balance_after_cents / 100),
              borderColor: '#38bdf8',
              backgroundColor: 'rgba(56, 189, 248, 0.08)',
              fill: true,
              tension: 0.2,
              borderWidth: 2,
              pointRadius: 1
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: true, labels: { color: '#94a3b8' } } },
            scales: {
              x: { grid: { color: '#1f2937' }, ticks: { color: '#64748b' } },
              y: { grid: { color: '#1f2937' }, ticks: { color: '#64748b', callback: v => '$' + v } }
            }
          }
        });
      } catch (e) {
        console.error("Dashboard render failed:", e);
      }
    }
    loadData();
  </script>
</body>
</html>
"""

class DualLedgerDashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/state":
            payload = {"verifiable": {}, "simulated": {}}

            # 1. Pull Authoritative Verifiable Ledger
            if VERIFIABLE_DB.exists():
                conn = sqlite3.connect(str(VERIFIABLE_DB))
                cur = conn.cursor()
                
                # Balances
                cur.execute("SELECT account_id, balance_cents FROM financial_accounts;")
                accs = dict(cur.fetchall())
                payload["verifiable"]["escrow_cents"] = accs.get("ESCROW_RESERVE", 0)
                payload["verifiable"]["payable_cents"] = accs.get("REWARD_PAYABLE", 0)

                # Total Inflows & Recent Deposits
                cur.execute("SELECT IFNULL(SUM(amount_cents), 0) FROM external_deposits;")
                payload["verifiable"]["total_cleared_inflow_cents"] = cur.fetchone()[0]

                cur.execute("SELECT deposit_id, source_rail, clearing_ref,Here is the exact setup to deploy the updated `tinka_dashboard.py` into your repository, restart the background process, and verify that both the real escrow reserves and the simulated macro cycle appear live side-by-side.

---

### Step 1: Write the Dual-Ledger Dashboard Script

To prevent any paste truncation or indentation problems in your web terminal, write the file using Python's file handler:

```bash
cat << 'EOF' > make_dash.py
from pathlib import Path

content = '''#!/usr/bin/env python3
import json
import sqlite3
import sys
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

ROOT_DIR = Path(__file__).resolve().parent
VERIFIABLE_DB = ROOT_DIR / "tinka_verifiable.db"
SIMULATED_DB = ROOT_DIR / "tinka_ledger.db"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Tinka Infinite Engine - Verified Economic Mission Control</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="[https://cdn.jsdelivr.net/npm/chart.js](https://cdn.jsdelivr.net/npm/chart.js)"></script>
  <style>
    body { background-color: #0b0f19; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 24px; }
    .container { max-width: 1280px; margin: 0 auto; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 16px; margin-bottom: 24px; }
    .badges { display: flex; gap: 8px; }
    .badge-verified { background: #064e3b; color: #34d399; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 0.8rem; border: 1px solid #059669; }
    .badge-sim { background: #1e293b; color: #38bdf8; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 0.8rem; border: 1px solid #334155; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .card { background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 16px; }
    .card.highlight { border-color: #059669; background: #06241b; }
    .card-title { font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.05em; margin-bottom: 8px; }
    .card-value { font-size: 1.75rem; font-weight: 700; color: #f8fafc; }
    .card-sub { font-size: 0.8rem; color: #10b981; margin-top: 4px; font-weight: 500; }
    .dual-tables { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 24px; }
    @media (max-width: 900px) { .dual-tables { grid-template-columns: 1fr; } }
    .chart-container { background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 20px; margin-bottom: 24px; height: 320px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.825rem; background: #111827; border-radius: 8px; overflow: hidden; border: 1px solid #1f2937; }
    th, td { padding: 10px 14px; text-align: left; }
    th { background: #1e293b; color: #94a3b8; font-weight: 600; }
    tr:not(:last-child) td { border-bottom: 1px solid #1f2937; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #94a3b8; }
    .profit { color: #34d399; font-weight: 600; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <h1 style="margin: 0; font-size: 1.5rem;">Tinka Autonomous Economic Engine</h1>
        <small style="color: #64748b;">Project: venture-engine-1411e | Operator: bambiblack808-art</small>
      </div>
      <div class="badges">
        <div class="badge-verified">REAL ASSET VERIFIED (SQLITE WAL)</div>
        <div class="badge-sim">155 MACRO EPOCHS ACTIVE</div>
      </div>
    </div>

    <!-- Top Key Metrics Cards -->
    <div class="grid">
      <div class="card highlight">
        <div class="card-title">Verified Liquid Escrow</div>
        <div class="card-value" id="val-escrow">$0.00</div>
        <div class="card-sub" id="val-inflow">+$0.00 external inflows cleared</div>
      </div>
      <div class="card">
        <div class="card-title">Reward Liability Payable</div>
        <div class="card-value" id="val-payable">$0.00</div>
        <div class="card-sub" style="color: #38bdf8;">Backed by Escrow Reserve</div>
      </div>
      <div class="card">
        <div class="card-title">Simulated Gameplay Equity</div>
        <div class="card-value" id="val-sim-bal">$0.00</div>
        <div class="card-sub" style="color: #94a3b8;" id="val-epoch">Epoch 0 / Stress 0.00</div>
      </div>
      <div class="card">
        <div class="card-title">Verified Missions & XP</div>
        <div class="card-value" id="val-xp">0 XP</div>
        <div class="card-sub" id="val-missions">0 Quests Completed</div>
      </div>
    </div>

    <!-- Chart -->
    <div class="chart-container">
      <canvas id="equityChart"></canvas>
    </div>

    <!-- Dual Tables: Real Inflows vs Simulated Journal -->
    <div class="dual-tables">
      <div>
        <h3 style="font-size: 1rem; margin-bottom: 10px; color: #34d399;">Authoritative Clearing Inflows (Stripe / On-Chain)</h3>
        <table>
          <thead>
            <tr>
              <th>Deposit ID</th>
              <th>Rail</th>
              <th>Clearing Ref</th>
              <th>Amount</th>
            </tr>
          </thead>
          <tbody id="inflow-table"></tbody>
        </table>
      </div>

      <div>
        <h3 style="font-size: 1rem; margin-bottom: 10px; color: #38bdf8;">Simulation Macroeconomic Transactions</h3>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Type</th>
              <th>Delta</th>
              <th>Balance</th>
              <th>Audit Hash</th>
            </tr>
          </thead>
          <tbody id="tx-table"></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    async function loadData() {
      try {
        const res = await fetch('/api/state');
        const d = await res.json();

        document.getElementById('val-escrow').innerText = '$' + (d.verifiable.escrow_cents / 100).toFixed(2);
        document.getElementById('val-inflow').innerText = '+$' + (d.verifiable.total_cleared_inflow_cents / 100).toFixed(2) + ' external inflows';
        document.getElementById('val-payable').innerText = '$' + (d.verifiable.payable_cents / 100).toFixed(2);
        
        document.getElementById('val-sim-bal').innerText = '$' + (d.simulated.profile.balance_cents / 100).toFixed(2);
        document.getElementById('val-epoch').innerText = 'Epoch ' + d.simulated.profile.level_index + ' | Stress: ' + d.simulated.profile.adaptive_stress.toFixed(2);

        document.getElementById('val-xp').innerText = d.verifiable.gameplay.xp + ' XP';
        document.getElementById('val-missions').innerText = d.verifiable.gameplay.verified_quests + ' Verified Missions';

        const inTbody = document.getElementById('inflow-table');
        inTbody.innerHTML = '';
        if (d.verifiable.deposits.length === 0) {
          inTbody.innerHTML = '<tr><td colspan="4" style="color: #64748b;">No external clearing deposits recorded yet.</td></tr>';
        } else {
          d.verifiable.deposits.forEach(dep => {
            inTbody.innerHTML += `<tr>
              <td class="mono">${dep.deposit_id}</td>
              <td><span style="color:#34d399; font-weight:600;">${dep.source_rail}</span></td>
              <td class="mono">${dep.clearing_ref.substring(0, 16)}...</td>
              <td class="profit">+$${(dep.amount_cents / 100).toFixed(2)}</td>
            </tr>`;
          });
        }

        const simTbody = document.getElementById('tx-table');
        simTbody.innerHTML = '';
        d.simulated.recent_tx.forEach(tx => {
          const isPos = tx.amount_cents >= 0;
          simTbody.innerHTML += `<tr>
            <td>#${tx.id}</td>
            <td>${tx.tx_type}</td>
            <td style="color:${isPos ? '#34d399' : '#f87171'}">${isPos ? '+' : ''}$${(tx.amount_cents / 100).toFixed(2)}</td>
            <td>$${(tx.balance_after_cents / 100).toFixed(2)}</td>
            <td class="mono">${tx.tx_hash.substring(0, 10)}...</td>
          </tr>`;
        });

        const ctx = document.getElementById('equityChart').getContext('2d');
        new Chart(ctx, {
          type: 'line',
          data: {
            labels: d.simulated.chart.map(p => 'E' + p.id),
            datasets: [{
              label: 'Macro Cycle Simulation Equity ($)',
              data: d.simulated.chart.map(p => p.balance_after_cents / 100),
              borderColor: '#38bdf8',
              backgroundColor: 'rgba(56, 189, 248, 0.08)',
              fill: true,
              tension: 0.2,
              borderWidth: 2,
              pointRadius: 1
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: true, labels: { color: '#94a3b8' } } },
            scales: {
              x: { grid: { color: '#1f2937' }, ticks: { color: '#64748b' } },
              y: { grid: { color: '#1f2937' }, ticks: { color: '#64748b', callback: v => '$' + v } }
            }
          }
        });
      } catch (e) {
        console.error("Dashboard render error:", e);
      }
    }
    loadData();
  </script>
</body>
</html>
"""

class DualLedgerDashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/state":
            payload = {"verifiable": {}, "simulated": {}}

            if VERIFIABLE_DB.exists():
                conn = sqlite3.connect(str(VERIFIABLE_DB))
                cur = conn.cursor()
                
                cur.execute("SELECT account_id, balance_cents FROM financial_accounts;")
                accs = dict(cur.fetchall())
                payload["verifiable"]["escrow_cents"] = accs.get("ESCROW_RESERVE", 0)
                payload["verifiable"]["payable_cents"] = accs.get("REWARD_PAYABLE", 0)

                cur.execute("SELECT IFNULL(SUM(amount_cents), 0) FROM external_deposits;")
                payload["verifiable"]["total_cleared_inflow_cents"] = cur.fetchone()[0]

                cur.execute("SELECT deposit_id, source_rail, clearing_ref, amount_cents, created_at FROM external_deposits ORDER BY created_at DESC LIMIT 6;")
                payload["verifiable"]["deposits"] = [
                    {"deposit_id": r[0], "source_rail": r[1], "clearing_ref": r[2], "amount_cents": r[3], "created_at": r[4]}
                    for r in cur.fetchall()
                ]

                cur.execute("SELECT xp, level, verified_quests_completed FROM player_gameplay WHERE player_id = 'bambiblack808-art';")
                gp = cur.fetchone() or (0, 1, 0)
                payload["verifiable"]["gameplay"] = {"xp": gp[0], "level": gp[1], "verified_quests": gp[2]}
                conn.close()

            if SIMULATED_DB.exists():
                conn = sqlite3.connect(str(SIMULATED_DB))
                cur = conn.cursor()
                cur.execute("SELECT balance_cents, level_index, adaptive_stress, success_rate FROM player_profile WHERE user_handle = 'bambiblack808-art';")
                row = cur.fetchone() or (0, 0, 1.0, 0.5)
                payload["simulated"]["profile"] = {"balance_cents": row[0], "level_index": row[1], "adaptive_stress": row[2], "success_rate": row[3]}

                cur.execute("SELECT id, timestamp, amount_cents, balance_after_cents, tx_type, tx_hash FROM transactions ORDER BY id DESC LIMIT 6;")
                payload["simulated"]["recent_tx"] = [
                    {"id": r[0], "timestamp": r[1], "amount_cents": r[2], "balance_after_cents": r[3], "tx_type": r[4], "tx_hash": r[5]}
                    for r in cur.fetchall()
                ]

                cur.execute("SELECT id, balance_after_cents FROM transactions ORDER BY id ASC;")
                payload["simulated"]["chart"] = [{"id": r[0], "balance_after_cents": r[1]} for r in cur.fetchall()]
                conn.close()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode())

def run(port=8080):
    server = HTTPServer(("0.0.0.0", port), DualLedgerDashboardHandler)
    print(f"Dual-Ledger Mission Control Live on http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\n[+] Dashboard stopped.")

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run(port)
'''

with open("tinka_dashboard.py", "w") as f:
    f.write(content.strip() + "\n")
print("tinka_dashboard.py updated successfully.")
