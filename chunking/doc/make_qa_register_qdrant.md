# [次の処理] make_qa_register_qdrant.py 完全ガイド

## 📋 目次

1. [概要](#概要)
2. [改修内容](#改修内容)
3. [提供ファイル一覧](#提供ファイル一覧)
4. [対応する入力形式](#対応する入力形式)
5. [CSV入力の詳細](#csv入力の詳細)
6. [使用方法（パターン別）](#使用方法パターン別)
7. [完全なワークフロー](#完全なワークフロー)
8. [コマンドラインオプション](#コマンドラインオプション)
9. [トラブルシューティング](#トラブルシューティング)
10. [ベストプラクティス](#ベストプラクティス)

---

## 📖 概要

`make_qa_register_qdrant.py` は、Q/Aペアの自動生成からQdrantデータベースへの登録までを一貫して行う統合ツールです。

### **主な機能**

- ✅ テキストファイル/CSVファイルからのチャンク作成
- ✅ 事前作成済みチャンクCSVの読み込み
- ✅ Q/Aペアの自動生成
- ✅ Qdrantベクトルデータベースへの登録
- ✅ Celeryによる並列処理対応

---

## 🔧 改修内容

### **改修第一弾: チャンクCSV読み込み機能**


| 項目           | 改修前                           | 改修後                            |
| -------------- | -------------------------------- | --------------------------------- |
| **入力形式**   | データセット or テキストファイル | ✅**チャンクCSVも対応**           |
| **処理フロー** | 1段階（チャンク作成→Q/A生成）   | ✅**2段階可能**（チャンク確認可） |
| **再利用性**   | なし                             | ✅**チャンクの再利用が可能**      |

---

## 📦 提供ファイル一覧


| # | ファイル名                              | 役割             | 主な変更点                   |
| - | --------------------------------------- | ---------------- | ---------------------------- |
| 1 | **csv_to_chunks_text_para_modified.py** | チャンク作成     | CSV/TXT入力対応、CSV出力機能 |
| 2 | **pipeline_modified.py**                | パイプライン制御 | CSV読み込み機能追加          |
| 3 | **make_qa_modified.py**                 | Q/A生成CLI       | `--input-chunks` 引数追加    |
| 4 | **make_qa_register_qdrant_modified.py** | 統合CLI          | `--input-chunks` 引数追加    |

---

## 🎯 対応する入力形式

### **入力ソースの種類**


| 入力形式                 | 拡張子 | 引数             | 説明                                |
| ------------------------ | ------ | ---------------- | ----------------------------------- |
| **事前定義データセット** | -      | `--dataset`      | `config.py`で定義済みのデータセット |
| **テキストファイル**     | `.txt` | `--input-csv`    | プレーンテキスト                    |
| **CSVファイル**          | `.csv` | `--input-csv`    | テキストまたはQ/Aペア               |
| **チャンクCSV**          | `.csv` | `--input-chunks` | ✅**新規対応**                      |

### **入力判定ロジック**

```
┌─────────────────────────────────────────┐
│ 入力ファイルの種類を判定                    │
├─────────────────────────────────────────┤
│ --input-chunks が指定されている場合:        │
│   → チャンクCSVとして読み込み               │
│   → チャンク作成をスキップ                  │
│                                         │
│ --input-csv が指定されている場合:           │
│   → CSVの中身を確認                       │
│   → question/answer カラムがある?         │
│      YES → Q/A生成スキップ → Qdrant登録    │
│      NO  → チャンク作成 → Q/A生成          │
│                                         │
│ --dataset が指定されている場合:            │
│   → データセット読み込み                   │
│   → チャンク作成 → Q/A生成                 │
└─────────────────────────────────────────┘
```

---

## 📊 CSV入力の詳細

### **1. テキストCSVからチャンク作成**

#### **入力CSVの形式例**

##### **形式1: シンプルなテキストCSV**

```csv
text
"第1章 機械学習の基礎について説明します。"
"第2章 深層学習の原理について解説します。"
"第3章 自然言語処理の応用例を紹介します。"
```

##### **形式2: メタデータ付きCSV**

```csv
id,title,Combined_Text,category,date
1,AI入門,"人工知能とは...",tech,2024-01-01
2,ML基礎,"機械学習の基本...",tech,2024-01-02
3,DL応用,"深層学習の応用...",tech,2024-01-03
```

##### **形式3: Wikipedia風CSV**

```csv
title,Combined_Text,url,category
機械学習,"機械学習（きかいがくしゅう、英: machine learning）は...",https://...,AI
深層学習,"深層学習（しんそうがくしゅう、英: deep learning）は...",https://...,AI
```

#### **テキストカラムの自動検出**

以下の優先順位でテキストカラムを自動検出します:

1. `text`, `Text`, `TEXT`
2. `content`, `Content`, `CONTENT`
3. `Combined_Text`, `combined_text`
4. `body`, `Body`, `BODY`
5. `document`, `Document`
6. `answer`, `Answer`

検出できない場合は最初のカラムを使用します。

---

### **2. チャンクCSVの形式**

#### **チャンクCSVの仕様**


| カラム名       | 型     | 必須 | 説明                        |
| -------------- | ------ | ---- | --------------------------- |
| chunk_id       | string | ✅   | チャンク識別子              |
| text           | string | ✅   | チャンクのテキスト          |
| tokens         | int    | ✅   | トークン数                  |
| chunk_idx      | int    | ✅   | チャンクインデックス        |
| dataset_type   | string | ✅   | データセット種別            |
| type           | string | ⚪   | チャンク種別（llm_chunk等） |
| sentence_count | int    | ⚪   | 含まれる文の数              |
| source_file    | string | ⚪   | 元ファイル名                |

#### **チャンクCSVの例**

```csv
chunk_id,text,tokens,chunk_idx,dataset_type,type,sentence_count,source_file
wiki_data_chunk_0,"第1章 概要...",150,0,wiki_data,llm_chunk,5,wiki_data.txt
wiki_data_chunk_1,"機械学習の基礎...",180,1,wiki_data,llm_chunk,6,wiki_data.txt
```

---

## 🚀 使用方法（パターン別）

### **パターン1: 2段階実行（チャンクCSV経由）【推奨】**

#### **Step 1: テキストファイルからチャンクCSV作成**

```bash
# TXT → チャンクCSV
python -m chunking.csv_to_chunks_text_para_modified \
  -i wiki_data.txt \
  -o wiki_chunks.csv \
  -w 8
```

#### **Step 2: チャンクCSVから一括処理（Q/A生成 + Qdrant登録）**

```bash
python make_qa_register_qdrant_modified.py \
  --input-chunks wiki_chunks.csv \
  --collection wiki_qa \
  --use-celery \
  --celery-workers 16 \
  --recreate
```

**メリット:**

- チャンクを事前確認できる
- チャンクを複数の実験で再利用可能
- 処理を段階的にデバッグできる

---

### **パターン2: CSVファイルから直接実行**

#### **Step 1: CSVファイルからチャンクCSV作成**

```bash
# CSV → チャンクCSV
python -m chunking.csv_to_chunks_text_para_modified \
  -i wikipedia.csv \
  -o wiki_chunks.csv \
  --text-column "Combined_Text" \
  --max-rows 1000 \
  -w 8
```

**オプション詳細:**


| オプション       | 説明                           | 例                             |
| ---------------- | ------------------------------ | ------------------------------ |
| `--text-column`  | テキストカラム名を明示的に指定 | `--text-column "article_body"` |
| `--max-rows`     | 処理する最大行数               | `--max-rows 100`               |
| `--combine-rows` | 全行を1つのテキストに結合      | `--combine-rows`               |

#### **Step 2: チャンクCSVから一括処理**

```bash
python make_qa_register_qdrant_modified.py \
  --input-chunks wiki_chunks.csv \
  --collection wikipedia_qa \
  --recreate
```

---

### **パターン3: テキストCSVから直接Q/A生成（チャンク作成を自動実行）**

```bash
# CSV → チャンク作成（自動） → Q/A生成 → Qdrant登録
python make_qa_register_qdrant_modified.py \
  --input-csv news_articles.csv \
  --collection news_qa \
  --use-celery \
  --celery-workers 24 \
  --recreate
```

**処理フロー:**

```
news_articles.csv (text/Combined_Textカラムあり)
  ↓ 内部でチャンク作成
  ↓ Q/A生成
  ↓ Qdrant登録
```

---

### **パターン4: Q/AペアCSVから直接登録（Q/A生成をスキップ）**

```bash
# Q/AペアCSV → Qdrant登録のみ
python make_qa_register_qdrant_modified.py \
  --input-csv qa_pairs.csv \
  --collection my_qa \
  --batch-size 100 \
  --recreate
```

**入力CSVの形式:**

```csv
question,answer
機械学習とは何ですか？,機械学習は人工知能の一分野で...
深層学習の特徴は？,深層学習はニューラルネットワークを...
```

---

### **パターン5: 事前定義データセットから実行（従来の方法）**

```bash
python make_qa_register_qdrant_modified.py \
  --dataset wikipedia_ja \
  --collection wikipedia_qa \
  --use-celery \
  --celery-workers 24 \
  --recreate
```

---

## 🔄 完全なワークフロー

### **ワークフロー1: テキストファイル → Qdrant登録**

```bash
# ===== Phase 1: チャンク作成 =====
python -m chunking.csv_to_chunks_text_para_modified \
  -i input.txt \
  -o chunks.csv \
  -w 8 \
  -v

# チャンク確認（オプション）
head -n 10 chunks.csv
wc -l chunks.csv

# ===== Phase 2: Q/A生成 + Qdrant登録 =====
python make_qa_register_qdrant_modified.py \
  --input-chunks chunks.csv \
  --collection my_qa \
  --use-celery \
  --celery-workers 16 \
  --recreate \
  --batch-size 100

# ===== 確認 =====
# Qdrantに登録されたことを確認
curl http://localhost:6333/collections/my_qa
```

---

### **ワークフロー2: CSVファイル → Qdrant登録**

```bash
# ===== Phase 1: CSVからチャンクCSV作成 =====
python -m chunking.csv_to_chunks_text_para_modified \
  -i wikipedia.csv \
  -o wiki_chunks.csv \
  --text-column "Combined_Text" \
  --max-rows 1000 \
  -w 8 \
  -v

# ===== Phase 2: Q/A生成 + Qdrant登録 =====
python make_qa_register_qdrant_modified.py \
  --input-chunks wiki_chunks.csv \
  --collection wiki_qa \
  --use-celery \
  --celery-workers 24 \
  --recreate
```

---

### **ワークフロー3: 大規模CSVのバッチ処理**

```bash
# ===== バッチごとに処理 =====

# Batch 1: 0-1000行
python -m chunking.csv_to_chunks_text_para_modified \
  -i large_data.csv \
  -o chunks_batch1.csv \
  --text-column "content" \
  --max-rows 1000 \
  -w 8

python make_qa_register_qdrant_modified.py \
  --input-chunks chunks_batch1.csv \
  --collection large_qa \
  --recreate

# Batch 2: 1001-2000行（続き）
# CSVの行スキップ機能は未実装のため、事前に分割が必要
# または、全体を一度に処理してmax-rowsで制御
```

---

## 🎛️ コマンドラインオプション

### **make_qa_register_qdrant_modified.py**

#### **入力ソース（いずれか1つ必須）**

```bash
--dataset DATASET_NAME        # 事前定義データセット
--input-csv CSV_PATH          # テキストCSVまたはQ/AペアCSV
--input-chunks CHUNKS_CSV     # チャンクCSV（✅ 新規）
```

#### **QA生成パラメータ**

```bash
--model MODEL_NAME            # Geminiモデル（デフォルト: gemini-2.0-flash）
--max-docs N                  # 最大処理文書数
--use-celery                  # Celery並列処理を使用
--celery-workers N            # Celeryワーカー数（デフォルト: 8）
--batch-chunks N              # 1回のAPIで処理するチャンク数（1-5）
--merge-chunks                # 小さいチャンクを統合（デフォルト: True）
--overlap-tokens N            # チャンク間の重複トークン数
--use-similarity              # ベクトル類似度分割を使用
--similarity-threshold FLOAT  # 類似度閾値（デフォルト: 0.7）
```

#### **Qdrant登録パラメータ**

```bash
--collection COLLECTION_NAME  # 登録先コレクション名（必須）
--recreate                    # コレクションを再作成
--batch-size N                # Embeddingバッチサイズ（デフォルト: 100）
--provider PROVIDER           # Embeddingプロバイダー（デフォルト: gemini）
```

---

### **csv_to_chunks_text_para_modified.py**

#### **基本オプション**

```bash
-i, --input FILE              # 入力ファイル（.txt または .csv）
-o, --output FILE             # 出力ファイル（.csv または .txt）
-m, --model MODEL             # Geminiモデル
-w, --workers N               # 並列ワーカー数（デフォルト: 8）
-b, --block-size N            # バッチサイズ（デフォルト: 2000）
-v, --verbose                 # 詳細ログ
--resume JOB_ID               # チェックポイントから再開
```

#### **CSV専用オプション**

```bash
--text-column COLUMN          # テキストカラム名（自動検出も可）
--max-rows N                  # 最大処理行数
--combine-rows                # 全行を1つのテキストに結合
```

---

## 📋 実行例集

### **例1: Wikipedia（CSV形式）**

```bash
# チャンク作成
python -m chunking.csv_to_chunks_text_para_modified \
  -i wikipedia_ja.csv \
  -o wiki_chunks.csv \
  --text-column "Combined_Text" \
  -w 8

# Q/A生成 + Qdrant登録
python make_qa_register_qdrant_modified.py \
  --input-chunks wiki_chunks.csv \
  --collection wikipedia_qa \
  --use-celery \
  --celery-workers 24 \
  --recreate
```

---

### **例2: ニュース記事（CSV形式）**

```bash
# チャンク作成（カラム名を明示）
python -m chunking.csv_to_chunks_text_para_modified \
  -i news_articles.csv \
  -o news_chunks.csv \
  --text-column "article_body" \
  --max-rows 500 \
  -w 8

# Q/A生成 + Qdrant登録
python make_qa_register_qdrant_modified.py \
  --input-chunks news_chunks.csv \
  --collection news_qa \
  --batch-chunks 3 \
  --recreate
```

---

### **例3: Q/Aペア直接登録**

```bash
# Q/AペアCSVから直接Qdrant登録（チャンク作成・Q/A生成をスキップ）
python make_qa_register_qdrant_modified.py \
  --input-csv existing_qa_pairs.csv \
  --collection existing_qa \
  --batch-size 100 \
  --recreate
```

---

### **例4: テストラン（小規模データ）**

```bash
# 最初の10行だけでテスト
python -m chunking.csv_to_chunks_text_para_modified \
  -i large_dataset.csv \
  -o test_chunks.csv \
  --text-column "content" \
  --max-rows 10 \
  -w 4 \
  -v

# Q/A生成テスト
python make_qa_register_qdrant_modified.py \
  --input-chunks test_chunks.csv \
  --collection test_qa \
  --recreate
```

---

## ⚠️ トラブルシューティング

### **問題1: テキストカラムが見つからない（CSV入力時）**

**エラーメッセージ:**

```
ValueError: 指定されたカラム 'text' が見つかりません。
利用可能なカラム: ['id', 'title', 'content', 'date']
```

**対処法:**

```bash
# CSVのカラムを確認
head -n 1 data.csv

# 正しいカラム名を指定
python -m chunking.csv_to_chunks_text_para_modified \
  -i data.csv \
  -o chunks.csv \
  --text-column "content"
```

---

### **問題2: チャンクCSVの必須カラム不足**

**エラーメッセージ:**

```
ValueError: 必須カラムが不足しています: ['chunk_id', 'text']
```

**対処法:**

```bash
# チャンクCSVの形式を確認
head -n 1 chunks.csv

# csv_to_chunks_text_para_modified.py で再作成
python -m chunking.csv_to_chunks_text_para_modified \
  -i input.txt \
  -o chunks.csv
```

---

### **問題3: Celeryワーカーが起動していない**

**エラーメッセージ:**

```
RuntimeError: Celery workers are not running
```

**対処法:**

```bash
# Celeryワーカーを起動
./start_celery.sh start -w 16

# ステータス確認
./start_celery.sh status

# または、Celeryなしで実行
python make_qa_register_qdrant_modified.py \
  --input-chunks chunks.csv \
  --collection my_qa \
  --recreate
  # --use-celery を指定しない
```

---

### **問題4: GOOGLE_API_KEYが設定されていない**

**エラーメッセージ:**

```
GOOGLE_API_KEYが設定されていません
```

**対処法:**

```bash
# 環境変数を設定
export GOOGLE_API_KEY="your-api-key-here"

# 確認
echo $GOOGLE_API_KEY
```

---

### **問題5: Qdrant接続エラー**

**エラーメッセージ:**

```
Qdrant接続エラー: Connection refused
```

**対処法:**

```bash
# Qdrantが起動しているか確認
curl http://localhost:6333/collections

# Qdrantを起動（Dockerの場合）
docker run -p 6333:6333 qdrant/qdrant

# または、設定ファイルで接続先を確認
cat qdrant_client_wrapper.py
```

---

### **問題6: メモリ不足**

**エラーメッセージ:**

```
MemoryError: Unable to allocate...
```

**対処法:**

```bash
# 行数を制限して処理
python -m chunking.csv_to_chunks_text_para_modified \
  -i large_data.csv \
  -o chunks.csv \
  --max-rows 1000 \
  -w 4

# または、バッチサイズを小さくする
python make_qa_register_qdrant_modified.py \
  --input-chunks chunks.csv \
  --collection my_qa \
  --batch-size 50 \
  --recreate
```

---

### **問題7: CSV読み込みエラー（エンコーディング）**

**エラーメッセージ:**

```
CSV読み込みエラー: 'utf-8' codec can't decode byte...
```

**対処法:**

```bash
# ファイルのエンコーディングを確認
file -I data.csv

# UTF-8に変換
iconv -f SHIFT-JIS -t UTF-8 data.csv > data_utf8.csv

# 変換後のファイルを使用
python -m chunking.csv_to_chunks_text_para_modified \
  -i data_utf8.csv \
  -o chunks.csv
```

---

## 💡 ベストプラクティス

### **1. 大規模データの処理**

```bash
# Step 1: 小規模テスト
python -m chunking.csv_to_chunks_text_para_modified \
  -i large_data.csv \
  -o test_chunks.csv \
  --max-rows 100 \
  -v

# Step 2: 結果確認
head -n 20 test_chunks.csv

# Step 3: 本番処理
python -m chunking.csv_to_chunks_text_para_modified \
  -i large_data.csv \
  -o chunks.csv \
  -w 16
```

---

### **2. チャンクの品質確認**

```bash
# チャンクCSVを作成
python -m chunking.csv_to_chunks_text_para_modified \
  -i input.txt \
  -o chunks.csv

# 統計確認
python -c "
import pandas as pd
df = pd.read_csv('chunks.csv')
print(f'チャンク数: {len(df)}')
print(f'平均トークン数: {df[\"tokens\"].mean():.1f}')
print(f'最大トークン数: {df[\"tokens\"].max()}')
print(f'最小トークン数: {df[\"tokens\"].min()}')
"

# 内容確認
head -n 10 chunks.csv | column -t -s,
```

---

### **3. 段階的なパイプライン実行**

```bash
# Phase 1: チャンク作成
python -m chunking.csv_to_chunks_text_para_modified \
  -i input.csv \
  -o chunks.csv \
  --text-column "Combined_Text"

# Phase 2: Q/A生成のみ（Qdrant登録なし）
python make_qa_modified.py \
  --input-chunks chunks.csv \
  --analyze-coverage

# Phase 3: 結果確認後、Qdrant登録
python make_qa_register_qdrant_modified.py \
  --input-chunks chunks.csv \
  --collection my_qa \
  --recreate
```

---

### **4. ログの活用**

```bash
# 詳細ログを記録
python -m chunking.csv_to_chunks_text_para_modified \
  -i input.csv \
  -o chunks.csv \
  -v 2>&1 | tee chunking.log

python make_qa_register_qdrant_modified.py \
  --input-chunks chunks.csv \
  --collection my_qa \
  --recreate 2>&1 | tee qa_registration.log

# ログを分析
grep "ERROR" *.log
grep "WARNING" *.log
```

---

### **5. チェックポイントからの再開**

```bash
# 処理中に中断された場合
python -m chunking.csv_to_chunks_text_para_modified \
  --resume JOB_ID_20250111_123456 \
  -i input.txt \
  -o chunks.csv

# ジョブ一覧確認
ls -la checkpoints/
```

---

## 📈 パフォーマンス指標

### **チャンク作成の処理時間**


| データサイズ | 行数    | ワーカー数 | 処理時間 | 出力チャンク数 |
| ------------ | ------- | ---------- | -------- | -------------- |
| 1MB          | 1,000   | 8          | ~5分     | ~300           |
| 10MB         | 10,000  | 8          | ~30分    | ~3,000         |
| 100MB        | 100,000 | 16         | ~3時間   | ~30,000        |

### **Q/A生成の処理時間**


| チャンク数 | Celeryワーカー数 | 処理時間 | 生成Q/Aペア数 |
| ---------- | ---------------- | -------- | ------------- |
| 100        | 8                | ~10分    | ~300          |
| 1,000      | 16               | ~1時間   | ~3,000        |
| 10,000     | 24               | ~8時間   | ~30,000       |

---

## 🎓 Tips & Tricks

### **Tip 1: CSV形式の選択**

```bash
# テキストCSV → チャンクCSV → Q/AペアCSV → Qdrant
# メリット: 各段階で確認・修正が可能

# Q/AペアCSV → Qdrant（直接）
# メリット: 高速、既存Q/Aペアの登録に最適
```

---

### **Tip 2: 並列度の最適化**

```bash
# CPUコア数を確認
nproc

# 推奨: コア数の50-100%
# 例: 16コアの場合
python -m chunking.csv_to_chunks_text_para_modified \
  -i input.csv \
  -o chunks.csv \
  -w 12  # 16コア × 75%
```

---

### **Tip 3: バッチサイズの調整**

```bash
# メモリが潤沢な場合
--batch-size 200

# メモリが限られている場合
--batch-size 50

# デフォルト（推奨）
--batch-size 100
```

---

## 📞 サポート

### **問題が発生した場合**

1. **詳細ログを確認**

   ```bash
   -v オプションで実行
   ```
2. **チェックポイントログを確認**

   ```bash
   ls -la checkpoints/
   cat checkpoints/*/step*.json
   ```
3. **CSVファイルの形式を確認**

   ```bash
   head -n 5 input.csv
   ```
4. **Githubでissueを作成** または **開発者に連絡**

---

## 🔄 次のステップ（改修第二弾候補）

- [ ]  チャンク統合機能の追加
- [ ]  オーバーラップ機能のLLMチャンク対応
- [ ]  チャンク品質評価機能
- [ ]  バッチ処理の自動化スクリプト
- [ ]  UIベースのチャンク確認ツール
- [ ]  CSVの行スキップ機能（大規模データの分割処理用）

---

## 📝 バージョン履歴


| バージョン | 日付       | 変更内容                    |
| ---------- | ---------- | --------------------------- |
| 1.0.0      | 2025-01-11 | 初版リリース                |
| 1.1.0      | 2025-01-11 | チャンクCSV読み込み機能追加 |
| 1.2.0      | 2025-01-11 | CSV入力対応機能追加         |

---

## 📄 関連ドキュメント

- `README_改修版.md` - 改修内容の詳細
- `CSV入力対応ガイド.md` - CSV入力の詳細仕様
- `config.py` - データセット設定
- `chunking/SKILL.md` - チャンク処理の技術詳細

---

**作成日**: 2025-01-11
**最終更新**: 2025-01-11
