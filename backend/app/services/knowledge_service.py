"""知识库服务。"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from langchain_community.document_loaders import UnstructuredFileLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import get_settings
from app.services.metadata_migration_service import migrate_document_metadata, needs_migration
from app.services.seed_data import SEED_DOCUMENTS
from app.vectorstore.milvus_client import get_knowledge_vectorstore


class KnowledgeService:
    """处理文档上传、索引与检索。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._metadata_path = self._settings.knowledge_metadata_path
        self._metadata_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._metadata_path.exists():
            self._metadata_path.write_text("[]", encoding="utf-8")
        self._migrate_metadata_if_needed()
        self._ensure_seed_documents()
        self.rebuild_index()

    def _migrate_metadata_if_needed(self) -> None:
        """启动时自动迁移旧 metadata。"""
        raw_items = json.loads(self._metadata_path.read_text(encoding="utf-8"))
        migrated = False
        new_items: list[dict[str, object]] = []
        for raw in raw_items:
            if needs_migration(raw):
                doc = migrate_document_metadata(raw)
                new_items.append(doc.model_dump(mode="json"))
                migrated = True
            else:
                new_items.append(raw)
        if migrated:
            self._metadata_path.write_text(
                json.dumps(new_items, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    def list_documents(self) -> list[dict[str, object]]:
        """返回文档清单。"""
        return json.loads(self._metadata_path.read_text(encoding="utf-8"))

    def upload_document(self, filename: str, content: bytes, department: str) -> dict[str, object]:
        """保存并索引上传文档。"""
        extension = Path(filename).suffix.lower().replace(".", "") or "txt"
        doc_id = f"doc-{uuid4().hex[:12]}"
        file_path = self._settings.upload_dir / f"{doc_id}-{filename}"
        file_path.write_bytes(content)
        chunk_count = self._register_document(file_path=file_path, doc_id=doc_id, department=department, doc_type=extension)
        self.rebuild_index()
        return {
            "doc_id": doc_id,
            "filename": filename,
            "chunk_count": chunk_count,
            "department": department,
            "indexed": True,
        }

    def delete_document(self, doc_id: str) -> bool:
        """删除文档。"""
        metadata = self.list_documents()
        remaining = [item for item in metadata if item["doc_id"] != doc_id]
        deleted = len(remaining) != len(metadata)
        if not deleted:
            return False
        self._metadata_path.write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")
        for file_path in self._settings.upload_dir.glob(f"{doc_id}-*"):
            file_path.unlink(missing_ok=True)
        self.rebuild_index()
        return True

    def search(self, query: str, *, department: str | None = None, doc_type: str | None = None) -> list[dict[str, object]]:
        """执行检索。"""
        return get_knowledge_vectorstore().search(
            query,
            department=department,
            doc_type=doc_type,
            top_k=self._settings.knowledge_top_k,
        )

    def rebuild_index(self) -> None:
        """重建索引。"""
        documents: list[Document] = []
        for item in self.list_documents():
            storage_path = item.get("storage_path")
            if not storage_path:
                continue
            file_path = Path(storage_path)
            if not file_path.exists():
                continue
            documents.extend(
                self._load_and_split(
                    file_path=file_path,
                    doc_id=str(item["doc_id"]),
                    department=str(item["department"]),
                    doc_type=str(item["doc_type"]),
                    upload_time=str(item["upload_time"]),
                )
            )
        get_knowledge_vectorstore().index_documents(documents)

    def _ensure_seed_documents(self) -> None:
        metadata = self.list_documents()
        if metadata:
            return
        for seed in SEED_DOCUMENTS:
            path = self._settings.knowledge_seed_dir / str(seed["filename"])
            if not path.exists():
                path.write_text(str(seed["content"]), encoding="utf-8")
            self._register_document(
                file_path=path,
                doc_id=f"seed-{uuid4().hex[:10]}",
                department=str(seed["department"]),
                doc_type="txt",
            )

    def _register_document(self, *, file_path: Path, doc_id: str, department: str, doc_type: str) -> int:
        metadata = self.list_documents()
        upload_time = datetime.utcnow().isoformat()
        chunk_count = len(
            self._load_and_split(
                file_path=file_path,
                doc_id=doc_id,
                department=department,
                doc_type=doc_type,
                upload_time=upload_time,
            )
        )
        metadata.append(
            {
                "doc_id": doc_id,
                "filename": file_path.name,
                "department": department,
                "doc_type": doc_type,
                "upload_time": upload_time,
                "chunk_count": chunk_count,
                "storage_path": str(file_path),
            }
        )
        self._metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return chunk_count

    def _load_and_split(
        self,
        *,
        file_path: Path,
        doc_id: str,
        department: str,
        doc_type: str,
        upload_time: str,
    ) -> list[Document]:
        loader = UnstructuredFileLoader(str(file_path))
        raw_documents = loader.load()
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
        split_documents = splitter.split_documents(raw_documents)
        for index, document in enumerate(split_documents, start=1):
            document.metadata.update(
                {
                    "doc_id": doc_id,
                    "source_file": file_path.name,
                    "page_num": index,
                    "department": department,
                    "upload_time": upload_time,
                    "doc_type": doc_type,
                }
            )
        return split_documents


@lru_cache
def get_knowledge_service() -> KnowledgeService:
    return KnowledgeService()


def get_knowledge_module_snapshot() -> dict[str, str]:
    return {
        "name": "企业知识库检索",
        "status": "已启用",
        "highlight": "支持文档上传、分块、检索与引用溯源",
        "capability": "支持 PDF、DOCX、TXT 解析与部门维度过滤",
    }
