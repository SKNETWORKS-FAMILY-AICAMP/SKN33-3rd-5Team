"""UI와 분리된 제품 추천과 문서 기반 QA 서비스를 공개한다."""

from .chat_service import ChatService, build_default_mock_chat_service

from .recommendation_agent import RecommendationAgent, RecommendationAgentResult
from .recommendation_response import build_recommendation_chat_response

__all__ = [
    "ChatService",
    "RecommendationAgent",
    "RecommendationAgentResult",
    "build_default_mock_chat_service",
    "build_recommendation_chat_response",
]
