"""research.ttl_cache: hits, expiry, and the bound that keeps the API process from growing."""
import gc
import weakref

import core.research
from core.research import ttl_cache


def _cached(monkeypatch, ttl=60, maxsize=3):
    clock = [0.0]
    monkeypatch.setattr(core.research.time, "monotonic", lambda: clock[0])
    calls = []

    @ttl_cache(ttl=ttl, maxsize=maxsize)
    def fetch(ticker):
        calls.append(ticker)
        return ticker.lower()

    return fetch, calls, clock


def test_hit_within_ttl_and_refetch_after(monkeypatch):
    fetch, calls, clock = _cached(monkeypatch)
    assert fetch("AAPL") == fetch("AAPL") == "aapl"
    assert calls == ["AAPL"]
    clock[0] = 61
    fetch("AAPL")
    assert calls == ["AAPL", "AAPL"]


def test_size_is_capped_oldest_first(monkeypatch):
    fetch, calls, clock = _cached(monkeypatch, maxsize=3)
    for t in ("A", "B", "C", "D"):
        fetch(t)
    calls.clear()
    fetch("B"), fetch("C"), fetch("D")
    assert calls == []          # still cached
    fetch("A")
    assert calls == ["A"]       # evicted when D arrived


def test_expired_and_evicted_results_are_freed(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(core.research.time, "monotonic", lambda: clock[0])

    class Result:  # stands in for a price-history DataFrame
        pass

    @ttl_cache(ttl=60, maxsize=2)
    def fetch(ticker):
        return Result()

    expired = weakref.ref(fetch("OLD"))
    clock[0] = 61
    fetch("NEW")
    gc.collect()
    assert expired() is None  # dropped on the next insert, not kept until the same key is asked again

    evicted = weakref.ref(fetch("A"))
    fetch("B"), fetch("C")
    gc.collect()
    assert evicted() is None
