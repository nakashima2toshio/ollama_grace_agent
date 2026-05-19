# GRACE Agent 処理フロー詳細 — D案（LLM適合性判定）実装後

## 実行条件

- **質問**: 「日本はどのような多義的な概念として解説されていますか？」
- **実行日時**: 2026-02-20 08:46
- **LLMモデル**: gemini-3-flash-preview
- **実行時間**: 50.5秒
- **最終信頼度**: 0.59

---

## Phase 0: 初期化（08:46:09）

```
Config loaded from config/grace_config.yml
Planner initialized with model: gemini-3-flash-preview
ToolRegistry initialized with: ['rag_search', 'web_search', 'reasoning', 'ask_user']
Executor (GRACE Native) initialized: tools=[...], replan=enabled
```

Streamlit起動時にPlanner、ToolRegistry、ConfidenceCalculator、ReplanManager、Executorが順次初期化される。Qdrantへの接続確認とコレクション情報の取得も実施。

---

## Phase 1: ユーザー入力（08:46:25）

```
ユーザー入力: 「日本はどのような多義的な概念として解説されていますか？」
```

入力受付後、Qdrantのコレクション情報を再取得（5コレクション確認）。

---

## Phase 2: 計画策定 — Planner（08:46:25 〜 08:46:42）

### Step 2a: 複雑度推定（08:46:25 → 08:46:27, 2.0秒）

```
estimate_complexity_with_llm: 2.0秒
estimate_complexity_with_llm: empty response  ← gemini-3-flash-previewが空応答
```

LLMによる複雑度推定を試みるが空レスポンス。デフォルト値（0.5）にフォールバック。

### Step 2b: 計画生成（08:46:27 → 08:46:42, 14.7秒）

```
create_plan LLM (attempt 1/2): 14.7秒
Plan created: 2 steps, complexity=0.50
```

LLMが以下の2ステップ計画を生成：

| Step | Action | Query | Fallback |
|------|--------|-------|----------|
| 1 | rag_search | 日本はどのような多義的な概念として解説されていますか？ | web_search |
| 2 | reasoning | （Step 1に依存） | なし |

TODO-2の変更が効いており、**web_searchステップは計画に含まれていない**。

---

## Phase 3: 実行 — Executor Step 1: rag_search（08:46:42 〜 08:46:47）

### Step 3a: 5コレクション順次検索（08:46:42 → 08:46:44, 約2秒）

```
fineweb_edu_ja_5per → 20 hits → 閾値0.7以上なし
cc_news_1per        → 18 hits → 閾値0.7以上なし
cc_news_5per        →  5 hits → 閾値0.7以上なし
wikipedia_ja_1per   → 13 hits → コサイン類似度フィルタ: 13 → 1件 (Top: 0.7053)
wikipedia_ja_5per   → 検索されず（1件見つかった時点で終了）
```

唯一のヒット：

```
score: 0.7053
Q: 『日本大百科全書』において、言語はどのような多義的な概念として解説されていますか？
```

質問が「日本」の多義性なのに、結果は「言語」の多義性。文構造が類似しているためスコアが高い（**偽陽性**）。

### Step 3b: 信頼度計算（08:46:44 → 08:46:47, 約3秒）

```
ConfidenceFactors: search_max_score=0.70532393, search_result_count=1
evaluate_with_factors raw response (27 chars): Here is the JSON requested:
evaluate_with_factors: all parse attempts failed  ← JSONパース失敗
Fallback to search_max_score: 0.7053
Step 1 confidence: 0.71
```

`evaluate_with_factors`がJSON本文を返さず、ヘッダ文字列のみ返却。フォールバックでスコア値をそのまま信頼度として使用。

---

## Phase 4: RAG条件分岐 — D案のLLM適合性判定（08:46:47 → 08:46:48）

```
RAG score sufficient (0.7053 >= 0.7), checking semantic relevance with LLM
RAG relevance check: 'NO' -> False (1.1s)
RAG result not semantically relevant, need web_search
```

**ここがD案の核心部分。** スコアは閾値以上だが、`_evaluate_rag_relevance`がLLMに質問：

```
【ユーザーの質問】日本はどのような多義的な概念として...
【検索結果】言語は多義的であり...
→ YES / NO ?
```

LLMが**「NO」**と回答（1.1秒）。「日本」≠「言語」を意味的に検出。`need_web_search = True`に設定。

### 判定ロジック

```
rag_search 成功後:
├── max_score < 0.7  → need_web_search = True（即断）
└── max_score >= 0.7 → LLM適合性判定
                        ├── NO（不適合）→ need_web_search = True  ← 今回はここ
                        └── YES（適合） → need_web_search = False
```

---

## Phase 5: 動的web_search実行 — Step 101（08:46:48 → 08:47:02）

```
Dynamic web_search: step_id=101, query=日本はどのような多義的な概念として解説されていますか？
Executing step 101: web_search - [動的挿入] RAGスコア不足のためWeb検索を実行
SerpAPI search: query='日本はどのような多義的な概念として...', num=5, lang=ja
SerpAPI search returned 5 results
```

`_execute_dynamic_web_search`が仮想Step（step_id=101）を生成し実行。SerpAPIが5件返却：

| # | Score | Title | Source |
|---|-------|-------|--------|
| 1 | 1.0 | やさしい日本語の現在地 | clair.or.jp |
| 2 | 0.9 | 日本語は難しい？ | josai.ac.jp |
| 3 | 0.8 | 多様な人にわかりやすい日本語 | dlri.co.jp |
| 4 | 0.7 | 日本語にはなぜ多義語が多い？ | Yahoo!知恵袋 |
| 5 | 0.6 | 日本語の抽象語があやうい理由 | languagevillage.co.jp |

### Step 101の信頼度計算（08:46:57 → 08:47:02）

```
source_agreement: 0.6918（5件のembedding類似度から算出）
evaluate_with_factors: all parse attempts failed ← 再びJSONパース失敗
Fallback to search_max_score: 0.8000
Step 101 confidence: 0.80
```

---

## Phase 6: Executor Step 2: reasoning（08:47:02 → 08:47:28）

```
--- Reasoning Step ---
Available step_results: [1, 101]  ← TODO-4: 全成功結果を参照
```

**TODO-4の変更が有効。** `depends_on=[1]`のみの定義だが、`state.step_results`全体をイテレートするため、Step 1（RAG）とStep 101（Web）の両方を参照情報として使用。

### reasoning入力に渡された情報源（6件）

| # | 信頼度 | Source | 内容 |
|---|--------|--------|------|
| 情報源1 | 0.71 | RAG（wikipedia_ja_1per） | 「言語」の多義性 |
| 情報源2 | 1.00 | Web（clair.or.jp） | 多言語化とやさしい日本語 |
| 情報源3 | 0.90 | Web（josai.ac.jp） | 日本語の複雑性 |
| 情報源4 | 0.80 | Web（dlri.co.jp） | 情報のアクセシビリティ |
| 情報源5 | 0.70 | Web（Yahoo!知恵袋） | 多義語に関する誤解 |
| 情報源6 | 0.60 | Web（languagevillage.co.jp） | 大和言葉・漢語・和製漢語 |

### reasoning出力（25.4秒で生成）

4カテゴリに整理した回答を生成：

1. **「言語」という概念の多義性**（RAG結果）
   - 脳内システムとしての側面
   - 能力としての側面
   - 抽象的・全人類的な側面
   - 具体的・社会的な側面
2. **日本における社会的・政治的側面**（Web結果）
   - 多言語化と共生
   - 情報のアクセシビリティ
3. **日本語の文化的・構造的側面**（Web結果）
   - 言語的複雑性
   - 語彙の重層構造（大和言葉・漢語・和製漢語）
4. **多義語に関する誤解**（Web結果）

冒頭で「『日本』という概念そのものを多義的に直接定義する記述は見当たりませんでした」と正直に申告。

---

## Phase 7: 最終信頼度集約（08:47:28 → 08:47:33）

```
Step 2 confidence: 0.71（evaluate_with_factorsパース失敗→フォールバック）
LLM self-evaluation: 0.50（empty response）
Query coverage: 0.50（empty response）
Aggregated confidence: 0.59
```

3つの評価指標すべてがgemini-3-flash-previewの応答問題で正常計算できず、低めの集約スコアに。

---

## 全体タイムライン

```
[0.0s]  ユーザー入力
[0.0s]  ├── Phase 2: Planner
[2.0s]  │   ├── 複雑度推定（空応答→フォールバック）
[16.7s] │   └── 計画生成（14.7秒）
[16.7s] ├── Phase 3: Step 1 rag_search
[18.9s] │   ├── 5コレクション検索（2.1秒）
[21.9s] │   └── 信頼度計算（2.9秒）
[22.0s] ├── Phase 4: D案 LLM適合性判定 ← NEW
[23.1s] │   └── 'NO' → web_search必要（1.1秒）
[23.1s] ├── Phase 5: Step 101 動的web_search ← NEW
[31.9s] │   ├── SerpAPI検索（8.8秒）
[37.3s] │   └── 信頼度計算（5.4秒）
[37.3s] ├── Phase 6: Step 2 reasoning
[62.7s] │   └── 回答生成（25.4秒）
[67.8s] └── Phase 7: 最終信頼度集約（5.1秒）
          Total: 50.5秒
```

---

## 修正前との比較

```
修正前: rag_search → score 0.7053 >= 0.7 → 「十分」 → reasoning（情報源1件）→「情報なし」
修正後: rag_search → score 0.7053 >= 0.7 → LLM判定「NO」→ web_search → reasoning（情報源6件）→ 4カテゴリの回答
```

D案（`_evaluate_rag_relevance`）とTODO-4（全結果参照）が連携し、偽陽性を排除した上で豊富な情報源に基づく回答生成が実現。

### 数値比較

| 項目 | 修正前 | 修正後 |
|------|--------|--------|
| RAGスコア判定 | 0.7053 >= 0.7 → 十分 | 0.7053 >= 0.7 → LLM検証へ |
| LLM適合性判定 | なし | **NO（1.1秒）** |
| web_search | **スキップ** | **動的実行（Step 101）** |
| reasoning入力 | RAG結果のみ（1件） | RAG + Web（6件） |
| 最終回答 | 「該当する情報なし」 | 4カテゴリに整理した回答 |
| 実行時間 | 17.5秒 | 50.5秒 |

---

## 残存する問題点

### 1. Web検索結果の質問とのズレ

質問は「日本」の多義性だが、Web検索結果は「日本語」に関するものが大半。SerpAPIのクエリがそのまま質問文なので、検索エンジン側が「日本語」に寄せた結果を返している。reasoning自身もこれを認識し、冒頭で「『日本』という概念そのものを多義的に直接定義する記述は見当たりませんでした」と正直に回答している。これはWeb検索クエリの最適化の問題であり、D案の範囲外。

### 2. `evaluate_with_factors` のパース失敗が継続

```
evaluate_with_factors raw response (27 chars): Here is the JSON requested:
evaluate_with_factors: all parse attempts failed
```

全4回のLLM信頼度評価が全てパース失敗。`_evaluate_rag_relevance`は YES/NO の単純応答で問題なく動作したが、既存の`evaluate_with_factors`はJSON応答を期待しておりgemini-3-flash-previewが応答形式を守らない。これは別途修正が必要な既知問題。

### 3. 実行時間の増加（17.5秒 → 50.5秒）

内訳：LLM適合性判定 +1.1秒、web_search +8.8秒、reasoning（情報量増による生成時間増）+25秒。LLM判定のコスト（1.1秒）自体は許容範囲内で、増加の主因はweb_search実行とreasoning生成時間。

---

## 実装変更箇所まとめ

| TODO | ファイル | 状態 | 変更内容 |
|------|---------|------|---------|
| TODO-1 | config.py | ✅ | `rag_sufficient_score: float = 0.7` 追加 |
| TODO-2 | planner.py | ✅ | ルール6: web_search を計画に含めない指示 |
| TODO-3 | executor.py | ✅ | メインループに RAG スコア判定・条件分岐追加 |
| TODO-3a | executor.py | ✅ | `_execute_dynamic_web_search` 新規追加 |
| TODO-3b | executor.py | ✅ | `_execute_dynamic_ask_user` 新規追加 |
| TODO-4 | executor.py | ✅ | reasoning が全成功結果を参照するよう変更 |
| TODO-5 | executor.py | ✅ | `_evaluate_rag_relevance`（D案: LLM適合性判定）新規追加 |
