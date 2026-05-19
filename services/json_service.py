#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
json_service.py - JSON処理サービス
==================================
安全なJSONシリアライズ、ファイル読み書き

統合元:
- helper_api.py::safe_json_serializer
- helper_api.py::safe_json_dumps
- helper_api.py::load_json_file
- helper_api.py::save_json_file
"""

import json
import logging
from typing import Any, Dict, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


# ===================================================================
# JSONシリアライザー
# ===================================================================

def safe_json_serializer(obj: Any) -> Any:
    """
    カスタムJSONシリアライザー

    OpenAI APIのレスポンスオブジェクトなど、
    標準では処理できないオブジェクトを変換

    Args:
        obj: シリアライズ対象オブジェクト

    Returns:
        JSON互換形式に変換されたオブジェクト
    """
    # Pydantic モデルの場合
    if hasattr(obj, 'model_dump'):
        try:
            return obj.model_dump()
        except Exception:
            pass

    # dict() メソッドがある場合
    if hasattr(obj, 'dict'):
        try:
            return obj.dict()
        except Exception:
            pass

    # datetime オブジェクトの場合
    if isinstance(obj, datetime):
        return obj.isoformat()

    # OpenAI ResponseUsage オブジェクトの場合（手動属性抽出）
    if hasattr(obj, 'prompt_tokens') and hasattr(obj, 'completion_tokens'):
        return {
            'prompt_tokens': getattr(obj, 'prompt_tokens', 0),
            'completion_tokens': getattr(obj, 'completion_tokens', 0),
            'total_tokens': getattr(obj, 'total_tokens', 0)
        }

    # bytes オブジェクトの場合
    if isinstance(obj, bytes):
        try:
            return obj.decode('utf-8')
        except UnicodeDecodeError:
            return obj.hex()

    # set オブジェクトの場合
    if isinstance(obj, set):
        return list(obj)

    # その他のオブジェクトは文字列化
    return str(obj)


def safe_json_dumps(data: Any, **kwargs) -> str:
    """
    安全なJSON文字列化

    Args:
        data: シリアライズ対象データ
        **kwargs: json.dumps の追加引数

    Returns:
        JSON文字列
    """
    default_kwargs = {
        'ensure_ascii': False,
        'indent': 2,
        'default': safe_json_serializer
    }
    default_kwargs.update(kwargs)

    try:
        return json.dumps(data, **default_kwargs)
    except Exception as e:
        logger.error(f"JSON serialization error: {e}")
        # フォールバック: 文字列化
        return json.dumps(str(data), **{k: v for k, v in default_kwargs.items() if k != 'default'})


def safe_json_loads(data: str, default: Any = None) -> Any:
    """
    安全なJSON読み込み

    Args:
        data: JSON文字列
        default: パースエラー時のデフォルト値

    Returns:
        パース結果（エラー時はdefault）
    """
    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        return default
    except Exception as e:
        logger.error(f"Unexpected error parsing JSON: {e}")
        return default


# ===================================================================
# ファイル操作
# ===================================================================

def load_json_file(filepath: str) -> Optional[Dict[str, Any]]:
    """
    JSONファイルの読み込み

    Args:
        filepath: ファイルパス

    Returns:
        読み込んだデータ（エラー時はNone）
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"JSON file not found: {filepath}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in {filepath}: {e}")
        return None
    except Exception as e:
        logger.error(f"JSON file read error ({filepath}): {e}")
        return None


def save_json_file(data: Dict[str, Any], filepath: str) -> bool:
    """
    JSONファイルの保存

    Args:
        data: 保存するデータ
        filepath: ファイルパス

    Returns:
        成功時True
    """
    try:
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        # 安全なJSON保存を使用
        json_str = safe_json_dumps(data)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(json_str)
        return True
    except Exception as e:
        logger.error(f"JSON file save error ({filepath}): {e}")
        return False


def load_json_file_or_default(filepath: str, default: Any = None) -> Any:
    """
    JSONファイルを読み込み、存在しない場合はデフォルト値を返す

    Args:
        filepath: ファイルパス
        default: デフォルト値

    Returns:
        読み込んだデータまたはデフォルト値
    """
    result = load_json_file(filepath)
    return result if result is not None else default


def merge_json_files(filepaths: list, output_path: str = None) -> Dict[str, Any]:
    """
    複数のJSONファイルをマージ

    Args:
        filepaths: マージするファイルパスのリスト
        output_path: 出力先パス（省略時は保存しない）

    Returns:
        マージされたデータ
    """
    merged = {}
    for filepath in filepaths:
        data = load_json_file(filepath)
        if data:
            merged.update(data)

    if output_path:
        save_json_file(merged, output_path)

    return merged


# ===================================================================
# ユーティリティ
# ===================================================================

def is_valid_json(data: str) -> bool:
    """
    文字列が有効なJSONか確認

    Args:
        data: チェック対象文字列

    Returns:
        有効なJSONの場合True
    """
    try:
        json.loads(data)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


def pretty_print_json(data: Any) -> str:
    """
    JSONを整形して文字列化

    Args:
        data: 対象データ

    Returns:
        整形されたJSON文字列
    """
    return safe_json_dumps(data, indent=4)


def compact_json(data: Any) -> str:
    """
    JSONをコンパクトに文字列化（改行・インデントなし）

    Args:
        data: 対象データ

    Returns:
        コンパクトなJSON文字列
    """
    return safe_json_dumps(data, indent=None, separators=(',', ':'))


# ===================================================================
# エクスポート
# ===================================================================

__all__ = [
    # シリアライザー
    "safe_json_serializer",
    "safe_json_dumps",
    "safe_json_loads",
    # ファイル操作
    "load_json_file",
    "save_json_file",
    "load_json_file_or_default",
    "merge_json_files",
    # ユーティリティ
    "is_valid_json",
    "pretty_print_json",
    "compact_json",
]