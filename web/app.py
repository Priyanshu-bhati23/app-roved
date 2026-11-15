"""The hosted App-roved site: landing page, free scan, sample scan and paid-review orders.

Everything business-specific is configured with environment variables, so the open-source
engine stays generic:

    CONTACT_EMAIL       shown on the page and used as the fallback for orders
    ORDER_WEBHOOK_URL   Discord or Slack incoming webhook that receives each order
    PAY_URL_REVIEW      payment link for the pre-submission review (optional)
    PAY_URL_RESCUE      payment link for the rejection rescue (optional)
    PRICE_REVIEW        display price, default "$29"
    PRICE_RESCUE        display price, default "$79"
    LAUNCH_NOTE         one line shown above the pricing cards (optional)
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Literal

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field, field_validator

from approved import ipa, llm, rag
from approved.api import _settings, app
from approved.catalog import Report
from approved.engine import analyze

log = logging.getLogger("approved.web")
STATIC = Path(__file__).resolve().parent / "static"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def config() -> dict[str, str]:
    return {
        "contact_email": os.getenv("CONTACT_EMAIL", ""),
        "price_review": os.getenv("PRICE_REVIEW", "$29"),
        "price_rescue": os.getenv("PRICE_RESCUE", "$79"),
        "launch_note": os.getenv("LAUNCH_NOTE", ""),
        "orders_open": "1" if os.getenv("ORDER_WEBHOOK_URL") else "",
    }


def testimonials() -> list[dict]:
    """Real quotes from real people, with their permission, in static/testimonials.json."""
    try:
        items = json.loads((STATIC / "testimonials.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    keep = ("name", "role", "quote")
    return [{k: str(t.get(k, ""))[:400] for k in keep} for t in items if isinstance(t, dict) and t.get("quote")]


# --- pages -----------------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def page() -> str:
    cfg = config()
    text = (STATIC / "index.html").read_text(encoding="utf-8")
    data = dict(cfg, testimonials=testimonials())
    text = text.replace("{{CONFIG_JSON}}", json.dumps(data).replace("<", "\\u003c"))
    for key, value in cfg.items():
        text = text.replace("{{" + key.upper() + "}}", html.escape(value))
    return text


SCRIPTS = ("slim.js", "phone3d.js", "theater.js", "mascot.js", "bg3d.js", "site3d.js")


@app.get("/{name}.js", include_in_schema=False)
def script(name: str) -> Response:
    if name + ".js" not in SCRIPTS:
        raise HTTPException(404)
    return Response((STATIC / (name + ".js")).read_bytes(), media_type="text/javascript")


ICONS = ("og.png", "icon-192.png", "icon-512.png", "apple-touch-icon.png")

MANIFEST = {
    "name": "App-roved",
    "short_name": "App-roved",
    "description": "Catch App Store rejections before you submit.",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#07080f",
    "theme_color": "#07080f",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ],
}


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest() -> Response:
    return Response(json.dumps(MANIFEST), media_type="application/manifest+json")


@app.get("/{name}.png", include_in_schema=False)
def image(name: str) -> Response:
    path = STATIC / (name + ".png")
    if name + ".png" not in ICONS or not path.exists():
        raise HTTPException(404)
    return Response(path.read_bytes(), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/robots.txt", include_in_schema=False)
def robots() -> PlainTextResponse:
    return PlainTextResponse("User-agent: *\nAllow: /\n")


# --- sample scan -------------------------------------------------------------------------------


def _sample_ipa() -> bytes:
    from tests.builders import GOOD_INFO, build_ipa, build_macho  # the same builder the test suite uses

    info = dict(GOOD_INFO, NSAppTransportSecurity={"NSAllowsArbitraryLoads": True}, NSCameraUsageDescription="")
    binary = build_macho(
        sdk=(18, 2, 0),
        symbols=("_stat", "_OBJC_CLASS_$_NSUserDefaults", "_OBJC_CLASS_$_CLLocationManager"),
        entitlements={"get-task-allow": True},
    )
    return build_ipa(info=info, binary=binary)


@app.post("/v1/demo-scan", response_model=Report, include_in_schema=False)
def demo_scan() -> Report:
    return rag.explain_report(analyze(ipa.load(_sample_ipa()), _settings()), llm.from_env())


# --- orders ------------------------------------------------------------------------------------

PLANS = {"review": "Pre-submission review", "rescue": "Rejection rescue"}


class Order(BaseModel):
    plan: Literal["review", "rescue"]
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=200)
    app_name: str = Field(default="", max_length=200)
    app_link: str = Field(default="", max_length=500)
    rejection: str = Field(default="", max_length=4000)
    notes: str = Field(default="", max_length=2000)
    scan_summary: str = Field(default="", max_length=3000)
    website: str = Field(default="", max_length=200)  # honeypot: people never see this field

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip()
        if not EMAIL_RE.match(value):
            raise ValueError("enter a valid email address")
        return value


_recent: dict[str, deque] = {}
MAX_ORDERS_PER_HOUR = 5


def _throttled(ip: str) -> bool:
    now = time.time()
    hits = _recent.setdefault(ip, deque())
    while hits and now - hits[0] > 3600:
        hits.popleft()
    hits.append(now)
    return len(hits) > MAX_ORDERS_PER_HOUR


def format_order(order: Order) -> str:
    def line(label: str, value: str) -> str:
        return f"**{label}:** {value.strip()}\n" if value.strip() else ""

    price = config()["price_" + order.plan]
    text = (
        f"New order: {PLANS[order.plan]} ({price})\n"
        + line("Name", order.name)
        + line("Email", order.email)
        + line("App", order.app_name)
        + line("Link", order.app_link)
        + line("Rejection message", order.rejection)
        + line("Notes", order.notes)
        + line("Scan", order.scan_summary)
    )
    return text[:1990]


@app.post("/v1/orders", include_in_schema=False)
def create_order(order: Order, request: Request) -> dict:
    if order.website:  # a bot filled the hidden field; pretend it worked
        return {"ok": True, "pay_url": ""}
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0]
    if _throttled(ip):
        raise HTTPException(429, "Too many requests. Please email us instead.")
    webhook = os.getenv("ORDER_WEBHOOK_URL", "")
    contact = os.getenv("CONTACT_EMAIL", "")
    if not webhook:
        raise HTTPException(503, f"Online orders are not open yet. Please email {contact or 'us'}.")
    text = format_order(order)
    payload = {"text": text} if "hooks.slack.com" in webhook else {"content": text, "allowed_mentions": {"parse": []}}
    try:
        httpx.post(webhook, json=payload, timeout=10).raise_for_status()
    except httpx.HTTPError as exc:
        log.error("order webhook failed: %s", exc)
        raise HTTPException(502, f"Couldn't send your request. Please email {contact or 'us'}.") from exc
    return {"ok": True, "pay_url": os.getenv("PAY_URL_" + order.plan.upper(), "")}
