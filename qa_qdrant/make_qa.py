#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
make_qa.py - Q/Aペア生成 CLIエントリーポイント（v3.0 - pipeline.py v3.0対応版）

改修内容 (v3.0):
- pipeline.py v3.0（チャンク処理削除版）に対応
- --input-chunks 引数を削除（--input-file に統一）
- チャンク関連引数を削除（--merge-chunks, --min-tokens, --max-tokens, --overlap-tokens, --use-similarity, --similarity-threshold）
- -c, --concurrency 引数を追加
- --use-smart-generation / --no-smart-generation 引数を追加

前提条件:
- 入力CSVは既にチャンク済み（csv_text_to_chunks_text_csv.py で処理済み）

使用例:
  # チャンク済みCSVからQ/A生成（Celery並列処理）
  python qa_qdrant/make_qa.py \
    --input-file output_chunked/data_chunks.csv \
    --use-celery \
    -c 8 \
    --use-smart-generation \
    --analyze-coverage

  # 同期処理（Celery不使用）
  python qa_qdrant/make_qa.py \
    --input-file output_chunked/data_chunks.csv \
    --analyze-coverage

  # 事前定義データセットを使用
  python qa_qdrant/make_qa.py \
    --dataset wikipedia_ja \
    --use-celery \
    -c 4
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
        description="make_qa.py - Q/Aペア自動生成システム (v3.0 - チャンク済みCSV専用)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # チャンク済みCSVからQ/A生成（Celery並列処理）
  python qa_qdrant/make_qa.py \
    --input-file output_chunked/data_chunks.csv \
    --use-celery \
    -c 8 \
    --analyze-coverage

  # 同期処理（Celery不使用）
  python qa_qdrant/make_qa.py \
    --input-file output_chunked/data_chunks.csv \
    --analyze-coverage

注意:
  入力ファイルは事前にチャンク化されている必要があります。
  テキストファイルの場合は、先に csv_text_to_chunks_text_csv.py でチャンク化してください。
        """
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
        help="チャンク済みCSVファイルのパス"
    )

    # ================================================================
    # 共通パラメータ
    # ================================================================
    # 🔧 デフォルト出力パスを絶対パスに変更
    default_output = os.path.join(PROJECT_ROOT, "qa_output", "pipeline")

    parser.add_argument(
        "--model",
        type=str,
        default="gpt-5.4-mini",
        help="使用するLLMモデル（デフォルト: gpt-5.4-mini）"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=default_output,
        help=f"出力ディレクトリ（デフォルト: {default_output}）"
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=None,
        help="処理する最大チャンク数"
    )

    # ================================================================
    # カバレージ分析パラメータ
    # ================================================================
    parser.add_argument(
        "--analyze-coverage",
        action="store_true",
        help="カバレージ分析を実行"
    )
    parser.add_argument(
        "--coverage-threshold",
        type=float,
        default=None,
        help="カバレージ判定の類似度閾値"
    )

    # ================================================================
    # Q/A生成パラメータ
    # ================================================================
    parser.add_argument(
        "--batch-chunks",
        type=int,
        default=3,
        choices=[1, 2, 3, 4, 5],
        help="1回のAPIで処理するチャンク数（デフォルト: 3）"
    )
    parser.add_argument(
        "--use-smart-generation",
        action="store_true",
        default=True,
        help="スマートQ/A生成を使用（LLMによる動的Q/A数決定、デフォルト有効）"
    )
    parser.add_argument(
        "--no-smart-generation",
        dest="use_smart_generation",
        action="store_false",
        help="従来方式のQ/A生成を使用（トークン数ベース）"
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
        "-c", "--concurrency",
        type=int,
        default=8,
        help="並列タスク数（デフォルト: 8）。start_celery.sh -c と同じ値を推奨"
    )
    parser.add_argument(
        "--celery-workers",
        type=int,
        default=1,
        help="(非推奨) Celeryワーカープロセス数チェック用。--concurrency を使用してください"
    )

    args = parser.parse_args()

    # ================================================================
    # APIキー確認
    # ================================================================
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEYが設定されていません")
        sys.exit(1)

    # ================================================================
    # 入力ファイルの検証
    # ================================================================
    if args.input_file:
        if not os.path.exists(args.input_file):
            logger.error(f"入力ファイルが見つかりません: {args.input_file}")
            sys.exit(1)

        if not args.input_file.endswith('.csv'):
            logger.error("❌ CSVファイル以外は直接処理できません")
            logger.error("   テキストファイルの場合は、先に csv_text_to_chunks_text_csv.py でチャンク化してください")
            logger.error(
                "   例: python -m chunking.csv_text_to_chunks_text_csv --input-file data.txt --output output_chunked")
            sys.exit(1)

    # ================================================================
    # 設定ログ表示
    # ================================================================
    logger.info("")
    logger.info("=" * 60)
    logger.info("make_qa.py v3.0 - Q/Aペア生成")
    logger.info("=" * 60)

    if args.input_file:
        logger.info(f"入力ファイル: {args.input_file}")
    else:
        logger.info(f"データセット: {args.dataset}")

    logger.info(f"モデル: {args.model}")
    logger.info(f"出力ディレクトリ: {args.output}")

    if args.use_smart_generation:
        logger.info("Q/A生成モード: スマート生成（LLMによる動的Q/A数決定）")
    else:
        logger.info("Q/A生成モード: 従来方式（トークン数ベース）")

    if args.use_celery:
        logger.info(f"並列処理: Celery（並列タスク数: {args.concurrency}）")
    else:
        logger.info("並列処理: なし（同期処理）")

    logger.info("=" * 60)

    try:
        # ================================================================
        # パイプラインの初期化
        # ================================================================
        pipeline = QAPipeline(
            dataset_name=args.dataset,
            input_file=args.input_file,
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
            concurrency=args.concurrency,
            batch_chunks=args.batch_chunks,
            analyze_coverage=args.analyze_coverage,
            coverage_threshold=args.coverage_threshold,
            use_smart_generation=args.use_smart_generation
        )

        # ================================================================
        # 結果表示
        # ================================================================
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ Make QA 完了")
        logger.info("=" * 60)
        logger.info(f"サマリーファイル: {result['saved_files']['summary']}")
        logger.info(f"Q/A CSVファイル: {result['saved_files'].get('qa_csv', 'N/A')}")
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
