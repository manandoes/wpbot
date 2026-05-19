# Arya – WhatsApp Sales Consultant Fine-Tune Dataset

A training dataset for fine-tuning a conversational AI assistant named **Arya**, a WhatsApp Sales Consultant for Coach Yogesh Vats' *Jira with AI Masterclass*.

---

## Files

| File | Description |
|---|---|
| `train.jsonl` | 200 training examples (JSONL, one object per line) |
| `valid.jsonl` | 40 validation examples (JSONL, one object per line) |
| `schema.json` | JSON Schema describing the structure of each JSONL record |
| `validate.py` | Python validation script for dataset quality checks |
| `integration_snippet.py` | Minimal API call examples (OpenAI + HuggingFace) |
| `examples_summary.txt` | Counts per scenario and label in each file |
| `README.md` | This file |

---

## Dataset Format

Each line in `train.jsonl` and `valid.jsonl` is a JSON object with three fields:

```json
{
  "prompt": "<SYSTEM_PROMPT>\n\n<USER_MESSAGE>",
  "completion": "Arya's ideal WhatsApp reply 😊",
  "meta": {
    "scenario": "warm_opening",
    "name_present": true,
    "role_relevant": true,
    "tone": "friendly",
    "label": "positive"
  }
}
```

See `schema.json` for full field definitions and allowed values.

### Scenarios covered
- `warm_opening` — Initial cold outreach response
- `qualify_yes` / `qualify_no` — Qualifying the contact's Jira relevance
- `pitch` — Answering product/pricing/logistics questions
- `objection_is_this_worth` — "Is ₹99 worth it?"
- `objection_too_busy` — "I don't have time"
- `objection_fresher` — "I'm a fresher / just starting out"
- `objection_recording` — "Will there be a recording?"
- `objection_not_interested` — Disengaging gracefully
- `follow_up` — Single follow-up after no reply
- `booking_confirmation` — Post-payment next steps

### Negative examples (~20%)
About 20% of examples are labeled `"label": "negative"` and **intentionally demonstrate bad behavior** — long walls of text, aggressive sales tactics, fabricated claims, multiple questions at once. These teach the model what NOT to do during fine-tuning.

---

## Using `train.jsonl` for Fine-Tuning

### Option 1: OpenAI Fine-Tuning

The dataset uses a `prompt`/`completion` format compatible with legacy fine-tuning.  
For newer chat-based fine-tuning, convert to `messages` format first.

**Upload using the OpenAI Python SDK:**

```python
from openai import OpenAI

client = OpenAI(api_key="YOUR_OPENAI_API_KEY")

# Upload the training file
with open("train.jsonl", "rb") as f:
    response = client.files.create(file=f, purpose="fine-tune")

file_id = response.id
print(f"Uploaded file ID: {file_id}")

# Start fine-tuning job
job = client.fine_tuning.jobs.create(
    training_file=file_id,
    model="gpt-3.5-turbo",  # or "gpt-4o-mini"
)
print(f"Fine-tune job ID: {job.id}")
```

**Or use the CLI:**

```bash
pip install openai
openai api fine_tunes.create \
  -t train.jsonl \
  -v valid.jsonl \
  -m gpt-3.5-turbo
```

> Note: For chat models (gpt-3.5-turbo, gpt-4o-mini), OpenAI expects messages format with `system`/`user`/`assistant` roles. You may need to split the `prompt` field into a system message and user message at the `\n\n` separator.

---

### Option 2: Hugging Face + Transformers Fine-Tuning

**Install dependencies:**

```bash
pip install transformers datasets accelerate peft
```

**Load dataset and tokenize:**

```python
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer

# Load JSONL datasets
dataset = load_dataset("json", data_files={
    "train": "train.jsonl",
    "validation": "valid.jsonl"
})

# Filter to positive examples only (recommended for supervised fine-tuning)
dataset = dataset.filter(lambda x: x["meta"]["label"] == "positive")

# Load tokenizer
model_name = "mistralai/Mistral-7B-Instruct-v0.2"  # or any suitable base model
tokenizer = AutoTokenizer.from_pretrained(model_name)

def tokenize(example):
    full_text = example["prompt"] + "\n" + example["completion"]
    return tokenizer(full_text, truncation=True, max_length=512, padding="max_length")

tokenized = dataset.map(tokenize, batched=True)
```

**Train with Accelerate:**

```bash
accelerate launch --mixed_precision fp16 train.py \
  --model_name_or_path mistralai/Mistral-7B-Instruct-v0.2 \
  --train_file train.jsonl \
  --validation_file valid.jsonl \
  --output_dir ./arya-fine-tuned \
  --num_train_epochs 3 \
  --per_device_train_batch_size 4 \
  --gradient_accumulation_steps 4 \
  --learning_rate 2e-5 \
  --fp16
```

> Tip: Use **LoRA/PEFT** for memory-efficient fine-tuning on consumer GPUs. See the [PEFT docs](https://huggingface.co/docs/peft).

---

## Running the Validator

```bash
python validate.py train.jsonl
python validate.py valid.jsonl
```

The script checks:
- Every line is valid JSON
- All required keys are present (`prompt`, `completion`, `meta`)
- `prompt` begins with the exact system prompt
- `meta` fields contain only allowed values
- Reports scenario distribution and negative example percentage
- Exits with code `1` if any errors are found

---

## Privacy & Data Notes

- **No real PII**: All messages are simulated. No real phone numbers, email addresses, or personal data are included.
- **Simulated conversations only**: All user messages are fictional, representative examples of common cold-outreach scenarios.
- **Booking link**: The URL `https://rzp.io/rzp/2-hour-live-ai-masterclass` appears in completions as trained. Verify it remains valid before deploying.
- **Negative examples**: ~20% of the dataset demonstrates bad behavior for contrastive learning. Filter these out (`meta.label == "positive"`) if your fine-tuning framework does not support contrastive/DPO-style training.
