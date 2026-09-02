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
from src.presentation import CitationPresenter, load_citation_presenter
from src.rag import RagSettings
from streamlit_app.runtime import (
    build_qa_service,
    build_recommendation_service,
    check_runtime_readiness,
)
from streamlit_app.streaming import iter_text_chunks
from streamlit_app.styles import APP_CSS


st.set_page_config(
    page_title="PiCare | Raspberry Pi 공식 문서 기반 도우미",
    page_icon="🍓",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(APP_CSS, unsafe_allow_html=True)


RUNTIME_READINESS = check_runtime_readiness(ROOT)

# 카드 위 요약 배지는 추천 화면 전용 문구를 쓴다. 답변 상태 라벨은
# QA 화면과 공유하므로 render_answer의 문구를 그대로 유지한다.
RECOMMENDATION_STATUS_LABELS = {
    "answered": "조건 충족",
    "needs_clarification": "추가 정보 필요",
    "insufficient_evidence": "근거 부족",
    "out_of_scope": "답변 범위 외",
    "safety_blocked": "안전 정책으로 보류",
    "error": "실행 오류",
}


@st.cache_resource(show_spinner=False)
def citation_presenter() -> CitationPresenter | None:
    """출처 표시 사전이 없어도 QA 자체는 계속 동작하게 한다."""

    try:
        return load_citation_presenter(RagSettings.from_env(ROOT).manifest_path)
    except Exception:
        return None


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

    page = st.query_params.get("page", "about")
    page = page if page in {"about", "recommend", "qa"} else "about"
    previous_page = st.session_state.get("active_page")
    if previous_page is not None and previous_page != page:
        for key in (
            "recommendation_response",
            "qa_response",
            "qa_question",
            "qa_history",
        ):
            st.session_state.pop(key, None)
    st.session_state.active_page = page
    return page


def render_header(page: str) -> str:
    """Render functional Streamlit navigation for the live service."""

    page_labels = {
        "about": "서비스 소개",
        "recommend": "제품 추천",
        "qa": "질의응답",
    }
    with st.container(key="topbar"):
        brand, navigation_area, _ = st.columns([1, 1.5, 1], vertical_alignment="center")
        with brand:
            st.markdown('<div class="picare-brand">🍓PiCare</div>', unsafe_allow_html=True)
        with navigation_area:
            with st.container(key="top_navigation"):
                navigation = st.columns(3, gap="small", vertical_alignment="center")
                for column, (target, label) in zip(navigation, page_labels.items(), strict=True):
                    with column:
                        if st.button(
                            label,
                            key=f"top_navigation_{target}",
                            type="primary" if target == page else "secondary",
                            use_container_width=False,
                        ):
                            st.query_params["page"] = target
                            st.rerun()
    st.markdown('<div class="picare-header-line"></div>', unsafe_allow_html=True)
    return page


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


def render_sources(sources, *, preferred_use_case: str | None = None) -> None:
    """Render citation metadata without asking an LLM to generate it."""

    if not sources:
        st.info("표시할 공식 검색 근거가 없습니다. 출처를 추측하지 않습니다.")
        return
    presenter = citation_presenter()
    for source in sources:
        citation = _value(source, "citation_id")
        if presenter is not None:
            display = presenter.present(source, preferred_use_case=preferred_use_case)
            citation_text = f"{html.escape(display.citation_id)} · "
            title = display.document_label
            section = display.section_label
            tags = " · ".join(display.tags) if display.tags else "없음"
        else:
            citation_text = f"{html.escape(citation)} · " if citation else ""
            title = str(_value(source, "title"))
            section = str(_value(source, "section")).rsplit(" > ", maxsplit=1)[-1]
            tags = "없음"
        url = str(_value(source, "source_url", _value(source, "url")))
        st.markdown(
            f"""
            <div class="source-card">
              <div class="source-icon">📄</div>
              <div>
                <div class="source-title">{citation_text}{html.escape(title)}</div>
                <div class="source-meta">섹션: {html.escape(section)}</div>
                <div class="source-meta">태그: {html.escape(tags)}</div>
              </div>
              <a class="source-link" href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer" aria-label="공식 문서 열기">↗</a>
            </div>
            """,
            unsafe_allow_html=True,
        )


RANK_TONES = ("tone-best", "tone-mid", "tone-light")
RANK_LABELS = ("⭐ 가장 추천", "2순위 추천", "3순위 추천")


def rank_tone(rank: int) -> str:
    """Return the card accent class for a 1-based recommendation rank."""

    return RANK_TONES[min(rank, len(RANK_TONES)) - 1]


def rank_label(rank: int) -> str:
    """Return the rank badge text; ranking comes from the scored candidates."""

    return RANK_LABELS[rank - 1] if rank <= len(RANK_LABELS) else f"{rank}순위 추천"


def product_card(product, rank: int) -> str:
    """Render one server-validated ProductRecommendation contract."""

    name = str(product.product_model)
    image = str(product.image_url) if product.image_url else ""
    tone = rank_tone(rank)
    stage = (
        f'<img src="{html.escape(image, quote=True)}" alt="{html.escape(name)}" class="product-image" />'
        if image
        else '<span class="product-image-empty">공식 이미지 없음</span>'
    )
    specs = "".join(
        f'<div class="spec-row"><span class="spec-key">{html.escape(key)}</span>'
        f'<span class="spec-value">{html.escape(value)}</span></div>'
        for key, value in (
            ("CPU", product.specs.cpu),
            ("RAM", product.specs.memory),
            ("무선", product.specs.wireless),
        )
    )
    tagline = product.matched_conditions[0] if product.matched_conditions else product.recommendation
    return f"""
        <article class="product-card">
          <div class="product-card-top">
            <span class="product-rank {tone}">{html.escape(rank_label(rank))}</span>
            <div class="product-name">{html.escape(name)}</div>
          </div>
          <div class="product-card-main">
            <div class="product-stage">{stage}</div>
            <div class="spec-list">{specs}</div>
          </div>
          <div class="product-card-foot">
            <span class="product-tagline {tone}">{html.escape(tagline)}</span>
            <a class="product-link" href="{html.escape(str(product.product_url), quote=True)}" target="_blank" rel="noopener noreferrer">자세히 보기</a>
          </div>
        </article>
        """


def comparison_table(products) -> str:
    """Compare the recommended products using reviewed catalog specs only."""

    headers = "".join(
        f'<th class="{rank_tone(rank)}">{html.escape(str(product.product_model))}</th>'
        for rank, product in enumerate(products, start=1)
    )
    rows = ""
    for label, read in (
        ("CPU", lambda item: item.specs.cpu),
        ("메모리", lambda item: item.specs.memory),
        ("무선 연결", lambda item: item.specs.wireless),
        ("크기", lambda item: item.specs.dimensions or "공식 문서 미확인"),
        (
            "충족한 조건",
            lambda item: ", ".join(item.matched_conditions) or item.recommendation,
        ),
    ):
        cells = "".join(f"<td>{html.escape(str(read(product)))}</td>" for product in products)
        rows += f"<tr><th>{html.escape(label)}</th>{cells}</tr>"
    return f"""
        <div class="compare-wrap">
          <table class="compare-table">
            <thead><tr><th>항목</th>{headers}</tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
        """


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
        st.markdown('<div class="form-group-label">추가 조건</div>', unsafe_allow_html=True)
        c1, c2, c3, c4, c5, c6, c7 = st.columns(
            [1.15, 1.15, .78, .78, .78, .78, 1.35], vertical_alignment="bottom"
        )
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
        with c7:
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
            with st.status("추천을 준비하고 있습니다…", expanded=True) as progress:
                progress.write("입력한 목적과 필수 조건을 확인하고 있습니다.")
                progress.write("조건 JSON → 제품 catalog → 공식 문서 근거 순서로 검증합니다.")
                st.session_state.recommendation_response = recommendation_service().answer_form(
                    form=form,
                    trace=True,
                )
                progress.write("추천 제품과 인용 근거의 일치를 확인했습니다.")
                progress.update(label="추천 답변 준비 완료", state="complete", expanded=False)
            st.session_state.purpose = purpose
        except Exception as exc:
            st.error(f"제품 추천 런타임을 준비하지 못했습니다: {exc}")

    response: ChatResponse | None = st.session_state.get("recommendation_response")
    if response is None:
        if not RUNTIME_READINESS.ready:
            st.warning(RUNTIME_READINESS.message)
        return

    section_title(
        f"추천 제품 {len(response.products)}가지",
        RECOMMENDATION_STATUS_LABELS[response.status],
    )
    if response.products:
        cards = "".join(
            product_card(product, rank).strip()
            for rank, product in enumerate(response.products, start=1)
        )
        st.markdown(f'<div class="product-grid">{cards}</div>', unsafe_allow_html=True)

        if len(response.products) > 1:
            section_title("한눈에 비교")
            st.markdown(comparison_table(response.products), unsafe_allow_html=True)

    section_title("추천 근거")
    with st.container(key="recommendation_evidence"):
        render_sources(
            response.citations,
            preferred_use_case=response.conditions.use_case if response.conditions else None,
        )
    render_citation_media(response.media, grid_images=True)
    render_answer(response, stream_key="recommendation")
    if response.conditions is not None:
        with st.expander("🧩 검증된 조건 JSON", expanded=False):
            st.json(response.conditions.model_dump(mode="json"))


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


def render_citation_media(
    media_items: list[MediaItem],
    *,
    grid_images: bool = False,
    show_title: bool = True,
    container_key_prefix: str = "citation_media",
) -> None:
    """Render only guide media already resolved from final citations by the server."""

    if not media_items:
        return
    with st.container(key=f"{container_key_prefix}_card"):
        if show_title:
            section_title("인용 근거와 연결된 이미지·영상")

        images = [item for item in media_items if item.media_type == "image"]
        videos = [item for item in media_items if item.media_type != "image"]

        def render_media_item(item: MediaItem) -> None:
            if item.media_type == "image":
                st.image(str(item.url), caption=item.alt_text or item.title, use_container_width=True)
            else:
                st.video(str(item.url))
            st.caption(
                f"{item.title} · {item.source_citation_id} · "
                f"{item.attribution} · {item.license}"
            )

        if grid_images and len(images) == 1:
            with st.container(key=f"{container_key_prefix}_single"):
                _, center, _ = st.columns([1, 2, 1])
                with center:
                    render_media_item(images[0])
        elif grid_images and len(images) > 1:
            with st.container(key=f"{container_key_prefix}_grid"):
                for start in range(0, len(images), 2):
                    columns = st.columns(2, gap="medium")
                    for column, item in zip(columns, images[start : start + 2], strict=False):
                        with column:
                            render_media_item(item)
        else:
            for item in images:
                render_media_item(item)

        for item in videos:
            render_media_item(item)


def render_answer(response: ChatResponse, *, stream_key: str) -> None:
    """Render a validated answer once with a typewriter-style stream."""

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
    streamed_request_key = f"{stream_key}_streamed_request_id"
    if st.session_state.get(streamed_request_key) != response.request_id:
        st.write_stream(iter_text_chunks(response.answer))
        st.session_state[streamed_request_key] = response.request_id
    else:
        st.markdown(response.answer)
    for question in response.clarification_questions:
        st.info(question)
    if response.warnings:
        with st.expander("실행 추적 정보", expanded=False):
            st.code("\n".join(response.warnings), language=None)


def submit_qa(question: str) -> None:
    """Run the real document-grounded chain and store the latest UI response."""

    clean_question = question.strip()
    st.session_state.qa_question = clean_question
    response = qa_chat_service().answer(
        request_id=str(uuid.uuid4()),
        question=clean_question,
        retrieval_mode="hybrid",
        trace=True,
    )
    st.session_state.qa_response = response
    history = st.session_state.setdefault("qa_history", [])
    history.append((clean_question, response))


def render_qa_page() -> None:
    """Render the document-grounded QA screen."""

    history: list[tuple[str, ChatResponse]] = st.session_state.get("qa_history", [])
    legacy_response: ChatResponse | None = st.session_state.get("qa_response")
    if not history and legacy_response is not None and st.session_state.get("qa_question"):
        history = [(st.session_state.qa_question, legacy_response)]

    with st.container(key="qa_workspace"):
        if history:
            title_column, action_column = st.columns([6, 1.15], vertical_alignment="center")
            with title_column:
                st.markdown(
                    '<div class="qa-conversation-heading">'
                    '<span class="qa-conversation-mark">🍓</span>'
                    '<div><strong>PiCare 질의응답</strong>'
                    '<small>Raspberry Pi 공식 문서를 바탕으로 답변합니다</small></div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            with action_column:
                if st.button("＋ 새 대화", key="qa_new_conversation", use_container_width=True):
                    for key in ("qa_response", "qa_question", "qa_history", "qa_streamed_request_id"):
                        st.session_state.pop(key, None)
                    st.rerun()

            st.markdown('<div class="qa-thread-divider"></div>', unsafe_allow_html=True)
            for index, (question, response) in enumerate(history):
                with st.container(key=f"qa_user_message_{index}"):
                    st.markdown(
                        '<div class="qa-message-user">'
                        f'<div class="qa-message-copy">{html.escape(question)}</div>'
                        '<div class="qa-avatar qa-avatar-user">나</div>'
                        '</div>',
                        unsafe_allow_html=True,
                    )

                with st.container(key=f"qa_assistant_message_{index}"):
                    st.markdown(
                        '<div class="qa-message-head">'
                        '<div class="qa-avatar qa-avatar-assistant">🍓</div>'
                        '<div><strong>PiCare</strong><small>공식 문서 기반 답변</small></div>'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                    render_answer(response, stream_key=f"qa_{index}")
                    if response.media:
                        with st.expander("답변과 연결된 이미지·영상", expanded=False):
                            render_citation_media(
                                response.media,
                                grid_images=True,
                                show_title=False,
                                container_key_prefix=f"qa_media_{index}",
                            )
                    with st.expander(f"공식 문서 출처 {len(response.citations)}건", expanded=False):
                        render_sources(response.citations)
        else:
            with st.container(key="qa_empty_state"):
                st.markdown(
                    '<div class="qa-empty-icon">🍓</div>'
                    '<h1>무엇이 궁금하신가요?</h1>'
                    '<p>사용법, 문제 해결, 공식 지원 절차를 검증된 문서 근거와 함께 알려드려요.</p>',
                    unsafe_allow_html=True,
                )

                categories = st.columns(3, gap="medium")
                for column, icon, label, description in zip(
                    categories,
                    ["💻", "🔧", "🛡️"],
                    ["설치·사용법", "문제 해결", "A/S·리콜"],
                    ["OS 설치와 초기 설정", "오류 원인과 점검 순서", "공식 지원 절차 확인"],
                    strict=True,
                ):
                    with column:
                        st.markdown(
                            '<div class="qa-category">'
                            f'<span>{icon}</span><strong>{label}</strong><small>{description}</small>'
                            '</div>',
                            unsafe_allow_html=True,
                        )

            if not RUNTIME_READINESS.ready:
                st.warning(RUNTIME_READINESS.message)

        st.markdown(
            '<div class="qa-safety-note">🛡️ 입력한 내용은 명령으로 실행되지 않으며, '
            '검색 근거가 없으면 답변을 보류합니다.</div>',
            unsafe_allow_html=True,
        )

    question = st.chat_input("Raspberry Pi에 대해 무엇이든 물어보세요", key="qa_chat_input")
    if question:
        try:
            with st.status("공식 근거를 확인하고 있습니다…", expanded=True) as progress:
                progress.write("질문 범위와 안전 정책을 확인하고 있습니다.")
                progress.write("공식 문서에서 관련 청크를 검색하고 있습니다.")
                submit_qa(question)
                progress.write("답변의 핵심 주장과 인용 근거를 검증했습니다.")
                progress.update(label="근거 기반 답변 준비 완료", state="complete", expanded=False)
            st.rerun()
        except Exception as exc:
            st.error(f"QA 런타임을 준비하지 못했습니다: {exc}")


def render_about_page() -> None:
    """Render a readable project introduction and clear paths into the service."""

    render_hero(
        "Raspberry Pi 시작을 위한 실용 가이드",
        "실용 가이드",
        "제품 선택부터 설치와 문제 해결까지, Raspberry Pi 공식 문서를 바탕으로 필요한 정보를 안내합니다.",
    )
    cards = (
        (
            "🧩",
            "맞춤형 제품 추천",
            "사용 목적과 환경에 맞는 제품·준비 항목 안내",
            "제품 추천 시작하기",
            "?page=recommend",
        ),
        (
            "🔎",
            "사용법·문제 해결 Q&A",
            "공식 문서 기반 사용법·문제 해결 안내",
            "질문 바로 하기",
            "?page=qa",
        ),
    )
    card_markup = "".join(
        f'<div class="about-card" style="width:335px;height:180px">'
        f'<div class="about-card-title"><span class="about-card-icon">{icon}</span>'
        f'<span>{title}</span></div>'
        f'<div class="about-card-body"><p>{text}</p>'
        f'<a class="about-card-action" href="{action_url}">{action_label}<span>→</span></a>'
        f'</div></div>'
        for icon, title, text, action_label, action_url in cards
    )
    st.markdown(
        f'<div class="about-card-grid" style="grid-template-columns:335px 335px">{card_markup}</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="about-abstention">
          <div class="about-abstention-icon">🛡️</div>
          <div>
            <strong>확인할 수 없으면 보류</strong>
            <p>근거가 부족한 내용은 추측하지 않고 추가 확인 정보 안내</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not RUNTIME_READINESS.ready:
        st.info("화면은 열려 있지만, 답변을 만들려면 검색 색인과 모델 실행 환경이 준비되어야 합니다.")
        with st.expander("실행 환경 준비 상태 보기", expanded=False):
            st.code(RUNTIME_READINESS.message, language=None)

    st.markdown(
        """
        <div class="about-source">
          대표 출처: <a href="https://www.raspberrypi.com/documentation/" target="_blank" rel="noopener noreferrer">Raspberry Pi Documentation ↗</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


page = render_header(current_page())
if page == "recommend":
    render_recommendation_page()
elif page == "qa":
    render_qa_page()
else:
    render_about_page()
