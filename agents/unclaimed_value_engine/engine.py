#!/usr/bin/env python3
"""
TINKA UNCLAIMED-VALUE ENGINE V1
Read-only discovery and evidence classification.
Standard library only. No transaction or signing capability.
"""

import json
import re
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

ROOT = Path.home() / ".tinka"
OUT = ROOT / "unclaimed_value_engine"
REPORT = OUT / "discovery_report.json"
AUDIT = OUT / "discovery_audit.jsonl"

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".cache",
    "venv", ".venv", "site-packages"
}

SKIP_NAME_PARTS = (
    "secret", "credential", "password", "private_key",
    "seed_phrase", "mnemonic", "cookie", "token",
    "kraken_env", "id_rsa"
)

MAX_FILE_SIZE = 2_000_000
MAX_FILES = 10000

PATTERNS = {
    "BITCOIN_BECH32": re.compile(
        r"(?<![a-zA-Z0-9])bc1[ac-hj-np-z02-9]{11,71}(?![a-zA-Z0-9])",
        re.IGNORECASE
    ),
    "BITCOIN_LEGACY": re.compile(
        r"(?<![a-zA-Z0-9])[13][a-km-zA-HJ-NP-Z1-9]{25,34}(?![a-zA-Z0-9])"
    ),
    "EVM_ADDRESS": re.compile(
        r"(?<![a-zA-Z0-9])0x[a-fA-F0-9]{40}(?![a-zA-Z0-9])"
    ),
}

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def safe_to_scan(path):
    try:
        if not path.is_file() or path.is_symlink():
            return False
        if any(part.lower() in SKIP_DIRS for part in path.parts):
            return False
        if any(word in path.name.lower() for word in SKIP_NAME_PARTS):
            return False
        if path.stat().st_size > MAX_FILE_SIZE:
            return False
        if path.suffix.lower() not in {
            ".json", ".jsonl", ".txt", ".csv", ".md",
            ".py", ".yaml", ".yml", ".toml", ".log"
        }:
            return False
        return True
    except OSError:
        return False

def main():
    OUT.mkdir(parents=True, exist_ok=True)

    findings = defaultdict(lambda: {
        "type": "",
        "files": set(),
        "occurrences": 0,
        "ownership": "UNVERIFIED",
        "eligibility": "UNVERIFIED",
        "action": "INVESTIGATE_PROVENANCE",
    })

    files_scanned = 0
    read_errors = 0
    files_with_hits = 0
    reward_leads = []
    address_hits = 0

    reward_terms = (
        "airdrop", "claimable", "unclaimed", "refund",
        "rebate", "reward", "incentive", "recovery"
    )

    for path in ROOT.rglob("*"):
        if files_scanned >= MAX_FILES:
            break
        if not safe_to_scan(path):
            continue

        try:
            content = path.read_text(errors="ignore")
            files_scanned += 1
            relative = str(path.relative_to(ROOT))
            found_in_file = False

            for kind, pattern in PATTERNS.items():
                for match in pattern.finditer(content):
                    address = match.group(0)
                    record = findings[address]
                    record["type"] = kind
                    record["files"].add(relative)
                    record["occurrences"] += 1
                    found_in_file = True
                    address_hits += 1

            if found_in_file:
                files_with_hits += 1

            lower_name = path.name.lower()
            if any(term in lower_name for term in reward_terms):
                reward_leads.append({
                    "file": relative,
                    "status": "UNVERIFIED_RESEARCH_LEAD",
                })

        except (OSError, UnicodeError):
            read_errors += 1

    candidates = []
    for address, record in findings.items():
        candidates.append({
            "address": address,
            "type": record["type"],
            "source_files": sorted(record["files"]),
            "occurrences": record["occurrences"],
            "ownership": record["ownership"],
            "claim_eligibility": record["eligibility"],
            "recommended_action": record["action"],
        })

    candidates.sort(key=lambda x: (
        x["type"], -x["occurrences"], x["address"]
    ))

    report = {
        "engine": "TINKA_UNCLAIMED_VALUE_ENGINE",
        "version": "1.0.0",
        "timestamp_utc": utc_now(),
        "mode": "READ_ONLY_LOCAL_DISCOVERY",
        "files_scanned": files_scanned,
        "read_errors": read_errors,
        "files_containing_address_candidates": files_with_hits,
        "address_occurrences": address_hits,
        "unique_address_candidates": len(candidates),
        "reward_filename_leads": reward_leads,
        "candidates": candidates,
        "safety": {
            "wallets_connected": False,
            "transactions_sent": False,
            "signatures_requested": False,
            "existing_ledger_modified": False,
            "ownership_inferred_from_address": False,
        },
        "limitations": [
            "Address format detection is not proof of address validity.",
            "A public address does not establish ownership.",
            "This version does not query live blockchain balances.",
            "Reward filename matches are leads, not confirmed entitlements.",
            "No funds have been claimed or moved.",
        ],
    }

    serialized = json.dumps(report, indent=2)
    REPORT.write_text(serialized + "\n")

    audit_record = {
        "timestamp_utc": utc_now(),
        "event": "DISCOVERY_SCAN_COMPLETED",
        "report_sha256": hashlib.sha256(
            serialized.encode()
        ).hexdigest(),
        "files_scanned": files_scanned,
        "candidate_count": len(candidates),
        "transactions_sent": False,
    }

    with AUDIT.open("a") as f:
        f.write(json.dumps(audit_record) + "\n")

    print("\n==========================================")
    print(" TINKA UNCLAIMED-VALUE ENGINE V1")
    print("==========================================")
    print("Mode:                   READ-ONLY")
    print("Files scanned:         ", files_scanned)
    print("Read errors:           ", read_errors)
    print("Files with candidates: ", files_with_hits)
    print("Address occurrences:   ", address_hits)
    print("Unique candidates:     ", len(candidates))
    print("Reward filename leads: ", len(reward_leads))
    print("------------------------------------------")

    for item in candidates[:30]:
        print("\nType:   ", item["type"])
        print("Address:", item["address"])
        print("Found:  ", len(item["source_files"]), "file(s)")
        for source in item["source_files"][:4]:
            print("  -", source)
        print("Owner:   UNVERIFIED")
        print("Claim:   NOT AUTHORIZED")

    if len(candidates) > 30:
        print("\nAdditional candidates are recorded in the report.")

    print("\nREPORT:", REPORT)
    print("AUDIT: ", AUDIT)
    print("------------------------------------------")
    print("Transactions sent:      NO")
    print("Existing ledger changed: NO")
    print("==========================================")

if __name__ == "__main__":
    main()
