"""Mock retrieval and answer-generation pipeline for the Streamlit QA page."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Protocol, Sequence

from src.lang import (
    AnswerSafetyError,
    PromptBuildError,
    PromptEvidence,
    build_grounded_answer_messages,
    evaluate_request,
    is_evidence_abstention,
    validate_grounded_answer,
)


@dataclass(frozen=True)
class MockDocument:
    """A retrieved chunk plus server-owned source metadata."""

    citation_id: str
    topic: str
    content: str
    title: str
    section: str
    source_url: str
    license: str

    def to_prompt_evidence(self) -> PromptEvidence:
        """Return only citation-safe fields for the answer prompt."""

        return PromptEvidence(
            citation_id=self.citation_id,
            content=self.content,
            title=self.title,
            section=self.section,
        )

    def to_source_card(self) -> dict[str, str]:
        """Build UI metadata without asking the answer model to create it."""

        return {
            "citation_id": self.citation_id,
            "title": self.title,
            "section": self.section,
            "url": self.source_url,
            "license": self.license,
        }


class DocumentRetriever(Protocol):
    """Replaceable interface for the current mock and future RAG retrievers."""

    def search(self, question: str) -> Sequence[MockDocument]: ...


class AnswerModel(Protocol):
    """Replaceable interface for the current fake and future LLM clients."""

    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        evidence: Sequence[MockDocument],
    ) -> str: ...


_MOCK_DOCUMENTS = {
    "boot": (
        MockDocument(
            citation_id="C1",
            topic="boot",
            content=(
                "부팅 문제를 확인할 때는 먼저 전원 공급 장치와 연결 상태를 확인하고, "
                "Raspberry Pi Imager로 저장장치에 운영체제 이미지를 다시 기록한다."
            ),
            title="Getting started",
            section="Troubleshooting",
            source_url=(
                "https://www.raspberrypi.com/documentation/computers/"
                "getting-started.html#troubleshooting"
            ),
            license="CC BY-SA 4.0",
        ),
        MockDocument(
            citation_id="C2",
            topic="boot",
            content=(
                "Raspberry Pi가 시작되지 않으면 상태 LED의 점멸 패턴을 확인해 "
                "공식 경고 코드와 비교한다."
            ),
            title="LED warning flash codes",
            section="LED warning flash codes",
            source_url=(
                "https://www.raspberrypi.com/documentation/computers/"
                "configuration.html#led-warning-flash-codes"
            ),
            license="CC BY-SA 4.0",
        ),
    ),
    "ssh": (
        MockDocument(
            citation_id="C1",
            topic="ssh",
            content=(
                "Raspberry Pi Imager의 OS 사용자 정의에서 호스트명, 무선 네트워크, "
                "사용자 계정과 SSH를 설정할 수 있다. 부팅 후 같은 네트워크에서 "
                "설정한 계정으로 SSH에 접속한다."
            ),
            title="Remote access",
            section="SSH",
            source_url=(
                "https://www.raspberrypi.com/documentation/computers/"
                "remote-access.html#ssh"
            ),
            license="CC BY-SA 4.0",
        ),
    ),
    "camera": (
        MockDocument(
            citation_id="C1",
            topic="camera",
            content=(
                "카메라를 설치하기 전에 Raspberry Pi 전원을 끄고, 보드에 맞는 "
                "케이블 방향과 커넥터 잠금 상태를 확인한다."
            ),
            title="Camera hardware",
            section="Install a Raspberry Pi camera",
            source_url=(
                "https://www.raspberrypi.com/documentation/accessories/"
                "camera.html#install-a-raspberry-pi-camera"
            ),
            license="CC BY-SA 4.0",
        ),
        MockDocument(
            citation_id="C2",
            topic="camera",
            content=(
                "최신 Raspberry Pi OS에서 rpicam-apps를 사용할 수 있으며, "
                "rpicam-hello로 연결된 카메라의 동작을 확인할 수 있다."
            ),
            title="Camera software",
            section="rpicam-apps",
            source_url=(
                "https://www.raspberrypi.com/documentation/computers/"
                "camera_software.html"
            ),
            license="CC BY-SA 4.0",
        ),
    ),
}


class MockRetriever:
    """Return deterministic official-document fixtures for demo questions."""

    _TOPIC_TERMS = {
        "ssh": ("ssh", "원격", "wi-fi", "wifi", "connect"),
        "camera": ("카메라", "camera", "rpicam"),
        "boot": ("부팅", "os 설치", "os를 설치", "sd 카드", "이미지 다시", "led"),
    }

    def search(self, question: str) -> Sequence[MockDocument]:
        """Search the small fixture collection by stable topic keywords."""

        lowered = question.lower()
        for topic, terms in self._TOPIC_TERMS.items():
            if any(term in lowered for term in terms):
                return _MOCK_DOCUMENTS[topic]
        return ()


class FakeAnswerModel:
    """Generate predictable Korean prose while the real LLM is unavailable."""

    _ANSWERS = {
        "boot": (
            "전원, OS 이미지, 상태 LED를 순서대로 확인해 보세요. [C1] [C2]\n"
            "전원 공급 장치와 연결 상태를 확인하세요. [C1]\n"
            "Raspberry Pi Imager로 OS 이미지를 다시 기록하세요. [C1]\n"
            "상태 LED 점멸 패턴을 공식 경고 코드와 비교하세요. [C2]"
        ),
        "ssh": (
            "Imager에서 SSH와 네트워크를 설정한 뒤 원격으로 접속할 수 있습니다. [C1]\n"
            "Imager의 OS 사용자 정의를 여세요. [C1]\n"
            "호스트명, Wi-Fi, 사용자 계정과 SSH를 설정하세요. [C1]\n"
            "부팅 후 같은 네트워크에서 설정한 계정으로 SSH에 접속하세요. [C1]"
        ),
        "camera": (
            "전원을 끄고 카메라 연결을 확인한 뒤 공식 도구로 테스트하세요. [C1] [C2]\n"
            "전원을 끈 뒤 케이블 방향과 커넥터 잠금을 확인하세요. [C1]\n"
            "최신 Raspberry Pi OS에서 rpicam-apps를 준비하세요. [C2]\n"
            "rpicam-hello로 카메라 동작을 확인하세요. [C2]"
        ),
    }

    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        evidence: Sequence[MockDocument],
    ) -> str:
        """Return a fixture answer after receiving the generated chat prompt."""

        if not messages or not evidence:
            return ""
        return self._ANSWERS[evidence[0].topic]


_TOPIC_PRESENTATION = {
    "boot": {
        "title": "먼저 확인하세요",
        "warning": "문제가 계속되면 사용 중인 전원 장치와 LED 점멸 패턴을 알려주세요.",
        "related": ["SD 카드 OS 다시 설치", "LED 점멸 코드", "공식 지원 문의"],
        "condition_updates": {
            "intent": "troubleshooting",
            "task": "troubleshooting",
            "os_versions": ["Raspberry Pi OS"],
        },
    },
    "ssh": {
        "title": "SSH를 켜고 네트워크 정보를 확인하세요",
        "warning": "비밀번호 인증을 쓰는 경우 강한 비밀번호를 설정하세요.",
        "related": ["Imager에서 Wi-Fi 설정", "Raspberry Pi Connect", "SSH 키 인증"],
        "condition_updates": {
            "intent": "how_to",
            "use_case": "headless_remote_management",
            "task": "remote_access",
            "remote_access_required": True,
        },
    },
    "camera": {
        "title": "전원을 끄고 카메라 케이블부터 확인하세요",
        "warning": "전원이 켜진 상태에서 카메라 케이블을 연결하거나 분리하지 마세요.",
        "related": ["카메라 케이블 연결", "rpicam-hello 사용법", "Camera Module 3 설정"],
        "condition_updates": {
            "intent": "troubleshooting",
            "use_case": "camera_monitoring",
            "task": "troubleshooting",
            "camera_required": True,
        },
    },
}


def _conditions(question: str, **updates: object) -> dict[str, object]:
    """Build the temporary condition payload displayed by the mock UI."""

    model_match = re.search(
        r"(?:raspberry\s*pi|라즈베리\s*파이|pi)\s*([45])", question, re.I
    )
    models = [f"Raspberry Pi {model_match.group(1)}"] if model_match else None
    payload: dict[str, object] = {
        "schema_version": "1.2.0",
        "intent": "qa",
        "use_case": None,
        "product_models": models,
        "os_versions": None,
        "task": None,
        "performance_priority": None,
        "wireless_required": None,
        "camera_required": None,
        "gpio_required": None,
        "monitor_available": None,
        "remote_access_required": None,
        "user_level": None,
        "needs_clarification": False,
        "clarification_questions": [],
    }
    payload.update(updates)
    return payload


def _status_response(
    question: str,
    status: str,
    message: str,
    *,
    reason_code: str | None = None,
) -> dict[str, object]:
    """Convert a safety or pipeline status to the existing Streamlit contract."""

    presentation = {
        "needs_clarification": (
            "추가 정보가 필요해요",
            "질문을 조금 더 구체적으로 적어주세요",
            "모델, OS 버전과 현재 증상을 함께 알려주세요.",
        ),
        "insufficient_evidence": (
            "공식 근거를 찾지 못했어요",
            "근거가 없어 답변을 보류합니다",
            "공식 문서 범위의 제품명과 작업을 포함해 다시 질문해 주세요.",
        ),
        "out_of_scope": (
            "지원 범위 밖 질문",
            "공식 기술 문서 범위에서 답변할 수 없어요",
            "제품 사양·설치·문제 해결에 관한 질문을 남겨 주세요.",
        ),
        "safety_blocked": (
            "안전 규칙에 따라 답변 보류",
            "실행하거나 만들어 낼 수 없는 요청이에요",
            "공식 범위의 설치·환경 설정 질문으로 바꿔 물어보세요.",
        ),
        "error": (
            "답변 검증 실패",
            "안전하게 표시할 수 있는 답변을 만들지 못했어요",
            "잠시 후 다시 질문하거나 질문을 더 구체적으로 적어주세요.",
        ),
    }
    label, title, warning = presentation[status]
    reason_presentations = {
        "prompt_disclosure": (
            "프롬프트 공개 요청은 처리할 수 없어요",
            "내부 지시 보호를 위한 안전 규칙에 해당합니다.",
        ),
        "prompt_injection": (
            "내부 지시를 변경하는 요청은 처리할 수 없어요",
            "사용자 입력에 포함된 명령은 실행하지 않습니다.",
        ),
        "live_commerce_data": (
            "가격·재고 비교는 지원하지 않아요",
            "실시간 판매 정보는 공식 기술 문서에서 확인할 수 없는 범위입니다.",
        ),
        "unsupported_modification": (
            "비공식 개조 방법은 안내하지 않아요",
            "공식 설치·구성·문제 해결 절차만 안내합니다.",
        ),
        "no_official_evidence": (
            "공식 문서 근거를 찾지 못했어요",
            "검색 근거가 없어 추측하지 않고 답변을 보류합니다.",
        ),
    }
    if reason_code in reason_presentations:
        title, warning = reason_presentations[reason_code]
    return {
        "status": status,
        "reason_code": reason_code,
        "mode": "mock_chain",
        "label": label,
        "title": title,
        "intro": message,
        "answer": message,
        "steps": [],
        "warning": warning,
        "conditions": _conditions(
            question,
            intent="out_of_scope"
            if status in {"out_of_scope", "safety_blocked"}
            else "qa",
            needs_clarification=status == "needs_clarification",
            clarification_questions=[warning]
            if status == "needs_clarification"
            else [],
        ),
        "sources": [],
        "related": ["Raspberry Pi 5 부팅 문제", "SSH 설정", "카메라 연결 확인"],
    }


class ChatService:
    """Orchestrate safety, retrieval, prompting, generation, and validation."""

    def __init__(self, *, retriever: DocumentRetriever, model: AnswerModel) -> None:
        self.retriever = retriever
        self.model = model

    def answer(self, question: str) -> dict[str, object]:
        """Return a UI-compatible answer without exposing unvalidated model text."""

        request_decision = evaluate_request(question)
        if not request_decision.allowed:
            return _status_response(
                question,
                request_decision.status,
                request_decision.message,
                reason_code=request_decision.reason_code,
            )

        if _ambiguous_boot_question(question):
            return _status_response(
                question,
                "needs_clarification",
                "부팅 문제는 모델·OS·LED 패턴에 따라 확인 절차가 달라집니다.",
            )

        try:
            documents = tuple(self.retriever.search(question))
        except Exception:
            return _status_response(
                question,
                "error",
                "공식 문서 검색 중 오류가 발생해 답변을 보류합니다.",
            )

        evidence_decision = evaluate_request(question, evidence_count=len(documents))
        if not evidence_decision.allowed:
            return _status_response(
                question,
                evidence_decision.status,
                evidence_decision.message,
                reason_code=evidence_decision.reason_code,
            )

        evidence = tuple(document.to_prompt_evidence() for document in documents)
        try:
            messages = build_grounded_answer_messages(question, evidence)
            generated_answer = self.model.generate(messages, documents)
            if is_evidence_abstention(generated_answer):
                return _status_response(
                    question, "insufficient_evidence",
                    "검색된 공식 문서만으로 질문에 답할 수 없어 답변을 보류합니다.",
                    reason_code="model_insufficient_evidence",
                )
            used_citations = validate_grounded_answer(
                generated_answer,
                allowed_citation_ids=[item.citation_id for item in documents],
            )
        except (AnswerSafetyError, PromptBuildError, ValueError, KeyError):
            return _status_response(
                question,
                "error",
                "생성된 답변이 인용·URL 안전 검사를 통과하지 못해 표시를 보류합니다.",
            )
        except Exception:
            return _status_response(
                question,
                "error",
                "답변 생성 중 오류가 발생해 표시를 보류합니다.",
            )

        lines = [line.strip() for line in generated_answer.splitlines() if line.strip()]
        topic = documents[0].topic
        view = _TOPIC_PRESENTATION[topic]
        conditions = _conditions(question)
        conditions.update(view["condition_updates"])
        return {
            "status": "answered",
            "mode": "mock_chain",
            "label": "공식 문서에서 확인한 답변",
            "title": view["title"],
            "intro": lines[0],
            "answer": generated_answer,
            "steps": lines[1:],
            "warning": view["warning"],
            "conditions": conditions,
            "sources": [
                document.to_source_card()
                for document in documents
                if document.citation_id in used_citations
            ],
            "related": view["related"],
        }


def _ambiguous_boot_question(question: str) -> bool:
    """Require a model name for generic boot-failure questions."""

    lowered = question.lower()
    if "부팅" not in lowered:
        return False
    return (
        re.search(
            r"(?:raspberry\s*pi|라즈베리\s*파이|pi)\s*[45]", question, re.I
        )
        is None
    )


def build_default_mock_chat_service() -> ChatService:
    """Create the dependency combination used before real RAG and LLM wiring."""

    return ChatService(retriever=MockRetriever(), model=FakeAnswerModel())


__all__ = [
    "AnswerModel",
    "ChatService",
    "DocumentRetriever",
    "FakeAnswerModel",
    "MockDocument",
    "MockRetriever",
    "build_default_mock_chat_service",
]
