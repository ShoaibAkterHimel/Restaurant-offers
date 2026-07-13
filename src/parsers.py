
from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import clean_space, fingerprint, normalize_url

STRONG_PATTERNS = [
    (r"\b\d{1,2}\s*%\s*(?:off|discount|savings?)\b", "Percentage discount", 5),
    (r"\b(?:off|discount|save)\s*\d{1,2}\s*%\b", "Percentage discount", 5),
    (r"\bbuy\s*\d+\s*(?:get|&)\s*\d+\b", "Buy/get offer", 6),
    (r"\bbogo\b", "BOGO", 6),
    (r"\bcash\s*back\b|\bcashback\b", "Cashback", 5),
    (r"\bfree\s+delivery\b", "Free delivery", 4),
    (r"\bpromo\s*code\b|\bvoucher\b", "Promo/voucher", 4),
    (r"\bapp[- ]only\s+deals?\b", "App-only deal", 4),
    (r"\bcombo\s+offer\b|\bfamily\s+combo\b", "Combo offer", 4),
    (r"\b\d{1,2}\s*%\s*(?:ছাড়|ডিসকাউন্ট)\b", "শতাংশ ছাড়", 5),
    (r"একটি\s+কিনলে\s+একটি\s+ফ্রি", "একটি কিনলে একটি ফ্রি", 6),
    (r"ফ্রি\s+ডেলিভারি", "ফ্রি ডেলিভারি", 4),
    (r"ক্যাশব্যাক", "ক্যাশব্যাক", 5),
]

WEAK_PATTERNS = [
    (r"\bspecial\s+offer\b|\blimited[- ]time\s+offer\b", "Special offer", 3),
    (r"\bdeal\b|\bdeals\b|\boffer\b|\bdiscount\b", "Offer mention", 2),
    (r"\bset\s*menu\b|\bplatter\b", "Set menu/platter", 2),
    (r"বিশেষ\s+অফার|অফার|ছাড়|ডিসকাউন্ট", "অফার উল্লেখ", 2),
]

CONDITION_PATTERNS = [
    r"\bminimum\s+(?:order|spend|purchase)\b[^.;|]{0,80}",
    r"\b(?:dine[- ]in|takeaway|delivery)\s+only\b",
    r"\b(?:friday|saturday|sunday|monday|tuesday|wednesday|thursday)s?\b[^.;|]{0,80}",
    r"\b(?:valid|available)\s+(?:from|until|till|through)\b[^.;|]{0,100}",
    r"\bapp[- ]only\b",
]

PROMO_CODE_PATTERNS = [
    r"(?:promo\s*code|voucher\s*code|code)\s*[:\-]?\s*([A-Z0-9_-]{4,20})",
    r"\b([A-Z]{3,}[0-9]{2,}[A-Z0-9_-]*)\b",
]

DATE_PHRASE = re.compile(
    r"(?:valid\s+(?:until|till|through)|expires?|ending|ends?)\s*[:\-]?\s*"
    r"("
    r"[A-Za-z]{3,9}\s+\d{1,2}(?:,\s*\d{4})?"
    r"|\d{1,2}\s+[A-Za-z]{3,9}(?:\s+\d{4})?"
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r")",
    re.I,
)

LOGIN_NOISE = {
    "log in", "sign up", "create new account", "forgotten password",
    "messenger", "meta pay", "privacy center",
}


def offer_score(text: str) -> tuple[int, str]:
    lower = clean_space(text).lower()
    best_score = 0
    best_type = ""
    for pattern, label, score in STRONG_PATTERNS + WEAK_PATTERNS:
        if re.search(pattern, lower, flags=re.I):
            if score > best_score:
                best_score = score
                best_type = label
    if "banasree" in lower or "বনশ্রী" in lower:
        best_score += 1
    if re.search(r"(?:tk|৳|bdt)\s*\.?\s*\d+", lower, flags=re.I):
        best_score += 1
    if re.search(r"\b(?:today|limited time|valid till|valid until|expires)\b", lower):
        best_score += 1
    return best_score, best_type


def useful_segments(text: str) -> list[str]:
    # Browser innerText can arrive as one long line, so split on both visible
    # line separators and punctuation while retaining compact offer statements.
    raw = re.split(r"[\r\n]+|(?<=[.!?।])\s+", text)
    output = []
    for part in raw:
        part = clean_space(part)
        if 5 <= len(part) <= 700:
            output.append(part)
    return output


def surrounding_snippet(text: str, match_start: int, max_len: int = 360) -> str:
    left = max(0, match_start - max_len // 2)
    right = min(len(text), match_start + max_len // 2)
    return clean_space(text[left:right]).strip(" -|,;")


def extract_expiry(text: str) -> str:
    match = DATE_PHRASE.search(text)
    if not match:
        return ""
    raw = clean_space(match.group(1))
    formats = (
        "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y",
        "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass

    # Month/day without a year: assume the next occurrence, not a past one.
    for fmt in ("%d %B", "%d %b", "%B %d", "%b %d"):
        try:
            partial = datetime.strptime(raw.replace(",", ""), fmt)
            today = date.today()
            candidate = date(today.year, partial.month, partial.day)
            if candidate < today:
                candidate = date(today.year + 1, partial.month, partial.day)
            return candidate.isoformat()
        except ValueError:
            pass
    return ""


def extract_promo_code(text: str) -> str:
    for pattern in PROMO_CODE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            value = match.group(1).upper()
            if value not in {"BDT", "APP", "OFF", "GET"}:
                return value
    return ""


def extract_conditions(text: str) -> str:
    found = []
    for pattern in CONDITION_PATTERNS:
        match = re.search(pattern, text, flags=re.I)
        if match:
            found.append(clean_space(match.group(0)))
    return " | ".join(dict.fromkeys(found))


def make_offer(
    restaurant_name: str,
    scope: str,
    title: str,
    snippet: str,
    offer_type: str,
    confidence: int,
    source_id: str,
    source_type: str,
    source_url: str,
) -> dict:
    expiry = extract_expiry(snippet)
    today = date.today().isoformat()
    if expiry and expiry < today:
        status = "EXPIRED"
    elif confidence >= 4:
        status = "DETECTED"
    else:
        status = "NEEDS REVIEW"

    canonical = re.sub(
        r"\b(?:today|tomorrow|valid|until|till|expires?|ending|ends?)\b.*$",
        "",
        snippet.lower(),
        flags=re.I,
    )
    return {
        "offer_id": fingerprint(restaurant_name, offer_type, canonical[:220]),
        "restaurant_name": restaurant_name,
        "scope": scope,
        "title": clean_space(title)[:180],
        "description": clean_space(snippet)[:500],
        "offer_type": offer_type,
        "confidence": confidence,
        "status": status,
        "expiry_date": expiry,
        "promo_code": extract_promo_code(snippet),
        "conditions": extract_conditions(snippet),
        "source_id": source_id,
        "source_type": source_type,
        "source_url": source_url,
    }


def extract_generic_offers(
    text: str,
    restaurant_name: str,
    scope: str,
    source_id: str,
    source_type: str,
    source_url: str,
    minimum_confidence: int = 2,
) -> list[dict]:
    offers = []
    seen = set()
    segments = useful_segments(text)

    for segment in segments:
        lower = segment.lower()
        if lower in LOGIN_NOISE:
            continue
        score, offer_type = offer_score(segment)
        if score < minimum_confidence:
            continue

        # A weak generic word alone is not useful.
        if score <= 2 and len(segment) > 240:
            continue

        key = fingerprint(restaurant_name, segment[:240])
        if key in seen:
            continue
        seen.add(key)

        title = segment
        if len(title) > 120:
            for pattern, _, _ in STRONG_PATTERNS + WEAK_PATTERNS:
                match = re.search(pattern, segment, flags=re.I)
                if match:
                    title = surrounding_snippet(segment, match.start(), 150)
                    break

        position = text.find(segment)
        context = (
            surrounding_snippet(text, position + len(segment) // 2, 520)
            if position >= 0 else segment
        )
        offers.append(make_offer(
            restaurant_name=restaurant_name,
            scope=scope,
            title=title,
            snippet=context,
            offer_type=offer_type or "Offer",
            confidence=score,
            source_id=source_id,
            source_type=source_type,
            source_url=source_url,
        ))

    return offers[:40]


def _nearest_card_text(anchor) -> str:
    best = clean_space(anchor.get_text(" ", strip=True))
    node = anchor
    for _ in range(5):
        node = node.parent
        if node is None:
            break
        text = clean_space(node.get_text(" ", strip=True))
        if len(text) > 1600:
            break
        score, _ = offer_score(text)
        if score >= 2 and len(text) > len(best):
            best = text
    return best


def _restaurant_name_from_anchor(anchor) -> str:
    for selector in ("h1", "h2", "h3", "h4", "[data-testid*='name']"):
        found = anchor.select_one(selector)
        if found:
            value = clean_space(found.get_text(" ", strip=True))
            if 2 < len(value) < 120:
                return value
    text = clean_space(anchor.get_text(" ", strip=True))
    # Remove common badges from the first visible line.
    parts = re.split(
        r"(?:\bCuisines\b|\bFree Delivery\b|\b\d{1,2}%\s*off\b|\bRated\b)",
        text,
        maxsplit=1,
        flags=re.I,
    )
    return clean_space(parts[0])[:120] or "Foodpanda restaurant"


def parse_foodpanda_area(html: str, visible_text: str, source: dict, final_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    offers = []
    seen_links = set()

    for anchor in soup.select("a[href*='/restaurant/']"):
        href = normalize_url(anchor.get("href", ""), final_url)
        if not href or href in seen_links:
            continue
        seen_links.add(href)
        card_text = _nearest_card_text(anchor)
        score, _ = offer_score(card_text)
        if score < 2:
            continue
        restaurant = _restaurant_name_from_anchor(anchor)
        offers.extend(extract_generic_offers(
            card_text,
            restaurant,
            source["scope"],
            source["source_id"],
            source["source_type"],
            href,
            minimum_confidence=2,
        ))

    # Fallback: retain area-level offers even when card markup changes.
    if not offers:
        offers = extract_generic_offers(
            visible_text,
            source["restaurant_name"],
            source["scope"],
            source["source_id"],
            source["source_type"],
            final_url,
            minimum_confidence=4,
        )
    return offers


def parse_foodpanda_vendor(html: str, visible_text: str, source: dict, final_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    restaurant = source["restaurant_name"]
    h1 = soup.find("h1")
    if h1:
        candidate = clean_space(h1.get_text(" ", strip=True))
        if candidate:
            restaurant = candidate
    return extract_generic_offers(
        visible_text,
        restaurant,
        source["scope"],
        source["source_id"],
        source["source_type"],
        final_url,
        minimum_confidence=2,
    )


def parse_social(html: str, visible_text: str, source: dict, final_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    pieces = []
    for attrs in [
        {"property": "og:title"},
        {"property": "og:description"},
        {"name": "description"},
        {"name": "twitter:description"},
    ]:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            pieces.append(clean_space(tag["content"]))
    pieces.append(visible_text)
    combined = "\n".join(dict.fromkeys(x for x in pieces if x))
    return extract_generic_offers(
        combined,
        source["restaurant_name"],
        source["scope"],
        source["source_id"],
        source["source_type"],
        final_url,
        minimum_confidence=2,
    )


def parse_website(html: str, visible_text: str, source: dict, final_url: str) -> list[dict]:
    return extract_generic_offers(
        visible_text,
        source["restaurant_name"],
        source["scope"],
        source["source_id"],
        source["source_type"],
        final_url,
        minimum_confidence=2,
    )


PARSERS = {
    "foodpanda_area": parse_foodpanda_area,
    "foodpanda_vendor": parse_foodpanda_vendor,
    "social_public": parse_social,
    "website": parse_website,
}
