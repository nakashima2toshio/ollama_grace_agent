# Agent性能比較 — 比較・調査仕様書

**バージョン**: 1.3  
**作成日**: 2026-05-24  
**更新日**: 2026-05-24（v1.2→v1.3: 全体設計方針・6モデル比較・詳細計測・実施フェーズを再構成）  
**対象リポジトリ**: openai / gemini / ollama / anthropic `_grace_agent`

---

## 0. 全体設計方針

| 原則 | 内容 |
|---|---|
| 同一条件 | 同一クエリ・同一設定で **6モデル** を走らせ、GRACEの各フェーズを定量比較 |
| 再現性 | `temperature=0.0`、`random_seed=42`（対応モデルのみ）、モデルバージョン固定 |
| 試行回数 | 各クエリ × 各モデル = **3回実行**（中央値を採用） |

---

## 1. 目的

4リポジトリ（OpenAI / Gemini / Ollama / Anthropic）上で動作する  
GRACE（Guided Reasoning with Adaptive Confidence Execution）エージェントで  
計 **6モデル**（クラウド4 + ローカル2）の  
**性能・品質・コストを定量的に比較し、最適なプロバイダー選択の根拠を示す**。

---

## 2. 比較対象モデル一覧

| # | 区分 | プロバイダー | モデルID | バージョン固定 | リポジトリ |
|---|---|---|---|---|---|
| 1 | Cloud | OpenAI | `gpt-4o-mini` | `gpt-4o-mini-2024-07-18` | `openai_grace_agent` |
| 2 | Cloud | OpenAI | `gpt-4o` | `gpt-4o-2024-08-06` | `openai_grace_agent` |
| 3 | Cloud | Google | `gemini-2.0-flash` | 日付スナップショット | `gemini_grace_agent` |
| 4 | Cloud | Anthropic | `claude-3-5-sonnet` | `claude-3-5-sonnet-20241022` | `anthropic_grace_agent` |
| 5 | Local | Ollama | `llama3.2` | `3.2:3b` | `ollama_grace_agent` |
| 6 | Local | Ollama | `gemma4:e4b` | 固定 | `ollama_grace_agent` |

**共通パラメータ設定:**

```python
temperature = 0.0   # 再現性確保
max_tokens  = 4096  # config.py 準拠
seed        = 42    # 対応モデルのみ（OpenAI）
```

> **⚠️ 注意 — Embedding次元の差異**  
> `ollama_grace_agent` のみ Embedding 次元が **768**（`nomic-embed-text`）であり、他3つ（3072）と異なる。  
> Qdrant コレクションを共有できないため、Ollama 専用コレクション（`cc_news_2per_768`等）を別途作成すること。

---

## 3. 入力クエリ設計

### 3-1. 難易度レベル（3段階）

| Level | 特徴 | 例 |
|---|---|---|
| Easy | 単一ステップ、明確な答えがある | 「2024年の米国大統領選の結果は？」 |
| Medium | 複数ステップ、比較・推論が必要 | 「経済制裁がロシアのGDPに与えた影響を2022-2024で分析して」 |
| Hard | 多段階・曖昧・リプランを誘発しやすい | 「ウクライナ情勢に関連して、エネルギー価格と食料安全保障の連鎖影響を欧州視点でまとめて」 |

### 3-2. クエリカテゴリ（4種類）

| カテゴリ | 狙い | GRACE的効果 |
|---|---|---|
| 事実検索 | RAGヒット率を測る | Confidence高い → SILENT |
| 推論・比較 | 複数ステップ計画が出るか | Replan誘発を確認 |
| 手順説明 | 計画のステップ分解精度 | Plan品質の比較 |
| 曖昧・不明瞭 | ESCALATE判定を確認 | Intervention動作確認 |

### 3-3. 推奨クエリセット（12問）

| クエリID | 難易度 | カテゴリ | クエリ本文 |
|---|---|---|---|
| Q01 | Easy | 事実検索 | cc_newsコレクションにある最近のAI関連ニュースを3件教えてください |
| Q02 | Easy | 事実検索 | 2024年に最も報道されたスポーツイベントは何ですか？ |
| Q03 | Medium | 推論・比較 | 2023-2024年の気候変動に関するニュースから主要トレンドを比較してまとめてください |
| Q04 | Medium | 推論・比較 | テクノロジー企業の人員削減ニュースを複数比較して、業界全体の傾向を分析してください |
| Q05 | Hard | 推論・比較 | エネルギー問題とインフレの関係を、複数のニュース記事から根拠を挙げて説明してください |
| Q06 | Hard | 推論・比較 | cc_newsの記事から、地政学的リスクが特定の産業に与えた影響を2022年から追ってください |
| Q07 | Easy | 手順説明 | AIの倫理問題について、ニュースで報道された主な事例を時系列で教えてください |
| Q08 | Medium | 手順説明 | 医療AI分野のここ2年のニュースをカテゴリ別に整理してください |
| Q09 | Easy | 曖昧 | 最近の重要なニュースを教えて（意図的に曖昧 → ESCALATE期待） |
| Q10 | Easy | 曖昧 | あの件について詳しく教えて（文脈なし → ESCALATE期待） |
| Q11 | Hard | エラー回復 | 存在しないコレクション "xyz_test" から情報を取得してリプランしてください |
| Q12 | Hard | 複合 | 5つ以上の異なるニュースソースの情報を統合して、2024年の総括レポートを作成してください |

> **cc_news_2per を使う理由:** ニュース記事は事実が明確で評価しやすく、GRACEの全フェーズ（Plan/Execute/Confidence/Intervention/Replan）を適切に誘発できる。

---

## 4. 利用コレクション設定

```yaml
# openai / gemini / anthropic 共通
collection:       "cc_news_2per"
search_limit:     3
score_threshold:  0.50
distance_metric:  "Cosine"
vector_dims:      3072        # text-embedding-3-large / gemini-embedding-001

# ollama 専用（次元数が異なるため別コレクション必須）
collection_ollama: "cc_news_2per_768"
vector_dims_ollama: 768       # nomic-embed-text
```

---

## 5. 計測項目

### 5-1. GRACEフェーズ別計測項目

| フェーズ | # | 計測項目 |
|---|---|---|
| **Plan** | ① | 計画生成時間（秒） |
| | ② | 推定複雑度スコア（0.0–1.0） |
| | ③ | 計画ステップ数 |
| | ④ | `requires_confirmation`（True / False） |
| **Execute** | ⑤ | 全体実行時間（秒） |
| | ⑥ | ステップ別実行時間（秒 × ステップ数） |
| | ⑦ | RAG検索ヒット数・平均スコア |
| | ⑧ | ツール呼び出し回数 |
| **Confidence** | ⑨ | 最終信頼度スコア（0.0–1.0） |
| | ⑩ | `search_avg_score`、`search_max_score` |
| | ⑪ | `source_agreement`（複数ソース一致度） |
| | ⑫ | `llm_self_confidence`（LLM自己評価） |
| **Intervention** | ⑬ | InterventionLevel（SILENT / NOTIFY / CONFIRM / ESCALATE） |
| **Replan** | ⑭ | リプラン発生回数 |
| | ⑮ | リプラン理由（ログから抽出） |

**介入レベル閾値（全エージェント共通）**

| レベル | 条件 | 動作 |
|---|---|---|
| SILENT | `confidence >= 0.9` | 自動続行 |
| NOTIFY | `0.7 <= confidence < 0.9` | ログ記録して続行 |
| CONFIRM | `0.4 <= confidence < 0.7` | ユーザー承認待ち |
| ESCALATE | `confidence < 0.4` | リプランまたは中止 |

### 5-2. コスト・リソース計測

| 計測項目 | クラウド（OpenAI / Gemini / Anthropic） | ローカル（Ollama） |
|---|---|---|
| 応答時間 | TTFT + 全体時間 | TTFT + 全体時間 |
| トークン数 | `input_tokens` / `output_tokens` | N/A（推定） |
| コスト | API単価 × トークン数（¥換算） | 電力費換算 |
| リソース | N/A | CPU/GPU使用率、VRAM |

### 5-3. 回答品質評価（LLM-as-Judge）

```yaml
# 自動評価スコア（0–5点）
評価軸:
  accuracy:      回答の正確性
  completeness:  質問への網羅性
  coherence:     論理的一貫性
  conciseness:   簡潔さ
  groundedness:  RAGソースに基づいているか
```

### 5-4. RAG品質指標（RAGAS）

| 指標 | 説明 | 計算方法 |
|---|---|---|
| `faithfulness` | 回答がコンテキストに忠実か | RAGAS |
| `answer_relevancy` | 回答がクエリに関連しているか | RAGAS |
| `context_precision` | 取得コンテキストの精度 | RAGAS |
| `context_recall` | 取得コンテキストの再現率 | RAGAS |

---

## 6. ログ出力・画面表示仕様

### 6-1. BENCHMARK ログ出力形式（標準出力）

```
[BENCHMARK] ========================================
[BENCHMARK] Query ID: Q03 | Level: Medium | Category: 推論
[BENCHMARK] Model: gpt-4o-mini | Run: 1/3
[BENCHMARK] ----------------------------------------
[BENCHMARK] [Plan]
[BENCHMARK]   生成時間:       2.31 秒
[BENCHMARK]   複雑度スコア:   0.72
[BENCHMARK]   計画ステップ数: 4
[BENCHMARK]   requires_conf:  False
[BENCHMARK] [Execute]
[BENCHMARK]   全体実行時間:   18.4 秒
[BENCHMARK]   ツール呼び出し: 3 回
[BENCHMARK]   RAGヒット数:    3 / avg_score: 0.68
[BENCHMARK] [Confidence]
[BENCHMARK]   最終スコア:     0.74
[BENCHMARK]   search_max:     0.81 / source_agreement: 0.65
[BENCHMARK]   llm_self_eval:  0.70 / query_coverage:  0.80
[BENCHMARK] [Intervention]
[BENCHMARK]   Level: NOTIFY
[BENCHMARK] [Replan]
[BENCHMARK]   発生回数: 0
[BENCHMARK] [Cost]
[BENCHMARK]   input_tokens: 2,341 / output_tokens: 487
[BENCHMARK]   推定コスト: ¥0.18
[BENCHMARK] ========================================
```

### 6-2. Streamlit 比較ダッシュボード（オプション）

既存 `agent_rag.py` に `benchmark_page` を追加：

```
サイドバー: "benchmark" メニュー追加
  └─ クエリ選択（Q01–Q12）
  └─ モデル選択（複数選択可）
  └─ 実行ボタン

メイン画面:
  ├─ リアルタイム実行ログ（現行 grace_chat_page 流用）
  ├─ フェーズ別タイムライン表示（Plan / Execute / Confidence）
  └─ 比較テーブル（実行後に表示）
```

---

## 7. 出力・集計フォーマット

### 7-1. CSV ログ形式（自動保存: `logs/benchmark_results.csv`）

```
query_id, level, category, model, run,
plan_time, complexity, steps,
exec_time, tool_calls, rag_hits, avg_score,
confidence, intervention_level, replan_count,
input_tokens, output_tokens, cost_jpy,
accuracy_score, completeness_score
```

### 7-2. 比較サマリーテーブル（例）

| 指標 | GPT-4o | GPT-4o-mini | Gemini-2.0-flash | Claude-3.5-Sonnet | llama3.2 | gemma4:e4b |
|---|---|---|---|---|---|---|
| 計画生成時間（秒） | - | - | - | - | - | - |
| 全体実行時間（秒） | - | - | - | - | - | - |
| 平均信頼度 | - | - | - | - | - | - |
| ESCALATE率 | - | - | - | - | - | - |
| リプラン率 | - | - | - | - | - | - |
| 推定コスト/Q | - | - | - | - | ¥0 | ¥0 |

### 7-3. 考察項目

- **速度**: レイテンシが最も低いモデル（Ollamaはネットワーク不要のため有利な可能性）
- **品質**: `overall_confidence`・RAGAS・LLM-as-Judge スコアが最も高いモデル
- **コスト効率**: `confidence / cost_jpy` 比率（Ollamaは分母が0のため別指標で評価）
- **安定性**: 試行間の標準偏差・`replan_count` の分布
- **ローカル推論**: llama3.2 vs gemma4:e4b の速度・品質トレードオフ

---

## 8. 実施手順（フェーズ）

### Phase 1 — 環境統一

- 全モデルで同一 Qdrant コレクション使用確認
- `temperature=0.0` 設定確認
- BENCHMARK ログ出力コードの追加確認

### Phase 2 — 予備実験

- Q01、Q09（Easy + Ambiguous）を各モデルで 1 回実行
- ログ・コスト・実行時間を確認

### Phase 3 — 本番実験

```bash
# openai_grace_agent（gpt-4o-mini / gpt-4o 切替可能）
cd openai_grace_agent
python -c "from grace.benchmark import BenchmarkRunner; BenchmarkRunner().run_query_set(runs_per_query=3)"

# gemini_grace_agent
cd gemini_grace_agent
python -c "from grace.benchmark import BenchmarkRunner; BenchmarkRunner().run_query_set(runs_per_query=3)"

# ollama_grace_agent（ollama serve 起動済み + gemma4:e4b / llama3.2 / nomic-embed-text pull 済み）
cd ollama_grace_agent
python -c "from grace.benchmark import BenchmarkRunner; BenchmarkRunner().run_query_set(runs_per_query=3)"

# anthropic_grace_agent
cd anthropic_grace_agent
python -c "from grace.benchmark import BenchmarkRunner; BenchmarkRunner().run_query_set(runs_per_query=3)"
```

Q01–Q12 × 6モデル × 3回実行 → CSV に自動保存

### Phase 4 — 分析・記事化

```python
# CSV 統合
import pandas as pd, glob
dfs = [pd.read_csv(f) for f in glob.glob("*/logs/benchmark_results.csv")]
df_all = pd.concat(dfs, ignore_index=True)
df_all.to_csv("comparison_results_all.csv", index=False)
```

```bash
# RAGAS 評価（オプション）
pip install ragas
```

Streamlit ベンチマークページ（`ui/pages/benchmark_page.py`）で可視化後、Qiita/Zenn 記事として公開。

---

## 9. フェーズ別スケジュール

| フェーズ | 内容 | 状態 |
|---|---|---|
| Phase 1 | 環境統一（`grace/benchmark.py` + `tests/test_agent_4operations.py` 配備） | **完了** |
| Phase 2 | 予備実験（Q01, Q09 × 各モデル 1回） | 未着手 |
| Phase 3 | 本番実験（Q01–Q12 × 6モデル × 3回、CSV自動保存） | 未着手 |
| Phase 4 | 分析・Streamlit可視化・Qiita/Zenn 記事公開 | 未着手 |

---

## 10. 前提条件・依存関係

| 項目 | 内容 |
|---|---|
| Qdrant | `http://localhost:6333` で起動済み |
| RAG コレクション（openai / gemini / anthropic） | `cc_news_2per`（3072次元）登録済み |
| RAG コレクション（ollama） | `cc_news_2per_768`（768次元）登録済み |
| API キー | `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `ANTHROPIC_API_KEY` が `.env` に設定済み |
| Ollama | `ollama serve` 起動済み、`gemma4:e4b`・`llama3.2`・`nomic-embed-text` モデル pull 済み |
| Python | 3.10 以上、各リポジトリの依存パッケージインストール済み |

---

## 11. 単体テスト（4操作テスト）

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

## 変更履歴

| バージョン | 日付 | 変更内容 |
|---|---|---|
| 1.0 | 2026-05-24 | 初版作成 |
| 1.1 | 2026-05-24 | config.py 調査に基づきモデル名修正、Ollama Embedding 次元差異追加、Section 8（単体テスト）追加 |
| 1.2 | 2026-05-24 | config.py を spec v1.0 の意図通りモデル名に更新し同期（openai: gpt-5.4-mini、gemini: gemini-2.0-flash、ollama: gemma4:e4b） |
| 1.3 | 2026-05-24 | 全体再構成: Section 0（設計方針）追加、6モデル比較表に拡張（gpt-4o / claude-3-5-sonnet / llama3.2 追加）、temperature=0.0 再現性設定、GRACEフェーズ別詳細計測項目、LLM-as-Judge 5軸、BENCHMARKログ出力仕様、Streamlitダッシュボード仕様、4フェーズ実施手順、CSV/サマリーテーブル形式を追加 |
