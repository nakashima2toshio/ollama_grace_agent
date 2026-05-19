"""
FastEmbed (Local Embedding) 実装モジュール

helper_embedding.py の EmbeddingClient を継承し、
ローカルCPUで高速に動作する FastEmbed ライブラリを使用したベクトル化を提供します。

依存:
    pip install fastembed

使用モデル:
    デフォルト: "BAAI/bge-small-en-v1.5" (英語向け, 384次元)
    ※ 日本語対応が必要な場合は "intfloat/multilingual-e5-large" 等を検討
"""

import logging
from typing import List, Optional
from helper.helper_embedding import EmbeddingClient  # [FIXED] helper_embedding → helper.helper_embedding

logger = logging.getLogger(__name__)

try:
    from fastembed import TextEmbedding
except ImportError:
    TextEmbedding = None
    logger.error("FastEmbed is not installed. Please run `pip install fastembed`.")

# FastEmbedのデフォルト設定
# 多言語対応が必要な場合は "intfloat/multilingual-e5-large" (1024次元) などに変更
DEFAULT_FASTEMBED_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_FASTEMBED_DIMS = 384


class FastEmbedEmbedding(EmbeddingClient):
    """FastEmbedを使用したローカルEmbedding生成クラス"""

    def __init__(
            self,
            model_name: str = DEFAULT_FASTEMBED_MODEL,
            threads: Optional[int] = None,
            cache_dir: Optional[str] = None
    ):
        """
        Args:
            model_name: 使用するモデル名 (例: "BAAI/bge-small-en-v1.5")
            threads: 並列処理スレッド数 (None=全コア)
            cache_dir: モデルキャッシュディレクトリ
        """
        if TextEmbedding is None:
            raise ImportError("FastEmbed library is missing.")

        logger.info(f"Initializing FastEmbed with model: {model_name}")

        self.model_name = model_name
        self._model = TextEmbedding(
            model_name=model_name,
            threads=threads,
            cache_dir=cache_dir
        )

        # モデルから次元数を取得したいが、FastEmbedのAPI的に
        # 初期化直後に取得する明確なプロパティがない場合があるため、
        # 既知のモデルであれば定数、そうでなければ一度ダミー実行して確認する手もある。
        # ここでは単純化のため、主要モデルの次元数をマッピングするか、
        # 初回実行で特定する。今回はダミー実行で特定する安全策をとる。
        try:
            dummy_vec = list(self._model.embed(["test"]))[0]
            self._dims = len(dummy_vec)
            logger.info(f"FastEmbed dimension detected: {self._dims}")
        except Exception as e:
            logger.warning(f"Failed to detect dimensions: {e}. Fallback to default.")
            self._dims = DEFAULT_FASTEMBED_DIMS

    @property
    def dimensions(self) -> int:
        return self._dims

    def embed_text(self, text: str) -> List[float]:
        """単一テキストのEmbedding生成"""
        # embedメソッドはジェネレータを返すため list() で化かす
        # 入力が文字列単体でもリストに入れて渡す必要がある
        embeddings = list(self._model.embed([text]))
        return embeddings[0].tolist()

    def embed_texts(
            self,
            texts: List[str],
            batch_size: int = 256
    ) -> List[List[float]]:
        """
        バッチEmbedding生成
        FastEmbedは内部で並列化されているため、そのまま渡すのが効率的だが、
        メモリ管理のために batch_size 引数も考慮する（FastEmbedのembedにもbatch_sizeがある）
        """
        # ジェネレータをリスト化して返す
        # FastEmbedの embed は numpy array を yield するので tolist() する
        results = []
        for vec in self._model.embed(texts, batch_size=batch_size):
            results.append(vec.tolist())
        return results
