"""
GRACE Replan - 動的リプランニングシステム

失敗やフィードバックに応じて計画を動的に修正
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

from .schemas import ExecutionPlan, PlanStep, StepResult
from .planner import Planner, create_planner
from .config import get_config, GraceConfig

logger = logging.getLogger(__name__)


# =============================================================================
# リプラントリガー・戦略
# =============================================================================

class ReplanTrigger(str, Enum):
    """リプランのトリガー条件"""
    STEP_FAILED = "step_failed"  # ステップ実行失敗
    LOW_CONFIDENCE = "low_confidence"  # 信頼度が閾値未満
    USER_FEEDBACK = "user_feedback"  # ユーザーからの修正要求
    NEW_INFORMATION = "new_information"  # 新しい情報の発見
    TIMEOUT = "timeout"  # タイムアウト


class ReplanStrategy(str, Enum):
    """リプラン戦略"""
    PARTIAL = "partial"  # 失敗ステップ以降のみ再計画
    FULL = "full"  # 全体を再計画
    FALLBACK = "fallback"  # 代替アクションへ切り替え
    SKIP = "skip"  # 失敗ステップをスキップ
    ABORT = "abort"  # 実行中断


# =============================================================================
# リプランコンテキスト
# =============================================================================

@dataclass
class ReplanContext:
    """リプラン時のコンテキスト"""

    trigger: ReplanTrigger
    original_query: str
    failed_step_id: Optional[int] = None
    error_message: Optional[str] = None
    completed_results: Dict[int, StepResult] = field(default_factory=dict)
    user_feedback: Optional[str] = None
    new_information: Optional[str] = None
    replan_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def has_completed_steps(self) -> bool:
        """完了済みステップがあるか"""
        return len(self.completed_results) > 0

    @property
    def completed_step_ids(self) -> List[int]:
        """完了済みステップIDのリスト"""
        return sorted(self.completed_results.keys())

    def get_completed_outputs(self) -> Dict[int, str]:
        """完了済みステップの出力を取得"""
        return {
            step_id: result.output
            for step_id, result in self.completed_results.items()
            if result.output is not None
        }


@dataclass
class ReplanResult:
    """リプラン結果"""

    success: bool
    strategy: ReplanStrategy
    new_plan: Optional[ExecutionPlan] = None
    reason: str = ""
    replan_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)


# =============================================================================
# リプランマネージャー
# =============================================================================

class ReplanManager:
    """
    動的リプランニング管理

    失敗やフィードバックに応じて計画を動的に修正
    """

    def __init__(
            self,
            config: Optional[GraceConfig] = None,
            planner: Optional[Planner] = None,
    ):
        """
        Args:
            config: GRACE設定
            planner: 計画生成用Planner（Noneの場合は自動作成）
        """
        self.config = config or get_config()
        self.planner = planner

        # リプラン制限
        self.max_replans = self.config.replan.max_replans
        self.confidence_threshold = self.config.replan.confidence_threshold
        self.partial_replan_threshold = self.config.replan.partial_replan_threshold

        # リプラン履歴
        self.history: List[ReplanResult] = []

        logger.info(
            f"ReplanManager initialized: max_replans={self.max_replans}, "
            f"confidence_threshold={self.confidence_threshold}"
        )

    def _get_planner(self) -> Planner:
        """Plannerを取得（遅延初期化）"""
        if self.planner is None:
            self.planner = create_planner(config=self.config)
        return self.planner

    def should_replan(
            self,
            step_result: StepResult,
            replan_count: int
    ) -> tuple[bool, Optional[ReplanTrigger]]:
        """
        リプランが必要か判定

        Args:
            step_result: ステップ実行結果
            replan_count: 現在のリプラン回数

        Returns:
            (should_replan, trigger): リプラン要否とトリガー
        """
        # 最大リプラン回数チェック
        if replan_count >= self.max_replans:
            logger.warning(f"Max replans reached ({self.max_replans})")
            return False, None

        # ステップ失敗
        if step_result.status == "failed":
            logger.info(f"Step {step_result.step_id} failed, replan triggered")
            return True, ReplanTrigger.STEP_FAILED

        # 低信頼度
        if step_result.confidence < self.confidence_threshold:
            logger.info(
                f"Step {step_result.step_id} low confidence "
                f"({step_result.confidence:.2f} < {self.confidence_threshold}), "
                f"replan triggered"
            )
            return True, ReplanTrigger.LOW_CONFIDENCE

        return False, None

    def should_replan_from_feedback(
            self,
            feedback: str,
            replan_count: int
    ) -> tuple[bool, Optional[ReplanTrigger]]:
        """
        ユーザーフィードバックに基づいてリプラン要否を判定

        Args:
            feedback: ユーザーフィードバック
            replan_count: 現在のリプラン回数

        Returns:
            (should_replan, trigger): リプラン要否とトリガー
        """
        if replan_count >= self.max_replans:
            return False, None

        # フィードバックに修正要求が含まれているか
        modification_keywords = ["修正", "変更", "やり直し", "違う", "別の"]
        if any(kw in feedback for kw in modification_keywords):
            return True, ReplanTrigger.USER_FEEDBACK

        return False, None

    def determine_strategy(
            self,
            context: ReplanContext,
            current_plan: ExecutionPlan
    ) -> ReplanStrategy:
        """
        リプラン戦略を決定

        Args:
            context: リプランコンテキスト
            current_plan: 現在の計画

        Returns:
            ReplanStrategy: 選択された戦略
        """
        # 最大リプラン回数を超えていたら中断
        if context.replan_count >= self.max_replans:
            return ReplanStrategy.ABORT

        # ステップ失敗で代替手段がある場合
        if context.trigger == ReplanTrigger.STEP_FAILED:
            if context.failed_step_id:
                failed_step = self._find_step(current_plan, context.failed_step_id)
                if failed_step and failed_step.fallback:
                    logger.info(f"Fallback available for step {context.failed_step_id}")
                    return ReplanStrategy.FALLBACK

        # タイムアウトの場合は全体再計画
        if context.trigger == ReplanTrigger.TIMEOUT:
            return ReplanStrategy.FULL

        # ユーザーフィードバックの場合
        if context.trigger == ReplanTrigger.USER_FEEDBACK:
            # フィードバック内容に応じて判断
            if context.user_feedback and "最初から" in context.user_feedback:
                return ReplanStrategy.FULL
            return ReplanStrategy.PARTIAL

        # 序盤（最初の1/3）で失敗した場合は全体再計画
        if context.failed_step_id:
            progress = context.failed_step_id / len(current_plan.steps)
            if progress <= 0.34:
                logger.info(f"Early failure (progress={progress:.1%}), full replan")
                return ReplanStrategy.FULL

        # それ以外は部分再計画
        return ReplanStrategy.PARTIAL

    def create_new_plan(
            self,
            context: ReplanContext,
            strategy: ReplanStrategy,
            current_plan: ExecutionPlan
    ) -> ReplanResult:
        """
        新しい計画を生成

        Args:
            context: リプランコンテキスト
            strategy: リプラン戦略
            current_plan: 現在の計画

        Returns:
            ReplanResult: リプラン結果
        """
        logger.info(f"Creating new plan with strategy: {strategy.value}")

        try:
            if strategy == ReplanStrategy.FULL:
                new_plan = self._create_full_replan(context)
                result = ReplanResult(
                    success=True,
                    strategy=strategy,
                    new_plan=new_plan,
                    reason="全体再計画",
                    replan_count=context.replan_count + 1
                )

            elif strategy == ReplanStrategy.PARTIAL:
                new_plan = self._create_partial_replan(context, current_plan)
                result = ReplanResult(
                    success=True,
                    strategy=strategy,
                    new_plan=new_plan,
                    reason="部分再計画",
                    replan_count=context.replan_count + 1
                )

            elif strategy == ReplanStrategy.FALLBACK:
                new_plan = self._apply_fallback(context, current_plan)
                result = ReplanResult(
                    success=True,
                    strategy=strategy,
                    new_plan=new_plan,
                    reason="代替アクション適用",
                    replan_count=context.replan_count + 1
                )

            elif strategy == ReplanStrategy.SKIP:
                new_plan = self._skip_failed_step(context, current_plan)
                result = ReplanResult(
                    success=True,
                    strategy=strategy,
                    new_plan=new_plan,
                    reason="失敗ステップスキップ",
                    replan_count=context.replan_count + 1
                )

            elif strategy == ReplanStrategy.ABORT:
                result = ReplanResult(
                    success=False,
                    strategy=strategy,
                    new_plan=None,
                    reason="最大リプラン回数超過により中断",
                    replan_count=context.replan_count
                )

            else:
                result = ReplanResult(
                    success=False,
                    strategy=strategy,
                    new_plan=None,
                    reason=f"Unknown strategy: {strategy}",
                    replan_count=context.replan_count
                )

            # 履歴に記録
            self.history.append(result)
            return result

        except Exception as e:
            logger.error(f"Replan failed: {e}")
            result = ReplanResult(
                success=False,
                strategy=strategy,
                new_plan=None,
                reason=f"リプラン失敗: {str(e)}",
                replan_count=context.replan_count
            )
            self.history.append(result)
            return result

    def _create_full_replan(self, context: ReplanContext) -> ExecutionPlan:
        """全体再計画: エラー情報を含めて新規計画生成"""
        enhanced_query = self._enhance_query_with_context(
            context.original_query,
            context
        )

        planner = self._get_planner()
        new_plan = planner.create_plan(enhanced_query)

        # リプラン後は確認を推奨
        new_plan.requires_confirmation = True

        return new_plan

    def _create_partial_replan(
            self,
            context: ReplanContext,
            current_plan: ExecutionPlan
    ) -> ExecutionPlan:
        """部分再計画: 失敗ステップ以降を再生成"""
        if not context.failed_step_id:
            return current_plan

        # 完了済みステップを保持
        completed_steps = [
            step for step in current_plan.steps
            if step.step_id < context.failed_step_id
        ]

        # 残りのステップを再計画
        remaining_query = self._create_remaining_query(context, completed_steps)
        planner = self._get_planner()
        new_partial = planner.create_plan(remaining_query)

        # ステップIDを調整して結合
        adjusted_steps = self._adjust_step_ids(
            new_partial.steps,
            start_id=len(completed_steps) + 1,
            completed_count=len(completed_steps)
        )

        # 結合
        final_steps = completed_steps + adjusted_steps

        return ExecutionPlan(
            original_query=context.original_query,
            complexity=current_plan.complexity,
            estimated_steps=len(final_steps),
            requires_confirmation=True,
            steps=final_steps,
            success_criteria=current_plan.success_criteria
        )

    # --- TODO #3: 検索系アクションのフォールバック優先順位 ---
    _SEARCH_FALLBACK_CHAIN = {
        "rag_search": "web_search",  # RAG失敗 → Web検索
        "web_search": "rag_search",  # Web失敗 → RAG検索
    }

    def _apply_fallback(
            self,
            context: ReplanContext,
            current_plan: ExecutionPlan
    ) -> ExecutionPlan:
        """代替アクションを適用（フォールバックチェーン付き）"""
        if not context.failed_step_id:
            return current_plan

        new_steps = []
        for step in current_plan.steps:
            if step.step_id == context.failed_step_id and step.fallback:
                # --- TODO #3: fallback先が reasoning で、元が検索系の場合は web_search に昇格 ---
                fallback_action = step.fallback
                if fallback_action == "reasoning" and step.action in self._SEARCH_FALLBACK_CHAIN:
                    fallback_action = self._SEARCH_FALLBACK_CHAIN[step.action]
                    logger.info(
                        f"Fallback escalation: {step.action} → {step.fallback} "
                        f"overridden to → {fallback_action}"
                    )

                # 代替アクションに置き換え
                new_step = PlanStep(
                    step_id=step.step_id,
                    action=fallback_action,
                    description=f"[代替] {step.description}",
                    query=step.query,
                    collection=step.collection if fallback_action != "web_search" else None,
                    depends_on=step.depends_on,
                    expected_output=step.expected_output,
                    fallback=None  # 代替の代替はなし
                )
                new_steps.append(new_step)
            else:
                new_steps.append(step)

        return ExecutionPlan(
            original_query=current_plan.original_query,
            complexity=current_plan.complexity,
            estimated_steps=current_plan.estimated_steps,
            requires_confirmation=False,
            steps=new_steps,
            success_criteria=current_plan.success_criteria
        )

    def _skip_failed_step(
            self,
            context: ReplanContext,
            current_plan: ExecutionPlan
    ) -> ExecutionPlan:
        """失敗ステップをスキップ"""
        if not context.failed_step_id:
            return current_plan

        # 失敗ステップを除外
        new_steps = [
            step for step in current_plan.steps
            if step.step_id != context.failed_step_id
        ]

        # 依存関係を更新（失敗ステップへの依存を削除）
        for step in new_steps:
            step.depends_on = [
                dep for dep in step.depends_on
                if dep != context.failed_step_id
            ]

        return ExecutionPlan(
            original_query=current_plan.original_query,
            complexity=current_plan.complexity,
            estimated_steps=len(new_steps),
            requires_confirmation=True,
            steps=new_steps,
            success_criteria=current_plan.success_criteria
        )

    def _enhance_query_with_context(
            self,
            original_query: str,
            context: ReplanContext
    ) -> str:
        """エラーコンテキストを含めたクエリ生成"""
        hints = []

        if context.error_message:
            hints.append(f"注意: 前回の試行で「{context.error_message}」というエラーが発生")

        if context.completed_results:
            completed_info = [
                f"ステップ{sid}は完了済み"
                for sid in sorted(context.completed_results.keys())
            ]
            hints.append(f"進捗: {', '.join(completed_info)}")

        if context.user_feedback:
            hints.append(f"ユーザーフィードバック: {context.user_feedback}")

        if context.new_information:
            hints.append(f"追加情報: {context.new_information}")

        if hints:
            return f"{original_query}\n\n【追加情報】\n" + "\n".join(hints)

        return original_query

    def _create_remaining_query(
            self,
            context: ReplanContext,
            completed_steps: List[PlanStep]
    ) -> str:
        """残りステップの再計画クエリを生成"""
        return f"""以下の計画の続きを作成してください。

元の質問: {context.original_query}
完了済みステップ: {len(completed_steps)}個
失敗理由: {context.error_message or "不明"}

失敗したステップ以降の代替アプローチを提案してください。

重要: 出力は必ず以下のJSONスキーマに従った有効なJSONオブジェクトにしてください。
特に、'action' フィールドは以下のいずれかである必要があります:
- 'rag_search'
- 'reasoning'
- 'ask_user'
- 'web_search' (必要な場合)

JSON形式以外のテキスト（解説など）を含めないでください。
"""

    def _adjust_step_ids(
            self,
            steps: List[PlanStep],
            start_id: int,
            completed_count: int
    ) -> List[PlanStep]:
        """ステップIDを調整し、依存関係を直前の完了ステップに修正"""
        adjusted_steps = []
        new_id = start_id
        last_completed_id = completed_count  # 最後に完了したステップID

        for i, step in enumerate(steps):
            # 依存関係の再構築
            # リプランで生成されたステップの依存関係は、原則として
            # 「直前のステップ（完了済み、またはこのループで追加された前ステップ）」とする

            new_depends_on = []

            # 最初のステップなら、直近の完了済みステップに依存
            if i == 0:
                if last_completed_id > 0:
                    new_depends_on = [last_completed_id]
            else:
                # それ以降は、一つ前の新ステップに依存
                new_depends_on = [new_id - 1]

            adjusted_step = PlanStep(
                step_id=new_id,
                action=step.action,
                description=step.description,
                query=step.query,
                collection=step.collection,
                depends_on=new_depends_on,
                expected_output=step.expected_output,
                fallback=step.fallback
            )
            adjusted_steps.append(adjusted_step)
            new_id += 1

        return adjusted_steps

    def _find_step(
            self,
            plan: ExecutionPlan,
            step_id: int
    ) -> Optional[PlanStep]:
        """計画からステップを検索"""
        for step in plan.steps:
            if step.step_id == step_id:
                return step
        return None

    def can_replan(self, replan_count: int) -> bool:
        """リプラン可能か判定"""
        return replan_count < self.max_replans

    def get_history(self) -> List[ReplanResult]:
        """リプラン履歴を取得"""
        return self.history.copy()

    def clear_history(self):
        """リプラン履歴をクリア"""
        self.history.clear()


# =============================================================================
# リプランオーケストレーター
# =============================================================================

class ReplanOrchestrator:
    """
    リプランオーケストレーター

    Executor とReplanManager を統合し、
    自動リプランフローを管理
    """

    def __init__(
            self,
            config: Optional[GraceConfig] = None,
            replan_manager: Optional[ReplanManager] = None,
    ):
        """
        Args:
            config: GRACE設定
            replan_manager: リプランマネージャー
        """
        self.config = config or get_config()
        self.replan_manager = replan_manager or ReplanManager(config=self.config)

    def handle_step_failure(
            self,
            step_result: StepResult,
            current_plan: ExecutionPlan,
            completed_results: Dict[int, StepResult],
            replan_count: int
    ) -> Optional[ReplanResult]:
        """
        ステップ失敗時のリプラン処理

        Args:
            step_result: 失敗したステップの結果
            current_plan: 現在の計画
            completed_results: 完了済み結果
            replan_count: 現在のリプラン回数

        Returns:
            ReplanResult or None: リプラン結果（リプランしない場合はNone）
        """
        # リプラン要否判定
        should_replan, trigger = self.replan_manager.should_replan(
            step_result, replan_count
        )

        if not should_replan:
            return None

        # コンテキスト作成
        context = ReplanContext(
            trigger=trigger,
            original_query=current_plan.original_query,
            failed_step_id=step_result.step_id,
            error_message=step_result.error,
            completed_results=completed_results,
            replan_count=replan_count
        )

        # 戦略決定
        strategy = self.replan_manager.determine_strategy(context, current_plan)

        # リプラン実行
        return self.replan_manager.create_new_plan(context, strategy, current_plan)

    def handle_user_feedback(
            self,
            feedback: str,
            current_plan: ExecutionPlan,
            completed_results: Dict[int, StepResult],
            replan_count: int
    ) -> Optional[ReplanResult]:
        """
        ユーザーフィードバックによるリプラン処理

        Args:
            feedback: ユーザーフィードバック
            current_plan: 現在の計画
            completed_results: 完了済み結果
            replan_count: 現在のリプラン回数

        Returns:
            ReplanResult or None: リプラン結果
        """
        # リプラン要否判定
        should_replan, trigger = self.replan_manager.should_replan_from_feedback(
            feedback, replan_count
        )

        if not should_replan:
            return None

        # コンテキスト作成
        context = ReplanContext(
            trigger=trigger,
            original_query=current_plan.original_query,
            user_feedback=feedback,
            completed_results=completed_results,
            replan_count=replan_count
        )

        # 戦略決定
        strategy = self.replan_manager.determine_strategy(context, current_plan)

        # リプラン実行
        return self.replan_manager.create_new_plan(context, strategy, current_plan)


# =============================================================================
# ファクトリ関数
# =============================================================================

def create_replan_manager(
        config: Optional[GraceConfig] = None,
        planner: Optional[Planner] = None,
) -> ReplanManager:
    """ReplanManagerインスタンスを作成"""
    return ReplanManager(config=config, planner=planner)


def create_replan_orchestrator(
        config: Optional[GraceConfig] = None,
        replan_manager: Optional[ReplanManager] = None,
) -> ReplanOrchestrator:
    """ReplanOrchestratorインスタンスを作成"""
    return ReplanOrchestrator(config=config, replan_manager=replan_manager)


# =============================================================================
# エクスポート
# =============================================================================

__all__ = [
    # Enums
    "ReplanTrigger",
    "ReplanStrategy",

    # Data classes
    "ReplanContext",
    "ReplanResult",

    # Managers
    "ReplanManager",
    "ReplanOrchestrator",

    # Factory functions
    "create_replan_manager",
    "create_replan_orchestrator",
]
