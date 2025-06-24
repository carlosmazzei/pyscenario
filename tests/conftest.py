import tracemalloc

import pytest


@pytest.fixture
def event_loop(function_event_loop):
    """Provide event_loop fixture compatible with pytest-asyncio>=1."""
    yield function_event_loop


pytest_plugins = "pytest_asyncio"


def pytest_configure(config):
    """Configure pytest-tracemalloc."""
    tracemalloc.start()
