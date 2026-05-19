#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qdrant_client_wrapper.py - Qdrant操作ユーティリティ
===================================================
Qdrantベクトルデータベースとの操作を一元管理

使用箇所:
- rag_qa_pair_qdrant.py
- a42_qdrant_registration.py
- a50_rag_search_local_qdrant.py
"""

import os
import logging
import socket
import time
import traceback
from typing import Dict, List, Optional, Any, Tuple, Iterable
from datetime import datetime, timezone

import pandas as pd
import tiktoken
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

# Gemini 3 Migration: Embedding抽象化レイヤー
from helper.helper_embedding import (
    create_embedding_client,
    get_embedding_dimensions,
    EmbeddingClient,
    DEFAULT_GEMINI_EMBEDDING_DIMS,
    DEFAULT_OPENAI_EMBEDDING_DIMS,
)
from helper.helper_embedding_sparse import get_sparse_embedding_client

# 共通モジュール
try:
    from config import QdrantConfig
except ImportError:
    # フォールバック設定
    class QdrantConfig:
        HOST = "localhost"
        PORT = 6333
        URL = "http://localhost:6333"
        DOCKER_IMAGE = "qdrant/qdrant"
        HEALTH_CHECK_ENDPOINT = "/collections"
        DEFAULT_TIMEOUT = 30
        DEFAULT_VECTOR_SIZE = 3072
        DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"

# ログ設定
logger = logging.getLogger(__name__)

# ===================================================================
# 定数
# ===================================================================

# Qdrant設定
QDRANT_CONFIG = {
    "name"                 : "Qdrant",
    "host"                 : QdrantConfig.HOST,
    "port"                 : QdrantConfig.PORT,
    "icon"                 : "🎯",
    "url"                  : QdrantConfig.URL,
    "health_check_endpoint": QdrantConfig.HEALTH_CHECK_ENDPOINT,
    "docker_image"         : QdrantConfig.DOCKER_IMAGE,
}

# デフォルト埋め込みモデル
DEFAULT_EMBEDDING_MODEL = QdrantConfig.DEFAULT_EMBEDDING_MODEL
DEFAULT_VECTOR_SIZE = QdrantConfig.DEFAULT_VECTOR_SIZE

# =====================================================
# Gemini 3 Migration: プロバイダー設定
# =====================================================
DEFAULT_EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai")  # [MIGRATION] "gemini" → "openai"

# プロバイダー別のデフォルト設定
PROVIDER_DEFAULTS = {
    "gemini"   : {
        "model": "gemini-embedding-001",
        "dims" : DEFAULT_GEMINI_EMBEDDING_DIMS,  # 3072
    },
    "openai"   : {
        "model": "text-embedding-3-small",
        "dims" : DEFAULT_OPENAI_EMBEDDING_DIMS,  # 1536
    },
    "fastembed": {
        "model": "BAAI/bge-small-en-v1.5",
        "dims" : 384,
    },
}

# コレクション固有の埋め込み設定（レガシー: OpenAI用）
# [DEPRECATED] Phase 4 STEP 11: 現在の検索は DEFAULT_EMBEDDING_PROVIDER=gemini (3072次元) を使用。
# これらの OpenAI 1536次元コレクションが Qdrant に残存している場合、次元数不整合で検索失敗する。
# 旧コレクション (qa_corpus, qa_cc_news_*, qa_livedoor_*) は Qdrant から削除済みか確認すること。
# 新規登録は COLLECTION_EMBEDDINGS_GEMINI または PROVIDER_DEFAULTS を使用すること。
COLLECTION_EMBEDDINGS = {
    "qa_corpus"             : {"model": "text-embedding-3-small", "dims": 1536},
    "qa_cc_news_a02_llm"    : {"model": "text-embedding-3-small", "dims": 1536},
    "qa_cc_news_a03_rule"   : {"model": "text-embedding-3-small", "dims": 1536},
    "qa_cc_news_a10_hybrid" : {"model": "text-embedding-3-small", "dims": 1536},
    "qa_livedoor_a02_20_llm": {"model": "text-embedding-3-small", "dims": 1536},
    "qa_livedoor_a03_rule"  : {"model": "text-embedding-3-small", "dims": 1536},
    "qa_livedoor_a10_hybrid": {"model": "text-embedding-3-small", "dims": 1536},
}

# Gemini 3対応コレクション設定（3072次元）
COLLECTION_EMBEDDINGS_GEMINI = {
    "qa_corpus_gemini"  : {"provider": "gemini", "model": "gemini-embedding-001", "dims": 3072},
    "qa_cc_news_gemini" : {"provider": "gemini", "model": "gemini-embedding-001", "dims": 3072},
    "qa_livedoor_gemini": {"provider": "gemini", "model": "gemini-embedding-001", "dims": 3072},
}

# コレクション名とCSVファイルのマッピング
COLLECTION_CSV_MAPPING = {
    "qa_cc_news_a02_llm"    : "a02_qa_pairs_cc_news.csv",
    "qa_cc_news_a03_rule"   : "a03_qa_pairs_cc_news.csv",
    "qa_cc_news_a10_hybrid" : "a10_qa_pairs_cc_news.csv",
    "qa_livedoor_a02_20_llm": "a02_qa_pairs_livedoor.csv",
    "qa_livedoor_a03_rule"  : "a03_qa_pairs_livedoor.csv",
    "qa_livedoor_a10_hybrid": "a10_qa_pairs_livedoor.csv",
}


# ===================================================================
# ユーティリティ関数
# ===================================================================

def batched(seq: Iterable, size: int):
    """
    イテラブルをバッチに分割
    Args:
        seq: 分割対象のイテラブル
        size: バッチサイズ
    Yields:
        バッチリスト
    """
    buf = []
    for x in seq:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


# ===================================================================
# Qdrant接続・ヘルスチェック
# ===================================================================

class QdrantHealthChecker:
    """Qdrantサーバーの接続状態をチェック"""

    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode
        self.client = None

    def check_port(self, host: str, port: int, timeout: float = 2.0) -> bool:
        """
        ポートが開いているかチェック
        Args:
            host: ホスト名
            port: ポート番号
            timeout: タイムアウト秒数
        Returns:
            ポートが開いているかどうか
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception as e:
            if self.debug_mode:
                logger.error(f"Port check failed for {host}:{port}: {e}")
            return False

    def check_qdrant(self) -> Tuple[bool, str, Optional[Dict]]:
        """
        Qdrant接続チェック
        Returns:
            (接続成功フラグ, メッセージ, メトリクス)
        """
        start_time = time.time()

        # ポートチェック
        if not self.check_port(QDRANT_CONFIG["host"], QDRANT_CONFIG["port"]):
            return False, "Connection refused (port closed)", None

        try:
            self.client = QdrantClient(url=QDRANT_CONFIG["url"], timeout=5)

            # コレクション取得
            collections = self.client.get_collections()

            metrics = {
                "collection_count": len(collections.collections),
                "collections"     : [c.name for c in collections.collections],
                "response_time_ms": round((time.time() - start_time) * 1000, 2),
            }

            return True, "Connected", metrics

        except Exception as e:
            error_msg = str(e)
            if self.debug_mode:
                error_msg = f"{error_msg}\n{traceback.format_exc()}"
            return False, error_msg, None

    def get_client(self) -> Optional[QdrantClient]:
        """接続済みクライアントを取得"""
        return self.client


def create_qdrant_client(url: str = None, timeout: int = 30) -> QdrantClient:
    """
    Qdrantクライアントを作成
    Args:
        url: QdrantサーバーURL（デフォルト: localhost:6333）
        timeout: タイムアウト秒数
    Returns:
        QdrantClientインスタンス
    """
    url = url or QDRANT_CONFIG["url"]
    return QdrantClient(url=url, timeout=timeout)


# シングルトン QdrantClient（Phase 2 STEP 4 改善）
_qdrant_client: Optional[QdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    """
    QdrantClient のシングルトンインスタンスを取得

    アプリケーション全体で1つの接続プールを共有し、
    リソース効率と設定一貫性を確保する。

    Returns:
        QdrantClientインスタンス（シングルトン）
    """
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            url=QDRANT_CONFIG["url"],
            timeout=QdrantConfig.DEFAULT_TIMEOUT
        )
        logger.info(f"QdrantClient シングルトン作成: url={QDRANT_CONFIG['url']}")
    return _qdrant_client


# ===================================================================
# EmbeddingClient シングルトンキャッシュ（Phase 2 STEP 5 改善）
# ===================================================================

_embedding_clients: Dict[str, EmbeddingClient] = {}


def get_embedding_client(provider: str = None) -> EmbeddingClient:
    """
    EmbeddingClient のキャッシュ済みインスタンスを取得

    プロバイダーごとに1つのインスタンスを保持し、
    毎回の create_embedding_client() 呼び出しを排除する。

    Args:
        provider: "gemini" or "openai"（Noneの場合はデフォルト）

    Returns:
        EmbeddingClientインスタンス（キャッシュ済み）
    """
    provider = provider or DEFAULT_EMBEDDING_PROVIDER
    if provider not in _embedding_clients:
        _embedding_clients[provider] = create_embedding_client(provider=provider)
        logger.info(f"EmbeddingClient キャッシュ作成: provider={provider}")
    return _embedding_clients[provider]


_sparse_embedding_clients: Dict[str, Any] = {}


def get_cached_sparse_embedding_client(model_name: str = None):
    """
    Sparse EmbeddingClient のキャッシュ済みインスタンスを取得

    Args:
        model_name: 使用するSparseモデル名（Noneの場合はデフォルト）

    Returns:
        Sparse EmbeddingClientインスタンス（キャッシュ済み）
    """
    cache_key = model_name or "_default"
    if cache_key not in _sparse_embedding_clients:
        _sparse_embedding_clients[cache_key] = get_sparse_embedding_client(model_name)
        logger.info(f"Sparse EmbeddingClient キャッシュ作成: model={model_name}")
    return _sparse_embedding_clients[cache_key]


# ===================================================================
# コレクション管理
# ===================================================================

def get_collection_stats(
        client: QdrantClient, collection_name: str
) -> Optional[Dict[str, Any]]:
    """
    コレクションの統計情報を取得

    Args:
        client: Qdrantクライアント
        collection_name: コレクション名

    Returns:
        統計情報辞書（存在しない場合はNone）
    """
    try:
        collection_info = client.get_collection(collection_name)
        total_points = collection_info.points_count

        # ベクトル設定情報を取得
        vectors_config = collection_info.config.params.vectors
        vector_info = {}

        if isinstance(vectors_config, dict):
            # Named Vectors
            for name, config in vectors_config.items():
                vector_info[name] = {
                    "size"    : config.size,
                    "distance": str(config.distance),
                }
        elif hasattr(vectors_config, "size"):
            # Single Vector
            vector_info["default"] = {
                "size"    : vectors_config.size,
                "distance": str(vectors_config.distance),
            }

        return {
            "total_points" : total_points,
            "vector_config": vector_info,
            "status"       : collection_info.status,
        }

    except UnexpectedResponse as e:
        if "doesn't exist" in str(e) or "not found" in str(e).lower():
            return None
        raise
    except Exception as e:
        logger.error(f"統計情報取得エラー: {e}")
        return None


def get_all_collections(client: QdrantClient) -> List[Dict[str, Any]]:
    """
    全コレクションの情報を取得
    Args:
        client: Qdrantクライアント
    Returns:
        コレクション情報のリスト
    """
    collections = client.get_collections()
    collection_list = []

    for collection in collections.collections:
        try:
            info = client.get_collection(collection.name)
            collection_list.append(
                {
                    "name"        : collection.name,
                    "points_count": info.points_count,
                    "status"      : info.status,
                }
            )
        except Exception:
            collection_list.append(
                {"name": collection.name, "points_count": 0, "status": "unknown"}
            )

    return collection_list


def delete_all_collections(client: QdrantClient, excluded: List[str] = None) -> int:
    """
    全コレクションを削除

    Args:
        client: Qdrantクライアント
        excluded: 除外するコレクション名のリスト

    Returns:
        削除されたコレクション数
    """
    excluded = excluded or []
    collections = get_all_collections(client)

    if not collections:
        return 0

    to_delete = [c for c in collections if c["name"] not in excluded]

    if not to_delete:
        return 0

    deleted_count = 0

    for col in to_delete:
        try:
            client.delete_collection(collection_name=col["name"])
            deleted_count += 1
        except Exception as e:
            logger.error(f"コレクション削除エラー {col['name']}: {e}")

    return deleted_count


def create_or_recreate_collection(
        client: QdrantClient,
        name: str,
        recreate: bool = False,
        vector_size: int = DEFAULT_VECTOR_SIZE,
        use_sparse: bool = False
):
    """
    コレクション作成または再作成

    Args:
        client: Qdrantクライアント
        name: コレクション名
        recreate: 再作成フラグ
        vector_size: ベクトル次元数
        use_sparse: Sparse Vector (Hybrid Search) を有効にするか
    """
    # Dense Vector設定
    vectors_config = models.VectorParams(
        size=vector_size, distance=models.Distance.COSINE
    )

    # Sparse Vector設定
    sparse_vectors_config = None
    if use_sparse:
        sparse_vectors_config = {
            "text-sparse": models.SparseVectorParams(
                index=models.SparseIndexParams(
                    on_disk=False,  # メモリ上に保持して高速化（大規模ならTrue）
                )
            )
        }

    if recreate:
        try:
            client.delete_collection(collection_name=name)
        except Exception:
            pass
        client.create_collection(
            collection_name=name,
            vectors_config=vectors_config,
            sparse_vectors_config=sparse_vectors_config
        )
    else:
        try:
            client.get_collection(name)
        except Exception:
            client.create_collection(
                collection_name=name,
                vectors_config=vectors_config,
                sparse_vectors_config=sparse_vectors_config
            )

    # ペイロード索引を作成
    try:
        client.create_payload_index(
            name, field_name="domain", field_schema=models.PayloadSchemaType.KEYWORD
        )
    except Exception:
        pass


# ===================================================================
# データ読み込み・変換
# ===================================================================

def load_csv_for_qdrant(
        path: str, required=("question", "answer"), limit: int = 0
) -> pd.DataFrame:
    """
    CSVをロード（Qdrant登録用）

    Args:
        path: CSVファイルパス
        required: 必須カラム
        limit: 行数制限（0=無制限）

    Returns:
        DataFrame
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"CSV not found: {path}")
    df = pd.read_csv(path)

    # 列名マッピング
    column_mappings = {
        "Question"      : "question",
        "Response"      : "answer",
        "Answer"        : "answer",
        "correct_answer": "answer",
    }
    df = df.rename(columns=column_mappings)

    for col in required:
        if col not in df.columns:
            raise ValueError(
                f"{path} には '{col}' 列が必要です（列: {list(df.columns)}）"
            )

    df = df.fillna("").drop_duplicates(subset=list(required)).reset_index(drop=True)

    if limit and limit > 0:
        df = df.head(limit).copy()

    return df


def build_inputs_for_embedding(df: pd.DataFrame, include_answer: bool) -> List[str]:
    """
    埋め込み用入力テキストを構築

    Args:
        df: DataFrame
        include_answer: answerを含めるかどうか

    Returns:
        テキストのリスト
    """
    if include_answer:
        return (df["question"].astype(str) + "\n" + df["answer"].astype(str)).tolist()
    return df["question"].astype(str).tolist()


# ===================================================================
# 埋め込み生成
# ===================================================================

def embed_texts(
        texts: List[str],
        model: str = DEFAULT_EMBEDDING_MODEL,
        batch_size: int = 128
) -> List[List[float]]:
    """
    テキストをバッチ処理でEmbeddingに変換（Gemini API使用）

    Args:
        texts: テキストリスト
        model: 埋め込みモデル名（互換性のため保持、Geminiを使用）
        batch_size: バッチサイズ

    Returns:
        埋め込みベクトルのリスト
    """
    # Gemini統合関数に委譲
    return embed_texts_unified(texts, provider="openai", batch_size=batch_size)  # [MIGRATION] "gemini" → "openai"


def embed_query(
        text: str,
        model: str = DEFAULT_EMBEDDING_MODEL,
        dims: Optional[int] = None
) -> List[float]:
    """
    クエリテキストを埋め込みベクトルに変換（Gemini API使用）

    Args:
        text: 埋め込むテキスト
        model: 使用する埋め込みモデル（互換性のため保持、Geminiを使用）
        dims: ベクトルの次元数（Geminiでは3072次元）

    Returns:
        埋め込みベクトル
    """
    # Gemini統合関数に委譲
    return embed_query_unified(text, provider="openai")  # [MIGRATION] "gemini" → "openai"


# =====================================================
# Gemini 3 Migration: 抽象化レイヤーを使用した埋め込み関数
# =====================================================

def embed_texts_unified(
        texts: List[str],
        provider: str = None,
        batch_size: int = 100
) -> List[List[float]]:
    """
    テキストをEmbeddingに変換（プロバイダー抽象化版）

    Gemini 3 Migration対応: OpenAIとGeminiの両方に対応

    Args:
        texts: テキストリスト
        provider: "gemini" or "openai"（Noneの場合はデフォルト）
        batch_size: バッチサイズ

    Returns:
        埋め込みベクトルのリスト（Gemini: 3072次元, OpenAI: 1536次元）

    Example:
        # Gemini Embedding（3072次元）
        vectors = embed_texts_unified(texts, provider="gemini")

        # OpenAI Embedding（1536次元）
        vectors = embed_texts_unified(texts, provider="openai")
    """
    provider = provider or DEFAULT_EMBEDDING_PROVIDER
    embedding_client = get_embedding_client(provider=provider)

    # 空文字列・空白のみの文字列を除外して処理
    valid_texts = []
    valid_indices = []
    for i, text in enumerate(texts):
        if text and text.strip():
            valid_texts.append(text)
            valid_indices.append(i)

    if not valid_texts:
        logger.warning("全てのテキストが空文字列です。ダミーベクトルを返します。")
        dims = get_embedding_dimensions(provider)
        return [[0.0] * dims] * len(texts)

    # 抽象化レイヤーを使用してEmbedding生成
    valid_vecs = embedding_client.embed_texts(valid_texts, batch_size=batch_size)

    # 元のインデックスに合わせてベクトルを再配置
    dims = embedding_client.dimensions
    vecs: List[List[float]] = []
    valid_vec_idx = 0
    for i in range(len(texts)):
        if i in valid_indices:
            vecs.append(valid_vecs[valid_vec_idx])
            valid_vec_idx += 1
        else:
            vecs.append([0.0] * dims)

    return vecs


def embed_query_unified(
        text: str,
        provider: str = None
) -> List[float]:
    """
    クエリテキストを埋め込みベクトルに変換（プロバイダー抽象化版）

    Gemini 3 Migration対応: OpenAIとGeminiの両方に対応

    Args:
        text: 埋め込むテキスト
        provider: "gemini" or "openai"（Noneの場合はデフォルト）

    Returns:
        埋め込みベクトル（Gemini: 3072次元, OpenAI: 1536次元）

    Example:
        # Gemini Embedding（3072次元）
        vector = embed_query_unified("検索クエリ", provider="gemini")
    """
    provider = provider or DEFAULT_EMBEDDING_PROVIDER
    embedding_client = get_embedding_client(provider=provider)
    # return embedding_client.embed_text(text)
    return embedding_client.embed_text(text, task_type="retrieval_query")


def embed_sparse_texts_unified(
        texts: List[str],
        model_name: str = None,
        batch_size: int = 4,
        progress_callback: Any = None
) -> List[models.SparseVector]:
    """
    テキストをSparse Embedding (キーワードベクトル) に変換

    Args:
        texts: テキストリスト
        model_name: 使用するSparseモデル（Noneの場合はデフォルト）
        batch_size: バッチサイズ
        progress_callback: 進捗コールバック関数 (current, total) -> None

    Returns:
        Qdrant用SparseVectorオブジェクトのリスト
    """
    sparse_client = get_cached_sparse_embedding_client(model_name)

    # 空文字列・空白のみの文字列を除外して処理
    valid_texts = []
    valid_indices = []
    for i, text in enumerate(texts):
        if text and text.strip():
            valid_texts.append(text)
            valid_indices.append(i)

    if not valid_texts:
        return [models.SparseVector(indices=[], values=[])] * len(texts)

    # Sparse Embedding生成
    raw_sparse_vecs = sparse_client.embed_texts(
        valid_texts,
        batch_size=batch_size,
        progress_callback=progress_callback
    )

    # Qdrantモデルに変換して元の順序に戻す
    sparse_vecs: List[models.SparseVector] = []
    valid_vec_idx = 0

    for i in range(len(texts)):
        if i in valid_indices:
            raw = raw_sparse_vecs[valid_vec_idx]
            sparse_vecs.append(models.SparseVector(
                indices=raw["indices"],
                values=raw["values"]
            ))
            valid_vec_idx += 1
        else:
            sparse_vecs.append(models.SparseVector(indices=[], values=[]))

    return sparse_vecs


def embed_sparse_query_unified(
        text: str,
        model_name: str = None
) -> models.SparseVector:
    """
    クエリテキストをSparse Embeddingに変換

    Args:
        text: クエリテキスト
        model_name: 使用するSparseモデル

    Returns:
        Qdrant用SparseVector
    """
    sparse_client = get_cached_sparse_embedding_client(model_name)
    raw = sparse_client.embed_text(text)
    return models.SparseVector(
        indices=raw["indices"],
        values=raw["values"]
    )


def create_collection_for_provider(
        client: QdrantClient,
        name: str,
        provider: str = None,
        recreate: bool = False,
        use_sparse: bool = False
):
    """
    プロバイダーに応じた次元数でコレクションを作成

    Gemini 3 Migration対応: 次元数を自動設定

    Args:
        client: Qdrantクライアント
        name: コレクション名
        provider: "gemini" or "openai"
        recreate: 再作成フラグ
        use_sparse: Hybrid Search用Sparse Vectorを有効化

    Example:
        # Gemini用コレクション（3072次元 + Sparse）
        create_collection_for_provider(client, "qa_gemini", provider="gemini", use_sparse=True)
    """
    provider = provider or DEFAULT_EMBEDDING_PROVIDER
    vector_size = get_embedding_dimensions(provider)

    logger.info(
        f"Creating collection '{name}' with {vector_size} dimensions (provider: {provider}, sparse: {use_sparse})")

    create_or_recreate_collection(
        client=client,
        name=name,
        recreate=recreate,
        vector_size=vector_size,
        use_sparse=use_sparse
    )


def get_provider_vector_size(provider: str = None) -> int:
    """
    プロバイダーに応じたベクトル次元数を取得

    Args:
        provider: "gemini" or "openai"

    Returns:
        次元数（Gemini: 3072, OpenAI: 1536）
    """
    provider = provider or DEFAULT_EMBEDDING_PROVIDER
    return get_embedding_dimensions(provider)


# ===================================================================
# ポイント作成・アップサート
# ===================================================================

def build_points(
        df: pd.DataFrame,
        vectors: List[List[float]],
        domain: str,
        source_file: str
) -> List[models.PointStruct]:
    """
    Qdrantポイントを構築

    Args:
        df: DataFrame
        vectors: 埋め込みベクトル
        domain: ドメイン名
        source_file: ソースファイル名

    Returns:
        PointStructのリスト
    """
    n = len(df)
    if len(vectors) != n:
        raise ValueError(f"vectors length mismatch: df={n}, vecs={len(vectors)}")

    now_iso = datetime.now(timezone.utc).isoformat()
    points: List[models.PointStruct] = []

    for i, row in enumerate(df.itertuples(index=False)):
        payload = {
            "domain"    : domain,
            "question"  : getattr(row, "question"),
            "answer"    : getattr(row, "answer"),
            "source"    : os.path.basename(source_file),
            "created_at": now_iso,
            "schema"    : "qa:v1",
        }

        pid = abs(hash(f"{domain}-{source_file}-{i}")) & 0x7FFFFFFFFFFFFFFF
        points.append(models.PointStruct(id=pid, vector=vectors[i], payload=payload))

    return points


def upsert_points(
        client: QdrantClient,
        collection: str,
        points: List[models.PointStruct],
        batch_size: int = 128,
) -> int:
    """
    ポイントをQdrantにアップサート

    Args:
        client: Qdrantクライアント
        collection: コレクション名
        points: ポイントリスト
        batch_size: バッチサイズ

    Returns:
        アップサートされたポイント数
    """
    count = 0
    for chunk in batched(points, batch_size):
        client.upsert(collection_name=collection, points=chunk)
        count += len(chunk)
    return count


# ===================================================================
# データ取得
# ===================================================================

class QdrantDataFetcher:
    """Qdrantからデータを取得"""

    def __init__(self, client: QdrantClient):
        self.client = client

    def fetch_collections(self) -> pd.DataFrame:
        """コレクション一覧を取得"""
        try:
            collections = self.client.get_collections()

            data = []
            for collection in collections.collections:
                try:
                    info = self.client.get_collection(collection.name)
                    data.append(
                        {
                            "Collection"     : collection.name,
                            "Vectors Count"  : info.vectors_count,
                            "Points Count"   : info.points_count,
                            "Indexed Vectors": info.indexed_vectors_count,
                            "Status"         : info.status,
                        }
                    )
                except Exception:
                    data.append(
                        {
                            "Collection"     : collection.name,
                            "Vectors Count"  : "N/A",
                            "Points Count"   : "N/A",
                            "Indexed Vectors": "N/A",
                            "Status"         : "Error",
                        }
                    )

            return (
                pd.DataFrame(data)
                if data
                else pd.DataFrame({"Info": ["No collections found"]})
            )

        except Exception as e:
            return pd.DataFrame({"Error": [str(e)]})

    def fetch_collection_points(
            self, collection_name: str, limit: int = 50
    ) -> pd.DataFrame:
        """コレクションの詳細データを取得"""
        try:
            # スクロールを使ってポイントを取得
            points_result = self.client.scroll(
                collection_name=collection_name,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            points = points_result[0]  # scrollは (points, next_offset) のタプルを返す

            if not points:
                return pd.DataFrame({"Info": ["No points found in collection"]})

            # ポイントをDataFrameに変換
            data = []
            for point in points:
                row = {"ID": point.id}

                # payloadの各フィールドを列として追加
                if point.payload:
                    for key, value in point.payload.items():
                        # 長すぎる文字列は切り詰め
                        if isinstance(value, str) and len(value) > 200:
                            row[key] = value[:200] + "..."
                        elif isinstance(value, (list, dict)):
                            row[key] = (
                                str(value)[:200] + "..."
                                if len(str(value)) > 200
                                else str(value)
                            )
                        else:
                            row[key] = value

                data.append(row)

            return pd.DataFrame(data)

        except Exception as e:
            return pd.DataFrame({"Error": [str(e)]})

    def fetch_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """コレクションの詳細情報を取得"""
        try:
            collection_info = self.client.get_collection(collection_name)

            # configの構造を安全にアクセス
            vector_config = collection_info.config.params.vectors

            # vector_configの型を判定して適切に処理
            if hasattr(vector_config, "size"):
                # 単一ベクトル設定
                vector_size = vector_config.size
                distance = vector_config.distance
            elif hasattr(vector_config, "__iter__"):
                # Named vectors設定の場合
                vector_sizes = {}
                distances = {}
                for name, config in (
                        vector_config.items() if isinstance(vector_config, dict) else []
                ):
                    vector_sizes[name] = (
                        config.size if hasattr(config, "size") else "N/A"
                    )
                    distances[name] = (
                        config.distance if hasattr(config, "distance") else "N/A"
                    )
                vector_size = vector_sizes if vector_sizes else "N/A"
                distance = distances if distances else "N/A"
            else:
                vector_size = "N/A"
                distance = "N/A"

            return {
                "vectors_count"  : collection_info.vectors_count,
                "points_count"   : collection_info.points_count,
                "indexed_vectors": collection_info.indexed_vectors_count,
                "status"         : collection_info.status,
                "config"         : {
                    "vector_size": vector_size,
                    "distance"   : distance,
                },
            }
        except Exception as e:
            return {"error": str(e)}

    def fetch_collection_source_info(
            self, collection_name: str, sample_size: int = 200
    ) -> Dict[str, Any]:
        """コレクションのデータソース情報を取得"""
        try:
            collection_info = self.client.get_collection(collection_name)
            total_points = collection_info.points_count

            # サンプルポイントを取得
            points_result = self.client.scroll(
                collection_name=collection_name,
                limit=min(sample_size, total_points),
                with_payload=True,
                with_vectors=False,
            )

            points = points_result[0]

            if not points:
                return {"total_points": total_points, "sources": {}, "sample_size": 0}

            # sourceとgeneration_methodを集計
            source_stats = {}
            for point in points:
                if point.payload:
                    source = point.payload.get("source", "unknown")
                    method = point.payload.get("generation_method", "unknown")
                    domain = point.payload.get("domain", "unknown")

                    if source not in source_stats:
                        source_stats[source] = {
                            "sample_count": 0,
                            "method"      : method,
                            "domain"      : domain,
                        }
                    source_stats[source]["sample_count"] += 1

            # 全体のデータ数を推定
            sample_total = len(points)
            for source, stats in source_stats.items():
                ratio = stats["sample_count"] / sample_total
                stats["estimated_total"] = int(total_points * ratio)
                stats["percentage"] = ratio * 100

            return {
                "total_points": total_points,
                "sources"     : source_stats,
                "sample_size" : sample_total,
            }

        except Exception as e:
            return {"error": str(e)}


# ===================================================================
# 検索
# ===================================================================

# ベクトル設定キャッシュ（Phase 3 STEP 6 改善）
_vector_config_cache: Dict[str, dict] = {}


def _get_vector_config(client: QdrantClient, collection_name: str) -> dict:
    """
    コレクションのベクトル設定をキャッシュ付きで取得

    並列検索時に同一コレクションへの get_collection() 重複呼び出しを排除する。
    """
    if collection_name not in _vector_config_cache:
        collection_info = client.get_collection(collection_name)
        vectors_config = collection_info.config.params.vectors
        _vector_config_cache[collection_name] = {
            "is_named_vector": isinstance(vectors_config, dict),
            "dense_vector_name": "default" if isinstance(vectors_config, dict) else None
        }
        logger.debug(f"ベクトル設定キャッシュ追加: {collection_name}")
    return _vector_config_cache[collection_name]


def search_collection(
        client: QdrantClient,
        collection_name: str,
        query_vector: List[float],
        sparse_vector: Optional[models.SparseVector] = None,
        limit: int = 5,
        hybrid_alpha: float = 0.5
) -> List[Dict[str, Any]]:
    """
    コレクションを検索（Dense または Hybrid）

    Sparse Vectorエラー時は自動的にDense Vectorのみで再試行
    """
    logger.info(
        f"search_collection: collection='{collection_name}', query_vec_dim={len(query_vector)}, limit={limit}, sparse={sparse_vector is not None}")

    try:
        # Phase 3 STEP 6 改善: ベクトル設定キャッシュを使用
        config = _get_vector_config(client, collection_name)
        is_named_vector = config["is_named_vector"]
        dense_vector_name = config["dense_vector_name"]

        # Phase 3 STEP 8: 3段階フォールバック（唯一の責務）
        # 【Stage 1】Sparse Vectorが指定されている場合、Hybrid Searchを試みる
        if sparse_vector:
            try:
                logger.debug(f"【Stage 1】Hybrid Search試行: '{collection_name}'")
                # Hybrid Search (Dense + Sparse)
                prefetch = [
                    models.Prefetch(
                        query=query_vector,
                        using=dense_vector_name or "",  # 名前なしの場合は空文字
                        limit=limit * 2,
                    ),
                    models.Prefetch(
                        query=sparse_vector,
                        using="text-sparse",
                        limit=limit * 2,
                    ),
                ]

                response = client.query_points(
                    collection_name=collection_name,
                    prefetch=prefetch,
                    query=models.FusionQuery(
                        fusion=models.Fusion.RRF,
                    ),
                    limit=limit,
                )
                hits = response.points
                logger.info(f"✅ 【Stage 1】Hybrid Search成功: {collection_name}")

            except UnexpectedResponse as e:
                # Sparse Vectorエラーの場合、Dense Vectorのみで再試行
                error_msg = str(e)
                if "text-sparse" in error_msg or "sparse" in error_msg.lower():
                    logger.warning(f"⚠️ 【Stage 1→2】Sparse Vector未設定 ({collection_name}): Denseのみに切替")
                    sparse_vector = None  # Sparse Vectorを無効化して Stage 2 へ
                else:
                    # その他のエラーは再スロー
                    raise

        # 【Stage 2】Dense Search（Sparse Vectorがない、またはエラーで無効化された場合）
        if not sparse_vector:
            logger.debug(f"【Stage 2】Dense Vector only: '{collection_name}'")
            # 名前付きベクトルの場合は models.NamedVector または query(..., using=...) を使用
            if is_named_vector:
                response = client.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    using=dense_vector_name,
                    limit=limit
                )
            else:
                response = client.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    limit=limit
                )
            hits = response.points

    except Exception as e:
        logger.error(f"❌ 【Stage 2】Search failed for '{collection_name}': {e}")
        logger.error(f"   Error type: {type(e).__name__}")

        # 【Stage 3】最終フォールバック: query_pointsの最もシンプルな形式
        try:
            logger.warning(f"🔄 【Stage 3】最終フォールバック試行: '{collection_name}'")
            response = client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit
            )
            hits = response.points
            logger.info(f"✅ 【Stage 3】最終フォールバック成功: {collection_name}")
        except Exception as fallback_e:
            logger.error(f"❌ 【Stage 3】最終フォールバックも失敗: '{collection_name}': {fallback_e}")
            return []

    logger.info(f"search_collection: found {len(hits)} hits for '{collection_name}'")

    results = []
    for h in hits:
        results.append({
            "score"  : h.score,
            "id"     : h.id,
            "payload": h.payload
        })

    return results


# ===================================================================
# 後方互換性のためのエイリアス
# ===================================================================

# 旧関数名でインポートしている場合の互換性維持
embed_texts_for_qdrant = embed_texts
create_or_recreate_collection_for_qdrant = create_or_recreate_collection
build_points_for_qdrant = build_points
upsert_points_to_qdrant = upsert_points
embed_query_for_search = embed_query

# ===================================================================
# エクスポート
# ===================================================================

__all__ = [
    # 定数
    "QDRANT_CONFIG",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_VECTOR_SIZE",
    "COLLECTION_EMBEDDINGS",
    "COLLECTION_CSV_MAPPING",

    # Gemini 3 Migration: プロバイダー設定
    "DEFAULT_EMBEDDING_PROVIDER",
    "PROVIDER_DEFAULTS",
    "COLLECTION_EMBEDDINGS_GEMINI",

    # ユーティリティ
    "batched",

    # クライアント・ヘルスチェック
    "QdrantHealthChecker",
    "create_qdrant_client",
    "get_qdrant_client",

    # コレクション管理
    "get_collection_stats",
    "get_all_collections",
    "delete_all_collections",
    "create_or_recreate_collection",

    # データ読み込み
    "load_csv_for_qdrant",
    "build_inputs_for_embedding",

    # 埋め込み（レガシー: OpenAI用）
    "embed_texts",
    "embed_query",

    # Gemini 3 Migration: 埋め込み（抽象化版）
    "embed_texts_unified",
    "embed_query_unified",
    "get_embedding_client",
    "get_cached_sparse_embedding_client",
    "create_collection_for_provider",
    "get_provider_vector_size",

    # ポイント操作
    "build_points",
    "upsert_points",

    # データ取得
    "QdrantDataFetcher",

    # 検索
    "search_collection",

    # 後方互換性エイリアス
    "embed_texts_for_qdrant",
    "create_or_recreate_collection_for_qdrant",
    "build_points_for_qdrant",
    "upsert_points_to_qdrant",
    "embed_query_for_search",
]
