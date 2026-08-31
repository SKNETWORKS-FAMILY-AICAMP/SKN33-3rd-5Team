"""Failure-boundary tests that remain valid when real RAG and LLM are wired."""

from __future__ import annotations

import unittest

from src.services.chat_service import ChatService, MockRetriever


class FailingRetriever:
    """Simulate an unavailable RAG service or broken search index."""

    def search(self, question: str):
        raise ConnectionError("internal RAG endpoint details")


class FailingModel:
    """Simulate an unavailable model API without making an external request."""

    def generate(self, messages, evidence):
        raise RuntimeError("internal model endpoint details")


class MustNotRunModel:
    """Fail immediately if retrieval failure incorrectly reaches generation."""

    def generate(self, messages, evidence):
        raise AssertionError("검색 실패 후 모델을 호출하면 안 됩니다.")


class ChatServiceEdgeCaseTests(unittest.TestCase):
    def test_shared_prompt_abstention_is_supported_by_mock_chat_chain(self):
        from src.lang import INSUFFICIENT_EVIDENCE_MARKER

        class AbstainingModel:
            def generate(self, messages, evidence):
                return INSUFFICIENT_EVIDENCE_MARKER

        response = ChatService(retriever=MockRetriever(), model=AbstainingModel()).answer(
            "Raspberry Pi 5에서 SSH를 설정하려면?"
        )
        self.assertEqual(response["status"], "insufficient_evidence")
        self.assertEqual(response["sources"], [])

    def test_retrieval_error_returns_safe_response_without_calling_model(self) -> None:
        service = ChatService(
            retriever=FailingRetriever(),
            model=MustNotRunModel(),
        )

        response = service.answer(
            "Raspberry Pi 5에서 SSH를 설정하는 방법을 알려주세요."
        )

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["sources"], [])
        self.assertIn("검색 중 오류", response["intro"])
        self.assertNotIn("endpoint", response["intro"])

    def test_model_error_returns_safe_response_without_internal_details(self) -> None:
        service = ChatService(
            retriever=MockRetriever(),
            model=FailingModel(),
        )

        response = service.answer(
            "Raspberry Pi 5에서 SSH를 설정하는 방법을 알려주세요."
        )

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["sources"], [])
        self.assertIn("답변 생성 중 오류", response["intro"])
        self.assertNotIn("endpoint", response["intro"])


if __name__ == "__main__":
    unittest.main()
