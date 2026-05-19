# Celery + スマート生成 クイックスタートガイド

**最終更新**: 2025-01-20
**バージョン**: v2.1

---

## 📋 目次

1. [前提条件](#前提条件)
2. [セットアップ](#セットアップ)
3. [基本的な使い方](#基本的な使い方)
4. [テスト方法](#テスト方法)
5. [トラブルシューティング](#トラブルシューティング)

---

## 🔧 前提条件

### 必要なソフトウェア

```bash
# Python 3.9+
python --version

# Redis（Celeryのブローカー）
redis-server --version

# Celery
pip install celery redis
```

### 必要なファイル

- ✅ `celery_tasks.py` - Celeryタスク定義（スマート生成対応）
- ✅ `celery_config.py` - Celery設定
- ✅ `start_celery.sh` - ワーカー起動スクリプト
- ✅ `test_celery_integration.py` - 統合テスト

---

## 🚀 セットアップ

### ステップ1: Redisの起動

```bash
# macOS（Homebrew）
brew services start redis

# Linux（systemd）
sudo systemctl start redis

# 起動確認
redis-cli ping
# 出力: PONG
```

### ステップ2: ファイルの配置

```bash
# プロジェクトルートに配置
cp celery_tasks.py /path/to/project/
cp celery_config.py /path/to/project/
cp start_celery.sh /path/to/project/
cp test_celery_integration.py /path/to/project/

# 実行権限の付与
chmod +x start_celery.sh
chmod +x test_celery_integration.py
```

### ステップ3: Celeryワーカーの起動

```bash
# スクリプトを使用（推奨）
./start_celery.sh start -w 8

# または、直接起動
celery -A celery_config worker --loglevel=info --concurrency=8

# 起動確認
./start_celery.sh status
```

**期待される出力**:
```
============================================================
=== Celeryワーカー ステータス ===
============================================================
Redis: ✓ 起動中
キュー長: 0
ワーカー: ✓ 起動中
```

---

## 💻 基本的な使い方

### パターン1: スマート生成（デフォルト）

```bash
python make_qa_register_qdrant.py \
  --input-file document.txt \
  --collection my_docs \
  --use-celery \
  --celery-workers 8 \
  --recreate
```

**期待される動作**:
- ✅ 8個のワーカーで並列処理
- ✅ LLMがチャンク分析（2回/チャンク）
- ✅ 動的Q/A数決定（0-5個）
- ✅ トピック付きQ/A生成

**実行ログ例**:
```
==============================================================
🆕 Q/A生成モード: スマート生成（デフォルト）
==============================================================

[3/4] Q/Aペア生成...
  生成モード: スマート生成
Celeryタスクを投入: 12チャンク
タスク投入完了: 12個
結果収集中: 12タスク, timeout=600秒
タスク 1/12: 成功（Q/A数=5）
タスク 2/12: 成功（Q/A数=3）
...
収集完了:
  - 成功: 12/12
  - 失敗: 0/12
  - Q/A総数: 42
```

### パターン2: 従来方式

```bash
python make_qa_register_qdrant.py \
  --input-file large_data.csv \
  --collection large_docs \
  --use-celery \
  --celery-workers 16 \
  --no-smart-generation \
  --recreate
```

**期待される動作**:
- ✅ 16個のワーカーで並列処理
- ✅ トークン数ベースで固定Q/A数（2-8個）
- ✅ 高速処理（約半分の時間）

---

## 🧪 テスト方法

### テスト1: 統合テストの実行

```bash
python test_celery_integration.py
```

**期待される出力**:
```
==============================================================
Celeryスマート生成統合テスト
==============================================================

テスト1: Celeryワーカー状態確認
✅ 合格: ワーカーが起動しています

テスト2: スマート生成（単一チャンク）
✅ 合格: 5個のQ/Aペア生成（8.2秒）

テスト3: 従来方式（単一チャンク）
✅ 合格: 3個のQ/Aペア生成（4.1秒）

テスト4: 複数チャンク並列処理（スマート生成）
✅ 合格: 9個のQ/Aペア生成（12.5秒）

テスト5: エラーハンドリング
✅ 合格: エラーハンドリングが正常に動作

==============================================================
テスト結果サマリー
==============================================================
✅ 合格: ワーカー状態確認
✅ 合格: スマート生成（単一）
✅ 合格: 従来方式（単一）
✅ 合格: 並列処理（複数）
✅ 合格: エラーハンドリング

合計: 5/5 テスト合格
🎉 全てのテストに合格しました！
```

### テスト2: 手動テスト

```python
# Python REPLで実行
from celery_tasks import submit_unified_qa_generation, collect_results

# テストチャンク
chunk = {
    'id': 'test_0',
    'text': 'テスト用のテキストです。',
    'tokens': 20,
    'doc_id': 'test_doc',
    'chunk_idx': 0
}

config = {'type': 'test', 'qa_per_chunk': 3}

# タスク投入（スマート生成）
tasks = submit_unified_qa_generation(
    chunks=[chunk],
    config=config,
    model="gemini-2.0-flash",
    use_smart_generation=True
)

# 結果収集
qa_pairs = collect_results(tasks, timeout=60)
print(f"生成されたQ/A数: {len(qa_pairs)}")
```

---

## 🔍 トラブルシューティング

### 問題1: Redisに接続できない

**症状**:
```
❌ Redisサーバーが起動していません
```

**解決策**:
```bash
# Redisを起動
brew services start redis  # macOS
sudo systemctl start redis  # Linux

# 接続確認
redis-cli ping
```

### 問題2: Celeryワーカーが応答しない

**症状**:
```
❌ Celeryワーカーが応答しません
```

**解決策**:
```bash
# ワーカーを再起動
./start_celery.sh restart -w 8

# ログを確認
tail -f logs/celery_qa_*.log

# 手動起動でエラーを確認
celery -A celery_config worker --loglevel=debug
```

### 問題3: タスクがタイムアウトする

**症状**:
```
タスク 1/10: タイムアウト（600秒）
```

**解決策**:

#### 方法1: タイムアウト設定を増やす

```python
# celery_config.py
task_time_limit = 1200  # 10分 → 20分に増やす
```

#### 方法2: ワーカー数を増やす

```bash
./start_celery.sh restart -w 16  # 8 → 16に増やす
```

#### 方法3: 従来方式に切り替え

```bash
python make_qa_register_qdrant.py \
  --input-file doc.txt \
  --collection docs \
  --use-celery \
  --no-smart-generation \  # 従来方式
  --recreate
```

### 問題4: メモリ不足

**症状**:
```
MemoryError or worker killed
```

**解決策**:

#### 方法1: ワーカーを定期的に再起動

```python
# celery_config.py
worker_max_tasks_per_child = 25  # 50 → 25に減らす
```

#### 方法2: ワーカー数を減らす

```bash
./start_celery.sh restart -w 4  # 8 → 4に減らす
```

### 問題5: 結果が空

**症状**:
```
収集完了:
  - 成功: 10/10
  - Q/A総数: 0  ← 空
```

**原因と解決策**:

#### 原因1: スマート生成が0個判定している

```bash
# ログを確認
tail -f logs/celery_qa_*.log

# 期待されるログ:
# Q/A生成スキップ（qa_count=0）

# 解決策: 従来方式に切り替え
--no-smart-generation
```

#### 原因2: LLM APIエラー

```bash
# ログでエラーを確認
grep "ERROR" logs/celery_qa_*.log

# 解決策: APIキーを確認
echo $GOOGLE_API_KEY
```

---

## 📊 パフォーマンス比較

### テスト条件

- データ: 100チャンク
- 環境: ローカル（macOS）
- Redis: localhost

### 結果（予測）

| 設定 | 処理時間 | Q/A総数 | 平均Q/A/チャンク |
|------|---------|---------|-----------------|
| スマート生成 + 8ワーカー | 15-20分 | 250-300個 | 2.5-3.0個 |
| スマート生成 + 16ワーカー | 8-12分 | 250-300個 | 2.5-3.0個 |
| 従来方式 + 8ワーカー | 8-10分 | 300-400個 | 3.0-4.0個 |
| 従来方式 + 16ワーカー | 4-6分 | 300-400個 | 3.0-4.0個 |

---

## 🎯 推奨設定

### 小規模データ（< 100チャンク）

```bash
# スマート生成 + 同期処理
python make_qa_register_qdrant.py \
  --input-file doc.txt \
  --collection docs \
  --recreate
  # --use-celeryを指定しない（同期処理）
```

### 中規模データ（100-1,000チャンク）

```bash
# スマート生成 + Celery
./start_celery.sh start -w 8
python make_qa_register_qdrant.py \
  --input-file doc.txt \
  --collection docs \
  --use-celery \
  --celery-workers 8 \
  --recreate
```

### 大規模データ（10,000+チャンク）

```bash
# 従来方式 + Celery（大量ワーカー）
./start_celery.sh start -w 24
python make_qa_register_qdrant.py \
  --input-file large_data.csv \
  --collection large_docs \
  --use-celery \
  --celery-workers 24 \
  --no-smart-generation \
  --recreate
```

---

## 📚 関連ドキュメント

- `celery_verification_report.md` - Celery対応検証レポート
- `celery_tasks.py` - Celeryタスク実装
- `celery_config.py` - Celery設定
- `make_qa_register_qdrant.md` - 統合ツール完全ガイド

---

## 🔄 ワーカー管理

### 起動

```bash
./start_celery.sh start -w 8
```

### 停止

```bash
./start_celery.sh stop
```

### 再起動

```bash
./start_celery.sh restart -w 8
```

### ステータス確認

```bash
./start_celery.sh status
```

### ワーカー数の変更

```bash
# 8ワーカー
./start_celery.sh restart -w 8

# 16ワーカー
./start_celery.sh restart -w 16

# 最大24ワーカー
./start_celery.sh restart -w 24
```

---

## 💡 ヒント

### ヒント1: ログの監視

```bash
# リアルタイムでログを表示
tail -f logs/celery_qa_*.log
```

### ヒント2: Flowerでモニタリング

```bash
# Flowerのインストール
pip install flower

# Flowerの起動
celery -A celery_config flower

# ブラウザで http://localhost:5555 にアクセス
```

### ヒント3: キューのクリア

```bash
# Pythonで実行
python -c "from celery_tasks import purge_queue; purge_queue()"
```

---

**作成日**: 2025-01-20
**作成者**: AI Assistant
