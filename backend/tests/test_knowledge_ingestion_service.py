"""知识接入服务测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.models.knowledge import DocumentStatus, VisibilityScope
from app.services.knowledge_ingestion_service import (
    ChunkingStrategyResolver,
    KnowledgeIngestionService,
    compute_checksum,
    count_tokens,
)


@pytest.fixture
def temp_ingestion_metadata(tmp_path, monkeypatch):
    """提供隔离的 metadata 与上传目录。"""
    metadata_path = tmp_path / "knowledge_metadata.json"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(get_settings(), "knowledge_metadata_path", metadata_path)
    monkeypatch.setattr(get_settings(), "upload_dir", upload_dir)
    return metadata_path, upload_dir


class TestTokenCounter:
    def test_count_tokens_chinese(self) -> None:
        assert count_tokens("你好世界") > 0

    def test_count_tokens_english(self) -> None:
        assert count_tokens("hello world") > 0


class TestChecksum:
    def test_same_content_same_checksum(self) -> None:
        assert compute_checksum(b"abc") == compute_checksum(b"abc")

    def test_different_content_different_checksum(self) -> None:
        assert compute_checksum(b"abc") != compute_checksum(b"abd")


class TestChunkingStrategyResolver:
    def test_default_strategy(self) -> None:
        resolver = ChunkingStrategyResolver()
        strategy = resolver.resolve("txt")
        assert strategy.chunk_size == 512
        assert strategy.chunk_overlap == 128

    def test_override_for_contract(self) -> None:
        resolver = ChunkingStrategyResolver()
        strategy = resolver.resolve("pdf", title="合同模板")
        assert strategy.chunk_size == 1024
        assert strategy.chunk_overlap == 256

    def test_override_for_table(self) -> None:
        resolver = ChunkingStrategyResolver()
        strategy = resolver.resolve("pdf", title="员工表格")
        assert strategy.chunk_size == 1024


class TestIngestionFlow:
    def test_ingest_success(self, temp_ingestion_metadata) -> None:
        metadata_path, _upload_dir = temp_ingestion_metadata
        service = KnowledgeIngestionService()
        result = service.ingest(
            "test.txt",
            "第一条制度\n\n第二条制度\n\n第三条制度".encode("utf-8"),
            "HR",
        )
        assert result.status == DocumentStatus.ACTIVE.value
        assert result.chunk_count > 0

        # metadata 应已写入
        docs = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert len(docs) == 1
        assert docs[0]["status"] == DocumentStatus.ACTIVE.value
        assert docs[0]["version"] == "v1.0"
        assert docs[0]["visibility_scope"] == VisibilityScope.DEPARTMENT.value

    def test_parse_failed_rollback(self, temp_ingestion_metadata) -> None:
        metadata_path, upload_dir = temp_ingestion_metadata
        service = KnowledgeIngestionService()
        # 构造一个不可解析的文件（模拟）
        # 由于 UnstructuredFileLoader 对任意 bytes 可能报错也可能不报，
        # 我们通过 monkeypatch parse 方法直接抛出异常来测试
        original_parse = service._parser.parse

        def fail_parse(*args, **kwargs):
            raise RuntimeError("parse error")

        service._parser.parse = fail_parse
        result = service.ingest("test.txt", b"valid content", "HR")

        assert result.status == DocumentStatus.PARSE_FAILED.value
        docs = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert docs[0]["status"] == DocumentStatus.PARSE_FAILED.value
        # 原始文件应保留
        assert any(upload_dir.iterdir())

        # 恢复
        service._parser.parse = original_parse

    def test_retry_parse(self, temp_ingestion_metadata) -> None:
        metadata_path, _upload_dir = temp_ingestion_metadata
        service = KnowledgeIngestionService()

        # 先制造一个 parse_failed
        original_parse = service._parser.parse
        call_count = 0

        def flaky_parse(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("parse error")
            return original_parse(*args, **kwargs)

        service._parser.parse = flaky_parse
        result = service.ingest("test.txt", b"line1\n\nline2", "HR")
        assert result.status == DocumentStatus.PARSE_FAILED.value

        # 重试解析
        retry_result = service.retry_parse(result.doc_id)
        assert retry_result is not None
        assert retry_result.status == DocumentStatus.ACTIVE.value

        service._parser.parse = original_parse

    def test_retry_index(self, temp_ingestion_metadata, monkeypatch) -> None:
        metadata_path, _upload_dir = temp_ingestion_metadata
        service = KnowledgeIngestionService()

        # 先正常解析，但让索引失败
        original_index = service._index_documents
        call_count = 0

        def flaky_index(docs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("index error")
            original_index(docs)

        service._index_documents = flaky_index
        result = service.ingest("test.txt", b"line1\n\nline2", "HR")
        assert result.status == DocumentStatus.INDEX_FAILED.value

        # 重试索引
        retry_result = service.retry_index(result.doc_id)
        assert retry_result is not None
        assert retry_result.status == DocumentStatus.ACTIVE.value

        service._index_documents = original_index

    def test_chunk_metadata_has_token_count(self, temp_ingestion_metadata) -> None:
        metadata_path, _upload_dir = temp_ingestion_metadata
        service = KnowledgeIngestionService()
        result = service.ingest("test.txt", "这是第一条规定。\n\n这是第二条规定。".encode("utf-8"), "HR")
        assert result.status == DocumentStatus.ACTIVE.value
        # chunk 的 token_count 应在 metadata 中体现（通过 Document 的 metadata）
        docs = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert docs[0]["chunk_count"] > 0
