# checkpoint_manager.py
"""
チェックポイント管理
- 各ステップ完了時に中間結果を保存
- クラッシュ時に途中から再開可能
"""

import json
import os
import shutil
from datetime import datetime
from typing import List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class CheckpointManager:
    """
    チェックポイント管理クラス
    
    各ステップ完了時に中間結果をJSONとして保存し、
    クラッシュ時に途中から再開できるようにする。
    """

    def __init__(
        self,
        checkpoint_dir: str = "./checkpoints",
        job_id: Optional[str] = None
    ):
        """
        Args:
            checkpoint_dir: チェックポイント保存ディレクトリ
            job_id: ジョブID（省略時は現在時刻から生成）
        """
        self.checkpoint_dir = checkpoint_dir
        self.job_id = job_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.job_dir = os.path.join(checkpoint_dir, self.job_id)
        os.makedirs(self.job_dir, exist_ok=True)
        logger.info(f"Checkpoint directory: {self.job_dir}")

    def save(
        self,
        step_name: str,
        data: List[str],
        metadata: Optional[dict] = None
    ) -> str:
        """
        ステップの結果を保存
        
        Args:
            step_name: ステップ名 (step1, step2, step3)
            data: 保存するデータ（文字列リスト）
            metadata: 追加メタデータ
        
        Returns:
            保存したファイルパス
        """
        checkpoint_data = {
            "step": step_name,
            "timestamp": datetime.now().isoformat(),
            "count": len(data),
            "data": data,
            "metadata": metadata or {}
        }

        filepath = os.path.join(self.job_dir, f"{step_name}.json")
        
        # 一時ファイルに書き込んでからリネーム（原子性確保）
        temp_filepath = filepath + ".tmp"
        try:
            with open(temp_filepath, "w", encoding="utf-8") as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
            os.replace(temp_filepath, filepath)
        except Exception as e:
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
            raise e

        logger.info(f"Checkpoint saved: {filepath} ({len(data)} items)")
        return filepath

    def load(self, step_name: str) -> Optional[List[str]]:
        """
        ステップの結果を読み込み
        
        Args:
            step_name: ステップ名
        
        Returns:
            保存されていたデータ、またはNone
        """
        filepath = os.path.join(self.job_dir, f"{step_name}.json")
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                checkpoint_data = json.load(f)

            logger.info(
                f"Checkpoint loaded: {filepath} "
                f"({checkpoint_data['count']} items, saved at {checkpoint_data['timestamp']})"
            )
            return checkpoint_data["data"]
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None

    def load_with_metadata(self, step_name: str) -> Optional[dict]:
        """
        ステップの結果をメタデータ付きで読み込み
        
        Returns:
            チェックポイントデータ全体、またはNone
        """
        filepath = os.path.join(self.job_dir, f"{step_name}.json")
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None

    def exists(self, step_name: str) -> bool:
        """チェックポイントが存在するか確認"""
        filepath = os.path.join(self.job_dir, f"{step_name}.json")
        return os.path.exists(filepath)

    def get_latest_completed_step(self) -> Optional[str]:
        """
        最後に完了したステップを取得
        
        Returns:
            最後に完了したステップ名、または None
        """
        for step in ["step3", "step2", "step1"]:
            if self.exists(step):
                return step
        return None

    def get_resume_point(self) -> tuple[Optional[str], Optional[List[str]]]:
        """
        再開ポイントを取得
        
        Returns:
            (再開すべきステップ, 前ステップのデータ) のタプル
        """
        latest = self.get_latest_completed_step()
        
        if latest == "step3":
            # 全て完了済み
            return (None, self.load("step3"))
        elif latest == "step2":
            # Step3 から再開
            return ("step3", self.load("step2"))
        elif latest == "step1":
            # Step2 から再開
            return ("step2", self.load("step1"))
        else:
            # 最初から
            return ("step1", None)

    def clear(self):
        """このジョブのチェックポイントを削除"""
        if os.path.exists(self.job_dir):
            shutil.rmtree(self.job_dir)
            logger.info(f"Checkpoints cleared: {self.job_dir}")

    def get_job_info(self) -> dict:
        """ジョブ情報を取得"""
        info = {
            "job_id": self.job_id,
            "job_dir": self.job_dir,
            "steps": {}
        }
        
        for step in ["step1", "step2", "step3"]:
            checkpoint = self.load_with_metadata(step)
            if checkpoint:
                info["steps"][step] = {
                    "timestamp": checkpoint.get("timestamp"),
                    "count": checkpoint.get("count"),
                    "metadata": checkpoint.get("metadata", {})
                }
        
        return info

    @classmethod
    def list_jobs(cls, checkpoint_dir: str = "./checkpoints") -> List[dict]:
        """
        保存されているジョブの一覧を取得
        
        Args:
            checkpoint_dir: チェックポイントディレクトリ
        
        Returns:
            ジョブ情報のリスト
        """
        if not os.path.exists(checkpoint_dir):
            return []
        
        jobs = []
        for job_id in sorted(os.listdir(checkpoint_dir), reverse=True):
            job_dir = os.path.join(checkpoint_dir, job_id)
            if os.path.isdir(job_dir):
                manager = cls(checkpoint_dir=checkpoint_dir, job_id=job_id)
                jobs.append(manager.get_job_info())
        
        return jobs

    @classmethod
    def cleanup_old_jobs(
        cls,
        checkpoint_dir: str = "./checkpoints",
        keep_count: int = 10
    ):
        """
        古いジョブを削除
        
        Args:
            checkpoint_dir: チェックポイントディレクトリ
            keep_count: 保持するジョブ数
        """
        if not os.path.exists(checkpoint_dir):
            return
        
        job_ids = sorted(os.listdir(checkpoint_dir), reverse=True)
        
        for job_id in job_ids[keep_count:]:
            job_dir = os.path.join(checkpoint_dir, job_id)
            if os.path.isdir(job_dir):
                shutil.rmtree(job_dir)
                logger.info(f"Removed old checkpoint: {job_id}")
