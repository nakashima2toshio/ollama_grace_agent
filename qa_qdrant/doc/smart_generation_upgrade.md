# スマートQ/A生成のデフォルト化 - 改修サマリー

**改修日**: 2025-01-20
**対象ファイル**:
- `qa_generation/pipeline.py`
- `qa_qdrant/make_qa_register_qdrant.py`

---

## 📋 改修内容

### 主な変更点

**スマートQ/A生成（`SmartQAGenerator`）をデフォルトで有効化**

従来のトークン数ベースの固定Q/A数決定から、LLMによる動的Q/A数決定に切り替え。

---

## 🔧 変更ファイル詳細

### 1. `qa_generation/pipeline.py`

#### 変更箇所

##### 1-1. `run()` メソッドのシグネチャ

```python
def run(
    self,
    use_celery: bool = False,
    celery_workers: int = 8,
    batch_chunks: int = 3,
    merge_chunks: bool = True,
    min_tokens: int = 150,
    max_tokens: int = 400,
    analyze_coverage: bool = True,
    coverage_threshold: Optional[float] = None,
    overlap_tokens: int = 0,
    use_similarity: bool = False,
    similarity_threshold: float = 0.7,
    use_smart_generation: bool = True  # ✨ 新規追加（デフォルト: True）
):
```

**変更内容**:
- `use_smart_generation`パラメータを追加
- デフォルト値を`True`に設定

##### 1-2. `generate_qa()` メソッド

```python
def generate_qa(self, chunks: List[Dict],
                use_celery: bool = False,
                celery_workers: int = 8,
                batch_chunks: int = 3,
                merge_chunks: bool = True,
                min_tokens: int = 150,
                max_tokens: int = 400,
                use_smart_generation: bool = True) -> List[Dict]:  # ✨ 追加
    """Q/Aペアを生成する"""
    logger.info("\n[3/4] Q/Aペア生成...")

    # ✨ スマート生成モードのログ出力
    mode_name = "スマート生成" if use_smart_generation else "従来方式"
    logger.info(f"  生成モード: {mode_name}")
```

**変更内容**:
- `use_smart_generation`パラメータを追加
- 生成モードをログ出力

##### 1-3. `_generate_sync()` メソッド

```python
def _generate_sync(self, chunks: List[Dict], batch_size: int,
                   merge: bool, min_tokens: int, max_tokens: int,
                   use_smart_generation: bool) -> List[Dict]:  # ✨ 追加
    """同期生成"""
    logger.info("通常処理モード")
    dataset_type = self.config.get("type", "unknown")

    return generate_qa_dataset(
        chunks,
        dataset_type,
        self.model,
        chunk_batch_size=batch_size,
        merge_chunks=merge,
        min_tokens=min_tokens,
        max_tokens=max_tokens,
        config=self.config,
        client=self.client,
        use_smart_generation=use_smart_generation  # ✨ 追加
    )
```

**変更内容**:
- `use_smart_generation`を`generate_qa_dataset()`に渡す

##### 1-4. `_generate_with_celery()` メソッド

```python
def _generate_with_celery(self, chunks: List[Dict], workers: int, batch_size: int,
                          merge: bool, min_tokens: int, max_tokens: int,
                          use_smart_generation: bool) -> List[Dict]:  # ✨ 追加
    """Celeryを使用した非同期生成"""
    # ...
    tasks = submit_unified_qa_generation(
        processed_chunks, self.config, self.model, provider="gemini",
        use_smart_generation=use_smart_generation  # ✨ 追加
    )
```

**変更内容**:
- `use_smart_generation`をCeleryタスクに渡す

---

### 2. `qa_qdrant/make_qa_register_qdrant.py`

#### 変更箇所

##### 2-1. ファイルヘッダー

```python
"""
make_qa_register_qdrant.py - Q/A生成からQdrant登録までを完結する統合ツール（リファクタリング版）

改修内容:
- --input-chunksを廃止（チャンク処理の統一）
- --input-csvを--input-fileに変更（テキスト/CSV両対応）
- --outputオプションを追加（出力先の柔軟化）
- --ui-outputオプションを追加（UI用CSV出力先の柔軟化）
- スマートQ/A生成をデフォルトで有効化（SmartQAGenerator使用）  # ✨ 追加
  - LLMによる動的Q/A数決定（0-5個）
  - 内容の重要度・複雑さを考慮
  - --no-smart-generationで従来方式に戻すことも可能
"""
```

##### 2-2. CLIオプション追加

```python
# QA生成パラメータ
group_gen = parser.add_argument_group("QA Generation Options")
group_gen.add_argument("--model", type=str, default="gemini-2.0-flash")
group_gen.add_argument("--max-docs", type=int, default=None)
# ... 他のオプション ...

# ✨ スマート生成オプション（デフォルト: True）
group_gen.add_argument(
    "--use-smart-generation",
    action="store_true",
    default=True,
    help="スマートQ/A生成を使用（LLMによる動的Q/A数決定、デフォルト有効）"
)
group_gen.add_argument(
    "--no-smart-generation",
    dest="use_smart_generation",
    action="store_false",
    help="従来方式のQ/A生成を使用（トークン数ベース）"
)
```

**変更内容**:
- `--use-smart-generation`オプションを追加（デフォルト: True）
- `--no-smart-generation`オプションを追加（従来方式に切り替え）

##### 2-3. モード表示ログ

```python
# APIキー確認
if not os.getenv("GOOGLE_API_KEY"):
    logger.error("GOOGLE_API_KEYが設定されていません")
    sys.exit(1)

# ✨ スマート生成モードのログ表示
logger.info("")
logger.info("=" * 60)
if args.use_smart_generation:
    logger.info("🆕 Q/A生成モード: スマート生成（デフォルト）")
    logger.info("   - LLMによる動的Q/A数決定（0-5個）")
    logger.info("   - 内容の重要度・複雑さを考慮")
    logger.info("   - 主要トピックを明示的にカバー")
    logger.info("   ※ 従来方式に戻す場合: --no-smart-generation")
else:
    logger.info("🔧 Q/A生成モード: 従来方式（トークン数ベース）")
    logger.info("   - 固定的なQ/A数決定（2-8個）")
    logger.info("   ※ スマート生成に切り替える場合: --use-smart-generation")
logger.info("=" * 60)
```

**変更内容**:
- 起動時に現在の生成モードを表示
- 切り替え方法をユーザーに提示

##### 2-4. `pipeline.run()` 呼び出しの修正（3箇所）

**すべての`pipeline.run()`呼び出しに`use_smart_generation`を追加**:

```python
result = pipeline.run(
    use_celery=args.use_celery,
    celery_workers=args.celery_workers,
    batch_chunks=args.batch_chunks,
    merge_chunks=args.merge_chunks,
    analyze_coverage=True,
    overlap_tokens=args.overlap_tokens,
    use_similarity=args.use_similarity,
    similarity_threshold=args.similarity_threshold,
    use_smart_generation=args.use_smart_generation  # ✨ 追加
)
```

**修正箇所**:
1. テキストファイル処理時
2. CSV（テキストカラムのみ）処理時
3. データセット指定時

---

## 📊 動作の違い

### 従来方式（Legacy Mode）

```
チャンク → トークン数カウント → 固定Q/A数決定 → Q/A生成
                                (2-8個)     (1回のLLM呼び出し)
```

**特徴**:
- ✅ 高速
- ✅ 低コスト
- ❌ 機械的（内容を考慮しない）
- ❌ 不要なQ/Aも生成

### スマート方式（Smart Mode）- デフォルト

```
チャンク → LLMで分析 → 動的Q/A数決定 → Q/A生成
         (1回目)     (0-5個)        (2回目のLLM呼び出し)
                     + 重要度
                     + 複雑さ
                     + トピック
```

**特徴**:
- ✅ インテリジェント（内容を理解）
- ✅ 効率的（不要なQ/A生成を回避）
- ✅ 高品質（主要トピックを確実にカバー）
- ❌ 低速（2倍の時間）
- ❌ 高コスト（約2倍のAPI呼び出し）

---

## 💻 使用方法

### デフォルト（スマート生成）

```bash
python make_qa_register_qdrant.py \
  --input-file document.txt \
  --collection my_docs \
  --recreate
```

**実行ログ**:
```
==============================================================
🆕 Q/A生成モード: スマート生成（デフォルト）
   - LLMによる動的Q/A数決定（0-5個）
   - 内容の重要度・複雑さを考慮
   - 主要トピックを明示的にカバー
   ※ 従来方式に戻す場合: --no-smart-generation
==============================================================

Phase 1: QA Generation Pipeline
==============================================================

[3/4] Q/Aペア生成...
  生成モード: スマート生成
```

### 従来方式に切り替え

```bash
python make_qa_register_qdrant.py \
  --input-file document.txt \
  --collection my_docs \
  --recreate \
  --no-smart-generation
```

**実行ログ**:
```
==============================================================
🔧 Q/A生成モード: 従来方式（トークン数ベース）
   - 固定的なQ/A数決定（2-8個）
   ※ スマート生成に切り替える場合: --use-smart-generation
==============================================================

Phase 1: QA Generation Pipeline
==============================================================

[3/4] Q/Aペア生成...
  生成モード: 従来方式
```

---

## ⚙️ 推奨設定

### スマート生成を使うべき場合（デフォルト）

- ✅ 品質重視のプロジェクト
- ✅ 少量〜中量のデータ（100-1,000チャンク）
- ✅ 多様なコンテンツ（技術文書と一般文書の混在）
- ✅ トピックカバレッジが重要

### 従来方式を使うべき場合（`--no-smart-generation`）

- ✅ 大規模データセット（10,000+チャンク）
- ✅ コスト最適化が必要
- ✅ 高速処理が必要
- ✅ 安定性重視（本番環境）

---

## 🔄 後方互換性

### 既存コードへの影響

- ✅ **既存のコードは動作します**
  - `use_smart_generation`はオプション引数
  - 指定しない場合は新しいデフォルト（True）が適用される

### 従来の動作を維持する方法

#### 方法1: CLIオプション

```bash
--no-smart-generation
```

#### 方法2: コード内で明示的に指定

```python
pipeline.run(
    # ... 他のパラメータ ...
    use_smart_generation=False  # 従来方式を使用
)
```

---

## 📝 実行例

### 例1: スマート生成（デフォルト）

```bash
python make_qa_register_qdrant.py \
  --input-file technical_doc.txt \
  --collection tech_docs \
  --recreate
```

**期待される動作**:
- 技術的なチャンクから4-5個のQ/A生成
- 単純なチャンクから1-2個のQ/A生成
- メタ情報のみのチャンクは0個（スキップ）

### 例2: 従来方式（オプション指定）

```bash
python make_qa_register_qdrant.py \
  --input-file large_dataset.csv \
  --collection large_docs \
  --max-docs 10000 \
  --no-smart-generation \
  --recreate
```

**期待される動作**:
- すべてのチャンクから固定数（2-8個）のQ/A生成
- 高速処理
- 低コスト

---

## ⚠️ 注意事項

### 1. API コスト

スマート生成はLLM呼び出しが2倍になるため、**コストも約2倍**になります。

### 2. 処理時間

スマート生成は分析ステップが追加されるため、**処理時間も約2倍**になります。

### 3. Celery並列処理

Celery並列処理を使用する場合、`celery_tasks.py`の`submit_unified_qa_generation()`関数が`use_smart_generation`パラメータを受け取れるように更新する必要があります（別途対応が必要）。

現在のCelery実装では、この改修で追加した`use_smart_generation`パラメータが正しく伝播しない可能性があります。

---

## 🔍 動作確認方法

### テスト1: スマート生成が有効か確認

```bash
python make_qa_register_qdrant.py \
  --input-file test.txt \
  --collection test \
  --max-docs 5 \
  --recreate
```

ログに以下が表示されることを確認:
```
🆕 Q/A生成モード: スマート生成（デフォルト）
  生成モード: スマート生成
```

### テスト2: 従来方式に切り替え可能か確認

```bash
python make_qa_register_qdrant.py \
  --input-file test.txt \
  --collection test \
  --max-docs 5 \
  --no-smart-generation \
  --recreate
```

ログに以下が表示されることを確認:
```
🔧 Q/A生成モード: 従来方式（トークン数ベース）
  生成モード: 従来方式
```

---

## 📚 関連ドキュメント

- `qa_generation_comparison.md` - 2つの生成方式の詳細比較
- `make_qa_register_qdrant.md` - 統合ツールの完全ガイド
- `smart_qa_generator.py` - スマート生成の実装

---

**改修者**: AI Assistant
**改修日**: 2025-01-20
**バージョン**: v2.1（スマート生成デフォルト化版）
