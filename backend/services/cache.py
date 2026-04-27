"""
简单的内存缓存管理，避免频繁请求 Yahoo Finance。
"""
from datetime import datetime

_store: dict[str, dict] = {}


def get(key: str, ttl_seconds: int = 3600):
    """返回缓存数据（未过期），否则返回 None。"""
    entry = _store.get(key)
    if not entry:
        return None
    age = (datetime.now() - entry["ts"]).total_seconds()
    if age > ttl_seconds:
        return None
    return entry["data"]


def set(key: str, data):
    """写入缓存，记录时间戳。"""
    _store[key] = {"data": data, "ts": datetime.now()}


def invalidate(key: str):
    """清除指定缓存。"""
    _store.pop(key, None)


def invalidate_all():
    """清除全部缓存。"""
    _store.clear()
