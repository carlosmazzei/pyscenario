import tracemalloc

pytest_plugins = "pytest_asyncio"


def pytest_configure(config):
    """Configure pytest-tracemalloc."""
    tracemalloc.start()
