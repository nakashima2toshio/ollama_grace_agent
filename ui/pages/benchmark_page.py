#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
benchmark_page.py - GRACE パイプライン性能計測ページ

GRACEパイプライン（Plan→Execute→Confidence→Intervention→Replan）の
性能を計測・可視化する Streamlit ページ。

使用方法::

    from ui.pages.benchmark_page import show_benchmark_page
    show_benchmark_page()
"""

import pandas as pd
import streamlit as st

from grace.benchmark import (
    BENCHMARK_CSV_PATH,
    BENCHMARK_QUERIES,
    BenchmarkRunner,
)
from grace.config import get_config


def show_benchmark_page() -> None:
    """GRACE Benchmark ページのエントリポイント"""
    st.header("📊 GRACE Benchmark (Phase 5)")
    st.caption(
        "GRACEパイプライン（Plan → Execute → Confidence → Intervention → Replan）"
        "の各フェーズ性能を計測し、CSV に記録・可視化します。"
    )
    st.divider()

    tab_run, tab_results = st.tabs(["▶ 実行", "📈 結果表示"])

    with tab_run:
        _run_tab()

    with tab_results:
        _results_tab()


def _run_tab() -> None:
    config = get_config()

    st.subheader("単一クエリ実行")

    query_labels = [
        f"{q['id']} [{q['level']}] {q['category']} — {q['text'][:45]}…"
        for q in BENCHMARK_QUERIES
    ]
    col1, col2 = st.columns([4, 1])
    with col1:
        idx = st.selectbox(
            "クエリ選択",
            range(len(BENCHMARK_QUERIES)),
            format_func=lambda i: query_labels[i],
        )
    with col2:
        run_number = st.number_input("試行番号", min_value=1, max_value=10, value=1)

    selected = BENCHMARK_QUERIES[idx]
    st.info(
        f"**{selected['id']}** | {selected['level']} | {selected['category']}\n\n"
        f"{selected['text']}"
    )

    st.divider()
    st.subheader("一括実行（全クエリセット）")
    col3, col4 = st.columns(2)
    with col3:
        runs_per_query = st.slider("各クエリの試行回数", 1, 5, 3)
    with col4:
        run_all = st.checkbox("全クエリ（Q01–Q12）を実行する")

    st.divider()
    if st.button("▶ ベンチマーク実行", type="primary"):
        runner = BenchmarkRunner(config=config)

        if run_all:
            total = len(BENCHMARK_QUERIES) * runs_per_query
            st.info(f"全 {len(BENCHMARK_QUERIES)} クエリ × {runs_per_query} 回 = {total} 回実行します…")
            progress_bar = st.progress(0)
            status_text = st.empty()
            done = 0
            for q in BENCHMARK_QUERIES:
                for r in range(1, runs_per_query + 1):
                    done += 1
                    status_text.text(f"実行中: {q['id']} — Run {r}/{runs_per_query}")
                    progress_bar.progress(done / total)
                    runner.run(
                        query_id=q["id"],
                        query_text=q["text"],
                        run_number=r,
                        level=q["level"],
                        category=q["category"],
                    )
            status_text.text("完了！")
            st.success(f"{total} 件完了。結果 → {BENCHMARK_CSV_PATH}")
        else:
            with st.spinner(f"{selected['id']} を実行中…"):
                session = runner.run(
                    query_id=selected["id"],
                    query_text=selected["text"],
                    run_number=run_number,
                    level=selected["level"],
                    category=selected["category"],
                )
            st.success("実行完了")
            _show_session_metrics(session)


def _show_session_metrics(session) -> None:
    st.subheader("計測結果")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("合計時間",   f"{session.total_time_sec:.2f} s")
    c2.metric("全体信頼度", f"{session.overall_confidence:.3f}")
    c3.metric("Intervention", session.intervention_level or "-")
    c4.metric("推定コスト", f"${session.cost_usd:.5f}")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Plan 時間",    f"{session.plan_time_sec:.2f} s")
    c6.metric("Execute 時間", f"{session.execute_time_sec:.2f} s")
    c7.metric("リプラン回数", session.replan_count)
    c8.metric("ステータス",   session.overall_status or "-")

    c9, c10, c11, c12 = st.columns(4)
    c9.metric("Input tokens",  f"{session.input_tokens:,}")
    c10.metric("Output tokens", f"{session.output_tokens:,}")
    c11.metric("RAG ステップ", session.rag_step_count)
    c12.metric("ソース総数",   session.sources_total)

    if session.step_confidences:
        st.markdown(
            f"**ステップ信頼度** — "
            f"min: `{session.min_step_confidence:.3f}` / "
            f"max: `{session.max_step_confidence:.3f}`"
        )


def _results_tab() -> None:
    if not BENCHMARK_CSV_PATH.exists():
        st.info("まだ結果がありません。「▶ 実行」タブでベンチマークを実行してください。")
        return

    df = pd.read_csv(BENCHMARK_CSV_PATH)
    if df.empty:
        st.info("CSV にデータがありません。")
        return

    st.subheader("フィルタ")
    col1, col2, col3 = st.columns(3)
    with col1:
        levels = ["全て"] + sorted(df["level"].dropna().unique().tolist())
        sel_level = st.selectbox("難易度", levels)
    with col2:
        providers = ["全て"] + sorted(df["provider"].dropna().unique().tolist())
        sel_provider = st.selectbox("プロバイダー", providers)
    with col3:
        categories = ["全て"] + sorted(df["category"].dropna().unique().tolist())
        sel_cat = st.selectbox("カテゴリ", categories)

    fdf = df.copy()
    if sel_level    != "全て": fdf = fdf[fdf["level"]    == sel_level]
    if sel_provider != "全て": fdf = fdf[fdf["provider"] == sel_provider]
    if sel_cat      != "全て": fdf = fdf[fdf["category"] == sel_cat]

    st.caption(f"{len(fdf)} 件表示 / 全 {len(df)} 件")
    st.divider()

    st.subheader("サマリー")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("平均合計時間",   f"{fdf['total_time_sec'].mean():.2f} s")
    c2.metric("平均信頼度",     f"{fdf['overall_confidence'].mean():.3f}")
    c3.metric("平均コスト",     f"${fdf['cost_usd'].mean():.5f}")
    c4.metric("リプラン発生率", f"{(fdf['replan_count'] > 0).mean() * 100:.1f} %")

    c5, c6, c7 = st.columns(3)
    c5.metric("平均 Plan 時間",    f"{fdf['plan_time_sec'].mean():.2f} s")
    c6.metric("平均 Execute 時間", f"{fdf['execute_time_sec'].mean():.2f} s")
    c7.metric("平均 RAG ステップ", f"{fdf['rag_step_count'].mean():.1f}")

    st.divider()
    st.subheader("チャート")

    ch1, ch2 = st.columns(2)
    with ch1:
        st.markdown("**クエリ別 平均合計時間（秒）**")
        st.bar_chart(fdf.groupby("query_id")["total_time_sec"].mean().sort_index())
    with ch2:
        st.markdown("**クエリ別 平均信頼度**")
        st.bar_chart(fdf.groupby("query_id")["overall_confidence"].mean().sort_index())

    ch3, ch4 = st.columns(2)
    with ch3:
        st.markdown("**Intervention レベル分布**")
        st.bar_chart(fdf["intervention_level"].value_counts())
    with ch4:
        st.markdown("**難易度別 平均合計時間**")
        st.bar_chart(fdf.groupby("level")["total_time_sec"].mean())

    if df["provider"].nunique() > 1:
        st.divider()
        st.subheader("プロバイダー比較")
        pv_time = fdf.groupby("provider")["total_time_sec"].mean().rename("平均合計時間(s)")
        pv_conf = fdf.groupby("provider")["overall_confidence"].mean().rename("平均信頼度")
        pv_cost = fdf.groupby("provider")["cost_usd"].mean().rename("平均コスト($)")
        st.dataframe(pd.concat([pv_time, pv_conf, pv_cost], axis=1).reset_index(),
                     use_container_width=True)

    st.divider()
    st.subheader("生データ")
    display_cols = [
        "timestamp", "query_id", "level", "category", "model", "provider", "run_number",
        "total_time_sec", "plan_time_sec", "execute_time_sec",
        "overall_confidence", "intervention_level", "replan_count",
        "input_tokens", "output_tokens", "cost_usd", "overall_status",
    ]
    show_cols = [c for c in display_cols if c in fdf.columns]
    st.dataframe(fdf[show_cols], use_container_width=True)

    csv_bytes = fdf.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 CSV ダウンロード",
        csv_bytes,
        file_name="benchmark_filtered.csv",
        mime="text/csv",
    )
