#!/usr/bin/env python
# ---------------------------------------------------
#
# ---------------------------------------------------
# uv run streamlit run agent_rag.py -- --model gemma4:e4b
# uv run streamlit run agent_rag.py
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
# # systemd の ExecStart を uv run に変更
# # 変更前: ExecStart=/path/.venv/bin/streamlit run agent_rag.py
# # 変更後: ExecStart=/usr/local/bin/uv run streamlit run agent_rag.py
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
# 詳細な仕様、実行方法、アーキテクチャについては、プロジェクトルートの `README.md` を参照してください。
#
# [リモートサーバー管理 (GCP)]:
# ssh -i ~/.ssh/gcp_key_v2 nakashima@34.84.198.115
#
# # 設定ファイルの変更を反映
# sudo systemctl daemon-reload
#
# # サーバー起動時に自動で立ち上がるように設定
# sudo systemctl enable streamlit-app
#
# # 今すぐ起動する
# sudo systemctl start streamlit-app
#
# # 停止する
# sudo systemctl stop streamlit-app
#
# # 再起動する
# sudo systemctl restart streamlit-app
#
# # 状態確認
# sudo systemctl status streamlit-app
#
# # ログ確認
# journalctl -u streamlit-app -f


import argparse
import os

import streamlit as st

# UIページをインポート
from ui.pages import (
    show_system_explanation_page,
    show_qdrant_search_page,
    show_grace_chat_page,
)
from ui.pages.agent_chat_page import show_agent_chat_page
from ui.pages.log_viewer_page import show_log_viewer_page


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
    """プロジェクト内のMarkdownファイルを読み込む"""
    from pathlib import Path
    p = Path(file_path)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return f"⚠️ ファイルが見つかりません: `{file_path}`"


# --- 新規ページ（仮実装） ---
def show_rag_data_creation_page():
    """RAGデータ作成ページ"""
    st.header("📄 RAGデータ作成")
    st.divider()

    # --- 関連ドキュメント参照テーブル ---
    st.subheader("📚 RAGデータ作成・登録のドキュメント")
    st.markdown(
        "| ドキュメント | 説明 |\n"
        "|:------------|:-----|\n"
        + "\n".join(
            f"| `{doc['path']}` | {doc['description']} |"
            for doc in RAG_DATA_DOCS
        )
    )

    # Expanderでドキュメント内容を表示
    for doc in RAG_DATA_DOCS:
        with st.expander(f"📖 {doc['path']}"):
            content = _load_local_markdown(doc["path"])
            st.markdown(content)

    st.divider()

    st.markdown(
        """
        ### RAGデータ作成の流れ：
        #### （チャンク分割 -> Q/Aペア作成 -> ベクターDB:Qdrantへ登録）
        - (1) チャンク分割：「Text or CVS」：文字列を「意味のある単位」に分割する。
        - (2) Q/Aペア作成：チャンクから、Question/Answerペアを作成
        - (3) Q/AペアをEmbedding(ベクトル化）し、Qdrantへ登録する。
        """
    )


def show_qdrant_crud_page():
    """QdrantのCRUDページ"""
    st.header("🗄️ QdrantのCRUD")
    st.divider()
    st.markdown(
        """
        ### Qdrant CRUD操作について

        このページでは、Qdrantベクトルデータベースに対するCRUD操作を行います。

        **主な機能：**
        - **Create**: コレクション作成、ポイント追加
        - **Read**: コレクション一覧、ポイント検索・取得
        - **Update**: ポイントのペイロード更新
        - **Delete**: ポイント削除、コレクション削除

        """
    )


def _resolve_startup_model() -> str:
    """
    起動時のデフォルトモデルを決定する（初回のみ実行）。
    優先順位: CLI引数 --model > 環境変数 OLLAMA_DEFAULT_MODEL > "llama3.2"
    """
    from config import GeminiConfig
    if "startup_model" in st.session_state:
        return st.session_state["startup_model"]

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--model", default=None, help="起動時のデフォルトOllamaモデル名")
    args, _ = parser.parse_known_args()

    model = (
        args.model
        or os.getenv("OLLAMA_DEFAULT_MODEL")
        or GeminiConfig.DEFAULT_MODEL
    )
    if model not in GeminiConfig.AVAILABLE_MODELS:
        import streamlit as _st
        _st.warning(f"指定モデル '{model}' は AVAILABLE_MODELS に未登録です。'llama3.2' を使用します。")
        model = "llama3.2"

    st.session_state["startup_model"] = model
    return model


def main():
    """メインアプリケーション - 画面選択"""

    # 起動時デフォルトモデルを確定（CLI引数 > 環境変数 > config デフォルト）
    _resolve_startup_model()

    # ページ設定
    st.set_page_config(page_title="Agent RAG(Ollama)", page_icon="🤖", layout="wide")

    # サイドバー：画面選択
    with st.sidebar:
        st.title("Agent RAG (Ollama)")
        st.divider()

        # メニュー見出し
        st.markdown("**メニュー**")

        # 画面選択
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
            ],
            format_func=lambda x: {
                "explanation": "📖 説明",
                "qdrant_search": "🔎 Qdrant検索",
                "agent_chat": "🤖 Agent(ReAct+Reflection)",
                "grace_chat": "[最新] 自律型Agent(Plan+Executor)",
                "log_viewer": "📊 未回答ログ",
                "rag_data_creation": "📄 RAGデータ作成",
                "qdrant_crud": "🗄️ QdrantのCRUD",
            }[x],
            label_visibility="collapsed",
        )
        st.markdown("全ソースは： [GitHub: nakashima2toshio/anthropic_agent_rag](https://github.com/nakashima2toshio/anthropic_agent_rag)")
        st.divider()

    # 選択された画面を表示
    page_mapping = {
        "explanation": show_system_explanation_page,
        "agent_chat": show_agent_chat_page,
        "grace_chat": show_grace_chat_page,
        "log_viewer": show_log_viewer_page,
        "rag_data_creation": show_rag_data_creation_page,
        "qdrant_crud": show_qdrant_crud_page,
        "qdrant_search": show_qdrant_search_page,
    }
    page_mapping[page]()


if __name__ == "__main__":
    main()
