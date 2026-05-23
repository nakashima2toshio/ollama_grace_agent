# セットアップ・インストール手順書

**プロジェクト**: ollama_grace_agent（GRACE Agent + RAG システム）  
**LLM**: Ollama（ローカル実行）デフォルトモデル: `gemma4:e4b`  
**作成日**: 2026-05-21

---

## 目次

1. [システム構成・概要](#1-システム構成概要)
2. [動作環境・前提条件](#2-動作環境前提条件)
3. [必要ソフトウェアのインストール](#3-必要ソフトウェアのインストール)
   - [3.1 Homebrew（macOS）](#31-homebrewmacos)
   - [3.2 Python 3.13](#32-python-313)
   - [3.3 uv（パッケージマネージャー）](#33-uvパッケージマネージャー)
   - [3.4 Docker Desktop](#34-docker-desktop)
   - [3.5 Ollama（ローカル LLM サーバー）](#35-ollamaローカル-llm-サーバー)
   - [3.6 MeCab（オプション）](#36-mecabオプション)
4. [プロジェクトのセットアップ](#4-プロジェクトのセットアップ)
   - [4.1 リポジトリのクローン](#41-リポジトリのクローン)
   - [4.2 Python 依存パッケージのインストール](#42-python-依存パッケージのインストール)
   - [4.3 環境変数の設定（.env）](#43-環境変数の設定env)
5. [インフラサービスの起動](#5-インフラサービスの起動)
   - [5.1 Ollama サーバーの起動と確認](#51-ollama-サーバーの起動と確認)
   - [5.2 Docker サービス（Qdrant + Redis）](#52-docker-サービスqdrant--redis)
   - [5.3 Celery ワーカーの起動](#53-celery-ワーカーの起動)
6. [初回データ登録](#6-初回データ登録)
7. [アプリケーションの起動・停止](#7-アプリケーションの起動停止)
8. [ポート一覧](#8-ポート一覧)
9. [動作確認チェックリスト](#9-動作確認チェックリスト)
10. [トラブルシューティング](#10-トラブルシューティング)
11. [主要ファイル構成](#11-主要ファイル構成)
12. [参考ドキュメント](#12-参考ドキュメント)

---

## 1. システム構成・概要

### アーキテクチャ図

```mermaid
flowchart TB
    USER["ユーザー（ブラウザ）\nhttp://localhost:8501"]

    subgraph APP["Streamlit アプリ"]
        STREAMLIT["agent_rag.py"]
    end

    subgraph LOCAL["ローカルサービス"]
        OLLAMA["Ollama\nLLM / Embedding\n:11434"]
        QDRANT["Qdrant\nVector DB\n:6333"]
        REDIS["Redis\nCelery Broker\n:6379"]
    end

    subgraph BG["バックグラウンド"]
        CELERY["Celery Workers\nQ/A生成・登録"]
    end

    USER --> STREAMLIT
    STREAMLIT --> OLLAMA
    STREAMLIT --> QDRANT
    STREAMLIT --> REDIS
    REDIS --> CELERY
    CELERY --> OLLAMA
```

### コンポーネント概要

| コンポーネント | 役割 | 実行場所 |
|--------------|------|---------|
| Streamlit | Web UI（agent_rag.py） | Python プロセス |
| Ollama | LLM・Embedding サーバー（gemma4:e4b） | ローカルプロセス |
| Qdrant | ベクトル DB（RAG 検索） | Docker コンテナ |
| Redis | Celery タスクブローカー・結果保存 | Docker コンテナ |
| Celery | Q/A 生成などのバックグラウンドタスク | Python プロセス |

---

## 2. 動作環境・前提条件

### 対応 OS

| OS | 対応状況 |
|----|---------|
| macOS（Apple Silicon M1/M2/M3） | ✅ 推奨 |
| macOS（Intel） | ✅ 動作可 |
| Linux（Ubuntu 22.04+） | ✅ 動作可 |
| Windows（WSL2） | ⚠️ 未確認 |

### ハードウェア要件

| リソース | 最小 | 推奨 |
|---------|------|------|
| CPU | 4 コア | 8 コア以上 |
| RAM | 8 GB | 16 GB 以上 |
| ディスク空き | 10 GB | 20 GB 以上 |

> gemma4:e4b モデルは約 3.3 GB。nomic-embed-text は約 274 MB。

### 必須ソフトウェア一覧

| ソフトウェア | バージョン | 用途 |
|------------|----------|------|
| Python | **3.13.x**（必須） | アプリ実行環境 |
| uv | 最新版 | パッケージ管理 |
| Docker Desktop | 最新版 | Qdrant / Redis |
| Ollama | 最新版 | ローカル LLM |
| Git | 2.x 以上 | リポジトリ操作 |

---

## 3. 必要ソフトウェアのインストール

### 3.1 Homebrew（macOS）

macOS の場合、パッケージ管理に Homebrew を使います。

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

インストール確認:
```bash
brew --version   # → Homebrew 4.x.x
```

> Linux の場合は `apt` / `dnf` など OS 標準のパッケージマネージャーを使用してください。

---

### 3.2 Python 3.13

本プロジェクトは **Python 3.13 専用**（`pyproject.toml` の `requires-python = ">=3.13,<3.14"`）。

#### macOS（Homebrew）

```bash
brew install python@3.13
python3.13 --version   # → Python 3.13.x
```

#### pyenv を使う場合（macOS / Linux）

```bash
brew install pyenv            # macOS
# または: curl https://pyenv.run | bash   # Linux

pyenv install 3.13.3
pyenv local 3.13.3
python --version   # → Python 3.13.3
```

#### Linux（Ubuntu）

```bash
sudo apt update
sudo apt install -y python3.13 python3.13-venv python3.13-dev
```

---

### 3.3 uv（パッケージマネージャー）

`pip` の代わりに **`uv`** を使います。依存解決が高速で、`uv.lock` による完全再現が可能です。

```bash
# 公式インストーラー（macOS / Linux）
curl -LsSf https://astral.sh/uv/install.sh | sh

# または Homebrew（macOS）
brew install uv
```

インストール後、シェルを再起動（または `source ~/.zshrc`）してから確認:

```bash
uv --version   # → uv 0.x.x
```

---

### 3.4 Docker Desktop

Qdrant と Redis を Docker コンテナで起動します。

#### macOS

[Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/) からダウンロードしインストール。  
**Apple Silicon（M1/M2/M3）の場合は ARM 版**を選択すること。

Docker Desktop 起動後、**Settings → Resources** で推奨値を設定:

| リソース | 推奨値 |
|---------|--------|
| CPUs | 4 以上 |
| Memory | 8 GB 以上 |
| Swap | 1 GB |

#### Linux

```bash
# Ubuntu の場合
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

インストール確認:
```bash
docker --version          # → Docker version 27.x.x
docker compose version    # → Docker Compose version v2.x.x
```

---

### 3.5 Ollama（ローカル LLM サーバー）

クラウド API キー不要でローカルで LLM を実行します。

#### インストール

```bash
# macOS（Homebrew）
brew install ollama

# macOS / Linux（公式スクリプト）
curl -fsSL https://ollama.com/install.sh | sh
```

#### インストール確認

```bash
ollama --version   # → ollama version 0.x.x
```

#### 必要モデルのダウンロード

```bash
# テキスト生成モデル（デフォルト・推奨・約 3.3 GB）
ollama pull gemma4:e4b

# テキスト生成モデル（llama3.2・約 2 GB）
ollama pull llama3.2

# Embedding モデル（約 274 MB）
ollama pull nomic-embed-text
```

ダウンロード確認:
```bash
ollama list
# NAME                  ID            SIZE    MODIFIED
# gemma4:e4b            ...           3.3 GB  ...
# llama3.2:latest       ...           2.0 GB  ...
# nomic-embed-text:...  ...           274 MB  ...
```

#### Ollama サーバーの起動

```bash
# フォアグラウンド起動（別ターミナルで常時起動しておく）
ollama serve
```

> macOS の場合、メニューバーの Ollama アイコンからも起動できます。

---

### 3.6 MeCab（オプション）

日本語形態素解析（キーワード抽出）に使用。なくてもアプリは動作します。

```bash
# macOS
brew install mecab mecab-ipadic

# Linux（Ubuntu）
sudo apt install -y mecab libmecab-dev mecab-ipadic-utf8
```

Python バインディングは `uv sync` で自動インストールされます（`mecab-python3`）。

---

## 4. プロジェクトのセットアップ

### 4.1 リポジトリのクローン

```bash
git clone https://github.com/nakashima2toshio/ollama_grace_agent.git
cd ollama_grace_agent
```

開発ブランチへ切り替え（最新の修正を含む場合）:
```bash
git checkout claude/ollama-grace-agent-YKCPL
```

---

### 4.2 Python 依存パッケージのインストール

```bash
# 本番依存のみ（推奨）
uv sync

# 開発用依存（ruff, pytest）も含める
uv sync --all-groups
```

> `uv sync` は `pyproject.toml` と `uv.lock` を読み込み、Python 仮想環境（`.venv/`）を自動作成してパッケージをインストールします。

インストール確認:
```bash
uv run python -c "import streamlit, qdrant_client, openai; print('OK')"
# → OK
```

主要パッケージバージョン（`pyproject.toml` より）:

| パッケージ | バージョン | 用途 |
|----------|----------|------|
| openai | 1.100.2 | Ollama OpenAI 互換クライアント |
| anthropic | >=0.40.0 | Claude API（オプション） |
| streamlit | 1.48.1 | Web UI |
| qdrant-client | 1.15.1 | ベクトル DB クライアント |
| celery | 5.5.3 | タスクキュー |
| redis | 6.2.0 | Celery ブローカー |
| pydantic | 2.11.7 | データバリデーション |
| fastembed | >=0.8.0 | ローカル Embedding |

---

### 4.3 環境変数の設定（`.env`）

プロジェクトルートに `.env` ファイルを作成します。

```bash
touch .env
```

`.env` の設定例（必要なものだけ設定）:

```dotenv
# ============================================================
# Ollama（ローカル実行のため通常設定不要）
# リモート Ollama サーバーを使う場合のみ設定
# ============================================================
# OLLAMA_BASE_URL=http://localhost:11434/v1

# ============================================================
# Qdrant（Docker で起動する場合はデフォルトで動作）
# ============================================================
# QDRANT_HOST=localhost
# QDRANT_PORT=6333

# ============================================================
# Redis / Celery（Docker で起動する場合はデフォルトで動作）
# ============================================================
# CELERY_BROKER_URL=redis://localhost:6379/0
# CELERY_RESULT_BACKEND=redis://localhost:6379/0

# ============================================================
# 外部 API（オプション）
# ============================================================
# OpenAI Embedding を使用する場合
# OPENAI_API_KEY=sk-...

# Anthropic Claude を使用する場合
# ANTHROPIC_API_KEY=sk-ant-...

# Cohere Rerank を使用する場合
# COHERE_API_KEY=...

# PostgreSQL を使用する場合
# PG_CONN_STR=postgresql://user:password@localhost:5432/dbname
```

> **Ollama をローカルで使う通常運用では、`.env` への設定は不要です。**

---

## 5. インフラサービスの起動

### 5.1 Ollama サーバーの起動と確認

```bash
# 別ターミナルで起動（常時起動）
ollama serve
```

接続確認:
```bash
curl http://localhost:11434/api/tags
# → {"models":[{"name":"gemma4:e4b",...},...]}
```

---

### 5.2 Docker サービス（Qdrant + Redis）

#### 起動

```bash
docker compose -f docker-compose/docker-compose.yml up -d
```

#### 状態確認

```bash
docker compose -f docker-compose/docker-compose.yml ps
```

期待される出力:
```
NAME      IMAGE                  STATUS
qdrant    qdrant/qdrant:latest   Up (healthy)
redis     redis:7-alpine         Up (healthy)
```

#### ヘルスチェック

```bash
# Qdrant
curl http://localhost:6333/health
# → {"title":"qdrant - vector search engine","version":"..."}

# Redis
docker compose -f docker-compose/docker-compose.yml exec redis redis-cli ping
# → PONG
```

#### ログ確認

```bash
docker compose -f docker-compose/docker-compose.yml logs -f qdrant
docker compose -f docker-compose/docker-compose.yml logs -f redis
```

#### 停止

```bash
# データを保持したまま停止
docker compose -f docker-compose/docker-compose.yml down

# データも削除してリセット
docker compose -f docker-compose/docker-compose.yml down -v
```

---

### 5.3 Celery ワーカーの起動

Q/A 自動生成などのバックグラウンドタスクを処理します。

```bash
# 実行権限付与（初回のみ）
chmod +x start_celery.sh

# 起動（M2 MacBook Air 推奨設定）
./start_celery.sh start -c 8 --flower

# 状態確認
./start_celery.sh status

# 再起動
./start_celery.sh restart -c 8 --flower

# 停止
./start_celery.sh stop
```

#### Flower タスクモニター

```
http://localhost:5555
```

#### 推奨パラメータ（M2 MacBook Air 8 コア）

| パラメータ | 推奨値 | 説明 |
|----------|--------|------|
| `-c`（concurrency） | 8 | CPU コア数に合わせる |
| `--flower` | 有効 | タスク状況のリアルタイム監視 |

---

## 6. 初回データ登録

Qdrant にベクトルデータを登録します（初回または再構築時）。

### 6.1 チャンク済みデータを Qdrant に登録

```bash
uv run python qa_qdrant/make_qa_register_qdrant.py \
    --input-file output_chunked/cc_news_5per_chunks.csv \
    --collection cc_news_5per \
    --recreate
```

### 6.2 Celery 経由で並列 Q/A 生成 + 登録

```bash
# Celery ワーカーを先に起動してから実行
uv run python qa_qdrant/make_qa_register_qdrant.py \
    --input-file output_chunked/cc_news_5per_chunks.csv \
    --collection cc_news_5per \
    --use-celery \
    --recreate
```

### 6.3 登録データの確認

```bash
# Qdrant コレクション一覧
curl http://localhost:6333/collections | python3 -m json.tool
```

---

## 7. アプリケーションの起動・停止

### 7.1 全サービスの一括起動手順

```bash
# ── ターミナル 1: Ollama ──────────────────────────────
ollama serve

# ── ターミナル 2: Docker (Qdrant + Redis) ────────────
docker compose -f docker-compose/docker-compose.yml up -d

# ── ターミナル 3: Celery ワーカー ────────────────────
./start_celery.sh start -c 8 --flower

# ── ターミナル 4: Streamlit アプリ ───────────────────
uv run streamlit run agent_rag.py --server.port 8501
```

ブラウザでアクセス:
```
http://localhost:8501
```

### 7.2 起動後のアクセス先一覧

| サービス | URL | 備考 |
|---------|-----|------|
| Streamlit Web UI | http://localhost:8501 | メインアプリ |
| Qdrant REST API | http://localhost:6333 | DB 管理 |
| Flower（Celery 監視） | http://localhost:5555 | タスクモニター |

### 7.3 全サービスの停止

```bash
# Streamlit: Ctrl+C

# Celery 停止
./start_celery.sh stop

# Docker 停止
docker compose -f docker-compose/docker-compose.yml down

# Ollama: Ctrl+C（またはメニューバーアイコンから終了）
```

---

## 8. ポート一覧

| サービス | ポート | プロトコル | 用途 |
|---------|--------|----------|------|
| Streamlit | **8501** | HTTP | Web UI |
| Ollama | **11434** | HTTP | LLM / Embedding API |
| Qdrant | **6333** | HTTP | ベクトル DB REST API |
| Redis | **6379** | TCP | Celery ブローカー・結果保存 |
| Flower | **5555** | HTTP | Celery タスクモニタリング |

---

## 9. 動作確認チェックリスト

セットアップ完了後、以下をすべて確認してください。

### ソフトウェア

```
[ ] python3 --version  →  Python 3.13.x
[ ] uv --version       →  uv 0.x.x
[ ] docker --version   →  Docker version 27.x.x
[ ] ollama --version   →  ollama version 0.x.x
```

### サービス起動

```
[ ] ollama serve が起動中（curl http://localhost:11434/api/tags が応答）
[ ] ollama list に gemma4:e4b が表示される
[ ] ollama list に nomic-embed-text が表示される
[ ] docker compose ps で qdrant が Up (healthy)
[ ] docker compose ps で redis が Up (healthy)
[ ] curl http://localhost:6333/health が正常応答
[ ] ./start_celery.sh status でワーカーが起動中
```

### アプリ起動

```
[ ] uv run streamlit run agent_rag.py が正常起動
[ ] http://localhost:8501 にブラウザでアクセス可能
[ ] 左ペインのメニューが表示される
[ ] Agent(ReAct+Reflection) でエラーなく動作する
[ ] 自律型 Agent(Plan+Executor) でエラーなく動作する
```

---

## 10. トラブルシューティング

### Ollama が接続できない

```bash
# サーバーが起動しているか確認
curl http://localhost:11434/api/tags

# プロセス確認
ps aux | grep ollama

# 再起動
pkill ollama; ollama serve
```

### `model 'gemma4:e4b' does not exist` エラー

```bash
# モデルをダウンロード
ollama pull gemma4:e4b
ollama pull nomic-embed-text
```

### Qdrant に接続できない

```bash
# コンテナ状態確認
docker compose -f docker-compose/docker-compose.yml ps

# unhealthy の場合は再起動
docker compose -f docker-compose/docker-compose.yml restart qdrant

# ログで原因確認
docker compose -f docker-compose/docker-compose.yml logs qdrant
```

### Celery ワーカーが起動しない

```bash
# Redis が起動しているか確認
docker compose -f docker-compose/docker-compose.yml exec redis redis-cli ping
# → PONG でなければ Docker を再起動

# Celery ログ確認
tail -50 logs/celery_qa_worker.log
```

### `ModuleNotFoundError` が出る

```bash
# uv run 経由で実行する（自動で venv を解決）
uv run python agent_rag.py

# PYTHONPATH を明示する場合
export PYTHONPATH="$(pwd):$(pwd)/helper"
```

### `uv sync` が Python バージョンエラーで失敗する

```bash
# Python 3.13 を明示指定
uv sync --python 3.13

# .python-version ファイルで固定
echo "3.13" > .python-version
uv sync
```

### `ExecutionPlan` ValidationError（GRACE Agent エラー）

llama3.2 / gemma4:e4b 等のOllama小型モデル は `$ref`/`$defs` を含む複雑な JSON スキーマを解釈できません。  
`helper/helper_llm.py` の `_resolve_schema_refs()` が自動解決します。  
詳細: `docs/migration_openai2ollama.md` §1-4 参照。

### Streamlit で「Q/A が生成されない」

Celery ワーカーが起動していない可能性があります:
```bash
./start_celery.sh status
# 起動していなければ
./start_celery.sh start -c 8 --flower
```

### `could not convert string to float` エラー（信頼度スコア）

`grace/confidence.py` で llama3.2 / gemma4:e4b 等のOllama小型モデル が自然言語付きで数値を返した場合のエラー。  
正規表現による抽出（`re.search(r"[01]?\.\d+|\b[01]\b", text)`）が実装済みです。  
エラーが継続する場合は `docs/llm_api_comparison_v3.md` §16-3 を参照。

---

## 11. 主要ファイル構成

```
ollama_grace_agent/
├── agent_rag.py              # Streamlit メインアプリ
├── agent_main.py             # エージェント共通ロジック
├── config.py                 # アプリ設定（モデル・DB・Celery など）
├── config.yml                # YAML 形式設定ファイル
├── pyproject.toml            # プロジェクト定義（uv 管理）
├── uv.lock                   # 依存ロックファイル（変更禁止）
├── .env                      # 環境変数（要作成・git 管理外）
│
├── docker-compose/
│   └── docker-compose.yml    # Qdrant + Redis コンテナ定義
│
├── start_celery.sh           # Celery ワーカー起動スクリプト
├── start_workers.sh          # 複数ワーカー起動スクリプト
│
├── helper/
│   ├── helper_llm.py         # Ollama / LLM クライアント（_resolve_schema_refs 含む）
│   └── helper_embedding.py   # Embedding クライアント（Ollama 対応）
│
├── grace/                    # GRACE Agent（Plan+Executor）
│   ├── confidence.py         # 信頼度スコア計算
│   ├── executor.py           # タスク実行エンジン
│   └── planner.py            # タスク計画生成
│
├── qa_generation/
│   └── smart_qa_generator.py # Q/A 自動生成（Ollama 対応）
│
├── qa_qdrant/
│   └── make_qa_register_qdrant.py  # Q/A 生成 + Qdrant 登録
│
├── chunking/                 # テキストチャンキング
├── output_chunked/           # チャンク済みデータ（CSV）
├── qa_output/                # 生成済み Q/A データ
├── logs/                     # Celery ログ
│
└── docs/
    ├── migration_openai2ollama.md   # OpenAI → Ollama 移植仕様書（v1.2）
    ├── llm_api_comparison_v3.md     # LLM API 比較表（v5）
    └── setup_and_install.md         # 本ファイル
```

---

## 12. 参考ドキュメント

| ドキュメント | 内容 |
|------------|------|
| `docs/migration_openai2ollama.md` | OpenAI → Ollama 移植仕様・注意点（v1.2） |
| `docs/llm_api_comparison_v3.md` | OpenAI / Gemini / Anthropic / Ollama API 比較表（v5） |
| `readme_rag.md` | RAG システム概要 |
| `readme_autonomous_agent.md` | GRACE 自律エージェント概要 |
| `readme_react_reflection.md` | ReAct + Reflection エージェント概要 |
| `CLAUDE.md` | Claude Code 向けプロジェクトガイド |

---

*最終更新: 2026-05-21*
