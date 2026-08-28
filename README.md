# GloLaunch AI — 全链路跨境智能上新引擎

> 从一张商品图片到全平台 Listing 上架，AI 自动完成商品理解、市场洞察、爆款文案、视觉素材、合规发布的端到端智能体系统。

**版本**: 3.0.0  
**引擎**: LangGraph StateGraph + Qwen3.8-Max / Qwen3.7-Plus  
**状态**: 生产就绪

---

## 产品简介

GloLaunch AI 是一款面向跨境电商卖家的 AI 全链路智能上新工具。用户只需提供一张商品图片或 1688 链接，系统即可自动完成从商品识别到上架发布的完整流程，将传统 3-7 天的上新周期压缩至 30 分钟。

系统由 LangGraph 状态机驱动，12 个智能节点按条件路由自动编排，支持 SSE 实时推送执行进度，覆盖 Amazon、Shopee、TikTok Shop 三大主流跨境平台。

---

## 核心能力

**多模态商品理解** — 基于 Qwen-VL 多模态模型，从商品图片中自动提取品类、材质、颜色、版型、风格标签、适用场景等结构化属性，替代人工填写。

**出海市场洞察** — 调用旗舰推理模型结合本地 ChromaDB 知识库进行 RAG 增强推理，输出目标市场趋势、建议售价区间、预估毛利率、高转化 SEO 关键词与买家痛点分析。

**上架机会评分** — 6 维加权评估（市场需求、竞争饱和度、利润空间、供应链可得性、合规风险、季节性）商品上架潜力，输出 0-100 分与推荐等级。

**素材盘点与缺口分析** — 自动清点现有素材（原图、场景图、视频），识别缺口并指导后续内容生产优先级。

**爆款对标研究** — 知识库沉淀分品类爆款标题公式与流量词策略，产出定制标题公式、埋词策略、转化钩子，Listing 据此改写而非字面直译。

**爆款化 Listing 撰写** — 注入目标市场洞察与同类爆款标题公式，严格遵循 Amazon A9/COSMO 算法规范，生成高转化、高权重的原生英语 Listing（标题 + 五点描述 + 长描述 + Backend Keywords）。

**AI 商品摄影** — 搬运原素材优先策略，无可用素材时调用 Wan2.7 生成专业场景图。集成虚拟试穿（AITryon）模块，支持服装类商品真人试穿效果合成。

**带货视频自动生产** — 自动生成分镜脚本，TTS 配音合成，ffmpeg 视频剪辑输出。支持商品展示视频与口播带货视频两种模式，无 ffmpeg 时自动降级为故事板模式。

**图片文字本地化** — 对接阿里云电商图片翻译服务，自动识别并替换详情页图片中的中文为英文，保持原有排版风格。未配置时降级为 Qwen-VL 文字识别+翻译方案。

**平台合规质检** — 自动检查 Listing 是否符合目标平台规范（字符限制、违禁词、类目匹配、图片要求），输出合规报告与修改建议。

**Listing 质量评分** — 发布前 8 维质量评估（图片 0.20 / 标题 0.18 / 五点 0.15 / 关键词 0.12 / 属性 0.10 / 描述 0.10 / 合规 0.10 / 类目 0.05），输出 A-F 等级与改进优先级。

**确定性 SKU 生成** — 采用 `GLO-{平台代码}-{品类}-{时间戳}` 格式，保证同一商品在不同节点、不同平台生成一致且唯一的 SKU 标识。

---

## 系统架构

### 整体技术栈

| 层次 | 技术 | 说明 |
|------|------|------|
| Agent 编排 | LangGraph StateGraph | 状态机驱动的多节点 AI 流水线 |
| 语言模型 | Qwen3.8-Max / Qwen3.7-Plus / Qwen3.6-Flash | 阿里云 Token Plan 专属 API |
| 视觉理解 | Qwen3.7-Plus 多模态 | 商品图片结构化属性提取 |
| 图像生成 | Wan2.7-Image-Pro / Wan2.5-I2I | 场景图、白底图、虚拟试穿 |
| 语音合成 | Qwen-Audio-TTS-Plus | 带货视频自动配音 |
| 向量检索 | ChromaDB 本地持久化 | 零外部 API 依赖的轻量 RAG |
| 后端服务 | FastAPI + SSE | 实时流式推送节点执行状态 |
| 前端工作台 | Vue 3 + Vite + Element Plus | 阶段泳道 + 工作流 hub + 深浅双主题 |
| 数据层 | SQLite + ChromaDB | 任务历史持久化 + 向量知识库 |

### LangGraph 执行拓扑（12 节点）

```
START
  │
  ▼
┌─────────────────────┐
│  extract_attributes │  Qwen-VL 多模态      — 多模态视觉商品属性提取
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│   analyze_market    │  Qwen3.8-Max + RAG   — 跨境出海市场洞察与选品评估
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  opportunity_score  │  Intelligence Engine  — 上架机会评分（6维加权）
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│   asset_inventory   │  Asset Analyzer       — 素材盘点与缺口分析
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│   trend_benchmark   │  Qwen3.8-Max + RAG   — 同类爆款标题公式与流量词策略
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│   generate_listing  │  Qwen3.7-Plus         — 爆款化 Listing 智能撰写
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  studio_generation  │  Wan2.7 按需          — AI 商品摄影（搬运优先/AI补给）
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  video_production   │  分镜+TTS+合成        — 带货视频自动生产（可选）
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ image_localization  │  阿里图翻/Qwen-VL     — 图片文字本地化翻译（可选）
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│   adapt_platform    │  Qwen3.6-Flash        — 平台合规质检与适配
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│   publish_package   │  Listing Health       — 发布包组装、质量评分与人工审核
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│       respond       │  LangGraph Core       — 成果汇总打包与自然语言报告
└──────────┬──────────┘
           ▼
          END
```

### 条件路由与意图模式

系统通过 `route_next_step()` 条件路由分发器，根据用户意图自动裁剪执行节点序列：

| 意图 | 说明 | 执行节点 |
|------|------|----------|
| `full_launch` | 全链路上新 | 全部 12 节点 |
| `market_only` | 仅市场洞察 | 属性提取 → 市场分析 → 机会评分 → 汇总 |
| `listing_only` | 仅 Listing 文案 | 属性提取 → Listing 撰写 → 发布包 → 汇总 |

可选节点 `video_production` 和 `image_localization` 支持用户通过前端技能 hub 手动关闭。

---

## 6 大阶段泳道

```
① 商品理解  →  ② 市场洞察  →  ③ 上架决策  →  ④ 爆款对标  →  ⑤ 内容生产  →  ⑥ 合规发布
```

| 阶段 | 包含节点 | 说明 |
|------|----------|------|
| ① 商品理解 | extract_attributes | 解析商品并提取结构化属性 |
| ② 市场洞察 | analyze_market | 出海市场与选品评估 |
| ③ 上架决策 | opportunity_score, asset_inventory | 机会评分与素材缺口分析 |
| ④ 爆款对标 | trend_benchmark | 同类爆款标题公式与流量词策略 |
| ⑤ 内容生产 | generate_listing, studio_generation, video_production, image_localization | Listing 撰写、视觉素材、带货视频与图片本地化 |
| ⑥ 合规发布 | adapt_platform, publish_package, respond | Listing 质检、发布包组装与人工审核 |

---

## 项目目录结构

```
GloLaunch_AI_/
├── backend/
│   ├── app/
│   │   ├── config.py                # Pydantic Settings 配置管理（读取 .env）
│   │   ├── main.py                  # FastAPI 主入口（9 个路由模块）
│   │   ├── agent/
│   │   │   ├── state.py             # AgentState 强类型状态定义
│   │   │   ├── graph.py             # StateGraph 构建与条件路由
│   │   │   ├── pipeline_meta.py     # 节点元数据、阶段分组、ETA 估算
│   │   │   └── nodes/               # 12 个智能节点实现
│   │   │       ├── product.py       # 商品属性提取（多模态 VL）
│   │   │       ├── market.py        # 出海市场洞察（RAG 增强）
│   │   │       ├── opportunity_score.py # 上架机会评分
│   │   │       ├── asset_inventory.py   # 素材盘点与缺口分析
│   │   │       ├── trend.py         # 爆款对标研究
│   │   │       ├── listing.py       # Listing 文案撰写
│   │   │       ├── studio.py        # AI 商品摄影
│   │   │       ├── video.py         # 带货视频生产
│   │   │       ├── localization.py  # 图片文字本地化
│   │   │       ├── platform.py      # 平台合规质检
│   │   │       ├── publish_package.py # 发布包组装与质量评分
│   │   │       └── respond.py       # 成果汇总
│   │   ├── intelligence/
│   │   │   ├── opportunity_scorer.py # 机会评分引擎（6维加权）
│   │   │   └── listing_health.py    # Listing 质量评分引擎（8维加权）
│   │   ├── services/
│   │   │   ├── llm.py               # LLM 统一调用封装
│   │   │   ├── media.py             # 图像生成/TTS 媒体服务
│   │   │   ├── aitryon.py           # 虚拟试穿服务
│   │   │   ├── publisher.py         # 电商平台直连发布
│   │   │   ├── task_store.py        # 任务持久化存储
│   │   │   └── vector_store.py      # ChromaDB 向量知识库
│   │   ├── domain/                  # 领域模型（ListingHealth, Compliance 等）
│   │   └── routers/                 # FastAPI 路由（9 个模块）
│   │       ├── chat.py              # 对话接口（SSE 流式）
│   │       ├── product.py           # 商品管理
│   │       ├── importer.py          # 商品导入（1688/URL/图片）
│   │       ├── tasks.py             # 任务管理
│   │       ├── publish.py           # 发布管理
│   │       ├── batch.py             # 批量操作
│   │       ├── system.py            # 系统状态
│   │       ├── skills.py            # 技能配置
│   │       └── v2.py                # V2 版本接口
│   ├── test_pipeline.py             # 端到端自动化测试
│   ├── .env                         # 环境变量（API 密钥）
│   └── requirements.txt             # Python 依赖清单
│
├── frontend/
│   ├── src/
│   │   ├── App.vue                  # 主页面（四视图切换）
│   │   ├── components/
│   │   │   ├── AgentGraph.vue       # LangGraph 实时节点拓扑可视化
│   │   │   ├── AppSidebar.vue       # 牛顿风格侧边栏导航
│   │   │   ├── WorkflowHub.vue      # 工作流与技能 hub
│   │   │   ├── TaskManager.vue      # 任务管理页
│   │   │   └── Connections.vue      # 连接页（外部服务状态）
│   │   ├── main.js                  # Vue 3 + Element Plus 初始化
│   │   └── theme.css                # 主题样式（深浅双主题）
│   ├── package.json
│   └── vite.config.js
│
├── start.bat                        # Windows 一键启动
├── dev.bat                          # Windows 开发启动
├── QUICKSTART.md                    # 快速启动指南
└── README.md                        # 本文件
```

---

## AI 模型配置

| 模型 | Token Plan 名称 | 主要用途 |
|------|----------------|---------|
| 旗舰推理 | `qwen3.8-max` | 市场洞察、爆款对标、深度分析 |
| 高端多模态 | `qwen3.7-plus` | 视觉识别、Listing 文案撰写 |
| 快速校验 | `qwen3.6-flash` | 平台规则校验、轻量任务 |
| AI 生图 | `wan2.7-image-pro` | 白底主图、海外场景图生成 |
| 图片编辑 | `wan2.5-i2i-preview` | 虚拟试穿合成（异步任务） |
| TTS 配音 | `qwen-audio-3.0-tts-plus` | 带货视频自动配音（音色 `longanhuan_v3.6`） |

**API 接入点**：`https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`

---

## 快速启动

### 环境要求

- Python 3.11+
- Node.js 18+（含 npm）
- 阿里云百炼 Token Plan API Key

### 方式一：双击一键启动（推荐）

```bat
:: 在项目根目录双击运行
start.bat
```

自动检测 Python/Node.js → 安装缺失依赖 → 清理端口占用 → 启动前后端 → 打开浏览器。

### 方式二：手动启动

```powershell
# 1. 安装后端依赖
cd backend
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 MODEL_ROUTER_API_KEY

# 3. 启动后端（端口 8000）
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 4. 新开终端，安装前端依赖
cd frontend
npm install

# 5. 启动前端
npm run dev
```

### 访问地址

- 前端工作台：http://localhost:5174
- 后端 API：http://localhost:8000
- Swagger 文档：http://localhost:8000/docs

---

## 配置说明

编辑 `backend/.env`，主要配置项：

| 配置项 | 说明 | 必填 |
|--------|------|------|
| `MODEL_ROUTER_API_KEY` | 阿里云百炼 Token Plan API Key | 是 |
| `MODEL_ROUTER_BASE_URL` | API 网关地址 | 否（默认百炼 Token Plan） |
| `ALI1688_APP_KEY` | 1688 开放平台 AppKey | 否 |
| `ALI1688_APP_SECRET` | 1688 开放平台 AppSecret | 否 |
| `ALI1688_ACCESS_TOKEN` | 1688 OAuth AccessToken | 否 |
| `AMAZON_SP_API_CLIENT_ID` | Amazon SP API 客户端 ID | 否 |
| `AMAZON_SP_API_CLIENT_SECRET` | Amazon SP API 客户端密钥 | 否 |
| `AMAZON_SP_API_REFRESH_TOKEN` | Amazon SP API 刷新令牌 | 否 |
| `SHOPEE_PARTNER_ID` | Shopee 合作伙伴 ID | 否 |
| `SHOPEE_PARTNER_KEY` | Shopee 合作伙伴密钥 | 否 |
| `JUSTONEAPI_API_KEY` | JustOneAPI 聚合数据密钥 | 否 |
| `ALIMT_ACCESS_KEY_ID` | 阿里云电商图片翻译 AK | 否 |
| `ALIMT_ACCESS_KEY_SECRET` | 阿里云电商图片翻译 SK | 否 |
| `PUBLISH_DRY_RUN` | 发布演练模式（不实际提交） | 否（默认 true） |

未配置的第三方服务会自动降级为备选方案，不影响核心流程运行。

---

## API 接口

### 核心接口：SSE 流式上新

```http
POST /api/chat/stream
Content-Type: application/json

{
  "message": "帮我将这款夏季法式复古碎花连衣裙上架到 Amazon US",
  "product_image_url": "https://example.com/dress.jpg",
  "target_platform": "Amazon",
  "target_market": "US"
}
```

**SSE 事件协议**：

| 事件 | 说明 |
|------|------|
| `plan` | 执行计划：阶段泳道分组 + 各节点预估耗时 |
| `node_start` | 节点开始执行，携带实时进度百分比与剩余 ETA |
| `node_update` | 节点完成，携带实际耗时、产出数据与进度 |
| `complete` | 全链路完成（结果自动存档至任务历史） |
| `error` | 执行异常，可携带 `thread_id` + `resume=true` 断点续跑 |

### 其他接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 健康检查 |
| GET | `/docs` | Swagger 交互式文档 |
| POST | `/api/chat/stream` | SSE 流式上新主接口 |
| GET | `/api/products/demo-presets` | 演示预设商品列表 |
| POST | `/api/products/knowledge/search` | 检索跨境知识库 |
| POST | `/api/products/upload` | 本地商品图上传 |
| POST | `/api/import/1688` | 1688 商品链接解析与搬运 |
| GET | `/api/tasks` | 历史上新任务列表 |
| GET | `/api/tasks/{thread_id}` | 单个任务详情 |
| GET | `/api/tasks/versions` | Listing 版本列表 |
| GET | `/api/tasks/versions/compare` | 两个 Listing 版本对比 |
| POST | `/api/publish` | 平台直连发布 |
| POST | `/api/batch/preview` | 批量上新 CSV 解析预览 |
| POST | `/api/batch/run` | SSE 批量流水线 |

---

## 支持的电商平台

| 平台 | 数据导入 | Listing 文案 | 直连发布 |
|------|----------|--------------|----------|
| Amazon | ✅ | ✅ | ✅（SP API） |
| Shopee | ✅ | ✅ | 🔜（Open API 规划中） |
| TikTok Shop | ✅ | ✅ | 🔜 |
| 1688（供应端） | ✅ | — | — |

未配置平台 API 凭证时，系统自动进入演练模式（Dry Run），生成完整发布包但不实际提交。

---

## 端到端测试

运行自动化管道测试（无需启动 Web 服务）：

```powershell
cd backend
python -X utf8 test_pipeline.py
```

预期输出：

```
============================================================
🚀 测试 GloLaunch AI LangGraph 端到端执行链路
============================================================

▶️ 开始逐步执行节点...
  ✅ [节点完成] extract_attributes   -> 已识别商品，提取面料、风格等 8 项核心视觉属性
  ✅ [节点完成] analyze_market       -> 市场洞察完成：建议定价 $32.99 - $46.99，挖掘 7 个高转化词
  ✅ [节点完成] opportunity_score    -> 上架机会评分完成
  ✅ [节点完成] asset_inventory      -> 素材盘点完成
  ✅ [节点完成] trend_benchmark      -> 爆款对标研究完成
  ✅ [节点完成] generate_listing     -> 已生成符合 Amazon 规范的高转化 Listing
  ✅ [节点完成] studio_generation    -> 已生成白底主图与 3 组海外生活方式场景图
  ✅ [节点完成] video_production     -> 带货视频生产完成
  ✅ [节点完成] image_localization   -> 图片文字本地化完成
  ✅ [节点完成] adapt_platform       -> 已完成 Amazon 平台合规质检
  ✅ [节点完成] publish_package      -> 发布包组装完成，Listing 质量评分 B 级
  ✅ [节点完成] respond              -> Agent 编排任务完成

🎉 全链路 12 节点执行完毕
```

---

## 开发说明

### 添加新节点

1. 在 `backend/app/agent/nodes/` 下创建节点文件
2. 实现 `async def xxx_node(state: AgentState) -> Dict[str, Any]` 函数
3. 在 `graph.py` 中注册节点并更新 `route_next_step()` 路由逻辑
4. 在 `pipeline_meta.py` 的 `PIPELINE_NODES` 中添加节点元数据（名称、阶段、ETA）
5. 在 `INTENT_PIPEELINES` 中将节点加入对应意图的节点序列

### 扩展新平台

1. 在 `config.py` 中添加平台 API 凭证配置
2. 在 `platform.py` 中实现平台合规规则
3. 在 SKU 生成映射表中添加平台代码（`Amazon→AMZ`, `Shopee→SPE`, `TikTok→TTK`）

### 模型切换

所有模型名称通过 `config.py` 配置，支持热切换：

```python
model_text_flagship: str = "qwen3.8-max"   # 旗舰推理
model_text_plus: str = "qwen3.7-plus"      # 多模态文案
model_text_flash: str = "qwen3.6-flash"    # 快速校验
model_vl: str = "qwen3.7-plus"             # 视觉理解
model_image: str = "wan2.7-image-pro"      # 图像生成
```

---

## 依赖清单

### 后端（Python）

```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
langgraph>=0.2.0
langchain>=0.3.0
langchain-openai>=0.2.0
chromadb>=0.5.0
pydantic-settings>=2.2.0
sse-starlette>=2.0.0
httpx>=0.27.0
Pillow>=10.0.0
```

### 前端（Node.js）

```
vue ^3.5.0
element-plus ^2.8.0
@element-plus/icons-vue ^2.3.1
axios ^1.7.0
vite ^5.4.0
```

---

## 开发路线图

### ✅ 已完成（Phase 1-3）

- LangGraph 12 节点状态机编排 + 条件路由（3 种意图模式）
- Qwen3.8-Max / Qwen3.7-Plus / Qwen3.6-Flash 三模型差异化调用
- 多模态视觉商品属性提取（全品类自适应 Schema）
- ChromaDB 本地向量知识库 + RAG 增强推理
- 上架机会评分引擎（6 维加权）
- 素材盘点与缺口分析
- 爆款对标 RAG（分品类标题公式与流量词策略）
- 多平台 Listing 智能撰写（Amazon A9/COSMO 规范）
- AI 商品摄影（搬运优先 / Wan2.7 按需补给 / 虚拟试穿）
- 带货视频自动生产（分镜 + TTS 配音 + ffmpeg 合成）
- 图片文字本地化（阿里云图翻优先 / Qwen-VL 降级）
- 平台合规质检与发布包组装
- Listing 质量评分引擎（8 维加权，A-F 等级）
- 确定性 SKU 生成（跨节点一致性保证）
- FastAPI SSE 实时进度推送（plan / node_start / node_update 事件协议）
- LangGraph MemorySaver Checkpointer（断点续跑与多轮续话）
- Vue 3 全链路可视化工作台（阶段泳道 + 进度条 + 节点拓扑）
- 1688 一键搬运（链接解析 → 智能推荐平台 → 零手填上新）
- 多商品批量上新（CSV 导入 + SSE 批量流水线）
- Listing 版本管理与对比
- SQLite 任务历史持久化
- 端到端自动化测试

### 🔜 规划中（Phase 4）

- Shopee Open Platform 真实上架通道
- 多语言批量本地化（欧区多语种：德/法/西/意）
- 视频生成升级为真实 AI 视频模型（图生视频）

---

## 许可证

MIT License © 2026 GloLaunch AI Team

---

<p align="center">
  <strong>GloLaunch AI</strong> — 让跨境上新像发朋友圈一样简单
</p>
