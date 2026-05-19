# Agent RAG ツール使用ガイド

---

## 0. 環境の起動・設定

アプリケーションを使用する前に、以下のサービスを起動してください。

### 0.1 Docker コンテナの起動（Qdrant + Redis）

```bash
docker compose up -d
```

起動確認:

```bash
# Qdrant ヘルスチェック
curl http://localhost:6333/health

# Redis 接続確認
docker compose exec redis redis-cli ping
# → PONG が返れば OK
```

### 0.2 環境変数の確認

`.env` ファイルに API キーが設定されていることを確認:

```bash
# 必須
GEMINI_API_KEY=your_gemini_api_key
GOOGLE_API_KEY=your_gemini_api_key

# オプション（Rerank 使用時）
COHERE_API_KEY=your_cohere_api_key
```

### 0.3 Celery ワーカーの起動

Q/A 生成ツールで Celery 並列処理を使う場合に必要です。
チャンク作成ツール（ツール1）は Celery を使用しません。

```bash
# 起動（推奨: concurrency=8 + Flower モニタリング）
./start_celery.sh restart -c 8 --flower

# 状態確認
./start_celery.sh status

# 停止
./start_celery.sh stop
```

Flower（タスクモニタリング UI）: http://localhost:5555

---

## 1. クイックスタート（簡易版コマンド集）

3 つのツールを順に実行することで、テキストデータ → チャンク → Q/A ペア → Qdrant 登録 → Agent 検索 という一連の RAG パイプラインが完成します。

### ツール 1: チャンク作成

```bash
python -m chunking.csv_text_to_chunks_text_csv \
  --input-file OUTPUT/wikipedia_ja_1per.csv \
  --output chunks_output \
  --model gemini-3-flash-preview \
  --workers 8
```

### ツール 2: Q/A ペア作成 + Qdrant 登録

```bash
# Celery 起動後に実行
./start_celery.sh restart -c 8 --flower

python qa_qdrant/make_qa_register_qdrant.py \
  --input-file chunks_output/wikipedia_ja_1per_chunks_XXXXXXXX_XXXXXX.csv \
  --collection wikipedia_ja_1per \
  --use-celery \
  --concurrency 8 \
  --recreate
```

### ツール 3: Agent 検索（Web UI）

```bash
streamlit run agent_rag.py --server.port 8501
```

ブラウザで http://localhost:8501 にアクセス。

---

## 2. ツール詳細: チャンク作成

**スクリプト:** `chunking/csv_text_to_chunks_text_csv.py`

LLM ベースのセマンティックチャンキングツールです。テキストを意味的なまとまりに 3 段階で分割します。Celery は使用しません（asyncio による並列処理）。

### 2.1 処理フロー

```
入力テキスト/CSV
  ↓ Step 1: 階層構造化（段落分割）
  ↓ Step 2: 意味的チャンキング
  ↓ Step 3: 文脈連続性チェック（結合/分離判定）
チャンク CSV（2 ファイル出力）
```

### 2.2 実行コマンド

CSV ファイルからチャンク作成:

```bash
python -m chunking.csv_text_to_chunks_text_csv \
  --input-file OUTPUT/cc_news_1per.csv \
  --output chunks_output \
  --model gemini-3-flash-preview \
  --workers 8 \
  --block-size 500
```

テキストファイルからチャンク作成:

```bash
python -m chunking.csv_text_to_chunks_text_csv \
  --input-file ./data/document.txt \
  --output chunks_output \
  --model gemini-3-flash-preview \
  --workers 8
```

### 2.3 オプション一覧

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `--input-file` | （必須） | 入力ファイル（.txt / .csv） |
| `--output` | `chunks_output` | 出力ディレクトリ |
| `--model` | `gemini-3-flash-preview` | 使用する LLM モデル |
| `--workers` | `8` | 並列ワーカー数（asyncio） |
| `--block-size` | `1000` | ブロックサイズ（文字数）。大きすぎると MAX_TOKENS エラー |
| `--text-column` | 自動検出 | CSV のテキストカラム名 |
| `--max-rows` | 全行 | 最大処理行数（CSV 用） |
| `--combine-rows` | `false` | CSV 全行を 1 テキストに結合 |
| `--resume` | なし | チェックポイントから再開するジョブ ID |
| `--verbose` | `false` | 詳細ログ出力 |

### 2.4 出力ファイル

2 つの CSV が自動生成されます:

| ファイル | 内容 |
|---------|------|
| `{入力名}_chunks_{日時}.csv` | メタデータ付き（chunk_id, text, tokens, sentence_count 等） |
| `{入力名}_chunks_{日時}_simple.csv` | シンプル版（Text カラムのみ） ← ツール 2 の入力に使用可能 |

### 2.5 CSV テキストカラムの自動検出

`--text-column` を省略した場合、以下の順序でカラムを自動検出します: `text`, `Text`, `content`, `Content`, `Combined_Text`, `body`, `Body`, `document`, `answer`。いずれもない場合は最初のカラムを使用します。

### 2.6 注意事項

Gemini API のレート制限に引っかかる場合は、`--block-size` を小さく（例: 500）、`--workers` を減らして（例: 4）調整してください。

---

## 3. ツール詳細: Q/A ペア作成 + Qdrant 登録

**スクリプト:** `qa_qdrant/make_qa_register_qdrant.py`

チャンク CSV から Q/A ペアを LLM で自動生成し、Qdrant に登録する統合ツールです。

### 3.1 処理フロー

```
入力（チャンク CSV / テキスト / Q&A CSV）
  ↓ Phase 1: Q/A ペア生成（LLM + Celery 並列）
  ↓   ・スマート生成: LLM がチャンクごとに最適な Q/A 数を決定（0〜5 個）
  ↓   ・従来方式: トークン数ベースで固定 Q/A 数（2〜8 個）
  ↓ Phase 2: Qdrant 登録
  ↓   ・Embedding 生成（gemini-embedding-001, 3072 次元）
  ↓   ・コレクション作成 + バッチアップサート
Q/A ペア CSV + Qdrant 登録完了
```

### 3.2 実行コマンド

基本（Celery 使用 + コレクション再作成）:

```bash
./start_celery.sh restart -c 8 --flower

python qa_qdrant/make_qa_register_qdrant.py \
  --input-file chunks_output/cc_news_1per_chunks.csv \
  --collection cc_news_1per \
  --use-celery \
  --concurrency 8 \
  --recreate
```

Celery を使わない同期処理:

```bash
python qa_qdrant/make_qa_register_qdrant.py \
  --input-file chunks_output/cc_news_1per_chunks.csv \
  --collection cc_news_1per \
  --recreate
```

前処理済み CSV の行結合モード:

```bash
python qa_qdrant/make_qa_register_qdrant.py \
  --input-file OUTPUT/cc_news_5per.csv \
  --collection cc_news_5per \
  --use-celery \
  --concurrency 4 \
  --text-column text \
  --combine-rows \
  --block-size 400 \
  --recreate
```

従来方式の Q/A 生成（スマート生成を無効化）:

```bash
python qa_qdrant/make_qa_register_qdrant.py \
  --input-file chunks_output/cc_news_5per_chunks.csv \
  --collection cc_news_5per \
  --use-celery \
  --no-smart-generation \
  --recreate
```

### 3.3 オプション一覧

**入力ソース（いずれか 1 つ必須）:**

| オプション | 説明 |
|-----------|------|
| `--input-file` | 入力ファイルパス（.txt / .csv） |
| `--dataset` | 事前定義データセット名（wikipedia_ja, cc_news 等） |

**CSV 処理（`--input-file` が CSV の場合）:**

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `--text-column` | `text` | テキストカラム名 |
| `--combine-rows` | `false` | 複数行を結合してチャンク化 |
| `--block-size` | `400` | 結合する行数 |

**Q/A 生成:**

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `--model` | `gemini-3-flash-preview` | LLM モデル |
| `--use-celery` | `false` | Celery 並列処理を使用 |
| `-c`, `--concurrency` | `8` | 並列タスク数 |
| `--batch-chunks` | `3` | 1 API 呼び出しで処理するチャンク数 |
| `--use-smart-generation` | `true`（デフォルト有効） | LLM による動的 Q/A 数決定 |
| `--no-smart-generation` | — | 従来方式（トークン数ベース）に切替 |
| `--max-docs` | 全件 | 処理する最大文書数 |

**Qdrant 登録:**

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `--collection` | （必須） | Qdrant コレクション名 |
| `--recreate` | `false` | コレクションを再作成（既存データ削除） |
| `--batch-size` | `100` | Embedding バッチサイズ |
| `--provider` | `gemini` | Embedding プロバイダー |

**出力:**

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `--output` | `qa_output/pipeline` | Q/A ペア CSV 出力ディレクトリ |
| `--ui-output` | `qa_output` | UI 用正規化 CSV 出力ディレクトリ |

### 3.4 入力 CSV の自動判定

入力 CSV のカラム構成に応じて処理が自動切替されます:

| CSV のカラム | 動作 |
|------------|------|
| `question` + `answer` あり | Q/A 生成をスキップ → 直接 Qdrant 登録 |
| `text`（または `Combined_Text`）あり | Q/A 生成 → Qdrant 登録 |
| 上記いずれもなし | エラー終了 |

### 3.5 出力ファイル

| 出力先 | 内容 |
|-------|------|
| `qa_output/pipeline/` | Q/A ペア CSV（question, answer カラム） |
| `qa_output/` | UI 用正規化 CSV（日時サフィックス除去済み） |

### 3.6 Celery 並列設定の推奨値

| マシン | `--concurrency` | `start_celery.sh -c` |
|-------|-----------------|----------------------|
| M2 MacBook Air (8 vCPU) | `8` | `8` |
| 軽量モード | `4` | `4` |

`--concurrency` と `start_celery.sh -c` は同じ値に揃えてください。

---

## 4. ツール詳細: Agent 検索（Web UI）

**スクリプト:** `agent_rag.py`

Streamlit ベースの Web UI アプリケーションです。Qdrant に登録済みの Q/A データに対して、ReAct + Reflection パターンの自律型 Agent 検索を実行できます。

### 4.1 起動コマンド

```bash
streamlit run agent_rag.py --server.port 8501
```

ブラウザで http://localhost:8501 にアクセスします。

### 4.2 メニュー構成

| メニュー | 機能 |
|---------|------|
| 📖 説明 | システム全体の説明ページ |
| 🔎 Qdrant 検索 | Qdrant に直接クエリを実行してベクトル検索 |
| 🤖 Agent（ReAct+Reflection） | ReAct + Reflection パターンのエージェント対話 |
| 🧠 Agent（Plan+Executor） | Plan+Executor パターンの自律型エージェント |
| 📊 未回答ログ | Agent が回答できなかった質問のログ閲覧 |
| 📄 RAG データ作成 | RAG データ作成（実装予定） |
| 🗄️ Qdrant の CRUD | Qdrant のデータ管理（実装予定） |

### 4.3 Agent（ReAct+Reflection）の動作

エージェントは以下の 2 フェーズで質問に回答します:

**Phase 1 — ReAct ループ:**
ユーザーの質問に対して Thought → Action（ツール呼び出し） → Observation のサイクルを繰り返し、回答案を作成します。エージェントは全 Qdrant コレクションを並列検索し、最適な結果を選択します。

**Phase 2 — Reflection:**
回答案を正確性・適切性・スタイルの観点で自己評価し、必要に応じて修正した最終回答を出力します。

### 4.4 検索の仕組み

エージェントは以下のツールを内部的に使用します:

| ツール | 用途 |
|-------|------|
| `search_rag_knowledge_base` | 全コレクション並列検索 + コサイン類似度フィルタ |
| `list_rag_collections` | 利用可能なコレクション一覧取得 |

検索時には Hybrid Search（Dense + Sparse ベクトル）を使用し、コサイン類似度 ≥ 0.7 の結果のみを採用します。

### 4.5 前提条件

Agent 検索を利用するには、以下が必要です:

- Docker コンテナ（Qdrant + Redis）が起動していること
- `.env` に `GEMINI_API_KEY` が設定されていること
- Qdrant に 1 つ以上のコレクションが登録されていること（ツール 2 で登録）

---

## 5. パイプライン全体の実行例

Wikipedia 日本語データを例にした、データ準備から検索までの一連の流れです。

```bash
# === Step 0: 環境起動 ===
docker compose up -d
./start_celery.sh restart -c 8 --flower

# === Step 1: チャンク作成 ===
python -m chunking.csv_text_to_chunks_text_csv \
  --input-file OUTPUT/wikipedia_ja_1per.csv \
  --output chunks_output \
  --model gemini-3-flash-preview \
  --workers 8

# === Step 2: Q/A 生成 + Qdrant 登録 ===
# ※ Step 1 で生成されたファイル名を指定
python qa_qdrant/make_qa_register_qdrant.py \
  --input-file chunks_output/wikipedia_ja_1per_chunks_XXXXXXXX_XXXXXX.csv \
  --collection wikipedia_ja_1per \
  --use-celery \
  --concurrency 8 \
  --recreate

# === Step 3: Agent 検索 ===
streamlit run agent_rag.py --server.port 8501

# === 終了時 ===
# Ctrl+C で Streamlit 停止
./start_celery.sh stop
docker compose down
```

---

## 6. ポート一覧

| サービス | ポート | 用途 |
|---------|-------|------|
| Streamlit | 8501 | Agent RAG Web UI |
| Qdrant | 6333 | ベクトル DB REST API |
| Redis | 6379 | Celery ブローカー / 結果保存 |
| Flower | 5555 | Celery タスクモニタリング |
