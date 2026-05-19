#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qdrant_registration_page.py - Qdrant登録ページ
==============================================
Q/AデータのQdrantへの登録機能

機能:
- CSVファイルからQdrantへの登録
- 埋め込みベクトル生成
"""

import logging
from datetime import datetime
from pathlib import Path
import re

import pandas as pd
import streamlit as st
from qdrant_client import QdrantClient

# サービスモジュールからインポート
from services.qdrant_service import (
    get_collection_stats,
    load_csv_for_qdrant,
    build_inputs_for_embedding,
    embed_texts_for_qdrant,
    create_or_recreate_collection_for_qdrant,
    build_points_for_qdrant,
    upsert_points_to_qdrant,
)
# Wrapperから直接インポート (Sparse用)
from qdrant_client_wrapper import embed_sparse_texts_unified
from helper.helper_embedding import get_embedding_dimensions, DEFAULT_EMBEDDING_PROVIDER

logger = logging.getLogger(__name__)


def show_qdrant_registration_page():
    """画面: CSVデータ登録"""
    st.title("📥 CSVデータ登録")
    st.caption("qa_output/*.csvのデータをQdrantベクトルDBに登録します")

    # サイドバー：設定
    with st.sidebar:
        st.header("⚙️ Qdrant設定")

        qdrant_url = st.text_input(
            "Qdrant URL", value="http://localhost:6333", help="QdrantサーバーのURL"
        )

    # Qdrant接続確認
    qdrant_connected = False
    try:
        client = QdrantClient(url=qdrant_url, timeout=30)
        # 接続テスト
        client.get_collections()
        qdrant_connected = True
    except Exception as e:
        st.error(f"❌ Qdrant接続エラー: {e}")
        st.warning("Qdrantが起動していることを確認してください。")
        st.code("docker run -p 6333:6333 qdrant/qdrant", language="bash")
        client = None

    st.divider()

    if not qdrant_connected:
        st.warning("Qdrantに接続できていません。設定を確認してください。")
        return

    # ===================================================================
    # CSV登録設定
    # ===================================================================
    st.subheader("📄 登録設定")

    # qa_output/*.csvファイル一覧取得
    qa_output_dir = Path("qa_output")
    if qa_output_dir.exists():
        csv_files = sorted(qa_output_dir.glob("*.csv"))
        csv_options = [f.name for f in csv_files]
    else:
        csv_options = []

    if not csv_options:
        st.warning("qa_output/フォルダにCSVファイルがありません")
        st.info("先に「Q/A生成」でデータを作成してください")
        return

    col_setting1, col_setting2 = st.columns(2)

    with col_setting1:
        selected_csv = st.selectbox(
            "ファイル選択",
            options=csv_options,
            help="登録するCSVファイルを選択",
        )

        # コレクション名を自動生成（カスタマイズ可能）
        default_collection = f"qa_{Path(selected_csv).stem}"
        collection_name = st.text_input(
            "コレクション名",
            value=default_collection,
            help="Qdrantコレクション名",
        )

        # コレクション名のバリデーション
        is_valid_collection_name = bool(re.fullmatch(r"^[a-zA-Z0-9_-]+$", collection_name))
        if not is_valid_collection_name:
            st.error("コレクション名には半角英数字、アンダースコア(_) 、ハイフン(-)のみ使用できます。")

    with col_setting2:
        recreate_collection = st.checkbox(
            "既存コレクションがあれば上書きする",
            value=True,
            help="同名のコレクションが存在する場合、削除して新規作成します（チェックを外すと追加登録になります）",
        )

        include_answer = st.checkbox(
            "answerを含める（推奨）",
            value=True,
            help="埋め込み生成時に質問だけでなく回答も含めることで、検索精度が向上する場合があります"
        )

        data_limit = st.number_input(
            "データ件数制限 (0=無制限)",
            min_value=0,
            max_value=100000,
            value=0,
            step=100,
            help="テスト用に登録件数を制限する場合に使用します",
        )

        use_hybrid_search = st.checkbox(
            "Hybrid Search (Sparse Vector) を有効にする",
            value=True,
            help="キーワード検索用のSparse Vectorも生成・登録します（検索精度が向上します）"
        )

    # ファイル情報表示
    csv_path = qa_output_dir / selected_csv
    file_size = csv_path.stat().st_size
    if file_size < 1024:
        size_str = f"{file_size} B"
    elif file_size < 1024 * 1024:
        size_str = f"{file_size / 1024:.1f} KB"
    else:
        size_str = f"{file_size / (1024 * 1024):.1f} MB"

    st.info(f"選択中: **{selected_csv}** ({size_str}) -> コレクション: **{collection_name}**")

    # データプレビュー
    with st.expander("📋 データプレビュー（最初の3件）"):
        try:
            df_preview = pd.read_csv(csv_path, nrows=3)
            st.dataframe(df_preview, use_container_width=True)
        except Exception as e:
            st.error(f"プレビュー読み込みエラー: {e}")

    st.divider()

    # API費用節約のための説明メッセージ（ピンク背景）
    pink_message_html = """
    <div style="background-color:#FFC0CB; padding:10px; border-radius:5px; border:1px solid #FF69B4;">
        <p style="color:#8B0000; font-weight:bold; margin-bottom:0px;">
            すでに、HuggingFaceから下記のファイルをダウンロードして配置、<br>
            Q/Aペアを作成済み、Qdrantにembeddingベクトルデータを登録済みです。<br>
            ・Wikipedia日本語版<br>
            ・日本語Webテキスト（CC100）<br>
            ・CC-News（英語ニュース）<br>
            ・Livedoorニュースコーパス<br>
            よって、ここの送信ボタンはdisableにしてあります。（API費用がかかり過ぎるので😹）
        </p>
    </div>
    """
    st.markdown(pink_message_html, unsafe_allow_html=True)
    st.write("")  # 1行空ける

    # 登録ボタン
    run_registration = st.button(
        "🚀 Qdrantに登録を実行",
        type="primary",
        use_container_width=True,
        disabled=not (qdrant_connected and is_valid_collection_name),
    )

    # ログ表示エリア
    st.subheader("📜 処理ログ")
    log_container = st.container()

    if "qdrant_registration_logs" not in st.session_state:
        st.session_state["qdrant_registration_logs"] = []

    def add_log(message: str):
        """ログを追加"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        st.session_state["qdrant_registration_logs"].append(f"[{timestamp}] {message}")

    # 登録処理実行
    if run_registration:
        st.session_state["qdrant_registration_logs"] = []  # ログクリア
        add_log(f"🚀 登録処理開始: {selected_csv}")

        try:
            # ステップ1: CSVロード
            with st.spinner("📁 CSVファイル読み込み中..."):
                add_log(f"📁 CSV読み込み: {csv_path}")
                df = load_csv_for_qdrant(str(csv_path), limit=data_limit)
                add_log(f"✅ {len(df)} 件のデータを読み込みました")

            # ステップ2: コレクション作成
            with st.spinner("🗄️ コレクション準備中..."):
                add_log(f"🗄️ コレクション準備: {collection_name}")

                # 次元数をプロバイダーから取得
                vector_size = get_embedding_dimensions(DEFAULT_EMBEDDING_PROVIDER)

                create_or_recreate_collection_for_qdrant(
                    client,
                    collection_name,
                    recreate_collection,
                    vector_size=vector_size,
                    use_sparse=use_hybrid_search
                )
                add_log(f"✅ コレクション準備完了 (Sparse: {use_hybrid_search})")

            # ステップ3: 埋め込み生成 (Dense)
            with st.spinner("🔢 Dense埋め込み生成中..."):
                add_log("🔢 Dense埋め込み生成開始")
                texts = build_inputs_for_embedding(df, include_answer)
                vectors = embed_texts_for_qdrant(
                    texts, model="gemini-embedding-001"  # model引数は互換性のため残るが内部でprovider使用
                )
                add_log(f"✅ {len(vectors)} 件のDense埋め込みを生成しました")

            # ステップ3.5: Sparse埋め込み生成
            sparse_vectors = None
            if use_hybrid_search:
                with st.spinner("🔠 Sparse埋め込み生成中 (FastEmbed)..."):
                    add_log("🔠 Sparse埋め込み生成開始 (FastEmbed)")

                    # プログレスバーの作成
                    progress_bar = st.progress(0, text="Sparse Embedding 生成中...")

                    def update_progress(current, total):
                        percent = int((current / total) * 100)
                        progress_bar.progress(percent, text=f"Sparse Embedding 生成中... ({current}/{total})")

                    try:
                        sparse_vectors = embed_sparse_texts_unified(
                            texts,
                            progress_callback=update_progress
                        )
                    finally:
                        progress_bar.empty()

                    add_log(f"✅ {len(sparse_vectors)} 件のSparse埋め込みを生成しました")

            # ステップ4: ポイント構築
            with st.spinner("📦 ポイント構築中..."):
                add_log("📦 Qdrantポイント構築中")
                # ドメイン名を推定
                if "cc_news" in selected_csv.lower():
                    domain = "cc_news"
                elif "livedoor" in selected_csv.lower():
                    domain = "livedoor"
                else:
                    domain = "custom"

                points = build_points_for_qdrant(
                    df,
                    vectors,
                    domain,
                    selected_csv,
                    sparse_vectors=sparse_vectors
                )
                add_log(f"✅ {len(points)} 個のポイントを構築しました")

            # ステップ5: Qdrantアップサート
            with st.spinner("⬆️ Qdrantアップサート中..."):
                add_log("⬆️ Qdrantにアップサート中")
                count = upsert_points_to_qdrant(client, collection_name, points)
                add_log(f"✅ {count} 件をQdrantに登録しました")

            # 完了
            add_log("🎉 全処理完了！")
            st.success(f"✅ {count}件のデータをQdrantに登録しました")

            # 統計情報を表示
            try:
                stats = get_collection_stats(client, collection_name)
                if stats:
                    st.divider()
                    st.subheader("📊 登録結果")
                    st.json(stats)
            except Exception as e:
                logger.warning(f"統計情報取得エラー: {e}")

        except Exception as e:
            add_log(f"❌ エラー発生: {str(e)}")
            st.error(f"エラーが発生しました: {str(e)}")

    # ログ表示
    with log_container:
        if st.session_state["qdrant_registration_logs"]:
            log_text = "\n".join(st.session_state["qdrant_registration_logs"])
            st.text_area("処理ログ", value=log_text, height=300, disabled=True)
        else:
            st.info("登録処理を開始するとここにログが表示されます")
