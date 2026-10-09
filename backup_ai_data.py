import os
import json
import datetime
from pathlib import Path
from git import Repo

IDENTIFIERS = {
    "primary_user": "carrodusjoshua",
    "github_handle": "bambiblack808",
    "backup_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
}

BACKUP_ROOT = Path("./backups")

def init_backup_structure():
    providers = ["gemini", "chatgpt", "grok", "manual_archives"]
    for provider in providers:
        (BACKUP_ROOT / provider).mkdir(parents=True, exist_ok=True)

def backup_gemini_metadata():
    api_key = os.getenv("GEMINI_API_KEY")
    output_path = BACKUP_ROOT / "gemini" / "gemini_metadata.json"
    data = {
        "account": IDENTIFIERS["primary_user"],
        "timestamp": IDENTIFIERS["backup_timestamp"],
        "status": "No API key found; manual Takeout archive recommended"
    }
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            models = [m.name for m in client.models.list()]
            data["models_available"] = models
            data["status"] = "Active API connection verified"
        except Exception as e:
            data["status"] = f"API query error: {str(e)}"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[+] Gemini snapshot recorded at {output_path}")

def backup_chatgpt_metadata():
    api_key = os.getenv("OPENAI_API_KEY")
    output_path = BACKUP_ROOT / "chatgpt" / "chatgpt_metadata.json"
    data = {
        "account": IDENTIFIERS["primary_user"],
        "timestamp": IDENTIFIERS["backup_timestamp"],
        "status": "No API key found; manual Data Export recommended"
    }
    if api_key:
        try:
            import openai
            client = openai.OpenAI(api_key=api_key)
            models = [m.id for m in client.models.list()]
            data["models_available"] = models
            data["status"] = "Active API connection verified"
        except Exception as e:
            data["status"] = f"API query error: {str(e)}"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[+] ChatGPT snapshot recorded at {output_path}")

def backup_grok_metadata():
    output_path = BACKUP_ROOT / "grok" / "grok_metadata.json"
    data = {
        "account": IDENTIFIERS["primary_user"],
        "handle": IDENTIFIERS["github_handle"],
        "timestamp": IDENTIFIERS["backup_timestamp"],
        "note": "Web conversation export requires manual X Archive extraction into /grok folder."
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[+] Grok placeholder recorded at {output_path}")

def git_commit_and_push():
    repo = Repo(".")
    repo.git.add(all=True)
    commit_msg = f"Automated AI Backup - {IDENTIFIERS['backup_timestamp']} [{IDENTIFIERS['github_handle']}]"
    if repo.is_dirty():
        repo.index.commit(commit_msg)
        print(f"[✓] Committed snapshot: '{commit_msg}'")
    else:
        print("[i] No file changes to commit.")

if __name__ == "__main__":
    init_backup_structure()
    backup_gemini_metadata()
    backup_chatgpt_metadata()
    backup_grok_metadata()
    git_commit_and_push()
