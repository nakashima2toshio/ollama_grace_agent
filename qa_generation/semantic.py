#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qa_generation/semantic.py - セマンティック分析・カバレッジ測定モジュール
"""

import re
import logging
from typing import List, Dict, Any, Optional
import numpy as np
import tiktoken
from helper.helper_llm import create_llm_client  # [FIXED] helper_llm → helper.helper_llm
from helper.helper_embedding import create_embedding_client, get_embedding_dimensions

logger = logging.getLogger(__name__)


class SemanticCoverage:
    """意味的な網羅性を測定するクラス（OpenAI Embedding API使用）"""

    def __init__(self,
                 embedding_model="text-embedding-3-large"):  # [MIGRATION] gemini-embedding-001 → text-embedding-3-large
        self.embedding_model = embedding_model
        # Gemini埋め込みクライアントを使用
        self.embedding_client = create_embedding_client(provider="openai")  # [MIGRATION] gemini → openai
        self.embedding_dims = get_embedding_dimensions("openai")  # 3072（openai text-embedding-3-large と同次元）
        # トークンカウント用のLLMクライアント (decode機能がないためtiktokenを併用)
        # [MIGRATION anthropic→openai] provider="anthropic" → "openai"
        self.unified_client = create_llm_client(provider="openai")
        self.tokenizer = tiktoken.get_encoding("cl100k_base")  # 強制分割・デコード用にtiktokenを使用

        # APIキーの有無フラグ（クライアント作成成功ならTrue）
        self.has_api_key = True

        # MeCab利用可否チェック
        self.mecab_available = self._check_mecab_availability()

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

    def create_semantic_chunks(self, document: str, max_tokens: int = 200, min_tokens: int = 50,
                               overlap_tokens: int = 0, use_similarity: bool = False,
                               similarity_threshold: float = 0.7,
                               prefer_paragraphs: bool = True, verbose: bool = True) -> List[Dict]:
        """
        文書を意味的に区切られたチャンクに分割（高度なセマンティック分割）

        追加機能：
        - チャンクオーバーラップ: 前のチャンクの末尾を次に追加し、文脈を維持。
        - ベクトル類似度分割: 文間の埋め込みベクトルの距離を見てトピック境界を特定。

        Args:
            document: 分割対象の文書
            max_tokens: チャンクの最大トークン数
            min_tokens: チャンクの最小トークン数
            overlap_tokens: 前のチャンクと重複させるトークン数
            use_similarity: ベクトル類似度による分割を行うか
            similarity_threshold: 分割判定の類似度閾値（低いほど大きく分割）
            prefer_paragraphs: 段落ベースの分割を優先するか
            verbose: 詳細な出力を行うか

        Returns:
            チャンク辞書のリスト
        """

        # Step 1: 段落ベースの分割を試行（prefer_paragraphs=Trueの場合）
        if prefer_paragraphs:
            para_chunks = self._chunk_by_paragraphs(document, max_tokens, min_tokens)

            # オーバーラップが必要な場合は、ここで調整が必要だが、
            # paragraph優先時は筆者の意図を尊重するため、基本はそのまま。
            # ただし、overlap_tokens > 0 の場合は後続処理で対応。

            if verbose:
                logger.info(f"段落ベースのチャンク数: {len(para_chunks)}")

            # 段落ベースのチャンクを標準フォーマットに変換
            chunks = []
            for i, chunk in enumerate(para_chunks):
                chunk_text = chunk['text']
                sentences = self._split_into_sentences(chunk_text)
                chunks.append({
                    "id": f"chunk_{i}",
                    "text": chunk_text,
                    "type": chunk['type'],
                    "sentences": sentences,
                    "start_sentence_idx": 0,
                    "end_sentence_idx": len(sentences) - 1
                })
        else:
            # Step 1 (旧方式/高度方式): 全文を文単位で分割
            sentences = self._split_into_sentences(document)
            if verbose:
                logger.info(f"文の数: {len(sentences)}")

            # 類似度による分割ポイントの特定
            similarities = []
            if use_similarity and len(sentences) > 1:
                similarities = self._calculate_sentence_similarities(sentences)

            # Step 2: 意味的に関連する文をグループ化
            chunks = []
            current_chunk = []
            current_tokens = 0

            for i, sentence in enumerate(sentences):
                # トークンカウントはローカルで実行（DNSエラー防止）
                sentence_tokens = len(self.tokenizer.encode(sentence))

                # 分割の判定条件
                # 1. トークン数が上限を超える
                # 2. 類似度が閾値を下回る（use_similarity=Trueの場合）
                should_split = False
                if current_chunk:
                    if current_tokens + sentence_tokens > max_tokens:
                        should_split = True
                    elif use_similarity and i > 0 and i - 1 < len(similarities):
                        if similarities[i - 1] < similarity_threshold:
                            should_split = True

                if should_split:
                    chunk_text = " ".join(current_chunk)
                    chunks.append({
                        "id": f"chunk_{len(chunks)}",
                        "text": chunk_text,
                        "type": "semantic_group" if use_similarity else "sentence_group",
                        "sentences": current_chunk.copy(),
                        "start_sentence_idx": i - len(current_chunk),
                        "end_sentence_idx": i - 1
                    })
                    current_chunk = [sentence]
                    current_tokens = sentence_tokens
                else:
                    current_chunk.append(sentence)
                    current_tokens += sentence_tokens

            # 最後のチャンクを追加
            if current_chunk:
                chunks.append({
                    "id": f"chunk_{len(chunks)}",
                    "text": " ".join(current_chunk),
                    "type": "semantic_group" if use_similarity else "sentence_group",
                    "sentences": current_chunk,
                    "start_sentence_idx": len(sentences) - len(current_chunk),
                    "end_sentence_idx": len(sentences) - 1
                })

        # Step 3: トピックの連続性を考慮した再調整
        chunks = self._adjust_chunks_for_topic_continuity(chunks, min_tokens)

        # Step 4: チャンクオーバーラップの適用
        if overlap_tokens > 0:
            chunks = self._apply_chunk_overlap(chunks, overlap_tokens)

        return chunks

    def _calculate_sentence_similarities(self, sentences: List[str]) -> List[float]:
        """隣接する文のコサイン類似度を計算する"""
        try:
            embeddings = self.generate_embeddings_batch(sentences)
            similarities = []
            for i in range(len(embeddings) - 1):
                sim = self.cosine_similarity(embeddings[i], embeddings[i + 1])
                similarities.append(sim)
            return similarities
        except Exception as e:
            logger.error(f"類似度計算失敗: {e}")
            return [1.0] * (len(sentences) - 1)  # 失敗時は分割しないように1.0を返す

    def _apply_chunk_overlap(self, chunks: List[Dict], overlap_tokens: int) -> List[Dict]:
        """前のチャンクの末尾を次のチャンクの冒頭に重複させる"""
        if len(chunks) <= 1:
            return chunks

        new_chunks = [chunks[0].copy()]

        for i in range(1, len(chunks)):
            current_chunk = chunks[i].copy()
            prev_chunk = chunks[i - 1]

            # 前のチャンクから末尾の文を抽出（overlap_tokensに収まる範囲で）
            overlap_sentences = []
            current_overlap_count = 0

            for sent in reversed(prev_chunk["sentences"]):
                sent_tokens = len(self.tokenizer.encode(sent))
                if current_overlap_count + sent_tokens <= overlap_tokens:
                    overlap_sentences.insert(0, sent)
                    current_overlap_count += sent_tokens
                else:
                    break

            if overlap_sentences:
                overlap_text = " ".join(overlap_sentences)
                current_chunk["text"] = overlap_text + " " + current_chunk["text"]
                current_chunk["overlap_text"] = overlap_text
                current_chunk["is_overlapped"] = True

            new_chunks.append(current_chunk)

        return new_chunks

    def _split_into_paragraphs(self, text: str) -> List[str]:
        """
        段落単位で分割（セマンティック分割の最優先レベル）

        段落は筆者が意図的に作った意味的なまとまりであり、
        最も重要なセマンティック境界となる
        """
        # 空行（\n\n）で段落を分割
        paragraphs = re.split(r'\n\s*\n', text)

        # 空白のみの段落を除外
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        return paragraphs

    def _chunk_by_paragraphs(self, text: str, max_tokens: int = 200, min_tokens: int = 50) -> List[Dict[str, Any]]:
        """
        段落単位でチャンク化（セマンティック最優先）

        段落をベースにチャンクを作成し、トークン数制限を考慮する。
        段落が大きすぎる場合は文単位に分割する。

        Args:
            text: 分割対象のテキスト
            max_tokens: チャンクの最大トークン数
            min_tokens: チャンクの最小トークン数（これより小さい場合は次と結合を検討）

        Returns:
            チャンクのリスト（各チャンクは {'text': str, 'type': str} の辞書）
        """
        paragraphs = self._split_into_paragraphs(text)
        chunks = []

        for para in paragraphs:
            para_tokens = self.unified_client.count_tokens(para, model=self.embedding_model)

            if para_tokens <= max_tokens:
                # 段落がそのままチャンクとして適切
                chunks.append({'text': para, 'type': 'paragraph'})
            else:
                # 段落が大きすぎる → 文単位に分割
                sentences = self._split_into_sentences(para)
                current_chunk = []
                current_tokens = 0

                for sent in sentences:
                    sent_tokens = self.unified_client.count_tokens(sent, model=self.embedding_model)

                    if sent_tokens > max_tokens:
                        # 単一文が上限超過 → 強制分割
                        if current_chunk:
                            chunks.append({'text': ''.join(current_chunk), 'type': 'sentence_group'})
                            # No need to recalculate current_tokens, just reset
                            current_chunk = []
                            current_tokens = 0

                        # 強制分割を実施
                        forced_chunks = self._force_split_sentence(sent, max_tokens)
                        chunks.extend(forced_chunks)

                    elif current_tokens + sent_tokens > max_tokens:
                        # 追加すると上限超過 → 現在のチャンクを確定
                        if current_chunk:
                            chunks.append({'text': ''.join(current_chunk), 'type': 'sentence_group'})
                        current_chunk = [sent]
                        current_tokens = sent_tokens

                    else:
                        # 追加可能
                        current_chunk.append(sent)
                        current_tokens += sent_tokens

                # 残りを確定
                if current_chunk:
                    chunks.append({'text': ''.join(current_chunk), 'type': 'sentence_group'})

        return chunks

    def _force_split_sentence(self, sentence: str, max_tokens: int = 200) -> List[Dict[str, Any]]:
        """
        単一文が上限超過の場合に強制的に分割（最終手段）

        セマンティック境界を無視して、トークン数ベースで強制的に分割する。
        これは意味的な一貫性を犠牲にするが、処理上の制約を守るために必要。

        Args:
            sentence: 分割対象の文
            max_tokens: チャンクの最大トークン数

        Returns:
            強制分割されたチャンクのリスト
        """
        # トークンレベルで分割
        tokens = self.tokenizer.encode(sentence)
        forced_chunks = []

        for i in range(0, len(tokens), max_tokens):
            chunk_tokens = tokens[i:i + max_tokens]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            forced_chunks.append({
                'text': chunk_text,
                'type': 'forced_split'
            })

        return forced_chunks

    def _split_into_sentences(self, text: str) -> List[str]:
        """文単位で分割（言語自動判定・MeCab優先対応）"""

        # 日本語判定（最初の100文字で判定）
        is_japanese = bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text[:100]))

        if is_japanese and self.mecab_available:
            # 日本語の場合、MeCab利用を優先（セマンティック精度向上）
            try:
                sentences = self._split_sentences_mecab(text)
                if sentences:
                    return sentences
            except Exception:
                pass  # フォールバック

        # 英語 or MeCab失敗時: 正規表現
        # 句点等で終わる塊を抽出
        sentences = re.findall(r'[^。．.！？!?]+[。．.！？!?]\s*', text)
        if not sentences:
            # 句点がない場合は全体を1つの文とする
            sentences = [text.strip()] if text.strip() else []
        else:
            # 最後の文の後に句点がないテキストが残っている場合
            last_pos = text.rfind(sentences[-1]) + len(sentences[-1])
            if last_pos < len(text):
                remaining = text[last_pos:].strip()
                if remaining:
                    sentences.append(remaining)

        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences

    def _split_sentences_mecab(self, text: str) -> List[str]:
        """MeCabを使った文分割（日本語用）"""
        import MeCab

        tagger = MeCab.Tagger()
        node = tagger.parseToNode(text)

        sentences = []
        current_sentence = []

        while node:
            surface = node.surface
            node.feature.split(',')

            if surface:
                current_sentence.append(surface)

                # 文末判定：句点（。）、疑問符（？）、感嘆符（！）
                if surface in ['。', '．', '？', '！', '?', '!']:
                    sentence = ''.join(current_sentence).strip()
                    if sentence:
                        sentences.append(sentence)
                    current_sentence = []

            node = node.next

        # 最後の文を追加
        if current_sentence:
            sentence = ''.join(current_sentence).strip()
            if sentence:
                sentences.append(sentence)

        return sentences if sentences else []

    def _adjust_chunks_for_topic_continuity(self, chunks: List[Dict], min_tokens: int = 50) -> List[Dict]:
        """
        トピックの連続性を考慮してチャンクを調整（最小トークン数対応）

        短すぎるチャンクを隣接チャンクとマージして意味的まとまりを維持する。

        Args:
            chunks: チャンクのリスト
            min_tokens: チャンクの最小トークン数（これより小さい場合はマージを検討）

        Returns:
            調整後のチャンクリスト
        """
        adjusted_chunks = []

        for i, chunk in enumerate(chunks):
            chunk_tokens = self.unified_client.count_tokens(chunk["text"], model=self.embedding_model)

            # 最小トークン数以下の短いチャンクの場合
            if i > 0 and chunk_tokens < min_tokens:
                # 前のチャンクとマージを検討
                prev_chunk = adjusted_chunks[-1]
                combined_text = prev_chunk["text"] + " " + chunk["text"]
                combined_tokens = self.unified_client.count_tokens(combined_text, model=self.embedding_model)

                # マージしても最大トークン数（300）を超えない場合はマージ
                if combined_tokens < 300:
                    # マージ実施
                    prev_chunk["text"] = combined_text
                    prev_chunk["sentences"].extend(chunk["sentences"])
                    prev_chunk["end_sentence_idx"] = chunk["end_sentence_idx"]

                    # typeの更新（異なるtypeがマージされた場合）
                    if prev_chunk.get("type") != chunk.get("type"):
                        prev_chunk["type"] = "merged"

                    continue

            adjusted_chunks.append(chunk)

        return adjusted_chunks

    def generate_embeddings(self, doc_chunks: List[Dict]) -> np.ndarray:
        """
        チャンクのリストから埋め込みベクトルを生成（OpenAI Embedding API使用）

        重要ポイント：
        1. バッチ処理で効率化
        2. エラーハンドリング
        3. 正規化（コサイン類似度計算の準備）
        """

        if not self.has_api_key:
            print("⚠️  OPENAI_API_KEY が設定されていません。埋め込み生成をスキップします。")
            # ダミーのゼロベクトルを返す
            return np.zeros((len(doc_chunks), self.embedding_dims))

        texts = [chunk["text"] for chunk in doc_chunks]

        try:
            # Gemini Embedding APIを呼び出し
            embedding_vectors = self.embedding_client.embed_texts(texts, batch_size=100)

            # 埋め込みベクトルを正規化
            embeddings = []
            for embedding in embedding_vectors:
                embedding = np.array(embedding)
                # L2正規化（コサイン類似度の計算を高速化）
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm
                embeddings.append(embedding)

            return np.array(embeddings)

        except Exception as e:
            print(f"埋め込み生成エラー: {e}")
            # エラー時はゼロベクトルを返す
            return np.zeros((len(doc_chunks), self.embedding_dims))

    def generate_embedding(self, text: str) -> np.ndarray:
        """単一テキストの埋め込み生成（OpenAI Embedding API使用）"""
        if not self.has_api_key:
            return np.zeros(self.embedding_dims)

        try:
            # Gemini Embedding APIを使用
            embedding = self.embedding_client.embed_text(text)
            embedding = np.array(embedding)
            # 正規化
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            return embedding
        except Exception as e:
            print(f"埋め込み生成エラー: {e}")
            return np.zeros(self.embedding_dims)

    def generate_embeddings_batch(self, texts: List[str], batch_size: int = 100) -> np.ndarray:
        """
        複数テキストの埋め込みを一括生成（OpenAI Embedding API使用）

        Args:
            texts: テキストのリスト
            batch_size: 1リクエストあたりのテキスト数（デフォルト: 100）

        Returns:
            埋め込みベクトルの配列 (len(texts), 3072)
        """
        if not self.has_api_key:
            print("⚠️  OPENAI_API_KEY が設定されていません。埋め込み生成をスキップします。")
            return np.zeros((len(texts), self.embedding_dims))

        try:
            # Gemini Embedding APIを使用
            embedding_vectors = self.embedding_client.embed_texts(texts, batch_size=batch_size)

            # 埋め込みベクトルを正規化
            embeddings = []
            for embedding in embedding_vectors:
                embedding = np.array(embedding)
                # L2正規化
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm
                embeddings.append(embedding)

            return np.array(embeddings)

        except Exception as e:
            print(f"バッチ埋め込み生成エラー: {e}")
            # エラー時はゼロベクトルを返す
            return np.zeros((len(texts), self.embedding_dims))

    def cosine_similarity(self, doc_emb: np.ndarray, qa_emb: np.ndarray) -> float:
        """
        コサイン類似度を計算

        重要ポイント：
        1. 事前に正規化済みなら内積で計算可能
        2. 範囲は[-1, 1]、1に近いほど類似
        """

        # ベクトルが正規化済みの場合は内積で計算
        if np.allclose(np.linalg.norm(doc_emb), 1.0) and \
                np.allclose(np.linalg.norm(qa_emb), 1.0):
            return float(np.dot(doc_emb, qa_emb))

        # 正規化されていない場合は完全な計算
        dot_product = np.dot(doc_emb, qa_emb)
        norm_doc = np.linalg.norm(doc_emb)
        norm_qa = np.linalg.norm(qa_emb)

        if norm_doc == 0 or norm_qa == 0:
            return 0.0

        return float(dot_product / (float(norm_doc) * float(norm_qa)))
