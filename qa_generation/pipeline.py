#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qa_generation/pipeline.py - Q/A生成パイプライン制御モジュール（v3.0 - チャンク処理削除版）

改修内容 (v3.0):
- ★重要★ チャンク分割処理を完全に削除（前段のchunkingで完了済み）
- create_chunks() メソッドを削除
- _convert_df_to_chunks() メソッドを削除
- skip_chunking パラメータを削除
- merge_chunks, min_tokens, max_tokens パラメータを削除
- overlap_tokens, use_similarity, similarity_threshold パラメータを削除
- structure.py への依存を削除
- SmartQAGenerator を直接使用

前提条件:
- 入力CSVは既にチャンク済み（csv_text_to_chunks_text_csv.py で処理済み）
- チャンクCSVには 'text' または 'Combined_Text' カラムが必要

使用例:
  # チャンク済みCSVからQ/A生成
  pipeline = QAPipeline(
      input_file="output_chunked/data_chunks.csv",
      model="gpt-5.4-mini",  # [MIGRATION] "claude-sonnet-4-6" → "gpt-5.4-mini"
      output_dir="qa_output/pipeline"
  )
  result = pipeline.run(
      use_celery=True,
      concurrency=8,
      use_smart_generation=True
  )
"""

import sys
import logging
from typing import List, Dict, Optional, Any
import pandas as pd
from pathlib import Path

from config import DATASET_CONFIGS
from helper.helper_llm import LLMClient
from qa_generation.smart_qa_generator import SmartQAGenerator
from qa_generation.evaluation import analyze_coverage
from celery_tasks import submit_unified_qa_generation, collect_results, check_celery_workers

logger = logging.getLogger(__name__)


class QAPipeline:
    """Q/A生成パイプライン（チャンク済みCSV専用）"""

    def __init__(self,
                 dataset_name: Optional[str] = None,
                 input_file: Optional[str] = None,
                 model: str = "gpt-5.4-mini",  # [MIGRATION] "claude-sonnet-4-6" → "gpt-5.4-mini"
                 output_dir: str = "qa_output/pipeline",
                 max_docs: Optional[int] = None,
                 client: Optional[LLMClient] = None):
        """
        Args:
            dataset_name: データセット名 (cc_news, wikipedia_ja, etc.)
            input_file: ローカル入力ファイルパス（チャンク済み.csv）
            model: 使用するモデル
            output_dir: 出力ディレクトリ
            max_docs: 最大処理チャンク数
            client: LLMクライアント（DI用）
        """
        self.dataset_name = dataset_name
        self.input_file = input_file
        self.model = model
        self.output_dir = output_dir
        self.max_docs = max_docs
        self.client = client

        # 引数の排他制御
        self._validate_inputs()

        self.config = self._load_config()

        # SmartQAGeneratorの初期化
        self.smart_generator = SmartQAGenerator(model=model)
        logger.info(f"SmartQAGenerator初期化完了 (model={model})")

    def _validate_inputs(self):
        """入力パラメータの検証"""
        inputs = [self.dataset_name, self.input_file]
        non_none_count = sum(1 for x in inputs if x is not None)

        if non_none_count == 0:
            raise ValueError(
                "dataset_name, input_file のいずれか1つを指定してください"
            )

        if non_none_count > 1:
            raise ValueError(
                "dataset_name, input_file は同時に指定できません"
            )

    def _load_config(self) -> Dict[str, Any]:
        """設定をロード"""
        if self.input_file:
            # ローカルファイル用の動的設定
            file_basename = Path(self.input_file).stem
            lang = "ja"  # デフォルト
            return {
                "name"        : f"ローカルファイル ({file_basename})",
                "text_column" : "text",  # チャンク済みCSVのデフォルトカラム
                "title_column": None,
                "lang"        : lang,
                "qa_per_chunk": 3,
                "type"        : file_basename
            }

        elif self.dataset_name:
            # 事前定義データセット
            if self.dataset_name not in DATASET_CONFIGS:
                raise ValueError(f"未知のデータセット: {self.dataset_name}")

            config = DATASET_CONFIGS[self.dataset_name].copy()
            logger.info(f"データセット設定をロード: {self.dataset_name}")
            return config

        else:
            raise ValueError("設定の読み込みに失敗しました")

    def load_data(self) -> pd.DataFrame:
        """データを読み込む"""
        from qa_generation.data_io import load_uploaded_file, load_preprocessed_data

        logger.info("\n[1/3] データ読み込み...")

        if self.input_file:
            file_path = Path(self.input_file)

            # CSVファイルのみ対応（チャンク済み前提）
            if file_path.suffix == '.csv':
                logger.info(f"  📊 チャンク済みCSVファイル: {self.input_file}")
                df = load_uploaded_file(self.input_file)
                logger.info(f"  ✅ 読み込み完了: {len(df)} 行")

            else:
                raise ValueError(
                    f"未対応のファイル形式: {file_path.suffix}\n"
                    f"チャンク済みCSVファイル（.csv）を指定してください。\n"
                    f"テキストファイルの場合は、先に csv_text_to_chunks_text_csv.py でチャンク化してください。"
                )

            # 最大チャンク数制限
            if self.max_docs and len(df) > self.max_docs:
                df = df.head(self.max_docs)
                logger.info(f"  📊 最大チャンク数制限: {len(df)} 件に制限")

            return df
        else:
            return load_preprocessed_data(self.dataset_name)

    def _load_chunks_from_csv(self, df: pd.DataFrame) -> List[Dict]:
        """チャンク済みCSVをチャンクリストに変換

        Args:
            df: チャンク済みデータを含むDataFrame

        Returns:
            チャンクのリスト
        """
        logger.info("\n[2/3] チャンクデータ変換...")

        # テキストカラムの検出
        text_col = None
        for col in ['text', 'Combined_Text', 'content', 'chunk_text']:
            if col in df.columns:
                text_col = col
                break

        if text_col is None:
            available_cols = list(df.columns)
            raise ValueError(
                f"テキストカラムが見つかりません。\n"
                f"利用可能なカラム: {available_cols}\n"
                f"必要なカラム: 'text', 'Combined_Text', 'content', 'chunk_text' のいずれか"
            )

        logger.info(f"  テキストカラム: {text_col}")

        # チャンクIDカラムの検出
        id_col = None
        for col in ['chunk_id', 'id', 'chunk_idx']:
            if col in df.columns:
                id_col = col
                break

        if id_col:
            logger.info(f"  IDカラム: {id_col}")

        chunks = []
        dataset_type = self.config.get("type", "unknown")

        for idx, row in df.iterrows():
            chunk_id = row[id_col] if id_col else f"{dataset_type}_chunk_{idx}"
            chunk_text = str(row[text_col]).strip()

            if not chunk_text:
                continue

            chunks.append({
                'id': chunk_id,
                'text': chunk_text,
                'type': row.get('type', 'pre_chunked'),
                'tokens': row.get('tokens', len(chunk_text) // 4),  # 概算
                'dataset_type': dataset_type
            })

        logger.info(f"  ✅ チャンク変換完了: {len(chunks)} チャンク")
        return chunks

    def generate_qa(self, chunks: List[Dict],
                    use_celery: bool = False,
                    celery_workers: int = 1,
                    concurrency: int = 8,
                    batch_chunks: int = 3,
                    use_smart_generation: bool = True) -> List[Dict]:
        """Q/Aペアを生成する

        Args:
            chunks: チャンクのリスト
            use_celery: Celery並列処理を使用するか
            celery_workers: Celeryワーカープロセス数チェック用（デフォルト: 1）
            concurrency: 並列タスク数（デフォルト: 8）
            batch_chunks: 1回のAPIで処理するチャンク数
            use_smart_generation: スマートQ/A生成を使用するか（常にTrue推奨）
        """
        logger.info("\n[3/3] Q/Aペア生成...")

        # スマート生成モードのログ出力
        mode_name = "スマート生成" if use_smart_generation else "従来方式"
        logger.info(f"  生成モード: {mode_name}")
        logger.info(f"  処理チャンク数: {len(chunks)}")

        if use_celery:
            return self._generate_with_celery(
                chunks, celery_workers, concurrency, batch_chunks, use_smart_generation
            )
        else:
            return self._generate_sync(chunks, batch_chunks, use_smart_generation)

    def _generate_with_celery(self, chunks: List[Dict],
                              workers: int,
                              concurrency: int,
                              batch_size: int,
                              use_smart_generation: bool) -> List[Dict]:
        """Celeryを使用した非同期生成

        Args:
            chunks: チャンクのリスト
            workers: ワーカープロセス数チェック用
            concurrency: 並列タスク数
            batch_size: バッチサイズ
            use_smart_generation: スマートQ/A生成を使用するか
        """
        logger.info(f"  Celery並列処理モード:")
        logger.info(f"    - ワーカープロセス数チェック: {workers}")
        logger.info(f"    - 並列タスク数 (concurrency): {concurrency}")

        logger.info("  Celeryワーカーの状態を確認中...")
        if not check_celery_workers(workers):
            raise RuntimeError("Celery workers are not running")

        # use_smart_generationをCeleryタスクに渡す
        tasks = submit_unified_qa_generation(
            chunks, self.config, self.model, provider="openai",  # [MIGRATION] "anthropic" → "openai"
            use_smart_generation=use_smart_generation
        )

        timeout_seconds = min(max(len(tasks) * 10, 600), 1800)
        logger.info(f"  結果収集タイムアウト: {timeout_seconds}秒（{len(tasks)}タスク）")
        return collect_results(tasks, timeout=timeout_seconds)

    def _generate_sync(self, chunks: List[Dict], batch_size: int,
                       use_smart_generation: bool) -> List[Dict]:
        """同期生成（SmartQAGenerator使用）

        Args:
            chunks: チャンクのリスト
            batch_size: バッチサイズ（現在は未使用、将来の拡張用）
            use_smart_generation: スマートQ/A生成を使用するか（常にTrue推奨）

        Returns:
            Q/Aペアのリスト
        """
        logger.info("  通常処理モード（SmartQAGenerator使用）")

        all_qa_pairs = []
        total = len(chunks)

        for i, chunk in enumerate(chunks, 1):
            chunk_text = chunk.get('text', '')
            chunk_id = chunk.get('id', f'chunk_{i}')

            if not chunk_text.strip():
                logger.warning(f"    [{i}/{total}] 空のチャンクをスキップ: {chunk_id}")
                continue

            logger.info(f"    [{i}/{total}] 処理中: {chunk_id}")

            try:
                # SmartQAGeneratorでQ/A生成
                result = self.smart_generator.process_chunk(chunk_text)

                if result['success'] and result['qa_pairs']:
                    for qa in result['qa_pairs']:
                        all_qa_pairs.append({
                            'question': qa['question'],
                            'answer': qa['answer'],
                            'chunk_id': chunk_id,
                            'topic': qa.get('topic', ''),
                            'dataset_type': chunk.get('dataset_type', 'unknown')
                        })
                    logger.info(f"      → {len(result['qa_pairs'])} Q/A生成")
                else:
                    logger.warning(f"      → Q/A生成なし（qa_count=0 または失敗）")

            except Exception as e:
                logger.error(f"      → エラー: {e}")
                continue

        logger.info(f"  ✅ 同期生成完了: {len(all_qa_pairs)} Q/Aペア")
        return all_qa_pairs

    def evaluate_coverage(self, chunks: List[Dict], qa_pairs: List[Dict],
                          threshold: Optional[float] = None) -> Dict:
        """カバレッジを評価する"""
        logger.info("\n[追加] カバレージ分析...")
        dataset_type = self.config.get("type", "unknown")
        return analyze_coverage(chunks, qa_pairs, dataset_type, custom_threshold=threshold)

    def save(self, qa_pairs: List[Dict], coverage_results: Dict) -> Dict[str, str]:
        """結果を保存する"""
        from qa_generation.data_io import save_results

        logger.info("\n結果を保存中...")
        dataset_type = self.config.get("type", "unknown")
        return save_results(qa_pairs, coverage_results, dataset_type, self.output_dir)

    def run(
            self,
            use_celery: bool = False,
            celery_workers: int = 1,
            concurrency: int = 8,
            batch_chunks: int = 3,
            analyze_coverage: bool = True,
            coverage_threshold: Optional[float] = None,
            use_smart_generation: bool = True):
        """
        パイプライン実行

        Args:
            use_celery: Celery並列処理を使用するか
            celery_workers: Celeryワーカープロセス数チェック用（デフォルト: 1）
            concurrency: 並列タスク数（デフォルト: 8）
            batch_chunks: 1回のAPIで処理するチャンク数
            analyze_coverage: カバレージ分析を実行するか
            coverage_threshold: カバレージ判定の類似度閾値
            use_smart_generation: スマートQ/A生成を使用するか（デフォルト: True）

        Returns:
            Dict: 実行結果
                - saved_files: 保存されたファイルパス
                - qa_count: 生成されたQ/Aペア数
                - coverage_results: カバレージ分析結果
                - success: 成功フラグ
        """
        try:
            # ================================================================
            # パイプライン開始
            # ================================================================
            logger.info("=" * 60)
            logger.info("Q/A生成パイプライン（チャンク済みCSV専用）")
            logger.info("=" * 60)

            # ================================================================
            # データ読み込み
            # ================================================================
            df = self.load_data()

            # ================================================================
            # チャンクリストに変換
            # ================================================================
            chunks = self._load_chunks_from_csv(df)

            if not chunks:
                raise RuntimeError("有効なチャンクがありません")

            # ================================================================
            # Q/A生成
            # ================================================================
            qa_pairs = self.generate_qa(
                chunks,
                use_celery,
                celery_workers,
                concurrency,
                batch_chunks,
                use_smart_generation
            )

            if not qa_pairs:
                logger.warning("Q/Aペアが生成されませんでした")

            # ================================================================
            # カバレージ分析
            # ================================================================
            coverage_results = {}
            if analyze_coverage and qa_pairs:
                coverage_results = self.evaluate_coverage(chunks, qa_pairs, coverage_threshold)
            else:
                coverage_results = {
                    "coverage_rate"   : 0,
                    "covered_chunks"  : 0,
                    "total_chunks"    : len(chunks),
                    "uncovered_chunks": []
                }

            # ================================================================
            # 結果保存
            # ================================================================
            saved_files = self.save(qa_pairs, coverage_results)

            # ================================================================
            # 完了サマリー
            # ================================================================
            logger.info("")
            logger.info("=" * 60)
            logger.info("✅ パイプライン完了")
            logger.info("=" * 60)
            logger.info(f"  入力チャンク数: {len(chunks)}")
            logger.info(f"  生成Q/A数: {len(qa_pairs)}")
            if analyze_coverage:
                logger.info(f"  カバレージ率: {coverage_results.get('coverage_rate', 0):.1%}")
            logger.info("=" * 60)

            # 返り値
            return {
                "saved_files"     : saved_files,
                "qa_count"        : len(qa_pairs),
                "coverage_results": coverage_results,
                "success"         : True
            }

        except Exception as e:
            logger.error(f"パイプライン実行エラー: {e}")
            raise
