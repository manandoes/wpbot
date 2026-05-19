#!/usr/bin/env python3
"""
validate.py — Validates train.jsonl or valid.jsonl for the Arya fine-tune dataset.

Usage:
    python validate.py train.jsonl
    python validate.py valid.jsonl

Exit codes:
    0 — all checks passed
    1 — one or more validation errors found
"""

import json
import sys
from collections import Counter

SYSTEM_PROMPT_START = "You are Arya, a friendly WhatsApp Sales Consultant for Coach Yogesh Vats' Jira with AI Masterclass."

REQUIRED_KEYS = {"prompt", "completion", "meta"}
REQUIRED_META_KEYS = {"scenario", "name_present", "role_relevant", "tone", "label"}

VALID_SCENARIOS = {
    "warm_opening", "qualify_yes", "qualify_no", "pitch",
    "objection_is_this_worth", "objection_too_busy", "objection_fresher",
    "objection_recording", "objection_not_interested", "follow_up",
    "booking_confirmation"
}
VALID_TONES = {"friendly", "empathetic", "concise", "reassuring"}
VALID_LABELS = {"positive", "negative"}


def validate_file(filepath: str) -> bool:
    errors = []
    scenario_counts = Counter()
    label_counts = Counter()
    total = 0

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"[ERROR] File not found: {filepath}")
        return False

    for i, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue

        total += 1

        # 1. Valid JSON
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"Line {i}: Invalid JSON — {e}")
            continue

        # 2. Required top-level keys
        missing_keys = REQUIRED_KEYS - set(obj.keys())
        if missing_keys:
            errors.append(f"Line {i}: Missing top-level keys: {missing_keys}")
            continue

        # 3. prompt starts with system prompt
        prompt = obj.get("prompt", "")
        if not isinstance(prompt, str) or not prompt.startswith(SYSTEM_PROMPT_START):
            errors.append(f"Line {i}: 'prompt' does not start with the required system prompt.")

        # 4. completion is non-empty string
        completion = obj.get("completion", "")
        if not isinstance(completion, str) or not completion.strip():
            errors.append(f"Line {i}: 'completion' is missing or empty.")

        # 5. meta fields
        meta = obj.get("meta", {})
        if not isinstance(meta, dict):
            errors.append(f"Line {i}: 'meta' must be an object.")
            continue

        missing_meta = REQUIRED_META_KEYS - set(meta.keys())
        if missing_meta:
            errors.append(f"Line {i}: Missing meta keys: {missing_meta}")
            continue

        scenario = meta.get("scenario")
        if scenario not in VALID_SCENARIOS:
            errors.append(f"Line {i}: Invalid scenario '{scenario}'. Must be one of {VALID_SCENARIOS}")
        else:
            scenario_counts[scenario] += 1

        tone = meta.get("tone")
        if tone not in VALID_TONES:
            errors.append(f"Line {i}: Invalid tone '{tone}'. Must be one of {VALID_TONES}")

        label = meta.get("label")
        if label not in VALID_LABELS:
            errors.append(f"Line {i}: Invalid label '{label}'. Must be one of {VALID_LABELS}")
        else:
            label_counts[label] += 1

        name_present = meta.get("name_present")
        if not isinstance(name_present, bool):
            errors.append(f"Line {i}: 'meta.name_present' must be a boolean.")

        role_relevant = meta.get("role_relevant")
        if not isinstance(role_relevant, bool):
            errors.append(f"Line {i}: 'meta.role_relevant' must be a boolean.")

    # --- Summary ---
    print(f"\n{'='*50}")
    print(f"File: {filepath}")
    print(f"Total examples: {total}")
    print(f"Errors found: {len(errors)}")
    print(f"\n--- Scenario Distribution ---")
    for scenario in sorted(VALID_SCENARIOS):
        count = scenario_counts.get(scenario, 0)
        print(f"  {scenario:<35} {count}")

    negative_count = label_counts.get("negative", 0)
    positive_count = label_counts.get("positive", 0)
    neg_pct = (negative_count / total * 100) if total > 0 else 0
    print(f"\n--- Label Distribution ---")
    print(f"  positive: {positive_count}")
    print(f"  negative: {negative_count} ({neg_pct:.1f}% of total)")

    if errors:
        print(f"\n--- Errors ---")
        for err in errors[:20]:
            print(f"  {err}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more errors.")
        print(f"{'='*50}\n")
        return False

    print(f"\n✅ All {total} examples passed validation.")
    print(f"{'='*50}\n")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate.py <path_to_jsonl>")
        sys.exit(1)

    filepath = sys.argv[1]
    passed = validate_file(filepath)
    sys.exit(0 if passed else 1)
