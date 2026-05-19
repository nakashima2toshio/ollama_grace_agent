#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ui.pages - Streamlitページモジュール
====================================
各ページの関数を提供
"""

from ui.pages.explanation_page import show_system_explanation_page
from ui.pages.download_page import show_rag_download_page
from ui.pages.qa_generation_page import show_qa_generation_page
from ui.pages.qdrant_registration_page import show_qdrant_registration_page
from ui.pages.qdrant_show_page import show_qdrant_page
from ui.pages.qdrant_search_page import show_qdrant_search_page
from ui.pages.grace_chat_page import show_grace_chat_page

__all__ = [
    "show_system_explanation_page",
    "show_rag_download_page",
    "show_qa_generation_page",
    "show_qdrant_registration_page",
    "show_qdrant_page",
    "show_qdrant_search_page",
    "show_grace_chat_page",
]