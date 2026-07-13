
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from parsers import extract_generic_offers, extract_expiry, offer_score


SOURCE_ARGS = {
    "restaurant_name": "Example Banasree Restaurant",
    "scope": "Banasree branch",
    "source_id": "example",
    "source_type": "website",
    "source_url": "https://example.com/offers",
}


def extract(text):
    return extract_generic_offers(
        text=text,
        minimum_confidence=2,
        **SOURCE_ARGS,
    )


def test_percentage_discount():
    offers = extract("Enjoy 20% off on all burgers. Valid until 31 December 2026.")
    assert offers
    assert offers[0]["status"] == "DETECTED"
    assert offers[0]["offer_type"] == "Percentage discount"


def test_buy_one_get_one():
    offers = extract("Buy 1 Get 1 free pizza every Tuesday.")
    assert offers
    assert offers[0]["confidence"] >= 6


def test_bangla_offer():
    offers = extract("আজ বনশ্রী শাখায় ১৫% ডিসকাউন্ট।")
    assert offers
    assert offers[0]["status"] == "DETECTED"


def test_expiry_date():
    assert extract_expiry("Offer valid until 31 December 2026") == "2026-12-31"


def test_regular_menu_is_not_offer():
    offers = extract("Chicken burger Tk 250. Beef burger Tk 300.")
    assert offers == []
