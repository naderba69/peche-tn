import asyncio

import pytest

from spotdata.services.cache import AsyncTTLCache


@pytest.mark.asyncio
async def test_cache_coalesces_concurrent_requests() -> None:
    cache: AsyncTTLCache[str, dict[str, int]] = AsyncTTLCache(ttl_seconds=60, max_entries=10)
    calls = 0

    async def factory() -> dict[str, int]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"value": 7}

    values = await asyncio.gather(*(cache.get_or_create("same", factory) for _ in range(8)))
    assert values == [{"value": 7}] * 8
    assert calls == 1
    assert cache.misses == 1
    assert cache.hits == 7
    assert cache.size == 1


@pytest.mark.asyncio
async def test_cache_expires_and_enforces_size() -> None:
    cache: AsyncTTLCache[str, int] = AsyncTTLCache(ttl_seconds=0.01, max_entries=2)

    async def value(number: int) -> int:
        return number

    await cache.get_or_create("one", lambda: value(1))
    await cache.get_or_create("two", lambda: value(2))
    await cache.get_or_create("three", lambda: value(3))
    assert cache.size == 2
    await asyncio.sleep(0.02)
    assert cache.size == 0


@pytest.mark.asyncio
async def test_failed_factory_is_not_cached() -> None:
    cache: AsyncTTLCache[str, int] = AsyncTTLCache(ttl_seconds=60)
    calls = 0

    async def factory() -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary")
        return 9

    with pytest.raises(RuntimeError, match="temporary"):
        await cache.get_or_create("key", factory)
    assert await cache.get_or_create("key", factory) == 9
    assert calls == 2


async def _immediate(value: str) -> str:
    return value


@pytest.mark.asyncio
async def test_cancelling_the_creator_stops_the_owned_upstream_task() -> None:
    """A dropped caller must not leave factory work running with no reader.

    The decision route cancels a started-but-unneeded fetch when its safety gate fails. The
    factory task lives inside the cache, so the creator has to cancel it on the way out —
    otherwise its result is discarded, its error goes unretrieved, and the upstream call keeps
    burning quota nobody will read.
    """
    cache: AsyncTTLCache[str, str] = AsyncTTLCache(ttl_seconds=60)
    state = {"started": False, "cancelled": False, "returned": False}

    async def factory() -> str:
        state["started"] = True
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise
        state["returned"] = True
        return "never-cached"

    outer = asyncio.ensure_future(cache.get_or_create("k", factory))
    await asyncio.sleep(0.01)
    outer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await outer
    await asyncio.sleep(0.01)

    assert state["started"] is True
    assert state["cancelled"] is True
    assert state["returned"] is False
    assert cache.size == 0
    # The in-flight slot was released, so a later caller starts fresh instead of awaiting an
    # orphaned cancelled task forever.
    assert await cache.get_or_create("k", lambda: _immediate("cached after cancel")) == (
        "cached after cancel"
    )
