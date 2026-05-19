#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
celery_config.py - Celery設定ファイル（修正版 v2.5）

修正内容（v2.5）:
- ★重要★ デフォルトキュー 'celery' を task_queues に追加
- キュー設定の不整合を解消
- ワーカーがすべてのタスクを受信できるように修正
"""

import os
import sys
from pathlib import Path
from kombu import Exchange, Queue
from celery import Celery
from celery.signals import worker_process_init
from dotenv import load_dotenv
import logging

# ================================================================
# ロギング設定（早期初期化）
# ================================================================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s'
)
logger = logging.getLogger(__name__)

# ================================================================
# 重要: プロジェクトルートをsys.pathに追加
# ================================================================
project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
    logger.info(f"✅ プロジェクトルートをsys.pathに追加: {project_root}")

# helper/ディレクトリもsys.pathに追加（LLMClientのインポート用）
helper_path = project_root / 'helper'
if helper_path.exists() and str(helper_path) not in sys.path:
    sys.path.insert(0, str(helper_path))
    logger.info(f"✅ helperディレクトリをsys.pathに追加: {helper_path}")

# 環境変数読み込み
load_dotenv()

# Celeryアプリケーション初期化
app = Celery('qa_generation')

# Redis設定
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')


# ================================================================
# ワーカープロセス初期化シグナル（重要）
# ================================================================
@worker_process_init.connect
def configure_worker_process(**kwargs):
    """
    各ワーカープロセスの初期化時に実行される
    これにより、フォークされた子プロセスでもsys.pathが正しく設定される
    """
    logger.info("=" * 60)
    logger.info("🔧 ワーカープロセス初期化")
    logger.info("=" * 60)

    # プロジェクトルートを再設定
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
        logger.info(f"✅ [Worker] プロジェクトルート追加: {project_root}")

    # helper/ディレクトリを再設定
    if helper_path.exists() and str(helper_path) not in sys.path:
        sys.path.insert(0, str(helper_path))
        logger.info(f"✅ [Worker] helperディレクトリ追加: {helper_path}")

    # sys.path確認
    logger.info(f"📁 [Worker] sys.path[0]: {sys.path[0]}")
    logger.info(f"📁 [Worker] sys.path[1]: {sys.path[1] if len(sys.path) > 1 else 'N/A'}")

    # 重要なディレクトリの存在確認
    qa_gen_dir = project_root / 'qa_generation'
    helper_dir = project_root / 'helper'

    logger.info(f"📂 [Worker] qa_generation/: {qa_gen_dir.exists()}")
    logger.info(f"📂 [Worker] helper/: {helper_dir.exists()}")

    if qa_gen_dir.exists():
        gen_file = qa_gen_dir / 'generation.py'
        logger.info(f"📄 [Worker] generation.py: {gen_file.exists()}")

    # インポートテスト
    try:
        from qa_generation.generation import generate_qa_dataset
        logger.info("✅ [Worker] インポート成功: qa_generation.generation")
    except ImportError as e:
        logger.error(f"❌ [Worker] インポート失敗: {e}")
        logger.error(f"❌ [Worker] sys.path: {sys.path}")

    logger.info("=" * 60)


# Celery設定クラス
class CeleryConfig:
    # ブローカー設定（Redis）
    broker_url = REDIS_URL
    result_backend = REDIS_URL

    # タスク設定
    task_serializer = 'json'
    accept_content = ['json']
    result_serializer = 'json'
    timezone = 'Asia/Tokyo'
    enable_utc = True

    # ワーカー設定
    worker_prefetch_multiplier = 1  # スマート生成用：各ワーカーが一度に1タスク取得
    worker_max_tasks_per_child = 50  # メモリリーク対策（スマート生成は50推奨）
    worker_disable_rate_limits = False

    # タスク実行設定（✨ スマート生成対応）
    task_acks_late = True  # タスク完了後にACK
    task_reject_on_worker_lost = True

    # ✨ スマート生成用タイムアウト（2回のLLM呼び出し考慮）
    task_time_limit = 600  # タスクタイムアウト（10分）
    task_soft_time_limit = 540  # ソフトタイムアウト（9分）

    # ================================================================
    # ★★★ 修正ポイント: デフォルトキューを設定 ★★★
    # ================================================================
    # task_default_queue を明示的に設定
    task_default_queue = 'celery'
    task_default_exchange = 'celery'
    task_default_routing_key = 'celery'

    # レート制限
    task_annotations = {
        # [MIGRATION anthropic→openai] OpenAI API用
        # gpt-4o-mini: rpm=500, tpm=200000
        'generate_qa_for_chunk': {
            'rate_limit': '60/m',  # 分あたり60リクエスト
        },
        # OpenAI API用（既存）
        'tasks.process_chunk_task': {
            'rate_limit': '50/m',  # 分あたり50リクエスト
        },
        'tasks.process_batch_task': {
            'rate_limit': '10/m',  # 分あたり10バッチ
        }
    }

    # ================================================================
    # ★★★ 修正ポイント: デフォルトキュー 'celery' を追加 ★★★
    # ================================================================
    task_queues = (
        # ★ デフォルトキュー（これがないとタスクが処理されない）
        Queue('celery', Exchange('celery'), routing_key='celery'),
        # 優先度付きキュー（オプション）
        Queue('high_priority', Exchange('high_priority'), routing_key='high'),
        Queue('normal_priority', Exchange('normal_priority'), routing_key='normal'),
        Queue('low_priority', Exchange('low_priority'), routing_key='low'),
    )

    # リトライ設定
    task_autoretry_for = (Exception,)
    task_retry_kwargs = {
        'max_retries': 3,
        'countdown': 60,  # 60秒後にリトライ
        'retry_jitter': True,  # ジッター追加
    }

    # 結果の有効期限
    result_expires = 3600  # 1時間

    # Celery Beat設定（定期タスク用）
    beat_schedule = {
        'cleanup-old-results': {
            'task': 'tasks.cleanup_old_results',
            'schedule': 3600.0,  # 1時間ごと
        },
    }


# 設定を適用
app.config_from_object(CeleryConfig())

# タスクの自動検出（重要）
app.autodiscover_tasks(['celery_tasks'])

# タスクを明示的にインポート（確実にタスクを登録するため）
try:
    import celery_tasks  # noqa: F401, E402
    logger.info("✅ celery_tasks.pyのインポート成功")
except ImportError as e:
    logger.warning(f"⚠️ celery_tasks.pyが見つかりません: {e}")

# ================================================================
# Gemini API設定
# ================================================================

GEMINI_CONFIG = {
    'api_key': os.getenv('GOOGLE_API_KEY'),
    'models': {
        'gemini-2.0-flash': {
            'rpm_limit': 1500,
            'tpm_limit': 1000000,
            'max_retries': 3,
            'retry_delay': 60
        },
        'gemini-1.5-pro': {
            'rpm_limit': 360,
            'tpm_limit': 120000,
            'max_retries': 3,
            'retry_delay': 120
        },
        'gemini-1.5-flash': {
            'rpm_limit': 1500,
            'tpm_limit': 1000000,
            'max_retries': 3,
            'retry_delay': 60
        }
    }
}

# ================================================================
# [MIGRATION 新規追加] Anthropic API設定
# migration資料 ⑧ に従い ANTHROPIC_CONFIG を追加
# GEMINI_CONFIG はそのまま残す（後方互換・gemini_grace_agent 用）
# ================================================================

ANTHROPIC_CONFIG = {
    'api_key': os.getenv('ANTHROPIC_API_KEY'),
    'models': {
        'claude-opus-4-7': {
            'rpm_limit': 50,
            'tpm_limit': 200000,
            'max_retries': 3,
            'retry_delay': 120
        },
        'claude-opus-4-6': {
            'rpm_limit': 50,
            'tpm_limit': 200000,
            'max_retries': 3,
            'retry_delay': 120
        },
        'claude-sonnet-4-6': {          # デフォルト推奨
            'rpm_limit': 2000,
            'tpm_limit': 1600000,
            'max_retries': 3,
            'retry_delay': 60
        },
        'claude-sonnet-4-5': {          # 前世代（後方互換）
            'rpm_limit': 2000,
            'tpm_limit': 1600000,
            'max_retries': 3,
            'retry_delay': 60
        },
        'claude-haiku-4-5-20251001': {
            'rpm_limit': 4000,
            'tpm_limit': 2000000,
            'max_retries': 3,
            'retry_delay': 30
        },
    }
}

# ================================================================
# OpenAI API設定（既存）
# ================================================================

OPENAI_CONFIG = {
    'api_key': os.getenv('OPENAI_API_KEY'),
    'models': {
        'gpt-5-mini': {
            'rpm_limit': 3500,
            'tpm_limit': 200000,
            'max_retries': 3,
            'retry_delay': 60
        },
        'gpt-4': {
            'rpm_limit': 500,
            'tpm_limit': 40000,
            'max_retries': 3,
            'retry_delay': 120
        },
        'gpt-4o': {
            'rpm_limit': 500,
            'tpm_limit': 30000,
            'max_retries': 3,
            'retry_delay': 120
        },
        'gpt-4o-mini': {
            'rpm_limit': 500,
            'tpm_limit': 200000,
            'max_retries': 3,
            'retry_delay': 60
        }
    }
}

# ================================================================
# スマート生成設定
# ================================================================

SMART_GENERATION_CONFIG = {
    'timeout_multiplier': 2.0,
    'max_retries': 3,
    'retry_delay': 60,
    'batch_size': 1,
    'default_mode': 'smart',
}

# ================================================================
# ログ設定
# ================================================================

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': 'logs/celery_qa_generation.log',
            'formatter': 'default',
        },
    },
    'loggers': {
        'celery': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
        },
        'tasks': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
        },
        'celery_tasks': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
        },
    },
}

# ================================================================
# 環境別設定
# ================================================================

ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

if ENVIRONMENT == 'production':
    CeleryConfig.worker_max_tasks_per_child = 100
    CeleryConfig.task_time_limit = 1200
    logger.info("🚀 本番環境設定を適用")
elif ENVIRONMENT == 'staging':
    CeleryConfig.worker_max_tasks_per_child = 75
    CeleryConfig.task_time_limit = 900
    logger.info("🧪 ステージング環境設定を適用")
else:
    logger.info("💻 開発環境設定を適用")

# ================================================================
# エクスポート
# ================================================================

__all__ = [
    'app',
    'CeleryConfig',
    'OPENAI_CONFIG',           # [MIGRATION anthropic→openai] メインプロバイダー
    'ANTHROPIC_CONFIG',        # 後方互換のため残存
    'GEMINI_CONFIG',           # 後方互換のため残存
    'SMART_GENERATION_CONFIG',
    'LOGGING_CONFIG'
]

# ================================================================
# 設定確認用
# ================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Celery Configuration - 修正版 v2.5")
    print("=" * 60)

    print("\n[プロジェクトルート]")
    print(f"Project Root: {project_root}")
    print(f"sys.path[0]: {sys.path[0]}")

    print("\n[Celery設定]")
    print(f"Broker URL: {CeleryConfig.broker_url}")
    print(f"Result Backend: {CeleryConfig.result_backend}")
    print(f"Task Time Limit: {CeleryConfig.task_time_limit}s")
    print(f"Worker Max Tasks: {CeleryConfig.worker_max_tasks_per_child}")
    print(f"Prefetch Multiplier: {CeleryConfig.worker_prefetch_multiplier}")

    # ★ キュー設定の確認
    print("\n[キュー設定]")
    print(f"デフォルトキュー: {CeleryConfig.task_default_queue}")
    print("定義済みキュー:")
    for q in CeleryConfig.task_queues:
        print(f"  - {q.name}")

    print("\n[OpenAI Configuration]")  # [MIGRATION anthropic→openai] メインプロバイダー
    if OPENAI_CONFIG['api_key']:
        print("✅ OPENAI_API_KEY設定済み")
    else:
        print("❌ OPENAI_API_KEY未設定")

    for model, config in OPENAI_CONFIG['models'].items():
        print(f"  {model}: RPM={config['rpm_limit']}, TPM={config['tpm_limit']}")

    print("\n[Anthropic Configuration]（後方互換用）")
    if ANTHROPIC_CONFIG['api_key']:
        print("✅ ANTHROPIC_API_KEY設定済み")
    else:
        print("⚠️ ANTHROPIC_API_KEY未設定（openai_grace_agent では不要）")

    for model, config in ANTHROPIC_CONFIG['models'].items():
        print(f"  {model}: RPM={config['rpm_limit']}, TPM={config['tpm_limit']}")

    print("\n[Gemini Configuration]（後方互換用）")
    if GEMINI_CONFIG['api_key']:
        print("✅ GOOGLE_API_KEY設定済み")
    else:
        print("⚠️ GOOGLE_API_KEY未設定（openai_grace_agent では不要）")

    for model, config in GEMINI_CONFIG['models'].items():
        print(f"  {model}: RPM={config['rpm_limit']}, TPM={config['tpm_limit']}")

    print("\n[スマート生成設定]")
    print(f"デフォルトモード: {SMART_GENERATION_CONFIG['default_mode']}")
    print(f"タイムアウト倍率: {SMART_GENERATION_CONFIG['timeout_multiplier']}x")
    print(f"最大リトライ: {SMART_GENERATION_CONFIG['max_retries']}回")

    # インポートテスト
    print("\n[インポートテスト]")
    try:
        from qa_generation.generation import generate_qa_dataset
        print("✅ qa_generation.generation.generate_qa_dataset")
    except ImportError as e:
        print(f"❌ qa_generation.generation: {e}")

    print("\n" + "=" * 60)
