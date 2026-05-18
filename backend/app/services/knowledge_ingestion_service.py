"""知识接入服务。

处理文档上传、解析、切分、索引写入的完整流程，支持失败回滚与分步重试。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.models.knowledge import DocumentMetadata, DocumentStatus, VisibilityScope

import tiktoken


def _get_tokenizer() -> tiktoken.Encoding | None:
    """统一使用 tiktoken 的 cl100k_base 作为 token 计数器。

    若首次下载失败（如测试环境无网），返回 None，由 count_tokens fallback。
    """
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


_tokenizer_instance: tiktoken.Encoding | None = None


def count_tokens(text: str) -> int:
    """计算文本的 token 数。

    首版统一 tiktoken；下载不可用时按中文字符 ~1.5 token/字估算，
    保证切分流程不因 tokenizer 初始化失败而中断。
    """
    global _tokenizer_instance
    if _tokenizer_instance is None:
        _tokenizer_instance = _get_tokenizer()
    if _tokenizer_instance is not None:
        return len(_tokenizer_instance.encode(text))
    # fallback：英文字符 0.3 token/字，中文字符 1.5 token/字
    en_count = sum(1 for c in text if c.isascii())
    cn_count = len(text) - en_count
    return int(en_count * 0.3 + cn_count * 1.5)


def compute_checksum(content: bytes) -> str:
    """计算文件内容 checksum，用于去重与变更检测。"""
    return hashlib.sha256(content).hexdigest()


# 默认 chunk 参数（设计文档硬性规定：512 tokens + 128 overlap）
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 128

# 允许特化策略的文档类型范围（设计文档硬性规定）
OVERRIDE_DOC_TYPES = {"合同", "协议", "表格", "流程表单", "审批模板", "通知", "公告"}


@dataclass
class ChunkingStrategy:
    """切分策略。"""

    chunk_size: int
    chunk_overlap: int


class ChunkingStrategyResolver:
    """根据文档类型解析切分策略。

    默认 512/128；仅在文档类型明确属于 OVERRIDE_DOC_TYPES 时才允许覆盖为 1024/256。
    """

    def resolve(self, doc_type: str, title: str = "") -> ChunkingStrategy:
        """返回对应文档类型的切分策略。"""
        normalized = (doc_type + title).lower()
        if any(keyword in normalized for keyword in OVERRIDE_DOC_TYPES):
            # 长条款/表格类文档允许更大上下文
            return ChunkingStrategy(chunk_size=1024, chunk_overlap=256)
        return ChunkingStrategy(chunk_size=DEFAULT_CHUNK_SIZE, chunk_overlap=DEFAULT_CHUNK_OVERLAP)


class DocumentParser:
    """文档解析器，提取文本与标题层级。"""

    def __init__(self) -> None:
        self._resolver = ChunkingStrategyResolver()

    def parse(self, file_path: Path, doc_type: str = "") -> tuple[list[Any], list[str | None]]:
        """解析文档，返回 (documents, section_paths)。

        section_paths 与 documents 一一对应，表示每页/每段的标题路径。
        如果提取不到标题，对应位置为 None。
        """
        from langchain_community.document_loaders import UnstructuredFileLoader
        from langchain_core.documents import Document

        loader = UnstructuredFileLoader(str(file_path))
        raw_documents = loader.load()
        section_paths: list[str | None] = []
        for doc in raw_documents:
            # 简化处理：直接取 page_content 的第一行非空文本作为潜在标题
            first_line = doc.page_content.strip().split("\n")[0].strip() if doc.page_content else ""
            if first_line and len(first_line) < 80:
                section_paths.append(first_line)
            else:
                section_paths.append(None)
        return raw_documents, section_paths

    def split(
        self,
        raw_documents: list[Any],
        section_paths: list[str | None],
        *,
        doc_id: str,
        file_path: Path,
        department: str,
        doc_type: str,
        upload_time: str,
        chunking_strategy: ChunkingStrategy | None = None,
    ) -> list[Any]:
        """按策略切分文档并写入 chunk 级 metadata。

        系统论说明：
        - 输入是 parse 产出的原始文档与标题路径；
        - 输出是带完整 metadata 的 chunk 列表，可直接送入向量索引；
        - section_path 采用"最近匹配"策略：遍历原始标题，取第一个出现在 chunk 中的标题；
        - 如果没有任何标题命中，section_path 为空字符串，由引用层回退到 source_file + chunk_index。
        """
        from langchain_core.documents import Document
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        strategy = chunking_strategy or self._resolver.resolve(doc_type)
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=strategy.chunk_size,
            chunk_overlap=strategy.chunk_overlap,
            length_function=count_tokens,
        )
        all_text = "\n\n".join(doc.page_content for doc in raw_documents)
        split_texts = splitter.split_text(all_text)

        documents: list[Any] = []
        for index, chunk_text in enumerate(split_texts, start=1):
            # 尽量回退 section_path：取原始文档中最近的标题
            section_path = ""
            for sp in section_paths:
                if sp and sp in chunk_text:
                    section_path = sp
                    break
            token_count = count_tokens(chunk_text)
            documents.append(
                Document(
                    page_content=chunk_text,
                    metadata={
                        "doc_id": doc_id,
                        "chunk_id": f"{doc_id}-chunk-{index}",
                        "chunk_index": index,
                        "source_file": file_path.name,
                        "section_path": section_path,
                        "page_num": index,
                        "department": department,
                        "upload_time": upload_time,
                        "doc_type": doc_type,
                        "token_count": token_count,
                    },
                )
            )
        return documents


@dataclass
class IngestionResult:
    """接入结果。"""

    doc_id: str
    status: str  # active / parse_failed / index_failed / sync_pending
    chunk_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class KnowledgeIngestionService:
    """知识接入服务：上传 -> 解析 -> 切分 -> 索引。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._metadata_path = self._settings.knowledge_metadata_path
        self._metadata_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._metadata_path.exists():
            self._metadata_path.write_text("[]", encoding="utf-8")

    def ingest(
        self,
        filename: str,
        content: bytes,
        department: str,
        *,
        title: str = "",
        visibility_scope: VisibilityScope = VisibilityScope.DEPARTMENT,
        owner_user_id: str = "",
    ) -> IngestionResult:
        """执行完整接入流程（骨架）。"""
        raise NotImplementedError

    def retry_parse(self, doc_id: str) -> IngestionResult | None:
        """对 parse_failed 的文档重试解析。"""
        raise NotImplementedError

    def retry_index(self, doc_id: str) -> IngestionResult | None:
        """对 index_failed 的文档重试索引。"""
        raise NotImplementedError
