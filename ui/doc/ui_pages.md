# UI画面構成ドキュメント

## 概要

本システムは、RAG（Retrieval-Augmented Generation）パイプラインのための統合UIを提供します。Streamlitをベースに構築され、データの前処理からQ/A生成、Qdrantへの登録、エージェント対話まで一貫したワークフローを実現します。

---

## 目次

1. [システムアーキテクチャ](#システムアーキテクチャ)
2. [ディレクトリ構成](#ディレクトリ構成)
3. [ページ一覧](#ページ一覧)
4. [各ページ詳細](#各ページ詳細)
5. [共通コンポーネント](#共通コンポーネント)
6. [セッション状態管理](#セッション状態管理)

---

## システムアーキテクチャ

### 全体構成図

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Streamlit App (app.py)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                Navigation                                   │
│  ┌─────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │説明 │エージェント │ GRACE    │未回答ログ │RAGダウン   │ Q/A生成  │CSVデータ  │  │
│  │     │  対話     │エージェント│         │ロード      │          │  登録    │  │
│  └─────┴──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘  │
│  ┌──────────┬──────────┐                                                    │
│  │Qdrantデータ│Qdrant   │                                                    │
│  │  管理      │ 検索    │                                                    │
│  └──────────┴──────────┘                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        ▼                             ▼                             ▼
┌───────────────┐           ┌───────────────┐           ┌───────────────┐
│   ui/pages/   │           │  ui/components/│          │   services/   │
│  (ページ群)    │           │ (UIコンポーネント)│          │  (ビジネス     │
│               │           │               │           │   ロジック)    │
└───────────────┘           └───────────────┘           └───────────────┘
        │                             │                             │
        ▼                             ▼                             ▼
┌───────────────┐           ┌───────────────┐           ┌───────────────┐
│ explanation   │           │ rag_components│           │ agent_service │
│ agent_chat    │           │ grace_components│         │ qdrant_service│
│ grace_chat    │           │               │           │ qa_service    │
│ log_viewer    │           │               │           │ file_service  │
│ download      │           │               │           │ dataset_service│
│ qa_generation │           │               │           │ log_service   │
│ qdrant_reg    │           │               │           │               │
│ qdrant_show   │           │               │           │               │
│ qdrant_search │           │               │           │               │
└───────────────┘           └───────────────┘           └───────────────┘
```

### データフロー

```
┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐
│ HuggingFace│    │   OUTPUT/  │    │ qa_output/ │    │   Qdrant   │
│  Dataset   │───▶│preprocessed│───▶│ qa_pairs   │───▶│ Collection │
│            │    │   *.csv    │    │   *.csv    │    │            │
└────────────┘    └────────────┘    └────────────┘    └────────────┘
      │                 │                 │                 │
      ▼                 ▼                 ▼                 ▼
┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐
│ RAGダウン   │    │  Q/A生成    │    │ CSVデータ   │    │エージェント  │
│  ロード     │    │            │    │   登録      │    │   対話      │
└────────────┘    └────────────┘    └────────────┘    └────────────┘
```

---

## ディレクトリ構成

```
ui/
├── __init__.py
├── pages/
│   ├── __init__.py
│   ├── explanation_page.py      # 説明ページ
│   ├── agent_chat_page.py       # エージェント対話
│   ├── grace_chat_page.py       # GRACEエージェント
│   ├── log_viewer_page.py       # 未回答ログ
│   ├── download_page.py         # RAGデータダウンロード
│   ├── qa_generation_page.py    # Q/A生成
│   ├── qdrant_registration_page.py  # CSVデータ登録
│   ├── qdrant_show_page.py      # Qdrantデータ管理
│   └── qdrant_search_page.py    # Qdrant検索
└── components/
    ├── __init__.py
    ├── rag_components.py        # RAG用UIコンポーネント
    └── grace_components.py      # GRACE用UIコンポーネント
```

---

## ページ一覧

| # | ページ名 | ファイル | 関数名 | 主な機能 |
|---|---------|----------|--------|---------|
| 1 | 説明 | explanation_page.py | `show_system_explanation_page()` | README.md表示、Mermaid図レンダリング |
| 2 | エージェント対話 | agent_chat_page.py | `show_agent_chat_page()` | ReAct+Qdrant RAGチャット |
| 3 | GRACEエージェント | grace_chat_page.py | `show_grace_chat_page()` | GRACEアーキテクチャチャット |
| 4 | 未回答ログ | log_viewer_page.py | `show_log_viewer_page()` | 未回答質問の履歴管理 |
| 5 | RAGデータダウンロード | download_page.py | `show_rag_download_page()` | HuggingFaceダウンロード・前処理 |
| 6 | Q/A生成 | qa_generation_page.py | `show_qa_generation_page()` | Q/Aペア自動生成 |
| 7 | CSVデータ登録 | qdrant_registration_page.py | `show_qdrant_registration_page()` | Qdrantへのデータ登録 |
| 8 | Qdrantデータ管理 | qdrant_show_page.py | `show_qdrant_page()` | コレクション管理・統合 |
| 9 | Qdrant検索 | qdrant_search_page.py | `show_qdrant_search_page()` | ベクトル検索・AI応答 |

---

## 各ページ詳細

### 1. 説明ページ（explanation_page.py）

#### 概要
README.mdおよび指定されたMarkdownドキュメントを表示するページ。Mermaid図のレンダリングに対応。

#### 構成図

```
┌─────────────────────────────────────────────────────────────┐
│                    explanation_page.py                      │
├─────────────────────────────────────────────────────────────┤
│  show_system_explanation_page()                             │
│    ├── query_params から doc パラメータ取得                    │
│    ├── Markdown ファイル読み込み                              │
│    └── render_markdown_with_mermaid() でレンダリング          │
├─────────────────────────────────────────────────────────────┤
│  render_markdown_with_mermaid(content)                      │
│    ├── 画像パスのBase64変換                                   │
│    ├── リンクのクエリパラメータ化                                │
│    └── Mermaidコードブロックのレンダリング                       │
├─────────────────────────────────────────────────────────────┤
│  get_image_base64(image_path)                               │
│    └── ローカル画像をBase64データURLに変換                      │
└─────────────────────────────────────────────────────────────┘
```

#### 利用モジュール

| モジュール | クラス/関数 | 用途 |
|-----------|-----------|------|
| streamlit_mermaid | st_mermaid | Mermaid図レンダリング |
| pathlib | Path | ファイルパス操作 |
| base64 | - | 画像のBase64エンコード |

---

### 2. エージェント対話ページ（agent_chat_page.py）

#### 概要
Gemini 2.0 Flash を使用したReAct型エージェントとの対話インターフェース。Qdrant上のナレッジベースを動的に選択し、RAG検索を行いながら回答を生成。

#### 構成図

```
┌─────────────────────────────────────────────────────────────┐
│                    agent_chat_page.py                       │
├─────────────────────────────────────────────────────────────┤
│  show_agent_chat_page()                                     │
│    ├── [Expander] コレクションデータ表示                        │
│    │     └── Qdrant scrollで100件取得・DataFrame表示          │
│    ├── [Sidebar] エージェント設定                             │
│    │     ├── モデル選択 (GeminiConfig.AVAILABLE_MODELS)      │
│    │     ├── コレクション選択 (multiselect)                   │
│    │     ├── ハイブリッド検索切替                              │
│    │     ├── 会話履歴クリア                                   │
│    │     └── キャッシュ統計表示                                │
│    ├── [Main] チャット履歴表示                                 │
│    └── [Main] ユーザー入力 → ReActAgent.execute_turn()        │
│              └── イベント駆動で思考プロセス・結果を表示           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  services/agent_service.py                  │
├─────────────────────────────────────────────────────────────┤
│  ReActAgent                                                 │
│    ├── __init__(collections, model, session_id, use_hybrid) │
│    └── execute_turn(prompt) -> Generator[Event]             │
├─────────────────────────────────────────────────────────────┤
│  get_available_collections_from_qdrant_helper()             │
│    └── Qdrantから利用可能なコレクション一覧を取得                 │
└─────────────────────────────────────────────────────────────┘
```

#### 利用モジュール

| モジュール | クラス/関数 | 用途 |
|-----------|-----------|------|
| services.agent_service | ReActAgent | エージェント本体 |
| services.agent_service | get_available_collections_from_qdrant_helper | コレクション取得 |
| config | AgentConfig, GeminiConfig | 設定値 |
| agent_cache | collection_cache | キャッシュ管理 |
| qdrant_client | QdrantClient | Qdrant接続 |

#### セッション状態

| キー | 型 | 用途 |
|-----|---|------|
| chat_history | List[Dict] | 会話履歴 |
| agent | ReActAgent | エージェントインスタンス |
| agent_session_id | str | セッションID（UUID） |
| current_collections | List[str] | 選択中コレクション |
| current_model | str | 選択中モデル |
| current_hybrid_search | bool | ハイブリッド検索設定 |

---

### 3. GRACEエージェントページ（grace_chat_page.py）

#### 概要
Goal-Reasoning-Action-Critique-Execute アーキテクチャを使用したエージェント対話。基本構造はエージェント対話ページと同様だが、セッション状態のプレフィックスが`grace_`で分離。

#### 構成図

```
┌─────────────────────────────────────────────────────────────┐
│                    grace_chat_page.py                       │
├─────────────────────────────────────────────────────────────┤
│  show_grace_chat_page()                                     │
│    ├── [Expander] コレクションデータ表示                        │
│    ├── [Sidebar] GRACE エージェント設定                        │
│    │     ├── モデル選択                                       │
│    │     ├── コレクション選択                                  │
│    │     ├── ハイブリッド検索切替                               │
│    │     └── キャッシュ統計表示                                 │
│    ├── [Main] チャット履歴表示                                 │
│    └── [Main] ユーザー入力 → grace_agent.execute_turn()       │
└─────────────────────────────────────────────────────────────┘
```

#### セッション状態（プレフィックス: grace_）

| キー | 型 | 用途 |
|-----|---|------|
| grace_chat_history | List[Dict] | 会話履歴 |
| grace_agent | ReActAgent | エージェントインスタンス |
| grace_session_id | str | セッションID |
| grace_current_collections | List[str] | 選択中コレクション |
| grace_current_model | str | 選択中モデル |
| grace_current_hybrid_search | bool | ハイブリッド検索設定 |

---

### 4. 未回答ログページ（log_viewer_page.py）

#### 概要
エージェントがRAG検索で回答を見つけられなかった質問の履歴を表示・管理。ナレッジベース拡充のための分析に活用。

#### 構成図

```
┌─────────────────────────────────────────────────────────────┐
│                    log_viewer_page.py                       │
├─────────────────────────────────────────────────────────────┤
│  show_log_viewer_page()                                     │
│    ├── [Sidebar] ログ操作                                    │
│    │     ├── 最新情報取得ボタン                               │
│    │     └── ログ全消去ボタン                                 │
│    ├── [Main] 統計情報                                       │
│    │     ├── 未回答数メトリクス                                │
│    │     └── 最多理由メトリクス                                │
│    ├── [Main] ログ一覧テーブル                                 │
│    │     ├── 検索フィルタ                                     │
│    │     └── DataFrameで表示                                 │
│    └── [Main] CSVダウンロードボタン                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  services/log_service.py                    │
├─────────────────────────────────────────────────────────────┤
│  load_unanswered_logs() -> pd.DataFrame                     │
│  clear_unanswered_logs() -> None                            │
└─────────────────────────────────────────────────────────────┘
```

#### 利用モジュール

| モジュール | クラス/関数 | 用途 |
|-----------|-----------|------|
| services.log_service | load_unanswered_logs | ログ読み込み |
| services.log_service | clear_unanswered_logs | ログ消去 |

---

### 5. RAGデータダウンロードページ（download_page.py）

#### 概要
HuggingFaceからのデータセットダウンロードとローカルファイルのアップロード・前処理を行う。OUTPUT/フォルダに前処理済みCSVを保存。

#### 構成図

```
┌─────────────────────────────────────────────────────────────┐
│                      download_page.py                       │
├─────────────────────────────────────────────────────────────┤
│  show_rag_download_page()                                   │
│    ├── [Main] 前処理済みデータセット一覧                        │
│    │     └── load_preprocessed_history() で履歴取得          │
│    ├── [Sidebar] データソース選択                             │
│    │     ├── dataset: DATASET_CONFIGS から選択               │
│    │     └── local_file: file_uploader                      │
│    ├── [Main] 処理オプション                                  │
│    │     ├── サンプル数                                      │
│    │     ├── 最小テキスト長                                   │
│    │     └── 重複除去チェックボックス                           │
│    ├── [Main] 実行ボタン                                      │
│    ├── [Main] 処理情報・進捗ログ                               │
│    └── [Main] 結果表示・プレビュー                             │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│dataset_service│     │ file_service  │     │    config     │
├───────────────┤     ├───────────────┤     ├───────────────┤
│download_hf_   │     │load_preproc.. │     │DATASET_CONFIGS│
│  dataset      │     │save_to_output │     │               │
│download_live..│     │               │     │               │
│load_livedoor..│     │               │     │               │
│extract_text.. │     │               │     │               │
│load_uploaded..│     │               │     │               │
└───────────────┘     └───────────────┘     └───────────────┘
```

#### 利用モジュール

| モジュール | クラス/関数 | 用途 |
|-----------|-----------|------|
| services.dataset_service | download_hf_dataset | HuggingFaceダウンロード |
| services.dataset_service | download_livedoor_corpus | Livedoorダウンロード |
| services.dataset_service | load_livedoor_corpus | Livedoor読み込み |
| services.dataset_service | extract_text_content | テキスト抽出 |
| services.dataset_service | load_uploaded_file | アップロードファイル読み込み |
| services.file_service | load_preprocessed_history | 履歴読み込み |
| services.file_service | save_to_output | OUTPUT保存 |
| config | DATASET_CONFIGS | データセット設定 |

#### セッション状態

| キー | 型 | 用途 |
|-----|---|------|
| logs | List[str] | 処理ログ |
| result_count | int | 処理完了件数 |
| saved_files | Dict | 保存ファイルパス |
| qa_saved_files | Dict | Q/A保存ファイルパス |
| processed_df | DataFrame | 処理済みデータ |

---

### 6. Q/A生成ページ（qa_generation_page.py）

#### 概要
データセットまたはローカルファイルからQ/Aペアを自動生成。Celery並列処理に対応し、カバレージ分析機能も提供。

#### 構成図

```
┌─────────────────────────────────────────────────────────────┐
│                   qa_generation_page.py                     │
├─────────────────────────────────────────────────────────────┤
│  show_qa_generation_page()                                  │
│    ├── [Main] 最新Q/A履歴表示                                 │
│    │     └── load_qa_output_history()                       │
│    ├── [Sidebar] 入力ソース選択                               │
│    │     ├── dataset: DATASET_CONFIGS選択                   │
│    │     └── local_file: file_uploader                      │
│    ├── [Sidebar] Q/A生成設定                                 │
│    │     ├── Celery並列処理                                  │
│    │     ├── バッチチャンク数                                 │
│    │     ├── 最大ドキュメント数                                │
│    │     ├── トークン数設定                                   │
│    │     ├── チャンク統合                                     │
│    │     ├── カバレージ閾値                                   │
│    │     ├── モデル選択                                      │
│    │     └── カバレージ分析                                   │
│    ├── [Main] 入力情報・処理設定表示                            │
│    ├── [Main] 実行ボタン                                      │
│    ├── [Main] 進捗バー・処理ログ                               │
│    └── [Main] 生成結果表示                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   services/qa_service.py                    │
├─────────────────────────────────────────────────────────────┤
│  run_advanced_qa_generation(                                │
│      dataset, input_file, use_celery, celery_workers,       │
│      batch_chunks, max_docs, merge_chunks, min_tokens,      │
│      max_tokens, coverage_threshold, model, analyze_coverage,│
│      log_callback, progress_callback                        │
│  ) -> Dict                                                  │
└─────────────────────────────────────────────────────────────┘
```

#### 利用モジュール

| モジュール | クラス/関数 | 用途 |
|-----------|-----------|------|
| services.file_service | load_qa_output_history | Q/A履歴読み込み |
| services.qa_service | run_advanced_qa_generation | Q/A生成実行 |
| config | DATASET_CONFIGS, ModelConfig | 設定値 |

#### セッション状態

| キー | 型 | 用途 |
|-----|---|------|
| qa_logs | List[str] | 処理ログ |
| qa_generation_running | bool | 実行中フラグ |
| qa_result_files | Dict | 結果ファイルパス |
| qa_result_count | int | 生成Q/A数 |

---

### 7. CSVデータ登録ページ（qdrant_registration_page.py）

#### 概要
qa_output/*.csvのQ/AデータをQdrantベクトルDBに登録。Dense/Sparse両方の埋め込みベクトルを生成し、ハイブリッド検索に対応。

#### 構成図

```
┌─────────────────────────────────────────────────────────────┐
│                qdrant_registration_page.py                  │
├─────────────────────────────────────────────────────────────┤
│  show_qdrant_registration_page()                            │
│    ├── [Sidebar] Qdrant設定 (URL)                            │
│    ├── Qdrant接続確認                                        │
│    ├── [Main] 登録設定                                       │
│    │     ├── ファイル選択 (qa_output/*.csv)                   │
│    │     ├── コレクション名                                   │
│    │     ├── 上書き設定                                      │
│    │     ├── answer含める設定                                │
│    │     ├── データ件数制限                                   │
│    │     └── Hybrid Search有効化                            │
│    ├── [Main] データプレビュー (Expander)                     │
│    ├── [Main] 登録実行ボタン                                  │
│    └── [Main] 処理ログ・結果表示                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  services/qdrant_service.py                 │
├─────────────────────────────────────────────────────────────┤
│  load_csv_for_qdrant(path, limit)                           │
│  build_inputs_for_embedding(df, include_answer)             │
│  embed_texts_for_qdrant(texts, model)                       │
│  create_or_recreate_collection_for_qdrant(client, name, ..) │
│  build_points_for_qdrant(df, vectors, domain, source, ..)   │
│  upsert_points_to_qdrant(client, collection, points)        │
│  get_collection_stats(client, collection_name)              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   qdrant_client_wrapper.py                  │
├─────────────────────────────────────────────────────────────┤
│  embed_sparse_texts_unified(texts, progress_callback)       │
└─────────────────────────────────────────────────────────────┘
```

#### 利用モジュール

| モジュール | クラス/関数 | 用途 |
|-----------|-----------|------|
| services.qdrant_service | load_csv_for_qdrant | CSV読み込み |
| services.qdrant_service | build_inputs_for_embedding | 埋め込み入力構築 |
| services.qdrant_service | embed_texts_for_qdrant | Dense埋め込み生成 |
| services.qdrant_service | create_or_recreate_collection_for_qdrant | コレクション作成 |
| services.qdrant_service | build_points_for_qdrant | ポイント構築 |
| services.qdrant_service | upsert_points_to_qdrant | データ登録 |
| qdrant_client_wrapper | embed_sparse_texts_unified | Sparse埋め込み生成 |
| helper.helper_embedding | get_embedding_dimensions | 次元数取得 |

#### セッション状態

| キー | 型 | 用途 |
|-----|---|------|
| qdrant_registration_logs | List[str] | 処理ログ |

---

### 8. Qdrantデータ管理ページ（qdrant_show_page.py）

#### 概要
Qdrantコレクションの一覧表示、削除、統合機能を提供。3つのタブで機能を分割。

#### 構成図

```
┌─────────────────────────────────────────────────────────────┐
│                     qdrant_show_page.py                     │
├─────────────────────────────────────────────────────────────┤
│  show_qdrant_page()                                         │
│    ├── [Sidebar] Qdrant接続設定                              │
│    │     ├── デバッグモード切替                                │
│    │     └── QdrantHealthChecker で接続確認                   │
│    └── [Tabs]                                               │
│          ├── Tab1: コレクション一覧・削除                      │
│          │     ├── 総計表示                                  │
│          │     ├── コレクションリスト                          │
│          │     └── 削除ボタン（確認ダイアログ付き）              │
│          ├── Tab2: データ詳細閲覧                             │
│          │     ├── コレクション選択                           │
│          │     ├── データソース分析ボタン                      │
│          │     ├── 表示件数設定                              │
│          │     └── データロード・CSVダウンロード               │
│          └── Tab3: コレクション統合                          │
│                ├── 統合元コレクション選択（マルチセレクト）       │
│                ├── 統合後コレクション名                       │
│                └── 統合実行ボタン                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  services/qdrant_service.py                 │
├─────────────────────────────────────────────────────────────┤
│  QdrantHealthChecker                                        │
│    ├── check_port(host, port, timeout)                      │
│    └── check_qdrant() -> (bool, str, Dict)                  │
├─────────────────────────────────────────────────────────────┤
│  QdrantDataFetcher                                          │
│    ├── fetch_collections() -> DataFrame                     │
│    ├── fetch_collection_points(name, limit) -> DataFrame    │
│    └── fetch_collection_source_info(name) -> Dict           │
├─────────────────────────────────────────────────────────────┤
│  get_all_collections(client) -> List[Dict]                  │
│  merge_collections(client, sources, target, recreate, ..)   │
└─────────────────────────────────────────────────────────────┘
```

#### 利用モジュール

| モジュール | クラス/関数 | 用途 |
|-----------|-----------|------|
| services.qdrant_service | QdrantHealthChecker | ヘルスチェック |
| services.qdrant_service | QdrantDataFetcher | データ取得 |
| services.qdrant_service | get_all_collections | コレクション一覧 |
| services.qdrant_service | merge_collections | コレクション統合 |
| services.qdrant_service | QDRANT_CONFIG | Qdrant設定 |

#### セッション状態

| キー | 型 | 用途 |
|-----|---|------|
| qdrant_debug_mode | bool | デバッグモード |
| confirm_delete_{name} | bool | 削除確認フラグ |

---

### 9. Qdrant検索ページ（qdrant_search_page.py）

#### 概要
Qdrantベクトルデータベースを使用した意味検索。検索結果に基づいてGemini AIによる応答を生成。

#### 構成図

```
┌─────────────────────────────────────────────────────────────┐
│                   qdrant_search_page.py                     │
├─────────────────────────────────────────────────────────────┤
│  show_qdrant_search_page()                                  │
│    ├── Qdrant接続確認                                        │
│    ├── [Main] コレクション一覧表示                             │
│    │     └── 詳細情報 (Expander)                             │
│    ├── [Sidebar] 検索設定                                    │
│    │     ├── コレクション選択                                  │
│    │     ├── Top-K設定                                       │
│    │     ├── ハイブリッド検索切替                               │
│    │     ├── デバッグモード                                   │
│    │     └── スコア詳細表示                                   │
│    ├── [Main] コレクションデータプレビュー (Expander)           │
│    ├── [Main] 検索入力・実行                                  │
│    ├── [Main] 検索結果表示                                    │
│    │     ├── スコア分布グラフ                                  │
│    │     └── カード形式結果表示                                │
│    └── [Main] AI応答生成 (Gemini)                            │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│qdrant_service │     │qdrant_client  │     │  helper_llm   │
├───────────────┤     │   _wrapper    │     ├───────────────┤
│embed_query_   │     ├───────────────┤     │create_llm_    │
│  for_search   │     │search_        │     │  client       │
│get_collection_│     │  collection   │     │               │
│  embedding_   │     │embed_sparse_  │     │               │
│  params       │     │  query_unified│     │               │
└───────────────┘     └───────────────┘     └───────────────┘
```

#### 利用モジュール

| モジュール | クラス/関数 | 用途 |
|-----------|-----------|------|
| services.qdrant_service | QdrantDataFetcher | データ取得 |
| services.qdrant_service | embed_query_for_search | クエリ埋め込み |
| services.qdrant_service | get_collection_embedding_params | 埋め込み設定取得 |
| qdrant_client_wrapper | search_collection | ベクトル検索 |
| qdrant_client_wrapper | embed_sparse_query_unified | Sparse埋め込み |
| helper.helper_llm | create_llm_client | LLMクライアント生成 |

#### セッション状態

| キー | 型 | 用途 |
|-----|---|------|
| search_query | str | 検索クエリ |

---

## 共通コンポーネント

### rag_components.py

RAGデータ前処理用の再利用可能なUIコンポーネント群。

| 関数 | 用途 |
|-----|------|
| `select_model(key)` | モデル選択UI |
| `show_model_info(model)` | モデル情報表示 |
| `estimate_token_usage(df, model)` | トークン使用量推定 |
| `display_statistics(df_orig, df_proc, type)` | 統計情報表示 |
| `show_usage_instructions(type)` | 使用方法説明表示 |
| `setup_page_config(type)` | ページ設定初期化 |
| `setup_page_header(type)` | ページヘッダー設定 |
| `setup_sidebar_header(type)` | サイドバーヘッダー設定 |

### grace_components.py

GRACEエージェント用のUIコンポーネント群。

| 関数 | 用途 |
|-----|------|
| `display_confidence_metric(score, level, breakdown)` | 信頼度スコア表示 |
| `display_execution_plan(plan, current_step_id)` | 実行計画進捗表示 |
| `display_intervention_request(request, on_response)` | 介入リクエスト表示 |

---

## セッション状態管理

### グローバルセッション状態

| キー | 型 | 用途 | 使用ページ |
|-----|---|------|----------|
| logs | List[str] | 処理ログ | download_page |
| qa_logs | List[str] | Q/A処理ログ | qa_generation_page |
| chat_history | List[Dict] | エージェント会話履歴 | agent_chat_page |
| grace_chat_history | List[Dict] | GRACE会話履歴 | grace_chat_page |
| agent | ReActAgent | エージェントインスタンス | agent_chat_page |
| grace_agent | ReActAgent | GRACEエージェントインスタンス | grace_chat_page |
| qdrant_debug_mode | bool | デバッグモード | qdrant_show_page |

### セッション状態のライフサイクル

```
┌─────────────┐
│ ページ遷移    │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ st.session_state の確認・初期化                               │
│  if "key" not in st.session_state:                          │
│      st.session_state["key"] = initial_value                │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ ユーザー操作による状態更新                                      │
│  st.session_state["key"] = new_value                        │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ クリアボタンによるリセット                                      │
│  del st.session_state["key"]                                │
│  st.rerun()                                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 技術的特徴

### 1. イベント駆動型エージェント表示

エージェントの思考プロセスをリアルタイムで表示するため、`execute_turn()`がジェネレータとしてイベントを`yield`する設計。

```python
for event in agent.execute_turn(prompt):
    if event["type"] == "log":
        # 思考ログ表示
    elif event["type"] == "tool_call":
        # ツール呼び出し表示
    elif event["type"] == "tool_result":
        # ツール結果表示
    elif event["type"] == "final_answer":
        # 最終回答表示
```

### 2. 動的コレクション選択

エージェントページでは、設定変更時にエージェントを再初期化する仕組み。

```python
should_reinitialize = False

if current_collections_key not in st.session_state:
    should_reinitialize = True
elif sorted(st.session_state[current_collections_key]) != sorted(selected_collections):
    should_reinitialize = True

if should_reinitialize:
    st.session_state.agent = ReActAgent(...)
```

### 3. ハイブリッド検索対応

Dense（Gemini Embedding）とSparse（FastEmbed）の両方のベクトルを生成・登録し、検索精度を向上。

---

*Last Updated: 2025-01-28*
