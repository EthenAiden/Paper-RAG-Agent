# RAG 问答机器人

基于 LangChain + LangGraph + Advanced RAG 的高校课程问答系统。

## 项目架构

```
├── app/
│   ├── api/routes/      # API 路由
│   ├── core/            # 核心配置（LLM、Embedding）
│   ├── db/              # 数据库客户端（Milvus、MySQL、Redis、MinIO）
│   ├── graph/           # LangGraph 工作流
│   ├── rag/             # RAG 检索器、文档处理
│   └── schemas/         # Pydantic 数据模型
├── frontend/            # Vue 3 前端
├── scripts/             # 数据处理脚本
└── docker-compose.yml   # 基础设施编排
```

## 技术栈

**后端**
- FastAPI + Uvicorn
- LangChain / LangGraph（Agent 工作流）
- Milvus（向量数据库）
- MySQL（会话、文档元数据）
- Redis（缓存、语义缓存）
- MinIO（文档对象存储）

**前端**
- Vue 3 + Vite
- Axios + Marked

**LLM**
- DeepSeek（对话生成）
- OpenAI / 阿里云 DashScope（Embedding）

## 快速开始

### 1. 启动基础设施

```bash
docker-compose up -d
```

服务端口：
- Milvus: 19530
- Attu (Milvus GUI): 3000
- MinIO: 9000 (API) / 9001 (Console)
- MySQL: 3306
- Redis: 6379

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 填入 API Key：

```env
# DeepSeek LLM
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# Embedding（OpenAI 或阿里云）
EMBEDDING_API_KEY=your_api_key
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
```

### 3. 安装依赖

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. 启动后端

```bash
python main.py
# 或
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API 文档：http://localhost:8000/docs

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：http://localhost:5173

## 核心功能

### Agent 工作流

```
┌─────────────────────────────────────────────────────────────────────┐
│                           用户问题                                   │
└─────────────────────────────────┬───────────────────────────────────┘
                                  ▼
                         ┌───────────────┐
                         │   classify    │
                         │   问题分类     │
                         └───────┬───────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
        ┌──────────┐      ┌──────────┐       ┌──────────┐
        │  course  │      │  unclear │       │ general  │
        │  课程问题 │      │  不明确   │       │ 通用问题  │
        └────┬─────┘      └────┬─────┘       └────┬─────┘
             │                 │                  │
             ▼                 ▼                  │
    ┌─────────────────┐  ┌───────────┐            │
    │  course_detect  │  │  clarify  │            │
    │    课程识别     │  │  追问澄清  │            │
    └────────┬────────┘  └─────┬─────┘            │
             │                 │                  │
             ▼                 ▼                  │
    ┌─────────────────┐      END                  │
    │    retrieve     │                           │
    │   向量检索       │                          │
    └────────┬────────┘                           │
             │                                    │
             ▼                                    │
    ┌─────────────────┐                           │
    │   grade_docs    │                           │
    │   文档评分       │                           │
    └────────┬────────┘                           │
             │                                    │
             ▼                                    ▼
    ┌─────────────────────────────────────────────────┐
    │                    generate                      │
    │                   生成答案                       │
    │  • RAG 模式：基于检索结果 + 引用标注              │
    │  • 直接模式：LLM 直接回答                        │
    └─────────────────────────┬───────────────────────┘
                              ▼
                         ┌───────────┐
                         │   END     │
                         │  返回答案  │
                         └───────────┘
```

- **问题分类**：区分课程问题 / 通用问题 / 不明确
- **课程识别**：自动识别问题所属课程
- **查询改写**：生成多个检索查询变体
- **向量检索**：Milvus 相似度搜索，支持课程过滤
- **引用标注**：答案中标注来源 [来源:n]

### API 接口

| 接口 | 说明 |
|------|------|
| `POST /api/v1/conversation/create` | 创建会话 |
| `GET /api/v1/conversation/list` | 会话列表 |
| `GET /api/v1/conversation/{id}/history` | 会话历史 |
| `POST /api/v1/chat/ask` | 普通问答 |
| `POST /api/v1/chat/stream_ask` | 流式问答（SSE） |


## 可观测性

支持 LangFuse 追踪，在 `.env` 中配置：

```env
LANGFUSE_PUBLIC_KEY=your_key
LANGFUSE_SECRET_KEY=your_secret
LANGFUSE_HOST=https://cloud.langfuse.com
```

## License

MIT