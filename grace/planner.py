"""
GRACE Planner - 計画生成エージェント

ユーザーの質問を分析し、実行計画を生成

[2026-05-19] ollama_grace_agent 移植対応:
    - OpenAIClient → OllamaClient (via create_llm_client)
    - create_llm_client("openai") → create_llm_client("ollama")
    - max_completion_tokens → max_tokens (Ollama は max_completion_tokens 非対応)
    - generate_structured() は JSON モード + Pydantic parse で代替

[2026-05-05] openai_grace_agent 移植対応:
    - AnthropicClient → OpenAIClient (via create_llm_client)
    - create_llm_client("anthropic") → create_llm_client("openai")
    - response_schema=ExecutionPlan → generate_structured() で Structured Outputs に代替
    - max_tokens → max_completion_tokens（gpt-5.4-mini以降の仕様変更）
    - AFC関連バグ回避コードを削除（Anthropic では不要）

[2026-05-20] ollama_grace_agent 移植対応:
    - create_llm_client("openai") → create_llm_client("ollama")
    - max_completion_tokens → max_tokens（Ollama は max_completion_tokens 非対応）
"""

import logging
from typing import Optional, List

# [MIGRATION openai→ollama] OllamaClient を helper_llm 経由で使用
from helper.helper_llm import create_llm_client

from .schemas import (
    ExecutionPlan,
    PlanStep,
    create_plan_id,
    validate_plan_dependencies,
)
from .config import get_config, GraceConfig
from services.qdrant_service import get_all_collections
from qdrant_client import QdrantClient
from services.prompts import SEARCH_QUERY_INSTRUCTION
from regex_mecab import KeywordExtractor

logger = logging.getLogger(__name__)

# =============================================================================
# プロンプト定義（変更なし）
# =============================================================================

PLAN_GENERATION_PROMPT = f"""
あなたは計画策定の専門家です。ユーザーの質問を分析し、回答を生成するための実行計画を作成してください。

【利用可能なアクション】
- rag_search: ベクトルDB（Qdrant）から関連情報を検索（社内ドキュメント・FAQ向け）
- web_search: Web検索で最新情報や一般的な情報を取得（最新ニュース・外部情報向け）
- reasoning: 収集した情報を分析・統合して回答を生成
- ask_user: ユーザーに追加情報や確認を求める

【利用可能なコレクション (rag_search用)】
{{available_collections}}

【コレクション選択のルール (重要)】
- `rag_search` の `collection` 引数は、原則として指定しないでください（`null` または省略）。
   * 特定のコレクション（例: wikipedia_ja）に限定せず、利用可能なすべてのコレクションから網羅的に検索を行うためです。
   * システム側で自動的に最適なコレクション順序で検索を実行します。
- 例外: ユーザーが明示的に「livedoorニュースから検索して」のように指定した場合のみ、そのコレクション名を指定してください。

【検索クエリの作成ルール】
- `rag_search` の `query` 引数は、ユーザーの質問文を極力そのまま使用してください。
   * 単語の羅列（例: "金色夜叉 尾崎紅葉"）に変換せず、自然言語の文脈
   （例:"〜の構成者は誰ですか？"）を維持することで、ベクトル検索の精度が向上します。

【計画作成のルール (厳守)】
1. 検索アクション（rag_search）は、可能な限り「1つのステップ」にまとめてください。
    * 質問を分解して複数の検索ステップを作らないでください。
2. `rag_search` の `query` は、ユーザーの元の質問文を「完全一致でコピー」してください。
    * 要約、キーワード化、分割は一切禁止です。
    * 悪い例: "金色夜叉 構成者"
    * 良い例: "『金色夜叉:尾崎紅葉不如帰:徳富蘆花』の構成者は誰ですか？"
3. 依存関係を正しく設定してください（depends_onは先行ステップのIDのみ）。
4. 失敗時の代替手段（fallback）を検討してください。
5. 最後のステップは必ず "reasoning" で回答を生成してください
6. rag_search と web_search の使い分け:
    * 計画には web_search ステップを含めないでください
    * web_search は、rag_search の結果が不十分な場合に executor が自動的に実行します
    * 計画は常に rag_search → reasoning の2ステップ構成としてください
    * rag_search の fallback には "web_search" を指定してください
    * 例外: ユーザーが明示的に「最新ニュースを検索して」等と指示した場合のみ、
      web_search 単体のステップを計画に含めてよい

{SEARCH_QUERY_INSTRUCTION}

【計画の複雑度(complexity)の目安】
- 0.0-0.3: 単純な質問（1-2ステップ）
- 0.4-0.6: 中程度の質問（2-3ステップ）
- 0.7-1.0: 複雑な質問（4ステップ以上）

【requires_confirmationをtrueにする条件】
- 質問が曖昧で複数の解釈が可能な場合
- 実行に時間がかかる可能性がある場合
- 外部リソースへのアクセスが必要な場合

ユーザーの質問: {{query}}

JSON形式で実行計画を出力してください。
"""

COMPLEXITY_ESTIMATION_PROMPT = """
以下の質問の複雑度を0.0から1.0の数値で評価してください。

評価基準:
- 0.0-0.2: 非常に単純（事実確認、定義の質問）
- 0.3-0.4: 単純（1つのトピックについての説明）
- 0.5-0.6: 中程度（比較、分析が必要）
- 0.7-0.8: 複雑（複数のソースからの情報統合が必要）
- 0.9-1.0: 非常に複雑（専門知識、多段階の推論が必要）

質問: {query}

数値のみを回答してください（例: 0.5）
"""


# =============================================================================
# Planner クラス
# =============================================================================

class Planner:
    """計画生成エージェント"""

    def __init__(
            self,
            config: Optional[GraceConfig] = None,
            model_name: Optional[str] = None
    ):
        """
        Args:
            config: GRACE設定（Noneの場合はデフォルト設定を使用）
            model_name: 使用するモデル名（Noneの場合は設定から取得）
        """
        self.config = config or get_config()
        self.model_name = model_name or self.config.llm.model

        # [MIGRATION openai→ollama] create_llm_client("openai") → create_llm_client("ollama")
        # OllamaClient.generate_structured() が JSON モード+Pydantic parse を隠蔽する
        self.llm = create_llm_client("ollama", default_model=self.model_name)

        try:
            self.keyword_extractor = KeywordExtractor(prefer_mecab=True)
            logger.info("Planner: KeywordExtractor initialized")
        except Exception as e:
            logger.warning(f"Planner: Failed to initialize KeywordExtractor: {e}")
            self.keyword_extractor = None

        logger.info(f"Planner initialized with model: {self.model_name}")

    def create_plan(self, query: str) -> ExecutionPlan:
        """
        質問から実行計画を生成（LLM使用版）

        Args:
            query: ユーザーの質問
        Returns:
            ExecutionPlan: LLMが生成した実行計画
        """
        logger.info(f"Creating execution plan for: {query[:50]}...")

        try:
            available_collections = self._get_available_collections()
            collections_str = ", ".join(available_collections) if available_collections else "(コレクションなし)"

            estimated_complexity = self.estimate_complexity_with_llm(query)

            prompt = PLAN_GENERATION_PROMPT.format(
                available_collections=collections_str,
                query=query
            ) + "\n\nIMPORTANT: Ensure the output is a valid, complete JSON object. Do not truncate the response."

            logger.info(f"\n{'=' * 20} [GRACE PLANNER IPO: INPUT] {'=' * 20}\n{prompt}\n{'=' * 60}")

            import time as _time

            plan = None
            last_error = None
            max_attempts = 2

            for attempt in range(max_attempts):
                try:
                    t0 = _time.time()

                    # [MIGRATION openai→ollama] max_completion_tokens → max_tokens
                    # OllamaClient.generate_structured() は JSON モード + Pydantic parse で実装
                    plan = self.llm.generate_structured(
                        prompt=prompt,
                        response_schema=ExecutionPlan,
                        model=self.model_name,
                        max_tokens=8192,  # [MIGRATION openai→ollama] max_completion_tokens → max_tokens
                        system="You are an expert planning agent. Always respond using the provided tool.",
                        temperature=self.config.llm.temperature,
                    )

                    elapsed = _time.time() - t0
                    logger.info(f"[API時間] create_plan LLM (attempt {attempt + 1}/{max_attempts}): {elapsed:.1f}秒")

                    logger.info(
                        f"\n{'=' * 20} [GRACE PLANNER IPO: OUTPUT] {'=' * 20}\n"
                        f"{plan.model_dump_json(indent=2)}\n{'=' * 60}"
                    )

                    break

                except Exception as e:
                    last_error = e
                    logger.warning(f"Plan creation attempt {attempt + 1}/{max_attempts} failed: {e}")
                    continue

            if plan is None:
                raise last_error or ValueError("Plan creation failed after all retries")

            plan.complexity = estimated_complexity
            plan.plan_id = create_plan_id()

            errors = validate_plan_dependencies(plan)
            if errors:
                logger.warning(f"Plan validation errors: {errors}")

            logger.info(
                f"Plan created: {len(plan.steps)} steps, "
                f"complexity={plan.complexity:.2f}, "
                f"requires_confirmation={plan.requires_confirmation}"
            )

            logger.info(f"Final Execution Plan:\n{plan.model_dump_json(indent=2)}")

            return plan

        except Exception as e:
            logger.error(f"Failed to create plan with LLM: {e}")
            logger.info("Falling back to simple plan")
            return self._create_fallback_plan(query)

    def _create_plan_legacy(self, query: str) -> ExecutionPlan:
        """質問から実行計画を生成（Legacy Agent委譲版 - バックアップ）"""
        return ExecutionPlan(
            original_query=query,
            complexity=0.1,
            estimated_steps=1,
            requires_confirmation=False,
            steps=[
                PlanStep(
                    step_id=1,
                    action="run_legacy_agent",
                    description="Legacy Agent (ReAct) を実行して回答を生成",
                    query=query,
                    collection=None,
                    expected_output="ユーザーへの回答",
                    fallback=None,
                    timeout_seconds=30
                )
            ],
            success_criteria="ユーザーの質問に適切に回答できている",
            plan_id=create_plan_id()
        )

    def _get_available_collections(self) -> list:
        """利用可能なQdrantコレクションを取得"""
        try:
            client = QdrantClient(url=self.config.qdrant.url)
            cols = get_all_collections(client)
            return [c["name"] for c in cols]
        except Exception as e:
            logger.warning(f"Failed to get collections: {e}")
            return self.config.qdrant.search_priority

    def _create_fallback_plan(self, query: str) -> ExecutionPlan:
        """フォールバック用の単純な計画を生成"""
        logger.info("Creating fallback plan")

        try:
            available = self._get_available_collections()
            fallback_collection = next(
                (c for c in available if "wikipedia" in c), None
            )
        except Exception:
            fallback_collection = None

        return ExecutionPlan(
            original_query=query,
            complexity=0.5,
            estimated_steps=2,
            requires_confirmation=False,
            steps=[
                PlanStep(
                    step_id=1,
                    action="rag_search",
                    description="全コレクションから関連情報を検索",
                    query=query,
                    collection=fallback_collection,
                    expected_output="関連するドキュメントや情報",
                    fallback="web_search",
                    timeout_seconds=30
                ),
                PlanStep(
                    step_id=2,
                    action="reasoning",
                    description="取得した情報を元に回答を生成",
                    query=None,
                    collection=None,
                    depends_on=[1],
                    expected_output="ユーザーへの回答",
                    fallback=None,
                    timeout_seconds=30
                )
            ],
            success_criteria="ユーザーの質問に適切に回答できている",
            plan_id=create_plan_id()
        )

    def estimate_complexity(self, query: str) -> float:
        """質問の複雑度を推定（キーワードベース簡易版）"""
        complexity_factors = [
            ("比較", 0.15), ("違い", 0.15), ("複数", 0.2),
            ("最新", 0.1),  ("理由", 0.1),  ("方法", 0.1),
            ("詳しく", 0.15), ("ステップ", 0.1), ("手順", 0.1),
            ("なぜ", 0.1),  ("どのように", 0.15),
        ]

        score = 0.5
        for keyword, weight in complexity_factors:
            if keyword in query:
                score += weight

        if len(query) > 100:
            score += 0.1
        if len(query) > 200:
            score += 0.1

        return min(1.0, score)

    def estimate_complexity_with_llm(self, query: str) -> float:
        """LLMを使用して質問の複雑度を推定"""
        import time as _time
        try:
            prompt = COMPLEXITY_ESTIMATION_PROMPT.format(query=query)

            t0 = _time.time()

            # [MIGRATION openai→ollama] max_completion_tokens → max_tokens
            complexity_str = self.llm.generate_content(
                prompt=prompt,
                model=self.model_name,
                max_tokens=10,  # [MIGRATION openai→ollama] max_completion_tokens → max_tokens
                temperature=0.1,
            )

            elapsed = _time.time() - t0
            logger.info(f"[API時間] estimate_complexity_with_llm: {elapsed:.1f}秒")

            if not complexity_str or not complexity_str.strip():
                logger.warning("estimate_complexity_with_llm: empty response")
                return self.estimate_complexity(query)

            complexity = float(complexity_str.strip())
            return min(1.0, max(0.0, complexity))

        except Exception as e:
            logger.warning(f"LLM complexity estimation failed: {e}")
            return self.estimate_complexity(query)

    def refine_plan(
            self,
            plan: ExecutionPlan,
            feedback: str
    ) -> ExecutionPlan:
        """フィードバックに基づいて計画を修正"""
        logger.info(f"Refining plan {plan.plan_id} with feedback")

        refine_prompt = f"""
以下の実行計画をユーザーのフィードバックに基づいて修正してください。

【元の計画】
クエリ: {plan.original_query}
ステップ数: {len(plan.steps)}
ステップ: {[s.description for s in plan.steps]}

【ユーザーのフィードバック】
{feedback}

修正された計画をJSON形式で出力してください。
"""

        try:
            import time as _time
            t0 = _time.time()

            # [MIGRATION openai→ollama] max_completion_tokens → max_tokens
            refined_plan = self.llm.generate_structured(
                prompt=refine_prompt,
                response_schema=ExecutionPlan,
                model=self.model_name,
                max_tokens=4096,  # [MIGRATION openai→ollama] max_completion_tokens → max_tokens
                temperature=self.config.llm.temperature,
            )

            elapsed = _time.time() - t0
            logger.info(f"[API時間] refine_plan LLM: {elapsed:.1f}秒")

            refined_plan.plan_id = create_plan_id()

            logger.info(f"Plan refined: {refined_plan.plan_id}")
            return refined_plan

        except Exception as e:
            logger.error(f"Failed to refine plan: {e}")
            return plan


# =============================================================================
# ファクトリ関数
# =============================================================================

def create_planner(
        config: Optional[GraceConfig] = None,
        model_name: Optional[str] = None
) -> Planner:
    """
    Plannerインスタンスを作成

    Args:
        config: GRACE設定
        model_name: 使用するモデル名
    Returns:
        Planner: Plannerインスタンス
    """
    return Planner(config=config, model_name=model_name)


# =============================================================================
# エクスポート
# =============================================================================

__all__ = [
    "Planner",
    "create_planner",
    "PLAN_GENERATION_PROMPT",
]
