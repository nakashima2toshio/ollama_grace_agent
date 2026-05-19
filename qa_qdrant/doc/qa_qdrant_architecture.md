# Q/A生成 & Qdrant登録システム 完全設計書（v3.0）

## 更新履歴

| 日付 | バージョン | 変更内容 |
|-----|----------|---------|
| 2025-01-28 | v3.0 | pipeline.py v3.0対応、チャンク処理の外部化、make_qa.py引数整理 |
| 2025-01-26 | v2.x | 初版作成 |

---

## 1. システム概要

テキスト/CSVデータからQ/Aペアを自動生成し、Qdrantベクトルデータベースに登録するRAGパイプラインシステム。

### v3.0の主な変更点

| 項目 | v2.x | v3.0 |
|-----|------|------|
| **チャンク処理** | pipeline.py内部で実行 | **外部で事前実行**（csv_text_to_chunks_text_csv.py） |
| **入力方式** | `--input-file`, `--input-chunks` 分離 | `--input-file` に統一 |
| **並列制御** | `--celery-workers` | `-c, --concurrency` 追加 |
| **Q/A生成** | 固定数生成 | **SmartQAGenerator**（動的0-5個） |
| **structure.py** | 依存あり | **依存削除** |
| **config.py依存** | evaluation.pyで使用 | **削除**（統一閾値） |

### システムアーキテクチャ図

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIツール群                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  make_qa.py              make_qa_register_qdrant.py    register_to_qdrant.py│
│  (Q/A生成専用)            (統合ツール)                  (Qdrant登録専用)        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  Phase 0      │         │    Phase 1      │         │    Phase 2      │
│  CSV行結合     │         │   Q/A生成        │         │  Qdrant登録     │
│ (オプション)    │         │                 │         │                 │
└───────────────┘         └─────────────────┘         └─────────────────┘
        │                         │                           │
        ▼                         ▼                           ▼
  combine_rows_to_chunks    QAPipeline                 run_registration
        │                         │                           │
        │                    ┌────┴────┐                      │
        │                    ▼         ▼                      ▼
        │              Smart生成   Legacy生成           Qdrant Service
        │                    │         │                      │
        │                    ▼         ▼                      ▼
        │               SmartQA    (トークン               Embedding生成
        │               Generator   ベース)                    │
        │                    │         │                      ▼
        │                    └────┬────┘                 ベクトル登録
        │                         │
        │                         ▼
        │                  カバレージ分析
        │                  (evaluation.py)
        │                         │
        └─────────────────────────┼─────────────────────────────
                                  ▼
                           出力ファイル生成
                        (CSV/JSON/UI CSV)
```

---

## 2. ファイル構成と依存関係

### 2.1 CLIツール (`qa_qdrant/`)

| ファイル | 役割 | v3.0変更 |
|---------|------|---------|
| `make_qa.py` | Q/A生成CLIエントリーポイント | 引数整理、`--input-chunks`削除 |
| `make_qa_register_qdrant.py` | Q/A生成+Qdrant登録統合ツール | `-c, --concurrency`追加 |
| `register_to_qdrant.py` | Qdrant登録専用ツール | 変更なし |

### 2.2 Q/A生成モジュール (`qa_generation/`)

| ファイル | 役割 | v3.0変更 |
|---------|------|---------|
| `pipeline.py` | Q/A生成パイプライン制御 | **チャンク処理削除**、SmartQAGenerator統合 |
| `smart_qa_generator.py` | スマートQ/A生成エンジン | google.genai API対応 |
| `evaluation.py` | カバレッジ分析 | **config.py依存削除**、統一閾値 |
| `semantic.py` | セマンティック分析・埋め込み | 変更なし |
| `data_io.py` | データ入出力 | 変更なし |
| `models.py` | Pydanticモデル定義 | 変更なし |
| ~~`structure.py`~~ | ~~チャンク分割~~ | **pipeline.pyから依存削除** |
| ~~`generation.py`~~ | ~~Q/A生成ロジック~~ | **SmartQAGeneratorに統合** |

### 2.3 前処理モジュール (`chunking/`)

| ファイル | 役割 | v3.0変更 |
|---------|------|---------|
| `csv_text_to_chunks_text_csv.py` | テキスト→チャンクCSV変換 | **新規追加（v3.0必須）** |

### 2.4 Qdrantモジュール

| ファイル | 役割 |
|---------|------|
| `services/qdrant_service.py` | Qdrant操作サービス（高レベルAPI） |
| `qdrant_client_wrapper.py` | Qdrantクライアントラッパー（低レベルAPI） |

### 2.5 ヘルパーモジュール (`helper/`)

| ファイル | 役割 |
|---------|------|
| `helper_llm.py` | LLMクライアント抽象化 |
| `helper_embedding.py` | Embeddingクライアント抽象化 |

### 2.6 設定・タスク

| ファイル | 役割 |
|---------|------|
| `config.py` | 全設定の一元管理 |
| `celery_tasks.py` | Celery分散タスク定義 |
| `celery_config.py` | Celery設定 |

---

## 3. 処理フロー詳細

### 3.0 前処理: チャンク化（v3.0で外部化）

```bash
# v3.0: チャンク化は事前に実行が必要
python -m chunking.csv_text_to_chunks_text_csv \
  --input-file data/document.txt \
  --output output_chunked \
  --max-tokens 200 \
  --min-tokens 50
```

```python
# csv_text_to_chunks_text_csv.py の処理
def create_chunks(input_file, output_dir, max_tokens, min_tokens):
    """
    テキストファイルをチャンクCSVに変換

    処理:
    1. テキストファイル読み込み
    2. 段落/文単位で分割
    3. トークン数に基づくチャンク作成
    4. チャンクCSVとして出力

    出力CSV形式:
    chunk_id, text, tokens, type
    """
```

### 3.1 Phase 0: CSV行結合（オプション）

```python
# トリガー: --combine-rows フラグ
def combine_rows_to_chunks(df, text_column, block_size, output_dir):
    """
    複数のCSV行を結合してチャンクを作成

    処理:
    1. CSVを読み込み
    2. text_columnからテキストを抽出
    3. block_size行ごとに結合
    4. combined_chunks_YYYYMMDD_HHMMSS.csv として出力

    出力:
    {
        "chunk_id": int,
        "text": str,
        "start_row": int,
        "end_row": int,
        "row_count": int
    }
    """
```

### 3.2 Phase 1: Q/A生成

#### 3.2.1 パイプライン制御 (`QAPipeline` v3.0)

```python
class QAPipeline:
    """Q/A生成パイプライン（v3.0 - チャンク処理削除版）"""

    def __init__(self,
                 dataset_name: str = None,
                 input_file: str = None,      # チャンク済みCSV
                 model: str = "gemini-2.0-flash",
                 output_dir: str = "qa_output/pipeline",
                 max_docs: int = None):
        """
        初期化

        v3.0変更点:
        - input_chunks引数を削除（input_fileに統合）
        - 入力はチャンク済みCSVのみ対応
        """

    def run(self,
            use_celery: bool = False,
            celery_workers: int = 1,
            concurrency: int = 8,           # v3.0追加
            batch_chunks: int = 3,
            analyze_coverage: bool = False,
            coverage_threshold: float = None,
            use_smart_generation: bool = True  # v3.0追加
            ) -> Dict:
        """
        メインパイプライン実行

        v3.0フロー:
        1. _load_chunks_from_csv()  - チャンクCSV読み込み
        2. generate_qa_pairs()      - Q/A生成（Smart or Legacy）
        3. evaluate_coverage()      - カバレージ分析（オプション）
        4. save_results()           - 結果保存

        削除されたステップ:
        - create_chunks() は外部で事前実行
        """
```

#### 3.2.2 チャンク読み込み（v3.0新規）

```python
def _load_chunks_from_csv(self, csv_path: str) -> List[Dict]:
    """
    チャンクCSVを読み込んでチャンクリストに変換

    対応カラム名:
    - テキスト: 'text' または 'Combined_Text'
    - ID: 'chunk_id', 'id', または 'chunk_idx'

    出力:
    [
        {
            'id': 'chunk_0',
            'text': '...',
            'chunk_idx': 0
        },
        ...
    ]
    """
```

#### 3.2.3 スマートQ/A生成 (`SmartQAGenerator` v2.5)

```python
class SmartQAGenerator:
    """コンテンツを考慮したインテリジェントQ/A生成（v2.5）"""

    def __init__(self, model: str = "gemini-2.0-flash", api_key: str = None):
        """
        初期化

        API対応:
        - 新API: google.genai（推奨）
        - 旧API: google.generativeai（フォールバック）
        """

    def analyze_chunk(self, chunk_text: str) -> Dict:
        """
        チャンク分析（LLM使用）

        分析観点:
        1. 情報密度: 独立した情報・事実の数
        2. 重要度: critical/high/medium/low
        3. 複雑さ: high/medium/low
        4. 独立性: 他の文脈なしで理解可能か

        出力:
        {
            'qa_count': 0-5,           # 生成すべきQ/A数
            'key_topics': [...],       # 主要トピック
            'importance_score': 0.85,  # 重要度スコア
            'complexity': 'high',      # low/medium/high
            'reasoning': '...'         # 分析理由
        }

        Q/A数の判断基準:
        - 0個: 補足情報のみ、メタ情報
        - 1個: 単純な事実の記述
        - 2個: 関連する2つの事実
        - 3個: 標準的な説明パラグラフ
        - 4-5個: 高密度な技術情報、警告・注意事項
        """

    def generate_qa_pairs(self, chunk_text: str, analysis: Dict) -> List[Dict]:
        """
        分析結果に基づくQ/A生成

        出力:
        [
            {
                'question': '...',
                'answer': '...',
                'topic': 'トピック名'
            },
            ...
        ]
        """

    def process_chunk(self, chunk_text: str) -> Dict:
        """
        analyze + generate の統合処理

        出力:
        {
            'analysis': Dict,
            'qa_pairs': List[Dict],
            'success': bool
        }
        """
```

### 3.3 Phase 2: Qdrant登録

#### 3.3.1 登録メイン処理

```python
def run_registration(csv_path, collection_name, recreate=False,
                    batch_size=100, provider="gemini", ui_output_dir="qa_output"):
    """
    Q/A CSVをQdrantに登録

    処理:
    1. CSVロード & テキスト列検出
    2. コレクション作成/再作成
    3. バッチ埋め込み生成
    4. ポイント構築 & アップサート
    5. UI用CSV生成（ファイル名正規化）
    """
```

#### 3.3.2 Qdrantサービス (`qdrant_service.py`)

```python
# ===== ヘルスチェック =====
class QdrantHealthChecker:
    def check_port(host, port, timeout=2.0) -> bool
    def check_qdrant() -> Tuple[bool, str, Optional[Dict]]

# ===== データフェッチ =====
class QdrantDataFetcher:
    def fetch_collections() -> pd.DataFrame
    def fetch_collection_points(collection_name, limit=50) -> pd.DataFrame
    def fetch_collection_info(collection_name) -> Dict

# ===== コレクション管理 =====
def create_or_recreate_collection_for_qdrant(client, name, recreate, vector_size=3072)
def get_collection_stats(client, collection_name) -> Optional[Dict]

# ===== データ処理・登録 =====
def embed_texts_for_qdrant(texts, batch_size=100) -> List[List[float]]
def build_points_for_qdrant(df, vectors, domain, source_file, start_index=0) -> List[PointStruct]
def upsert_points_to_qdrant(client, collection, points, batch_size=128) -> int
```

---

## 4. カバレッジ分析 (`evaluation.py` v3.0)

```python
def get_optimal_thresholds(dataset_type: str = None) -> Dict[str, float]:
    """
    カバレージ分析用の閾値を取得

    v3.0変更: 統一デフォルト値を使用（データセット別設定を廃止）

    返却:
    {
        "strict": 0.8,
        "standard": 0.7,
        "lenient": 0.6
    }
    """

def multi_threshold_coverage(coverage_matrix, chunks, qa_pairs, thresholds) -> Dict:
    """
    複数閾値でカバレージを評価

    各閾値レベル（strict/standard/lenient）ごとに:
    - covered_chunks
    - coverage_rate
    - uncovered_chunks
    """

def analyze_chunk_characteristics_coverage(chunks, coverage_matrix, qa_pairs, threshold=0.7) -> Dict:
    """
    チャンク特性別のカバレージ分析

    分析軸:
    - by_length: short(<100)/medium(100-199)/long(>=200)
    - by_position: beginning(<33%)/middle(33-66%)/end(>=67%)
    - summary + insights
    """

def analyze_coverage(chunks, qa_pairs, dataset_type="wikipedia_ja",
                    custom_threshold=None) -> Dict:
    """
    包括的カバレージ分析

    処理:
    1. チャンク埋め込み生成
    2. Q/Aペア埋め込み生成（バッチAPI）
    3. カバレージ行列計算（NumPy行列積）
    4. 多段階カバレージ分析
    5. チャンク特性別分析
    """
```

---

## 5. コマンドラインオプション

### 5.1 make_qa.py（v3.0）

```bash
python qa_qdrant/make_qa.py [OPTIONS]

# === 入力オプション（排他的・必須） ===
--dataset NAME           # 定義済みデータセット名
--input-file PATH        # チャンク済みCSVファイルパス

# === 共通パラメータ ===
--model NAME             # LLMモデル (default: gemini-2.0-flash)
--output DIR             # 出力ディレクトリ (default: qa_output/pipeline)
--max-docs N             # 処理する最大チャンク数

# === カバレージ分析 ===
--analyze-coverage       # カバレージ分析を実行
--coverage-threshold N   # カバレージ判定の類似度閾値

# === Q/A生成パラメータ ===
--batch-chunks N         # 1回のAPIで処理するチャンク数 (default: 3)
--use-smart-generation   # スマートQ/A生成を使用 (default: True)
--no-smart-generation    # 従来方式を使用

# === Celery並列処理 ===
--use-celery             # Celery並列処理を使用
-c, --concurrency N      # 並列タスク数 (default: 8)
--celery-workers N       # (非推奨) ワーカー数チェック用

# === 削除された引数（v3.0） ===
# --input-chunks        → --input-file に統合
# --merge-chunks        → 削除
# --min-tokens          → 削除
# --max-tokens          → 削除
# --overlap-tokens      → 削除
# --use-similarity      → 削除
# --similarity-threshold → 削除
```

### 5.2 make_qa_register_qdrant.py

```bash
python qa_qdrant/make_qa_register_qdrant.py [OPTIONS]

# === 入力オプション ===
--dataset NAME           # 定義済みデータセット名
--input-file PATH        # ローカルファイルパス (.txt, .csv)
--text-column NAME       # CSVのテキスト列名 (default: text)
--combine-rows           # CSV行結合モード有効化
--block-size N           # 結合する行数 (default: 400)

# === Q/A生成オプション ===
--model NAME             # LLMモデル (default: gemini-2.0-flash)
--use-smart-generation   # スマート生成有効 (default: True)
--no-smart-generation    # 従来方式
--batch-chunks N         # バッチあたりのチャンク数 (default: 3)
--use-celery             # Celery並列処理有効化
-c, --concurrency N      # 並列タスク数 (default: 8)

# === Qdrantオプション ===
--collection NAME        # コレクション名（必須）
--recreate               # コレクション再作成
--batch-size N           # 埋め込みバッチサイズ (default: 100)
--provider NAME          # gemini or openai (default: gemini)

# === 出力オプション ===
--output DIR             # Q/A出力ディレクトリ (default: qa_output/pipeline)
--ui-output DIR          # UI用CSV出力ディレクトリ (default: qa_output)
```

### 5.3 register_to_qdrant.py

```bash
python qa_qdrant/register_to_qdrant.py [OPTIONS]

# === 必須引数 ===
--input-file PATH        # 登録するCSVファイルのパス
--collection NAME        # 登録先のQdrantコレクション名

# === Qdrant設定 ===
--recreate               # コレクション再作成
--batch-size N           # バッチサイズ (default: 100)

# === ベクトル化設定 ===
--text-col NAME          # ベクトル化対象カラム（自動検出可）
--provider NAME          # gemini or openai (default: gemini)

# === 出力設定 ===
--normalize-filename     # ファイル名正規化 (default: True)
--create-ui-csv          # UI用CSV生成 (default: True)
--ui-output-dir DIR      # UI用CSV出力先 (default: qa_output)
```

---

## 6. 使用例

### 6.1 基本的なワークフロー（v3.0）

```bash
# Step 1: テキストファイルをチャンク化（v3.0で必須）
python -m chunking.csv_text_to_chunks_text_csv \
  --input-file data/document.txt \
  --output output_chunked \
  --max-tokens 200

# Step 2: Q/A生成
python qa_qdrant/make_qa.py \
  --input-file output_chunked/document_chunks.csv \
  --use-celery \
  -c 8 \
  --analyze-coverage

# Step 3: Qdrant登録（オプション）
python qa_qdrant/register_to_qdrant.py \
  --input-file qa_output/pipeline/qa_pairs_xxx.csv \
  --collection my_collection \
  --recreate
```

### 6.2 統合ツールを使用

```bash
# Q/A生成 + Qdrant登録を一括実行
python qa_qdrant/make_qa_register_qdrant.py \
  --input-file output_chunked/data_chunks.csv \
  --collection my_collection \
  --use-celery \
  -c 8 \
  --recreate
```

### 6.3 CSV行結合モード

```bash
# 多数の短い行を結合してからQ/A生成
python qa_qdrant/make_qa_register_qdrant.py \
  --input-file data/news.csv \
  --text-column text \
  --combine-rows \
  --block-size 400 \
  --collection news_qa \
  --use-celery \
  -c 8 \
  --recreate
```

### 6.4 Celery並列処理

```bash
# 1. Celeryワーカー起動（別ターミナル）
./start_celery.sh restart -c 8 --flower

# 2. 並列処理でQ/A生成
python qa_qdrant/make_qa.py \
  --input-file output_chunked/data_chunks.csv \
  --use-celery \
  -c 8 \
  --use-smart-generation \
  --analyze-coverage
```

### 6.5 従来方式（Legacy）

```bash
# スマート生成を使わない高速処理
python qa_qdrant/make_qa.py \
  --input-file output_chunked/data_chunks.csv \
  --no-smart-generation \
  --analyze-coverage
```

---

## 7. 出力ファイル

### 7.1 Q/A生成フェーズ出力

```
qa_output/pipeline/
├── qa_pairs_local_file_20250128_123456.csv   # Q/Aペア（CSV）
├── qa_pairs_local_file_20250128_123456.json  # Q/Aペア（JSON）
├── coverage_local_file_20250128_123456.json  # カバレージ分析
└── summary_local_file_20250128_123456.json   # サマリー
```

### 7.2 Qdrant登録フェーズ出力

```
qa_output/
└── {collection_name}.csv   # UI用CSV（タイムスタンプなし、正規化済み）
```

### 7.3 チャンク化出力（v3.0）

```
output_chunked/
└── {filename}_chunks.csv   # チャンク済みCSV
```

---

## 8. 依存関係図（v3.0）

```
make_qa.py / make_qa_register_qdrant.py
├── qa_generation/
│   ├── pipeline.py (v3.0)
│   │   ├── data_io.py
│   │   ├── smart_qa_generator.py (v2.5)  ← 直接依存
│   │   └── evaluation.py (v3.0)
│   │       └── semantic.py
│   └── models.py
├── services/qdrant_service.py
│   ├── qdrant_client_wrapper.py
│   └── helper/helper_embedding.py
├── helper/
│   ├── helper_llm.py
│   └── helper_embedding.py
├── config.py
└── celery_tasks.py
    └── celery_config.py

chunking/
└── csv_text_to_chunks_text_csv.py  ← 前処理（pipeline.pyから分離）
```

### 削除された依存関係（v3.0）

```
# pipeline.py から削除
- structure.py への依存
- create_chunks() メソッド
- _convert_df_to_chunks() メソッド

# evaluation.py から削除
- config.py への依存（DATASET_CONFIGS）
```

---

## 9. 環境変数

```bash
# 必須
GOOGLE_API_KEY=your_gemini_api_key

# オプション（OpenAI使用時）
OPENAI_API_KEY=your_openai_api_key

# オプション（設定変更）
EMBEDDING_PROVIDER=gemini  # or openai
LLM_PROVIDER=gemini        # or openai

# Celery（並列処理時）
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

---

## 10. 技術的特徴

### 10.1 SmartQAGenerator

- **動的Q/A数決定**: LLMによるチャンク分析で0-5個を決定
- **2段階処理**: 分析（temperature=0.1）→ 生成（temperature=0.3）
- **フォールバック**: API障害時は文字数ベースで簡易判定

### 10.2 Gemini API

- **google.genai** パッケージ使用（新API）
- 埋め込み: 3072次元（Gemini最大精度）
- フォールバック: google.generativeai（旧API）

### 10.3 並列処理

- チャンク分割: csv_text_to_chunks_text_csv.py（前処理）
- Q/A生成: Celery分散タスク
- 埋め込み生成: バッチAPI（最大100件/リクエスト）

### 10.4 カバレッジ分析

- 多段階閾値評価（strict/standard/lenient）
- チャンク特性別分析（長さ別/位置別）
- NumPy行列積による高速計算

---

*Last Updated: 2025-01-28 (v3.0)*
