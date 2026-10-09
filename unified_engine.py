import os
import sys
import json
import socket
import datetime
import subprocess
from pathlib import Path
from git import Repo

CONFIG = {
    "primary_user": "carrodusjoshua",
    "github_owner": "bambiblack808-art",
    "gcp_project_id": "venture-engine-1411e",
    "gcp_region": "australia-southeast1",
    "location_locale": "Bentleigh East, Victoria, Australia",
    "repo_path": "/home/bambiblack808/workspace/ai-unified-backups",
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
}

BACKUP_ROOT = Path("./backups")
for sub in ["gemini", "chatgpt", "grok", "remote_connections", "endpoint_management", "manual_archives"]:
    (BACKUP_ROOT / sub).mkdir(parents=True, exist_ok=True)

def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "Unavailable"

def snapshot_ai_metadata():
    gemini_file = BACKUP_ROOT / "gemini" / "gemini_metadata.json"
    g_data = {
        "account": CONFIG["primary_user"],
        "project_id": CONFIG["gcp_project_id"],
        "region": CONFIG["gcp_region"],
        "locale": CONFIG["location_locale"],
        "timestamp": CONFIG["timestamp"],
        "status": "Verified active GCP/AI Studio environment"
    }
    if key := os.getenv("GEMINI_API_KEY"):
        try:
            from google import genai
            client = genai.Client(api_key=key)
            g_data["models"] = [m.name for m in client.models.list()]
            g_data["api_connection"] = "Authenticated"
        except Exception as e:
            g_data["api_error"] = str(e)
    with open(gemini_file, "w", encoding="utf-8") as f:
        json.dump(g_data, f, indent=2)

    chatgpt_file = BACKUP_ROOT / "chatgpt" / "chatgpt_metadata.json"
    c_data = {
        "account": CONFIG["primary_user"],
        "timestamp": CONFIG["timestamp"],
        "status": "Metadata recorded; export JSON/ZIP placed in manual_archives/"
    }
    if key := os.getenv("OPENAI_API_KEY"):
        try:
            import openai
            client = openai.OpenAI(api_key=key)
            c_data["models"] = [m.id for m in client.models.list()]
            c_data["api_connection"] = "Authenticated"
        except Exception as e:
            c_data["api_error"] = str(e)
    with open(chatgpt_file, "w", encoding="utf-8") as f:
        json.dump(c_data, f, indent=2)

    grok_file = BACKUP_ROOT / "grok" / "grok_metadata.json"
    gr_data = {
        "account": CONFIG["primary_user"],
        "github_identity": CONFIG["github_owner"],
        "timestamp": CONFIG["timestamp"],
        "status": "Archive placeholder active"
    }
    with open(grok_file, "w", encoding="utf-8") as f:
        json.dump(gr_data, f, indent=2)

    print("[+] AI state snapshots compiled (Gemini, ChatGPT, Grok).")

def audit_connections_and_endpoints():
    ts_slug = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    audit_file = BACKUP_ROOT / "remote_connections" / f"audit_{ts_slug}.json"
    data = {
        "timestamp": CONFIG["timestamp"],
        "target_user": CONFIG["primary_user"],
        "target_github": CONFIG["github_owner"],
        "target_gcp_project": CONFIG["gcp_project_id"],
        "target_region": CONFIG["gcp_region"],
        "locale": CONFIG["location_locale"],
        "hostname": socket.gethostname(),
        "egress_public_ip": run_cmd("curl -s ifconfig.me || curl -s icanhazip.com"),
        "active_sessions": [s for s in run_cmd("who").splitlines() if s],
        "established_sockets": [s for s in run_cmd("ss -tunp 2>/dev/null").splitlines() if "ESTAB" in s],
        "git_status": run_cmd("git remote -v")
    }
    with open(audit_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[+] Remote connection & perimeter audit saved: {audit_file}")

def push_to_github():
    try:
        repo = Repo(CONFIG["repo_path"])
        repo.git.add(all=True)
        if repo.is_dirty():
            msg = f"Auto-Sync [Project: {CONFIG['gcp_project_id']} | User: {CONFIG['github_owner']}] - {CONFIG['timestamp']}"
            repo.index.commit(msg)
            origin = repo.remotes.origin
            origin.push()
            print(f"[v] Synchronized commit to GitHub origin/main: {msg}")
        else:
            print("[i] No file changes to push.")
    except Exception as e:
        print(f"[!] Git sync error: {e}")

if __name__ == "__main__":
    snapshot_ai_metadata()
    audit_connections_and_endpoints()
    push_to_github()
