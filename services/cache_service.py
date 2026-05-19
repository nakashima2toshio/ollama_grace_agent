#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cache_service.py - キャッシュサービス
=====================================
TTLベースのメモリキャッシュ実装

統合元:
- helper_api.py::MemoryCache
"""

import time
from typing import Any, Optional, Dict
from functools import wraps
import hashlib


class MemoryCache:
    """
    メモリベースキャッシュ

    Features:
    - TTL (Time To Live) 対応
    - 最大サイズ制限
    - 古いエントリの自動削除
    """

    def __init__(
        self,
        enabled: bool = True,
        ttl: int = 3600,
        max_size: int = 100
    ):
        """
        Args:
            enabled: キャッシュ有効フラグ
            ttl: キャッシュの有効期限（秒）
            max_size: 最大エントリ数
        """
        self._storage: Dict[str, Dict[str, Any]] = {}
        self._enabled = enabled
        self._ttl = ttl
        self._max_size = max_size

    def get(self, key: str) -> Optional[Any]:
        """
        キャッシュから値を取得

        Args:
            key: キャッシュキー

        Returns:
            キャッシュされた値（存在しない/期限切れの場合はNone）
        """
        if not self._enabled or key not in self._storage:
            return None

        cached_data = self._storage[key]
        if time.time() - cached_data['timestamp'] > self._ttl:
            del self._storage[key]
            return None

        return cached_data['result']

    def set(self, key: str, value: Any) -> None:
        """
        キャッシュに値を設定

        Args:
            key: キャッシュキー
            value: キャッシュする値
        """
        if not self._enabled:
            return

        self._storage[key] = {
            'result': value,
            'timestamp': time.time()
        }

        # サイズ制限チェック
        if len(self._storage) > self._max_size:
            self._evict_oldest()

    def delete(self, key: str) -> bool:
        """
        キャッシュからエントリを削除

        Args:
            key: キャッシュキー

        Returns:
            削除成功時True
        """
        if key in self._storage:
            del self._storage[key]
            return True
        return False

    def clear(self) -> None:
        """キャッシュを全クリア"""
        self._storage.clear()

    def size(self) -> int:
        """現在のキャッシュサイズ"""
        return len(self._storage)

    def keys(self) -> list:
        """全キャッシュキーを取得"""
        return list(self._storage.keys())

    def has(self, key: str) -> bool:
        """キーが存在するか（有効期限考慮）"""
        return self.get(key) is not None

    def _evict_oldest(self) -> None:
        """最も古いエントリを削除"""
        if not self._storage:
            return
        oldest_key = min(self._storage, key=lambda k: self._storage[k]['timestamp'])
        del self._storage[oldest_key]

    def cleanup_expired(self) -> int:
        """期限切れエントリを削除"""
        current_time = time.time()
        expired_keys = [
            key for key, data in self._storage.items()
            if current_time - data['timestamp'] > self._ttl
        ]
        for key in expired_keys:
            del self._storage[key]
        return len(expired_keys)

    @property
    def enabled(self) -> bool:
        """キャッシュが有効か"""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """キャッシュの有効/無効を設定"""
        self._enabled = value

    @property
    def ttl(self) -> int:
        """現在のTTL値"""
        return self._ttl

    @ttl.setter
    def ttl(self, value: int) -> None:
        """TTLを設定"""
        self._ttl = value

    def stats(self) -> Dict[str, Any]:
        """キャッシュ統計情報"""
        return {
            "enabled": self._enabled,
            "size": len(self._storage),
            "max_size": self._max_size,
            "ttl": self._ttl
        }


# ===================================================================
# デコレータ
# ===================================================================

def cache_result(cache: MemoryCache = None, ttl: int = None):
    """
    関数結果をキャッシュするデコレータ

    Args:
        cache: 使用するキャッシュインスタンス（省略時はグローバルキャッシュ）
        ttl: このデコレータ用のTTL（未使用、将来拡張用）

    Usage:
        @cache_result()
        def expensive_function(arg1, arg2):
            return compute(arg1, arg2)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            target_cache = cache or _global_cache
            if not target_cache.enabled:
                return func(*args, **kwargs)

            # キャッシュキーの生成
            cache_key = _generate_cache_key(func.__name__, args, kwargs)

            # キャッシュから取得
            cached_result = target_cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            # 関数実行とキャッシュ保存
            result = func(*args, **kwargs)
            target_cache.set(cache_key, result)
            return result

        return wrapper
    return decorator


def _generate_cache_key(func_name: str, args: tuple, kwargs: dict) -> str:
    """キャッシュキーを生成"""
    key_data = f"{func_name}_{str(args)}_{str(sorted(kwargs.items()))}"
    return hashlib.md5(key_data.encode()).hexdigest()


# ===================================================================
# グローバルキャッシュインスタンス
# ===================================================================

# 設定からキャッシュパラメータを取得（循環インポート回避のためデフォルト値使用）
_global_cache = MemoryCache(
    enabled=True,
    ttl=3600,
    max_size=100
)


def get_global_cache() -> MemoryCache:
    """グローバルキャッシュを取得"""
    return _global_cache


def init_cache_from_config(config) -> None:
    """
    設定からキャッシュを初期化

    Args:
        config: ConfigManagerインスタンス
    """
    global _global_cache
    _global_cache._enabled = config.get("cache.enabled", True)
    _global_cache._ttl = config.get("cache.ttl", 3600)
    _global_cache._max_size = config.get("cache.max_size", 100)


# 後方互換性のためのエイリアス
cache = _global_cache


# ===================================================================
# エクスポート
# ===================================================================

__all__ = [
    # クラス
    "MemoryCache",
    # デコレータ
    "cache_result",
    # グローバルインスタンス
    "cache",
    # ユーティリティ
    "get_global_cache",
    "init_cache_from_config",
]