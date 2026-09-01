"""Streamlit 화면의 출처·미디어 렌더링 연결을 런타임 없이 검증한다."""

from __future__ import annotations

import ast
from pathlib import Path


APP_PATH = Path("streamlit_app/app.py")


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _called_names(function: ast.FunctionDef) -> list[str]:
    return [
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]


def test_streamlit_renders_citation_media_once_per_response_page() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "render_media(" not in source
    assert _called_names(_function(tree, "render_answer")).count("render_citation_media") == 0
    assert _called_names(_function(tree, "render_qa_page")).count("render_citation_media") == 1
    assert _called_names(_function(tree, "render_recommendation_page")).count("render_citation_media") == 1


def test_recommendation_sources_receive_the_extracted_use_case() -> None:
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    recommendation_page = _function(tree, "render_recommendation_page")
    source_calls = [
        node
        for node in ast.walk(recommendation_page)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "render_sources"
    ]

    assert len(source_calls) == 1
    assert [keyword.arg for keyword in source_calls[0].keywords] == ["preferred_use_case"]
