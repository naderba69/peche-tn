from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass(slots=True)
class _Entry(Generic[V]):
    value: V
    expires_at: float


class AsyncTTLCache(Generic[K, V]):
    """Small process-local TTL cache with single-flight request coalescing.

    Vercel instances are ephemeral, so this is an optimization rather than persistent
    storage. It still prevents duplicate upstream calls inside a warm function instance.
    """

    def __init__(self, *, ttl_seconds: float, max_entries: int = 256) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._entries: OrderedDict[K, _Entry[V]] = OrderedDict()
        self._inflight: dict[K, asyncio.Future[V]] = {}
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0

    async def get_or_create(self, key: K, factory: Callable[[], Awaitable[V]]) -> V:
        creator = False
        async with self._lock:
            self._discard_expired()
            entry = self._entries.get(key)
            if entry is not None:
                self._entries.move_to_end(key)
                self.hits += 1
                return entry.value
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.ensure_future(factory())
                self._inflight[key] = task
                self.misses += 1
                creator = True
            else:
                self.hits += 1

        try:
            value = await task
        except BaseException:
            if creator:
                async with self._lock:
                    self._inflight.pop(key, None)
            raise

        if creator:
            async with self._lock:
                self._inflight.pop(key, None)
                self._entries[key] = _Entry(value=value, expires_at=time.monotonic() + self._ttl)
                self._entries.move_to_end(key)
                while len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)
        return value

    async def delete(self, key: K) -> None:
        async with self._lock:
            self._entries.pop(key, None)

    def _discard_expired(self) -> None:
        now = time.monotonic()
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)

    @property
    def size(self) -> int:
        self._discard_expired()
        return len(self._entries)
