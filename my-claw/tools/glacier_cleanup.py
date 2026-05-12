#!/usr/bin/env python3
"""
AWS Glacier Vault Cleanup Script

Reads a Glacier inventory JSON file, extracts all archive IDs, and deletes
them in batches using the AWS CLI. Supports resumption via a state file that
tracks which archives have already been deleted.

Usage:
    python3 glacier_cleanup.py \
        --inventory /tmp/glacier_inventory.json \
        --vault sldkfjslkf_001132EF1136_2 \
        --region us-west-2 \
        [--state /tmp/glacier_cleanup_state.json] \
        [--batch-size 50] \
        [--max-workers 4] \
        [--dry-run]

Prerequisites:
    - AWS CLI configured with appropriate credentials
    - Inventory file downloaded from a completed inventory-retrieval job:
        aws glacier get-job-output \
            --vault-name sldkfjslkf_001132EF1136_2 \
            --account-id - \
            --region us-west-2 \
            --job-id <JOB_ID> \
            /tmp/glacier_inventory.json
"""

import argparse
import json
import subprocess
import sys
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def log(msg: str) -> None:
    """Log a message to stderr with a timestamp."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr, flush=True)


def load_inventory(inventory_path: str) -> list[dict]:
    """Load the Glacier inventory JSON and return the list of archives."""
    log(f"Loading inventory from {inventory_path}")
    with open(inventory_path, "r") as f:
        data = json.load(f)

    archives = data.get("ArchiveList", [])
    log(f"Inventory contains {len(archives)} archives")
    return archives


def load_state(state_path: str) -> set[str]:
    """Load the set of already-deleted archive IDs from the state file."""
    if not Path(state_path).exists():
        log("No existing state file found; starting fresh")
        return set()

    with open(state_path, "r") as f:
        data = json.load(f)

    deleted = set(data.get("deleted_ids", []))
    log(f"Loaded state: {len(deleted)} archives already deleted")
    return deleted


def save_state(state_path: str, deleted_ids: set[str], total: int) -> None:
    """Persist the set of deleted archive IDs to the state file."""
    data = {
        "total_archives": total,
        "deleted_count": len(deleted_ids),
        "deleted_ids": sorted(deleted_ids),
    }
    # Write atomically: write to tmp then rename
    tmp_path = state_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f)
    os.replace(tmp_path, state_path)


def delete_archive(
    vault: str, region: str, archive_id: str, dry_run: bool = False
) -> tuple[str, bool, str]:
    """
    Delete a single archive from the vault.

    Returns (archive_id, success, error_message).
    Implements exponential backoff for throttling (HTTP 429 / ThrottlingException).
    """
    if dry_run:
        return (archive_id, True, "")

    max_retries = 5
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                [
                    "aws", "glacier", "delete-archive",
                    "--vault-name", vault,
                    "--account-id", "-",
                    "--region", region,
                    "--archive-id", archive_id,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                return (archive_id, True, "")

            stderr = result.stderr
            # Retry on throttling
            if "Throttling" in stderr or "Rate exceeded" in stderr or "SlowDown" in stderr:
                delay = base_delay * (2 ** attempt)
                log(f"Throttled on attempt {attempt + 1}/{max_retries}, "
                    f"retrying in {delay:.1f}s...")
                time.sleep(delay)
                continue

            return (archive_id, False, stderr.strip())

        except subprocess.TimeoutExpired:
            delay = base_delay * (2 ** attempt)
            log(f"Timeout on attempt {attempt + 1}/{max_retries}, "
                f"retrying in {delay:.1f}s...")
            time.sleep(delay)
            continue

    return (archive_id, False, f"Exhausted {max_retries} retries")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete all archives from an AWS Glacier vault using an inventory file."
    )
    parser.add_argument(
        "--inventory", required=True,
        help="Path to the downloaded Glacier inventory JSON file",
    )
    parser.add_argument(
        "--vault", required=True,
        help="Name of the Glacier vault",
    )
    parser.add_argument(
        "--region", required=True,
        help="AWS region of the vault",
    )
    parser.add_argument(
        "--state", default="/tmp/glacier_cleanup_state.json",
        help="Path to the state file for resumption (default: /tmp/glacier_cleanup_state.json)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=50,
        help="Number of archives to delete before saving state (default: 50)",
    )
    parser.add_argument(
        "--max-workers", type=int, default=4,
        help="Number of parallel deletion threads (default: 4)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be deleted without actually deleting",
    )
    args = parser.parse_args()

    # Load inventory and state
    archives = load_inventory(args.inventory)
    deleted_ids = load_state(args.state)
    total = len(archives)

    # Filter out already-deleted archives
    remaining = [a for a in archives if a["ArchiveId"] not in deleted_ids]
    log(f"{len(remaining)} archives remaining to delete out of {total} total")

    if not remaining:
        log("Nothing to delete. All archives already processed.")
        return

    if args.dry_run:
        log("DRY RUN: would delete the following archives:")
        for a in remaining[:10]:
            log(f"  {a['ArchiveId'][:40]}...")
        if len(remaining) > 10:
            log(f"  ... and {len(remaining) - 10} more")
        return

    # Process in batches
    errors = 0
    batch_start = 0

    while batch_start < len(remaining):
        batch = remaining[batch_start : batch_start + args.batch_size]
        batch_num = (batch_start // args.batch_size) + 1
        total_batches = (len(remaining) + args.batch_size - 1) // args.batch_size

        log(f"Batch {batch_num}/{total_batches}: deleting {len(batch)} archives "
            f"({len(deleted_ids)}/{total} done so far)")

        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {
                executor.submit(
                    delete_archive, args.vault, args.region, a["ArchiveId"]
                ): a["ArchiveId"]
                for a in batch
            }

            for future in as_completed(futures):
                archive_id, success, err = future.result()
                if success:
                    deleted_ids.add(archive_id)
                else:
                    errors += 1
                    log(f"FAILED to delete {archive_id[:40]}...: {err}")

        # Save state after each batch
        save_state(args.state, deleted_ids, total)
        log(f"State saved: {len(deleted_ids)}/{total} deleted, {errors} errors so far")

        batch_start += args.batch_size

    # Final summary
    log("=" * 60)
    log(f"DONE. Deleted {len(deleted_ids)}/{total} archives. Errors: {errors}")
    if len(deleted_ids) == total:
        log("All archives deleted. You can now delete the vault:")
        log(f"  aws glacier delete-vault --vault-name {args.vault} "
            f"--account-id - --region {args.region}")
    elif errors > 0:
        log("Some deletions failed. Re-run this script to retry.")
    log("=" * 60)


if __name__ == "__main__":
    main()
