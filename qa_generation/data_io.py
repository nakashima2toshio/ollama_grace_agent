#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qa_generation/data_io.py - データ入出力モジュール
"""

import logging
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from config import DATASET_CONFIGS
from helper.helper_rag import clean_text

logger = logging.getLogger(__name__)

def load_uploaded_file(file_path: str) -> pd.DataFrame:
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")

    file_extension = file_path_obj.suffix.lower().lstrip('.')
    logger.info(f"ローカルファイル読み込み中: {file_path} (形式: {file_extension})")

    try:
        if file_extension == 'csv':
            df = pd.read_csv(file_path)
        elif file_extension in ['txt', 'text']:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            df = pd.DataFrame({'text': lines})
        elif file_extension == 'json':
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, dict):
                df = pd.DataFrame([data])
            else:
                raise ValueError("JSONファイルはリストまたはオブジェクトである必要があります")
        elif file_extension == 'jsonl':
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [json.loads(line) for line in f if line.strip()]
            df = pd.DataFrame(lines)
        else:
            raise ValueError(f"未対応のファイル形式: {file_extension}")

        if 'Combined_Text' not in df.columns:
            text_candidates = ['text', 'content', 'body', 'document', 'answer', 'question']
            found_field = None
            for field in text_candidates:
                if field in df.columns:
                    found_field = field
                    break
            if found_field:
                df['Combined_Text'] = df[found_field].apply(
                    lambda x: clean_text(str(x)) if x is not None else ""
                )
            else:
                df['Combined_Text'] = df.apply(
                    lambda row: " ".join([str(v) for v in row.values if v is not None]),
                    axis=1
                )

        df = df[df['Combined_Text'].str.strip() != '']
        df = df.reset_index(drop=True)
        return df

    except Exception as e:
        logger.error(f"ファイル読み込みエラー: {e}")
        raise

def load_preprocessed_data(dataset_type: str) -> pd.DataFrame:
    config = DATASET_CONFIGS.get(dataset_type)
    if not config:
        raise ValueError(f"未対応のデータセット: {dataset_type}")

    file_path = config["file"]
    file_path_obj = Path(file_path)

    if not file_path_obj.exists():
        base_name = file_path_obj.stem
        extension = file_path_obj.suffix
        pattern = f"{base_name}_*{extension}"
        output_dir = file_path_obj.parent
        matching_files = list(output_dir.glob(pattern))

        if not matching_files:
            raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")

        matching_files.sort(key=lambda x: x.name)
        file_path = str(matching_files[-1])
        logger.info(f"タイムスタンプ付きファイルを自動選択: {Path(file_path).name}")

    logger.info(f"データ読み込み中: {file_path}")
    df = pd.read_csv(file_path)
    text_col = config["text_column"]
    if text_col not in df.columns:
        raise ValueError(f"テキストカラム '{text_col}' が見つかりません")
    df = df[df[text_col].notna() & (df[text_col].str.strip() != '')]
    return df

def save_results(
    qa_pairs: List[Dict],
    coverage_results: Dict,
    dataset_type: str,
    output_dir: str = "qa_output/a02"
) -> Dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    qa_file = output_path / f"qa_pairs_{dataset_type}_{timestamp}.json"
    with open(qa_file, 'w', encoding='utf-8') as f:
        json.dump(qa_pairs, f, ensure_ascii=False, indent=2)

    qa_csv_file = output_path / f"qa_pairs_{dataset_type}_{timestamp}.csv"
    qa_df = pd.DataFrame(qa_pairs)
    qa_df.to_csv(qa_csv_file, index=False, encoding='utf-8')

    coverage_file = output_path / f"coverage_{dataset_type}_{timestamp}.json"
    coverage_save = coverage_results.copy()
    if 'uncovered_chunks' in coverage_save:
        coverage_save['uncovered_chunks'] = [
            {
                'chunk_id': uc['chunk'].get('id', ''),
                'similarity': uc['similarity'],
                'gap': uc['gap'],
                'text_preview': uc['chunk']['text'][:200] + '...'
            }
            for uc in coverage_save.get('uncovered_chunks', [])
        ]
    with open(coverage_file, 'w', encoding='utf-8') as f:
        json.dump(coverage_save, f, ensure_ascii=False, indent=2)

    dataset_name = DATASET_CONFIGS.get(dataset_type, {}).get("name", dataset_type)
    summary = {
        "dataset_type": dataset_type,
        "dataset_name": dataset_name,
        "generated_at": timestamp,
        "total_qa_pairs": len(qa_pairs),
        "coverage_rate": coverage_results.get('coverage_rate', 0),
        "files": {
            "qa_json": str(qa_file),
            "qa_csv": str(qa_csv_file),
            "coverage": str(coverage_file)
        }
    }
    summary_file = output_path / f"summary_{dataset_type}_{timestamp}.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return {
        "qa_json": str(qa_file),
        "qa_csv": str(qa_csv_file),
        "coverage": str(coverage_file),
        "summary": str(summary_file)
    }
