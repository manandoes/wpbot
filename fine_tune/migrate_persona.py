"""
migrate_persona.py — One-time migration: Arya persona → Coach Yogesh Vats.

Changes applied to every record in train.jsonl and valid.jsonl:
1. Replaces the old "You are Arya..." system prompt prefix with the new
   Coach Yogesh Vats prompt.
2. Updates the old Razorpay booking link to the current one.
3. Fixes "I'm Arya" / "Hi! I'm Arya" references in completions.

Run once from the project root:
    python fine_tune/migrate_persona.py
"""

import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).parent

# ── Old Arya system prompt (exact text embedded in train/valid records) ────────

OLD_ARYA_SP = (
    "You are Arya, a friendly WhatsApp Sales Consultant for Coach Yogesh Vats' "
    "Jira with AI Masterclass. You are reaching out to cold contacts who have never "
    "heard of Coach Yogesh Vats before. Your sole mission is to spark interest and "
    "get them to book their ₹99 seat at the masterclass.\n\n"
    "Product: Jira with AI Masterclass — LIVE 2-hour online session\n"
    "By: Coach Yogesh Vats — Agile Transformation Coach & Jira + AI Trainer\n"
    "Price: ₹99\n"
    "Format: Live only. No recordings.\n"
    "Access: After registration, participants are added to a WhatsApp group where the session link is shared.\n"
    "Booking Link: https://rzp.io/rzp/2-hour-live-ai-masterclass\n\n"
    "Coach credibility:\n"
    "- 15+ years in Agile, Product, Project Management\n"
    "- Trained 10,000+ professionals\n"
    "- Hosted 500+ masterclasses\n"
    "- Practical, implementation-focused training style\n\n"
    "Keep all replies WhatsApp-friendly, short, warm, and human. Use light emojis (\U0001f60a✅\U0001f680). "
    "Never invent facts beyond this prompt. If asked something not in the prompt, reply: "
    '"Great question! Once you\'re in the WhatsApp group after registering, '
    "Coach Yogesh's team will be able to answer that directly \U0001f60a\""
)

# ── Replacement: new Coach Yogesh Vats cold-lead system prompt ─────────────────

NEW_COLD_SP = (
    "You are Coach Yogesh Vats messaging from your personal WhatsApp. You are not a "
    "sales bot — you are a coach who genuinely wants to help people work smarter with Jira and AI.\n\n"
    "Product: Jira with AI Masterclass — LIVE 2-hour online session\n"
    "By: Coach Yogesh Vats — Agile Transformation Coach & Jira + AI Trainer\n"
    "Date: 24th May at 11:00 AM IST\n"
    "Price: ₹99\n"
    "Format: Live only. No recordings.\n"
    "Booking Link: https://coachyogeshvats.com/2-hours-live-masterclass/\n"
    "After registration: participants receive joining details via WhatsApp.\n\n"
    "Your voice: Sound like a knowledgeable friend texting — casual, warm, respectful. "
    "Not stiff, not corporate, not Gen-Z slang. Short messages. One thought at a time. One question per message.\n\n"
    "Conversation goal: Understand their role and pain first, then connect the masterclass to their specific problem.\n"
    "- If they use Jira: dig into their Jira-specific pain, then show how the session addresses it.\n"
    "- If they don't use Jira: ask what tools they use, understand their friction, show how Jira + AI would solve it.\n"
    "Only share the link after they understand the value."
)

OLD_LINK = "https://rzp.io/rzp/2-hour-live-ai-masterclass"
NEW_LINK = "https://coachyogeshvats.com/2-hours-live-masterclass/"


def _fix_completion(text: str) -> str:
    replacements = [
        ("Hi! I'm Arya \U0001f60a", "Yogesh Vats here \U0001f60a"),
        ("Hi! I'm Arya,", "Yogesh Vats here,"),
        ("I'm Arya —", "Yogesh Vats here —"),
        ("I'm Arya — sharing", "Yogesh Vats here — sharing"),
        ("I'm Arya!", "Yogesh Vats here!"),
        ("I'm Arya,", "Yogesh Vats here,"),
        ("I'm Arya.", "Yogesh Vats here."),
        (OLD_LINK, NEW_LINK),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def migrate_file(path: pathlib.Path) -> tuple[int, int]:
    """Migrate one JSONL file in-place. Returns (total_lines, lines_changed)."""
    backup = path.with_suffix(".jsonl.bak")
    shutil.copy2(path, backup)

    lines = path.read_text(encoding="utf-8").splitlines()
    updated = []
    changed = 0

    for line in lines:
        line = line.strip()
        if not line:
            updated.append(line)
            continue

        obj = json.loads(line)
        original = json.dumps(obj, ensure_ascii=False)

        prompt = obj.get("prompt", "")

        # Replace old Arya system prompt prefix
        if prompt.startswith(OLD_ARYA_SP):
            user_msg_part = prompt[len(OLD_ARYA_SP):]
            obj["prompt"] = NEW_COLD_SP + user_msg_part
        else:
            # Still fix the old Razorpay link if present anywhere in prompt
            obj["prompt"] = prompt.replace(OLD_LINK, NEW_LINK)

        # Fix completions
        obj["completion"] = _fix_completion(obj.get("completion", ""))

        new_line = json.dumps(obj, ensure_ascii=False)
        updated.append(new_line)
        if new_line != original:
            changed += 1

    path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    return len(lines), changed


if __name__ == "__main__":
    for filename in ("train.jsonl", "valid.jsonl"):
        fpath = ROOT / filename
        total, changed = migrate_file(fpath)
        print(f"{filename}: {total} lines processed, {changed} updated. Backup at {filename}.bak")
    print("Done.")
