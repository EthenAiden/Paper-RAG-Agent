from app.core.config import get_settings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langfuse.langchain import CallbackHandler
from langchain_core.embeddings import Embeddings
from typing import List
import dashscope
from dashscope import TextEmbedding
import os
import logging

_settings = get_settings()
logger = logging.getLogger(__name__)

# 初始化 LangFuse（通过环境变量配置）
_langfuse_initialized = False

def _init_langfuse():
    """初始化 LangFuse 客户端"""
    global _langfuse_initialized
    if _langfuse_initialized:
        return
    
    if _settings.langfuse_public_key and _settings.langfuse_secret_key:
        os.environ["LANGFUSE_PUBLIC_KEY"] = _settings.langfuse_public_key
        os.environ["LANGFUSE_SECRET_KEY"] = _settings.langfuse_secret_key
        if _settings.langfuse_host:
            os.environ["LANGFUSE_HOST"] = _settings.langfuse_host
        _langfuse_initialized = True


def get_langfuse_handler() -> CallbackHandler | None:
    """获取 LangFuse 回调处理器"""
    if not _settings.langfuse_public_key or not _settings.langfuse_secret_key:
        return None
    _init_langfuse()
    return CallbackHandler()


def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=_settings.deepseek_api_key,
        base_url=_settings.deepseek_base_url,
        model=_settings.deepseek_model,
        temperature=0.3,
    )


class AliyunEmbeddings(Embeddings):
    """阿里云嵌入模型适配器"""
    
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        dashscope.api_key = api_key
    
    def _embed_with_retry(self, texts: List[str], max_retries: int = 3) -> List[List[float]]:
        """带重试的嵌入调用"""
        import time
        for retry in range(max_retries):
            try:
                result = TextEmbedding.call(
                    model=self.model,
                    input=texts,
                    parameters={"text_type": "document"}
                )
                if result.status_code == 200:
                    return [item['embedding'] for item in result.output['embeddings']]
                else:
                    raise Exception(f"API error: {result.code} - {result.message}")
            except Exception as e:
                if retry < max_retries - 1:
                    wait_time = (retry + 1) * 2  # 2s, 4s, 6s
                    logger.warning(f"[阿里云嵌入] 调用失败，{wait_time}秒后重试 ({retry+1}/{max_retries}): {str(e)[:100]}")
                    time.sleep(wait_time)
                else:
                    raise
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # 分批处理，阿里云限制每批最多 10 条
        batch_size = 10
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = self._embed_with_retry(batch)
            all_embeddings.extend(embeddings)
            # 批次间短暂休息，避免限流
            if i + batch_size < len(texts):
                import time
                time.sleep(0.5)
        return all_embeddings
    
    def embed_query(self, text: str) -> List[float]:
        result = self._embed_with_retry([text])
        return result[0]


def get_embeddings() -> Embeddings:
    # 判断是否使用阿里云嵌入模型
    if "dashscope" in _settings.embedding_base_url.lower() or "aliyun" in _settings.embedding_model.lower():
        return AliyunEmbeddings(
            api_key=_settings.embedding_api_key,
            model=_settings.embedding_model,
        )
    return OpenAIEmbeddings(
        api_key=_settings.embedding_api_key,
        base_url=_settings.embedding_base_url,
        model=_settings.embedding_model,
    )