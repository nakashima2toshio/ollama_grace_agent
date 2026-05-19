"""
GRACE Intervention - HITL（Human-in-the-Loop）介入システム

人間と協調するためのインターフェースと介入ロジックを提供
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Any, Literal, Dict
from enum import Enum
from datetime import datetime

from .schemas import ExecutionPlan, PlanStep
from .confidence import InterventionLevel, ConfidenceScore, ActionDecision
from .config import get_config, GraceConfig

logger = logging.getLogger(__name__)


# =============================================================================
# 介入リクエスト/レスポンス
# =============================================================================

@dataclass
class InterventionRequest:
    """介入リクエスト"""

    level: InterventionLevel
    step_id: Optional[int] = None
    message: str = ""
    question: Optional[str] = None
    reason: Optional[str] = None
    options: Optional[List[str]] = None
    timeout_seconds: int = 300
    is_blocking: bool = True
    confidence_score: Optional[float] = None
    plan: Optional[ExecutionPlan] = None
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def requires_response(self) -> bool:
        """レスポンスが必要か"""
        return self.level in [InterventionLevel.CONFIRM, InterventionLevel.ESCALATE]


class InterventionAction(str, Enum):
    """介入アクション"""
    PROCEED = "proceed"       # そのまま進行
    MODIFY = "modify"         # 計画を修正して進行
    CANCEL = "cancel"         # キャンセル
    INPUT = "input"           # ユーザー入力を受け取る
    RETRY = "retry"           # 再試行
    SKIP = "skip"             # 現在のステップをスキップ


@dataclass
class InterventionResponse:
    """介入レスポンス"""

    action: InterventionAction
    user_input: Optional[str] = None
    modified_plan: Optional[ExecutionPlan] = None
    selected_option: Optional[str] = None
    timeout_reached: bool = False
    response_time_ms: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def should_continue(self) -> bool:
        """実行を継続すべきか"""
        return self.action in [
            InterventionAction.PROCEED,
            InterventionAction.MODIFY,
            InterventionAction.RETRY,
            InterventionAction.SKIP
        ]


# =============================================================================
# 介入ハンドラー
# =============================================================================

class InterventionHandler:
    """
    介入ハンドラー

    信頼度レベルに応じた介入リクエストを生成し、
    ユーザーからのレスポンスを処理する
    """

    def __init__(
        self,
        config: Optional[GraceConfig] = None,
        on_notify: Optional[Callable[[str], None]] = None,
        on_confirm: Optional[Callable[[InterventionRequest], InterventionResponse]] = None,
        on_escalate: Optional[Callable[[InterventionRequest], InterventionResponse]] = None,
    ):
        """
        Args:
            config: GRACE設定
            on_notify: 通知コールバック（NOTIFYレベル）
            on_confirm: 確認コールバック（CONFIRMレベル）
            on_escalate: エスカレーションコールバック（ESCALATEレベル）
        """
        self.config = config or get_config()
        self.on_notify = on_notify
        self.on_confirm = on_confirm
        self.on_escalate = on_escalate

        # 介入履歴
        self.history: List[Dict[str, Any]] = []

        logger.info("InterventionHandler initialized")

    def handle(
        self,
        decision: ActionDecision,
        step: Optional[PlanStep] = None,
        plan: Optional[ExecutionPlan] = None,
    ) -> InterventionResponse:
        """
        ActionDecisionに基づいて介入を処理

        Args:
            decision: 信頼度に基づくアクション決定
            step: 現在のステップ（オプション）
            plan: 現在の計画（オプション）

        Returns:
            InterventionResponse: 介入レスポンス
        """
        level = decision.level

        if level == InterventionLevel.SILENT:
            return self._handle_silent(decision)

        elif level == InterventionLevel.NOTIFY:
            return self._handle_notify(decision, step)

        elif level == InterventionLevel.CONFIRM:
            return self._handle_confirm(decision, step, plan)

        elif level == InterventionLevel.ESCALATE:
            return self._handle_escalate(decision, step, plan)

        # デフォルト: 進行
        return InterventionResponse(action=InterventionAction.PROCEED)

    def _handle_silent(self, decision: ActionDecision) -> InterventionResponse:
        """SILENTレベル処理: 何もしない"""
        self._record_history(InterventionLevel.SILENT, "auto_proceed")
        return InterventionResponse(action=InterventionAction.PROCEED)

    def _handle_notify(
        self,
        decision: ActionDecision,
        step: Optional[PlanStep]
    ) -> InterventionResponse:
        """NOTIFYレベル処理: 通知のみ"""
        message = self._create_notify_message(decision, step)

        if self.on_notify:
            self.on_notify(message)

        self._record_history(InterventionLevel.NOTIFY, "notified", message=message)
        return InterventionResponse(action=InterventionAction.PROCEED)

    def _handle_confirm(
        self,
        decision: ActionDecision,
        step: Optional[PlanStep],
        plan: Optional[ExecutionPlan]
    ) -> InterventionResponse:
        """CONFIRMレベル処理: 確認を求める"""
        request = InterventionRequest(
            level=InterventionLevel.CONFIRM,
            step_id=step.step_id if step else None,
            message=self._create_confirm_message(decision, step),
            reason=decision.reason,
            options=["はい、続行", "計画を修正", "キャンセル"],
            timeout_seconds=self.config.intervention.default_timeout,
            is_blocking=True,
            confidence_score=decision.confidence_score,
            plan=plan
        )

        if self.on_confirm:
            start_time = time.time()
            response = self.on_confirm(request)
            response.response_time_ms = int((time.time() - start_time) * 1000)
            self._record_history(
                InterventionLevel.CONFIRM,
                response.action.value,
                message=request.message,
                response=response
            )
            return response

        # コールバックがない場合はタイムアウト処理
        return self._handle_timeout(request)

    def _handle_escalate(
        self,
        decision: ActionDecision,
        step: Optional[PlanStep],
        plan: Optional[ExecutionPlan]
    ) -> InterventionResponse:
        """ESCALATEレベル処理: ユーザー入力を求める"""
        request = InterventionRequest(
            level=InterventionLevel.ESCALATE,
            step_id=step.step_id if step else None,
            message=self._create_escalate_message(decision, step),
            question="追加情報を入力してください",
            reason=decision.reason,
            timeout_seconds=self.config.intervention.default_timeout,
            is_blocking=True,
            confidence_score=decision.confidence_score,
            plan=plan
        )

        if self.on_escalate:
            start_time = time.time()
            response = self.on_escalate(request)
            response.response_time_ms = int((time.time() - start_time) * 1000)
            self._record_history(
                InterventionLevel.ESCALATE,
                response.action.value,
                message=request.message,
                response=response
            )
            return response

        # コールバックがない場合はタイムアウト処理
        return self._handle_timeout(request)

    def _handle_timeout(self, request: InterventionRequest) -> InterventionResponse:
        """タイムアウト処理"""
        if self.config.intervention.auto_proceed_on_timeout:
            logger.warning(f"Intervention timeout, auto-proceeding")
            return InterventionResponse(
                action=InterventionAction.PROCEED,
                timeout_reached=True
            )
        else:
            logger.warning(f"Intervention timeout, cancelling")
            return InterventionResponse(
                action=InterventionAction.CANCEL,
                timeout_reached=True
            )

    def _create_notify_message(
        self,
        decision: ActionDecision,
        step: Optional[PlanStep]
    ) -> str:
        """通知メッセージを作成"""
        if step:
            return f"実行中: {step.description} (信頼度: {decision.confidence_score:.1%})"
        return f"処理中... (信頼度: {decision.confidence_score:.1%})"

    def _create_confirm_message(
        self,
        decision: ActionDecision,
        step: Optional[PlanStep]
    ) -> str:
        """確認メッセージを作成"""
        if step:
            return (
                f"信頼度が低いため確認が必要です。\n"
                f"ステップ: {step.description}\n"
                f"信頼度: {decision.confidence_score:.1%}\n"
                f"理由: {decision.reason}\n"
                f"続行しますか？"
            )
        return (
            f"信頼度が低いため確認が必要です。\n"
            f"信頼度: {decision.confidence_score:.1%}\n"
            f"理由: {decision.reason}\n"
            f"続行しますか？"
        )

    def _create_escalate_message(
        self,
        decision: ActionDecision,
        step: Optional[PlanStep]
    ) -> str:
        """エスカレーションメッセージを作成"""
        if step:
            return (
                f"追加情報が必要です。\n"
                f"ステップ: {step.description}\n"
                f"信頼度: {decision.confidence_score:.1%}\n"
                f"理由: {decision.reason}"
            )
        return (
            f"追加情報が必要です。\n"
            f"信頼度: {decision.confidence_score:.1%}\n"
            f"理由: {decision.reason}"
        )

    def _record_history(
        self,
        level: InterventionLevel,
        action: str,
        message: Optional[str] = None,
        response: Optional[InterventionResponse] = None
    ):
        """介入履歴を記録"""
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "level": level.value,
            "action": action,
            "message": message,
            "response_action": response.action.value if response else None,
            "timeout_reached": response.timeout_reached if response else False
        })

    def request_confirmation(
        self,
        plan: ExecutionPlan,
        confidence: float,
        message: Optional[str] = None
    ) -> InterventionResponse:
        """
        計画の確認をリクエスト

        Args:
            plan: 確認する計画
            confidence: 信頼度スコア
            message: カスタムメッセージ（オプション）

        Returns:
            InterventionResponse: 介入レスポンス
        """
        request = InterventionRequest(
            level=InterventionLevel.CONFIRM,
            message=message or f"以下の計画を実行してよろしいですか？\n{self._format_plan(plan)}",
            options=["はい、実行", "計画を修正", "キャンセル"],
            timeout_seconds=self.config.intervention.default_timeout,
            is_blocking=True,
            confidence_score=confidence,
            plan=plan
        )

        if self.on_confirm:
            return self.on_confirm(request)

        return self._handle_timeout(request)

    def request_clarification(
        self,
        question: str,
        reason: str,
        options: Optional[List[str]] = None,
        is_blocking: bool = True
    ) -> InterventionResponse:
        """
        ユーザーに追加情報を求める

        Args:
            question: 質問文
            reason: 質問の理由
            options: 選択肢（オプション）
            is_blocking: ブロッキングか

        Returns:
            InterventionResponse: 介入レスポンス
        """
        request = InterventionRequest(
            level=InterventionLevel.ESCALATE,
            question=question,
            reason=reason,
            options=options,
            timeout_seconds=self.config.intervention.default_timeout,
            is_blocking=is_blocking
        )

        if self.on_escalate:
            return self.on_escalate(request)

        return self._handle_timeout(request)

    def notify_status(self, message: str) -> None:
        """ステータス通知"""
        if self.on_notify:
            self.on_notify(message)

        self._record_history(InterventionLevel.NOTIFY, "status_update", message=message)

    def _format_plan(self, plan: ExecutionPlan) -> str:
        """計画をフォーマット"""
        lines = [f"質問: {plan.original_query}", "ステップ:"]
        for step in plan.steps:
            lines.append(f"  {step.step_id}. [{step.action}] {step.description}")
        return "\n".join(lines)

    def get_history(self) -> List[Dict[str, Any]]:
        """介入履歴を取得"""
        return self.history.copy()

    def clear_history(self):
        """介入履歴をクリア"""
        self.history.clear()


# =============================================================================
# 動的閾値調整
# =============================================================================

@dataclass
class FeedbackRecord:
    """フィードバック記録"""
    confidence: float
    was_correct: bool
    timestamp: datetime = field(default_factory=datetime.now)


class DynamicThresholdAdjuster:
    """
    ユーザーフィードバックに基づく動的閾値調整

    過去のフィードバックを学習して、閾値を自動調整
    """

    def __init__(
        self,
        config: Optional[GraceConfig] = None,
        learning_rate: float = 0.05,
        min_samples: int = 10
    ):
        """
        Args:
            config: GRACE設定
            learning_rate: 学習率
            min_samples: 調整に必要な最小サンプル数
        """
        self.config = config or get_config()
        self.learning_rate = learning_rate
        self.min_samples = min_samples

        # 現在の閾値（設定から初期化）
        self.silent_threshold = self.config.confidence.thresholds.silent
        self.notify_threshold = self.config.confidence.thresholds.notify
        self.confirm_threshold = self.config.confidence.thresholds.confirm

        # フィードバック履歴
        self.feedback_history: List[FeedbackRecord] = []

        logger.info(
            f"DynamicThresholdAdjuster initialized: "
            f"silent={self.silent_threshold}, notify={self.notify_threshold}, "
            f"confirm={self.confirm_threshold}"
        )

    def record_feedback(self, confidence: float, was_correct: bool):
        """
        ユーザーフィードバックを記録

        Args:
            confidence: その時点の信頼度
            was_correct: 結果が正しかったか
        """
        self.feedback_history.append(FeedbackRecord(
            confidence=confidence,
            was_correct=was_correct
        ))

        logger.debug(f"Feedback recorded: confidence={confidence}, correct={was_correct}")

        # 十分なサンプルがあれば閾値を調整
        if len(self.feedback_history) >= self.min_samples:
            self._adjust_thresholds()

    def _adjust_thresholds(self):
        """フィードバックに基づいて閾値を調整"""
        recent = self.feedback_history[-self.min_samples:]

        # 偽陽性: 高信頼度（> notify）だが誤り
        false_positives = sum(
            1 for r in recent
            if r.confidence > self.notify_threshold and not r.was_correct
        )

        # 偽陰性: 低信頼度（< confirm）だが正解
        false_negatives = sum(
            1 for r in recent
            if r.confidence < self.confirm_threshold and r.was_correct
        )

        # 調整判定
        fp_rate = false_positives / len(recent)
        fn_rate = false_negatives / len(recent)

        if fp_rate > 0.3:  # 偽陽性率が30%を超えたら
            self._raise_thresholds()
            logger.info(f"Thresholds raised due to high FP rate: {fp_rate:.1%}")

        elif fn_rate > 0.3:  # 偽陰性率が30%を超えたら
            self._lower_thresholds()
            logger.info(f"Thresholds lowered due to high FN rate: {fn_rate:.1%}")

    def _raise_thresholds(self):
        """閾値を引き上げ（より慎重に）"""
        self.silent_threshold = min(0.95, self.silent_threshold + self.learning_rate)
        self.notify_threshold = min(0.85, self.notify_threshold + self.learning_rate)
        self.confirm_threshold = min(0.6, self.confirm_threshold + self.learning_rate)

    def _lower_thresholds(self):
        """閾値を引き下げ（より積極的に）"""
        self.silent_threshold = max(0.8, self.silent_threshold - self.learning_rate)
        self.notify_threshold = max(0.6, self.notify_threshold - self.learning_rate)
        self.confirm_threshold = max(0.3, self.confirm_threshold - self.learning_rate)

    def get_level(self, confidence: float) -> InterventionLevel:
        """
        現在の閾値に基づいて介入レベルを判定

        Args:
            confidence: 信頼度スコア

        Returns:
            InterventionLevel: 介入レベル
        """
        if confidence >= self.silent_threshold:
            return InterventionLevel.SILENT
        elif confidence >= self.notify_threshold:
            return InterventionLevel.NOTIFY
        elif confidence >= self.confirm_threshold:
            return InterventionLevel.CONFIRM
        else:
            return InterventionLevel.ESCALATE

    def get_current_thresholds(self) -> Dict[str, float]:
        """現在の閾値を取得"""
        return {
            "silent": self.silent_threshold,
            "notify": self.notify_threshold,
            "confirm": self.confirm_threshold
        }

    def reset_thresholds(self):
        """閾値を初期値にリセット"""
        self.silent_threshold = self.config.confidence.thresholds.silent
        self.notify_threshold = self.config.confidence.thresholds.notify
        self.confirm_threshold = self.config.confidence.thresholds.confirm
        self.feedback_history.clear()

        logger.info("Thresholds reset to defaults")


# =============================================================================
# 確認フロー
# =============================================================================

class ConfirmationFlow:
    """
    計画確認フロー

    計画の確認→修正→実行のフローを管理
    """

    def __init__(
        self,
        handler: InterventionHandler,
        max_modifications: int = 3
    ):
        """
        Args:
            handler: 介入ハンドラー
            max_modifications: 最大修正回数
        """
        self.handler = handler
        self.max_modifications = max_modifications
        self.modification_count = 0

    def confirm_plan(
        self,
        plan: ExecutionPlan,
        confidence: float
    ) -> tuple[bool, Optional[ExecutionPlan]]:
        """
        計画の確認を行う

        Args:
            plan: 確認する計画
            confidence: 信頼度スコア

        Returns:
            tuple: (確認結果, 修正された計画 or None)
        """
        self.modification_count = 0

        while self.modification_count < self.max_modifications:
            response = self.handler.request_confirmation(plan, confidence)

            if response.action == InterventionAction.PROCEED:
                return True, plan

            elif response.action == InterventionAction.MODIFY:
                if response.modified_plan:
                    plan = response.modified_plan
                    self.modification_count += 1
                    logger.info(f"Plan modified (attempt {self.modification_count})")
                    continue
                else:
                    # 修正計画がない場合はキャンセル
                    return False, None

            elif response.action == InterventionAction.CANCEL:
                return False, None

            elif response.timeout_reached:
                logger.warning("Confirmation flow timeout")
                return False, None

        # 最大修正回数を超えた
        logger.warning(f"Max modifications reached ({self.max_modifications})")
        return False, None


# =============================================================================
# ファクトリ関数
# =============================================================================

def create_intervention_handler(
    config: Optional[GraceConfig] = None,
    on_notify: Optional[Callable[[str], None]] = None,
    on_confirm: Optional[Callable[[InterventionRequest], InterventionResponse]] = None,
    on_escalate: Optional[Callable[[InterventionRequest], InterventionResponse]] = None,
) -> InterventionHandler:
    """InterventionHandlerインスタンスを作成"""
    return InterventionHandler(
        config=config,
        on_notify=on_notify,
        on_confirm=on_confirm,
        on_escalate=on_escalate
    )


def create_threshold_adjuster(
    config: Optional[GraceConfig] = None,
    learning_rate: float = 0.05
) -> DynamicThresholdAdjuster:
    """DynamicThresholdAdjusterインスタンスを作成"""
    return DynamicThresholdAdjuster(config=config, learning_rate=learning_rate)


def create_confirmation_flow(
    handler: InterventionHandler,
    max_modifications: int = 3
) -> ConfirmationFlow:
    """ConfirmationFlowインスタンスを作成"""
    return ConfirmationFlow(handler=handler, max_modifications=max_modifications)


# =============================================================================
# エクスポート
# =============================================================================

__all__ = [
    # Data classes
    "InterventionRequest",
    "InterventionResponse",
    "FeedbackRecord",

    # Enums
    "InterventionAction",

    # Handlers
    "InterventionHandler",
    "DynamicThresholdAdjuster",
    "ConfirmationFlow",

    # Factory functions
    "create_intervention_handler",
    "create_threshold_adjuster",
    "create_confirmation_flow",
]