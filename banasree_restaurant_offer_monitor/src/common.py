
from __future__ import annotations

import hashlib
import re
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Banasree-Offer-Monitor/1.0 "
    "(personal non-commercial offer checker; contact repository owner)"
)
DEFAULT_TIMEOUT = 30
_last_request: dict[str, float] = {}


@dataclass
class FetchResult:
    ok: bool
    url: str
    status_code: int | None
    content_type: str
    html: str
    visible_text: str
    error: str = ""
    used_browser: bool = False
    blocked_reason: str = ""


def clean_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_url(value: str, base: str = "") -> str:
    value = clean_space(value)
    if not value:
        return ""
    if value.startswith("www."):
        value = "https://" + value
    if base:
        value = urljoin(base, value)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return ""
    return parsed._replace(fragment="").geturl()


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return clean_space(soup.get_text(" ", strip=True))


def fingerprint(*parts: str) -> str:
    normalized = "|".join(
        re.sub(r"[^a-z0-9\u0980-\u09ff]+", " ", clean_space(x).lower())
        for x in parts
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def robots_allowed(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(USER_AGENT, url), robots_url
    except Exception:
        # An unreachable robots file is not interpreted as a prohibition.
        return True, robots_url


def polite_pause(url: str, delay_seconds: float = 1.0) -> None:
    domain = urlparse(url).netloc.lower()
    elapsed = time.monotonic() - _last_request.get(domain, 0.0)
    if elapsed < delay_seconds:
        time.sleep(delay_seconds - elapsed)
    _last_request[domain] = time.monotonic()


def detect_access_wall(text: str, url: str) -> str:
    lower = clean_space(text).lower()
    domain = urlparse(url).netloc.lower()
    if "facebook.com" in domain:
        patterns = (
            "log in to facebook", "you must log in", "create new account",
            "see more on facebook", "content isn't available",
        )
        if any(x in lower for x in patterns) and len(lower) < 2500:
            return "Facebook login or access wall"
    if "instagram.com" in domain:
        patterns = (
            "log in to instagram", "sign up to see photos",
            "create an account or log in", "page isn't available",
        )
        if any(x in lower for x in patterns) and len(lower) < 2500:
            return "Instagram login or access wall"
    if "captcha" in lower or "verify you are human" in lower:
        return "CAPTCHA or human verification"
    return ""


def fetch_requests(url: str, delay_seconds: float = 1.0) -> FetchResult:
    allowed, robots_url = robots_allowed(url)
    if not allowed:
        return FetchResult(
            False, url, None, "", "", "",
            error=f"Blocked by robots.txt: {robots_url}",
            blocked_reason="robots.txt",
        )

    polite_pause(url, delay_seconds)
    try:
        response = requests.get(
            url,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9,bn;q=0.8",
            },
        )
        content_type = response.headers.get("content-type", "").lower()
        html = response.text
        visible = html_to_text(html) if "html" in content_type or "<html" in html[:1000].lower() else clean_space(html)
        wall = detect_access_wall(visible, response.url)
        if response.status_code >= 400:
            return FetchResult(
                False, response.url, response.status_code, content_type,
                html, visible, error=f"HTTP {response.status_code}",
                blocked_reason=wall,
            )
        return FetchResult(
            not bool(wall), response.url, response.status_code, content_type,
            html, visible,
            error=wall,
            blocked_reason=wall,
        )
    except Exception as exc:
        return FetchResult(
            False, url, None, "", "", "",
            error=f"{type(exc).__name__}: {exc}",
        )


def fetch_browser(url: str, delay_seconds: float = 1.0) -> FetchResult:
    allowed, robots_url = robots_allowed(url)
    if not allowed:
        return FetchResult(
            False, url, None, "", "", "",
            error=f"Blocked by robots.txt: {robots_url}",
            used_browser=True,
            blocked_reason="robots.txt",
        )

    polite_pause(url, delay_seconds)
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=USER_AGENT,
                locale="en-US",
                viewport={"width": 1365, "height": 1600},
            )
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass

            html = page.content()
            visible = clean_space(page.locator("body").inner_text(timeout=10_000))
            final_url = page.url
            status = response.status if response else None
            context.close()
            browser.close()

        wall = detect_access_wall(visible, final_url)
        ok_status = status is None or status < 400
        return FetchResult(
            ok=ok_status and not bool(wall),
            url=final_url,
            status_code=status,
            content_type="text/html",
            html=html,
            visible_text=visible,
            error=wall if wall else ("" if ok_status else f"HTTP {status}"),
            used_browser=True,
            blocked_reason=wall,
        )
    except Exception as exc:
        return FetchResult(
            False, url, None, "", "", "",
            error=f"{type(exc).__name__}: {exc}",
            used_browser=True,
        )


def fetch_page(url: str, render_mode: str, delay_seconds: float = 1.0) -> FetchResult:
    if render_mode == "browser":
        return fetch_browser(url, delay_seconds)

    result = fetch_requests(url, delay_seconds)
    if render_mode == "requests" or not result.ok:
        return result

    # Browser fallback for JavaScript shells.
    if len(result.visible_text) < 250:
        browser_result = fetch_browser(url, delay_seconds)
        if browser_result.ok or browser_result.blocked_reason:
            return browser_result
    return result
