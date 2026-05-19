# pip → uv 移行手順

**環境**: Mac / zsh / OpenAI API 専用
**プロジェクト**: `openai_grace_agent`
**作成日**: 2026-04-25

---

## なぜ uv か

| 項目 | pip | uv |
|---|---|---|
| インストール速度 | 普通 | **10〜100倍高速** |
| lock ファイル | なし（requirements.txt のみ） | `uv.lock`（再現性が高い） |
| 仮想環境管理 | `venv` 別途必要 | `uv venv` で統合管理 |
| Python バージョン管理 | 別途 pyenv 等が必要 | `uv python install` で管理可能 |

---

## Step 1: uv のインストール

```zsh
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.zshrc

# インストール確認
uv --version
```

---

## Step 2: プロジェクトへ移動・初期化

```zsh
cd /Users/nakashima_toshio/PycharmProjects/openai_grace_agent

# pyproject.toml を生成
uv init --no-workspace
```

---

## Step 3: Python バージョンを固定

```zsh
# 現在のバージョン確認
python --version

# 例: 3.12 を使う場合
uv python pin 3.12
```

---

## Step 4: requirements.txt から `anthropic` を削除して移行

まず `anthropic` を除いた `requirements.txt` を作成します。

```zsh
# anthropic を除いた requirements を生成
grep -v "^anthropic" requirements.txt > requirements_openai.txt

# 確認（anthropic が含まれていないこと）
grep "anthropic" requirements_openai.txt
# → 何も表示されなければOK

# 仮想環境を作成して一括インストール
uv venv
uv pip install -r requirements_openai.txt
```

---

## Step 5: lock ファイルを生成

```zsh
uv lock
uv sync
```

---

## Step 6: requirements.txt を OpenAI 専用に更新

```zsh
# uv から正式な requirements.txt を再生成
uv export --format requirements-txt > requirements.txt

# anthropic が含まれていないか確認
grep "anthropic" requirements.txt
# → 何も表示されなければOK
```

---

## Step 7: よく使うコマンド対応表

| 操作 | pip（変更前） | uv（変更後） |
|---|---|---|
| パッケージ追加 | `pip install openai` | `uv add openai` |
| パッケージ削除 | `pip uninstall openai` | `uv remove openai` |
| 一括インストール | `pip install -r requirements.txt` | `uv sync` |
| アップデート | `pip install --upgrade openai` | `uv add openai --upgrade` |
| 仮想環境作成 | `python -m venv .venv` | `uv venv` |
| スクリプト実行 | `python script.py` | `uv run python script.py` |
| Streamlit 起動 | `streamlit run app.py` | `uv run streamlit run app.py` |

---

## Step 8: `.env` の整理（Anthropic キー削除）

```zsh
# .env から ANTHROPIC_API_KEY を削除
sed -i '' '/ANTHROPIC_API_KEY/d' .env

# 確認（OPENAI_API_KEY のみ残っていればOK）
cat .env | grep -E "API_KEY"
```

---

## Step 9: Systemd サービスの修正（GCP サーバー）

```zsh
# GCP サーバーに SSH 接続
ssh -i ~/.ssh/gcp_key_v2 nakashima@34.84.198.115
```

```bash
# サーバー側（bash）で uv をインストール
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# サービスファイルを修正
sudo vim /etc/systemd/system/streamlit-app.service
```

```ini
# 変更前
ExecStart=/path/.venv/bin/streamlit run agent_rag.py

# 変更後
ExecStart=/usr/local/bin/uv run streamlit run agent_rag.py --server.port 8501
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart streamlit-app
sudo systemctl status streamlit-app
```

---

## Step 10: `.gitignore` に追加

```zsh
cat >> .gitignore << 'EOF'
.venv/
__pycache__/
EOF
```

> `uv.lock` はチーム開発では**コミット推奨**です。

---

## Step 11: PyCharm のインタープリタ更新

```
Settings → Project → Python Interpreter
→ Add Interpreter → Existing
→ /Users/nakashima_toshio/PycharmProjects/openai_grace_agent/.venv/bin/python を選択
```

---

## 移行後のプロジェクト構成

```
openai_grace_agent/
├── pyproject.toml     ← uv の設定ファイル（新規）
├── uv.lock            ← lock ファイル（新規・コミット推奨）
├── requirements.txt   ← OpenAI 専用（anthropic 削除済み）
├── .python-version    ← Python バージョン固定（新規）
├── .env               ← OPENAI_API_KEY のみ（ANTHROPIC_API_KEY 削除済み）
└── .venv/             ← 仮想環境（.gitignore に追加）
```

---

## まとめ：移行コマンド一覧

```zsh
# ① uv インストール
curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.zshrc

# ② プロジェクトへ移動
cd /Users/nakashima_toshio/PycharmProjects/openai_grace_agent

# ③ anthropic を除いた requirements を作成
grep -v "^anthropic" requirements.txt > requirements_openai.txt

# ④ 仮想環境作成 + インストール
uv venv && uv pip install -r requirements_openai.txt

# ⑤ lock ファイル生成
uv lock

# ⑥ .env の整理
sed -i '' '/ANTHROPIC_API_KEY/d' .env

# ⑦ 動作確認
uv run streamlit run agent_rag.py --server.port 8501
```

---

*本ドキュメントは `openai_grace_agent` の pip → uv 移行手順書として使用する。*
