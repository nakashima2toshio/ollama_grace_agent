#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
log_service.py - ログ管理サービス
===============================
エージェントの未回答質問ログなどを管理・保存・読み込みするサービス。
"""

import os
import csv
import logging
from datetime import datetime
from pathlib import Path
import pandas as pd
from typing import List, Dict, Optional

from config import PathConfig

logger = logging.getLogger(__name__)

# ログファイルの保存先
LOG_DIR = Path("logs")
UNANSWERED_LOG_FILE = LOG_DIR / "unanswered_questions.csv"

def _ensure_log_dir():
    """ログディレクトリとファイルの初期化"""
    if not LOG_DIR.exists():
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    if not UNANSWERED_LOG_FILE.exists():
        with open(UNANSWERED_LOG_FILE, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "query", "collections", "reason", "agent_response"])

def log_unanswered_question(query: str, collections: List[str], reason: str, agent_response: str = ""):
    """
    回答できなかった質問をログに記録する

    Args:
        query: ユーザーの質問
        collections: 検索対象としたコレクションのリスト
        reason: 未回答の理由（例: "No RAG results", "Low score"）
        agent_response: エージェントの最終応答（あれば）
    """
    try:
        _ensure_log_dir()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        collections_str = ", ".join(collections)
        
        with open(UNANSWERED_LOG_FILE, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, query, collections_str, reason, agent_response])
            
        logger.info(f"Unanswered question logged: {query}")
        
    except Exception as e:
        logger.error(f"Failed to log unanswered question: {e}")

def load_unanswered_logs() -> pd.DataFrame:
    """
    未回答質問ログを読み込む

    Returns:
        pd.DataFrame: ログデータ
    """
    _ensure_log_dir()
    
    try:
        if not UNANSWERED_LOG_FILE.exists() or UNANSWERED_LOG_FILE.stat().st_size == 0:
            return pd.DataFrame(columns=["timestamp", "query", "collections", "reason", "agent_response"])
        
        df = pd.read_csv(UNANSWERED_LOG_FILE)
        # 日付の新しい順にソート
        if "timestamp" in df.columns:
            df = df.sort_values("timestamp", ascending=False)
        return df
        
    except Exception as e:
        logger.error(f"Failed to load unanswered logs: {e}")
        return pd.DataFrame(columns=["timestamp", "query", "collections", "reason", "agent_response"])

def clear_unanswered_logs():
    """未回答ログをクリア（ファイルを再作成）"""
    try:
        with open(UNANSWERED_LOG_FILE, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "query", "collections", "reason", "agent_response"])
        logger.info("Unanswered logs cleared.")
    except Exception as e:
        logger.error(f"Failed to clear logs: {e}")
