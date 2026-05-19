#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
agent_parallel_search.py - 並列検索エンジン
==========================================
複数のQdrantコレクションを並列検索

機能:
- ThreadPoolExecutorによる並列処理
- タイムアウト管理
- エラーハンドリング
- 進捗ログ
"""

import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """検索結果のラッパー"""
    collection_name: str
    results: List[Dict[str, Any]]
    top_score: float
    elapsed_ms: float
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and len(self.results) > 0


class ParallelSearchEngine:
    """
    並列検索エンジン

    複数のQdrantコレクションを並列に検索し、結果を統合します。

    使用例:
        engine = ParallelSearchEngine(max_workers=4)

        results = engine.search_all_collections(
            query="レベッカ・クローン",
            collections=["qa_pairs", "wikipedia_ja", "livedoor"],
            search_func=search_rag_knowledge_base_structured
        )
    """

    def __init__(self, max_workers: int = 4, timeout_per_collection: int = 10):
        """
        初期化

        Args:
            max_workers: 並列実行数（デフォルト4）
            timeout_per_collection: コレクション毎のタイムアウト（秒）
        """
        self.max_workers = max_workers
        self.timeout_per_collection = timeout_per_collection
        logger.info(f"ParallelSearchEngine initialized (workers: {max_workers}, timeout: {timeout_per_collection}s)")

    def search_all_collections(
            self,
            query: str,
            collections: List[str],
            search_func: Callable
    ) -> List[Dict[str, Any]]:
        """
        全コレクションを並列検索

        Args:
            query: 検索クエリ
            collections: コレクション名リスト
            search_func: 検索関数 (query, collection_name) -> List[Dict] or str

        Returns:
            全検索結果のリスト（スコア降順）
        """
        if not collections:
            logger.warning("No collections provided for search")
            return []

        start_time = time.time()
        total_collections = len(collections)

        logger.info(f"🔄 並列検索開始: {total_collections}コレクション × {self.max_workers}並列")
        logger.info(f"   クエリ: '{query}'")

        all_results = []
        search_results: List[SearchResult] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 全コレクションに対して並列検索を投入
            future_to_collection = {
                executor.submit(self._search_single_collection, query, col, search_func): col
                for col in collections
            }

            completed = 0
            for future in as_completed(future_to_collection):
                collection = future_to_collection[future]
                completed += 1

                try:
                    search_result = future.result(timeout=self.timeout_per_collection)
                    search_results.append(search_result)

                    if search_result.success:
                        logger.info(
                            f"  ✓ [{completed}/{total_collections}] {collection}: "
                            f"{len(search_result.results)}件 "
                            f"(Top: {search_result.top_score:.3f}, "
                            f"{search_result.elapsed_ms:.0f}ms)"
                        )
                        all_results.extend(search_result.results)
                    else:
                        if search_result.error:
                            logger.warning(
                                f"  ✗ [{completed}/{total_collections}] {collection}: "
                                f"エラー - {search_result.error}"
                            )
                        else:
                            logger.debug(
                                f"  - [{completed}/{total_collections}] {collection}: "
                                f"0件 ({search_result.elapsed_ms:.0f}ms)"
                            )

                except TimeoutError:
                    logger.error(
                        f"  ⏱️ [{completed}/{total_collections}] {collection}: "
                        f"タイムアウト ({self.timeout_per_collection}s)"
                    )
                except Exception as e:
                    logger.error(
                        f"  ✗ [{completed}/{total_collections}] {collection}: "
                        f"予期せぬエラー - {e}"
                    )

        # スコア順にソート
        all_results.sort(key=lambda x: x.get('score', 0.0), reverse=True)

        elapsed = (time.time() - start_time) * 1000
        success_count = sum(1 for r in search_results if r.success)

        logger.info(
            f"✅ 並列検索完了: {success_count}/{total_collections}コレクション成功, "
            f"合計{len(all_results)}件の結果 ({elapsed:.0f}ms)"
        )

        # 統計情報をログ
        if all_results:
            top_score = all_results[0].get('score', 0.0)
            logger.info(f"   最高スコア: {top_score:.3f}")

        return all_results

    def _search_single_collection(
            self,
            query: str,
            collection_name: str,
            search_func: Callable
    ) -> SearchResult:
        """
        単一コレクションを検索（内部関数）

        Args:
            query: 検索クエリ
            collection_name: コレクション名
            search_func: 検索関数

        Returns:
            SearchResult オブジェクト
        """
        start_time = time.time()

        try:
            results = search_func(query, collection_name)

            elapsed_ms = (time.time() - start_time) * 1000

            # 文字列（エラーメッセージ）が返された場合
            if isinstance(results, str):
                return SearchResult(
                    collection_name=collection_name,
                    results=[],
                    top_score=0.0,
                    elapsed_ms=elapsed_ms,
                    error=results
                )

            # 正常な結果の場合
            if results and len(results) > 0:
                top_score = max(r.get('score', 0.0) for r in results)

                # 結果にコレクション名を埋め込む（後で識別できるように）
                for r in results:
                    if 'collection_name' not in r:
                        r['collection_name'] = collection_name

                return SearchResult(
                    collection_name=collection_name,
                    results=results,
                    top_score=top_score,
                    elapsed_ms=elapsed_ms
                )
            else:
                return SearchResult(
                    collection_name=collection_name,
                    results=[],
                    top_score=0.0,
                    elapsed_ms=elapsed_ms
                )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return SearchResult(
                collection_name=collection_name,
                results=[],
                top_score=0.0,
                elapsed_ms=elapsed_ms,
                error=str(e)
            )

    def search_with_priority(
            self,
            query: str,
            priority_collections: List[str],
            other_collections: List[str],
            search_func: Callable,
            early_stop_score: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        優先順位付き検索

        優先コレクションから検索を開始し、高スコアが得られたら停止。

        Args:
            query: 検索クエリ
            priority_collections: 優先コレクションリスト
            other_collections: その他のコレクションリスト
            search_func: 検索関数
            early_stop_score: この閾値を超えたら検索を停止

        Returns:
            検索結果リスト
        """
        logger.info(f"🎯 優先順位付き検索開始")
        logger.info(f"   優先: {priority_collections}")
        logger.info(f"   その他: {len(other_collections)}コレクション")

        # フェーズ1: 優先コレクションを検索
        if priority_collections:
            priority_results = self.search_all_collections(query, priority_collections, search_func)

            # 高スコア結果があれば終了
            if priority_results and priority_results[0].get('score', 0.0) >= early_stop_score:
                top_score = priority_results[0].get('score', 0.0)
                logger.info(
                    f"✅ 優先コレクションで高スコア発見 ({top_score:.3f}), 検索終了"
                )
                return priority_results

            logger.info(f"⚠️ 優先コレクションのスコアが低い → その他コレクションも検索")
        else:
            priority_results = []

        # フェーズ2: その他のコレクションを検索
        if other_collections:
            other_results = self.search_all_collections(query, other_collections, search_func)
        else:
            other_results = []

        # 全結果を統合してソート
        all_results = priority_results + other_results
        all_results.sort(key=lambda x: x.get('score', 0.0), reverse=True)

        return all_results


# ===================================================================
# グローバルインスタンス
# ===================================================================

# デフォルト並列検索エンジン（4並列）
parallel_search_engine = ParallelSearchEngine(max_workers=4, timeout_per_collection=10)


# ===================================================================
# ユーティリティ関数
# ===================================================================

def search_all_parallel(
        query: str,
        collections: List[str],
        search_func: Callable,
        max_workers: int = 4
) -> List[Dict[str, Any]]:
    """
    並列検索のショートカット関数

    Args:
        query: 検索クエリ
        collections: コレクション名リスト
        search_func: 検索関数
        max_workers: 並列数

    Returns:
        検索結果リスト
    """
    engine = ParallelSearchEngine(max_workers=max_workers)
    return engine.search_all_collections(query, collections, search_func)


# ===================================================================
# エクスポート
# ===================================================================

__all__ = [
    "ParallelSearchEngine",
    "SearchResult",
    "parallel_search_engine",
    "search_all_parallel",
]
