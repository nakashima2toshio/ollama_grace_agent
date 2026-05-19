# helper_rag.py
# RAGデータ前処理の共通機能（ロジックのみ）
# -----------------------------------------

import pandas as pd
import re
import io
import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime
from functools import wraps

# ===================================================================
# 基本ログ設定
# ===================================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================================================================
# 共通モジュールからインポート
# ===================================================================
from helper.helper_llm import create_llm_client, LLMClient, DEFAULT_LLM_PROVIDER
from helper.helper_embedding import create_embedding_client, EmbeddingClient, DEFAULT_EMBEDDING_PROVIDER, get_embedding_dimensions, get_embedding_model_pricing
from helper.helper_llm import get_llm_model_pricing
from helper.helper_text import clean_text


# ==================================================
# RAG設定クラス（全データセット対応）
# ==================================================
class RAGConfig:
    """RAGデータ前処理の設定（全データセット統合）"""

    DATASET_CONFIGS = {
        # カスタマーサポートFAQ
        "customer_support_faq": {
            "name"            : "カスタマーサポート・FAQ",
            "icon"            : "💬",
            "required_columns": ["question", "answer"],
            "description"     : "カスタマーサポートFAQデータセット",
            "combine_template": "{question} {answer}",
            "port"            : 8501
        },

        # 医療QA
        "medical_qa"          : {
            "name"            : "医療QAデータ",
            "icon"            : "🏥",
            "required_columns": ["Question", "Complex_CoT", "Response"],
            "description"     : "医療質問回答データセット",
            "combine_template": "{question} {complex_cot} {response}",
            "port"            : 8503
        },

        # 科学・技術QA
        "sciq_qa"             : {
            "name"            : "科学・技術QA（SciQ）",
            "icon"            : "🔬",
            "required_columns": ["question", "correct_answer"],
            "description"     : "科学・技術質問回答データセット",
            "combine_template": "{question} {correct_answer}",
            "port"            : 8504
        },

        # 法律・判例QA
        "legal_qa"            : {
            "name"            : "法律・判例QA",
            "icon"            : "⚖️",
            "required_columns": ["question", "answer"],
            "description"     : "法律・判例質問回答データセット",
            "combine_template": "{question} {answer}",
            "port"            : 8505
        },
        
        # TriviaQA
        "trivia_qa"           : {
            "name"            : "雑学QA（TriviaQA）",
            "icon"            : "🎯",
            "required_columns": ["question", "answer"],
            "description"     : "雑学質問回答データセット",
            "combine_template": "{question} {answer} {entity_pages} {search_results}",
            "port"            : 8506
        }
    }

    @classmethod
    def get_config(cls, dataset_type: str) -> Dict[str, Any]:
        """データセット設定の取得"""
        return cls.DATASET_CONFIGS.get(dataset_type, {
            "name"            : "未知のデータセット",
            "icon"            : "❓",
            "required_columns": [],
            "description"     : "未知のデータセット",
            "combine_template": "{}",
            "port"            : 8500
        })

    @classmethod
    def get_all_datasets(cls) -> List[str]:
        """全データセットタイプのリストを取得"""
        return list(cls.DATASET_CONFIGS.keys())

    @classmethod
    def get_dataset_by_port(cls, port: int) -> Optional[str]:
        """ポート番号からデータセットタイプを取得"""
        for dataset_type, config in cls.DATASET_CONFIGS.items():
            if config.get("port") == port:
                return dataset_type
        return None


# ==================================================
# トークン管理クラス（services/token_serviceから統合）
# ==================================================
# 後方互換性のため、services.token_serviceからimport
from services.token_service import TokenManager  # noqa: E402


# ==================================================
# エラーハンドリングデコレータ（共通）
# ==================================================
def safe_execute(func):
    """安全実行デコレータ（UI非依存）"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            # UIがないのでst.errorは削除
            return None

    return wrapper


# ==================================================
# データ処理関数群（共通）
# ==================================================
def combine_columns(row: pd.Series, dataset_type: str) -> str:
    """複数列を結合して1つのテキストにする（データセット対応）"""
    config_data = RAGConfig.get_config(dataset_type)
    required_columns = config_data["required_columns"]

    # 各列からテキストを抽出・クレンジング
    cleaned_values = []
    for col in required_columns:
        if col in row.index:
            value = row.get(col, '')
            cleaned_text = clean_text(str(value))
            if cleaned_text:  # 空でない場合のみ追加
                cleaned_values.append(cleaned_text)

    # 医療QAの特別処理（Question, Complex_CoT, Response）
    if dataset_type == "medical_qa":
        # 大文字小文字を考慮した列名マッピング
        medical_cols = {}
        for col in row.index:
            col_lower = col.lower()
            if 'question' in col_lower:
                medical_cols['question'] = clean_text(str(row.get(col, '')))
            elif 'complex_cot' in col_lower or 'cot' in col_lower:
                medical_cols['complex_cot'] = clean_text(str(row.get(col, '')))
            elif 'response' in col_lower:
                medical_cols['response'] = clean_text(str(row.get(col, '')))

        # 医療QA用の結合
        medical_values = [v for v in medical_cols.values() if v]
        if medical_values:
            return " ".join(medical_values).strip()

    # 結合
    combined = " ".join(cleaned_values)
    return combined.strip()


def validate_data(df: pd.DataFrame, dataset_type: str = None) -> List[str]:
    """データの検証"""
    issues = []

    # 基本統計
    issues.append(f"総行数: {len(df):,}")
    issues.append(f"総列数: {len(df.columns)}")

    # 必須列の確認
    if dataset_type:
        config_data = RAGConfig.get_config(dataset_type)
        required_columns = config_data["required_columns"]

        # 大文字小文字を考慮した列名チェック
        [col.lower() for col in df.columns]
        missing_columns = []
        found_columns = []

        for req_col in required_columns:
            req_col_lower = req_col.lower()
            # 部分一致も許可（例：Question -> question, Complex_CoT -> complex_cot）
            found = False
            for available_col in df.columns:
                if req_col_lower in available_col.lower() or available_col.lower() in req_col_lower:
                    found_columns.append(available_col)
                    found = True
                    break
            if not found:
                missing_columns.append(req_col)

        if missing_columns:
            issues.append(f"⚠️ 必須列が不足: {missing_columns}")
        else:
            issues.append(f"✅ 必須列確認済み: {found_columns}")

    # 各列の空値確認
    for col in df.columns:
        empty_count = df[col].isna().sum() + (df[col] == '').sum()
        if empty_count > 0:
            percentage = (empty_count / len(df)) * 100
            issues.append(f"{col}列: 空値 {empty_count:,}個 ({percentage:.1f}%)")

    # 重複行の確認
    duplicate_count = df.duplicated().sum()
    if duplicate_count > 0:
        issues.append(f"⚠️ 重複行: {duplicate_count:,}個")
    else:
        issues.append("✅ 重複行なし")

    return issues


@safe_execute
def load_dataset(uploaded_file, dataset_type: str = None) -> Tuple[pd.DataFrame, List[str]]:
    """データセットの読み込みと基本検証"""
    # CSVファイルの読み込み
    df = pd.read_csv(uploaded_file)

    # 基本検証
    validation_results = validate_data(df, dataset_type)

    logger.info(f"データセット読み込み完了: {len(df):,}行, {len(df.columns)}列")
    return df, validation_results


@safe_execute
def process_rag_data(df: pd.DataFrame, dataset_type: str, combine_columns_option: bool = True) -> pd.DataFrame:
    """RAGデータの前処理を実行"""
    # 基本的な前処理
    df_processed = df.copy()

    # 重複行の除去
    initial_rows = len(df_processed)
    df_processed = df_processed.drop_duplicates()
    duplicates_removed = initial_rows - len(df_processed)

    # 空行の除去（全列がNAの行）
    df_processed = df_processed.dropna(how='all')
    empty_rows_removed = initial_rows - duplicates_removed - len(df_processed)

    # インデックスのリセット
    df_processed = df_processed.reset_index(drop=True)

    logger.info(f"前処理完了: 重複除去={duplicates_removed:,}行, 空行除去={empty_rows_removed:,}行")

    # 各列のクレンジング（データセット対応）
    config_data = RAGConfig.get_config(dataset_type)
    required_columns = config_data["required_columns"]

    # 大文字小文字を考慮した列名処理
    for col in df_processed.columns:
        for req_col in required_columns:
            if req_col.lower() in col.lower() or col.lower() in req_col.lower():
                df_processed[col] = df_processed[col].apply(clean_text)

    # 列の結合（オプション）
    if combine_columns_option:
        df_processed['Combined_Text'] = df_processed.apply(
            lambda row: combine_columns(row, dataset_type),
            axis=1
        )

        # 空の結合テキストを除去
        before_filter = len(df_processed)
        df_processed = df_processed[df_processed['Combined_Text'].str.strip() != '']
        after_filter = len(df_processed)
        empty_combined_removed = before_filter - after_filter

        if empty_combined_removed > 0:
            logger.info(f"空の結合テキストを除去: {empty_combined_removed:,}行")

    return df_processed


@safe_execute
def create_download_data(df: pd.DataFrame, include_combined: bool = True, dataset_type: str = None) -> Tuple[
    str, Optional[str]]:
    """ダウンロード用データの作成"""
    # CSVデータの作成
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False, encoding='utf-8')
    csv_data = csv_buffer.getvalue()

    # 結合テキストデータの作成
    text_data = None
    if include_combined and 'Combined_Text' in df.columns:
        # インデックスなしで結合テキストのみを出力
        text_lines = []
        for text in df['Combined_Text']:
            if text and str(text).strip():
                text_lines.append(str(text).strip())
        text_data = '\n'.join(text_lines)

    return csv_data, text_data


# ==================================================
# ファイル保存関数群（共通）
# ==================================================
def create_output_directory() -> Path:
    """OUTPUTディレクトリの作成"""
    try:
        output_dir = Path("OUTPUT")
        output_dir.mkdir(exist_ok=True)

        # 書き込み権限のテスト
        test_file = output_dir / ".test_write"
        try:
            test_file.write_text("test", encoding='utf-8')
            if test_file.exists():
                test_file.unlink()
                logger.info("書き込み権限テスト: 成功")
        except Exception as e:
            raise PermissionError(f"書き込み権限テストに失敗: {e}")

        logger.info(f"OUTPUTディレクトリ準備完了: {output_dir.absolute()}")
        return output_dir

    except Exception as e:
        logger.error(f"ディレクトリ作成エラー: {e}")
        raise


@safe_execute
def save_files_to_output(df_processed, dataset_type: str, csv_data: str, text_data: str = None) -> Dict[str, str]:
    """処理済みデータをOUTPUTフォルダに保存"""
    output_dir = create_output_directory()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_files = {}

    # CSVファイルの保存
    csv_filename = f"preprocessed_{dataset_type}.csv"
    csv_path = output_dir / csv_filename

    with open(csv_path, 'w', encoding='utf-8') as f:
        f.write(csv_data)

    if csv_path.exists():
        saved_files['csv'] = str(csv_path)
        logger.info(f"CSVファイル保存完了: {csv_path}")

    # テキストファイルの保存
    if text_data and len(text_data.strip()) > 0:
        txt_filename = f"{dataset_type}.txt"
        txt_path = output_dir / txt_filename

        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(text_data)

        if txt_path.exists():
            saved_files['txt'] = str(txt_path)
            logger.info(f"テキストファイル保存完了: {txt_path}")

    # メタデータファイルの保存
    metadata = {
        "dataset_type"        : dataset_type,
        "processed_rows"      : len(df_processed),
        "processing_timestamp": timestamp,
        "created_at"          : datetime.now().isoformat(),
        "files_created"       : list(saved_files.keys()),
        "processing_info"     : {
            "original_rows": 0, # セッション状態依存を排除のため一旦0
            "removed_rows" : 0
        }
    }

    metadata_filename = f"metadata_{dataset_type}.json"
    metadata_path = output_dir / metadata_filename

    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    if metadata_path.exists():
        saved_files['metadata'] = str(metadata_path)
        logger.info(f"メタデータファイル保存完了: {metadata_path}")

    return saved_files


# ==================================================
# エクスポート（共通関数一覧）
# ==================================================
__all__ = [
    # 設定クラス
    'RAGConfig',
    'TokenManager',

    # デコレータ
    'safe_execute',

    # データ処理関数
    'clean_text',
    'combine_columns',
    'validate_data',
    'load_dataset',
    'process_rag_data',
    'create_download_data',

    # ファイル保存関数
    'create_output_directory',
    'save_files_to_output',
]