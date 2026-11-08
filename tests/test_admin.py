import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def c():
    from kaiku.app import app  # imported lazily: settings are read at import, test_core sets its env first
    return TestClient(app)


def test_admin_needs_key(c):
    assert c.get("/admin").status_code == 403
    assert c.get("/admin?key=wrong").status_code == 403


def test_admin_hub_with_key(c):
    r = c.get("/admin", headers={"x-kaiku-key": "testkey"})
    assert r.status_code == 200
    h = r.text
    for s in ("FIWARE in three sentences", "Aura", "The city twin", "The room",
              'href="/aura"', 'href="/city"', 'href="/room"', 'href="/fiware"', 'id="dc-email"', 'id="run"'):
        assert s in h, s
    assert "<iframe" not in h
    assert "testkey" not in h


def test_admin_key_only_in_keyed_hrefs(c):
    r = c.get("/admin?key=testkey")
    assert r.status_code == 200
    assert r.text.count("testkey") == 2
    assert "/judge?key=testkey" in r.text and "/console?key=testkey" in r.text
