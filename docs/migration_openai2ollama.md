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

---

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
    api_key="ollama",   # ダミー値。リモート認証が必要な場合は尊重すること
)
```

---

### 1-2. テキスト生成（シングルターン）

| 項目 | OpenAI Chat Completions | OpenAI Responses API | Ollama |
|---|---|---|---|
| メソッド | `client.chat.completions.create()` | `client.responses.create()` | `client.chat.completions.create()` |
| プロンプト引数名 | `messages=[...]` | `input=[...]` | `messages=[...]` |
| システムプロンプト | `messages` 先頭に `{"role":"system",...}` | `input` 先頭に `{"role":"system",...}` | `messages` 先頭に `{"role":"system",...}` |
| 出力トークン上限 | `max_completion_tokens=...` | `max_output_tokens=...` | **`max_tokens=...`** |
| 温度パラメータ | `temperature=...` | `temperature=...` | `temperature=...` |
| レスポンス取得 | `response.choices[0].message.content` | `response.output_text` | `response.choices[0].message.content` |
| AFC 無効化 | 不要 | 不要 | **不要** |

```python
# OpenAI Chat Completions
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "あなたは..."},
        {"role": "user",   "content": prompt}
    ],
    max_completion_tokens=4096,
    temperature=0.7,
)
answer = response.choices[0].message.content

# OpenAI Responses API
response = client.responses.create(
    model="gpt-4o",
    input=[
        {"role": "system", "content": "あなたは..."},
        {"role": "user",   "content": prompt}
    ],
    max_output_tokens=4096,
    temperature=0.7,
)
answer = response.output_text

# Ollama
response = client.chat.completions.create(
    model="llama3.2",
    messages=[
        {"role": "system", "content": "あなたは..."},
        {"role": "user",   "content": prompt}
    ],
    max_tokens=4096,       # max_completion_tokens / max_output_tokens ではなく max_tokens
    temperature=0.7,
)
answer = response.choices[0].message.content   # OpenAI Chat と同じ
```

> **⚠️ 重要**: Ollama は `max_completion_tokens` / `max_output_tokens` に非対応。
> 必ず **`max_tokens`** を使用すること。

---

### 1-3. Responses API 与存機能対応表

`helper/helper_api.py` は OpenAI Responses API (下記) を使用しており、Ollama では非対応の機能がある。

| OpenAI Responses API | Ollama 代替手段 |
|---|---|
| `client.responses.create(model, input, ...)` | `client.chat.completions.create(model, messages, ...)` |
| `client.responses.parse(text_format=Schema)` | JSON モード + プロンプト内スキーマ + Pydantic parse |
| `response.output_text` | `response.choices[0].message.content` |
| `response.output_parsed` | `Schema.model_validate_json(response.choices[0].message.content)` |
| `response.status == "completed"` | `response.choices[0].finish_reason == "stop"` |
| `EasyInputMessageParam` | `{"role": ..., "content": ...}` dict |
| `previous_response_id` 連鎖 | `messages` リストを自前管理 |

---

### 1-4. 構造化出力（最大の差異）

| 項目 | OpenAI Chat (旧) | OpenAI Responses API (現行) | Ollama |
|---|---|---|---|
| 方式 | `client.beta.chat.completions.parse()` | `client.responses.parse(text_format=Schema)` | **JSON モード + Pydantic parse** |
| スキーマ形式 | `response_format=PydanticClass` | `text_format=PydanticClass` | `response_format={"type":"json_object"}` + プロンプト内指定 |
| レスポンス取得 | `response.choices[0].message.parsed` | `response.output_parsed` | `Schema.model_validate_json(raw)` |
| JSON 解析 | SDK が自動パース | SDK が自動パース | **手動 parse** (`JSONDecodeError` リスクあり) |
| スキーマ次元の関数 | `beta.chat.completions.parse` | `responses.parse` | `json_object` モード |

```python
# OpenAI Chat Completions （旧 beta）
response = client.beta.chat.completions.parse(
    model="gpt-4o",
    messages=[{"role":"user", "content": prompt}],
    response_format=ExecutionPlan,
    max_completion_tokens=4096,
)
plan = response.choices[0].message.parsed  # ExecutionPlan インスタンス

# OpenAI Responses API （現行推奨）
response = client.responses.parse(
    model="gpt-4o",
    input=[{"role":"user", "content": prompt}],
    text_format=ExecutionPlan,
    max_output_tokens=4096,
)
plan = response.output_parsed  # ExecutionPlan インスタンス

# Ollama
schema_json = json.dumps(ExecutionPlan.model_json_schema(), ensure_ascii=False, indent=2)
messages = [
    {"role": "system", "content": "You are a helpful assistant. Output valid JSON only."},
    {
        "role": "user",
        "content": (
            f"{prompt}\n\n"
            f"以下の JSON スキーマに完全に準拠した JSON のみを出力してください:\n{schema_json}"
        )
    },
]
response = client.chat.completions.create(
    model="llama3.2",
    messages=messages,
    max_tokens=4096,
    temperature=0.1,
    response_format={"type": "json_object"},
)
raw = response.choices[0].message.content
plan = ExecutionPlan.model_validate_json(raw)  # JSONDecodeError に注意
```

---

### 1-5. Tool Use（ReAct ループ）

| 項目 | OpenAI | Ollama |
|---|---|---|
| **ツール定義形式** | `[{"type":"function","function":{"name":...,"parameters":{...}}}]` | **同じ**（OpenAI 互換） |
| スキーマキー名 | `"parameters"` | `"parameters"` |
| **ツール呼び出し検出** | `finish_reason == "tool_calls"` | `finish_reason == "tool_calls"` |
| ツール名取得 | `tc.function.name` | `tc.function.name` |
| ツール引数取得 | `json.loads(tc.function.arguments)` | `json.loads(tc.function.arguments)` |
| **ツール ID** | `tc.id` | `tc.id` |
| **ツール結果の返送** | `{"role":"tool","tool_call_id":id,"content":result}` を messages に追記 | **同じ** |
| 終了判定 | `finish_reason == "stop"` | `finish_reason == "stop"` |
| 対応モデル | 全モデル | **llama3.2, llama3.1, qwen2.5, mistral-nemo** 等一部 |

> **⚠️ Tool Use 対応モデル**: Ollama で Tool Use を使う場合は
> **`llama3.2`, `llama3.1:8b`, `qwen2.5:7b`, `mistral-nemo`** を推奨。
> `phi3`, `gemma2` は当初 Tool Use が不安定な場合がある。

```python
# ツール定義（OpenAI ・ Ollama 共通）
tools = [
    {
        "type": "function",
        "function": {
            "name"       : "search_rag",
            "description": "RAG 検索を実行する",
            "parameters" : {
                "type"      : "object",
                "properties": {"query": {"type": "string"}},
                "required"  : ["query"]
            }
        }
    }
]

# Ollama・ OpenAI 共通の ReAct ループ
messages = [{"role": "user", "content": query}]
while True:
    response = client.chat.completions.create(
        model="llama3.2",
        messages=messages,
        tools=tools,
        max_tokens=4096,
    )
    msg = response.choices[0].message
    finish_reason = response.choices[0].finish_reason

    if finish_reason != "tool_calls" or not msg.tool_calls:
        final_answer = msg.content
        break

    # ツール実行
    messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})
    for tc in msg.tool_calls:
        args = json.loads(tc.function.arguments)
        result = execute_tool(tc.function.name, args)
        messages.append({
            "role"        : "tool",
            "tool_call_id": tc.id,
            "content"     : str(result),
        })
```

---

### 1-6. トークンカウント

| 項目 | OpenAI | Ollama |
|---|---|---|
| メソッド | `tiktoken` （ローカル計算） | `tiktoken` （ローカル計算） |
| API コール | なし | **なし**（Ollama にトークンカウント API なし） |
| エンコーディング | `tiktoken.encoding_for_model(model)` | `tiktoken.get_encoding("cl100k_base")` |
| 推定精度 | モデル固有エンコーディングで高精度 | cl100k_base は近似値（実務上十分） |

```python
# 共通: tiktoken ベースのトークンカウント
import tiktoken

# OpenAI
try:
    encoding = tiktoken.encoding_for_model(model)
except KeyError:
    encoding = tiktoken.get_encoding("cl100k_base")
count = len(encoding.encode(text))

# Ollama―cl100k_base で近似
encoding = tiktoken.get_encoding("cl100k_base")
count = len(encoding.encode(text))
```

---

### 1-7. Embedding

| 項目 | OpenAI | Ollama |
|---|---|---|
| API | `client.embeddings.create(model, input, dimensions)` | `client.embeddings.create(model, input)` |
| クライアント | `OpenAI(api_key=...)` | `OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")` |
| 推奨モデル | `text-embedding-3-large` | **`nomic-embed-text`** |
| 次元数 | 3072 (`text-embedding-3-large`) | **768** (`nomic-embed-text`) |
| `dimensions` パラメータ | 対応（短縮可） | **非対応**（モデル内部固定） |
| `task_type` | なし | なし |
| ベクトル取得 | `response.data[0].embedding` | `response.data[0].embedding` |
| API キー | `OPENAI_API_KEY` 必須 | **不要** |
| Qdrant 互換性 | **互換なし**（次元数が尊属別） | コレクション再作成が必要 |

```python
# OpenAI Embedding
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

response = client.embeddings.create(
    model="text-embedding-3-large",
    input=text,
    dimensions=3072,    # 短縮が可能
)
vector = response.data[0].embedding  # 3072次元

# Ollama Embedding
from openai import OpenAI
client = OpenAI(
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    api_key="ollama",
)

response = client.embeddings.create(
    model="nomic-embed-text",
    input=text,
    # dimensions パラメータは指定不可（モデルの固定次元数が使われる）
)
vector = response.data[0].embedding  # 768次元
```

---

### 1-8. OpenAI 固有機能で Ollama に存在しないもの

| OpenAI 固有機能 | Ollama での代替手段 |
|---|---|
| `client.responses.create()` Responses API | `client.chat.completions.create()`（Chat 形式） |
| `client.responses.parse(text_format=Schema)` | JSON モード + スキーマプロンプト + `model_validate_json()` |
| `response.output_text` | `response.choices[0].message.content` |
| `response.output_parsed` | `Schema.model_validate_json(raw_text)` |
| `response.status == "completed"` | `response.choices[0].finish_reason == "stop"` |
| `client.beta.chat.completions.parse()` | 同上 |
| `max_completion_tokens` | **`max_tokens`** |
| `max_output_tokens` (Responses API) | **`max_tokens`** |
| `dimensions` パラメータ (Embedding) | **不要**（モデル固定） |
| `EasyInputMessageParam` | `{"role":..., "content":...}` dict |
| `previous_response_id` 連鎖 | `messages` リストを自前管理 |
| クラウドバッチ処理 API | なし（ローカル実行のため不要） |
| トークン課金 | **なし**（無料） |

---

### 1-9. モデル名対比

| 用途目安 | OpenAI（移植元） | Ollama（移植先） |
|---|---|---|
| 最高性能 | `gpt-4o` | `llama3.1:70b` / `qwen2.5:14b` |
| **推奨デフォルト** | `gpt-4o-mini` | **`llama3.2`** |
| 高速・軽量 | `gpt-4o-mini` | `llama3.2:1b` / `phi3:mini` |
| 日本語対応 | `gpt-4o-mini` | `qwen2.5:7b` / `llama3.2` |
| Embedding | `text-embedding-3-large` (3072次) | `nomic-embed-text` (768次) |
| Embedding (高精度) | `text-embedding-3-large` (3072次) | `mxbai-embed-large` (1024次) |
| Tool Use 対応 | 全モデル | `llama3.2`, `qwen2.5:7b`, `mistral-nemo` |

---

## 第2部　移植コツ・ベストプラクティス

---

### コツ① OllamaClient 抽象化レイヤーを作る

`helper/helper_llm.py` に `OllamaClient` を追加し、各ファイルの変更が
`create_llm_client("ollama")` の 1 行変更で済むようにする。

```python
# 各ファイルの変更がこれだけになる
# 変更前
self.llm = create_llm_client("openai", default_model=self.model_name)

# 変更後
self.llm = create_llm_client("ollama", default_model=self.model_name)
```

`generate_content()` / `generate_structured()` / `generate_with_tools()` の 3 メソッドを
`OllamaClient` 内部で吸収し、呼び出し側のコード変更を最小化する。

---

### コツ② `generate_structured()` で JSON パースを隐蔽する

Ollama は `beta.chat.completions.parse()` / `responses.parse()` に非対応。
`OllamaClient.generate_structured()` に JSON モード + Pydantic parse を隠蔽することで、
呼び出し側のコードを変更しない。

```python
# helper_llm.py 内に一度だけ実装（みぞ OllamaClient の内部に隐蔽）
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
    raw = response.choices[0].message.content
    return response_schema.model_validate_json(raw)

# 呼び出し側（planner.py 等）は変更不要
plan = self.llm.generate_structured(prompt, ExecutionPlan)
```

---

### コツ③ `max_completion_tokens` / `max_output_tokens` を `max_tokens` に統一する

Ollama は `max_completion_tokens`（OpenAI Chat 新形式）でも `max_output_tokens`（Responses API）でもなく、
常に `max_tokens` を使用する。

```python
# ❗ OllamaClient.generate_content() 内部で自動変換する
max_tokens = kwargs.pop("max_completion_tokens", None) or kwargs.pop("max_tokens", 4096)
```

`OllamaClient` 内部で吸収するため、呼び出し側は変更不要。

---

### コツ④ `helper_api.py` の Responses API 依存部分を分離する

`helper_api.py` は OpenAI Responses API 固有の型定義を使用している。
Ollama では Chat Completions 形式に統一する。

```python
# ❗ OpenAI Responses API 固有 (移植時に対応が必要)
from openai.types.responses import EasyInputMessageParam, Response   # ▊ Ollama 非対応

# ✅ 全プロバイダー共通の dict 形式
messages = [{"role": "user", "content": prompt}]
```

`MessageManager` など `EasyInputMessageParam` に依存するクラスは、
`Dict[str, str]` 形式に統一するか、Ollama では利用しないよう分沐する。

---

### コツ⑤ Qdrant コレクションの再作成を必ず実施する

OpenAI `text-embedding-3-large` (3072次) → Ollama `nomic-embed-text` (768次) で
**次元数が大きく変わる**ため、既存コレクションは使用不可能。

```bash
# Ollama Embedding モデルのインストール
ollama pull nomic-embed-text

# Qdrant コレクション唤起
# 新コレクションを作成（次元数 768 で指定）
python a30_qdrant_registration.py --recreate --limit 100
```

次元数の比較：

| エンベディングモデル | 次元数 | Qdrant 互換性 |
|---|---|---|
| OpenAI `text-embedding-3-large` | 3072 | — |
| OpenAI `text-embedding-3-small` | 1536 | — |
| Ollama `nomic-embed-text` | 768 | **再作成必要** |
| Ollama `mxbai-embed-large` | 1024 | **再作成必要** |
| Ollama `all-minilm` | 384 | **再作成必要** |

---

### コツ⑥ YAML 設定ファイルも必ず更新する

Python コードを直しても YAML が古いと実行時に上書きされる。

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

---

### コツ⑦ Tool Use 対応モデルを確認する

Ollama すべてのモデルが Tool Use に対応しているわけではない。

```bash
# 推奨: Tool Use 対応モデル
ollama pull llama3.2         # 初心者向ケ 推奨
ollama pull llama3.1:8b      # 性能・素数バランス
ollama pull qwen2.5:7b       # 日本語対応も良好
ollama pull mistral-nemo     # 文書処理向ケ

# 非推奨: Tool Use が不安定な場合あり
ollama pull phi3             # Tool Use は非対応のパターンあり
ollama pull gemma2           # 機能削減モデルでは漏れの場合あり
```

---

### コツ⑧ 環境変数を整理する

```bash
# .env 変更後

# [MIGRATION] 不要になる
# OPENAI_API_KEY=sk-...

# [MIGRATION] 新設 (リモート Ollama サーバーを使う場合のみ)
# OLLAMA_BASE_URL=http://your-remote-host:11434/v1

# [MIGRATION] プロバイダー切替
LLM_PROVIDER=ollama
EMBEDDING_PROVIDER=ollama

# 共通: Qdrant
QDRANT_URL=http://localhost:6333

# 後方互換: 他プロジェクトと並行利用時のみ
# OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=AIza...
# ANTHROPIC_API_KEY=sk-ant-...
```

---

### コツ⑨ Ollama の起動とモデルの事前准備を定常化する

```bash
# Ollama サーバー起動
ollama serve

# 必要モデルの pull
ollama pull llama3.2          # LLM デフォルト
ollama pull nomic-embed-text  # Embedding デフォルト

# ダウンロード確認
ollama list

# 接続確認
curl http://localhost:11434/v1/models
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
| **3** | `services/agent_service.py` | ループ高適化 | ReAct インターフェース确認（既に共通形式） | ⏳ |
| **3** | `agent_main.py` | 設定変更 | モデルデフォルト値を Ollama 用に変更 | ⏳ |
| **4** | `helper/helper_api.py` | API 分離 | Responses API 依存部分を Chat 形式に統一、`EasyInputMessageParam` 依存を排除 | ⏳ |
| **4** | `celery_config.py` | 設定確認 | Ollama プロバイダー設定を追加 | ⏳ |
| **4** | `ui/pages/qdrant_search_page.py` | 変更不要 | Embedding 次元変更を隤いて Qdrant の再登録対応 | ⏳ |
| **4** | `ui/pages/qdrant_registration_page.py` | 変更不要 | 次元数が変わるため再登録が必要 | ⏳ |
| **5** | Qdrant コレクション | **再作成必須** | 3072次元 → 768次元のため完全に不互換 | ⚠️ |

**状態けい**: ✅ 完了 / ⏳ 作業中 / ➡️ 間接変更のみ / ✔️ 変更不要 / ⚠️ 要注意

---

## 第4部　環境変数・設定

### .env ファイル

```bash
# =========================================
# ollama_grace_agent 環境変数
# =========================================

# [不要になる] OpenAI API キー（Ollama はローカル実行のため不要）
# OPENAI_API_KEY=sk-...

# [オプション] Ollama エンドポイント（デフォルト: localhost）
# OLLAMA_BASE_URL=http://localhost:11434/v1

# [激推] プロバイダー切替
LLM_PROVIDER=ollama
EMBEDDING_PROVIDER=ollama

# 共通: Qdrant
QDRANT_URL=http://localhost:6333

# 後方互換: 他プロジェクトと並行利用時のみ
# GOOGLE_API_KEY=AIza...
# ANTHROPIC_API_KEY=sk-ant-...
```

### Ollama モデル一覧

| モデル | VRAM (目安) | 性能 | Tool Use | 日本語 |
|---|---|---|---|---|
| `llama3.2` | ~2GB | 標準 | ✅ | ✅ |
| `llama3.2:1b` | ~1GB | 軽量 | ⚠️ 不安定 | ✅ |
| `llama3.1:8b` | ~5GB | 高性能 | ✅ | ✅ |
| `llama3.1:70b` | ~40GB | 最高性能 | ✅ | ✅ |
| `qwen2.5:7b` | ~5GB | 高性能 | ✅ | **★ 溘語優秀** |
| `qwen2.5:14b` | ~9GB | 高性能 | ✅ | **★ 溘語優秀** |
| `mistral` | ~4GB | 標準 | ✅ | ⚠️ 限定的 |
| `mistral-nemo` | ~7GB | 高性能 | ✅ | ⚠️ 限定的 |
| `phi3:mini` | ~2GB | 軽量 | ⚠️ 不安定 | ⚠️ 限定的 |
| `gemma2:9b` | ~6GB | 標準 | ⚠️ 不安定 | ⚠️ 限定的 |

### Ollama Embedding モデル一覧

| モデル | 次元数 | 性能 | 日本語 |
|---|---|---|---|
| `nomic-embed-text` | **768** | 標準（**推奨**） | ✅ |
| `mxbai-embed-large` | **1024** | 高精度 | ⚠️ 限定的 |
| `all-minilm` | **384** | 軽量・高速 | ⚠️ 限定的 |

---

## 第5部　Qdrant コレクション互換性

OpenAI `text-embedding-3-large` (3072次) と Ollama `nomic-embed-text` (768次) は
**次元数が全く异なる**ため、Qdrant コレクションの再作成は必須である。

**推奨対応方针：**

1. **並行コレクション作成**（推奨）: サフィックス `_ollama` で新コレクションを作成し、第元コレクションと精度を比較する。
2. **既存コレクション再登録**: Ollama Embedding でデータを再登録する。

```python
# Qdrant コレクション 再作成時の次元数指定
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

client = QdrantClient(url="http://localhost:6333")
client.create_collection(
    collection_name="my_collection_ollama",
    vectors_config=VectorParams(
        size=768,               # nomic-embed-text: 768 次元
        distance=Distance.COSINE,
    )
)

# 再登録コマンド
python a30_qdrant_registration.py --recreate --limit 100
```

---

## 第6部　よくある移植ミスと対策

| ミス | OpenAI | Ollama |
|---|---|---|
| トークン上限パラメータ | `max_completion_tokens` / `max_output_tokens` | **`max_tokens`** |
| 構造化出力 | `beta.parse()` / `responses.parse()` | **JSON モード + `model_validate_json()`** |
| Embedding 次元 | `dimensions=3072` 指定 | **`dimensions` パラメータは非対応** |
| Qdrant 次元 | 3072次元のコレクションをそのまま使用 | **768次元でコレクション再作成必須** |
| API キー | `OPENAI_API_KEY` 必須 | **不要**（`api_key="ollama"`） |
| Responses API 型 | `EasyInputMessageParam` 使用 | **dict `{"role":...,"content":...}` で代替** |
| `response.output_text` | 正常動作 | **属性なし → `choices[0].message.content`** |
| `response.output_parsed` | 正常動作 | **属性なし → `model_validate_json(raw)`** |
| Tool Use 全モデル対応想定 | OK | **対応モデルに限定あり** |
| プロンプトで完結 | 次の內容を続ける | **日本語プロンプトで出力が英語になる場合 → プロンプト内で日本語指定** |
| JSON スキーマ遵守 | SDK が保証 | **モデル依存、小型モデルはスキーマ違反あり → リトライ必須** |

---

## 第7部　移植後の動作確認手順

### Step 1: Ollama セットアップ

```bash
# Ollama インストール
curl -fsSL https://ollama.ai/install.sh | sh   # Linux/Mac

# サービス起動
ollama serve

# 必要モデルのダウンロード
ollama pull llama3.2
ollama pull nomic-embed-text

# 動作確認
curl http://localhost:11434/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"llama3.2","messages":[{"role":"user","content":"hello"}]}'
```

### Step 2: Qdrant 起動 + データ再登録

```bash
# Qdrant 起動
docker-compose -f docker-compose/docker-compose.yml up -d

# Ollama Embedding で再登録（必須: 次元数が変わる）
python a30_qdrant_registration.py --recreate --limit 100
```

### Step 3: 統合テスト

```bash
# 単体テスト: LLM
python -c "
from helper.helper_llm import create_llm_client
llm = create_llm_client('ollama')
print(llm.generate_content('こんにちは'))
"

# 単体テスト: Embedding
python -c "
from helper.helper_embedding import create_embedding_client
emb = create_embedding_client('ollama')
v = emb.embed_text('テスト')
print(f'dims={len(v)}')
"

# 単体テスト: 構造化出力
python -c "
from helper.helper_llm import create_llm_client
from grace.schemas import ExecutionPlan
llm = create_llm_client('ollama')
plan = llm.generate_structured('テスト質問に回答して', ExecutionPlan)
print(plan.plan_id)
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
*以後の OpenAI → Ollama 移植プロジェクトでも本ドキュメントのコツ集を再利用可能。*
