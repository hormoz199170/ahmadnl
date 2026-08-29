from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ahmadnl.models import AIResult, AIResultKind, Document, DocumentState
from ahmadnl.services.ai import AIError, ReadingAssistant, ReadingTask
from ahmadnl.services.credits import CreditError, balance, consume, refund


TASK_COSTS = {
    ReadingTask.SUMMARY: "summary_credit_cost",
    ReadingTask.KEY_POINTS: "key_points_credit_cost",
    ReadingTask.STUDY_QUESTIONS: "study_questions_credit_cost",
    ReadingTask.ANSWER_GUIDANCE: "answer_guidance_credit_cost",
}


@dataclass(frozen=True)
class ReadingOperationResult:
    document: Document
    ai_result: AIResult
    cached: bool
    credits_left: int


async def run_reading_operation(
    session: AsyncSession,
    *,
    assistant: ReadingAssistant,
    settings,
    user_id: str,
    document_id: str,
    task: ReadingTask,
) -> ReadingOperationResult:
    document = await session.get(Document, document_id)
    if not document or document.user_id != user_id or document.state != DocumentState.READY:
        raise AIError("Please choose a processed PDF first.")

    kind = AIResultKind(task.value)
    cached = await session.scalar(
        select(AIResult).where(AIResult.document_id == document_id, AIResult.kind == kind, AIResult.status == "completed")
    )
    if cached:
        return ReadingOperationResult(document, cached, True, await balance(session, user_id))

    cost = int(getattr(settings, TASK_COSTS[task]))
    if await balance(session, user_id) < cost:
        raise CreditError("Not enough credits.")

    request_id = ReadingAssistant.request_id(document_id, task)
    await consume(session, user_id, cost, f"ai-consume:{request_id}", f"{task.value} for document {document_id}")
    try:
        ai_result = await assistant.run(session, document_id, task)
    except Exception:
        await refund(session, user_id, cost, f"ai-refund:{request_id}", "AI operation failed")
        raise
    return ReadingOperationResult(document, ai_result, False, await balance(session, user_id))
