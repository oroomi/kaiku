import pytest


@pytest.fixture(scope="module")
def client():
    # imported lazily so other test modules set their env (DB path, owner phone) before the app loads
    from fastapi.testclient import TestClient

    from kaiku.app import app
    return TestClient(app)


def test_landing_page(client):
    r = client.get("/")
    assert r.status_code == 200
    h = r.text
    for want in ("We reach you where you are", "one tap", 'href="/owner"', "https://youtu.be/Opg_gzlo_II", 'href="/fiware"'):
        assert want in h
    assert "Welcome to" not in h


def test_owner_page_still_there(client):
    assert 'data-pilot="hero"' in client.get("/owner").text


def test_landing_css(client):
    assert client.get("/static/landing/landing.css").status_code == 200
