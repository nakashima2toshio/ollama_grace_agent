"""
Embeddingクライアント抽象化レイヤー

OpenAI / Gemini / Ollama Embeddings API に対応する統一インターフェースを提供。

[2026-04-20] anthropic_grace_agent 移植対応:
    - デフォルトプロバイダーを "gemini" → "openai" に変更
    - OpenAI デフォルトモデルを text-embedding-3-large (3072次元) に変更
    - Qdrant コレクション次元数 3072 は変更なし（Gemini と同次元）

[2026-05-20] ollama_grace_agent 移植対応:
    - OllamaEmbedding クラスを追加（nomic-embed-text / 768次元）
    - デフォルトプロバイダーを "openai" → "ollama" に変更
    - Qdrant コレクションの再作成が必要（3072次元 → 768次元）

使用例:
    from helper_embedding import create_embedding_client

    # OpenAI Embeddingクライアント（3072次元: デフォルト）
    embedding = create_embedding_client(provider="openai")
    vector = embedding.embed_text("Hello world")
    print(f"Dimensions: {len(vector)}")  # 3072

    # Gemini Embeddingクライアント（3072次元: 後方互換）
    embedding = create_embedding_client(provider="gemini")
    vector = embedding.embed_text("Hello world")

    # バッチ処理
    vectors = embedding.embed_texts(["Hello", "World"], batch_size=100)
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional
import os
import logging
import time

from dotenv import load_dotenv

# SDK imports (モジュールレベルでインポート - モック対象)
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)


# [MIGRATION] DEFAULT_OPENAI_EMBEDDING_DIMS: 1536 → 3072
# text-embedding-3-large の最大次元数。Gemini gemini-embedding-001 と同次元のため
# Qdrant コレクションの再作成は不要。
DEFAULT_GEMINI_EMBEDDING_DIMS = 3072
DEFAULT_OPENAI_EMBEDDING_DIMS = 3072  # 変更前: 1536
DEFAULT_OLLAMA_EMBEDDING_DIMS = 768   # [MIGRATION openai→ollama] nomic-embed-text


class EmbeddingClient(ABC):
    """Embeddingクライアント抽象基底クラス"""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Embedding次元数を返す"""
        pass

    @abstractmethod
    def embed_text(self, text: str, task_type: Optional[str] = None) -> List[float]:
        """
        単一テキストのEmbedding生成

        Args:
            text: 入力テキスト
            task_type: タスクタイプ (Gemini用: retrieval_query, retrieval_documentなど)
                       OpenAI では無視される。

        Returns:
            Embeddingベクトル（floatのリスト）
        """
        pass

    @abstractmethod
    def embed_texts(
        self,
        texts: List[str],
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        バッチEmbedding生成

        Args:
            texts: 入力テキストのリスト
            batch_size: バッチサイズ

        Returns:
            Embeddingベクトルのリスト
        """
        pass


class OpenAIEmbedding(EmbeddingClient):
    """OpenAI Embeddings API実装"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        # [MIGRATION] モデル変更: text-embedding-3-small → text-embedding-3-large
        # 英語・非英語ともに最高性能。dimensions=3072 で Gemini と同次元を維持。
        model: str = "text-embedding-3-large",   # 変更前: "text-embedding-3-small"
        dims: int = DEFAULT_OPENAI_EMBEDDING_DIMS  # 変更前: 1536 → 定数経由で 3072
    ):
        """
        Args:
            api_key: OpenAI APIキー（Noneの場合は環境変数から取得）
            model: 使用モデル（text-embedding-3-large 推奨）
            dims: Embedding次元数（3072: text-embedding-3-large 最大次元・Gemini と同次元）
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY が設定されていません")

        self.client = OpenAI(api_key=self.api_key)
        self.model = model
        self._dims = dims

    @property
    def dimensions(self) -> int:
        return self._dims

    def embed_text(self, text: str, task_type: Optional[str] = None) -> List[float]:
        """単一テキストのEmbedding生成"""
        # OpenAI では task_type は使用しない（Gemini 互換引数のため無視）
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self._dims  # 明示指定: 3072
        )
        return response.data[0].embedding

    def embed_texts(
        self,
        texts: List[str],
        batch_size: int = 100
    ) -> List[List[float]]:
        """バッチEmbedding生成"""
        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self._dims  # 明示指定: 3072
            )

            # レスポンスはindex順にソートされていない場合があるため、ソート
            sorted_data = sorted(response.data, key=lambda x: x.index)
            batch_embeddings = [item.embedding for item in sorted_data]
            all_embeddings.extend(batch_embeddings)

            # レート制限対策
            if i + batch_size < len(texts):
                time.sleep(0.1)

        return all_embeddings


class OllamaEmbedding(EmbeddingClient):
    """Ollama Embeddings API 実装（OpenAI SDK 流用 / nomic-embed-text / 768次元）

    [MIGRATION openai→ollama] 2026-05-20
    - OpenAI SDK の base_url を差し替えて Ollama の OpenAI 互換エンドポイントを使用
    - dimensions パラメータ非対応（モデル固定次元数）
    - API キー不要（api_key="ollama" はダミー値）
    - Qdrant コレクション再作成必須（3072次元 → 768次元）
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "nomic-embed-text",
        dims: int = DEFAULT_OLLAMA_EMBEDDING_DIMS,
    ):
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.client = OpenAI(base_url=self.base_url, api_key="ollama")
        self.model = model
        self._dims = dims
        logger.info(f"OllamaEmbedding initialized: model={model}, dims={dims}, base_url={self.base_url}")

    @property
    def dimensions(self) -> int:
        return self._dims

    def embed_text(self, text: str, task_type: Optional[str] = None) -> List[float]:
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
            # dimensions パラメータは Ollama では非対応（指定しない）
        )
        return response.data[0].embedding

    def embed_texts(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
            )
            sorted_data = sorted(response.data, key=lambda x: x.index)
            all_embeddings.extend([item.embedding for item in sorted_data])
            if i + batch_size < len(texts):
                time.sleep(0.05)
        return all_embeddings


class GeminiEmbedding(EmbeddingClient):
    """Gemini Embeddings API実装（3072次元: 後方互換として残存）

    Note:
        anthropic_grace_agent ではデフォルトプロバイダーは OpenAI に変更済み。
        本クラスは gemini_grace_agent との後方互換および比較検証用として残す。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-embedding-001",
        dims: int = DEFAULT_GEMINI_EMBEDDING_DIMS
    ):
        """
        Args:
            api_key: Gemini APIキー（Noneの場合は環境変数から取得）
            model: 使用モデル
            dims: Embedding次元数（3072推奨: Gemini 3最大精度）
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY が設定されていません")

        try:
            from google import genai as _genai
        except ImportError:
            raise ImportError(
                "google-genai が未インストールです: pip install google-genai"
            )
        self.client = _genai.Client(api_key=self.api_key)

        self.model = model
        self._dims = dims

        logger.info(f"GeminiEmbedding initialized: model={model}, dims={dims}")

    @property
    def dimensions(self) -> int:
        return self._dims

    def embed_text(self, text: str, task_type: Optional[str] = None) -> List[float]:
        """単一テキストのEmbedding生成（3072次元）"""
        config: dict[str, Any] = {"output_dimensionality": self._dims}

        if task_type:
            config["task_type"] = task_type

        kwargs = {
            "model": self.model,
            "contents": text,
            "config": config
        }

        response = self.client.models.embed_content(**kwargs)
        return response.embeddings[0].values

    def embed_texts(
        self,
        texts: List[str],
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        バッチEmbedding生成

        Gemini APIのバッチ機能（contentsにリストを渡す）を使用して高速化
        """
        all_embeddings: List[List[float]] = []
        total = len(texts)
        start_time = time.time()

        logger.info(f"[Embedding] 開始: {total}件のテキストを処理します (Batch Size: {batch_size})")

        # Gemini API restriction: max 100 per batch
        if batch_size > 100:
            logger.warning(f"[Embedding] Batch size {batch_size} exceeds Gemini limit (100). Clamping to 100.")
            batch_size = 100

        for i in range(0, total, batch_size):
            batch_texts = texts[i: i + batch_size]

            try:
                response = self.client.models.embed_content(
                    model=self.model,
                    contents=batch_texts,
                    config={
                        "output_dimensionality": self._dims,
                        "task_type": "retrieval_document"
                    }
                )

                if hasattr(response, "embeddings") and response.embeddings:
                    batch_embeddings = [e.values for e in response.embeddings]
                    all_embeddings.extend(batch_embeddings)
                else:
                    raise ValueError("No embeddings returned in response")

                current_count = min(i + batch_size, total)
                elapsed = time.time() - start_time
                logger.info(f"[Embedding] 進捗: {current_count}/{total} (Batch {i // batch_size + 1}) 経過={elapsed:.1f}秒")

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[Embedding] Batch error at index {i}: {e}")
                logger.warning("Error batch filled with zero vectors to maintain alignment.")
                zeros = [[0.0] * self._dims] * len(batch_texts)
                all_embeddings.extend(zeros)
                time.sleep(2.0)

        elapsed_total = time.time() - start_time
        logger.info(f"[Embedding] 完了: {total}件, 所要時間={elapsed_total:.1f}秒")

        return all_embeddings

    def embed_texts_batch(
        self,
        texts: List[str]
    ) -> List[List[float]]:
        """
        バッチEmbedding生成（Gemini Batch API使用）

        Note: 大量データの場合はBatch APIを使用すると50%割引
              現時点では通常のAPIを使用（Batch API実装は将来対応）
        """
        return self.embed_texts(texts)


def create_embedding_client(
    provider: str = "ollama",  # [MIGRATION openai→ollama] デフォルト変更: "openai" → "ollama"
    **kwargs
) -> EmbeddingClient:
    """
    Embeddingクライアントのファクトリ関数

    Args:
        provider: "openai", "gemini", or "fastembed"
                  デフォルト: "openai"（anthropic_grace_agent 移植後）
        **kwargs: クライアント初期化パラメータ

    Returns:
        EmbeddingClientインスタンス

    Example:
        # OpenAI Embedding（3072次元: デフォルト）
        embedding = create_embedding_client("openai")

        # Gemini Embedding（3072次元: 後方互換）
        embedding = create_embedding_client("gemini")

        # FastEmbed (Local, default 384 dims)
        embedding = create_embedding_client("fastembed")
    """
    if provider is None:
        logger.warning("Provider is None. Defaulting to 'ollama'.")
        provider = "ollama"  # [MIGRATION openai→ollama]

    if provider.lower() == "ollama":
        return OllamaEmbedding(**kwargs)
    elif provider.lower() == "openai":
        return OpenAIEmbedding(**kwargs)
    elif provider.lower() == "gemini":
        return GeminiEmbedding(**kwargs)
    elif provider.lower() == "fastembed":
        try:
            from helper.helper_embedding_fastembed import FastEmbedEmbedding
            return FastEmbedEmbedding(**kwargs)
        except ImportError as e:
            raise ImportError(f"FastEmbed module load failed: {e}. Check if 'fastembed' is installed.")
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'ollama', 'openai', 'gemini', or 'fastembed'")


# [MIGRATION openai→ollama] デフォルトプロバイダー変更: "openai" → "ollama"
# 環境変数 EMBEDDING_PROVIDER で上書き可能（.env に EMBEDDING_PROVIDER=ollama を追加推奨）
DEFAULT_EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama")  # 変更前: "openai"


def get_default_embedding_client(**kwargs) -> EmbeddingClient:
    """デフォルト設定でEmbeddingクライアントを取得"""
    return create_embedding_client(DEFAULT_EMBEDDING_PROVIDER, **kwargs)


# Qdrant用のヘルパー関数

# [BUG FIX] EMBEDDING_PRICING が未定義のため NameError が発生していた。
# migration 資料に定義は含まれていないため、暫定的に空辞書で定義する。
# 正式な価格表は migration 資料 §9 を参照のこと。
EMBEDDING_PRICING: dict = {
    "text-embedding-3-large": 0.00013,   # $0.00013 / 1K tokens（OpenAI 公式）
    "text-embedding-3-small": 0.00002,
    "text-embedding-ada-002": 0.00010,
    "gemini-embedding-001": 0.0,         # Gemini 価格は別途確認
}


def get_embedding_model_pricing(model_name: str) -> float:
    """Embeddingモデルの価格を取得"""
    return EMBEDDING_PRICING.get(model_name, 0.0)


def get_embedding_dimensions(provider: str = "openai") -> int:  # 変更前: "gemini"
    """
    指定プロバイダーのデフォルトEmbedding次元数を取得

    Qdrantコレクション作成時に使用

    Args:
        provider: "openai", "gemini", or "fastembed"

    Returns:
        次元数
    """
    if provider is None:
        provider = "ollama"  # [MIGRATION openai→ollama]

    if provider.lower() == "ollama":
        return DEFAULT_OLLAMA_EMBEDDING_DIMS  # 768
    elif provider.lower() == "gemini":
        return DEFAULT_GEMINI_EMBEDDING_DIMS  # 3072
    elif provider.lower() == "openai":
        return DEFAULT_OPENAI_EMBEDDING_DIMS  # 3072
    elif provider.lower() == "fastembed":
        return 384
    else:
        raise ValueError(f"Unknown provider: {provider}")


if __name__ == "__main__":
    # 簡易テスト
    print("EmbeddingClient テスト")
    print("=" * 40)

    try:
        # OpenAI Embeddingテスト（メイン）
        print("\n[OpenAI Embedding Test] text-embedding-3-large / 3072次元")
        openai_emb = create_embedding_client("openai")
        print(f"Dimensions: {openai_emb.dimensions}")

        vector = openai_emb.embed_text("これはテストです")
        print(f"Vector length: {len(vector)}")
        print(f"First 5 values: {vector[:5]}")

        if len(vector) == DEFAULT_OPENAI_EMBEDDING_DIMS:
            print(f"[OK] 3072次元の検証: PASS")
        else:
            print(f"[NG] 3072次元の検証: FAIL (actual: {len(vector)})")

    except Exception as e:
        print(f"OpenAI Error: {e}")

    try:
        # Gemini Embeddingテスト（後方互換確認）
        print("\n[Gemini Embedding Test] gemini-embedding-001 / 3072次元（後方互換）")
        gemini = create_embedding_client("gemini")
        print(f"Dimensions: {gemini.dimensions}")

        vector = gemini.embed_text("これはテストです", task_type="retrieval_query")
        print(f"Vector length: {len(vector)}")
        print(f"First 5 values: {vector[:5]}")

        if len(vector) == DEFAULT_GEMINI_EMBEDDING_DIMS:
            print(f"[OK] 3072次元の検証: PASS")
        else:
            print(f"[NG] 3072次元の検証: FAIL (actual: {len(vector)})")

    except Exception as e:
        print(f"Gemini Error: {e}")

    print("\n" + "=" * 40)
    print(f"OpenAI default dims: {get_embedding_dimensions('openai')}")   # 3072
    print(f"Gemini default dims: {get_embedding_dimensions('gemini')}")   # 3072
    print(f"DEFAULT_EMBEDDING_PROVIDER: {DEFAULT_EMBEDDING_PROVIDER}")    # openai
