#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qa_generation_page.py - Q/A生成ページ
=====================================
Q/Aペアの自動生成機能

機能:
- データセットまたはローカルファイルからQ/A生成
- Celery並列処理対応
- カバレージ分析
"""

from datetime import datetime
from pathlib import Path

import streamlit as st

# サービスモジュールからインポート
from services.file_service import load_qa_output_history
from services.qa_service import run_advanced_qa_generation
from config import DATASET_CONFIGS, ModelConfig


def show_qa_generation_page():
    """画面2: Q/A生成"""

    st.title("🤖 Q/A生成ツール")
    st.caption(
        "既存データまたはローカルファイルからQ/Aペアを生成（make_qa.py機能）"
    )

    # 最新のQ/A履歴表示
    st.subheader("📋 最新のQ&Aペア")
    df_history = load_qa_output_history()

    if not df_history.empty:
        st.dataframe(df_history, use_container_width=True, hide_index=True, height=200)
    else:
        st.info("まだQ&Aペアデータがありません。")

    st.divider()

    # サイドバー：入力ソース選択
    with st.sidebar:
        st.header("📂 入力ソース選択")

        # 入力ソース選択
        input_source = st.radio(
            "入力ソースを選択",
            options=["dataset", "local_file"],
            format_func=lambda x: "🌐 データセット"
            if x == "dataset"
            else "📁 ローカルファイル",
            key="input_source_selector",
        )

        st.divider()

        if input_source == "dataset":
            # データセット選択
            st.subheader("📥 データセット")

            dataset_options = list(DATASET_CONFIGS.keys())
            dataset_labels = {
                key: f"{DATASET_CONFIGS[key]['icon']} {DATASET_CONFIGS[key]['name']}"
                for key in dataset_options
            }

            selected_dataset = st.radio(
                "Q/A生成するデータセット",
                options=dataset_options,
                format_func=lambda x: dataset_labels[x],
                label_visibility="collapsed",
            )

            uploaded_file = None
            input_file_path = None

        else:
            # ローカルファイルアップロード
            st.subheader("📁 ファイルアップロード")

            uploaded_file = st.file_uploader(
                "ファイルを選択",
                type=["csv", "txt", "json", "jsonl"],
                help="CSV, TXT, JSON, JSONL形式に対応",
            )

            selected_dataset = None
            input_file_path = None

        # =========================================================
        # Q/A生成オプション（a02_make_qa_para.py相当）
        # =========================================================
        st.divider()
        st.subheader("🚀 Q/A生成設定")

        # Celery設定
        use_celery = st.checkbox(
            "Celery並列処理", value=True, help="複数ワーカーで並列処理"
        )

        if use_celery:
            celery_workers = st.number_input(
                "Celeryワーカー数",
                min_value=1,
                max_value=48,
                value=24,  # Gemini APIレート制限対策のためデフォルトを24に設定
                step=1,
                help="並列処理するワーカー数",
            )
        else:
            celery_workers = 1

        col_a1, col_a2 = st.columns(2)
        with col_a1:
            batch_chunks = st.number_input(
                "バッチチャンク数",
                min_value=1,
                max_value=5,
                value=3,
                step=1,
                help="1回のAPIで処理するチャンク数",
            )

            max_docs = st.number_input(
                "最大ドキュメント数",
                min_value=1,
                max_value=10000,
                value=100,
                step=10,
                help="処理する最大ドキュメント数",
            )

        with col_a2:
            min_tokens = st.number_input(
                "最小トークン数",
                min_value=50,
                max_value=500,
                value=150,
                step=10,
                help="統合対象の最小トークン数",
            )

            max_tokens = st.number_input(
                "最大トークン数",
                min_value=100,
                max_value=1000,
                value=400,
                step=50,
                help="統合後の最大トークン数",
            )

        merge_chunks = st.checkbox(
            "チャンク統合", value=True, help="小さいチャンクを統合"
        )

        coverage_threshold = st.slider(
            "カバレージ閾値",
            min_value=0.0,
            max_value=1.0,
            value=0.58,
            step=0.01,
            help="カバレージ判定の類似度閾値",
        )

        qa_model = st.selectbox(
            "モデル",
            options=ModelConfig.AVAILABLE_MODELS,
            # [MIGRATION anthropic→openai] DEFAULT_MODEL を使用（gpt-4o-mini）
            index=ModelConfig.AVAILABLE_MODELS.index(ModelConfig.DEFAULT_MODEL)
                  if ModelConfig.DEFAULT_MODEL in ModelConfig.AVAILABLE_MODELS else 0,
            help="Q/A生成に使用するモデル",
        )

        analyze_coverage = st.checkbox(
            "カバレージ分析", value=True, help="Q/Aペアのカバレージを分析"
        )

    # メインエリア：処理オプション
    st.subheader("⚙️ 入力情報")

    # 入力情報表示
    col_info, col_opts = st.columns([1, 1])

    with col_info:
        if input_source == "dataset":
            config = DATASET_CONFIGS[selected_dataset]
            st.info(f"""
**{config["name"]}**

{config["description"]}

- データソース: {config.get("hf_dataset", "直接ダウンロード")}
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
        st.markdown("**処理設定**")
        st.write(f"- Celery並列処理: {'有効' if use_celery else '無効'}")
        if use_celery:
            st.write(f"- ワーカー数: {celery_workers}")
        st.write(f"- バッチチャンク数: {batch_chunks}")
        st.write(f"- 最大ドキュメント数: {max_docs}")
        st.write(f"- モデル: {qa_model}")
        st.write(f"- カバレージ分析: {'実行' if analyze_coverage else 'スキップ'}")

    # 実行中フラグの初期化
    if "qa_generation_running" not in st.session_state:
        st.session_state["qa_generation_running"] = False

    # 実行ボタン（実行中は無効化）
    run_qa_generation = st.button(
        "🚀 Q/A生成開始" if not st.session_state["qa_generation_running"] else "⏳ 処理中...",
        type="primary",
        use_container_width=True,
        disabled=st.session_state["qa_generation_running"]
    )

    st.divider()

    # メインエリア：進捗表示
    st.subheader("📜 処理履歴・進捗")
    log_container = st.container()

    # ログ表示用
    if "qa_logs" not in st.session_state:
        st.session_state["qa_logs"] = []

    def add_log(message: str):
        """ログを追加（最新1000行のみ保持）"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        st.session_state["qa_logs"].append(f"[{timestamp}] {message}")

        # 最新1000行のみ保持（メモリ節約＋レンダリング高速化）
        if len(st.session_state["qa_logs"]) > 1000:
            st.session_state["qa_logs"] = st.session_state["qa_logs"][-1000:]

    # 処理実行
    if run_qa_generation and not st.session_state["qa_generation_running"]:
        st.session_state["qa_generation_running"] = True  # 実行開始
        st.session_state["qa_logs"] = []  # ログクリア

        # 入力チェック
        if input_source == "local_file" and not uploaded_file:
            st.error("ファイルを選択してください")
            st.stop()

        try:
            add_log("🚀 Q/A生成処理開始")

            # ローカルファイルの場合、一時保存
            if input_source == "local_file":
                with st.spinner("📁 ファイル準備中..."):
                    add_log(f"📁 ローカルファイル読み込み: {uploaded_file.name}")

                    # 一時ファイルに保存
                    temp_dir = Path("temp_uploads")
                    temp_dir.mkdir(exist_ok=True)

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    temp_filename = f"temp_qa_{timestamp}_{uploaded_file.name}"
                    temp_path = temp_dir / temp_filename

                    # ファイルを保存
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    input_file_path = str(temp_path)
                    add_log(f"  ✅ 一時ファイル作成: {temp_filename}")

            # make_qa.pyを実行
            add_log("🚀 make_qa.py (pipeline)実行開始")

            # プログレスバー用のコンテナとセッション状態
            progress_container = st.empty()
            progress_bar = progress_container.progress(0)

            # 進捗コールバック関数
            def update_progress(current: int, total: int):
                """進捗バーを更新"""
                if total > 0:
                    progress = current / total
                    progress_bar.progress(progress, text=f"進捗: {current}/{total} タスク完了")

            with st.spinner("🚀 Q/Aペア生成中（make_qa.py実行）..."):
                result = run_advanced_qa_generation(
                    dataset=selected_dataset if input_source == "dataset" else None,
                    input_file=input_file_path,
                    use_celery=use_celery,
                    celery_workers=celery_workers,
                    batch_chunks=batch_chunks,
                    max_docs=max_docs,
                    merge_chunks=merge_chunks,
                    min_tokens=min_tokens,
                    max_tokens=max_tokens,
                    coverage_threshold=coverage_threshold,
                    model=qa_model,
                    analyze_coverage=analyze_coverage,
                    log_callback=add_log,
                    progress_callback=update_progress,
                )

                # 処理完了後はプログレスバーをクリア
                progress_container.empty()

                # 一時ファイルを削除
                if input_source == "local_file" and input_file_path:
                    try:
                        Path(input_file_path).unlink()
                        add_log("  🗑️ 一時ファイルを削除しました")
                    except Exception:
                        pass

                if result["success"]:
                    qa_saved_files = result.get("saved_files")
                    qa_count = result.get("qa_count", 0)

                    # 結果を保存
                    st.session_state["qa_result_files"] = qa_saved_files
                    st.session_state["qa_result_count"] = qa_count

                    if result.get("coverage_results"):
                        add_log(
                            f"📊 カバレージ率: {result['coverage_results']['coverage_rate']:.1%}"
                        )

                    add_log("🎉 Q/A生成完了！")
                else:
                    add_log("⚠️ Q/A生成に失敗しました")

        except Exception as e:
            add_log(f"❌ エラー発生: {str(e)}")
            st.error(f"エラーが発生しました: {str(e)}")
        finally:
            # 実行完了 - フラグをリセット
            st.session_state["qa_generation_running"] = False

    # ログ表示
    with log_container:
        if st.session_state["qa_logs"]:
            with st.expander("📜 処理ログを表示", expanded=False):
                log_text = "\n".join(st.session_state["qa_logs"])
                st.text_area("処理ログ", value=log_text, height=400, disabled=True)
                st.caption(f"総ログ数: {len(st.session_state['qa_logs'])} 行")
        else:
            st.info("Q/A生成を開始するとここにログが表示されます")

    # 結果表示
    if "qa_result_files" in st.session_state and st.session_state["qa_result_files"]:
        st.divider()
        st.subheader("📁 生成結果")

        qa_files = st.session_state["qa_result_files"]
        qa_count = st.session_state.get("qa_result_count", 0)

        st.info(f"✅ 生成されたQ/Aペア: **{qa_count}** 個")

        col_qa1, col_qa2 = st.columns(2)

        with col_qa1:
            if "csv" in qa_files:
                st.success(f"📄 CSV: {qa_files['csv']}")

        with col_qa2:
            if "json" in qa_files:
                st.success(f"📄 JSON: {qa_files['json']}")
