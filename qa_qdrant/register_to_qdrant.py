#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
register_to_qdrant.py - CSVデータをQdrantに登録する統合CLIツール
================================================================
register_csv_to_qdrant.py と register_qdrant.py を統合した最終版

主な機能:
- Q/AペアCSV、汎用CSVの両対応
- ファイル名の正規化（日時サフィックス除去）
- UI用CSV自動生成
- 柔軟なベクトル化対象カラム指定
- バッチ処理によるスケーラブルな登録

使用例:
    # 基本的な使い方
    python register_to_qdrant.py \
      --input-file qa_output/qa_pairs.csv \
      --collection my_collection \
      --recreate

    # フル機能
    python register_to_qdrant.py \
      --input-file qa_output/pipeline/qa_pairs_fineweb_edu_ja_20251230_123456.csv \
      --collection qa_fineweb_edu_ja \
      --recreate \
      --batch-size 100 \
      --normalize-filename \
      --create-ui-csv \
      --ui-output-dir qa_output

    # テスト用
    python register_to_qdrant.py \
      --input-file test.csv \
      --collection test \
      --max-docs 10
"""

import sys
import os

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
import re
import pandas as pd
from typing import List, Optional

# プロジェクト内モジュール
from services.qdrant_service import (
    create_or_recreate_collection_for_qdrant,
    embed_texts_for_qdrant,
    upsert_points_to_qdrant,
    build_points_for_qdrant
)
from qdrant_client_wrapper import create_qdrant_client

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def normalize_source_filename(filename: str) -> str:
    """
    ファイル名から日時サフィックス（例: _20251230_232641）を除去して正規化する。

    Args:
        filename: 元のファイル名

    Returns:
        str: 正規化されたファイル名

    Example:
        normalize_source_filename("qa_pairs_fineweb_edu_ja_20251230_123456.csv")
        'qa_pairs_fineweb_edu_ja.csv'
    """
    normalized = re.sub(r'_\d{8}_\d{6}', '', filename)
    return normalized


def detect_text_column(df: pd.DataFrame, text_col: Optional[str] = None) -> tuple[List[str], str]:
    """
    ベクトル化対象のテキストを自動検出する。

    優先順位:
    1. --text-col で指定されたカラム
    2. question + answer の結合
    3. Combined_Text
    4. text

    Args:
        df: 入力DataFrame
        text_col: 明示的に指定されたカラム名（オプション）

    Returns:
        tuple: (texts: List[str], detection_method: str)

    Raises:
        ValueError: ベクトル化対象カラムが見つからない場合
    """
    # ケース1: 明示的に指定されたカラム
    if text_col:
        if text_col not in df.columns:
            raise ValueError(
                f"指定されたカラム '{text_col}' がCSVに存在しません。\n"
                f"存在するカラム: {list(df.columns)}"
            )
        texts = df[text_col].astype(str).tolist()
        return texts, f"指定カラム '{text_col}'"

    # ケース2: question + answer
    if 'question' in df.columns and 'answer' in df.columns:
        texts = (df['question'].astype(str) + "\n" + df['answer'].astype(str)).tolist()
        return texts, "'question' + 'answer' の結合"

    # ケース3: Combined_Text
    if 'Combined_Text' in df.columns:
        texts = df['Combined_Text'].astype(str).tolist()
        return texts, "'Combined_Text' カラム"

    # ケース4: text
    if 'text' in df.columns:
        texts = df['text'].astype(str).tolist()
        return texts, "'text' カラム"

    # どれにも該当しない場合
    raise ValueError(
        "ベクトル化対象のカラムを特定できませんでした。\n"
        "以下のいずれかが必要です:\n"
        "  - --text-col で明示的に指定\n"
        "  - 'question' と 'answer' カラム\n"
        "  - 'Combined_Text' カラム\n"
        "  - 'text' カラム\n"
        f"現在のカラム: {list(df.columns)}"
    )


def register_to_qdrant(
        input_file: str,
        collection_name: str,
        recreate: bool = False,
        batch_size: int = 100,
        text_col: Optional[str] = None,
        domain: Optional[str] = None,
        max_docs: Optional[int] = None,
        provider: str = "gemini",
        normalize_filename: bool = True,
        create_ui_csv: bool = True,
        ui_output_dir: str = "qa_output"
) -> bool:
    """
    CSVファイルをQdrantコレクションに登録するメイン処理。

    Args:
        input_file: 入力CSVファイルパス
        collection_name: Qdrantコレクション名
        recreate: コレクションを再作成するか
        batch_size: Embeddingバッチサイズ
        text_col: ベクトル化対象カラム（None=自動検出）
        domain: ペイロードのdomain値（None=collection名）
        max_docs: 登録する最大件数（None=全件）
        provider: Embeddingプロバイダー
        normalize_filename: ファイル名正規化を行うか
        create_ui_csv: UI用CSVを生成するか
        ui_output_dir: UI用CSVの出力先

    Returns:
        bool: 成功時True、失敗時False
    """
    # ================================================================
    # 1. 入力検証
    # ================================================================
    if not os.path.exists(input_file):
        logger.error(f"❌ 入力ファイルが見つかりません: {input_file}")
        return False

    # ================================================================
    # 2. CSV読み込み
    # ================================================================
    logger.info(f"📁 ファイル読み込み中: {input_file}")
    try:
        df = pd.read_csv(input_file)
        logger.info(f"   ✅ 読み込み完了: {len(df)} 行")
        logger.info(f"   📋 カラム: {list(df.columns)}")
    except Exception as e:
        logger.error(f"❌ ファイル読み込みエラー: {e}")
        return False

    # 件数制限の適用
    if max_docs and len(df) > max_docs:
        df = df.head(max_docs)
        logger.info(f"   ⚠️  {max_docs} 件に制限しました（テストモード）")

    # ================================================================
    # 3. ベクトル化対象テキストの決定
    # ================================================================
    try:
        texts, detection_method = detect_text_column(df, text_col)
        logger.info(f"📝 ベクトル化対象: {detection_method}")
    except ValueError as e:
        logger.error(f"❌ {e}")
        return False

    # ================================================================
    # 4. Qdrantクライアント初期化 & コレクション準備
    # ================================================================
    logger.info(f"🔌 Qdrant接続中...")
    try:
        client = create_qdrant_client()

        if recreate:
            logger.info(f"🗑️  コレクション '{collection_name}' を再作成します...")
            create_or_recreate_collection_for_qdrant(client, collection_name, recreate=True)
        else:
            collections = client.get_collections()
            exists = any(c.name == collection_name for c in collections.collections)

            if not exists:
                logger.info(f"🆕 コレクション '{collection_name}' を新規作成します...")
                create_or_recreate_collection_for_qdrant(client, collection_name, recreate=False)
            else:
                logger.info(f"ℹ️  既存のコレクション '{collection_name}' に追記します")

    except Exception as e:
        logger.error(f"❌ Qdrant接続エラー: {e}")
        logger.error("   Dockerコンテナが起動しているか確認してください:")
        logger.error("   docker-compose up -d")
        return False

    # ================================================================
    # 5. バッチ処理による登録
    # ================================================================
    total_processed = 0
    domain_val = domain if domain else collection_name

    # ファイル名の処理
    source_filename = os.path.basename(input_file)
    if normalize_filename:
        normalized_filename = normalize_source_filename(source_filename)
        logger.info(f"📎 ファイル名正規化: {source_filename} → {normalized_filename}")
    else:
        normalized_filename = source_filename

    logger.info(f"\n{'=' * 60}")
    logger.info(f"🚀 登録処理開始")
    logger.info(f"{'=' * 60}")
    logger.info(f"   全件数       : {len(df)} 件")
    logger.info(f"   バッチサイズ : {batch_size}")
    logger.info(f"   プロバイダー : {provider}")
    logger.info(f"{'=' * 60}\n")

    try:
        for i in range(0, len(df), batch_size):
            end_idx = min(i + batch_size, len(df))
            batch_df = df.iloc[i:end_idx]
            batch_texts = texts[i:end_idx]

            # A. ベクトル化
            vectors = embed_texts_for_qdrant(batch_texts)

            if not vectors:
                logger.warning(f"   ⚠️  Batch {i}-{end_idx}: ベクトル生成失敗（スキップ）")
                continue

            # B. ポイント構築
            points = build_points_for_qdrant(
                batch_df,
                vectors,
                domain=domain_val,
                source_file=normalized_filename,
                start_index=i
            )

            # C. メタデータの追加
            for point in points:
                # source情報を確実に設定
                if "source" not in point.payload:
                    point.payload["source"] = normalized_filename

                # Embeddingメタデータ
                point.payload["embedding_provider"] = provider
                if provider == "gemini":
                    point.payload["embedding_model"] = "gemini-embedding-001"
                elif provider == "openai":
                    point.payload["embedding_model"] = "text-embedding-3-small"

            # D. Qdrantへアップサート
            upsert_points_to_qdrant(client, collection_name, points)

            total_processed += len(points)
            logger.info(f"   ✅ 進捗: {total_processed:,} / {len(df):,} 件完了 ({total_processed / len(df) * 100:.1f}%)")

    except KeyboardInterrupt:
        logger.warning("\n⚠️  処理が中断されました。")
        return False
    except Exception as e:
        logger.error(f"\n❌ 登録中にエラー発生: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ================================================================
    # 6. UI用CSV生成（オプション）
    # ================================================================
    if create_ui_csv:
        try:
            os.makedirs(ui_output_dir, exist_ok=True)
            output_path = os.path.join(ui_output_dir, normalized_filename)

            logger.info(f"\n📋 UI用ファイル作成中: {output_path}")

            # question/answerカラムが存在する場合のみ作成
            if 'question' in df.columns and 'answer' in df.columns:
                df_ui = df[['question', 'answer']].copy()
                df_ui.to_csv(output_path, index=False, encoding='utf-8')
                logger.info(f"   ✅ 作成完了 ({len(df_ui):,} 行)")
            else:
                logger.warning(f"   ⚠️  'question', 'answer' カラムが見つからないためスキップ")

        except Exception as e:
            logger.warning(f"   ⚠️  UI用ファイル作成エラー: {e}")

    # ================================================================
    # 7. 完了メッセージ
    # ================================================================
    logger.info(f"\n{'=' * 60}")
    logger.info(f"🎉 登録完了！")
    logger.info(f"{'=' * 60}")
    logger.info(f"   コレクション : {collection_name}")
    logger.info(f"   登録件数     : {total_processed:,} 件")
    logger.info(f"   プロバイダー : {provider}")
    if create_ui_csv and 'question' in df.columns and 'answer' in df.columns:
        logger.info(f"   UI用CSV      : {os.path.join(ui_output_dir, normalized_filename)}")
    logger.info(f"{'=' * 60}\n")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="CSVデータをQdrantに登録・インデックス化する統合ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
    # 基本的な使い方
    python register_to_qdrant.py \\
      --input-file qa_output/qa_pairs.csv \\
      --collection my_collection \\
      --recreate

    # フル機能を使う場合
    python register_to_qdrant.py \\
      --input-file qa_output/pipeline/qa_pairs_fineweb_edu_ja_20251230_123456.csv \\
      --collection qa_fineweb_edu_ja \\
      --recreate \\
      --batch-size 100 \\
      --normalize-filename \\
      --create-ui-csv \\
      --ui-output-dir qa_output

    # テスト用（少量データで動作確認）
    python register_to_qdrant.py \\
      --input-file test_data.csv \\
      --collection test_collection \\
      --max-docs 10 \\
      --batch-size 5
        """
    )

    # ================================================================
    # 必須引数
    # ================================================================
    required = parser.add_argument_group('必須引数')
    required.add_argument(
        "--input-file",
        type=str,
        required=True,
        help="登録するCSVファイルのパス"
    )
    required.add_argument(
        "--collection",
        type=str,
        required=True,
        help="登録先のQdrantコレクション名"
    )

    # ================================================================
    # Qdrant設定
    # ================================================================
    qdrant_group = parser.add_argument_group('Qdrant設定')
    qdrant_group.add_argument(
        "--recreate",
        action="store_true",
        help="既存の同名コレクションを削除して作り直す"
    )
    qdrant_group.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="1回のEmbedding API呼び出し/登録処理で扱う件数（デフォルト: 100）"
    )

    # ================================================================
    # ベクトル化設定
    # ================================================================
    vector_group = parser.add_argument_group('ベクトル化設定')
    vector_group.add_argument(
        "--text-col",
        type=str,
        default=None,
        help="ベクトル化対象のカラム名（未指定時は自動検出）"
    )
    vector_group.add_argument(
        "--provider",
        type=str,
        default="gemini",
        choices=["gemini", "openai"],
        help="Embeddingに使用するプロバイダー（デフォルト: gemini）"
    )

    # ================================================================
    # データ処理設定
    # ================================================================
    data_group = parser.add_argument_group('データ処理設定')
    data_group.add_argument(
        "--domain",
        type=str,
        default=None,
        help="ペイロードの 'domain' フィールドに設定する値（デフォルト: コレクション名）"
    )
    data_group.add_argument(
        "--max-docs",
        type=int,
        default=None,
        help="登録する最大ドキュメント数（テスト用）"
    )

    # ================================================================
    # 出力設定
    # ================================================================
    output_group = parser.add_argument_group('出力設定')
    output_group.add_argument(
        "--normalize-filename",
        action="store_true",
        default=True,
        help="ファイル名から日時サフィックスを除去（デフォルト: True）"
    )
    output_group.add_argument(
        "--no-normalize-filename",
        dest="normalize_filename",
        action="store_false",
        help="ファイル名正規化を無効化"
    )
    output_group.add_argument(
        "--create-ui-csv",
        action="store_true",
        default=True,
        help="UI用正規化CSVを生成（デフォルト: True）"
    )
    output_group.add_argument(
        "--no-create-ui-csv",
        dest="create_ui_csv",
        action="store_false",
        help="UI用CSV生成を無効化"
    )
    output_group.add_argument(
        "--ui-output-dir",
        type=str,
        default="qa_output",
        help="UI用CSVの出力ディレクトリ（デフォルト: qa_output）"
    )

    args = parser.parse_args()

    # ================================================================
    # APIキー確認
    # ================================================================
    if args.provider == "gemini" and not os.getenv("GOOGLE_API_KEY"):
        logger.error("❌ GOOGLE_API_KEY環境変数が設定されていません。")
        sys.exit(1)

    if args.provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        logger.error("❌ OPENAI_API_KEY環境変数が設定されていません。")
        sys.exit(1)

    # ================================================================
    # 実行
    # ================================================================
    success = register_to_qdrant(
        input_file=args.input_file,
        collection_name=args.collection,
        recreate=args.recreate,
        batch_size=args.batch_size,
        text_col=args.text_col,
        domain=args.domain,
        max_docs=args.max_docs,
        provider=args.provider,
        normalize_filename=args.normalize_filename,
        create_ui_csv=args.create_ui_csv,
        ui_output_dir=args.ui_output_dir
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

