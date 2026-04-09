"""用户反馈路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.schemas import ApiResponse, FeedbackRequest, FeedbackData
from app.db.mysql import get_db, UserFeedback, ConversationMessage

router = APIRouter(tags=["反馈"])


@router.post("/feedback/submit", summary="提交反馈")
async def submit_feedback(req: FeedbackRequest, db: AsyncSession = Depends(get_db)):
    # 校验 message_id 存在
    msg = await db.get(ConversationMessage, req.message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    if msg.role != "assistant":
        raise HTTPException(status_code=400, detail="只能对助手回答评分")

    feedback = UserFeedback(
        message_id=req.message_id,
        score=req.score,
        comment=req.comment,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    return ApiResponse(data=FeedbackData(feedback_id=feedback.id))
