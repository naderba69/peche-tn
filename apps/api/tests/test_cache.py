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
