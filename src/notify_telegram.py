
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram secrets are not configured; notification skipped.")
        return

    new_file = ROOT / "data" / "new_offers.json"
    offers = json.loads(new_file.read_text(encoding="utf-8")) if new_file.exists() else []
    if not offers:
        print("No new offers; notification skipped.")
        return

    lines = ["🍽️ New Banasree restaurant offer candidates"]
    for offer in offers[:10]:
        lines.append(
            f"\n• {offer['restaurant_name']}\n"
            f"  {offer['title'][:180]}\n"
            f"  Status: {offer['status']} | Source: {offer['source_type']}\n"
            f"  {offer['source_url']}"
        )
    if len(offers) > 10:
        lines.append(f"\n…and {len(offers) - 10} more on the dashboard.")

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        timeout=20,
        json={
            "chat_id": chat_id,
            "text": "\n".join(lines),
            "disable_web_page_preview": True,
        },
    )
    response.raise_for_status()
    print(f"Telegram notification sent for {len(offers)} offer(s).")


if __name__ == "__main__":
    main()
