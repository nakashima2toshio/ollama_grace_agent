# TODO: ユーザークエリ入力〜Embedding処理 改善チェックリスト

**作成日**: 2026-02-09
**対象**: grace_chat_page.py 関連パイプライン
**方針**: 影響範囲が小さく安全なものから着手し、段階的に進める

---

## 実施順の考え方

```
Phase 1 (STEP 1-3): 低リスク整理 — 既存動作に影響なし
Phase 2 (STEP 4-5): インフラ統一 — クライアント・インスタンス管理
Phase 3 (STEP 6-8): コア改善 — Embedding重複・ヘルスチェック最適化
Phase 4 (STEP 9-10): 設計改善 — アーキテクチャ整理・検索精度向上
```

---

## Phase 1: 低リスク整理（既存動作に影響なし）

---

### STEP 1: print() を logger に置換（#10）

> **リスク**: ⚪ 最小 | **対象**: `regex_mecab.py` | **依存**: なし

- [x] **1-1.** `regex_mecab.py` のバックアップを作成
- [x] **1-2.** L102-103 の `print()` を `logger.info()` / `logger.warning()` に変更
  ```python
  # Before
  print("✅ MeCabが利用可能です（複合名詞抽出モード）")
  print("⚠️ MeCabが利用できません（正規表現モード）")

  # After
  logger.info("✅ MeCabが利用可能です（複合名詞抽出モード）")
  logger.warning("⚠️ MeCabが利用できません（正規表現モード）")
  ```
- [x] **1-3.** ファイル先頭に `import logging` と `logger = logging.getLogger(__name__)` を追加（未追加の場合）
- [x] **1-4.** L136 の `print(f"⚠️ MeCab抽出エラー: {e}")` も `logger.warning()` に変更
- [x] **1-5.** L140 の `print("ℹ️ 英語主体の...")` も `logger.info()` に変更
- [ ] **1-6.** 動作確認: Streamlitで質問入力 → KeywordExtractor経由の処理が正常動作すること
- [ ] **1-7.** 完了コミット

---

### STEP 2: デッドコード `filter_results_by_keywords` の整理（#8）

> **リスク**: ⚪ 最小 | **対象**: `agent_tools.py` | **依存**: なし

- [x] **2-1.** `agent_tools.py` のバックアップを作成
- [x] **2-2.** プロジェクト全体で `filter_results_by_keywords` の呼び出し箇所を検索
  ```bash
  grep -rn "filter_results_by_keywords" *.py services/*.py
  ```
- [x] **2-3.** 呼び出しがない場合:
  - [x] 関数定義（L144-186）に `# TODO: 将来のキーワードフィルタ強化で活用予定` コメントを追加
  - [ ] **または** 関数を削除する（不要と判断した場合）
- [x] **2-4.** 呼び出しがある場合: その箇所を記録し、この STEP はスキップ → **呼び出しなし確認済み**
- [ ] **2-5.** 完了コミット

---

### STEP 3: 設計ドキュメントの次元数記載を修正（#9 の一部）

> **リスク**: ⚪ 最小 | **対象**: `grace_chat_input_query.md` | **依存**: なし

- [x] **3-1.** `grace_chat_input_query.md` 内の「768次元」記載箇所を検索 → **12箇所特定**
- [x] **3-2.** 実際のコード設定と照合:
  - `config.py` → `QdrantConfig.DEFAULT_VECTOR_SIZE = 3072`
  - `config.py` → `GeminiConfig.EMBEDDING_DIMS = 3072`
  - `qdrant_client_wrapper.py` → `PROVIDER_DEFAULTS["gemini"]["dims"] = 3072`
- [x] **3-3.** ドキュメント内の次元数を正しい値（3072）に修正 → **全12箇所修正完了**
- [x] **3-4.** OpenAI用コレクション（1536次元）が混在している旨を注意書きとして追記 → **4.6 embed_query セクションに追記**
- [ ] **3-5.** 完了コミット

---

## Phase 2: インフラ統一（クライアント・インスタンス管理）

---

### STEP 4: QdrantClient のシングルトン化（#4）

> **リスク**: 🟡 中 | **対象**: `qdrant_client_wrapper.py`, `agent_tools.py`, `grace_chat_page.py`, `agent_service.py` | **依存**: なし

- [x] **4-1.** 現在 `QdrantClient` を生成している全箇所をリストアップ
  ```bash
  grep -rn "QdrantClient(" *.py services/*.py
  ```
- [x] **4-2.** `qdrant_client_wrapper.py` にシングルトン取得関数を追加
  ```python
  _qdrant_client: Optional[QdrantClient] = None

  def get_qdrant_client() -> QdrantClient:
      global _qdrant_client
      if _qdrant_client is None:
          _qdrant_client = QdrantClient(
              url=QdrantConfig.URL,
              timeout=QdrantConfig.DEFAULT_TIMEOUT
          )
      return _qdrant_client
  ```
- [x] **4-3.** `__all__` に `"get_qdrant_client"` を追加
- [x] **4-4.** `agent_tools.py` L34-35 を変更
  ```python
  # Before
  client: QdrantClient = QdrantClient(url=qdrant_url)

  # After
  from qdrant_client_wrapper import get_qdrant_client
  client: QdrantClient = get_qdrant_client()
  ```
- [x] **4-5.** `grace_chat_page.py` L55 のコレクションデータ表示部分を変更
  ```python
  # Before
  client = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))

  # After
  from qdrant_client_wrapper import get_qdrant_client
  client = get_qdrant_client()
  ```
- [x] **4-5b.** `agent_chat_page.py` も同様に変更 → **追加対象として実施済み**
- [x] **4-6.** `agent_service.py` L442 の `get_available_collections_from_qdrant_helper()` を変更
  ```python
  # Before
  client = QdrantClient(url=qdrant_url)

  # After
  from qdrant_client_wrapper import get_qdrant_client
  client = get_qdrant_client()
  ```
- [ ] **4-7.** 動作確認: 全画面でQdrant接続が正常に動作すること
- [ ] **4-8.** 完了コミット

---

### STEP 5: EmbeddingClient のシングルトン化（#3）

> **リスク**: 🟡 中 | **対象**: `qdrant_client_wrapper.py` | **依存**: STEP 4 完了推奨

- [x] **5-1.** `qdrant_client_wrapper.py` にEmbeddingClientキャッシュを追加
  ```python
  _embedding_clients: Dict[str, EmbeddingClient] = {}

  def get_embedding_client(provider: str = None) -> EmbeddingClient:
      provider = provider or DEFAULT_EMBEDDING_PROVIDER
      if provider not in _embedding_clients:
          _embedding_clients[provider] = create_embedding_client(provider=provider)
      return _embedding_clients[provider]
  ```
- [x] **5-2.** `embed_query_unified()` を修正
  ```python
  # Before
  embedding_client = create_embedding_client(provider=provider)

  # After
  embedding_client = get_embedding_client(provider=provider)
  ```
- [x] **5-3.** `embed_texts_unified()` も同様に修正
- [x] **5-4.** Sparse用: `embed_sparse_query_unified()` の `get_sparse_embedding_client()` も同様にキャッシュ化を検討
  - [x] `get_cached_sparse_embedding_client()` を新規追加してキャッシュ化
  - [x] `embed_sparse_texts_unified()` と `embed_sparse_query_unified()` を修正
  - [ ] `helper_embedding_sparse.py` が内部でキャッシュしているか確認（**未提供のため未検証**）
- [ ] **5-5.** 動作確認: 検索実行 → Embeddingが正常に生成されること
- [ ] **5-6.** 完了コミット

---

## Phase 3: コア改善（Embedding重複・ヘルスチェック最適化）

---

### STEP 6: ヘルスチェック・コレクション存在確認のキャッシュ化（#2）

> **リスク**: 🔴 高（効果大） | **対象**: `agent_tools.py`, `qdrant_client_wrapper.py` | **依存**: STEP 4

- [x] **6-1.** `agent_tools.py` にコレクション設定キャッシュを追加
  ```python
  import time

  _collections_cache: Optional[List[str]] = None
  _collections_cache_time: float = 0.0
  _COLLECTIONS_CACHE_TTL: float = 60.0  # 60秒

  def get_existing_collections_cached() -> List[str]:
      global _collections_cache, _collections_cache_time
      now = time.time()
      if _collections_cache is None or (now - _collections_cache_time) > _COLLECTIONS_CACHE_TTL:
          _collections_cache = [c.name for c in client.get_collections().collections]
          _collections_cache_time = now
      return _collections_cache
  ```
- [x] **6-2.** `search_rag_knowledge_base_structured()` L389-396 を修正
  - [x] `search_rag_knowledge_base_structured()`: ヘルスチェック削除 + キャッシュ化
  - [x] `search_rag_knowledge_base_cached()` ステップ3: キャッシュ化
  - [x] `search_rag_knowledge_base()` フォールバック: キャッシュ化
  - [x] `list_rag_collections()`: キャッシュ化
- [x] **6-3.** `qdrant_client_wrapper.py` の `search_collection()` にベクトル設定キャッシュを追加
  ```python
  _vector_config_cache: Dict[str, dict] = {}

  def _get_vector_config(client, collection_name):
      if collection_name not in _vector_config_cache:
          collection_info = client.get_collection(collection_name)
          vectors_config = collection_info.config.params.vectors
          _vector_config_cache[collection_name] = {
              "is_named_vector": isinstance(vectors_config, dict),
              "dense_vector_name": "default" if isinstance(vectors_config, dict) else None
          }
      return _vector_config_cache[collection_name]
  ```
- [x] **6-4.** `search_collection()` 内の `client.get_collection()` をキャッシュ版に置換
- [x] **6-5.** `check_qdrant_health()` の呼び出しを削減:
  - [x] `search_rag_knowledge_base_structured()` からは削除
  - [x] `check_qdrant_health()` 関数自体は残存（他から参照可能）
- [ ] **6-6.** 動作確認: 並列検索時にQdrant管理APIの呼び出し回数が削減されていること（ログで確認）
- [ ] **6-7.** 完了コミット

---

### STEP 7: Embedding生成の重複呼び出し排除（#1）

> **リスク**: 🔴 高（効果最大・変更範囲広め） | **対象**: `agent_tools.py`, `agent_parallel_search.py` | **依存**: STEP 5, STEP 6

- [ ] **7-1.** 改善方針の確認:
  - `search_rag_knowledge_base_cached()` でEmbeddingを**1回だけ生成**
  - 各コレクション検索にはベクトルを直接渡す
- [x] **7-2.** `agent_tools.py` に**ベクトル受け渡し版**を実装（既存関数にオプションパラメータ追加方式）
  ```python
  def search_rag_knowledge_base_structured(
      query, collection_name=None, use_hybrid_search=True,
      precomputed_query_vector=None,      # Phase 3 STEP 7
      precomputed_sparse_vector=None       # Phase 3 STEP 7
  ):
      # precomputed が渡されていればそれを使用、なければ内部で生成
  ```
- [x] **7-3.** `search_rag_knowledge_base_cached()` を修正:
  - Embeddingを関数冒頭で1回だけ生成
  - 全3パス（ユーザー指定/キャッシュヒット/並列検索）に事前計算ベクトルを渡す
- [x] **7-4.** キャッシュヒット時（ステップ2）も同様にベクトル事前生成に対応
- [x] **7-5.** ユーザー指定コレクション時（ステップ1）も同様に対応
  - `search_rag_knowledge_base()` 経由 → `search_rag_knowledge_base_structured()` 直接呼び出しに変更
- [ ] **7-6.** 動作確認（重要）:
  - [ ] 並列検索時のログで `embed_query` の呼び出しが1回のみであること
  - [ ] 検索結果が改善前と同等であること（スコア・件数を比較）
  - [ ] Hybrid検索ON/OFF 両方で正常動作すること
- [x] **7-7.** 旧パス（`search_rag_knowledge_base_structured` 単体呼び出し）が壊れていないか確認
  - precomputed パラメータはOptional（デフォルトNone）なので後方互換
- [ ] **7-8.** 完了コミット

---

### STEP 8: Sparse フォールバックの一元化（#6）

> **リスク**: 🟡 中 | **対象**: `agent_tools.py`, `qdrant_client_wrapper.py` | **依存**: STEP 7

- [x] **8-1.** フォールバック責務を `search_collection()` に集約する方針を確認:
  - `qdrant_client_wrapper.py` の `search_collection()` が唯一のフォールバック処理を持つ
  - `agent_tools.py` 側の try-except は削除する
- [x] **8-2.** `agent_tools.py` `search_rag_knowledge_base_structured()` L418-443 のスパースエラー二重リトライを削除
  ```python
  # Before: try-except で sparse エラーをキャッチして再試行
  # After: search_collection() に任せる（search_collection 内に既にフォールバックがある）
  candidates = search_collection(
      client=client,
      collection_name=collection_name,
      query_vector=query_vector,
      sparse_vector=sparse_vector,
      limit=20
  )
  ```
- [x] **8-3.** `qdrant_client_wrapper.py` の `search_collection()` 内のフォールバックログを整理:
  - 【Stage 1】Hybrid Search 試行
  - 【Stage 1→2】Sparse未設定時 Dense切替
  - 【Stage 2】Dense のみ検索
  - 【Stage 3】最終フォールバック（最シンプル形式）
- [ ] **8-4.** 動作確認:
  - [ ] Sparse未対応コレクションに対して検索 → Dense フォールバックが正常動作
  - [ ] Sparse対応コレクションに対して検索 → Hybrid検索が正常動作
- [ ] **8-5.** 完了コミット

---

## Phase 4: 設計改善（アーキテクチャ整理・検索精度向上）

---

### STEP 9: 検索エントリポイントの整理（#7）

> **リスク**: 🟡 中 | **対象**: `agent_tools.py`, `agent_service.py` | **依存**: STEP 7, STEP 8

- [x] **9-1.** 現在の3つのエントリポイントの使用箇所を調査
  - `search_rag_knowledge_base`: TOOLS_MAP登録 + Gemini tools API定義用。実行時は agent_service が `search_rag_knowledge_base_cached` にインターセプト
  - `search_rag_knowledge_base_structured`: 内部検索エンジン（5箇所から呼び出し）
  - `search_rag_knowledge_base_cached`: メインエントリポイント（agent_service L310 から呼び出し）
- [x] **9-2.** 整理方針を決定:
  - `search_rag_knowledge_base_cached()` → **メインエントリポイント**（維持）
  - `search_rag_knowledge_base_structured()` → **内部関数**（維持、将来的にリネーム検討）
  - `search_rag_knowledge_base()` → **薄いラッパー**（フォールバック削除済み）
- [x] **9-3.** `search_rag_knowledge_base()` の独自フォールバックロジック（86行→23行に簡素化）を削除
  - `search_rag_knowledge_base_cached()` が全コレクション並列検索でカバーしているため
- [x] **9-4.** フォーマット処理の統一:
  - `search_rag_knowledge_base()` 内のフォーマット処理を `_format_results()` に統一
- [x] **9-5.** `TOOLS_MAP` の確認: 関数名・シグネチャ維持で影響なし
- [ ] **9-6.** 動作確認:
  - [ ] `search_rag_knowledge_base_cached` 経由の通常検索が正常
  - [ ] Legacy 呼び出しパスが壊れていないこと
- [ ] **9-7.** 完了コミット

---

### STEP 10: キーワード抽出と検索クエリの連携強化（#5）

> **リスク**: 🟡 中 | **対象**: `agent_service.py` | **依存**: STEP 9

- [x] **10-1.** 現状の問題を再確認:
  - KeywordExtractor で抽出 → LLMへヒント → LLMが独自にクエリ生成
  - 抽出キーワードが検索クエリに含まれる保証なし
- [x] **10-2.** 改善方針を選択:
  - [ ] **案A**: LLM生成クエリにキーワードを強制付加 → リスク大（クエリがノイジー）
  - [ ] **案B**: 検索結果のフィルタリングにキーワードを活用 → recall低下リスク
  - [x] **案C**: 現状維持＋プロンプト改善（採用）
- [x] **10-3.** 案Cで実装: 「固有名詞・専門用語は原文のまま含める」指示を追加
- [ ] **10-4.** 効果測定: 同一クエリで改善前/後の検索結果を比較
- [ ] **10-5.** 完了コミット

---

### STEP 11: Embedding次元数の不整合対応（#9 の本体）

> **リスク**: ⚪ 低（将来的なバグ防止） | **対象**: `qdrant_client_wrapper.py`, `agent_tools.py` | **依存**: STEP 7

- [x] **11-1.** 現在登録されている全コレクションの次元数を確認
  - `COLLECTION_EMBEDDINGS` (OpenAI 1536次元): 定義のみ、検索ロジックで未参照
  - `COLLECTION_EMBEDDINGS_GEMINI` (3072次元): 定義のみ、検索ロジックで未参照
  - 現在の検索は `DEFAULT_EMBEDDING_PROVIDER=gemini` (3072次元) を使用
- [x] **11-2.** OpenAI用コレクション（1536次元）が実際に使用されているか確認
  - `COLLECTION_EMBEDDINGS` はプロジェクト内で定義・エクスポートのみ。検索パスで参照なし
- [ ] ~~**11-3.** 使用されている場合: プロバイダー判定ロジックを実装~~ → 不要
- [x] **11-4.** 使用されていない場合: `COLLECTION_EMBEDDINGS` の旧定義にdeprecatedコメントを追加
- [ ] **11-5.** 完了コミット

---

## 進捗サマリ

| Phase | STEP | 項目 | 優先度 | 状態 |
|-------|------|------|--------|------|
| 1 | 1 | print() → logger 置換 | ⚪ | ✅ コード修正済み（動作確認・コミット待ち） |
| 1 | 2 | デッドコード整理 | ⚪ | ✅ コード修正済み（コミット待ち） |
| 1 | 3 | ドキュメント次元数修正 | ⚪ | ✅ 修正済み（コミット待ち） |
| 2 | 4 | QdrantClient シングルトン化 | 🟡 | ✅ コード修正済み（動作確認・コミット待ち） |
| 2 | 5 | EmbeddingClient シングルトン化 | 🟡 | ✅ コード修正済み（動作確認・コミット待ち） |
| 3 | 6 | ヘルスチェック・存在確認キャッシュ | 🔴 | ✅ コード修正済み（動作確認・コミット待ち） |
| 3 | 7 | Embedding重複排除 | 🔴 | ✅ コード修正済み（動作確認・コミット待ち） |
| 3 | 8 | Sparse フォールバック一元化 | 🟡 | ✅ コード修正済み（動作確認・コミット待ち） |
| 4 | 9 | 検索エントリポイント整理 | 🟡 | ✅ コード修正済み（動作確認・コミット待ち） |
| 4 | 10 | キーワード抽出連携強化 | 🟡 | ✅ 案C採用・プロンプト微修正済み（動作確認・コミット待ち） |
| 4 | 11 | Embedding次元数不整合対応 | ⚪ | ✅ DEPRECATEDコメント追加済み（コミット待ち） |

---

## 注意事項

- **各STEPは必ず動作確認してからコミット**すること
- **Phase 3（STEP 6-7）が最も効果が大きい**が、Phase 1-2を先に済ませることで安全にコードベースを整理してから取り組める
- STEP 7（Embedding重複排除）は変更範囲が最も広いため、**テスト用クエリを事前に3-5個用意**し、改善前後でスコア・件数を比較すること
- 各STEPでバックアップを取ること（git commit で十分）

---
---
## ユーザークエリ入力〜Embedding処理: 改善点・問題点分析

**Version 1.0** | 分析日: 2026-02-09

---

## 分析対象ファイル

| ファイル | 役割 |
|---------|------|
| `grace_chat_page.py` | UI層（チャット入力・表示） |
| `agent_service.py` | ReActAgent（LLM制御・ツール呼び出し） |
| `agent_tools.py` | 検索エントリポイント（キャッシュ・並列・Rerank） |
| `qdrant_client_wrapper.py` | Embedding生成・Qdrant検索実行 |
| `agent_parallel_search.py` | 並列検索エンジン |
| `regex_mecab.py` | キーワード抽出 |
| `config.py` | 設定・定数 |

---

## 1. Embedding生成の重複呼び出し（🔴 重大）

### 問題

並列検索時に、**同一クエリに対してEmbedding APIが最大N回（コレクション数分）呼び出される**。

**根拠コード:**

```
agent_tools.py: search_rag_knowledge_base_cached()
  → parallel_search_engine.search_all_collections(query, all_collections, search_func_with_hybrid)
    → 各コレクションごとに search_rag_knowledge_base_structured(query, col) を並列実行
      → embed_query(query)            ← コレクションごとに毎回呼ばれる
      → embed_sparse_query_unified(query) ← コレクションごとに毎回呼ばれる
```

`search_rag_knowledge_base_structured()` (agent_tools.py L398) で `embed_query(query)` を呼んでおり、`ParallelSearchEngine._search_single_collection()` はコレクション単位で `search_func` を呼ぶため、4コレクションあれば Dense Embedding が4回、Sparse Embedding も4回生成される。

### 改善案

Embeddingを**事前に1回だけ生成**し、各コレクション検索にはベクトルのみを渡す。

```python
# 改善案: search_rag_knowledge_base_cached() 内
query_vector = embed_query(query)                          # 1回だけ
sparse_vector = embed_sparse_query_unified(query) if use_hybrid_search else None  # 1回だけ

# 各コレクションにはベクトルを渡す
def search_func(q, col):
    return search_collection_with_vectors(client, col, query_vector, sparse_vector, limit=20)
```

### 影響

- **API コスト削減**: Gemini Embedding API の呼び出し回数が N → 1 に
- **レイテンシ改善**: Embedding生成（約100-300ms）× N回 が1回に
- **レート制限リスク低減**: API呼び出し集中による429エラーの回避

---

## 2. Qdrant ヘルスチェック・コレクション存在確認の過剰呼び出し（🔴 重大）

### 問題

`search_rag_knowledge_base_structured()` が呼ばれるたびに、以下の処理が**毎回**実行される:

```python
# agent_tools.py L389-396
if not check_qdrant_health():          # ← client.get_collections() を実行
    raise QdrantConnectionError(...)

existing_collections = [c.name for c in client.get_collections().collections]  # ← 2回目
if collection_name not in existing_collections:
    raise CollectionNotFoundError(...)
```

加えて `search_collection()` (qdrant_client_wrapper.py L1016) 内でも:

```python
collection_info = client.get_collection(collection_name)  # ← 3回目（ベクトル設定確認用）
```

並列4コレクション検索時、Qdrant への `get_collections()` / `get_collection()` が **少なくとも12回**発生する。

### 改善案

- ヘルスチェックは**起動時またはセッション開始時に1回**実行し、結果をキャッシュ
- コレクション存在確認は `search_rag_knowledge_base_cached()` レベルで1回行い、子関数には verified フラグを渡す
- `search_collection()` 内のベクトル設定は**初回のみ取得してキャッシュ**する（コレクションのスキーマは起動中に変わらない）

```python
# 例: コレクション設定キャッシュ
_collection_config_cache: Dict[str, dict] = {}

def get_collection_vector_config(client, collection_name):
    if collection_name not in _collection_config_cache:
        info = client.get_collection(collection_name)
        _collection_config_cache[collection_name] = {
            "is_named_vector": isinstance(info.config.params.vectors, dict),
            "dense_vector_name": "default" if isinstance(info.config.params.vectors, dict) else None
        }
    return _collection_config_cache[collection_name]
```

---

## 3. EmbeddingClient の毎回インスタンス化（🟡 中程度）

### 問題

`embed_query_unified()` (qdrant_client_wrapper.py L596-599) が呼ばれるたびに:

```python
def embed_query_unified(text, provider=None):
    provider = provider or DEFAULT_EMBEDDING_PROVIDER
    embedding_client = create_embedding_client(provider=provider)  # ← 毎回新規作成
    return embedding_client.embed_text(text, task_type="retrieval_query")
```

`create_embedding_client()` の実装は `helper_embedding.py`（未提供）にあるが、毎回クライアントを生成するのはオーバーヘッド。特にモデルのロードや接続初期化が含まれる場合は大きい。

### 改善案

モジュールレベルでシングルトンとして保持する:

```python
_embedding_clients: Dict[str, EmbeddingClient] = {}

def get_embedding_client(provider: str = None) -> EmbeddingClient:
    provider = provider or DEFAULT_EMBEDDING_PROVIDER
    if provider not in _embedding_clients:
        _embedding_clients[provider] = create_embedding_client(provider=provider)
    return _embedding_clients[provider]
```

※ `embed_sparse_query_unified()` の `get_sparse_embedding_client()` も同様。

---

## 4. QdrantClient のグローバルインスタンス管理（🟡 中程度）

### 問題

`QdrantClient` が複数箇所で**個別に生成**されている:

| 場所 | コード |
|------|--------|
| `agent_tools.py` L35 | `client = QdrantClient(url=qdrant_url)` （モジュールレベル） |
| `grace_chat_page.py` L55 | `client = QdrantClient(url=os.getenv("QDRANT_URL", ...))` |
| `agent_service.py` L442 | `client = QdrantClient(url=qdrant_url)` (`get_available_collections_from_qdrant_helper`) |

各インスタンスは別の接続プールを持ち、リソースが無駄になる。また設定の不一致リスクもある（`os.getenv` vs `QdrantConfig.URL`）。

### 改善案

`qdrant_client_wrapper.py` にファクトリ関数を用意し、シングルトンで管理:

```python
_qdrant_client: Optional[QdrantClient] = None

def get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=QdrantConfig.URL, timeout=QdrantConfig.DEFAULT_TIMEOUT)
    return _qdrant_client
```

---

## 5. キーワード抽出とLLMクエリ生成の二重処理（🟡 中程度）

### 問題

`execute_turn()` で以下の流れになっている:

1. `KeywordExtractor.extract(user_input)` → キーワード抽出
2. 抽出キーワードをプロンプトに追加: `「重要キーワード: X, Y, Z」`
3. LLM(Gemini)が `Thought:` で思考し、`Action: search_rag_knowledge_base(query="...")` を生成
4. **LLMが生成した `query` で検索実行**（キーワードが含まれる保証なし）

つまり、KeywordExtractor で抽出したキーワードは**LLMへのヒント**に過ぎず、LLMが生成する検索クエリに反映される保証がない。キーワードが検索クエリに含まれなかった場合、抽出処理が無駄になる。

### 改善案

2つのアプローチを検討:

**案A: LLM生成クエリにキーワードを強制付加**
```python
# LLMが生成したクエリに抽出キーワードを追加
final_query = f"{llm_generated_query} {' '.join(keywords)}"
```

**案B: Embedding検索とは別にキーワードフィルタリングに活用**（現在の `filter_results_by_keywords` を強化）
```python
# MeCab抽出キーワードで検索結果をフィルタ
filtered = filter_results_by_extracted_keywords(results, mecab_keywords)
```

---

## 6. Sparse Embedding のフォールバック処理が多重化（🟡 中程度）

### 問題

Sparse Vector がサポートされないコレクションへのフォールバックが **3段階** で重複実装されている:

1. **agent_tools.py L403-412**: `embed_sparse_query_unified()` の例外キャッチ → `sparse_vector = None`
2. **agent_tools.py L426-443**: `search_collection()` のスパースエラーキャッチ → `sparse_vector=None` で再試行
3. **qdrant_client_wrapper.py L1052-1060**: `search_collection()` 内の `UnexpectedResponse` キャッチ → `sparse_vector = None` で再試行

同一エラーに対して3段階のtry-exceptが走り、コードの可読性が低く、ログも混乱しやすい。

### 改善案

フォールバックの責務を `search_collection()` に一元化する:

```python
def search_collection(client, collection_name, query_vector, sparse_vector=None, limit=5):
    # sparse_vector があれば Hybrid Search を試行、失敗なら Dense のみ
    # フォールバックロジックはここだけ
    ...
```

呼び出し側 (`search_rag_knowledge_base_structured`) では try-except 不要にする。

---

## 7. `search_rag_knowledge_base` と `search_rag_knowledge_base_structured` の責務重複（🟡 中程度）

### 問題

`search_rag_knowledge_base()` (Legacy版) は内部で `search_rag_knowledge_base_structured()` を呼び、さらに独自のフォールバック検索ロジックを持っている。一方 `search_rag_knowledge_base_cached()` も `search_rag_knowledge_base_structured()` を呼ぶ。

```
search_rag_knowledge_base_cached → search_rag_knowledge_base → search_rag_knowledge_base_structured
search_rag_knowledge_base_cached → parallel_search_engine → search_rag_knowledge_base_structured
search_rag_knowledge_base_cached → (直接) → search_rag_knowledge_base_structured
```

3つのエントリポイントが存在し、フォーマット処理も `search_rag_knowledge_base()` と `_format_results()` で重複。

### 改善案

- `search_rag_knowledge_base()` の独自フォールバックロジックを削除（`search_rag_knowledge_base_cached` が並列検索で全コレクションをカバーしているため不要）
- エントリポイントを `search_rag_knowledge_base_cached()` に統一し、Legacy版は薄いラッパーにする

---

## 8. `filter_results_by_keywords` が未使用（⚪ 軽微）

### 問題

`agent_tools.py` L144 に `filter_results_by_keywords()` が定義されているが、現在の検索パイプラインのどこからも呼ばれていない。デッドコードになっている。

### 改善案

活用するか削除する。活用する場合は `rerank_results()` の後に配置するのが効果的。

---

## 9. Embedding次元数の不整合リスク（⚪ 軽微だが潜在的）

### 問題

`config.py` で `QdrantConfig.DEFAULT_VECTOR_SIZE = 3072` (gemini-embedding-001) だが、設計ドキュメント (`grace_chat_input_query.md`) では「768次元」と記載されている箇所がある。

また、`COLLECTION_EMBEDDINGS` にはOpenAI用 (1536次元) のコレクションも混在しており、検索時に次元数不整合でエラーになるリスクがある。

現在 `embed_query()` は常に `provider="gemini"` (3072次元) を使うため、OpenAI用コレクション (1536次元) に対して検索すると次元不一致エラーが発生する。

### 改善案

- コレクションごとにどのプロバイダー/次元数で作成されたかをメタデータとして保持
- 検索時にコレクションの次元数に合致するプロバイダーで Embedding を生成する

```python
def embed_query_for_collection(query: str, collection_name: str) -> List[float]:
    config = get_collection_embedding_config(collection_name)
    return embed_query_unified(query, provider=config["provider"])
```

---

## 10. print() がプロダクションコードに残存（⚪ 軽微）

### 問題

`regex_mecab.py` L102-103:
```python
print("✅ MeCabが利用可能です（複合名詞抽出モード）")
print("⚠️ MeCabが利用できません（正規表現モード）")
```

Streamlit環境ではコンソールに出力されるだけで、ユーザーには見えない。`logger` を使うべき。

---

## 改善優先度まとめ

| 優先度 | # | 項目 | 効果 |
|--------|---|------|------|
| 🔴 高 | 1 | Embedding生成の重複呼び出し | API コスト・レイテンシ大幅削減 |
| 🔴 高 | 2 | ヘルスチェック・存在確認の過剰呼び出し | Qdrant負荷・レイテンシ削減 |
| 🟡 中 | 3 | EmbeddingClient の毎回インスタンス化 | オーバーヘッド削減 |
| 🟡 中 | 4 | QdrantClient の分散管理 | リソース統一・設定不一致防止 |
| 🟡 中 | 5 | キーワード抽出とLLMクエリの二重処理 | 検索精度向上 |
| 🟡 中 | 6 | Sparse フォールバックの多重化 | コード可読性・保守性向上 |
| 🟡 中 | 7 | 検索関数の責務重複 | アーキテクチャ整理 |
| ⚪ 低 | 8 | デッドコード | コード整理 |
| ⚪ 低 | 9 | Embedding次元数の不整合リスク | 将来的なバグ防止 |
| ⚪ 低 | 10 | print()残存 | ログ統一 |
