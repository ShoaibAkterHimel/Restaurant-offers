
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from common import fetch_page
from parsers import PARSERS

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_FILE = ROOT / "config" / "settings.yml"
SOURCES_FILE = ROOT / "config" / "sources.csv"
LATEST_FILE = ROOT / "data" / "latest.json"
HISTORY_FILE = ROOT / "data" / "offers_history.csv"
SOURCE_HISTORY_FILE = ROOT / "data" / "source_history.csv"
NEW_OFFERS_FILE = ROOT / "data" / "new_offers.json"


def load_previous() -> dict:
    if not LATEST_FILE.exists():
        return {}
    try:
        return json.loads(LATEST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def append_rows(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    settings = yaml.safe_load(SETTINGS_FILE.read_text(encoding="utf-8"))
    timezone = ZoneInfo(settings.get("timezone", "Asia/Dhaka"))
    now = datetime.now(timezone)
    run_at = now.isoformat(timespec="seconds")
    delay = float(settings.get("request_delay_seconds", 1.0))

    previous = load_previous()
    previous_ids = {
        item["offer_id"]
        for item in previous.get("offers", [])
        if item.get("status") != "EXPIRED"
    }

    with SOURCES_FILE.open(encoding="utf-8-sig", newline="") as handle:
        sources = list(csv.DictReader(handle))

    offers = []
    source_statuses = []

    for index, source in enumerate(sources, 1):
        if source.get("active", "yes").strip().lower() not in {"yes", "true", "1"}:
            continue

        source_type = source["source_type"].strip()
        parser = PARSERS.get(source_type)
        status_row = {
            "run_at": run_at,
            "source_id": source["source_id"],
            "restaurant_name": source["restaurant_name"],
            "scope": source["scope"],
            "source_type": source_type,
            "url": source["url"],
            "final_url": "",
            "status": "CHECK FAILED",
            "offers_found": 0,
            "http_status": "",
            "used_browser": False,
            "message": "",
        }

        if not parser:
            status_row["message"] = f"Unknown source_type: {source_type}"
            source_statuses.append(status_row)
            continue

        result = fetch_page(
            source["url"],
            source.get("render_mode", "auto") or "auto",
            delay_seconds=delay,
        )
        status_row["final_url"] = result.url
        status_row["http_status"] = result.status_code or ""
        status_row["used_browser"] = result.used_browser

        if not result.ok:
            status_row["status"] = "BLOCKED" if result.blocked_reason else "CHECK FAILED"
            status_row["message"] = result.error
            source_statuses.append(status_row)
            print(
                f"[{index}/{len(sources)}] {source['source_id']}: "
                f"{status_row['status']} — {result.error}"
            )
            continue

        try:
            discovered = parser(
                result.html, result.visible_text, source, result.url
            )
            for offer in discovered:
                offer["checked_at"] = run_at
                offer["is_new"] = offer["offer_id"] not in previous_ids
            offers.extend(discovered)
            status_row["status"] = "OFFER FOUND" if discovered else "NO OFFER FOUND"
            status_row["offers_found"] = len(discovered)
            status_row["message"] = (
                f"{len(discovered)} candidate offer(s) detected"
                if discovered else
                "Source loaded successfully; no offer signal detected"
            )
        except Exception as exc:
            status_row["status"] = "CHECK FAILED"
            status_row["message"] = f"{type(exc).__name__}: {exc}"

        source_statuses.append(status_row)
        print(
            f"[{index}/{len(sources)}] {source['source_id']}: "
            f"{status_row['status']} ({status_row['offers_found']})"
        )

    # Deduplicate across overlapping Foodpanda and social sources.
    deduped = {}
    for offer in offers:
        current = deduped.get(offer["offer_id"])
        if current is None or offer["confidence"] > current["confidence"]:
            deduped[offer["offer_id"]] = offer
    offers = sorted(
        deduped.values(),
        key=lambda x: (
            not x["is_new"],
            x["status"] != "DETECTED",
            -int(x["confidence"]),
            x["restaurant_name"].lower(),
        ),
    )

    new_offers = [
        x for x in offers
        if x["is_new"] and x["status"] in {"DETECTED", "NEEDS REVIEW"}
    ]

    summary = {
        "sources_total": len(source_statuses),
        "sources_ok": sum(x["status"] in {"OFFER FOUND", "NO OFFER FOUND"} for x in source_statuses),
        "sources_blocked": sum(x["status"] == "BLOCKED" for x in source_statuses),
        "sources_failed": sum(x["status"] == "CHECK FAILED" for x in source_statuses),
        "offers_detected": sum(x["status"] == "DETECTED" for x in offers),
        "needs_review": sum(x["status"] == "NEEDS REVIEW" for x in offers),
        "expired": sum(x["status"] == "EXPIRED" for x in offers),
        "new_today": len(new_offers),
    }

    payload = {
        "project_title": settings["project_title"],
        "area": settings["area"],
        "generated_at": run_at,
        "summary": summary,
        "offers": offers,
        "source_statuses": source_statuses,
    }

    LATEST_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    NEW_OFFERS_FILE.write_text(
        json.dumps(new_offers, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    offer_history_rows = []
    for offer in offers:
        row = {"run_at": run_at}
        row.update(offer)
        row["is_new"] = str(offer["is_new"]).lower()
        offer_history_rows.append(row)

    append_rows(
        HISTORY_FILE,
        [
            "run_at", "offer_id", "restaurant_name", "scope", "title",
            "description", "offer_type", "confidence", "status",
            "expiry_date", "promo_code", "conditions", "source_id",
            "source_type", "source_url", "checked_at", "is_new",
        ],
        offer_history_rows,
    )
    append_rows(
        SOURCE_HISTORY_FILE,
        [
            "run_at", "source_id", "restaurant_name", "scope", "source_type",
            "url", "final_url", "status", "offers_found", "http_status",
            "used_browser", "message",
        ],
        source_statuses,
    )


if __name__ == "__main__":
    main()
