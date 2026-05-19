# helper_api.py
# OpenAI API関連とコア機能（後方互換レイヤー）
# -----------------------------------------
"""
helper_api.py - 後方互換レイヤー
================================
このモジュールは後方互換性のために維持されています。
新しいコードでは services/ パッケージを直接使用してください。

統合先:
- services/config_service.py: ConfigManager, config, logger
- services/cache_service.py: MemoryCache, cache, cache_result
- services/json_service.py: safe_json_*, load/save_json_file
- services/token_service.py: TokenManager
"""

import re
import time
import os
import json
from typing import List, Dict, Any, Optional, Union, Literal
from pathlib import Path
from functools import wraps
from datetime import datetime
import hashlib

# ===================================================================
# services/ からの統合インポート（後方互換性）
# ===================================================================
from services.config_service import (
    ConfigManager,
    config,
    logger,
)

from services.cache_service import (
    MemoryCache,
    cache,
    cache_result,
)

from services.json_service import (
    safe_json_serializer,
    safe_json_dumps,
    load_json_file,
    save_json_file,
)

from services.token_service import TokenManager

# ===================================================================
# 外部ライブラリ
# ===================================================================
from openai import OpenAI

# Gemini 3 Migration: 抽象化レイヤー
from helper.helper_llm import (  # [FIXED] helper_llm → helper.helper_llm
    create_llm_client as create_unified_llm_client,
    LLMClient,
    GeminiClient as GeminiLLMClient,
    OpenAIClient,        # 後方互換性のため再エクスポート
    AnthropicClient,     # [MIGRATION 追加] migration資料 ⑩
)

# -----------------------------------------------------
# OpenAI API型定義
# -----------------------------------------------------
from openai.types.responses import (
    EasyInputMessageParam,
    Response
)
from openai.types.chat import (
    ChatCompletionMessageParam,
)

# Role型の定義
RoleType = Literal["user", "assistant", "system", "developer"]


# ==================================================
# デコレータ（API用）
# ==================================================
def error_handler(func):
    """エラーハンドリングデコレータ（API用）"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            # API用では例外を再発生させる
            raise

    return wrapper


def timer(func):
    """実行時間計測デコレータ（API用）"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        logger.info(f"{func.__name__} took {execution_time:.2f} seconds")
        return result

    return wrapper


# --------------------------------------------------
# デフォルトプロンプト　responses-API（例）ソフトウェア開発用
# --------------------------------------------------
developer_text = (
    "You are a strong developer and good at teaching software developer professionals "
    "please provide an up-to-date, informed overview of the API by function, then show "
    "cookbook programs for each, and explain the API options."
    "あなたは強力な開発者でありソフトウェア開発者の専門家に教えるのが得意です。"
    "OpenAIのAPIを機能別に最新かつ詳細に説明してください。"
    "それぞれのAPIのサンプルプログラムを示しAPIのオプションについて説明してください。"
)
user_text = (
    "Organize and identify the problem and list the issues. "
    "Then, provide a solution procedure for the issues you have organized and identified, "
    "and solve the problems/issues according to the solution procedures."
    "不具合、問題を特定し、整理して箇条書きで列挙・説明してください。"
    "次に、整理・特定した問題点の解決手順を示しなさい。"
    "次に、解決手順に従って問題・課題を解決してください。"
)
assistant_text = "OpenAIのAPIを使用するには、公式openaiライブラリが便利です。回答は日本語で"


def get_default_messages() -> list[EasyInputMessageParam]:
    return [
        EasyInputMessageParam(role="developer", content=developer_text),
        EasyInputMessageParam(role="user", content=user_text),
        EasyInputMessageParam(role="assistant", content=assistant_text),
    ]


def append_user_message(append_text, image_url=None):
    return [
        EasyInputMessageParam(role="developer", content=developer_text),
        EasyInputMessageParam(role="user", content=user_text),
        EasyInputMessageParam(role="assistant", content=assistant_text),
        EasyInputMessageParam(role="user", content=append_text),
    ]


def append_developer_message(append_text):
    return [
        EasyInputMessageParam(role="developer", content=developer_text),
        EasyInputMessageParam(role="user", content=user_text),
        EasyInputMessageParam(role="assistant", content=assistant_text),
        EasyInputMessageParam(role="developer", content=append_text),
    ]


def append_assistant_message(append_text):
    return [
        EasyInputMessageParam(role="developer", content=developer_text),
        EasyInputMessageParam(role="user", content=user_text),
        EasyInputMessageParam(role="assistant", content=assistant_text),
        EasyInputMessageParam(role="assistant", content=append_text),
    ]


# ==================================================
# メッセージ管理
# ==================================================
class MessageManager:
    """メッセージ履歴の管理（API用）"""

    def __init__(self, messages: List[EasyInputMessageParam] = None):
        self._messages = messages or self.get_default_messages()

    @staticmethod
    def get_default_messages() -> List[EasyInputMessageParam]:
        """デフォルトメッセージの取得"""
        default_messages = config.get("default_messages", {})

        developer_content = default_messages.get(
            "developer",
            "You are a helpful assistant specialized in software development."
        )
        user_content = default_messages.get(
            "user",
            "Please help me with my software development tasks."
        )
        assistant_content = default_messages.get(
            "assistant",
            "I'll help you with your software development needs. Please let me know what you'd like to work on."
        )

        return [
            EasyInputMessageParam(role="developer", content=developer_content),
            EasyInputMessageParam(role="user", content=user_content),
            EasyInputMessageParam(role="assistant", content=assistant_content),
        ]

    def add_message(self, role: RoleType, content: str):
        """メッセージの追加"""
        valid_roles: List[RoleType] = ["user", "assistant", "system", "developer"]
        if role not in valid_roles:
            raise ValueError(f"Invalid role: {role}. Must be one of {valid_roles}")

        self._messages.append(EasyInputMessageParam(role=role, content=content))

        # メッセージ数制限
        limit = config.get("api.message_limit", 50)
        if len(self._messages) > limit:
            # 最初のdeveloperメッセージは保持
            developer_msg = self._messages[0] if self._messages[0]['role'] == 'developer' else None
            self._messages = self._messages[-limit:]
            if developer_msg and self._messages[0]['role'] != 'developer':
                self._messages.insert(0, developer_msg)

    def get_messages(self) -> List[EasyInputMessageParam]:
        """メッセージ履歴の取得"""
        return self._messages.copy()

    def clear_messages(self):
        """メッセージ履歴のクリア"""
        self._messages = self.get_default_messages()

    def export_messages(self) -> Dict[str, Any]:
        """メッセージ履歴のエクスポート"""
        return {
            'messages': self.get_messages(),
            'exported_at': datetime.now().isoformat()
        }

    def import_messages(self, data: Dict[str, Any]):
        """メッセージ履歴のインポート"""
        if 'messages' in data:
            self._messages = data['messages']


# ==================================================
# レスポンス処理
# ==================================================
class ResponseProcessor:
    """API レスポンスの処理"""

    @staticmethod
    def extract_text(response: Response) -> List[str]:
        """レスポンスからテキストを抽出"""
        texts = []

        if hasattr(response, 'output'):
            for item in response.output:
                if hasattr(item, 'type') and item.type == "message":
                    if hasattr(item, 'content'):
                        for content in item.content:
                            if hasattr(content, 'type') and content.type == "output_text":
                                if hasattr(content, 'text'):
                                    texts.append(content.text)

        # フォールバック: output_text属性
        if not texts and hasattr(response, 'output_text'):
            texts.append(response.output_text)

        return texts

    @staticmethod
    def _serialize_usage(usage_obj) -> Dict[str, Any]:
        """ResponseUsageオブジェクトを辞書に変換"""
        if usage_obj is None:
            return {}

        # Pydantic モデルの場合
        if hasattr(usage_obj, 'model_dump'):
            try:
                return usage_obj.model_dump()
            except Exception:
                pass

        # dict() メソッドがある場合
        if hasattr(usage_obj, 'dict'):
            try:
                return usage_obj.dict()
            except Exception:
                pass

        # 手動で属性を抽出
        usage_dict = {}
        for attr in ['prompt_tokens', 'completion_tokens', 'total_tokens']:
            if hasattr(usage_obj, attr):
                usage_dict[attr] = getattr(usage_obj, attr)

        return usage_dict

    @staticmethod
    def format_response(response: Response) -> Dict[str, Any]:
        """レスポンスを整形（JSON serializable）"""
        # usage オブジェクトを安全に変換
        usage_obj = getattr(response, "usage", None)
        usage_dict = ResponseProcessor._serialize_usage(usage_obj)

        return {
            "id": getattr(response, "id", None),
            "model": getattr(response, "model", None),
            "created_at": getattr(response, "created_at", None),
            "text": ResponseProcessor.extract_text(response),
            "usage": usage_dict,
        }

    @staticmethod
    def save_response(response: Response, filename: str = None) -> str:
        """レスポンスの保存"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"response_{timestamp}.json"

        formatted = ResponseProcessor.format_response(response)

        # ファイルパスの生成
        logs_dir = Path(config.get("paths.logs_dir", "logs"))
        logs_dir.mkdir(exist_ok=True)
        filepath = logs_dir / filename

        # 保存
        save_json_file(formatted, str(filepath))

        return str(filepath)


# ==================================================
# Gemini 3 Migration: 統合LLMクライアント
# ==================================================

# デフォルトプロバイダー（環境変数で設定可能）
# [MIGRATION anthropic→openai] デフォルトを "openai" に変更
DEFAULT_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # "openai" | "anthropic" | "gemini"


class UnifiedLLMClient:
    """
    プロバイダー切り替え対応の統合LLMクライアント

    Gemini 3 Migration: OpenAIとGeminiの両方に対応する統一インターフェース

    Usage:
        # デフォルト（Gemini）
        client = UnifiedLLMClient()
        response = client.generate("Hello, world!")

        # 明示的にプロバイダーを指定
        client = UnifiedLLMClient(provider="openai")
        response = client.generate("Hello, world!")

        # 構造化出力（Pydantic対応）
        result = client.generate_structured("Generate Q&A", QAPairsResponse)
    """

    def __init__(self, provider: str = None, **kwargs):
        """
        Args:
            provider: "gemini" or "openai"（Noneの場合はデフォルト）
            **kwargs: プロバイダー固有の初期化パラメータ
        """
        self.provider = provider or DEFAULT_LLM_PROVIDER
        self._client: LLMClient = create_unified_llm_client(
            provider=self.provider,
            **kwargs
        )
        logger.info(f"UnifiedLLMClient initialized with provider: {self.provider}")

    @property
    def client(self) -> LLMClient:
        """内部LLMクライアントを取得"""
        return self._client

    @error_handler
    @timer
    def generate(
        self,
        prompt: str,
        model: str = None,
        system_instruction: str = None,
        **kwargs
    ) -> str:
        """
        テキスト生成

        Args:
            prompt: プロンプトテキスト
            model: モデル名（省略時はデフォルト）
            system_instruction: システム指示
            **kwargs: 追加パラメータ

        Returns:
            生成されたテキスト
        """
        return self._client.generate_content(
            prompt=prompt,
            model=model,
            system_instruction=system_instruction,
            **kwargs
        )

    @error_handler
    @timer
    def generate_structured(
        self,
        prompt: str,
        response_schema,
        model: str = None,
        **kwargs
    ):
        """
        構造化出力生成（Pydantic対応）

        Args:
            prompt: プロンプトテキスト
            response_schema: Pydanticモデルクラス
            model: モデル名（省略時はデフォルト）
            **kwargs: 追加パラメータ

        Returns:
            Pydanticモデルインスタンス
        """
        return self._client.generate_structured(
            prompt=prompt,
            response_schema=response_schema,
            model=model,
            **kwargs
        )

    def count_tokens(self, text: str, model: str = None) -> int:
        """
        トークン数をカウント

        Args:
            text: テキスト
            model: モデル名

        Returns:
            トークン数
        """
        return self._client.count_tokens(text, model=model)


def create_llm_client(provider: str = None, **kwargs) -> UnifiedLLMClient:
    """
    統合LLMクライアントのファクトリ関数

    Args:
        provider: "gemini" or "openai"
        **kwargs: クライアント初期化パラメータ

    Returns:
        UnifiedLLMClientインスタンス

    Example:
        # Geminiクライアント
        client = create_llm_client("gemini")

        # OpenAIクライアント
        client = create_llm_client("openai")
    """
    return UnifiedLLMClient(provider=provider, **kwargs)


def get_default_llm_client(**kwargs) -> UnifiedLLMClient:
    """デフォルト設定で統合LLMクライアントを取得"""
    return UnifiedLLMClient(**kwargs)


# ==================================================
# ユーティリティ関数
# ==================================================
def sanitize_key(name: str) -> str:
    """キー用に安全な文字列へ変換"""
    return re.sub(r'[^0-9a-zA-Z_]', '_', name).lower()


def format_timestamp(timestamp: Union[int, float, str] = None) -> str:
    """タイムスタンプのフォーマット"""
    if timestamp is None:
        timestamp = time.time()

    if isinstance(timestamp, str):
        return timestamp

    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def create_session_id() -> str:
    """セッションIDの生成"""
    return hashlib.md5(f"{time.time()}_{id(object())}".encode()).hexdigest()[:8]


# ==================================================
# エクスポート
# ==================================================
__all__ = [
    # 型定義
    'RoleType',

    # クラス（services/から再エクスポート）
    'ConfigManager',
    'MemoryCache',
    'TokenManager',

    # クラス（このモジュール固有）
    'MessageManager',
    'ResponseProcessor',
    'OpenAIClient',

    'AnthropicClient',           # 後方互換のため残存
    'GeminiLLMClient',           # 後方互換のため残存

    # Gemini 3 Migration: 統合クライアント
    'UnifiedLLMClient',
    'create_llm_client',
    'get_default_llm_client',
    'DEFAULT_LLM_PROVIDER',

    # デコレータ
    'error_handler',
    'timer',
    'cache_result',

    # ユーティリティ（services/から再エクスポート）
    'safe_json_serializer',
    'safe_json_dumps',
    'load_json_file',
    'save_json_file',

    # ユーティリティ（このモジュール固有）
    'sanitize_key',
    'format_timestamp',
    'create_session_id',

    # 定数
    'developer_text',
    'user_text',
    'assistant_text',

    # グローバル（services/から再エクスポート）
    'config',
    'logger',
    'cache',
]
