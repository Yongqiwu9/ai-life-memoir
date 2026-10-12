"""Deterministic synthetic provider. It has no model, credentials or transport."""

import unicodedata

from app.contracts import QuestionRequest, QuestionResult

QUESTION_CATALOG = (
    ("opening", "您想从哪段回忆开始讲起？"),
    ("story", "还有哪件事情，是您现在愿意讲的？"),
    ("feelings", "这段回忆里，您最想保留怎样的感受？"),
    ("detail", "您愿意继续说说自己记得的细节吗？"),
    ("continue", "接下来，您希望聊些什么？"),
)


def normalize_question(text: str) -> str:
    return "".join(
        char.casefold()
        for char in unicodedata.normalize("NFKC", text)
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


class MockAIProvider:
    def generate_question(self, context: QuestionRequest) -> QuestionResult:
        catalog = QUESTION_CATALOG
        if context.context_text and any(
            word in context.context_text for word in ("上学", "学校", "读书")
        ):
            catalog = (("school", "关于您提到的上学，您想继续讲哪件事？"), *catalog)
        asked_keys = {question.question_key for question in context.asked_questions}
        asked_texts = {normalize_question(question.text) for question in context.asked_questions}
        selected = next(
            (
                (key, text)
                for key, text in catalog
                if key not in asked_keys and normalize_question(text) not in asked_texts
            ),
            None,
        )
        binding = {
            "request_id": context.request_id,
            "session_id": context.session_id,
            "agent_version": context.agent_version,
            "generation_epoch": context.generation_epoch,
            "context_message_ids": context.context_message_ids,
        }
        if selected is None:
            return QuestionResult(**binding, outcome="no_question")
        key, text = selected
        follow_up = key == "school"
        return QuestionResult(
            **binding,
            outcome="question",
            question_key=key,
            question=text,
            question_basis="follow_up" if follow_up else "neutral",
            basis_message_ids=context.context_message_ids if follow_up else (),
        )
