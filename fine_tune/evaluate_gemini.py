#!/usr/bin/env python3
"""
evaluate_gemini.py — run held-out Arya examples through the current Gemini
assistant and print a compact comparison against the reference completions.

Usage:
    python evaluate_gemini.py valid.jsonl --limit 10
    python evaluate_gemini.py valid.jsonl --positive-only

This is a lightweight validation tool, not a formal benchmark.
"""

from __future__ import annotations

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.gemini_agent import FALLBACK_MESSAGE, get_reply


def load_examples(path: Path) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                examples.append(json.loads(raw_line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
    return examples


def extract_user_message(prompt: str) -> str:
    if "\n\n" in prompt:
        return prompt.rsplit("\n\n", 1)[1].strip()
    return prompt.strip()


def count_questions(text: str) -> int:
    return text.count("?")


def has_booking_link(text: str) -> bool:
    return "rzp.io/rzp/2-hour-live-ai-masterclass" in text


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Gemini replies on held-out Arya examples.")
    parser.add_argument("jsonl_path", type=Path, help="Path to train.jsonl or valid.jsonl")
    parser.add_argument("--limit", type=int, default=10, help="Maximum examples to evaluate")
    parser.add_argument(
        "--positive-only",
        action="store_true",
        help="Only evaluate examples labeled as positive",
    )
    args = parser.parse_args()

    examples = load_examples(args.jsonl_path)
    if args.positive_only:
        examples = [example for example in examples if example.get("meta", {}).get("label") == "positive"]

    examples = examples[: args.limit]
    if not examples:
        print("No examples to evaluate.")
        return 1

    total_similarity = 0.0
    total_questions = 0
    link_hits = 0
    fallback_hits = 0

    print(f"Evaluating {len(examples)} examples from {args.jsonl_path.name}\n")

    for index, example in enumerate(examples, start=1):
        prompt = example["prompt"]
        reference = example["completion"].strip()
        meta = example.get("meta", {})
        scenario = meta.get("scenario", "unknown")
        label = meta.get("label", "unknown")

        user_message = extract_user_message(prompt)
        generated = get_reply([], user_message).strip()
        is_fallback = generated == FALLBACK_MESSAGE

        similarity = SequenceMatcher(None, reference, generated).ratio()
        question_count = count_questions(generated)
        link_present = has_booking_link(generated)

        total_similarity += similarity
        total_questions += question_count
        link_hits += int(link_present)
        fallback_hits += int(is_fallback)

        print(f"[{index}] scenario={scenario} label={label}")
        print(f"  user:      {user_message[:140]}")
        print(f"  reference: {reference[:180]}")
        print(f"  generated: {generated[:180]}")
        print(
            f"  similarity={similarity:.2f} questions={question_count} "
            f"link={link_present} fallback={is_fallback}"
        )
        print()

    average_similarity = total_similarity / len(examples)
    average_questions = total_questions / len(examples)
    link_rate = link_hits / len(examples)
    fallback_rate = fallback_hits / len(examples)

    print("Summary")
    print(f"  examples evaluated: {len(examples)}")
    print(f"  average similarity:  {average_similarity:.2f}")
    print(f"  average questions:   {average_questions:.2f}")
    print(f"  booking-link rate:   {link_rate:.2%}")
    print(f"  fallback rate:       {fallback_rate:.2%}")

    if fallback_hits:
        print("  note: Gemini quota is currently preventing live generations; responses fell back to the local fallback message.")

    # Heuristic signal only. Non-zero exit is reserved for load/runtime failures.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())