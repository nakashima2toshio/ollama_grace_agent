"""
GRACE Benchmark Logger

GRACEエージェントの各フェーズ（Plan / Execute / Confidence /
Intervention / Replan）の性能指標を計測・記録・CSV出力するモジュール。

使用例::

    from grace.benchmark import BenchmarkRunner, BENCHMARK_QUERIES

    runner = BenchmarkRunner()          # config.llm.model / provider を自動取得
    session = runner.run(
        query_id="Q01",
        query_text="cc_newsから最近のAIニュースを3件教えて",
        level="Easy",
        category="事実検索",
    )

    # 全クエリセットを3回ずつ実行
    sessions = runner.run_query_set(runs_per_query=3)
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

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

BENCHMARK_LOG_DIR = Path("logs")
BENCHMARK_CSV_PATH = BENCHMARK_LOG_DIR / "benchmark_results.csv"

CSV_HEADERS: List[str] = [
    "timestamp", "session_id", "query_id", "query_text_short",
    "level", "category", "model", "provider", "run_number",
    # Plan フェーズ
    "plan_time_sec", "plan_complexity", "plan_steps", "requires_confirmation",
    # Execute フェーズ
    "execute_time_sec", "total_time_sec",
    "tool_calls", "rag_step_count", "sources_total",
    # Confidence
    "overall_confidence", "min_step_confidence", "max_step_confidence",
    # Intervention
    "intervention_level",
    # Replan
    "replan_count", "overall_status",
    # Cost / Tokens
    "input_tokens", "output_tokens", "cost_usd",
    # 品質スコア（後付け: LLM-Judge または手動）
    "accuracy_score", "completeness_score",
]

# ---------------------------------------------------------------------------
# 標準クエリセット
# ---------------------------------------------------------------------------

BENCHMARK_QUERIES: List[Dict[str, str]] = [
    # Easy / 事実検索
    {"id": "Q01", "level": "Easy",   "category": "事実検索",
     "text": "cc_newsコレクションにある最近のAI関連ニュースを3件教えてください"},
    {"id": "Q02", "level": "Easy",   "category": "事実検索",
     "text": "2024年に最も報道されたスポーツイベントは何ですか？"},
    # Medium / 推論・比較
    {"id": "Q03", "level": "Medium", "category": "推論・比較",
     "text": "2023-2024年の気候変動に関するニュースから主要トレンドを比較してまとめてください"},
    {"id": "Q04", "level": "Medium", "category": "推論・比較",
     "text": "テクノロジー企業の人員削減ニュースを複数比較して、業界全体の傾向を分析してください"},
    # Hard / 多段階推論
    {"id": "Q05", "level": "Hard",   "category": "推論・比較",
     "text": "エネルギー問題とインフレの関係を、複数のニュース記事から根拠を挙げて説明してください"},
    {"id": "Q06", "level": "Hard",   "category": "推論・比較",
     "text": "地政学的リスクが特定の産業に与えた影響を2022年から追って分析してください"},
    # Easy-Medium / 手順説明
    {"id": "Q07", "level": "Easy",   "category": "手順説明",
     "text": "AIの倫理問題について、ニュースで報道された主な事例を時系列で教えてください"},
    {"id": "Q08", "level": "Medium", "category": "手順説明",
     "text": "医療AI分野のここ2年のニュースをカテゴリ別に整理してください"},
    # Ambiguous / 曖昧（ESCALATE を誘発するテスト）
    {"id": "Q09", "level": "Easy",   "category": "曖昧",
     "text": "最近の重要なニュースを教えて"},
    {"id": "Q10", "level": "Easy",   "category": "曖昧",
     "text": "あの件について詳しく教えて"},
    # Hard / エラー回復・複合
    {"id": "Q11", "level": "Hard",   "category": "推論・比較",
     "text": "cc_newsに存在しないトピックを検索して、リプランが発生する過程を示してください"},
    {"id": "Q12", "level": "Hard",   "category": "推論・比較",
     "text": "5つ以上の異なるニュースソースの情報を統合して、2024年の総括レポートを作成してください"},
]


# ---------------------------------------------------------------------------
# BenchmarkSession
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkSession:
    """
    1回の実行セッションのベンチマークデータを保持するデータクラス。

    タイミングは ``time.monotonic()`` で計測し、plan_time_sec /
    execute_time_sec / total_time_sec は property で計算する。
    """

    # ── Identity ────────────────────────────────────────────────────────────
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    query_id: str = ""
    query_text: str = ""
    level: str = ""         # Easy / Medium / Hard
    category: str = ""      # 事実検索 / 推論・比較 / 手順説明 / 曖昧
    model: str = ""
    provider: str = ""
    run_number: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # ── Phase タイミング（monotonic秒） ─────────────────────────────────────
    plan_start: float = 0.0
    plan_end: float = 0.0
    execute_start: float = 0.0
    execute_end: float = 0.0

    # ── Plan フェーズ指標 ────────────────────────────────────────────────────
    plan_complexity: float = 0.0
    plan_steps: int = 0
    requires_confirmation: bool = False
    plan_id: str = ""

    # ── Execute フェーズ指標 ─────────────────────────────────────────────────
    tool_calls: int = 0         # 実行された全ステップ数
    rag_step_count: int = 0     # rag_search アクションのステップ数
    sources_total: int = 0      # 全ステップのソース数合計

    # ── Confidence 指標 ─────────────────────────────────────────────────────
    step_confidences: List[float] = field(default_factory=list)
    overall_confidence: float = 0.0

    # ── Intervention ────────────────────────────────────────────────────────
    intervention_level: str = ""   # SILENT / NOTIFY / CONFIRM / ESCALATE

    # ── Replan ──────────────────────────────────────────────────────────────
    replan_count: int = 0
    overall_status: str = ""

    # ── Cost / Tokens ────────────────────────────────────────────────────────
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    # ── 品質スコア（後付け） ───────────────────────────────────────────────
    accuracy_score: Optional[float] = None
    completeness_score: Optional[float] = None

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def plan_time_sec(self) -> float:
        """計画生成フェーズの所要時間（秒）"""
        if self.plan_end > 0 and self.plan_start > 0:
            return round(self.plan_end - self.plan_start, 3)
        return 0.0

    @property
    def execute_time_sec(self) -> float:
        """実行フェーズの所要時間（秒）"""
        if self.execute_end > 0 and self.execute_start > 0:
            return round(self.execute_end - self.execute_start, 3)
        return 0.0

    @property
    def total_time_sec(self) -> float:
        """Plan + Execute の合計所要時間（秒）"""
        start = self.plan_start if self.plan_start > 0 else self.execute_start
        end   = self.execute_end if self.execute_end > 0 else self.plan_end
        if start > 0 and end > 0:
            return round(end - start, 3)
        return round(self.plan_time_sec + self.execute_time_sec, 3)

    @property
    def min_step_confidence(self) -> float:
        """ステップ信頼度の最小値"""
        return round(min(self.step_confidences), 3) if self.step_confidences else 0.0

    @property
    def max_step_confidence(self) -> float:
        """ステップ信頼度の最大値"""
        return round(max(self.step_confidences), 3) if self.step_confidences else 0.0

    def to_csv_row(self) -> Dict[str, Any]:
        """CSV 1行分の辞書を返す"""
        return {
            "timestamp":           self.timestamp,
            "session_id":          self.session_id,
            "query_id":            self.query_id,
            "query_text_short":    self.query_text[:50].replace("\n", " "),
            "level":               self.level,
            "category":            self.category,
            "model":               self.model,
            "provider":            self.provider,
            "run_number":          self.run_number,
            "plan_time_sec":       self.plan_time_sec,
            "plan_complexity":     round(self.plan_complexity, 3),
            "plan_steps":          self.plan_steps,
            "requires_confirmation": self.requires_confirmation,
            "execute_time_sec":    self.execute_time_sec,
            "total_time_sec":      self.total_time_sec,
            "tool_calls":          self.tool_calls,
            "rag_step_count":      self.rag_step_count,
            "sources_total":       self.sources_total,
            "overall_confidence":  round(self.overall_confidence, 3),
            "min_step_confidence": self.min_step_confidence,
            "max_step_confidence": self.max_step_confidence,
            "intervention_level":  self.intervention_level,
            "replan_count":        self.replan_count,
            "overall_status":      self.overall_status,
            "input_tokens":        self.input_tokens,
            "output_tokens":       self.output_tokens,
            "cost_usd":            round(self.cost_usd, 6),
            "accuracy_score":      self.accuracy_score,
            "completeness_score":  self.completeness_score,
        }


# ---------------------------------------------------------------------------
# BenchmarkLogger
# ---------------------------------------------------------------------------

class BenchmarkLogger:
    """
    BenchmarkSession の内容を
    - ``[BENCHMARK]`` プレフィックス付きのフォーマットログ
    - ``logs/benchmark_results.csv`` への CSV 追記
    の両形式で出力する。
    """

    # Confidence → InterventionLevel の閾値（grace/config.py の ConfidenceThresholds と一致）
    _THRESH_SILENT:  float = 0.9
    _THRESH_NOTIFY:  float = 0.7
    _THRESH_CONFIRM: float = 0.4

    def __init__(self, csv_path: Optional[Path] = None) -> None:
        self.csv_path = csv_path or BENCHMARK_CSV_PATH
        BENCHMARK_LOG_DIR.mkdir(exist_ok=True)
        self._ensure_csv_headers()

    def _ensure_csv_headers(self) -> None:
        """CSV ファイルが存在しない場合のみヘッダー行を書き込む"""
        if not self.csv_path.exists():
            with open(self.csv_path, "w", newline="", encoding="utf-8") as fh:
                csv.DictWriter(fh, fieldnames=CSV_HEADERS).writeheader()

    # ── record helpers ──────────────────────────────────────────────────────

    def record_plan_result(self, session: BenchmarkSession, plan: Any) -> None:
        """
        Planner.create_plan() が返した ExecutionPlan の指標を session に記録する。

        Args:
            session: 記録対象のセッション
            plan: grace.schemas.ExecutionPlan インスタンス
        """
        session.plan_complexity       = getattr(plan, "complexity", 0.0)
        session.plan_steps            = len(getattr(plan, "steps", []))
        session.requires_confirmation = getattr(plan, "requires_confirmation", False)
        session.plan_id               = getattr(plan, "plan_id", "") or ""

        logger.debug(
            "[BENCHMARK] plan recorded: steps=%d complexity=%.2f requires_conf=%s",
            session.plan_steps, session.plan_complexity, session.requires_confirmation,
        )

    def record_execution_result(self, session: BenchmarkSession, result: Any) -> None:
        """
        Executor.execute() が返した ExecutionResult の指標を session に記録する。

        Args:
            session: 記録対象のセッション
            result: grace.schemas.ExecutionResult インスタンス
        """
        session.overall_confidence = getattr(result, "overall_confidence", 0.0)
        session.replan_count       = getattr(result, "replan_count", 0)
        session.overall_status     = getattr(result, "overall_status", "")

        # total_execution_time_ms が付いている場合はそちらも参照
        exec_ms = getattr(result, "total_execution_time_ms", None)
        if exec_ms and session.execute_time_sec == 0.0:
            session.execute_end = session.execute_start + exec_ms / 1000.0

        # Token usage（プロバイダーによってキー名が異なる）
        tu = getattr(result, "total_token_usage", None) or {}
        if isinstance(tu, dict):
            session.input_tokens  = (
                tu.get("input_tokens")  or tu.get("prompt_tokens")    or 0
            )
            session.output_tokens = (
                tu.get("output_tokens") or tu.get("completion_tokens") or 0
            )

        # Cost
        cost = getattr(result, "total_cost_usd", None)
        if cost is not None:
            session.cost_usd = float(cost)

        # ステップ別指標
        for step_result in getattr(result, "step_results", []):
            session.tool_calls += 1
            conf = getattr(step_result, "confidence", 0.0)
            session.step_confidences.append(conf)
            sources = getattr(step_result, "sources", []) or []
            if sources:
                session.rag_step_count += 1
                session.sources_total  += len(sources)

        # Confidence → Intervention Level
        session.intervention_level = self._score_to_intervention(
            session.overall_confidence
        )

        logger.debug(
            "[BENCHMARK] execution recorded: confidence=%.3f replan=%d status=%s",
            session.overall_confidence, session.replan_count, session.overall_status,
        )

    def _score_to_intervention(self, score: float) -> str:
        """信頼度スコアをInterventionLevel文字列に変換"""
        if score >= self._THRESH_SILENT:
            return "SILENT"
        if score >= self._THRESH_NOTIFY:
            return "NOTIFY"
        if score >= self._THRESH_CONFIRM:
            return "CONFIRM"
        return "ESCALATE"

    # ── output ──────────────────────────────────────────────────────────────

    def finalize_and_log(self, session: BenchmarkSession) -> None:
        """ベンチマーク結果をフォーマットして logger.info + print に出力"""
        sep  = "=" * 60
        dash = "-" * 58
        lines = [
            f"\n[BENCHMARK] {sep}",
            f"[BENCHMARK] Query    : {session.query_id} | {session.level} | {session.category}",
            f"[BENCHMARK] Model    : {session.model} ({session.provider}) | Run: {session.run_number}",
            f"[BENCHMARK] {dash}",
            f"[BENCHMARK] [Plan]",
            f"[BENCHMARK]   生成時間       : {session.plan_time_sec:.2f} 秒",
            f"[BENCHMARK]   複雑度スコア   : {session.plan_complexity:.2f}",
            f"[BENCHMARK]   計画ステップ数 : {session.plan_steps}",
            f"[BENCHMARK]   要確認フラグ   : {session.requires_confirmation}",
            f"[BENCHMARK] [Execute]",
            f"[BENCHMARK]   実行時間       : {session.execute_time_sec:.2f} 秒",
            f"[BENCHMARK]   合計時間       : {session.total_time_sec:.2f} 秒",
            f"[BENCHMARK]   ツール呼出回数 : {session.tool_calls}",
            f"[BENCHMARK]   RAGステップ数  : {session.rag_step_count}",
            f"[BENCHMARK]   ソース数合計   : {session.sources_total}",
            f"[BENCHMARK] [Confidence]",
            f"[BENCHMARK]   全体信頼度     : {session.overall_confidence:.3f}",
            f"[BENCHMARK]   ステップ最小   : {session.min_step_confidence:.3f}",
            f"[BENCHMARK]   ステップ最大   : {session.max_step_confidence:.3f}",
            f"[BENCHMARK] [Intervention]",
            f"[BENCHMARK]   Level          : {session.intervention_level}",
            f"[BENCHMARK] [Replan]",
            f"[BENCHMARK]   リプラン回数   : {session.replan_count}",
            f"[BENCHMARK]   ステータス     : {session.overall_status}",
            f"[BENCHMARK] [Cost / Tokens]",
            f"[BENCHMARK]   Input tokens   : {session.input_tokens:,}",
            f"[BENCHMARK]   Output tokens  : {session.output_tokens:,}",
            f"[BENCHMARK]   推定コスト     : ${session.cost_usd:.6f} USD",
            f"[BENCHMARK] {sep}\n",
        ]
        log_text = "\n".join(lines)
        logger.info(log_text)
        print(log_text)

    def save_to_csv(self, session: BenchmarkSession) -> None:
        """ベンチマーク結果を CSV ファイルに追記"""
        with open(self.csv_path, "a", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=CSV_HEADERS).writerow(session.to_csv_row())
        logger.info("[BENCHMARK] CSV appended: %s", self.csv_path)


# ---------------------------------------------------------------------------
# BenchmarkRunner
# ---------------------------------------------------------------------------

class BenchmarkRunner:
    """
    GRACEパイプライン全体（Plan → Execute → Confidence → Intervention → Replan）
    をラップし、1クエリまたはクエリセット全体のベンチマークを実行する。

    モデル名・プロバイダーは ``config.llm`` から自動取得するため、
    各リポジトリ（openai / gemini / ollama）でコードを変更せずに使用できる。
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        provider: Optional[str]   = None,
        config: Any               = None,
        csv_path: Optional[Path]  = None,
    ) -> None:
        from .config import get_config as _get_config

        self.config     = config or _get_config()
        self.model_name = model_name or self.config.llm.model
        self.provider   = provider   or self.config.llm.provider
        self.bm_logger  = BenchmarkLogger(csv_path=csv_path)

    # ── 単一クエリ実行 ──────────────────────────────────────────────────────

    def run(
        self,
        query_id:   str,
        query_text: str,
        run_number: int = 1,
        level:      str = "",
        category:   str = "",
    ) -> BenchmarkSession:
        """
        1クエリをフルパイプラインで実行し、各指標を計測して返す。

        Args:
            query_id:   クエリID（例: "Q01"）
            query_text: クエリ本文
            run_number: 同一クエリ内の試行番号（1〜3 を推奨）
            level:      難易度ラベル（"Easy" / "Medium" / "Hard"）
            category:   カテゴリラベル

        Returns:
            BenchmarkSession: 計測結果
        """
        from .planner  import Planner
        from .executor import Executor

        session = BenchmarkSession(
            query_id   = query_id,
            query_text = query_text,
            model      = self.model_name,
            provider   = self.provider,
            run_number = run_number,
            level      = level,
            category   = category,
        )

        try:
            # ── Phase 1: Plan ────────────────────────────────────────────
            planner = Planner(config=self.config, model_name=self.model_name)
            session.plan_start = time.monotonic()
            plan = planner.create_plan(query_text)
            session.plan_end   = time.monotonic()
            self.bm_logger.record_plan_result(session, plan)

            # ── Phase 2-5: Execute / Confidence / Intervention / Replan ──
            executor = Executor(config=self.config, model_name=self.model_name)
            session.execute_start = time.monotonic()
            result = self._call_execute(executor, plan)
            session.execute_end   = time.monotonic()
            self.bm_logger.record_execution_result(session, result)

        except Exception as exc:
            logger.error(
                "[BENCHMARK] %s run%d failed: %s",
                query_id, run_number, exc, exc_info=True,
            )
            session.overall_status = "failed"
            now = time.monotonic()
            if session.plan_end    == 0.0: session.plan_end    = now
            if session.execute_end == 0.0: session.execute_end = now

        finally:
            self.bm_logger.finalize_and_log(session)
            self.bm_logger.save_to_csv(session)

        return session

    @staticmethod
    def _call_execute(executor: Any, plan: Any) -> Any:
        """
        Executor.execute() を呼び出す。

        ストリーミング（Generator）とバッチ（直接 ExecutionResult を返す）の
        両インターフェースに対応する。
        """
        import types
        result = executor.execute(plan)

        # Generator の場合はすべて消費して最後の値を取得する
        if isinstance(result, types.GeneratorType):
            last = None
            for item in result:
                last = item
            return last

        return result

    # ── クエリセット一括実行 ────────────────────────────────────────────────

    def run_query_set(
        self,
        queries: Optional[List[Dict[str, str]]] = None,
        runs_per_query: int = 3,
    ) -> List[BenchmarkSession]:
        """
        複数クエリを ``runs_per_query`` 回ずつ実行する。

        Args:
            queries:        クエリリスト（省略時は ``BENCHMARK_QUERIES`` を使用）
            runs_per_query: 各クエリの試行回数（統計的信頼性のため 3 を推奨）

        Returns:
            List[BenchmarkSession]: 全セッション結果
        """
        queries = queries or BENCHMARK_QUERIES
        sessions: List[BenchmarkSession] = []
        total = len(queries) * runs_per_query
        done  = 0

        for query in queries:
            for run in range(1, runs_per_query + 1):
                done += 1
                logger.info(
                    "[BENCHMARK] Progress %d/%d | %s Run %d/%d",
                    done, total, query["id"], run, runs_per_query,
                )
                session = self.run(
                    query_id   = query["id"],
                    query_text = query["text"],
                    run_number = run,
                    level      = query.get("level", ""),
                    category   = query.get("category", ""),
                )
                sessions.append(session)

        logger.info(
            "[BENCHMARK] All done: %d sessions. CSV => %s",
            done, self.bm_logger.csv_path,
        )
        return sessions


# ---------------------------------------------------------------------------
# エクスポート
# ---------------------------------------------------------------------------

__all__ = [
    "BENCHMARK_QUERIES",
    "CSV_HEADERS",
    "BENCHMARK_CSV_PATH",
    "BenchmarkSession",
    "BenchmarkLogger",
    "BenchmarkRunner",
]
