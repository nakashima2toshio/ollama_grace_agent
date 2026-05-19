# LLM API 3プロバイダー完全対比表

**対象プロジェクト**

| プロジェクト | LLM | Embedding |
|---|---|---|
| `anthropic_grace_agent` | Anthropic `claude-sonnet-4-6` | Gemini `gemini-embedding-001` |
| `openai_grace_agent` | OpenAI `gpt-4o` / `gpt-4o-mini` | OpenAI `text-embedding-3-large` |
| `gemini_grace_agent` | Gemini `gemini-2.5-flash` | Gemini `gemini-embedding-001` |

**参照実装**: `helper/helper_llm.py`（`AnthropicClient` / `OpenAIClient` / `GeminiClient`）
**作成日**: 2026-05-10

---

## 1. クライアント初期化

| 項目 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| SDK パッケージ | `anthropic` | `openai` | `google-genai` |
| インポート | `import anthropic` | `from openai import OpenAI` | `from google import genai` |
| クライアント生成 | `anthropic.Anthropic(api_key=...)` | `OpenAI(api_key=...)` | `genai.Client(api_key=...)` |
| API キー環境変数 | `ANTHROPIC_API_KEY` | `OPENAI_API_KEY` | `GOOGLE_API_KEY` |
| チャットセッション | **なし**（ステートレス設計） | **なし**（ステートレス設計） | `client.chats.create(model, config)` |

```python
# Anthropic
import anthropic
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# OpenAI
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Gemini
from google import genai
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
```

---

## 2. テキスト生成（シングルターン）

| 項目 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| メソッド | `client.messages.create()` | `client.chat.completions.create()` | `client.models.generate_content()` |
| プロンプト引数 | `messages=[{"role":"user","content":prompt}]` | `messages=[{"role":"user","content":prompt}]` | `contents=prompt` |
| システムプロンプト | `system="..."` **（messages の外・トップレベル）** | `messages` 先頭に `{"role":"system","content":"..."}` を挿入 | `config=GenerateContentConfig(system_instruction="...")` |
| 出力トークン上限 | `max_tokens=...` **（必須）** | `max_completion_tokens=...`（gpt-4o系） | `config.max_output_tokens=...` |
| 温度パラメータ | `temperature=...`（直接パラメータ） | `temperature=...`（直接パラメータ） | `config=GenerateContentConfig(temperature=...)` |
| レスポンス取得 | `response.content[0].text` | `response.choices[0].message.content` | `response.text` |
| AFC 無効化 | **不要**（概念なし） | **不要**（概念なし） | `AutomaticFunctionCallingConfig(disable=True)` 必要 |

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

# OpenAI
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "あなたは..."},  # messages の中
        {"role": "user",   "content": prompt}
    ],
    max_completion_tokens=4096,
    temperature=0.7,
)
answer = response.choices[0].message.content

# Gemini
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
    config=genai_types.GenerateContentConfig(
        system_instruction="あなたは...",
        max_output_tokens=4096,
        temperature=0.7,
        automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True)
    )
)
answer = response.text
```

---

## 3. 会話履歴の管理

| 項目 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| 管理方式 | `messages` リストを**自前管理** | `messages` リストを**自前管理** | `chat` オブジェクトが**自動管理** |
| 初期化 | `messages = []` | `messages = []` | `client.chats.create(model, config)` |
| ユーザー追加 | 手動で `messages.append({"role":"user",...})` | 手動で `messages.append({"role":"user",...})` | `chat.send_message(input)` で自動追加 |
| アシスタント追加 | 手動で `messages.append({"role":"assistant",...})` | 手動で `messages.append({"role":"assistant",...})` | 自動（chat オブジェクトが保持） |
| ロール種別 | `"user"` / `"assistant"` | `"system"` / `"user"` / `"assistant"` / `"tool"` | `parts` 内で自動区別 |
| 再呼び出し | `client.messages.create(messages=全履歴)` | `client.chat.completions.create(messages=全履歴)` | `chat.send_message(次のメッセージ)` |

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
res1 = chat.send_message("質問1")
res2 = chat.send_message("続き")   # 履歴は chat オブジェクトが保持
```

---

## 4. 構造化出力（最大の差異）

| 項目 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| 方式 | **Tool Use** で代替（`input_schema` にスキーマを渡す） | **Structured Outputs**（`beta.chat.completions.parse`） | `response_schema=PydanticClass` を直接渡す |
| スキーマ形式 | `"input_schema": PydanticClass.model_json_schema()` | `response_format=PydanticClass`（クラスをそのまま） | `response_schema=PydanticClass.model_json_schema()` |
| レスポンス取得 | `tool_block.input` → `model_validate(tool_block.input)` | `response.choices[0].message.parsed`（SDK が自動パース） | `response.text` → `model_validate_json(response.text)` |
| JSON 解析 | SDK が自動パース（`model_validate()` で型安全） | SDK が自動パース（`message.parsed` で型安全） | 手動パース（`JSONDecodeError` 発生リスクあり） |
| 終了検出 | `response.stop_reason == "tool_use"` | `response.choices[0].finish_reason == "stop"` | 通常の `generate_content()` と同様 |

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

# OpenAI（Structured Outputs）
response = client.beta.chat.completions.parse(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "..."},
        {"role": "user",   "content": prompt}
    ],
    response_format=ExecutionPlan,     # Pydantic クラスを直接渡す
    max_completion_tokens=4096,
)
plan = response.choices[0].message.parsed  # ExecutionPlan インスタンスが直接返る

# Gemini（response_schema 直渡し）
response = client.models.generate_content(
    model=model_name,
    contents=prompt,
    config=genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ExecutionPlan.model_json_schema(),
    )
)
plan = ExecutionPlan.model_validate_json(response.text)
```

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
tools = genai_types.Tool(function_declarations=[
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
| ツール引数取得 | `b.input`（`dict` が直接返る） | `json.loads(tc.function.arguments)` | `fn.args` |
| **ツール ID** | **`b.id`**（`tool_result` 返送時に必須） | `tc.id`（`tool_call_id` として必須） | なし |
| **ツール結果の送信** | **2件追記が必須**（① assistant + ② user/tool_result） | tool ごとに `{"role":"tool",...}` を **複数追記**（1件ずつ） | `Part.from_function_response()` + `chat.send_message(part)` **1回** |
| 複数ツール同時 | 全件を同一 `user` メッセージにまとめる | tool 1件ごとに独立した `"role":"tool"` メッセージ | 1件ずつ処理 |
| **終了判定** | `stop_reason == "end_turn"` | `finish_reason == "stop"` | `function_call` が見つからない |

```python
# ─────────────────────────────────────────────────────────
# Anthropic（2件追記が必須）
# ─────────────────────────────────────────────────────────
text, tool_calls, stop_reason = llm.generate_with_tools(
    messages=messages, tools=tools, system=system_prompt, max_tokens=4096
)

if stop_reason == "tool_use" and tool_calls:
    # ① assistant ターンを追記（response.content をそのまま）
    messages.append({"role": "assistant", "content": response.content})

    tool_results = []
    for tc in tool_calls:
        result = execute_tool(tc["name"], tc["input"])
        tool_results.append({
            "type"       : "tool_result",
            "tool_use_id": tc["id"],    # ← b.id と必ず一致させる（必須）
            "content"    : str(result)
        })

    # ② 全ツール結果を同一 user メッセージにまとめて追記
    messages.append({"role": "user", "content": tool_results})
else:
    final_answer = text  # stop_reason == "end_turn" で終了

# ─────────────────────────────────────────────────────────
# OpenAI（tool ごとに独立した role:"tool" メッセージ）
# ─────────────────────────────────────────────────────────
response = client.chat.completions.create(model=..., messages=messages, tools=tools)
msg = response.choices[0].message

if response.choices[0].finish_reason == "tool_calls":
    # assistant ターンを追記
    messages.append({"role": "assistant", "content": msg.content,
                     "tool_calls": msg.tool_calls})

    for tc in msg.tool_calls:
        args = json.loads(tc.function.arguments)
        result = execute_tool(tc.function.name, args)
        # tool 1件ごとに独立した role:"tool" メッセージ
        messages.append({
            "role"        : "tool",
            "tool_call_id": tc.id,      # ← tc.id と必ず一致させる（必須）
            "content"     : str(result)
        })
else:
    final_answer = msg.content  # finish_reason == "stop" で終了

# ─────────────────────────────────────────────────────────
# Gemini（chat 経由で 1 回送信）
# ─────────────────────────────────────────────────────────
response = chat.send_message(message=augmented_input)
for part in response.candidates[0].content.parts:
    if hasattr(part, "function_call") and part.function_call:
        fn = part.function_call
        result = execute_tool(fn.name, fn.args)
        # 1 件ずつ Part.from_function_response() で返す
        part_response = genai_types.Part.from_function_response(
            name=fn.name, response={"result": result}
        )
        response = chat.send_message(message=part_response)  # 1回で送信
    else:
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

# Gemini
response = client.models.count_tokens(model="gemini-2.5-flash", contents=text)
count = response.total_tokens
```

---

## 8. Embedding

| 項目 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| Embedding API | **存在しない** | `client.embeddings.create(model, input, dimensions)` | `client.models.embed_content(model, contents, config)` |
| 代替手段 | **Gemini `gemini-embedding-001` を使用** | — | — |
| デフォルトモデル | `gemini-embedding-001`（代替） | `text-embedding-3-large` | `gemini-embedding-001` |
| 次元数 | **3072**（Gemini 経由） | 3072（`dimensions=3072`） | 3072 |
| `task_type` | Gemini 経由なので使用可 | **なし** | `retrieval_query` / `retrieval_document` 等 |
| API キー | `GOOGLE_API_KEY`（Gemini 経由） | `OPENAI_API_KEY` | `GOOGLE_API_KEY` |

```python
# Anthropic プロジェクト（Gemini Embedding を使用）
from google import genai
embed_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
response = embed_client.models.embed_content(
    model="gemini-embedding-001",
    contents=text,
    config=genai_types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
)
vector = response.embeddings[0].values  # 3072次元

# OpenAI Embedding
from openai import OpenAI
embed_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
response = embed_client.embeddings.create(
    model="text-embedding-3-large",
    input=text,
    dimensions=3072
)
vector = response.data[0].embedding  # 3072次元

# Gemini Embedding
from google import genai
embed_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
response = embed_client.models.embed_content(
    model="gemini-embedding-001",
    contents=text,
    config=genai_types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
)
vector = response.embeddings[0].values  # 3072次元
```

---

## 9. モデル名・料金比較

### LLM モデル

| 用途目安 | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| 最高性能 | `claude-opus-4-7` | `gpt-4o` | `gemini-3-pro-preview` |
| **推奨デフォルト** | **`claude-sonnet-4-6`** | **`gpt-4o-mini`** | **`gemini-2.5-flash`** |
| 高速・低コスト | `claude-haiku-4-5-20251001` | `gpt-4o-mini` | `gemini-2.0-flash` |

### 料金（USD / 1K tokens）

| モデル | Input | Output |
|---|---|---|
| `claude-opus-4-7` | $0.005 | $0.025 |
| `claude-sonnet-4-6` | $0.003 | $0.015 |
| `claude-haiku-4-5-20251001` | $0.0008 | $0.004 |
| `gpt-4o` | $0.005 | $0.015 |
| `gpt-4o-mini` | $0.00015 | $0.0006 |
| `gemini-2.5-flash` | $0.0001 | $0.0004 |
| `gemini-3-pro-preview` | $0.00125 | $0.010 |

### Embedding モデル

| モデル | 次元数 | 料金（/1K tokens） | 備考 |
|---|---|---|---|
| `gemini-embedding-001` | **3072** | 無料枠あり | anthropic / gemini プロジェクト採用 |
| `text-embedding-3-large` | **3072** | $0.00013 | openai プロジェクト採用 |
| `text-embedding-3-small` | 1536 | $0.00002 | 軽量・低コスト |

---

## 10. grace/ モジュール別 API 使用状況（anthropic_grace_agent）

| モジュール | クラス / 機能 | 使用プロバイダー | 主要 API |
|---|---|---|---|
| `grace/planner.py` | `Planner.create_plan()` | **Anthropic** | `generate_structured()` → Tool Use |
| `grace/planner.py` | `Planner.estimate_complexity_with_llm()` | **Anthropic** | `generate_content()` |
| `grace/tools.py` | `ReasoningTool.execute()` | **Anthropic** | `generate_content()` |
| `grace/tools.py` | `AskUserTool` ツール定義 | — | `"input_schema"` キー形式 |
| `grace/confidence.py` | `LLMSelfEvaluator.evaluate()` | **OpenAI** | `generate_content()` |
| `grace/confidence.py` | `LLMSelfEvaluator.evaluate_with_factors()` | **OpenAI** | `generate_structured()` → `beta.parse()` |
| `grace/confidence.py` | `QueryCoverageCalculator.calculate()` | **OpenAI** | `generate_content()` |
| `grace/confidence.py` | `SourceAgreementCalculator.calculate()` | **OpenAI Embedding** | `embed_text()` |
| `services/agent_service.py` | `ReActAgent` ReAct ループ | **Anthropic** | `generate_with_tools()` |
| `helper/helper_embedding.py` | `create_embedding_client()` | **Gemini** / OpenAI | `embed_text()` / `embed_texts()` |

> **Note**: `confidence.py` の `LLMSelfEvaluator` と `QueryCoverageCalculator` は
> コード上 `create_llm_client("openai")` を使用（`# [MIGRATION anthropic→openai]` コメント参照）。

---

## 11. プロバイダー切替方法

```python
# helper/helper_llm.py の create_llm_client() で切り替え可能
from helper.helper_llm import create_llm_client

llm = create_llm_client("anthropic")   # → AnthropicClient
llm = create_llm_client("openai")      # → OpenAIClient
llm = create_llm_client("gemini")      # → GeminiClient

# 環境変数での切り替え
# export LLM_PROVIDER=anthropic   # anthropic_grace_agent
# export LLM_PROVIDER=openai      # openai_grace_agent
# export LLM_PROVIDER=gemini      # gemini_grace_agent

# Embedding の切り替え
from helper.helper_embedding import create_embedding_client

emb = create_embedding_client("gemini")   # → GeminiEmbedding（3072次元）
emb = create_embedding_client("openai")   # → OpenAIEmbedding（3072次元）
```

---

## 12. よくある移植ミスと対策

| ミス | Anthropic | OpenAI | Gemini |
|---|---|---|---|
| システムプロンプトの場所 | `system=` トップレベル（messages の外） | `messages` 先頭に `{"role":"system",...}` | `config.system_instruction=...` |
| `max_tokens` 省略 | **エラー**（必須） | 省略可（デフォルトなし注意） | `max_output_tokens` で指定（省略可） |
| ツール定義キー名 | `"input_schema"` | `"parameters"` | `"parameters"` |
| ツール結果の追記数 | **2件**（assistant + user） | **N件**（tool 1件ごと） | **1件**（`chat.send_message(part)`） |
| `tool_use_id` / `tool_call_id` | `b.id` を `tool_use_id` に設定（必須） | `tc.id` を `tool_call_id` に設定（必須） | **不要** |
| 終了判定 | `stop_reason == "end_turn"` | `finish_reason == "stop"` | `function_call` が見つからない |
| 構造化出力 | Tool Use で代替（`tool_block.input`） | `beta.parse()` + `message.parsed` | `response_schema=` 直渡し |
| AFC 無効化コード | **削除する**（概念なし） | **削除する**（概念なし） | `AutomaticFunctionCallingConfig(disable=True)` |

---

## 13. セマンティックチャンキング（chunking/ モジュール）

**実装**: `chunking/csv_text_to_chunks_text_csv.py` + `chunking/async_api_client.py`

| 項目 | Anthropic（現行） | OpenAI | Gemini |
|---|---|---|---|
| SDK | `anthropic` | `openai` | `google-genai` |
| クライアント生成 | `anthropic.Anthropic(api_key=...)` | `OpenAI(api_key=...)` | `genai.Client(api_key=...)` |
| API メソッド | `client.messages.create()` | `client.chat.completions.create()` | `client.models.generate_content()` |
| 構造化出力方式 | **Tool Use 強制**（`tool_choice="tool"`） | `beta.chat.completions.parse()` | `response_schema=` 直渡し |
| スキーマ渡し | `"input_schema": Schema.model_json_schema()` | `response_format=Schema` | `response_schema=Schema.model_json_schema()` |
| 結果取得 | `block.input` → `json.dumps()` | `message.parsed` | `response.text` → `model_validate_json()` |
| 非同期化 | `asyncio.to_thread(client.messages.create, ...)` | `asyncio.to_thread(client.chat.completions.create, ...)` | `asyncio.to_thread(client.models.generate_content, ...)` |
| 並列制御 | `asyncio.Semaphore(max_workers)` | 同左 | 同左 |
| 正常終了検出 | `stop_reason == "tool_use"` | `finish_reason == "stop"` | 通常の `generate_content()` と同様 |
| 切断検出 | `stop_reason == "max_tokens"` → リトライ | `finish_reason == "length"` → リトライ | `finish_reason == MAX_TOKENS` → リトライ |
| レート制限検出 | `"429"` / `"rate_limit"` / `"overloaded"` → 30秒待機 | `RateLimitError` → バックオフ | `"429"` / `"quota"` → 待機 |

```python
# chunking/async_api_client.py（現行 Anthropic 実装）

class AsyncAPIClient:
    def __init__(self, api_key: str, max_workers: int = 8, max_output_tokens: int = 8192):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.semaphore = asyncio.Semaphore(max_workers)  # 並列数制御

    def _build_tool(self, response_schema: Type[BaseModel]) -> dict:
        # Pydantic モデル → Tool Use 定義（Anthropic 形式）
        return {
            "name"        : "structured_output",
            "description" : f"Return the structured result as {response_schema.__name__}",
            "input_schema": response_schema.model_json_schema(),  # ← "input_schema" キー
        }

    async def generate_content(self, model, contents, response_schema, task_id=None):
        async with self.semaphore:
            # 同期 API を asyncio.to_thread でスレッド化
            response = await asyncio.to_thread(
                self.client.messages.create,
                model=model,
                max_tokens=self.max_output_tokens,
                tools=[self._build_tool(response_schema)],
                tool_choice={"type": "tool", "name": "structured_output"},  # Tool Use 強制
                messages=[{"role": "user", "content": contents}],
            )

            # 切断チェック
            if response.stop_reason == "max_tokens":
                raise ValueError("Response truncated")  # → リトライ

            # tool_use ブロックから JSON 文字列を抽出
            for block in response.content:
                if block.type == "tool_use":
                    return json.dumps(block.input, ensure_ascii=False)
```

### 3段階チャンキングパイプライン

| Step | 処理内容 | 入力 | 出力 | API呼び出し |
|---|---|---|---|---|
| **Step 1** | 階層構造化（段落分割） | 生テキスト（ブロック単位） | 段落リスト | `StructuralResult` を Tool Use で取得 |
| **Step 2** | 意味的チャンキング | 段落リスト | チャンクリスト | `StructuralResult` を Tool Use で取得 |
| **Step 3** | 文脈連続性チェック | チャンクペア | 結合済みチャンクリスト | `ContinuityResult` を Tool Use で取得 |

---

## 14. Q/A自動生成（qa_generation/ + Celery）

**実装**: `qa_generation/smart_qa_generator.py` + `celery_tasks.py` + `qa_generation/pipeline.py`

| 項目 | Anthropic（現行） | OpenAI | Gemini |
|---|---|---|---|
| SDK | `anthropic`（`helper_llm` 経由） | `openai`（`helper_llm` 経由） | `google-genai`（`helper_llm` 経由） |
| LLM クライアント生成 | `create_llm_client("anthropic")` | `create_llm_client("openai")` | `create_llm_client("gemini")` |
| API メソッド（テキスト生成） | `llm.generate_content(prompt, model, temperature, max_tokens)` | 同左（内部は `chat.completions.create`） | 同左（内部は `models.generate_content`） |
| 処理フロー | `analyze_chunk()` → `generate_qa_pairs()` | 同左 | 同左 |
| 並列処理 | **Celery** + `apply_async(args=...)` | 同左 | 同左 |
| API キー | `ANTHROPIC_API_KEY` | `OPENAI_API_KEY` | `GOOGLE_API_KEY` |

```python
# qa_generation/smart_qa_generator.py（現行 Anthropic 実装）

class SmartQAGenerator:
    def __init__(self, model: str = "claude-sonnet-4-6", api_key: Optional[str] = None):
        # [MIGRATION] genai.Client() → create_llm_client("anthropic")
        self.llm = create_llm_client("anthropic", default_model=model)

    def _generate_content(self, prompt: str, temperature: float = 0.1) -> str:
        # [MIGRATION] client.models.generate_content() → llm.generate_content()
        return self.llm.generate_content(
            prompt=prompt,
            model=self.model,
            temperature=temperature,
            max_tokens=4096,
        )

    def analyze_chunk(self, chunk_text: str) -> Dict:
        """Step 1: チャンク分析（重要度・トピック数・Q/A生成数を決定）"""
        prompt = ANALYZE_PROMPT.format(chunk_text=chunk_text)
        text = self._generate_content(prompt, temperature=0.1)
        return json.loads(text)   # → {"num_qa": 3, "importance": "high", ...}

    def generate_qa_pairs(self, chunk_text: str, analysis: Dict) -> List[Dict]:
        """Step 2: Q/Aペア生成"""
        prompt = QA_GENERATION_PROMPT.format(
            chunk_text=chunk_text,
            num_qa=analysis.get("num_qa", 3)
        )
        text = self._generate_content(prompt, temperature=0.3)
        return json.loads(text)   # → [{"question": ..., "answer": ...}, ...]


# celery_tasks.py（Celery 並列処理）
@celery_app.task(name='generate_qa_for_chunk')
def generate_qa_for_chunk_task(chunk, config, model, use_smart_generation=True):
    generator = SmartQAGenerator(model=model)
    return generator.process_chunk(chunk["text"])

# 並列投入
tasks = []
for chunk in chunks:
    task = generate_qa_for_chunk_task.apply_async(
        args=(chunk, config, model, use_smart_generation)
    )
    tasks.append(task)
```

---

## 15. Qdrant 登録・検索

**実装**: `services/qdrant_service.py` + `qdrant_client_wrapper.py` + `make_qa_register_qdrant.py`

### 15-1. Qdrant 登録フロー

| 項目 | Anthropic プロジェクト（現行） | OpenAI プロジェクト | Gemini プロジェクト |
|---|---|---|---|
| Embedding プロバイダー | **Gemini `gemini-embedding-001`** | OpenAI `text-embedding-3-large` | Gemini `gemini-embedding-001` |
| Embedding クライアント | `create_embedding_client(provider="gemini")` | `create_embedding_client(provider="openai")` | `create_embedding_client(provider="gemini")` |
| Embedding API | `embed_client.embed_texts(texts, batch_size)` | 同左 | 同左 |
| `task_type`（登録時） | `"RETRIEVAL_DOCUMENT"` | **なし** | `"RETRIEVAL_DOCUMENT"` |
| 次元数 | **3072** | 3072 | 3072 |
| Qdrant SDK | `qdrant_client.QdrantClient` | 同左 | 同左 |
| 登録メソッド | `client.upsert(collection_name, points)` | 同左 | 同左 |
| ベクトル構造 | `models.PointStruct(id, vector, payload)` | 同左 | 同左 |
| API キー（登録） | `ANTHROPIC_API_KEY`（LLM） + `GOOGLE_API_KEY`（Embedding） | `OPENAI_API_KEY`（LLM + Embedding） | `GOOGLE_API_KEY`（LLM + Embedding） |

```python
# services/qdrant_service.py（現行: Gemini Embedding + Qdrant upsert）

def embed_texts_for_qdrant(
    texts: List[str], model: str = "gemini-embedding-001", batch_size: int = 100
) -> List[List[float]]:
    # [REVERT] OpenAI → Gemini に戻す（OpenAI Tier制限問題のため）
    embedding_client = create_embedding_client(provider="gemini")
    dims = get_embedding_dimensions("gemini")   # 3072

    valid_texts = [t for t in texts if t and t.strip()]
    valid_vecs = embedding_client.embed_texts(valid_texts, batch_size=batch_size)
    return valid_vecs

def upsert_points_to_qdrant(client: QdrantClient, collection_name: str, points):
    client.upsert(collection_name=collection_name, points=points, wait=True)
```

### 15-2. Qdrant 検索フロー

| 項目 | Anthropic プロジェクト（現行） | OpenAI プロジェクト | Gemini プロジェクト |
|---|---|---|---|
| クエリ Embedding | **Gemini `gemini-embedding-001`** | OpenAI `text-embedding-3-large` | Gemini `gemini-embedding-001` |
| クライアント生成 | `create_embedding_client(provider="gemini", dims=3072)` | `create_embedding_client(provider="openai", dims=3072)` | `create_embedding_client(provider="gemini", dims=3072)` |
| `task_type`（検索時） | `"retrieval_query"` | **なし** | `"retrieval_query"` |
| Dense 検索 | `client.query_points(collection, query=vector, limit=N)` | 同左 | 同左 |
| Hybrid 検索 | `client.query_points(prefetch=[Dense+Sparse], query=FusionQuery(RRF))` | 同左 | 同左 |
| スコア自動選択 | 次元数 3072 → Gemini / 1536 → OpenAI（自動判定） | 同左 | 同左 |

```python
# services/qdrant_service.py（現行: 検索クエリ Embedding + Qdrant query）

def embed_query_for_search(
    query: str, model: str = "gemini-embedding-001", dims: Optional[int] = None
) -> List[float]:
    """検索クエリをベクトル化（プロバイダー自動選択）"""
    # 次元数またはモデル名からプロバイダーを自動判定
    provider = "gemini"           # デフォルト
    if dims == 1536:
        provider = "openai"
    elif "text-embedding-3" in (model or ""):
        provider = "openai"

    embedding_client = create_embedding_client(provider=provider, dims=dims)
    task_type = "retrieval_query" if provider == "gemini" else None  # Gemini のみ task_type 指定
    vector = embedding_client.embed_text(query, task_type=task_type)
    return vector


# qdrant_client_wrapper.py（3段階フォールバック検索）

def search_collection(client, collection_name, query_vector, sparse_vector=None, limit=5):
    """
    Stage 1: Hybrid Search (Dense + Sparse, RRF Fusion)  ← sparse_vector が渡された場合
    Stage 2: Dense Search のみ                            ← Sparse Vector 未設定コレクション
    Stage 3: エラー時フォールバック
    """
    if sparse_vector:
        # Hybrid Search（RRF Fusion）
        response = client.query_points(
            collection_name=collection_name,
            prefetch=[
                models.Prefetch(query=query_vector, using="dense", limit=limit * 2),
                models.Prefetch(query=sparse_vector, using="text-sparse", limit=limit * 2),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
        )
    else:
        # Dense Search のみ
        response = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
        )
    return [{"score": h.score, "payload": h.payload} for h in response.points]
```

### 15-3. エンドツーエンドのデータフロー

```
[テキスト/CSV]
    ↓ csv_text_to_chunks_text_csv.py
[セマンティックチャンク]  ← Anthropic API (messages.create + Tool Use)
    ↓ make_qa_register_qdrant.py (Phase 1)
[Q/Aペア CSV]           ← Anthropic API (generate_content) + Celery
    ↓ make_qa_register_qdrant.py (Phase 2)
[Qdrant 登録]           ← Gemini Embedding (embed_texts) + QdrantClient.upsert()
    ↓
[Qdrant コレクション]   ← 3072次元ベクトル
    ↓ qdrant_client_wrapper.search_collection()
[検索結果]              ← Gemini Embedding (embed_text, task_type="retrieval_query") + QdrantClient.query_points()
```

### 15-4. 各フェーズの必要 API キー

| フェーズ | 必要 API キー | 用途 |
|---|---|---|
| チャンキング | `ANTHROPIC_API_KEY` | Anthropic `messages.create()` (Tool Use) |
| Q/A生成 | `ANTHROPIC_API_KEY` | Anthropic `messages.create()` (テキスト生成) |
| Qdrant 登録 | `GOOGLE_API_KEY` / `GEMINI_API_KEY` | Gemini Embedding (`embed_texts`) |
| 検索クエリ | `GOOGLE_API_KEY` / `GEMINI_API_KEY` | Gemini Embedding (`embed_text`, `retrieval_query`) |

---

*本ドキュメントは `anthropic_grace_agent` の `helper/helper_llm.py` 実装に基づく。*
*3プロジェクト横断で移植・切り替えを行う際の技術参照資料として使用する。*
