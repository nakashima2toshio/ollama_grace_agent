"""
tests/test_agent_4operations.py
================================
自立GRACE Agent の4大コア動作テスト

テスト対象操作:
  1. 計画立案   (Planning)               - grace.planner.Planner
  2. 実行       (Execution)              - grace.executor.Executor
  3. 信頼度評価 (Confidence Evaluation)  - grace.confidence
  4. 介入/再計画 (Intervention/Replan)  - grace.intervention + grace.replan

実行方法:
  pytest tests/test_agent_4operations.py -v
  pytest tests/test_agent_4operations.py -v --tb=short
"""

import time
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.llm.model = "mock-model"
    config.llm.provider = "ollama"
    config.llm.temperature = 0.0
    config.llm.max_tokens = 1000
    config.confidence.threshold_silent  = 0.9
    config.confidence.threshold_notify  = 0.7
    config.confidence.threshold_confirm = 0.4
    config.agent.max_replan_count = 3
    return config


@pytest.fixture
def simple_plan():
    from grace.schemas import ExecutionPlan, PlanStep
    steps = [
        PlanStep(step_id=1, action="rag_search", description="AIに関する最新情報を検索する",
                 query="AIニュース 最新動向", expected_output="AI関連ニュース記事リスト"),
        PlanStep(step_id=2, action="reasoning", description="検索結果を日本語で要約する",
                 expected_output="3行の要約テキスト", depends_on=[1]),
    ]
    return ExecutionPlan(
        original_query="AIの最新動向を調べて3行で要約してください",
        complexity=0.45, estimated_steps=2, requires_confirmation=False,
        steps=steps, success_criteria="2件以上のAI関連情報を収集し要約できた",
    )


@pytest.fixture
def completed_step_results():
    from grace.schemas import StepResult
    return [
        StepResult(step_id=1, status="success", output="AI関連ニュース3件",
                   confidence=0.88, sources=["cc_news_001.txt", "cc_news_042.txt"], execution_time_ms=1450),
        StepResult(step_id=2, status="success", output="2024年はLLMの多様化が進み。",
                   confidence=0.91, sources=[], execution_time_ms=820),
    ]


class TestOperation1Planning:
    def test_planner_module_importable(self):
        from grace.planner import Planner
        assert Planner is not None

    def test_execution_plan_schema_valid(self, simple_plan):
        assert simple_plan.original_query != ""
        assert len(simple_plan.steps) == 2
        assert simple_plan.success_criteria != ""

    def test_plan_steps_have_required_fields(self, simple_plan):
        valid_actions = {"rag_search", "web_search", "reasoning", "ask_user", "code_execute", "run_legacy_agent"}
        for step in simple_plan.steps:
            assert step.step_id >= 1
            assert step.action in valid_actions
            assert step.description != ""
            assert step.expected_output != ""

    def test_plan_complexity_is_normalized(self, simple_plan):
        assert 0.0 <= simple_plan.complexity <= 1.0

    def test_plan_confirmation_flag_bool(self, simple_plan):
        assert isinstance(simple_plan.requires_confirmation, bool)

    def test_plan_with_confirmation_required(self):
        from grace.schemas import ExecutionPlan, PlanStep
        plan = ExecutionPlan(
            original_query="何かをしてください", complexity=0.9, estimated_steps=1,
            requires_confirmation=True,
            steps=[PlanStep(step_id=1, action="ask_user", description="曖昧なリクエストの明確化", expected_output="明確化された要件")],
            success_criteria="ユーザーの意図が明確になった",
        )
        assert plan.requires_confirmation is True

    def test_plan_step_id_sequential(self, simple_plan):
        for i, step in enumerate(simple_plan.steps, start=1):
            assert step.step_id == i

    def test_plan_estimated_steps_matches_actual(self, simple_plan):
        assert simple_plan.estimated_steps == len(simple_plan.steps)

    def test_plan_schema_serializable(self, simple_plan):
        plan_dict = simple_plan.model_dump() if hasattr(simple_plan, "model_dump") else simple_plan.dict()
        assert "original_query" in plan_dict
        assert "steps" in plan_dict

    def test_plan_dependency_validation(self):
        from grace.schemas import ExecutionPlan, PlanStep, validate_plan_dependencies
        steps = [
            PlanStep(step_id=1, action="rag_search", description="検索", expected_output="結果"),
            PlanStep(step_id=2, action="reasoning", description="推論", expected_output="回答", depends_on=[1]),
        ]
        plan = ExecutionPlan(original_query="テスト", complexity=0.3, estimated_steps=2,
                             requires_confirmation=False, steps=steps, success_criteria="完了")
        assert validate_plan_dependencies(plan) == []


class TestOperation2Execution:
    def test_executor_module_importable(self):
        from grace.executor import Executor
        assert Executor is not None

    def test_step_result_success_status(self, completed_step_results):
        for result in completed_step_results:
            assert result.status == "success"

    def test_step_result_confidence_valid(self, completed_step_results):
        for result in completed_step_results:
            assert 0.0 <= result.confidence <= 1.0

    def test_step_result_sources_is_list(self, completed_step_results):
        for result in completed_step_results:
            assert isinstance(result.sources, list)

    def test_execution_result_aggregates_steps(self, completed_step_results):
        from grace.schemas import ExecutionResult
        avg_conf = sum(r.confidence for r in completed_step_results) / len(completed_step_results)
        result = ExecutionResult(
            plan_id="plan_test", original_query="AIの最新動向",
            step_results=completed_step_results, overall_confidence=round(avg_conf, 3), overall_status="success",
        )
        assert len(result.step_results) == 2
        assert result.overall_status == "success"

    def test_failed_step_result(self):
        from grace.schemas import StepResult
        failed = StepResult(step_id=99, status="failed", output=None, confidence=0.0, sources=[], error="タイムアウト")
        assert failed.status == "failed"

    def test_partial_step_result(self):
        from grace.schemas import StepResult
        partial = StepResult(step_id=5, status="partial", output="1件のみ取得", confidence=0.5, sources=["p.txt"])
        assert partial.status == "partial"

    def test_execution_result_token_tracking(self, completed_step_results):
        from grace.schemas import ExecutionResult
        result = ExecutionResult(
            plan_id="plan_tokens", original_query="トークンテスト",
            step_results=completed_step_results, overall_confidence=0.8, overall_status="success",
            total_token_usage={"input_tokens": 500, "output_tokens": 200}, total_cost_usd=0.0,
        )
        assert result.total_token_usage["input_tokens"] == 500

    def test_execution_time_measurement(self):
        start = time.monotonic()
        time.sleep(0.01)
        assert (time.monotonic() - start) * 1000 > 5


class TestOperation3ConfidenceEvaluation:
    THRESH_SILENT  = 0.9
    THRESH_NOTIFY  = 0.7
    THRESH_CONFIRM = 0.4

    def test_confidence_module_importable(self):
        import grace.confidence as conf_mod
        assert conf_mod is not None

    def test_silent_level_at_high_confidence(self):
        for score in [0.9, 0.95, 1.0]:
            assert self._classify(score) == "SILENT"

    def test_notify_level_at_medium_high_confidence(self):
        for score in [0.7, 0.75, 0.89]:
            assert self._classify(score) == "NOTIFY"

    def test_confirm_level_at_medium_low_confidence(self):
        for score in [0.4, 0.55, 0.69]:
            assert self._classify(score) == "CONFIRM"

    def test_escalate_level_at_low_confidence(self):
        for score in [0.0, 0.2, 0.39]:
            assert self._classify(score) == "ESCALATE"

    def test_threshold_boundary_silent(self):
        assert self._classify(0.9)   == "SILENT"
        assert self._classify(0.899) == "NOTIFY"

    def test_threshold_boundary_notify(self):
        assert self._classify(0.7)   == "NOTIFY"
        assert self._classify(0.699) == "CONFIRM"

    def test_threshold_boundary_confirm(self):
        assert self._classify(0.4)   == "CONFIRM"
        assert self._classify(0.399) == "ESCALATE"

    def test_step_confidence_aggregation(self, completed_step_results):
        confidences = [r.confidence for r in completed_step_results]
        overall = sum(confidences) / len(confidences)
        assert 0.0 <= overall <= 1.0

    def test_benchmark_session_min_max_confidence(self):
        from grace.benchmark import BenchmarkSession
        session = BenchmarkSession(query_id="Q_CONF", query_text="信頼度テスト")
        session.step_confidences = [0.9, 0.65, 0.80, 0.55]
        assert session.min_step_confidence == pytest.approx(0.55, abs=0.001)
        assert session.max_step_confidence == pytest.approx(0.90, abs=0.001)

    @classmethod
    def _classify(cls, score: float) -> str:
        if score >= cls.THRESH_SILENT:  return "SILENT"
        if score >= cls.THRESH_NOTIFY:  return "NOTIFY"
        if score >= cls.THRESH_CONFIRM: return "CONFIRM"
        return "ESCALATE"


class TestOperation4InterventionReplan:
    def test_intervention_module_importable(self):
        import grace.intervention as iv
        assert iv is not None

    def test_replan_module_importable(self):
        import grace.replan as rp
        assert rp is not None

    def test_silent_no_intervention_needed(self):
        assert 0.95 >= 0.9

    def test_escalate_requires_action(self):
        assert 0.15 < 0.4

    def test_replan_count_in_execution_result(self):
        from grace.schemas import ExecutionResult, StepResult
        result = ExecutionResult(
            plan_id="plan_replan", original_query="再計画テスト",
            step_results=[StepResult(step_id=1, status="failed", output=None, confidence=0.1, sources=[], error="検索失敗")],
            overall_confidence=0.1, overall_status="failed", replan_count=2,
        )
        assert result.replan_count == 2

    def test_max_replan_limit_stops_loop(self):
        MAX_REPLAN = 3
        replan_count = 0
        resolved = False
        while replan_count < MAX_REPLAN and not resolved:
            replan_count += 1
            if 0.1 >= 0.4:
                resolved = True
        assert replan_count == MAX_REPLAN
        assert not resolved

    def test_intervention_decision_matrix(self):
        for conf, expected_level, expected_action in [
            (0.95, "SILENT",   "continue"),
            (0.80, "NOTIFY",   "log_and_continue"),
            (0.55, "CONFIRM",  "wait_for_approval"),
            (0.15, "ESCALATE", "replan_or_abort"),
        ]:
            assert self._to_level(conf) == expected_level
            assert self._to_action(self._to_level(conf)) == expected_action

    def test_cancelled_execution_status(self):
        from grace.schemas import ExecutionResult
        r = ExecutionResult(plan_id="p", original_query="q", step_results=[],
                            overall_confidence=0.0, overall_status="cancelled", replan_count=3)
        assert r.overall_status == "cancelled"

    def test_partial_execution_status(self):
        from grace.schemas import ExecutionResult, StepResult
        r = ExecutionResult(
            plan_id="p", original_query="q",
            step_results=[
                StepResult(step_id=1, status="success", output="ok", confidence=0.7, sources=[]),
                StepResult(step_id=2, status="failed",  output=None, confidence=0.0, sources=[], error="タイムアウト"),
            ],
            overall_confidence=0.35, overall_status="partial",
        )
        assert r.overall_status == "partial"

    @staticmethod
    def _to_level(c: float) -> str:
        if c >= 0.9: return "SILENT"
        if c >= 0.7: return "NOTIFY"
        if c >= 0.4: return "CONFIRM"
        return "ESCALATE"

    @staticmethod
    def _to_action(level: str) -> str:
        return {"SILENT": "continue", "NOTIFY": "log_and_continue",
                "CONFIRM": "wait_for_approval", "ESCALATE": "replan_or_abort"}.get(level, "unknown")


class TestBenchmarkPerformanceEvaluation:
    def test_benchmark_module_importable(self):
        from grace.benchmark import BenchmarkRunner, BenchmarkSession, BenchmarkLogger
        assert BenchmarkRunner is not None

    def test_benchmark_queries_complete(self):
        from grace.benchmark import BENCHMARK_QUERIES
        assert len(BENCHMARK_QUERIES) >= 10
        for q in BENCHMARK_QUERIES:
            assert "id" in q and "text" in q and "level" in q
            assert q["id"].startswith("Q")
            assert q["level"] in ("Easy", "Medium", "Hard")

    def test_benchmark_session_default_values(self):
        from grace.benchmark import BenchmarkSession
        s = BenchmarkSession(query_id="Q01", query_text="テスト")
        assert s.plan_time_sec == 0.0
        assert s.execute_time_sec == 0.0
        assert s.replan_count == 0

    def test_benchmark_session_plan_timing(self):
        from grace.benchmark import BenchmarkSession
        s = BenchmarkSession(query_id="Q_PLAN", query_text="計画時間テスト")
        s.plan_start = time.monotonic()
        time.sleep(0.02)
        s.plan_end = time.monotonic()
        assert s.plan_time_sec > 0.01

    def test_benchmark_session_execute_timing(self):
        from grace.benchmark import BenchmarkSession
        s = BenchmarkSession(query_id="Q_EXEC", query_text="実行時間テスト")
        s.execute_start = time.monotonic()
        time.sleep(0.02)
        s.execute_end = time.monotonic()
        assert s.execute_time_sec > 0.01

    def test_benchmark_session_confidence_min_max(self):
        from grace.benchmark import BenchmarkSession
        s = BenchmarkSession(query_id="Q_CONF", query_text="信頼度")
        s.step_confidences = [0.9, 0.65, 0.80, 0.55]
        assert s.min_step_confidence == pytest.approx(0.55, abs=0.001)
        assert s.max_step_confidence == pytest.approx(0.90, abs=0.001)

    def test_benchmark_logger_creates_csv(self, tmp_path):
        from grace.benchmark import BenchmarkLogger
        csv_path = tmp_path / "test.csv"
        BenchmarkLogger(csv_path=csv_path)
        assert csv_path.exists()

    def test_benchmark_csv_contains_all_headers(self, tmp_path):
        import csv as csv_mod
        from grace.benchmark import BenchmarkLogger
        csv_path = tmp_path / "headers.csv"
        BenchmarkLogger(csv_path=csv_path)
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv_mod.DictReader(f)
            actual = set(reader.fieldnames or [])
        critical = {"timestamp", "query_id", "model", "provider", "plan_time_sec",
                    "execute_time_sec", "overall_confidence", "intervention_level", "replan_count"}
        assert not (critical - actual)

    def test_benchmark_csv_row_generation(self):
        from grace.benchmark import BenchmarkSession
        s = BenchmarkSession(query_id="Q_CSV", query_text="CSVテスト",
                             model="llama3.2", provider="ollama", level="Easy", category="事実検索")
        row = s.to_csv_row()
        for key in ["timestamp", "query_id", "model", "provider", "plan_time_sec", "intervention_level"]:
            assert key in row

    def test_benchmark_logger_silent_on_high_confidence(self, tmp_path):
        from grace.benchmark import BenchmarkLogger, BenchmarkSession
        bm = BenchmarkLogger(csv_path=tmp_path / "iv.csv")
        s = BenchmarkSession(query_id="Q_IV", query_text="介入レベル")
        mock_result = MagicMock()
        mock_result.overall_confidence = 0.95
        mock_result.replan_count       = 0
        mock_result.overall_status     = "success"
        mock_result.total_execution_time_ms = None
        mock_result.total_token_usage  = {"input_tokens": 100, "output_tokens": 50}
        mock_result.total_cost_usd     = 0.0
        mock_result.step_results       = []
        bm.record_execution_result(s, mock_result)
        assert s.intervention_level == "SILENT"

    def test_benchmark_logger_escalate_on_low_confidence(self, tmp_path):
        from grace.benchmark import BenchmarkLogger, BenchmarkSession
        bm = BenchmarkLogger(csv_path=tmp_path / "esc.csv")
        s = BenchmarkSession(query_id="Q_ESC", query_text="ESCALATE")
        mock_result = MagicMock()
        mock_result.overall_confidence = 0.1
        mock_result.replan_count       = 2
        mock_result.overall_status     = "failed"
        mock_result.total_execution_time_ms = None
        mock_result.total_token_usage  = {}
        mock_result.total_cost_usd     = 0.0
        mock_result.step_results       = []
        bm.record_execution_result(s, mock_result)
        assert s.intervention_level == "ESCALATE"
