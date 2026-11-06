def pytest_configure(config):
    config.addinivalue_line("markers", "live: hits the real Yext sandbox (needs YEXT_API_KEY)")
