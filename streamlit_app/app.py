"""PiCare Streamlit mock UI for product recommendations and document-grounded QA."""

from __future__ import annotations

import base64
import html
import mimetypes
import time
from pathlib import Path

import streamlit as st

from mock_data import (
    PRODUCTS,
    RECOMMENDATION_SOURCES,
    mock_qa_response,
    recommendation_conditions,
)
from styles import APP_CSS


ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(
    page_title="PiCare | Raspberry Pi 공식 문서 기반 도우미",
    page_icon="🍓",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(APP_CSS, unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def image_data_uri(relative_path: str) -> str:
    """Read a repository image as a data URI for stable custom cards."""

    path = ROOT / relative_path
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def current_page() -> str:
    """Return a supported top-level page from the URL query string."""

    page = st.query_params.get("page", "recommend")
    return page if page in {"about", "recommend", "qa"} else "recommend"


def render_header(page: str) -> str:
    """Render functional Streamlit navigation styled like the shared mockup."""

    page_labels = {
        "about": "서비스 소개",
        "recommend": "제품 추천",
        "qa": "질의응답",
    }
    label_pages = {label: value for value, label in page_labels.items()}
    brand, navigation, badge = st.columns([1, 1.6, 1], vertical_alignment="center")
    with brand:
        st.markdown('<div class="picare-brand"><span>🍓</span>PiCare</div>', unsafe_allow_html=True)
    with navigation:
        selection = st.radio(
            "페이지",
            list(label_pages),
            index=list(label_pages).index(page_labels[page]),
            horizontal=True,
            label_visibility="collapsed",
            key="top_navigation",
        )
    with badge:
        st.markdown('<div class="picare-doc-badge">📖 공식 문서 기반</div>', unsafe_allow_html=True)
    st.markdown('<div class="picare-header-line"></div>', unsafe_allow_html=True)
    return label_pages[selection]


def render_hero(title: str, highlighted: str | None, subtitle: str) -> None:
    """Render a consistent page heading."""

    safe_title = html.escape(title)
    if highlighted:
        safe_title = safe_title.replace(
            html.escape(highlighted), f"<em>{html.escape(highlighted)}</em>"
        )
    st.markdown(
        f"""
        <div class="hero">
          <div class="mock-ribbon">✨ MOCK DATA · sLLM/RAG 연동 전 화면</div>
          <h1>{safe_title}</h1>
          <p>{html.escape(subtitle)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str, pill: str | None = None) -> None:
    """Render a section heading and optional status pill."""

    badge = f'<span class="status-pill">{html.escape(pill)}</span>' if pill else ""
    st.markdown(
        f'<div class="section-title"><h2>{html.escape(title)}</h2>{badge}</div>',
        unsafe_allow_html=True,
    )


def render_sources(sources: list[dict]) -> None:
    """Render citation metadata without asking an LLM to generate it."""

    if not sources:
        st.info("표시할 공식 검색 근거가 없습니다. 출처를 추측하지 않습니다.")
        return
    for source in sources:
        citation = source.get("citation_id", "")
        citation_text = f"{html.escape(citation)} · " if citation else ""
        st.markdown(
            f"""
            <div class="source-card">
              <div class="source-icon">📄</div>
              <div>
                <div class="source-title">{citation_text}{html.escape(source['title'])}</div>
                <div class="source-meta">Section: {html.escape(source['section'])} &nbsp; · &nbsp; {html.escape(source['license'])}</div>
              </div>
              <a class="source-link" href="{html.escape(source['url'], quote=True)}" target="_blank" rel="noopener noreferrer" aria-label="공식 문서 열기">↗</a>
            </div>
            """,
            unsafe_allow_html=True,
        )


def product_card(product: dict) -> None:
    """Render a product card backed by repository-owned licensed assets."""

    image_uri = image_data_uri(product["image"])
    limitations = " ".join(product["limitations"])
    st.markdown(
        f"""
        <div class="product-card">
          <span class="product-badge tone-{html.escape(product['badge_tone'])}">{html.escape(product['badge'])}</span>
          <img src="{image_uri}" alt="{html.escape(product['name'])}" style="width:100%;height:155px;object-fit:contain;" />
          <div class="product-name">{html.escape(product['name'])}</div>
          <div class="spec-grid">
            <strong>⚙ CPU</strong><span>{html.escape(product['cpu'])}</span>
            <strong>▦ RAM</strong><span>{html.escape(product['memory'])}</span>
            <strong>⌑ 무선</strong><span>{html.escape(product['wireless'])}</span>
          </div>
          <div class="product-reason">{html.escape(product['reason'])}</div>
          <div style="color:#677180;font-size:.72rem;margin-top:.55rem;line-height:1.55;">{html.escape(limitations)}</div>
          <a href="{html.escape(product['url'], quote=True)}" target="_blank" rel="noopener noreferrer" style="display:block;margin-top:.65rem;text-align:center;border:1px solid #ed003f;border-radius:7px;padding:.42rem;color:#ed003f;text-decoration:none;font-size:.8rem;font-weight:700;">자세히 보기 ↗</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_recommendation_page() -> None:
    """Render the mock product recommendation form and results."""

    render_hero(
        "나에게 맞는 Raspberry Pi 찾기",
        "Raspberry Pi",
        "사용 목적과 필요한 기능을 선택하면 공식 사양을 바탕으로 후보를 비교해 드려요.",
    )

    with st.form("recommendation_form"):
        purpose = st.text_input(
            "어디에 사용하실 건가요?",
            value=st.session_state.get("purpose", "모니터 없이 홈 서버로 사용하고 싶어요."),
            placeholder="예: 모니터 없이 홈 서버로 사용하고 싶어요.",
        )
        st.caption("사용 목적과 환경을 자유롭게 적어주세요.")
        st.markdown("**추가 조건**")
        c1, c2, c3, c4, c5, c6 = st.columns([1.15, 1.15, .8, .8, .8, .8])
        with c1:
            user_level = st.selectbox("사용자 수준", ["입문자", "중급자", "고급자"])
        with c2:
            performance = st.selectbox("성능 우선순위", ["낮음", "보통", "높음"], index=1)
        with c3:
            wifi = st.toggle("Wi-Fi 필요", value=True)
        with c4:
            camera = st.toggle("카메라 사용", value=False)
        with c5:
            gpio = st.toggle("GPIO 사용", value=False)
        with c6:
            monitor_absent = st.toggle("모니터 없음", value=True)
        submitted = st.form_submit_button("추천 결과 보기  ✨", use_container_width=True)

    if "recommendation_conditions" not in st.session_state:
        st.session_state.recommendation_conditions = recommendation_conditions(
            purpose, user_level, performance, wifi, camera, gpio, monitor_absent
        )

    if submitted:
        if not purpose.strip():
            st.error("사용 목적을 한 문장 이상 입력해 주세요.")
            return
        with st.spinner("입력 조건을 분석하고 공식 사양을 확인하는 중입니다…"):
            time.sleep(0.35)
        st.session_state.purpose = purpose
        st.session_state.recommendation_conditions = recommendation_conditions(
            purpose, user_level, performance, wifi, camera, gpio, monitor_absent
        )

    with st.expander("🧩 추출된 조건 JSON · mock", expanded=False):
        st.json(st.session_state.recommendation_conditions)
        st.caption("실제 연동 후에는 sLLM이 생성하고 JSON Schema를 통과한 값만 표시됩니다.")

    section_title("추천 제품 3가지", "조건 충족")
    columns = st.columns(3, gap="medium")
    for column, product in zip(columns, PRODUCTS, strict=True):
        with column:
            product_card(product)

    section_title("한눈에 비교")
    comparison_rows = {
        "항목": ["성능", "무선 연결", "크기", "추천 용도"],
        **{
            product["name"]: [
                product["performance"], product["wireless"], product["size"], product["use_case"]
            ]
            for product in PRODUCTS
        },
    }
    st.dataframe(comparison_rows, hide_index=True, use_container_width=True)

    section_title("추천 근거")
    render_sources(RECOMMENDATION_SOURCES)
    st.caption("제품 이미지: © Raspberry Pi Ltd · Raspberry Pi Documentation · CC BY-SA 4.0 · 변경 없음(파일명만 변경)")


def answer_label_class(status: str) -> str:
    """Return a visual class for answer status labels."""

    return "blocked" if status in {"out_of_scope", "safety_blocked", "needs_clarification"} else ""


def render_answer(response: dict) -> None:
    """Render the answer body, steps, and safe warning."""

    rows = "".join(
        f'<div class="step-row"><span class="step-number">{index}</span><strong>{html.escape(step)}</strong></div>'
        for index, step in enumerate(response["steps"], start=1)
    )
    st.markdown(
        f"""
        <div class="answer-card">
          <div class="answer-label {answer_label_class(response['status'])}">● {html.escape(response['label'])}</div>
          <h3>{html.escape(response['title'])}</h3>
          <p>{html.escape(response['intro'])}</p>
          {rows}
          <div class="warning-box">⚠ {html.escape(response['warning'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def submit_qa(question: str) -> None:
    """Update session state with a deterministic mock response."""

    st.session_state.qa_question = question.strip()
    st.session_state.qa_response = mock_qa_response(question)


def render_qa_page() -> None:
    """Render the mock document-grounded question answering screen."""

    render_hero(
        "무엇이 궁금하신가요?",
        None,
        "사용법, 문제 해결, 공식 지원 절차를 문서 근거와 함께 알려드려요.",
    )

    categories = st.columns(3)
    for column, icon, label in zip(
        categories, ["💻", "🔧", "🛡️"], ["설치·사용법", "문제 해결", "A/S·리콜"], strict=True
    ):
        with column:
            st.markdown(f'<div class="qa-category"><span style="font-size:1.5rem">{icon}</span>&nbsp;&nbsp;{label}</div>', unsafe_allow_html=True)

    if "qa_question" not in st.session_state:
        submit_qa("Raspberry Pi 5에 OS를 설치했는데 부팅이 되지 않아요.")
    response = st.session_state.qa_response

    st.markdown(f'<div class="user-bubble">{html.escape(st.session_state.qa_question)}</div>', unsafe_allow_html=True)
    left, right = st.columns([1.35, 1], gap="large")
    with left:
        render_answer(response)
        with st.expander("🧩 조건 JSON과 응답 상태 · mock", expanded=False):
            st.json({"status": response["status"], "mode": "mock", "conditions": response["conditions"]})
    with right:
        section_title(f"공식 문서 출처 {len(response['sources'])}건")
        render_sources(response["sources"])
        section_title("관련 질문")
        for index, related in enumerate(response["related"]):
            if st.button(f"{related}  ›", key=f"related_{index}", use_container_width=True):
                with st.spinner("공식 문서 근거를 확인하는 중입니다…"):
                    time.sleep(0.25)
                submit_qa(related)
                st.rerun()

    st.markdown("---")
    with st.form("qa_form", clear_on_submit=False):
        c1, c2 = st.columns([8, 1.2])
        with c1:
            question = st.text_input("질문", placeholder="질문을 입력하세요", label_visibility="collapsed")
        with c2:
            sent = st.form_submit_button("✈ 보내기", use_container_width=True)
        st.caption("🛡 입력한 내용은 명령으로 실행되지 않습니다. 검색 근거가 없으면 답변을 보류합니다.")
    if sent:
        if not question.strip():
            st.warning("질문을 입력해 주세요.")
        else:
            with st.spinner("질문을 분석하고 공식 문서를 검색하는 중입니다…"):
                time.sleep(0.35)
            submit_qa(question)
            st.rerun()


def render_about_page() -> None:
    """Render a compact project introduction for the shared navigation."""

    render_hero(
        "공식 근거로 더 안심하고 시작하세요",
        "공식 근거",
        "PiCare는 Raspberry Pi 입문자의 제품 선택과 설치·문제 해결을 돕는 비공식 교육용 프로젝트입니다.",
    )
    cards = st.columns(3)
    items = [
        ("🧩", "조건을 구조화", "사용 목적과 환경을 고정 JSON으로 정리합니다."),
        ("🔎", "공식 문서만 검색", "검증된 Raspberry Pi 문서에서만 근거를 찾습니다."),
        ("🛡️", "근거가 없으면 보류", "확인할 수 없는 내용은 추측하지 않습니다."),
    ]
    for column, (icon, title, text) in zip(cards, items, strict=True):
        with column:
            st.markdown(f'<div class="answer-card" style="text-align:center;min-height:180px"><div style="font-size:2.2rem">{icon}</div><h3>{title}</h3><p>{text}</p></div>', unsafe_allow_html=True)
    st.info("현재 화면은 mock 데이터로 동작합니다. sLLM·RAG·metadata 연동 후에도 동일한 표시 계약을 사용할 예정입니다.")


page = render_header(current_page())
if page == "recommend":
    render_recommendation_page()
elif page == "qa":
    render_qa_page()
else:
    render_about_page()
