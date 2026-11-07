"""Outbound safety: real WhatsApp, email and calls leave only from the production instance."""
import os

from kaiku.contact import call as C
from kaiku.contact import email as E
from kaiku.contact import whatsapp as W


def test_localhost_instance_is_silent(monkeypatch):
    monkeypatch.delenv("KAIKU_ALLOW_OUTBOUND", raising=False)
    monkeypatch.setenv("KAIKU_ENV", "/nonexistent/.env")
    monkeypatch.setenv("PUBLIC_URL", "http://127.0.0.1:8299")
    assert W.outbound_allowed() is False


def test_production_url_or_explicit_flag_allows(monkeypatch):
    monkeypatch.setenv("KAIKU_ENV", "/nonexistent/.env")
    monkeypatch.delenv("KAIKU_ALLOW_OUTBOUND", raising=False)
    monkeypatch.setenv("PUBLIC_URL", W.PRODUCTION_URL + "/")
    assert W.outbound_allowed() is True
    monkeypatch.setenv("PUBLIC_URL", "http://127.0.0.1:8299")
    monkeypatch.setenv("KAIKU_ALLOW_OUTBOUND", "1")
    assert W.outbound_allowed() is True


def test_whatsapp_real_transport_blocked_off_production(monkeypatch):
    monkeypatch.setenv("KAIKU_ENV", "/nonexistent/.env")
    monkeypatch.delenv("KAIKU_ALLOW_OUTBOUND", raising=False)
    monkeypatch.setenv("PUBLIC_URL", "http://127.0.0.1:8299")
    c = W.WhatsAppClient(token="TOK", phone_id="123")  # the real httpx transport
    r = c.send_text("+358401234567", "hello")
    assert r["ok"] is False and r.get("blocked") and "outbound disabled" in r["error"]


def test_place_call_disabled_off_production(monkeypatch):
    monkeypatch.setenv("KAIKU_ENV", "/nonexistent/.env")
    monkeypatch.delenv("KAIKU_ALLOW_OUTBOUND", raising=False)
    monkeypatch.delenv("KAIKU_NO_CALL", raising=False)
    monkeypatch.setenv("PUBLIC_URL", "http://127.0.0.1:8299")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "agent_x")
    monkeypatch.setenv("ELEVENLABS_PHONE_NUMBER_ID", "phnum_x")
    monkeypatch.setenv("OWNER_WHATSAPP", "+358401234567")
    r = C.place_call({"id": "sg-guard", "business_id": "furry-paw"})
    assert r["ok"] is False and r["reason"] == "calls disabled on this instance"


def test_place_call_disabled_by_flag_even_on_production(monkeypatch):
    monkeypatch.setenv("KAIKU_ENV", "/nonexistent/.env")
    monkeypatch.setenv("PUBLIC_URL", W.PRODUCTION_URL)
    monkeypatch.setenv("KAIKU_NO_CALL", "1")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "agent_x")
    monkeypatch.setenv("ELEVENLABS_PHONE_NUMBER_ID", "phnum_x")
    monkeypatch.setenv("OWNER_WHATSAPP", "+358401234567")
    r = C.place_call({"id": "sg-guard2", "business_id": "furry-paw"})
    assert r["ok"] is False and r["reason"] == "calls disabled on this instance"


def test_email_dry_run_off_production(monkeypatch):
    monkeypatch.setenv("KAIKU_ENV", "/nonexistent/.env")
    monkeypatch.delenv("KAIKU_ALLOW_OUTBOUND", raising=False)
    monkeypatch.delenv("KAIKU_NO_SMTP", raising=False)
    monkeypatch.setenv("PUBLIC_URL", "http://127.0.0.1:8299")
    monkeypatch.setenv("SMTP_HOST", "smtp.example")
    monkeypatch.setenv("SMTP_FROM", "kaiku@example.test")
    assert E.smtp_config() is None
