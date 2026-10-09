import os, json, datetime
from pathlib import Path
from git import Repo

IDENTIFIERS = {
    "primary_user": "carrodusjoshua",
    "github_handle": "bambiblack808",
    "backup_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
}

B_ROOT = Path("./backups")
for p in ["gemini", "chatgpt", "grok", "manual_archives"]:
    (B_ROOT / p).mkdir(parents=True, exist_ok=True)


def save_data(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(the_data := data, f, indent=2)
    print(f"[+] Snapshot saved: {path}")


gemini_data = {
    "account": IDENTIFIERS["primary_user"],
    "timestamp": IDENTIFIERS["backup_timestamp"],
    "status": "No API key found; manual Takeout archive recommended"
}
if key := os.getenv("GEMINI_API_KEY"):
    try:
        from google import genai
        gemini_data["models"] = [m.name for m in genai.Client(api_key=key).models.list()]
        gemini_data["status"] = "Active API connection verified"
    except Exception as e:
        gemini_data["status"] = fstr = f"API_ERROR: {e}"
save_data(B_ROOT / "gemini" / "gemini_metadata.json", gemini_data)


chatgpt_data = {
    "account": IDENTIFIERS["primary_user"],
    "timestamp": IDENTIFIERS["backup_timestamp"],
    "status": "No API key found; manual Data Export recommended"
}
if key := os.getenv("OPENAI_API_KEY"):
    try:
        import openai
        chatgpt_data["models"] = [m.id for m in openai.OpenAI(api_key=key).models.list()]
        chatgpt_data["status"] = "Active API connection verified"
    except Exception as e:
        chatgpt_data["status"] = fstr = f"API_ERROR: {e}"
save_data(B_ROOT / "chatgpt" / "chatgpt_metadata.json", chatgpt_data)


grok_data = {
    "account": IDENTIFIERS["primary_user"],
    "handle": IDENTIFIERS["github_handle"],
    "timestamp": IDENTIFIERS["backup_timestamp"],
    "status": "Placeholder recorded. Manual X archive conversation files required."
}
save_data(B_ROOT / "grok" / "grok_metadata.json", grok_data)


repo = Repo(".")
repo.git.add(all=True)
commit_msg = f"AU Identities Snapshot [carrodusjoshua | bambiblack808] - {IDENTIFIERS['backup_timestamp']}"
if repo.is_dirty():
    repo.index.commit(commit_msg)
    print(f"[v] Committed: {commit_msg}")
else:
    print("[i] No changes to commit.")
