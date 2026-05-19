共通事項
- クラス名: いずれもStreamlitのページ関数として実装されており、クラスではなく関数として定義されています。
- 変更内容: st.button() の引数に disabled=True を追加（または条件式を True に変更）しています。

---

(1) RAGデータダウンロード
* ファイル名: ui/pages/download_page.py
* 関数名: show_rag_download_page
* 変更箇所:

変更前 (Before)
```python
    # 実行ボタン
    run_download = st.button(
        "🚀 ダウンロード＆前処理開始", type="primary", width='stretch'
    )
```
```python
    # 変更後 (After)
    # 実行ボタン
    run_download = st.button(
        "🚀 ダウンロード＆前処理開始", type="primary", width='stretch', disabled=True
    )
```
---

(2) Q/A生成
* ファイル名: ui/pages/qa_generation_page.py
* 関数名: show_qa_generation_page
* 変更箇所:

変更前 (Before)
```python
# 実行ボタン（実行中は無効化）
run_qa_generation = st.button(
    "🚀 Q/A生成開始" if not st.session_state["qa_generation_running"] else "⏳ 処理中...",
    type="primary",
    width='stretch',
    disabled=st.session_state["qa_generation_running"]
)
```

変更後 (After)
```python
    # 実行ボタン（実行中は無効化）
    run_qa_generation = st.button(
        "🚀 Q/A生成開始" if not st.session_state["qa_generation_running"] else "⏳ 処理中...",
        type="primary",
        width='stretch',
        disabled=True # st.session_state["qa_generation_running"]
    )
```

---

(3) CSVデータ登録
* ファイル名: ui/pages/qdrant_registration_page.py
* 関数名: show_qdrant_registration_page
* 変更箇所:

変更前 (Before)
```python
# 登録ボタン
    run_registration = st.button(
        "🚀 Qdrantに登録を実行",
        type="primary",
        width='stretch',
        disabled=not (qdrant_connected and is_valid_collection_name),
    )
```

変更後 (After)
```python
    # 登録ボタン
    run_registration = st.button(
        "🚀 Qdrantに登録を実行",
        type="primary",
        width='stretch',
        disabled=True, # not (qdrant_connected and is_valid_collection_name),
    )
```
---

(4) Qdrantデータ管理
このページには「削除」「ロード」「統合」など複数のアクションボタンがありますが、主要なものを挙げます。

* ファイル名: ui/pages/qdrant_show_page.py
* 関数名: show_qdrant_page
* 変更箇所:

変更前 (Before)
```python
    # 削除ボタン
    if c4.button("🗑️ 削除", key=f"del_btn_{name}", type="secondary"):
        # ...

    # データをロードボタン
    if st.button("🔎 データをロード", type="primary", width='stretch'):
        # ...

    # 統合を実行ボタン
    if st.button("🚀 統合を実行", type="primary", disabled=len(selected_to_merge) < 2):
        # ...
```

変更後 (After)
```python
    # 削除ボタン
    if c4.button("🗑️ 削除", key=f"del_btn_{name}", type="secondary", disabled=True):
        # ...

    # データをロードボタン
    if st.button("🔎 データをロード", type="primary", width='stretch', disabled=True):
        # ...

    # 統合を実行ボタン
    if st.button("🚀 統合を実行", type="primary", disabled=True): # len(selected_to_merge) < 2
        # ...
```
