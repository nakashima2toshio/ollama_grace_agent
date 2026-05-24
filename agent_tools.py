# agent_tools.py
"""
Rankの無効化：
1. [UI/Agent] RAGSearchTool.execute (GRACEエージェント)
   * ↘ 呼び出し: search_rag_knowledge_base_structured
       * ↘ [直接実行]: rerank_results (Cohere API使用)
2. 無効化 Code
    reranked_results = rerank_results(query, candidates, top_k=AgentConfig.RAG_SEARCH_LIMIT)
"""

import os
import time
import json
import logging
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass, field
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse, ResponseHandlingException
from qdrant_client_wrapper import search_collection, embed_query, embed_sparse_query_unified, QDRANT_CONFIG, get_qdrant_client
from config import AgentConfig, CohereConfig
from services.qdrant_service import get_collection_embedding_params, embed_query_for_search

# キャッシュと並列検索のインポート
from agent_cache import collection_cache
from agent_parallel_search import parallel_search_engine

try:
    import cohere
except ImportError:
    cohere = None

logger = logging.getLogger(__name__)  # Configure logger for this module

# Initialize Client（シングルトン: Phase 2 STEP 4 改善）
client: QdrantClient = get_qdrant_client()


# ============ コサイン類似度閾値 ============
COSINE_SIMILARITY_THRESHOLD: float = 0.7  # Cohere Rerank廃止 → コサイン類似度で直接フィルタ


# ============ コレクション一覧キャッシュ（Phase 3 STEP 6 改善）============
_collections_cache: Optional[List[str]] = None
_collections_cache_time: float = 0.0
_COLLECTIONS_CACHE_TTL: float = 60.0  # 60秒


def get_existing_collections_cached() -> List[str]:
    """
    コレクション一覧をキャッシュ付きで取得

    TTL（60秒）以内は前回結果を返す。
    並列検索時に N 回呼ばれても API は 1 回で済む。
    """
    global _collections_cache, _collections_cache_time
    now = time.time()
    if _collections_cache is None or (now - _collections_cache_time) > _COLLECTIONS_CACHE_TTL:
        _collections_cache = [c.name for c in client.get_collections().collections]
        _collections_cache_time = now
        logger.debug(f"コレクション一覧キャッシュ更新: {len(_collections_cache)}件")
    return _collections_cache


# ============ カスタム例外 ============
class RAGToolError(Exception):
    """RAGツール固有のエラー基底クラス"""
    pass


class QdrantConnectionError(RAGToolError):
    """Qdrant接続エラー"""
    pass


class CollectionNotFoundError(RAGToolError):
    """コレクション未存在エラー"""
    pass


class EmbeddingError(RAGToolError):
    """埋め込み生成エラー"""
    pass


# ============ 評価用メトリクス ============
@dataclass
class SearchMetrics:
    """検索結果のメトリクス（評価用）"""
    query: str
    collection_name: str
    latency_ms: float
    total_results: int
    filtered_results: int
    top_score: float
    scores: List[float] = field(default_factory=list)
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))


# Global metrics log (in-memory for evaluation session)
_search_metrics_log: List[SearchMetrics] = []


def get_search_metrics() -> List[SearchMetrics]:
    """評価用: 収集したメトリクスを取得"""
    return _search_metrics_log.copy()


def clear_search_metrics() -> None:
    """評価用: メトリクスをクリア"""
    _search_metrics_log.clear()


def export_metrics_to_dict() -> List[Dict[str, Any]]:
    """メトリクスを辞書形式でエクスポート"""
    from dataclasses import asdict
    return [asdict(m) for m in _search_metrics_log]


# ============ ヘルスチェック ============
def check_qdrant_health() -> bool:
    """Qdrantサーバーの接続確認"""
    try:
        client.get_collections()
        logger.info("Qdrant health check: OK")
        return True
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")
        return False


# ============ ツール関数 ============
def list_rag_collections() -> str:
    """
    利用可能なRAGのコレクション一覧（ナレッジベースの種類）を取得します。
    ユーザーが「どのような知識があるか」「コレクション一覧を教えて」と質問した場合に使用してください。
    Returns:
        str: 利用可能なコレクション名のリスト。
    """
    logger.info("ツールアクション: コレクション一覧を取得中...")
    try:
        # Phase 3 STEP 6 改善: コレクション一覧キャッシュ化
        collections: List[str] = get_existing_collections_cached()

        if not collections:
            logger.info("Qdrantに利用可能なコレクションがありません。")
            return "現在、利用可能なコレクションはありません。"

        result_lines: List[str] = ["利用可能なコレクション一覧:"]
        for c in collections:
            try:
                info = client.get_collection(c)
                count: int = info.points_count
                result_lines.append(f"- {c} ({count} documents)")
            except (UnexpectedResponse, ResponseHandlingException) as e:
                logger.warning(f"コレクション '{c}' の情報取得エラー: {e}")
                result_lines.append(f"- {c} (情報取得エラー)")
            except Exception as e:
                logger.error(f"不明なエラー: コレクション '{c}' の情報取得中にエラーが発生しました: {e}", exc_info=True)
                result_lines.append(f"- {c} (不明なエラー)")

        logger.info(f"コレクション一覧取得完了: {len(collections)}件")
        return "\n".join(result_lines)

    except Exception as e:
        logger.error(f"コレクション一覧取得エラー: {e}", exc_info=True)
        raise QdrantConnectionError(f"Qdrant接続エラー、またはコレクション一覧の取得に失敗しました: {str(e)}")


def filter_results_by_keywords(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """
    検索結果をクエリのキーワードでフィルタリングする（共通ロジック）
    Legacy Agentと同じく、スペース区切りのトークンを必須キーワードとして扱う。
    """
    import re

    # 必須キーワードの抽出（Legacyと同一ロジック: スペース区切り）
    tokens = query.split()
    required_keywords = []

    for t in tokens:
        # 2文字以上で、かつ記号のみでないものを採用
        if len(t) >= 2:
            required_keywords.append(t)

    required_keywords = list(set(required_keywords))
    logger.info(f"Filtering Logic - Required keywords: {required_keywords}")

    filtered_results = []
    for res in results:
        payload = res.get("payload", {})
        content = (str(payload.get("question", "")) + " " +
                   str(payload.get("answer", "")) + " " +
                   str(payload.get("content", "")))

        is_relevant = True
        if required_keywords:
            # キーワードが1つでも含まれていればOKとする（緩やかなAND条件）
            # Legacy Agentでは「キーワードを含めてください」と指示しているため、
            # 検索結果にそれらが含まれることを期待するが、
            # 全てが含まれるとは限らないため、ヒット数で判定。
            hit_count = sum(1 for k in required_keywords if k in content)

            # 1つもヒットしない場合は除外
            if hit_count == 0:
                is_relevant = False
                logger.debug(f"Keyword miss (score={res.get('score', 0):.3f}): Filtering out.")

        if is_relevant:
            filtered_results.append(res)

    return filtered_results


def rerank_results(
        query: str,
        results: List[Dict[str, Any]],
        top_k: int = 3,
        threshold: float = 0.5
) -> List[Dict[str, Any]]:
    """
    検索結果をCohere Rerank APIで再評価し、スコアを更新してソートする。
    Args:
        query: ユーザーの検索クエリ
        results: Qdrantからの検索結果リスト
        top_k: 最終的に残す件数
        threshold: スコアの足切りライン（Cohere APIがない場合は無視される）
    Returns:
        再ランク付けされた結果リスト
    """
    if not results:
        return []

    # Cohere APIキーがない場合、RRFスコアのままで結果を返す（threshold判定なし）
    if not CohereConfig.API_KEY or cohere is None:
        logger.info("Cohere APIキーがないため、RRFスコアのまま結果を返します（threshold判定なし）")
        # スコア順にソート（RRFスコア）
        sorted_results = sorted(results, key=lambda x: x.get("score", 0.0), reverse=True)
        return sorted_results[:top_k]

    try:
        co = cohere.Client(api_key=CohereConfig.API_KEY)

        # ドキュメントのテキストリストを作成
        documents = []
        for res in results:
            payload = res.get("payload", {})
            # QuestionとAnswerを組み合わせて文脈を作る
            doc_text = f"Question: {payload.get('question', '')}\nAnswer: {payload.get('answer', '')}"
            documents.append(doc_text)

        # Rerank実行
        rerank_response = co.rerank(
            model=CohereConfig.RERANK_MODEL,
            query=query,
            documents=documents,
            top_n=len(documents)
        )

        # スコアを更新
        reranked_results = []
        for r in rerank_response.results:
            # 元の結果を取得 (indexで対応)
            original_result = results[r.index]
            new_score = r.relevance_score

            # スコアを更新した新しい辞書を作成
            new_result = original_result.copy()
            # 元のQdrantスコアを保持
            new_result["original_score"] = original_result.get("score", 0.0)
            # CohereのRe-rankingスコアを設定
            new_result["rerank_score"] = new_score
            new_result["score"] = new_score  # 互換性のため

            # 閾値判定
            if new_score >= threshold:
                reranked_results.append(new_result)

        # スコア順はCohereが保証しているはずだが、念のためソート
        reranked_results.sort(key=lambda x: x["score"], reverse=True)

        logger.info(
            f"Re-ranking completed: {len(results)} -> {len(reranked_results)} results (Top score: {reranked_results[0]['score'] if reranked_results else 0.0:.4f})")

        return reranked_results[:top_k]

    except Exception as e:
        logger.error(f"Re-ranking failed: {e}")
        # 失敗時は元の結果をスコア順で返す（threshold判定なし）
        sorted_results = sorted(results, key=lambda x: x.get("score", 0.0), reverse=True)
        return sorted_results[:top_k]


def search_rag_knowledge_base(
        query: str,
        collection_name: Optional[str] = None,
        use_hybrid_search: bool = True
) -> str:
    """
    【上位モジュール】全コレクション並列検索 + コサイン類似度閾値フィルタ

    Gemini SDK (AFC) から直接呼ばれるツール関数。
    collection_name はモデルが指定しても無視し、全コレクションを検索する。

    処理フロー:
      1. Embedding生成（Dense + Sparse、1回だけ）
      2. 全コレクション一覧取得
      3. 並列検索（下位モジュール: search_rag_knowledge_base_structured）
      4. コサイン類似度 >= COSINE_SIMILARITY_THRESHOLD でフィルタ
      5. スコア順ソート、上位5件をフォーマットして返す

    Args:
        query: 検索クエリ
        collection_name: モデルが指定しても無視される（全コレクション検索）
        use_hybrid_search: ハイブリッド検索を使用するか
    """
    start_time = time.time()
    hybrid_status = "有効 (Sparse+Dense)" if use_hybrid_search else "無効 (Denseのみ)"
    logger.info(f"\n{'=' * 60}")
    logger.info(f"🔍 全コレクション検索開始")
    logger.info(f"   Query: '{query}'")
    logger.info(f"   Hybrid Search: {hybrid_status}")
    logger.info(f"   コサイン類似度閾値: {COSINE_SIMILARITY_THRESHOLD}")
    logger.info(f"{'=' * 60}")

    # Step 1: Embedding生成（1回だけ、全コレクションで共有）
    try:
        query_vector: List[float] = embed_query(query)
        if query_vector is None:
            return "[[RAG_TOOL_ERROR]] クエリの埋め込み生成に失敗しました。"
    except Exception as e:
        logger.error(f"Dense Embedding生成エラー: {e}")
        return f"[[RAG_TOOL_ERROR]] Embedding生成エラー: {str(e)}"

    sparse_vector = None
    if use_hybrid_search:
        try:
            sparse_vector = embed_sparse_query_unified(query)
            logger.debug("Sparseベクトル生成成功（1回のみ）")
        except Exception as e:
            logger.debug(f"Sparseベクトル生成スキップ: {e}")

    logger.info(f"✅ Embedding生成完了（Dense: {len(query_vector)}D, Sparse: {'あり' if sparse_vector else 'なし'}）")

    # Step 2: 全コレクション一覧取得
    try:
        all_collections = get_existing_collections_cached()
        logger.info(f"🔍 全コレクション並列検索: {len(all_collections)}コレクション")
    except Exception as e:
        logger.error(f"コレクション一覧取得エラー: {e}")
        return f"[[RAG_TOOL_ERROR]] コレクション一覧の取得に失敗しました: {str(e)}"

    if not all_collections:
        return "[[NO_RAG_RESULT]] 利用可能なコレクションがありません。"

    # Step 3: 並列検索（下位モジュールを各コレクションに対して呼ぶ）
    def search_single(q: str, col: str):
        """1コレクション検索（事前計算ベクトルを共有）"""
        return search_rag_knowledge_base_structured(
            q, col,
            use_hybrid_search=use_hybrid_search,
            precomputed_query_vector=query_vector,
            precomputed_sparse_vector=sparse_vector
        )

    all_results = parallel_search_engine.search_all_collections(
        query=query,
        collections=all_collections,
        search_func=search_single
    )

    # Step 4: コサイン類似度閾値フィルタ（下位モジュールでもフィルタ済みだが、安全のため再度確認）
    filtered = [r for r in all_results if r.get('score', 0.0) >= COSINE_SIMILARITY_THRESHOLD]

    elapsed = (time.time() - start_time) * 1000
    logger.info(f"✅ 全コレクション検索完了: {len(all_results)}件中 {len(filtered)}件が閾値以上 ({elapsed:.0f}ms)")
    logger.info(f"{'=' * 60}\n")

    if not filtered:
        return (
            f"[[NO_RAG_RESULT_LOW_SCORE]] 全コレクションを検索しましたが、"
            f"コサイン類似度 >= {COSINE_SIMILARITY_THRESHOLD} の結果が見つかりませんでした。"
        )

    # Step 5: 上位5件をフォーマットして返す
    return _format_results(filtered[:5], "複数コレクション")


# ★変更: use_hybrid_search パラメータを追加
def search_rag_knowledge_base_structured(
        query: str,
        collection_name: Optional[str] = None,
        use_hybrid_search: bool = True,  # ★追加
        precomputed_query_vector: Optional[List[float]] = None,      # Phase 3 STEP 7 改善
        precomputed_sparse_vector: Optional[Any] = None              # Phase 3 STEP 7 改善
) -> Union[List[Dict[str, Any]], str]:
    """
    Qdrantデータベースから専門的な知識を検索します（構造化データ版）。

    Args:
        query: 検索クエリ
        collection_name: 検索対象のコレクション名（省略時はデフォルト）
        use_hybrid_search: ハイブリッド検索（Sparse + Dense）を使用するか（デフォルト: True）
        precomputed_query_vector: 事前計算済みDenseベクトル（Noneの場合は内部で生成）
        precomputed_sparse_vector: 事前計算済みSparseベクトル（Noneの場合は内部で生成）
    """
    if collection_name is None:
        collection_name = AgentConfig.RAG_DEFAULT_COLLECTION

    start_time: float = time.time()
    # ★変更: ログにハイブリッド検索の状態を追加
    hybrid_status = "有効" if use_hybrid_search else "無効"
    logger.info(
        f"ツールアクション(Structured): RAG検索を実行: query='{query}', collection='{collection_name}', hybrid={hybrid_status}")

    metrics: SearchMetrics = SearchMetrics(
        query=query,
        collection_name=collection_name,
        latency_ms=0.0,
        total_results=0,
        filtered_results=0,
        top_score=0.0
    )

    try:
        # Phase 3 STEP 6 改善: ヘルスチェック削除 + コレクション一覧キャッシュ化
        existing_collections: List[str] = get_existing_collections_cached()
        if collection_name not in existing_collections:
            error_msg: str = f"コレクション '{collection_name}' はQdrantサーバーに存在しません。"
            logger.warning(error_msg)
            raise CollectionNotFoundError(error_msg)

        # Phase 3 STEP 7 改善: 事前計算ベクトルがあればそれを使用（次元数チェック付き）
        collection_params = get_collection_embedding_params(client, collection_name)
        col_dims = collection_params.get("dims", 3072)
        col_model = collection_params.get("model", "text-embedding-3-large")

        if precomputed_query_vector is not None and len(precomputed_query_vector) == col_dims:
            query_vector = precomputed_query_vector
            logger.debug(f"事前計算済みDenseベクトルを使用: {collection_name}")
        elif col_dims != 3072:
            # 次元数不一致 → コレクション専用のEmbeddingを再生成（例: 768次元はnomic-embed-text/Ollama）
            logger.info(f"次元数不一致: precomputed={len(precomputed_query_vector) if precomputed_query_vector else 'None'}D, "
                        f"collection={col_dims}D → {collection_name}用Embedding再生成 (model={col_model})")
            query_vector = embed_query_for_search(query, model=col_model, dims=col_dims)
        else:
            query_vector = precomputed_query_vector if precomputed_query_vector is not None else embed_query(query)
        if query_vector is None:
            raise EmbeddingError("クエリの埋め込み生成に失敗しました。")

        # ★変更: use_hybrid_search フラグに基づいてスパースベクトルを生成
        sparse_vector = None
        if use_hybrid_search:
            if precomputed_sparse_vector is not None:
                sparse_vector = precomputed_sparse_vector
                logger.debug(f"事前計算済みSparseベクトルを使用: {collection_name}")
            else:
                try:
                    sparse_vector = embed_sparse_query_unified(query)
                    logger.debug(f"スパースベクトル取得成功: {collection_name}")
                except Exception as e:
                    logger.debug(f"スパースベクトル取得スキップ ({collection_name}): {e}")
        else:
            logger.debug(f"ハイブリッド検索無効: スパースベクトルをスキップ ({collection_name})")

        # 1. Retrieval (Broad Search)
        # Re-rankingの効果を高めるため、最終的に欲しい数より多く取得する
        # Phase 3 STEP 8 改善: Sparseフォールバックは search_collection() に一元化
        # search_collection() 内で Hybrid → Dense → 最終フォールバック の3段階を処理
        candidates: List[Dict[str, Any]] = search_collection(
            client=client,
            collection_name=collection_name,
            query_vector=query_vector,
            sparse_vector=sparse_vector,
            limit=20  # 候補を広げる
        )

        metrics.total_results = len(candidates) if candidates else 0

        if not candidates:
            metrics.latency_ms = (time.time() - start_time) * 1000.0
            _search_metrics_log.append(metrics)
            return f"[[NO_RAG_RESULT]] 検索結果が見つかりませんでした。コレクション: '{collection_name}'."

        # 2. コサイン類似度閾値フィルタ（Cohere Rerank 廃止）
        filtered_results = [
            r for r in candidates
            if r.get("score", 0.0) >= COSINE_SIMILARITY_THRESHOLD
        ]
        filtered_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        filtered_results = filtered_results[:AgentConfig.RAG_SEARCH_LIMIT]

        # 3. Metrics & Return
        scores: List[float] = [res.get("score", 0.0) for res in filtered_results]
        metrics.scores = scores
        metrics.top_score = max(scores) if scores else 0.0
        metrics.filtered_results = len(filtered_results)

        metrics.latency_ms = (time.time() - start_time) * 1000.0
        _search_metrics_log.append(metrics)

        if not filtered_results:
            all_scores = [r.get('score', 0.0) for r in candidates]
            max_score = max(all_scores) if all_scores else 0.0
            return (
                f"[[NO_RAG_RESULT_LOW_SCORE]] スコア閾値未満の結果のみでした。"
                f"最高スコア: {max_score:.2f} (閾値: {COSINE_SIMILARITY_THRESHOLD})"
            )

        logger.info(
            f"コサイン類似度フィルタ: {len(candidates)} -> {len(filtered_results)}件 "
            f"(Top: {filtered_results[0]['score']:.4f}, 閾値: {COSINE_SIMILARITY_THRESHOLD})"
        )

        return filtered_results

    except Exception as e:
        logger.error(f"RAGツールエラー: {e}", exc_info=True)
        return f"[[RAG_TOOL_ERROR]] エラーが発生しました: {str(e)}"


# ============ 新戦略: キャッシュ + 並列検索 ============

# ★変更: use_hybrid_search パラメータを追加
def search_rag_knowledge_base_cached(
        query: str,
        session_id: str,
        collection_name: Optional[str] = None,
        cache_threshold: float = 0.6,
        use_hybrid_search: bool = True  # ★追加
) -> str:
    """
    キャッシュと並列検索を使用したスマート検索（新戦略）

    戦略:
    1. ユーザーが明示的にコレクション指定 → そのコレクションのみ検索
    2. 前回の成功コレクションがキャッシュにある → そのコレクションから検索開始
    3. キャッシュがない、またはスコアが低い → 全コレクション4並列検索
    4. 最高スコアのコレクションをキャッシュに保存

    Args:
        query: 検索クエリ
        session_id: セッションID（キャッシュキー）
        collection_name: 明示的に指定されたコレクション名（優先）
        cache_threshold: キャッシュ検索成功とみなすスコア閾値
        use_hybrid_search: ハイブリッド検索（Sparse + Dense）を使用するか（デフォルト: True）

    Returns:
        検索結果（フォーマット済み文字列）
    """
    start_time = time.time()

    # ★変更: ログにハイブリッド検索の状態を追加
    hybrid_status = "有効 (Sparse+Dense)" if use_hybrid_search else "無効 (Denseのみ)"
    logger.info(f"\n{'=' * 60}")
    logger.info(f"🔍 スマート検索開始")
    logger.info(f"   Query: '{query}'")
    logger.info(f"   Session: {session_id}")
    logger.info(f"   Hybrid Search: {hybrid_status}")  # ★追加
    logger.info(f"{'=' * 60}")

    # Phase 3 STEP 7 改善: Embeddingを1回だけ生成（全検索パスで共有）
    try:
        query_vector: List[float] = embed_query(query)
        if query_vector is None:
            return "[[RAG_TOOL_ERROR]] クエリの埋め込み生成に失敗しました。"
    except Exception as e:
        logger.error(f"Dense Embedding生成エラー: {e}")
        return f"[[RAG_TOOL_ERROR]] Embedding生成エラー: {str(e)}"

    sparse_vector = None
    if use_hybrid_search:
        try:
            sparse_vector = embed_sparse_query_unified(query)
            logger.debug("Sparseベクトル生成成功（1回のみ）")
        except Exception as e:
            logger.debug(f"Sparseベクトル生成スキップ: {e}")

    logger.info(f"✅ Embedding生成完了（Dense: {len(query_vector)}D, Sparse: {'あり' if sparse_vector else 'なし'}）")

    # ステップ1: ユーザーが明示的にコレクション指定した場合
    if collection_name:
        logger.info(f"🎯 ユーザー指定コレクション: {collection_name}")
        # Phase 3 STEP 7 改善: 事前計算ベクトルを渡す
        result = search_rag_knowledge_base_structured(
            query, collection_name,
            use_hybrid_search=use_hybrid_search,
            precomputed_query_vector=query_vector,
            precomputed_sparse_vector=sparse_vector
        )

        elapsed = (time.time() - start_time) * 1000
        logger.info(f"⏱️ 検索完了: {elapsed:.0f}ms (ユーザー指定)")

        if isinstance(result, str):
            return result
        return _format_results(result, collection_name)

    # ステップ2: キャッシュチェック
    cached_entry = collection_cache.get(session_id)

    if cached_entry:
        logger.info(
            f"💾 キャッシュヒット: {cached_entry.collection_name} "
            f"(前回スコア: {cached_entry.last_score:.3f}, "
            f"ヒット回数: {cached_entry.hit_count})"
        )

        # Phase 3 STEP 7 改善: 事前計算ベクトルを渡す
        cached_results = search_rag_knowledge_base_structured(
            query, cached_entry.collection_name,
            use_hybrid_search=use_hybrid_search,
            precomputed_query_vector=query_vector,
            precomputed_sparse_vector=sparse_vector
        )

        if not isinstance(cached_results, str) and cached_results:
            top_score = max(r.get('score', 0.0) for r in cached_results)

            # 良いスコアが得られた場合
            if top_score >= cache_threshold:
                logger.info(f"✅ キャッシュ検索成功: スコア {top_score:.3f}")

                # キャッシュを更新（より高いスコアの場合のみ）
                collection_cache.set(session_id, cached_entry.collection_name, top_score, query)
                collection_cache.update_query_history(session_id, query)

                elapsed = (time.time() - start_time) * 1000
                logger.info(f"⏱️ 検索完了: {elapsed:.0f}ms (キャッシュ利用)")

                return _format_results(cached_results, cached_entry.collection_name)
            else:
                logger.info(f"⚠️ キャッシュ検索のスコアが低い: {top_score:.3f} → 全検索に移行")
        else:
            logger.info(f"⚠️ キャッシュ検索で結果なし → 全検索に移行")
    else:
        logger.info(f"🆕 キャッシュなし → 全検索実行")

    # ステップ3: 全コレクション並列検索
    try:
        # Phase 3 STEP 6 改善: コレクション一覧キャッシュ化
        all_collections = get_existing_collections_cached()
        logger.info(f"🔍 全コレクション並列検索: {len(all_collections)}コレクション × 4並列")
    except Exception as e:
        logger.error(f"コレクション一覧取得エラー: {e}")
        return f"[[RAG_TOOL_ERROR]] コレクション一覧の取得に失敗しました: {str(e)}"

    if not all_collections:
        return "[[NO_RAG_RESULT]] 利用可能なコレクションがありません。"

    # Phase 3 STEP 7 改善: 事前計算ベクトルを渡すラッパー関数
    def search_func_with_precomputed(q: str, col: str) -> Union[List[Dict[str, Any]], str]:
        return search_rag_knowledge_base_structured(
            q, col,
            use_hybrid_search=use_hybrid_search,
            precomputed_query_vector=query_vector,
            precomputed_sparse_vector=sparse_vector
        )

    all_results = parallel_search_engine.search_all_collections(
        query=query,
        collections=all_collections,
        search_func=search_func_with_precomputed
    )

    if not all_results:
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"⏱️ 検索完了: {elapsed:.0f}ms (結果なし)")
        return "[[NO_RAG_RESULT]] 全コレクションを検索しましたが、関連する結果が見つかりませんでした。"

    # ステップ4: 最高スコアのコレクションをキャッシュに保存
    top_result = all_results[0]
    top_score = top_result.get('score', 0.0)
    top_collection = top_result.get('collection_name')

    if top_collection and top_score >= 0.5:
        collection_cache.set(session_id, top_collection, top_score, query)
        logger.info(f"💾 キャッシュ更新: {top_collection} (スコア: {top_score:.3f})")

    elapsed = (time.time() - start_time) * 1000
    logger.info(f"⏱️ 検索完了: {elapsed:.0f}ms (全検索)")
    logger.info(f"{'=' * 60}\n")

    # トップ5件のみ返却
    return _format_results(all_results[:5], "複数コレクション")


def _format_results(results: List[Dict[str, Any]], source_label: str) -> str:
    """
    検索結果をフォーマット

    Args:
        results: 検索結果リスト
        source_label: ソースラベル（表示用）

    Returns:
        フォーマット済み文字列
    """
    if not results:
        return "[[NO_RAG_RESULT_LOW_SCORE]] 検索結果は見つかりましたが、関連性スコアが低すぎたため採用しませんでした。"

    formatted_results = []
    for i, res in enumerate(results, 1):
        score = res.get("score", 0.0)
        collection = res.get("collection_name", source_label)

        payload = res.get("payload", {})
        q = payload.get("question", "N/A")
        a = payload.get("answer", "N/A")

        formatted_results.append(
            f"--- Result {i} [Cosine: {score:.4f}] ---\n"
            f"Q: {q}\n"
            f"A: {a}\n"
            f"Source: {collection}\n"
        )

    return "\n".join(formatted_results)
