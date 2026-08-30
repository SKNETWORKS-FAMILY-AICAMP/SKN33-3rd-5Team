"""문서·데이터 담당에게 받을 제품 카탈로그와 추천 결과 계약을 정의한다."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from pathlib import Path

from pydantic import Field, HttpUrl, model_validator

from src.contracts import ConditionPayload
from src.contracts.models import StrictContract, Task, UseCase


class ProductFamily(str, Enum):
    """제품 형태와 사용 성격을 구분하는 Raspberry Pi 계열이다."""

    FLAGSHIP = "flagship"
    KEYBOARD = "keyboard"
    ZERO = "zero"
    COMPUTE_MODULE = "compute_module"
    MICROCONTROLLER = "microcontroller"


class PerformanceTier(str, Enum):
    """팀이 검수한 제품의 상대적 성능 등급이다."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GpioHeader(str, Enum):
    """GPIO 핀 헤더의 장착 상태를 표현한다."""

    POPULATED = "populated"
    UNPOPULATED = "unpopulated"
    NONE = "none"


class SourceRecord(StrictContract):
    """제품 사실의 근거가 되는 공식 문서 한 건이다."""

    document_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    source_url: HttpUrl
    retrieved_at: date
    license: str = Field(min_length=1, max_length=100)


class ProductCapabilities(StrictContract):
    """하드 필터에 사용하는 제품별 연결·입출력 기능이다."""

    wireless: bool
    ethernet: bool
    gpio_header: GpioHeader
    camera_connector_count: int = Field(ge=0, le=8)
    display_output_count: int = Field(ge=0, le=8)
    built_in_keyboard: bool


class ProductDisplayMetadata(StrictContract):
    """제품 카드와 비교표에 표시할 검수 완료 사양 요약이다."""

    cpu: str = Field(min_length=1, max_length=200)
    memory: str = Field(min_length=1, max_length=100)
    wireless: str = Field(min_length=1, max_length=200)
    # 공식 documentation corpus에서 확인되지 않은 크기는 추측하지 않고 숨긴다.
    dimensions: str | None = Field(default=None, max_length=100)


class ProductRecommendationProfile(StrictContract):
    """sLLM이 생성하지 않고 사람이 검수한 추천 판단용 메타데이터다."""

    performance_tier: PerformanceTier
    beginner_friendly: bool
    recommended_use_cases: list[UseCase]
    recommended_tasks: list[Task]


class ProductFieldEvidence(StrictContract):
    """카탈로그의 제품별 사실·추천 기준을 뒷받침하는 문서 ID 묶음이다.

    각 키는 제품 레코드의 같은 이름 사실을 지지한다. 빈 목록은 해당 값이
    카탈로그에 없거나(예: 확인하지 못한 크기), 추천 결과에 쓰지 않는다는 뜻이다.
    """

    identity: list[str] = Field(default_factory=list)
    wireless: list[str] = Field(default_factory=list)
    ethernet: list[str] = Field(default_factory=list)
    gpio_header: list[str] = Field(default_factory=list)
    camera_connector_count: list[str] = Field(default_factory=list)
    display_output_count: list[str] = Field(default_factory=list)
    built_in_keyboard: list[str] = Field(default_factory=list)
    cpu: list[str] = Field(default_factory=list)
    memory: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    recommendation_profile: list[str] = Field(default_factory=list)
    required_accessories: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_ids_are_unique(self) -> "ProductFieldEvidence":
        for field_name in type(self).model_fields:
            document_ids = getattr(self, field_name)
            if len(document_ids) != len(set(document_ids)):
                raise ValueError(f"evidence_by_field.{field_name}에 중복 document_id가 있습니다.")
        return self

    def all_document_ids(self) -> list[str]:
        """필드별 근거를 정렬된 중복 없는 제품 근거 목록으로 만든다."""

        return sorted(
            {
                document_id
                for field_name in type(self).model_fields
                for document_id in getattr(self, field_name)
            }
        )


class ProductRecord(StrictContract):
    """제품 정보·추천 기준·공식 근거를 묶은 카탈로그 레코드다."""

    product_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    aliases: list[str] = Field(default_factory=list)
    family: ProductFamily
    is_current: bool
    memory_options_gb: list[float] = Field(min_length=1)
    capabilities: ProductCapabilities
    display: ProductDisplayMetadata
    recommendation_profile: ProductRecommendationProfile
    required_accessories: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    evidence_by_field: ProductFieldEvidence
    document_ids: list[str] = Field(min_length=1)
    product_url: HttpUrl
    image_url: HttpUrl | None

    @model_validator(mode="after")
    def values_are_unique(self) -> "ProductRecord":
        """메모리·별칭·문서 ID의 유효 범위와 중복 여부를 검사한다."""

        if any(option <= 0 for option in self.memory_options_gb):
            raise ValueError("memory_options_gb는 0보다 커야 합니다.")
        if len(self.memory_options_gb) != len(set(self.memory_options_gb)):
            raise ValueError("memory_options_gb에 중복 값이 있습니다.")
        if len(self.aliases) != len(set(alias.casefold() for alias in self.aliases)):
            raise ValueError("aliases에 대소문자만 다른 중복 값이 있습니다.")
        if len(self.document_ids) != len(set(self.document_ids)):
            raise ValueError("document_ids에 중복 값이 있습니다.")
        if self.document_ids != self.evidence_by_field.all_document_ids():
            raise ValueError(
                "document_ids는 evidence_by_field의 정렬된 중복 제거 합집합과 같아야 합니다."
            )

        required_evidence = (
            "identity",
            "wireless",
            "ethernet",
            "gpio_header",
            "camera_connector_count",
            "display_output_count",
            "built_in_keyboard",
            "cpu",
            "memory",
            "recommendation_profile",
        )
        missing = [
            field_name
            for field_name in required_evidence
            if not getattr(self.evidence_by_field, field_name)
        ]
        if self.display.dimensions is not None and not self.evidence_by_field.dimensions:
            missing.append("dimensions")
        if self.required_accessories and not self.evidence_by_field.required_accessories:
            missing.append("required_accessories")
        if self.caveats and not self.evidence_by_field.caveats:
            missing.append("caveats")
        if missing:
            raise ValueError(f"필드별 공식 근거가 없습니다: {sorted(missing)}")
        return self


class ProductCatalog(StrictContract):
    """버전이 지정된 공식 출처와 추천 대상 제품 전체를 담는다."""

    schema_version: str = Field(pattern=r"^1\.1\.0$")
    catalog_version: str = Field(min_length=1, max_length=100)
    generated_at: datetime
    sources: list[SourceRecord] = Field(min_length=1)
    products: list[ProductRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def references_are_resolvable(self) -> "ProductCatalog":
        """제품과 출처 ID의 중복 및 존재하지 않는 문서 참조를 검사한다."""

        document_ids = [source.document_id for source in self.sources]
        product_ids = [product.product_id for product in self.products]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("sources의 document_id가 중복됩니다.")
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("products의 product_id가 중복됩니다.")
        known = set(document_ids)
        for product in self.products:
            missing = set(product.document_ids) - known
            if missing:
                raise ValueError(
                    f"{product.product_id}가 알 수 없는 document_id를 참조합니다: "
                    f"{sorted(missing)}"
                )
        return self

    @classmethod
    def from_received_file(cls, path: str | Path) -> "ProductCatalog":
        """전달받은 catalog.json을 수정하지 않고 읽어 전체 계약을 검증한다."""

        resolved = Path(path)
        if not resolved.is_file():
            raise FileNotFoundError(
                f"받게 되는 제품 카탈로그가 없습니다: {resolved}. "
                "docs/data-contracts/product-catalog.md의 전달 계약을 확인하세요."
            )
        return cls.model_validate_json(resolved.read_text(encoding="utf-8"))


class RecommendationStatus(str, Enum):
    """추천 성공·추가 질문·후보 없음·범위 밖 상태를 구분한다."""

    RECOMMENDED = "recommended"
    NEEDS_CLARIFICATION = "needs_clarification"
    NO_MATCH = "no_match"
    OUT_OF_SCOPE = "out_of_scope"


class RecommendationCandidate(StrictContract):
    """화면에 전달할 제품 후보와 점수·근거·주의사항을 담는다."""

    product_id: str
    name: str
    score: int
    matched_conditions: list[str]
    tradeoffs: list[str]
    required_accessories: list[str]
    evidence_document_ids: list[str]
    product_url: HttpUrl
    image_url: HttpUrl | None
    display: ProductDisplayMetadata


class RecommendationDecision(StrictContract):
    """조건 분석 후 만들어진 최대 3개 후보와 추천 상태를 담는다."""

    status: RecommendationStatus
    conditions: ConditionPayload
    candidates: list[RecommendationCandidate] = Field(max_length=3)
    clarification_questions: list[str] = Field(max_length=3)
    catalog_version: str
