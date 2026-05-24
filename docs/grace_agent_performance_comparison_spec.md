# Agent性能比較 — 比較・調査仕様書

**バージョン**: 1.1  
**作成日**: 2026-05-24  
**更新日**: 2026-05-24（v1.0→v1.1: 各リポジトリ config.py 調査に基づきモデル名・Embedding情報を修正）  
**対象リポジトリ**: openai / gemini / ollama / anthropic `_grace_agent`

---

## 1. 目的

4つのLLMプロバイダー（OpenAI / Gemini / Ollama / Anthropic）上で動作する  
GRACE（Guided Reasoning with Adaptive Confidence Execution）エージェントの  
**性能・品質・コストを定量的に比較し、最適なプロバイダー選択の根拠を示す**。

---

## 2. 比較対象エージェント

| エージェント | プロバイダー | デフォルトLLMモデル | Embeddingモデル | Embedding次元 | 実行環境 |
|---|---|---|---|---|---|
| `openai_grace_agent` | OpenAI | `gpt-4o-mini` | `text-embedding-3-large` | 3072 | クラウド API |
| `gemini_grace_agent` | Google Gemini | `gemini-3-flash-preview` | `gemini-embedding-001` | 3072 | クラウド API |
| `ollama_grace_agent` | Ollama (ローカル) | `llama3.2` | `nomic-embed-text` | **768** | ローカル推論 |
| `anthropic_grace_agent` | Anthropic | `claude-sonnet-4-6` | `text-embedding-3-large` | 3072 | クラウド API |

> **⚠️ 注意 — Embedding次元の差異**  
> `ollama_grace_agent` のみ Embedding 次元が **768** であり、他3つ（3072）と異なる。  
> Qdrant コレクションを共有できないため、Ollama 専用コレクション（`cc_news_2per_768`等）を別途作成すること。

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

**介入レベル閾値（全エージェント共通）**

| レベル | 条件 | 動作 |
|---|---|---|
| SILENT | `confidence >= 0.9` | 自動続行 |
| NOTIFY | `0.7 <= confidence < 0.9` | ログ記録して続行 |
| CONFIRM | `0.4 <= confidence < 0.7` | ユーザー承認待ち |
| ESCALATE | `confidence < 0.4` | リプランまたは中止 |

### 3-3. コスト指標

| 指標 | 説明 | 単位 |
|---|---|---|
| `input_tokens` | 入力トークン数 | tokens |
| `output_tokens` | 出力トークン数 | tokens |
| `cost_usd` | 推定コスト | USD |
| コスト効率 | `overall_confidence / cost_usd` | - |

> Ollama はローカル実行のため `cost_usd = 0.0`（インフラコストは別途計算）

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
| RAG コレクション（openai/gemini/anthropic） | `cc_news_2per`（3072次元） |
| RAG コレクション（ollama） | `cc_news_2per_768`（768次元、別途作成必要） |
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

# ollama_grace_agent（ollama serve 起動済み + llama3.2/nomic-embed-text pull済みであること）
cd ollama_grace_agent
python -c "from grace.benchmark import BenchmarkRunner; BenchmarkRunner().run_query_set()"

# anthropic_grace_agent
cd anthropic_grace_agent
python -c "from grace.benchmark import BenchmarkRunner; BenchmarkRunner().run_query_set()"
```

### Step 2: CSV の収集

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

### Step 4: 集計・可視化

Streamlit ベンチマークページ（`ui/pages/benchmark_page.py`）の「プロバイダー比較」セクションを使用。

---

## 6. 期待される出力形式

### 6-2. サマリーテーブル（例）

| provider | model | avg_total_sec | avg_confidence | avg_cost_usd | success_rate | avg_rag_sources |
|---|---|---|---|---|---|---|
| openai | gpt-4o-mini | - | - | - | - | - |
| gemini | gemini-3-flash-preview | - | - | - | - | - |
| ollama | llama3.2 | - | - | 0.0 | - | - |
| anthropic | claude-sonnet-4-6 | - | - | - | - | - |

### 6-3. 考察項目

- **速度**: レイテンシが最も低いプロバイダー（Ollamaはネットワーク不要のため有利な可能性）
- **品質**: `overall_confidence` および RAGAS スコアが最も高いプロバイダー
- **コスト効率**: `confidence / cost_usd` 比率（Ollamaは分母が0のため別指標で評価）
- **安定性**: 試行間の標準偏差・`replan_count` の分布
- **ローカル推論**: Ollama（llama3.2）の速度・品質トレードオフ（Embedding次元差異の影響含む）

---

## 7. 前提条件・依存関係

| 項目 | 内容 |
|---|---|
| Qdrant | `http://localhost:6333` で起動済み |
| RAG コレクション (openai/gemini/anthropic) | `cc_news_2per`（3072次元）登録済み |
| RAG コレクション (ollama) | `cc_news_2per_768`（768次元）登録済み |
| API キー | `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `ANTHROPIC_API_KEY` が `.env` に設定済み |
| Ollama | `ollama serve` 起動済み、`llama3.2` および `nomic-embed-text` モデル pull 済み |
| Python | 3.10 以上、各リポジトリの依存パッケージインストール済み |

---

## 8. 単体テスト（4操作テスト）

各リポジトリに `tests/test_agent_4operations.py` が追加済み（API キー・Qdrant 不要）。

```bash
pytest tests/test_agent_4operations.py -v
```

| テストクラス | 対象 | テスト数 |
|---|---|---|
| `TestOperation1Planning` | 計画立案フェーズ | 10 |
| `TestOperation2Execution` | 実行フェーズ | 8 |
| `TestOperation3ConfidenceEvaluation` | 信頼度評価 | 9 |
| `TestOperation4InterventionReplan` | 介入/再計画 | 8 |
| `TestBenchmarkPerformanceEvaluation` | ベンチマーク統合 | 11 |

---

## 9. スケジュール（案）

| フェーズ | 内容 | 状態 |
|---|---|---|
| Phase A | バグ修正・ベンチマーク基盤整備（`grace/benchmark.py` + `tests/test_agent_4operations.py`） | **完了** |
| Phase B | 各エージェントのベンチマーク実行（Q01–Q12 × 3回） | 実施中 |
| Phase C | RAG 性能比較（RAGAS）| 次フェーズ |
| Phase D | 結果集計・Streamlit レポート作成 | Phase C 完了後 |

---

## 変更履歴

| バージョン | 日付 | 変更内容 |
|---|---|---|
| 1.0 | 2026-05-24 | 初版作成 |
| 1.1 | 2026-05-24 | 各リポジトリ `config.py` 調査に基づきモデル名修正（openai: gpt-4o-mini、gemini: gemini-3-flash-preview、ollama: llama3.2）、Ollama Embedding 次元差異（768）の注意追加、セクション8（単体テスト）追加 |
