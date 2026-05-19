"""
integration_snippet.py
Minimal examples for calling a fine-tuned Arya model via:
  A) OpenAI-compatible API (works with OpenAI, Azure OpenAI, or any compatible endpoint)
  B) Hugging Face Inference API
"""

# ─────────────────────────────────────────────
# SHARED: The exact system prompt Arya was trained on
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """You are Arya, a friendly WhatsApp Sales Consultant for Coach Yogesh Vats' Jira with AI Masterclass. You are reaching out to cold contacts who have never heard of Coach Yogesh Vats before. Your sole mission is to spark interest and get them to book their ₹99 seat at the masterclass.

Product: Jira with AI Masterclass — LIVE 2-hour online session
By: Coach Yogesh Vats — Agile Transformation Coach & Jira + AI Trainer
Price: ₹99
Format: Live only. No recordings.
Access: After registration, participants are added to a WhatsApp group where the session link is shared.
Booking Link: https://rzp.io/rzp/2-hour-live-ai-masterclass

Coach credibility:
- 15+ years in Agile, Product, Project Management
- Trained 10,000+ professionals
- Hosted 500+ masterclasses
- Practical, implementation-focused training style

Keep all replies WhatsApp-friendly, short, warm, and human. Use light emojis (😊✅🚀). Never invent facts beyond this prompt. If asked something not in the prompt, reply: "Great question! Once you're in the WhatsApp group after registering, Coach Yogesh's team will be able to answer that directly 😊\""""


# ═══════════════════════════════════════════
# VARIANT A: OpenAI-compatible API (chat completions)
# Works with OpenAI fine-tuned models or Azure OpenAI
# ═══════════════════════════════════════════
def call_arya_openai(user_message: str) -> str:
    """
    Call the fine-tuned Arya model via OpenAI-compatible chat completions API.

    Replace:
      OPENAI_API_KEY  — your OpenAI API key
      FINE_TUNED_MODEL_ID — e.g. "ft:gpt-3.5-turbo-0125:your-org:arya:xxxxxxxx"
    """
    import openai  # pip install openai

    client = openai.OpenAI(
        api_key="YOUR_OPENAI_API_KEY",  # ← insert your key here
    )

    response = client.chat.completions.create(
        model="YOUR_FINE_TUNED_MODEL_ID",  # ← e.g. "ft:gpt-3.5-turbo-0125:org:arya:abc123"
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        max_tokens=200,
        temperature=0.7,
    )

    return response.choices[0].message.content


# ─── OR: using raw requests (no openai library needed) ───
def call_arya_openai_requests(user_message: str) -> str:
    import requests

    API_KEY = "YOUR_OPENAI_API_KEY"           # ← insert your key here
    MODEL_ID = "YOUR_FINE_TUNED_MODEL_ID"     # ← e.g. "ft:gpt-3.5-turbo-0125:org:arya:abc123"

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL_ID,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            "max_tokens": 200,
            "temperature": 0.7,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════
# VARIANT B: Hugging Face Inference API
# Works with models hosted on the HF Hub (after fine-tuning with transformers)
# ═══════════════════════════════════════════
def call_arya_huggingface(user_message: str) -> str:
    """
    Call the fine-tuned Arya model via Hugging Face Inference API.

    Replace:
      HF_API_TOKEN   — your HuggingFace API token (from https://huggingface.co/settings/tokens)
      HF_MODEL_ID    — e.g. "your-username/arya-jira-masterclass"
    """
    import requests

    HF_API_TOKEN = "YOUR_HF_API_TOKEN"            # ← insert your HF token here
    HF_MODEL_ID  = "your-username/arya-fine-tuned" # ← insert your HF model repo here

    # Build the prompt in the same format as training
    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_message}"

    response = requests.post(
        f"https://api-inference.huggingface.co/models/{HF_MODEL_ID}",
        headers={
            "Authorization": f"Bearer {HF_API_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "inputs": full_prompt,
            "parameters": {
                "max_new_tokens": 200,
                "temperature": 0.7,
                "return_full_text": False,  # return only the completion, not the prompt
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    result = response.json()
    # HF text-generation returns a list
    if isinstance(result, list) and result:
        return result[0].get("generated_text", "").strip()
    return str(result)


# ─── Quick test ───────────────────────────
if __name__ == "__main__":
    test_message = "Hi, who is this?"

    print("=== Testing OpenAI variant (requests) ===")
    print("(Replace API key and model ID before running)")
    # reply = call_arya_openai_requests(test_message)
    # print(f"Arya: {reply}")

    print("\n=== Testing HuggingFace variant ===")
    print("(Replace HF token and model ID before running)")
    # reply = call_arya_huggingface(test_message)
    # print(f"Arya: {reply}")
