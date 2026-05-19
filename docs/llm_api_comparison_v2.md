# LLM API 3プロバイダー完全対比表 v2

**対象プロジェクト**

| プロジェクト | LLM | Embedding |
|---|---|---|
| `anthropic_grace_agent` | Anthropic `claude-sonnet-4-6` | Gemini `gemini-embedding-001` |
| `openai_grace_agent` | OpenAI `gpt-4o` / `gpt-4o-mini` | OpenAI `text-embedding-3-small` |
| `gemini_grace_agent` | Gemini `gemini-3-flash-preview` ← **修正** | Gemini `gemini-embedding-001` |

**参照実装**: `helper/helper_llm.py`（`GeminiClient` / `OpenAIClient`）、`grace/planner.py`、`grace/confidence.py`、`helper/helper_embedding.py`  
**作成日**: 2026-05-10  
**v2 更新日**: 2026-05-11（Gemini セクション実コード検証による修正）  
**v3 更新日**: 2026-05-18（OpenAI Responses API 移行対応）

---

## API 一覧表（早見表）

### A. LLM API メソッド一覧

| 機能 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| **テキスト生成** | `client.messages.create(model, messages, max_tokens, system, temperature)` | ~~`client.chat.completions.create()`~~ → **`client.responses.create(model, input, ...)`** | `client.models.generate_content(model, contents, config)` |
| **構造化出力** | `client.messages.create(tools=[{input_schema}], tool_choice="tool")` → `block.input` | ~~`client.beta.chat.completions.parse(model, messages, response_format=Schema)` → `message.parsed`~~ → **`client.responses.parse(model, input, text_format=Schema)` → `response.output_parsed`** | `client.models.generate_content(config={response_schema=Schema})` → `response.text` |
| **Tool Use（ReAct）** | `client.messages.create(tools, messages)` → `stop_reason=="tool_use"` | `client.responses.create(tools, input)` → `stop_reason=="tool_calls"` | `chat.send_message(message=input)` → `part.function_call` |
| **ツール結果返送** | `messages` に **2件追記**（assistant + user/tool_result） | `input` に `type="function_call_output"` を **N件追記** | `chat.send_message(message=Part.from_function_response(...))` **1回** |
| **トークンカウント** | `client.messages.count_tokens(model, messages)` → `.input_tokens` | `tiktoken.encode(text)`（ローカル） | `client.models.count_tokens(model, contents)` → `.total_tokens` |
| **レスポンス取得** | `response.content[0].text` | ~~`response.choices[0].message.content`~~ → **`response.output_text`**（ヘルパー）or `response.output[0].content[0].text` | `response.text` |
| **終了判定** | `stop_reason == "end_turn"` | `stop_reason == "completed"` | `part.function_call` が存在しない |

### B. Embedding API メソッド一覧

| 機能 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| **Embedding API** | **存在しない** → Gemini 代替 | `client.embeddings.create(model, input, dimensions)` | `client.models.embed_content(model, contents, config)` |
| **単一テキスト** | `embedding_client.embed_text(text, task_type=None)` | 同左（内部で `embeddings.create`） | 同左（内部で `embed_content`） |
| **バッチ処理** | `embedding_client.embed_texts(texts, batch_size)` | 同左 | 同左（100件/バッチ） |
| **ベクトル取得** | `response.embeddings[0].values`（Gemini 経由） | `response.data[0].embedding` | `response.embeddings[0].values` |
| **task_type（登録）** | `"retrieval_document"`（Gemini 経由・小文字） | **なし** | `"retrieval_document"`（小文字） |
| **task_type（検索）** | `"retrieval_query"`（Gemini 経由・小文字） | **なし** | `"retrieval_query"`（小文字） |
| **デフォルトモデル** | `gemini-embedding-001` | `text-embedding-3-small` | `gemini-embedding-001` |
| **デフォルト次元数** | 3072 | 1536 | 3072 |
| **config 形式** | dict `{"output_dimensionality": 3072, "task_type": "..."}` | `dimensions=1536`（直接パラメータ） | dict `{"output_dimensionality": 3072, "task_type": "..."}` |

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

### D. 初期化・APIキー一覧

| プロジェクト | 必要 API キー | 環境変数名 | 用途 |
|---|---|---|---|
| `anthropic_grace_agent` | Anthropic | `ANTHROPIC_API_KEY` | LLM（テキスト生成・チャンキング・Q&A生成） |
| `anthropic_grace_agent` | Gemini | `GOOGLE_API_KEY` / `GEMINI_API_KEY` | Embedding（登録・検索） |
| `openai_grace_agent` | OpenAI | `OPENAI_API_KEY` | LLM + Embedding |
| `gemini_grace_agent` | Gemini | `GOOGLE_API_KEY` | LLM + Embedding |
| 全プロジェクト共通 | Qdrant | `QDRANT_HOST` / `QDRANT_PORT` | ベクトル DB |
| オプション | Cohere | `COHERE_API_KEY` | Rerank（省略可） |

### E. クライアント初期化コード（3プロバイダー）

```python
# ── Anthropic ──────────────────────────────────────────────────
import anthropic
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ── OpenAI（Responses API・現行推奨） ───────────────────────────
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
# テキスト生成（Responses API）
response = client.responses.create(model="gpt-4o", input=[...])
# 旧: client.chat.completions.create() → 引き続き使用可（非推奨ではないが新規は Responses API 推奨）

# ── Gemini ─────────────────────────────────────────────────────
from google import genai
from google.genai import types           # GenerateContentConfig 等に必須
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# ── Qdrant（全プロジェクト共通） ──────────────────────────────
from qdrant_client import QdrantClient
qdrant = QdrantClient(url="http://localhost:6333")
```

---

## v2 修正箇所サマリ（Gemini API 関連）

| 節 | 修正内容 | 修正理由（実コード根拠） |
|:---|:---|:---|
| 表頭 | LLM モデル `gemini-2.5-flash` → `gemini-3-flash-preview` | `grace/config.py` `LLMConfig.model` デフォルト値 |
| 1節 | `GeminiClient` デフォルト `gemini-2.0-flash` に廃止警告追加 | `helper_llm.py` L85。2026-06-01 廃止予定 |
| 4節 | Gemini Structured Output: `response_schema=ExecutionPlan.model_json_schema()` を2方式に整理 | `grace/planner.py` は Pydantic 直渡し。`helper_llm.py` は `.model_json_schema()` 使用。混在あり |
| 4節 | Gemini の AFC 無効化コード追加 | `grace/planner.py`・`grace/confidence.py` で必須 |
| 8節 | Embedding 設定形式を修正: `EmbedContentConfig` → dict 形式、`task_type` を小文字に修正、`output_dimensionality` パラメータ追加 | `helper/helper_embedding.py` 実装 |
| 8節 | OpenAI Embedding デフォルトモデル `text-embedding-3-large` → `text-embedding-3-small` に修正 | `helper/helper_embedding.py` `OpenAIEmbedding` デフォルト値 |
| 9節 | `gemini-2.0-flash` に廃止警告追加。`gemini-3-flash-preview` を追加 | 2026-06-01 シャットダウン予定 |
| 10節 | `gemini_grace_agent` の `grace/confidence.py` は OpenAI ではなく Gemini を使用と注記 | `confidence.py` 全クラスが `genai.Client()` を使用 |

---

## 1. クライアント初期化

| 項目 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| SDK パッケージ | `anthropic` | `openai` | `google-genai` |
| インポート | `import anthropic` | `from openai import OpenAI` | `from google import genai` / `from google.genai import types` |
| クライアント生成 | `anthropic.Anthropic(api_key=...)` | `OpenAI(api_key=...)` | `genai.Client(api_key=...)` |
| API キー環境変数 | `ANTHROPIC_API_KEY` | `OPENAI_API_KEY` | `GOOGLE_API_KEY` |
| チャットセッション | **なし**（ステートレス設計） | **なし**（Responses API は `previous_response_id` で連鎖） | `client.chats.create(model, config)` |
| デフォルトモデル（`grace/`） | `claude-sonnet-4-6` | `gpt-4o-mini` | **`gemini-3-flash-preview`** |
| デフォルトモデル（`helper_llm.py`） | — | `gpt-4o-mini` | ~~`gemini-2.0-flash`~~ **⚠️ 廃止予定→要変更** |

```python
# Anthropic
import anthropic
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# OpenAI（Responses API：現行推奨）
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
# テキスト生成
response = client.responses.create(model="gpt-4o-mini", input=[{"role":"user","content":"..."}])
# 旧 Chat Completions（引き続き使用可能、非推奨ではない）
# response = client.chat.completions.create(model="gpt-4o-mini", messages=[...])

# Gemini
from google import genai
from google.genai import types   # ← 必須（GenerateContentConfig等）
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
```

> **⚠️ helper_llm.py の GeminiClient デフォルトモデル**  
> `helper_llm.py` の `GeminiClient.__init__` は `default_model="gemini-2.0-flash"` だが、
> このモデルは **2026-06-01 に廃止**。`"gemini-3-flash-preview"` または `"gemini-2.5-flash"` に変更が必要。

---

## 2. テキスト生成（シングルターン）

| 項目 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| メソッド | `client.messages.create()` | `client.chat.completions.create()` | `client.models.generate_content()` |
| プロンプト引数 | `messages=[{"role":"user","content":prompt}]` | ~~`messages=[...]`~~ → **`input=[{"role":"user","content":prompt}]`** | `contents=prompt` |
| システムプロンプト | `system="..."` **（messages の外・トップレベル）** | ~~`messages` 先頭に `{"role":"system",...}`~~ → **`input` の先頭に `{"role":"system",...}`** | `config=types.GenerateContentConfig(system_instruction="...")` |
| 出力トークン上限 | `max_tokens=...` **（必須）** | **`max_output_tokens=...`**（Responses API） | `config.max_output_tokens=...` |
| 温度パラメータ | `temperature=...`（直接パラメータ） | `temperature=...`（直接パラメータ） | `config=types.GenerateContentConfig(temperature=...)` |
| レスポンス取得 | `response.content[0].text` | ~~`response.choices[0].message.content`~~ → **`response.output_text`**（ヘルパー）または `response.output[0].content[0].text` | `response.text` |
| AFC 無効化 | **不要**（概念なし） | **不要**（概念なし） | **`AutomaticFunctionCallingConfig(disable=True)` 必須** |

```python
# Anthropic
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=4096,            # 必須
    system="あなたは...",        # messages の外
    temperature=0.7,
    messages=[{"role": "user", "content": prompt}]
)
answer = response.content[0].text

# OpenAI（Responses API：現行推奨）
response = client.responses.create(
    model="gpt-4o",
    input=[
        {"role": "system", "content": "あなたは..."},
        {"role": "user",   "content": prompt}
    ],
    max_output_tokens=4096,    # Responses API は max_output_tokens
    temperature=0.7,
)
answer = response.output_text  # ← 新ヘルパー（旧: response.choices[0].message.content）

# OpenAI（旧 Chat Completions：引き続き使用可能）
# response = client.chat.completions.create(
#     model="gpt-4o",
#     messages=[{"role":"system","content":"..."}, {"role":"user","content":prompt}],
#     max_completion_tokens=4096,
#     temperature=0.7,
# )
# answer = response.choices[0].message.content

# Gemini（実コード: grace/planner.py, grace/confidence.py 参照）
from google import genai
from google.genai import types

response = client.models.generate_content(
    model="gemini-3-flash-preview",
    contents=prompt,
    config=types.GenerateContentConfig(
        system_instruction="あなたは...",
        max_output_tokens=4096,
        temperature=0.7,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)  # 必須
    )
)
answer = response.text
```

---

## 3. 会話履歴の管理

| 項目 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| 管理方式 | `messages` リストを**自前管理** | **`previous_response_id` で連鎖**（または `input` リストを自前管理） | `chat` オブジェクトが**自動管理** |
| 初期化 | `messages = []` | `input = []` または `previous_response_id=None` | `client.chats.create(model, config)` |
| ユーザー追加 | 手動で `messages.append({"role":"user",...})` | 手動で `input.append({"role":"user",...})` または次の呼び出し時に `previous_response_id` を渡す | `chat.send_message(message=input)` で自動追加 |
| アシスタント追加 | 手動で `messages.append({"role":"assistant",...})` | `previous_response_id` 方式なら**不要**（API 側が保持） | 自動（chat オブジェクトが保持） |
| ロール種別 | `"user"` / `"assistant"` | `"system"` / `"user"` / `"assistant"` / `"function_call_output"` | `parts` 内で自動区別 |
| 再呼び出し | `client.messages.create(messages=全履歴)` | `client.responses.create(input=全履歴)` または `client.responses.create(previous_response_id=前回ID)` | `chat.send_message(message=次のメッセージ)` |

```python
# Anthropic（自前管理）
messages = []
messages.append({"role": "user", "content": "質問1"})
res1 = client.messages.create(model=..., messages=messages, max_tokens=4096)
messages.append({"role": "assistant", "content": res1.content[0].text})
messages.append({"role": "user", "content": "続き"})
res2 = client.messages.create(model=..., messages=messages, max_tokens=4096)

# OpenAI（自前管理 ※ system は最初に固定）
messages = [{"role": "system", "content": "あなたは..."}]
messages.append({"role": "user", "content": "質問1"})
res1 = client.chat.completions.create(model=..., messages=messages)
messages.append({"role": "assistant", "content": res1.choices[0].message.content})
messages.append({"role": "user", "content": "続き"})
res2 = client.chat.completions.create(model=..., messages=messages)

# Gemini（chat が自動管理）
chat = client.chats.create(model=model_name, config=config)
res1 = chat.send_message(message="質問1")   # ← キーワード引数 message= 推奨
res2 = chat.send_message(message="続き")    # 履歴は chat オブジェクトが保持
```

---

## 4. 構造化出力（最大の差異）

| 項目 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| 方式 | **Tool Use** で代替（`input_schema` にスキーマを渡す） | **Responses API**: `client.responses.parse(text_format=Schema)` ← **正式版** / 旧: `client.beta.chat.completions.parse()` | `response_schema` に Pydantic クラスを渡す |
| スキーマ形式 | `"input_schema": PydanticClass.model_json_schema()` | **`text_format=PydanticClass`**（Responses API） / 旧: `response_format=PydanticClass` | **`response_schema=PydanticClass`（クラス直渡し） ← grace/planner.py** |
| レスポンス取得 | `tool_block.input` → `model_validate(tool_block.input)` | **`response.output_parsed`**（Responses API） / 旧: `response.choices[0].message.parsed` | `response.text` → `model_validate_json(response.text)` |
| JSON 解析 | SDK が自動パース（`model_validate()` で型安全） | SDK が自動パース（`output_parsed` で型安全） | 手動パース（`JSONDecodeError` リスクあり。空レスポンスガード必要） |
| 終了検出 | `response.stop_reason == "tool_use"` | `response.status == "completed"` | 通常の `generate_content()` と同様 |
| AFC 無効化 | 不要 | 不要 | **`AutomaticFunctionCallingConfig(disable=True)` 必須（空レスポンス防止）** |

```python
# Anthropic（Tool Use で代替）
tool_def = {
    "name"        : "structured_output",
    "description" : "Return structured data",
    "input_schema": ExecutionPlan.model_json_schema()
}
response = client.messages.create(
    model=model_name, max_tokens=4096,
    system="Always respond using the provided tool.",
    tools=[tool_def],
    tool_choice={"type": "tool", "name": "structured_output"},
    messages=[{"role": "user", "content": prompt}]
)
tool_block = next(b for b in response.content if b.type == "tool_use")
plan = ExecutionPlan.model_validate(tool_block.input)

# ─────────────────────────────────────────────────────────────────
# OpenAI — 正式版（Responses API）← 現行推奨
# ─────────────────────────────────────────────────────────────────
response = client.responses.parse(
    model="gpt-4o",
    input=[
        {"role": "system", "content": "..."},
        {"role": "user",   "content": prompt}
    ],
    text_format=ExecutionPlan,      # ← Pydantic クラスを直接渡す
    max_output_tokens=4096,
)
plan = response.output_parsed      # ← ExecutionPlan インスタンスが直接返る

# OpenAI — 旧ベータ版（Chat Completions）← 引き続き動作するが移行推奨
# response = client.beta.chat.completions.parse(
#     model="gpt-4o",
#     messages=[{"role":"system","content":"..."}, {"role":"user","content":prompt}],
#     response_format=ExecutionPlan,
#     max_completion_tokens=4096,
# )
# plan = response.choices[0].message.parsed

# ─────────────────────────────────────────────────────────────────
# Gemini — 方式A: Pydantic クラス直渡し（grace/planner.py の実装）← 推奨
# ─────────────────────────────────────────────────────────────────
response = client.models.generate_content(
    model="gemini-3-flash-preview",
    contents=prompt,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ExecutionPlan,          # ← Pydantic クラスをそのまま渡す
        temperature=0.3,
        max_output_tokens=8192,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),  # 必須
    )
)
# 空レスポンスガード（AFC 永続化バグ対策。planner.py 参照）
if response and response.text:
    plan = ExecutionPlan.model_validate_json(response.text)

# ─────────────────────────────────────────────────────────────────
# Gemini — 方式B: .model_json_schema() 使用（helper_llm.py の実装）
# ─────────────────────────────────────────────────────────────────
config = {
    "response_mime_type": "application/json",
    "response_schema"   : ExecutionPlan.model_json_schema()  # ← dict 形式
}
response = client.models.generate_content(
    model=model_name,
    contents=prompt,
    config=types.GenerateContentConfig(**config)
)
plan = ExecutionPlan.model_validate_json(response.text)
```

> **OpenAI 構造化出力の移行状況**  
> `client.beta.chat.completions.parse()` → `client.responses.parse()` への移行が公式推奨。  
> 旧 beta API も引き続き動作するが、Responses API では `text_format=` パラメータを使用し、
> 結果は `response.output_parsed` で取得する点に注意。

> **コードベース内の混在について（Gemini）**  
> `grace/planner.py`（方式A）と `helper/helper_llm.py`（方式B）で実装が異なる。  
> 方式Aの方が新SDK本来の使い方で簡潔。grace/ モジュールは方式Aに統一することを推奨。

---

## 5. Tool Use 定義形式

| 項目 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| ツール定義形式 | `[{"name":..., "description":..., "input_schema":{...}}]` | `[{"type":"function","function":{"name":...,"description":...,"parameters":{...}}}]` | `types.Tool(function_declarations=[{"name":..., "parameters":{...}}])` |
| スキーマキー名 | **`"input_schema"`** | **`"parameters"`** | **`"parameters"`** |
| `description` | ツール直下に必須 | `function` 内に記述 | `function_declarations` 直下（任意） |

```python
# Anthropic（"input_schema" キー）
tools = [
    {
        "name"        : "search_rag",
        "description" : "RAG 検索を実行する",
        "input_schema": {
            "type"      : "object",
            "properties": {"query": {"type": "string", "description": "検索クエリ"}},
            "required"  : ["query"]
        }
    }
]

# OpenAI（"parameters" キー + "type":"function" ラッパー）
tools = [
    {
        "type"    : "function",
        "function": {
            "name"       : "search_rag",
            "description": "RAG 検索を実行する",
            "parameters" : {
                "type"      : "object",
                "properties": {"query": {"type": "string", "description": "検索クエリ"}},
                "required"  : ["query"]
            }
        }
    }
]

# Gemini（types.Tool ラッパー + "parameters" キー）
tools = types.Tool(function_declarations=[
    {
        "name"      : "search_rag",
        "parameters": {
            "type"      : "object",
            "properties": {"query": {"type": "string", "description": "検索クエリ"}},
        }
    }
])
```

---

## 6. ReAct ループ（Tool Use 検出・結果送信）

| 項目 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| **ツール呼び出し検出** | `response.stop_reason == "tool_use"` | `response.choices[0].finish_reason == "tool_calls"` | `candidates[0].content.parts` を走査して `part.function_call` を探す |
| ツール名取得 | `b.name`（`b.type == "tool_use"` のブロック） | `tc.function.name` | `fn.name` |
| ツール引数取得 | `b.input`（`dict` が直接返る） | `json.loads(tc.function.arguments)` | `dict(fn.args) if hasattr(fn, 'args') else {}` |
| **ツール ID** | **`b.id`**（`tool_result` 返送時に必須） | `tc.id`（`tool_call_id` として必須） | なし |
| **ツール結果の送信** | **2件追記が必須**（① assistant + ② user/tool_result） | tool ごとに `{"role":"tool",...}` を **複数追記**（1件ずつ） | `types.Part.from_function_response()` + `chat.send_message(message=part)` **1回** |
| 複数ツール同時 | 全件を同一 `user` メッセージにまとめる | tool 1件ごとに独立した `"role":"tool"` メッセージ | 1件ずつ処理 |
| **終了判定** | `stop_reason == "end_turn"` | `finish_reason == "stop"` | `function_call` が見つからない |

```python
# ─────────────────────────────────────────────────────────────────
# Gemini（chat 経由 + 新SDK パターン / agent_service.py 参照）
# ─────────────────────────────────────────────────────────────────
response = chat.send_message(message=augmented_input)   # ← キーワード引数必須

# レスポンスアクセスは candidates 経由（response.parts は旧SDK）
if response.candidates and len(response.candidates) > 0:
    candidate = response.candidates[0]
    if candidate.content and candidate.content.parts:
        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fn = part.function_call
                result = execute_tool(fn.name, dict(fn.args) if hasattr(fn, 'args') else {})

                # Function Response 返送（旧SDK の genai.protos.Part は使用不可）
                part_response = types.Part.from_function_response(
                    name=str(fn.name),                  # str() キャスト必須
                    response={"result": result}
                )
                response = chat.send_message(message=part_response)  # ← キーワード引数
            elif hasattr(part, 'text') and part.text:
                final_answer = part.text   # function_call がなければ終了
```

---

## 7. トークンカウント

| 項目 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| メソッド | `client.messages.count_tokens(model, messages)` | **ローカル計算**（`tiktoken` ライブラリ） | `client.models.count_tokens(model, contents)` |
| 戻り値 | `response.input_tokens` | `len(encoding.encode(text))` | `response.total_tokens` |
| API コール | **あり**（リモート） | **なし**（ローカル） | **あり**（リモート） |
| 備考 | メッセージ形式のまま渡せる | `cl100k_base` or モデル固有エンコーディング | シンプルなテキストを渡す |

```python
# Anthropic
response = client.messages.count_tokens(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": text}]
)
count = response.input_tokens

# OpenAI（ローカル・高速）
import tiktoken
try:
    encoding = tiktoken.encoding_for_model(model)
except KeyError:
    encoding = tiktoken.get_encoding("cl100k_base")
count = len(encoding.encode(text))

# Gemini（helper_llm.py の GeminiClient.count_tokens() 実装）
response = client.models.count_tokens(model="gemini-3-flash-preview", contents=text)
count = response.total_tokens
```

---

## 8. Embedding

| 項目 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| Embedding API | **存在しない** | `client.embeddings.create(model, input, dimensions)` | `client.models.embed_content(model, contents, config)` |
| 代替手段 | **Gemini `gemini-embedding-001` を使用** | — | — |
| デフォルトモデル | `gemini-embedding-001`（代替） | **`text-embedding-3-small`** ← 修正 | `gemini-embedding-001` |
| 次元数 | **3072**（Gemini 経由） | **1536**（`text-embedding-3-small` デフォルト）← 修正 | 3072 |
| `task_type` | Gemini 経由なので使用可（`"retrieval_document"` 等） | **なし** | `"retrieval_query"` / `"retrieval_document"` 等（小文字） |
| `output_dimensionality` | Gemini 経由で指定可 | `dimensions=` パラメータで指定 | **必須**（指定しないとデフォルト次元になる場合あり） |
| API キー | `GOOGLE_API_KEY`（Gemini 経由） | `OPENAI_API_KEY` | `GOOGLE_API_KEY` |
| 設定形式 | dict 形式 | 直接パラメータ | **dict 形式**（`EmbedContentConfig` クラスは使用しない） ← 修正 |

```python
# ─────────────────────────────────────────────────────────────────
# Gemini Embedding（helper/helper_embedding.py 実装）
# ─────────────────────────────────────────────────────────────────
from google import genai

embed_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# 単一テキスト（task_type は省略可）
response = embed_client.models.embed_content(
    model="gemini-embedding-001",
    contents=text,
    config={
        "output_dimensionality": 3072,          # ← 必須（明示指定）
        "task_type": "retrieval_document"       # ← 小文字。EmbedContentConfig は使用しない
    }
)
vector = response.embeddings[0].values  # list[float]、3072次元

# バッチ処理（最大100件/バッチ）
response = embed_client.models.embed_content(
    model="gemini-embedding-001",
    contents=["テキスト1", "テキスト2", ...],   # ← リストを渡す
    config={
        "output_dimensionality": 3072,
        "task_type": "retrieval_document"
    }
)
vectors = [e.values for e in response.embeddings]

# ─────────────────────────────────────────────────────────────────
# OpenAI Embedding（helper/helper_embedding.py 実装）デフォルト 1536次元
# ─────────────────────────────────────────────────────────────────
from openai import OpenAI

embed_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

response = embed_client.embeddings.create(
    model="text-embedding-3-small",    # ← デフォルト（3072次元が必要な場合は text-embedding-3-large）
    input=text,
    dimensions=1536                    # ← デフォルト次元数
)
vector = response.data[0].embedding  # list[float]、1536次元

# ─────────────────────────────────────────────────────────────────
# Anthropic プロジェクト（Gemini Embedding を代替使用）
# ─────────────────────────────────────────────────────────────────
# 実装は上記 Gemini Embedding と同一
```

> **`EmbedContentConfig` クラスについて**  
> ドキュメント v1 では `genai_types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")` と記載していたが、
> 実際の `helper/helper_embedding.py` は `config={"output_dimensionality": 3072, "task_type": "retrieval_document"}` の
> **dict 形式**を使用。`task_type` は**小文字**。`EmbedContentConfig` クラスは現行コードでは使用していない。

---

## 9. モデル名・料金比較

### LLM モデル

| 用途目安 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| 最高性能 | `claude-opus-4-7` | `gpt-4o` | `gemini-3-pro-preview` |
| **推奨デフォルト** | **`claude-sonnet-4-6`** | **`gpt-4o-mini`** | **`gemini-3-flash-preview`** ← 修正 |
| 高速・低コスト | `claude-haiku-4-5-20251001` | `gpt-4o-mini` | `gemini-2.5-flash-lite` |
| ~~廃止予定~~ | — | — | ~~`gemini-2.0-flash`~~ **⚠️ 2026-06-01 廃止** |

### 料金（USD / 1K tokens）

| モデル | Input | Output | 備考 |
|---|---|---|---|
| `claude-opus-4-7` | $0.005 | $0.025 | |
| `claude-sonnet-4-6` | $0.003 | $0.015 | |
| `claude-haiku-4-5-20251001` | $0.0008 | $0.004 | |
| `gpt-4o` | $0.005 | $0.015 | |
| `gpt-4o-mini` | $0.00015 | $0.0006 | |
| `gemini-3-flash-preview` | $0.0005 | $0.003 | ← 追加 |
| `gemini-2.5-flash` | $0.0001 | $0.0004 | `helper_llm.py` 定義値 |
| `gemini-3-pro-preview` | $0.00125 | $0.010 | |
| ~~`gemini-2.0-flash`~~ | ~~$0.0001~~ | ~~$0.0004~~ | **⚠️ 2026-06-01 廃止** |

### Embedding モデル

| モデル | 次元数 | 料金（/1K tokens） | プロジェクト採用 |
|---|---|---|---|
| `gemini-embedding-001` | **3072** | 無料枠あり | anthropic / gemini プロジェクト |
| `text-embedding-3-small` | **1536** | $0.00002 | **openai プロジェクト（デフォルト）** ← 修正 |
| `text-embedding-3-large` | 3072 | $0.00013 | openai プロジェクト（3072次元が必要な場合） |

---

## 10. grace/ モジュール別 API 使用状況

### gemini_grace_agent（実コード確認済み）

| モジュール | クラス / 機能 | 使用プロバイダー | 主要 API |
|---|---|---|---|
| `grace/planner.py` | `Planner.create_plan()` | **Gemini** | `generate_content()` + `response_schema=ExecutionPlan`（方式A） |
| `grace/planner.py` | `Planner.estimate_complexity_with_llm()` | **Gemini** | `generate_content()`（テキスト生成） |
| `grace/confidence.py` | `LLMSelfEvaluator.evaluate()` | **Gemini** ← 修正 | `generate_content()`（スコア数値のみ返す） |
| `grace/confidence.py` | `LLMSelfEvaluator.evaluate_with_factors()` | **Gemini** ← 修正 | `generate_content()` + `response_schema=EvaluationResult` |
| `grace/confidence.py` | `QueryCoverageCalculator.calculate()` | **Gemini** ← 修正 | `generate_content()`（スコア数値のみ返す） |
| `grace/confidence.py` | `SourceAgreementCalculator.calculate()` | **Gemini Embedding** ← 修正 | `embed_content()` + コサイン類似度 |
| `helper/helper_llm.py` | `GeminiClient.generate_content()` | **Gemini** | `models.generate_content()`（AFC は config に含めず） |
| `helper/helper_llm.py` | `GeminiClient.generate_structured()` | **Gemini** | `models.generate_content()` + `.model_json_schema()`（方式B） |
| `helper/helper_embedding.py` | `GeminiEmbedding.embed_text()` | **Gemini** | `models.embed_content()` + dict config |

> **注**: `grace/confidence.py` の全クラスは `genai.Client()` を直接初期化しており、
> OpenAI は一切使用していない。ドキュメント v1 の `anthropic_grace_agent` の表記（OpenAI を使用）
> は anthropic_grace_agent 固有の実装であり、`gemini_grace_agent` には該当しない。

---

## 11. プロバイダー切替方法

```python
# helper/helper_llm.py の create_llm_client() で切り替え可能
from helper.helper_llm import create_llm_client

llm = create_llm_client("openai")      # → OpenAIClient（default: gpt-4o-mini）
llm = create_llm_client("gemini")      # → GeminiClient（default: gemini-2.0-flash ⚠️廃止予定→修正必要）

# 環境変数での切り替え
# export LLM_PROVIDER=openai      # openai_grace_agent
# export LLM_PROVIDER=gemini      # gemini_grace_agent

# Embedding の切り替え
from helper.helper_embedding import create_embedding_client

emb = create_embedding_client("gemini")   # → GeminiEmbedding（3072次元）
emb = create_embedding_client("openai")   # → OpenAIEmbedding（デフォルト1536次元 text-embedding-3-small）
emb = create_embedding_client("fastembed") # → FastEmbedEmbedding（384次元）
```

---

## 12. よくある移植ミスと対策

| ミス | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| システムプロンプトの場所 | `system=` トップレベル（messages の外） | `input` の先頭に `{"role":"system",...}`（Responses API） | `config.system_instruction=...` |
| `max_tokens` 省略 | **エラー**（必須） | `max_output_tokens=`（Responses API）/ 省略可（デフォルトなし注意） | `max_output_tokens` で指定（省略可） |
| ツール定義キー名 | `"input_schema"` | `"parameters"` | `"parameters"` |
| ツール結果の追記数 | **2件**（assistant + user） | **N件**（`type="function_call_output"` を input に追記） | **1件**（`chat.send_message(message=part)`） |
| `tool_use_id` / `tool_call_id` | `b.id` を `tool_use_id` に設定（必須） | `tc.id` を `call_id` に設定（必須） | **不要** |
| 終了判定 | `stop_reason == "end_turn"` | `response.status == "completed"` | `function_call` が見つからない |
| 構造化出力 | Tool Use で代替（`tool_block.input`） | **`responses.parse(text_format=Schema)` → `response.output_parsed`**（正式版） / 旧: `beta.parse()` + `message.parsed` | `response_schema=PydanticClass` 直渡し（方式A）または `.model_json_schema()`（方式B） |
| レスポンスアクセス | `response.content[0].text` | **`response.output_text`**（Responses API ヘルパー）/ 旧: `response.choices[0].message.content` | `response.text`（簡易）または `response.candidates[0].content.parts`（防御的） |
| AFC 無効化コード | **削除する**（概念なし） | **削除する**（概念なし） | `AutomaticFunctionCallingConfig(disable=True)` **必須** |
| `send_message` 引数形式 | — | — | **`message=`** キーワード引数必須（位置引数は非推奨） |
| Function Response | — | — | `types.Part.from_function_response(name=str(fn.name), ...)` **`str()` キャスト必須** |
| Embedding 設定形式 | — | — | **dict 形式** `{"output_dimensionality": 3072, "task_type": "retrieval_document"}`。`EmbedContentConfig` は使用しない |
| Embedding task_type 大小文字 | — | — | **小文字**（`"retrieval_document"` / `"retrieval_query"`） |

---

## 13. セマンティックチャンキング（chunking/ モジュール）

**実装**: `chunking/csv_text_to_chunks_text_csv.py` + `chunking/async_api_client.py`

| 項目 | Anthropic（現行） | OpenAI | Gemini |
|---|---|---|---|
| SDK | `anthropic` | `openai` | `google-genai` |
| クライアント生成 | `anthropic.Anthropic(api_key=...)` | `OpenAI(api_key=...)` | `genai.Client(api_key=...)` |
| API メソッド | `client.messages.create()` | `client.responses.create()` （旧: `client.chat.completions.create()`） | `client.models.generate_content()` |
| 構造化出力方式 | **Tool Use 強制**（`tool_choice="tool"`） | **`responses.parse(text_format=Schema)`** （旧: `beta.chat.completions.parse()`） | `response_schema=PydanticClass` 直渡し（方式A） |
| スキーマ渡し | `"input_schema": Schema.model_json_schema()` | **`text_format=Schema`** （旧: `response_format=Schema`） | `response_schema=Schema` |
| 結果取得 | `block.input` → `json.dumps()` | **`response.output_parsed`** （旧: `message.parsed`） | `response.text` → `model_validate_json()` |
| 非同期化 | `asyncio.to_thread(client.messages.create, ...)` | `asyncio.to_thread(client.responses.create, ...)` | `asyncio.to_thread(client.models.generate_content, ...)` |
| 並列制御 | `asyncio.Semaphore(max_workers)` | 同左 | 同左 |
| 正常終了検出 | `stop_reason == "tool_use"` | `response.status == "completed"` | 通常の `generate_content()` と同様 |
| 切断検出 | `stop_reason == "max_tokens"` → リトライ | `stop_reason == "max_output_tokens"` → リトライ | `finish_reason == MAX_TOKENS` → リトライ |
| レート制限検出 | `"429"` / `"rate_limit"` / `"overloaded"` → 30秒待機 | `RateLimitError` → バックオフ | `"429"` / `"quota"` → 待機 |

---

## 14. Q/A自動生成（qa_generation/ + Celery）

| 項目 | Anthropic（現行） | OpenAI | Gemini |
|---|---|---|---|
| SDK | `anthropic`（`helper_llm` 経由） | `openai`（`helper_llm` 経由） | `google-genai`（`helper_llm` 経由） |
| LLM クライアント生成 | `create_llm_client("anthropic")` | `create_llm_client("openai")` | `create_llm_client("gemini")` |
| API メソッド（テキスト生成） | `llm.generate_content(prompt, model, temperature, max_tokens)` | 同左（内部は `chat.completions.create`） | 同左（内部は `models.generate_content`） |
| 処理フロー | `analyze_chunk()` → `generate_qa_pairs()` | 同左 | 同左 |
| 並列処理 | **Celery** + `apply_async(args=...)` | 同左 | 同左 |
| API キー | `ANTHROPIC_API_KEY` | `OPENAI_API_KEY` | `GOOGLE_API_KEY` |

---

## 15. Qdrant 登録・検索

### 15-1. Qdrant 登録フロー

| 項目 | Anthropic プロジェクト（現行） | OpenAI プロジェクト | Gemini プロジェクト |
|---|---|---|---|
| Embedding プロバイダー | **Gemini `gemini-embedding-001`** | OpenAI `text-embedding-3-small`（デフォルト）← 修正 | Gemini `gemini-embedding-001` |
| Embedding クライアント | `create_embedding_client(provider="gemini")` | `create_embedding_client(provider="openai")` | `create_embedding_client(provider="gemini")` |
| Embedding API | `embed_client.embed_texts(texts, batch_size)` | 同左 | 同左 |
| `task_type`（登録時） | `"retrieval_document"`（小文字） ← 修正 | **なし** | `"retrieval_document"`（小文字） ← 修正 |
| 次元数 | **3072** | **1536**（`text-embedding-3-small`） ← 修正 | 3072 |
| Qdrant SDK | `qdrant_client.QdrantClient` | 同左 | 同左 |
| 登録メソッド | `client.upsert(collection_name, points)` | 同左 | 同左 |
| ベクトル構造 | `models.PointStruct(id, vector, payload)` | 同左 | 同左 |

---

## 不足情報・要確認事項

以下の項目は実コードから確認できず、情報が不足している。

| 項目 | 状況 | 対策 |
|---|---|---|
| `helper_llm.py` の `GeminiClient` デフォルトモデルが `gemini-2.0-flash`（廃止予定） | **要緊急修正** | `"gemini-3-flash-preview"` に変更 |
| `grace/confidence.py` の LLMSelfEvaluator で AFC 無効化が適用済みか | `evaluate()` / `evaluate_with_factors()` で `AutomaticFunctionCallingConfig(disable=True)` あり ✅ 確認済み | — |
| `openai_grace_agent` の `grace/confidence.py` 実装（`create_llm_client("openai")` コメント） | `gemini_grace_agent` では Gemini 使用。`anthropic_grace_agent` の実装詳細は要別途確認 | anthropic_grace_agent のコード確認 |
| `chunking/async_api_client.py` の Gemini 版実装 | 現行は Anthropic 実装。Gemini 版への切り替えスクリプトは未確認 | gemini_grace_agent の chunking/ を確認 |

---

## 改訂履歴

| 版 | 日付 | 変更内容 |
|---|---|---|
| v1 | 2026-05-10 | 初版作成 |
| v2 | 2026-05-11 | Gemini 各節を `gemini_grace_agent` 実コード（`grace/planner.py`、`grace/confidence.py`、`helper/helper_llm.py`、`helper/helper_embedding.py`）で検証。7項目を修正。不足情報節を追加。 |
| v3 | 2026-05-18 | **OpenAI Responses API 移行対応**。`client.chat.completions.create()` → `client.responses.create()`、`client.beta.chat.completions.parse()` → `client.responses.parse(text_format=Schema)`、結果取得 `message.parsed` → `response.output_parsed`、レスポンス取得 `response.choices[0].message.content` → `response.output_text`、終了判定 `finish_reason=="stop"` → `response.status=="completed"`、ツール結果追記形式の更新、会話管理の `previous_response_id` 方式追記。早見表A・§1・§2・§3・§4・§12・§13 を更新。 |
