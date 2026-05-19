"""
Sparse Embedding (SPLADE) 実装モジュール

QdrantのHybrid Search用に、Sparse Vector (キーワード重み付きベクトル) を生成します。
FastEmbedライブラリを使用し、ローカルCPUで高速に動作します。

依存:
    pip install fastembed

使用モデル:
    デフォルト: "prithivida/Splade_PP_en_v1" (英語向け)
    ※ 日本語等の多言語対応が必要な場合は、Qdrant推奨の多言語モデルを検討
"""

import logging
from typing import List, Dict, Any, Iterable
import time

logger = logging.getLogger(__name__)

try:
    from fastembed import SparseTextEmbedding
except ImportError:
    SparseTextEmbedding = None
    logger.error("FastEmbed is not installed. Please run `pip install fastembed`.")

# Sparse Embeddingのデフォルトモデル
DEFAULT_SPARSE_MODEL = "prithivida/Splade_PP_en_v1"

class SparseEmbeddingClient:
    """Sparse Embedding生成クライアント"""

    def __init__(
        self,
        model_name: str = DEFAULT_SPARSE_MODEL,
        threads: int = None,
        cache_dir: str = None
    ):
        if SparseTextEmbedding is None:
            raise ImportError("FastEmbed library is missing.")
        
        # Handle explicit None
        if model_name is None:
            model_name = DEFAULT_SPARSE_MODEL
        
        logger.info(f"Initializing SparseEmbedding with model: {model_name}")
        self.model_name = model_name
        self._model = SparseTextEmbedding(
            model_name=model_name,
            threads=threads,
            cache_dir=cache_dir
        )

    def embed_text(self, text: str) -> Dict[int, float]:
        """
        単一テキストのSparse Embedding生成
        
        Returns:
            {index: weight, ...} 形式の辞書 (QdrantのSparseVector形式に対応可能)
        """
        # embedメソッドはジェネレータを返す
        # 戻り値は SparseEmbedding オブジェクト (indices, values)
        sparse_vectors = list(self._model.embed([text]))
        vec = sparse_vectors[0]
        
        # Qdrant用に {index: value} の辞書形式、または (indices, values) のタプルで管理
        # ここでは処理しやすいように辞書で返すことも可能だが、
        # Qdrant Clientへの渡しやすさを考慮して raw object または indices/values を返す
        return self._format_output(vec)

    def embed_texts(
        self,
        texts: List[str],
        batch_size: int = 32,
        progress_callback: Any = None
    ) -> List[Dict[str, List[Any]]]:
        """
        バッチSparse Embedding生成
        
        Args:
            texts: テキストリスト
            batch_size: バッチサイズ
            progress_callback: 進捗コールバック関数 (current, total) -> None
        
        Returns:
            [{"indices": [...], "values": [...]}, ...] のリスト
        """
        try:
            from tqdm import tqdm
            use_tqdm = True
        except ImportError:
            use_tqdm = False

        results = []
        total = len(texts)
        
        # progress_callbackが指定されている場合はそちらを優先
        if progress_callback:
            logger.info(f"Starting sparse embedding generation with callback (total={total}, batch_size={batch_size})")
            # ジェネレータではなく手動で回してコールバックを呼び出す
            for i in range(0, total, batch_size):
                batch_texts = texts[i : i + batch_size]
                # FastEmbedのembedメソッドはジェネレータを返すが、ここではリスト化して処理
                batch_results = list(self._model.embed(batch_texts, batch_size=batch_size))
                for vec in batch_results:
                    results.append(self._format_output(vec))
                
                # 進捗更新
                current = min(i + batch_size, total)
                progress_callback(current, total)
                
        else:
            # 従来通りtqdmを使用
            generator = self._model.embed(texts, batch_size=batch_size)
            if use_tqdm:
                generator = tqdm(generator, total=total, desc="Sparse Embedding", unit="docs")
                
            for vec in generator:
                results.append(self._format_output(vec))
                
        return results

    def _format_output(self, sparse_vec) -> Dict[str, List[Any]]:
        """FastEmbedの出力をQdrantが受け入れやすい形式に変換"""
        # sparse_vec は indices と values を持つ
        return {
            "indices": sparse_vec.indices.tolist(),
            "values": sparse_vec.values.tolist()
        }

# シングルトン的な利用のためのファクトリ
_sparse_client_instance = None

def get_sparse_embedding_client(model_name: str = DEFAULT_SPARSE_MODEL) -> SparseEmbeddingClient:
    # Handle explicit None passed from callers
    if model_name is None:
        model_name = DEFAULT_SPARSE_MODEL

    global _sparse_client_instance
    if _sparse_client_instance is None:
        _sparse_client_instance = SparseEmbeddingClient(model_name=model_name)
    elif _sparse_client_instance.model_name != model_name:
        _sparse_client_instance = SparseEmbeddingClient(model_name=model_name)
    return _sparse_client_instance
