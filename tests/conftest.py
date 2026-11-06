import os
import tempfile

import pytest

# Keep tests off the live app state (sqlite, tokens, prefs, clock) before any kaiku module is imported.
os.environ.setdefault("KAIKU_DB", os.path.join(tempfile.mkdtemp(prefix="kaiku-test-"), "t.sqlite"))
os.environ.setdefault("KAIKU_DATA_DIR", tempfile.mkdtemp(prefix="kaiku-data-"))


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
