"""HTTP API: upload an IPA, get a labelled compliance report."""

from __future__ import annotations

import os

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from . import __version__, ipa, llm, rag
from .catalog import Report, Signal, load_catalog
from .checks import Settings
from .engine import analyze

MAX_UPLOAD_BYTES = int(os.getenv("APPROVED_MAX_UPLOAD_MB", "500")) * 1024 * 1024
CHUNK = 1024 * 1024

app = FastAPI(
    title="App-roved",
    version=__version__,
    description="Static App Store compliance checks for iOS builds. Every finding carries a provenance label.",
)


def _settings() -> Settings:
    return Settings(
        min_sdk=os.getenv("APPROVED_MIN_SDK", Settings.min_sdk),
        min_deployment_target=os.getenv("APPROVED_MIN_DEPLOYMENT_TARGET", Settings.min_deployment_target),
    )


@app.get("/healthz")
def health() -> dict:
    return {"status": "ok", "version": __version__, "signals": len(load_catalog())}


@app.get("/v1/signals", response_model=list[Signal])
def signals() -> list[Signal]:
    """The full catalog - everything this service is able to report."""
    return list(load_catalog())


@app.post("/v1/scans", response_model=Report)
def scan(
    file: UploadFile = File(..., description="The .ipa to analyse"),
    explain: bool = Query(True, description="Attach a grounded explanation to every finding"),
) -> Report:
    # Read in bounded chunks so an oversized upload is rejected before it is buffered whole.
    buffer = bytearray()
    while chunk := file.file.read(CHUNK):
        buffer.extend(chunk)
        if len(buffer) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "IPA exceeds the maximum upload size")
    try:
        bundle = ipa.load(bytes(buffer))
    except ipa.IPAError as exc:
        raise HTTPException(422, str(exc)) from exc
    report = analyze(bundle, _settings())
    return rag.explain_report(report, llm.from_env()) if explain else report
