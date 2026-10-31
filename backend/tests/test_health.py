from __future__ import annotations

from fastapi.testclient import TestClient


def test_liveness_and_alias(client: TestClient) -> None:
    for path in ("/healthz", "/health"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["service"]


def test_readiness_reports_capabilities(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    # Tests force rules/lexical so readiness must not claim a transformer.
    assert body["nlu"] == "rules-v1"
    assert body["rag"] in {"lexical", "semantic"}
    assert body["queue"] == "inline"
