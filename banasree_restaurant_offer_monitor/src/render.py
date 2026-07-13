
from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
LATEST_FILE = ROOT / "data" / "latest.json"


def empty_data() -> dict:
    return {
        "project_title": "Banasree Restaurant Offer Monitor",
        "area": "Banasree, Dhaka",
        "generated_at": "Not run yet",
        "summary": {
            "sources_total": 0,
            "sources_ok": 0,
            "sources_blocked": 0,
            "sources_failed": 0,
            "offers_detected": 0,
            "needs_review": 0,
            "expired": 0,
            "new_today": 0,
        },
        "offers": [],
        "source_statuses": [],
    }


def main() -> None:
    data = (
        json.loads(LATEST_FILE.read_text(encoding="utf-8"))
        if LATEST_FILE.exists()
        else empty_data()
    )
    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    html = env.get_template("index.html.j2").render(data=data)
    (ROOT / "docs" / "index.html").write_text(html, encoding="utf-8")
    (ROOT / "docs" / "latest.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
