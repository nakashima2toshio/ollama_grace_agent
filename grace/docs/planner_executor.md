# GRACE Agent - 処理フロー仕様書

## 1. 全体アーキテクチャ概要

GRACE (Guided Reasoning with Adaptive Confidence Execution) は、**Plan → Execute → Evaluate → Intervene → Replan** のループで動作する自律型エージェントシステムです。

ユーザーの質問に対して、LLM が実行計画を生成し、各ステップを順次実行しながら信頼度を評価し、必要に応じて人間への確認やリプランを行います。

---

## 2. モジュール構成と実行順序

```
grace/
├── config.py        … [0] 設定管理（全モジュールが参照）
├── schemas.py       … [0] データモデル定義（全モジュールが参照）
├── planner.py       … [1] 計画生成（最初に実行）
├── tools.py         … [2] ツール定義（Executor が呼び出す道具箱）
├── executor.py      … [3] 計画実行（中核エンジン）
├── confidence.py    … [4] 信頼度計算（各ステップ実行後に評価）
├── intervention.py  … [5] HITL 介入（信頼度が低い場合に発動）
├── replan.py        … [6] 動的リプラン（失敗・低信頼度時に再計画）
└── __init__.py      … パッケージ公開 API
```

---

## 3. 処理フロー全体図

```
[User Query
    │
    ▼
┌──────────────────────────────────────────┐
│ [Phase 1] config.py - 設定ロード         　│
│  GraceConfig (YAML + 環境変数)           　│
└──────────────┬───────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│ [Phase 2] [planner.py] - 計画生成         │
│  (1) 複雑度推定 (LLM)                   　 │
│  (2) 利用可能コレクション取得            　　 │
│  (3) LLM で ExecutionPlan (JSON) 生成   　│
│  (4) 依存関係検証                       　 │
└──────────────┬───────────────────────────┘
               │ ExecutionPlan
               ▼
┌──────────────────────────────────────────┐
│ [Phase 3] [executor.py] - 計画実行ループ   │
│  for step in plan.steps:                 │
│    ├─ 依存関係チェック                      │
│    ├─ [tools.py] でツール実行              │
│    ├─ [confidence.py] で信頼度計算         │
│    ├─ RAG結果の意味的適合性判定 (LLM)        │
│    ├─ [動的 web_search] / [ask_user 挿入]  │
│    ├─ [intervention.py] で介入判定         │
│    └─ 失敗時: replan.py でリプラン          │
└──────────────┬───────────────────────────┘
               │ ExecutionResult
               ▼
           最終回答
```


## 4. 各モジュールの詳細

### 4.1 config.py - 設定管理

**役割**: 全モジュールが参照する統合設定を提供する。

**主なクラス / 関数**:


| クラス / 関数  | 説明                                                                                                                    |
| :------------- | :---------------------------------------------------------------------------------------------------------------------- |
| `GraceConfig`  | Pydantic ベースの統合設定モデル。LLM, Embedding, Qdrant, WebSearch, Confidence, Intervention, Replan 等のサブ設定を保持 |
| `ConfigLoader` | YAML ファイル → 環境変数オーバーライド → Pydantic 検証の3段階でロード                                                 |
| `get_config()` | シングルトンで設定を取得（全モジュールから利用）                                                                        |

**設定の読み込み優先順**: `config/grace_config.yml` → `GRACE_*` 環境変数でオーバーライド

**他モジュールとの関係**: すべてのモジュールが `get_config()` を通じて設定を取得する。

---

### 4.2 schemas.py - データモデル定義

**役割**: 計画・実行結果・検索結果のスキーマを定義する（全モジュール共通）。

**主なモデル**:


| モデル             | 説明                                                                                |
| :----------------- | :---------------------------------------------------------------------------------- |
| `PlanStep`         | 計画の1ステップ。`action`, `query`, `collection`, `depends_on`, `fallback` 等を持つ |
| `ExecutionPlan`    | 実行計画全体。`steps[]`, `complexity`, `requires_confirmation` 等                   |
| `StepResult`       | ステップ実行結果。`status`, `output`, `confidence`, `sources`                       |
| `ExecutionResult`  | 計画全体の実行結果。`final_answer`, `overall_confidence`, `replan_count`            |
| `SearchResultItem` | RAG/Web 共通の検索結果フォーマット                                                  |

**利用可能なアクション (`ActionType`)**:
`rag_search`, `web_search`, `reasoning`, `ask_user`, `code_execute`

---

### 4.3 planner.py - 計画生成（Phase 2）

**役割**: ユーザーの質問を受け取り、LLM で実行計画（`ExecutionPlan`）を生成する。

**処理フロー**:

create_plan(query)
│
├─ (1) _get_available_collections()
│       Qdrant から利用可能コレクション一覧を取得
│
├─ (2) estimate_complexity_with_llm(query)
│       LLM で複雑度 (0.0-1.0) を推定
│       失敗時は estimate_complexity() (キーワードベース) にフォールバック
│
├─ (3) LLM 呼び出し (Gemini API)
│       ・PLAN_GENERATION_PROMPT にコレクション情報・クエリを埋め込み
│       ・response_schema=ExecutionPlan で構造化出力
│       ・最大2回リトライ（空レスポンス/JSON不正時）
│
├─ (4) validate_plan_dependencies(plan)
│       依存関係の循環・後方依存をチェック
│
└─ (5) 失敗時: _create_fallback_plan(query)
rag_search → reasoning の2ステップ計画を静的に生成

```

**計画生成ルール（プロンプトで強制）**:
- `rag_search` の `query` はユーザーの質問文をそのまま使用（要約・キーワード化禁止）
- 計画は `rag_search → reasoning` の2ステップが基本
- `web_search` は計画に含めず、Executor が動的に実行する
- `rag_search` の `fallback` には `"web_search"` を指定

**出力**: `ExecutionPlan`（JSON 構造化出力）

**次のモジュールへの受け渡し**: `executor.py` の `execute_plan()` または `execute_plan_generator()` に渡される。

---

### 4.4 tools.py - ツール定義（Phase 3 で利用）

**役割**: Executor が呼び出すツール群を定義・管理する。

**ツール一覧**:

| ツール | クラス | 説明 |
|:---|:---|:---|
| `rag_search` | `RAGSearchTool` | Qdrant ベクトル DB 検索。複数コレクションを優先順に自動フォールバック。Dynamic Thresholding（Top1 が 0.98 以上なら他を除去）。 |
| `web_search` | `WebSearchTool` | Web 検索。バックエンド切替可能（SerpAPI / DuckDuckGo / Google CSE）。結果を RAG 互換フォーマットに変換。 |
| `reasoning` | `ReasoningTool` | 収集情報を統合して回答を生成。LLM（Gemini）で推論。先行ステップの結果をコンテキストとして受け取る。 |
| `ask_user` | `AskUserTool` | ユーザーへの追加情報要求。質問文・理由・緊急度を構造化して出力。 |

**ToolRegistry**: 設定の `tools.enabled` に基づき、使用可能なツールだけを登録する。

**他モジュールとの関係**: `executor.py` が `ToolRegistry.get(action)` でツールを取得し、`tool.execute(**kwargs)` で実行する。

---

### 4.5 executor.py - 計画実行（Phase 3 中核）

**役割**: `ExecutionPlan` を受け取り、各ステップを順次実行して `ExecutionResult` を返す。

**2つの実行モード**:

| メソッド | 用途 |
|:---|:---|
| `execute_plan(plan)` | ブロッキング実行（テスト・バッチ処理向け） |
| `execute_plan_generator(plan)` | ジェネレータ実行（UI リアルタイム表示向け） |

**ステップ実行フロー（`execute_plan_generator`）**:

```

for step in plan.steps:
│
├─ (1) 依存関係チェック (_check_dependencies)
│       depends_on の全ステップが成功済みか確認
│
├─ (2) ツール実行 (_execute_step)
│       ├─ ToolRegistry からツール取得
│       ├─ _prepare_tool_kwargs() で引数構築
│       │   - rag_search: query, collection
│       │   - web_search: query, num_results, language
│       │   - reasoning: query, context(先行ステップ出力), sources
│       │   - ask_user: question, reason, urgency
│       ├─ tool.execute(**kwargs)
│       └─ yield {type: "log", content: ...}  ← UI中間通知
│
├─ (3) 信頼度計算 (_llm_calculate_step_confidence)
│       confidence.py の各コンポーネントを使用（後述）
│
├─ (4) RAG 結果の意味的適合性判定 ★D案実装
│       ├─ rag_max_score >= rag_sufficient_score (0.7)?
│       │   ├─ YES → _evaluate_rag_relevance() で LLM 判定
│       │   │         "YES/NO" のみ回答させる軽量評価
│       │   │   ├─ YES → web_search スキップ (パターン1)
│       │   │   └─ NO  → web_search 動的実行 (パターン2)
│       │   └─ NO  → web_search 動的実行 (パターン2)
│       │
│       └─ web_search も失敗 → ask_user 動的実行 (パターン3)
│
├─ (5) 介入判定 (_handle_intervention_if_needed)
│       信頼度に基づく ActionDecision から
│       SILENT/NOTIFY → 自動続行
│       CONFIRM/ESCALATE → 一時停止・ユーザー確認
│
└─ (6) 失敗時リプラン
replan.py の ReplanOrchestrator に委譲

```

**動的ステップ挿入**:
- `_execute_dynamic_web_search()`: RAG 不足時に `step_id + 100` で web_search を挿入
- `_execute_dynamic_ask_user()`: RAG + Web 両方不足時に `step_id + 200` で ask_user を挿入

**フォールバック**: `_execute_fallback()` でステップの `fallback` アクションを試行（二重フォールバックは無し）

**出力**: `ExecutionResult`（`final_answer`, `overall_confidence`, `step_results[]`）

---

### 4.6 confidence.py - 信頼度計算（Phase 4 評価）

**役割**: 各ステップと計画全体の信頼度を多軸で計算する。

**コンポーネント**:

| クラス | 説明 |
|:---|:---|
| `ConfidenceCalculator` | 重み付き平均 + ペナルティによるハイブリッド信頼度計算。検索ステップと推論ステップで計算ロジックを分離。 |
| `LLMSelfEvaluator` | LLM にステップ出力の信頼度を自己評価させる (0.0-1.0 + 理由)。Gemini Structured Output で応答。 |
| `SourceAgreementCalculator` | 複数ソースの回答をEmbeddingし、コサイン類似度で一致度を計算。 |
| `QueryCoverageCalculator` | 最終回答がクエリの全要素をカバーしているか LLM で評価 (0.0-1.0)。 |
| `ConfidenceAggregator` | 複数ステップの信頼度を集計（mean / min / weighted）。 |

**信頼度の構成要素 (`ConfidenceFactors`)**:
- `search_avg_score`, `search_max_score` — 検索スコア
- `source_agreement` — ソース間一致度
- `llm_self_confidence` — LLM 自己評価
- `tool_success_rate` — ツール成功率
- `query_coverage` — クエリ網羅度

**介入レベル判定 (`ActionDecision`)**:

| レベル | 信頼度 | 動作 |
|:---|:---|:---|
| SILENT | >= 0.9 | バックグラウンド進行 |
| NOTIFY | >= 0.7 | ステータス表示 |
| CONFIRM | >= 0.4 | ユーザー確認を要求 |
| ESCALATE | < 0.4 | ユーザー入力を要求 |

**呼び出し元**: `executor.py` の `_llm_calculate_step_confidence()` および `_calculate_overall_confidence()`

---

### 4.7 intervention.py - HITL 介入（Phase 5）

**役割**: 信頼度が低い場合にユーザーへの確認・入力要求を管理する。

**主なクラス**:

| クラス | 説明 |
|:---|:---|
| `InterventionHandler` | ActionDecision に基づき、SILENT → NOTIFY → CONFIRM → ESCALATE を段階的に処理。コールバック (`on_notify`, `on_confirm`, `on_escalate`) 経由で UI と連携。 |
| `DynamicThresholdAdjuster` | ユーザーフィードバック（正解/不正解）の履歴に基づき、介入閾値を動的調整。偽陽性が多ければ閾値引き上げ、偽陰性が多ければ引き下げ。 |
| `ConfirmationFlow` | 計画の「確認→修正→実行」フローを管理。最大修正回数制限あり。 |

**InterventionAction（ユーザーの選択肢）**:
`PROCEED`(続行) / `MODIFY`(計画修正) / `CANCEL`(中止) / `INPUT`(追加入力) / `RETRY`(再試行) / `SKIP`(スキップ)

**呼び出し元**: `executor.py` の `_handle_intervention_if_needed()` が信頼度レベルに応じて `InterventionHandler.handle()` を呼び出す。

---

### 4.8 replan.py - 動的リプラン（Phase 6）

**役割**: ステップ失敗・低信頼度・ユーザーフィードバック時に計画を動的に修正する。

**リプラントリガー (`ReplanTrigger`)**:

| トリガー | 条件 |
|:---|:---|
| `STEP_FAILED` | ステップ実行失敗 |
| `LOW_CONFIDENCE` | 信頼度が閾値 (0.4) 未満 |
| `USER_FEEDBACK` | ユーザーからの修正要求 |
| `TIMEOUT` | タイムアウト |

**リプラン戦略 (`ReplanStrategy`)**:

| 戦略 | 説明 |
|:---|:---|
| `PARTIAL` | 失敗ステップ以降のみ再計画 |
| `FULL` | 全体を再計画 |
| `FALLBACK` | 代替アクションへ切替 |
| `SKIP` | 失敗ステップをスキップ |
| `ABORT` | 実行中断 |

**戦略選択ロジック**:
- fallback が定義されている → `FALLBACK`
- 序盤（進捗 <= 34%）の失敗 → `FULL`
- ユーザーが「最初から」と指示 → `FULL`
- それ以外 → `PARTIAL`

**ReplanOrchestrator**: Executor から呼び出され、`should_replan()` → `determine_strategy()` → `create_new_plan()` の一連の処理を統合する。

**呼び出し元**: `executor.py` の `execute_plan_generator()` 内でステップ失敗時に `replan_orchestrator.handle_step_failure()` を呼び出す。

---

## 5. モジュール間の依存関係

```

config.py ◄──── (全モジュールが参照)
schemas.py ◄──── (全モジュールが参照)

planner.py
├── uses: config.py, schemas.py
├── uses: Gemini API (計画生成)
└── uses: Qdrant (コレクション取得)

tools.py
├── uses: config.py
├── uses: Qdrant (RAG検索)
├── uses: Gemini API (reasoning)
└── uses: SerpAPI / DuckDuckGo (Web検索)

executor.py
├── uses: config.py, schemas.py
├── uses: tools.py (ToolRegistry)
├── uses: confidence.py (信頼度計算)
├── uses: intervention.py (介入処理)
├── uses: replan.py (リプラン)
└── uses: Gemini API (RAG意味的適合性判定)

confidence.py
├── uses: config.py
└── uses: Gemini API (LLM自己評価, Query Coverage)

intervention.py
├── uses: config.py, schemas.py
└── uses: confidence.py (InterventionLevel)

replan.py
├── uses: config.py, schemas.py
└── uses: planner.py (再計画生成)

```

---

## 6. 典型的な実行シーケンス

### 6.1 正常系（RAG 検索成功）

```

1. User → "金色夜叉の著者は誰ですか？"
2. Planner.create_plan()
   → 複雑度推定: 0.3
   → Plan: [rag_search(query=原文) → reasoning]
3. Executor: Step 1 - rag_search
   → Qdrant 検索 → score=0.92, 結果あり
   → _evaluate_rag_relevance() → "YES"
   → web_search スキップ
   → confidence = 0.85
4. Executor: Step 2 - reasoning
   → Step 1 の結果をコンテキストに回答生成
   → confidence = 0.88
5. _calculate_overall_confidence() → 0.87
6. ExecutionResult(final_answer="...", overall_confidence=0.87)

```

### 6.2 異常系（RAG 意味不適合 → Web 検索）

```

1. User → "日本の政治制度について教えてください"
2. Planner → Plan: [rag_search → reasoning]
3. Executor: Step 1 - rag_search
   → score=0.75 (>= 0.7 で閾値クリア)
   → _evaluate_rag_relevance() → "NO" (似た文構造だが主題不一致)
   → _execute_dynamic_web_search() → Web検索実行
   → web_search 成功
4. Executor: Step 2 - reasoning
   → RAG + Web の両方をコンテキストに回答生成
5. ExecutionResult

```

### 6.3 リプラン発生

```

1. Executor: Step 1 - rag_search → 失敗
2. ReplanOrchestrator.handle_step_failure()
   → should_replan: True (STEP_FAILED)
   → strategy: FULL (序盤失敗)
   → create_new_plan() → 新しい ExecutionPlan
3. Executor: 新計画で再実行

```

---

## 7. 不足情報・今後の確認事項

| # | 項目 | 詳細 |
|:---|:---|:---|
| 1 | **UI 層 (`ui/pages/`)** | `show_grace_chat_page` がどのように `Planner` → `Executor` を呼び出しているかのコード未提供。UI コールバック (`on_step_start`, `on_intervention_required` 等) の実装詳細が不明。 |
| 2 | **`services/` 層** | `agent_service.py` (Legacy ReActAgent), `qdrant_service.py`, `prompts.py` の詳細が未提供。特に `search_rag_knowledge_base_structured()` の実装。 |
| 3 | **`agent_tools.py`** | `RAGSearchTool` 内で `from agent_tools import search_rag_knowledge_base_structured` しているが、このモジュールの詳細が不明。 |
| 4 | **`regex_mecab.py`** | `KeywordExtractor` の実装詳細（Planner / RAGSearchTool で初期化されるが、現在はコメントアウトされている箇所が多い）。 |
| 5 | **`qdrant_client_wrapper.py`** | `search_collection`, `embed_query_unified` 等のラッパー関数の詳細。 |
| 6 | **`config/grace_config.yml`** | 実際の設定ファイル内容（デフォルト値と運用値の差分）。 |
| 7 | **`confidence.py` 280-689行** | `LLMSelfEvaluator` の `evaluate_with_factors()` 等、ファイル中間部の実装詳細（truncated 部分）。 |
| 8 | **`tools.py` 239-643行** | `WebSearchTool` の `execute()` メソッド本体、`ReasoningTool` と `AskUserTool` の全実装（truncated 部分）。 |
```
