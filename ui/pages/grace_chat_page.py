# grace_chat_page.py
# !/usr/bin/env python
# -*- coding: utf-8 -*-
"""
grace_chat_page.py - 自律型エージェント チャット画面
===================================================
GRACE (Planner + Executor) アーキテクチャを使用したエージェントとの対話インターフェース。

改修(2): ReActAgent → Planner/Executor 接続
"""

import os
import logging
import streamlit as st
import pandas as pd
from typing import Dict, List, Any, Optional, Generator
from qdrant_client import QdrantClient

# Configuration and Services
from config import AgentConfig, GeminiConfig

# --- STEP 2-1: import変更 ---
# 旧: from services.agent_service import ReActAgent, get_available_collections_from_qdrant_helper
from services.agent_service import get_available_collections_from_qdrant_helper  # これだけ残す
from grace import (
    Planner, create_planner,
    Executor, create_executor,
    ExecutionPlan, ExecutionState, ExecutionResult,
    StepResult, StepStatus,
    GraceConfig, get_config as get_grace_config,
)
from qdrant_client_wrapper import get_qdrant_client

logger = logging.getLogger(__name__)


def show_grace_chat_page():
    st.title("🧠 自律型エージェント (GRACE)")
    st.caption("Goal-Reasoning-Action-Critique-Execute Architecture — Planner + Executor")

    # -------------------------------------------------------------------------
    # コレクションデータの表示エリア (変更なし)
    # -------------------------------------------------------------------------
    with st.expander("📊 コレクションデータの表示", expanded=False):
        st.markdown("登録されているコレクションから、質問と回答のデータを100件表示します。")

        # プレビュー用のコレクション取得
        preview_collections = get_available_collections_from_qdrant_helper()

        if preview_collections:
            col1, col2 = st.columns([1, 3])
            with col1:
                target_collection = st.selectbox(
                    "コレクションを選択:",
                    preview_collections,
                    index=0,
                    key="grace_collection_selector"
                )

            if target_collection:
                try:
                    # Qdrantクライアント接続（シングルトン）
                    client = get_qdrant_client()

                    st.caption(f"📊 コレクション: **{target_collection}** から100件を表示")

                    # Qdrantから直接データを取得（scrollを使用）
                    points, next_page_offset = client.scroll(
                        collection_name=target_collection,
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
                                "Answer"  : payload.get("answer", "N/A")
                            })

                        df_preview = pd.DataFrame(data_list)

                        # コレクションの総ポイント数を取得
                        try:
                            col_info = client.get_collection(target_collection)
                            total_points = col_info.points_count if hasattr(col_info, 'points_count') else "N/A"
                        except:
                            total_points = "N/A"

                        st.caption(f"📈 表示: {len(data_list)} 件 / 総ポイント数: {total_points}")

                        # データフレーム表示（スクロール可能）
                        st.dataframe(
                            df_preview,
                            use_container_width=True,
                            hide_index=True,
                            height=600,
                            column_config={
                                "ID"      : st.column_config.NumberColumn("ID", width="small"),
                                "Question": st.column_config.TextColumn("質問 (Question)", width="medium"),
                                "Answer"  : st.column_config.TextColumn("回答 (Answer)", width="large")
                            }
                        )
                    else:
                        st.info(f"コレクション '{target_collection}' にデータが見つかりませんでした。")

                except Exception as e:
                    st.error(f"データ取得エラー: {e}")
        else:
            st.warning("表示可能なコレクションがありません。Qdrantの状態を確認してください。")

    # -------------------------------------------------------------------------
    # GRACEエージェントのメイン機能
    # -------------------------------------------------------------------------
    st.divider()
    st.markdown("### 💬 チャット")

    # サイドバー設定
    with st.sidebar:
        st.header("⚙️ GRACE エージェント設定")

        # モデル選択（起動時デフォルト: CLI --model > 環境変数 > config デフォルト）
        _default_model = st.session_state.get("startup_model", AgentConfig.MODEL_NAME)
        selected_model = st.selectbox(
            "使用モデル (Model)",
            options=GeminiConfig.AVAILABLE_MODELS,
            index=GeminiConfig.AVAILABLE_MODELS.index(_default_model)
            if _default_model in GeminiConfig.AVAILABLE_MODELS else 0
        )

        # コレクション一覧の取得（表示用・参考情報）
        all_collections = get_available_collections_from_qdrant_helper()

        if not all_collections:
            st.warning("利用可能なコレクションが見つかりません。Qdrantサーバーを確認してください。")
            all_collections = ["(None)"]

        # 検索対象コレクションの表示（GRACEは全コレクション自動検索）
        selected_collections = st.multiselect(
            "検索対象コレクション (参考表示)",
            options=all_collections,
            default=all_collections if all_collections != ["(None)"] else [],
            help="GRACEエージェントはQdrant上の全コレクションを自動検索します。"
        )

        # ハイブリッド検索（表示のみ・GRACE側デフォルトに任せる）
        use_hybrid_search = st.checkbox(
            "⚡ ハイブリッド検索 (Sparse + Dense)",
            value=True,
            help="GRACEエージェント内部のデフォルト動作に従います",
            disabled=True  # GRACE側のデフォルトに任せるため無効化
        )

        # --- STEP 2-4: session_state キー整理 ---
        if st.button("🗑️ 会話履歴をクリア"):
            st.session_state.grace_chat_history = []
            # Planner / Executor をクリアして再初期化を強制
            for key in ["grace_planner", "grace_executor",
                        "grace_current_collections", "grace_current_model"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

        # キャッシュリセットボタン
        if st.button("🔄 キャッシュをリセット"):
            from agent_cache import collection_cache
            if "grace_session_id" in st.session_state:
                collection_cache.clear(st.session_state.grace_session_id)
                st.toast("✅ キャッシュをクリアしました")

        # キャッシュ統計表示
        with st.expander("📊 キャッシュ統計", expanded=False):
            from agent_cache import collection_cache
            if "grace_session_id" in st.session_state:
                stats = collection_cache.get_stats(st.session_state.grace_session_id)
                if stats.get("cached"):
                    st.metric("キャッシュ状態", "🟢 ヒット")
                    st.metric("コレクション", stats.get("collection", "N/A"))
                    st.metric("前回スコア", f"{stats.get('last_score', 0):.3f}")
                    st.metric("ヒット回数", stats.get("hit_count", 0))
                    st.metric("経過時間", f"{stats.get('age_seconds', 0):.1f}秒")
                else:
                    st.metric("キャッシュ状態", "⚪ なし")
            else:
                st.info("セッションIDが見つかりません")

    # セッション状態の初期化
    if "grace_chat_history" not in st.session_state:
        st.session_state.grace_chat_history = []

    # エージェント用のセッションIDを初期化
    if "grace_session_id" not in st.session_state:
        import uuid
        st.session_state.grace_session_id = str(uuid.uuid4())
        logger.info(f"New GRACE session ID created: {st.session_state.grace_session_id}")

    # --- STEP 2-2: 初期化ロジック変更 ---
    current_model_key = "grace_current_model"
    should_reinitialize = False

    # モデルの変更チェック
    if current_model_key not in st.session_state:
        should_reinitialize = True
    elif st.session_state[current_model_key] != selected_model:
        should_reinitialize = True
        st.toast(f"モデルが変更されました: {selected_model}")

    if should_reinitialize or "grace_planner" not in st.session_state or "grace_executor" not in st.session_state:
        try:
            # GraceConfig を取得し、UIで選択したモデルを反映
            grace_config = get_grace_config()
            grace_config.llm.model = selected_model

            # Planner + Executor を初期化
            st.session_state.grace_planner = create_planner(
                config=grace_config,
                model_name=selected_model
            )
            st.session_state.grace_executor = create_executor(
                config=grace_config
            )

            st.session_state[current_model_key] = selected_model
            st.toast("GRACE Planner + Executor の準備が完了しました。")
        except Exception as e:
            st.error(f"GRACE エージェントの初期化に失敗しました: {e}")
            logger.error(f"GRACE init failed: {e}", exc_info=True)
            return

    # チャット履歴の表示
    for message in st.session_state.grace_chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # --- STEP 2-3: ユーザー入力処理 + イベントループ変更 ---
    if prompt := st.chat_input("質問を入力してください..."):
        st.chat_message("user").markdown(prompt)
        st.session_state.grace_chat_history.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            final_response_content = ""

            try:
                # ============================================================
                # Phase 1: Plan — 計画策定
                # ============================================================
                with st.expander("📋 計画策定 (Plan)", expanded=True):
                    with st.spinner("計画を生成中..."):
                        plan: ExecutionPlan = st.session_state.grace_planner.create_plan(prompt)

                    # --- 計画概要 ---
                    st.markdown(f"**目標**: {plan.original_query}")
                    col_plan1, col_plan2, col_plan3 = st.columns(3)
                    with col_plan1:
                        st.metric("複雑度", f"{plan.complexity:.1f}")
                    with col_plan2:
                        st.metric("ステップ数", plan.estimated_steps)
                    with col_plan3:
                        st.metric("要確認", "⚠️ はい" if plan.requires_confirmation else "✅ いいえ")

                    if plan.success_criteria:
                        st.caption(f"🎯 成功基準: {plan.success_criteria}")

                    st.divider()

                    # --- 各ステップ詳細 ---
                    for step in plan.steps:
                        action_icon = {
                            "rag_search": "🔍",
                            "web_search": "🌐",
                            "reasoning": "🧠",
                            "ask_user": "💬",
                            "code_execute": "💻",
                            "run_legacy_agent": "🤖",
                        }.get(step.action, "▶️")

                        deps = f"  ← 依存: Step {step.depends_on}" if step.depends_on else ""
                        st.markdown(f"**{action_icon} Step {step.step_id}: [{step.action}]** {step.description}{deps}")

                        detail_parts = []
                        if step.query:
                            detail_parts.append(f"🔑 **Query**: `{step.query}`")
                        if step.collection:
                            detail_parts.append(f"📁 **Collection**: `{step.collection}`")
                        if step.expected_output:
                            detail_parts.append(f"📤 **期待出力**: {step.expected_output}")
                        if step.fallback:
                            detail_parts.append(f"🔄 **Fallback**: `{step.fallback}`")

                        if detail_parts:
                            for part in detail_parts:
                                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{part}")

                    # --- Plan JSON (デバッグ用) ---
                    with st.expander("🔧 Plan JSON (raw)", expanded=False):
                        st.json(plan.model_dump(mode="json", exclude={"created_at"}))

                # ============================================================
                # Phase 2-4: Execute — 実行 (Confidence/Intervention/Replan)
                # ============================================================
                with st.expander("⚡ 実行 (Execute)", expanded=True):
                    executor: Executor = st.session_state.grace_executor
                    gen = executor.execute_plan_generator(plan)

                    # 思考プロセスログ蓄積用
                    thought_log: List[str] = []
                    thought_container = st.container()

                    execution_result: Optional[ExecutionResult] = None

                    try:
                        while True:
                            yielded = next(gen)

                            if isinstance(yielded, ExecutionState):
                                # --- ステップ完了/一時停止の通知 ---
                                state: ExecutionState = yielded
                                sid = state.current_step_id
                                status = state.step_statuses.get(sid, "unknown")

                                # 信頼度を表示（結果がある場合）
                                conf_str = ""
                                if sid in state.step_results:
                                    conf_str = f" (信頼度: {state.step_results[sid].confidence:.2f})"

                                status_icon = {
                                    StepStatus.SUCCESS: "✅",
                                    StepStatus.FAILED: "❌",
                                    StepStatus.SKIPPED: "⏭️",
                                    StepStatus.RUNNING: "🔄",
                                    StepStatus.PENDING: "⏳",
                                }.get(status, "❓")

                                log_entry = f"Step {sid}: {status_icon} {status.value if hasattr(status, 'value') else status}{conf_str}"
                                thought_log.append(log_entry)

                                with thought_container:
                                    st.markdown(log_entry)

                                # 介入リクエストがある場合
                                if state.is_paused and state.intervention_request:
                                    req = state.intervention_request
                                    st.warning(f"⚠️ 確認が必要: {req.message}")
                                    # Phase 3 HITL: 現時点では自動続行
                                    st.info("（自動続行します）")

                            elif isinstance(yielded, dict):
                                # --- ツール実行結果などのイベント ---
                                event_type = yielded.get("type", "")

                                if event_type == "log":
                                    log_entry = yielded["content"]
                                    thought_log.append(log_entry)
                                    with thought_container:
                                        st.markdown(log_entry)
                                        st.divider()

                                elif event_type == "tool_call":
                                    log_entry = f"🛠️ **Tool Call:** `{yielded.get('name', '')}`\nArgs: `{yielded.get('args', '')}`"
                                    thought_log.append(log_entry)
                                    with thought_container:
                                        st.markdown(log_entry)

                                elif event_type == "tool_result":
                                    content = yielded.get("content", "")
                                    display = content[:500] + "..." if len(content) > 500 else content
                                    log_entry = f"📝 **Tool Result:**\n{display}"
                                    thought_log.append(log_entry)
                                    with thought_container:
                                        st.markdown(log_entry)
                                        st.divider()

                                elif event_type == "final_answer":
                                    # Legacy Agent 経由の最終回答
                                    final_response_content = yielded.get("content", "")

                    except StopIteration as e:
                        # Generator の return 値 = ExecutionResult
                        execution_result = e.value

                # ============================================================
                # 最終回答の表示
                # ============================================================
                if execution_result and execution_result.final_answer:
                    final_response_content = execution_result.final_answer

                    # メタ情報の表示
                    with st.expander("📊 実行結果サマリ", expanded=False):
                        st.markdown(f"**ステータス**: {execution_result.overall_status}")
                        st.markdown(f"**全体信頼度**: {execution_result.overall_confidence:.2f}")
                        st.markdown(f"**リプラン回数**: {execution_result.replan_count}")
                        if execution_result.total_execution_time_ms:
                            st.markdown(f"**実行時間**: {execution_result.total_execution_time_ms}ms")

                if final_response_content:
                    st.markdown(final_response_content)
                    st.session_state.grace_chat_history.append(
                        {"role": "assistant", "content": final_response_content}
                    )
                else:
                    st.warning("エージェントからの応答がありませんでした。")

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
                logger.error(f"GRACE Chat Error: {e}", exc_info=True)


if __name__ == "__main__":
    show_grace_chat_page()
