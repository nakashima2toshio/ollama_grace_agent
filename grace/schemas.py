"""
GRACE Schemas - Pydanticモデル定義

計画生成・実行に使用するデータモデルを定義
"""

from typing import Literal, Optional, List, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from enum import Enum


# =============================================================================
# アクション種別
# =============================================================================

class ActionType(str, Enum):
    """実行可能なアクション種別"""
    RAG_SEARCH = "rag_search"
    WEB_SEARCH = "web_search"
    REASONING = "reasoning"
    ASK_USER = "ask_user"
    CODE_EXECUTE = "code_execute"


class StepStatus(str, Enum):
    """ステップの実行状態"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


# =============================================================================
# 計画スキーマ
# =============================================================================

class PlanStep(BaseModel):
    """計画の1ステップを表現"""

    step_id: int = Field(
        ...,
        description="ステップ番号（1から開始）",
        ge=1
    )

    action: Literal["rag_search", "web_search", "reasoning", "ask_user", "code_execute", "run_legacy_agent"] = Field(
        ...,
        description="実行するアクション種別"
    )

    description: str = Field(
        ...,
        description="このステップで何をするか",
        min_length=1
    )

    query: Optional[str] = Field(
        None,
        description="検索クエリ（検索系アクションの場合）"
    )

    collection: Optional[str] = Field(
        None,
        description="検索対象コレクション（RAG検索の場合）"
    )

    depends_on: List[int] = Field(
        default_factory=list,
        description="依存する先行ステップのID"
    )

    expected_output: str = Field(
        ...,
        description="期待される出力の説明"
    )

    fallback: Optional[str] = Field(
        None,
        description="失敗時の代替アクション"
    )

    timeout_seconds: Optional[int] = Field(
        30,
        description="タイムアウト秒数",
        ge=1,
        le=300
    )

    model_config = ConfigDict(use_enum_values=True)


class ExecutionPlan(BaseModel):
    """実行計画全体"""

    original_query: str = Field(
        ...,
        description="ユーザーの元の質問",
        min_length=1
    )

    complexity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="推定複雑度（0.0-1.0）"
    )

    estimated_steps: int = Field(
        ...,
        description="推定ステップ数",
        ge=1,
        le=20
    )

    requires_confirmation: bool = Field(
        ...,
        description="実行前に確認が必要か"
    )

    steps: List[PlanStep] = Field(
        ...,
        description="実行ステップのリスト",
        min_length=1
    )

    success_criteria: str = Field(
        ...,
        description="計画成功の判定基準"
    )

    created_at: Optional[datetime] = Field(
        default_factory=datetime.now,
        description="計画作成日時"
    )

    plan_id: Optional[str] = Field(
        None,
        description="計画ID（自動生成）"
    )

    model_config = ConfigDict(use_enum_values=True)


# =============================================================================
# 実行結果スキーマ
# =============================================================================

class StepResult(BaseModel):
    """ステップ実行結果"""

    step_id: int = Field(
        ...,
        description="ステップID"
    )

    status: Literal["success", "partial", "failed"] = Field(
        ...,
        description="実行結果ステータス"
    )

    output: Optional[str] = Field(
        None,
        description="出力内容"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="信頼度スコア（0.0-1.0）"
    )

    sources: List[str] = Field(
        default_factory=list,
        description="引用ソース"
    )

    error: Optional[str] = Field(
        None,
        description="エラーメッセージ（失敗時）"
    )

    execution_time_ms: Optional[int] = Field(
        None,
        description="実行時間（ミリ秒）"
    )

    token_usage: Optional[dict] = Field(
        None,
        description="トークン使用量"
    )

    created_at: Optional[datetime] = Field(
        default_factory=datetime.now,
        description="結果作成日時"
    )


class ExecutionResult(BaseModel):
    """計画全体の実行結果"""

    plan_id: str = Field(
        ...,
        description="計画ID"
    )

    original_query: str = Field(
        ...,
        description="元のクエリ"
    )

    final_answer: Optional[str] = Field(
        None,
        description="最終回答"
    )

    step_results: List[StepResult] = Field(
        default_factory=list,
        description="各ステップの結果"
    )

    overall_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="全体の信頼度"
    )

    overall_status: Literal["success", "partial", "failed", "cancelled"] = Field(
        ...,
        description="全体のステータス"
    )

    replan_count: int = Field(
        0,
        description="リプラン回数"
    )

    total_execution_time_ms: Optional[int] = Field(
        None,
        description="総実行時間（ミリ秒）"
    )

    total_token_usage: Optional[dict] = Field(
        None,
        description="総トークン使用量"
    )

    total_cost_usd: Optional[float] = Field(
        None,
        description="総コスト（USD）"
    )

    created_at: Optional[datetime] = Field(
        default_factory=datetime.now,
        description="結果作成日時"
    )


# =============================================================================
# 検索結果スキーマ（RAG/Web共通）
# =============================================================================

class SearchResultPayload(BaseModel):
    """検索結果ペイロード（RAG/Web共通）"""

    question: str = Field(
        "",
        description="関連質問文（RAG検索時）"
    )

    answer: str = Field(
        "",
        description="回答・スニペット文"
    )

    content: str = Field(
        "",
        description="本文コンテンツ（question/answerがない場合）"
    )

    source: str = Field(
        "",
        description="出典URLまたはファイル名"
    )

    title: str = Field(
        "",
        description="ドキュメント・ページタイトル"
    )


class SearchResultItem(BaseModel):
    """検索結果1件（RAG/Web共通フォーマット）"""

    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="関連度スコア（0.0-1.0）"
    )

    payload: SearchResultPayload = Field(
        default_factory=SearchResultPayload,
        description="検索結果の詳細情報"
    )

    collection: str = Field(
        "",
        description="検索元コレクション名（例: 'wikipedia_ja', 'web_search'）"
    )


# =============================================================================
# ユーティリティ
# =============================================================================

def create_plan_id() -> str:
    """一意の計画IDを生成"""
    import hashlib
    import time
    unique_str = f"{time.time()}_{id(object())}"
    return hashlib.md5(unique_str.encode()).hexdigest()[:12]


def validate_plan_dependencies(plan: ExecutionPlan) -> List[str]:
    """
    計画の依存関係を検証

    Returns:
        エラーメッセージのリスト（空なら問題なし）
    """
    errors = []
    step_ids = {step.step_id for step in plan.steps}

    for step in plan.steps:
        for dep_id in step.depends_on:
            if dep_id not in step_ids:
                errors.append(
                    f"Step {step.step_id}: 存在しない依存先 {dep_id}"
                )
            if dep_id >= step.step_id:
                errors.append(
                    f"Step {step.step_id}: 循環依存または後方依存 {dep_id}"
                )

    return errors


# =============================================================================
# エクスポート
# =============================================================================

__all__ = [
    # Enums
    "ActionType",
    "StepStatus",

    # Plan schemas
    "PlanStep",
    "ExecutionPlan",

    # Result schemas
    "StepResult",
    "ExecutionResult",

    # Search result schemas (RAG/Web common)
    "SearchResultPayload",
    "SearchResultItem",

    # Utilities
    "create_plan_id",
    "validate_plan_dependencies",
]