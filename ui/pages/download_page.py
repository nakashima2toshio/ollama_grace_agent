#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
download_page.py - RAGデータダウンロードページ
==============================================
HuggingFaceからのデータダウンロードと前処理

機能:
- HuggingFaceデータセットのダウンロード
- ローカルファイルのアップロード
- データの前処理（テキスト抽出、クレンジング）
- OUTPUT/フォルダへの保存
"""

import streamlit as st
from datetime import datetime
from pathlib import Path

# サービスモジュールからインポート
from services.dataset_service import (
    download_livedoor_corpus,
    load_livedoor_corpus,
    download_hf_dataset,
    extract_text_content,
    load_uploaded_file,
)
from services.file_service import (
    load_preprocessed_history,
    save_to_output,
)
from config import DATASET_CONFIGS


def show_rag_download_page():
    """画面1: RAGデータダウンロード・前処理"""
    st.title("📥 RAGデータダウンロード・前処理ツール")
    st.caption(
        "HuggingFaceデータセットまたはローカルファイルをダウンロード・前処理してOUTPUT/フォルダに保存"
    )

    # ダウンロード・前処理済みデータセット
    st.subheader("📦 ダウンロード・前処理済みデータセット")
    df_preprocessed = load_preprocessed_history()

    if not df_preprocessed.empty:
        st.dataframe(
            df_preprocessed, use_container_width=True, hide_index=True, height=200
        )
    else:
        st.info(
            "まだ前処理済みデータがありません。下記からデータセットをダウンロード・前処理してください。"
        )

    st.divider()
    st.caption("データセットの自動ダウンロード → 前処理 → OUTPUT/フォルダに保存")

    # サイドバー：データソース選択
    with st.sidebar:
        st.header("📂 データソース選択")

        # データソース選択（データセット or ローカルファイル）
        data_source = st.radio(
            "データソースを選択",
            options=["dataset", "local_file"],
            format_func=lambda x: "🌐 データセット"
            if x == "dataset"
            else "📁 ローカルファイル",
            key="data_source_selector",
        )

        st.divider()

        if data_source == "dataset":
            # データセット選択
            st.subheader("📥 データセット")

            dataset_options = list(DATASET_CONFIGS.keys())
            dataset_labels = {
                key: f"{DATASET_CONFIGS[key]['icon']} {DATASET_CONFIGS[key]['name']}"
                for key in dataset_options
            }

            selected_dataset = st.radio(
                "ダウンロードするデータセット",
                options=dataset_options,
                format_func=lambda x: dataset_labels[x],
                label_visibility="collapsed",
            )

            uploaded_file = None
            config = DATASET_CONFIGS[selected_dataset]

        else:
            # ローカルファイルアップロード
            st.subheader("📁 ファイルアップロード")

            uploaded_file = st.file_uploader(
                "ファイルを選択",
                type=["csv", "txt", "json", "jsonl"],
                help="CSV, TXT, JSON, JSONL形式に対応",
            )

            selected_dataset = "custom_upload"
            config = {
                "name": "カスタムアップロード",
                "icon": "📁",
                "description": "ローカルファイルからQ/Aペアを生成",
                "text_field": "Combined_Text",
                "title_field": None,
                "sample_size": 0,
                "min_text_length": 50,
            }

    # データソースの表示名
    data_source_name = (
        config["name"]
        if data_source == "dataset"
        else (uploaded_file.name if uploaded_file else "未選択")
    )

    # メインエリア：処理オプション（上部）
    st.subheader("⚙️ 処理オプション")

    # データセット情報と処理オプションを横並び
    col_info, col_opts = st.columns([1, 1])

    with col_info:
        if data_source == "dataset":
            st.info(f"""
**{config["name"]}**

{config["description"]}

- データソース: {config.get("hf_dataset", "直接ダウンロード")}
- デフォルトサンプル数: {config["sample_size"]:,} 件
            """)
        else:
            if uploaded_file:
                st.info(f"""
**📁 ローカルファイル**

ファイル名: {uploaded_file.name}

ファイル形式: {uploaded_file.name.split(".")[-1].upper()}
                """)
            else:
                st.warning("ファイルを選択してください")

    with col_opts:
        if data_source == "dataset":
            sample_size = st.number_input(
                "サンプル数",
                min_value=10,
                max_value=10000,
                value=config["sample_size"],
                step=50,
                help="ダウンロードするデータ件数",
            )
        else:
            sample_size = st.number_input(
                "最大ドキュメント数（上限: 1,000件）",
                min_value=1,
                max_value=1000,
                value=100,
                step=10,
                help="処理する最大ドキュメント数。全件処理する場合は1,000に設定",
            )

        min_length = st.number_input(
            "最小テキスト長",
            min_value=10,
            max_value=1000,
            value=config["min_text_length"],
            step=10,
            help="この長さ未満のテキストを除外",
        )

        remove_duplicates = st.checkbox(
            "重複を除去", value=True, help="完全に同じテキストを除外"
        )

    st.divider()
    st.caption("データセットの自動ダウンロード → 前処理 → OUTPUT/フォルダに保存")

    # API費用節約のための説明メッセージ（ピンク背景）
    pink_message_html = """
    <div style="background-color:#FFC0CB; padding:10px; border-radius:5px; border:1px solid #FF69B4;">
        <p style="color:#8B0000; font-weight:bold; margin-bottom:0px;">
            すでに、HuggingFaceから下記のファイルをダウンロードして<br>
            OUTPUT/preprocessed_*.csvに配置しています。<br>
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
    st.write("") # 1行空ける

    # 実行ボタン
    run_download = st.button(
        "🚀 ダウンロード＆前処理開始", type="primary", use_container_width=True
    )

    st.divider()

    # メインエリア：処理情報と履歴（下部）
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("📊 処理情報")
        info_container = st.container()

    with col2:
        st.subheader("📜 処理履歴・進捗")
        log_container = st.container()

    # 初期情報表示
    with info_container:
        st.metric("選択データセット", config["name"])
        st.metric("処理予定件数", f"{sample_size:,} 件")
        if "result_count" in st.session_state:
            st.metric("処理完了件数", f"{st.session_state['result_count']:,} 件")

    # ログ表示用
    if "logs" not in st.session_state:
        st.session_state["logs"] = []

    def add_log(message: str):
        """ログを追加"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        st.session_state["logs"].append(f"[{timestamp}] {message}")

    # 処理実行
    if run_download:
        st.session_state["logs"] = []  # ログクリア
        add_log(f"🚀 処理開始: {data_source_name}")

        # ローカルファイルの場合はファイルチェック
        if data_source == "local_file" and not uploaded_file:
            st.error("左ペインでローカル・ファイルを選択してください")
            st.stop()

        try:
            # ===================================================================
            # ローカルファイルの場合
            # ===================================================================
            if data_source == "local_file":
                # ステップ1: ファイル読み込み
                with st.spinner("📁 ファイル読み込み中..."):
                    add_log(f"📁 ローカルファイル読み込み: {uploaded_file.name}")
                    df = load_uploaded_file(uploaded_file)
                    add_log(f"✅ {len(df)} 件のデータを読み込みました")

                    # サンプリング
                    if len(df) > sample_size:
                        df = df.head(sample_size)
                        add_log(f"📊 {len(df)} 件に制限しました")

                # ステップ2: question, answerカラムの確認と抽出
                with st.spinner("⚙️ データ処理中..."):
                    add_log("⚙️ question, answerカラムを確認中...")

                    # question, answerカラムを探す
                    question_col = None
                    answer_col = None

                    for col in df.columns:
                        col_lower = col.lower()
                        if "question" in col_lower and not question_col:
                            question_col = col
                        if "answer" in col_lower and not answer_col:
                            answer_col = col

                    # question, answerカラムがない場合は通常処理
                    if question_col and answer_col:
                        add_log(f"  ✅ questionカラム: {question_col}")
                        add_log(f"  ✅ answerカラム: {answer_col}")

                        # question, answerのみ抽出
                        df_qa = df[[question_col, answer_col]].copy()
                        df_qa.columns = ["question", "answer"]  # カラム名を統一

                        # 空のデータを除外
                        before_len = len(df_qa)
                        df_qa = df_qa.dropna(subset=["question", "answer"])
                        df_qa = df_qa[
                            (df_qa["question"].str.strip() != "")
                            & (df_qa["answer"].str.strip() != "")
                        ]
                        removed = before_len - len(df_qa)
                        if removed > 0:
                            add_log(
                                f"📊 空データ除外: {removed} 件を除外（残り {len(df_qa)} 件）"
                            )

                        # 重複除去（オプション）
                        if remove_duplicates:
                            before_len = len(df_qa)
                            df_qa = df_qa.drop_duplicates()
                            removed = before_len - len(df_qa)
                            if removed > 0:
                                add_log(
                                    f"📊 重複除去: {removed} 件を除外（残り {len(df_qa)} 件）"
                                )

                        df_qa = df_qa.reset_index(drop=True)
                        add_log(f"✅ データ処理完了: {len(df_qa)} 件")

                        # ステップ3: qa_output/に保存
                        with st.spinner("💾 ファイル保存中..."):
                            add_log("💾 qa_output/フォルダに保存中...")

                            qa_output_dir = Path("qa_output")
                            qa_output_dir.mkdir(exist_ok=True)

                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            csv_filename = f"qa_pairs_upload_{timestamp}.csv"
                            csv_path = qa_output_dir / csv_filename

                            df_qa.to_csv(csv_path, index=False, encoding="utf-8-sig")
                            add_log(f"  📄 CSV保存: {csv_filename}")
                            add_log("✅ ファイル保存完了")

                        # 結果を保存
                        st.session_state["result_count"] = len(df_qa)
                        st.session_state["qa_saved_files"] = {"csv": str(csv_path)}
                        st.session_state["qa_count"] = len(df_qa)
                        st.session_state["processed_df"] = df_qa

                        add_log("🎉 全処理完了！")
                    else:
                        add_log(
                            "⚠️ Q/Aカラムが見つかりません。テキストデータとして処理します"
                        )

                        # テキストデータとして保存
                        with st.spinner("💾 ファイル保存中..."):
                            output_dir = Path("OUTPUT")
                            output_dir.mkdir(exist_ok=True)

                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            csv_filename = f"preprocessed_upload_{timestamp}.csv"
                            csv_path = output_dir / csv_filename

                            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
                            add_log(f"  📄 CSV保存: {csv_filename}")

                            st.session_state["result_count"] = len(df)
                            st.session_state["saved_files"] = {"csv": str(csv_path)}
                            st.session_state["processed_df"] = df

                            add_log("✅ データ保存完了")
                            add_log("🎉 全処理完了！")

            # ===================================================================
            # データセットの場合：既存の処理フロー
            # ===================================================================
            else:
                # ステップ1: データ読み込み
                with st.spinner("📥 データ読み込み中..."):
                    if selected_dataset == "livedoor":
                        # Livedoor特別処理
                        add_log("Livedoorコーパスをダウンロード中...")
                        data_dir = download_livedoor_corpus("datasets")
                        add_log("✅ ダウンロード完了")

                        add_log("データを読み込み中...")
                        df = load_livedoor_corpus(data_dir)
                        add_log(f"✅ {len(df)} 件のデータを読み込みました")

                        # サンプリング
                        if sample_size < len(df):
                            df = df.sample(n=sample_size, random_state=42)
                            add_log(f"📊 {len(df)} 件にサンプリングしました")

                    else:
                        # HuggingFaceからダウンロード
                        df = download_hf_dataset(
                            config["hf_dataset"],
                            config.get("hf_config"),
                            config["split"],
                            sample_size,
                            add_log,
                        )

                    add_log(f"✅ データ読み込み完了: {len(df)} 件")

                # ステップ2: 前処理
                with st.spinner("⚙️ 前処理実行中..."):
                    add_log("⚙️ 前処理開始")

                    add_log("テキストコンテンツを抽出中...")
                    df_processed = extract_text_content(df, config)
                    add_log(f"✅ テキスト抽出完了: {len(df_processed)} 件")

                    # 短文除外
                    before_len = len(df_processed)
                    df_processed = df_processed[
                        df_processed["Combined_Text"].str.len() >= min_length
                    ]
                    removed = before_len - len(df_processed)
                    if removed > 0:
                        add_log(
                            f"📊 短文除外: {removed} 件を除外（残り {len(df_processed)} 件）"
                        )

                    # 重複除去
                    if remove_duplicates:
                        before_len = len(df_processed)
                        df_processed = df_processed.drop_duplicates(
                            subset=["Combined_Text"]
                        )
                        removed = before_len - len(df_processed)
                        if removed > 0:
                            add_log(
                                f"📊 重複除去: {removed} 件を除外（残り {len(df_processed)} 件）"
                            )

                    df_processed = df_processed.reset_index(drop=True)
                    add_log(f"✅ 前処理完了: {len(df_processed)} 件")

                # ステップ3: OUTPUT保存
                with st.spinner("💾 ファイル保存中..."):
                    add_log("💾 OUTPUTフォルダに保存中...")
                    saved_files = save_to_output(df_processed, selected_dataset)
                    add_log("✅ ファイル保存完了")

                # 結果を保存
                st.session_state["result_count"] = len(df_processed)
                st.session_state["saved_files"] = saved_files
                st.session_state["processed_df"] = df_processed

                add_log("🎉 全処理完了！")

        except Exception as e:
            add_log(f"❌ エラー発生: {str(e)}")
            st.error(f"エラーが発生しました: {str(e)}")

    # ログ表示
    with log_container:
        if st.session_state["logs"]:
            log_text = "\n".join(st.session_state["logs"])
            st.text_area("処理ログ", value=log_text, height=400, disabled=True)
        else:
            st.info("処理を開始するとここにログが表示されます")

    # 結果表示
    if "saved_files" in st.session_state:
        st.divider()
        st.subheader("📁 保存されたファイル")

        saved_files = st.session_state["saved_files"]
        for file_type, file_path in saved_files.items():
            st.success(f"✅ {file_type.upper()}: {file_path}")

    if "qa_saved_files" in st.session_state:
        st.divider()
        st.subheader("📁 保存されたQ/Aファイル")

        qa_files = st.session_state["qa_saved_files"]
        for file_type, file_path in qa_files.items():
            st.success(f"✅ {file_type.upper()}: {file_path}")

    # プレビュー表示
    if "processed_df" in st.session_state:
        st.divider()
        st.subheader("📋 データプレビュー（最初の10件）")
        df_preview = st.session_state["processed_df"].head(10)
        st.dataframe(df_preview, use_container_width=True, hide_index=True)
