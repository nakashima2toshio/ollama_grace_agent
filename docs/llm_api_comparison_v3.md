# LLM API 4プロバイダー完全対比表 v3

**対象プロジェクト**

| プロジェクト | LLM | Embedding |
|---|---|---|
| `anthropic_grace_agent` | Anthropic `claude-sonnet-4-6` | Gemini `gemini-embedding-001` |
| `openai_grace_agent` | OpenAI `gpt-4o` / `gpt-4o-mini` | OpenAI `text-embedding-3-small` |
| `gemini_grace_agent` | Gemini `gemini-3-flash-preview` | Gemini `gemini-embedding-001` |
| **`ollama_grace_agent`** | **Ollama `llama3.2`** | **Ollama `nomic-embed-text`** |

**参照実装**: `helper/helper_llm.py`（`GeminiClient` / `OpenAIClient` / `OllamaClient`）、`grace/planner.py`、`grace/confidence.py`、`helper/helper_embedding.py`  
**作成日**: 2026-05-10  
**v2 更新日**: 2026-05-11（Gemini セクション実コード検証による修正）  
**v3 更新日**: 2026-05-18（OpenAI Responses API 移行対応）  
**v4 更新日**: 2026-05-20（**Ollama プロバイダー追加**）

---

## API 一覧表（早見表）

### A. LLM API メソッド一覧

| 機能 | Anthropic | OpenAI | Gemini | **Ollama** |
|---|---|---|---|---|
| **テキスト生成** | `client.messages.create(model, messages, max_tokens, system, temperature)` | `client.responses.create(model, input, ...)` | `client.models.generate_content(model, contents, config)` | **`client.chat.completions.create(model, messages, max_tokens, temperature)`** |
| **構造化出力** | Tool Use → `block.input` | `client.responses.parse(model, input, text_format=Schema)` → `response.output_parsed` | `generate_content(config={response_schema=Schema})` → `response.text` | **JSON モード + スキーマをプロンプトに埋込 + `model_validate_json()`** |
| **Tool Use（ReAct）** | `client.messages.create(tools, messages)` → `stop_reason=="tool_use"` | `client.responses.create(tools, input)` → `stop_reason=="tool_calls"` | `chat.send_message(message=input)` → `part.function_call` | **`client.chat.completions.create(tools, messages)` → `finish_reason=="tool_calls"`（対応モデル限定）** |
| **ツール結果返送** | `messages` に2件追記（assistant + user/tool_result） | `input` に `type="function_call_output"` を N件追記 | `chat.send_message(message=Part.from_function_response(...))` 1回 | **`messages` に `{"role":"tool",...}` を N件追記**（OpenAI Chat 互換） |
| **トークンカウント** | `client.messages.count_tokens(model, messages)` → `.input_tokens` | `tiktoken.encode(text)`（ローカル） | `client.models.count_tokens(model, contents)` → `.total_tokens` | **`tiktoken.encode(text)`（ローカル）** |
| **レスポンス取得** | `response.content[0].text` | `response.output_text` | `response.text` | **`response.choices[0].message.content`** |
| **終了判定** | `stop_reason == "end_turn"` | `stop_reason == "completed"` | `part.function_call` が存在しない | **`finish_reason == "stop"`** |

### B. Embedding API メソッド一覧

| 機能 | Anthropic | OpenAI | Gemini | **Ollama** |
|---|---|---|---|---|
| **Embedding API** | **存在しない** → Gemini 代替 | `client.embeddings.create(model, input, dimensions)` | `client.models.embed_content(model, contents, config)` | **`client.embeddings.create(model, input)`（`dimensions` パラメータ非対応）** |
| **単一テキスト** | `embedding_client.embed_text(text, task_type=None)` | 同左 | 同左 | **同左（内部で `embeddings.create`）** |
| **バッチ処理** | `embedding_client.embed_texts(texts, batch_size)` | 同左 | 同左（100件/バッチ） | **同左** |
| **ベクトル取得** | `response.embeddings[0].values` | `response.data[0].embedding` | `response.embeddings[0].values` | **`response.data[0].embedding`** |
| **task_type（登録）** | `"retrieval_document"`（Gemini 経由） | **なし** | `"retrieval_document"`（小文字） | **なし** |
| **task_type（検索）** | `"retrieval_query"`（Gemini 経由） | **なし** | `"retrieval_query"`（小文字） | **なし** |
| **デフォルトモデル** | `gemini-embedding-001` | `text-embedding-3-small` | `gemini-embedding-001` | **`nomic-embed-text`** |
| **デフォルト次元数** | 3072 | 1536 | 3072 | **768** |
| **config 形式** | dict `{"output_dimensionality": 3072, "task_type": "..."}` | `dimensions=1536`（直接パラメータ） | dict `{"output_dimensionality": 3072, "task_type": "..."}` | **`dimensions` パラメータ非対応。モデル固定次元** |

### C. Qdrant 操作 API 一覧

| 機能 | SDK / メソッド | 備考 |
|---|---|---|
| **クライアント生成** | `QdrantClient(url="http://localhost:6333")` | 全プロジェクト共通 |
| **コレクション作成** | `client.create_collection(name, vectors_config=VectorParams(size, distance))` | `distance=Distance.COSINE` |
| **ベクトル登録** | `client.upsert(collection_name, points=[PointStruct(id, vector, payload)])` | `wait=True` 推奨 |
| **Dense 検索** | `client.query_points(collection_name, query=vector, limit=N)` | |
| **Hybrid 検索** | `client.query_points(collection_name, prefetch=[Dense+Sparse], query=FusionQuery(RRF), limit=N)` | Sparse Vector 必要 |
| **スコア取得** | `response.points[i].score` | コサイン類似度 (0.0–1.0) |
| **ペイロード取得** | `response.points[i].payload` | `{"question":..., "answer":..., "source":...}` |

> **⚠️ Ollama Qdrant 互換性注意**  
> `openai_grace_agent` は `text-embedding-3-small` で**1536次元** / `text-embedding-3-large` で**3072次元**コレクションを使用。  
> `ollama_grace_agent` は `nomic-embed-text` で**768次元**。次元数が異なるため**Qdrantコレクションの再作成が必要**。

### D. 初期化・APIキー一覧

| プロジェクト | 必要 API キー | 環境変数名 | 用途 |
|---|---|---|---|
| `anthropic_grace_agent` | Anthropic | `ANTHROPIC_API_KEY` | LLM |
| `anthropic_grace_agent` | Gemini | `GOOGLE_API_KEY` / `GEMINI_API_KEY` | Embedding |
| `openai_grace_agent` | OpenAI | `OPENAI_API_KEY` | LLM + Embedding |
| `gemini_grace_agent` | Gemini | `GOOGLE_API_KEY` | LLM + Embedding |
| **`ollama_grace_agent`** | **不要（ローカル）** | `OLLAMA_BASE_URL`（省略時: `http://localhost:11434/v1`） | **LLM + Embedding** |
| 全プロジェクト共通 | Qdrant | `QDRANT_HOST` / `QDRANT_PORT` | ベクトル DB |
| オプション | Cohere | `COHERE_API_KEY` | Rerank（省略可） |

### E. クライアント初期化コード（4プロバイダー）

```python
# ── Anthropic ──────────────────────────────────────────────────
import anthropic
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ── OpenAI（Responses API・現行推奨） ───────────────────────────
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
response = client.responses.create(model="gpt-4o", input=[...])

# ── Gemini ─────────────────────────────────────────────────────
from google import genai
from google.genai import types
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# ── Ollama（OpenAI SDK 流用・API キー不要） ─────────────────────
from openai import OpenAI
client = OpenAI(
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    api_key="ollama"   # ダミー（Ollama はキー不要）
)
# Chat Completions のみ対応（Responses API 非対応）
response = client.chat.completions.create(
    model="llama3.2",
    messages=[{"role": "user", "content": "..."}],
    max_tokens=4096
)

# ── Qdrant（全プロジェクト共通） ──────────────────────────────
from qdrant_client import QdrantClient
qdrant = QdrantClient(url="http://localhost:6333")
```

---

## 1. クライアント初期化

| 項目 | Anthropic | OpenAI | Gemini | **Ollama** |
|---|---|---|---|---|
| SDK パッケージ | `anthropic` | `openai` | `google-genai` | **`openai`（流用）** |
| インポート | `import anthropic` | `from openai import OpenAI` | `from google import genai` / `from google.genai import types` | **`from openai import OpenAI`** |
| クライアント生成 | `anthropic.Anthropic(api_key=...)` | `OpenAI(api_key=...)` | `genai.Client(api_key=...)` | **`OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")`** |
| API キー環境変数 | `ANTHROPIC_API_KEY` | `OPENAI_API_KEY` | `GOOGLE_API_KEY` | **不要（`api_key="ollama"` はダミー）** |
| ベース URL | 固定 | 固定 | 固定 | **`OLLAMA_BASE_URL`（デフォルト: `http://localhost:11434/v1`）** |
| チャットセッション | なし | なし（`previous_response_id` で連鎖） | `client.chats.create(model, config)` | **なし（ステートレス）** |
| デフォルトモデル（`grace/`） | `claude-sonnet-4-6` | `gpt-4o-mini` | `gemini-3-flash-preview` | **`llama3.2`** |
| デフォルトモデル（`helper_llm.py`） | — | `gpt-4o-mini` | `gemini-2.0-flash`（⚠️廃止予定） | **`llama3.2`** |

---

## 2. テキスト生成（シングルターン）

| 項目 | Anthropic | OpenAI | Gemini | **Ollama** |
|---|---|---|---|---|
| メソッド | `client.messages.create()` | `client.responses.create()` | `client.models.generate_content()` | **`client.chat.completions.create()`** |
| プロンプト引数 | `messages=[{"role":"user","content":prompt}]` | `input=[{"role":"user","content":prompt}]` | `contents=prompt` | **`messages=[{"role":"user","content":prompt}]`** |
| システムプロンプト | `system="..."` **（トップレベル）** | `input` 先頭に `{"role":"system",...}` | `config=types.GenerateContentConfig(system_instruction="...")` | **`messages` 先頭に `{"role":"system","content":"..."}`** |
| 出力トークン上限 | `max_tokens=...` **（必須）** | `max_output_tokens=...` | `config.max_output_tokens=...` | **`max_tokens=...`**（`max_completion_tokens` / `max_output_tokens` は非対応） |
| 温度パラメータ | `temperature=...` | `temperature=...` | `config=types.GenerateContentConfig(temperature=...)` | **`temperature=...`** |
| レスポンス取得 | `response.content[0].text` | `response.output_text` | `response.text` | **`response.choices[0].message.content`** |
| AFC 無効化 | 不要 | 不要 | **`AutomaticFunctionCallingConfig(disable=True)` 必須** | **不要** |

```python
# Ollama（Chat Completions のみ。max_tokens を使用）
response = client.chat.completions.create(
    model="llama3.2",
    messages=[
        {"role": "system", "content": "あなたは..."},
        {"role": "user",   "content": prompt}
    ],
    max_tokens=4096,      # ← max_completion_tokens / max_output_tokens は非対応
    temperature=0.7,
)
answer = response.choices[0].message.content
```

---

## 3. 会話履歴の管理

| 項目 | Anthropic | OpenAI | Gemini | **Ollama** |
|---|---|---|---|---|
| 管理方式 | `messages` リストを自前管理 | `previous_response_id` で連鎖（または自前管理） | `chat` オブジェクトが自動管理 | **`messages` リストを自前管理** |
| 初期化 | `messages = []` | `input = []` | `client.chats.create(model, config)` | **`messages = []`** |
| ユーザー追加 | 手動で `messages.append({"role":"user",...})` | 手動で `input.append(...)` | `chat.send_message(message=input)` で自動 | **手動で `messages.append({"role":"user",...})`** |
| アシスタント追加 | 手動で `messages.append({"role":"assistant",...})` | `previous_response_id` 方式なら不要 | 自動 | **手動で `messages.append({"role":"assistant",...})`** |
| ロール種別 | `"user"` / `"assistant"` | `"system"` / `"user"` / `"assistant"` / `"function_call_output"` | `parts` 内で自動区別 | **`"system"` / `"user"` / `"assistant"` / `"tool"`** |
| 再呼び出し | `client.messages.create(messages=全履歴)` | `client.responses.create(input=全履歴)` | `chat.send_message(message=次のメッセージ)` | **`client.chat.completions.create(messages=全履歴)`** |

---

## 4. 構造化出力（最大の差異）

| 項目 | Anthropic | OpenAI | Gemini | **Ollama** |
|---|---|---|---|---|
| 方式 | **Tool Use** で代替 | `client.responses.parse(text_format=Schema)` ← 正式版 | `response_schema` に Pydantic クラスを渡す | **JSON モード + スキーマをプロンプトに埋込 + 手動 `model_validate_json()`** |
| スキーマ形式 | `"input_schema": Schema.model_json_schema()` | `text_format=PydanticClass` | `response_schema=PydanticClass` | **`response_format={"type": "json_object"}` + プロンプト内に JSON スキーマを文字列で記載** |
| レスポンス取得 | `tool_block.input` → `model_validate(...)` | `response.output_parsed` | `response.text` → `model_validate_json(...)` | **`response.choices[0].message.content` → `model_validate_json(...)`** |
| JSON 解析 | SDK が自動パース | SDK が自動パース | 手動パース（`JSONDecodeError` リスクあり） | **手動パース（`JSONDecodeError` リスクあり）** |
| `beta.chat.completions.parse()` | 不要 | 旧ベータ版（移行推奨） | なし | **非対応**（使用不可） |
| AFC 無効化 | 不要 | 不要 | **必須** | **不要** |

```python
# Ollama（JSON モード + プロンプト埋込 + 手動パース）
import json
schema_json = json.dumps(ExecutionPlan.model_json_schema(), ensure_ascii=False, indent=2)
augmented_prompt = f"{prompt}\n\n以下の JSON スキーマに従って回答してください:\n{schema_json}"
response = client.chat.completions.create(
    model="llama3.2",
    messages=[
        {"role": "system", "content": "あなたは指定された JSON スキーマに従って出力します。"},
        {"role": "user",   "content": augmented_prompt}
    ],
    response_format={"type": "json_object"},
    max_tokens=4096,
    temperature=0.3,
)
plan = ExecutionPlan.model_validate_json(response.choices[0].message.content)
```

> **Ollama 構造化出力の注意事項**  
> - `client.beta.chat.completions.parse()` は Ollama では使用不可。  
> - `response_format={"type": "json_object"}` はモデルによってサポート状況が異なる（llama3.2, qwen2.5 は対応）。  
> - `OllamaClient.generate_structured()` 内部でこの変換を隠蔽するため、呼び出し元のコードは変更不要。

---

## 5. Tool Use 定義形式

| 項目 | Anthropic | OpenAI | Gemini | **Ollama** |
|---|---|---|---|---|
| ツール定義形式 | `[{"name":..., "description":..., "input_schema":{...}}]` | `[{"type":"function","function":{"name":...,...}}]` | `types.Tool(function_declarations=[{"name":..., "parameters":{...}}])` | **`[{"type":"function","function":{"name":...,...}}]`**（OpenAI 互換） |
| スキーマキー名 | **`"input_schema"`** | **`"parameters"`** | **`"parameters"`** | **`"parameters"`** |
| 対応モデル | 全モデル | 全モデル | 全モデル | **llama3.2 / qwen2.5 / mistral-nemo のみ**（要確認） |

---

## 6. ReAct ループ（Tool Use 検出・結果送信）

| 項目 | Anthropic | OpenAI | Gemini | **Ollama** |
|---|---|---|---|---|
| **ツール呼び出し検出** | `response.stop_reason == "tool_use"` | `response.choices[0].finish_reason == "tool_calls"` | `part.function_call` を走査 | **`response.choices[0].finish_reason == "tool_calls"`** |
| ツール名取得 | `b.name` | `tc.function.name` | `fn.name` | **`tc.function.name`** |
| ツール引数取得 | `b.input`（dict） | `json.loads(tc.function.arguments)` | `dict(fn.args)` | **`json.loads(tc.function.arguments)`** |
| **ツール ID** | `b.id`（`tool_result` 返送時に必須） | `tc.id` | なし | **`tc.id`** |
| **ツール結果の送信** | 2件追記（assistant + user/tool_result） | `{"role":"tool",...}` を複数追記 | `Part.from_function_response()` 1回 | **`{"role":"tool",...}` を複数追記**（OpenAI 互換） |
| **終了判定** | `stop_reason == "end_turn"` | `finish_reason == "stop"` | `function_call` が見つからない | **`finish_reason == "stop"`** |
| **対応モデル** | 全モデル | 全モデル | 全モデル | **llama3.2 / qwen2.5 / mistral-nemo のみ** |

---

## 7. トークンカウント

| 項目 | Anthropic | OpenAI | Gemini | **Ollama** |
|---|---|---|---|---|
| メソッド | `client.messages.count_tokens(model, messages)` | **ローカル計算**（`tiktoken`） | `client.models.count_tokens(model, contents)` | **ローカル計算**（`tiktoken`） |
| 戻り値 | `response.input_tokens` | `len(encoding.encode(text))` | `response.total_tokens` | **`len(encoding.encode(text))`** |
| API コール | あり（リモート） | なし（ローカル） | あり（リモート） | **なし（ローカル）** |
| エンコーディング | — | `cl100k_base` | — | **`cl100k_base`**（近似値） |

---

## 8. Embedding

| 項目 | Anthropic | OpenAI | Gemini | **Ollama** |
|---|---|---|---|---|
| Embedding API | **存在しない** | `client.embeddings.create(model, input, dimensions)` | `client.models.embed_content(model, contents, config)` | **`client.embeddings.create(model, input)`**（OpenAI SDK 流用） |
| デフォルトモデル | `gemini-embedding-001`（代替） | `text-embedding-3-small` | `gemini-embedding-001` | **`nomic-embed-text`** |
| 次元数 | 3072（Gemini 経由） | 1536（`text-embedding-3-small`） | 3072 | **768** |
| `task_type` | Gemini 経由なので使用可 | **なし** | `"retrieval_query"` / `"retrieval_document"` | **なし** |
| `dimensions` パラメータ | Gemini 経由で指定可 | `dimensions=` で指定 | `output_dimensionality=` で指定 | **非対応**（モデル固定次元） |
| API キー | `GOOGLE_API_KEY` | `OPENAI_API_KEY` | `GOOGLE_API_KEY` | **不要**（`api_key="ollama"` ダミー） |
| Qdrant 互換性 | 3072次元コレクション | 1536次元 or 3072次元コレクション | 3072次元コレクション | **768次元コレクション（再作成必要）** |

```python
# Ollama Embedding（OpenAI SDK 流用）
from openai import OpenAI
embed_client = OpenAI(
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    api_key="ollama"
)
response = embed_client.embeddings.create(model="nomic-embed-text", input=text)
vector = response.data[0].embedding  # list[float]、768次元
```

> **⚠️ Qdrant コレクション再作成について**  
> `openai_grace_agent` のコレクションは 1536/3072次元で作成されている。  
> `ollama_grace_agent` では `nomic-embed-text` の **768次元**に変更されるため、コレクションの再作成が必要。

---

## 9. モデル名・料金比較

### LLM モデル

| 用途目安 | Anthropic | OpenAI | Gemini | **Ollama（ローカル）** |
|---|---|---|---|---|
| 最高性能 | `claude-opus-4-7` | `gpt-4o` | `gemini-3-pro-preview` | **`llama3.1:70b`** |
| **推奨デフォルト** | **`claude-sonnet-4-6`** | **`gpt-4o-mini`** | **`gemini-3-flash-preview`** | **`llama3.2`** |
| 高速・低コスト | `claude-haiku-4-5-20251001` | `gpt-4o-mini` | `gemini-2.5-flash-lite` | **`llama3.2:3b` / `phi3:mini`** |
| 軽量 | — | — | — | **`llama3.2:1b`** |
| Tool Use 対応 | 全モデル | 全モデル | 全モデル | **`llama3.2` / `qwen2.5` / `mistral-nemo`** |

### 料金（USD / 1K tokens）

| モデル | Input | Output | 備考 |
|---|---|---|---|
| `claude-opus-4-7` | $0.005 | $0.025 | |
| `claude-sonnet-4-6` | $0.003 | $0.015 | |
| `claude-haiku-4-5-20251001` | $0.0008 | $0.004 | |
| `gpt-4o` | $0.005 | $0.015 | |
| `gpt-4o-mini` | $0.00015 | $0.0006 | |
| `gemini-3-flash-preview` | $0.0005 | $0.003 | |
| `gemini-2.5-flash` | $0.0001 | $0.0004 | |
| `gemini-3-pro-preview` | $0.00125 | $0.010 | |
| **`llama3.2` / 全 Ollama モデル** | **$0.0** | **$0.0** | **ローカル実行（電力・ハードウェアコストのみ）** |

### Embedding モデル

| モデル | 次元数 | 料金（/1K tokens） | プロジェクト採用 |
|---|---|---|---|
| `gemini-embedding-001` | **3072** | 無料枠あり | anthropic / gemini プロジェクト |
| `text-embedding-3-small` | **1536** | $0.00002 | openai プロジェクト（デフォルト） |
| `text-embedding-3-large` | 3072 | $0.00013 | openai プロジェクト（3072次元が必要な場合） |
| **`nomic-embed-text`** | **768** | **$0.0（ローカル）** | **ollama プロジェクト** |

### Ollama モデル一覧（`helper_llm.py` 定義）

| モデル | コンテキスト長 | Tool Use | 備考 |
|---|---|---|---|
| `llama3.2` | 128,000 | ✅ 対応 | **デフォルト推奨** |
| `llama3.2:3b` | 128,000 | ✅ 対応 | 軽量版 |
| `llama3.2:1b` | 128,000 | △ 非推奨 | 最軽量 |
| `llama3.1` | 128,000 | ✅ 対応 | |
| `llama3.1:8b` | 128,000 | ✅ 対応 | |
| `llama3.1:70b` | 128,000 | ✅ 対応 | 最高性能 |
| `qwen2.5:7b` | 128,000 | ✅ 対応 | |
| `qwen2.5:14b` | 128,000 | ✅ 対応 | |
| `mistral` | 128,000 | △ 非推奨 | |
| `mistral-nemo` | 128,000 | ✅ 対応 | |
| `phi3` | 128,000 | ❌ 非対応 | |
| `phi3:mini` | 128,000 | ❌ 非対応 | |
| `gemma2` | 128,000 | ❌ 非対応 | |
| `gemma2:9b` | 128,000 | ❌ 非対応 | |

---

## 10. grace/ モジュール別 API 使用状況

### ollama_grace_agent（移行後）

| モジュール | クラス / 機能 | 使用プロバイダー | 主要 API |
|---|---|---|---|
| `grace/planner.py` | `Planner.create_plan()` | **Ollama** | `chat.completions.create()` + JSON モード + `model_validate_json()` |
| `grace/planner.py` | `Planner.estimate_complexity_with_llm()` | **Ollama** | `chat.completions.create()`（テキスト生成） |
| `grace/confidence.py` | `LLMSelfEvaluator.evaluate()` | **Ollama** | `chat.completions.create()`（スコア数値のみ） |
| `grace/confidence.py` | `LLMSelfEvaluator.evaluate_with_factors()` | **Ollama** | `chat.completions.create()` + JSON モード + `model_validate_json()` |
| `grace/confidence.py` | `QueryCoverageCalculator.calculate()` | **Ollama** | `chat.completions.create()`（スコア数値のみ） |
| `grace/confidence.py` | `SourceAgreementCalculator.calculate()` | **Ollama Embedding** | `embeddings.create()` + コサイン類似度 |
| `helper/helper_llm.py` | `OllamaClient.generate_content()` | **Ollama** | `chat.completions.create()`（max_tokens 内部変換） |
| `helper/helper_llm.py` | `OllamaClient.generate_structured()` | **Ollama** | `chat.completions.create()` + JSON モード + スキーマ埋込 |
| `helper/helper_embedding.py` | `OllamaEmbedding.embed_text()` | **Ollama** | `embeddings.create()`（OpenAI SDK 流用） |

---

## 11. プロバイダー切替方法

```python
# helper/helper_llm.py の create_llm_client() で切り替え可能
from helper.helper_llm import create_llm_client

llm = create_llm_client("anthropic")  # → AnthropicClient
llm = create_llm_client("openai")     # → OpenAIClient（default: gpt-4o-mini）
llm = create_llm_client("gemini")     # → GeminiClient
llm = create_llm_client("ollama")     # → OllamaClient（default: llama3.2）

# 環境変数での切り替え
# export LLM_PROVIDER=anthropic   # anthropic_grace_agent
# export LLM_PROVIDER=openai      # openai_grace_agent
# export LLM_PROVIDER=gemini      # gemini_grace_agent
# export LLM_PROVIDER=ollama      # ollama_grace_agent（デフォルト）

# Embedding の切り替え
from helper.helper_embedding import create_embedding_client

emb = create_embedding_client("gemini")    # → GeminiEmbedding（3072次元）
emb = create_embedding_client("openai")    # → OpenAIEmbedding（1536次元）
emb = create_embedding_client("ollama")    # → OllamaEmbedding（768次元）
emb = create_embedding_client("fastembed") # → FastEmbedEmbedding（384次元）

# Ollama ベース URL の変更
# export OLLAMA_BASE_URL=http://remote-server:11434/v1
```

---

## 12. よくある移植ミスと対策

| ミス | Anthropic | OpenAI | Gemini | **Ollama** |
|---|---|---|---|---|
| システムプロンプトの場所 | `system=` トップレベル | `input` 先頭に `{"role":"system",...}` | `config.system_instruction=...` | **`messages` 先頭に `{"role":"system",...}`** |
| `max_tokens` 系パラメータ名 | `max_tokens`（必須） | `max_output_tokens`（Responses API） | `max_output_tokens` | **`max_tokens`**（`max_completion_tokens` / `max_output_tokens` は非対応） |
| ツール定義キー名 | `"input_schema"` | `"parameters"` | `"parameters"` | **`"parameters"`** |
| ツール結果の追記数 | 2件 | N件 | 1件 | **N件**（`{"role":"tool",...}` を追記） |
| 構造化出力 | Tool Use | `responses.parse(text_format=Schema)` | `response_schema=PydanticClass` | **JSON モード + スキーマ埋込 + `model_validate_json()`** |
| `beta.chat.completions.parse()` | なし | 旧ベータ版 | なし | **使用不可** |
| レスポンスアクセス | `response.content[0].text` | `response.output_text` | `response.text` | **`response.choices[0].message.content`** |
| AFC 無効化コード | 削除する | 削除する | **必須** | **不要（削除する）** |
| Tool Use 対応モデル確認 | 全モデル対応 | 全モデル対応 | 全モデル対応 | **llama3.2 / qwen2.5 / mistral-nemo のみ** |
| Qdrant 次元数 | 3072次元 | 1536/3072次元 | 3072次元 | **768次元（コレクション再作成必要）** |
| `dimensions` パラメータ | Gemini 経由で指定可 | `dimensions=` で指定 | `output_dimensionality=` | **非対応（渡さない）** |
| API キー | 必要 | 必要 | 必要 | **不要（`api_key="ollama"` ダミー）** |
| Responses API 使用 | なし | 使用可 | なし | **使用不可（Chat Completions のみ）** |

---

## 13. セマンティックチャンキング（chunking/ モジュール）

| 項目 | Anthropic（現行） | OpenAI | Gemini | **Ollama** |
|---|---|---|---|---|
| SDK | `anthropic` | `openai` | `google-genai` | **`openai`（流用）** |
| クライアント生成 | `anthropic.Anthropic(api_key=...)` | `OpenAI(api_key=...)` | `genai.Client(api_key=...)` | **`OpenAI(base_url=..., api_key="ollama")`** |
| API メソッド | `client.messages.create()` | `client.responses.create()` | `client.models.generate_content()` | **`client.chat.completions.create()`** |
| 構造化出力方式 | Tool Use 強制 | `responses.parse(text_format=Schema)` | `response_schema=PydanticClass` | **JSON モード + スキーマ埋込 + `model_validate_json()`** |
| 結果取得 | `block.input` → `json.dumps()` | `response.output_parsed` | `response.text` → `model_validate_json()` | **`response.choices[0].message.content` → `model_validate_json()`** |
| 非同期化 | `asyncio.to_thread(client.messages.create, ...)` | `asyncio.to_thread(client.responses.create, ...)` | `asyncio.to_thread(client.models.generate_content, ...)` | **`asyncio.to_thread(client.chat.completions.create, ...)`** |
| 並列制御 | `asyncio.Semaphore(max_workers)` | 同左 | 同左 | **同左** |
| 正常終了検出 | `stop_reason == "tool_use"` | `response.status == "completed"` | 通常と同様 | **`finish_reason == "stop"`** |
| 切断検出 | `stop_reason == "max_tokens"` → リトライ | `stop_reason == "max_output_tokens"` → リトライ | `finish_reason == MAX_TOKENS` → リトライ | **`finish_reason == "length"` → リトライ** |
| レート制限 | `"429"` / `"overloaded"` → 30秒待機 | `RateLimitError` → バックオフ | `"429"` / `"quota"` → 待機 | **通常なし（ローカル）。ただし VRAM 不足でエラーになる場合あり** |

---

## 14. Q/A自動生成（qa_generation/ + Celery）

| 項目 | Anthropic（現行） | OpenAI | Gemini | **Ollama** |
|---|---|---|---|---|
| SDK | `anthropic` | `openai` | `google-genai` | **`openai`（流用）** |
| LLM クライアント生成 | `create_llm_client("anthropic")` | `create_llm_client("openai")` | `create_llm_client("gemini")` | **`create_llm_client("ollama")`** |
| API メソッド | `llm.generate_content(prompt, model, ...)` | 同左 | 同左 | **同左（内部で `chat.completions.create`）** |
| 処理フロー | `analyze_chunk()` → `generate_qa_pairs()` | 同左 | 同左 | **同左** |
| 並列処理 | Celery + `apply_async(args=...)` | 同左 | 同左 | **同左** |
| API キー | `ANTHROPIC_API_KEY` | `OPENAI_API_KEY` | `GOOGLE_API_KEY` | **不要** |
| レート制限 | あり（Anthropic API 上限） | あり（OpenAI API 上限） | あり（Gemini API 上限） | **なし（ローカル実行速度による）** |

---

## 15. Qdrant 登録・検索

### 15-1. Qdrant 登録フロー

| 項目 | Anthropic | OpenAI | Gemini | **Ollama** |
|---|---|---|---|---|
| Embedding プロバイダー | Gemini `gemini-embedding-001` | OpenAI `text-embedding-3-small` | Gemini `gemini-embedding-001` | **Ollama `nomic-embed-text`** |
| Embedding クライアント | `create_embedding_client("gemini")` | `create_embedding_client("openai")` | `create_embedding_client("gemini")` | **`create_embedding_client("ollama")`** |
| `task_type`（登録時） | `"retrieval_document"` | **なし** | `"retrieval_document"` | **なし** |
| 次元数 | **3072** | **1536** | **3072** | **768** |
| Qdrant コレクション再作成 | 不要（Gemini で統一） | 不要（OpenAI で統一） | 不要（Gemini で統一） | **必要**（768次元に変更） |

### 15-2. Qdrant コレクション作成例（Ollama 768次元）

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

qdrant = QdrantClient(url="http://localhost:6333")
qdrant.create_collection(
    collection_name="ollama_grace_qa",
    vectors_config=VectorParams(
        size=768,             # ← nomic-embed-text の次元数
        distance=Distance.COSINE
    )
)
```

---

## 16. Ollama 固有の注意事項

### 16-1. Ollama サーバーのセットアップ

```bash
ollama serve
ollama pull llama3.2
ollama pull nomic-embed-text
ollama list
```

### 16-2. 環境変数設定

```bash
export OLLAMA_BASE_URL=http://localhost:11434/v1
export LLM_PROVIDER=ollama
export EMBEDDING_PROVIDER=ollama

# リモート Ollama サーバーへの接続
# export OLLAMA_BASE_URL=http://remote-server:11434/v1
```

### 16-3. Ollama vs クラウド API の比較

| 項目 | Ollama（ローカル） | クラウド API（OpenAI/Gemini/Anthropic） |
|---|---|---|
| コスト | 電力・ハードウェアのみ | トークン従量課金 |
| プライバシー | 完全ローカル（データ送信なし） | データがクラウドに送信される |
| 速度 | GPU/CPU 性能に依存 | 通常は高速（大規模インフラ） |
| モデル性能 | クラウド最新モデルより劣る場合あり | GPT-4o, Gemini Pro など最高性能 |
| オフライン | 使用可能 | 要インターネット接続 |
| API キー | 不要 | 必要 |
| Responses API | **非対応** | OpenAI のみ対応 |
| `beta.parse()` | **非対応** | OpenAI のみ対応 |
| 構造化出力 | JSON モード + 手動パース | SDK が自動パース（OpenAI/Gemini） |

---

## 不足情報・要確認事項

| 項目 | 状況 | 対策 |
|---|---|---|
| `helper_llm.py` の `GeminiClient` デフォルトモデルが `gemini-2.0-flash`（廃止予定） | **要緊急修正** | `"gemini-3-flash-preview"` に変更 |
| Ollama の `response_format={"type": "json_object"}` 対応モデル | モデルにより異なる | `llama3.2` / `qwen2.5` で確認推奨 |
| Ollama Tool Use の非対応モデルでの graceful fallback | `phi3`、`gemma2` 等で Tool Use 呼び出し時 | モデル選択時に確認、または JSON モードで代替 |
| `helper/helper_api.py` の Responses API 依存箇所 | `EasyInputMessageParam` 等の Ollama 非対応部分が残存 | Chat Completions 互換に置き換え必要 |
| `grace/confidence.py` の Ollama 移行完了確認 | `create_llm_client("ollama")` に変更済みか未確認 | 実コード検証必要 |
| Ollama `nomic-embed-text` の実際の次元数 | 768次元（公称値） | `ollama pull nomic-embed-text` 後に実測確認推奨 |

---

## 改訂履歴

| 版 | 日付 | 変更内容 |
|---|---|---|
| v1 | 2026-05-10 | 初版作成（Anthropic / OpenAI / Gemini 3プロバイダー） |
| v2 | 2026-05-11 | Gemini 各節を `gemini_grace_agent` 実コードで検証。7項目を修正 |
| v3 | 2026-05-18 | OpenAI Responses API 移行対応（`responses.create()` / `responses.parse()` / `response.output_text` 等） |
| **v4** | **2026-05-20** | **Ollama プロバイダー列を全節に追加**。早見表A・B・D・E を4プロバイダー対応に拡張。§1–§15 に Ollama 列追記。§16「Ollama 固有の注意事項」を新設。モデル一覧・Qdrant 互換性・Tool Use 対応モデル一覧を追加 |
