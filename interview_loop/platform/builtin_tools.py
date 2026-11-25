from interview_loop.core.question_engine import questions_too_similar
from interview_loop.export.markdown import save_markdown_record
from interview_loop.platform.tool_registry import ToolRegistry, ToolSpec
from interview_loop.rag.text import decode_resume_text

BYTES_SCHEMA = {
    "type": "object",
    "required": ["type", "encoding", "data"],
    "properties": {
        "type": {"const": "bytes"},
        "encoding": {"const": "base64"},
        "data": {"type": "string"},
    },
    "additionalProperties": False,
}

QUESTION_SIMILARITY_INPUT_SCHEMA = {
    "type": "object",
    "required": ["new_question", "previous_question"],
    "properties": {
        "new_question": {"type": "string", "minLength": 1},
        "previous_question": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}

QUESTION_SIMILARITY_OUTPUT_SCHEMA = {"type": "boolean"}


def _transcribe(audio_bytes: bytes) -> str:
    from interview_loop.services.asr import audio2text

    return audio2text(audio_bytes)


def _synthesize(text: str) -> bytes:
    from interview_loop.services.tts import text2audio

    return text2audio(text)


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "resume.decode",
            "Decode resume text bytes.",
            decode_resume_text,
            required_permission="resume:read",
            input_schema={
                "type": "object",
                "required": ["data"],
                "properties": {"data": BYTES_SCHEMA},
                "additionalProperties": False,
            },
            output_schema={"type": "string"},
            idempotent=True,
        )
    )
    registry.register(
        ToolSpec(
            "question.similarity",
            "Compare two interview questions.",
            questions_too_similar,
            input_schema=QUESTION_SIMILARITY_INPUT_SCHEMA,
            output_schema=QUESTION_SIMILARITY_OUTPUT_SCHEMA,
            idempotent=True,
        )
    )
    registry.register(
        ToolSpec(
            "asr.transcribe",
            "Transcribe interview audio.",
            _transcribe,
            timeout_seconds=60,
            required_permission="audio:read",
            input_schema={
                "type": "object",
                "required": ["audio_bytes"],
                "properties": {"audio_bytes": BYTES_SCHEMA},
                "additionalProperties": False,
            },
            output_schema={"type": "string"},
            idempotent=True,
        )
    )
    registry.register(
        ToolSpec(
            "tts.synthesize",
            "Synthesize interviewer speech.",
            _synthesize,
            timeout_seconds=60,
            required_permission="audio:write",
            input_schema={
                "type": "object",
                "required": ["text"],
                "properties": {"text": {"type": "string", "minLength": 1}},
                "additionalProperties": False,
            },
            output_schema=BYTES_SCHEMA,
            idempotent=True,
        )
    )
    registry.register(
        ToolSpec(
            "record.export",
            "Export an interview record as Markdown.",
            save_markdown_record,
            required_permission="record:write",
            input_schema={
                "type": "object",
                "required": ["record_dir", "data"],
                "properties": {
                    "record_dir": {"type": "string"},
                    "data": {"type": "object"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": {"type": "string"},
            },
            idempotent=True,
        )
    )
    return registry
