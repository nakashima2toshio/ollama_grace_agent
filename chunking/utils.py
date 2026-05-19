# utils.py
"""
ユーティリティ関数
"""

import logging
import os
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)


def show_paragraphs(paragraphs: List[str], title: Optional[str] = None) -> None:
    """
    分割されたパラグラフのリストを整形して標準出力に表示
    
    Args:
        paragraphs: パラグラフのリスト
        title: 表示タイトル（オプション）
    """
    # if title:
    #     print(f"--- {title} ---")
    #
    # if paragraphs:
    #     for i, p_text in enumerate(paragraphs):
    #         # 表示が見やすいように改行を除去
    #         display_text = p_text.replace('\n', ' ').strip()
    #         # 長すぎる場合はカット
    #         if len(display_text) > 100:
    #             display_text = display_text[:100] + "..."
    #         print(f"Chunk [ID:{i + 1}]: {display_text}")
    # else:
    #     print("No paragraphs to display.")
    # print("")
    pass


def setup_logging(
    verbose: bool = False,
    log_dir: str = "./logs",
    log_prefix: str = "chunking"
) -> str:
    """
    ロギングの設定
    
    Args:
        verbose: 詳細ログを出力するか
        log_dir: ログディレクトリ
        log_prefix: ログファイル名のプレフィックス
    
    Returns:
        ログファイルパス
    """
    log_level = logging.DEBUG if verbose else logging.INFO

    # ログディレクトリ作成
    os.makedirs(log_dir, exist_ok=True)

    # ログファイル名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f"{log_prefix}_{timestamp}.log")

    # ログフォーマット
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # ファイルハンドラ
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    # コンソールハンドラ
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # ルートロガー設定
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # 既存のハンドラをクリア
    root_logger.handlers.clear()
    
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logger.info(f"Logging initialized. Log file: {log_file}")
    return log_file


def format_time(seconds: float) -> str:
    """
    秒数を読みやすい形式に変換
    
    Args:
        seconds: 秒数
    
    Returns:
        フォーマットされた時間文字列
    """
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}分"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}時間"


def format_size(chars: int) -> str:
    """
    文字数を読みやすい形式に変換
    
    Args:
        chars: 文字数
    
    Returns:
        フォーマットされた文字数文字列
    """
    if chars < 1000:
        return f"{chars}文字"
    elif chars < 1000000:
        return f"{chars/1000:.1f}K文字"
    else:
        return f"{chars/1000000:.1f}M文字"


def estimate_api_calls(
    text_length: int,
    block_size: int = 2000
) -> dict:
    """
    API呼び出し回数を見積もる
    
    Args:
        text_length: テキストの文字数
        block_size: バッチサイズ
    
    Returns:
        見積もり情報
    """
    # Step1: バッチ数
    batch_count = (text_length + block_size - 1) // block_size
    
    # Step2: パラグラフ数（バッチあたり平均4パラグラフと仮定）
    estimated_paragraphs = batch_count * 4
    
    # Step3: チャンク数（パラグラフあたり平均1.5チャンクと仮定）
    estimated_chunks = int(estimated_paragraphs * 1.5)
    
    # 合計API呼び出し回数
    total_api_calls = batch_count + estimated_paragraphs + (estimated_chunks - 1)
    
    # 処理時間見積もり（1 API呼び出し = 2秒と仮定）
    estimated_time_serial = total_api_calls * 2
    
    return {
        "text_length": text_length,
        "block_size": block_size,
        "batch_count": batch_count,
        "estimated_paragraphs": estimated_paragraphs,
        "estimated_chunks": estimated_chunks,
        "total_api_calls": total_api_calls,
        "estimated_time_serial_seconds": estimated_time_serial,
        "estimated_time_serial": format_time(estimated_time_serial)
    }


def print_stats(stats: dict, title: str = "Statistics"):
    """
    統計情報を整形して表示
    
    Args:
        stats: 統計情報の辞書
        title: タイトル
    """
    print(f"\n=== {title} ===")
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")
    print("")
