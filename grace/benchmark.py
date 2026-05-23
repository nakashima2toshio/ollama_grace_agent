"""
GRACE Benchmark Logger
"""

from __future__ import annotations

import csv
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BENCHMARK_LOG_DIR = Path("logs")
BENCHMARK_CSV_PATH = BENCHMARK_LOG_DIR / "benchmark_results.csv"

CSV_HEADERS: List[str] = [
    "timestamp", "session_id", "query_id", "query_text_short",
    "level", "category", "model", "provider", "run_number",
    "plan_time_sec", "plan_complexity", "plan_steps", "requires_confirmation",
    "execute_time_sec", "total_time_sec",
    "tool_calls", "rag_step_count", "sources_total",
    "overall_confidence", "min_step_confidence", "max_step_confidence",
    "intervention_level",
    "replan_count", "overall_status",
    "input_tokens", "output_tokens", "cost_usd",
    "accuracy_score", "completeness_score",
]

BENCHMARK_QUERIES: List[Dict[str, str]] = [
    {"id": "Q01", "level": "Easy",   "category": "事実検索",  "text": "cc_newsコレクションにある最近のAI関連ニュースを3件教えてください"},
    {"id": "Q02", "level": "Easy",   "category": "事実検索",  "text": "2024年に最も報道されたスポーツイベントは何ですか？"},
    {"id": "Q03", "level": "Medium", "category": "推論・比較", "text": "2023-2024年の気候変動に関するニュースから主要トレンドを比較してまとめてください"},
    {"id": "Q04", "level": "Medium", "category": "推論・比較", "text": "テクノロジー企業の人員削減ニュースを複数比較して、業界全体の傾向を分析してください"},
    {"id": "Q05", "level": "Hard",   "category": "推論・比較", "text": "エネルギー問題とインフレの関係を、複数のニュース記事から根拠を挙げて説明してください"},
    {"id": "Q06", "level": "Hard",   "category": "推論・比較", "text": "地政学的リスクが特定の産業に与えた影響を2022年から追って分析してください"},
    {"id": "Q07", "level": "Easy",   "category": "手順説明",  "text": "AIの倫理問題について、ニュースで報道された主な事例を時系列で教えてください"},
    {"id": "Q08", "level": "Medium", "category": "手順説明",  "text": "医療AI分野のここ２年のニュースをカテゴリ別に整理してください"},
    {"id": "Q09", "level": "Easy",   "category": "曘昧",      "text": "最近の重要なニュースを教えて"},
    {"id": "Q10", "level": "Easy",   "category": "曘昧",      "text": "あの件について詳しく教えて"},
    {"id": "Q11", "level": "Hard",   "category": "推論・比較", "text": "cc_newsに存在しないトピックを検索して、リプランが発生する過程を示してください"},
    {"id": "Q12", "level": "Hard",   "category": "推論・比較", "text": "5つ以上の異なるニュースソースの情報を統合して、2024年の総括レポートを作成してください"},
]


@dataclass
class BenchmarkSession:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    query_id: str = ""
    query_text: str = ""
    level: str = ""
    category: str = ""
    model: str = ""
    provider: str = ""
    run_number: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    plan_start: float = 0.0
    plan_end: float = 0.0
    execute_start: float = 0.0
    execute_end: float = 0.0
    plan_complexity: float = 0.0
    plan_steps: int = 0
    requires_confirmation: bool = False
    plan_id: str = ""
    tool_calls: int = 0
    rag_step_count: int = 0
    sources_total: int = 0
    step_confidences: List[float] = field(default_factory=list)
    overall_confidence: float = 0.0
    intervention_level: str = ""
    replan_count: int = 0
    overall_status: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    accuracy_score: Optional[float] = None
    completeness_score: Optional[float] = None

    @property
    def plan_time_sec(self) -> float:
        return round(self.plan_end - self.plan_start, 3) if self.plan_end > 0 and self.plan_start > 0 else 0.0

    @property
    def execute_time_sec(self) -> float:
        return round(self.execute_end - self.execute_start, 3) if self.execute_end > 0 and self.execute_start > 0 else 0.0

    @property
    def total_time_sec(self) -> float:
        start = self.plan_start if self.plan_start > 0 else self.execute_start
        end   = self.execute_end if self.execute_end > 0 else self.plan_end
        if start > 0 and end > 0:
            return round(end - start, 3)
        return round(self.plan_time_sec + self.execute_time_sec, 3)

    @property
    def min_step_confidence(self) -> float:
        return round(min(self.step_confidences), 3) if self.step_confidences else 0.0

    @property
    def max_step_confidence(self) -> float:
        return round(max(self.step_confidences), 3) if self.step_confidences else 0.0

    def to_csv_row(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp, "session_id": self.session_id,
            "query_id": self.query_id, "query_text_short": self.query_text[:50].replace("\n", " "),
            "level": self.level, "category": self.category, "model": self.model,
            "provider": self.provider, "run_number": self.run_number,
            "plan_time_sec": self.plan_time_sec, "plan_complexity": round(self.plan_complexity, 3),
            "plan_steps": self.plan_steps, "requires_confirmation": self.requires_confirmation,
            "execute_time_sec": self.execute_time_sec, "total_time_sec": self.total_time_sec,
            "tool_calls": self.tool_calls, "rag_step_count": self.rag_step_count,
            "sources_total": self.sources_total,
            "overall_confidence": round(self.overall_confidence, 3),
            "min_step_confidence": self.min_step_confidence, "max_step_confidence": self.max_step_confidence,
            "intervention_level": self.intervention_level, "replan_count": self.replan_count,
            "overall_status": self.overall_status, "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens, "cost_usd": round(self.cost_usd, 6),
            "accuracy_score": self.accuracy_score, "completeness_score": self.completeness_score,
        }


class BenchmarkLogger:
    _THRESH_SILENT:  float = 0.9
    _THRESH_NOTIFY:  float = 0.7
    _THRESH_CONFIRM: float = 0.4

    def __init__(self, csv_path: Optional[Path] = None) -> None:
        self.csv_path = csv_path or BENCHMARK_CSV_PATH
        BENCHMARK_LOG_DIR.mkdir(exist_ok=True)
        self._ensure_csv_headers()

    def _ensure_csv_headers(self) -> None:
        if not self.csv_path.exists():
            with open(self.csv_path, "w", newline="", encoding="utf-8") as fh:
                csv.DictWriter(fh, fieldnames=CSV_HEADERS).writeheader()

    def record_plan_result(self, session: BenchmarkSession, plan: Any) -> None:
        session.plan_complexity       = getattr(plan, "complexity", 0.0)
        session.plan_steps            = len(getattr(plan, "steps", []))
        session.requires_confirmation = getattr(plan, "requires_confirmation", False)
        session.plan_id               = getattr(plan, "plan_id", "") or ""

    def record_execution_result(self, session: BenchmarkSession, result: Any) -> None:
        session.overall_confidence = getattr(result, "overall_confidence", 0.0)
        session.replan_count       = getattr(result, "replan_count", 0)
        session.overall_status     = getattr(result, "overall_status", "")
        exec_ms = getattr(result, "total_execution_time_ms", None)
        if exec_ms and session.execute_time_sec == 0.0:
            session.execute_end = session.execute_start + exec_ms / 1000.0
        tu = getattr(result, "total_token_usage", None) or {}
        if isinstance(tu, dict):
            session.input_tokens  = tu.get("input_tokens")  or tu.get("prompt_tokens")    or 0
            session.output_tokens = tu.get("output_tokens") or tu.get("completion_tokens") or 0
        cost = getattr(result, "total_cost_usd", None)
        if cost is not None:
            session.cost_usd = float(cost)
        for step_result in getattr(result, "step_results", []):
            session.tool_calls += 1
            conf = getattr(step_result, "confidence", 0.0)
            session.step_confidences.append(conf)
            sources = getattr(step_result, "sources", []) or []
            if sources:
                session.rag_step_count += 1
                session.sources_total  += len(sources)
        session.intervention_level = self._score_to_intervention(session.overall_confidence)

    def _score_to_intervention(self, score: float) -> str:
        if score >= self._THRESH_SILENT:  return "SILENT"
        if score >= self._THRESH_NOTIFY:  return "NOTIFY"
        if score >= self._THRESH_CONFIRM: return "CONFIRM"
        return "ESCALATE"

    def finalize_and_log(self, session: BenchmarkSession) -> None:
        sep = "=" * 60
        lines = [
            f"\n[BENCHMARK] {sep}",
            f"[BENCHMARK] Query    : {session.query_id} | {session.level} | {session.category}",
            f"[BENCHMARK] Model    : {session.model} ({session.provider}) | Run: {session.run_number}",
            f"[BENCHMARK] {"-" * 58}",
            f"[BENCHMARK] [Plan]   時間:{session.plan_time_sec:.2f}s  複雑度:{session.plan_complexity:.2f}  ステップ:{session.plan_steps}",
            f"[BENCHMARK] [Execute]時間:{session.execute_time_sec:.2f}s  合計:{session.total_time_sec:.2f}s  Tool:{session.tool_calls}  RAG:{session.rag_step_count}",
            f"[BENCHMARK] [Conf]   overall:{session.overall_confidence:.3f}  min:{session.min_step_confidence:.3f}  max:{session.max_step_confidence:.3f}",
            f"[BENCHMARK] [Intv]   {session.intervention_level}  replan:{session.replan_count}  status:{session.overall_status}",
            f"[BENCHMARK] [Token]  in:{session.input_tokens:,}  out:{session.output_tokens:,}  cost:${session.cost_usd:.6f}",
            f"[BENCHMARK] {sep}\n",
        ]
        log_text = "\n".join(lines)
        logger.info(log_text)
        print(log_text)

    def save_to_csv(self, session: BenchmarkSession) -> None:
        with open(self.csv_path, "a", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=CSV_HEADERS).writerow(session.to_csv_row())
        logger.info("[BENCHMARK] CSV appended: %s", self.csv_path)


class BenchmarkRunner:
    def __init__(self, model_name=None, provider=None, config=None, csv_path=None):
        from .config import get_config as _get_config
        self.config     = config or _get_config()
        self.model_name = model_name or self.config.llm.model
        self.provider   = provider   or self.config.llm.provider
        self.bm_logger  = BenchmarkLogger(csv_path=csv_path)

    def run(self, query_id, query_text, run_number=1, level="", category=""):
        from .planner  import Planner
        from .executor import Executor

        session = BenchmarkSession(
            query_id=query_id, query_text=query_text,
            model=self.model_name, provider=self.provider,
            run_number=run_number, level=level, category=category,
        )

        try:
            try:
                planner = Planner(config=self.config, model_name=self.model_name)
            except TypeError:
                planner = Planner(config=self.config)
            session.plan_start = time.monotonic()
            plan = planner.create_plan(query_text)
            session.plan_end   = time.monotonic()
            self.bm_logger.record_plan_result(session, plan)

            try:
                executor = Executor(config=self.config, model_name=self.model_name)
            except TypeError:
                executor = Executor(config=self.config)
            session.execute_start = time.monotonic()
            result = self._call_execute(executor, plan)
            session.execute_end   = time.monotonic()
            self.bm_logger.record_execution_result(session, result)

        except Exception as exc:
            logger.error("[BENCHMARK] %s run%d failed: %s", query_id, run_number, exc, exc_info=True)
            session.overall_status = "failed"
            now = time.monotonic()
            if session.plan_end    == 0.0: session.plan_end    = now
            if session.execute_end == 0.0: session.execute_end = now

        finally:
            self.bm_logger.finalize_and_log(session)
            self.bm_logger.save_to_csv(session)

        return session

    @staticmethod
    def _call_execute(executor, plan):
        import types
        result = executor.execute(plan)
        if isinstance(result, types.GeneratorType):
            last = None
            for item in result: last = item
            return last
        return result

    def run_query_set(self, queries=None, runs_per_query=3):
        queries = queries or BENCHMARK_QUERIES
        sessions = []
        total = len(queries) * runs_per_query
        done  = 0
        for query in queries:
            for run in range(1, runs_per_query + 1):
                done += 1
                logger.info("[BENCHMARK] Progress %d/%d | %s Run %d/%d", done, total, query["id"], run, runs_per_query)
                sessions.append(self.run(
                    query_id=query["id"], query_text=query["text"],
                    run_number=run, level=query.get("level", ""), category=query.get("category", ""),
                ))
        logger.info("[BENCHMARK] All done: %d sessions. CSV => %s", done, self.bm_logger.csv_path)
        return sessions


__all__ = ["BENCHMARK_QUERIES", "CSV_HEADERS", "BENCHMARK_CSV_PATH", "BenchmarkSession", "BenchmarkLogger", "BenchmarkRunner"]
