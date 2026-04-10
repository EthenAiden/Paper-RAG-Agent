from app.core.config import get_settings
from langchain_openai import ChatOpenAI
from langfuse.langchain import CallbackHandler
from langchain_core.embeddings import Embeddings
from typing import List
from openai import OpenAI
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


class OpenAIEmbeddingsAdapter(Embeddings):
    """OpenAI 嵌入模型适配器"""
    
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量生成嵌入向量"""
        all_embeddings = []
        batch_size = 100  # OpenAI 支持较大批次
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=batch
                )
                embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(embeddings)
            except Exception as e:
                logger.error(f"[OpenAI嵌入] 批量嵌入失败: {str(e)}")
                raise
        
        return all_embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """生成单个文本的嵌入向量"""
        response = self.client.embeddings.create(
            model=self.model,
            input=text
        )
        return response.data[0].embedding


def get_embeddings() -> Embeddings:
    return OpenAIEmbeddingsAdapter(
        api_key=_settings.embedding_api_key,
        base_url=_settings.embedding_base_url,
        model=_settings.embedding_model,
    )