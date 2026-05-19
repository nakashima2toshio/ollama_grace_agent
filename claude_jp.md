# CLAUDE.md (日本語版)

このファイルは、このリポジトリでコードを扱う際のClaude Code (claude.ai/code) への指針を提供します。

## プロジェクト概要

このプロジェクトは、Q&Aデータセットと文書の意味的カバレッジ分析を実装した日本語RAG（Retrieval-Augmented Generation）質問応答システムです。OpenAIの埋め込みモデルとQdrantベクトルデータベースを使用して、類似度検索とカバレッジメトリクスの計算を行います。

## 開発コマンド

### 環境セットアップ
```bash
# 初期セットアップ（パッケージのインストールと環境設定）
python setup.py

# 依存関係のインストール
pip install -r requirements.txt

# Qdrantベクトルデータベースの起動
docker-compose -f docker-compose/docker-compose.yml up -d

# Qdrantへのデータ登録
python a30_qdrant_registration.py --recreate --limit 100
```

### アプリケーションの実行
```bash
# Qdrantサーバー管理スクリプトの起動
python server.py

# Streamlit検索UIの実行
streamlit run a50_rag_search_local_qdrant.py

# 意味的カバレッジ分析のサンプル実行
python example.py
```

### コード品質
```bash
# ruffリンターの実行（設定ファイルはまだ存在しません）
ruff check .

# ruffでコードフォーマット
ruff format .
```

## アーキテクチャ

### コアコンポーネント

1. **SemanticCoverage** (`rag_qa.py`): 文書チャンキングと意味的カバレッジ計算を実装するメインクラス
   - 文書から意味的チャンクを作成
   - 文書とQ&Aペアの埋め込みを生成
   - コサイン類似度を使用してカバレッジメトリクスを計算
   - 文境界検出による日本語テキスト処理をサポート

2. **ヘルパーモジュール**:
   - `helper_api.py`: OpenAI API統合、モデル設定、コスト追跡
   - `helper_rag.py`: RAGデータ前処理、設定管理（AppConfigクラス）
   - `helper_st.py`: カスタマーサポートFAQ処理用Streamlitユーティリティ

### OpenAI API リファレンス（重要）

**このプロジェクトでOpenAI APIを扱う際は、必ず以下を参照してください：**
- **`helper_api.py`**: OpenAI API呼び出しの実装とラッパー
- **`doc/helper_api.md`**: サポートされているAPIとその使用方法の完全なドキュメント

これらのファイルには、最新のOpenAI API実装パターンが含まれています：
- **Responses API** (`client.responses.create()`) - developerロールを含む新しいメッセージ形式
- **Chat Completions API** (`client.chat.completions.create()`) - JSON出力対応の標準チャット形式
- **Structured Outputs API** (`client.responses.parse()`) - Pydanticモデルによる型安全な出力

このプロジェクトで使用するOpenAIモデル：
- GPT-4o、GPT-4.1、GPT-5シリーズ - 一般的なテキスト生成用
- Oシリーズ（o1、o3、o4） - 推論重視のタスク用（temperatureパラメータ非対応）
- Structured Outputs API - PydanticモデルによるQ&Aペア生成の型安全性

3. **データ管理スクリプト**（aプレフィックス付きファイル）:
   - `a01_load_set_rag_data.py`: RAGデータのロードと設定
   - `a02_set_vector_store_vsid.py`: ベクトルストアIDの設定
   - `a03_rag_search_cloud_vs.py`: クラウドベクトルストアの検索
   - `a30_qdrant_registration.py`: Qdrantへのデータ登録
   - `a35_qdrant_truncate.py`: Qdrantコレクションの削除
   - `a40_show_qdrant_data.py`: Qdrantデータの表示
   - `a50_rag_search_local_qdrant.py`: ローカルQdrant検索用Streamlit UI

4. **インフラストラクチャ**:
   - `server.py`: Qdrantサーバーのヘルスチェックと起動管理
   - `docker-compose/docker-compose.yml`: コンテナ化されたQdrantのデプロイ

### データフロー

1. 文書は文境界を保持しながら意味的チャンクに分割される
2. チャンクとQ&AペアのOpenAI埋め込みが生成される
3. 埋め込みはQdrantベクトルデータベースに保存される
4. カバレッジ分析でQ&A埋め込みと文書チャンクを比較する
5. 結果はStreamlit UIまたはAPIエンドポイント経由で表示される

### モデル設定

システムは広範なOpenAIモデルをサポート（`config.yml`で設定）:
- GPT-4oシリーズ（miniおよびaudioバリアントを含む）
- GPT-4.1、GPT-5シリーズ
- Oシリーズモデル（o1、o3、o4とminiバリアント）
- 埋め込みモデル（text-embedding-3-small/large）

## 環境変数

`.env`ファイルに必要な設定:
```
OPENAI_API_KEY=your-openai-api-key
QDRANT_URL=http://localhost:6333  # オプション、デフォルトはlocalhost
PG_CONN_STR=postgresql://...       # オプション、PostgreSQL統合用
```

## 主要な実装詳細

- **日本語テキスト処理**: 日本語文分割用の正規表現パターンを使用
- **チャンキング戦略**: チャンクあたり200トークン制限の意味的チャンキング
- **埋め込みモデル**: デフォルトは"text-embedding-3-small"
- **カバレッジ閾値**: Q&Aとチャンクのマッチングに0.8のコサイン類似度
- **トークンカウント**: "cl100k_base"エンコーディングでtiktokenを使用

## 依存関係

主要パッケージ:
- `openai>=1.100.2`: 埋め込みとチャット用APIクライアント
- `qdrant-client>=1.15.1`: ベクトルデータベースクライアント
- `streamlit>=1.48.1`: Web UIフレームワーク
- `fastapi>=0.115.6`: APIサーバーフレームワーク
- `tiktoken`: チャンクサイズ管理用トークンカウント
- `scikit-learn`: コサイン類似度計算

## 重要な注意事項

- 正式なテストスイートは存在しません - 新機能実装時はpytestの追加を検討してください
- コードベースの一部で日本語の変数名とコメントが使用されています
- 古い実装は`old_code/`ディレクトリにアーカイブされています
- データ登録や検索機能を使用する前にQdrantが実行されている必要があります