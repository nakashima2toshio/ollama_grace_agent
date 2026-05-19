
## 構成の比較

| セクション | 推奨構成 | 理由 |
|-----------|---------|------|
| 設定管理 | 01_config | 全体で使用する設定の理解が先 |
| データI/O | 02_data_io | 入出力の基本を理解 |
| 前処理（CSV行結合） | 02_data_io内 | データI/Oの一部として統合 |
| チャンク分割 | 03_chunking | Q/A生成の前提として重要 |
| Q/A生成 | 04_qa_generation | 順序を整理 |
| Semantic分析 | 05_evaluation | カバレッジ分析として独立 |
| Embedding | 06_helper内 | ヘルパーとして統合 |
| LLM | 06_helper内 | 同上 |
| Qdrant | 07_qdrant | より細分化 |
| Celery | 08_celery | 同上 |
| 統合テスト | 09_integration | 学習の総仕上げ |

---

# Q/A生成 & Qdrant登録システム - カテゴリー別一覧

## 📁 ファイル構成

```
qa_qdrant/
├── make_qa_register_qdrant.py  # 統合CLIエントリーポイント
├── make_qa.py                   # Q/A生成専用CLI
├── register_to_qdrant.py        # Qdrant登録専用CLI
│
├── config.py                    # 設定管理
│
├── qa_generation/               # Q/A生成モジュール
│   ├── pipeline.py              #   パイプライン制御
│   ├── structure.py             #   チャンク分割
│   ├── generation.py            #   Q/A生成ロジック
│   ├── smart_qa_generator.py    #   スマート生成
│   ├── semantic.py              #   セマンティック分析
│   ├── evaluation.py            #   カバレッジ評価
│   ├── data_io.py               #   データ入出力
│   └── models.py                #   Pydanticモデル
│
├── helper/                      # ヘルパーモジュール
│   ├── helper_llm.py            #   LLMクライアント
│   └── helper_embedding.py      #   Embeddingクライアント
│
├── services/
│   └── qdrant_service.py        # Qdrantサービス（高レベル）
├── qdrant_client_wrapper.py     # Qdrantラッパー（低レベル）
│
└── celery_tasks.py              # Celery非同期タスク
```

---

## 1️⃣ CLIエントリーポイント

### make_qa_register_qdrant.py (780行)
| 関数 | 説明 |
|------|------|
| `main()` | CLIエントリーポイント |
| `normalize_source_filename()` | 日時サフィックス除去 |
| `combine_rows_to_chunks()` | CSV行結合（Phase 0） |
| `run_registration()` | Qdrant登録実行（Phase 2） |

### make_qa.py (180行)
| 関数 | 説明 |
|------|------|
| `main()` | Q/A生成専用CLIエントリーポイント |

### register_to_qdrant.py (514行)
| 関数 | 説明 |
|------|------|
| `main()` | Qdrant登録専用CLIエントリーポイント |
| `normalize_source_filename()` | ファイル名正規化 |
| `detect_text_column()` | テキスト列自動検出 |
| `create_ui_csv()` | UI用CSV生成 |
| `register_to_qdrant()` | 登録メイン処理 |

---

## 2️⃣ 設定管理

### config.py (552行)
| クラス/関数 | 説明 |
|------------|------|
| `DatasetInfo` | データセット情報（dataclass） |
| `ModelConfig` | LLMモデル設定 |
| `DatasetConfig` | データセット設定 |
| `QAConfig` | Q/A生成設定 |
| `QdrantConfig` | Qdrant接続設定 |
| `GeminiConfig` | Gemini API設定 |
| `CeleryConfig` | Celery設定 |
| `PathConfig` | パス設定 |
| `DATASET_CONFIGS` | グローバル変数（後方互換） |

---

## 3️⃣ データ入出力

### data_io.py (227行)
| 関数 | 説明 |
|------|------|
| `load_uploaded_file()` | ローカルファイル読み込み（CSV/TXT/JSON/JSONL） |
| `load_preprocessed_data()` | 前処理済みデータセット読み込み |
| `save_results()` | Q/A結果保存（JSON/CSV） |
| `clean_text()` | テキストクリーニング |

### models.py (267行)
| クラス | 説明 |
|-------|------|
| `QAPair` | Q/Aペアモデル |
| `QAPairsResponse` | Q/Aペアリスト応答 |
| `ChunkAnalysis` | チャンク分析結果 |
| `CoverageResult` | カバレッジ結果 |

---

## 4️⃣ チャンク分割

### structure.py (239行)
| 関数 | 説明 |
|------|------|
| `create_document_chunks()` | **メイン関数**: DataFrameからチャンク作成（並列処理） |
| `create_semantic_chunks()` | セマンティック分割（SemanticCoverage使用） |
| `merge_small_chunks()` | 小さいチャンクの統合 |
| `_process_single_document()` | 単一ドキュメント処理（内部） |

---

## 5️⃣ Q/A生成

### pipeline.py (414行)
| クラス/関数 | 説明 |
|------------|------|
| `QAPipeline` | **メインクラス**: Q/A生成パイプライン制御 |
| `QAPipeline.__init__()` | 初期化（dataset_name/input_file） |
| `QAPipeline.run()` | パイプライン実行 |
| `QAPipeline._load_data()` | データ読み込み |
| `QAPipeline._create_chunks()` | チャンク作成 |
| `QAPipeline._generate_qa()` | Q/A生成（Celery/同期） |
| `QAPipeline._save_results()` | 結果保存 |

### generation.py (614行)
| クラス/関数 | 説明 |
|------------|------|
| `QAGenerator` | **メインクラス**: Q/Aペア生成 |
| `QAGenerator.determine_qa_count()` | Q/A数決定（Smart/Legacy） |
| `QAGenerator.generate_for_chunk()` | 単一チャンクからQ/A生成 |
| `QAGenerator.generate_for_batch()` | バッチQ/A生成 |
| `QAGenerator._generate_smart()` | スマート生成 |
| `QAGenerator._generate_legacy()` | 従来方式生成 |
| `QAGenerator._legacy_determine_qa_count()` | トークン数ベースQ/A数決定 |
| `generate_qa_dataset()` | 関数版Q/A生成（後方互換） |

### smart_qa_generator.py (512行)
| クラス/関数 | 説明 |
|------------|------|
| `SmartQAGenerator` | **メインクラス**: インテリジェントQ/A生成 |
| `SmartQAGenerator.analyze_chunk()` | チャンク分析（qa_count, importance等） |
| `SmartQAGenerator.generate_qa_pairs()` | Q/Aペア生成 |
| `SmartQAGenerator._generate_content()` | LLMコンテンツ生成（API切替対応） |
| `SmartQAGenerator._parse_analysis_response()` | 分析応答パース |
| `SmartQAGenerator._parse_qa_response()` | Q/A応答パース |

---

## 6️⃣ セマンティック分析・評価

### semantic.py (537行)
| クラス/関数 | 説明 |
|------------|------|
| `SemanticCoverage` | **メインクラス**: 意味的網羅性測定 |
| `SemanticCoverage.create_semantic_chunks()` | セマンティックチャンク分割 |
| `SemanticCoverage.calculate_coverage()` | カバレッジ計算 |
| `SemanticCoverage._chunk_by_paragraphs()` | 段落ベース分割 |
| `SemanticCoverage._split_into_sentences()` | 文分割（MeCab/regex） |
| `SemanticCoverage._apply_chunk_overlap()` | オーバーラップ適用 |
| `SemanticCoverage._embed_texts()` | テキスト埋め込み |

### evaluation.py (297行)
| 関数 | 説明 |
|------|------|
| `analyze_coverage()` | **メイン関数**: カバレッジ分析 |
| `calculate_multi_threshold_coverage()` | 複数閾値でのカバレッジ計算 |
| `identify_uncovered_chunks()` | 未カバーチャンク特定 |
| `generate_coverage_report()` | カバレッジレポート生成 |

---

## 7️⃣ ヘルパーモジュール

### helper_llm.py (267行)
| クラス/関数 | 説明 |
|------------|------|
| `LLMClient` | **抽象基底クラス**: LLMクライアント |
| `GeminiClient` | Gemini LLMクライアント |
| `OpenAIClient` | OpenAI LLMクライアント |
| `create_llm_client()` | **ファクトリ関数**: クライアント生成 |
| `LLMClient.generate_content()` | コンテンツ生成 |
| `LLMClient.generate_structured()` | 構造化出力生成 |
| `LLMClient.count_tokens()` | トークン数カウント |

### helper_embedding.py (398行)
| クラス/関数 | 説明 |
|------------|------|
| `EmbeddingClient` | **抽象基底クラス**: Embeddingクライアント |
| `GeminiEmbedding` | Gemini Embeddingクライアント |
| `OpenAIEmbedding` | OpenAI Embeddingクライアント |
| `create_embedding_client()` | **ファクトリ関数**: クライアント生成 |
| `get_embedding_dimensions()` | 次元数取得 |
| `EmbeddingClient.embed_text()` | 単一テキスト埋め込み |
| `EmbeddingClient.embed_texts()` | バッチ埋め込み |

---

## 8️⃣ Qdrantモジュール

### qdrant_service.py (1072行)
| クラス/関数 | 説明 |
|------------|------|
| `QdrantHealthChecker` | ヘルスチェッククラス |
| `QdrantHealthChecker.check_port()` | ポート接続確認 |
| `QdrantHealthChecker.check_qdrant()` | Qdrant状態確認 |
| `QdrantDataFetcher` | データ取得クラス |
| `QdrantDataFetcher.fetch_collections()` | コレクション一覧取得 |
| `QdrantDataFetcher.fetch_collection_points()` | ポイント取得 |
| `QdrantDataFetcher.fetch_collection_info()` | コレクション情報取得 |
| `create_or_recreate_collection_for_qdrant()` | コレクション作成/再作成 |
| `load_csv_for_qdrant()` | CSV読み込み |
| `build_inputs_for_embedding()` | 埋め込み入力構築 |
| `embed_texts_for_qdrant()` | テキスト埋め込み |
| `build_points_for_qdrant()` | PointStruct構築 |
| `upsert_points_to_qdrant()` | ポイントアップサート |
| `embed_query_for_search()` | 検索クエリ埋め込み |
| `scroll_all_points_with_vectors()` | 全ポイント取得 |
| `merge_collections()` | コレクションマージ |

### qdrant_client_wrapper.py (1184行)
| 関数 | 説明 |
|------|------|
| `create_qdrant_client()` | **ファクトリ関数**: クライアント生成 |
| `get_collection_stats()` | コレクション統計取得 |
| `create_or_recreate_collection()` | コレクション作成/再作成 |
| `load_csv_for_qdrant()` | CSV読み込み |
| `build_inputs_for_embedding()` | 埋め込み入力構築 |
| `embed_texts()` | テキスト埋め込み |
| `embed_texts_unified()` | プロバイダー統一埋め込み |
| `embed_query()` | クエリ埋め込み |
| `embed_query_unified()` | プロバイダー統一クエリ埋め込み |
| `embed_sparse_texts_unified()` | スパース埋め込み（ハイブリッド検索用） |
| `build_points()` | PointStruct構築 |
| `upsert_points()` | ポイントアップサート |
| `search_collection()` | **検索関数**: ハイブリッド検索対応 |
| `create_collection_for_provider()` | プロバイダー別コレクション作成 |
| `get_provider_vector_size()` | プロバイダー別次元数取得 |

---

## 9️⃣ Celery非同期処理

### celery_tasks.py (588行)
| 関数 | 説明 |
|------|------|
| `check_celery_workers()` | ワーカー稼働確認 |
| `get_worker_info()` | ワーカー情報取得 |
| `submit_unified_qa_generation()` | **メイン関数**: Q/A生成タスク投入 |
| `collect_results()` | 結果収集 |
| `generate_qa_for_chunk_task` | Celeryタスク: チャンクQ/A生成 |
| `generate_qa_batch_task` | Celeryタスク: バッチQ/A生成 |

---

## 📊 カテゴリー別サマリー

| カテゴリ | ファイル数 | 主要クラス | 主要関数 |
|---------|-----------|-----------|---------|
| CLI | 3 | - | `main()`, `run_registration()` |
| 設定管理 | 1 | 8 | - |
| データI/O | 2 | 4 | 4 |
| チャンク分割 | 1 | - | 4 |
| Q/A生成 | 3 | 3 | 10+ |
| セマンティック分析 | 2 | 1 | 8+ |
| ヘルパー | 2 | 5 | 4 |
| Qdrant | 2 | 2 | 20+ |
| Celery | 1 | - | 6 |
| **合計** | **17** | **23+** | **60+** |

---

## 🔄 主要な処理フロー

```
make_qa_register_qdrant.py
    │
    ├─ Phase 0: combine_rows_to_chunks()     [オプション]
    │
    ├─ Phase 1: QAPipeline.run()
    │      │
    │      ├─ data_io.load_uploaded_file()
    │      ├─ structure.create_document_chunks()
    │      │      └─ semantic.SemanticCoverage.create_semantic_chunks()
    │      │
    │      ├─ [Celery] celery_tasks.submit_unified_qa_generation()
    │      │      └─ generation.QAGenerator.generate_for_chunk()
    │      │             └─ smart_qa_generator.SmartQAGenerator
    │      │
    │      ├─ [同期] generation.QAGenerator.generate_for_batch()
    │      │
    │      ├─ evaluation.analyze_coverage()
    │      └─ data_io.save_results()
    │
    └─ Phase 2: run_registration()
           │
           ├─ qdrant_service.load_csv_for_qdrant()
           ├─ qdrant_service.embed_texts_for_qdrant()
           │      └─ helper_embedding.GeminiEmbedding.embed_texts()
           ├─ qdrant_service.build_points_for_qdrant()
           └─ qdrant_service.upsert_points_to_qdrant()
```

