FROM python:3.11-slim

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R app:app /app
USER app

EXPOSE 8000

# A single worker on purpose. Each worker is its own process, so with two of
# them the follow-up scheduler ran twice and every contact got two identical
# follow-ups at the same moment; the in-process de-duplication of incoming
# messages is likewise only global while there is one process. The gateway
# drives a single WhatsApp session, so one worker is ample.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
