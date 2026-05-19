#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
file_service.py - ファイル操作サービス
======================================
ファイルの読み込み、保存、履歴管理を担当

機能:
- Q/A出力履歴の取得
- 前処理済みデータ履歴の取得
- ファイル保存（OUTPUT, qa_output）
- サンプルデータの読み込み
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from config import DATASET_CONFIGS
from services.qdrant_service import map_collection_to_csv

logger = logging.getLogger(__name__)


def load_qa_output_history() -> pd.DataFrame:
    """
    qa_output/フォルダから最新のQ&AペアCSVファイル一覧を取得

    Returns:
        ファイル情報のDataFrame
    """
    qa_output_dir = Path("qa_output")

    if not qa_output_dir.exists():
        return pd.DataFrame(columns=["ファイル名", "ファイルサイズ", "作成日付"])

    # CSVファイルを全て取得
    csv_files = list(qa_output_dir.glob("*.csv"))

    if not csv_files:
        return pd.DataFrame(columns=["ファイル名", "ファイルサイズ", "作成日付"])

    history_data = []

    for csv_file in csv_files:
        try:
            # ファイル情報を取得
            file_stat = csv_file.stat()
            file_size = file_stat.st_size
            created_time = datetime.fromtimestamp(file_stat.st_mtime)

            # ファイルサイズを人間が読みやすい形式に変換
            if file_size < 1024:
                size_str = f"{file_size} B"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"

            history_data.append(
                {
                    "ファイル名": csv_file.name,
                    "ファイルサイズ": size_str,
                    "作成日付": created_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "_timestamp": created_time,  # ソート用
                }
            )

        except Exception as e:
            logger.error(f"ファイル情報取得エラー {csv_file}: {e}")
            continue

    # DataFrameに変換して日付でソート（昇順：古いものが上）
    df_history = pd.DataFrame(history_data)

    if not df_history.empty:
        df_history = df_history.sort_values("_timestamp", ascending=True)
        df_history = df_history.drop(columns=["_timestamp"])  # ソート用カラムを削除

    return df_history


def load_preprocessed_history() -> pd.DataFrame:
    """
    OUTPUT/フォルダから前処理済みCSVファイル一覧を取得
    Returns:
        ファイル情報のDataFrame
    """
    output_dir = Path("OUTPUT")

    if not output_dir.exists():
        return pd.DataFrame(
            columns=["ファイル名", "ファイルサイズ", "作成日付", "データセット名"]
        )

    # preprocessed_*.csvファイルを全て取得
    csv_files = list(output_dir.glob("preprocessed_*.csv"))

    if not csv_files:
        return pd.DataFrame(
            columns=["ファイル名", "ファイルサイズ", "作成日付", "データセット名"]
        )

    history_data = []

    for csv_file in csv_files:
        try:
            # ファイル情報を取得
            file_stat = csv_file.stat()
            file_size = file_stat.st_size
            created_time = datetime.fromtimestamp(file_stat.st_mtime)

            # ファイルサイズを人間が読みやすい形式に変換
            if file_size < 1024:
                size_str = f"{file_size} B"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"

            # データセット名を抽出（preprocessed_XXX.csv → XXX）
            dataset_name = csv_file.stem.replace("preprocessed_", "")

            history_data.append(
                {
                    "ファイル名": csv_file.name,
                    "データセット名": dataset_name,
                    "ファイルサイズ": size_str,
                    "作成日付": created_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "_timestamp": created_time,  # ソート用
                }
            )

        except Exception as e:
            logger.error(f"ファイル情報取得エラー {csv_file}: {e}")
            continue

    # DataFrameに変換して日付でソート（降順：新しいものが上）
    df_history = pd.DataFrame(history_data)

    if not df_history.empty:
        df_history = df_history.sort_values("_timestamp", ascending=False)
        df_history = df_history.drop(columns=["_timestamp"])  # ソート用カラムを削除

    return df_history


def save_to_output(df: pd.DataFrame, dataset_type: str) -> Dict[str, str]:
    """
    OUTPUTフォルダに保存

    Args:
        df: 保存するDataFrame（Combined_Textカラムを含む）
        dataset_type: データセットタイプ名

    Returns:
        保存されたファイルパスの辞書
    """
    output_dir = Path("OUTPUT")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_files = {}

    # CSVファイル
    csv_filename = f"preprocessed_{dataset_type}_{timestamp}.csv"
    csv_path = output_dir / csv_filename
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    saved_files["csv"] = str(csv_path)

    # テキストファイル
    txt_filename = f"{dataset_type}_{timestamp}.txt"
    txt_path = output_dir / txt_filename
    text_data = "\n".join(df["Combined_Text"].dropna().astype(str))
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text_data)
    saved_files["txt"] = str(txt_path)

    # メタデータ
    config = DATASET_CONFIGS.get(dataset_type, {})
    metadata = {
        "dataset_type": dataset_type,
        "dataset_name": config.get("name", dataset_type),
        "processed_at": datetime.now().isoformat(),
        "row_count": len(df),
        "csv_file": csv_filename,
        "txt_file": txt_filename,
    }
    json_filename = f"metadata_{dataset_type}_{timestamp}.json"
    json_path = output_dir / json_filename
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    saved_files["json"] = str(json_path)

    return saved_files


def load_sample_questions_from_csv(
    collection_name: str, num_samples: int = 3
) -> List[str]:
    """
    qa_output/からCSVファイルを読み込んで質問例を取得

    Args:
        collection_name: コレクション名
        num_samples: 取得する質問数

    Returns:
        質問のリスト
    """
    # コレクション名に対応するCSVファイルを取得
    csv_filename = map_collection_to_csv(collection_name)
    if not csv_filename:
        return []

    csv_path = Path("qa_output") / csv_filename
    if not csv_path.exists():
        return []

    try:
        df = pd.read_csv(csv_path)
        # questionカラムがあるか確認
        if "question" not in df.columns:
            return []

        # ランダムにサンプリング
        questions = df["question"].dropna().sample(min(num_samples, len(df))).tolist()
        return questions
    except Exception as e:
        logger.error(f"質問例の読み込みエラー {csv_path}: {e}")
        return []


def load_source_qa_data(
    source_filename: str, num_rows: int = 20
) -> Optional[pd.DataFrame]:
    """
    qa_output/*.csvからQ/Aデータを取得

    Args:
        source_filename: ソースファイル名（例: "a02_qa_pairs_cc_news.csv"）
        num_rows: 取得する行数（デフォルト: 20）

    Returns:
        question, answerカラムのDataFrame（上位num_rows行）、エラー時はNone
    """
    csv_path = Path("qa_output") / source_filename
    if not csv_path.exists():
        logger.warning(f"CSVファイルが存在しません: {csv_path}")
        return None

    try:
        # 効率的に最初のnum_rows行だけを読み込み
        df = pd.read_csv(csv_path, nrows=num_rows, usecols=["question", "answer"])

        # カラムの存在確認
        if "question" not in df.columns or "answer" not in df.columns:
            logger.error(
                f"CSVファイルに必要なカラム (question, answer) がありません: {csv_path}"
            )
            return None

        logger.info(f"ソースファイル読み込み成功: {csv_path} ({len(df)}行)")
        return df

    except Exception as e:
        logger.error(f"ソースファイル読み込みエラー {csv_path}: {e}")
        return None


def load_collection_qa_preview(
    collection_name: str, num_rows: int = 20
) -> Optional[pd.DataFrame]:
    """
    コレクションに対応するCSVファイルからQ/Aデータのプレビューを取得

    Args:
        collection_name: コレクション名
        num_rows: 取得する行数（デフォルト: 20）

    Returns:
        question, answerカラムのDataFrame（上位num_rows行）、エラー時はNone
    """
    # コレクション名に対応するCSVファイルを取得
    csv_filename = map_collection_to_csv(collection_name)
    if not csv_filename:
        logger.warning(
            f"コレクション '{collection_name}' に対応するCSVファイルが見つかりません"
        )
        return None

    csv_path = Path("qa_output") / csv_filename
    if not csv_path.exists():
        logger.warning(f"CSVファイルが存在しません: {csv_path}")
        return None

    try:
        # 効率的に最初のnum_rows行だけを読み込み
        df = pd.read_csv(csv_path, nrows=num_rows, usecols=["question", "answer"])

        # カラムの存在確認
        if "question" not in df.columns or "answer" not in df.columns:
            logger.error(
                f"CSVファイルに必要なカラム (question, answer) がありません: {csv_path}"
            )
            return None

        logger.info(f"CSVプレビュー読み込み成功: {csv_path} ({len(df)}行)")
        return df

    except Exception as e:
        logger.error(f"CSVプレビュー読み込みエラー {csv_path}: {e}")
        return None
