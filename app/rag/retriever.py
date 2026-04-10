"""
高校课程助手 - RAG 检索器
策略：
1. 查询改写（Query Rewriting）- 生成多个检索查询
2. 向量检索（Dense Retrieval）- 支持按课程过滤
3. 重排序（Reranking）- 基于相关度分数过滤
"""
import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document

from app.core.llm import get_llm, get_embeddings
from app.db.milvus_client import search_similar

logger = logging.getLogger(__name__)

_REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是一个搜索查询优化专家。给定用户问题，生成 2 个语义相近但措辞不同的搜索查询，"
        "每行一个，不要编号，不要解释。如果问题已经很明确，可以只输出原问题。",
    ),
    ("human", "{question}"),
])


def rewrite_query(question: str) -> list[str]:
    """生成多个查询变体，用于多路检索"""
    llm = get_llm()
    chain = _REWRITE_PROMPT | llm | StrOutputParser()
    
    try:
        raw = chain.invoke({"question": question})
        queries = [q.strip() for q in raw.strip().splitlines() if q.strip()]
        # 原始 + 最多2个变体
        return [question] + queries[:2]
    except Exception as e:
        logger.warning(f"[检索] 查询改写失败: {e}")
        return [question]


def retrieve(
    question: str,
    top_k: int = 5,
    doc_ids: list[int] | None = None,
) -> list[Document]:
    """
    课程 RAG 检索
    
    Args:
        question: 用户问题
        top_k: 返回结果数量
        doc_ids: 文档ID列表，用于过滤
    
    Returns:
        检索到的文档列表
    """
    logger.info(f"[检索] 开始: question={question[:50]}...")
    
    embeddings_model = get_embeddings()
    
    # 查询改写
    queries = rewrite_query(question)
    logger.info(f"[检索] 查询变体: {len(queries)} 个")
    
    seen_ids: set[str] = set()
    all_hits: list[dict] = []
    
    # 多路检索
    for q in queries:
        try:
            vec = embeddings_model.embed_query(q)
            hits = search_similar(vec, top_k=top_k, doc_ids=doc_ids)
            
            for hit in hits:
                if hit["id"] not in seen_ids:
                    seen_ids.add(hit["id"])
                    all_hits.append(hit)
        except Exception as e:
            logger.warning(f"[检索] 向量检索失败: {e}")
            continue
    
    # 按相似度分数降序
    all_hits.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    # 记录实际分数用于调试
    if all_hits:
        top_scores = [h.get("score", 0) for h in all_hits[:5]]
        logger.info(f"[检索] Top分数: {top_scores}")
    
    # 相关性过滤（保留分数 > 0.2 的结果，cosine相似度通常在0.3-0.8之间）
    filtered = [h for h in all_hits if h.get("score", 0) > 0.2][:top_k]
    
    logger.info(f"[检索] 结果: total={len(all_hits)}, filtered={len(filtered)}")
    
    return [
        Document(
            page_content=h["content"],
            metadata={
                "doc_id": h.get("doc_id"),
                "chunk_id": h.get("chunk_id"),
                "chunk_db_id": h.get("chunk_id"),  # 兼容旧字段
                "doc_name": h.get("doc_name", "未知文档"),
                "score": h.get("score", 0),
            },
        )
        for h in filtered
    ]
