# Text to chunks[List]
# 日本語・英語対応版
import re
from typing import List, Dict, Tuple
from collections import Counter


# =============================================================================
# チャンク分割機能（日本語・英語対応）
# =============================================================================

def chunk_text(text: str, keep_delimiter: bool = True) -> List[str]:
    """
    テキストをチャンクに分割する（日本語・英語自動判定対応）
    分割ルール:
    - 改行が含まれる場合: 改行で分割
    - 改行がない場合:
        - 日本語テキスト: 「。」で分割
        - 英語テキスト: 文末ピリオド「. 」で分割（略語等を考慮）
    Args:
        text: 分割対象のテキスト
        keep_delimiter: 区切り文字（。や.）を保持するか（デフォルト: True）
    Returns:
        チャンクのリスト
    """
    # 前後の空白を除去
    text = text.strip()

    if not text:
        return []

    # 改行が含まれているかチェック（空白のみの行は除外）
    has_meaningful_newlines = bool(re.search(r'\n\s*\S', text))

    if has_meaningful_newlines:
        # 改行で分割
        chunks = text.split('\n')
    else:
        # 言語判定（日本語文字が含まれているか）
        is_japanese = bool(re.search(r'[ぁ-んァ-ヶー一-龠]', text))

        if is_japanese:
            # 日本語: 「。」で分割
            if keep_delimiter:
                chunks = re.split(r'(?<=。)', text)
            else:
                chunks = text.split('。')
        else:
            # 英語: 文末ピリオドで分割
            # 略語（Dr., Mr., e.g., i.e., etc.）や小数点を避けるため、
            # ピリオド + スペース + 大文字 または ピリオド + 大文字 で分割
            if keep_delimiter:
                # ピリオドを保持して分割
                # パターン: ピリオドの後にスペース（0個以上）と大文字
                chunks = re.split(r'(?<=[.!?])\s*(?=[A-Z])', text)
            else:
                # ピリオドを除去して分割
                chunks = re.split(r'[.!?]\s*(?=[A-Z])', text)

    # 空のチャンクを除去し、各チャンクをstrip
    chunks = [chunk.strip() for chunk in chunks if chunk.strip()]

    return chunks


def chunk_text_with_info(text: str, keep_delimiter: bool = True) -> Dict[str, any]:
    """
    テキストをチャンクに分割し、詳細情報も返す

    Args:
        text: 分割対象のテキスト
        keep_delimiter: 区切り文字を保持するか

    Returns:
        {
            'chunks': チャンクのリスト,
            'method': 分割方法 ('newline', 'period_ja', 'period_en'),
            'language': 検出言語 ('japanese', 'english', 'unknown'),
            'count': チャンク数,
            'original_length': 元テキストの長さ
        }
    """
    text = text.strip()

    if not text:
        return {
            'chunks'         : [],
            'method'         : 'none',
            'language'       : 'unknown',
            'count'          : 0,
            'original_length': 0
        }

    # 言語判定
    is_japanese = bool(re.search(r'[ぁ-んァ-ヶー一-龠]', text))
    language = 'japanese' if is_japanese else 'english'

    # 改行が含まれているかチェック
    has_meaningful_newlines = bool(re.search(r'\n\s*\S', text))

    if has_meaningful_newlines:
        method = 'newline'
        chunks = text.split('\n')
    else:
        if is_japanese:
            method = 'period_ja'
            if keep_delimiter:
                chunks = re.split(r'(?<=。)', text)
            else:
                chunks = text.split('。')
        else:
            method = 'period_en'
            if keep_delimiter:
                chunks = re.split(r'(?<=[.!?])\s*(?=[A-Z])', text)
            else:
                chunks = re.split(r'[.!?]\s*(?=[A-Z])', text)

    # 空のチャンクを除去し、各チャンクをstrip
    chunks = [chunk.strip() for chunk in chunks if chunk.strip()]

    return {
        'chunks'         : chunks,
        'method'         : method,
        'language'       : language,
        'count'          : len(chunks),
        'original_length': len(text)
    }


def main():
    """メイン実行関数"""

    # 1. 日本語サンプル（改行あり）
    text_jp = """
    人工知能（AI）は、機械学習と深層学習を基盤として急速に発展しています。
    特に自然言語処理（NLP）の分野では、トランスフォーマーモデルが革命的な成果を上げました。
    BERTやGPTなどの大規模言語モデルは、文脈理解能力を大幅に向上させています。
    AIの応用は医療診断から自動運転まで幅広く、社会に大きな影響を与えています。
    """

    # 2. 日本語サンプル（改行なし - 句点で分割対象）
    text_jp2 = """人工知能（AI）は、機械学習と深層学習を基盤として急速に発展しています。特に自然言語処理（NLP）の分野では、トランスフォーマーモデルが革命的な成果を上げました。BERTやGPTなどの大規模言語モデルは、文脈理解能力を大幅に向上させています。AIの応用は医療診断から自動運転まで幅広く、社会に大きな影響を与えています。"""

    # 3. 英語サンプル（改行あり）
    text_en = """
    Artificial intelligence (AI) is rapidly advancing based on machine learning and deep learning.
    In the field of natural language processing (NLP) in particular, transformer models have achieved revolutionary results.
    Large language models like BERT and GPT have significantly enhanced contextual understanding capabilities.
    AI applications span widely from medical diagnosis to autonomous driving, profoundly impacting society.
    """

    # 4. 英語サンプル（改行なし - ピリオドで分割対象）
    text_en2 = """Artificial intelligence (AI) is rapidly advancing based on machine learning and deep learning. In the field of natural language processing (NLP) in particular, transformer models have achieved revolutionary results. Large language models like BERT and GPT have significantly enhanced contextual understanding capabilities. AI applications span widely from medical diagnosis to autonomous driving, profoundly impacting society."""

    # =========================================================================
    # チャンク分割のデモ
    # =========================================================================
    print(text_jp)
    chunks_jp = chunk_text(text_jp)
    for i, chunk_jp in enumerate(chunks_jp, 1):
        print(f'{i}. {chunk_jp}')
    print('------------------------')

    print(text_jp2)
    print('------------------------')
    chunks_jp2 = chunk_text(text_jp2)
    for i, chunk_jp2 in enumerate(chunks_jp2, 1):
        print(f'{i}. {chunk_jp2}')
    print('------------------------')

    print(text_en)
    chunks_en = chunk_text(text_en)
    for i, chunk_en in enumerate(chunks_en, 1):
        print(f'{i}. {chunk_en}')
    print('------------------------')

    print(text_en2)
    chunks_en2 = chunk_text(text_en2)
    for i, chunk_en2 in enumerate(chunks_en2, 1):
        print(f'{i}. {chunk_en2}')
    print('------------------------')

if __name__ == "__main__":
    main()
