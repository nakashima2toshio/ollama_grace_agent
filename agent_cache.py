#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
agent_cache.py - コレクションキャッシュマネージャー
================================================
前回の検索成功コレクションをセッション単位でキャッシュ

機能:
- 最高スコアコレクションの記録
- セッション単位の管理
- TTL（有効期限）サポート
- ヒット回数の追跡
"""

import time
import logging
from typing import Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CollectionCacheEntry:
    """コレクションキャッシュエントリ"""
    collection_name: str
    last_score: float
    timestamp: float
    hit_count: int = 1
    query_history: list = None  # 直近のクエリ履歴（オプション）

    def __post_init__(self):
        if self.query_history is None:
            self.query_history = []


class CollectionCache:
    """
    前回の検索成功コレクションをキャッシュ

    戦略:
    - セッション単位で最高スコアのコレクションを記録
    - TTL経過後は自動削除
    - ヒット回数を追跡して頻度を把握

    使用例:
        cache = CollectionCache(ttl=300)  # 5分

        # 保存
        cache.set("session_123", "qa_pairs_custom_upload", 0.87)

        # 取得
        entry = cache.get("session_123")
        if entry:
            print(f"前回: {entry.collection_name}, スコア: {entry.last_score}")
    """

    def __init__(self, ttl: int = 300):
        """
        初期化

        Args:
            ttl: Time To Live（秒）。デフォルト5分。
        """
        self._cache: Dict[str, CollectionCacheEntry] = {}
        self._ttl = ttl
        logger.info(f"CollectionCache initialized (TTL: {ttl}s)")

    def get(self, session_id: str) -> Optional[CollectionCacheEntry]:
        """
        キャッシュから取得

        Args:
            session_id: セッションID

        Returns:
            キャッシュエントリ（存在しないor期限切れの場合はNone）
        """
        if session_id not in self._cache:
            logger.debug(f"Cache miss: {session_id}")
            return None

        entry = self._cache[session_id]

        # 有効期限チェック
        age = time.time() - entry.timestamp
        if age > self._ttl:
            logger.info(f"Cache expired: {session_id} (age: {age:.1f}s)")
            del self._cache[session_id]
            return None

        # ヒットカウント増加
        entry.hit_count += 1

        logger.info(f"💾 Cache hit: {session_id} → {entry.collection_name} "
                    f"(score: {entry.last_score:.3f}, hits: {entry.hit_count}, age: {age:.1f}s)")

        return entry

    def set(self, session_id: str, collection_name: str, score: float, query: str = None):
        """
        キャッシュに保存

        Args:
            session_id: セッションID
            collection_name: コレクション名
            score: 検索スコア
            query: 検索クエリ（オプション）
        """
        # 既存エントリがあり、スコアが高い場合のみ更新
        if session_id in self._cache:
            existing = self._cache[session_id]
            if score < existing.last_score:
                logger.debug(f"Cache not updated: new score {score:.3f} < existing {existing.last_score:.3f}")
                return

        entry = CollectionCacheEntry(
            collection_name=collection_name,
            last_score=score,
            timestamp=time.time(),
            query_history=[query] if query else []
        )

        self._cache[session_id] = entry

        logger.info(f"💾 Cache set: {session_id} → {collection_name} (score: {score:.3f})")

    def update_query_history(self, session_id: str, query: str, max_history: int = 5):
        """
        クエリ履歴を更新

        Args:
            session_id: セッションID
            query: 検索クエリ
            max_history: 保持する履歴数
        """
        if session_id in self._cache:
            entry = self._cache[session_id]
            entry.query_history.append(query)
            # 履歴数制限
            if len(entry.query_history) > max_history:
                entry.query_history = entry.query_history[-max_history:]

    def clear(self, session_id: str = None):
        """
        キャッシュをクリア

        Args:
            session_id: セッションID（省略時は全削除）
        """
        if session_id:
            if session_id in self._cache:
                del self._cache[session_id]
                logger.info(f"Cache cleared: {session_id}")
        else:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"All cache cleared: {count} entries")

    def get_stats(self, session_id: str = None) -> Dict:
        """
        統計情報取得

        Args:
            session_id: セッションID（省略時は全体統計）

        Returns:
            統計情報の辞書
        """
        if session_id:
            # 個別セッションの統計
            entry = self._cache.get(session_id)
            if not entry:
                return {"cached": False, "session_id": session_id}

            age = time.time() - entry.timestamp
            return {
                "cached"       : True,
                "session_id"   : session_id,
                "collection"   : entry.collection_name,
                "last_score"   : entry.last_score,
                "hit_count"    : entry.hit_count,
                "age_seconds"  : age,
                "query_history": entry.query_history,
                "expired"      : age > self._ttl
            }
        else:
            # 全体統計
            total_sessions = len(self._cache)
            if total_sessions == 0:
                return {
                    "total_sessions" : 0,
                    "active_sessions": 0
                }

            current_time = time.time()
            active_sessions = sum(
                1 for entry in self._cache.values()
                if current_time - entry.timestamp <= self._ttl
            )

            total_hits = sum(entry.hit_count for entry in self._cache.values())
            avg_score = sum(entry.last_score for entry in self._cache.values()) / total_sessions

            # 最も使われているコレクション
            collection_counts = {}
            for entry in self._cache.values():
                collection_counts[entry.collection_name] = collection_counts.get(entry.collection_name, 0) + 1

            most_used = max(collection_counts.items(), key=lambda x: x[1]) if collection_counts else None

            return {
                "total_sessions"      : total_sessions,
                "active_sessions"     : active_sessions,
                "total_hits"          : total_hits,
                "avg_score"           : avg_score,
                "most_used_collection": most_used[0] if most_used else None,
                "most_used_count"     : most_used[1] if most_used else 0,
                "ttl"                 : self._ttl
            }

    def cleanup_expired(self) -> int:
        """
        期限切れエントリを削除

        Returns:
            削除されたエントリ数
        """
        current_time = time.time()
        expired_sessions = [
            session_id for session_id, entry in self._cache.items()
            if current_time - entry.timestamp > self._ttl
        ]

        for session_id in expired_sessions:
            del self._cache[session_id]

        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired cache entries")

        return len(expired_sessions)

    def __len__(self) -> int:
        """キャッシュエントリ数"""
        return len(self._cache)

    def __repr__(self) -> str:
        return f"CollectionCache(entries={len(self._cache)}, ttl={self._ttl}s)"


# ===================================================================
# グローバルインスタンス
# ===================================================================

# デフォルトキャッシュ（TTL: 5分）
collection_cache = CollectionCache(ttl=300)


# ===================================================================
# ユーティリティ関数
# ===================================================================

def get_cache_stats(session_id: str = None) -> Dict:
    """キャッシュ統計を取得（ショートカット）"""
    return collection_cache.get_stats(session_id)


def clear_cache(session_id: str = None):
    """キャッシュをクリア（ショートカット）"""
    collection_cache.clear(session_id)


# ===================================================================
# エクスポート
# ===================================================================

__all__ = [
    "CollectionCache",
    "CollectionCacheEntry",
    "collection_cache",
    "get_cache_stats",
    "clear_cache",
]
