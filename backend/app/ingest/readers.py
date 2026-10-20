"""Байты файла -> текст. TXT и MD сами, DOCX сами или через Tika, PDF через Tika."""

import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx

from ..config import settings

MEDIA_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
}

# Экранирование Markdown: «2011\.» в выгрузке Google Docs означает «2011.»
_MD_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!<>|~])")

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ReadError(ValueError):
    pass


def media_type(file_name: str) -> str:
    return MEDIA_TYPES.get(Path(file_name).suffix.lower(), "application/octet-stream")


def decode_text(data: bytes) -> str:
    """UTF-8 (с BOM или без), иначе cp1251. Переводы строк приводятся к LF."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1251")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = ET.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError) as e:
        raise ReadError(f"повреждённый DOCX: {e}") from e
    paragraphs = []
    for p in root.iter(_W + "p"):
        parts = []
        for node in p.iter():
            if node.tag == _W + "t":
                parts.append(node.text or "")
            elif node.tag == _W + "tab":
                parts.append("\t")
            elif node.tag == _W + "br":
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def _tika_text(data: bytes) -> str:
    resp = httpx.put(
        f"{settings.tika_url.rstrip('/')}/tika",
        content=data,
        headers={"Accept": "text/plain; charset=UTF-8"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.text.replace("\r\n", "\n")


def read_document_text(file_name: str, data: bytes) -> str:
    ext = Path(file_name).suffix.lower()
    if ext in (".txt", ""):
        return decode_text(data)
    if ext == ".md":
        return _MD_ESCAPE.sub(r"\1", decode_text(data))
    if settings.tika_url and ext in (".docx", ".pdf", ".doc", ".rtf"):
        return _tika_text(data)
    if ext == ".docx":
        return _docx_text(data)
    raise ReadError(f"формат {ext or '(без расширения)'} требует Apache Tika (задайте TIKA_URL)")
