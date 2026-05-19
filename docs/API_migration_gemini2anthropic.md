# Anthropic API 移植完了報告書

**プロジェクト**: `anthropic_grace_agent`
**移植元**: Gemini API (`google.genai`)
**移植先**: Anthropic API (`anthropic`) + OpenAI Embedding API
**作成日**: 2026-04-20
**完了日**: 2026-04-25

---

## 移植完了サマリー

| 項目 | 内容 |
|---|---|
| 移植対象ファイル | **29 ファイル**（変更不要 5 ファイル含む） |
| 移植実施ファイル | **24 ファイル** |
| 変更不要ファイル | 5 ファイル（Qdrant UI 系・間接変更のみ） |
| Embedding | Anthropic に Embedding API なし → **OpenAI `text-embedding-3-large` (3072次元)** |
| Qdrant 互換性 | Gemini / OpenAI ともに **3072次元** → **コレクション再作成不要** |

---

## 第1部　Gemini API vs Anthropic API 完全対比表

---

### 1-1. クライアント初期化

| 項目 | Gemini（移植元） | Anthropic（移植先） |
|---|---|---|
| SDK | `google-genai` | `anthropic` |
| インポート | `from google import genai` | `import anthropic` |
| クライアント生成 | `genai.Client(api_key=...)` | `anthropic.Anthropic(api_key=...)` |
| API キー環境変数 | `GOOGLE_API_KEY` / `GEMINI_API_KEY` | `ANTHROPIC_API_KEY` |
| チャットセッション | `client.chats.create(model, config)` | **なし（ステートレス設計）** |

```python
# Gemini
from google import genai
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# Anthropic
import anthropic
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
```

---

### 1-2. テキスト生成（シングルターン）

| 項目 | Gemini | Anthropic |
|---|---|---|
| メソッド | `client.models.generate_content()` | `client.messages.create()` |
| プロンプト引数名 | `contents=prompt` | `messages=[{"role":"user","content":prompt}]` |
| システムプロンプト | `config.system_instruction=...` | `system="..."` パラメータ（messages 外） |
| 温度パラメータ | `config=types.GenerateContentConfig(temperature=...)` | `temperature=...`（直接パラメータ） |
| 出力トークン上限 | `config.max_output_tokens=...` | `max_tokens=...`（**必須**） |
| レスポンス取得 | `response.text` | `response.content[0].text` |
| AFC 無効化 | `AutomaticFunctionCallingConfig(disable=True)` 必要 | **不要** |

```python
# Gemini
response = client.models.generate_content(
    model="gemini-3-flash",
    contents=prompt,
    config=types.GenerateContentConfig(
        system_instruction="あなたは...",
        temperature=0.7,
        max_output_tokens=4096,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
    )
)
answer = response.text

# Anthropic
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=4096,               # 必須
    system="あなたは...",           # messages の外
    temperature=0.7,
    messages=[{"role": "user", "content": prompt}]
)
answer = response.content[0].text
```

---

### 1-3. 会話履歴の管理

| 項目 | Gemini | Anthropic |
|---|---|---|
| 管理方式 | `chat` オブジェクトが**自動管理** | `messages` リストを**自前管理** |
| 初期化 | `client.chats.create(model, config)` | `messages = []` |
| メッセージ追加 | `chat.send_message(input)` で自動追加 | 手動で `messages.append(...)` |
| ロール種別 | `parts` 内で自動区別 | `{"role": "user" / "assistant", "content": ...}` で明示 |
| 再呼び出し | `chat.send_message(次のメッセージ)` | `client.messages.create(messages=全履歴)` |

```python
# Gemini（chat が履歴を自動管理）
chat = client.chats.create(model=model_name, config=config)
response1 = chat.send_message("質問1")
response2 = chat.send_message("続き")

# Anthropic（自前で管理）
messages = []
messages.append({"role": "user", "content": "質問1"})
response1 = client.messages.create(model=model_name, messages=messages, max_tokens=4096)
messages.append({"role": "assistant", "content": response1.content[0].text})
messages.append({"role": "user", "content": "続き"})
response2 = client.messages.create(model=model_name, messages=messages, max_tokens=4096)
```

---

### 1-4. 構造化出力（最大の差異）

| 項目 | Gemini | Anthropic |
|---|---|---|
| 方式 | `response_schema=PydanticClass` を直接渡す | **Tool Use** で代替 |
| スキーマ形式 | Pydantic クラスを直接渡す | `input_schema=PydanticClass.model_json_schema()` |
| レスポンス取得 | `response.text` → `model_validate_json()` | `tool_block.input` → `model_validate()` |
| JSON 解析 | 手動パース必要（エラー多発） | SDK が自動パース |

```python
# Gemini（Pydantic 直渡し）
response = client.models.generate_content(
    model=model_name,
    contents=prompt,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ExecutionPlan,
    )
)
plan = ExecutionPlan.model_validate_json(response.text)

# Anthropic（Tool Use で代替）
tool_def = {
    "name"        : "structured_output",
    "description" : "Return structured data",
    "input_schema": ExecutionPlan.model_json_schema()
}
response = client.messages.create(
    model=model_name, max_tokens=4096,
    tools=[tool_def],
    tool_choice={"type": "tool", "name": "structured_output"},
    messages=[{"role": "user", "content": prompt}]
)
tool_block = next(b for b in response.content if b.type == "tool_use")
plan = ExecutionPlan.model_validate(tool_block.input)
```

---

### 1-5. Tool Use（ReAct ループ）

| 項目 | Gemini | Anthropic |
|---|---|---|
| **ツール定義形式** | `types.Tool(function_declarations=[...])` | `[{"name":..., "description":..., "input_schema":{...}}]` |
| スキーマキー名 | `"parameters"` | **`"input_schema"`** |
| **ツール検出方法** | `candidates[0].content.parts` を走査して `part.function_call` を探す | `response.stop_reason == "tool_use"` を確認後 `content` を走査 |
| ツール名取得 | `fn.name` | `b.name` |
| ツール引数取得 | `fn.args` | `b.input` |
| **ツール ID** | なし | **`b.id`**（`tool_result` 返送時に必須） |
| **ツール結果の送信** | `Part.from_function_response()` + `chat.send_message()` 1回 | `messages` に **2件追記**（assistant + tool_result） |
| 複数ツール同時 | 1件ずつ処理 | 全件を同一 `user` メッセージにまとめる |
| 終了判定 | `function_call` が見つからない | `stop_reason == "end_turn"` |

```python
# Gemini（ツール定義）
tools = types.Tool(function_declarations=[
    {"name": "search", "parameters": {"type": "object", "properties": {...}}}
])

# Anthropic（ツール定義）
tools = [
    {"name": "search", "description": "...",
     "input_schema": {"type": "object", "properties": {...}, "required": [...]}}
]

# ─────────────────────────────────
# Gemini（ツール結果の送信）
function_response_part = types.Part.from_function_response(
    name=tool_name, response={"result": tool_result}
)
response = chat.send_message(message=function_response_part)   # 1回

# Anthropic（ツール結果の送信）：2件追記が必須
messages.append({"role": "assistant", "content": response.content})  # ①
messages.append({                                                      # ②
    "role"   : "user",
    "content": [{
        "type"       : "tool_result",
        "tool_use_id": tool_id,           # b.id と一致（必須）
        "content"    : str(tool_result)
    }]
})
response = client.messages.create(model=..., messages=messages, ...)
```

---

### 1-6. トークンカウント

| 項目 | Gemini | Anthropic |
|---|---|---|
| メソッド | `client.models.count_tokens(model, contents)` | `client.messages.count_tokens(model, messages)` |
| 戻り値 | `response.total_tokens` | `response.input_tokens` |

---

### 1-7. Embedding

| 項目 | Gemini | OpenAI（Anthropic 代替）|
|---|---|---|
| API | `client.models.embed_content(model, contents, config)` | `client.embeddings.create(model, input, dimensions)` |
| デフォルトモデル | `gemini-embedding-001` | `text-embedding-3-large` |
| 次元数 | 3072 | **3072**（同じ → Qdrant 互換） |
| task_type | `retrieval_query` / `retrieval_document` 等 | **なし** |
| 理由 | — | **Anthropic に Embedding API がない** |

---

### 1-8. Gemini 固有機能で Anthropic に存在しないもの

| Gemini 固有機能 | Anthropic での代替手段 |
|---|---|
| `response_schema=PydanticClass` | Tool Use（`generate_structured()`） |
| AFC（Automatic Function Calling） | 不要・存在しない |
| `AutomaticFunctionCallingConfig(disable=True)` | 不要・削除する |
| `chats.create()` チャットセッション | `messages` リストを自前管理 |
| `types.Part.from_function_response()` | `messages` に `tool_result` を直接追記 |
| `response.candidates[0].content.parts` | `response.content`（フラットなリスト） |
| `response.usage_metadata.prompt_token_count` | `response.usage.input_tokens` |
| `task_type`（Embedding） | 存在しない |
| Embedding API | 存在しない → **OpenAI を使用** |

---

### 1-9. モデル名対比

| 用途 | Gemini（移植元） | Anthropic（移植先） |
|---|---|---|
| 最高性能 | `gemini-3-pro-preview` | `claude-opus-4-7` |
| バランス型（推奨） | `gemini-3-flash-preview` | **`claude-sonnet-4-6`** |
| 高速・低コスト | `gemini-2.0-flash` | `claude-haiku-4-5-20251001` |
| Embedding | `gemini-embedding-001` | `text-embedding-3-large`（OpenAI） |

---

## 第2部　移植コツ・ベストプラクティス

---

### コツ① 抽象化レイヤー（LLMClient）を先に作る

直接 Gemini を置き換えるのではなく、**`LLMClient` 抽象基底クラスを設計し `AnthropicClient` を追加する**。
これにより各ファイルの変更が `self.client → self.llm` の置き換えだけで済む。

```python
# 各ファイルの変更がこれだけになる
# 変更前
self.client = genai.Client()
response = self.client.models.generate_content(...)
answer = response.text

# 変更後
self.llm = create_llm_client("anthropic")
answer = self.llm.generate_content(prompt)   # str が直接返る
```

`generate_content()` / `generate_structured()` / `generate_with_tools()` の3メソッドを
抽象化することで、呼び出し側のコードを大幅に簡素化できる。

---

### コツ② `generate_structured()` で構造化出力を隠蔽する

```python
# helper_llm.py に一度だけ実装
def generate_structured(self, prompt, response_schema, **kwargs):
    tool_def = {
        "name"        : "structured_output",
        "description" : "Return structured data",
        "input_schema": response_schema.model_json_schema()
    }
    response = self.client.messages.create(
        tools=[tool_def],
        tool_choice={"type": "tool", "name": "structured_output"},
        messages=[{"role": "user", "content": prompt}], **kwargs
    )
    tool_block = next(b for b in response.content if b.type == "tool_use")
    return response_schema.model_validate(tool_block.input)

# 呼び出し側（planner.py, confidence.py 等）はこれだけ
plan = self.llm.generate_structured(prompt, ExecutionPlan)
```

---

### コツ③ ReAct ループは「2件追記」を必ず守る

Anthropic の ReAct ループで最も間違えやすい箇所。
Gemini は `chat.send_message(part)` の1回で済むが、Anthropic では **2件追記が必須**。

```python
# ❌ よくある間違い（1件しか追記しない）
messages.append({"role": "user", "content": [{"type": "tool_result", ...}]})

# ✅ 正しい（2件追記が必須）
messages.append({"role": "assistant", "content": response.content})  # ① 必須
messages.append({
    "role"   : "user",
    "content": [{"type": "tool_result", "tool_use_id": tc["id"], "content": str(result)}]
})  # ②
```

`tool_use_id` に `b.id` を正確に設定しないと **API エラー**になる。

---

### コツ④ `stop_reason` でループ制御する

```python
# Gemini（function_call を走査）
for part in response.candidates[0].content.parts:
    if hasattr(part, 'function_call') and part.function_call:
        function_call_found = True
if not function_call_found:
    break

# Anthropic（stop_reason で判定）
text, tool_calls, stop_reason = self.llm.generate_with_tools(...)
if stop_reason != "tool_use" or not tool_calls:
    final_text = text
    break
```

---

### コツ⑤ `max_tokens` は必須・`system` は `messages` の外

```python
# ❌ よくある間違い
response = client.messages.create(
    model=model_name,
    messages=[
        {"role": "system", "content": "..."},  # ❌ system を messages に入れてはいけない
        {"role": "user",   "content": prompt}
    ]
    # max_tokens 未指定 → エラー
)

# ✅ 正しい
response = client.messages.create(
    model=model_name,
    max_tokens=4096,      # ✅ 必須
    system="...",         # ✅ messages の外
    messages=[{"role": "user", "content": prompt}]
)
```

---

### コツ⑥ GeminiClient は削除せず `try/except` で遅延インポートする

```python
# ✅ GeminiClient.__init__() 内で遅延インポート
try:
    from google import genai as _genai
except ImportError:
    raise ImportError("pip install google-genai")
self.client = _genai.Client(api_key=self.api_key)
```

`google-genai` が未インストールでも `GeminiClient` を使わない限りエラーにならない。

---

### コツ⑦ モジュールレベルの `from google import genai` を全て削除する

```bash
# 移植後の確認コマンド（全ファイルをチェック）
grep -rn "from google import genai" --include="*.py" .
grep -rn "from google.genai import" --include="*.py" .
# 何も出なければ合格（try/except 内の import は許容）
```

---

### コツ⑧ AFC 無効化コードを全て削除する

```python
# ❌ Gemini 固有コード（Anthropic では不要・削除する）
config=types.GenerateContentConfig(
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
)
```

Anthropic には AFC の概念が存在しない。

---

### コツ⑨ Reflection は `generate_with_tools(tools=[])` を使う

```python
# ❌ 会話履歴が引き継がれない
reflection_text = self.llm.generate_content(prompt=reflection_msg, ...)

# ✅ ReAct ループの検索結果・思考ログを引き継ぎ
self._messages.append({"role": "user", "content": reflection_msg})
reflection_text, _, _ = self.llm.generate_with_tools(
    messages=self._messages,
    tools=[],                      # Tool Use なし
    system=self.system_instruction,
)
```

---

### コツ⑩ 設定ファイルのデフォルト値の落とし穴

`get_config("models.default", "claude-sonnet-4-6")` の第2引数は「キーが存在しない場合のみ」使われる。
`_get_default_config()` 内に Gemini モデルが残っているとフォールバック値が使われない。

```python
# ❌ よくある落とし穴
def _get_default_config(self):
    return {"models": {"default": "gemini-2.0-flash"}}  # ← これが返り続ける

# ✅ 正しい修正
def _get_default_config(self):
    return {"models": {"default": "claude-sonnet-4-6"}}
```

---

### コツ⑪ YAML 設定ファイルも必ず更新する

Python コードを直しても YAML が古いと実行時に上書きされる。

```yaml
# grace_config.yml 変更後
llm:
  provider: "anthropic"
  model: "claude-sonnet-4-6"
embedding:
  provider: "openai"
  model: "text-embedding-3-large"
```

---

## 第3部　移植対象ファイル一覧（完了）

| Phase | ファイル | 変更種別 | 主な変更内容 | 状態 |
|---|---|---|---|---|
| **1** | `helper/helper_llm.py` | クラス追加 | `AnthropicClient` 追加、デフォルトプロバイダーを `anthropic` に変更 | ✅ |
| **1** | `helper_embedding.py` | 設定変更 | デフォルト `openai`、`text-embedding-3-large`（3072次元） | ✅ |
| **1** | `grace/config.py` | 設定変更 | `LLMConfig.model = claude-sonnet-4-6`、`EmbeddingConfig.provider = openai` | ✅ |
| **1** | `grace_config.yml` | 設定変更 | llm/embedding プロバイダー・モデルを更新 | ✅ |
| **1** | `services/config_service.py` | 設定変更 | `_get_default_config()` を Anthropic デフォルトに変更 | ✅ |
| **2** | `grace/planner.py` | API 置換 | `genai.Client()` → `AnthropicClient`、`generate_structured()` 使用 | ✅ |
| **2** | `grace/confidence.py` | API 置換 | `genai.Client()` → `AnthropicClient` / `create_embedding_client("openai")` | ✅ |
| **2** | `grace/tools.py` | API 置換 | `genai.Client()` → `AnthropicClient`、`"parameters"` → `"input_schema"` | ✅ |
| **2** | `grace/executor.py` | 間接変更 | 依存先の変更に追従 | ➖ |
| **2** | `grace/replan.py` | 間接変更 | 依存先の変更に追従 | ➖ |
| **2** | `grace/schemas.py` | 変更不要 | Pydantic 定義のみ・Gemini 依存なし | ➖ |
| **3** | `service/agent_service.py` | ループ書き直し | ReAct Tool Use を Anthropic 形式に完全書き直し | ✅ |
| **3** | `agent_main.py` | ループ書き直し | `UpgradedCLIAgent` を Anthropic 形式に書き直し | ✅ |
| **4** | `celery_config.py` | 設定追加 | `ANTHROPIC_CONFIG` を追加 | ✅ |
| **4** | `helper/helper_api.py` | import 追加 | `AnthropicClient` の再エクスポートを追加 | ✅ |
| **4** | `ui/pages/qa_generation_page.py` | UI 更新 | モデル選択リストを Claude モデルに更新 | ✅ |
| **4** | `ui/pages/qdrant_search_page.py` | 変更不要 | 次元数 3072 は変わらないため修正不要 | ➖ |
| **4** | `ui/pages/qdrant_registration_page.py` | 変更不要 | 次元数 3072 は変わらないため修正不要 | ➖ |
| **4** | `config.py`（ModelConfig） | 設定変更 | `AVAILABLE_MODELS` / `DEFAULT_MODEL` を Claude モデルに更新 | ✅ |
| **4** | `qa_generation/pipeline.py` | API 置換 | モデルデフォルトを `claude-sonnet-4-6` に変更 | ✅ |
| **4** | `qa_generation/smart_qa_generator.py` | API 置換 | `genai.Client()` → `create_llm_client("anthropic")` | ✅ |
| **4** | `qa_generation/semantic.py` | API 置換 | import パス修正、プロバイダーを Anthropic/OpenAI に変更 | ✅ |
| **4** | `celery_tasks.py` | 変更不要 | 移植完了済み・Gemini 依存なし | ➖ |
| **5** | Qdrant コレクション | 精度検証 | 次元数 3072 は互換だが、ベクトル空間の差異を並行テストで確認推奨 | ⏳ |

---

## 第4部　環境変数・設定

### .env ファイル

```bash
# Anthropic API（必須）
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI（Embedding 用・必須）
OPENAI_API_KEY=sk-...

# プロバイダー切替
LLM_PROVIDER=anthropic
EMBEDDING_PROVIDER=openai

# Gemini（後方互換・gemini_grace_agent 用）
GOOGLE_API_KEY=AIza...
```

### Anthropic モデル一覧（2026年4月時点）

| モデル文字列 | 用途目安 | RPM | TPM |
|---|---|---|---|
| `claude-opus-4-7` | 最高性能・複雑タスク | 50 | 200,000 |
| `claude-opus-4-6` | Opus 前世代（後方互換） | 50 | 200,000 |
| `claude-sonnet-4-6` | **推奨デフォルト**・バランス型 | 2,000 | 1,600,000 |
| `claude-sonnet-4-5` | Sonnet 前世代（後方互換） | 2,000 | 1,600,000 |
| `claude-haiku-4-5-20251001` | 高速・低コスト | 4,000 | 2,000,000 |

### OpenAI Embedding モデル比較

| モデル | 次元数 | 価格（/1K tokens） | 備考 |
|---|---|---|---|
| `text-embedding-3-large` | **3072** | $0.00013 | **本プロジェクト採用**。Gemini と同次元 |
| `text-embedding-3-small` | 1536 | $0.00002 | 軽量・低コスト |
| `text-embedding-ada-002` | 1536 | $0.00010 | 旧世代・非推奨 |

---

## 第5部　Qdrant コレクション互換性

`text-embedding-3-large`（OpenAI）と `gemini-embedding-001`（Gemini）は
**どちらも 3072 次元**のため、Qdrant コレクションの**再作成は不要**。

ただし、ベクトル空間の分布特性はモデルごとに異なるため、
既存コレクションに OpenAI Embedding でクエリすると精度が低下する可能性がある。

**推奨対応方針：**

1. **並行コレクション作成**（推奨）：サフィックス `_openai` で新コレクションを作成し精度を比較してから本番切り替えする。
2. **既存コレクション再登録**：データを `text-embedding-3-large` で再 Embedding して登録し直す（構造変更不要）。

```python
# dimensions パラメータで次元数を短縮可能
response = client.embeddings.create(
    model="text-embedding-3-large",
    input=text,
    dimensions=1536    # 3072 → 1536（MTEB スコアはほぼ変わらない）
)
```

---

*本ドキュメントは `anthropic_grace_agent` 移植作業の完了報告書兼技術参照資料として使用する。*
*以後の Gemini → Anthropic 移植プロジェクトでも本ドキュメントのコツ集を再利用可能。*
