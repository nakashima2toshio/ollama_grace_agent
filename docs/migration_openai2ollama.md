# OpenAI API → Ollama 移植仕様書

**プロジェクト**: `ollama_grace_agent`  
**移植元**: OpenAI API (`openai` SDK ・ Responses API)  
**移植先**: Ollama (ローカル LLM サーバー、OpenAI 互換 API 経由)  
**作成日**: 2026-05-19  
**最終更新**: 2026-05-21  
**参照資料**: `docs/API_migration_gemini2anthropic.md` / `docs/llm_api_comparison_v2.md`

---

## 移植完了サマリー

| 項目 | 内容 |
|---|---|
| 移植対象ファイル | **24 ファイル**（変更不要 6 ファイル含む） |
| Embedding | OpenAI `text-embedding-3-large` (3072次元) → **Ollama `nomic-embed-text` (768次元)** |
| Qdrant 互換性 | 次元数変更 (3072 → 768) → **コレクション再作成必要** |
| API キー | `OPENAI_API_KEY` 必須 → **不要**（ローカル実行） |
| コスト | トークン当たり課金 → **無料**（ローカル GPU/CPU 使用） |

---

## 第1部　OpenAI API vs Ollama 完全対比表

### 1-1. クライアント初期化

| 項目 | OpenAI（移植元） | Ollama（移植先） |
|---|---|---|
| SDK | `openai` | `openai`（同じパッケージを流用） |
| インポート | `from openai import OpenAI` | `from openai import OpenAI` |
| クライアント生成 | `OpenAI(api_key=os.getenv("OPENAI_API_KEY"))` | `OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")` |
| API キー環境変数 | `OPENAI_API_KEY`（必須） | **不要**（`api_key="ollama"` はダミー値） |
| エンドポイント | `https://api.openai.com/v1` | `http://localhost:11434/v1` |
| 追加環境変数 | なし | `OLLAMA_BASE_URL`（リモート起動時に指定） |

```python
# OpenAI
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Ollama
from openai import OpenAI
client = OpenAI(
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    api_key="ollama",
)
```

### 1-2. テキスト生成（シングルターン）

| 項目 | OpenAI Chat Completions | Ollama |
|---|---|---|
| メソッド | `client.chat.completions.create()` | `client.chat.completions.create()` |
| 出力トークン上限 | `max_completion_tokens=...` | **`max_tokens=...`** |
| レスポンス取得 | `response.choices[0].message.content` | `response.choices[0].message.content` |

```python
# Ollama
response = client.chat.completions.create(
    model="gemma4:e4b",
    messages=[
        {"role": "system", "content": "あなたは..."},
        {"role": "user",   "content": prompt}
    ],
    max_tokens=4096,
    temperature=0.7,
)
answer = response.choices[0].message.content
```

> **⚠️ 重要**: Ollama は `max_completion_tokens` / `max_output_tokens` に非対応。必ず **`max_tokens`** を使用すること。

### 1-3. Responses API 既存機能対応表

| OpenAI Responses API | Ollama 代替手段 |
|---|---|
| `client.responses.create(model, input, ...)` | `client.chat.completions.create(model, messages, ...)` |
| `client.responses.parse(text_format=Schema)` | JSON モード + プロンプト内スキーマ + Pydantic parse |
| `response.output_text` | `response.choices[0].message.content` |
| `response.output_parsed` | `Schema.model_validate_json(response.choices[0].message.content)` |
| `response.status == "completed"` | `response.choices[0].finish_reason == "stop"` |
| `EasyInputMessageParam` | `{"role": ..., "content": ...}` dict |
| `previous_response_id` 連鎖 | `messages` リストを自前管理 |

### 1-4. 構造化出力

```python
# Ollama（JSON モード + $ref/$defs 解決 + 手動パース）
import json

def _resolve_schema_refs(schema: dict) -> dict:
    """$ref/$defs を解決してフラットなスキーマを生成（llama3.2 対応）"""
    defs = schema.get("$defs", {})
    def resolve(obj, depth=0):
        if depth > 10:
            return obj
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref_name = obj["$ref"].split("/")[-1]
                return resolve(defs.get(ref_name, obj), depth + 1)
            return {k: resolve(v, depth + 1) for k, v in obj.items() if k not in ("$defs", "title")}
        if isinstance(obj, list):
            return [resolve(item, depth + 1) for item in obj]
        return obj
    return resolve(schema)

# フラットなスキーマを使用してプロンプトを構築
raw_schema  = ExecutionPlan.model_json_schema()
flat_schema = _resolve_schema_refs(raw_schema)
schema_json = json.dumps(flat_schema, ensure_ascii=False, indent=2)

messages = [
    {"role": "system", "content": "あなたはJSONを出力するアシスタントです。JSONのみを出力してください。"},
    {"role": "user",   "content": (
        f"{prompt}\n\n"
        "以下のJSONスキーマに完全に従い、スキーマ定義自体ではなく実際のデータをJSONで出力してください。\n"
        f"スキーマ:\n{schema_json}"
    )},
]
response = client.chat.completions.create(
    model="gemma4:e4b",
    messages=messages,
    max_tokens=4096,
    temperature=0.1,
    response_format={"type": "json_object"},
)
plan = ExecutionPlan.model_validate_json(response.choices[0].message.content)
```

> **⚠️ 重要（llama3.2 固有の問題）**:  
> Pydantic の `model_json_schema()` は `$defs` / `$ref` を含む複雑なスキーマを生成する。  
> llama3.2 等の小型モデルはこれを解釈できず、**スキーマ定義をそのままオウム返し**してしまう。  
> 必ず `_resolve_schema_refs()` でフラット化してから渡すこと。  
> → 実装は `helper/helper_llm.py` の `OllamaClient.generate_structured()` を参照。

### 1-5. JSON 配列出力の注意点

`response_format={"type": "json_object"}` は **JSON オブジェクト（`{}`）のみ**を強制する。  
プロンプトで JSON 配列（`[]`）を要求すると、llama3.2 はオブジェクトでラップして返す。

```python
# ❌ 悪い例：配列を直接要求する
prompt = '出力形式: [{"question": "...", "answer": "..."}]'
# → llama3.2 は {"qa_pairs": [...]} のようなオブジェクトで返す
# → for qa in result: で qa がキー文字列になり
#    qa['topic'] = '...' が 'str' object does not support item assignment エラー

# ✅ 良い例：オブジェクトでラップして要求する
prompt = '出力形式: {"qa_pairs": [{"question": "...", "answer": "...", "topic": "..."}]}'
# → json.loads() 後に result["qa_pairs"] でリストを取り出す
parsed = json.loads(response_text)
if isinstance(parsed, dict):
    qa_pairs = parsed.get("qa_pairs", [])
    if not qa_pairs:
        for v in parsed.values():
            if isinstance(v, list):
                qa_pairs = v
                break
else:
    qa_pairs = parsed  # 後方互換
```

### 1-6. Tool Use（ReAct ループ）

対応モデル: **llama3.2, llama3.1, qwen2.5, mistral-nemo** 等一部に限定。

```python
# ツール定義（OpenAI・Ollama 共通）
tools = [{"type": "function", "function": {"name": "search_rag", "description": "...", "parameters": {...}}}]

# ReAct ループ
messages = [{"role": "user", "content": query}]
while True:
    response = client.chat.completions.create(model="llama3.2", messages=messages, tools=tools, max_tokens=4096)
    msg = response.choices[0].message
    if response.choices[0].finish_reason != "tool_calls" or not msg.tool_calls:
        final_answer = msg.content
        break
    messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})
    for tc in msg.tool_calls:
        result = execute_tool(tc.function.name, json.loads(tc.function.arguments))
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})
```

### 1-7. トークンカウント

```python
# Ollama（tiktoken ローカル計算）
import tiktoken
encoding = tiktoken.get_encoding("cl100k_base")
count = len(encoding.encode(text))
```

### 1-8. Embedding

| 項目 | OpenAI | Ollama |
|---|---|---|
| 推奨モデル | `text-embedding-3-large` | **`nomic-embed-text`** |
| 次元数 | 3072 | **768** |
| `dimensions` パラメータ | 対応 | **非対応** |

```python
# Ollama Embedding
from openai import OpenAI
client = OpenAI(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"), api_key="ollama")
response = client.embeddings.create(model="nomic-embed-text", input=text)
vector = response.data[0].embedding  # 768次元
```

### 1-9. OpenAI 固有機能で Ollama に存在しないもの

| OpenAI 固有機能 | Ollama での代替手段 |
|---|---|
| `client.responses.create()` | `client.chat.completions.create()` |
| `client.responses.parse(text_format=Schema)` | JSON モード + `_resolve_schema_refs()` + `model_validate_json()` |
| `response.output_text` | `response.choices[0].message.content` |
| `max_completion_tokens` | **`max_tokens`** |
| `dimensions` パラメータ (Embedding) | **不要**（モデル固定） |
| `EasyInputMessageParam` | `{"role":..., "content":...}` dict |

### 1-10. モデル名対比

| 用途目安 | OpenAI（移植元） | Ollama（移植先） |
|---|---|---|
| **推奨デフォルト** | `gpt-4o-mini` | **`gemma4:e4b`** |
| 最高性能 | `gpt-4o` | `llama3.1:70b` |
| Embedding | `text-embedding-3-large` (3072次) | `nomic-embed-text` (768次) |
| Tool Use 対応 | 全モデル | `llama3.2`, `qwen2.5:7b`, `mistral-nemo` |

### 1-11. LLM 出力のパース注意点（llama3.2 固有）

llama3.2 は数値だけを要求しても自然言語で返すことがある。`float()` 直接変換ではなく **regex で数値を抽出**すること。

```python
# ❌ 悪い例
score = float(text)  # "答えは 0.8です。" → ValueError

# ✅ 良い例
import re
m = re.search(r"[01]?\.\d+|\b[01]\b", text.strip())
score = float(m.group()) if m else 0.5
```

また、`max_tokens=10` 程度に制限しても効果は薄い。プロンプトで「**数値のみを出力**してください」と明示する。

---

## 第2部　移植コツ・ベストプラクティス

### コツ① OllamaClient 抽象化レイヤーを使う

```python
# 各ファイルの変更がこれだけになる
self.llm = create_llm_client("ollama", default_model=self.model_name)
```

### コツ② `generate_structured()` で JSON パース・スキーマ展開を隠蔽する

`helper/helper_llm.py` の `OllamaClient.generate_structured()` が `_resolve_schema_refs()` を内部適用済み。  
呼び出し側は通常通り Pydantic モデルを渡すだけでよい。

```python
result: ExecutionPlan = llm.generate_structured(
    prompt=prompt,
    response_schema=ExecutionPlan,
    model="gemma4:e4b",
    max_tokens=4096,
    temperature=0.1,
)
```

### コツ③ `max_tokens` に統一する

```python
# OllamaClient.generate_content() 内部で自動変換
max_tokens = (
    kwargs.pop("max_completion_tokens", None)
    or kwargs.pop("max_output_tokens", None)
    or kwargs.pop("max_tokens", 4096)
)
```

### コツ④ `generate_content()` に JSON モードを渡す

`OllamaClient.generate_content()` は `response_format` kwarg をサポートしている。  
JSON 出力が必要な場合は明示的に渡すこと。

```python
text = llm.generate_content(
    prompt=prompt,
    model="gemma4:e4b",
    max_tokens=4096,
    temperature=0.1,
    response_format={"type": "json_object"},
    system="あなたはJSONのみを出力するアシスタントです。",
)
```

### コツ⑤ Qdrant コレクションの再作成を必ず実施する

```bash
ollama pull nomic-embed-text
python a30_qdrant_registration.py --recreate --limit 100
```

### コツ⑥ YAML 設定ファイルも必ず更新する

```yaml
# config/grace_config.yml 変更後
llm:
  provider: "ollama"
  model: "gemma4:e4b"
embedding:
  provider: "ollama"
  model: "nomic-embed-text"
  dimensions: 768
ollama:
  base_url: "http://localhost:11434/v1"
  llm_model: "gemma4:e4b"
  embedding_model: "nomic-embed-text"
  embedding_dims: 768
```

### コツ⑦ Tool Use 対応モデルを確認する

```bash
ollama pull gemma4:e4b       # 推奨デフォルト
ollama pull llama3.1:8b      # 性能・速度バランス
ollama pull qwen2.5:7b       # 日本語対応良好
ollama pull mistral-nemo     # 文書処理向け
```

### コツ⑧ 環境変数を整理する

```bash
# .env 変更後
LLM_PROVIDER=ollama
EMBEDDING_PROVIDER=ollama
QDRANT_URL=http://localhost:6333
# OPENAI_API_KEY は不要になる
```

---

## 第3部　移植対象ファイル一覧

| Phase | ファイル | 変更種別 | 主な変更内容 | 状態 |
|---|---|---|---|---|
| **1** | `helper/helper_llm.py` | クラス追加・修正 | `OllamaClient` 追加、`_resolve_schema_refs()` 追加、`generate_structured()` にフラットスキーマ適用、`generate_content()` に `response_format` kwarg 追加、`DEFAULT_LLM_PROVIDER="ollama"` | ✅ |
| **1** | `helper/helper_embedding.py` | クラス追加 | `OllamaEmbedding` 追加、デフォルト `"ollama"` | ✅ |
| **1** | `grace/config.py` | 設定変更 | `LLMConfig.model="gemma4:e4b"`、`EmbeddingConfig.dims=768`、`OllamaConfig` 追加 | ✅ |
| **1** | `config/grace_config.yml` | 設定変更 | llm/embedding プロバイダー・モデルを更新 | ✅ |
| **1** | `config.py` | 設定変更 | `GeminiConfig.AVAILABLE_MODELS` を Ollama モデル一覧に更新、`DEFAULT_MODEL="gemma4:e4b"`、`LLMProviderConfig.DEFAULT_LLM_PROVIDER="ollama"` | ✅ |
| **2** | `grace/planner.py` | API 置換 | `create_llm_client("openai")` → `("ollama")`、`max_completion_tokens` → `max_tokens` | ✅ |
| **2** | `grace/confidence.py` | API 置換・パース修正 | LLM/Embedding クライアントを Ollama に変更、`float(text)` → regex による数値抽出（2箇所） | ✅ |
| **2** | `grace/tools.py` | API 置換 | `create_llm_client` を Ollama に変更 | ✅ |
| **2** | `grace/executor.py` | API 置換 | `_evaluate_rag_relevance()` の `create_llm_client("openai")` → `("ollama")`、`max_completion_tokens` → `max_tokens` | ✅ |
| **2** | `grace/replan.py` | 間接変更 | 依存先の変更に追従 | ✅ |
| **2** | `grace/schemas.py` | 変更不要 | Pydantic 定義のみ・API 依存なし | ✔️ |
| **3** | `services/agent_service.py` | ループ更新 | `create_llm_client("ollama")`、デフォルトモデル `"gemma4:e4b"` | ✅ |
| **4** | `helper/helper_api.py` | API 分離 | Responses API 型 → Chat Completions 互換型に置換 | ✅ |
| **5** | `chunking/async_api_client.py` | 全面移植 | `_resolve_schema_refs()` 追加、Ollama エンドポイント、JSON モード、`max_tokens` | ✅ |
| **5** | `chunking/csv_text_to_chunks_text_csv.py` | モデル変更 | デフォルトモデル `"llama3.2"`、`OPENAI_API_KEY` チェック削除 | ✅ |
| **6** | `qa_generation/smart_qa_generator.py` | 全面移植 | `OllamaClient` 使用、JSON モード強制、QA ペア出力を `{"qa_pairs": [...]}` オブジェクトに変更、システムプロンプト追加 | ✅ |
| **6** | `qa_generation/semantic.py` | プロバイダー変更 | `"openai"` → `"ollama"`、`nomic-embed-text` (768次元) | ✅ |
| **6** | `qa_generation/pipeline.py` | プロバイダー変更 | `provider="ollama"`、デフォルトモデル `"llama3.2"` | ✅ |
| **7** | Qdrant コレクション | **再作成必須** | 3072次元 → 768次元のため完全に不互換 | ✅ |

**状態凡例**: ✅ 完了 / ⏳ 作業中 / ➡️ 間接変更のみ / ✔️ 変更不要 / ⚠️ 要注意

---

## 第4部　環境変数・設定

### .env ファイル

```bash
LLM_PROVIDER=ollama
EMBEDDING_PROVIDER=ollama
QDRANT_URL=http://localhost:6333
# OLLAMA_BASE_URL=http://localhost:11434/v1  # デフォルト値のため省略可
```

### Ollama モデル一覧

| モデル | VRAM (目安) | Tool Use | 日本語 |
|---|---|---|---|
| `llama3.2` | ~2GB | ✅ | ✅ |
| `llama3.1:8b` | ~5GB | ✅ | ✅ |
| `llama3.1:70b` | ~40GB | ✅ | ✅ |
| `qwen2.5:7b` | ~5GB | ✅ | **★ 優秀** |
| `qwen2.5:14b` | ~9GB | ✅ | **★ 優秀** |
| `mistral-nemo` | ~7GB | ✅ | ⚠️ 限定的 |
| `phi3:mini` | ~2GB | ⚠️ 不安定 | ⚠️ 限定的 |
| `gemma2:9b` | ~6GB | ⚠️ 不安定 | ⚠️ 限定的 |

---

## 第5部　Qdrant コレクション互換性

OpenAI `text-embedding-3-large` (3072次) と Ollama `nomic-embed-text` (768次) は次元数が異なるため、**コレクション再作成が必須**。

```python
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

client = QdrantClient(url="http://localhost:6333")
client.create_collection(
    collection_name="my_collection_ollama",
    vectors_config=VectorParams(size=768, distance=Distance.COSINE)
)
```

---

## 第6部　よくある移植ミスと対策

| ミス | OpenAI | Ollama |
|---|---|---|
| トークン上限パラメータ | `max_completion_tokens` | **`max_tokens`** |
| 構造化出力 | `beta.parse()` / `responses.parse()` | **JSON モード + `_resolve_schema_refs()` + `model_validate_json()`** |
| スキーマの渡し方 | `model_json_schema()` そのまま | **`_resolve_schema_refs()` でフラット化必須**（llama3.2 は `$ref` を解釈できずスキーマをオウム返しする） |
| JSON 配列の要求 | `[{...}]` 形式で直接要求 | **`{"key": [...]}` でラップして要求**（`json_object` モードはオブジェクトのみ） |
| 数値のみ出力要求 | `float(response)` で直接変換 | **regex で数値を抽出**（`"答えは 0.8です。"` 形式で返ることがある） |
| Embedding 次元 | `dimensions=3072` 指定 | **`dimensions` パラメータは非対応** |
| Qdrant 次元 | 3072次元コレクション | **768次元でコレクション再作成必須** |
| API キー | `OPENAI_API_KEY` 必須 | **不要**（`api_key="ollama"`） |
| `response.output_text` | 正常動作 | **属性なし → `choices[0].message.content`** |
| Tool Use 全モデル対応想定 | OK | **対応モデルに限定あり** |
| プロバイダー指定漏れ | `create_llm_client("openai")` | **`create_llm_client("ollama")`** に変更（検索コマンドで漏れを確認） |

---

## 第7部　移植後の動作確認手順

### Step 1: Ollama セットアップ

```bash
ollama serve
ollama pull llama3.2
ollama pull nomic-embed-text
```

### Step 2: Qdrant 起動 + データ再登録

```bash
docker-compose -f docker-compose/docker-compose.yml up -d
python a30_qdrant_registration.py --recreate --limit 100
```

### Step 3: 統合テスト

```bash
# LLM テスト
python -c "
from helper.helper_llm import create_llm_client
llm = create_llm_client('ollama')
print(llm.generate_content('こんにちは'))
"

# 構造化出力テスト（$ref/$defs 解決の確認）
python -c "
from helper.helper_llm import create_llm_client
from pydantic import BaseModel
from typing import List

class TestSchema(BaseModel):
    items: List[str]
    count: int

llm = create_llm_client('ollama')
result = llm.generate_structured('果物を3つ挙げてください', TestSchema)
print(result)
"

# Embedding テスト
python -c "
from helper.helper_embedding import create_embedding_client
emb = create_embedding_client('ollama')
v = emb.embed_text('テスト')
print(f'dims={len(v)}')  # 768 が表示されれば OK
"

# チャンキングテスト
uv run python -m chunking.csv_text_to_chunks_text_csv \
  --input-file data/your_input.csv \
  --model llama3.2

# QA生成テスト
python qa_qdrant/make_qa_register_qdrant.py \
  --input-file chunks_output/your_chunks.csv \
  --collection your_collection \
  --model llama3.2 \
  --recreate

# アプリ起動
streamlit run agent_rag.py --server.port 8501
```

### Step 4: 漏れチェック（openai プロバイダー残存確認）

```bash
# "openai" プロバイダー指定が残っていないか確認（コメント・docs 以外）
grep -rn 'create_llm_client("openai")\|create_embedding_client("openai")' \
  --include="*.py" . | grep -v ".venv" | grep -v "#"
```

---

## 改訂履歴

| 版 | 日付 | 変更内容 |
|---|---|---|
| v1.0 | 2026-05-19 | 初版作成。OpenAI → Ollama 移植仕様書 |
| v1.1 | 2026-05-20 | 第3部の移植状態を最新に更新（confidence.py / tools.py / agent_service.py / helper_api.py 完了） |
| v1.2 | 2026-05-21 | llama3.2 固有の問題と対策を大幅追記。`_resolve_schema_refs()` の必要性、JSON オブジェクトラップ（1-5節）、regex float 抽出（1-11節）を新規追加。`grace/executor.py`・`config.py`・`chunking/`・`qa_generation/` の移植完了を反映。第6部よくあるミスを拡充。コツ④を追加。 |

---

*本ドキュメントは `ollama_grace_agent` 移植作業の仕様書として使用する。*
