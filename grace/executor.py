# grace/executor.py
"""
GRACE Executor - 計画実行エージェント
生成された計画を順次実行し、結果を管理
"""

import logging
import time
from typing import Dict, Literal, Optional, List, Callable, Any, Generator, cast
from dataclasses import dataclass, field
from enum import Enum

from .schemas import (
    ExecutionPlan,
    PlanStep,
    StepResult,
    ExecutionResult,
    StepStatus,
    create_plan_id,
)
from .tools import ToolRegistry, ToolResult, create_tool_registry
from .config import get_config, GraceConfig
from .confidence import (
    ConfidenceCalculator,
    ConfidenceFactors,
    ConfidenceScore,
    LLMSelfEvaluator,
    ConfidenceAggregator,
    ActionDecision,
    InterventionLevel,
    create_confidence_calculator,
    create_llm_evaluator,
    create_confidence_aggregator,
    create_query_coverage_calculator,
    create_source_agreement_calculator,
)
from .intervention import (
    InterventionHandler,
    InterventionRequest,
    InterventionResponse,
    InterventionAction,
    create_intervention_handler,
)

# === Legacy Agent Integration ===
try:
    from services.agent_service import ReActAgent, get_available_collections_from_qdrant_helper
    LEGACY_AGENT_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("Failed to import services.agent_service. Legacy agent execution will fail.")
    LEGACY_AGENT_AVAILABLE = False
# ================================

# [MIGRATION] create_llm_client を追加
try:
    from helper.helper_llm import create_llm_client
    _LLM_CLIENT_AVAILABLE = True
except ImportError:
    _LLM_CLIENT_AVAILABLE = False
# ベンチマーク用トークン集計
try:
    from helper.helper_llm import (
        reset_token_counter as _reset_token_counter,
        get_token_counter   as _get_token_counter,
        LLM_PRICING         as _LLM_PRICING,
    )
    _TOKEN_TRACKING_AVAILABLE = True
except ImportError:
    _TOKEN_TRACKING_AVAILABLE = False
    def _reset_token_counter() -> None: pass
    def _get_token_counter()   -> dict: return {}
    _LLM_PRICING: dict = {}

logger = logging.getLogger(__name__)


@dataclass
class ExecutionState:
    plan: ExecutionPlan
    current_step_id: int = 0
    step_results: Dict[int, StepResult] = field(default_factory=dict)
    step_statuses: Dict[int, StepStatus] = field(default_factory=dict)
    overall_confidence: float = 0.0
    is_cancelled: bool = False
    is_paused: bool = False
    intervention_request: Optional[Any] = None
    replan_count: int = 0
    max_replans: int = 3
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    def __post_init__(self):
        for step in self.plan.steps:
            self.step_statuses[step.step_id] = StepStatus.PENDING

    def get_completed_outputs(self) -> Dict[int, str]:
        return {
            step_id: result.output
            for step_id, result in self.step_results.items()
            if result.status == "success"
        }

    def get_completed_sources(self) -> List[str]:
        sources = []
        for result in self.step_results.values():
            if result.status == "success" and result.sources:
                sources.extend(result.sources)
        return sources

    def can_replan(self) -> bool:
        return self.replan_count < self.max_replans and not self.is_cancelled

    def get_execution_time_ms(self) -> Optional[int]:
        if self.start_time is None:
            return None
        end = self.end_time or time.time()
        return int((end - self.start_time) * 1000)


from .replan import ReplanOrchestrator, create_replan_orchestrator


class Executor:
    def __init__(
            self,
            config: Optional[GraceConfig] = None,
            tool_registry: Optional[ToolRegistry] = None,
            on_step_start: Optional[Callable[[PlanStep], None]] = None,
            on_step_complete: Optional[Callable[[StepResult], None]] = None,
            on_intervention_required: Optional[Callable[[str, Dict], Any]] = None,
            on_confidence_update: Optional[Callable[[ConfidenceScore, ActionDecision], None]] = None,
            on_replan: Optional[Callable[[str, int], None]] = None,
            replan_orchestrator: Optional[ReplanOrchestrator] = None,
            enable_replan: bool = True,
    ):
        self.config = config or get_config()
        self.tool_registry = tool_registry or create_tool_registry(config=self.config)
        self.confidence_calculator = create_confidence_calculator(config=self.config)
        self.llm_evaluator = create_llm_evaluator(config=self.config)
        self.query_coverage_calculator = create_query_coverage_calculator(config=self.config)
        self.confidence_aggregator = create_confidence_aggregator(config=self.config)
        self.on_step_start = on_step_start
        self.on_step_complete = on_step_complete
        self.on_intervention_required = on_intervention_required
        self.on_confidence_update = on_confidence_update
        self.on_replan = on_replan
        self.intervention_handler = create_intervention_handler(
            config=self.config,
            on_notify=self._handle_intervention_notify,
            on_confirm=self._handle_intervention_confirm,
            on_escalate=self._handle_intervention_escalate,
        )
        if replan_orchestrator is not None:
            self.replan_orchestrator = replan_orchestrator
        elif enable_replan:
            self.replan_orchestrator = create_replan_orchestrator(config=self.config)
        else:
            self.replan_orchestrator = None
        self.step_confidence_scores: Dict[int, ConfidenceScore] = {}
        replan_status = "enabled" if self.replan_orchestrator else "disabled"
        logger.info(f"Executor (GRACE Native) initialized: tools={self.tool_registry.list_tools()}, replan={replan_status}")

    def execute_plan_generator(self, plan: ExecutionPlan, state: Optional[ExecutionState] = None) -> Generator[ExecutionState, None, ExecutionResult]:
        logger.info(f"Executing plan (generator): {plan.plan_id}, steps={len(plan.steps)}")
        logger.info(f"Received Execution Plan in Executor (generator):\n{plan.model_dump_json(indent=2)}")
        if state is None:
            state = ExecutionState(plan=plan)
            state.start_time = time.time()
        try:
            steps_to_execute = [s for s in plan.steps if state.step_statuses.get(s.step_id) != StepStatus.SUCCESS]
            for step in steps_to_execute:
                state.current_step_id = step.step_id
                if state.is_cancelled:
                    logger.info("Execution cancelled")
                    break
                if state.step_statuses.get(step.step_id) == StepStatus.SKIPPED:
                    yield state
                    continue
                if not self._check_dependencies(step, state):
                    state.step_statuses[step.step_id] = StepStatus.SKIPPED
                    yield state
                    continue
                state.step_statuses[step.step_id] = StepStatus.RUNNING
                if self.on_step_start:
                    self.on_step_start(step)
                step_execution = self._execute_step(step, state)
                result = None
                if isinstance(step_execution, Generator):
                    result = yield from step_execution
                else:
                    result = step_execution
                state.step_results[step.step_id] = result
                state.step_statuses[step.step_id] = (StepStatus.SUCCESS if result.status == "success" else StepStatus.FAILED)
                if step.action == "rag_search" and result.status == "success":
                    rag_max_score = 0.0
                    if step.step_id in self.step_confidence_scores:
                        rag_max_score = self.step_confidence_scores[step.step_id].factors.search_max_score
                    rag_threshold = self.config.qdrant.rag_sufficient_score
                    need_web_search = False
                    if rag_max_score < rag_threshold:
                        need_web_search = True
                    else:
                        is_relevant = self._evaluate_rag_relevance(query=step.query or step.description, rag_output=result.output or "")
                        if not is_relevant:
                            need_web_search = True
                    if need_web_search:
                        web_result = yield from self._execute_dynamic_web_search(step, state)
                        if web_result is None or web_result.status == "failed":
                            yield from self._execute_dynamic_ask_user(step, state)
                    else:
                        for future_step in steps_to_execute:
                            if future_step.action == "web_search" and future_step.step_id > step.step_id:
                                state.step_statuses[future_step.step_id] = StepStatus.SKIPPED
                if self.on_step_complete:
                    self.on_step_complete(result)
                if step.step_id in self.step_confidence_scores:
                    confidence_score = self.step_confidence_scores[step.step_id]
                    action_decision = self.confidence_calculator.decide_action(confidence_score)
                    if action_decision.level in [InterventionLevel.CONFIRM, InterventionLevel.ESCALATE]:
                        state.is_paused = True
                        message = f"信頼度が低いため確認が必要です ({confidence_score.score:.2f})"
                        if action_decision.reason:
                            message += f"\n理由: {action_decision.reason}"
                        state.intervention_request = InterventionRequest(
                            level=action_decision.level, step_id=step.step_id, message=message,
                            reason=action_decision.reason, confidence_score=confidence_score.score, plan=plan
                        )
                        yield state
                        return self._create_execution_result(state)
                    self._handle_intervention_if_needed(action_decision, step, state)
                yield state
                if step.action == "ask_user" and result.status == "success":
                    pass
                if result.status == "failed" and self.replan_orchestrator:
                    replan_result = self.replan_orchestrator.handle_step_failure(
                        step_result=result, current_plan=plan, completed_results=state.step_results, replan_count=state.replan_count
                    )
                    if replan_result and replan_result.success and replan_result.new_plan:
                        state.replan_count += 1
                        state.plan = replan_result.new_plan
                        yield from self.execute_plan_generator(replan_result.new_plan, state)
                        return self._create_execution_result(state)
            state.overall_confidence = self._calculate_overall_confidence(state)
            state.end_time = time.time()
            return self._create_execution_result(state)
        except Exception as e:
            logger.error(f"Execution failed: {e}", exc_info=True)
            state.end_time = time.time()
            return ExecutionResult(
                plan_id=plan.plan_id or create_plan_id(), original_query=plan.original_query,
                final_answer=f"実行エラー: {str(e)}", step_results=list(state.step_results.values()),
                overall_confidence=0.0, overall_status="failed", replan_count=state.replan_count,
                total_execution_time_ms=state.get_execution_time_ms(), total_token_usage=None, total_cost_usd=None,
            )

    def execute_plan(self, plan: ExecutionPlan) -> ExecutionResult:
        logger.info(f"Executing plan: {plan.plan_id}, steps={len(plan.steps)}")
        logger.info(f"Received Execution Plan in Executor (blocking):\n{plan.model_dump_json(indent=2)}")
        state = ExecutionState(plan=plan)
        state.start_time = time.time()
        try:
            for step in plan.steps:
                if state.is_cancelled:
                    break
                if not self._check_dependencies(step, state):
                    state.step_statuses[step.step_id] = StepStatus.SKIPPED
                    continue
                state.step_statuses[step.step_id] = StepStatus.RUNNING
                if self.on_step_start:
                    self.on_step_start(step)
                step_execution = self._execute_step(step, state)
                result = None
                if isinstance(step_execution, Generator):
                    try:
                        while True:
                            event = next(step_execution)
                            if isinstance(event, dict) and event.get("type") == "log":
                                logger.info(event.get("content"))
                    except StopIteration as e:
                        result = e.value
                else:
                    result = step_execution
                state.step_results[step.step_id] = result
                state.step_statuses[step.step_id] = (StepStatus.SUCCESS if result.status == "success" else StepStatus.FAILED)
                if self.on_step_complete:
                    self.on_step_complete(result)
                if step.action == "ask_user" and result.status == "success":
                    if self.on_intervention_required and isinstance(result.output, str):
                        try:
                            output_data = eval(result.output) if result.output.startswith("{}") else {"question": result.output}
                        except Exception:
                            output_data = {"question": result.output}
                        user_response = self.on_intervention_required("ask_user", output_data)
                        if user_response:
                            result.output = f"ユーザー応答: {user_response}"
                            state.step_results[step.step_id] = result
                if result.status == "failed" and self.replan_orchestrator:
                    replan_result = self.replan_orchestrator.handle_step_failure(
                        step_result=result, current_plan=plan, completed_results=state.step_results, replan_count=state.replan_count
                    )
                    if replan_result and replan_result.success and replan_result.new_plan:
                        state.replan_count += 1
                        return self.execute_plan(replan_result.new_plan)
            state.overall_confidence = self._calculate_overall_confidence(state)
            state.end_time = time.time()
            return self._create_execution_result(state)
        except Exception as e:
            logger.error(f"Execution failed: {e}", exc_info=True)
            state.end_time = time.time()
            return ExecutionResult(
                plan_id=plan.plan_id or create_plan_id(), original_query=plan.original_query,
                final_answer=f"実行エラー: {str(e)}", step_results=list(state.step_results.values()),
                overall_confidence=0.0, overall_status="failed", replan_count=state.replan_count,
                total_execution_time_ms=state.get_execution_time_ms(), total_token_usage=None, total_cost_usd=None,
            )

    def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        """execute_plan() の統一エントリーポイント（benchmark.py 互換）"""
        return self.execute_plan(plan)

    def _check_dependencies(self, step: PlanStep, state: ExecutionState) -> bool:
        for dep_id in step.depends_on:
            if dep_id not in state.step_results:
                return False
            if state.step_results[dep_id].status == "failed":
                return False
        return True

    def _execute_step(self, step: PlanStep, state: ExecutionState) -> Any:
        logger.info(f"Executing step {step.step_id}: {step.action} - {step.description}")
        start_time = time.time()
        try:
            tool = self.tool_registry.get(step.action)
            if tool is None and step.action == "run_legacy_agent":
                return self._execute_legacy_agent_step(step, state, start_time)
            if tool is None:
                raise ValueError(f"Unknown action: {step.action}")
            kwargs = self._prepare_tool_kwargs(step, state)
            if _TOKEN_TRACKING_AVAILABLE:
                _reset_token_counter()
            tool_result: ToolResult = tool.execute(**kwargs)
            if tool_result.success and tool_result.output:
                import json
                try:
                    out_display = json.dumps(tool_result.output, indent=2, ensure_ascii=False) if isinstance(tool_result.output, (list, dict)) else str(tool_result.output)
                except Exception:
                    out_display = str(tool_result.output)
                yield {"type": "log", "content": f"📝 【ツール実行結果: {step.action}】\n{out_display}"}
            execution_time = int((time.time() - start_time) * 1000)
            confidence = self._llm_calculate_step_confidence(tool_result, step, state)
            sources = self._extract_sources(tool_result)
            _tu = _get_token_counter() if _TOKEN_TRACKING_AVAILABLE else {}
            _step_token_usage = _tu if (_tu.get("input_tokens") or _tu.get("output_tokens")) else None
            return StepResult(
                step_id=step.step_id, status="success" if tool_result.success else "failed",
                output=self._format_output(tool_result.output), confidence=confidence, sources=sources,
                error=tool_result.error if not tool_result.success else None,
                execution_time_ms=execution_time, token_usage=_step_token_usage,
            )
        except Exception as e:
            logger.error(f"Step {step.step_id} failed: {e}")
            execution_time = int((time.time() - start_time) * 1000)
            if step.fallback:
                fallback_result = self._execute_fallback(step, state)
                if fallback_result.status == "success":
                    return fallback_result
            return StepResult(step_id=step.step_id, status="failed", output=None, confidence=0.0, error=str(e), execution_time_ms=execution_time, token_usage=None)

    def _execute_legacy_agent_step(self, step: PlanStep, state: ExecutionState, start_time: float) -> Generator[Any, None, StepResult]:
        if not LEGACY_AGENT_AVAILABLE:
            raise ImportError("agent_service module not found")
        available_collections = get_available_collections_from_qdrant_helper()
        if not available_collections:
            available_collections = self.config.qdrant.search_priority
        agent = ReActAgent(selected_collections=available_collections, model_name=self.config.llm.model)
        query = step.query or step.description
        final_answer = ""
        sources = []
        for event in agent.execute_turn(query):
            yield event
            if event["type"] == "log":
                logger.info(f"[LegacyAgent] {event['content']}")
            elif event["type"] == "tool_result":
                if "Source:" in event["content"]:
                    import re
                    found_sources = re.findall(r"Source:\s*([a-zA-Z0-9_.\-]+)", event["content"])
                    if found_sources:
                        sources.extend(found_sources)
            elif event["type"] == "final_answer":
                final_answer = event["content"]
        execution_time = int((time.time() - start_time) * 1000)
        sources = list(set(sources))
        confidence = 0.8 if final_answer and "申し訳ありません" not in final_answer else 0.3
        conf_score_obj = ConfidenceScore(score=confidence, factors=ConfidenceFactors(source_count=len(sources), search_result_count=len(sources), llm_self_confidence=confidence))
        self.step_confidence_scores[step.step_id] = conf_score_obj
        if self.on_confidence_update:
            action = self.confidence_calculator.decide_action(conf_score_obj)
            self.on_confidence_update(conf_score_obj, action)
        return StepResult(step_id=step.step_id, status="success", output=final_answer, confidence=confidence, sources=sources, error=None, execution_time_ms=execution_time, token_usage=None)

    def _prepare_tool_kwargs(self, step: PlanStep, state: ExecutionState) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {"query": step.query or step.description}
        if step.action == "rag_search":
            kwargs["collection"] = step.collection
        elif step.action == "web_search":
            kwargs["num_results"] = self.config.web_search.num_results
            kwargs["language"] = self.config.web_search.language
        elif step.action == "reasoning":
            context_parts = []
            sources = []
            for dep_id in sorted(state.step_results.keys()):
                dep_result = state.step_results[dep_id]
                if dep_result.status != "success":
                    continue
                dep_output = dep_result.output
                if dep_output:
                    if isinstance(dep_output, str):
                        try:
                            if dep_output.startswith("[{") or dep_output.startswith("[{'"):
                                import ast
                                parsed = ast.literal_eval(dep_output)
                                if isinstance(parsed, list):
                                    sources.extend(parsed)
                                    continue
                        except (ValueError, SyntaxError):
                            pass
                        context_parts.append(f"--- 参照情報 (Step {dep_id}) ---\n{dep_output}")
                    elif isinstance(dep_output, list):
                        sources.extend(dep_output)
            if sources:
                kwargs["sources"] = sources
            if context_parts:
                kwargs["context"] = "\n\n".join(context_parts)
        elif step.action == "ask_user":
            kwargs.update({"question": step.query or step.description, "reason": f"ステップ {step.step_id}: {step.description}", "urgency": "blocking"})
        return kwargs

    def _evaluate_rag_relevance(self, query: str, rag_output: str) -> bool:
        prompt = (
            "以下の【検索結果】が、【ユーザーの質問】に対する回答として使えるかを判定してください。\n\n"
            f"【ユーザーの質問】\n{query}\n\n【検索結果】\n{rag_output[:500]}\n\n"
            "回答として使える場合は YES、使えない場合は NO とだけ回答してください。"
        )
        try:
            import time as _time
            if not _LLM_CLIENT_AVAILABLE:
                raise ImportError("helper_llm.create_llm_client が利用できません")
            llm = create_llm_client("openai", default_model=self.config.llm.model)
            t0 = _time.time()
            answer = llm.generate_content(prompt=prompt, temperature=0.0, max_completion_tokens=5).strip().upper()
            elapsed = _time.time() - t0
            is_relevant = "YES" in answer
            logger.info(f"RAG relevance check: '{answer}' -> {is_relevant} ({elapsed:.1f}s)")
            return is_relevant
        except Exception as e:
            logger.warning(f"RAG relevance check failed: {e}, defaulting to True")
            return True

    def _execute_dynamic_web_search(self, rag_step: PlanStep, state: ExecutionState) -> Generator:
        web_step_id = rag_step.step_id + 100
        web_step = PlanStep(step_id=web_step_id, action="web_search", description=f"[動的挿入] RAGスコア不足のためWeb検索を実行",
            query=rag_step.query, collection=None, depends_on=[rag_step.step_id], expected_output="Web検索結果", fallback=None, timeout_seconds=15)
        state.current_step_id = web_step_id
        state.step_statuses[web_step_id] = StepStatus.RUNNING
        if self.on_step_start:
            self.on_step_start(web_step)
        try:
            step_execution = self._execute_step(web_step, state)
            web_result = None
            if isinstance(step_execution, Generator):
                web_result = yield from step_execution
            else:
                web_result = step_execution
            state.step_results[web_step_id] = web_result
            state.step_statuses[web_step_id] = (StepStatus.SUCCESS if web_result.status == "success" else StepStatus.FAILED)
            if self.on_step_complete:
                self.on_step_complete(web_result)
            yield state
            return web_result
        except Exception as e:
            logger.error(f"Dynamic web_search failed: {e}")
            failed_result = StepResult(step_id=web_step_id, status="failed", output=None, confidence=0.0, error=str(e), execution_time_ms=0, token_usage=None)
            state.step_results[web_step_id] = failed_result
            state.step_statuses[web_step_id] = StepStatus.FAILED
            yield state
            return failed_result

    def _execute_dynamic_ask_user(self, rag_step: PlanStep, state: ExecutionState) -> Generator:
        ask_step_id = rag_step.step_id + 200
        ask_step = PlanStep(step_id=ask_step_id, action="ask_user", description=f"[動的挿入] 検索結果が不十分なためユーザーに確認",
            query=f"「{rag_step.query[:100]}」について検索しましたが、十分な情報が見つかりませんでした。追加情報があれば教えてください。",
            collection=None, depends_on=[rag_step.step_id], expected_output="ユーザーの指示", fallback=None)
        state.current_step_id = ask_step_id
        state.step_statuses[ask_step_id] = StepStatus.RUNNING
        if self.on_step_start:
            self.on_step_start(ask_step)
        try:
            step_execution = self._execute_step(ask_step, state)
            ask_result = None
            if isinstance(step_execution, Generator):
                ask_result = yield from step_execution
            else:
                ask_result = step_execution
            state.step_results[ask_step_id] = ask_result
            state.step_statuses[ask_step_id] = (StepStatus.SUCCESS if ask_result.status == "success" else StepStatus.FAILED)
            if self.on_step_complete:
                self.on_step_complete(ask_result)
            yield state
        except Exception as e:
            logger.error(f"Dynamic ask_user failed: {e}")
            yield state

    def _execute_fallback(self, step: PlanStep, state: ExecutionState) -> StepResult:
        fallback_step = PlanStep(
            step_id=step.step_id,
            action=cast(Literal["rag_search", "web_search", "reasoning", "ask_user", "code_execute", "run_legacy_agent"], step.fallback),
            description=f"[Fallback] {step.description}", query=step.query, collection=step.collection,
            depends_on=step.depends_on, expected_output=step.expected_output, fallback=None, timeout_seconds=step.timeout_seconds,
        )
        step_execution = self._execute_step(fallback_step, state)
        if isinstance(step_execution, Generator):
            try:
                while True:
                    next(step_execution)
            except StopIteration as e:
                return e.value
        return step_execution

    def _llm_calculate_step_confidence(self, tool_result: ToolResult, step: PlanStep, state: ExecutionState) -> float:
        if not tool_result.success:
            return 0.0
        factors = tool_result.confidence_factors
        extracted_sources = self._extract_sources(tool_result)
        source_count = factors.get("source_count", len(extracted_sources))
        source_agreement = 1.0
        if source_count > 1:
            texts = []
            if isinstance(tool_result.output, list):
                for item in tool_result.output:
                    if isinstance(item, dict):
                        payload = item.get("payload", {})
                        content = payload.get("content") or payload.get("text") or payload.get("answer")
                        if content:
                            texts.append(str(content))
            if len(texts) > 1:
                try:
                    sa_calc = create_source_agreement_calculator(config=self.config)
                    source_agreement = sa_calc.calculate(texts)
                except Exception as e:
                    logger.warning(f"Failed to calculate source_agreement: {e}")
                    source_agreement = 0.5
        current_result_count = factors.get("result_count", 0)
        current_max_score = factors.get("max_score", factors.get("avg_score", 0.0))
        current_avg_score = factors.get("avg_score", 0.0)
        if current_result_count == 0 and not (step.action in ["rag_search", "web_search"]):
            inherited_max = 0.0
            inherited_found = False
            for dep_id in step.depends_on:
                if dep_id in state.step_results:
                    dep_res = state.step_results[dep_id]
                    if dep_res.confidence > inherited_max:
                        inherited_max = dep_res.confidence
                        inherited_found = True
            if inherited_found:
                current_max_score = inherited_max
                current_avg_score = inherited_max
                current_result_count = 1
        confidence_factors = ConfidenceFactors(
            search_result_count=current_result_count, search_avg_score=current_avg_score,
            search_max_score=current_max_score, search_score_variance=factors.get("score_variance", 1.0),
            source_count=source_count, source_agreement=source_agreement,
            tool_success_rate=1.0 if tool_result.success else 0.0,
            tool_execution_count=1, tool_success_count=1 if tool_result.success else 0,
            is_search_step=(step.action in ["rag_search", "web_search"])
        )
        try:
            confidence_score = self.confidence_calculator.llm_calculate(factors=confidence_factors, step_description=step.description, tool_output=str(tool_result.output))
            if confidence_score.score < 0.6 and confidence_factors.is_search_step:
                heuristic_score = self.confidence_calculator.calculate(confidence_factors)
                if heuristic_score.score > confidence_score.score:
                    confidence_score = heuristic_score
        except Exception as e:
            logger.error(f"LLM confidence calculation failed: {e}, falling back to heuristic")
            confidence_score = self.confidence_calculator.calculate(confidence_factors)
        self.step_confidence_scores[step.step_id] = confidence_score
        action_decision = self.confidence_calculator.decide_action(confidence_score)
        if self.on_confidence_update:
            self.on_confidence_update(confidence_score, action_decision)
        logger.info(f"Step {step.step_id} confidence: {confidence_score.score:.2f} (level={confidence_score.level}, action={action_decision.level.value})")
        return confidence_score.score

    def _calculate_step_confidence(self, tool_result: ToolResult, step: PlanStep, state: ExecutionState) -> float:
        if not tool_result.success:
            return 0.0
        factors = tool_result.confidence_factors
        extracted_sources = self._extract_sources(tool_result)
        source_count = factors.get("source_count", len(extracted_sources))
        source_agreement = 1.0
        current_result_count = factors.get("result_count", 0)
        current_max_score = factors.get("max_score", factors.get("avg_score", 0.0))
        current_avg_score = factors.get("avg_score", 0.0)
        confidence_factors = ConfidenceFactors(
            search_result_count=current_result_count, search_avg_score=current_avg_score,
            search_max_score=current_max_score, search_score_variance=factors.get("score_variance", 1.0),
            source_count=source_count, source_agreement=source_agreement,
            tool_success_rate=1.0 if tool_result.success else 0.0,
            tool_execution_count=1, tool_success_count=1 if tool_result.success else 0,
            is_search_step=(step.action in ["rag_search", "web_search"])
        )
        confidence_score = self.confidence_calculator.calculate(confidence_factors)
        self.step_confidence_scores[step.step_id] = confidence_score
        action_decision = self.confidence_calculator.decide_action(confidence_score)
        if self.on_confidence_update:
            self.on_confidence_update(confidence_score, action_decision)
        return confidence_score.score

    def _extract_sources(self, tool_result: ToolResult) -> List[str]:
        sources = []
        if isinstance(tool_result.output, list):
            for item in tool_result.output:
                if isinstance(item, dict):
                    payload = item.get("payload", {})
                    source = payload.get("source", "")
                    if source and source not in sources:
                        sources.append(source)
        return sources

    def _format_output(self, output: Any) -> Optional[str]:
        if output is None:
            return None
        if isinstance(output, str):
            return output
        if isinstance(output, dict):
            return str(output)
        if isinstance(output, list):
            if output and isinstance(output[0], dict):
                return str(output)
            return "\n".join(str(item) for item in output)
        return str(output)

    def _calculate_overall_confidence(self, state: ExecutionState) -> float:
        if not state.step_results:
            return 0.0
        step_scores = list(self.step_confidence_scores.values())
        current_breakdown = {}
        if step_scores:
            current_breakdown = step_scores[-1].breakdown.copy()
        final_answer: Optional[str] = None
        for step in reversed(state.plan.steps):
            if (step.action in ["reasoning", "run_legacy_agent"]) and step.step_id in state.step_results:
                result = state.step_results[step.step_id]
                if result.status == "success":
                    final_answer = result.output
                    break
        if final_answer is not None:
            try:
                eval_result = self.llm_evaluator.evaluate(query=state.plan.original_query, answer=final_answer, sources=state.get_completed_sources())
                score_val = 0.0
                if hasattr(eval_result, 'score'):
                    score_val = eval_result.score
                elif isinstance(eval_result, (int, float)):
                    score_val = float(eval_result)
                current_breakdown["llm_self_eval"] = score_val
                llm_score = ConfidenceScore(score=score_val, factors=ConfidenceFactors(llm_self_confidence=score_val), breakdown=current_breakdown.copy())
                step_scores.append(llm_score)
            except Exception as e:
                logger.warning(f"LLM self-evaluation failed: {e}")
            try:
                coverage_score = self.query_coverage_calculator.calculate(query=state.plan.original_query, answer=final_answer)
                current_breakdown["query_coverage"] = coverage_score
                coverage_obj = ConfidenceScore(score=coverage_score, factors=ConfidenceFactors(query_coverage=coverage_score), breakdown=current_breakdown.copy())
                step_scores.append(coverage_obj)
                if self.on_confidence_update:
                    decision = ActionDecision(level=InterventionLevel.SILENT, confidence_score=coverage_score, reason="Final coverage evaluation completed")
                    self.on_confidence_update(coverage_obj, decision)
            except Exception as e:
                logger.warning(f"Query coverage evaluation failed: {e}")
        if step_scores:
            aggregated_score = self.confidence_aggregator.aggregate(scores=step_scores, method="weighted")
            return aggregated_score
        confidences = [r.confidence for r in state.step_results.values()]
        return sum(confidences) / len(confidences)

    def _create_execution_result(self, state: ExecutionState) -> ExecutionResult:
        statuses = [r.status for r in state.step_results.values()]
        overall_status: Literal["success", "partial", "failed", "cancelled"]
        if state.is_cancelled:
            overall_status = "cancelled"
        elif all(s == "success" for s in statuses):
            overall_status = "success"
        elif any(s == "success" for s in statuses):
            overall_status = "partial"
        else:
            overall_status = "failed"
        final_answer = None
        for step in reversed(state.plan.steps):
            if (step.action in ["reasoning", "run_legacy_agent"]) and step.step_id in state.step_results:
                result = state.step_results[step.step_id]
                if result.status == "success":
                    final_answer = result.output
                    break
        _total_in  = sum((sr.token_usage or {}).get("input_tokens",  0) for sr in state.step_results.values())
        _total_out = sum((sr.token_usage or {}).get("output_tokens", 0) for sr in state.step_results.values())
        _token_summary = ({"input_tokens": _total_in, "output_tokens": _total_out} if (_total_in or _total_out) else None)
        _total_cost: Optional[float] = None
        if _token_summary and _TOKEN_TRACKING_AVAILABLE:
            _pricing = _LLM_PRICING.get(self.config.llm.model, {"input": 0.0, "output": 0.0})
            _total_cost = round(_total_in * _pricing["input"] / 1000 + _total_out * _pricing["output"] / 1000, 6)
        return ExecutionResult(
            plan_id=state.plan.plan_id or create_plan_id(), original_query=state.plan.original_query,
            final_answer=final_answer, step_results=list(state.step_results.values()),
            overall_confidence=state.overall_confidence, overall_status=overall_status,
            replan_count=state.replan_count, total_execution_time_ms=state.get_execution_time_ms(),
            total_token_usage=_token_summary, total_cost_usd=_total_cost,
        )

    def cancel(self, state: ExecutionState):
        state.is_cancelled = True

    def resume(self, state: ExecutionState):
        state.is_paused = False

    def _handle_intervention_notify(self, message: str) -> None:
        logger.info(f"[NOTIFY] {message}")
        if self.on_intervention_required:
            self.on_intervention_required("notify", {"message": message})

    def _handle_intervention_confirm(self, request: InterventionRequest) -> InterventionResponse:
        logger.info(f"[CONFIRM] {request.message}")
        if self.on_intervention_required:
            user_response = self.on_intervention_required("confirm", {"message": request.message, "reason": request.reason, "options": request.options, "confidence": request.confidence_score})
            if user_response:
                if user_response in ["はい、続行", "proceed", "yes"]:
                    return InterventionResponse(action=InterventionAction.PROCEED)
                elif user_response in ["計画を修正", "modify"]:
                    return InterventionResponse(action=InterventionAction.MODIFY)
                elif user_response in ["キャンセル", "cancel", "no"]:
                    return InterventionResponse(action=InterventionAction.CANCEL)
                else:
                    return InterventionResponse(action=InterventionAction.INPUT, user_input=str(user_response))
        return InterventionResponse(action=InterventionAction.PROCEED)

    def _handle_intervention_escalate(self, request: InterventionRequest) -> InterventionResponse:
        logger.info(f"[ESCALATE] {request.message}")
        if self.on_intervention_required:
            user_response = self.on_intervention_required("escalate", {"message": request.message, "question": request.question, "reason": request.reason, "confidence": request.confidence_score})
            if user_response:
                return InterventionResponse(action=InterventionAction.INPUT, user_input=str(user_response))
        return InterventionResponse(action=InterventionAction.PROCEED, timeout_reached=True)

    def _handle_intervention_if_needed(self, action_decision: ActionDecision, step: PlanStep, state: ExecutionState) -> Optional[InterventionResponse]:
        if action_decision.level in [InterventionLevel.SILENT, InterventionLevel.NOTIFY]:
            if action_decision.level == InterventionLevel.NOTIFY:
                self.intervention_handler.handle(action_decision, step, state.plan)
            return None
        response = self.intervention_handler.handle(action_decision, step, state.plan)
        if response.action == InterventionAction.CANCEL:
            state.is_cancelled = True
        return response


def create_executor(config: Optional[GraceConfig] = None, tool_registry: Optional[ToolRegistry] = None, **kwargs) -> Executor:
    return Executor(config=config, tool_registry=tool_registry, **kwargs)


__all__ = ["ExecutionState", "Executor", "create_executor"]
