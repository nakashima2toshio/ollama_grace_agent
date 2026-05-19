"""
GRACE Config - 設定管理

YAMLファイルと環境変数からの設定読み込み
"""

import os
import logging
from pathlib import Path
from typing import Any, Optional, Dict
import yaml
from pydantic import BaseModel, Field


# =============================================================================
# Logging Configuration
# =============================================================================

def init_grace_logging():
    """GRACEパッケージ用のロギングを初期化"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "grace_run.log"

    # 既存のハンドラがあるかチェックして重複を防ぐ
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
    else:
        # graceパッケージの出力を確実にする
        grace_logger = logging.getLogger("grace")
        if not any(isinstance(h, logging.FileHandler) for h in grace_logger.handlers):
            fh = logging.FileHandler(log_file, encoding='utf-8')
            fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            grace_logger.addHandler(fh)
            grace_logger.setLevel(logging.INFO)


# モジュール読み込み時に初期化
init_grace_logging()

logger = logging.getLogger(__name__)


# =============================================================================
# 設定モデル定義
# =============================================================================

class LLMConfig(BaseModel):
    """LLM設定"""
    # [MIGRATION anthropic→openai] provider: "anthropic" → "openai"
    # [MIGRATION anthropic→openai] model: "claude-sonnet-4-6" → "gpt-4o-mini"（デフォルト）
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 30


class EmbeddingConfig(BaseModel):
    """Embedding設定"""
    # [MIGRATION] provider: "gemini" → "openai"
    # [MIGRATION] model: "gemini-embedding-001" → "text-embedding-3-large"
    # dimensions: 3072 のまま維持（Gemini と同次元 → Qdrant コレクション再作成不要）
    provider: str = "openai"
    model: str = "text-embedding-3-large"
    dimensions: int = 3072


class ConfidenceWeights(BaseModel):
    """Confidence重み設定"""
    search_quality: float = 0.25
    source_agreement: float = 0.20
    llm_self_eval: float = 0.25
    tool_success: float = 0.15
    query_coverage: float = 0.15


class ConfidenceThresholds(BaseModel):
    """Confidence閾値設定"""
    silent: float = 0.9
    notify: float = 0.7
    confirm: float = 0.4


class ConfidenceConfig(BaseModel):
    """Confidence計算設定"""
    weights: ConfidenceWeights = Field(default_factory=ConfidenceWeights)
    thresholds: ConfidenceThresholds = Field(default_factory=ConfidenceThresholds)


class InterventionConfig(BaseModel):
    """介入設定"""
    default_timeout: int = 300  # 5分
    auto_proceed_on_timeout: bool = False
    max_clarification_rounds: int = 3


class ReplanConfig(BaseModel):
    """リプラン設定"""
    max_replans: int = 3
    confidence_threshold: float = 0.4
    partial_replan_threshold: float = 0.6
    cooldown_seconds: int = 5


class CostConfig(BaseModel):
    """コスト管理設定"""
    daily_limit_usd: float = 10.0
    hourly_limit_usd: float = 2.0
    per_query_limit_usd: float = 0.50
    warning_threshold: float = 0.8


class ErrorConfig(BaseModel):
    """エラーハンドリング設定"""
    max_retries: int = 3
    retry_delay_base: float = 1.0
    retry_delay_max: float = 30.0
    exponential_backoff: bool = True


class LoggingConfig(BaseModel):
    """ログ設定"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: str = "logs/grace.log"
    max_size_mb: int = 100
    backup_count: int = 5


class QdrantConfig(BaseModel):
    """Qdrant設定"""
    url: str = "http://localhost:6333"
    collection_name: str = "customer_support_faq"
    search_limit: int = 5
    score_threshold: float = 0.35
    rag_sufficient_score: float = 0.7  # RAG結果が十分と判断するスコア閾値（これ未満ならweb_searchを動的実行）
    search_priority: list = Field(default_factory=lambda: ["wikipedia_ja", "livedoor", "cc_news", "japanese_text"])


class WebSearchConfig(BaseModel):
    """Web検索設定"""
    backend: str = "serpapi"  # "duckduckgo" or "google_cse" or "serpapi"
    num_results: int = 5
    language: str = "ja"
    timeout: int = 30
    # Google CSE用（backendが"google_cse"の場合のみ使用）※新規受付停止
    google_cse_api_key: str = ""
    google_cse_engine_id: str = ""
    # SerpAPI用（backendが"serpapi"の場合に使用）
    serpapi_api_key: str = ""


class ToolsConfig(BaseModel):
    """ツール設定"""
    enabled: list = Field(default_factory=lambda: ["rag_search", "web_search", "reasoning", "ask_user"])
    disabled: list = Field(default_factory=list, description="プロジェクト全体で恒久的に禁止するツールのリスト")


class GraceConfig(BaseModel):
    """GRACE Agent 統合設定"""
    version: str = "1.0"
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    confidence: ConfidenceConfig = Field(default_factory=ConfidenceConfig)
    intervention: InterventionConfig = Field(default_factory=InterventionConfig)
    replan: ReplanConfig = Field(default_factory=ReplanConfig)
    cost: CostConfig = Field(default_factory=CostConfig)
    error: ErrorConfig = Field(default_factory=ErrorConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)


# =============================================================================
# 設定ローダー
# =============================================================================

class ConfigLoader:
    """設定ローダー"""

    DEFAULT_CONFIG_PATH = "config/grace_config.yml"
    ENV_PREFIX = "GRACE_"

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._config: Optional[GraceConfig] = None

    def load(self) -> GraceConfig:
        """設定を読み込み"""
        if self._config is not None:
            return self._config

        # 1. デフォルト設定
        config_dict: Dict[str, Any] = {}

        # 2. YAMLファイルから読み込み
        config_file = Path(self.config_path)
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    loaded = yaml.safe_load(f)
                    if loaded:
                        config_dict = loaded
                logger.info(f"Config loaded from {self.config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config from {self.config_path}: {e}")
        else:
            logger.info(f"Config file not found: {self.config_path}, using defaults")

        # 3. 環境変数で上書き
        config_dict = self._apply_env_overrides(config_dict)

        # 4. Pydanticモデルで検証
        self._config = GraceConfig(**config_dict)

        return self._config

    def _apply_env_overrides(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """環境変数による上書き"""
        for key, value in os.environ.items():
            if not key.startswith(self.ENV_PREFIX):
                continue

            # GRACE_LLM_MODEL -> llm.model
            parts = key[len(self.ENV_PREFIX):].lower().split('_')

            if len(parts) >= 2:
                section = parts[0]
                subkey = '_'.join(parts[1:])

                if section not in config_dict:
                    config_dict[section] = {}

                # 型変換
                config_dict[section][subkey] = self._convert_value(value)
                logger.debug(f"Config override: {section}.{subkey} = {value}")

        return config_dict

    def _convert_value(self, value: str) -> Any:
        """文字列から適切な型に変換"""
        # bool
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'

        # int
        try:
            return int(value)
        except ValueError:
            pass

        # float
        try:
            return float(value)
        except ValueError:
            pass

        # リスト（カンマ区切り）
        if ',' in value:
            return [v.strip() for v in value.split(',')]

        return value

    def reload(self) -> GraceConfig:
        """設定を再読み込み"""
        self._config = None
        return self.load()


# =============================================================================
# シングルトンインスタンス
# =============================================================================

_config_loader: Optional[ConfigLoader] = None


def get_config(config_path: Optional[str] = None) -> GraceConfig:
    """設定を取得（シングルトン）"""
    global _config_loader

    if _config_loader is None:
        _config_loader = ConfigLoader(config_path)

    return _config_loader.load()


def reload_config() -> GraceConfig:
    """設定を再読み込み"""
    global _config_loader

    if _config_loader is not None:
        return _config_loader.reload()

    return get_config()


def reset_config():
    """設定をリセット（テスト用）"""
    global _config_loader
    _config_loader = None


# =============================================================================
# エクスポート
# =============================================================================

__all__ = [
    # Config models
    "LLMConfig",
    "EmbeddingConfig",
    "ConfidenceWeights",
    "ConfidenceThresholds",
    "ConfidenceConfig",
    "InterventionConfig",
    "ReplanConfig",
    "CostConfig",
    "ErrorConfig",
    "LoggingConfig",
    "QdrantConfig",
    "WebSearchConfig",
    "ToolsConfig",
    "GraceConfig",

    # Loader
    "ConfigLoader",

    # Functions
    "get_config",
    "reload_config",
    "reset_config",
]
