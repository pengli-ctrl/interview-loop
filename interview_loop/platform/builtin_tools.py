from interview_loop.core.question_engine import questions_too_similar
from interview_loop.export.markdown import save_markdown_record
from interview_loop.platform.tool_registry import ToolRegistry, ToolSpec
from interview_loop.rag.text import decode_resume_text


def _transcribe(audio_bytes: bytes) -> str:
    from interview_loop.services.asr import audio2text

    return audio2text(audio_bytes)


def _synthesize(text: str) -> bytes:
    from interview_loop.services.tts import text2audio

    return text2audio(text)


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolSpec("resume.decode", "Decode resume text bytes.", decode_resume_text, required_permission="resume:read"))
    registry.register(ToolSpec("question.similarity", "Compare two interview questions.", questions_too_similar))
    registry.register(ToolSpec("asr.transcribe", "Transcribe interview audio.", _transcribe, timeout_seconds=60, required_permission="audio:read"))
    registry.register(ToolSpec("tts.synthesize", "Synthesize interviewer speech.", _synthesize, timeout_seconds=60, required_permission="audio:write"))
    registry.register(ToolSpec("record.export", "Export an interview record as Markdown.", save_markdown_record, required_permission="record:write"))
    return registry
