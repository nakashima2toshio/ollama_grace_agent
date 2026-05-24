# Agent性能比較 — 比較・調査仕様書

**バージョン**: 1.0  
**作成日**: 2026-05-24  
**対象リポジトリ**: openai / gemini / ollama / anthropic `_grace_agent`

---

## 1. 目的

4つのLLMプロバイダー（OpenAI / Gemini / Ollama / Anthropic）上で動作する  
GRACE（Guided Reasoning with Adaptive Confidence Execution）エージェントの  
**性能・品質・コストを定量的に比較し、最適なプロバイダー選択の根拠を示す**。

---

## 2. 比較対象エージェント

| エージェント | プロバイダー | デフォルトモデル | 実行環境 |
|---|---|---|---|
| `openai_grace_agent` | OpenAI | `gpt-5.4-mini` | クラウド API |
| `gemini_grace_agent` | Google Gemini | `gemini-2.0-flash` | クラウド API |
| `ollama_grace_agent` | Ollama (ローカル) | `gemma4:e4b` | ローカル推論 |
| `anthropic_grace_agent` | Anthropic | `claude-sonnet-4-6` | クラウド API |

---

## 3. 評価軸と指標

### 3-1. パイプライン性能（BenchmarkRunner で自動計測）

| 指標 | 説明 | 単位 |
|---|---|---|
| `plan_time_sec` | Plan フェーズ所要時間 | 秒 |
| `execute_time_sec` | Execute フェーズ所要時間 | 秒 |
| `total_time_sec` | Plan + Execute 合計時間 | 秒 |
| `plan_steps` | 計画ステップ数 | 件 |
| `plan_complexity` | 計画複雑度スコア | 0.0–1.0 |
| `tool_calls` | 実行ツール呼出回数 | 件 |
| `rag_step_count` | RAG 検索ステップ数 | 件 |
| `sources_total` | 取得ソース数合計 | 件 |
| `replan_count` | リプラン発生回数 | 件 |
| `overall_status` | 最終ステータス | success / partial / failed |

### 3-2. 信頼度指標

| 指標 | 説明 | 単位 |
|---|---|---|
| `overall_confidence` | 全体信頼度スコア | 0.0–1.0 |
| `min_step_confidence` | ステップ信頼度の最小値 | 0.0–1.0 |
| `max_step_confidence` | ステップ信頼度の最大値 | 0.0–1.0 |
| `intervention_level` | 介入レベル | SILENT / NOTIFY / CONFIRM / ESCALATE |

### 3-3. コスト指標

| 指標 | 説明 | 単位 |
|---|---|---|
| `input_tokens` | 入力トークン数 | tokens |
| `output_tokens` | 出力トークン数 | tokens |
| `cost_usd` | 推定コスト | USD |
| コスト効率 | `overall_confidence / cost_usd` | - |

### 3-4. RAG 品質指標（RAGAS）

| 指標 | 説明 | 計算方法 |
|---|---|---|
| `faithfulness` | 回答がコンテキストに忠実か | RAGAS |
| `answer_relevancy` | 回答がクエリに関連しているか | RAGAS |
| `context_precision` | 取得コンテキストの精度 | RAGAS |
| `context_recall` | 取得コンテキストの再現率 | RAGAS |

### 3-5. 回答品質指標（LLM-Judge）

| 指標 | 説明 | スコア範囲 |
|---|---|---|
| `accuracy_score` | 回答の正確性 | 0.0–1.0 |
| `completeness_score` | 回答の完全性 | 0.0–1.0 |

---

## 4. ベンチマーク設計

### 4-1. テストクエリセット

`grace/benchmark.py` の `BENCHMARK_QUERIES`（12件）を共通クエリとして使用。

| クエリID | 難易度 | カテゴリ | 目的 |
|---|---|---|---|
| Q01–Q02 | Easy | 事実検索 | 基本的なRAG性能を計測 |
| Q03–Q04 | Medium | 推論・比較 | 複数ドキュメント統合能力を評価 |
| Q05–Q06 | Hard | 推論・比較 | 多段階推論・根拠提示能力を評価 |
| Q07–Q08 | Easy–Medium | 手順説明 | 時系列整理・カテゴリ分類を評価 |
| Q09–Q10 | Easy | 曖昧 | ESCALATE 誘発・クエリ明確化を評価 |
| Q11–Q12 | Hard | 推論・比較 | リプラン・多ソース統合を評価 |

### 4-2. 実行条件

| 項目 | 値 |
|---|---|
| 試行回数 | 各クエリ 3 回（`runs_per_query=3`） |
| RAG コレクション | `cc_news_2per`（全エージェント共通） |
| Qdrant URL | `http://localhost:6333` |
| 温度パラメータ | `temperature=0.7`（Plan/Execute）|
| Confidence 評価温度 | `temperature=0.0` |

### 4-3. 実行コマンド

```python
from grace.benchmark import BenchmarkRunner
runner = BenchmarkRunner()
sessions = runner.run_query_set(runs_per_query=3)
```

---

## 5. 比較手順

### Step 1: 各エージェントのベンチマーク実行

```bash
# openai_grace_agent
cd openai_grace_agent
python -c "from grace.benchmark import BenchmarkRunner; BenchmarkRunner().run_query_set()"

# gemini_grace_agent
cd gemini_grace_agent
python -c "from grace.benchmark import BenchmarkRunner; BenchmarkRunner().run_query_set()"

# ollama_grace_agent（Ollamaサーバー起動済みであること）
cd ollama_grace_agent
python -c "from grace.benchmark import BenchmarkRunner; BenchmarkRunner().run_query_set()"

# anthropic_grace_agent
cd anthropic_grace_agent
python -c "from grace.benchmark import BenchmarkRunner; BenchmarkRunner().run_query_set()"
```

### Step 2: CSV の収集

各リポジトリの `logs/benchmark_results.csv` を収集し、`provider` カラムで統合。

```python
import pandas as pd, glob
dfs = [pd.read_csv(f) for f in glob.glob("*/logs/benchmark_results.csv")]
df_all = pd.concat(dfs, ignore_index=True)
df_all.to_csv("comparison_results_all.csv", index=False)
```

### Step 3: RAGAS 評価（オプション）

```bash
pip install ragas
```

```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
# 各エージェントの回答・コンテキストで評価
```

### Step 4: 集計・可視化

Streamlit ベンチマークページ（`ui/pages/benchmark_page.py`）の「プロバイダー比較」セクションを使用。

---

## 6. 期待される出力形式

### 6-1. CSV（`comparison_results_all.csv`）

`benchmark_results.csv` の全カラム＋`provider` カラムによるクロス集計。

### 6-2. サマリーテーブル（例）

| provider | avg_total_sec | avg_confidence | avg_cost_usd | success_rate | avg_rag_sources |
|---|---|---|---|---|---|
| openai | - | - | - | - | - |
| gemini | - | - | - | - | - |
| ollama | - | - | - | - | - |
| anthropic | - | - | - | - | - |

### 6-3. 考察項目

- **速度**: レイテンシが最も低いプロバイダー
- **品質**: `overall_confidence` および RAGAS スコアが最も高いプロバイダー
- **コスト効率**: `confidence / cost_usd` 比率
- **安定性**: 試行間の標準偏差・`replan_count` の分布
- **ローカル推論**: Ollama の速度・品質トレードオフ

---

## 7. 前提条件・依存関係

| 項目 | 内容 |
|---|---|
| Qdrant | `http://localhost:6333` で起動済み、`cc_news_2per` コレクション登録済み |
| API キー | `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `ANTHROPIC_API_KEY` が `.env` に設定済み |
| Ollama | `ollama serve` 起動済み、`gemma4:e4b` または `llama3.2` モデル pull 済み |
| Python | 3.10 以上、各リポジトリの依存パッケージインストール済み |

---

## 8. スケジュール（案）

| フェーズ | 内容 | 目安 |
|---|---|---|
| Phase A | バグ修正・ベンチマーク基盤整備 | 完了 |
| Phase B | 各エージェントのベンチマーク実行 | 実施中 |
| Phase C | RAG 性能比較（RAGAS） | 次フェーズ |
| Phase D | 結果集計・レポート作成 | Phase C 完了後 |
