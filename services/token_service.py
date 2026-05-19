#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
token_service.py - トークン管理サービス
=======================================
トークンカウント、コスト推定、テキスト切り詰めの統合モジュール

統合元:
- helper_api.py::TokenManager
- helper_rag.py::TokenManager
- helper_text.py::count_tokens
"""

import logging
from typing import Dict, Optional

import tiktoken

logger = logging.getLogger(__name__)

# ===================================================================
# 定数
# ===================================================================

# デフォルトエンコーディング
DEFAULT_ENCODING = "cl100k_base"

# モデル別エンコーディング対応表
MODEL_ENCODINGS = {
    # OpenAI GPT-4o系
    "gpt-4o": "cl100k_base",
    "gpt-4o-mini": "cl100k_base",
    "gpt-4o-audio-preview": "cl100k_base",
    "gpt-4o-mini-audio-preview": "cl100k_base",
    # OpenAI GPT-4.1系
    "gpt-4.1": "cl100k_base",
    "gpt-4.1-mini": "cl100k_base",
    # OpenAI O系
    "o1": "cl100k_base",
    "o1-mini": "cl100k_base",
    "o3": "cl100k_base",
    "o3-mini": "cl100k_base",
    "o4": "cl100k_base",
    "o4-mini": "cl100k_base",
    # Gemini系 (tiktokenでは近似)
    "gemini-2.0-flash": "cl100k_base",
    "gemini-2.0-pro": "cl100k_base",
    "gemini-1.5-pro-latest": "cl100k_base",
    "gemini-1.5-flash-latest": "cl100k_base",
}

# LLMモデル価格 ($/1000トークン)
LLM_PRICING = {
    "gemini-2.0-flash": {"input": 0.0001, "output": 0.0002},
    "gemini-2.0-pro": {"input": 0.002, "output": 0.004},
    "gemini-1.5-pro-latest": {"input": 0.0035, "output": 0.0105},
    "gemini-1.5-flash-latest": {"input": 0.00035, "output": 0.00105},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.005, "output": 0.015},
}

# Embeddingモデル価格 ($/1000トークン)
EMBEDDING_PRICING = {
    "gemini-embedding-001": 0.0001,
    "text-embedding-3-small": 0.00002,
    "text-embedding-3-large": 0.00013,
}

# モデル制限
MODEL_LIMITS = {
    "gpt-4o": {"max_tokens": 128000, "max_output": 4096},
    "gpt-4o-mini": {"max_tokens": 128000, "max_output": 4096},
    "gpt-4.1": {"max_tokens": 128000, "max_output": 4096},
    "gpt-4.1-mini": {"max_tokens": 128000, "max_output": 4096},
    "o1": {"max_tokens": 128000, "max_output": 32768},
    "o1-mini": {"max_tokens": 128000, "max_output": 65536},
    "o3": {"max_tokens": 200000, "max_output": 100000},
    "o3-mini": {"max_tokens": 200000, "max_output": 100000},
    "o4": {"max_tokens": 256000, "max_output": 128000},
    "o4-mini": {"max_tokens": 256000, "max_output": 128000},
    "gemini-2.0-flash": {"max_tokens": 1048576, "max_output": 8192},
    "gemini-2.0-pro": {"max_tokens": 1048576, "max_output": 8192},
}


# ===================================================================
# TokenManager クラス（統合版）
# ===================================================================

class TokenManager:
    """
    トークン管理クラス（統合版）

    統合元:
    - helper_api.py::TokenManager
    - helper_rag.py::TokenManager
    """

    # クラス変数として定数を公開
    MODEL_ENCODINGS = MODEL_ENCODINGS
    LLM_PRICING = LLM_PRICING
    EMBEDDING_PRICING = EMBEDDING_PRICING
    MODEL_LIMITS = MODEL_LIMITS

    @classmethod
    def count_tokens(cls, text: str, model: str = None) -> int:
        """
        テキストのトークン数をカウント

        Args:
            text: カウント対象テキスト
            model: モデル名（省略時はデフォルトエンコーディング使用）

        Returns:
            トークン数
        """
        if not text:
            return 0

        try:
            if model:
                encoding_name = cls.MODEL_ENCODINGS.get(model, DEFAULT_ENCODING)
            else:
                encoding_name = DEFAULT_ENCODING

            enc = tiktoken.get_encoding(encoding_name)
            return len(enc.encode(text))

        except Exception as e:
            logger.warning(f"トークンカウントエラー（簡易推定を使用）: {e}")
            return estimate_tokens_simple(text)

    @classmethod
    def truncate_text(cls, text: str, max_tokens: int, model: str = None) -> str:
        """
        テキストを指定トークン数に切り詰め

        Args:
            text: 対象テキスト
            max_tokens: 最大トークン数
            model: モデル名

        Returns:
            切り詰められたテキスト
        """
        if not text:
            return ""

        try:
            encoding_name = cls.MODEL_ENCODINGS.get(model, DEFAULT_ENCODING) if model else DEFAULT_ENCODING
            enc = tiktoken.get_encoding(encoding_name)
            tokens = enc.encode(text)

            if len(tokens) <= max_tokens:
                return text

            return enc.decode(tokens[:max_tokens])

        except Exception as e:
            logger.error(f"テキスト切り詰めエラー: {e}")
            # フォールバック: 文字数ベース
            estimated_chars = max_tokens * 2
            return text[:estimated_chars]

    @classmethod
    def estimate_cost(
        cls,
        input_tokens: int,
        output_tokens: int,
        model: str,
        is_embedding: bool = False
    ) -> float:
        """
        API使用コストを推定

        Args:
            input_tokens: 入力トークン数
            output_tokens: 出力トークン数
            model: モデル名
            is_embedding: Embeddingモデルか

        Returns:
            推定コスト（USD）
        """
        if is_embedding:
            pricing_per_1k = cls.EMBEDDING_PRICING.get(model, 0.0001)
            return (input_tokens / 1000) * pricing_per_1k
        else:
            pricing = cls.LLM_PRICING.get(model, {"input": 0.00015, "output": 0.0006})
            input_cost = (input_tokens / 1000) * pricing["input"]
            output_cost = (output_tokens / 1000) * pricing["output"]
            return input_cost + output_cost

    @classmethod
    def get_model_limits(cls, model: str) -> Dict[str, int]:
        """
        モデルのトークン制限を取得

        Args:
            model: モデル名

        Returns:
            {"max_tokens": int, "max_output": int}
        """
        return cls.MODEL_LIMITS.get(model, {"max_tokens": 128000, "max_output": 4096})


# ===================================================================
# ユーティリティ関数
# ===================================================================

def get_encoding(encoding_name: str = DEFAULT_ENCODING) -> tiktoken.Encoding:
    """
    tiktokenエンコーディングを取得

    Args:
        encoding_name: エンコーディング名

    Returns:
        tiktokenエンコーディング
    """
    return tiktoken.get_encoding(encoding_name)


def count_tokens(text: str, model: str = None) -> int:
    """
    テキストのトークン数をカウント（関数版）

    TokenManager.count_tokensのショートカット

    Args:
        text: カウント対象テキスト
        model: モデル名

    Returns:
        トークン数
    """
    return TokenManager.count_tokens(text, model)


def estimate_tokens_simple(text: str) -> int:
    """
    簡易的なトークン数推定

    日本語文字は約0.5トークン、英数字は約0.25トークンとして推定

    Args:
        text: 対象テキスト

    Returns:
        推定トークン数
    """
    if not text:
        return 0

    japanese_chars = len([c for c in text if ord(c) > 127])
    english_chars = len(text) - japanese_chars
    estimated = int(japanese_chars * 0.5 + english_chars * 0.25)

    return max(1, estimated)


def truncate_text(
    text: str,
    max_tokens: int = 1000,
    model: str = None,
    add_ellipsis: bool = True
) -> str:
    """
    テキストを指定トークン数で切り詰め

    Args:
        text: 対象テキスト
        max_tokens: 最大トークン数
        model: モデル名
        add_ellipsis: 省略記号を追加するか

    Returns:
        切り詰められたテキスト
    """
    if not text:
        return ""

    truncated = TokenManager.truncate_text(text, max_tokens, model)

    if add_ellipsis and len(truncated) < len(text):
        truncated += "..."

    return truncated


def get_llm_pricing(model: str) -> Dict[str, float]:
    """LLMモデルの価格を取得"""
    return LLM_PRICING.get(model, {"input": 0.0, "output": 0.0})


def get_embedding_pricing(model: str) -> float:
    """Embeddingモデルの価格を取得"""
    return EMBEDDING_PRICING.get(model, 0.0)


def get_model_limits(model: str) -> Dict[str, int]:
    """モデルのトークン制限を取得"""
    return MODEL_LIMITS.get(model, {"max_tokens": 0, "max_output": 0})


# ===================================================================
# エクスポート
# ===================================================================

__all__ = [
    # クラス
    "TokenManager",
    # 定数
    "DEFAULT_ENCODING",
    "MODEL_ENCODINGS",
    "LLM_PRICING",
    "EMBEDDING_PRICING",
    "MODEL_LIMITS",
    # 関数
    "get_encoding",
    "count_tokens",
    "estimate_tokens_simple",
    "truncate_text",
    "get_llm_pricing",
    "get_embedding_pricing",
    "get_model_limits",
]