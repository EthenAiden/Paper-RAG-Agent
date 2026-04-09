"""Redis 客户端 - 会话缓存、语义缓存"""
import json
import hashlib
import redis.asyncio as aioredis
from app.core.config import get_settings

settings = get_settings()

# 会话缓存 TTL：7 天
_CONV_TTL = 7 * 24 * 3600
# 语义缓存 TTL：24 小时
_SEMANTIC_TTL = 24 * 3600
# 会话保留的最近消息条数
_CONV_MAX_TURNS = 20

_redis_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.redis_db,
            decode_responses=True,
        )
    return _redis_client


# ── 通用缓存 ────────────────────────────────────────────────

async def cache_set(key: str, value: dict | list | str, ttl: int | None = None) -> None:
    client = get_redis()
    data = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    await client.set(key, data, ex=ttl or settings.redis_ttl)


async def cache_get(key: str) -> dict | list | str | None:
    client = get_redis()
    data = await client.get(key)
    if data is None:
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return data


async def cache_delete(key: str) -> None:
    client = get_redis()
    await client.delete(key)


# ── 会话缓存：conv:{conv_id}（List，存最近 N 条消息 JSON）────

def _conv_key(conv_id: str) -> str:
    return f"conv:{conv_id}"


async def conv_cache_append(conv_id: str, role: str, content: str) -> None:
    """追加一条消息到会话缓存，超出上限时截断头部"""
    client = get_redis()
    key = _conv_key(conv_id)
    msg = json.dumps({"role": role, "content": content}, ensure_ascii=False)
    await client.rpush(key, msg)
    await client.ltrim(key, -_CONV_MAX_TURNS, -1)
    await client.expire(key, _CONV_TTL)


async def conv_cache_get(conv_id: str) -> list[dict]:
    """获取会话缓存中的消息列表"""
    client = get_redis()
    raw_list = await client.lrange(_conv_key(conv_id), 0, -1)
    return [json.loads(item) for item in raw_list]


async def conv_cache_delete(conv_id: str) -> None:
    client = get_redis()
    await client.delete(_conv_key(conv_id))


# ── 语义缓存：cache:question:{hash} ───────────────────────────

def _semantic_key(question: str) -> str:
    h = hashlib.md5(question.strip().encode()).hexdigest()
    return f"cache:question:{h}"


async def semantic_cache_get(question: str) -> dict | None:
    """精确 hash 匹配语义缓存"""
    data = await cache_get(_semantic_key(question))
    if isinstance(data, dict):
        return data
    return None


async def semantic_cache_set(question: str, answer: str, references: list) -> None:
    """写入语义缓存"""
    await cache_set(
        _semantic_key(question),
        {"answer": answer, "references": references},
        ttl=_SEMANTIC_TTL,
    )


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


# ── Embedding 缓存：emb:{hash} ────────────────────────────────
# 缓存文本的 embedding 向量，避免重复计算
_EMB_TTL = 7 * 24 * 3600  # 7 天

def _embedding_key(text: str) -> str:
    """生成 embedding 缓存 key"""
    h = hashlib.md5(text.strip().encode()).hexdigest()
    return f"emb:{h}"


async def embedding_cache_get(text: str) -> list[float] | None:
    """获取缓存的 embedding"""
    data = await cache_get(_embedding_key(text))
    if isinstance(data, list):
        return data
    return None


async def embedding_cache_set(text: str, embedding: list[float]) -> None:
    """缓存 embedding 向量"""
    await cache_set(_embedding_key(text), embedding, ttl=_EMB_TTL)
