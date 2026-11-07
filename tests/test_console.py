import re

import pytest
from fastapi.testclient import TestClient

from kaiku import demo_contact
from kaiku.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_refused_without_key(client):
    r = client.get("/console")
    assert r.status_code == 403
    assert "Run the chain" not in r.text
    assert client.get("/console?key=wrong").status_code == 403


def test_page_with_key(client):
    r = client.get("/console?key=testkey")
    assert r.status_code == 200
    for s in ("WHO KAIKU REACHES", "THE CUSTOMER WE WERE GIVEN", "Furry Paw Vet Clinic, Vantaa. Fonecta sandbox entity SinceAI07, fictional.",
              "ON FONECTA NOW", "Run the chain", "Reset demo", "+1 555 188 5173", "Meta test app", "Last call:"):
        assert s in r.text
    assert "—" not in r.text


def test_no_full_phone_or_email(client):
    demo_contact.save("visitor@example.com", "+358401234567")
    try:
        html = client.get("/console?key=testkey").text
        assert "visitor@example.com" not in html and "+358401234567" not in html and "358401234567" not in html
        assert not re.search(r"\+\d{9,}", html)
        assert not re.search(r"[\w.]+@[\w.]+\.\w+", html.replace("name@company.fi", ""))
    finally:
        demo_contact.clear()
