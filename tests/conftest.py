import os
import tempfile

import pytest

# Keep tests off the live app state (sqlite, tokens, prefs, clock) before any kaiku module is imported.
os.environ.setdefault("KAIKU_DB", os.path.join(tempfile.mkdtemp(prefix="kaiku-test-"), "t.sqlite"))
os.environ["KAIKU_ROOM_KEY"] = "testkey"
os.environ.setdefault("KAIKU_DATA_DIR", tempfile.mkdtemp(prefix="kaiku-data-"))


@pytest.fixture(autouse=True)
def _never_send_mail(monkeypatch):
    """The suite never sends email and the live .env never steers a test (KAIKU_LIVE=1 lifts this)."""
    if os.environ.get("KAIKU_LIVE") == "1":
        return
    monkeypatch.setenv("KAIKU_NO_SMTP", "1")
    monkeypatch.setenv("KAIKU_FEED_NETWORK", "0")  # the suggestions engine never fetches websites during tests
    monkeypatch.setenv("KAIKU_NO_CALL", "1")  # no test ever dials the owner
    for k in ("SMTP_HOST", "SMTP_FROM", "SMTP_USER", "SMTP_PASS", "OWNER_EMAIL", "ELEVENLABS_API_KEY", "WA_TOKEN", "WA_PHONE_ID",
              "KAIKU_REVIEW_CARDS"):  # the live .env caps review cards for the demo; tests use the engine default
        monkeypatch.delenv(k, raising=False)


def pytest_configure(config):
    config.addinivalue_line("markers", "live: hits a real external service (Yext, Orion, Meta, Nager); skipped unless KAIKU_LIVE=1")
    config.addinivalue_line("markers", "network: needs the network; skipped unless KAIKU_LIVE=1")


def pytest_collection_modifyitems(config, items):
    """Default run is offline and fast. KAIKU_LIVE=1 runs everything, including tests that touch Orion/Yext/Meta/Nager."""
    if os.environ.get("KAIKU_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="live/network test, set KAIKU_LIVE=1 to run")
    for it in items:
        if "live" in it.keywords or "network" in it.keywords:
            it.add_marker(skip)
