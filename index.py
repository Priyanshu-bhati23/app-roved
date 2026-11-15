"""Vercel entry point for the hosted App-roved site.

Vercel limits a request body to about 4.5 MB, so the page trims each .ipa in the browser
(web/static/slim.js) and uploads only what the checks read. See web/app.py for the routes
and the environment variables that configure orders and pricing.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("APPROVED_MAX_UPLOAD_MB", "4")

from web.app import app  # noqa: E402

__all__ = ["app"]
