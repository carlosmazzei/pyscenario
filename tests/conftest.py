import tracemalloc


def pytest_configure(config):
    """Configure pytest-tracemalloc."""
    tracemalloc.start()
