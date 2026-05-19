"""
GRACE Confidence - 信頼度計算システム

ハイブリッド方式（重み付き平均 + LLM自己評価）による
多軸信頼度計算を実装
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Literal, Dict, Any
from enum import Enum

# [MIGRATION] from google import genai / from google.genai import types を削除
# AnthropicClient は helper_llm 経由、Embedding は helper_embedding 経由で使用
from helper.helper_llm import create_llm_client  # [FIXED] helper_llm → helper.helper_llm
from helper.helper_embedding import create_embedding_client  # [FIXED] helper_embedding → helper.helper_embedding
from pydantic import BaseModel
from .config import get_config, GraceConfig

logger = logging.getLogger(__name__)


# =============================================================================
# 信頼度要素
# =============================================================================
# Gemini Structured Output用スキーマ
class EvaluationResult(BaseModel):  # ← 追加
    """LLM信頼度評価の応答スキーマ"""  # ← 追加
    score: float  # ← 追加
    reason: str


@dataclass
class ConfidenceFactors:
    """信頼度を構成する各要素"""

    # RAG検索関連
    search_result_count: int = 0  # 検索結果数
    search_avg_score: float = 0.0  # 平均類似度スコア
    search_max_score: float = 0.0  # 最高類似度スコア
    search_score_variance: float = 1.0  # スコアの分散（低いほど一貫性あり）

    # 複数ソース関連
    source_agreement: float = 0.0  # 情報源間の一致度 (0-1)
    source_count: int = 0  # 引用ソース数

    # LLM自己評価
    llm_self_confidence: float = 0.5  # LLMの自己評価 (0-1)

    # ツール実行関連
    tool_success_rate: float = 1.0  # ツール成功率
    tool_execution_count: int = 0  # 実行ツール数
    tool_success_count: int = 0  # 成功ツール数

    # クエリ関連
    query_coverage: float = 0.0  # クエリへの回答網羅度

    # ステップタイプ
    is_search_step: bool = False  # 検索ステップかどうか


@dataclass
class ConfidenceScore:
    """信頼度スコアと内訳"""

    score: float  # 最終スコア (0.0-1.0)
    factors: ConfidenceFactors  # 計算に使用した要素
    breakdown: Dict[str, float] = field(default_factory=dict)  # 各要素のスコア内訳
    penalties_applied: List[str] = field(default_factory=list)  # 適用されたペナルティ
    reason: str = ""  # 信頼度スコアの理由（LLM評価などで使用）

    @property
    def level(self) -> str:
        """信頼度レベルを取得"""
        if self.score >= 0.9:
            return "high"
        elif self.score >= 0.7:
            return "medium"
        elif self.score >= 0.4:
            return "low"
        else:
            return "very_low"


# =============================================================================
# 介入レベル
# =============================================================================

class InterventionLevel(str, Enum):
    """介入レベル"""
    SILENT = "silent"  # バックグラウンドで進行
    NOTIFY = "notify"  # ステータス表示
    CONFIRM = "confirm"  # 確認を求める
    ESCALATE = "escalate"  # ユーザー入力を要求


@dataclass
class ActionDecision:
    """信頼度に基づくアクション決定"""

    level: InterventionLevel
    confidence_score: float
    reason: str
    suggested_action: Optional[str] = None

    @property
    def should_proceed(self) -> bool:
        """自動進行可能か"""
        return self.level in [InterventionLevel.SILENT, InterventionLevel.NOTIFY]

    @property
    def needs_confirmation(self) -> bool:
        """確認が必要か"""
        return self.level == InterventionLevel.CONFIRM

    @property
    def needs_user_input(self) -> bool:
        """ユーザー入力が必要か"""
        return self.level == InterventionLevel.ESCALATE


# =============================================================================
# Confidence Calculator
# =============================================================================

class ConfidenceCalculator:
    """ハイブリッド方式によるConfidence計算"""

    def __init__(self, config: Optional[GraceConfig] = None):
        """
        Args:
            config: GRACE設定（Noneの場合はデフォルト）
        """
        self.config = config or get_config()
        self.weights = self.config.confidence.weights
        self._validate_weights()

        logger.info("ConfidenceCalculator initialized")

    def _validate_weights(self):
        """重みの合計が1.0であることを確認"""
        total = (
                self.weights.search_quality +
                self.weights.source_agreement +
                self.weights.llm_self_eval +
                self.weights.tool_success +
                self.weights.query_coverage
        )
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

    def calculate(self, factors: ConfidenceFactors) -> ConfidenceScore:
        """
        ハイブリッドConfidence計算
        1. 各要素を0-1にスケーリング
        2. 重み付き平均を計算
        3. ペナルティ適用（検索結果0件など）
        Args:
            factors: 信頼度要素
        Returns:
            ConfidenceScore: 信頼度スコアと内訳
        """
        breakdown = {}
        penalties = []

        # 検索品質スコア
        search_quality = self._calc_search_quality(factors)
        breakdown["search_quality"] = search_quality

        # ソース一致度（そのまま使用）
        source_agreement = factors.source_agreement
        breakdown["source_agreement"] = source_agreement

        # LLM自己評価（そのまま使用）
        llm_self_eval = factors.llm_self_confidence
        breakdown["llm_self_eval"] = llm_self_eval

        # ツール成功率
        tool_success = self._calc_tool_success(factors)
        breakdown["tool_success"] = tool_success

        # クエリ網羅度（そのまま使用）
        query_coverage = factors.query_coverage
        breakdown["query_coverage"] = query_coverage

        # 重み付き平均
        if factors.is_search_step:
            # 検索ステップの場合、検索品質（search_quality）をベースにする
            # tool_successは掛け算による減点として扱う（足し算による薄まりを防ぐ）
            base_score = search_quality
            if tool_success < 1.0:
                base_score *= tool_success

            # 内訳も調整（表示用）
            breakdown["llm_self_eval"] = 0.0  # N/A
            breakdown["query_coverage"] = 0.0  # N/A
        else:
            # 検索ステップ以外（Reasoningなど）の場合
            # 「有効な（信頼できる）要素」だけで加重平均を計算し、正規化する
            valid_weights = 0.0
            weighted_sum = 0.0

            # 1. 検索品質 (Search Quality) - 継承されたスコアがあれば最優先 (重み 0.6)
            if search_quality > 0:
                w = 0.6
                weighted_sum += search_quality * w
                valid_weights += w

            # 2. ツール成功 (Tool Success) - 必須要素 (重み 0.4)
            w = 0.4
            weighted_sum += tool_success * w
            valid_weights += w

            # 3. ソース一致度 (Source Agreement) - 複数ソースがある場合のみ (重み 0.2)
            if factors.source_count > 1:
                w = 0.2
                weighted_sum += source_agreement * w
                valid_weights += w

            # 4. LLM自己評価 (LLM Self Eval) - 評価済みの場合のみ反映 (重み 0.3)
            if llm_self_eval > 0.6:
                w = 0.3
                weighted_sum += llm_self_eval * w
                valid_weights += w

            # 5. クエリ網羅度 (Query Coverage) - 評価済みの場合のみ反映 (重み 0.1)
            if query_coverage > 0.1:
                w = 0.1
                weighted_sum += query_coverage * w
                valid_weights += w

            # 正規化 (加重平均)
            if valid_weights > 0:
                base_score = weighted_sum / valid_weights
            else:
                base_score = 0.0

        # ペナルティ適用
        final_score, penalties = self._apply_penalties(base_score, factors)

        # 0.0-1.0の範囲に収める
        final_score = round(min(1.0, max(0.0, final_score)), 3)

        return ConfidenceScore(
            score=final_score,
            factors=factors,
            breakdown=breakdown,
            penalties_applied=penalties
        )

    def llm_calculate(
            self,
            factors: ConfidenceFactors,
            step_description: str = "",
            tool_output: str = ""
    ) -> ConfidenceScore:
        """
        LLMを使用した信頼度計算（次世代版）

        Args:
            factors: 統計的要因（参考情報として使用）
            step_description: ステップの目的
            tool_output: ツールの出力

        Returns:
            ConfidenceScore: 計算された信頼度
        """
        # LLM Evaluatorの準備
        evaluator = create_llm_evaluator(config=self.config)

        # LLMによる評価実行
        eval_result = evaluator.evaluate_with_factors(
            description=step_description,
            output=tool_output,
            factors=factors
        )

        final_score = eval_result["score"]
        reason = eval_result["reason"]

        # --- ガードレール: 検索スコアの優先 ---
        # 検索ステップで、かつ検索システムのスコアが高い場合は、機械的なスコアを尊重する
        # (LLMがハルシネーションや過度な慎重さでスコアを下げすぎるのを防ぐ)
        if factors.is_search_step and factors.search_max_score > 0.7:
            if factors.search_max_score > final_score:
                logger.info(
                    f"Override LLM score ({final_score:.4f}) with Search Score ({factors.search_max_score:.4f})")
                final_score = factors.search_max_score
                reason += f" (検索スコア {factors.search_max_score:.4f} を優先)"

        # 内訳の作成（デバッグ用）
        breakdown = {
            "llm_score": final_score,
            "reason"   : 1.0 if reason else 0.0  # ダミー値だが存在確認用
        }

        logger.info(f"LLM Confidence Calculation: score={final_score}, reason={reason}")

        return ConfidenceScore(
            score=final_score,
            factors=factors,
            breakdown=breakdown,
            reason=reason,
            penalties_applied=[]
        )

    def _calc_search_quality(self, factors: ConfidenceFactors) -> float:
        """RAG検索品質のスコア化（最高スコア重視版）"""
        # 検索結果数が0でも、最大スコアが継承されていれば計算を続行する
        if factors.search_result_count == 0 and factors.search_max_score == 0:
            return 0.0

        # 1件でも高評価 (0.6以上) があれば、それをそのまま採用する
        # 注: Hybrid Search (RRF) の場合スコアが低めに出るため、閾値を0.8から0.6に緩和
        if factors.search_max_score >= 0.6:
            return factors.search_max_score

        # それ以外（不確かな場合）は、平均スコアも考慮する (70% Max + 30% Avg)
        combined_score = (factors.search_max_score * 0.7) + (factors.search_avg_score * 0.3)

        # 分散によるペナルティ（スコアがバラバラすぎる場合）
        variance_penalty = min(0.15, factors.search_score_variance * 0.3)

        return max(0.0, combined_score - variance_penalty)

    def _calc_tool_success(self, factors: ConfidenceFactors) -> float:
        """ツール成功率の計算"""
        if factors.tool_execution_count == 0:
            return factors.tool_success_rate

        return factors.tool_success_count / factors.tool_execution_count

    def _apply_penalties(
            self,
            base_score: float,
            factors: ConfidenceFactors
    ) -> tuple[float, List[str]]:
        """特定条件でのペナルティ適用"""
        score = base_score
        penalties = []

        # 検索結果が0件の場合、大幅減点（検索ステップの場合のみ適用）
        if factors.is_search_step and factors.search_result_count == 0:
            score *= 0.5
            penalties.append("no_search_results")

        # ツール失敗がある場合
        if factors.tool_success_rate < 1.0:
            multiplier = 0.8 + 0.2 * factors.tool_success_rate
            score *= multiplier
            penalties.append(f"tool_failures(rate={factors.tool_success_rate:.2f})")

        # ソースが0の場合
        if factors.source_count == 0:
            # 検索ステップで、かつ検索結果がある場合はペナルティを適用しない
            if factors.is_search_step and factors.search_result_count > 0:
                pass
            # 検索ステップ以外かつ自己評価が高い場合はペナルティなし
            elif not factors.is_search_step and factors.llm_self_confidence >= 0.8:
                pass
            else:
                score *= 0.7
                penalties.append("no_sources")

        return score, penalties

    def decide_action(self, score: ConfidenceScore) -> ActionDecision:
        """
        信頼度スコアに基づいてアクションを決定

        Args:
            score: 信頼度スコア

        Returns:
            ActionDecision: アクション決定
        """
        thresholds = self.config.confidence.thresholds

        if score.score >= thresholds.silent:
            return ActionDecision(
                level=InterventionLevel.SILENT,
                confidence_score=score.score,
                reason="高い信頼度: 自動進行",
                suggested_action="proceed"
            )
        elif score.score >= thresholds.notify:
            return ActionDecision(
                level=InterventionLevel.NOTIFY,
                confidence_score=score.score,
                reason="中程度の信頼度: ステータス表示しながら進行",
                suggested_action="proceed_with_status"
            )
        elif score.score >= thresholds.confirm:
            return ActionDecision(
                level=InterventionLevel.CONFIRM,
                confidence_score=score.score,
                reason="低い信頼度: ユーザー確認を推奨",
                suggested_action="ask_confirmation"
            )
        else:
            return ActionDecision(
                level=InterventionLevel.ESCALATE,
                confidence_score=score.score,
                reason="非常に低い信頼度: 追加情報が必要",
                suggested_action="request_clarification"
            )


# =============================================================================
# LLM Self Evaluator
# =============================================================================

class LLMSelfEvaluator:
    """LLMによる自己評価"""

    EVAL_PROMPT = """以下の基準に基づいて、回答の確信度を0.0から1.0の数値で評価してください。

【評価基準】
1. 正確性 (Accuracy):
   - 回答は提供された情報源（検索結果）に基づいているか？
   - 情報源にない情報を捏造していないか？
2. 適切性 (Relevance):
   - ユーザーの質問に直接的かつ明確に答えているか？
   - 質問の意図を正しく理解しているか？
3. スタイル (Style):
   - 親しみやすく、丁寧な日本語（です・ます調）か？
   - 読みやすい構成か？

【スコアの目安】
- 1.0: 完全に正確で、適切かつスタイルも完璧（複数の信頼できる情報源で確認済み）
- 0.8: ほぼ確実（信頼できる情報源あり、回答も適切）
- 0.6: やや確信あり（関連情報はあるが、完全ではない、またはスタイルに改善の余地あり）
- 0.4: 不確実（情報が限定的、または質問への回答として不十分）
- 0.2: 推測に近い（根拠が弱い）
- 0.0: 全く分からない、または不適切な回答

質問: {query}
回答: {answer}
使用した情報源: {sources}

確信度（0.0-1.0の数値のみ回答）:"""

    def __init__(
            self,
            config: Optional[GraceConfig] = None,
            model_name: Optional[str] = None
    ):
        """
        Args:
            config: GRACE設定
            model_name: 使用するモデル名（Noneの場合は設定から取得）
        """
        self.config = config or get_config()
        self.model_name = model_name or self.config.llm.model

        # [MIGRATION] genai.Client() → AnthropicClient (via create_llm_client)
        self.llm = create_llm_client("openai", default_model=self.model_name)   # [MIGRATION anthropic→openai]

        logger.info(f"LLMSelfEvaluator initialized with model: {self.model_name}")

    def evaluate(
            self,
            query: str,
            answer: str,
            sources: Optional[List[str]] = None
    ) -> float:
        """
        LLMに自己評価させる
        Args:
            query: 元の質問
            answer: 生成された回答
            sources: 使用した情報源のリスト
        Returns:
            float: 信頼度 (0.0-1.0)
        """
        sources_str = ", ".join(sources) if sources else "なし"

        prompt = self.EVAL_PROMPT.format(
            query=query,
            answer=answer,
            sources=sources_str
        )

        try:
            # --- [IPO LOG] PROCESS INPUT (GRACE SELF-EVAL) ---
            logger.info(f"\n{'=' * 20} [GRACE SELF-EVAL IPO: INPUT] {'=' * 20}\n{prompt}\n{'=' * 60}")

            import time as _time
            t0 = _time.time()

            # [MIGRATION] generate_content() + types.GenerateContentConfig
            #           → llm.generate_content() (Anthropic版)
            # 戻り値は str が直接返る。AFC 無効化オプションは不要。
            text = self.llm.generate_content(
                prompt=prompt,
                model=self.model_name,
                max_completion_tokens=10,  # [FIX] gpt-5.4-mini以降: max_tokens → max_completion_tokens
                temperature=0.0,
            )

            elapsed = _time.time() - t0
            logger.info(f"[API時間] LLMSelfEvaluator.evaluate: {elapsed:.1f}秒")

            # [MIGRATION] Noneガード: generate_content() は str を返すため基本不要だが念のため維持
            if not text:
                logger.warning("LLM self-evaluation returned empty response")
                return 0.5

            text = text.strip()

            # --- [IPO LOG] PROCESS OUTPUT (GRACE SELF-EVAL) ---
            logger.info(f"\n{'=' * 20} [GRACE SELF-EVAL IPO: OUTPUT] {'=' * 20}\n{text}\n{'=' * 60}")

            confidence = float(text)
            result = min(1.0, max(0.0, confidence))

            logger.debug(f"LLM self-evaluation: {result}")
            return result

        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse LLM self-evaluation: {e}")
            return 0.5  # デフォルト値
        except Exception as e:
            logger.error(f"LLM self-evaluation error: {e}")
            return 0.5

    def evaluate_with_factors(
            self,
            description: str,
            output: str,
            factors: ConfidenceFactors
    ) -> Dict[str, Any]:
        """
        Factorsとコンテキストを考慮した総合評価
        Args:
            description: ステップの目的
            output: ツールの出力内容
            factors: 統計적要因
        Returns:
            Dict: {"score": float, "reason": str}
        """
        import json

        prompt = f"""
あなたはAIエージェントの実行監視役です。
現在のステップが「成功」し、十分な信頼度があるかを評価してください。

【ステップの目的】
{description}

【実行結果（ツールの出力）】
{output[:2000]}... (省略)

【統計データ（Factors）】
- 検索品質 (Search Quality):
    - ヒット数: {factors.search_result_count}
    - 最高スコア: {factors.search_max_score:.4f}
    - 平均スコア: {factors.search_avg_score:.4f}
- ツール成功 (Tool Success):
    - 成功: {"Yes" if factors.tool_success_rate > 0.9 else "No (" + str(factors.tool_success_rate) + ")"}
- ソース一致度 (Source Agreement):
    - スコア: {factors.source_agreement:.4f} (1.0に近いほど複数の情報源が一致)
    - ソース数: {factors.source_count}

【評価基準】
以下の4項目を総合的に判断して、0.0 〜 1.0 の信頼度スコアを付けてください。

1. 検索品質: 質問に対する回答の根拠となる情報が十分にマッチしているか。
2. ツール成功: 計画されたアクションがエラーなく、期待される情報を返しているか。
3. ソース一致度: 複数の情報源がある場合、それらが矛盾していないか。
4. 目標達成度: このステップの出力だけで（またはこれまでの蓄積で）ステップの目的を達成できているか。

【スコアリング目安】
- 1.0: 完璧。根拠が明確で、矛盾もなく、目的を完全に達成した。
- 0.8: ほぼ十分。主要な情報は得られており、信頼できる。
- 0.5: 部分的。核心的な情報が不足している、または情報源に不安がある。
- 0.3: 不十分。再検索や再試行（Replan）が必要なレベル。
- 0.0: 失敗。全く無関係な情報、またはエラー。

回答は以下のJSON形式のみで出力してください。Markdownのコードブロックは不要です。
{{
  "score": 0.0,  // 0.0〜1.0の数値を入力
  "reason": "評価理由を記述"
}}
"""
        try:
            logger.info(f"LLM evaluate_with_factors prompt len: {len(prompt)}")

            # [MIGRATION] generate_content() + response_schema=EvaluationResult (Gemini 構造化出力)
            #           → generate_structured() で Tool Use に自動変換 (Anthropic)
            # 戻り値は EvaluationResult インスタンスが直接返る。
            # ・response.parsed / response.text の手動パース不要
            # ・Markdownコードブロック除去、JSONDecodeError ハンドリング不要
            # ・AFC 無効化オプション不要（Anthropic には AFC が存在しない）
            result: EvaluationResult = self.llm.generate_structured(
                prompt=prompt,
                response_schema=EvaluationResult,
                model=self.model_name,
                max_completion_tokens=200,  # [FIX] gpt-5.4-mini以降: max_tokens → max_completion_tokens
                temperature=0.0,
                system="You are an AI agent monitor. Evaluate the step result and return structured JSON.",
            )

            score = float(result.score)
            reason = result.reason or "No reason provided"
            logger.info(f"evaluate_with_factors: score={score}, reason={reason}")
            return {"score": score, "reason": reason}

        except Exception as e:
            logger.error(f"evaluate_with_factors failed: {e}")
            if factors.search_max_score > 0:
                logger.info(f"Fallback to search_max_score: {factors.search_max_score:.4f}")
                return {"score": factors.search_max_score, "reason": f"LLM evaluation failed, using search score"}
            return {"score": 0.5, "reason": f"Evaluation error: {str(e)}"}


# =============================================================================
# Source Agreement Calculator
# =============================================================================

class SourceAgreementCalculator:
    """複数ソース間の一致度計算"""

    def __init__(self, config: Optional[GraceConfig] = None):
        """
        Args:
            config: GRACE設定
        """
        self.config = config or get_config()

        # [MIGRATION] genai.Client() → create_embedding_client("openai")
        # Gemini Embedding (embed_content) → OpenAI Embedding (embed_text)
        # text-embedding-3-large: 3072次元（Gemini と同次元のため Qdrant 互換）
        self.embedding_client = create_embedding_client("openai")

        logger.info("SourceAgreementCalculator initialized")

    def calculate(self, answers: List[str]) -> float:
        """
        複数の回答間の一致度を計算
        Embeddingの類似度を使用して一致度を算出
        Args:
            answers: 回答のリスト
        Returns:
            float: 一致度 (0.0-1.0)
        """
        if len(answers) < 2:
            return 1.0  # 単一ソースは完全一致とみなす

        try:
            # 各回答のEmbeddingを取得
            # [MIGRATION] self.client.models.embed_content() (Gemini)
            #           → self.embedding_client.embed_text() (OpenAI)
            embeddings = []
            for answer in answers:
                vector = self.embedding_client.embed_text(answer)
                embeddings.append(vector)

            # ペアワイズ類似度を計算
            similarities = []
            for i in range(len(embeddings)):
                for j in range(i + 1, len(embeddings)):
                    sim = self._cosine_similarity(embeddings[i], embeddings[j])
                    similarities.append(sim)

            # 平均一致度を返す
            agreement = sum(similarities) / len(similarities)

            logger.debug(f"Source agreement: {agreement:.3f} from {len(answers)} sources")
            return agreement

        except Exception as e:
            logger.error(f"Source agreement calculation error: {e}")
            return 0.5  # デフォルト値

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """コサイン類似度を計算"""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)


# =============================================================================
# Query Coverage Calculator
# =============================================================================

class QueryCoverageCalculator:
    """クエリ網羅度計算"""

    COVERAGE_PROMPT = """以下の質問に対する回答が、質問のすべての要素をカバーしているか評価してください。

質問: {query}
回答: {answer}

網羅度（0.0-1.0の数値のみ回答）:
- 1.0: すべての質問要素に完全に回答
- 0.8: ほぼすべての要素に回答
- 0.6: 主要な要素に回答
- 0.4: 一部の要素のみに回答
- 0.2: ほとんど回答できていない
- 0.0: 全く回答できていない

数値のみ回答:"""

    def __init__(
            self,
            config: Optional[GraceConfig] = None,
            model_name: Optional[str] = None
    ):
        """
        Args:
            config: GRACE設定
            model_name: 使用するモデル名
        """
        self.config = config or get_config()
        self.model_name = model_name or self.config.llm.model

        # [MIGRATION] genai.Client() → AnthropicClient (via create_llm_client)
        self.llm = create_llm_client("openai", default_model=self.model_name)   # [MIGRATION anthropic→openai]

        logger.info("QueryCoverageCalculator initialized")

    def calculate(self, query: str, answer: str) -> float:
        """
        クエリに対する回答の網羅度を計算

        Args:
            query: 元の質問
            answer: 生成された回答

        Returns:
            float: 網羅度 (0.0-1.0)
        """
        prompt = self.COVERAGE_PROMPT.format(query=query, answer=answer)

        try:
            import time as _time
            t0 = _time.time()

            # [MIGRATION] generate_content() + types.GenerateContentConfig
            #           → llm.generate_content() (Anthropic版)
            # 戻り値は str が直接返る。AFC 無効化オプションは不要。
            text = self.llm.generate_content(
                prompt=prompt,
                model=self.model_name,
                max_completion_tokens=10,  # [FIX] gpt-5.4-mini以降: max_tokens → max_completion_tokens
                temperature=0.0,
            )

            elapsed = _time.time() - t0
            logger.info(f"[API時間] QueryCoverageCalculator: {elapsed:.1f}秒")

            # [MIGRATION] Noneガード: generate_content() は str を返すため基本不要だが念のため維持
            if not text:
                logger.warning("QueryCoverageCalculator: empty response")
                return 0.5

            text = text.strip()
            coverage = float(text)
            result = min(1.0, max(0.0, coverage))

            logger.debug(f"Query coverage: {result}")
            return result

        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse query coverage: {e}")
            return 0.5
        except Exception as e:
            logger.error(f"Query coverage calculation error: {e}")
            return 0.5


# =============================================================================
# Confidence Aggregator
# =============================================================================

class ConfidenceAggregator:
    """
    複数ステップの信頼度を集計

    計画全体の信頼度を算出するためのアグリゲータ
    """

    def __init__(self, config: Optional[GraceConfig] = None):
        """
        Args:
            config: GRACE設定
        """
        self.config = config or get_config()
        logger.info("ConfidenceAggregator initialized")

    def aggregate(
            self,
            scores: List[ConfidenceScore],
            method: Literal["mean", "min", "weighted"] = "mean"
    ) -> float:
        """
        複数の信頼度スコアを集計
        Args:
            scores: 信頼度スコアのリスト
            method: 集計方法
                - "mean": 平均
                - "min": 最小値（最も弱い部分を重視）
                - "weighted": 重み付き平均（後半のステップを重視）
        Returns:
            float: 集計された信頼度
        """
        if not scores:
            return 0.0

        values = [s.score for s in scores]

        if method == "mean":
            return sum(values) / len(values)

        elif method == "min":
            return min(values)

        elif method == "weighted":
            # 後半のステップほど重みを増やす
            weights = [i + 1 for i in range(len(values))]
            total_weight = sum(weights)
            weighted_sum = sum(v * w for v, w in zip(values, weights))
            return weighted_sum / total_weight

        else:
            raise ValueError(f"Unknown aggregation method: {method}")

    def aggregate_with_critical_check(
            self,
            scores: List[ConfidenceScore],
            critical_threshold: float = 0.3
    ) -> tuple[float, bool]:
        """
        重要度チェック付きの集計
        いずれかのステップが閾値を下回る場合、
        全体の信頼度を低下させる
        Args:
            scores: 信頼度スコアのリスト
            critical_threshold: 重要閾値
        Returns:
            tuple: (集計スコア, 重要ステップ失敗フラグ)
        """
        if not scores:
            return 0.0, False

        values = [s.score for s in scores]
        has_critical_failure = any(v < critical_threshold for v in values)

        base_score = sum(values) / len(values)

        if has_critical_failure:
            # 重要ステップ失敗時はペナルティ
            return base_score * 0.7, True

        return base_score, False


# =============================================================================
# ファクトリ関数
# =============================================================================

def create_confidence_calculator(
        config: Optional[GraceConfig] = None
) -> ConfidenceCalculator:
    """ConfidenceCalculatorインスタンスを作成"""
    return ConfidenceCalculator(config=config)


def create_llm_evaluator(
        config: Optional[GraceConfig] = None,
        model_name: Optional[str] = None
) -> LLMSelfEvaluator:
    """LLMSelfEvaluatorインスタンスを作成"""
    return LLMSelfEvaluator(config=config, model_name=model_name)


def create_source_agreement_calculator(
        config: Optional[GraceConfig] = None
) -> SourceAgreementCalculator:
    """SourceAgreementCalculatorインスタンスを作成"""
    return SourceAgreementCalculator(config=config)


def create_query_coverage_calculator(
        config: Optional[GraceConfig] = None,
        model_name: Optional[str] = None
) -> QueryCoverageCalculator:
    """QueryCoverageCalculatorインスタンスを作成"""
    return QueryCoverageCalculator(config=config, model_name=model_name)


def create_confidence_aggregator(
        config: Optional[GraceConfig] = None
) -> ConfidenceAggregator:
    """ConfidenceAggregatorインスタンスを作成"""
    return ConfidenceAggregator(config=config)


# =============================================================================
# エクスポート
# =============================================================================

__all__ = [
    # Data classes
    "ConfidenceFactors",
    "ConfidenceScore",
    "ActionDecision",

    # Enums
    "InterventionLevel",

    # Calculators
    "ConfidenceCalculator",
    "LLMSelfEvaluator",
    "SourceAgreementCalculator",
    "QueryCoverageCalculator",
    "ConfidenceAggregator",

    # Factory functions
    "create_confidence_calculator",
    "create_llm_evaluator",
    "create_source_agreement_calculator",
    "create_query_coverage_calculator",
    "create_confidence_aggregator",
]
