"""文本处理模块，负责简历文本编码识别和解码。"""
def decode_resume_text(data: bytes) -> str:
    """按多种编码解码简历文本。

    Args:
        data: `data` 输入参数，类型为 bytes。

    Returns:
        函数处理结果，类型为 str。

    Raises:
        ValueError: 当输入、状态或外部依赖不满足要求时抛出 ValueError。

    """
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文本编码，请将简历另存为 UTF-8 后重试")
