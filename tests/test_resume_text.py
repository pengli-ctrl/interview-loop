import pytest

from interview_loop.rag.text import decode_resume_text


def test_decode_utf8():
    assert decode_resume_text("张三的简历".encode("utf-8")) == "张三的简历"


def test_decode_gb18030():
    assert decode_resume_text("张三的简历".encode("gb18030")) == "张三的简历"


def test_invalid_data_raises():
    with pytest.raises(ValueError):
        decode_resume_text(b"\xff\xfe\x00\x00")
