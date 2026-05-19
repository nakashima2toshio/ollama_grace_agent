# async_api_client.py
"""
非同期APIクライアント（OpenAI版）
- asyncio.to_thread() で同期APIをラップ
- Semaphore で並列数制御（固定）
- リトライロジック（3回、指数バックオフ）
- 構造化出力は OpenAI Structured Outputs (beta.chat.completions.parse) で実現

[MIGRATION] Gemini → OpenAI (2026-05-04)
  - from google import genai / from google.genai import types → 削除
  - genai.Client(api_key=...) → OpenAI(api_key=...)
  - client.models.generate_content() + GenerateContentConfig + response_schema
    → client.beta.chat.completions.parse(response_format=PydanticClass)
  - response.text (JSON文字列) → response.choices[0].message.parsed (Pydanticインスタンス)
  - api_key: GOOGLE_API_KEY → OPENAI_API_KEY
  - 不完全JSON検出・finish_reason チェック → max_completion_tokens超過検出に変更
  - max_tokens → max_completion_tokens（gpt-5.4-mini以降の仕様変更に対応）
"""

import asyncio
import json
import logging
from typing import Type, Optional

from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AsyncAPIClient:
    """
    非同期APIクライアント（OpenAI版）
    - asyncio.to_thread() で同期APIをラップ
    - Semaphore で並列数制御（固定）
    - リトライロジック（3回、指数バックオフ）
    - 構造化出力: OpenAI Structured Outputs (beta.chat.completions.parse)
    """

    def __init__(
        self,
        api_key: str,
        max_workers: int = 8,
        max_retries: int = 3,
        max_output_tokens: int = 8192
    ):
        """
        Args:
            api_key: OpenAI API Key
            max_workers: 並列数（デフォルト: 8）
            max_retries: リトライ回数（デフォルト: 3）
            max_output_tokens: 出力トークン制限（デフォルト: 8192）
        """
        # [MIGRATION] genai.Client(api_key=...) → OpenAI(api_key=...)
        self.client = OpenAI(api_key=api_key)
        self.max_workers = max_workers
        self.semaphore = asyncio.Semaphore(max_workers)
        self.max_retries = max_retries
        self.max_output_tokens = max_output_tokens
        self._total_requests = 0
        self._failed_requests = 0
        self._truncated_responses = 0

    def _is_truncated(self, finish_reason: Optional[str]) -> bool:
        """レスポンスが max_completion_tokens で切断されたか判定"""
        return finish_reason == "length"

    async def generate_content(
        self,
        model: str,
        contents: str,
        response_schema: Type[BaseModel],
        task_id: Optional[str] = None
    ) -> Optional[str]:
        """
        セマフォで並列数を制御しながらAPI呼び出し
        失敗時は指数バックオフでリトライ

        Args:
            model: OpenAI モデル名（例: gpt-4o-mini, gpt-4o）
            contents: 入力テキスト
            response_schema: レスポンスのPydanticスキーマ
            task_id: タスク識別子（ログ用）

        Returns:
            JSON文字列（Pydanticモデルとして解析可能）、失敗時はNone
        """
        async with self.semaphore:
            return await self._execute_with_retry(
                model, contents, response_schema, task_id
            )

    async def _execute_with_retry(
        self,
        model: str,
        contents: str,
        response_schema: Type[BaseModel],
        task_id: Optional[str]
    ) -> Optional[str]:
        """リトライロジック（OpenAI Structured Outputs による構造化出力）"""

        for attempt in range(self.max_retries):
            try:
                self._total_requests += 1

                # [MIGRATION] asyncio.to_thread で同期APIを非同期実行
                # Gemini: client.models.generate_content(model, contents, config=GenerateContentConfig(...))
                # OpenAI: client.beta.chat.completions.parse(model, messages, response_format=PydanticClass)
                # [FIX] gpt-5.4-mini 以降は max_tokens が廃止。max_completion_tokens を使用する
                response = await asyncio.to_thread(
                    self.client.beta.chat.completions.parse,
                    model=model,
                    max_completion_tokens=self.max_output_tokens,
                    messages=[{"role": "user", "content": contents}],
                    response_format=response_schema,
                )

                choice = response.choices[0]
                finish_reason = choice.finish_reason

                # max_tokens超過チェック（Geminiのfinish_reason=MAX_TOKENS相当）
                if self._is_truncated(finish_reason):
                    self._truncated_responses += 1
                    raise ValueError(
                        f"Response truncated (finish_reason: {finish_reason}). "
                        f"Increase max_output_tokens or reduce block_size."
                    )

                # [MIGRATION] レスポンス取得
                # Gemini: response.text → JSON文字列
                # OpenAI: choice.message.parsed → Pydanticインスタンス → json.dumps()
                parsed = choice.message.parsed
                if parsed is None:
                    raise ValueError(
                        f"Parsed result is None (finish_reason: {finish_reason}). "
                        f"Possible refusal: {choice.message.refusal}"
                    )

                result_json = json.dumps(parsed.model_dump(), ensure_ascii=False)
                return result_json

            except ValueError as e:
                wait_time = 2 ** attempt
                logger.warning(
                    f"[{task_id}] {e}. "
                    f"Retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(wait_time)

            except Exception as e:
                error_str = str(e).lower()

                if "429" in error_str or "rate" in error_str or "quota" in error_str or "insufficient_quota" in error_str:
                    wait_time = 30 * (attempt + 1)
                    logger.warning(
                        f"[{task_id}] Rate limit / quota hit. "
                        f"Waiting {wait_time}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                else:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"[{task_id}] Error: {e}. "
                        f"Retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})"
                    )

                if attempt < self.max_retries - 1:
                    await asyncio.sleep(wait_time)

        self._failed_requests += 1
        logger.error(f"[{task_id}] Failed after {self.max_retries} retries. Using fallback.")
        return None

    def get_stats(self) -> dict:
        """統計情報を取得"""
        return {
            "total_requests"     : self._total_requests,
            "failed_requests"    : self._failed_requests,
            "truncated_responses": self._truncated_responses,
            "success_rate"       : (
                (self._total_requests - self._failed_requests) / self._total_requests * 100
                if self._total_requests > 0 else 0
            ),
            "concurrency"        : self.max_workers
        }

    def reset_stats(self):
        """統計情報をリセット"""
        self._total_requests = 0
        self._failed_requests = 0
        self._truncated_responses = 0
