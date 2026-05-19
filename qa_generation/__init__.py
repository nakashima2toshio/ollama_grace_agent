#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qa_generation - Q/A generation package
======================================
Core functionality for RAG Q&A system

Module structure:
- models.py: Pydantic data models (QAPair, QAPairsList, etc.)
- semantic.py: Semantic coverage (SemanticCoverage)
- smart_qa_generator.py: Smart Q/A generation (SmartQAGenerator)
- evaluation.py: Q/A evaluation
- pipeline.py: Generation pipeline (QAPipeline)
- data_io.py: Data I/O
"""

# ===================================================================
# Models
# ===================================================================
from qa_generation.models import (
    QAPair,
    QAPairsList,
    ChainOfThoughtAnalysis,
    ChainOfThoughtQAPair,
    ChainOfThoughtResponse,
    EnhancedQAPair,
    EnhancedQAPairsList,
    QAGenerationConsiderations,
)

# ===================================================================
# Semantic Coverage
# ===================================================================
from qa_generation.semantic import SemanticCoverage

# ===================================================================
# Smart QA Generator
# ===================================================================
from qa_generation.smart_qa_generator import SmartQAGenerator

# ===================================================================
# Pipeline
# ===================================================================
from qa_generation.pipeline import QAPipeline

# ===================================================================
# Export
# ===================================================================
__all__ = [
    # Models
    "QAPair",
    "QAPairsList",
    "ChainOfThoughtAnalysis",
    "ChainOfThoughtQAPair",
    "ChainOfThoughtResponse",
    "EnhancedQAPair",
    "EnhancedQAPairsList",
    "QAGenerationConsiderations",
    # Semantic coverage
    "SemanticCoverage",
    # Smart QA Generator
    "SmartQAGenerator",
    # Pipeline
    "QAPipeline",
]
