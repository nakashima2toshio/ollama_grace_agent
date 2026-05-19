#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
models.py - 共通Pydanticモデル定義
==================================
プロジェクト全体で使用されるデータモデルを一元管理

使用箇所:
- rag_qa_pair_qdrant.py
- celery_tasks.py
- a02_make_qa_para.py
- helper_rag_qa.py
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ===================================================================
# Q/A関連モデル
# ===================================================================

class QAPair(BaseModel):
    """
    Q/Aペアのデータモデル

    基本的なQ/Aペア情報に加え、品質・難易度のメタデータを含む
    """
    question: str = Field(..., description="質問文")
    answer: str = Field(..., description="回答文")
    question_type: str = Field(
        default="fact",
        description="質問タイプ: fact/reason/comparison/application/definition/process/evaluation"
    )
    difficulty_level: Optional[str] = Field(
        default="medium",
        description="難易度: easy/medium/hard"
    )
    question_category: Optional[str] = Field(
        default="understanding",
        description="質問カテゴリ: basic/understanding/application"
    )
    source_chunk_id: Optional[str] = Field(
        default=None,
        description="ソースチャンクID"
    )
    dataset_type: Optional[str] = Field(
        default=None,
        description="データセットタイプ"
    )
    auto_generated: bool = Field(
        default=False,
        description="自動生成フラグ"
    )
    confidence_score: Optional[float] = Field(
        default=None,
        description="生成の確信度 (0.0-1.0)"
    )
    quality_score: Optional[float] = Field(
        default=None,
        description="品質スコア (0.0-1.0)"
    )


class QAPairsResponse(BaseModel):
    """
    Q/Aペア生成レスポンス

    OpenAI APIの構造化出力で使用
    """
    qa_pairs: List[QAPair] = Field(
        default_factory=list,
        description="生成されたQ/Aペアのリスト"
    )


# ===================================================================
# チャンク関連モデル
# ===================================================================

class ChunkData(BaseModel):
    """
    テキストチャンクのデータモデル
    """
    id: str = Field(..., description="チャンクID")
    text: str = Field(..., description="チャンクテキスト")
    tokens: int = Field(default=0, description="トークン数")
    doc_id: Optional[str] = Field(default=None, description="ドキュメントID")
    dataset_type: Optional[str] = Field(default=None, description="データセットタイプ")
    chunk_idx: int = Field(default=0, description="チャンクインデックス")
    position: Optional[str] = Field(
        default=None,
        description="チャンクの位置: start/middle/end"
    )


class ChunkComplexity(BaseModel):
    """
    チャンクの複雑度分析結果
    """
    complexity_level: str = Field(
        default="medium",
        description="複雑度レベル: low/medium/high"
    )
    technical_terms: List[str] = Field(
        default_factory=list,
        description="専門用語リスト"
    )
    avg_sentence_length: float = Field(
        default=0.0,
        description="平均文長"
    )
    concept_density: float = Field(
        default=0.0,
        description="概念密度"
    )
    sentence_count: int = Field(default=0, description="文数")
    token_count: int = Field(default=0, description="トークン数")


# ===================================================================
# Celeryタスク関連モデル
# ===================================================================

class QAGenerationResult(BaseModel):
    """
    Q/A生成タスクの結果
    """
    success: bool = Field(..., description="成功フラグ")
    chunk_id: Optional[str] = Field(default=None, description="チャンクID")
    chunk_ids: Optional[List[str]] = Field(
        default=None,
        description="バッチ処理時のチャンクIDリスト"
    )
    qa_pairs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="生成されたQ/Aペア"
    )
    error: Optional[str] = Field(default=None, description="エラーメッセージ")


# ===================================================================
# カバレージ分析関連モデル
# ===================================================================

class CoverageResult(BaseModel):
    """
    カバレージ分析結果
    """
    coverage_rate: float = Field(
        default=0.0,
        description="カバレージ率 (0.0-1.0)"
    )
    covered_chunks: int = Field(default=0, description="カバーされたチャンク数")
    total_chunks: int = Field(default=0, description="総チャンク数")
    uncovered_chunks: List[str] = Field(
        default_factory=list,
        description="未カバーチャンクIDリスト"
    )


# ===================================================================
# Qdrant関連モデル
# ===================================================================

class QdrantPointPayload(BaseModel):
    """
    Qdrantポイントのペイロード
    """
    domain: str = Field(..., description="ドメイン名")
    question: str = Field(..., description="質問文")
    answer: str = Field(..., description="回答文")
    source: str = Field(..., description="ソースファイル名")
    created_at: str = Field(..., description="作成日時 (ISO形式)")
    schema_version: str = Field(default="qa:v1", description="スキーマバージョン")
    generation_method: Optional[str] = Field(
        default=None,
        description="生成方法"
    )


class QdrantCollectionStats(BaseModel):
    """
    Qdrantコレクション統計情報
    """
    total_points: int = Field(default=0, description="総ポイント数")
    vector_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="ベクトル設定"
    )
    status: str = Field(default="unknown", description="ステータス")


# ===================================================================
# 処理結果モデル
# ===================================================================

class ProcessingResult(BaseModel):
    """
    汎用処理結果
    """
    success: bool = Field(..., description="成功フラグ")
    message: Optional[str] = Field(default=None, description="メッセージ")
    data: Optional[Dict[str, Any]] = Field(default=None, description="データ")
    error: Optional[str] = Field(default=None, description="エラーメッセージ")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="タイムスタンプ"
    )


class SavedFilesResult(BaseModel):
    """
    ファイル保存結果
    """
    csv_path: Optional[str] = Field(default=None, description="CSVファイルパス")
    json_path: Optional[str] = Field(default=None, description="JSONファイルパス")
    txt_path: Optional[str] = Field(default=None, description="テキストファイルパス")


# ===================================================================
# ファイル互換性のためのエイリアス
# ===================================================================

# 以前の名前でインポートしている場合の互換性維持
QAPairsList = QAPairsResponse