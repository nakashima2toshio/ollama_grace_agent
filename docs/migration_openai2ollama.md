# OpenAI API → Ollama 移植仕様書

**プロジェクト**: `ollama_grace_agent`  
**移植元**: OpenAI API (`openai` SDK ・ Responses API)  
**移植先**: Ollama (ローカル LLM サーバー、OpenAI 互換 API 経由)  
**作成日**: 2026-05-19  
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
    model="llama3.2",
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
# Ollama（JSON モード + プロンプト埋込 + 手動パース）
import json
schema_json = json.dumps(ExecutionPlan.model_json_schema(), ensure_ascii=False, indent=2)
messages = [
    {"role": "system", "content": "Output valid JSON only."},
    {"role": "user",   "content": f"{prompt}\n\nJSON Schema:\n{schema_json}"},
]
response = client.chat.completions.create(
    model="llama3.2",
    messages=messages,
    max_tokens=4096,
    temperature=0.1,
    response_format={"type": "json_object"},
)
plan = ExecutionPlan.model_validate_json(response.choices[0].message.content)
```

### 1-5. Tool Use（ReAct ループ）

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

### 1-6. トークンカウント

```python
# Ollama（tiktoken ローカル計算）
import tiktoken
encoding = tiktoken.get_encoding("cl100k_base")
count = len(encoding.encode(text))
```

### 1-7. Embedding

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

### 1-8. OpenAI 固有機能で Ollama に存在しないもの

| OpenAI 固有機能 | Ollama での代替手段 |
|---|---|
| `client.responses.create()` | `client.chat.completions.create()` |
| `client.responses.parse(text_format=Schema)` | JSON モード + `model_validate_json()` |
| `response.output_text` | `response.choices[0].message.content` |
| `max_completion_tokens` | **`max_tokens`** |
| `dimensions` パラメータ (Embedding) | **不要**（モデル固定） |
| `EasyInputMessageParam` | `{"role":..., "content":...}` dict |

### 1-9. モデル名対比

| 用途目安 | OpenAI（移植元） | Ollama（移植先） |
|---|---|---|
| **推奨デフォルト** | `gpt-4o-mini` | **`llama3.2`** |
| 最高性能 | `gpt-4o` | `llama3.1:70b` |
| Embedding | `text-embedding-3-large` (3072次) | `nomic-embed-text` (768次) |
| Tool Use 対応 | 全モデル | `llama3.2`, `qwen2.5:7b`, `mistral-nemo` |

---

## 第2部　移植コツ・ベストプラクティス

### コツ① OllamaClient 抽象化レイヤーを作る

```python
# 各ファイルの変更がこれだけになる
self.llm = create_llm_client("ollama", default_model=self.model_name)
```

### コツ② `generate_structured()` で JSON パースを隠蔽する

```python
def generate_structured(self, prompt, response_schema, **kwargs):
    schema_json = json.dumps(response_schema.model_json_schema(), ensure_ascii=False, indent=2)
    messages = [
        {"role": "system", "content": "Output valid JSON only."},
        {"role": "user",   "content": f"{prompt}\n\nJSON Schema:\n{schema_json}"},
    ]
    response = self.client.chat.completions.create(
        model=self.default_model, messages=messages,
        response_format={"type": "json_object"}, max_tokens=8192, temperature=0.1,
    )
    return response_schema.model_validate_json(response.choices[0].message.content)
```

### コツ③ `max_tokens` に統一する

```python
# OllamaClient.generate_content() 内部で自動変換
max_tokens = kwargs.pop("max_completion_tokens", None) or kwargs.pop("max_tokens", 4096)
```

### コツ④ `helper_api.py` の Responses API 依存部分を分離する

```python
# ❗ OpenAI Responses API 固有（移植時に対応が必要）
from openai.types.responses import EasyInputMessageParam, Response   # Ollama 非対応

# ✅ 全プロバイダー共通の dict 形式
messages = [{"role": "user", "content": prompt}]
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
  model: "llama3.2"
embedding:
  provider: "ollama"
  model: "nomic-embed-text"
  dimensions: 768
ollama:
  base_url: "http://localhost:11434/v1"
  llm_model: "llama3.2"
  embedding_model: "nomic-embed-text"
  embedding_dims: 768
```

### コツ⑦ Tool Use 対応モデルを確認する

```bash
ollama pull llama3.2         # 推奨デフォルト
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
| **1** | `helper/helper_llm.py` | クラス追加 | `OllamaClient` 追加、`DEFAULT_LLM_PROVIDER="ollama"` | ✅ |
| **1** | `helper/helper_embedding.py` | クラス追加 | `OllamaEmbedding` 追加、デフォルト `"ollama"` | ✅ |
| **1** | `grace/config.py` | 設定変更 | `LLMConfig.model="llama3.2"`、`EmbeddingConfig.dims=768`、`OllamaConfig` 追加 | ✅ |
| **1** | `config/grace_config.yml` | 設定変更 | llm/embedding プロバイダー・モデルを更新 | ⏳ |
| **2** | `grace/planner.py` | API 置換 | `create_llm_client("openai")` → `("ollama")`、`max_completion_tokens` → `max_tokens` | ✅ |
| **2** | `grace/confidence.py` | API 置換 | LLM/Embedding クライアントを Ollama に変更 | ⏳ |
| **2** | `grace/tools.py` | API 置換 | `create_embedding_client` を Ollama に変更 | ⏳ |
| **2** | `grace/executor.py` | 間接変更 | 依存先の変更に追従 | ➡️ |
| **2** | `grace/replan.py` | 間接変更 | 依存先の変更に追従 | ➡️ |
| **2** | `grace/schemas.py` | 変更不要 | Pydantic 定義のみ・API 依存なし | ✔️ |
| **3** | `services/agent_service.py` | ループ確認 | ReAct インターフェース確認（既に共通形式） | ⏳ |
| **3** | `agent_main.py` | 設定変更 | モデルデフォルト値を Ollama 用に変更 | ⏳ |
| **4** | `helper/helper_api.py` | API 分離 | Responses API 依存部分を Chat 形式に統一 | ⏳ |
| **5** | Qdrant コレクション | **再作成必須** | 3072次元 → 768次元のため完全に不互換 | ⚠️ |

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
| 構造化出力 | `beta.parse()` / `responses.parse()` | **JSON モード + `model_validate_json()`** |
| Embedding 次元 | `dimensions=3072` 指定 | **`dimensions` パラメータは非対応** |
| Qdrant 次元 | 3072次元コレクション | **768次元でコレクション再作成必須** |
| API キー | `OPENAI_API_KEY` 必須 | **不要**（`api_key="ollama"`） |
| `response.output_text` | 正常動作 | **属性なし → `choices[0].message.content`** |
| Tool Use 全モデル対応想定 | OK | **対応モデルに限定あり** |

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

# Embedding テスト
python -c "
from helper.helper_embedding import create_embedding_client
emb = create_embedding_client('ollama')
v = emb.embed_text('テスト')
print(f'dims={len(v)}')  # 768 が表示されれば OK
"

# アプリ起動
streamlit run agent_rag.py --server.port 8501
```

---

## 改訂履歴

| 版 | 日付 | 変更内容 |
|---|---|---|
| v1.0 | 2026-05-19 | 初版作成。OpenAI → Ollama 移植仕様書 |

---

*本ドキュメントは `ollama_grace_agent` 移植作業の仕様書として使用する。*
