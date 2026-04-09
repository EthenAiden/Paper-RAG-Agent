"""文档管理路由"""
import asyncio
import uuid
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from app.schemas import ApiResponse, DocumentUploadData, DocumentOut, DocumentDetail, DocumentListData
from app.db.mysql import get_db, Document, DocumentChunk
from app.db.milvus_client import delete_by_doc_id
from app.db.minio_client import upload_file, delete_file, get_presigned_url, ensure_bucket
from app.rag.document_processor import process_document
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/document", tags=["文档管理"])

_ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".docx", ".xlsx"}

_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@router.post("/upload", summary="上传文档")
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        logger.warning(f"[文档上传] 不支持的文件类型: {ext}, filename={file.filename}")
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    content = await file.read()
    file_size = len(content)
    logger.info(f"[文档上传] 开始上传: filename={file.filename}, size={file_size}, type={ext}")

    # MinIO 对象路径：documents/{yyyyMMdd}/{uuid}.{ext}
    date_str = datetime.now().strftime("%Y%m%d")
    object_path = f"documents/{date_str}/{uuid.uuid4().hex}{ext}"

    ensure_bucket()
    upload_file(object_path, content, _CONTENT_TYPES.get(ext, "application/octet-stream"))
    logger.info(f"[文档上传] 文件已上传到MinIO: {object_path}")

    doc = Document(
        name=file.filename,
        file_type=ext.lstrip("."),
        file_size=file_size,
        minio_bucket=settings.minio_bucket,
        minio_object_path=object_path,
        status=0,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    doc_id = doc.id
    logger.info(f"[文档上传] 文档记录已创建: doc_id={doc_id}, filename={file.filename}")

    # 异步后台处理：解析 → 分块 → 向量化 → 写 MySQL
    async def _process():
        from app.db.mysql import AsyncSessionLocal
        logger.info(f"[文档处理] 开始处理: doc_id={doc_id}")
        async with AsyncSessionLocal() as session:
            try:
                chunk_count = await process_document(object_path, doc_id, session)
                doc_update = await session.get(Document, doc_id)
                if doc_update:
                    doc_update.status = 1
                    doc_update.chunk_count = chunk_count
                await session.commit()
                logger.info(f"[文档处理] 处理完成: doc_id={doc_id}, chunks={chunk_count}")
            except Exception as e:
                logger.error(f"[文档处理] 处理失败: doc_id={doc_id}, error={str(e)}")
                doc_update = await session.get(Document, doc_id)
                if doc_update:
                    doc_update.status = 2
                    doc_update.error_msg = str(e)[:500]
                await session.commit()

    asyncio.create_task(_process())

    return ApiResponse(data=DocumentUploadData(
        doc_id=doc_id,
        name=file.filename,
        status=0,
        created_at=str(doc.created_at),
    ))


@router.get("/list", summary="文档列表")
async def list_documents(
    page: int = 1,
    page_size: int = 10,
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size
    total = (await db.execute(select(func.count()).select_from(Document))).scalar()
    rows = (await db.execute(
        select(Document).order_by(Document.created_at.desc()).offset(offset).limit(page_size)
    )).scalars().all()

    items = [
        DocumentOut(
            id=d.id,
            name=d.name,
            file_type=d.file_type,
            file_size=d.file_size,
            status=d.status,
            chunk_count=d.chunk_count,
            created_at=str(d.created_at),
        )
        for d in rows
    ]
    return ApiResponse(data=DocumentListData(total=total, list=items))


@router.get("/{doc_id}", summary="文档详情")
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    minio_url = get_presigned_url(doc.minio_object_path)
    return ApiResponse(data=DocumentDetail(
        id=doc.id,
        name=doc.name,
        file_type=doc.file_type,
        file_size=doc.file_size,
        minio_url=minio_url,
        status=doc.status,
        summary=doc.summary,
        chunk_count=doc.chunk_count,
        created_at=str(doc.created_at),
    ))


@router.delete("/{doc_id}", summary="删除文档")
async def delete_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 1. Milvus 向量删除
    await asyncio.to_thread(delete_by_doc_id, doc_id)
    # 2. MinIO 文件删除
    delete_file(doc.minio_object_path)
    # 3. MySQL 分块记录删除
    await db.execute(delete(DocumentChunk).where(DocumentChunk.doc_id == doc_id))
    # 4. MySQL 文档记录删除
    await db.delete(doc)
    await db.commit()

    return ApiResponse(data={"doc_id": doc_id})


@router.post("/{doc_id}/reparse", summary="重新解析文档")
async def reparse_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.status == 0:
        raise HTTPException(status_code=400, detail="文档正在解析中")

    # 断点续传：失败时不清除旧数据，跳过已处理的分块
    if doc.status == 2:
        # 失败重试，启用断点续传
        doc.status = 0
        doc.error_msg = None
        await db.commit()
        resume = True
    else:
        # 手动重新解析，清除旧数据
        await asyncio.to_thread(delete_by_doc_id, doc_id)
        await db.execute(delete(DocumentChunk).where(DocumentChunk.doc_id == doc_id))
        doc.status = 0
        doc.chunk_count = 0
        doc.error_msg = None
        await db.commit()
        resume = False

    object_path = doc.minio_object_path

    async def _reprocess():
        from app.db.mysql import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            try:
                chunk_count = await process_document(object_path, doc_id, session, resume=resume)
                doc_update = await session.get(Document, doc_id)
                if doc_update:
                    doc_update.status = 1
                    doc_update.chunk_count = chunk_count
                await session.commit()
            except Exception as e:
                doc_update = await session.get(Document, doc_id)
                if doc_update:
                    doc_update.status = 2
                    doc_update.error_msg = str(e)[:500]
                await session.commit()

    asyncio.create_task(_reprocess())
    return ApiResponse(data={"doc_id": doc_id, "status": 0, "resume": resume})
