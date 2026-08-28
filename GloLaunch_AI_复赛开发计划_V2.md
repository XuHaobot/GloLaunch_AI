# GloLaunch AI 复赛开发计划（V2 — LangGraph 架构）

---

## 一、架构策略：LangGraph + 零迁移 + 仅迁移虚拟试穿

**核心变化：放弃迁移 experiment-agent 和 aitryon 的基础设施代码，用 LangGraph 替代手写 Agent 循环，仅迁移虚拟试穿模块。**

| 旧方案（V1） | 新方案（V2） | 理由 |
|------------|-----------|------|
| 迁移 agent_v2.py 的 Function Calling 循环 | 用 LangGraph StateGraph 声明式编排 | 省去 200+ 行手写循环代码，LangGraph 原生支持状态管理、并行分支、重试、可视化 |
| 迁移 llm_client.py | LangChain ChatOpenAI（改 base_url 指向 Model Router） | 一行配置搞定，不用维护自己的 HTTP 客户端 |
| 迁移 memory.py | LangGraph 内置 SqliteSaver checkpointer | 对话记忆由框架管理，无需自己写 SQLite 会话逻辑 |
| 迁移 vector_store.py | ChromaDB 官方 Python SDK + LangChain Embeddings | 直接用 `chromadb.PersistentClient`，更简洁 |
| 迁移 ai_util.py（Qwen-VL 识别） | 在新 Tool 里直接调 ChatOpenAI 传图片 | LangChain 原生支持多模态消息，不需要单独的识别模块 |
| 迁移 ai_tryon.py | **迁移**（唯一保留的迁移项） | DashScope OSS 上传 + 异步轮询流程繁琐，自己重写无意义 |

### 1.1 技术栈对比

```
旧方案:  手写 Agent 循环 → 手写 LLM 客户端 → 手写记忆管理 → 手写向量存储
新方案:  LangGraph 图编排 → ChatOpenAI → SqliteSaver → ChromaDB SDK
         ↑ 框架帮你做的     ↑ 一行配置     ↑ 内置的      ↑ 官方的
```

### 1.2 新项目目录结构

```
glolaunch-ai/
├── backend/
│   ├── main.py                      # FastAPI 入口
│   ├── config.py                    # Pydantic Settings
│   ├── database.py                  # SQLAlchemy
│   │
│   ├── agent/                       # LangGraph Agent（核心）
│   │   ├── state.py                 # AgentState 类型定义
│   │   ├── graph.py                 # LangGraph StateGraph 定义 + 编译
│   │   ├── router.py                # 条件路由：决定下一步走哪个节点
│   │   └── nodes/                   # 每个 Tool 是一个独立节点
│   │       ├── market.py            # 市场洞察节点
│   │       ├── product.py           # 商品属性识别节点
│   │       ├── listing.py           # Listing 生成节点
│   │       ├── images.py            # 商品图生成节点
│   │       ├── tryon.py             # 虚拟试穿节点（迁移自 aitryon）
│   │       ├── video.py             # 视频生成节点
│   │       ├── platform.py          # 多平台适配节点
│   │       └── knowledge.py         # 知识库检索节点
│   │
│   ├── services/                    # 业务服务（被 nodes 调用）
│   │   ├── llm.py                   # ChatOpenAI 实例工厂（统一配置）
│   │   ├── vector_store.py          # ChromaDB 向量存储
│   │   ├── tryon.py                 # 虚拟试穿（迁移自 aitryon/ai_tryon.py）
│   │   └── oss.py                   # 阿里云 OSS
│   │
│   ├── routers/                     # FastAPI 路由
│   │   ├── chat.py                  # POST /chat, POST /chat/stream（SSE）
│   │   ├── products.py              # 商品 CRUD
│   │   ├── listing.py               # Listing 导出
│   │   └── studio.py                # AI 拍摄（试穿 + 商品图）
│   │
│   ├── models/                      # SQLAlchemy ORM
│   │   ├── product.py
│   │   └── listing.py
│   │
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── DashboardView.vue
│   │   │   ├── MarketInsightView.vue
│   │   │   ├── ListingEditorView.vue
│   │   │   ├── PhotoStudioView.vue
│   │   │   └── PublishView.vue
│   │   ├── components/
│   │   │   ├── AgentGraph.vue        # LangGraph 执行图可视化
│   │   │   ├── ChatPanel.vue         # SSE 流式对话
│   │   │   └── TryOnResult.vue
│   │   └── router/index.js
│   ├── vite.config.js
│   └── package.json
│
└── docs/
    ├── product-guide.md
    ├── tech-architecture.md
    └── development-log.md
```

### 1.3 LangGraph Agent 核心代码示意

```python
# agent/state.py
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # 对话历史（自动追加）
    product_id: int | None                    # 当前操作的商品
    market_insights: str                      # 市场洞察结论
    listing_content: dict                     # 生成的 Listing
    generated_images: list[str]               # 生成的商品图 URL
    tryon_result: str | None                  # 虚拟试穿结果图
    video_url: str | None                     # 生成的视频 URL
    platform_packages: list[dict]             # 多平台发布包
    trace: list[dict]                         # 工具调用追踪（前端可视化用）


# agent/graph.py
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

def build_agent():
    graph = StateGraph(AgentState)

    # 添加节点（每个 Tool 是一个节点）
    graph.add_node("analyze_market", market_node)
    graph.add_node("extract_attributes", product_node)
    graph.add_node("generate_listing", listing_node)
    graph.add_node("generate_images", images_node)
    graph.add_node("virtual_tryon", tryon_node)
    graph.add_node("generate_video", video_node)
    graph.add_node("adapt_platform", platform_node)
    graph.add_node("search_knowledge", knowledge_node)
    graph.add_node("respond", respond_node)          # 最终回复

    # 条件路由：LLM 决定下一步走哪个节点
    graph.add_conditional_edges(START, route_next_action)
    graph.add_conditional_edges("analyze_market", route_next_action)
    graph.add_conditional_edges("extract_attributes", route_next_action)
    graph.add_conditional_edges("generate_listing", route_next_action)
    graph.add_conditional_edges("generate_images", route_next_action)
    graph.add_conditional_edges("virtual_tryon", route_next_action)
    graph.add_conditional_edges("generate_video", route_next_action)
    graph.add_conditional_edges("adapt_platform", route_next_action)
    graph.add_conditional_edges("search_knowledge", route_next_action)
    graph.add_edge("respond", END)

    # 编译（带持久化记忆）
    checkpointer = SqliteSaver.from_conn_string("data/checkpoints.db")
    return graph.compile(checkpointer=checkpointer)
```

这个架构的关键优势：每个节点是一个独立函数，只接收 `AgentState`、返回 `dict` 更新状态。不需要自己写 tool_calls 解析、消息追加、迭代控制这些逻辑。

---

## 二、四周开发路线

### Sprint 1（第 1 周）：LangGraph Agent 骨架 + 2 个核心节点

**目标：跑通 "用户对话 → Agent 自主调用 Qwen-VL 分析商品图 → 返回结果" 的最小闭环。**

| 天 | 任务 | 交付物 |
|----|------|--------|
| D1 | 初始化后端项目（FastAPI + LangGraph + ChromaDB）；编写 config.py；配置 `ChatOpenAI(base_url=model_router_url, model="qwen/qwen3.6-plus")` 验证连通性 | 可启动的后端 + LLM 调通 |
| D2 | 定义 AgentState；实现 `graph.py` 骨架（含 router 和 respond 节点）；编写 `product.py` 节点（调 Qwen-VL 提取商品属性） | Agent 图可运行 |
| D3 | 实现 `knowledge.py` 节点（ChromaDB 向量检索）；编写 FastAPI 路由 `/chat` 和 `/chat/stream`（SSE）；前端初始化（Vue 3 + Element Plus） | 对话可触发 Agent |
| D4 | 实现 `market.py` 节点（Qwen3.7-Max 分析 + Qwen3-Rerank 排序）；完善 router 条件路由逻辑 | 3 个节点可用 |
| D5 | 前端 ChatPanel（SSE 流式）+ AgentGraph 组件（节点执行可视化）；端到端联调 | 最小 Demo 可演示 |

**Sprint 1 验收：** 用户在对话中输入"分析这张商品图"并上传图片 → Agent 自动走 router → product_node → respond，前端实时显示图执行过程。

---

### Sprint 2（第 2 周）：Listing + 图片 + 虚拟试穿

**目标：Agent 可自主编排完整的 "分析→文案→拍摄" 工具链。**

| 天 | 任务 | 交付物 |
|----|------|--------|
| D6 | 实现 `listing.py` 节点（Qwen3.6-Plus，多平台模板 prompt） | Listing 文案可生成 |
| D7 | 实现 `images.py` 节点（Wan2.7-Image-Pro 调用 `/v1/images/generations`） | AI 商品图可生成 |
| D8 | 迁移 aitryon 虚拟试穿模块到 `services/tryon.py`；实现 `tryon.py` 节点 | 虚拟试穿可运行 |
| D9 | 实现商品管理 CRUD（上传/列表/详情/删除）；商品数据注入 AgentState | 商品管理打通 |
| D10 | 在 router 中实现"完整上架"多步编排逻辑；测试 3 节点串联调用 | 全链路 Agent 可运行 |

**Sprint 2 验收：** "帮我在 Amazon 上架这款连衣裙"→ Agent 依次执行 extract → market → listing → images → tryon → respond，完整 6 步。

---

### Sprint 3（第 3 周）：前端完整 + 视频 + 多平台

**目标：5 个前端页面全部完成，视频生成和多平台适配上线。**

| 天 | 任务 | 交付物 |
|----|------|--------|
| D11 | MarketInsightView：品类输入 → 趋势图表 + 竞品分析 + 选品推荐 | 市场洞察页面 |
| D12 | ListingEditorView：左右分栏编辑器，多平台/多语言切换，AI 一键优化 | Listing 编辑器 |
| D13 | PhotoStudioView：商品图 → 风格选择 → AI 生成 + 虚拟试穿 → 结果画廊 | AI 拍摄工作台 |
| D14 | 实现 `video.py` 节点（Wan2.7-I2V + Qwen3-TTS）；实现 `platform.py` 节点 | 视频 + 平台适配 |
| D15 | PublishView：多平台发布包预览与导出；AgentGraph 组件完善（展示完整执行图） | 发布页面 + 图可视化 |

**Sprint 3 验收：** 完整产品 Demo 可展示，5 个页面全部可用。

---

### Sprint 4（第 4 周）：打磨 + 提交材料

**目标：稳定 Demo + 全部复赛提交材料产出。**

| 天 | 任务 | 交付物 |
|----|------|--------|
| D16 | 3 个真实场景端到端测试（服装/3C/家居）；Bug 修复 | 稳定 Demo |
| D17 | 体验优化（加载动画、错误兜底、预生成 Demo 数据） | 体验流畅 |
| D18 | 编写 product-guide.md + tech-architecture.md | 两份核心文档 |
| D19 | 录制 3-5 分钟演示视频；编写 development-log.md | 视频 + 开发日志 |
| D20 | GitCode 仓库整理 + README + 测试账号 + 最终提交检查 | 全部材料就绪 |

---

## 三、复赛提交材料对照表

| 提交要求 | 对应产出 | 时间 |
|---------|---------|------|
| 可运行的产品 Demo | 完整 Web 应用（5 页面 + LangGraph Agent） | Sprint 1-3 |
| 产品功能与使用说明 | `docs/product-guide.md` | Sprint 4 D18 |
| 技术架构及调用模型说明 | `docs/tech-architecture.md` | Sprint 4 D18 |
| GitCode 代码仓库 | 整理后的仓库 + README | Sprint 4 D20 |
| 产品演示视频 | 3-5 分钟录屏 | Sprint 4 D19 |
| 测试账号/体验地址 | 预置数据 + 部署地址 | Sprint 4 D20 |
| 项目开发及阶段成果说明 | `docs/development-log.md` | Sprint 4 D19 |

---

## 四、关键技术方案

### 4.1 LangChain + Model Router 对接

```python
# services/llm.py
from langchain_openai import ChatOpenAI
from config import get_settings

def get_llm(model: str = None, temperature: float = 0.7) -> ChatOpenAI:
    s = get_settings()
    return ChatOpenAI(
        model=model or s.model_text_plus,          # "qwen/qwen3.6-plus"
        openai_api_key=s.model_router_api_key,
        openai_api_base=s.model_router_base_url,   # "https://model-router.edu-aliyun.com/v1"
        temperature=temperature,
    )

def get_vl_llm() -> ChatOpenAI:
    """多模态模型（用于图片分析）"""
    return get_llm(model=get_settings().model_vl)

def get_flagship_llm() -> ChatOpenAI:
    """旗舰模型（用于深度分析）"""
    return get_llm(model=get_settings().model_text_flagship, temperature=0.3)
```

一个工厂函数，所有节点通过 `get_llm()` 获取模型实例，model 格式统一为 `qwen/xxx`。

### 4.2 节点实现模式（以 product_node 为例）

```python
# agent/nodes/product.py
from langchain_core.messages import HumanMessage
from services.llm import get_vl_llm

async def product_node(state: AgentState) -> dict:
    """商品属性识别节点"""
    product_image = state.get("product_image_url")
    if not product_image:
        return {"messages": [HumanMessage(content="请先上传商品图片。")]}

    vl_llm = get_vl_llm()
    response = await vl_llm.ainvoke([
        HumanMessage(content=[
            {"type": "image_url", "image_url": {"url": product_image}},
            {"type": "text", "text": PROMPT_EXTRACT_ATTRIBUTES},
        ])
    ])

    attributes = parse_attributes(response.content)
    return {
        "product_attributes": attributes,
        "trace": [{"node": "extract_attributes", "status": "done", "result": attributes}],
    }
```

每个节点就是一个 `async def`，接收 `AgentState`，返回要更新的字段。干净、独立、可测试。

### 4.3 Agent 工具编排策略

| 用户意图 | 图的执行路径 |
|---------|------------|
| "分析夏季连衣裙市场" | START → analyze_market → respond → END |
| "帮我写 Amazon Listing" | START → extract_attributes → generate_listing → respond → END |
| "完整上架这款连衣裙" | START → analyze_market → extract_attributes → generate_listing → generate_images → virtual_tryon → adapt_platform → respond → END |
| "生成 TikTok 短视频" | START → generate_video → respond → END |

router 节点通过 LLM 的 Function Calling 判断下一步走哪个节点，如果没有更多工具需要调用，走 respond → END。

### 4.4 前端 LangGraph 执行图可视化

AgentGraph 组件展示的不仅是工具调用日志，而是 **LangGraph 的图结构本身**——哪些节点被激活、执行顺序、每个节点的输入输出。这比 V1 方案的步骤条更有技术深度，评委可以直观看到 Agent 的"决策路径图"。

实现方式：后端每次执行完一个节点，通过 SSE 推送 `{"type": "node_complete", "node": "generate_listing", "status": "done"}`，前端实时更新图节点的亮显状态。

### 4.5 并行节点（LangGraph 原生支持）

在"完整上架"场景下，`generate_listing`、`generate_images`、`virtual_tryon` 三个节点无数据依赖，可以用 LangGraph 的 fan-out/fan-in 模式并行执行：

```python
graph.add_edge("extract_attributes", "generate_listing")
graph.add_edge("extract_attributes", "generate_images")
graph.add_edge("extract_attributes", "virtual_tryon")
# 三路汇聚
graph.add_edge("generate_listing", "adapt_platform")
graph.add_edge("generate_images", "adapt_platform")
graph.add_edge("virtual_tryon", "adapt_platform")
```

LangGraph 会自动并行执行这三个节点，等全部完成后再进入 adapt_platform。无需手写 asyncio.gather。

---

## 五、依赖对比

| 包 | V1 方案 | V2 方案 |
|---|--------|--------|
| 核心 Agent | 无（手写） | `langgraph>=0.2`, `langchain-openai` |
| LLM 调用 | `httpx`（手写客户端） | `langchain-openai`（ChatOpenAI） |
| 对话记忆 | 手写 SQLite MemoryManager | `langgraph.checkpoint.sqlite` |
| 向量存储 | 手写 ChromaDB 封装 | `chromadb` 官方 SDK |
| 虚拟试穿 | 迁移 aitryon 代码 | 迁移 aitryon 代码（不变） |
| Web 框架 | `fastapi` | `fastapi`（不变） |
| 前端 | Vue 3 + Element Plus | Vue 3 + Element Plus（不变） |

requirements.txt 核心依赖：

```
fastapi>=0.115
uvicorn
sqlalchemy>=2.0
pydantic-settings
langgraph>=0.2
langchain-openai>=0.2
langchain-core>=0.3
chromadb>=0.5
httpx
Pillow
python-jose
bcrypt
```

---

## 六、风险预案

| 风险 | 预案 |
|------|------|
| LangGraph 学习成本 | D1-D2 集中攻克；官方文档 + LangChain Academy 教程；核心概念只有 StateGraph + Node + Edge + Checkpointer |
| Model Router 接口限流 | 关键路径用 Qwen3.6-Flash 兜底；预生成 Demo 素材作为 fallback |
| 虚拟试穿 API 响应慢 | 前端进度动画 + 预生成试穿结果图；Demo 中先展示其他节点 |
| 视频生成不稳定 | 设为可选模块（P1），优先保证文案 + 图片 + 试穿 |
| 前端时间不足 | 优先 ChatPanel + AgentGraph（对话驱动全部功能），其他页面可简化 |
| 部署受限 | 阿里云 ECS 或本地 + ngrok 内网穿透 |

---

## 七、V1 vs V2 总结

| 维度 | V1（手写 Agent + 迁移模块） | V2（LangGraph + 最小迁移） |
|------|--------------------------|-------------------------|
| 代码量 | ~3000 行后端 | ~1800 行后端（-40%） |
| Agent 编排 | 手写循环，自己管状态 | 声明式图，框架管状态 |
| 并行执行 | 手写 asyncio.gather | LangGraph fan-out 原生支持 |
| 可调试性 | 自己打日志 | LangSmith 可视化调试 + 内置 tracing |
| 迁移风险 | 旧代码适配问题多 | 只迁移 1 个文件（ai_tryon.py） |
| Demo 展示 | 步骤条（普通） | 执行图可视化（更专业） |
| 技术叙事 | "我写了一个 Agent" | "我用 LangGraph 构建了多工具 Agent 编排系统" |
