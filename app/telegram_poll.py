"""
PM AI Signal Tracker — Telegram Polling Loop
============================================
Polls the Telegram bot for new messages and publishes them as on-demand
queries to the ADK agent's Pub/Sub trigger endpoint.

Run in a second terminal alongside `uv run adk web --trigger_sources pubsub`:

  uv run python app/telegram_poll.py

On-demand flow:
  You message bot → this script picks it up → POSTs to /apps/app/trigger/pubsub
  → agent processes as 'query' → query_formatter replies to Telegram
"""

from __future__ import annotations

import base64
import json
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
PUBSUB_ENDPOINT = "http://localhost:8000/apps/app/trigger/pubsub"
POLL_INTERVAL = 5  # seconds


def get_updates(offset: int) -> list:
    """Fetch new Telegram messages since offset."""
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
            params={"offset": offset, "timeout": 5},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])
    except Exception as e:
        print(f"[poll] getUpdates error: {e}")
        return []


def publish_query(question: str) -> None:
    """Wrap question as Pub/Sub message and POST to agent endpoint."""
    payload = json.dumps({"trigger": "query", "question": question})
    encoded = base64.b64encode(payload.encode()).decode()

    envelope = {
        "message": {
            "data": encoded,
            "subscription": "projects/local/subscriptions/telegram-query",
        }
    }

    try:
        resp = requests.post(
            PUBSUB_ENDPOINT,
            json=envelope,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        print(f"[poll] Published query → {resp.status_code}")
    except Exception as e:
        print(f"[poll] Failed to publish: {e}")


def main() -> None:
    if not TELEGRAM_TOKEN:
        print("[poll] TELEGRAM_BOT_TOKEN not set. Exiting.")
        return

    print(f"[poll] Starting Telegram polling → {PUBSUB_ENDPOINT}")
    offset = 0

    while True:
        updates = get_updates(offset)

        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message", {})
            text = message.get("text", "").strip()

            # Only process messages from your own chat
            chat_id = str(message.get("chat", {}).get("id", ""))
            if chat_id != TELEGRAM_CHAT_ID:
                print(f"[poll] Ignoring message from unknown chat {chat_id}")
                continue

            # Skip bot commands
            if not text or text.startswith("/"):
                continue

            print(f"[poll] Received: {text[:80]}")
            publish_query(text)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
