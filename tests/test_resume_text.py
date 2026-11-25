"""测试模块，覆盖简历文本相关行为和回归场景。"""
import pytest

from interview_loop.rag.text import decode_resume_text


def test_decode_utf8():
    """验证解码 UTF-8 简历。"""
    assert decode_resume_text("张三的简历".encode("utf-8")) == "张三的简历"


def test_decode_gb18030():
    """验证解码 GB18030 简历。"""
    assert decode_resume_text("张三的简历".encode("gb18030")) == "张三的简历"


def test_invalid_data_raises():
    """验证无效数据抛出。"""
    with pytest.raises(ValueError):
        decode_resume_text(b"\xff\xfe\x00\x00")
