#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
helper_text.py - テキスト処理ユーティリティ
==========================================
テキストのクレンジング、トークン処理、チャンク分割の共通機能

使用箇所:
- rag_qa_pair_qdrant.py
- a02_make_qa_para.py
- helper_rag.py
- helper_rag_qa.py
"""

import re
import logging
from typing import List
import tiktoken

# ログ設定
logger = logging.getLogger(__name__)

# ===================================================================
# 定数
# ===================================================================

# デフォルトのチャンクサイズ設定
DEFAULT_CHUNK_SIZE = 300  # トークン数
DEFAULT_CHUNK_OVERLAP = 50  # オーバーラップトークン数
DEFAULT_MIN_CHUNK_SIZE = 50  # 最小チャンクサイズ

# デフォルトの埋め込みモデル用エンコーディング
DEFAULT_ENCODING = "cl100k_base"


# ===================================================================
# テキストクレンジング関数
# ===================================================================

def clean_text(text: str) -> str:
    """
    テキストのクレンジング処理

    Args:
        text: クレンジング対象のテキスト

    Returns:
        クレンジング済みのテキスト
    """
    if text is None or (hasattr(text, '__iter__') and not isinstance(text, str)):
        return ""

    # pandas NAチェック
    try:
        import pandas as pd
        if pd.isna(text):
            return ""
    except (ImportError, TypeError):
        pass

    if text == "":
        return ""

    # 文字列に変換
    text = str(text)

    # 改行を空白に置換
    text = text.replace('\n', ' ').replace('\r', ' ')

    # 連続した空白を1つの空白にまとめる
    text = re.sub(r'\s+', ' ', text)

    # 先頭・末尾の空白を除去
    text = text.strip()

    # 引用符の正規化
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")

    return text


def normalize_japanese_text(text: str) -> str:
    """
    日本語テキストの正規化

    Args:
        text: 正規化対象のテキスト

    Returns:
        正規化済みのテキスト
    """
    if not text:
        return ""

    # 全角英数字を半角に変換
    result = []
    for char in text:
        code = ord(char)
        # 全角英数字 (！-～ の範囲)
        if 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        # 全角スペース
        elif code == 0x3000:
            result.append(' ')
        else:
            result.append(char)

    text = ''.join(result)

    # 連続する句読点の正規化
    text = re.sub(r'[。]{2,}', '。', text)
    text = re.sub(r'[、]{2,}', '、', text)

    return text


def extract_sentences_japanese(text: str) -> List[str]:
    """
    日本語テキストから文を抽出

    Args:
        text: 対象テキスト

    Returns:
        文のリスト
    """
    if not text:
        return []

    # 日本語の文末パターン
    sentence_endings = r'([。！？\!\?])'
    sentences = re.split(sentence_endings, text)

    # 文末記号を前の文に結合
    result = []
    current = ""
    for part in sentences:
        if re.match(sentence_endings, part):
            current += part
            if current.strip():
                result.append(current.strip())
            current = ""
        else:
            current = part

    # 残りの部分を追加
    if current.strip():
        result.append(current.strip())

    return result


# ===================================================================
# トークン処理関数（services/token_serviceから統合）
# ===================================================================
# 後方互換性のため、services.token_serviceからimport
from services.token_service import (
    get_encoding,
    count_tokens,
    estimate_tokens_simple,
)  # noqa: E402


# ===================================================================
# チャンク分割関数
# ===================================================================

def split_into_chunks(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    encoding_name: str = DEFAULT_ENCODING
) -> List[str]:
    """
    テキストをチャンクに分割

    Args:
        text: 分割するテキスト
        chunk_size: チャンクサイズ（トークン数）
        overlap: オーバーラップ（トークン数）
        encoding_name: エンコーディング名

    Returns:
        チャンクのリスト
    """
    if not text:
        return []

    encoding = tiktoken.get_encoding(encoding_name)
    tokens = encoding.encode(text)

    if len(tokens) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(tokens):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        chunk_text = encoding.decode(chunk_tokens)
        chunks.append(chunk_text)

        # オーバーラップを考慮して次の開始位置を設定
        start = end - overlap

        # 最後のチャンクの場合は終了
        if end >= len(tokens):
            break

    return chunks


def split_into_chunks_with_metadata(
    text: str,
    doc_id: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    encoding_name: str = DEFAULT_ENCODING
) -> List[dict]:
    """
    テキストをメタデータ付きチャンクに分割

    Args:
        text: 分割するテキスト
        doc_id: ドキュメントID
        chunk_size: チャンクサイズ（トークン数）
        overlap: オーバーラップ（トークン数）
        encoding_name: エンコーディング名

    Returns:
        チャンクデータのリスト（id, text, tokens, doc_id, chunk_idx, position含む）
    """
    if not text:
        return []

    encoding = tiktoken.get_encoding(encoding_name)
    tokens = encoding.encode(text)
    total_tokens = len(tokens)

    if total_tokens <= chunk_size:
        return [{
            "id": f"{doc_id}_chunk_0",
            "text": text,
            "tokens": total_tokens,
            "doc_id": doc_id,
            "chunk_idx": 0,
            "position": "full"
        }]

    chunks = []
    start = 0
    chunk_idx = 0
    (total_tokens + chunk_size - overlap - 1) // (chunk_size - overlap)

    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = encoding.decode(chunk_tokens)

        # 位置を判定
        if chunk_idx == 0:
            position = "start"
        elif end >= len(tokens):
            position = "end"
        else:
            position = "middle"

        chunks.append({
            "id": f"{doc_id}_chunk_{chunk_idx}",
            "text": chunk_text,
            "tokens": len(chunk_tokens),
            "doc_id": doc_id,
            "chunk_idx": chunk_idx,
            "position": position
        })

        # オーバーラップを考慮して次の開始位置を設定
        start = end - overlap
        chunk_idx += 1

        # 最後のチャンクの場合は終了
        if end >= len(tokens):
            break

    return chunks


def merge_small_chunks(
    chunks: List[dict],
    min_tokens: int = DEFAULT_MIN_CHUNK_SIZE,
    max_tokens: int = DEFAULT_CHUNK_SIZE * 2
) -> List[dict]:
    """
    小さいチャンクを統合

    Args:
        chunks: チャンクデータのリスト
        min_tokens: 統合対象の最小トークン数
        max_tokens: 統合後の最大トークン数

    Returns:
        統合後のチャンクリスト
    """
    if not chunks:
        return []

    merged = []
    current = None

    for chunk in chunks:
        if current is None:
            current = chunk.copy()
            continue

        # 現在のチャンクが小さく、統合しても最大トークン数を超えない場合
        if current["tokens"] < min_tokens and current["tokens"] + chunk["tokens"] <= max_tokens:
            # 同じドキュメントのチャンクのみ統合
            if current["doc_id"] == chunk["doc_id"]:
                current["text"] = current["text"] + " " + chunk["text"]
                current["tokens"] = current["tokens"] + chunk["tokens"]
                current["id"] = f"{current['doc_id']}_merged_{current['chunk_idx']}_{chunk['chunk_idx']}"
                continue

        merged.append(current)
        current = chunk.copy()

    if current is not None:
        merged.append(current)

    return merged


# ===================================================================
# テキスト分析関数
# ===================================================================

def analyze_text_complexity(text: str) -> dict:
    """
    テキストの複雑度を分析

    Args:
        text: 分析対象テキスト

    Returns:
        複雑度分析結果
    """
    if not text:
        return {
            "complexity_level": "low",
            "sentence_count": 0,
            "avg_sentence_length": 0,
            "token_count": 0,
            "technical_terms": []
        }

    # 文を抽出
    sentences = extract_sentences_japanese(text)
    sentence_count = len(sentences)

    # トークン数
    token_count = count_tokens(text)

    # 平均文長
    avg_sentence_length = token_count / sentence_count if sentence_count > 0 else 0

    # 複雑度判定
    if avg_sentence_length > 50 or token_count > 500:
        complexity_level = "high"
    elif avg_sentence_length > 25 or token_count > 200:
        complexity_level = "medium"
    else:
        complexity_level = "low"

    return {
        "complexity_level": complexity_level,
        "sentence_count": sentence_count,
        "avg_sentence_length": round(avg_sentence_length, 2),
        "token_count": token_count,
        "technical_terms": []  # 専門用語抽出は別途実装
    }


def extract_key_concepts(text: str, max_concepts: int = 5) -> List[str]:
    """
    テキストからキーコンセプトを抽出（簡易版）

    Args:
        text: 対象テキスト
        max_concepts: 最大抽出数

    Returns:
        キーコンセプトのリスト
    """
    if not text:
        return []

    # 簡易的なキーワード抽出（名詞的なパターン）
    # より高度な抽出には形態素解析器（MeCab等）の使用を推奨

    # 日本語の複合名詞パターン（簡易版）
    patterns = [
        r'[一-龯々ぁ-んァ-ン]{2,}',  # 漢字・ひらがな・カタカナの連続
    ]

    concepts = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if len(match) >= 2 and match not in concepts:
                concepts.append(match)
                if len(concepts) >= max_concepts:
                    break
        if len(concepts) >= max_concepts:
            break

    return concepts[:max_concepts]


# ===================================================================
# ユーティリティ関数
# ===================================================================

def truncate_text(text: str, max_tokens: int = 1000, add_ellipsis: bool = True) -> str:
    """
    テキストを指定トークン数で切り詰め

    Args:
        text: 対象テキスト
        max_tokens: 最大トークン数
        add_ellipsis: 省略記号を追加するか

    Returns:
        切り詰められたテキスト
    """
    if not text:
        return ""

    encoding = tiktoken.get_encoding(DEFAULT_ENCODING)
    tokens = encoding.encode(text)

    if len(tokens) <= max_tokens:
        return text

    truncated_tokens = tokens[:max_tokens]
    truncated_text = encoding.decode(truncated_tokens)

    if add_ellipsis:
        truncated_text += "..."

    return truncated_text


def get_text_stats(text: str) -> dict:
    """
    テキストの統計情報を取得

    Args:
        text: 対象テキスト

    Returns:
        統計情報
    """
    if not text:
        return {
            "char_count": 0,
            "token_count": 0,
            "word_count": 0,
            "sentence_count": 0,
            "avg_word_length": 0
        }

    char_count = len(text)
    token_count = count_tokens(text)
    sentences = extract_sentences_japanese(text)
    sentence_count = len(sentences)

    # 単語数の推定（スペースまたは句読点で分割）
    words = re.split(r'[\s、。！？\!\?]+', text)
    words = [w for w in words if w.strip()]
    word_count = len(words)

    avg_word_length = char_count / word_count if word_count > 0 else 0

    return {
        "char_count": char_count,
        "token_count": token_count,
        "word_count": word_count,
        "sentence_count": sentence_count,
        "avg_word_length": round(avg_word_length, 2)
    }


# ===================================================================
# 後方互換性のためのエイリアス
# ===================================================================

# 旧名称でインポートしている場合の互換性維持
count_tokens_tiktoken = count_tokens
split_text_into_chunks = split_into_chunks