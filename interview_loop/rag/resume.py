import io

from interview_loop.config import MAX_RESUME_BYTES


def _decode_resume_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文本编码，请将简历另存为 UTF-8 后重试")


def extract_resume_text(upload) -> str:
    data = upload.getvalue()
    if len(data) > MAX_RESUME_BYTES:
        raise ValueError("简历文件超过 10 MB，请压缩或删除图片后重试")

    filename = upload.name.lower()
    if filename.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            try:
                from PyPDF2 import PdfReader
            except ImportError as exc:
                raise RuntimeError("缺少 PDF 解析依赖，请安装 pypdf") from exc

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception as exc:
                    raise ValueError("PDF 已加密，无法读取") from exc
            pages = [(page.extract_text() or "").strip() for page in reader.pages]
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"PDF 解析失败：{exc}") from exc
        return "\n".join(page for page in pages if page)

    return _decode_resume_text(data)
