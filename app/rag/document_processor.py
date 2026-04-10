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
import httpx
import fitz  # PyMuPDF
import os
from langchain_core.documents import Document as LCDocument
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.llm import get_embeddings
from app.db.milvus_client import insert_chunks, get_collection
from app.db.minio_client import download_file
from app.db.mysql import DocumentChunk
from app.db.redis_client import embedding_cache_get_sync, embedding_cache_set_sync

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
        # 先尝试用 PyMuPDF 提取文本层
        loader = PyMuPDFLoader(file_path)
        docs = loader.load()
        
        # 检查是否提取到内容（如果内容很少，可能是扫描件）
        total_text = "".join(d.page_content for d in docs).strip()
        if len(total_text) < 100:  # 内容太少，调用 百度OCR
            logger.info(f"[文档处理] 文本内容少，调用 百度OCR: {file_path}")
            try:
                ocr_text = _ocr_space(file_path)
                docs = [LCDocument(page_content=ocr_text, metadata={"source": file_path})]
                logger.info(f"[文档处理] OCR 完成，字符数: {len(ocr_text)}")
            except Exception as e:
                logger.error(f"[文档处理] OCR 失败: {e}")
        return docs
    elif ext in {".md", ".markdown"}:
        loader = UnstructuredMarkdownLoader(file_path)
    else:
        loader = TextLoader(file_path, encoding="utf-8")
    return loader.load()


def _ocr_space(file_path: str) -> str:
    """调用百度 OCR API（支持大文件分页处理）"""
    import fitz  # PyMuPDF
    import time
    import base64
    
    from app.core.config import get_settings
    settings = get_settings()
    
    # 检查文件大小
    file_size = os.path.getsize(file_path)
    max_size = 1 * 1024 * 1024  # 1MB 限制
    
    if file_size <= max_size:
        # 小文件直接上传
        return _baidu_ocr_single(file_path)
    
    # 大文件：分页提取图片，逐页 OCR
    logger.info(f"[OCR] 文件较大 ({file_size / 1024 / 1024:.2f}MB)，分页处理")
    
    doc = fitz.open(file_path)
    text_parts = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # 将页面渲染为图片
        mat = fitz.Matrix(2, 2)  # 2x 放大提高识别率
        pix = page.get_pixmap(matrix=mat)
        
        # 转为 PNG 字节
        img_bytes = pix.tobytes("png")
        
        # 调用百度 OCR
        try:
            page_text = _baidu_ocr_bytes(img_bytes)
            text_parts.append(page_text)
            logger.info(f"[OCR] 第 {page_num + 1}/{len(doc)} 页完成")
            time.sleep(0.5)  # 避免频率限制
        except Exception as e:
            logger.warning(f"[OCR] 第 {page_num + 1} 页失败: {e}")
    
    doc.close()
    return "\n".join(text_parts)


def _get_baidu_access_token() -> str:
    """获取百度 OCR access_token"""
    from app.core.config import get_settings
    settings = get_settings()
    
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": settings.baidu_ocr_api_key,
        "client_secret": settings.baidu_ocr_secret_key,
    }
    
    response = httpx.post(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()["access_token"]


def _baidu_ocr_single(file_path: str) -> str:
    """单文件百度 OCR"""
    import base64
    
    with open(file_path, "rb") as f:
        img_base64 = base64.b64encode(f.read()).decode()
    
    return _baidu_ocr_base64(img_base64)


def _baidu_ocr_bytes(img_bytes: bytes) -> str:
    """对图片字节进行百度 OCR"""
    import base64
    img_base64 = base64.b64encode(img_bytes).decode()
    return _baidu_ocr_base64(img_base64)


def _baidu_ocr_base64(img_base64: str) -> str:
    """调用百度 OCR API"""
    access_token = _get_baidu_access_token()
    
    url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token={access_token}"
    
    data = {
        "image": img_base64,
        "language_type": "CHN_ENG",  # 中英文混合
    }
    
    response = httpx.post(url, data=data, timeout=60)
    response.raise_for_status()
    result = response.json()
    
    if "error_code" in result:
        raise Exception(f"百度 OCR 失败: {result.get('error_msg', 'Unknown error')}")
    
    # 提取文字
    words_list = result.get("words_result", [])
    return "\n".join(item["words"] for item in words_list)





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
        embedding = embedding_cache_get_sync(text)
        if embedding is not None:
            cached_embeddings[child_id] = embedding
            cache_hit_count += 1
        else:
            texts_need_embedding.append((child_id, parent_id, text))

    logger.info(f"[文档处理] 缓存命中: {cache_hit_count}, 需计算: {len(texts_need_embedding)}")

    # 批量计算 embedding
    if texts_need_embedding:
        batch_size = 100  # OpenAI 支持较大批次
        for i in range(0, len(texts_need_embedding), batch_size):
            batch = texts_need_embedding[i:i + batch_size]
            batch_texts = [t for _, _, t in batch]
            batch_ids = [cid for cid, _, _ in batch]
            
            try:
                batch_embeddings = embeddings_model.embed_documents(batch_texts)
                
                for child_id, text, emb in zip(batch_ids, batch_texts, batch_embeddings):
                    cached_embeddings[child_id] = emb
                    embedding_cache_set_sync(text, emb)
                    
            except Exception as e:
                logger.error(f"[文档处理] 批量嵌入失败: batch_start={i}, error={str(e)}")
                raise
            
            logger.info(f"[文档处理] 批量嵌入进度: {min(i + batch_size, len(texts_need_embedding))}/{len(texts_need_embedding)}")

    # 构建 Milvus 记录（父块 + 子块）
    milvus_records = []
    chunk_meta = []
    chunk_index = 0

    # 建立 (parent_id, child_text) -> child_id 的映射
    child_key_to_id = {(pid, text): cid for cid, pid, text in children_to_process}

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
            
            # 用 (parent_id, child_text) 找到之前生成的 child_id
            child_id = child_key_to_id.get((parent_id, child_text))
            if not child_id:
                continue
            
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
            
            if len(milvus_records) >= 200:
                insert_chunks(milvus_records)
                logger.info(f"[文档处理] 批量写入Milvus: doc_id={doc_id}, batch_size={len(milvus_records)}")
                milvus_records = []

    if milvus_records:
        insert_chunks(milvus_records)
    
    # 最后统一 flush
    from app.db.milvus_client import get_collection
    col = get_collection()
    col.flush()
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
