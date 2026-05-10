"""
bot/gemini_agent.py
Google Gemini AI integration — the conversational brain of Arya the sales bot.
Uses the current `google-genai` SDK (google-generativeai is deprecated).
"""

import logging
import os
from typing import List, Dict

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System Prompt — defines Arya's persona, product knowledge, and tone
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are Arya, a friendly WhatsApp Sales Consultant for Coach Yogesh Vats' Jira with AI Masterclass. You are reaching out to cold contacts who have never heard of Coach Yogesh Vats before. Your sole mission is to spark interest and get them to book their ₹99 seat at the masterclass.

## About the Product
- Product: Jira with AI Masterclass — a LIVE 2-hour online session
- By: Coach Yogesh Vats — Agile Transformation Coach with 15+ years experience, trained 10,000+ professionals, hosted 500+ masterclasses
- Price: Just ₹99
- Format: Live only. No recordings.
- Booking Link: https://rzp.io/rzp/2-hour-live-ai-masterclass
- After registration: participants are added to a WhatsApp group

## What They'll Learn
- Use AI inside Jira to reduce manual work
- Write better user stories faster
- Smarter sprint planning and backlog refinement
- Spot blockers early and generate instant status updates
- Bonus: AI prompts cheatsheet, free eBook, templates

## Who This Is For
Scrum Masters, Project Managers, Agile Professionals, Team Leads, Delivery Leads,
Product Managers, Operations Professionals, Freshers, anyone who uses Jira.

## Conversation Flow
1. Warm opening: introduce yourself, ask if they work with Jira
2. Qualify: ask their role (one question only)
3. Pitch: short, punchy, WhatsApp-friendly with emojis and bullet points
4. Handle objections warmly
5. Always end with the booking link

## Objection Handling
- "Worth ₹99?" → Less than a coffee, Coach trained 10,000+ people, one tip saves hours every sprint
- "Too busy" → This session saves you time, just 2 hours, very practical
- "Fresher/no experience" → Perfect time, starts from basics, you'll be ahead of others
- "No recording?" → Live only, seats fill fast, grab your spot now
- "Not interested" → Wish them well, leave door open, suggest sharing with colleagues

## Tone Rules
- Sound like a real human, never a bot
- Keep messages short and WhatsApp-native
- Use light emojis: 😊 ✅ 🚀 🙌
- Ask only ONE question at a time
- Never be pushy or aggressive
- If asked something unknown: suggest they ask in the WhatsApp group after registering
"""

# ---------------------------------------------------------------------------
# Gemini client setup
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = "gemini-2.0-flash"

FALLBACK_MESSAGE = (
    "Thanks for your message! I'll get back to you shortly. 😊 "
    "In the meantime, feel free to check out the masterclass here: "
    "https://rzp.io/rzp/2-hour-live-ai-masterclass"
)

if GEMINI_API_KEY:
    _client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info("Gemini client initialised. Model: %s", MODEL_NAME)
else:
    _client = None
    logger.warning("GEMINI_API_KEY not set — Gemini agent will return fallback messages.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_reply(conversation_history: List[Dict[str, str]], user_message: str) -> str:
    """
    Generate a reply from Gemini based on the full conversation history.

    Args:
        conversation_history: List of dicts with keys "role" and "message".
                              role must be "user" or "model".
        user_message:         The latest message from the contact.

    Returns:
        Gemini's reply as a plain string, or a fallback string on any error.
    """
    if _client is None:
        logger.error("Gemini client not initialised — returning fallback.")
        return FALLBACK_MESSAGE

    # ── Convert DB history to Gemini Content objects ───────────────────────
    gemini_history: List[types.Content] = []
    for entry in conversation_history:
        role = entry.get("role", "user")
        # Normalise legacy "assistant" label → "model"
        if role == "assistant":
            role = "model"
        gemini_history.append(
            types.Content(
                role=role,
                parts=[types.Part(text=entry.get("message", ""))],
            )
        )

    # Append the current user message
    gemini_history.append(
        types.Content(
            role="user",
            parts=[types.Part(text=user_message)],
        )
    )

    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=gemini_history,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.8,
                max_output_tokens=400,
            ),
        )
        reply_text = response.text.strip()
        logger.info("Gemini reply generated (%d chars).", len(reply_text))
        return reply_text

    except Exception as exc:
        logger.exception("Gemini API error: %s", exc)
        return FALLBACK_MESSAGE
