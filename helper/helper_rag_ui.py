#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
helper_rag_ui.py - RAGデータ前処理用UIコンポーネント（後方互換レイヤー）
======================================================================
このモジュールは後方互換性のために維持されています。
新しいコードでは ui.components を直接使用してください。

移動先: ui/components/rag_components.py
"""

# ui.components からの統合インポート（後方互換性）
from ui.components.rag_components import (
    select_model,
    show_model_info,
    estimate_token_usage,
    display_statistics,
    show_usage_instructions,
    setup_page_config,
    setup_page_header,
    setup_sidebar_header,
)

# ロガー（後方互換性）
import logging
logger = logging.getLogger(__name__)

# エクスポート
__all__ = [
    "select_model",
    "show_model_info",
    "estimate_token_usage",
    "display_statistics",
    "show_usage_instructions",
    "setup_page_config",
    "setup_page_header",
    "setup_sidebar_header",
]