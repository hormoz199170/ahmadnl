from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ahmadnl.config import Settings
from ahmadnl.models import AIResult, AIResultKind, DocumentChunk


class AIError(RuntimeError):
    pass


class ReadingTask(str, Enum):
    SUMMARY = "summary"
    KEY_POINTS = "key_points"
    STUDY_QUESTIONS = "study_questions"
    ANSWER_GUIDANCE = "answer_guidance"


class AIProvider(Protocol):
    async def generate(self, prompt: str, request_id: str) -> str: ...


@dataclass
class GeminiProvider:
    api_key: str
    model: str
    timeout_seconds: int
    max_retries: int
    max_output_tokens: int

    async def generate(self, prompt: str, request_id: str) -> str:
        if not self.api_key:
            raise AIError("AI is not configured yet.")
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model)
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        model.generate_content,
                        prompt,
                        generation_config={"max_output_tokens": self.max_output_tokens, "temperature": 0.2},
                    ),
                    timeout=self.timeout_seconds,
                )
                return getattr(response, "text", "").strip()
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
        raise AIError("AI request failed. Please try again later.") from last_error


class ReadingAssistant:
    def __init__(self, provider: AIProvider, settings: Settings):
        self.provider = provider
        self.settings = settings
        self._semaphore = asyncio.Semaphore(settings.ai_concurrency)

    @staticmethod
    def request_id(document_id: str, task: ReadingTask, prompt_version: str = "v1") -> str:
        raw = f"{document_id}:{task.value}:{prompt_version}".encode()
        return hashlib.sha256(raw).hexdigest()[:40]

    async def run(self, session: AsyncSession, document_id: str, task: ReadingTask) -> AIResult:
        kind = AIResultKind(task.value)
        cached = await session.scalar(select(AIResult).where(AIResult.document_id == document_id, AIResult.kind == kind, AIResult.status == "completed"))
        if cached:
            return cached
        chunks = (await session.execute(select(DocumentChunk).where(DocumentChunk.document_id == document_id).order_by(DocumentChunk.page_number))).scalars().all()
        document_text = "\n\n".join(f"Page {c.page_number}: {c.text}" for c in chunks)[: self.settings.ai_max_input_chars]
        prompt = build_prompt(task, document_text)
        rid = self.request_id(document_id, task)
        result = await session.scalar(select(AIResult).where(AIResult.request_id == rid))
        if result:
            result.status = "running"
            result.error_message = None
            result.input_chars = len(prompt)
        else:
            result = AIResult(document_id=document_id, kind=kind, request_id=rid, status="running", input_chars=len(prompt))
            session.add(result)
        await session.flush()
        try:
            async with self._semaphore:
                content = await self.provider.generate(prompt, rid)
            result.content = content
            result.output_chars = len(content)
            result.status = "completed"
        except Exception as exc:
            result.status = "failed"
            result.error_message = "AI request failed."
            raise AIError("AI request failed. Please try again later.") from exc
        return result


def build_prompt(task: ReadingTask, document_text: str) -> str:
    instructions = {
        ReadingTask.SUMMARY: "Give a concise reading-oriented summary with context, main argument, and what to focus on next.",
        ReadingTask.KEY_POINTS: "List the key points with short explanations and page references when visible.",
        ReadingTask.STUDY_QUESTIONS: "Create study questions that test comprehension, from easy to challenging.",
        ReadingTask.ANSWER_GUIDANCE: "Provide answer guidance: how to approach questions, common traps, and where to reread.",
    }[task]
    return f"You are AhmadNL, a guided PDF reading assistant. Use clear English. {instructions}\n\nDocument excerpt:\n{document_text}"
