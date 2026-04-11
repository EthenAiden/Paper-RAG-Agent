"""对话路由 - 普通问答、流式问答、会话管理"""
import uuid
import json
import asyncio
import logging
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from app.schemas import (
    ApiResponse,
    AskRequest, AskData, ReferenceChunk,
    ConversationCreateData, ConversationOut, ConversationListData,
    MessageOut, MessageListData,
)
from app.graph.chat_graph import run_chat
from app.db.mysql import get_db, Conversation, ConversationMessage, DocumentChunk
from app.db.redis_client import (
    conv_cache_append, conv_cache_get, conv_cache_delete,
    semantic_cache_get, semantic_cache_set,
)
from app.rag.retriever import retrieve
from app.core.llm import get_llm, get_langfuse_handler

logger = logging.getLogger(__name__)
router = APIRouter(tags=["对话"])


# ── 工具函数 ──────────────────────────────────────────────

async def _load_history(conv_id: str, db: AsyncSession) -> list[BaseMessage]:
    """从 Redis 缓存或 MySQL 加载历史消息"""
    cached = await conv_cache_get(conv_id)
    if cached:
        return [
            HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"])
            for m in cached
        ]
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conv_id == conv_id)
        .order_by(ConversationMessage.id)
    )
    rows = result.scalars().all()
    for r in rows:
        await conv_cache_append(conv_id, r.role, r.content)
    return [
        HumanMessage(content=r.content) if r.role == "user" else AIMessage(content=r.content)
        for r in rows
    ]


async def _get_chunk_meta(chunk_ids: list[int], db: AsyncSession) -> list[dict]:
    """批量查询分块元数据，用于构建 references"""
    if not chunk_ids:
        return []
    result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids))
    )
    return result.scalars().all()


# ── 会话管理 ──────────────────────────────────────────────

@router.post("/conversation/create", summary="创建会话")
async def create_conversation(db: AsyncSession = Depends(get_db)):
    conv_id = str(uuid.uuid4()).replace("-", "")
    conv = Conversation(id=conv_id)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    logger.info(f"[会话创建] conv_id={conv_id}")
    return ApiResponse(data=ConversationCreateData(
        conv_id=conv.id,
        created_at=str(conv.created_at),
    ))


@router.get("/conversation/list", summary="会话列表")
async def list_conversations(
    page: int = 1,
    page_size: int = 10,
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size
    total = (await db.execute(select(func.count()).select_from(Conversation))).scalar()
    rows = (await db.execute(
        select(Conversation).order_by(Conversation.updated_at.desc()).offset(offset).limit(page_size)
    )).scalars().all()

    items = [
        ConversationOut(
            id=c.id,
            title=c.title,
            message_count=c.message_count,
            updated_at=str(c.updated_at),
        )
        for c in rows
    ]
    return ApiResponse(data=ConversationListData(total=total, list=items))


@router.get("/conversation/{conv_id}/history", summary="会话历史")
async def get_history(conv_id: str, db: AsyncSession = Depends(get_db)):
    from app.db.mysql import DocumentChunk, Document
    from app.schemas.schemas import ReferenceInfo
    
    conv = await db.get(Conversation, conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conv_id == conv_id)
        .order_by(ConversationMessage.id)
    )
    rows = result.scalars().all()

    items = []
    for r in rows:
        refs = None
        if r.references:
            # 直接解析 JSON
            try:
                refs = json.loads(r.references)
            except:
                refs = None
        
        items.append(MessageOut(
            id=r.id,
            role=r.role,
            content=r.content,
            reference_chunks=refs,
            created_at=str(r.created_at),
        ))
    return ApiResponse(data=MessageListData(list=items))


@router.delete("/conversation/{conv_id}", summary="删除会话")
async def delete_conversation(conv_id: str, db: AsyncSession = Depends(get_db)):
    conv = await db.get(Conversation, conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    await db.execute(delete(ConversationMessage).where(ConversationMessage.conv_id == conv_id))
    await db.delete(conv)
    await db.commit()
    await conv_cache_delete(conv_id)
    return ApiResponse(data={"conv_id": conv_id})


# ── 问答 ──────────────────────────────────────────────────

async def _do_ask(req: AskRequest, db: AsyncSession) -> tuple[str, int, list[dict]]:
    """
    核心问答逻辑，返回 (answer, message_id, references)。
    """
    # 1. 加载历史
    conv = await db.get(Conversation, req.conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    history = await _load_history(req.conv_id, db)

    # 3. 运行 LangGraph
    answer, _, references, detected_course = await run_chat(
        question=req.question,
        conversation_id=req.conv_id,
        history=history,
    )

    # 4. 检索分块用于 references
    docs = retrieve(req.question, top_k=req.top_k)
    chunk_ids_str = ",".join(str(d.metadata.get("chunk_db_id", 0)) for d in docs)

    # 5. 保存消息
    user_msg = ConversationMessage(conv_id=req.conv_id, role="user", content=req.question)
    db.add(user_msg)
    await db.flush()

    # 存储 references 为 JSON
    refs_json = json.dumps(references, ensure_ascii=False) if references else None
    
    asst_msg = ConversationMessage(
        conv_id=req.conv_id,
        role="assistant",
        content=answer,
        references=refs_json,
    )
    db.add(asst_msg)

    conv.message_count = (conv.message_count or 0) + 2
    
    # 第一次对话时自动生成标题
    if conv.title == "新对话" or not conv.title:
        from app.graph.chat_graph import generate_title
        conv.title = generate_title(req.question)
        logger.info(f"[问答] 生成标题: {conv.title}")
    
    await db.commit()
    await db.refresh(asst_msg)

    # 6. 更新 Redis 会话缓存
    await conv_cache_append(req.conv_id, "user", req.question)
    await conv_cache_append(req.conv_id, "assistant", answer)

    # 7. 构建 references
    references = [
        {
            "chunk_id": d.metadata.get("chunk_db_id", 0),
            "doc_name": d.metadata.get("doc_name", ""),
            "content": d.page_content[:200],
        }
        for d in docs
    ]

    return answer, asst_msg.id, references


@router.post("/chat/ask", summary="普通问答")
async def ask(req: AskRequest, db: AsyncSession = Depends(get_db)):
    answer, message_id, references = await _do_ask(req, db)
    return ApiResponse(data=AskData(
        answer=answer,
        message_id=message_id,
        references=[ReferenceChunk(**r) for r in references],
    ))


@router.post("/chat/stream_ask", summary="流式问答（SSE）")
async def stream_ask(req: AskRequest, db: AsyncSession = Depends(get_db)):
    """SSE 流式输出。"""
    logger.info(f"[流式问答] conv_id={req.conv_id}, question={req.question[:50]}...")
    
    # 加载历史
    conv = await db.get(Conversation, req.conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    history = await _load_history(req.conv_id, db)
    
    conv_id = req.conv_id
    question = req.question

    async def _stream() -> AsyncIterator[str]:
        from app.db.mysql import AsyncSessionLocal
        
        # 运行 Agent
        answer, _, references, detected_course = await run_chat(
            question=question,
            conversation_id=conv_id,
            history=history,
        )
        
        # 流式输出
        for char in answer:
            yield f"event: message\ndata: {json.dumps({'content': char}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
        
        logger.info(f"[流式问答] 生成完成, answer_len={len(answer)}")

        # 保存消息（使用独立的同步引擎）
        message_id = -1
        try:
            from app.core.config import get_settings
            from sqlalchemy import create_engine
            from sqlalchemy.orm import Session
            
            settings = get_settings()
            # 创建独立的同步引擎（不使用连接池，避免异步问题）
            sync_url = settings.mysql_url.replace("+aiomysql", "+pymysql")
            sync_engine = create_engine(sync_url, pool_pre_ping=True)
            
            with Session(sync_engine) as session:
                user_msg = ConversationMessage(conv_id=conv_id, role="user", content=question)
                session.add(user_msg)
                
                # 存储 references 为 JSON
                refs_json = json.dumps(references, ensure_ascii=False) if references else None
                asst_msg = ConversationMessage(
                    conv_id=conv_id,
                    role="assistant",
                    content=answer,
                    references=refs_json,
                )
                session.add(asst_msg)
                
                conv_obj = session.get(Conversation, conv_id)
                if conv_obj:
                    conv_obj.message_count = (conv_obj.message_count or 0) + 2
                    # 第一次对话时自动生成标题
                    if conv_obj.title == "新对话" or not conv_obj.title:
                        from app.graph.chat_graph import generate_title
                        conv_obj.title = generate_title(question)
                        logger.info(f"[流式问答] 生成标题: {conv_obj.title}")
                session.commit()
                message_id = asst_msg.id
            
            logger.info(f"[流式问答] 消息已保存, message_id={message_id}")

            await conv_cache_append(conv_id, "user", question)
            await conv_cache_append(conv_id, "assistant", answer)
        except Exception as e:
            logger.error(f"[流式问答] 保存消息失败: {e}")

        yield f"event: end\ndata: {json.dumps({'message_id': message_id, 'references': references, 'course': detected_course}, ensure_ascii=False)}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")