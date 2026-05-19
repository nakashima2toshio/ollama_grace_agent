# models.py
"""
Pydanticモデル定義
Gemini APIのレスポンススキーマとして使用
"""

from typing import List
from pydantic import BaseModel, Field


class SentenceUnit(BaseModel):
    """1つの文、または意味の最小単位"""
    text: str = Field(description="1つの文、または意味の最小単位")


class ParagraphUnit(BaseModel):
    """段落単位"""
    id: int = Field(description="Paragraph ID")
    sentences: List[SentenceUnit] = Field(description="この段落に含まれる文のリスト")

    @property
    def full_text(self) -> str:
        """段落内の全文を結合して返す

        注意: 改行（\n）で文を結合します。
        これにより、元のテキスト構造が保持され、
        Step2・Step3での処理精度が向上します。

        CSV入力時に特に重要：
        - CSVセル内の改行が保持される
        - 可読性が高まる
        - 意味的分割が正確になる
        """
        return "\n".join([s.text for s in self.sentences])


class StructuralResult(BaseModel):
    """テキスト構造化の結果"""
    paragraphs: List[ParagraphUnit]


class ContinuityResult(BaseModel):
    is_connected: bool = Field(
        description=(
            "前のテキスト(Prev)と次のテキスト(Next)が一つの連続した話題としてつながっている場合はTrue。"
            "Nextを単独で読んだ場合に意味が不完全・曖昧になる場合もTrue。"
            "話題が転換し、NextがPrevなしでも完全に理解できる場合はFalse。"
        )
    )
