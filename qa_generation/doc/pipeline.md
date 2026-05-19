
## pipeline.py 完全ガイド（v3.0）

## アーキテクチャ概要

```
csv_text_to_chunks_text_csv.py（前段処理）
              ↓
        チャンク済みCSV
              ↓
┌───────────────────────────────────────┐
│        pipeline.py (v3.0)             │
├───────────────────────────────────────┤
│ [1/3] load_data()                     │  ← CSV読み込み
│ [2/3] _load_chunks_from_csv()         │  ← チャンクリストに変換
│ [3/3] generate_qa()                   │  ← Q/A生成（SmartQAGenerator）
│       evaluate_coverage()             │  ← カバレッジ分析
│       save()                          │  ← 結果保存
└───────────────────────────────────────┘
```

---

## 目次

1. [概要](#概要)
2. [v3.0の変更点](#v30の変更点)
3. [システムアーキテクチャ](#システムアーキテクチャ)
4. [クラス構成](#クラス構成)
5. [メソッド詳細](#メソッド詳細)
6. [使用方法](#使用方法)
7. [パラメータリファレンス](#パラメータリファレンス)
8. [実行例](#実行例)
9. [出力ファイル](#出力ファイル)
10. [トラブルシューティング](#トラブルシューティング)
11. [関連モジュール](#関連モジュール)

---

## 概要

`qa_generation/pipeline.py` は、**チャンク済みCSVからQ/A生成、カバレッジ分析、結果保存までを一貫して実行するパイプライン制御モジュール**です。

### 主な特徴

- **チャンク済みCSV専用**: 前段処理（`csv_text_to_chunks_text_csv.py`）で作成されたチャンクCSVを入力として使用
- **SmartQAGenerator統合**: コンテンツを分析し、適切なQ/A数を動的に決定
- **Celery並列処理対応**: 大規模データセットの高速処理
- **多段階カバレッジ分析**: Strict/Standard/Lenientの3段階で評価
- **チャンク特性分析**: 長さ別・位置別のカバレッジ分析

### 前提条件

- 入力CSVは既にチャンク済み（`csv_text_to_chunks_text_csv.py`で処理済み）
- チャンクCSVには `text` または `Combined_Text` カラムが必要

---

## v3.0の変更点

### 削除された機能

| 削除項目 | 理由 |
|---------|------|
| `create_chunks()` メソッド | 前段のchunkingで完了済み |
| `_convert_df_to_chunks()` メソッド | 不要 |
| `skip_chunking` パラメータ | チャンク処理自体を削除 |
| `merge_chunks` パラメータ | 不要 |
| `min_tokens` / `max_tokens` パラメータ | 不要 |
| `overlap_tokens` パラメータ | 不要 |
| `use_similarity` / `similarity_threshold` パラメータ | 不要 |
| `structure.py` への依存 | 削除 |
| `input_chunks` パラメータ | `input_file` に統合 |

### 追加・変更された機能

| 項目 | 内容 |
|-----|------|
| SmartQAGenerator | Q/A生成の中核として直接使用 |
| `_load_chunks_from_csv()` | チャンクCSV→チャンクリスト変換用の新メソッド |
| `use_smart_generation` パラメータ | スマート生成モードの制御（デフォルト: True） |

---

## システムアーキテクチャ

### 依存関係

```
QAPipeline
├── qa_generation.data_io
│   ├── load_uploaded_file()         # ローカルファイル読み込み
│   ├── load_preprocessed_data()     # 前処理済みデータ読み込み
│   └── save_results()               # 結果保存
│
├── qa_generation.smart_qa_generator
│   └── SmartQAGenerator             # インテリジェントQ/A生成
│
├── qa_generation.evaluation
│   └── analyze_coverage()           # カバレッジ分析
│
├── celery_tasks
│   ├── submit_unified_qa_generation() # Celeryタスク投入
│   ├── collect_results()              # 結果収集
│   └── check_celery_workers()         # ワーカー確認
│
├── helper.helper_llm
    └── LLMClient                    # LLM操作

```

### レイヤー構成

```
┌──────────────────────────────────────────┐
│  Application Layer (QAPipeline)          │  ← パイプライン制御
│  - run()                                 │
├──────────────────────────────────────────┤
│  Business Logic Layer                    │
│  ├─ データ読み込み (data_io)               │
│  ├─ Q/A生成 (smart_qa_generator)         │
│  ├─ カバレッジ分析 (evaluation)            │
│  └─ 結果保存 (data_io)                    │
├──────────────────────────────────────────┤
│  Infrastructure Layer                    │
│  ├─ Celery (並列処理)                     │
│  ├─ LLMClient (Gemini API)               │
│  └─ SemanticCoverage (埋め込み生成)        │
└──────────────────────────────────────────┘
```

---

## クラス構成

```
QAPipeline
├── __init__()                    # 初期化、入力検証
├── _validate_inputs()            # 入力の排他制御
├── _load_config()                # 設定ロード
│
├── load_data()                   # データ読み込み（データセット/ファイル）
├── _load_chunks_from_csv()       # チャンクCSV→チャンクリスト変換
│
├── generate_qa()                 # Q/A生成（Celery/逐次）
│   ├── _generate_with_celery()   # Celery並列処理
│   └── _generate_sync()          # 逐次処理（SmartQAGenerator使用）
│
├── evaluate_coverage()           # カバレッジ分析
├── save()                        # 結果保存（JSON/CSV）
│
└── run()                         # パイプライン実行 ⭐メイン
```

---

## メソッド詳細

### `__init__()`

パイプラインの初期化を行います。

```python
def __init__(self,
             dataset_name: Optional[str] = None,
             input_file: Optional[str] = None,
             model: str = "gemini-2.0-flash",
             output_dir: str = "qa_output/pipeline",
             max_docs: Optional[int] = None,
             client: Optional[LLMClient] = None)
```

| パラメータ | 型 | デフォルト | 説明 |
|----------|---|----------|------|
| `dataset_name` | Optional[str] | None | 事前定義データセット名 |
| `input_file` | Optional[str] | None | チャンク済みCSVファイルパス |
| `model` | str | "gemini-2.0-flash" | 使用モデル |
| `output_dir` | str | "qa_output/pipeline" | 出力ディレクトリ |
| `max_docs` | Optional[int] | None | 最大処理チャンク数 |
| `client` | Optional[LLMClient] | None | LLMクライアント（DI用） |

**入力の排他制御**: `dataset_name` と `input_file` は同時に指定できません。

---

### `load_data()`

データを読み込みます。CSVファイルのみ対応。

```python
def load_data(self) -> pd.DataFrame
```

- `input_file` 指定時: `load_uploaded_file()` でCSV読み込み
- `dataset_name` 指定時: `load_preprocessed_data()` で前処理済みデータ読み込み

---

### `_load_chunks_from_csv()`

チャンク済みCSVをチャンクリストに変換します。

```python
def _load_chunks_from_csv(self, df: pd.DataFrame) -> List[Dict]
```

**対応カラム**:

| カラム種別 | 対応カラム名（優先順） |
|-----------|---------------------|
| テキスト | `text`, `Combined_Text`, `content`, `chunk_text` |
| ID | `chunk_id`, `id`, `chunk_idx` |

**出力形式**:

```python
{
    'id': 'chunk_0',
    'text': 'チャンクテキスト...',
    'type': 'pre_chunked',
    'tokens': 250,
    'dataset_type': 'data_chunks'
}
```

---

### `generate_qa()`

Q/Aペアを生成します。

```python
def generate_qa(self, chunks: List[Dict],
                use_celery: bool = False,
                celery_workers: int = 1,
                concurrency: int = 8,
                batch_chunks: int = 3,
                use_smart_generation: bool = True) -> List[Dict]
```

| パラメータ | 型 | デフォルト | 説明 |
|----------|---|----------|------|
| `chunks` | List[Dict] | - | チャンクのリスト |
| `use_celery` | bool | False | Celery並列処理を使用するか |
| `celery_workers` | int | 1 | ワーカープロセス数チェック用 |
| `concurrency` | int | 8 | 並列タスク数 |
| `batch_chunks` | int | 3 | 1回のAPIで処理するチャンク数 |
| `use_smart_generation` | bool | True | スマートQ/A生成を使用するか |

---

### `_generate_sync()`

SmartQAGeneratorを使用した同期生成。

```python
def _generate_sync(self, chunks: List[Dict], batch_size: int,
                   use_smart_generation: bool) -> List[Dict]
```

**処理フロー**:

1. 各チャンクに対して `SmartQAGenerator.process_chunk()` を実行
2. チャンク分析（`analyze_chunk`）で適切なQ/A数を動的決定
3. 分析結果に基づいてQ/Aペアを生成
4. 結果をリストに蓄積

---

### `evaluate_coverage()`

カバレッジを評価します。

```python
def evaluate_coverage(self, chunks: List[Dict], qa_pairs: List[Dict],
                      threshold: Optional[float] = None) -> Dict
```

**出力に含まれる情報**:

- 基本メトリクス（coverage_rate, covered_chunks, total_chunks）
- 多段階カバレッジ（strict, standard, lenient）
- チャンク特性別分析（長さ別、位置別）

---

### `run()`

パイプライン全体を実行します。

```python
def run(self,
        use_celery: bool = False,
        celery_workers: int = 1,
        concurrency: int = 8,
        batch_chunks: int = 3,
        analyze_coverage: bool = True,
        coverage_threshold: Optional[float] = None,
        use_smart_generation: bool = True) -> Dict
```

| パラメータ | 型 | デフォルト | 説明 |
|----------|---|----------|------|
| `use_celery` | bool | False | Celery並列処理を使用するか |
| `celery_workers` | int | 1 | ワーカープロセス数チェック用 |
| `concurrency` | int | 8 | 並列タスク数 |
| `batch_chunks` | int | 3 | 1回のAPIで処理するチャンク数 |
| `analyze_coverage` | bool | True | カバレッジ分析を実行するか |
| `coverage_threshold` | Optional[float] | None | カスタム閾値 |
| `use_smart_generation` | bool | True | スマートQ/A生成を使用するか |

**戻り値**:

```python
{
    "saved_files": {
        "qa_json": "path/to/qa_pairs.json",
        "qa_csv": "path/to/qa_pairs.csv",
        "coverage": "path/to/coverage.json",
        "summary": "path/to/summary.json"
    },
    "qa_count": 150,
    "coverage_results": {...},
    "success": True
}
```

---

## 使用方法

### 基本的な使用例

```python
from qa_generation.pipeline import QAPipeline

# チャンク済みCSVからQ/A生成
pipeline = QAPipeline(
    input_file="output_chunked/data_chunks.csv",
    model="gemini-2.0-flash",
    output_dir="qa_output/pipeline"
)

result = pipeline.run(
    use_celery=True,
    concurrency=8,
    use_smart_generation=True
)

print(f"生成Q/A数: {result['qa_count']}")
print(f"カバレッジ率: {result['coverage_results']['coverage_rate']:.1%}")
```

### データセットモード

```python
# 事前定義されたデータセットを使用
pipeline = QAPipeline(
    dataset_name="wikipedia_ja",
    max_docs=100
)

result = pipeline.run()
```

### 逐次処理モード（デバッグ用）

```python
pipeline = QAPipeline(input_file="chunks.csv")

result = pipeline.run(
    use_celery=False,  # Celeryを使用しない
    use_smart_generation=True
)
```

---

## パラメータリファレンス

### QAPipeline初期化パラメータ

| パラメータ | 必須 | 型 | デフォルト | 説明 |
|----------|:---:|---|----------|------|
| `dataset_name` | △ | str | None | データセット名 |
| `input_file` | △ | str | None | 入力CSVパス |
| `model` | - | str | "gemini-2.0-flash" | LLMモデル |
| `output_dir` | - | str | "qa_output/pipeline" | 出力先 |
| `max_docs` | - | int | None | 最大処理数 |
| `client` | - | LLMClient | None | カスタムクライアント |

※ `dataset_name` と `input_file` はいずれか1つを必ず指定

### run()メソッドパラメータ

| パラメータ | 型 | デフォルト | 説明 |
|----------|---|----------|------|
| `use_celery` | bool | False | Celery使用 |
| `celery_workers` | int | 1 | ワーカー数チェック |
| `concurrency` | int | 8 | 並列タスク数 |
| `batch_chunks` | int | 3 | バッチサイズ |
| `analyze_coverage` | bool | True | カバレッジ分析実行 |
| `coverage_threshold` | float | None | カスタム閾値 |
| `use_smart_generation` | bool | True | スマート生成使用 |

---

## 実行例

### ワークフロー1: 小規模テスト（逐次処理）

```python
pipeline = QAPipeline(
    input_file="test_chunks.csv",
    max_docs=10
)

result = pipeline.run(use_celery=False)
```

**所要時間**: 数分

### ワークフロー2: 中規模処理（Celery並列）

```bash
# Celery起動（別ターミナル）
./start_celery.sh restart -w 8
```

```python
pipeline = QAPipeline(input_file="data_chunks.csv")

result = pipeline.run(
    use_celery=True,
    celery_workers=8,
    concurrency=8
)
```

**所要時間**: 10〜30分

### ワークフロー3: 大規模処理

```bash
# Celery起動（最大ワーカー）
./start_celery.sh restart -w 24
```

```python
pipeline = QAPipeline(
    input_file="large_chunks.csv",
    max_docs=5000
)

result = pipeline.run(
    use_celery=True,
    celery_workers=24,
    concurrency=24
)
```

**所要時間**: 数時間

---

## 出力ファイル

パイプライン実行後、以下のファイルが生成されます:

```
qa_output/pipeline/
├── qa_pairs_{dataset}_{timestamp}.json    # Q/Aペア（JSON）
├── qa_pairs_{dataset}_{timestamp}.csv     # Q/Aペア（CSV）
├── coverage_{dataset}_{timestamp}.json    # カバレッジ分析結果
└── summary_{dataset}_{timestamp}.json     # 実行サマリー
```

### Q/Aペアの構造

```json
{
    "question": "AES-256暗号化の鍵長は何ビットですか？",
    "answer": "AES-256暗号化の鍵長は256ビットです。",
    "chunk_id": "chunk_0",
    "topic": "暗号化方式",
    "dataset_type": "data_chunks"
}
```

### カバレッジ分析結果の構造

```json
{
    "coverage_rate": 0.85,
    "covered_chunks": 85,
    "total_chunks": 100,
    "threshold": 0.7,
    "multi_threshold": {
        "strict": {"threshold": 0.8, "coverage_rate": 0.72},
        "standard": {"threshold": 0.7, "coverage_rate": 0.85},
        "lenient": {"threshold": 0.6, "coverage_rate": 0.93}
    },
    "chunk_analysis": {
        "by_length": {...},
        "by_position": {...}
    }
}
```

---

## トラブルシューティング

### 問題1: 入力検証エラー

**症状**:
```
ValueError: dataset_name, input_file のいずれか1つを指定してください
```

**対処法**:
```python
# ❌ 誤り: 何も指定していない
pipeline = QAPipeline()

# ❌ 誤り: 両方指定
pipeline = QAPipeline(dataset_name="wiki", input_file="data.csv")

# ✅ 正しい
pipeline = QAPipeline(input_file="data_chunks.csv")
```

### 問題2: テキストカラムが見つからない

**症状**:
```
ValueError: テキストカラムが見つかりません。
```

**対処法**:
```python
# CSVカラム名を確認
import pandas as pd
df = pd.read_csv("chunks.csv")
print(df.columns.tolist())

# 必要に応じてカラム名を変更
df = df.rename(columns={'content': 'text'})
df.to_csv("chunks_fixed.csv", index=False)
```

### 問題3: Celeryワーカー未起動

**症状**:
```
RuntimeError: Celery workers are not running
```

**対処法**:
```bash
# ワーカー起動
./start_celery.sh restart -w 8

# ステータス確認
./start_celery.sh status

# または、Celeryなしで実行
pipeline.run(use_celery=False)
```

### 問題4: カバレッジ率が低い

**症状**:
```
coverage_rate: 0.45  # 期待: 0.70以上
```

**対処法**:

1. Q/A生成数を確認（SmartQAGeneratorは自動調整するため、チャンク内容に依存）
2. チャンクサイズが適切か確認（小さすぎると情報不足でQ/A生成されない）
3. カスタム閾値を下げてみる

```python
result = pipeline.run(coverage_threshold=0.6)
```

### 問題5: メモリ不足

**症状**:
```
MemoryError: Unable to allocate array
```

**対処法**:
```python
# max_docsで制限
pipeline = QAPipeline(input_file="large.csv", max_docs=100)

# または、Celeryで分散処理
result = pipeline.run(use_celery=True, celery_workers=24)
```

---

## 関連モジュール

| モジュール | 説明 |
|-----------|------|
| `qa_generation/data_io.py` | データ入出力 |
| `qa_generation/smart_qa_generator.py` | インテリジェントQ/A生成 |
| `qa_generation/evaluation.py` | カバレッジ分析 |
| `qa_generation/semantic.py` | セマンティック分析・埋め込み生成 |
| `qa_generation/models.py` | Pydanticモデル定義 |
| `celery_tasks.py` | Celeryタスク定義 |

### SmartQAGenerator

コンテンツを分析し、適切なQ/A数を動的に決定するインテリジェント生成システム。

**主な機能**:
- チャンク分析（情報密度、重要度、複雑さ）
- 0〜5個の動的Q/A数決定
- 重要トピックの抽出と優先化

**使用例**:
```python
from qa_generation.smart_qa_generator import SmartQAGenerator

generator = SmartQAGenerator(model="gemini-2.0-flash")
result = generator.process_chunk(chunk_text)

print(f"分析結果: {result['analysis']}")
print(f"生成Q/A数: {len(result['qa_pairs'])}")
```

### カバレッジ分析（evaluation.py）

**多段階カバレッジ**:
- Strict（閾値0.8）: 厳格な評価
- Standard（閾値0.7）: 標準評価
- Lenient（閾値0.6）: 緩やかな評価

**チャンク特性分析**:
- 長さ別（short/medium/long）
- 位置別（beginning/middle/end）

---

## ベストプラクティス

### 1. 開発フロー

```
1. チャンクCSV作成（csv_text_to_chunks_text_csv.py）
      ↓
2. チャンク品質確認
      ↓
3. 小規模テスト（max_docs=10, use_celery=False）
      ↓
4. 中規模テスト（max_docs=100, use_celery=True）
      ↓
5. 本番実行
```

### 2. Celeryの活用

```python
# チャンク数に応じた選択
chunk_count = len(chunks)

if chunk_count < 50:
    use_celery = False
elif chunk_count < 500:
    use_celery = True
    celery_workers = 8
else:
    use_celery = True
    celery_workers = 24
```

### 3. エラーハンドリング

```python
import logging

logging.basicConfig(level=logging.INFO)

try:
    pipeline = QAPipeline(input_file="chunks.csv")
    result = pipeline.run()

except ValueError as e:
    logging.error(f"設定エラー: {e}")
except RuntimeError as e:
    logging.error(f"実行時エラー: {e}")
except Exception as e:
    logging.error(f"予期しないエラー: {e}")
```

### 4. 結果の検証

```python
import pandas as pd

# CSV読み込み
df = pd.read_csv(result['saved_files']['qa_csv'])

# 基本統計
print(f"Q/A数: {len(df)}")
print(f"チャンク別Q/A数:\n{df.groupby('chunk_id').size().describe()}")

# サンプル確認
for i in range(min(3, len(df))):
    print(f"\nQ: {df.iloc[i]['question']}")
    print(f"A: {df.iloc[i]['answer']}")
```

---

**作成日**: 2025-01-27
**対象ファイル**: `qa_generation/pipeline.py`
**バージョン**: v3.0（チャンク処理削除版）

