"""
高校课程 Agent 助手 - LangGraph 工作流

节点：
  classify      → 问题分类（课程问题/通用问题/不明确）
  course_detect → 课程识别
  clarify       → 追问澄清
  retrieve      → 课程知识库检索
  grade_docs    → 文档相关性评分
  generate      → 生成答案 + 引用标注
"""
from __future__ import annotations

import uuid
import logging
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.documents import Document
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from app.core.llm import get_llm, get_langfuse_handler
from app.rag.retriever import retrieve

logger = logging.getLogger(__name__)


# ---------- State ----------

class ChatState(TypedDict):
    conversation_id: str
    messages: Annotated[list[BaseMessage], add_messages]
    question: str
    
    # 分类相关
    question_type: str  # "course" | "general" | "unclear"
    
    # 课程相关
    detected_course: str | None
    course_id: int | None
    
    # 检索相关
    retrieved_docs: list[dict]
    retrieval_quality: str  # "high" | "low" | "none"
    
    # 生成相关
    answer: str
    references: list[dict]
    
    # 澄清相关
    need_clarify: bool
    clarify_question: str


# ---------- Prompts ----------

_CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是一个高校课程助手的意图识别模块。\n"
        "分析用户问题，判断属于哪一类：\n"
        "1. course - 课程相关问题（关于某门课程的知识点、概念、作业、考试等）\n"
        "2. general - 通用问题（闲聊、数学计算、编程问题、生活问题等）\n"
        "3. unclear - 不明确（问题模糊，需要更多信息）\n"
        "只输出类别名称（course/general/unclear），不要解释。",
    ),
    ("human", "{question}"),
])

_COURSE_DETECT_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是一个课程识别专家。根据用户问题，判断可能涉及哪门课程。\n\n"
        "可选课程列表：\n"
        "{course_list}\n\n"
        "输出规则：\n"
        "- 如果能确定课程，只输出课程名称\n"
        "- 如果无法确定，输出 unknown\n"
        "- 如果涉及多门课程，输出最相关的一门",
    ),
    ("human", "{question}"),
])

_CLARIFY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是一个友好的课程助手。用户的问题不够明确，需要追问澄清。\n"
        "生成一个简洁的追问，帮助明确用户想问的课程或问题。",
    ),
    ("human", "{question}"),
])

_GRADE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是一个文档相关性评估专家。评估检索到的文档是否与问题相关。\n"
        "评分标准：\n"
        "- high: 文档包含直接相关的核心信息\n"
        "- low: 文档只有部分相关或边缘信息\n"
        "- none: 文档与问题完全无关\n"
        "只输出评分结果（high/low/none）。",
    ),
    ("human", "问题：{question}\n\n文档内容：{content}"),
])

_RAG_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是一个专业的高校课程助教。基于检索到的课程资料回答学生问题。\n\n"
        "要求：\n"
        "1. 准确、专业地回答问题\n"
        "2. 在使用参考资料时，标注引用来源，格式为 [来源:n]\n"
        "3. 如果资料不足，诚实说明并尝试用自身知识补充\n"
        "4. 语言简洁清晰\n\n"
        "课程：{course_name}\n\n"
        "参考资料：\n{context_with_refs}",
    ),
    MessagesPlaceholder("history"),
    ("human", "{question}"),
])

_DIRECT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是一个友好的助手，直接回答用户问题。保持简洁专业。"),
    MessagesPlaceholder("history"),
    ("human", "{question}"),
])


# ---------- Helper Functions ----------

def _get_course_list() -> str:
    """获取课程列表"""
    # TODO: 从数据库获取
    # 暂时返回示例
    return "机器学习、深度学习、数据结构、算法设计、操作系统、计算机网络、数据库原理"


def _build_context_with_refs(docs: list[dict]) -> tuple[str, list[dict]]:
    """构建带引用编号的上下文"""
    if not docs:
        return "", []
    
    context_parts = []
    references = []
    
    for i, doc in enumerate(docs, 1):
        context_parts.append(f"[来源:{i}] {doc['content']}")
        references.append({
            "id": i,
            "doc_name": doc.get("doc_name", "未知文档"),
            "chunk_id": doc.get("chunk_id"),
            "content": doc["content"][:200] + "..." if len(doc["content"]) > 200 else doc["content"],
        })
    
    return "\n\n---\n\n".join(context_parts), references


# ---------- Nodes ----------

def _classify_node(state: ChatState) -> dict:
    """问题分类节点"""
    logger.info(f"[Agent] 分类节点: question={state['question'][:50]}...")
    
    llm = get_llm()
    chain = _CLASSIFY_PROMPT | llm
    result = chain.invoke({"question": state["question"]})
    
    question_type = result.content.strip().lower()
    if question_type not in ["course", "general", "unclear"]:
        question_type = "general"
    
    logger.info(f"[Agent] 分类结果: type={question_type}")
    return {"question_type": question_type}


def _course_detect_node(state: ChatState) -> dict:
    """课程识别节点"""
    logger.info(f"[Agent] 课程识别节点")
    
    llm = get_llm()
    course_list = _get_course_list()
    chain = _COURSE_DETECT_PROMPT | llm
    result = chain.invoke({
        "question": state["question"],
        "course_list": course_list,
    })
    
    detected_course = result.content.strip()
    if detected_course.lower() == "unknown":
        detected_course = None
    
    logger.info(f"[Agent] 课程识别结果: course={detected_course}")
    return {"detected_course": detected_course}


def _clarify_node(state: ChatState) -> dict:
    """追问澄清节点"""
    logger.info(f"[Agent] 澄清节点")
    
    llm = get_llm()
    chain = _CLARIFY_PROMPT | llm
    result = chain.invoke({"question": state["question"]})
    
    clarify_question = result.content.strip()
    return {
        "need_clarify": True,
        "clarify_question": clarify_question,
        "answer": clarify_question,
    }


def _retrieve_node(state: ChatState) -> dict:
    """检索节点"""
    logger.info(f"[Agent] 检索节点: course={state.get('detected_course')}")
    
    # 检索相关文档
    docs = retrieve(
        state["question"],
        top_k=5,
        course_id=state.get("course_id"),  # 按课程过滤
    )
    
    # 转换为字典格式
    doc_dicts = []
    for d in docs:
        doc_dicts.append({
            "content": d.page_content,
            "doc_name": d.metadata.get("doc_name", "未知"),
            "chunk_id": d.metadata.get("chunk_id"),
            "score": d.metadata.get("score", 0),
        })
    
    logger.info(f"[Agent] 检索结果: docs={len(doc_dicts)}")
    return {"retrieved_docs": doc_dicts}


def _grade_docs_node(state: ChatState) -> dict:
    """文档相关性评分节点"""
    logger.info(f"[Agent] 评分节点")
    
    docs = state.get("retrieved_docs", [])
    
    if not docs:
        return {"retrieval_quality": "none"}
    
    # 简单评分：基于分数阈值
    high_score_count = sum(1 for d in docs if d.get("score", 0) > 0.6)
    
    if high_score_count >= 2:
        quality = "high"
    elif high_score_count >= 1:
        quality = "low"
    else:
        quality = "none"
    
    logger.info(f"[Agent] 评分结果: quality={quality}, high_score_count={high_score_count}")
    return {"retrieval_quality": quality}


def _generate_node(state: ChatState) -> dict:
    """生成节点"""
    logger.info(f"[Agent] 生成节点")
    
    llm = get_llm()
    history = state.get("messages", [])[:-1]  # 排除当前问题
    
    # 判断生成模式
    if state.get("question_type") == "course" and state.get("retrieved_docs"):
        # RAG 生成
        context_with_refs, references = _build_context_with_refs(state["retrieved_docs"])
        course_name = state.get("detected_course", "未知课程")
        
        chain = _RAG_PROMPT | llm
        result = chain.invoke({
            "course_name": course_name,
            "context_with_refs": context_with_refs,
            "history": history,
            "question": state["question"],
        })
        
        return {
            "answer": result.content,
            "references": references,
        }
    else:
        # 直接生成
        chain = _DIRECT_PROMPT | llm
        result = chain.invoke({
            "history": history,
            "question": state["question"],
        })
        
        return {
            "answer": result.content,
            "references": [],
        }


# ---------- Routing Functions ----------

def _route_after_classify(state: ChatState) -> str:
    """分类后的路由"""
    q_type = state.get("question_type", "general")
    if q_type == "course":
        return "course_detect"
    elif q_type == "unclear":
        return "clarify"
    else:
        return "generate"


def _route_after_grade(state: ChatState) -> str:
    """评分后的路由"""
    quality = state.get("retrieval_quality", "none")
    if quality == "none":
        # 无相关内容，直接生成（不使用检索结果）
        return "generate"
    else:
        return "generate"


# ---------- Build Graph ----------

def build_graph() -> StateGraph:
    graph = StateGraph(ChatState)
    
    # 添加节点
    graph.add_node("classify", _classify_node)
    graph.add_node("course_detect", _course_detect_node)
    graph.add_node("clarify", _clarify_node)
    graph.add_node("retrieve", _retrieve_node)
    graph.add_node("grade_docs", _grade_docs_node)
    graph.add_node("generate", _generate_node)
    
    # 设置入口
    graph.set_entry_point("classify")
    
    # 添加边
    graph.add_conditional_edges(
        "classify",
        _route_after_classify,
        {
            "course_detect": "course_detect",
            "clarify": "clarify",
            "generate": "generate",
        }
    )
    
    graph.add_edge("course_detect", "retrieve")
    graph.add_edge("retrieve", "grade_docs")
    graph.add_conditional_edges(
        "grade_docs",
        _route_after_grade,
        {"generate": "generate"}
    )
    
    graph.add_edge("clarify", END)
    graph.add_edge("generate", END)
    
    return graph.compile()


# 全局编译好的图
rag_graph = build_graph()


async def run_chat(
    question: str,
    conversation_id: str | None = None,
    history: list[BaseMessage] | None = None,
) -> tuple[str, str, list[dict], str | None]:
    """
    运行对话
    
    Returns:
        tuple: (answer, conversation_id, references, detected_course)
    """
    cid = conversation_id or str(uuid.uuid4())
    messages = list(history or []) + [HumanMessage(content=question)]
    
    initial_state: ChatState = {
        "conversation_id": cid,
        "messages": messages,
        "question": question,
        "question_type": "general",
        "detected_course": None,
        "course_id": None,
        "retrieved_docs": [],
        "retrieval_quality": "none",
        "answer": "",
        "references": [],
        "need_clarify": False,
        "clarify_question": "",
    }
    
    # 获取 LangFuse handler
    langfuse_handler = get_langfuse_handler()
    config = {"callbacks": [langfuse_handler]} if langfuse_handler else {}
    
    logger.info(f"[Agent] 开始执行: conv_id={cid}, question={question[:50]}...")
    final_state = await rag_graph.ainvoke(initial_state, config=config)
    
    answer = final_state.get("answer", "")
    references = final_state.get("references", [])
    detected_course = final_state.get("detected_course")
    
    logger.info(f"[Agent] 执行完成: answer_len={len(answer)}, refs={len(references)}, course={detected_course}")
    
    return answer, cid, references, detected_course