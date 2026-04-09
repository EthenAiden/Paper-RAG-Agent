"""Milvus 向量数据库操作"""
from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)
from app.core.config import get_settings
import logging

settings = get_settings()
logger = logging.getLogger(__name__)

_COLLECTION_NAME = settings.milvus_collection
_DIM = settings.embedding_dimension


def connect_milvus():
    connections.connect(host=settings.milvus_host, port=settings.milvus_port)


def ensure_collection() -> Collection:
    connect_milvus()
    
    # 检查现有集合的维度和字段
    if utility.has_collection(_COLLECTION_NAME):
        col = Collection(_COLLECTION_NAME)
        existing_dim = None
        has_parent_id = False
        for field in col.schema.fields:
            if field.name == "embedding":
                existing_dim = field.params.get("dim")
            if field.name == "parent_id":
                has_parent_id = True
        
        # 维度不匹配或缺少父子分块字段，重建集合
        if existing_dim and existing_dim != _DIM:
            logger.warning(f"[Milvus] 维度不匹配，删除旧集合: existing_dim={existing_dim}, new_dim={_DIM}")
            utility.drop_collection(_COLLECTION_NAME)
        elif not has_parent_id:
            logger.warning(f"[Milvus] 缺少父子分块字段，删除旧集合重建")
            utility.drop_collection(_COLLECTION_NAME)
        else:
            return col

    logger.info(f"[Milvus] 创建新集合: name={_COLLECTION_NAME}, dim={_DIM}")
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
        FieldSchema(name="doc_id", dtype=DataType.INT64),
        FieldSchema(name="chunk_index", dtype=DataType.INT64),
        FieldSchema(name="parent_id", dtype=DataType.VARCHAR, max_length=64),  # 父块ID
        FieldSchema(name="is_child", dtype=DataType.BOOL),  # 是否为子块
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=8192),  # 增大容量存父块
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=_DIM),
    ]
    schema = CollectionSchema(fields=fields, description="RAG document chunks with parent-child")
    collection = Collection(name=_COLLECTION_NAME, schema=schema)

    # IVF_FLAT 索引（适合中小规模）
    collection.create_index(
        field_name="embedding",
        index_params={"metric_type": "COSINE", "index_type": "IVF_FLAT", "params": {"nlist": 128}},
    )
    collection.load()
    return collection


def get_collection() -> Collection:
    connect_milvus()
    col = Collection(_COLLECTION_NAME)
    col.load()
    return col


def insert_chunks(chunks: list[dict]) -> None:
    """
    chunks: list of {id, doc_id, chunk_index, parent_id, is_child, content, embedding}
    """
    col = ensure_collection()
    col.insert(chunks)
    col.flush()


def search_similar(
    query_embedding: list[float],
    top_k: int = 5,
    doc_ids: list[int] | None = None,
) -> list[dict]:
    """检索子块，返回对应的父块内容"""
    col = get_collection()
    
    # 只检索子块
    expr = "is_child == true"
    if doc_ids:
        expr = f"doc_id in {doc_ids} and is_child == true"
    
    results = col.search(
        data=[query_embedding],
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"nprobe": 16}},
        limit=top_k,
        expr=expr,
        output_fields=["id", "doc_id", "chunk_index", "parent_id", "content"],
    )
    
    hits = []
    parent_ids = set()
    child_to_parent = {}
    
    for hit in results[0]:
        child_id = hit.entity.get("id")
        parent_id = hit.entity.get("parent_id")
        child_to_parent[child_id] = parent_id
        parent_ids.add(parent_id)
        
        hits.append({
            "id": child_id,
            "doc_id": hit.entity.get("doc_id"),
            "chunk_index": hit.entity.get("chunk_index"),
            "parent_id": parent_id,
            "content": hit.entity.get("content"),  # 先存子块内容，后面替换为父块
            "score": hit.distance,
        })
    
    # 批量查询父块内容
    if parent_ids:
        parent_contents = {}
        parent_results = col.query(
            expr=f'id in {[pid for pid in parent_ids if pid]}',
            output_fields=["id", "content"]
        )
        for pr in parent_results:
            parent_contents[pr["id"]] = pr["content"]
        
        # 用父块内容替换子块内容
        for hit in hits:
            parent_content = parent_contents.get(hit["parent_id"])
            if parent_content:
                hit["content"] = parent_content
    
    return hits


def delete_by_doc_id(doc_id: int) -> None:
    col = get_collection()
    col.delete(expr=f"doc_id == {doc_id}")
    col.flush()
