import time
from typing import Callable, Any


def wait_for(predicate: Callable[[], bool], timeout: float = 5.0, interval: float = 0.1) -> bool:
    """Wait for a predicate to become True within timeout.
    Returns True if satisfied, False otherwise.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def try_call(func: Callable[[], Any], timeout: float = 5.0, interval: float = 0.1) -> tuple[bool, Any]:
    """Try to call a function until it succeeds without raising, or timeout."""
    deadline = time.time() + timeout
    last_exc = None
    while time.time() < deadline:
        try:
            return True, func()
        except Exception as e:
            last_exc = e
            time.sleep(interval)
    return False, last_exc
