#!/usr/bin/env python3
"""
TINKA TELEMETRY COLLECTOR: Real GCP Infrastructure Waste Ingestion
Discovers idle VMs and unattached disks in venture-engine-1411e and creates
verifiable quests in tinka_verifiable.db.
"""

import sys
import json
import sqlite3
import hashlib
import datetime
from pathlib import Path

# Google Cloud SDKs
try:
    from google.cloud import compute_v1
    from google.cloud import monitoring_v3
except ImportError:
    print("Missing GCP client libraries. Run: pip install google-cloud-monitoring google-cloud-compute")
    sys.exit(1)

PROJECT_ID = "venture-engine-1411e"
DB_PATH = Path(__file__).resolve().parent / "tinka_verifiable.db"

# Pricing estimates (US/AU Region approximations in Integer Cents per month)
# Standard Persistent Disk: ~$0.040 per GB/mo = 4 cents/GB
COST_PER_GB_STANDARD_DISK_CENTS = 4
# SSD Persistent Disk: ~$0.170 per GB/mo = 17 cents/GB
COST_PER_GB_SSD_DISK_CENTS = 17
# Baseline e2-standard-2 instance: ~$48.92/mo = 4892 cents
BASELINE_E2_MONTHLY_CENTS = 4892


def register_verifiable_quest(
    quest_id: str,
    domain: str,
    problem_statement: str,
    baseline_metric: float,
    target_metric: float,
    window_seconds: int,
    pre_evidence: dict
) -> bool:
    """Inserts a discovered problem into the authoritative tinka_verifiable.db."""
    if not DB_PATH.exists():
        print(f"Error: {DB_PATH} not found.")
        return False

    pre_evidence_str = json.dumps(pre_evidence, sort_keys=True)
    evidence_hash = hashlib.sha256(pre_evidence_str.encode("utf-8")).hexdigest()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    try:
        with conn:
            conn.execute("""
                INSERT OR IGNORE INTO quests (
                    quest_id, domain, problem_statement, baseline_metric,
                    target_metric, observation_window_seconds, state,
                    created_at, pre_evidence_hash
                ) VALUES (?, ?, ?, ?, ?, ?, 'DISCOVERED', ?, ?);
            """, (
                quest_id,
                domain,
                problem_statement,
                baseline_metric,
                target_metric,
                window_seconds,
                now,
                evidence_hash
            ))
        print(f"[+] Successfully registered verifiable quest: {quest_id}")
        return True
    except sqlite3.Error as e:
        print(f"[-] Database insertion failed for {quest_id}: {e}")
        return False
    finally:
        conn.close()


def scan_unattached_disks(project_id: str):
    """Scans all Compute Engine disks in the project and identifies orphan volumes."""
    print(f"\n[Scanning GCP Compute API: Disks in {project_id}]...")
    client = compute_v1.DisksClient()
    request = compute_v1.AggregatedListDisksRequest(project=project_id)

    total_scanned = 0
    orphan_count = 0

    try:
        agg_list = client.aggregated_list(request=request)
        for zone, disks_scoped_list in agg_list:
            if not disks_scoped_list.disks:
                continue
            for disk in disks_scoped_list.disks:
                total_scanned += 1
                # If disk.users is empty or absent, disk is unattached
                if not disk.users:
                    orphan_count += 1
                    disk_size_gb = disk.size_gb
                    disk_type = "SSD" if "pd-ssd" in disk.type_ else "Standard"
                    rate = COST_PER_GB_SSD_DISK_CENTS if disk_type == "SSD" else COST_PER_GB_STANDARD_DISK_CENTS
                    monthly_burn_cents = disk_size_gb * rate
                    monthly_burn_dollars = monthly_burn_cents / 100.0

                    qid = f"QUEST-GCP-DISK-{disk.name}"
                    evidence = {
                        "source": "google.cloud.compute_v1.DisksClient",
                        "project_id": project_id,
                        "resource_id": disk.id,
                        "resource_name": disk.name,
                        "zone": zone.split("/")[-1],
                        "size_gb": disk_size_gb,
                        "disk_type": disk_type,
                        "status": disk.status,
                        "users_attached": [],
                        "estimated_monthly_burn_cents": monthly_burn_cents
                    }

                    statement = (
                        f"Unattached persistent disk '{disk.name}' ({disk_size_gb}GB {disk_type}) "
                        f"in {evidence['zone']} consuming ${monthly_burn_dollars:.2f}/mo with 0 attached instances."
                    )

                    register_verifiable_quest(
                        quest_id=qid,
                        domain="Cloud Storage Optimization",
                        problem_statement=statement,
                        baseline_metric=monthly_burn_dollars,
                        target_metric=0.0,  # Eliminating the unattached disk drops burn to $0
                        window_seconds=86400 * 7,
                        pre_evidence=evidence
                    )
        print(f"[✓] Scanned {total_scanned} disks: Found {orphan_count} unattached volumes.")
    except Exception as e:
        print(f"[-] Disk scan warning/failure: {e}")


def scan_idle_instances(project_id: str):
    """Queries Cloud Monitoring metric for instances with average CPU utilization < 5%."""
    print(f"\n[Scanning GCP Monitoring API: Idle Compute in {project_id}]...")
    client = monitoring_v3.MetricServiceClient()
    project_name = f"projects/{project_id}"

    # Query last 7 days of CPU utilization
    now = datetime.datetime.now(datetime.timezone.utc)
    start_time = now - datetime.timedelta(days=7)

    interval = monitoring_v3.TimeInterval(
        end_time={"seconds": int(now.timestamp())},
        start_time={"seconds": int(start_time.timestamp())}
    )

    aggregation = monitoring_v3.Aggregation(
        alignment_period={"seconds": 86400 * 7},  # 7-day average
        per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_MEAN
    )

    metric_filter = 'metric.type = "compute.googleapis.com/instance/cpu/utilization"'

    try:
        results = client.list_time_series(
            request={
                "name": project_name,
                "filter": metric_filter,
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                "aggregation": aggregation
            }
        )

        idle_count = 0
        for ts in results:
            instance_id = ts.metric.labels.get("instance_name") or ts.resource.labels.get("instance_id")
            zone = ts.resource.labels.get("zone", "unknown")

            for point in ts.points:
                mean_cpu = point.value.double_value  # Ratio: 0.05 = 5%
                if mean_cpu < 0.05:  # Less than 5% average utilization over 7 days
                    idle_count += 1
                    qid = f"QUEST-GCP-IDLEVM-{instance_id}"
                    evidence = {
                        "source": "google.cloud.monitoring_v3.MetricServiceClient",
                        "metric": "compute.googleapis.com/instance/cpu/utilization",
                        "instance_id": instance_id,
                        "zone": zone,
                        "mean_7d_utilization": round(mean_cpu, 4),
                        "estimated_monthly_burn_cents": BASELINE_E2_MONTHLY_CENTS
                    }

                    statement = (
                        f"Instance '{instance_id}' in {zone} is idle with {mean_cpu * 100:.2f}% "
                        f"average 7-day CPU load. Candidate for downsizing or scheduled shutdown."
                    )

                    register_verifiable_quest(
                        quest_id=qid,
                        domain="Compute Rightsizing",
                        problem_statement=statement,
                        baseline_metric=BASELINE_E2_MONTHLY_CENTS / 100.0,
                        target_metric=(BASELINE_E2_MONTHLY_CENTS / 100.0) * 0.25,  # Target 75% cost reduction
                        window_seconds=86400 * 14,
                        pre_evidence=evidence
                    )
        print(f"[✓] Monitoring query completed: Found {idle_count} idle instances.")
    except Exception as e:
        print(f"[-] Metric scan warning/failure: {e}")


if __name__ == "__main__":
    print("=" * 70)
    print(f"  TINKA TELEMETRY HARVESTER | TARGET PROJECT: {PROJECT_ID}")
    print("=" * 70)
    scan_unattached_disks(PROJECT_ID)
    scan_idle_instances(PROJECT_ID)
    print("=" * 70)
