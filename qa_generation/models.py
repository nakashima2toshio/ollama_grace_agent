#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qa_generation/models.py - Q/A生成用Pydanticモデル
================================================
Q/Aペア生成で使用するデータモデルを定義

統合元:
- helper_rag_qa.py::QAPair
- helper_rag_qa.py::QAPairsList
- helper_rag_qa.py::ChainOfThoughtAnalysis
- helper_rag_qa.py::ChainOfThoughtQAPair
- helper_rag_qa.py::ChainOfThoughtResponse
- helper_rag_qa.py::EnhancedQAPair
- helper_rag_qa.py::EnhancedQAPairsList
- helper_rag_qa.py::QAGenerationConsiderations
"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


# ===================================================================
# 基本Q/Aペアモデル
# ===================================================================

class QAPair(BaseModel):
    """Q/Aペアの基本データモデル"""
    question: str = Field(..., description="質問文")
    answer: str = Field(..., description="回答文")
    question_type: str = Field(default="fact", description="質問タイプ (fact/reason/comparison/application)")
    difficulty: str = Field(default="medium", description="難易度 (easy/medium/hard)")
    source_span: str = Field(default="", description="回答の根拠となる元テキストの一部")


class QAPairsList(BaseModel):
    """Q/Aペアのリスト"""
    qa_pairs: List[QAPair] = Field(default_factory=list, description="Q/Aペアのリスト")


# ===================================================================
# Chain-of-Thought関連モデル
# ===================================================================

class ChainOfThoughtAnalysis(BaseModel):
    """ChainOfThought分析結果モデル"""
    main_topics: List[str] = Field(default_factory=list, description="主要トピック")
    key_concepts: List[str] = Field(default_factory=list, description="重要概念")
    information_density: str = Field(default="medium", description="情報密度 (low/medium/high)")


class ChainOfThoughtQAPair(BaseModel):
    """ChainOfThought用Q/Aペアモデル"""
    question: str = Field(..., description="質問文")
    answer: str = Field(..., description="回答文")
    reasoning: str = Field(default="", description="推論過程")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="信頼度スコア")


class ChainOfThoughtResponse(BaseModel):
    """ChainOfThought生成結果モデル"""
    analysis: ChainOfThoughtAnalysis = Field(default_factory=ChainOfThoughtAnalysis)
    qa_pairs: List[ChainOfThoughtQAPair] = Field(default_factory=list)


# ===================================================================
# 拡張Q/Aペアモデル
# ===================================================================

class EnhancedQAPair(BaseModel):
    """LLM品質向上用のシンプルなQ/Aペアモデル"""
    question: str = Field(..., description="質問文")
    answer: str = Field(..., description="回答文")


class EnhancedQAPairsList(BaseModel):
    """LLM品質向上用のQ/Aペアリスト"""
    qa_pairs: List[EnhancedQAPair] = Field(default_factory=list)


# ===================================================================
# Q/A生成要件・設定モデル
# ===================================================================

class QAGenerationConsiderations(BaseModel):
    """
    Q/A生成前のチェックリスト

    文書特性分析、Q/A要件定義、品質基準設定を行う
    """
    # 文書分析
    document_characteristics: Dict[str, Any] = Field(
        default_factory=lambda: {
            "domain": "general",  # 専門分野
            "text_type": "informative",  # 説明文、対話、etc
            "complexity": "medium",  # 複雑度
            "length": "medium"  # 文書長
        },
        description="文書特性"
    )

    # 抽出要件
    extraction_requirements: Dict[str, Any] = Field(
        default_factory=lambda: {
            "focus_areas": [],  # 重点領域
            "key_entities": [],  # 重要エンティティ
            "ignore_sections": []  # 無視するセクション
        },
        description="抽出要件"
    )

    # 品質基準
    quality_standards: Dict[str, Any] = Field(
        default_factory=lambda: {
            "min_answer_length": 10,  # 最小回答文字数
            "max_answer_length": 200,  # 最大回答文字数
            "require_source_span": True,  # 出典必須
            "diversity_threshold": 0.7  # 多様性閾値
        },
        description="品質基準"
    )

    # Q/A特性
    qa_characteristics: Dict[str, Any] = Field(
        default_factory=lambda: {
            "question_types": ["fact", "reason", "comparison", "application"],
            "difficulty_distribution": {"easy": 0.3, "medium": 0.5, "hard": 0.2},
            "answer_formats": ["短答", "説明", "リスト", "段落"],
            "coverage_targets": {
                "minimum": 0.3,
                "optimal": 0.6,
                "comprehensive": 0.8
            }
        },
        description="Q/A特性"
    )


# ===================================================================
# エクスポート
# ===================================================================

__all__ = [
    # 基本モデル
    "QAPair",
    "QAPairsList",
    # Chain-of-Thoughtモデル
    "ChainOfThoughtAnalysis",
    "ChainOfThoughtQAPair",
    "ChainOfThoughtResponse",
    # 拡張モデル
    "EnhancedQAPair",
    "EnhancedQAPairsList",
    # 設定モデル
    "QAGenerationConsiderations",
]