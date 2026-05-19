# qdrant_service.py - Qdrant操作サービス ドキュメント

## 概要

`qdrant_service.py`は、Qdrantベクトルデータベースとの通信・操作を一元管理するサービスモジュールです。RAG（Retrieval-Augmented Generation）システムにおけるベクトル検索の基盤を提供します。

### 主な機能

- **ヘルスチェック**: Qdrantサーバーの接続状態監視
- **データ取得**: コレクションからのデータ取得・分析
- **コレクション管理**: CRUD操作（作成・読取・更新・削除）
- **埋め込み生成・登録**: テキストのベクトル化とQdrantへの登録
- **検索機能**: クエリベクトルによる類似検索

---

## 設定・定数

### QDRANT_CONFIG

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

### 非推奨の定数

以下の定数は後方互換性のために残されていますが、動的マッピング関数の使用を推奨します。

| 定数名 | 説明 | 代替方法 |
|--------|------|----------|
| `COLLECTION_EMBEDDINGS_SEARCH` | コレクション固有の埋め込み設定 | `get_collection_embedding_params()` |
| `COLLECTION_CSV_MAPPING` | コレクションとCSVファイルの対応表 | `get_dynamic_collection_mapping()` |

---

## クラス

### QdrantHealthChecker

Qdrantサーバーの接続状態を確認するクラス。

#### コンストラクタ

```python
QdrantHealthChecker(debug_mode: bool = False)
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `debug_mode` | bool | False | デバッグモード（詳細なエラー出力） |

#### メソッド

##### check_port(host, port, timeout)

指定ポートが開いているかを確認します。

```python
def check_port(self, host: str, port: int, timeout: float = 2.0) -> bool
```

**戻り値**: ポートが開いている場合は`True`

##### check_qdrant()

Qdrantサーバーへの接続を確認し、統計情報を取得します。

```python
def check_qdrant(self) -> Tuple[bool, str, Optional[Dict]]
```

**戻り値**: `(接続成功フラグ, メッセージ, メトリクス辞書)`

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

### QdrantDataFetcher

Qdrantからデータを取得するクラス。

#### コンストラクタ

```python
QdrantDataFetcher(client: QdrantClient)
```

#### メソッド

##### fetch_collections()

コレクション一覧をDataFrameとして取得します。

```python
def fetch_collections(self) -> pd.DataFrame
```

**戻り値**: コレクション情報を含むDataFrame

| カラム名 | 説明 |
|----------|------|
| Collection | コレクション名 |
| Vectors Count | ベクトル数 |
| Points Count | ポイント数 |
| Indexed Vectors | インデックス済みベクトル数 |
| Status | ステータス |

##### fetch_collection_points(collection_name, limit)

コレクションのポイントデータを取得します。

```python
def fetch_collection_points(self, collection_name: str, limit: int = 50) -> pd.DataFrame
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|------|-----------|------|
| `collection_name` | str | - | コレクション名 |
| `limit` | int | 50 | 取得する最大件数 |

##### fetch_collection_info(collection_name)

コレクションの詳細設定情報を取得します。

```python
def fetch_collection_info(self, collection_name: str) -> Dict[str, Any]
```

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

##### fetch_collection_source_info(collection_name, sample_size)

コレクションのデータソース統計を取得します。

```python
def fetch_collection_source_info(self, collection_name: str, sample_size: int = 200) -> Dict[str, Any]
```

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
        }
    },
    "sample_size": 200
}
```

---

## 関数

### マッピング関数

#### map_collection_to_csv(collection_name, qa_output_dir)

コレクション名から対応するCSVファイル名を取得します。

```python
def map_collection_to_csv(
    collection_name: str,
    qa_output_dir: str = "qa_output"
) -> Optional[str]
```

> ⚠️ **非推奨**: ペイロードの`source`フィールドを使用することを推奨します。

**動作**: 完全一致のみをサポート（`{collection_name}.csv`の存在確認）

#### get_dynamic_collection_mapping(client, qa_output_dir)

Qdrantのコレクション一覧とローカルCSVファイルを動的にマッピングします。

```python
def get_dynamic_collection_mapping(
    client: QdrantClient,
    qa_output_dir: str = "qa_output"
) -> Dict[str, str]
```

**マッピング優先順位**:
1. ペイロードの`source`フィールド（最優先）
2. 完全一致によるCSVファイル検索（フォールバック）

```python
# 使用例
client = QdrantClient(url="http://localhost:6333")
mapping = get_dynamic_collection_mapping(client)
# {"wikipedia_ja": "wikipedia.csv", "cc_news": "cc_news.csv"}
```

#### get_collection_embedding_params(client, collection_name)

コレクションのベクトル設定から埋め込みモデル設定を推論します。

```python
def get_collection_embedding_params(
    client: QdrantClient,
    collection_name: str
) -> Dict[str, Any]
```

**戻り値**: `{"model": str, "dims": int}`

| 次元数 | 推定モデル |
|--------|-----------|
| 1536 | text-embedding-3-small |
| 3072 | gemini-embedding-001 |
| 768 | gemini-embedding-001 |

---

### コレクション管理関数

#### get_collection_stats(client, collection_name)

コレクションの統計情報を取得します。

```python
def get_collection_stats(
    client: QdrantClient,
    collection_name: str
) -> Optional[Dict[str, Any]]
```

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

#### get_all_collections(client)

全コレクションの基本情報を取得します。

```python
def get_all_collections(client: QdrantClient) -> List[Dict[str, Any]]
```

**戻り値例**:
```python
[
    {"name": "wikipedia_ja", "points_count": 5000, "status": "green"},
    {"name": "cc_news", "points_count": 3000, "status": "green"}
]
```

#### get_all_collections_simple(client)

全コレクションの一覧を取得します（シンプル版）。

```python
def get_all_collections_simple(client: QdrantClient) -> List[Dict[str, Any]]
```

CSVマッピングなしで基本情報のみを返します。

#### delete_all_collections(client, excluded)

全コレクションを削除します。

```python
def delete_all_collections(
    client: QdrantClient,
    excluded: List[str] = None
) -> int
```

| パラメータ | 型 | 説明 |
|------------|------|------|
| `excluded` | List[str] | 削除対象から除外するコレクション名のリスト |

**戻り値**: 削除されたコレクション数

---

### データ処理・登録関数

#### load_csv_for_qdrant(path, required, limit)

CSVファイルをQdrant登録用に読み込みます。

```python
def load_csv_for_qdrant(
    path: str,
    required: tuple = ("question", "answer"),
    limit: int = 0
) -> pd.DataFrame
```

**カラム名の自動マッピング**:
| 元のカラム名 | マッピング後 |
|--------------|-------------|
| Question | question |
| Response | answer |
| Answer | answer |
| correct_answer | answer |

#### build_inputs_for_embedding(df, include_answer)

DataFrameから埋め込み用テキストを生成します。

```python
def build_inputs_for_embedding(
    df: pd.DataFrame,
    include_answer: bool
) -> List[str]
```

| パラメータ | 説明 |
|------------|------|
| `include_answer` | `True`: question + answer を結合<br>`False`: question のみ |

#### embed_texts_for_qdrant(texts, model, batch_size)

テキストリストをベクトルに変換します。

```python
def embed_texts_for_qdrant(
    texts: List[str],
    model: str = "gemini-embedding-001",
    batch_size: int = 100
) -> List[List[float]]
```

**特徴**:
- 空文字列・空白のみのテキストは自動的にダミーベクトル（ゼロベクトル）に置換
- Gemini Embedding APIを使用（3072次元）

#### create_or_recreate_collection_for_qdrant(client, name, recreate, vector_size, use_sparse)

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

**Hybrid Search有効時のベクトル構成**:
- `default`: Dense Vector (Gemini/OpenAI)
- `text-sparse`: Sparse Vector (Splade)

#### build_points_for_qdrant(df, vectors, domain, source_file, sparse_vectors, start_index)

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

#### upsert_points_to_qdrant(client, collection, points, batch_size)

ポイントをQdrantにアップサートします。

```python
def upsert_points_to_qdrant(
    client: QdrantClient,
    collection: str,
    points: List[models.PointStruct],
    batch_size: int = 128
) -> int
```

**戻り値**: アップサートされたポイント数

---

### 検索関数

#### embed_query_for_search(query, model, dims)

検索クエリをベクトル化します。

```python
def embed_query_for_search(
    query: str,
    model: str = "gemini-embedding-001",
    dims: Optional[int] = None
) -> List[float]
```

**プロバイダー自動選択ロジック**:
| 条件 | 選択されるプロバイダー |
|------|----------------------|
| dims == 1536 | OpenAI |
| dims == 3072 or 768 | Gemini |
| model に "text-embedding-3" を含む | OpenAI |
| model に "gemini" を含む | Gemini |
| デフォルト | Gemini |

```python
# 使用例
query_vector = embed_query_for_search(
    "浦沢直樹の代表作は？",
    dims=3072
)
# -> 3072次元のベクトルを返す
```

---

### コレクション統合関数

#### scroll_all_points_with_vectors(client, collection_name, batch_size, progress_callback)

コレクションから全ポイントをベクトル付きで取得します。

```python
def scroll_all_points_with_vectors(
    client: QdrantClient,
    collection_name: str,
    batch_size: int = 100,
    progress_callback: Optional[callable] = None
) -> List[models.Record]
```

| パラメータ | 説明 |
|------------|------|
| `progress_callback` | コールバック関数 `(取得済み件数, 総件数) -> None` |

#### merge_collections(client, source_collections, target_collection, recreate, vector_size, progress_callback)

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

**統合時のペイロード拡張**:
- `_source_collection`: 元のコレクション名
- `_original_id`: 元のポイントID

---

## ユーティリティ関数

#### batched(seq, size)

イテラブルをバッチに分割するジェネレータ。

```python
def batched(seq: Iterable, size: int) -> Generator
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

## 使用例

### 基本的なワークフロー

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

### Hybrid Search対応のワークフロー

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

## 依存関係

### 外部ライブラリ

| ライブラリ | 用途 |
|-----------|------|
| qdrant-client | Qdrant Python クライアント |
| pandas | データフレーム操作 |
| tiktoken | トークンカウント |

### 内部モジュール

| モジュール | 用途 |
|-----------|------|
| helper.helper_embedding | 埋め込みクライアント作成 |
| qdrant_client_wrapper | Sparse Vector生成、コレクション作成ラッパー |

---

## エクスポート

`__init__.py` でエクスポートされる要素:

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

## 変更履歴

| バージョン | 変更内容 |
|-----------|---------|
| 1.0 | 初版作成 |
| 1.1 | 命名規則依存廃止、動的マッピング導入 |
| 1.2 | Hybrid Search（Sparse Vector）対応 |
