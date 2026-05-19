# qdrant_service.py - Qdrant操作サービス ドキュメント

**Version 1.3** | 最終更新: 2025-01-28

---

## 概要

`qdrant_service.py`は、Qdrantベクトルデータベースとの通信・操作を一元管理するサービスモジュールです。RAG（Retrieval-Augmented Generation）システムにおけるベクトル検索の基盤を提供します。

### 主な機能

| 機能 | 説明 |
|------|------|
| ヘルスチェック | Qdrantサーバーの接続状態監視 |
| データ取得 | コレクションからのデータ取得・分析 |
| コレクション管理 | CRUD操作（作成・読取・更新・削除） |
| 埋め込み生成・登録 | テキストのベクトル化とQdrantへの登録 |
| 検索機能 | クエリベクトルによる類似検索 |

---

## 1. アーキテクチャ構成図

### 1.1 システム全体構成

```
┌─────────────────────────────────────────────────────────────────┐
│                        クライアント層                            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │   Streamlit      │  │    FastAPI       │  │  CLI Tools   │  │
│  │   Dashboard      │  │    Endpoints     │  │              │  │
│  └────────┬─────────┘  └────────┬─────────┘  └──────┬───────┘  │
└───────────┼─────────────────────┼───────────────────┼──────────┘
            │                     │                   │
            └──────────────────┬──┴───────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      qdrant_service.py                          │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  QdrantHealthChecker  │  QdrantDataFetcher                 │ │
│  ├────────────────────────────────────────────────────────────┤ │
│  │  Collection Management │  Embedding Functions              │ │
│  ├────────────────────────────────────────────────────────────┤ │
│  │  Search Functions      │  Utility Functions                │ │
│  └────────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬─────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       外部サービス層                             │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │
│  │    Qdrant      │  │    Gemini      │  │    OpenAI      │    │
│  │    Server      │  │    API         │  │    API         │    │
│  │    :6333       │  │   Embedding    │  │   Embedding    │    │
│  └────────────────┘  └────────────────┘  └────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 データフロー

1. クライアント層からのリクエストを受信
2. `qdrant_service.py`が適切な処理を実行
3. 必要に応じてEmbedding APIを呼び出してベクトル生成
4. Qdrantサーバーとの通信（CRUD・検索）
5. 結果をクライアント層に返却

---

## 2. モジュール構成図

### 2.1 内部モジュール構成

```
qdrant_service.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[設定・定数]
  • QDRANT_CONFIG              - サーバー接続設定
  • COLLECTION_EMBEDDINGS_SEARCH  (deprecated)
  • COLLECTION_CSV_MAPPING        (deprecated)

[クラス]
  ├── QdrantHealthChecker      - 接続状態確認
  │     ├── check_port()
  │     └── check_qdrant()
  │
  └── QdrantDataFetcher        - データ取得
        ├── fetch_collections()
        ├── fetch_collection_points()
        ├── fetch_collection_info()
        └── fetch_collection_source_info()

[関数グループ]
  ├── マッピング関数
  │     ├── map_collection_to_csv()
  │     ├── get_dynamic_collection_mapping()
  │     └── get_collection_embedding_params()
  │
  ├── コレクション管理関数
  │     ├── get_collection_stats()
  │     ├── get_all_collections()
  │     ├── get_all_collections_simple()
  │     └── delete_all_collections()
  │
  ├── データ処理・登録関数
  │     ├── load_csv_for_qdrant()
  │     ├── build_inputs_for_embedding()
  │     ├── embed_texts_for_qdrant()
  │     ├── create_or_recreate_collection_for_qdrant()
  │     ├── build_points_for_qdrant()
  │     └── upsert_points_to_qdrant()
  │
  ├── 検索関数
  │     └── embed_query_for_search()
  │
  ├── コレクション統合関数
  │     ├── scroll_all_points_with_vectors()
  │     └── merge_collections()
  │
  └── ユーティリティ関数
        └── batched()
```

### 2.2 外部依存関係

| ライブラリ | バージョン | 用途 |
|-----------|-----------|------|
| `qdrant-client` | 1.x | Qdrant Python クライアント |
| `pandas` | 2.x | データフレーム操作 |
| `tiktoken` | 0.x | トークンカウント |

### 2.3 内部依存モジュール

| モジュール | 用途 |
|-----------|------|
| `helper.helper_embedding` | 埋め込みクライアント作成・次元数取得 |
| `qdrant_client_wrapper` | Sparse Vector生成、コレクション作成ラッパー |

---

## 3. クラス・関数一覧表

### 3.1 クラス一覧

#### QdrantHealthChecker

| メソッド | 概要 |
|---------|------|
| `__init__(debug_mode)` | コンストラクタ（debug_mode指定） |
| `check_port(host, port, timeout)` | ポート開放確認 |
| `check_qdrant()` | Qdrant接続・統計取得 |

#### QdrantDataFetcher

| メソッド | 概要 |
|---------|------|
| `__init__(client)` | コンストラクタ（QdrantClient指定） |
| `fetch_collections()` | コレクション一覧取得 |
| `fetch_collection_points(collection_name, limit)` | ポイントデータ取得 |
| `fetch_collection_info(collection_name)` | コレクション詳細情報取得 |
| `fetch_collection_source_info(collection_name, sample_size)` | データソース統計取得 |

### 3.2 関数一覧（カテゴリ別）

#### マッピング関数

| 関数名 | 概要 |
|-------|------|
| `map_collection_to_csv(collection_name, qa_output_dir)` | コレクション名からCSVファイル名を取得（非推奨） |
| `get_dynamic_collection_mapping(client, qa_output_dir)` | コレクションとCSVの動的マッピング生成 |
| `get_collection_embedding_params(client, collection_name)` | 埋め込みモデル設定の推論 |

#### コレクション管理関数

| 関数名 | 概要 |
|-------|------|
| `get_collection_stats(client, collection_name)` | コレクション統計情報取得 |
| `get_all_collections(client)` | 全コレクション基本情報取得 |
| `get_all_collections_simple(client)` | 全コレクション一覧取得（シンプル版） |
| `delete_all_collections(client, excluded)` | 全コレクション削除（除外リスト対応） |

#### データ処理・登録関数

| 関数名 | 概要 |
|-------|------|
| `load_csv_for_qdrant(path, required, limit)` | CSVファイル読み込み・前処理 |
| `build_inputs_for_embedding(df, include_answer)` | 埋め込み用テキスト生成 |
| `embed_texts_for_qdrant(texts, model, batch_size)` | テキストのベクトル変換 |
| `create_or_recreate_collection_for_qdrant(client, name, recreate, vector_size, use_sparse)` | コレクション作成/再作成 |
| `build_points_for_qdrant(df, vectors, domain, source_file, sparse_vectors, start_index)` | ポイント構造体生成 |
| `upsert_points_to_qdrant(client, collection, points, batch_size)` | ポイントのアップサート |

#### 検索関数

| 関数名 | 概要 |
|-------|------|
| `embed_query_for_search(query, model, dims)` | 検索クエリのベクトル化 |

#### コレクション統合関数

| 関数名 | 概要 |
|-------|------|
| `scroll_all_points_with_vectors(client, collection_name, batch_size, progress_callback)` | 全ポイント取得（ベクトル付き） |
| `merge_collections(client, source_collections, target_collection, recreate, vector_size, progress_callback)` | 複数コレクションの統合 |

#### ユーティリティ関数

| 関数名 | 概要 |
|-------|------|
| `batched(seq, size)` | イテラブルをバッチ分割するジェネレータ |

---

## 4. クラス・関数 IPO詳細

### 4.1 QdrantHealthChecker クラス

Qdrantサーバーの接続状態を確認するクラス。

#### コンストラクタ: `__init__`

```python
QdrantHealthChecker(debug_mode: bool = False)
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `debug_mode` | bool | False | デバッグモード（詳細なエラー出力） |

| 項目 | 内容 |
|------|------|
| **Input** | `debug_mode: bool = False`（デバッグモード） |
| **Process** | デバッグモードの設定、clientをNoneで初期化 |
| **Output** | QdrantHealthCheckerインスタンス |

#### メソッド: `check_port`

指定ポートが開いているかを確認します。

```python
def check_port(self, host: str, port: int, timeout: float = 2.0) -> bool
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `host` | str | - | ホスト名 |
| `port` | int | - | ポート番号 |
| `timeout` | float | 2.0 | タイムアウト秒数 |

| 項目 | 内容 |
|------|------|
| **Input** | `host: str`, `port: int`, `timeout: float = 2.0` |
| **Process** | ソケット接続でポートの開放状態を確認 |
| **Output** | `bool`: ポートが開いている場合True |

```python
# 使用例
checker = QdrantHealthChecker()
is_open = checker.check_port("localhost", 6333)
print(f"ポート開放状態: {is_open}")
# ポート開放状態: True
```

#### メソッド: `check_qdrant`

Qdrantサーバーへの接続を確認し、統計情報を取得します。

```python
def check_qdrant(self) -> Tuple[bool, str, Optional[Dict]]
```

| 項目 | 内容 |
|------|------|
| **Input** | なし（selfのみ） |
| **Process** | 1. ポートチェック実行<br>2. QdrantClientで接続<br>3. コレクション一覧取得<br>4. メトリクス計算 |
| **Output** | `Tuple[bool, str, Optional[Dict]]`<br>- bool: 接続成功フラグ<br>- str: メッセージ<br>- Dict: `{collection_count, collections, response_time_ms}` |

**戻り値例**:
```python
(
    True,
    "接続成功",
    {
        "collection_count": 3,
        "collections": ["wikipedia_ja", "cc_news", "qa_data"],
        "response_time_ms": 15.2
    }
)
```

```python
# 使用例
checker = QdrantHealthChecker(debug_mode=True)
is_connected, message, metrics = checker.check_qdrant()

if is_connected:
    print(f"接続成功: {metrics['collection_count']}個のコレクション")
else:
    print(f"接続失敗: {message}")
```

---

### 4.2 QdrantDataFetcher クラス

Qdrantからデータを取得するクラス。

#### コンストラクタ: `__init__`

```python
QdrantDataFetcher(client: QdrantClient)
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `client` | QdrantClient | - | Qdrantクライアントインスタンス |

#### メソッド: `fetch_collections`

コレクション一覧をDataFrameとして取得します。

```python
def fetch_collections(self) -> pd.DataFrame
```

| 項目 | 内容 |
|------|------|
| **Input** | なし（selfのみ） |
| **Process** | 1. `get_collections()`で一覧取得<br>2. 各コレクションの詳細情報取得<br>3. DataFrameに変換 |
| **Output** | `pd.DataFrame`: Collection, Vectors Count, Points Count, Indexed Vectors, Status |

**戻り値例**:
```python
#    Collection     Vectors Count  Points Count  Indexed Vectors  Status
# 0  wikipedia_ja   5000           5000          5000             green
# 1  cc_news        3000           3000          3000             green
```

```python
# 使用例
from qdrant_client import QdrantClient

client = QdrantClient(url="http://localhost:6333")
fetcher = QdrantDataFetcher(client)
df = fetcher.fetch_collections()
print(df)
```

#### メソッド: `fetch_collection_points`

コレクションのポイントデータを取得します。

```python
def fetch_collection_points(self, collection_name: str, limit: int = 50) -> pd.DataFrame
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `collection_name` | str | - | コレクション名 |
| `limit` | int | 50 | 取得する最大件数 |

| 項目 | 内容 |
|------|------|
| **Input** | `collection_name: str`, `limit: int = 50` |
| **Process** | 1. `scroll()`でポイント取得<br>2. ペイロードを展開<br>3. 長文は200文字で切り詰め |
| **Output** | `pd.DataFrame`: ID + ペイロードの各フィールド |

**戻り値例**:
```python
#    ID       question                          answer                  source
# 0  abc123   浦沢直樹の代表作は？               MONSTERや20世紀少年... wikipedia.csv
# 1  def456   東京タワーの高さは？               333メートルです...      wikipedia.csv
```

```python
# 使用例
fetcher = QdrantDataFetcher(client)
df = fetcher.fetch_collection_points("wikipedia_ja", limit=100)
print(df.head())
```

#### メソッド: `fetch_collection_info`

コレクションの詳細設定情報を取得します。

```python
def fetch_collection_info(self, collection_name: str) -> Dict[str, Any]
```

| 項目 | 内容 |
|------|------|
| **Input** | `collection_name: str` |
| **Process** | 1. `get_collection()`で設定取得<br>2. ベクトル設定を解析<br>3. Named Vectors対応 |
| **Output** | `Dict`: `{vectors_count, points_count, indexed_vectors, status, config}` |

**戻り値例**:
```python
{
    "vectors_count": 1000,
    "points_count": 1000,
    "indexed_vectors": 1000,
    "status": "green",
    "config": {
        "vector_size": 3072,
        "distance": "Cosine"
    }
}
```

```python
# 使用例
fetcher = QdrantDataFetcher(client)
info = fetcher.fetch_collection_info("wikipedia_ja")
print(f"ベクトル次元: {info['config']['vector_size']}")
# ベクトル次元: 3072
```

#### メソッド: `fetch_collection_source_info`

コレクションのデータソース統計を取得します。

```python
def fetch_collection_source_info(self, collection_name: str, sample_size: int = 200) -> Dict[str, Any]
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `collection_name` | str | - | コレクション名 |
| `sample_size` | int | 200 | サンプリングサイズ |

| 項目 | 内容 |
|------|------|
| **Input** | `collection_name: str`, `sample_size: int = 200` |
| **Process** | 1. サンプルポイントを取得<br>2. source, method, domainを集計<br>3. 全体数を推定 |
| **Output** | `Dict`: `{total_points, sources, sample_size}`<br>sources内: `{sample_count, method, domain, estimated_total, percentage}` |

**戻り値例**:
```python
{
    "total_points": 5000,
    "sources": {
        "wikipedia.csv": {
            "sample_count": 150,
            "method": "auto",
            "domain": "wikipedia",
            "estimated_total": 3750,
            "percentage": 75.0
        },
        "news.csv": {
            "sample_count": 50,
            "method": "auto",
            "domain": "news",
            "estimated_total": 1250,
            "percentage": 25.0
        }
    },
    "sample_size": 200
}
```

```python
# 使用例
fetcher = QdrantDataFetcher(client)
source_info = fetcher.fetch_collection_source_info("wikipedia_ja", sample_size=500)
for source, stats in source_info["sources"].items():
    print(f"{source}: 約{stats['estimated_total']}件 ({stats['percentage']:.1f}%)")
```

---

### 4.3 マッピング関数

#### `map_collection_to_csv`

コレクション名から対応するCSVファイル名を取得します。

> ⚠️ **非推奨**: ペイロードの`source`フィールドを使用することを推奨します。

```python
def map_collection_to_csv(
    collection_name: str,
    qa_output_dir: str = "qa_output"
) -> Optional[str]
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `collection_name` | str | - | コレクション名 |
| `qa_output_dir` | str | "qa_output" | CSVファイルの格納ディレクトリ |

| 項目 | 内容 |
|------|------|
| **Input** | `collection_name: str`, `qa_output_dir: str = "qa_output"` |
| **Process** | 完全一致のみをサポート（`{collection_name}.csv`の存在確認） |
| **Output** | `Optional[str]`: CSVファイル名（見つからない場合はNone） |

**戻り値例**:
```python
"wikipedia.csv"  # 存在する場合
None             # 存在しない場合
```

```python
# 使用例
csv_file = map_collection_to_csv("wikipedia")
if csv_file:
    print(f"対応CSV: {csv_file}")
# 対応CSV: wikipedia.csv
```

#### `get_dynamic_collection_mapping`

Qdrantのコレクション一覧とローカルCSVファイルを動的にマッピングします。

```python
def get_dynamic_collection_mapping(
    client: QdrantClient,
    qa_output_dir: str = "qa_output"
) -> Dict[str, str]
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `client` | QdrantClient | - | Qdrantクライアント |
| `qa_output_dir` | str | "qa_output" | CSVファイルの格納ディレクトリ |

| 項目 | 内容 |
|------|------|
| **Input** | `client: QdrantClient`, `qa_output_dir: str = "qa_output"` |
| **Process** | 1. 全コレクション取得<br>2. 各コレクションのペイロードからsource取得<br>3. フォールバック: 完全一致でCSV検索<br>4. マッピング結果を記録 |
| **Output** | `Dict[str, str]`: `{コレクション名: CSVファイル名}` |

**マッピング優先順位**:
1. ペイロードの`source`フィールド（最優先）
2. 完全一致によるCSVファイル検索（フォールバック）

**戻り値例**:
```python
{
    "wikipedia_ja": "wikipedia.csv",
    "cc_news": "cc_news.csv",
    "qa_data": "qa_data.csv"
}
```

```python
# 使用例
client = QdrantClient(url="http://localhost:6333")
mapping = get_dynamic_collection_mapping(client)
for collection, csv_file in mapping.items():
    print(f"{collection} -> {csv_file}")
# wikipedia_ja -> wikipedia.csv
# cc_news -> cc_news.csv
```

#### `get_collection_embedding_params`

コレクションのベクトル設定から埋め込みモデル設定を推論します。

```python
def get_collection_embedding_params(
    client: QdrantClient,
    collection_name: str
) -> Dict[str, Any]
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `client` | QdrantClient | - | Qdrantクライアント |
| `collection_name` | str | - | コレクション名 |

| 項目 | 内容 |
|------|------|
| **Input** | `client: QdrantClient`, `collection_name: str` |
| **Process** | 1. コレクション情報取得<br>2. ベクトル次元数を確認<br>3. 次元数からモデルを推論 |
| **Output** | `Dict[str, Any]`: `{"model": str, "dims": int}` |

**次元数とモデルの対応表**:

| 次元数 | 推定モデル | プロバイダー |
|--------|-----------|-------------|
| 1536 | text-embedding-3-small | OpenAI |
| 3072 | gemini-embedding-001 | Gemini |
| 768 | gemini-embedding-001 | Gemini |

**戻り値例**:
```python
{
    "model": "gemini-embedding-001",
    "dims": 3072
}
```

```python
# 使用例
params = get_collection_embedding_params(client, "wikipedia_ja")
print(f"モデル: {params['model']}, 次元数: {params['dims']}")
# モデル: gemini-embedding-001, 次元数: 3072
```

---

### 4.4 コレクション管理関数

#### `get_collection_stats`

コレクションの統計情報を取得します。

```python
def get_collection_stats(
    client: QdrantClient,
    collection_name: str
) -> Optional[Dict[str, Any]]
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `client` | QdrantClient | - | Qdrantクライアント |
| `collection_name` | str | - | コレクション名 |

| 項目 | 内容 |
|------|------|
| **Input** | `client: QdrantClient`, `collection_name: str` |
| **Process** | コレクション情報を取得し、統計データを抽出 |
| **Output** | `Optional[Dict[str, Any]]`: 統計情報（存在しない場合はNone） |

**戻り値例**:
```python
{
    "total_points": 1000,
    "vector_config": {
        "default": {"size": 3072, "distance": "Cosine"}
    },
    "status": "green"
}
```

```python
# 使用例
stats = get_collection_stats(client, "wikipedia_ja")
if stats:
    print(f"ポイント数: {stats['total_points']}")
# ポイント数: 1000
```

#### `get_all_collections`

全コレクションの基本情報を取得します。

```python
def get_all_collections(client: QdrantClient) -> List[Dict[str, Any]]
```

| 項目 | 内容 |
|------|------|
| **Input** | `client: QdrantClient` |
| **Process** | 全コレクションを走査し、基本情報を収集 |
| **Output** | `List[Dict[str, Any]]`: コレクション情報のリスト |

**戻り値例**:
```python
[
    {"name": "wikipedia_ja", "points_count": 5000, "status": "green"},
    {"name": "cc_news", "points_count": 3000, "status": "green"}
]
```

```python
# 使用例
collections = get_all_collections(client)
for col in collections:
    print(f"{col['name']}: {col['points_count']}件")
# wikipedia_ja: 5000件
# cc_news: 3000件
```

#### `get_all_collections_simple`

全コレクションの一覧を取得します（シンプル版）。

```python
def get_all_collections_simple(client: QdrantClient) -> List[Dict[str, Any]]
```

| 項目 | 内容 |
|------|------|
| **Input** | `client: QdrantClient` |
| **Process** | CSVマッピングなしで基本情報のみを返す |
| **Output** | `List[Dict[str, Any]]`: コレクション情報のリスト |

**戻り値例**:
```python
[
    {"name": "wikipedia_ja", "points_count": 5000},
    {"name": "cc_news", "points_count": 3000}
]
```

```python
# 使用例
collections = get_all_collections_simple(client)
print(f"コレクション数: {len(collections)}")
# コレクション数: 2
```

#### `delete_all_collections`

全コレクションを削除します。

```python
def delete_all_collections(
    client: QdrantClient,
    excluded: List[str] = None
) -> int
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `client` | QdrantClient | - | Qdrantクライアント |
| `excluded` | List[str] | None | 削除対象から除外するコレクション名のリスト |

| 項目 | 内容 |
|------|------|
| **Input** | `client: QdrantClient`, `excluded: List[str] = None` |
| **Process** | 全コレクションを走査し、除外リスト以外を削除 |
| **Output** | `int`: 削除されたコレクション数 |

**戻り値例**:
```python
3  # 3つのコレクションを削除
```

```python
# 使用例
# 重要なコレクションを除外して削除
deleted_count = delete_all_collections(client, excluded=["production_data"])
print(f"{deleted_count}個のコレクションを削除しました")
# 2個のコレクションを削除しました
```

---

### 4.5 データ処理・登録関数

#### `load_csv_for_qdrant`

CSVファイルをQdrant登録用に読み込みます。

```python
def load_csv_for_qdrant(
    path: str,
    required: tuple = ("question", "answer"),
    limit: int = 0
) -> pd.DataFrame
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `path` | str | - | CSVファイルのパス |
| `required` | tuple | ("question", "answer") | 必須カラム |
| `limit` | int | 0 | 読み込み件数制限（0は無制限） |

| 項目 | 内容 |
|------|------|
| **Input** | `path: str`, `required: tuple = ("question", "answer")`, `limit: int = 0` |
| **Process** | 1. CSV読み込み<br>2. カラム名マッピング（Question→question等）<br>3. 必須カラム確認<br>4. 重複削除・欠損値処理<br>5. limit適用 |
| **Output** | `pd.DataFrame`: 前処理済みデータ |

**カラム名マッピング**:

| 元のカラム名 | マッピング後 |
|-------------|-------------|
| Question | question |
| Response | answer |
| Answer | answer |
| correct_answer | answer |

**戻り値例**:
```python
#    question                    answer
# 0  浦沢直樹の代表作は？          MONSTERや20世紀少年などがあります
# 1  東京タワーの高さは？          333メートルです
```

```python
# 使用例
df = load_csv_for_qdrant("qa_output/wikipedia.csv", limit=1000)
print(f"読み込み件数: {len(df)}")
# 読み込み件数: 1000
```

#### `build_inputs_for_embedding`

DataFrameから埋め込み用テキストを生成します。

```python
def build_inputs_for_embedding(
    df: pd.DataFrame,
    include_answer: bool
) -> List[str]
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `df` | pd.DataFrame | - | 入力データフレーム |
| `include_answer` | bool | - | `True`: question + answer を結合<br>`False`: question のみ |

| 項目 | 内容 |
|------|------|
| **Input** | `df: pd.DataFrame`, `include_answer: bool` |
| **Process** | DataFrameからテキストを抽出し、必要に応じて結合 |
| **Output** | `List[str]`: 埋め込み用テキストのリスト |

**戻り値例**:
```python
# include_answer=True の場合
[
    "浦沢直樹の代表作は？ MONSTERや20世紀少年などがあります",
    "東京タワーの高さは？ 333メートルです"
]

# include_answer=False の場合
[
    "浦沢直樹の代表作は？",
    "東京タワーの高さは？"
]
```

```python
# 使用例
texts = build_inputs_for_embedding(df, include_answer=True)
print(f"テキスト数: {len(texts)}")
print(f"サンプル: {texts[0][:50]}...")
```

#### `embed_texts_for_qdrant`

テキストリストをベクトルに変換します。

```python
def embed_texts_for_qdrant(
    texts: List[str],
    model: str = "gemini-embedding-001",
    batch_size: int = 100
) -> List[List[float]]
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `texts` | List[str] | - | テキストのリスト |
| `model` | str | "gemini-embedding-001" | 使用する埋め込みモデル |
| `batch_size` | int | 100 | バッチサイズ |

| 項目 | 内容 |
|------|------|
| **Input** | `texts: List[str]`, `model: str = "gemini-embedding-001"`, `batch_size: int = 100` |
| **Process** | 1. 空文字列を除外してインデックス記録<br>2. Gemini APIでバッチ処理<br>3. 空文字列位置にダミーベクトル挿入 |
| **Output** | `List[List[float]]`: 3072次元ベクトルのリスト |

**特徴**:
- 空文字列・空白のみのテキストは自動的にダミーベクトル（ゼロベクトル）に置換
- Gemini Embedding APIを使用（3072次元）

**戻り値例**:
```python
[
    [0.0123, -0.0456, 0.0789, ...],  # 3072次元
    [0.0234, -0.0567, 0.0891, ...],  # 3072次元
    ...
]
```

```python
# 使用例
texts = ["浦沢直樹の代表作は？", "東京タワーの高さは？"]
vectors = embed_texts_for_qdrant(texts)
print(f"ベクトル数: {len(vectors)}")
print(f"次元数: {len(vectors[0])}")
# ベクトル数: 2
# 次元数: 3072
```

#### `create_or_recreate_collection_for_qdrant`

コレクションを作成または再作成します。

```python
def create_or_recreate_collection_for_qdrant(
    client: QdrantClient,
    name: str,
    recreate: bool,
    vector_size: int = 3072,
    use_sparse: bool = False
)
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `name` | str | - | コレクション名 |
| `recreate` | bool | - | `True`: 既存を削除して再作成 |
| `vector_size` | int | 3072 | Dense Vectorの次元数 |
| `use_sparse` | bool | False | Hybrid Search（Sparse Vector）の有効化 |

| 項目 | 内容 |
|------|------|
| **Input** | `client: QdrantClient`, `name: str`, `recreate: bool`, `vector_size: int = 3072`, `use_sparse: bool = False` |
| **Process** | 1. Dense Vector設定作成<br>2. Sparse Vector設定作成（use_sparse時）<br>3. recreate=True: 削除→作成<br>4. recreate=False: 存在確認→なければ作成<br>5. domainフィールドにインデックス作成 |
| **Output** | `None`（副作用: コレクション作成） |

**Hybrid Search有効時のベクトル構成**:
- `default`: Dense Vector (Gemini/OpenAI)
- `text-sparse`: Sparse Vector (Splade)

```python
# 使用例（基本）
create_or_recreate_collection_for_qdrant(
    client,
    name="wikipedia_qa",
    recreate=True,
    vector_size=3072
)

# 使用例（Hybrid Search対応）
create_or_recreate_collection_for_qdrant(
    client,
    name="hybrid_collection",
    recreate=True,
    vector_size=3072,
    use_sparse=True
)
```

#### `build_points_for_qdrant`

Qdrantに登録するポイント構造体を生成します。

```python
def build_points_for_qdrant(
    df: pd.DataFrame,
    vectors: List[List[float]],
    domain: str,
    source_file: str,
    sparse_vectors: Optional[List[models.SparseVector]] = None,
    start_index: int = 0
) -> List[models.PointStruct]
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `df` | pd.DataFrame | - | 元データ |
| `vectors` | List[List[float]] | - | Dense Vectorリスト |
| `domain` | str | - | ドメイン名 |
| `source_file` | str | - | ソースファイル名 |
| `sparse_vectors` | Optional[List[SparseVector]] | None | Sparse Vectorリスト |
| `start_index` | int | 0 | 開始インデックス |

| 項目 | 内容 |
|------|------|
| **Input** | `df: pd.DataFrame`, `vectors: List[List[float]]`, `domain: str`, `source_file: str`, `sparse_vectors: Optional[List[SparseVector]]`, `start_index: int = 0` |
| **Process** | 1. 件数の整合性チェック<br>2. 各行をペイロード化<br>3. ユニークIDをハッシュ生成<br>4. Sparse Vector対応時はNamed Vectors構造 |
| **Output** | `List[PointStruct]`: Qdrant登録用ポイント |

**生成されるペイロード構造**:
```python
{
    "domain": "wikipedia",
    "question": "質問テキスト",
    "answer": "回答テキスト",
    "source": "wikipedia.csv",
    "created_at": "2025-01-28T12:00:00+00:00",
    "schema": "qa:v1"
}
```

```python
# 使用例
points = build_points_for_qdrant(
    df,
    vectors,
    domain="wikipedia",
    source_file="wikipedia.csv"
)
print(f"ポイント数: {len(points)}")
# ポイント数: 1000
```

#### `upsert_points_to_qdrant`

ポイントをQdrantにアップサートします。

```python
def upsert_points_to_qdrant(
    client: QdrantClient,
    collection: str,
    points: List[models.PointStruct],
    batch_size: int = 128
) -> int
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `client` | QdrantClient | - | Qdrantクライアント |
| `collection` | str | - | コレクション名 |
| `points` | List[PointStruct] | - | 登録するポイントのリスト |
| `batch_size` | int | 128 | バッチサイズ |

| 項目 | 内容 |
|------|------|
| **Input** | `client: QdrantClient`, `collection: str`, `points: List[PointStruct]`, `batch_size: int = 128` |
| **Process** | ポイントをバッチ単位でQdrantにアップサート |
| **Output** | `int`: アップサートされたポイント数 |

**戻り値例**:
```python
1000  # 1000件のポイントをアップサート
```

```python
# 使用例
count = upsert_points_to_qdrant(client, "wikipedia_qa", points)
print(f"{count}件のポイントを登録しました")
# 1000件のポイントを登録しました
```

---

### 4.6 検索関数

#### `embed_query_for_search`

検索クエリをベクトル化します。

```python
def embed_query_for_search(
    query: str,
    model: str = "gemini-embedding-001",
    dims: Optional[int] = None
) -> List[float]
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `query` | str | - | 検索クエリ文字列 |
| `model` | str | "gemini-embedding-001" | 埋め込みモデル |
| `dims` | Optional[int] | None | 次元数（プロバイダー判定に使用） |

| 項目 | 内容 |
|------|------|
| **Input** | `query: str`, `model: str = "gemini-embedding-001"`, `dims: Optional[int] = None` |
| **Process** | 1. 次元数/モデル名でプロバイダー判定<br>2. Embeddingクライアント作成<br>3. ベクトル生成（Gemini: retrieval_query） |
| **Output** | `List[float]`: クエリベクトル |

**プロバイダー自動選択ロジック**:

| 条件 | 選択されるプロバイダー |
|-----|---------------------|
| dims == 1536 | OpenAI |
| dims == 3072 or 768 | Gemini |
| model に "text-embedding-3" を含む | OpenAI |
| model に "gemini" を含む | Gemini |
| デフォルト | Gemini |

**戻り値例**:
```python
[0.0123, -0.0456, 0.0789, ...]  # 3072次元ベクトル
```

```python
# 使用例
query_vector = embed_query_for_search(
    "浦沢直樹の代表作は？",
    dims=3072
)
print(f"次元数: {len(query_vector)}")
# 次元数: 3072
```

---

### 4.7 コレクション統合関数

#### `scroll_all_points_with_vectors`

コレクションから全ポイントをベクトル付きで取得します。

```python
def scroll_all_points_with_vectors(
    client: QdrantClient,
    collection_name: str,
    batch_size: int = 100,
    progress_callback: Optional[callable] = None
) -> List[models.Record]
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `client` | QdrantClient | - | Qdrantクライアント |
| `collection_name` | str | - | コレクション名 |
| `batch_size` | int | 100 | バッチサイズ |
| `progress_callback` | Optional[callable] | None | コールバック関数 `(取得済み件数, 総件数) -> None` |

| 項目 | 内容 |
|------|------|
| **Input** | `client: QdrantClient`, `collection_name: str`, `batch_size: int = 100`, `progress_callback: Optional[callable] = None` |
| **Process** | scrollメソッドで全ポイントを順次取得 |
| **Output** | `List[models.Record]`: 全ポイントのリスト |

```python
# 使用例
def on_progress(current, total):
    print(f"進捗: {current}/{total}")

points = scroll_all_points_with_vectors(
    client,
    "wikipedia_ja",
    progress_callback=on_progress
)
print(f"取得件数: {len(points)}")
```

#### `merge_collections`

複数コレクションを統合して新コレクションに登録します。

```python
def merge_collections(
    client: QdrantClient,
    source_collections: List[str],
    target_collection: str,
    recreate: bool = True,
    vector_size: int = 3072,
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `client` | QdrantClient | - | Qdrantクライアント |
| `source_collections` | List[str] | - | 統合元コレクションのリスト |
| `target_collection` | str | - | 統合先コレクション名 |
| `recreate` | bool | True | 統合先を再作成するか |
| `vector_size` | int | 3072 | ベクトル次元数 |
| `progress_callback` | Optional[callable] | None | 進捗コールバック |

| 項目 | 内容 |
|------|------|
| **Input** | `client: QdrantClient`, `source_collections: List[str]`, `target_collection: str`, `recreate: bool = True`, `vector_size: int = 3072`, `progress_callback: Optional[callable]` |
| **Process** | 1. 統合先コレクション作成<br>2. 各ソースから全ポイント取得<br>3. IDを再生成（重複回避）<br>4. メタデータ追加（_source_collection等）<br>5. バッチでアップサート |
| **Output** | `Dict`: `{source_collections, target_collection, points_per_collection, total_points, success, error}` |

**統合時のペイロード拡張**:
- `_source_collection`: 元のコレクション名
- `_original_id`: 元のポイントID

**戻り値例**:
```python
{
    "source_collections": ["wikipedia_ja", "cc_news"],
    "target_collection": "merged_all",
    "points_per_collection": {
        "wikipedia_ja": 5000,
        "cc_news": 3000
    },
    "total_points": 8000,
    "success": True,
    "error": None
}
```

```python
# 使用例
result = merge_collections(
    client,
    source_collections=["wikipedia_ja", "cc_news"],
    target_collection="merged_all",
    recreate=True
)

if result["success"]:
    print(f"統合完了: {result['total_points']}件")
else:
    print(f"エラー: {result['error']}")
```

---

### 4.8 ユーティリティ関数

#### `batched`

イテラブルをバッチに分割するジェネレータ。

```python
def batched(seq: Iterable, size: int) -> Generator
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `seq` | Iterable | - | 分割対象のイテラブル |
| `size` | int | - | バッチサイズ |

| 項目 | 内容 |
|------|------|
| **Input** | `seq: Iterable`, `size: int` |
| **Process** | イテラブルを指定サイズのバッチに分割 |
| **Output** | `Generator`: バッチのジェネレータ |

**戻り値例**:
```python
# batched(range(10), 3) の出力
[0, 1, 2]
[3, 4, 5]
[6, 7, 8]
[9]
```

```python
# 使用例
for batch in batched(range(10), 3):
    print(batch)
# [0, 1, 2]
# [3, 4, 5]
# [6, 7, 8]
# [9]
```

---

## 5. 設定・定数

### 5.1 QDRANT_CONFIG

Qdrantサーバーの接続設定を定義する辞書。

```python
QDRANT_CONFIG = {
    "name"                 : "Qdrant",
    "host"                 : "localhost",
    "port"                 : 6333,
    "icon"                 : "🎯",
    "url"                  : "http://localhost:6333",
    "health_check_endpoint": "/collections",
    "docker_image"         : "qdrant/qdrant",
}
```

| キー | デフォルト値 | 説明 |
|-----|-------------|------|
| `name` | "Qdrant" | サービス名 |
| `host` | "localhost" | ホスト名 |
| `port` | 6333 | ポート番号 |
| `url` | "http://localhost:6333" | 完全URL |
| `health_check_endpoint` | "/collections" | ヘルスチェック用エンドポイント |
| `docker_image` | "qdrant/qdrant" | Dockerイメージ名 |

### 5.2 非推奨の定数

以下の定数は後方互換性のために残されていますが、動的マッピング関数の使用を推奨します。

| 定数名 | 状態 | 代替方法 |
|-------|------|---------|
| `COLLECTION_EMBEDDINGS_SEARCH` | ⚠️ 非推奨 | `get_collection_embedding_params()` |
| `COLLECTION_CSV_MAPPING` | ⚠️ 非推奨 | `get_dynamic_collection_mapping()` |

---

## 6. 使用例

### 6.1 基本的なワークフロー

```python
from qdrant_client import QdrantClient
from services.qdrant_service import (
    QdrantHealthChecker,
    QdrantDataFetcher,
    load_csv_for_qdrant,
    build_inputs_for_embedding,
    embed_texts_for_qdrant,
    create_or_recreate_collection_for_qdrant,
    build_points_for_qdrant,
    upsert_points_to_qdrant,
)

# 1. 接続確認
checker = QdrantHealthChecker()
is_connected, msg, metrics = checker.check_qdrant()
if not is_connected:
    raise ConnectionError(f"Qdrant接続失敗: {msg}")

# 2. クライアント作成
client = QdrantClient(url="http://localhost:6333")

# 3. CSVデータ読み込み
df = load_csv_for_qdrant("qa_output/wikipedia.csv", limit=1000)

# 4. 埋め込み生成
texts = build_inputs_for_embedding(df, include_answer=True)
vectors = embed_texts_for_qdrant(texts)

# 5. コレクション作成
create_or_recreate_collection_for_qdrant(
    client,
    name="wikipedia_qa",
    recreate=True,
    vector_size=3072
)

# 6. ポイント構築・登録
points = build_points_for_qdrant(
    df,
    vectors,
    domain="wikipedia",
    source_file="wikipedia.csv"
)
count = upsert_points_to_qdrant(client, "wikipedia_qa", points)
print(f"{count}件のポイントを登録しました")
```

### 6.2 Hybrid Search対応のワークフロー

```python
from services.qdrant_service import (
    create_or_recreate_collection_for_qdrant,
    build_points_for_qdrant,
)
from qdrant_client_wrapper import embed_sparse_texts_unified

# Sparse Vectorを有効にしてコレクション作成
create_or_recreate_collection_for_qdrant(
    client,
    name="hybrid_collection",
    recreate=True,
    vector_size=3072,
    use_sparse=True  # Hybrid Search有効
)

# Sparse Vector生成
sparse_vectors = embed_sparse_texts_unified(texts)

# ポイント構築（Dense + Sparse）
points = build_points_for_qdrant(
    df,
    dense_vectors,
    domain="hybrid",
    source_file="data.csv",
    sparse_vectors=sparse_vectors
)
```

---

## 7. エクスポート

`__init__.py`でエクスポートされる要素：

```python
__all__ = [
    # クラス
    "QdrantHealthChecker",
    "QdrantDataFetcher",
    # コレクション管理
    "get_collection_stats",
    "get_all_collections",
    "delete_all_collections",
    # データ処理・登録
    "load_csv_for_qdrant",
    "build_inputs_for_embedding",
    "embed_texts_for_qdrant",
    "create_or_recreate_collection_for_qdrant",
    "build_points_for_qdrant",
    "upsert_points_to_qdrant",
    # 検索
    "embed_query_for_search",
    # 定数
    "QDRANT_CONFIG",
    "COLLECTION_EMBEDDINGS_SEARCH",  # 非推奨
    "COLLECTION_CSV_MAPPING",         # 非推奨
]
```

---

## 8. 変更履歴

| バージョン | 変更内容 |
|-----------|---------|
| 1.0 | 初版作成 |
| 1.1 | 命名規則依存廃止、動的マッピング導入 |
| 1.2 | Hybrid Search（Sparse Vector）対応 |
| 1.3 | ドキュメント改修: シグネチャ・戻り値例・使用例を追加 |

---

## 付録: 依存関係図

```
qdrant_service.py
    │
    ├──► qdrant-client
    │        └── qdrant_client.QdrantClient
    │        └── qdrant_client.http.models
    │
    ├──► pandas
    │        └── pd.DataFrame
    │
    ├──► tiktoken
    │
    ├──► helper.helper_embedding (内部)
    │        └── create_embedding_client()
    │        └── get_embedding_dimensions()
    │
    └──► qdrant_client_wrapper (内部)
             └── embed_sparse_texts_unified()
             └── create_or_recreate_collection()
```
