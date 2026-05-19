#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
smart_qa_generator.py - コンテンツを考慮したインテリジェントQ/A生成システム v2.5

改修内容（v2.5）:
- google.generativeai → google.genai に移行
- 新しいAPIに対応

現在の問題点:
- すべてのチャンクで固定数（qa_per_chunk=3）のQ/Aを生成
- 内容の重要度、情報密度、複雑さを考慮していない

改善内容:
- LLMによるチャンク分析で適切なQ/A数を動的決定
- 0個（Q/A不要）〜5個まで柔軟に調整
- 重要トピックの明示化による品質向上
"""

import json
import logging
from typing import Dict, List, Optional
# [MIGRATION] from google import genai / from google.genai import types を削除
# AnthropicClient を helper_llm 経由で使用
from helper.helper_llm import create_llm_client  # [FIXED] helper_llm → helper.helper_llm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SmartQAGenerator:
    """
    コンテンツを考慮したインテリジェントQ/A生成クラス
    [MIGRATION] Gemini API → Anthropic API に移植済み
    """

    def __init__(self, model: str = "gpt-4o-mini", api_key: Optional[str] = None):
        """
        初期化

        Args:
            model: 使用する OpenAI モデル（デフォルト: gpt-4o-mini）
            api_key: OpenAI API Key（環境変数 OPENAI_API_KEY から自動取得）
        """
        # [MIGRATION anthropic→openai] "claude-sonnet-4-6" → "gpt-4o-mini"
        # api_key は create_llm_client 内部で OPENAI_API_KEY を自動参照するため不要
        self.model = model
        self.llm = create_llm_client("openai", default_model=self.model)
        logger.info(f"OpenAI API を使用 (model={self.model})")


    def _generate_content(self, prompt: str, temperature: float = 0.1) -> str:
        """
        コンテンツ生成
        [MIGRATION] client.models.generate_content() → llm.generate_content()
        戻り値は str が直接返るため response.text の取り出し不要

        Args:
            prompt: プロンプト
            temperature: 温度パラメータ
        Returns:
            生成されたテキスト
        """
        # [MIGRATION] Gemini: self.client.models.generate_content(model, contents, config)
        #           → Anthropic: self.llm.generate_content(prompt, model, temperature, max_tokens)
        # AFC 無効化オプションは Anthropic では不要
        return self.llm.generate_content(
            prompt=prompt,
            model=self.model,
            temperature=temperature,
            max_completion_tokens=4096,  # [FIX] gpt-5.4-mini以降: max_tokens → max_completion_tokens
        )


    def analyze_chunk(self, chunk_text: str) -> Dict:
        """
        チャンクを分析してQ/A生成計画を立てる
        Args:
            chunk_text: 分析対象のチャンク
        Returns:
            dict: {
                'qa_count': int,           # 生成すべきQ/A数（0-5）
                'key_topics': List[str],   # 主要トピック
                'importance_score': float, # 重要度（0.0-1.0）
                'complexity': str,         # 複雑さ（low/medium/high）
                'reasoning': str           # 判断理由
            }
        """

        prompt = f"""
以下のテキストチャンクを分析し、Q/Aペアの生成計画を立ててください。

# 分析観点
1. **情報密度**: このチャンクに含まれる独立した情報・事実の数
2. **重要度**: 情報の重要性（critical/high/medium/low）
3. **複雑さ**: 説明に必要な詳細度（high/medium/low）
4. **独立性**: 各情報が他の文脈なしで理解可能か

# チャンク
```
{chunk_text}
```

# 判断基準
## 0個（Q/A生成不要）:
- 補足情報のみ（「詳細は付録参照」など）
- 意味のない繰り返し
- メタ情報のみ（ページ番号、参照リンクなど）

## 1個:
- 単純な事実の記述（1つの情報のみ）
- 例: "この製品は赤色です。"

## 2個:
- 関連する2つの事実
- 例: "この製品は赤色で、サイズはMです。"

## 3個（標準）:
- 複数の関連情報
- 標準的な説明パラグラフ

## 4-5個:
- 高密度な技術情報
- 複数の独立したポイント
- 重要な警告や注意事項を含む
- 例: API仕様、暗号化の詳細、安全上の注意

# 出力形式（JSON）
{{
    "qa_count": <0-5の整数>,
    "key_topics": [<主要トピックのリスト>],
    "importance_score": <0.0-1.0の実数>,
    "complexity": "<low/medium/high>",
    "reasoning": "<判断理由を1-2文で>"
}}

# 重要な注意
- 質より量を優先しない（無駄なQ/Aは作らない）
- 重複した情報は1つのQ/Aにまとめる
- 警告・注意事項は必ず独立したQ/Aにする
"""

        try:
            text = self._generate_content(prompt, temperature=0.1)

            # JSONパース
            text = text.strip()

            # Markdownコードブロックの除去
            if text.startswith('```json'):
                text = text[7:]
            if text.startswith('```'):
                text = text[3:]
            if text.endswith('```'):
                text = text[:-3]

            result = json.loads(text.strip())

            # バリデーション
            result['qa_count'] = max(0, min(5, int(result['qa_count'])))
            result['importance_score'] = max(0.0, min(1.0, float(result['importance_score'])))

            if 'key_topics' not in result:
                result['key_topics'] = []

            logger.info(f"分析完了: Q/A数={result['qa_count']}, 重要度={result['importance_score']:.2f}")

            return result

        except Exception as e:
            logger.warning(f"分析エラー（フォールバック使用）: {e}")

            # フォールバック：文字数ベース
            token_count = len(chunk_text) // 4

            if token_count < 50:
                fallback_count = 0
            elif token_count < 100:
                fallback_count = 1
            elif token_count < 200:
                fallback_count = 2
            else:
                fallback_count = 3

            return {
                'qa_count'        : fallback_count,
                'key_topics'      : [],
                'importance_score': 0.5,
                'complexity'      : 'medium',
                'reasoning'       : f'分析エラーのため文字数ベースで決定: {e}'
            }

    def generate_qa_pairs(
            self,
            chunk_text: str,
            analysis: Optional[Dict] = None
    ) -> List[Dict]:
        """
        分析結果に基づいてQ/Aペアを生成

        Args:
            chunk_text: チャンクテキスト
            analysis: analyze_chunk()の結果（Noneの場合は自動分析）

        Returns:
            List[Dict]: [{'question': str, 'answer': str, 'topic': str}, ...]
        """

        # 分析がない場合は実行
        if analysis is None:
            analysis = self.analyze_chunk(chunk_text)

        qa_count = analysis['qa_count']

        # Q/A生成不要の場合
        if qa_count == 0:
            logger.info("Q/A生成スキップ（qa_count=0）")
            return []

        # トピックヒントの作成
        topics_hint = ""
        if analysis['key_topics']:
            topics_hint = "\n## 重点トピック\n以下のトピックを優先的にカバーしてください:\n" + \
                          "\n".join([f"- {topic}" for topic in analysis['key_topics']])

        # 重要度に基づく指示
        importance_hint = ""
        if analysis['importance_score'] >= 0.8:
            importance_hint = "\n## 重要度\nこのチャンクは非常に重要です。詳細で正確なQ/Aを生成してください。"

        prompt = f"""
以下のテキストから、**正確に{qa_count}個**のQ/Aペアを生成してください。

# 生成計画
- 生成数: {qa_count}個
- 重要度スコア: {analysis['importance_score']:.2f}
- 複雑さ: {analysis['complexity']}
{topics_hint}
{importance_hint}

# テキスト
```
{chunk_text}
```

# 出力形式（JSON配列）
[
    {{"question": "質問1", "answer": "回答1", "topic": "トピック1"}},
    {{"question": "質問2", "answer": "回答2", "topic": "トピック2"}},
    ...
]

# ガイドライン
1. **質問の形式**:
   - 自然な日本語
   - ユーザーが実際に尋ねそうな形式
   - 「〜は何ですか？」「〜について教えてください」など

2. **回答の形式**:
   - 簡潔かつ正確
   - チャンクの情報のみを使用（推測しない）
   - 50-150文字程度

3. **優先順位**:
   - 重要な情報から順にQ/A化
   - 警告・注意事項は必ず含める
   - 冗長な質問は避ける

4. **トピック**:
   - 各Q/Aの主題を1-3単語で表現
   - 例: "暗号化方式", "鍵長", "利用モード"

# 重要
- 必ず{qa_count}個のQ/Aを生成してください
- 重複を避けてください
- トピックフィールドは必須です
"""

        try:
            text = self._generate_content(prompt, temperature=0.3)

            # Markdownコードブロックの除去
            text = text.strip()
            if text.startswith('```json'):
                text = text[7:]
            if text.startswith('```'):
                text = text[3:]
            if text.endswith('```'):
                text = text[:-3]

            qa_pairs = json.loads(text.strip())

            # 件数チェック
            if len(qa_pairs) != qa_count:
                logger.warning(
                    f"期待: {qa_count}個、実際: {len(qa_pairs)}個 "
                    f"（差分: {abs(len(qa_pairs) - qa_count)}個）"
                )

            # トピック欠損の補完
            for qa in qa_pairs:
                if 'topic' not in qa:
                    qa['topic'] = 'その他'

            logger.info(f"Q/A生成完了: {len(qa_pairs)}個")

            return qa_pairs

        except Exception as e:
            logger.error(f"Q/A生成エラー: {e}")
            return []

    def process_chunk(self, chunk_text: str) -> Dict:
        """
        チャンクの分析とQ/A生成を一括実行

        Args:
            chunk_text: チャンクテキスト

        Returns:
            dict: {
                'analysis': Dict,        # 分析結果
                'qa_pairs': List[Dict],  # 生成されたQ/A
                'success': bool          # 成功フラグ
            }
        """
        try:
            # Step 1: 分析
            analysis = self.analyze_chunk(chunk_text)

            # Step 2: Q/A生成
            qa_pairs = self.generate_qa_pairs(chunk_text, analysis)

            return {
                'analysis': analysis,
                'qa_pairs': qa_pairs,
                'success' : True
            }

        except Exception as e:
            logger.error(f"チャンク処理エラー: {e}")
            return {
                'analysis': {},
                'qa_pairs': [],
                'success' : False
            }


# ============================================================
# 統計分析ユーティリティ
# ============================================================

def analyze_qa_statistics(results: List[Dict]) -> Dict:
    """
    Q/A生成結果の統計分析

    Args:
        results: process_chunk()の結果リスト

    Returns:
        dict: 統計情報
    """
    total_chunks = len(results)
    total_qa = sum(len(r['qa_pairs']) for r in results)

    qa_distribution = {}
    for r in results:
        count = len(r['qa_pairs'])
        qa_distribution[count] = qa_distribution.get(count, 0) + 1

    avg_qa_per_chunk = total_qa / total_chunks if total_chunks > 0 else 0

    importance_scores = [
        r['analysis'].get('importance_score', 0)
        for r in results
        if r['analysis']
    ]
    avg_importance = sum(importance_scores) / len(importance_scores) if importance_scores else 0

    return {
        'total_chunks'        : total_chunks,
        'total_qa_pairs'      : total_qa,
        'avg_qa_per_chunk'    : avg_qa_per_chunk,
        'avg_importance_score': avg_importance,
        'qa_distribution'     : qa_distribution
    }


# ============================================================
# 使用例
# ============================================================

if __name__ == "__main__":
    import os

    # [MIGRATION anthropic→openai] OPENAI_API_KEY を使用
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("エラー: OPENAI_API_KEYが設定されていません")
        exit(1)

    # ジェネレーター初期化（api_key は内部で自動取得）
    generator = SmartQAGenerator()

    # テストチャンク
    test_chunks = [
        # ケース1: 短いチャンク（1個期待）
        "この製品は赤色です。",

        # ケース2: 中程度のチャンク（2-3個期待）
        """
        この製品は赤色で、サイズはMサイズです。
        価格は3,000円で、送料無料です。
        """,

        # ケース3: 技術的で重要なチャンク（4-5個期待）
        """
        AES-256暗号化アルゴリズムは、対称鍵暗号方式の一種で、
        256ビットの鍵長を持ちます。NIST（米国国立標準技術研究所）
        により承認されており、機密情報の保護に広く使用されています。
        ブロック暗号として動作し、128ビットのブロックサイズで
        データを処理します。CBC、GCM、CTRなど複数のモードが利用可能で、
        用途に応じて選択できます。
        """,

        # ケース4: メタ情報（0個期待）
        "詳細については付録Aを参照してください。"
    ]

    # 各チャンクを処理
    results = []

    print("=" * 60)
    print("スマートQ/A生成システム - デモ v2.5")
    print("=" * 60)

    for i, chunk in enumerate(test_chunks, 1):
        print(f"\n{'=' * 60}")
        print(f"チャンク {i}")
        print(f"{'=' * 60}")
        print(f"内容:\n{chunk.strip()}\n")

        result = generator.process_chunk(chunk)
        results.append(result)

        if result['success']:
            analysis = result['analysis']
            qa_pairs = result['qa_pairs']

            print(f"【分析結果】")
            print(f"  Q/A数      : {analysis['qa_count']}")
            print(f"  重要度     : {analysis['importance_score']:.2f}")
            print(f"  複雑さ     : {analysis['complexity']}")
            print(f"  主要トピック: {', '.join(analysis['key_topics']) if analysis['key_topics'] else 'なし'}")
            print(f"  理由       : {analysis['reasoning']}")

            if qa_pairs:
                print(f"\n【生成されたQ/A】")
                for j, qa in enumerate(qa_pairs, 1):
                    print(f"\n  Q{j} ({qa.get('topic', 'N/A')}): {qa['question']}")
                    print(f"  A{j}: {qa['answer']}")
        else:
            print("❌ 処理失敗")

    # 統計表示
    print(f"\n{'=' * 60}")
    print("統計情報")
    print(f"{'=' * 60}")

    stats = analyze_qa_statistics(results)
    print(f"総チャンク数        : {stats['total_chunks']}")
    print(f"総Q/A数            : {stats['total_qa_pairs']}")
    print(f"平均Q/A数/チャンク : {stats['avg_qa_per_chunk']:.2f}")
    print(f"平均重要度         : {stats['avg_importance_score']:.2f}")
    print(f"\nQ/A数分布:")
    for count, freq in sorted(stats['qa_distribution'].items()):
        print(f"  {count}個: {freq}チャンク")

    print(f"\n{'=' * 60}")
    print("✅ デモ完了")
    print(f"{'=' * 60}")
