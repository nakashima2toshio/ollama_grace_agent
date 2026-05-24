# ベンチマーク実施 TODO

参照仕様書: `docs/grace_agent_performance_comparison_spec.md` (v1.3)

---

## ✅ Phase 1 完了済み

| 項目 | 状態 |
|---|---|
| `grace/benchmark.py` 全4リポジトリ配備 | ✅ |
| `tests/test_agent_4operations.py` 全4リポジトリ配備 | ✅ |
| `grace/config.py` モデル名修正（gpt-5.4-mini / gemini-2.0-flash / gemma4:e4b） | ✅ |
| spec v1.3 全4リポジトリ配備 | ✅ |

---

## 🔲 Phase 1 補完：インターフェース＆環境確認（ユーザー側）

**TODO-1: schemas.py のフィールド整合チェック**

`benchmark.py` が以下のフィールドを期待しているため、`grace/schemas.py` の実際のクラス定義と一致するか確認。

```python
# ExecutionPlan に必要
plan.complexity              # float
plan.steps                   # list
plan.requires_confirmation   # bool
plan.plan_id                 # str

# ExecutionResult に必要
result.overall_confidence    # float
result.replan_count          # int
result.overall_status        # str
result.total_token_usage     # dict (input_tokens / output_tokens)
result.step_results          # list of StepResult

# StepResult に必要
step.confidence  # float
step.sources     # list
```

**TODO-2: temperature=0.0 設定確認**

```python
# 各 grace/config.py で確認
LLMConfig(
    temperature=0.0,   # ← これが入っているか
    ...
)
```

**TODO-3: ローカルインフラ確認**

```bash
# Qdrant 起動確認
curl http://localhost:6333/collections
# → cc_news_2per (3072次元) と cc_news_2per_768 (768次元) が存在すること

# API キー確認（各リポジトリの .env）
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
ANTHROPIC_API_KEY=sk-ant-...

# Ollama モデル確認
ollama list
# → gemma4:e4b, llama3.2, nomic-embed-text が pull 済みであること
ollama serve  # 起動
```

> **注意**: ベンチマークはローカル実行が前提。Qdrant・Ollama はローカル起動必須。
> `pytest tests/test_agent_4operations.py` のみ CI でも実行可能（APIキー・Qdrant 不要）。

---

## 🔲 Phase 2：予備実験（動作確認）

**TODO-4: anthropic で Q01 1回実行（最もシンプルなケース）**

```bash
cd anthropic_grace_agent
python -c "
from grace.benchmark import BenchmarkRunner
runner = BenchmarkRunner()
runner.run('Q01',
           'cc_newsコレクションにある最近のAI関連ニュースを3件教えてください',
           run_number=1, level='Easy', category='事実検索')
"
```

確認ポイント：
- `[BENCHMARK]` ログが標準出力に出るか
- `logs/benchmark_results.csv` が生成されるか
- `intervention_level` が `SILENT` または `NOTIFY` になるか

**TODO-5: Q09（曖昧クエリ）で ESCALATE 動作確認**

```bash
python -c "
from grace.benchmark import BenchmarkRunner
runner = BenchmarkRunner()
runner.run('Q09', '最近の重要なニュースを教えて',
           run_number=1, level='Easy', category='曖昧')
"
# → intervention_level: ESCALATE が期待値
```

**TODO-6: エラー発生時の修正**

schemas.py のフィールド名が異なる場合 → `benchmark.py` の `getattr(result, "xxx", 0.0)` 部分を修正して push。

---

## 🔲 Phase 3：本番実験

**TODO-7: 全モデル × Q01–Q12 × 3回 実行**

```bash
# anthropic_grace_agent（claude-3-5-sonnet）
cd anthropic_grace_agent
python -c "from grace.benchmark import BenchmarkRunner; BenchmarkRunner().run_query_set(runs_per_query=3)"

# openai_grace_agent（gpt-4o-mini）
cd openai_grace_agent
python -c "from grace.benchmark import BenchmarkRunner; BenchmarkRunner().run_query_set(runs_per_query=3)"

# openai_grace_agent（gpt-4o に切替）
python -c "
from grace.benchmark import BenchmarkRunner
BenchmarkRunner(model_name='gpt-4o-2024-08-06').run_query_set(runs_per_query=3)
"

# gemini_grace_agent（gemini-2.0-flash）
cd gemini_grace_agent
python -c "from grace.benchmark import BenchmarkRunner; BenchmarkRunner().run_query_set(runs_per_query=3)"

# ollama_grace_agent（gemma4:e4b）
cd ollama_grace_agent
python -c "from grace.benchmark import BenchmarkRunner; BenchmarkRunner().run_query_set(runs_per_query=3)"

# ollama_grace_agent（llama3.2 に切替）
python -c "
from grace.benchmark import BenchmarkRunner
BenchmarkRunner(model_name='llama3.2').run_query_set(runs_per_query=3)
"
```

計 **Q12 × 6モデル × 3回 = 216セッション**、各リポジトリに `logs/benchmark_results.csv` が保存される。

---

## 🔲 Phase 4：分析・記事化

**TODO-8: CSV 統合**

```python
import pandas as pd, glob
dfs = [pd.read_csv(f) for f in glob.glob("*/logs/benchmark_results.csv")]
df_all = pd.concat(dfs, ignore_index=True)
df_all.to_csv("comparison_results_all.csv", index=False)
print(df_all.groupby("model")[["plan_time_sec","total_time_sec","overall_confidence"]].mean())
```

**TODO-9: LLM-as-Judge スコアリング**

5軸（accuracy / completeness / coherence / conciseness / groundedness）で各回答を 0–5 評価、
`accuracy_score` / `completeness_score` 列に追記。

**TODO-10: RAGAS 評価（オプション）**

```bash
pip install ragas
# faithfulness / answer_relevancy / context_precision / context_recall を計算
```

**TODO-11: Streamlit ダッシュボード**

`ui/pages/benchmark_page.py` を追加（spec Section 6-2 参照）。

**TODO-12: Qiita / Zenn 記事公開**

---

## 優先実施順

```
TODO-1（スキーマ確認）
  → TODO-2（temperature 確認）
  → TODO-3（インフラ確認）
  → TODO-4（Q01 予備実験）
  → TODO-5（Q09 予備実験）
  → TODO-6（エラー修正があれば）
  → TODO-7（本番 216 セッション）
  → TODO-8（CSV 統合）
  → TODO-9 以降（分析・記事化）
```

---

## 補足：実行環境について

| 作業 | ローカル | CI（GitHub Actions 等） |
|---|---|---|
| `pytest tests/test_agent_4operations.py` | ✅ | ✅（APIキー・Qdrant 不要）|
| Phase 2・3 のベンチマーク実行 | ✅ | ❌（Qdrant・Ollama が必要）|
| Phase 4 の CSV 分析・可視化 | ✅ | △（データがあれば可能）|

---

*最終更新: 2026-05-24*
