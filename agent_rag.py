#!/usr/bin/env python
# ---------------------------------------------------
# # GCP サーバーで実行
# ---------------------------------------------------
# ssh -i ~/.ssh/gcp_key_v2 nakashima@34.84.198.115
# curl -LsSf https://astral.sh/uv/install.sh | sh
# source ~/.bashrc
#
# cd /path/to/project
# uv venv
# uv pip install -r requirements.txt
#
# sudo systemctl daemon-reload
# sudo systemctl restart streamlit-app
#
# -*- coding: utf-8 -*-
#
# uv run streamlit run agent_rag.py --server.port 8501
# streamlit run agent_rag.py --server.port 8501
# Agent RAG Q&A生成・Qdrant管理 Streamlit アプリケーション
# sudo systemctl restart streamlit-app
# ---------------------------------------------------
# 実行コマンド：
# ---------------------------------------------------
# ./start_celery.sh restart -w 4 --flower
# uv run streamlit run agent_rag.py --server.port 8501
# ---------------------------------------------------

import streamlit as st

# UIページをインポート
from ui.pages import (
    show_system_explanation_page,
    show_qdrant_search_page,
    show_grace_chat_page,
)
from ui.pages.agent_chat_page import show_agent_chat_page
from ui.pages.log_viewer_page import show_log_viewer_page
from ui.pages.benchmark_page import show_benchmark_page


# --- 関連ドキュメント定義 ---
RAG_DATA_DOCS = [
    {
        "path"       : "readme_usage_tools.md",
        "description": "[tools]：ツールの使い方（RAGデータ作成はCLIの下記コマンドを利用します）",
    },
    {
        "path": "chunking/doc/csv_text_to_chunks_text_csv.md",
        "description": "[チャンク分割]：LLMベース - 3段階セマンティックチャンキング - パイプラインの仕様書",
    },
    {
        "path": "qa_qdrant/doc/make_qa_register_qdrant.md",
        "description": "[Q/A生成＋Qdrant登録]： 統合CLIツールの仕様書",
    },
]


def _load_local_markdown(file_path: str) -> str:
    from pathlib import Path
    p = Path(file_path)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return f"⚠️ ファイルが見つかりません: `{file_path}`"


def show_rag_data_creation_page():
    st.header("📄 RAGデータ作成")
    st.divider()
    st.subheader("📚 RAGデータ作成・登録のドキュメント")
    st.markdown(
        "| ドキュメント | 説明 |\n"
        "|:------------|:-----|\n"
        + "\n".join(f"| `{doc['path']}` | {doc['description']} |" for doc in RAG_DATA_DOCS)
    )
    for doc in RAG_DATA_DOCS:
        with st.expander(f"📖 {doc['path']}"):
            st.markdown(_load_local_markdown(doc["path"]))
    st.divider()
    st.markdown(
        """
        ### RAGデータ作成の流れ：
        - (1) チャンク分割：文字列を「意味のある単位」に分割する。
        - (2) Q/Aペア作成：チャンクから Question/Answer ペアを作成。
        - (3) Q/Aペアを Embedding し、Qdrant へ登録する。
        """
    )


def show_qdrant_crud_page():
    st.header("🗄️ QdrantのCRUD")
    st.divider()
    st.markdown(
        """
        ### Qdrant CRUD操作
        - **Create**: コレクション作成、ポイント追加
        - **Read**: コレクション一覧、ポイント検索・取得
        - **Update**: ポイントのペイロード更新
        - **Delete**: ポイント削除、コレクション削除
        """
    )


def main():
    st.set_page_config(page_title="Agent RAG(Ollama)", page_icon="🤖", layout="wide")

    with st.sidebar:
        st.title("Agent RAG (Ollama)")
        st.divider()
        st.markdown("**メニュー**")

        page = st.radio(
            "機能選択",
            options=[
                "explanation",
                "qdrant_search",
                "agent_chat",
                "grace_chat",
                "log_viewer",
                "rag_data_creation",
                "qdrant_crud",
                "benchmark",
            ],
            format_func=lambda x: {
                "explanation":       "📖 説明",
                "qdrant_search":     "🔎 Qdrant検索",
                "agent_chat":        "🤖 Agent(ReAct+Reflection)",
                "grace_chat":        "[最新] 自律型Agent(Plan+Executor)",
                "log_viewer":        "📊 未回答ログ",
                "rag_data_creation": "📄 RAGデータ作成",
                "qdrant_crud":       "🗄️ QdrantのCRUD",
                "benchmark":         "📊 ベンチマーク (Phase 5)",
            }[x],
            label_visibility="collapsed",
        )
        st.markdown("全ソースは： [GitHub: nakashima2toshio/ollama_agent_rag](https://github.com/nakashima2toshio/ollama_agent_rag)")
        st.divider()

    page_mapping = {
        "explanation":       show_system_explanation_page,
        "agent_chat":        show_agent_chat_page,
        "grace_chat":        show_grace_chat_page,
        "log_viewer":        show_log_viewer_page,
        "rag_data_creation": show_rag_data_creation_page,
        "qdrant_crud":       show_qdrant_crud_page,
        "qdrant_search":     show_qdrant_search_page,
        "benchmark":         show_benchmark_page,
    }
    page_mapping[page]()


if __name__ == "__main__":
    main()
