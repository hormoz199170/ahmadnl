from ahmadnl.services.ai import ReadingAssistant, ReadingTask, build_prompt


def test_request_id_is_deterministic():
    first = ReadingAssistant.request_id("doc", ReadingTask.SUMMARY)
    second = ReadingAssistant.request_id("doc", ReadingTask.SUMMARY)
    assert first == second


def test_prompt_is_reading_assistant_oriented():
    prompt = build_prompt(ReadingTask.STUDY_QUESTIONS, "Page 1: hello")
    assert "guided PDF reading assistant" in prompt
    assert "study questions" in prompt.lower()
