#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
explanation_page.py - システム説明ページ
========================================
README.md の内容を表示（Mermaid図対応）
"""

import re
import base64
import mimetypes
import streamlit as st
from pathlib import Path

try:
    import streamlit_mermaid as stmd

    MERMAID_AVAILABLE = True
except ImportError:
    MERMAID_AVAILABLE = False


def get_image_base64(image_path_str):
    """
    Reads an image from the local path and returns a base64 data URL.
    Resolves paths relative to the project root.
    """
    # Calculate project root based on the location of this file (ui/pages/explanation_page.py)
    # root is ../../../ relative to this file
    project_root = Path(__file__).resolve().parent.parent.parent
    
    target_path = Path(image_path_str)
    
    # List of possible paths to check
    candidates = [
        project_root / target_path,
        project_root / "doc" / target_path.name,
        project_root / "assets" / target_path.name,
        project_root / "doc" / "assets" / target_path.name
    ]

    found_path = None
    for p in candidates:
        if p.exists() and p.is_file():
            found_path = p
            break

    if found_path:
        try:
            with open(found_path, "rb") as img_file:
                b64_data = base64.b64encode(img_file.read()).decode()
                mime_type, _ = mimetypes.guess_type(found_path)
                if not mime_type:
                    mime_type = "image/png"
                return f"data:{mime_type};base64,{b64_data}"
        except Exception as e:
            # print(f"Error reading image {found_path}: {e}")
            return None
    return None


def render_markdown_with_mermaid(content: str):
    """
    Mermaid コードブロックを含む Markdown を表示する。
    画像パスのBase64化、リンクのクエリパラメータ化を行う。
    """
    
    # 1. Image Replacement: Convert local images to Base64
    # Pattern: ![alt](path)
    def replace_image(match):
        alt_text = match.group(1)
        image_path = match.group(2)
        # Skip external links and already base64 encoded images
        if image_path.startswith("http") or image_path.startswith("data:"):
            return match.group(0)
        
        b64_src = get_image_base64(image_path)
        if b64_src:
            return f"![{alt_text}]({b64_src})"
        return match.group(0)

    content = re.sub(r'!\[(.*?)\]\((.*?)\)', replace_image, content)

    # 2. Link Replacement: Convert [text](file.md) to ?doc=file.md
    # This allows navigation within the Streamlit app
    def replace_link(match):
        text = match.group(1)
        link_path = match.group(2)
        if link_path.endswith(".md") and not link_path.startswith("http"):
            return f"[{text}](?doc={link_path})"
        return match.group(0)

    content = re.sub(r'\[(.*?)\]\((.*?\.md)\)', replace_link, content)


    # Mermaid コードブロックを検出するパターン
    mermaid_pattern = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)

    # コンテンツを分割
    last_end = 0
    for match in mermaid_pattern.finditer(content):
        # Mermaid の前のマークダウン部分を表示
        before_text = content[last_end : match.start()]
        if before_text.strip():
            st.markdown(before_text, unsafe_allow_html=True)

        # Mermaid 図を表示
        mermaid_code = match.group(1).strip()

        # Inject classDef after the first line (graph declaration)
        if mermaid_code.startswith("flowchart") or mermaid_code.startswith("graph"):
            lines = mermaid_code.split('\n')
            if len(lines) > 0:
                lines.insert(1, "classDef default fill:#000,stroke:#fff,stroke-width:1px,color:#fff;")
                mermaid_code = "\n".join(lines)

        if MERMAID_AVAILABLE:
            try:
                stmd.st_mermaid(mermaid_code)
            except Exception as e:
                st.code(mermaid_code, language="mermaid")
                st.warning(f"Mermaid 図のレンダリングに失敗: {e}")
        else:
            st.code(mermaid_code, language="mermaid")
            st.info("Mermaid 図を表示するには: pip install streamlit-mermaid")

        last_end = match.end()

    # 残りのマークダウン部分を表示
    remaining_text = content[last_end:]
    if remaining_text.strip():
        st.markdown(remaining_text, unsafe_allow_html=True)


def show_system_explanation_page():
    """システム説明ページ - README.md または指定されたドキュメントを表示"""
    
    # Check for query parameter 'doc'
    query_params = st.query_params
    target_doc = query_params.get("doc", "README.md")
    
    # Title logic
    if target_doc == "README.md":
        st.title("📖 システム説明")
        st.caption("プロジェクト README.md")
    else:
        st.title(f"📖 {target_doc}")
        if st.button("← README.md に戻る"):
            st.query_params.clear()
            st.rerun()

    st.markdown("---")

    # Resolve file path
    project_root = Path(__file__).resolve().parent.parent.parent
    
    # Handle simple relative paths
    file_path = project_root / target_doc
    
    # If not found directly, try finding it in doc/ folder if it looks like a doc
    if not file_path.exists() and not str(target_doc).startswith("doc/"):
         alt_path = project_root / "doc" / target_doc
         if alt_path.exists():
             file_path = alt_path

    if file_path.exists() and file_path.suffix == ".md":
        readme_content = file_path.read_text(encoding="utf-8")
        render_markdown_with_mermaid(readme_content)
    else:
        st.error(f"ドキュメントが見つかりません: {target_doc}")
        if target_doc != "README.md":
             if st.button("トップに戻る"):
                st.query_params.clear()
                st.rerun()