"""Record the actual generator input/output without changing service responses."""

from __future__ import annotations

from src.rag_to_llm import EvidenceTemplateGenerator

from .answer_eval import AnswerEvalRecord, EvaluationEvidence


class RecordingAnswerGenerator:
    """Sequential evaluation helper. Reset before every request; do not share across threads."""

    def __init__(self, inner):
        self.inner = inner
        self.provider = getattr(inner, "provider", "unknown")
        self.model_id = getattr(inner, "model_id", "unknown")
        self.reset()

    def reset(self):
        self.invoked = False
        self.evidence = []
        self.generation = None

    def generate(self, messages, evidence):
        self.invoked = True
        self.evidence = [EvaluationEvidence(
            citation_id=item.citation_id, content=item.content, title=item.title, section=item.section
        ) for item in evidence]
        self.generation = self.inner.generate(messages, evidence)
        return self.generation

    def record(self, *, case, response, run_id, configuration=None, model_revision=None):
        return AnswerEvalRecord(
            run_id=run_id, case=case, response=response,
            provider=self.generation.provider if self.generation else self.provider,
            model_id=self.generation.model_id if self.generation else self.model_id,
            model_revision=model_revision,
            configuration=configuration or {}, generator_invoked=self.invoked,
            evidence=self.evidence, raw_answer=self.generation.text if self.generation else None,
        )


class RecordingTemplateGenerator(RecordingAnswerGenerator, EvidenceTemplateGenerator):
    """Preserve the recommendation service's existing isinstance(template) behavior."""


def recording_generator(inner):
    cls = RecordingTemplateGenerator if isinstance(inner, EvidenceTemplateGenerator) else RecordingAnswerGenerator
    return cls(inner)
