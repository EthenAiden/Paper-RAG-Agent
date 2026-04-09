"""
Advanced RAG 文档处理流水线
流程：
1. 从 MinIO 下载原始文件到临时目录
2. 文档加载（支持 PDF / TXT / Markdown）
3. 父-子分块（Parent-Child Chunking）
   - 父块：较大，用于提供给 LLM（提供更多上下文）
   - 子块：较小，用于向量检索（精准匹配）
4. 生成嵌入，写入 Milvus（只对子块生成嵌入）
5. 分块元数据写入 MySQL document_chunk 表
6. 更新 document 状态与 chunk_count

支持断点续传：重试时跳过已处理的分块
"""
import uuid
import asyncio
import tempfile
import os
import logging
from pathlib import Path

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyMuPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
)
from langchain_core.documents import Document as LCDocument
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.llm import get_embeddings
from app.db.milvus_client import insert_chunks, get_collection
from app.db.minio_client import download_file
from app.db.mysql import DocumentChunk
from app.db.redis_client import embedding_cache_get, embedding_cache_set

logger = logging.getLogger(__name__)

# 父块：较大，保留上下文，用于提供给 LLM
_PARENT_CHUNK_SIZE = 1500
_PARENT_OVERLAP = 200

# 子块：较小，用于向量检索（精准匹配）
_CHILD_CHUNK_SIZE = 400
_CHILD_OVERLAP = 50

_tokenizer = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(_tokenizer.encode(text))


def _load_file(file_path: str) -> list[LCDocument]:
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        loader = PyMuPDFLoader(file_path)
    elif ext in {".md", ".markdown"}:
        loader = UnstructuredMarkdownLoader(file_path)
    else:
        loader = TextLoader(file_path, encoding="utf-8")
    return loader.load()


def _split_parent_child(docs: list[LCDocument]) -> list[tuple[str, LCDocument, list[LCDocument]]]:
    """
    父子分块：返回 [(parent_id, parent_doc, [child_docs]), ...]
    """
    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=_PARENT_CHUNK_SIZE,
        chunk_overlap=_PARENT_OVERLAP,
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=_CHILD_CHUNK_SIZE,
        chunk_overlap=_CHILD_OVERLAP,
    )
    pairs = []
    for doc in docs:
        parents = parent_splitter.split_documents([doc])
        for parent in parents:
            parent_id = str(uuid.uuid4())
            children = child_splitter.split_documents([parent])
            pairs.append((parent_id, parent, children))
    return pairs


def _get_processed_chunks(doc_id: int) -> set[str]:
    """获取已处理的 chunk ID 集合（从 Milvus 查询）"""
    try:
        col = get_collection()
        results = col.query(
            expr=f"doc_id == {doc_id}",
            output_fields=["id"]
        )
        return {r["id"] for r in results}
    except Exception as e:
        logger.warning(f"[文档处理] 查询已处理分块失败: {e}")
        return set()


def process_document_sync(minio_object_path: str, doc_id: int, resume: bool = False) -> list[dict]:
    """
    同步处理文档：下载 → 解析 → 父子分块 → 向量化 → 写入 Milvus。
    
    父子分块策略：
    - 父块：1500字符，存储完整上下文，不生成嵌入
    - 子块：400字符，用于检索，生成嵌入
    - 检索时：匹配子块，返回对应父块内容
    
    Args:
        minio_object_path: MinIO 对象路径
        doc_id: 文档 ID
        resume: 是否断点续传，跳过已处理的分块
    
    返回 chunk 记录列表（含 content / chunk_index / token_count），
    供调用方写入 MySQL。
    在 asyncio.to_thread 中调用。
    """
    from app.core.config import get_settings
    settings = get_settings()
    
    logger.info(f"[文档处理] 开始同步处理: doc_id={doc_id}, path={minio_object_path}, resume={resume}")
    
    # 断点续传：获取已处理的分块 ID
    processed_ids = set()
    if resume:
        processed_ids = _get_processed_chunks(doc_id)
        logger.info(f"[文档处理] 已处理分块数: {len(processed_ids)}")
    
    # 下载原始文件到临时目录
    raw_data = download_file(minio_object_path)
    ext = Path(minio_object_path).suffix.lower() or ".txt"
    logger.info(f"[文档处理] 文件已下载: doc_id={doc_id}, size={len(raw_data)}")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(raw_data)
        tmp_path = tmp.name

    try:
        docs = _load_file(tmp_path)
        logger.info(f"[文档处理] 文档已解析: doc_id={doc_id}, pages/sections={len(docs)}")
    finally:
        os.unlink(tmp_path)

    pairs = _split_parent_child(docs)
    logger.info(f"[文档处理] 分块完成: doc_id={doc_id}, parent_chunks={len(pairs)}")
    
    embeddings_model = get_embeddings()

    # 收集需要处理的子块
    children_to_process = []  # [(child_id, parent_id, text), ...]
    parent_contents = {}  # parent_id -> parent_content
    skipped_count = 0

    for parent_id, parent_doc, children in pairs:
        parent_text = parent_doc.page_content.strip()
        if not parent_text:
            continue
        
        parent_contents[parent_id] = parent_text
        
        for child in children:
            child_text = child.page_content.strip()
            if not child_text:
                continue
            
            child_id = str(uuid.uuid4())
            
            # 断点续传：跳过已处理的分块（基于父ID判断）
            if parent_id in processed_ids:
                skipped_count += 1
                continue
            
            children_to_process.append((child_id, parent_id, child_text))

    logger.info(f"[文档处理] 需处理子块数: {len(children_to_process)}, 跳过: {skipped_count}")

    # 批量获取缓存的 embedding
    cache_hit_count = 0
    texts_need_embedding = []  # [(child_id, parent_id, text), ...]
    cached_embeddings = {}  # child_id -> embedding

    for child_id, parent_id, text in children_to_process:
        embedding = asyncio.run(embedding_cache_get(text))
        if embedding is not None:
            cached_embeddings[child_id] = embedding
            cache_hit_count += 1
        else:
            texts_need_embedding.append((child_id, parent_id, text))

    logger.info(f"[文档处理] 缓存命中: {cache_hit_count}, 需计算: {len(texts_need_embedding)}")

    # 批量计算 embedding
    if texts_need_embedding:
        batch_size = 20
        for i in range(0, len(texts_need_embedding), batch_size):
            batch = texts_need_embedding[i:i + batch_size]
            batch_texts = [t for _, _, t in batch]
            batch_ids = [cid for cid, _, _ in batch]
            
            try:
                batch_embeddings = embeddings_model.embed_documents(batch_texts)
                
                for child_id, text, emb in zip(batch_ids, batch_texts, batch_embeddings):
                    cached_embeddings[child_id] = emb
                    asyncio.run(embedding_cache_set(text, emb))
                    
            except Exception as e:
                logger.error(f"[文档处理] 批量嵌入失败: batch_start={i}, error={str(e)}")
                raise
            
            logger.info(f"[文档处理] 批量嵌入进度: {min(i + batch_size, len(texts_need_embedding))}/{len(texts_need_embedding)}")

    # 构建 Milvus 记录（父块 + 子块）
    milvus_records = []
    chunk_meta = []
    chunk_index = 0

    for parent_id, parent_doc, children in pairs:
        parent_text = parent_doc.page_content.strip()
        if not parent_text:
            continue
        
        # 存储父块（不生成嵌入，用零向量占位）
        parent_embedding = [0.0] * settings.embedding_dimension
        milvus_records.append({
            "id": parent_id,
            "doc_id": doc_id,
            "chunk_index": -1,
            "parent_id": "",
            "is_child": False,
            "content": parent_text[:8192],
            "embedding": parent_embedding,
        })
        
        # 存储子块（有嵌入）
        for child in children:
            child_text = child.page_content.strip()
            if not child_text:
                continue
            
            child_id = str(uuid.uuid4())
            embedding = cached_embeddings.get(child_id)
            
            if embedding:
                milvus_records.append({
                    "id": child_id,
                    "doc_id": doc_id,
                    "chunk_index": chunk_index,
                    "parent_id": parent_id,
                    "is_child": True,
                    "content": child_text[:4096],
                    "embedding": embedding,
                })
                chunk_meta.append({
                    "chunk_index": chunk_index,
                    "content": child_text,
                    "token_count": _count_tokens(child_text),
                })
                chunk_index += 1
            
            if len(milvus_records) >= 50:
                insert_chunks(milvus_records)
                logger.info(f"[文档处理] 批量写入Milvus: doc_id={doc_id}, batch_size={len(milvus_records)}")
                milvus_records = []

    if milvus_records:
        insert_chunks(milvus_records)
        logger.info(f"[文档处理] 向量已写入Milvus: doc_id={doc_id}, chunks={chunk_index}")

    logger.info(f"[文档处理] 同步处理完成: doc_id={doc_id}, total_chunks={chunk_index}, cache_hit={cache_hit_count}")
    return chunk_meta


async def process_document(
    minio_object_path: str,
    doc_id: int,
    db: AsyncSession,
    resume: bool = False,
) -> int:
    """
    异步包装：处理文档并将分块元数据写入 MySQL。
    
    Args:
        minio_object_path: MinIO 对象路径
        doc_id: 文档 ID
        db: 数据库会话
        resume: 是否断点续传
    
    返回 chunk 数量。
    """
    logger.info(f"[文档处理] 开始异步处理: doc_id={doc_id}, resume={resume}")
    chunk_meta = await asyncio.to_thread(process_document_sync, minio_object_path, doc_id, resume)

    for meta in chunk_meta:
        db.add(DocumentChunk(
            doc_id=doc_id,
            content=meta["content"],
            chunk_index=meta["chunk_index"],
            token_count=meta["token_count"],
        ))
    await db.commit()
    logger.info(f"[文档处理] 分块元数据已写入MySQL: doc_id={doc_id}, chunks={len(chunk_meta)}")

    return len(chunk_meta)
