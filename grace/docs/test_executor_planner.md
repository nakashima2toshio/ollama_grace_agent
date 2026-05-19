## test_executor_planner.md — Planner × Executor 連携テスト計画

**Version 1.0** | 作成日: 2026-02-13

---

## 目次

1. [概要](#1-概要)
2. [データフロー分析](#2-データフロー分析)
3. [テストレベル分類](#3-テストレベル分類)
4. [Phase A: Level 1 — planner.py 単体テスト（完了）](#4-phase-a-level-1--plannerpy-単体テスト完了)
5. [Phase B: Level 2 — Plan構造の品質テスト（schemas準拠）](#5-phase-b-level-2--plan構造の品質テストschemas準拠)
6. [Phase C: Level 3 — Executor連携テスト](#6-phase-c-level-3--executor連携テスト)
7. [モック戦略](#7-モック戦略)
8. [実装の優先順位](#8-実装の優先順位)
9. [TODOチェックリスト](#9-todoチェックリスト)
10. [付録: executor.py の Planner出力参照箇所](#10-付録-executorpy-の-planner出力参照箇所)

---

## 1. 概要

本ドキュメントは、GRACE Agent の `planner.py` を `executor.py` との連携観点からテストするための計画書である。

executor.py は planner.py が生成する `ExecutionPlan` を入力として受け取り、各 `PlanStep` を順次実行する。したがって planner.py のテストは「単体で正しく動くか」だけでなく、「executor.py が消費可能な Plan を生成するか」の観点が不可欠である。

### 対象ファイル

| ファイル | 役割 | LOC |
|---------|------|-----|
| `grace/planner.py` | 計画生成エージェント（テスト対象） | ~450 |
| `grace/executor.py` | 計画実行エージェント（連携先） | ~1,260 |
| `grace/schemas.py` | Pydanticモデル定義（データ契約） | ~280 |
| `grace/tools.py` | ツール定義（executor内部で使用） | ~620 |

---

## 2. データフロー分析

### Planner → Executor のデータフロー

```
Planner.create_plan(query)
    ↓ ExecutionPlan
Executor.execute_plan(plan) / execute_plan_generator(plan)
    ↓ plan.steps をループ
    ↓ 各 PlanStep の属性を参照
        ├── step.action       → ツール選択 (_execute_step)
        ├── step.depends_on   → 依存関係チェック (_check_dependencies)
        ├── step.query        → ツール引数 (_prepare_tool_kwargs)
        ├── step.collection   → RAG検索先 (_prepare_tool_kwargs)
        ├── step.fallback     → 失敗時代替 (_execute_fallback)
        └── step.description  → ログ、reasoning context
    ↓
    plan.plan_id            → ExecutionResult.plan_id
    plan.original_query     → ExecutionResult.original_query, reasoning context
    plan.requires_confirmation → (将来的な確認フロー)
```

### Executor が参照する ExecutionPlan の属性一覧

| 属性 | 参照箇所（executor.py） | 用途 |
|------|----------------------|------|
| `plan.plan_id` | `execute_plan_generator` L192, `_create_execution_result` L1105 | ログ出力、ExecutionResult生成 |
| `plan.original_query` | `_create_execution_result` L1107, `_calculate_overall_confidence` L1040 | 最終結果、LLM評価のクエリ |
| `plan.steps` | `execute_plan_generator` L209-214, `execute_plan` L364 | ステップのループ処理 |
| `plan.steps[].action` | `_execute_step` L482, `_prepare_tool_kwargs` L645-689 | ツール選択・引数準備 |
| `plan.steps[].depends_on` | `_check_dependencies` L458-465 | 依存関係の検証 |
| `plan.steps[].query` | `_prepare_tool_kwargs` L642 | ツール実行引数 |
| `plan.steps[].collection` | `_prepare_tool_kwargs` L646 | RAG検索対象コレクション |
| `plan.steps[].fallback` | `_execute_step` L540 | フォールバック処理 |
| `plan.steps[].description` | `_execute_step` L476, `_prepare_tool_kwargs` L642 | ログ、query代替 |
| `plan.steps[].step_id` | 多数（状態管理全般） | ステップ識別子 |

---

## 3. テストレベル分類

| レベル | 対象 | モック範囲 | 目的 | Phase |
|--------|------|-----------|------|-------|
| **Level 1** | planner.py 単体 | 外部依存を全モック | 各メソッドの入出力の正しさ | A |
| **Level 2** | planner → schemas 連携 | LLM/Qdrantをモック | 生成されたPlanがschema制約を満たすか | B |
| **Level 3** | planner → executor 連携 | LLM/Qdrant/Toolsをモック | executorが消費可能なPlanを生成するか | C |

---

## 4. Phase A: Level 1 — planner.py 単体テスト（完了）

> ファイル: `test_planner.py`（作成済み）

| # | テスト対象 | テスト数 | 状態 |
|---|-----------|---------|------|
| A-1 | `estimate_complexity` | 7 | ✅ 完了 |
| A-2 | `_create_fallback_plan` | 6 | ✅ 完了 |
| A-3 | `_create_plan_legacy` | 3 | ✅ 完了 |
| A-4 | `estimate_complexity_with_llm` | 7 | ✅ 完了 |
| A-5 | `create_plan` | 6 | ✅ 完了 |
| A-6 | `_get_available_collections` | 2 | ✅ 完了 |
| A-7 | `refine_plan` | 2 | ✅ 完了 |
| A-8 | `__init__` / `create_planner` | 5 | ✅ 完了 |
| | **合計** | **38** | |

---

## 5. Phase B: Level 2 — Plan構造の品質テスト（schemas準拠）

### 目的

Executor が正しく動作するために Plan が満たすべき**構造的制約**を検証する。
Planner のどのパス（正常系、フォールバック、Legacy）で生成された Plan であっても、これらの制約を満たす必要がある。

### テスト項目一覧

| # | テスト名 | 検証内容 | Executor参照箇所 | 重要度 |
|---|---------|---------|-----------------|--------|
| B-1 | 最終ステップがreasoningか | `plan.steps[-1].action == "reasoning"` ※Legacy計画は除く | `_create_execution_result` L1096-1102 | 高 |
| B-2 | step_idの連番・一意性 | step_idが1始まりで重複なし | `step_statuses` / `step_results` のDict key | 高 |
| B-3 | depends_onが前方参照のみ | 全depends_onのidがそのstep_idより小さい | `_check_dependencies` L458-465 | 高 |
| B-4 | depends_onの参照先が存在する | depends_on内のidが全てstep_idsに含まれる | `_check_dependencies` L461 | 高 |
| B-5 | actionが有効値のみ | 各stepのactionがExecutorのツールレジストリまたは特殊ハンドラで処理可能な値 | `_execute_step` L482-490 | 高 |
| B-6 | queryがrag_searchステップに設定済み | rag_searchステップに `query != None` | `_prepare_tool_kwargs` L642 | 中 |
| B-7 | plan_idが設定済み | `plan.plan_id is not None` | `_create_execution_result` L1105 | 中 |
| B-8 | original_queryが保持 | `plan.original_query == 入力クエリ` | `_create_execution_result` L1107 | 中 |
| B-9 | complexityが0.0-1.0の範囲 | Pydanticバリデーション範囲内 | ログ出力のみ | 低 |
| B-10 | フォールバック計画の構造 | LLM失敗時のフォールバック計画もB-1〜B-8を全て満たす | 全体 | 高 |

### テストの詳細設計

#### B-1: 最終ステップがreasoningか

**根拠**: `_create_execution_result` (L1096-1102) が最終回答を取得する際、`reversed(state.plan.steps)` でループし、`action in ["reasoning", "run_legacy_agent"]` のステップの出力を `final_answer` とする。最後のステップがこれらでない場合、`final_answer = None` となる。

```python
# executor.py L1096-1102
for step in reversed(state.plan.steps):
    if (step.action in ["reasoning", "run_legacy_agent"]) and step.step_id in state.step_results:
        result = state.step_results[step.step_id]
        if result.status == "success":
            final_answer = result.output
            break
```

| INPUT | 期待OUTPUT | 条件 |
|-------|-----------|------|
| `create_plan("単純な質問")` の正常系 | `plan.steps[-1].action == "reasoning"` | LLM応答をモック |
| `_create_fallback_plan("質問")` | `plan.steps[-1].action == "reasoning"` | モック不要 |
| `_create_plan_legacy("質問")` | `plan.steps[-1].action == "run_legacy_agent"` | モック不要（例外ケース） |

#### B-2: step_idの連番・一意性

**根拠**: `ExecutionState.__post_init__` が `step.step_id` をキーとして `step_statuses` Dictを初期化する。重複があると後のステップで上書きされる。

| INPUT | 期待OUTPUT | 条件 |
|-------|-----------|------|
| 任意のPlan | `len(set(ids)) == len(ids)` かつ `ids == sorted(ids)` | 全パスで検証 |

#### B-3 / B-4: depends_onの妥当性

**根拠**: `_check_dependencies` (L458-465) は `dep_id in state.step_results` でチェックする。ステップは昇順で実行されるため、後方参照や存在しない参照は依存未解決となりステップがスキップされる。

| INPUT | 期待OUTPUT | 条件 |
|-------|-----------|------|
| 任意のPlan | `validate_plan_dependencies(plan)` がエラー空 | `schemas.validate_plan_dependencies` を使用 |

#### B-5: actionが有効値のみ

**根拠**: `_execute_step` (L482-490) は `tool_registry.get(step.action)` でツールを取得し、取得できない場合は `run_legacy_agent` の特殊ハンドリングを試み、それも該当しなければ `ValueError` を発生させる。

```python
VALID_ACTIONS = {"rag_search", "reasoning", "ask_user", "run_legacy_agent"}
# web_search, code_execute はschema上存在するがツール未登録の可能性あり
```

| INPUT | 期待OUTPUT | 条件 |
|-------|-----------|------|
| 任意のPlan | 全stepの `action` が `VALID_ACTIONS` に含まれる | |

#### B-6: queryがrag_searchステップに設定済み

**根拠**: `_prepare_tool_kwargs` (L642) は `step.query or step.description` でクエリを構成する。`query` が None でも `description` にフォールバックするが、rag_search では明示的なクエリが望ましい。

| INPUT | 期待OUTPUT | 条件 |
|-------|-----------|------|
| 任意のPlan | rag_searchステップの `query is not None` | |

#### B-7 / B-8: plan_id, original_query

**根拠**: `_create_execution_result` がこれらの値を `ExecutionResult` に直接コピーする。

| INPUT | 期待OUTPUT | 条件 |
|-------|-----------|------|
| `create_plan("テスト質問")` | `plan.plan_id is not None`, `plan.original_query == "テスト質問"` | |

---

## 6. Phase C: Level 3 — Executor連携テスト

### 目的

Executor のメソッドに対して Planner の出力を渡し、正しく処理されるか検証する。

### テスト項目一覧

| # | テスト名 | 検証内容 | 重要度 |
|---|---------|---------|--------|
| C-1 | ExecutionState初期化 | `ExecutionState(plan=plan)` で全ステップがPENDING初期化される | 高 |
| C-2 | 依存関係チェック通過 | `_check_dependencies(step, state)` がPlannerの計画で正しく動く | 高 |
| C-3 | ツール引数準備（rag_search） | `_prepare_tool_kwargs` がrag_searchステップから正しいkwargsを生成 | 高 |
| C-4 | ツール引数準備（reasoning） | `_prepare_tool_kwargs` がreasoningステップで依存先出力をcontextに含める | 高 |
| C-5 | ツール引数準備（ask_user） | `_prepare_tool_kwargs` がask_userステップで正しいkwargsを生成 | 中 |
| C-6 | execute_plan完走（正常系） | Plannerの計画でexecute_planが最後まで完走しExecutionResultを返す | 高 |
| C-7 | execute_plan完走（フォールバック計画） | フォールバック計画でもexecute_planが完走する | 高 |
| C-8 | execute_plan完走（Legacy計画） | `_create_plan_legacy`の計画でもexecuteが適切にルーティングする | 中 |
| C-9 | 最終回答の取得 | ExecutionResultのfinal_answerが最後のreasoningステップの出力と一致 | 高 |
| C-10 | 全体ステータス判定 | 全ステップ成功→"success"、一部成功→"partial"、全失敗→"failed" | 中 |

### テストの詳細設計

#### C-1: ExecutionState初期化

```python
# 検証内容
plan = planner._create_fallback_plan("テスト")
state = ExecutionState(plan=plan)

# 期待
assert len(state.step_statuses) == len(plan.steps)
for step in plan.steps:
    assert state.step_statuses[step.step_id] == StepStatus.PENDING
assert state.current_step_id == 0
assert state.is_cancelled is False
```

#### C-2: 依存関係チェック通過

```python
# 検証内容
plan = planner._create_fallback_plan("テスト")
state = ExecutionState(plan=plan)

# Step 1（依存なし）→ True
assert executor._check_dependencies(plan.steps[0], state) is True

# Step 2（Step 1に依存、未完了）→ False
assert executor._check_dependencies(plan.steps[1], state) is False

# Step 1完了後 → Step 2もTrue
state.step_results[1] = StepResult(step_id=1, status="success", confidence=0.8)
assert executor._check_dependencies(plan.steps[1], state) is True
```

#### C-3: ツール引数準備（rag_search）

```python
# 検証内容
plan = planner._create_fallback_plan("東京タワーの高さは？")
state = ExecutionState(plan=plan)
step = plan.steps[0]  # rag_search

kwargs = executor._prepare_tool_kwargs(step, state)

# 期待
assert kwargs["query"] == "東京タワーの高さは？"
assert kwargs.get("collection") == "wikipedia_ja"  # フォールバック計画の場合
```

#### C-4: ツール引数準備（reasoning）

```python
# 検証内容
plan = planner._create_fallback_plan("テスト")
state = ExecutionState(plan=plan)

# Step 1の結果を設定
state.step_results[1] = StepResult(
    step_id=1,
    status="success",
    output="検索結果テキスト",
    confidence=0.8
)

step = plan.steps[1]  # reasoning (depends_on=[1])
kwargs = executor._prepare_tool_kwargs(step, state)

# 期待: contextに依存先の出力が含まれる
assert "context" in kwargs or "sources" in kwargs
```

#### C-6: execute_plan完走（正常系）

```python
# 検証内容
plan = planner._create_fallback_plan("テスト")

# ToolRegistryのモック: 全ツールがToolResultを返す
mock_tool = MagicMock()
mock_tool.execute.return_value = ToolResult(
    success=True,
    output="テスト結果",
    confidence_factors={"result_count": 1, "avg_score": 0.8, "max_score": 0.8}
)
mock_registry = MagicMock()
mock_registry.get.return_value = mock_tool

result = executor.execute_plan(plan)

# 期待
assert result.overall_status in ["success", "partial"]
assert result.plan_id == plan.plan_id
assert result.original_query == plan.original_query
```

#### C-9: 最終回答の取得

```python
# 検証内容
# reasoningステップの出力が final_answer になることを確認

plan = planner._create_fallback_plan("テスト")

# Step 1 (rag_search) → 検索結果
# Step 2 (reasoning) → "最終回答テキスト"
# ↑ この値が result.final_answer に入る

result = executor.execute_plan(plan)
assert result.final_answer == "最終回答テキスト"  # reasoningの出力
```

#### C-10: 全体ステータス判定

```python
# _create_execution_result のロジック (executor.py L1084-1093):
#   cancelled    → "cancelled"
#   全success    → "success"
#   一部success  → "partial"
#   全failed     → "failed"

# テストケース:
# (a) 全ステップ成功 → "success"
# (b) Step1成功、Step2失敗 → "partial"
# (c) 全ステップ失敗 → "failed"
# (d) キャンセル → "cancelled"
```

---

## 7. モック戦略

### Phase B のモック構成

```
Planner (モック済: genai, Qdrant, KeywordExtractor)
  └→ ExecutionPlan (実オブジェクト) ← テスト対象
       └→ schemas.validate_plan_dependencies (実コード)
```

| モック対象 | パッチパス | 理由 |
|-----------|----------|------|
| `genai.Client` | `grace.planner.genai.Client` | LLM API呼び出し回避 |
| `QdrantClient` | `grace.planner.QdrantClient` | DB接続回避 |
| `get_all_collections` | `grace.planner.get_all_collections` | DB接続回避 |
| `KeywordExtractor` | `grace.planner.KeywordExtractor` | MeCab依存回避 |

### Phase C のモック構成

```
Planner (モック済)
  └→ ExecutionPlan (実オブジェクト)
       └→ Executor (実コード) ← テスト対象
            ├── ToolRegistry.get("rag_search").execute() → モック ToolResult
            ├── ToolRegistry.get("reasoning").execute()  → モック ToolResult
            ├── ConfidenceCalculator → モック
            ├── LLMSelfEvaluator → モック
            ├── InterventionHandler → モック
            └── ReplanOrchestrator → None (無効化)
```

| モック対象 | パッチパス | 理由 |
|-----------|----------|------|
| `ToolRegistry` | コンストラクタ引数で注入 | ツール実行の制御 |
| `ConfidenceCalculator` 系 | `grace.executor.create_confidence_calculator` 等 | LLM呼び出し回避 |
| `InterventionHandler` | `grace.executor.create_intervention_handler` | UI介入回避 |
| `ReplanOrchestrator` | `enable_replan=False` | リプラン無効化 |
| `ReActAgent` | `grace.executor.LEGACY_AGENT_AVAILABLE = False` | Legacy Agent回避 |

---

## 8. 実装の優先順位

### 推奨順序

```
Step 1: Phase B（構造テスト）を先に実装
  → Plannerの出力品質を保証
  → Executor不要でテスト可能
  → 所要時間: 短

Step 2: Phase C-1〜C-5（Executor個別メソッド連携）
  → Executorの個々のメソッドとPlanの連携を確認
  → モック構成がシンプル
  → 所要時間: 中

Step 3: Phase C-6〜C-10（Executor end-to-end連携）
  → 全体フローの結合テスト
  → モック構成が複雑
  → 所要時間: 長
```

### テストファイル構成

```
tests/
├── test_planner.py                 # Phase A: 単体テスト（完了）
├── test_planner_plan_quality.py    # Phase B: Plan構造品質テスト
├── test_executor_planner.py        # Phase C: Executor連携テスト
└── conftest.py                     # 共通フィクスチャ
```

---

## 9. TODOチェックリスト

### Phase A: planner.py 単体テスト

- [x] A-1: `estimate_complexity` テスト（7件）
- [x] A-2: `_create_fallback_plan` テスト（6件）
- [x] A-3: `_create_plan_legacy` テスト（3件）
- [x] A-4: `estimate_complexity_with_llm` テスト（7件）
- [x] A-5: `create_plan` テスト（6件）
- [x] A-6: `_get_available_collections` テスト（2件）
- [x] A-7: `refine_plan` テスト（2件）
- [x] A-8: `__init__` / `create_planner` テスト（5件）

### Phase B: Plan構造品質テスト

- [ ] B-1: 最終ステップがreasoning（またはrun_legacy_agent）
- [ ] B-2: step_idの連番・一意性
- [ ] B-3: depends_onが前方参照のみ
- [ ] B-4: depends_onの参照先が存在する
- [ ] B-5: actionが有効値のみ
- [ ] B-6: queryがrag_searchステップに設定済み
- [ ] B-7: plan_idが設定済み
- [ ] B-8: original_queryが保持
- [ ] B-9: complexityが0.0-1.0の範囲
- [ ] B-10: フォールバック計画の構造（B-1〜B-8を全て満たす）

### Phase C: Executor連携テスト

- [ ] C-1: ExecutionState初期化
- [ ] C-2: 依存関係チェック通過
- [ ] C-3: ツール引数準備（rag_search）
- [ ] C-4: ツール引数準備（reasoning）
- [ ] C-5: ツール引数準備（ask_user）
- [ ] C-6: execute_plan完走（正常系）
- [ ] C-7: execute_plan完走（フォールバック計画）
- [ ] C-8: execute_plan完走（Legacy計画）
- [ ] C-9: 最終回答の取得
- [ ] C-10: 全体ステータス判定

---

## 10. 付録: executor.py の Planner出力参照箇所

### ExecutionState.__post_init__ (L78-82)

```python
def __post_init__(self):
    for step in self.plan.steps:
        self.step_statuses[step.step_id] = StepStatus.PENDING
```

→ `plan.steps` の各 `step.step_id` を参照。step_idの一意性が必須。

### _check_dependencies (L458-465)

```python
def _check_dependencies(self, step: PlanStep, state: ExecutionState) -> bool:
    for dep_id in step.depends_on:
        if dep_id not in state.step_results:
            return False
        if state.step_results[dep_id].status == "failed":
            return False
    return True
```

→ `step.depends_on` の各idが `state.step_results` に存在し、かつ成功していることを要求。

### _execute_step (L467-553)

```python
tool = self.tool_registry.get(step.action)
if tool is None and step.action == "run_legacy_agent":
    return self._execute_legacy_agent_step(step, state, start_time)
if tool is None:
    raise ValueError(f"Unknown action: {step.action}")
```

→ `step.action` がツールレジストリまたは特殊ハンドラで処理可能であること。

### _prepare_tool_kwargs (L635-691)

```python
kwargs = {"query": step.query or step.description}

if step.action == "rag_search":
    kwargs["collection"] = step.collection
elif step.action == "reasoning":
    # depends_onの結果をcontext/sourcesとして追加
elif step.action == "ask_user":
    kwargs.update({
        "question": step.query or step.description,
        "reason": f"ステップ {step.step_id}: {step.description}",
        "urgency": "blocking"
    })
```

→ actionごとに異なる属性を参照。rag_searchは `query` + `collection`、reasoningは `depends_on` 経由の結果、ask_userは `query` + `description`。

### _create_execution_result (L1081-1113)

```python
# 最終回答の取得
for step in reversed(state.plan.steps):
    if (step.action in ["reasoning", "run_legacy_agent"]) and step.step_id in state.step_results:
        result = state.step_results[step.step_id]
        if result.status == "success":
            final_answer = result.output
            break

return ExecutionResult(
    plan_id=state.plan.plan_id or create_plan_id(),
    original_query=state.plan.original_query,
    final_answer=final_answer,
    ...
)
```

→ `plan.plan_id`, `plan.original_query`, および最後のreasoning/legacy_agentステップの出力を参照。

---

## 変更履歴

| バージョン | 日付 | 変更内容 |
|-----------|------|---------|
| 1.0 | 2026-02-13 | 初版作成 |
