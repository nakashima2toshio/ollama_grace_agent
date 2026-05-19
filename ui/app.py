#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ui/app.py - メインアプリケーション
==================================
RAGツールのStreamlitメインエントリポイント

使用方法:
    streamlit run ui/app.py

または:
    streamlit run agent_rag.py  # 従来の方法
"""

import streamlit as st
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def main():
    """メインアプリケーション - 画面選択"""

    # ページ設定
    st.set_page_config(page_title="RAGツール", page_icon="🤖", layout="wide")

    # サイドバー：画面選択
    with st.sidebar:
        st.title("🤖 RAGツール")
        st.divider()

        # メニュー見出し
        st.markdown("**メニュー**")

        # 画面オプション
        page_options = [
            "explanation",
            "rag_download",
            "qa_generation",
            "qdrant_registration",
            "show_qdrant",
            "qdrant_search",
        ]

        page_labels = {
            "explanation": "📖 説明",
            "rag_download": "📥 RAGデータダウンロード",
            "qa_generation": "🤖 Q/A生成",
            "qdrant_registration": "🗄️ Qdrant登録",
            "show_qdrant": "🔍 Show-Qdrant",
            "qdrant_search": "🔎 Qdrant検索",
        }

        # 画面選択
        page = st.radio(
            "機能選択",
            options=page_options,
            format_func=lambda x: page_labels[x],
            label_visibility="collapsed",
        )

        st.divider()

        # バージョン情報
        st.caption("v1.0.0 - リファクタリング版")

    # ページをインポートして表示
    try:
        if page == "explanation":
            from ui.pages.explanation_page import show_system_explanation_page
            show_system_explanation_page()

        elif page == "rag_download":
            from ui.pages.download_page import show_rag_download_page
            show_rag_download_page()

        elif page == "qa_generation":
            from ui.pages.qa_generation_page import show_qa_generation_page
            show_qa_generation_page()

        elif page == "qdrant_registration":
            from ui.pages.qdrant_registration_page import show_qdrant_registration_page
            show_qdrant_registration_page()

        elif page == "show_qdrant":
            from ui.pages.qdrant_show_page import show_qdrant_page
            show_qdrant_page()

        elif page == "qdrant_search":
            from ui.pages.qdrant_search_page import show_qdrant_search_page
            show_qdrant_search_page()

    except Exception as e:
        st.error(f"ページの読み込みに失敗しました: {e}")
        st.exception(e)


if __name__ == "__main__":
    main()