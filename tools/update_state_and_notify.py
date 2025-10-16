#!/usr/bin/env python3
"""Helper used by CI to update artifacts/state.json and send notifications.

This script expects artifacts/ to contain the most recent slots_*.json file
created by `src.checker --output-json`. It will find the newest slots file,
compute the next slot for TARGET_DOCTOR, compare with the stored state, send
an email (using the same send_notification logic) if an earlier slot is found,
and update `state.json`.
"""
import os
import sys
import json
import glob
import time
import logging

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
try:
    # import the module's helpers
    import checker
except Exception:
    # fallback: try to import as package
    import src.checker as checker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


def find_latest_slots(artifacts_dir):
    files = glob.glob(os.path.join(artifacts_dir, "slots_*.json"))
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


def load_state(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            logging.exception("Failed to read state file")
    return {}


def save_state(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception:
        logging.exception("Failed to save state file")


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", default="./artifacts", help="Artifacts directory")
    parser.add_argument("--state-file", default="./artifacts/state.json", help="State file path")
    args = parser.parse_args()

    artifacts_dir = args.artifacts
    state_file = args.state_file

    latest = find_latest_slots(artifacts_dir)
    if not latest:
        logging.info("No slots JSON found in %s", artifacts_dir)
        return 0

    try:
        with open(latest, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        logging.exception("Failed reading latest slots file %s", latest)
        return 2

    target = os.getenv("TARGET_DOCTOR")
    if not target:
        logging.info("No TARGET_DOCTOR set in env; nothing to do")
        return 0

    slots = data.get("slots", [])
    next_slot = checker.find_next_slot(slots, target, int(os.getenv("MAX_DAYS", "30")))
    state = load_state(state_file)

    saved = state.get(target)
    prev_hora = saved.get("hora") if saved else None
    new_hora = None
    if next_slot:
        new_hora = next_slot.get("HORA") or next_slot.get("hora") or next_slot.get("PROXIMA")

    def parse_dt(s):
        return checker._parse_slot_datetime(s) if s else None

    prev_dt = parse_dt(prev_hora)
    new_dt = parse_dt(new_hora)

    if new_dt and (not prev_dt or new_dt < prev_dt):
        # send notification
        msg = f"Slot freed for {target}: {new_hora}. Previously: {prev_hora}"
        try:
            checker.send_notification(msg)
            logging.info("Sent notification for %s", target)
        except Exception:
            logging.exception("Failed to send notification via checker.send_notification")
        state[target] = {"hora": new_hora, "raw": next_slot}
        save_state(state_file, state)
    else:
        logging.info("No earlier slot for %s (found=%s saved=%s)", target, new_dt, prev_dt)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
