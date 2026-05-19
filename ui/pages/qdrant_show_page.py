#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qdrant_show_page.py - Qdrantデータ管理ページ
============================================
Qdrantコレクションの閲覧・管理（削除・統合）機能

機能:
- コレクション一覧表示と管理（削除）
- コレクション統合
- ポイントデータ詳細閲覧
- ヘルスチェック
"""

import time
from datetime import datetime
import logging

import pandas as pd
import streamlit as st
from qdrant_client import QdrantClient

# サービスモジュールからインポート
from services.qdrant_service import (
    QdrantHealthChecker,
    QdrantDataFetcher,
    QDRANT_CONFIG,
    merge_collections,
    get_collection_stats,
    get_all_collections,  # 追加
)

logger = logging.getLogger(__name__)


def display_source_info(source_info: dict) -> None:
    """データソース情報を表示"""
    if "error" in source_info:
        st.error(f"ソース情報取得エラー: {source_info['error']}")
        return

    total_points = source_info.get("total_points", 0)
    sources = source_info.get("sources", {})
    sample_size = source_info.get("sample_size", 0)

    if not sources:
        st.info("📂 データソース情報が見つかりません")
        return

    # メトリクス表示
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("総ポイント数", f"{total_points:,}")
    with col2:
        st.metric("ソース数", f"{len(sources)}")
    with col3:
        st.metric("サンプルサイズ", f"{sample_size}")

    # ソース情報テーブル
    source_data = []
    for source, stats in sorted(sources.items()):
        source_data.append({
            "ソース"  : source,
            "推定数"  : stats["estimated_total"],
            "割合"    : f"{stats['percentage']:.1f}%",
            "生成方法": stats.get("method", "unknown"),
            "ドメイン": stats.get("domain", "unknown"),
        })

    df_sources = pd.DataFrame(source_data)
    st.dataframe(df_sources, use_container_width=True, hide_index=True)


def show_qdrant_page():
    """画面: Qdrantデータ管理"""
    st.title("🗄️ Qdrantデータ管理")
    st.caption("Qdrantコレクションの閲覧、削除、および統合管理")

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

    # セッションステート初期化
    if "qdrant_debug_mode" not in st.session_state:
        st.session_state.qdrant_debug_mode = False

    # サイドバー（接続設定など）
    with st.sidebar:
        st.header("⚙️ Qdrant接続")

        # デバッグモード切り替え
        debug_mode = st.checkbox(
            "🐛 デバッグモード", value=st.session_state.qdrant_debug_mode
        )
        st.session_state.qdrant_debug_mode = debug_mode

        # 接続チェック
        checker = QdrantHealthChecker(debug_mode=debug_mode)
        is_connected, message, _ = checker.check_qdrant()

        if is_connected:
            st.success(f"✅ 接続済み: {QDRANT_CONFIG['url']}")
        else:
            st.error(f"❌ 未接続: {message}")
            st.code("docker run -p 6333:6333 qdrant/qdrant", language="bash")
            return  # 接続できない場合はここで終了

    # Qdrantクライアント作成
    try:
        client = QdrantClient(url=QDRANT_CONFIG["url"], timeout=10)
        data_fetcher = QdrantDataFetcher(client)
    except Exception as e:
        st.error(f"クライアント初期化エラー: {e}")
        return

    # タブで機能を分割
    tab_list, tab_details, tab_merge = st.tabs([
        "📊 コレクション一覧・削除",
        "🔍 データ詳細閲覧",
        "🔗 コレクション統合"
    ])

    # =================================================================
    # タブ1: コレクション一覧・削除
    # =================================================================
    with tab_list:
        st.subheader("📚 コレクション管理")

        # コレクション一覧取得
        # data_fetcher.fetch_collections() は DataFrame を返すが、ここでは操作用に生リストが欲しい
        # なので get_all_collections を使用する
        collections = get_all_collections(client)

        if not collections:
            st.info("コレクションが存在しません")
        else:
            # 総計表示
            total_points = sum(c["points_count"] for c in collections if isinstance(c["points_count"], int))
            st.metric("総コレクション数 / 総ポイント数", f"{len(collections)} / {total_points:,}")

            st.divider()

            # リスト表示と削除ボタン
            # ヘッダー
            cols = st.columns([3, 2, 2, 2])
            cols[0].markdown("**コレクション名**")
            cols[1].markdown("**ポイント数**")
            cols[2].markdown("**ステータス**")
            cols[3].markdown("**操作**")

            st.markdown("---")

            for col_info in collections:
                name = col_info["name"]
                points = col_info["points_count"]
                status = col_info["status"]

                c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                c1.code(name)
                c2.text(f"{points:,}")

                # ステータス色分け
                if status == "green":
                    c3.success(status)
                elif status == "yellow":
                    c3.warning(status)
                else:
                    c3.error(status)

                # 削除ボタン
                if c4.button("🗑️ 削除", key=f"del_btn_{name}", type="secondary"):
                    st.session_state[f"confirm_delete_{name}"] = True

                # 削除確認
                if st.session_state.get(f"confirm_delete_{name}", False):
                    with st.container():
                        st.warning(f"⚠️ '{name}' を本当に削除しますか？")
                        col_yes, col_no = st.columns(2)
                        if col_yes.button("✅ はい", key=f"yes_del_{name}"):
                            try:
                                client.delete_collection(name)
                                st.success(f"削除しました: {name}")
                                st.session_state[f"confirm_delete_{name}"] = False
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"削除エラー: {e}")

                        if col_no.button("❌ いいえ", key=f"no_del_{name}"):
                            st.session_state[f"confirm_delete_{name}"] = False
                            st.rerun()
                    st.markdown("---")

    # =================================================================
    # タブ2: データ詳細閲覧
    # =================================================================
    with tab_details:
        st.subheader("🔍 ポイントデータ詳細")

        if not collections:
            st.warning("表示できるコレクションがありません")
        else:
            collection_names = [c["name"] for c in collections]

            selected_collection = st.selectbox(
                "コレクションを選択",
                options=collection_names,
                key="details_collection_select"
            )

            col1, col2 = st.columns(2)
            with col1:
                if st.button("📦 データソース分析を表示", use_container_width=True):
                    with st.spinner("分析中..."):
                        source_info = data_fetcher.fetch_collection_source_info(selected_collection)
                        display_source_info(source_info)

            with col2:
                limit = st.number_input("表示件数", 10, 500, 50, step=10)

            st.divider()

            if st.button("🔎 データをロード", type="primary", use_container_width=True):
                with st.spinner("ロード中..."):
                    df_points = data_fetcher.fetch_collection_points(selected_collection, limit=limit)

                    if not df_points.empty and "ID" in df_points.columns:
                        st.dataframe(
                            df_points,
                            use_container_width=True,
                            column_config={
                                "answer"  : st.column_config.TextColumn(
                                    "回答", width="large", max_chars=200
                                ),
                                "question": st.column_config.TextColumn(
                                    "質問", width="medium"
                                )
                            }
                        )

                        # DLボタン
                        csv = df_points.to_csv(index=False)
                        st.download_button(
                            "📥 CSVでダウンロード",
                            csv,
                            f"{selected_collection}_sample.csv",
                            "text/csv"
                        )
                    else:
                        st.warning("データが見つかりません、または取得できませんでした")

    # =================================================================
    # タブ3: コレクション統合
    # =================================================================
    with tab_merge:
        st.subheader("🔗 コレクション統合")
        st.caption("複数のコレクションを1つにまとめます")

        if len(collections) < 2:
            st.warning("統合するには2つ以上のコレクションが必要です")
        else:
            # マルチセレクト
            collection_names = [c["name"] for c in collections]
            selected_to_merge = st.multiselect(
                "統合元コレクションを選択 (2つ以上)",
                options=collection_names,
                default=[]
            )

            # 統合先名
            default_name = f"integration_{datetime.now().strftime('%Y%m%d')}"
            target_name = st.text_input("統合後のコレクション名", value=default_name)

            recreate = st.checkbox("既存コレクションがあれば上書きする", value=True, key="merge_recreate")

            if st.button("🚀 統合を実行", type="primary", disabled=len(selected_to_merge) < 2):

                progress_bar = st.progress(0)
                status_text = st.empty()
                log_area = st.empty()
                logs = []

                def merge_callback(msg, current, total):
                    logs.append(msg)
                    # 最新5行を表示
                    log_area.text("\n".join(logs[-5:]))
                    status_text.text(f"{msg} ({current}/{total})")
                    if total > 0:
                        progress_bar.progress(min(current / total, 1.0))

                try:
                    result = merge_collections(
                        client,
                        selected_to_merge,
                        target_name,
                        recreate=recreate,
                        progress_callback=merge_callback
                    )

                    if result["success"]:
                        st.success(f"✅ 統合完了！ 合計 {result['total_points']:,} ポイント")
                        st.balloons()
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error(f"失敗: {result['error']}")

                except Exception as e:
                    st.error(f"予期せぬエラー: {e}")
