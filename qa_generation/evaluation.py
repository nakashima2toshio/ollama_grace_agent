#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qa_generation/evaluation.py - カバレッジ分析モジュール（v3.0 - config.py依存削除版）

改修内容 (v3.0):
- qa_generation/config.py への依存を削除
- データセット別の決め打ち閾値を廃止し、統一デフォルト値を使用
"""
import logging
import numpy as np
import tiktoken
from typing import List, Dict, Optional
from qa_generation.semantic import SemanticCoverage

logger = logging.getLogger(__name__)


def get_optimal_thresholds(dataset_type: str = None) -> Dict[str, float]:
    '''カバレージ分析用の閾値を取得

    Args:
        dataset_type: データセットタイプ（現在は未使用、後方互換性のため残す）

    Returns:
        閾値辞書 {strict, standard, lenient}
    '''
    # 統一デフォルト値を使用（データセット別の決め打ち値を廃止）
    return {
        "strict": 0.8,
        "standard": 0.7,
        "lenient": 0.6
    }


def multi_threshold_coverage(coverage_matrix: np.ndarray, chunks: List[Dict],
                             qa_pairs: List[Dict], thresholds: Dict[str, float]) -> Dict:
    '''複数閾値でカバレージを評価
    Args:
        coverage_matrix: カバレージ行列
        chunks: チャンクリスト
        qa_pairs: Q/Aペアリスト
        thresholds: 閾値辞書
    Returns:
        多段階カバレージ結果
    '''
    results = {}
    max_similarities = coverage_matrix.max(axis=1)

    for level, threshold in thresholds.items():
        covered = sum(1 for s in max_similarities if s >= threshold)
        uncovered_chunks = [
            {
                "chunk_id": chunks[i].get("id", f"chunk_{i}"),
                "similarity": float(max_similarities[i]),
                "gap": float(threshold - max_similarities[i])
            }
            for i, sim in enumerate(max_similarities)
            if sim < threshold
        ]

        results[level] = {
            "threshold": threshold,
            "covered_chunks": covered,
            "coverage_rate": covered / len(chunks) if chunks else 0,
            "uncovered_count": len(uncovered_chunks),
            "uncovered_chunks": uncovered_chunks
        }

    return results


def analyze_chunk_characteristics_coverage(chunks: List[Dict], coverage_matrix: np.ndarray,
                                          qa_pairs: List[Dict], threshold: float = 0.7) -> Dict:
    '''チャンク特性別のカバレージ分析
    Args:
        chunks: チャンクリスト
        coverage_matrix: カバレージ行列
        qa_pairs: Q/Aペアリスト
        threshold: 判定閾値
    Returns:
        チャンク特性別カバレージ結果
    '''
    tokenizer = tiktoken.get_encoding("cl100k_base")
    results = {
        "by_length": {},      # 長さ別
        "by_position": {},    # 位置別
        "summary": {}
    }

    # 1. 長さ別分析
    for i, chunk in enumerate(chunks):
        token_count = len(tokenizer.encode(chunk['text']))
        length_category = (
            "short" if token_count < 100 else
            "medium" if token_count < 200 else
            "long"
        )

        if length_category not in results["by_length"]:
            results["by_length"][length_category] = {
                "count": 0,
                "covered": 0,
                "avg_similarity": 0.0,
                "similarities": []
            }

        max_sim = coverage_matrix[i].max()
        results["by_length"][length_category]["count"] += 1
        results["by_length"][length_category]["similarities"].append(float(max_sim))

        if max_sim >= threshold:
            results["by_length"][length_category]["covered"] += 1

    # 平均類似度とカバレージ率を計算
    for length_cat in results["by_length"]:
        data = results["by_length"][length_cat]
        data["avg_similarity"] = float(np.mean(data["similarities"])) if data["similarities"] else 0.0
        data["coverage_rate"] = data["covered"] / data["count"] if data["count"] > 0 else 0.0
        del data["similarities"]

    # 2. 位置別分析（文書の前半/中盤/後半）
    total_chunks = len(chunks)
    for i, chunk in enumerate(chunks):
        position = (
            "beginning" if i < total_chunks * 0.33 else
            "middle" if i < total_chunks * 0.67 else
            "end"
        )

        if position not in results["by_position"]:
            results["by_position"][position] = {
                "count": 0,
                "covered": 0,
                "avg_similarity": 0.0,
                "similarities": []
            }

        max_sim = coverage_matrix[i].max()
        results["by_position"][position]["count"] += 1
        results["by_position"][position]["similarities"].append(float(max_sim))

        if max_sim >= threshold:
            results["by_position"][position]["covered"] += 1

    # 平均類似度とカバレージ率を計算
    for position in results["by_position"]:
        data = results["by_position"][position]
        data["avg_similarity"] = float(np.mean(data["similarities"])) if data["similarities"] else 0.0
        data["coverage_rate"] = data["covered"] / data["count"] if data["count"] > 0 else 0.0
        del data["similarities"]

    # 3. サマリー情報
    results["summary"] = {
        "total_chunks": len(chunks),
        "total_qa_pairs": len(qa_pairs),
        "threshold_used": threshold,
        "insights": []
    }

    # インサイト生成
    for length_cat, data in results["by_length"].items():
        if data["coverage_rate"] < 0.7:
            results["summary"]["insights"].append(
                f"{length_cat}チャンクのカバレージが低い（{data['coverage_rate']:.1%}）"
            )

    for position, data in results["by_position"].items():
        if data["coverage_rate"] < 0.7:
            results["summary"]["insights"].append(
                f"文書{position}部分のカバレージが低い（{data['coverage_rate']:.1%}）"
            )

    return results


def analyze_coverage(chunks: List[Dict], qa_pairs: List[Dict], dataset_type: str = "wikipedia_ja",
                     custom_threshold: Optional[float] = None) -> Dict:
    """生成されたQ/Aペアのカバレージを分析（多段階カバレージ分析対応）
    Args:
        chunks: チャンクリスト
        qa_pairs: Q/Aペアリスト
        dataset_type: データセットタイプ（閾値自動設定に使用）
        custom_threshold: カスタム閾値（指定時はこれを使用）
    Returns:
        カバレージ分析結果（多段階評価、チャンク特性分析を含む）
    """
    analyzer = SemanticCoverage()

    # 埋め込み生成（バッチAPI最適化版）
    logger.info("=" * 60)
    logger.info("カバレージ分析: 埋め込みベクトル生成開始")
    logger.info("=" * 60)

    # チャンクの埋め込み生成（既存メソッド使用）
    logger.info(f"[Step 1/3] チャンク埋め込み生成: {len(chunks)}件")
    doc_embeddings = analyzer.generate_embeddings(chunks)
    logger.info(f"[Step 1/3] チャンク埋め込み完了: {len(doc_embeddings)}件")

    # Q&Aペアの埋め込み生成（バッチAPI使用で高速化）
    qa_texts = [f"{qa['question']} {qa['answer']}" for qa in qa_pairs]
    logger.info(f"[Step 2/3] Q/Aペア埋め込み生成: {len(qa_texts)}件")
    qa_embeddings = analyzer.generate_embeddings_batch(qa_texts, batch_size=2048)
    logger.info(f"[Step 2/3] Q/Aペア埋め込み完了: {len(qa_embeddings)}件")

    if len(qa_embeddings) == 0:
        return {
            "coverage_rate": 0.0,
            "covered_chunks": 0,
            "total_chunks": len(chunks),
            "uncovered_chunks": chunks,
            "multi_threshold": {},
            "chunk_analysis": {}
        }

    # カバレージ行列計算
    logger.info("カバレージ行列計算中...")
    # 行列演算により全類似度を一括計算（NumPy/BLASによる高速化）
    try:
        # すでに正規化済みのベクトルのため、行列積がコサイン類似度となります
        coverage_matrix = np.dot(doc_embeddings, qa_embeddings.T)
        # 数値計算上の微小な誤差を [-1.0, 1.0] にクリップ
        coverage_matrix = np.clip(coverage_matrix, -1.0, 1.0)
    except Exception as e:
        logger.error(f"行列計算エラー (フォールバック実行): {e}")
        coverage_matrix = np.zeros((len(chunks), len(qa_pairs)))
        for i in range(len(doc_embeddings)):
            for j in range(len(qa_embeddings)):
                similarity = analyzer.cosine_similarity(doc_embeddings[i], qa_embeddings[j])
                coverage_matrix[i, j] = similarity

    # データセット別最適閾値を取得
    thresholds = get_optimal_thresholds(dataset_type)

    # カスタム閾値が指定されている場合は上書き
    if custom_threshold is not None:
        standard_threshold = custom_threshold
        logger.info(f"カスタム閾値を使用: {custom_threshold}")
    else:
        standard_threshold = thresholds["standard"]

    # 基本カバレージ（標準閾値）
    max_similarities = coverage_matrix.max(axis=1)
    covered_count = sum(1 for s in max_similarities if s >= standard_threshold)
    coverage_rate = covered_count / len(chunks) if chunks else 0

    # 未カバーチャンクの特定
    uncovered_chunks = []
    for i, (chunk, sim) in enumerate(zip(chunks, max_similarities)):
        if sim < standard_threshold:
            uncovered_chunks.append({
                'chunk': chunk,
                'similarity': float(sim),
                'gap': float(standard_threshold - sim)
            })

    # 提案1の機能: 多段階カバレージ分析
    logger.info("多段階カバレージ分析実行中...")
    multi_threshold_results = multi_threshold_coverage(coverage_matrix, chunks, qa_pairs, thresholds)

    # 提案1の機能: チャンク特性別分析
    logger.info("チャンク特性別分析実行中...")
    chunk_characteristics = analyze_chunk_characteristics_coverage(
        chunks, coverage_matrix, qa_pairs, standard_threshold
    )

    # 結果を統合
    results = {
        # 基本メトリクス
        "coverage_rate": coverage_rate,
        "covered_chunks": covered_count,
        "total_chunks": len(chunks),
        "uncovered_chunks": uncovered_chunks,
        "max_similarities": max_similarities.tolist(),
        "threshold": standard_threshold,

        # 提案1: 多段階カバレージ
        "multi_threshold": multi_threshold_results,

        # 提案1: チャンク特性別分析
        "chunk_analysis": chunk_characteristics,

        # データセット情報
        "dataset_type": dataset_type,
        "optimal_thresholds": thresholds
    }

    # 分析結果のサマリーをログ出力
    logger.info(
        f"\n    多段階カバレージ分析結果:"
        f"\n    - Strict  (閾値{thresholds['strict']:.2f}): {multi_threshold_results['strict']['coverage_rate']:.1%}"
        f"\n    - Standard(閾値{thresholds['standard']:.2f}): {multi_threshold_results['standard']['coverage_rate']:.1%}"
        f"\n    - Lenient (閾値{thresholds['lenient']:.2f}): {multi_threshold_results['lenient']['coverage_rate']:.1%}"
        f"\n"
        f"\n    チャンク特性別カバレージ:"
        f"\n    長さ別:"
        f"\n    - Short チャンク: {chunk_characteristics['by_length'].get('short', {}).get('coverage_rate', 0):.1%}"
        f"\n    - Medium チャンク: {chunk_characteristics['by_length'].get('medium', {}).get('coverage_rate', 0):.1%}"
        f"\n    - Long チャンク: {chunk_characteristics['by_length'].get('long', {}).get('coverage_rate', 0):.1%}"
        f"\n"
        f"\n    位置別:"
        f"\n    - Beginning (前半): {chunk_characteristics['by_position'].get('beginning', {}).get('coverage_rate', 0):.1%}"
        f"\n    - Middle (中盤): {chunk_characteristics['by_position'].get('middle', {}).get('coverage_rate', 0):.1%}"
        f"\n    - End (後半): {chunk_characteristics['by_position'].get('end', {}).get('coverage_rate', 0):.1%}"
    )

    # インサイトがある場合は表示
    if chunk_characteristics['summary']['insights']:
        logger.info("\n📊 分析インサイト:")
        for insight in chunk_characteristics['summary']['insights']:
            logger.info(f"  • {insight}")

    return results

