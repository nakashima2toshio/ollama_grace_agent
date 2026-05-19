#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
chunking パッケージ
chunking__init__updated.py

テキストを意味的なチャンクに分割するためのツール。
非同期・並列処理により高速化。

主要機能:
- chunks_all_async(): テキストからチャンクを作成（LLMベース、asyncio並列処理）
- load_text_from_csv(): CSVファイルからテキストを読み込み（✅ v1.2.0追加）
- save_chunks_as_csv(): チャンクをCSV形式で保存（✅ v1.2.0追加）
- save_chunks_as_text(): チャンクをテキスト形式で保存（✅ v1.2.0追加）

バージョン履歴:
- v1.0.0: 初版
- v1.1.0: チェックポイント機能追加
- v1.2.0: CSV入力対応、CSV出力機能追加
"""

# ===================================================================
# Models
# ===================================================================
from .models import (
    SentenceUnit,
    ParagraphUnit,
    StructuralResult,
    ContinuityResult
)

# ===================================================================
# Prompts
# ===================================================================
from .prompts import (
    PARAGRAPH_SEPARATION_PROMPT,
    SEMANTIC_CHUNKING_PROMPT,
    CONTINUITY_CHECK_PROMPT
)

# ===================================================================
# API Client
# ===================================================================
from .async_api_client import AsyncAPIClient

# ===================================================================
# Checkpoint Manager
# ===================================================================
from .checkpoint_manager import CheckpointManager

# ===================================================================
# Main Processor (✅ v1.2.0 更新)
# ===================================================================
from .csv_text_to_chunks_text_csv import (
    chunks_all_async,        # ✅ 既存（シグネチャ拡張）
    load_text_from_csv,      # ✅ v1.2.0 新規追加
    save_chunks_as_csv,      # ✅ v1.2.0 新規追加
    save_chunks_as_text,     # ✅ v1.2.0 新規追加
)

# ===================================================================
# Utils
# ===================================================================
from .utils import (
    show_paragraphs,
    setup_logging,
    format_time,
    format_size,
    estimate_api_calls
)

# ===================================================================
# Version
# ===================================================================
__version__ = "1.2.0"

# ===================================================================
# Export
# ===================================================================
__all__ = [
    # Models
    "SentenceUnit",
    "ParagraphUnit",
    "StructuralResult",
    "ContinuityResult",
    # Prompts
    "PARAGRAPH_SEPARATION_PROMPT",
    "SEMANTIC_CHUNKING_PROMPT",
    "CONTINUITY_CHECK_PROMPT",
    # API Client
    "AsyncAPIClient",
    # Checkpoint
    "CheckpointManager",
    # Main Processor
    "chunks_all_async",
    "load_text_from_csv",     # ✅ v1.2.0 追加
    "save_chunks_as_csv",     # ✅ v1.2.0 追加
    "save_chunks_as_text",    # ✅ v1.2.0 追加
    # Utils
    "show_paragraphs",
    "setup_logging",
    "format_time",
    "format_size",
    "estimate_api_calls",
    # Version
    "__version__",
]
