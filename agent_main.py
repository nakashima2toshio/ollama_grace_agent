#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
agent_main.py - 高品質CLI版エージェント (Upgraded)
====================================================
agent_service.py のプロンプトと機能を統合したCLI版

実行コマンド:
    python agent_main.py

機能:
- ReAct + Reflection の2段階処理
- 動的コレクション取得
- キーワード抽出（オプション）
- 多言語対応の検索戦略
- 再試行メカニズム
"""

import os
import uuid

# [MIGRATION] from google import genai / from google.genai import types を削除
# AnthropicClient を helper_llm 経由で使用（agent_service.py と同パターン）
from helper.helper_llm import create_llm_client  # [FIXED] helper_llm → helper.helper_llm

from dotenv import load_dotenv
import logging
import datetime
from typing import Dict, List, Any, Optional, Union, Tuple
from pathlib import Path

# Configuration and Tools
# [MIGRATION] AgentConfig 削除（Anthropic版では不要）
from config import PathConfig
from agent_tools import search_rag_knowledge_base, list_rag_collections, RAGToolError
from qdrant_client import QdrantClient
from services.qdrant_service import get_all_collections

# キーワード抽出（オプション）
try:
    from regex_mecab import KeywordExtractor

    KEYWORD_EXTRACTION_AVAILABLE = True
except ImportError:
    KEYWORD_EXTRACTION_AVAILABLE = False
    KeywordExtractor = None

logger = logging.getLogger(__name__)

# ============================================================================
# プロンプト定義 (agent_service.py から移植・改良)
# ============================================================================

SYSTEM_INSTRUCTION_TEMPLATE = """
あなたは、社内ドキュメント検索システムと連携した「ハイブリッド・ナレッジ・エージェント」です。
あなたの役割は、ユーザーの質問に対して、一般的な知識と、提供されたツール（社内ナレッジ検索）を適切に使い分けて回答することです。

## ReAct プロセスと出力フォーマット (厳守)

あなたは **Thought (思考)**、**Action (ツール実行)**、**Observation (結果観察)** のサイクルを回して回答に到達する必要があります。

### 1. ツールを使用する場合（検索が必要な場合）
必ず以下の形式で思考を出力してから、ツールを呼び出してください。
**Thought: [なぜ検索が必要か、どんなクエリで検索するか]**
(この後にツール呼び出しが行われます)
**重要: 
- 検索クエリを作成する際は、提供された「重要キーワード」を必ず含めてください。
- `collection_name` パラメータは絶対に指定しないでください。システムが自動的に全コレクションから最適なものを選択します。**

### 2. 最終回答を行う場合（検索が完了した、または検索不要な場合）
必ず以下の形式で出力してください。
**Thought: [得られた情報に基づいてどう回答するか、または検索結果がなかった場合の判断]**
**Answer: [ユーザーへの最終的な回答]**

**重要:**
- 検索クエリは、質問文から「いつ」「誰」「何」などの具体的な要素を抽出して作成してください。抽象的な質問（例：「教えて」）をそのまま検索クエリにせず、具体的なキーワードに変換してください。
- 検索結果のスコアが低くても（例: 0.5程度）、内容が質問に関連していれば、その情報を積極的に使用して回答を作成してください。「情報が見つかりませんでした」と即断せず、得られた断片的な情報からでも回答を試みてください。
- 回答は必ず `Answer:` (または `**Answer:**`) で始めてください。

---

## 行動指針 (Router Guidelines)

1.  **専門知識の検索**:
    *   以下のいずれかに該当する場合は、**必ず `search_rag_knowledge_base` ツールを使用してください。**
        *   プロジェクト固有の仕様、設定、エラー、社内規定、Wikipediaの知識に関する質問。
        *   特定の情報源（例: "Wikipediaによると"、"ライブドアニュースで"）が指定されている質問。
        *   **内容が不明瞭であっても、社内ナレッジに関連する可能性があると判断される質問（例：特定のコード名、システム名、ランダムに見える文字列など）。**
        *   **ただし、一般的なプログラミング言語の文法や使い方に関する質問にはツールを使用しないでください。**
    *   **現在利用可能なコレクションは以下の通りです:**
        {available_collections}

2.  **検索システム**:
    *   **重要: `search_rag_knowledge_base` ツールを呼び出す際、`collection_name` パラメータは指定しないでください。**
    *   システムが自動的に最適なコレクションを検索します。
    *   あなたは `query` パラメータのみを指定してください。例: `search_rag_knowledge_base(query="カリン・フォン・アロルディンゲン")`
    *   
    *   **参考: 利用可能なコレクション（自動選択されます）**
        *   `cc_news`: 英語のニュース記事
        *   `wikipedia_ja`: 日本語の百科事典
        *   `livedoor`: 日本語のニュース・ブログ
        *   `japanese_text`: 日本語のWebテキスト
        *   `qa_pairs_custom_upload`, `custom_upload`: ユーザーアップロードの専門Q&A

3.  **一般的な会話**:
    *   挨拶、雑談、単純な計算など、専門知識が不要な場合は、ツールを使わずに `Answer:` で直接回答してください。

4.  **正直さと不足情報の処理 (Critical)**:
    *   ツール検索の結果、情報が得られなかった場合は、**絶対に**あなたの事前学習知識で捏造してはいけません。
    *   「提供された社内ナレッジには関連情報がありませんでした」と正直に伝えてください。

5.  **回答のスタイル**:
    *   丁寧な日本語（です・ます調）で回答してください。
    *   検索結果に基づく回答の場合、「社内ナレッジによると...」や「ソース [ファイル名] によると...」と出典を明示してください。
"""

REFLECTION_INSTRUCTION = """
## Reflection (自己評価と修正)

あなたは上記で作成した「回答案」を、以下の基準で客観的に評価し、必要であれば修正してください。

**チェックリスト:**
1.  **正確性:** 検索結果(もしあれば)に基づいているか？ 提供された情報源に含まれない情報を捏造していないか？
2.  **回答の適切性:** ユーザーの質問に直接的かつ明確に答えているか？
3.  **スタイル:** 親しみやすく、丁寧な日本語（です・ます調）か？ 箇条書きなどを活用して読みやすいか？

**指示:**
*   修正が不要な場合でも、必ず **Final Answer** を出力してください。
*   修正が必要な場合は、修正後の回答を **Final Answer** として出力してください。
*   思考プロセスは `Thought:` で始めてください。

**出力フォーマット:**
Thought: [評価と修正の思考プロセス]
Final Answer: [最終的な回答]
"""

# ツールマップ
TOOLS_MAP: Dict[str, Any] = {
    'search_rag_knowledge_base': search_rag_knowledge_base,
    'list_rag_collections'     : list_rag_collections
}


# ============================================================================
# ヘルパー関数
# ============================================================================

def get_available_collections_dynamic() -> List[str]:
    """Qdrantから動的にコレクション一覧を取得"""
    try:
        from config import QdrantConfig
        client = QdrantClient(url=QdrantConfig.URL)
        collections = get_all_collections(client)
        return [c["name"] for c in collections]
    except Exception as e:
        logger.warning(f"Failed to fetch collections dynamically: {e}")
        return ["(利用可能なコレクションはありません)"]


def setup_logging() -> logging.Logger:
    """ロギング設定 [MIGRATION] AgentConfig 依存を除去 → 直接定数を使用"""
    LOG_FILE_NAME = "agent_chat.log"      # AgentConfig.CHAT_LOG_FILE_NAME 相当
    LOG_LEVEL     = "INFO"                # AgentConfig.CHAT_LOG_LEVEL 相当
    log_file_path: Path = PathConfig.LOG_DIR / LOG_FILE_NAME
    PathConfig.ensure_dirs()
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(log_file_path, encoding='utf-8')]
    )
    return logging.getLogger(__name__)


def print_colored(text: str, color: str = "white") -> None:
    """カラー出力"""
    colors: Dict[str, str] = {
        "cyan" : "\033[96m", "green": "\033[92m", "yellow": "\033[93m",
        "red"  : "\033[91m", "blue": "\033[94m", "magenta": "\033[95m",
        "reset": "\033[0m"
    }
    print(f"{colors.get(color, '')}{text}{colors['reset']}")


# ============================================================================
# 高品質エージェントクラス
# ============================================================================

class UpgradedCLIAgent:
    """
    高品質CLI版エージェント

    agent_service.pyのReActAgentと同等の機能を持つCLI版
    """

    def __init__(self, model_name: str = None):
        # [MIGRATION] AgentConfig.MODEL_NAME → "claude-sonnet-4-6"
        self.model_name = model_name or "claude-sonnet-4-6"
        self.session_id = str(uuid.uuid4())

        # [MIGRATION] genai.Client() + chat_session
        #           → AnthropicClient (via create_llm_client)
        # Anthropic はステートレス設計のため chat_session を廃止し
        # self._messages リストで会話履歴を自前管理する
        self.llm = create_llm_client("openai", default_model=self.model_name)  # [MIGRATION anthropic→openai]
        self._messages: List[Dict[str, Any]] = []

        # システムプロンプトとツール定義を事前構築
        self.system_instruction: str = self._build_system_instruction()
        self.tools: List[Dict[str, Any]] = self._build_tools()

        # キーワード抽出器の初期化（変更なし）
        self.keyword_extractor = None
        if KEYWORD_EXTRACTION_AVAILABLE:
            try:
                self.keyword_extractor = KeywordExtractor(prefer_mecab=True)
                logger.info("KeywordExtractor initialized successfully.")
            except Exception as e:
                logger.warning(f"Failed to initialize KeywordExtractor: {e}")

        logger.info(f"UpgradedCLIAgent initialized (session: {self.session_id})")

    def _build_system_instruction(self) -> str:
        """
        [MIGRATION] _setup_session() の system_instruction 部分を独立メソッドに分離。
        Anthropic は system= パラメータで渡すため chat セッションとは切り離す。
        """
        available_collections = get_available_collections_dynamic()
        collections_str = ", ".join(available_collections)
        return SYSTEM_INSTRUCTION_TEMPLATE.format(available_collections=collections_str)

    def _build_tools(self) -> List[Dict[str, Any]]:
        """
        [MIGRATION] Gemini 形式（Python 関数参照）→ Anthropic Tool Use 形式（dict リスト）
        変更点: "parameters" キー → "input_schema" キー
        """
        return [
            {
                "name"        : "search_rag_knowledge_base",
                "description" : (
                    "社内ドキュメント（Qdrant）から関連情報をベクトル検索する。"
                    "プロジェクト固有の仕様・社内規定・Wikipedia・ニュース記事など"
                    "専門知識が必要な質問に使用する。"
                    "collection_name は指定しないこと（システムが自動選択）。"
                ),
                "input_schema": {
                    "type"      : "object",
                    "properties": {
                        "query": {
                            "type"       : "string",
                            "description": "検索クエリ。ユーザーの質問から重要キーワードを含めて作成する。"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name"        : "list_rag_collections",
                "description" : "利用可能な Qdrant コレクション一覧を取得する。",
                "input_schema": {
                    "type": "object", "properties": {}, "required": []
                }
            }
        ]

    def execute_turn(self, user_input: str) -> str:
        """
        エージェントのターンを実行（ReAct → Reflection）
        Args:
            user_input: ユーザーの質問
        Returns:
            最終回答
        """
        print_colored("\n" + "=" * 60, "cyan")
        print_colored("🤖 ReAct Phase Start", "cyan")
        print_colored("=" * 60 + "\n", "cyan")

        # Phase 1: ReAct Loop
        draft_answer = self._execute_react_loop(user_input)

        # Phase 2: Reflection
        if draft_answer:
            print_colored("\n" + "=" * 60, "magenta")
            print_colored("🔄 Reflection Phase (推敲)", "magenta")
            print_colored("=" * 60 + "\n", "magenta")

            final_answer = self._execute_reflection_phase(draft_answer)
            return self._format_final_answer(final_answer)

        return self._format_final_answer(draft_answer)

    def _execute_react_loop(self, user_input: str) -> str:
        """
        ReAct ループの実行
        [MIGRATION] Gemini → Anthropic Tool Use 形式に完全書き直し
        agent_service.py の _execute_react_loop() と同パターン
        """
        # キーワード抽出とプロンプト拡張（変更なし）
        augmented_input = user_input
        if self.keyword_extractor:
            try:
                keywords = self.keyword_extractor.extract(user_input, top_n=5)
                if keywords:
                    keywords_str = ", ".join(keywords)
                    augmented_input = f"""{user_input}
【重要: 検索クエリ作成の指示】
以下の抽出された重要キーワードを、必ず検索クエリに含めてください。
重要キーワード: {keywords_str}"""
                    logger.info(f"Augmented input with keywords: {keywords_str}")
                    print_colored(f"🔑 Extracted Keywords: {keywords_str}", "yellow")
            except Exception as e:
                logger.warning(f"Keyword extraction failed: {e}")

        # [MIGRATION] Anthropic: messages リストで会話履歴を自前管理
        # Gemini: chat_session.send_message(augmented_input) に相当する初期化
        self._messages = [{"role": "user", "content": augmented_input}]

        max_turns = 10
        final_text = ""

        for turn_count in range(1, max_turns + 1):
            # [MIGRATION anthropic→openai]
            # Anthropic: stop_reason / OpenAI: finish_reason
            text, tool_calls, finish_reason = self.llm.generate_with_tools(
                messages=self._messages,
                tools=self.tools,
                system=self.system_instruction,
            )

            # テキスト部分の表示（変更なし）
            if text and ("Thought:" in text or "考え:" in text):
                print_colored(f"💭 {text}", "blue")
                logger.info(f"Thought: {text}")

            # [MIGRATION] ツール呼び出し検出
            # Anthropic: stop_reason == "tool_use"
            # OpenAI:    finish_reason == "tool_calls"
            if finish_reason != "tool_calls" or not tool_calls:
                final_text = text
                break

            # [MIGRATION] assistant ターンを OpenAI 形式で追記
            import json as _json
            self._messages.append({
                "role"      : "assistant",
                "content"   : text or None,
                "tool_calls": [
                    {
                        "id"      : tc["id"],
                        "type"    : "function",
                        "function": {
                            "name"     : tc["name"],
                            "arguments": _json.dumps(tc["input"], ensure_ascii=False),
                        }
                    }
                    for tc in tool_calls
                ]
            })

            # [MIGRATION] ツール結果を OpenAI 形式で個別追記
            # Anthropic: 同一 user メッセージにまとめる（1件）
            # OpenAI:    {"role":"tool","tool_call_id":...} を1件ずつ追記（複数件）
            for tc in tool_calls:
                tool_name = tc["name"]
                tool_args = tc["input"]
                tool_id   = tc["id"]

                print_colored(f"🛠️  Tool Call: {tool_name}({tool_args})", "green")
                logger.info(f"Tool Call: {tool_name}({tool_args})")

                # ツール実行（変更なし）
                tool_result = ""
                try:
                    if tool_name in TOOLS_MAP:
                        tool_result = TOOLS_MAP[tool_name](**tool_args)
                    else:
                        tool_result = f"Error: Tool '{tool_name}' not found."
                except RAGToolError as e:
                    tool_result = f"エラーが発生しました: {str(e)}"
                    logger.error(f"RAG Tool Error: {e}")
                except Exception as e:
                    tool_result = f"予期せぬエラー: {str(e)}"
                    logger.error(f"Unexpected error: {e}", exc_info=True)

                log_result = str(tool_result)[:500] + "..." if len(str(tool_result)) > 500 else str(tool_result)
                print_colored(f"📝 Tool Result:\n{log_result}", "yellow")
                logger.info(f"Tool Result: {log_result}")

                # [MIGRATION] OpenAI: role=tool の個別メッセージとして追記
                self._messages.append({
                    "role"        : "tool",
                    "tool_call_id": tool_id,
                    "content"     : str(tool_result),
                })


        return final_text

    def _execute_reflection_phase(self, draft_answer: str) -> str:
        """
        Reflection フェーズの実行
        [MIGRATION] chat_session.send_message()
                  → generate_with_tools(tools=[]) で会話履歴全体を引き継ぎ
        """
        try:
            reflection_msg = f"{REFLECTION_INSTRUCTION}\n\n**あなたの回答案:**\n{draft_answer}"

            # [MIGRATION] Anthropic: self._messages に reflection_msg を追記して
            # ReAct ループの検索結果・思考ログのコンテキストを維持する
            # Tool Use は不要のため tools=[] を指定
            self._messages.append({"role": "user", "content": reflection_msg})
            reflection_text, _, _ = self.llm.generate_with_tools(
                messages=self._messages,
                tools=[],
                system=self.system_instruction,
            )

            if not reflection_text:
                logger.warning("Reflection phase did not generate text.")
                return draft_answer

            # Final Answer を抽出（変更なし）
            if "Final Answer:" in reflection_text:
                parts = reflection_text.split("Final Answer:", 1)
                thought = parts[0].strip()
                answer  = parts[1].strip()

                if thought:
                    clean_thought = thought.replace("Thought:", "").strip()
                    print_colored(f"🤔 Reflection: {clean_thought}", "magenta")
                    logger.info(f"Reflection: {clean_thought}")

                return answer
            else:
                return reflection_text

        except Exception as e:
            logger.error(f"Reflection error: {e}")
            return draft_answer

    def _format_final_answer(self, raw_answer: str) -> str:
        """最終回答の整形"""
        if "Answer:" in raw_answer:
            parts = raw_answer.split("Answer:", 1)
            return parts[1].strip()
        elif raw_answer.startswith("Thought:"):
            return raw_answer.replace("Thought:", "").strip()
        elif raw_answer.startswith("考え:"):
            return raw_answer.replace("考え:", "").strip()
        return raw_answer


# ============================================================================
# メイン関数
# ============================================================================

def main() -> None:
    """メインエントリーポイント"""
    logger = setup_logging()

    print_colored("\n" + "=" * 60, "cyan")
    print_colored("🤖 Upgraded CLI Agent (ReAct + Reflection)", "cyan")
    print_colored("=" * 60, "cyan")
    print("高品質CLI版エージェント - agent_service.py レベルの機能")
    print("\n機能:")
    print("  ✅ ReAct + Reflection 2段階処理")
    print("  ✅ 動的コレクション取得")
    print("  ✅ 多言語対応の検索戦略")
    print("  ✅ 再試行メカニズム")
    if KEYWORD_EXTRACTION_AVAILABLE:
        print("  ✅ キーワード抽出（有効）")
    else:
        print("  ⚠️  キーワード抽出（無効 - regex_mecabが必要）")
    print("\nコマンド:")
    print("  'exit' or 'quit' - 終了")
    print("  'reset' - エージェントをリセット")
    print_colored("=" * 60 + "\n", "cyan")

    logger.info(f"Agent session started at {datetime.datetime.now()}")

    try:
        agent = UpgradedCLIAgent()
    except Exception as e:
        print_colored(f"❌ Error setting up agent: {e}", "red")
        logger.error(f"Error setting up agent: {e}")
        return

    while True:
        try:
            user_input = input("\n💬 You: ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit"]:
                logger.info("User requested exit.")
                print_colored("\n👋 Agent: Goodbye!", "green")
                break

            if user_input.lower() == "reset":
                print_colored("🔄 Resetting agent...", "yellow")
                agent = UpgradedCLIAgent()
                print_colored("✅ Agent reset complete!", "green")
                continue

            # エージェント実行
            response = agent.execute_turn(user_input)

            print_colored("\n" + "=" * 60, "green")
            print_colored(f"🤖 Agent: {response}", "green")
            print_colored("=" * 60 + "\n", "green")

        except KeyboardInterrupt:
            logger.info("User interrupted with Ctrl+C.")
            print_colored("\n\n👋 Agent: Goodbye!", "green")
            break
        except Exception as e:
            print_colored(f"\n❌ Error during chat: {e}", "red")
            logger.error(f"Error during chat: {e}", exc_info=True)
            continue


if __name__ == "__main__":
    main()
