"""PiCare Streamlit UI connected to the shared recommendation and RAG services."""

from __future__ import annotations

import html
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from src.condition_extraction.ui_input import RecommendationFormInput
from src.contracts import ChatResponse, MediaItem
from streamlit_app.runtime import (
    build_qa_service,
    build_recommendation_service,
    check_runtime_readiness,
)
from streamlit_app.styles import APP_CSS


st.set_page_config(
    page_title="PiCare | Raspberry Pi 공식 문서 기반 도우미",
    page_icon="🍓",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(APP_CSS, unsafe_allow_html=True)


RUNTIME_READINESS = check_runtime_readiness(ROOT)


@st.cache_resource(show_spinner=False)
def qa_chat_service():
    """Keep one real QA service for the Streamlit process."""

    return build_qa_service(ROOT)


@st.cache_resource(show_spinner=False)
def recommendation_service():
    """Keep the model, catalog, and retriever assembly across Streamlit reruns."""

    return build_recommendation_service(ROOT)


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
          <div class="mock-ribbon">✨ 실제 서비스 연결 · ChatResponse 1.2.0</div>
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


def _value(item, name: str, default=""):
    """Read a field from a Pydantic contract or a legacy mapping."""

    return getattr(item, name, item.get(name, default) if isinstance(item, dict) else default)


def render_sources(sources) -> None:
    """Render citation metadata without asking an LLM to generate it."""

    if not sources:
        st.info("표시할 공식 검색 근거가 없습니다. 출처를 추측하지 않습니다.")
        return
    for source in sources:
        citation = _value(source, "citation_id")
        citation_text = f"{html.escape(citation)} · " if citation else ""
        title = str(_value(source, "title"))
        section = str(_value(source, "section"))
        license_name = str(_value(source, "license"))
        url = str(_value(source, "source_url", _value(source, "url")))
        st.markdown(
            f"""
            <div class="source-card">
              <div class="source-icon">📄</div>
              <div>
                <div class="source-title">{citation_text}{html.escape(title)}</div>
                <div class="source-meta">Section: {html.escape(section)} &nbsp; · &nbsp; {html.escape(license_name)}</div>
              </div>
              <a class="source-link" href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer" aria-label="공식 문서 열기">↗</a>
            </div>
            """,
            unsafe_allow_html=True,
        )


def product_card(product) -> None:
    """Render one server-validated ProductRecommendation contract."""

    name = str(product.product_model)
    image = str(product.image_url) if product.image_url else ""
    limitations = " ".join(product.limitations) or "추가 유의사항 없음"
    citation_ids = ", ".join(product.citation_ids)
    st.markdown(
        f"""
        <div class="product-card">
          <span class="product-badge tone-red">공식 근거 {html.escape(citation_ids)}</span>
          {f'<img src="{html.escape(image, quote=True)}" alt="{html.escape(name)}" style="width:100%;height:155px;object-fit:contain;" />' if image else ''}
          <div class="product-name">{html.escape(name)}</div>
          <div class="product-reason">{html.escape(product.recommendation)}</div>
          <div style="color:#677180;font-size:.72rem;margin-top:.55rem;line-height:1.55;">{html.escape(limitations)}</div>
          <a href="{html.escape(str(product.product_url), quote=True)}" target="_blank" rel="noopener noreferrer" style="display:block;margin-top:.65rem;text-align:center;border:1px solid #ed003f;border-radius:7px;padding:.42rem;color:#ed003f;text-decoration:none;font-size:.8rem;font-weight:700;">자세히 보기 ↗</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_recommendation_page() -> None:
    """Render the product form and the real recommendation service response."""

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

    if submitted:
        if not purpose.strip():
            st.error("사용 목적을 한 문장 이상 입력해 주세요.")
            return
        form = RecommendationFormInput.from_widget_values(
            request_id=str(uuid.uuid4()),
            free_text=purpose.strip(),
            user_level_label=user_level,
            performance_priority_label=performance,
            wireless_required=wifi,
            camera_required=camera,
            gpio_required=gpio,
            monitor_absent=monitor_absent,
        )
        try:
            with st.spinner("조건 분석 → catalog 필터 → Hybrid RAG → 답변 검증 중…"):
                st.session_state.recommendation_response = recommendation_service().answer_form(
                    form=form,
                    trace=True,
                )
            st.session_state.purpose = purpose
        except Exception as exc:
            st.error(f"제품 추천 런타임을 준비하지 못했습니다: {exc}")

    response: ChatResponse | None = st.session_state.get("recommendation_response")
    if response is None:
        if not RUNTIME_READINESS.ready:
            st.warning(RUNTIME_READINESS.message)
        return

    render_answer(response)
    if response.conditions is not None:
        with st.expander("🧩 검증된 조건 JSON", expanded=False):
            st.json(response.conditions.model_dump(mode="json"))

    section_title(f"추천 제품 {len(response.products)}개", response.status)
    if response.products:
        columns = st.columns(len(response.products), gap="medium")
        for column, product in zip(columns, response.products, strict=True):
            with column:
                product_card(product)

    section_title("추천 근거")
    render_sources(response.citations)
    render_citation_media(response.media)
    st.caption("제품·출처 카드는 모델이 아니라 검증된 catalog와 manifest metadata에서 조립됩니다.")


def answer_label_class(status: str) -> str:
    """Return a visual class for answer status labels."""

    blocked = {
        "error",
        "insufficient_evidence",
        "needs_clarification",
        "out_of_scope",
        "safety_blocked",
    }
    return "blocked" if status in blocked else ""


def render_citation_media(media_items: list[MediaItem]) -> None:
    """Render only guide media already resolved from final citations by the server."""

    if not media_items:
        return
    section_title("인용 근거와 연결된 이미지·영상")
    for item in media_items:
        if item.media_type == "image":
            st.image(str(item.url), caption=item.alt_text or item.title, use_container_width=True)
        else:
            st.video(str(item.url))
        st.caption(
            f"{item.title} · {item.source_citation_id} · "
            f"{item.attribution} · {item.license}"
        )


def render_answer(response: ChatResponse) -> None:
    """Render the canonical answer without reinterpreting service output."""

    status_labels = {
        "answered": "근거 확인 완료",
        "needs_clarification": "추가 정보 필요",
        "insufficient_evidence": "근거 부족",
        "out_of_scope": "답변 범위 외",
        "safety_blocked": "안전 정책으로 보류",
        "error": "실행 오류",
    }
    status = response.status
    st.markdown(
        f'<div class="answer-label {answer_label_class(status)}">● {html.escape(status_labels[status])}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(response.answer)
    for question in response.clarification_questions:
        st.info(question)
    if response.warnings:
        with st.expander("실행 추적 정보", expanded=False):
            st.code("\n".join(response.warnings), language=None)


def submit_qa(question: str) -> None:
    """Run the real document-grounded chain and store its contract response."""

    st.session_state.qa_question = question.strip()
    st.session_state.qa_response = qa_chat_service().answer(
        request_id=str(uuid.uuid4()),
        question=question.strip(),
        retrieval_mode="hybrid",
        trace=True,
    )


def render_qa_page() -> None:
    """Render the document-grounded QA screen."""

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

    response: ChatResponse | None = st.session_state.get("qa_response")
    if response is not None:
        st.markdown(f'<div class="user-bubble">{html.escape(st.session_state.qa_question)}</div>', unsafe_allow_html=True)
        left, right = st.columns([1.35, 1], gap="large")
        with left:
            render_answer(response)
        with right:
            section_title(f"공식 문서 출처 {len(response.citations)}건")
            render_sources(response.citations)
            render_citation_media(response.media)
    elif not RUNTIME_READINESS.ready:
        st.warning(RUNTIME_READINESS.message)

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
            try:
                with st.spinner("공식 문서 Hybrid 검색과 답변 인용 검증 중…"):
                    submit_qa(question)
                st.rerun()
            except Exception as exc:
                st.error(f"QA 런타임을 준비하지 못했습니다: {exc}")


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
    if RUNTIME_READINESS.ready:
        st.success(RUNTIME_READINESS.message)
    else:
        st.warning(RUNTIME_READINESS.message)


page = render_header(current_page())
if page == "recommend":
    render_recommendation_page()
elif page == "qa":
    render_qa_page()
else:
    render_about_page()
