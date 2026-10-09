import os, sys, json, socket, datetime, subprocess
from pathlib import Path
from git import Repo

BACKUP_ROOT = Path("./backups")
CONN_DIR = BACKUP_ROOT / "remote_connections"
CONN_DIR.mkdir(parents=True, exist_ok=True)

def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "Unavailable"

def audit_remote_connections():
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    hostname = socket.gethostname()
    connection_data = {
        "timestamp_utc": timestamp,
        "hostname": hostname,
        "primary_user": "carrodusjoshua",
        "github_identity": "bambiblack808-art",
        "cloud_shell_project": os.getenv("GOOGLE_CLOUD_PROJECT", "venture-engine-1411e"),
        "client_ip_route": run_cmd("curl -s ifconfig.me || curl -s icanhazip.com"),
        "active_ssh_sessions": [line for line in run_cmd("who").splitlines() if line],
        "open_sockets": [line for line in run_cmd("ss -tunap 2>/dev/null || netstat -tunap 2>/dev/null").splitlines() if "ESTAB" in line],
        "git_remote_status": run_cmd("git remote -v")
    }
    filename = f"conn_audit_{datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")}.json"
    target_file = CONN_DIR / filename
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(connection_data, f, indent=2)
    print(f"[+] Remote connections & session telemetry captured: {target_file}")

def run_git_sync():
    try:
        repo = Repo(".")
        repo.git.add(all=True)
        if repo.is_dirty():
            ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
            repo.index.commit(f"Auto-Snapshot [On-Entry & Connections] - {ts}")
            origin = repo.remotes.origin
            origin.push()
            print("[v] Automatically synchronized session snapshots to GitHub.")
        else:
            print("[i] Repository clean; no new data to push.")
    except Exception as e:
        print(f"[!] Git sync warning: {e}")

if __name__ == "__main__":
    if Path("backup_ai_data.py").exists():
        os.system("python backup_ai_data.py")
    audit_remote_connections()
    run_git_sync()
