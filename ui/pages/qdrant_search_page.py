#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qdrant_search_page.py - Qdrant検索ページ
========================================
Qdrantベクトルデータベースを使用した意味検索

機能:
- コレクション検索
- 埋め込みベクトル生成
- AI応答生成
- スコア詳細表示（Original + Rerank）
"""

import warnings
import pandas as pd
import streamlit as st
from helper.helper_llm import create_llm_client
from qdrant_client import QdrantClient

# サービスモジュールからインポート
from services.qdrant_service import (
    QdrantDataFetcher,
    embed_query_for_search,
    get_collection_embedding_params,
)
from services.file_service import load_source_qa_data
from qdrant_client_wrapper import search_collection, \
    embed_sparse_query_unified  # Import search_collection and embed_sparse_query_unified


def show_qdrant_search_page():
    """画面5: Qdrant検索"""
    st.title("🔎 Qdrant検索")
    st.caption("Qdrantベクトルデータベースを使用した意味検索")

    # Qdrant接続確認
    qdrant_url = "http://localhost:6333"
    client = None
    available_collections = []

    try:
        client = QdrantClient(url=qdrant_url)
        collections_response = client.get_collections()
        available_collections = [col.name for col in collections_response.collections]
    except Exception:
        st.error(f"❌ Qdrantサーバーに接続できません: {qdrant_url}")
        st.warning("Qdrantサーバーが起動していることを確認してください")
        st.code("python server.py", language="bash")
        st.caption("または")
        st.code("docker run -p 6333:6333 qdrant/qdrant", language="bash")
        return

    st.subheader("📚 コレクションの一覧")

    # 全コレクション情報を取得（シンプル版）
    try:
        collections_response = client.get_collections()
        collections_info = []

        for col in collections_response.collections:
            # CollectionInfoから直接情報を取得
            collections_info.append({
                "コレクション名": col.name,
            })

        if collections_info:
            collections_df = pd.DataFrame(collections_info)
            # FIXED: use_container_width=True を use_container_width=True に変更
            st.dataframe(collections_df, use_container_width=True, hide_index=True)
            st.caption(f"✅ 合計 {len(collections_info)} 個のコレクションが見つかりました")

            # 詳細情報を個別に取得して表示
            with st.expander("📊 詳細情報", expanded=False):
                for col_name in [c["コレクション名"] for c in collections_info]:
                    try:
                        col_detail = client.get_collection(col_name)
                        st.markdown(f"**{col_name}**")
                        st.json({
                            "vectors_count": getattr(col_detail, 'vectors_count', 'N/A'),
                            "points_count" : getattr(col_detail, 'points_count', 'N/A'),
                            "status"       : str(getattr(col_detail, 'status', 'N/A'))
                        })
                    except Exception as e:
                        st.error(f"{col_name}: {e}")
        else:
            st.info("コレクションが存在しません")

    except Exception as e:
        st.error(f"コレクション一覧の取得に失敗しました: {e}")

    st.divider()

    if not available_collections:
        st.warning("利用可能なコレクションがありません")
        st.info("先に「Qdrant登録」でデータを登録してください")
        return

    # サイドバー：検索設定
    with st.sidebar:
        st.header("🔧 検索設定")

        # コレクション選択
        collection = st.selectbox(
            "コレクション",
            options=available_collections,
            help="検索対象のコレクションを選択",
        )

        # コレクション情報表示
        if client and collection:
            col_info = get_collection_embedding_params(client, collection)
            st.info(f"📊 {col_info['model']} ({col_info['dims']}次元)")

        # Top-K設定
        topk = st.slider(
            "検索結果数（Top-K）", min_value=1, max_value=20, value=5, step=1
        )

        # ハイブリッド検索の有効化トグル
        use_hybrid_search = st.checkbox("⚙️ ハイブリッド検索を有効にする (Sparse + Dense)", value=False)

        # デバッグモード
        debug_mode = st.checkbox("🐛 デバッグモード", value=False)

        # スコア詳細表示モード
        show_score_details = st.checkbox("📊 スコア詳細表示", value=True, help="Original/Rerankスコアを表示")

    # メインエリア
    # セッション状態の初期化
    if "search_query" not in st.session_state:
        st.session_state.search_query = ""

    # コレクションデータプレビューセクション
    with st.expander("📋 コレクションデータプレビュー", expanded=False):
        try:
            st.caption(f"📊 コレクション: **{collection}** から100件を表示")

            # Qdrantから直接データを取得（scrollを使用）
            points, next_page_offset = client.scroll(
                collection_name=collection,
                limit=100,
                with_payload=True,
                with_vectors=False
            )

            if points:
                # DataFrameに変換
                data_list = []
                for point in points:
                    payload = point.payload or {}
                    data_list.append({
                        "ID"      : point.id,
                        "Question": payload.get("question", "N/A"),
                        "Answer"  : payload.get("answer", "N/A"),
                        "Source"  : payload.get("source", "N/A")
                    })

                df_preview = pd.DataFrame(data_list)

                # コレクションの総ポイント数を取得
                try:
                    col_info = client.get_collection(collection)
                    total_points = col_info.points_count if hasattr(col_info, 'points_count') else "N/A"
                except:
                    total_points = "N/A"

                st.caption(f"📈 表示: {len(data_list)} 件 / 総ポイント数: {total_points}")

                # データフレーム表示（スクロール可能）
                # FIXED: use_container_width=True を use_container_width=True に変更
                st.dataframe(
                    df_preview,
                    use_container_width=True,
                    hide_index=True,
                    height=600,  # スクロール可能な高さ
                    column_config={
                        "ID"      : st.column_config.NumberColumn("ID", width="small"),
                        "Question": st.column_config.TextColumn("質問", width="medium"),
                        "Answer"  : st.column_config.TextColumn("回答", width="large"),
                        "Source"  : st.column_config.TextColumn("ソース", width="small")
                    }
                )
            else:
                st.info(f"コレクション '{collection}' にデータが見つかりませんでした。")

        except Exception as e:
            st.error(f"データ取得エラー: {e}")
            if debug_mode:
                import traceback
                st.code(traceback.format_exc())

    st.divider()

    # 検索入力
    st.subheader("🔍 検索")
    query = st.text_input(
        "検索クエリを入力してください",
        value=st.session_state.search_query,
        placeholder="検索したい質問を入力してください",
    )

    col_search, col_clear = st.columns([4, 1])
    with col_search:
        do_search = st.button("🔍 検索実行", type="primary", use_container_width=True)
    with col_clear:
        if st.button("🗑️ クリア", use_container_width=True):
            st.session_state.search_query = ""
            st.rerun()

    # 検索実行
    if do_search and query.strip():
        try:
            client = QdrantClient(url=qdrant_url)

            # コレクションに対応した埋め込み設定を取得
            collection_config = get_collection_embedding_params(client, collection)
            embedding_model = collection_config["model"]
            embedding_dims = collection_config.get("dims")

            # クエリの埋め込みベクトルを生成
            with st.spinner("クエリの埋め込みベクトルを生成中..."):
                qvec = embed_query_for_search(query, model=embedding_model)

                if debug_mode:
                    st.success(f"✅ {len(qvec)}次元のベクトルを生成しました")

            # Qdrantで検索
            with st.spinner("検索中..."):
                sparse_vector = None
                if use_hybrid_search:
                    with st.spinner("Sparseベクトルを生成中..."):
                        # sparse_vector生成
                        sparse_vector = embed_sparse_query_unified(query)
                        if debug_mode:
                            st.success("✅ Sparseベクトルを生成しました")

                # search_collection関数を呼び出し
                hits_dict_list = search_collection(  # search_collection returns List[Dict[str, Any]]
                    client=client,
                    collection_name=collection,
                    query_vector=qvec,
                    sparse_vector=sparse_vector if use_hybrid_search else None,  # ハイブリッド検索が有効な場合のみSparseベクトルを渡す
                    limit=topk
                )

            # search_collectionの戻り値はDictのリストなので、QdrantのPointStructに変換 (UI表示のため)
            class MockHit:  # 既存のUI表示ロジックに合わせるため
                def __init__(self, hit_dict):
                    self.score = hit_dict.get("score", 0.0)
                    self.original_score = hit_dict.get("original_score", 0.0)
                    self.rerank_score = hit_dict.get("rerank_score", 0.0)
                    self.id = hit_dict.get("id")
                    self.payload = hit_dict.get("payload")

            hits = [MockHit(h) for h in hits_dict_list]

            # 検索結果を表示
            st.divider()
            st.subheader(f"📊 検索結果 (Top {len(hits)})")

            if not hits:
                st.warning("検索結果が見つかりませんでした")
                return

            # ===================================================================
            # スコア分布の可視化（追加）
            # ===================================================================
            if show_score_details and hits:
                with st.expander("📈 スコア分布", expanded=True):
                    # スコアデータを準備
                    score_data = []
                    for i, h in enumerate(hits, 1):
                        if h.original_score > 0:
                            score_data.append({
                                "Result"        : f"Result {i}",
                                "Original Score": h.original_score,
                                "Rerank Score"  : h.rerank_score,
                            })
                        else:
                            score_data.append({
                                "Result": f"Result {i}",
                                "Score" : h.score,
                            })

                    df_scores = pd.DataFrame(score_data)

                    # 棒グラフで表示
                    if "Original Score" in df_scores.columns:
                        st.bar_chart(df_scores.set_index("Result")[["Original Score", "Rerank Score"]])
                    else:
                        st.bar_chart(df_scores.set_index("Result")["Score"])

            # ===================================================================
            # 結果をカード形式で表示（改善版）
            # ===================================================================
            for i, h in enumerate(hits, 1):
                # スコア情報の準備
                score = h.score
                original_score = h.original_score
                rerank_score = h.rerank_score

                # スコア表示テキストと色の決定
                if original_score > 0 and show_score_details:
                    # スコアの変化を計算
                    diff = rerank_score - original_score

                    # 変化の程度に応じてアイコンを選択
                    if diff > 0.1:
                        score_icon = "🟢"  # 大幅向上
                        change_text = f"+{diff:.3f}"
                    elif diff < -0.1:
                        score_icon = "🔴"  # 大幅低下
                        change_text = f"{diff:.3f}"
                    else:
                        score_icon = "🟡"  # 変化なし
                        change_text = "変化なし"

                    score_display = f"{score_icon} **Rerank: {rerank_score:.4f}** (Original: {original_score:.4f})"
                    score_change = change_text
                else:
                    score_display = f"**Score: {score:.4f}**"
                    score_change = None

                # ペイロード情報
                payload = h.payload or {}
                question = payload.get("question", "N/A")
                answer = payload.get("answer", "N/A")
                source = payload.get("source", "N/A")

                # カード表示
                with st.container():
                    st.markdown(f"### Result {i} - {score_display}")

                    # メトリクス行
                    if show_score_details:
                        col_metrics = st.columns([1, 1, 1, 2])
                        with col_metrics[0]:
                            st.metric("表示スコア", f"{score:.3f}")
                        with col_metrics[1]:
                            if original_score > 0:
                                st.metric("元のスコア", f"{original_score:.3f}")
                        with col_metrics[2]:
                            if score_change:
                                st.metric("変化", score_change)
                        with col_metrics[3]:
                            st.caption(f"ソース: {source}")
                    else:
                        col_simple = st.columns([1, 3])
                        with col_simple[0]:
                            st.metric("スコア", f"{score:.3f}")
                        with col_simple[1]:
                            st.caption(f"ソース: {source}")

                    # 質問と回答
                    st.markdown("**質問:**")
                    st.info(question)

                    st.markdown("**回答:**")
                    st.success(answer)

                    # デバッグ情報（オプション）
                    if debug_mode:
                        with st.expander("🐛 デバッグ情報", expanded=False):
                            st.json({
                                "id"            : h.id,
                                "score"         : score,
                                "original_score": original_score,
                                "rerank_score"  : rerank_score,
                                "payload_keys"  : list(payload.keys()) if payload else []
                            })

                    st.divider()

            # ===================================================================
            # 最高スコアの結果でAI応答生成
            # ===================================================================
            if hits:
                best_hit = hits[0]
                st.divider()
                st.subheader("🧠 AI応答（OpenAI）")

                best_payload = best_hit.payload or {}
                best_question = best_payload.get("question", "")
                best_answer = best_payload.get("answer", "")
                best_score = best_hit.score

                # スコア情報を含めたプロンプト
                score_info = ""
                if best_hit.original_score > 0:
                    score_info = f"""
検索スコア詳細:
- 最終スコア (Rerank): {best_hit.rerank_score:.4f}
- 元のスコア (Original): {best_hit.original_score:.4f}
"""
                else:
                    score_info = f"検索スコア: {best_score:.4f}"

                qa_prompt = f"""以下の検索結果とユーザーの質問を踏まえて、日本語で簡潔かつ正確に回答してください。

ユーザーの質問:
{query}

{score_info}

検索結果の質問: {best_question}
検索結果の回答: {best_answer}
"""

                with st.expander("📝 プロンプト詳細", expanded=False):
                    st.code(qa_prompt)

                try:
                    with st.spinner("OpenAI GPTが回答を生成中..."):
                        llm_client = create_llm_client(provider="openai")
                        generated_answer = llm_client.generate_content(
                            prompt=qa_prompt,
                            model="gpt-5.4-mini"
                        )

                    if generated_answer and generated_answer.strip():
                        st.markdown("**AI応答:**")
                        st.write(generated_answer)
                    else:
                        st.info("応答テキストを取得できませんでした")
                except Exception as gen_err:
                    st.error(f"AI応答生成に失敗しました: {str(gen_err)}")
                    if debug_mode:
                        st.exception(gen_err)

        except Exception as e:
            st.error(f"❌ エラーが発生しました: {str(e)}")
            if debug_mode:
                st.exception(e)

            if "Connection refused" in str(e):
                st.warning("Qdrantサーバーが起動していることを確認してください")
                st.code("python server.py", language="bash")
            elif "collection" in str(e).lower() and "not found" in str(e).lower():
                st.warning(f"コレクション '{collection}' が見つかりません")
                st.info("「Qdrant登録」でデータを登録してください")
