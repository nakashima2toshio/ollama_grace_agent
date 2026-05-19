# python sample_regex_mecab.py
# MeCab複合名詞版と正規表現版を統合したロバストなキーワード抽出システム
# [Usage:] List: keywords = extractor.extract(sample_text_jp, top_n=10)
# [Usage:] List: chunks = chunk_text(sample_text_jp2)
import re
import logging
from typing import List, Dict, Tuple
from collections import Counter

logger = logging.getLogger(__name__)


# =============================================================================
# チャンク分割機能
# =============================================================================

def chunk_text(text: str, keep_delimiter: bool = True) -> List[str]:
    """
    テキストをチャンクに分割する
    分割ルール:
    - 改行が含まれる場合: 改行で分割
    - 改行がない場合: 「。」で分割
    Args:
        text: 分割対象のテキスト
        keep_delimiter: 区切り文字（。）を保持するか（デフォルト: True）
    Returns:
        チャンクのリスト
    """
    # 前後の空白を除去
    text = text.strip()

    if not text:
        return []

    # 改行が含まれているかチェック（空白のみの行は除外）
    has_meaningful_newlines = bool(re.search(r'\n\s*\S', text))

    if has_meaningful_newlines:
        # 改行で分割
        chunks = text.split('\n')
    else:
        # 「。」で分割
        if keep_delimiter:
            # 「。」を保持して分割（正規表現で「。」の後で分割）
            chunks = re.split(r'(?<=。)', text)
        else:
            # 「。」を除去して分割
            chunks = text.split('。')

    # 空のチャンクを除去し、各チャンクをstrip
    chunks = [chunk.strip() for chunk in chunks if chunk.strip()]

    return chunks


# =============================================================================
# キーワード抽出クラス
# =============================================================================

class KeywordExtractor:
    """
    MeCabと正規表現を統合したキーワード抽出クラス

    MeCabが利用可能な場合は複合名詞抽出を優先し、
    利用不可の場合は正規表現版に自動フォールバック
    """

    def __init__(self, prefer_mecab: bool = True):
        """
        Args:
            prefer_mecab: MeCabを優先的に使用するか（デフォルト: True）
        """
        self.prefer_mecab = prefer_mecab
        self.mecab_available = self._check_mecab_availability()

        # ストップワード定義 (日本語 + 英語)
        self.stopwords = {
            # 日本語
            'こと', 'もの', 'これ', 'それ', 'ため', 'よう', 'さん',
            'ます', 'です', 'ある', 'いる', 'する', 'なる', 'できる',
            'いう', '的', 'な', 'に', 'を', 'は', 'が', 'で', 'と',
            'の', 'から', 'まで', '等', 'など', 'よる', 'おく', 'くる',
            # 英語
            'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'having', 'do', 'does', 'did', 'done',
            'a', 'an', 'the', 'and', 'but', 'or', 'as', 'if', 'when',
            'at', 'by', 'for', 'with', 'about', 'against', 'between',
            'into', 'through', 'during', 'before', 'after', 'above',
            'below', 'to', 'from', 'up', 'down', 'in', 'out', 'on', 'off',
            'over', 'under', 'again', 'further', 'then', 'once', 'this',
            'that', 'these', 'those', 'which', 'who', 'whom', 'whose',
            'whose', 'it', 'its', 'they', 'them', 'their', 'theirs'
        }

        # 重要キーワードの定義（スコアブースト用）
        self.important_keywords = {
            'AI', 'Artificial Intelligence', 'Machine Learning', 'Deep Learning',
            'NLP', 'Natural Language Processing', 'Transformer', 'BERT', 'GPT',
            'CNN', 'Vision', '医療', 'Diagnosis', 'Autonomous Driving',
            'Ethics', 'Bias', 'Challenges', 'Issues', 'Model', 'Data'
        }

        if self.mecab_available:
            logger.info("✅ MeCabが利用可能です（複合名詞抽出モード）")
        else:
            logger.warning("⚠️ MeCabが利用できません（正規表現モード）")

    def _check_mecab_availability(self) -> bool:
        """MeCabの利用可能性をチェック"""
        try:
            import MeCab
            # 実際にインスタンス化して動作確認
            tagger = MeCab.Tagger()
            tagger.parse("テスト")
            return True
        except (ImportError, RuntimeError):
            return False

    def extract(self, text: str, top_n: int = 5,
                use_scoring: bool = True) -> List[str]:
        """
        テキストからキーワードを抽出（自動フォールバック・言語判定対応）
        Args:
            text: 分析対象テキスト
            top_n: 抽出するキーワード数
            use_scoring: スコアリングを使用するか
        Returns:
            キーワードリスト
        """
        # 言語判定（日本語文字が含まれているか）
        is_japanese = bool(re.search(r'[ぁ-んァ-ヶー一-龠]', text))

        if self.mecab_available and self.prefer_mecab and is_japanese:
            try:
                keywords = self._extract_with_mecab(text, top_n, use_scoring)
                if keywords:  # 空でなければ成功
                    return keywords
            except Exception as e:
                logger.warning(f"⚠️ MeCab抽出エラー: {e}")

        # 日本語がない、またはMeCabエラー・不可の場合は正規表現版
        if not is_japanese:
            logger.info("ℹ️ 英語主体のテキストとして判定されました（正規表現モードを使用）")
        return self._extract_with_regex(text, top_n, use_scoring)

    def _extract_with_mecab(self, text: str, top_n: int,
                            use_scoring: bool) -> List[str]:
        """MeCabを使用した複合名詞抽出"""
        import MeCab

        tagger = MeCab.Tagger()
        node = tagger.parseToNode(text)

        # 複合名詞の抽出
        compound_buffer = []
        compound_nouns = []

        while node:
            features = node.feature.split(',')
            pos = features[0]  # 品詞

            if pos == '名詞':
                compound_buffer.append(node.surface)
            else:
                # 名詞以外が来たらバッファをフラッシュ
                if compound_buffer:
                    compound_noun = ''.join(compound_buffer)
                    # 英語のゴミ（スペースが詰まった長大な文字列）を簡易的に除外
                    if len(compound_noun) > 0 and not (re.match(r'^[A-Za-z]{15,}$', compound_noun)):
                        compound_nouns.append(compound_noun)
                    compound_buffer = []

            node = node.next

        # 最後のバッファをフラッシュ
        if compound_buffer:
            compound_noun = ''.join(compound_buffer)
            if len(compound_noun) > 0 and not (re.match(r'^[A-Za-z]{15,}$', compound_noun)):
                compound_nouns.append(compound_noun)

        # フィルタリングとスコアリング
        if use_scoring:
            return self._score_and_rank(compound_nouns, top_n)
        else:
            return self._filter_and_count(compound_nouns, top_n)

    def _extract_with_regex(self, text: str, top_n: int,
                            use_scoring: bool) -> List[str]:
        """正規表現を使用したキーワード抽出"""
        # カタカナ語、漢字複合語、英数字を抽出
        pattern = r'[ァ-ヴー]{2,}|[一-龥]{2,}|[A-Za-z]{2,}[A-Za-z0-9]*'
        words = re.findall(pattern, text)

        # フィルタリングとスコアリング
        if use_scoring:
            return self._score_and_rank(words, top_n)
        else:
            return self._filter_and_count(words, top_n)

    def _filter_and_count(self, words: List[str], top_n: int) -> List[str]:
        """頻度ベースのフィルタリング（シンプル版）"""
        # ストップワード除外 (小文字で比較)
        filtered = [w for w in words if w.lower() not in self.stopwords and len(w) > 1]

        # 頻度カウント
        word_freq = Counter(filtered)

        # 上位N件を返す
        return [word for word, freq in word_freq.most_common(top_n)]

    def _score_and_rank(self, words: List[str], top_n: int) -> List[str]:
        """スコアリングベースのランキング（高度版）"""
        word_scores = {}
        word_freq = Counter(words)

        for word, freq in word_freq.items():
            # ストップワード除外 (小文字で比較)
            if word.lower() in self.stopwords or len(word) <= 1:
                continue

            score = 0.0

            # 1. 頻度スコア（正規化: 最大3回まで）
            freq_score = min(freq / 3.0, 1.0) * 0.3
            score += freq_score

            # 2. 長さスコア（複合語優遇）
            length_score = min(len(word) / 8.0, 1.0) * 0.3
            score += length_score

            # 3. 重要キーワードブースト (部分一致も考慮)
            is_important = False
            for imp in self.important_keywords:
                if imp.lower() in word.lower():
                    is_important = True
                    break
            if is_important:
                score += 0.5

            # 4. 文字種スコア
            # カタカナ3文字以上
            if re.match(r'^[ァ-ヴー]{3,}$', word):
                score += 0.2
            # 英大文字2文字以上 (頭字語)
            elif re.match(r'^[A-Z]{2,}$', word):
                score += 0.3
            # 英語の開始が大文字 (固有名詞の可能性)
            elif re.match(r'^[A-Z][a-z]+$', word):
                score += 0.1
            # 漢字4文字以上
            elif re.match(r'^[一-龥]{4,}$', word):
                score += 0.2

            word_scores[word] = score

        # スコア降順でソート
        ranked = sorted(word_scores.items(), key=lambda x: x[1], reverse=True)

        return [word for word, score in ranked[:top_n]]

    def extract_with_details(self, text: str, top_n: int = 10) -> Dict[str, List[Tuple[str, float]]]:
        """
        詳細情報付きでキーワードを抽出（比較分析用）
        Returns:
            各手法での抽出結果と詳細スコア
        """
        results = {}
        is_japanese = bool(re.search(r'[ぁ-んァ-ヶー一-龠]', text))

        # MeCab複合名詞版
        if self.mecab_available and is_japanese:
            try:
                mecab_keywords = self._extract_with_mecab_scored(text, top_n)
                results['MeCab複合名詞'] = mecab_keywords
            except Exception as e:
                results['MeCab複合名詞'] = [(f"エラー: {e}", 0.0)]
        elif not is_japanese:
            results['MeCab複合名詞'] = [("(英語テキストのためスキップ)", 0.0)]

        # 正規表現版
        regex_keywords = self._extract_with_regex_scored(text, top_n)
        results['正規表現'] = regex_keywords

        # 統合版（デフォルト動作）
        integrated_keywords = self._extract_integrated(text, top_n)
        results['統合版'] = integrated_keywords

        return results

    def _extract_with_mecab_scored(self, text: str, top_n: int) -> List[Tuple[str, float]]:
        """MeCab版（スコア付き）"""
        keywords = self._extract_with_mecab(text, top_n, use_scoring=True)
        # スコアを再計算
        scored = []
        for kw in keywords:
            score = self._calculate_keyword_score(kw, text)
            scored.append((kw, score))
        return scored

    def _extract_with_regex_scored(self, text: str, top_n: int) -> List[Tuple[str, float]]:
        """正規表現版（スコア付き）"""
        keywords = self._extract_with_regex(text, top_n, use_scoring=True)
        scored = []
        for kw in keywords:
            score = self._calculate_keyword_score(kw, text)
            scored.append((kw, score))
        return scored

    def _extract_integrated(self, text: str, top_n: int) -> List[Tuple[str, float]]:
        """統合版: MeCabと正規表現の結果をマージ"""
        all_keywords = set()
        is_japanese = bool(re.search(r'[ぁ-んァ-ヶー一-龠]', text))

        # MeCabから抽出 (日本語のみ)
        if self.mecab_available and is_japanese:
            try:
                mecab_kws = self._extract_with_mecab(text, top_n * 2, use_scoring=False)
                all_keywords.update(mecab_kws)
            except Exception:
                pass

        # 正規表現から抽出
        regex_kws = self._extract_with_regex(text, top_n * 2, use_scoring=False)
        all_keywords.update(regex_kws)

        # 統合スコアリング
        scored = []
        for kw in all_keywords:
            if kw in self.stopwords or len(kw) <= 1:
                continue
            score = self._calculate_keyword_score(kw, text)
            scored.append((kw, score))

        # スコア降順でソート
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_n]

    def _calculate_keyword_score(self, keyword: str, text: str) -> float:
        """キーワードの総合スコアを計算"""
        score = 0.0

        # ストップワード除外
        if keyword.lower() in self.stopwords:
            return 0.0

        # 出現頻度
        freq = text.count(keyword)
        freq_score = min(freq / 3.0, 1.0) * 0.3
        score += freq_score

        # 長さ
        length_score = min(len(keyword) / 8.0, 1.0) * 0.2
        score += length_score

        # 重要キーワード
        is_important = False
        for imp in self.important_keywords:
            if imp.lower() in keyword.lower():
                is_important = True
                break
        if is_important:
            score += 0.4

        # 文字種
        if re.match(r'^[ァ-ヴー]{3,}$', keyword):
            score += 0.15
        elif re.match(r'^[A-Z]{2,}$', keyword):
            score += 0.2
        elif re.match(r'^[A-Z][a-z]+$', keyword):
            score += 0.1
        elif re.match(r'^[一-龥]{4,}$', keyword):
            score += 0.15

        return min(score, 1.0)


# =============================================================================
# ユーティリティ関数
# =============================================================================

def compare_methods(text: str, top_n: int = 10):
    """各抽出手法を比較して結果を表示"""
    extractor = KeywordExtractor()

    print("=" * 80)
    print(f"キーワード抽出手法の比較 (Text: {text[:30].strip()}...)")
    print("=" * 80)

    results = extractor.extract_with_details(text, top_n)

    for method, keywords in results.items():
        print(f"\n【{method}】")
        print("-" * 80)
        for i, (keyword, score) in enumerate(keywords, 1):
            print(f"  {i:2d}. {keyword:20s} (スコア: {score:.3f})")


def main():
    """メイン実行関数"""

    # 1. 日本語サンプル（改行あり）
    sample_text_jp = """
    人工知能（AI）は、機械学習と深層学習を基盤として急速に発展しています。
    特に自然言語処理（NLP）の分野では、トランスフォーマーモデルが革命的な成果を上げました。
    BERTやGPTなどの大規模言語モデルは、文脈理解能力を大幅に向上させています。
    AIの応用は医療診断から自動運転まで幅広く、社会に大きな影響を与えています。
    """

    # 2. 日本語サンプル（改行なし - 句点で分割対象）
    sample_text_jp2 = """人工知能（AI）は、機械学習と深層学習を基盤として急速に発展しています。特に自然言語処理（NLP）の分野では、トランスフォーマーモデルが革命的な成果を上げました。BERTやGPTなどの大規模言語モデルは、文脈理解能力を大幅に向上させています。AIの応用は医療診断から自動運転まで幅広く、社会に大きな影響を与えています。"""

    # 3. 英語サンプル
    sample_text_en = """
    Artificial intelligence (AI) is rapidly advancing based on machine 00_learning.md and deep 00_learning.md.
    In the field of natural language processing (NLP) in particular, transformer models have achieved revolutionary results.
    Large language models like BERT and GPT have significantly enhanced contextual understanding capabilities.
    AI applications span widely from medical diagnosis to autonomous driving, profoundly impacting society.
    """

    sample_text_en2 = """Artificial intelligence (AI) is rapidly advancing based on machine 00_learning.md and deep 00_learning.md.In the field of natural language processing (NLP) in particular, transformer models have achieved revolutionary results.Large language models like BERT and GPT have significantly enhanced contextual understanding capabilities.AI applications span widely from medical diagnosis to autonomous driving, profoundly impacting society."""

    # =========================================================================
    # チャンク分割のデモ
    # =========================================================================
    print("=" * 80)
    print("【チャンク分割機能のデモ】")
    print("=" * 80)

    # --- sample_text_jp（改行あり）のチャンク分割 ---
    print("\n■ sample_text_jp（改行あり）のチャンク分割")
    print("-" * 60)
    chunks_jp = chunk_text(sample_text_jp)
    print(f"分割方法: 改行")
    print(f"チャンク数: {len(chunks_jp)}")
    for i, chunk in enumerate(chunks_jp, 1):
        print(f"  [{i}] {chunk}")

    print()
    chunks_en2 = chunk_text(sample_text_en2)
    for i, chunk_en in enumerate(chunks_en2, 1):
        print(f"  [{i}] {chunk_en}")

    # --- sample_text_jp2（改行なし）のチャンク分割 ---
    print("\n■ sample_text_jp2（改行なし）のチャンク分割")
    print("-" * 60)
    chunks_jp2 = chunk_text(sample_text_jp2)
    print(f"分割方法: 句点（。）")
    print(f"チャンク数: {len(chunks_jp2)}")
    for i, chunk in enumerate(chunks_jp2, 1):
        print(f"  [{i}] {chunk}")

    # =========================================================================
    # キーワード抽出のデモ（従来機能）
    # =========================================================================
    print("\n\n" + "=" * 80)
    print("【キーワード抽出機能のデモ】")
    print("=" * 80)

    extractor = KeywordExtractor()

    for lang, text in [("日本語（改行あり）", sample_text_jp), ("英語", sample_text_en)]:
        print("\n" + "-" * 60)
        print(f"--- {lang} キーワード抽出テスト ---")
        print("-" * 60)

        # デフォルト抽出
        keywords = extractor.extract(text, top_n=10)
        print(f"\n【抽出結果（上位10件）】")
        for i, kw in enumerate(keywords, 1):
            print(f"  {i:2d}. {kw}")

    # =========================================================================
    # シンプルな出力例
    # =========================================================================
    print("\n\n" + "=" * 80)
    print("【シンプルな使用例】")
    print("=" * 80)

    print('\n--- chunk_text() の戻り値 ---')
    chunks = chunk_text(sample_text_jp2)
    for i, chunk in enumerate(chunks, 1):
        print(f"[{i}] {chunk}")
    # print(f"chunks = {chunks}\n")
    # print(f"type: {type(chunks)}")

    print('\n--- KeywordExtractor.extract() の戻り値 ---')
    keywords = extractor.extract(sample_text_jp2, top_n=5)
    print(f"keywords = {keywords}")
    print(f"type: {type(keywords)}")


if __name__ == "__main__":
    main()
