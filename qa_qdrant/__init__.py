#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
make_qa.py - Q/Aペア生成 CLIエントリーポイント（改修版）
チャンクCSV読み込み機能を追加

🔧 qa_qdrant/ ディレクトリ配下に移動後の修正版
"""

import sys
import os

# 🔧 プロジェクトルートをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
from qa_generation.pipeline import QAPipeline
from config import DATASET_CONFIGS

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 🔧 プロジェクトルートの絶対パスを取得
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(
        description="make_qa.py - Q/Aペア自動生成システム (チャンクCSV対応)"
    )

    # ================================================================
    # 入力ソース（排他的）
    # ================================================================
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--dataset",
        type=str,
        choices=list(DATASET_CONFIGS.keys()),
        help="処理するデータセット"
    )
    input_group.add_argument(
        "--input-file",
        type=str,
        help="ローカルテキスト/CSVファイルのパス"
    )
    input_group.add_argument(
        "--input-chunks",
        type=str,
        help="事前作成されたチャンクCSVファイルのパス"
    )

    # ================================================================
    # 共通パラメータ
    # ================================================================
    # 🔧 デフォルト出力パスを絶対パスに変更
    default_output = os.path.join(PROJECT_ROOT, "qa_output", "pipeline")

    parser.add_argument(
        "--model",
        type=str,
        default="gemini-2.0-flash",
        help="使用するGeminiモデル"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=default_output,  # 🔧 絶対パス
        help=f"出力ディレクトリ (デフォルト: {default_output})"
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=None,
        help="処理する最大文書数"
    )
    parser.add_argument(
        "--analyze-coverage",
        action="store_true",
        help="カバレージ分析を実行"
    )

    # ================================================================
    # Q/A生成パラメータ
    # ================================================================
    parser.add_argument(
        "--batch-chunks",
        type=int,
        default=3,
        choices=[1, 2, 3, 4, 5],
        help="1回のAPIで処理するチャンク数"
    )
    parser.add_argument(
        "--merge-chunks",
        action="store_true",
        default=True,
        help="小さいチャンクを統合する"
    )
    parser.add_argument(
        "--no-merge-chunks",
        dest="merge_chunks",
        action="store_false",
        help="チャンク統合を無効化"
    )
    parser.add_argument(
        "--min-tokens",
        type=int,
        default=150,
        help="統合対象の最小トークン数"
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=400,
        help="統合後の最大トークン数"
    )

    # ================================================================
    # Celery並列処理
    # ================================================================
    parser.add_argument(
        "--use-celery",
        action="store_true",
        help="Celeryによる非同期並列処理を使用"
    )
    parser.add_argument(
        "--celery-workers",
        type=int,
        default=8,
        help="Celeryワーカー数"
    )

    # ================================================================
    # チャンク作成パラメータ（--input-chunksの場合は無視される）
    # ================================================================
    parser.add_argument(
        "--coverage-threshold",
        type=float,
        default=None,
        help="カバレージ判定の類似度閾値"
    )
    parser.add_argument(
        "--overlap-tokens",
        type=int,
        default=0,
        help="チャンク間の重複トークン数"
    )
    parser.add_argument(
        "--use-similarity",
        action="store_true",
        help="ベクトル類似度によるセマンティック分割を使用"
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.7,
        help="セマンティック分割の類似度閾値"
    )

    args = parser.parse_args()

    # APIキー確認
    if not os.getenv("GOOGLE_API_KEY"):
        logger.error("GOOGLE_API_KEYが設定されていません")
        sys.exit(1)

    # ================================================================
    # ✅ 改修ポイント: input_chunks のログ表示
    # ================================================================
    if args.input_chunks:
        logger.info("")
        logger.info("=" * 60)
        logger.info("モード: チャンクCSV読み込み")
        logger.info("=" * 60)
        logger.info(f"チャンクCSV: {args.input_chunks}")
        logger.info("注意: チャンク作成パラメータ(--overlap-tokens等)は無視されます")
        logger.info("=" * 60)

    try:
        # ================================================================
        # パイプラインの初期化
        # ================================================================
        pipeline = QAPipeline(
            dataset_name=args.dataset,
            input_file=args.input_file,
            # input_chunks=args.input_chunks,
            model=args.model,
            output_dir=args.output,
            max_docs=args.max_docs
        )

        # ================================================================
        # パイプラインの実行
        # ================================================================
        result = pipeline.run(
            use_celery=args.use_celery,
            celery_workers=args.celery_workers,
            batch_chunks=args.batch_chunks,
            # merge_chunks=args.merge_chunks,
            # min_tokens=args.min_tokens,
            # max_tokens=args.max_tokens,
            analyze_coverage=args.analyze_coverage,
            coverage_threshold=args.coverage_threshold,
            # overlap_tokens=args.overlap_tokens,
            # use_similarity=args.use_similarity,
            # similarity_threshold=args.similarity_threshold
        )

        # ================================================================
        # 結果表示
        # ================================================================
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ Make QA 完了")
        logger.info("=" * 60)
        logger.info(f"サマリーファイル: {result['saved_files']['summary']}")
        logger.info(f"生成Q/A数: {result['qa_count']}")
        if args.analyze_coverage:
            logger.info(f"カバレージ率: {result['coverage_results'].get('coverage_rate', 0):.1%}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"実行中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
