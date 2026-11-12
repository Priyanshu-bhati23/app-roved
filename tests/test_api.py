from fastapi.testclient import TestClient

from approved.api import app

from .builders import build_ipa, build_macho

client = TestClient(app)


def upload(data, **params):
    return client.post("/v1/scans", files={"file": ("Demo.ipa", data, "application/octet-stream")}, params=params)


def test_health_and_catalog():
    assert client.get("/healthz").json()["status"] == "ok"
    signals = client.get("/v1/signals").json()
    assert {s["provenance"] for s in signals} == {"OFFICIAL", "COMMUNITY_HEURISTIC", "NOT_PUBLICLY_VERIFIABLE"}


def test_scan_returns_labelled_findings_with_explanations(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = upload(build_ipa(binary=build_macho(signed=False, symbols=("_OBJC_CLASS_$_UIWebView",))))
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "blocked"
    by_id = {f["signal"]["id"]: f for f in body["findings"]}
    assert {"SIGN-001", "MACHO-002"} <= set(by_id)
    for f in body["findings"]:
        assert f["signal"]["provenance"] in {"OFFICIAL", "COMMUNITY_HEURISTIC", "NOT_PUBLICLY_VERIFIABLE"}
        assert f["explanation"]["text"]


def test_scan_without_explanations():
    body = upload(build_ipa(binary=build_macho(signed=False)), explain="false").json()
    assert all(f["explanation"] is None for f in body["findings"])


def test_invalid_upload_is_a_422():
    response = upload(b"not an ipa")
    assert response.status_code == 422 and "zip" in response.json()["detail"]


def test_sdk_threshold_from_environment(monkeypatch):
    monkeypatch.setenv("APPROVED_MIN_SDK", "27.0")
    ids = {f["signal"]["id"] for f in upload(build_ipa()).json()["findings"]}
    assert "PLIST-006" in ids
