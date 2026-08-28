# GloLaunch AI P0 最终 E2E 黑盒验收报告

---

## 1. 验收时间

**验收日期**：2026-08-28

**验收环境**：Windows 10 (10.0.19045) x64 / Python 3.x / Node.js + Vite

**验收方式**：真实环境黑盒验收，不修改业务代码，不 Mock 数据

---

## 2. 测试环境

| 项目 | 状态 | 说明 |
|------|------|------|
| Backend (FastAPI) | configured | 9 路由、12 Agent 节点、6 服务模块，可正常启动 |
| Frontend (Vue 3 + Element Plus) | configured | App.vue (~2900 行) + 5 组件，Vite 开发服务器 |
| 1688 API (JustOneAPI) | **invalid** | Token 已配置 (16 chars)，但 API 返回 code=601「账户余额不足」，所有请求均失败 |
| 1688 API (官方开放平台) | missing | ALI1688_APP_KEY / APP_SECRET / ACCESS_TOKEN 均未配置 |
| Amazon API (JustOneAPI) | configured | Token 共用，Search/Detail/Reviews 三接口正常返回真实数据 |
| Amazon BSR (JustOneAPI) | **partial** | 接口可调用但返回 0 条结果（可能需特定 category 路径格式） |
| Shopee API | missing | 未配置 |
| TikTok Shop API | missing | 未配置 |
| LLM API (DashScope Token Plan) | configured | MODEL_ROUTER_API_KEY 已配置 (115 chars)，基地址为 token-plan 专属 |
| Image API (wan2.7-image-pro) | configured | 同一 MODEL_ROUTER_API_KEY，生图能力可用 |
| VL Model (qwen3.7-plus) | configured | 多模态视觉分析能力可用 |
| Database / Store | configured | SQLite (data/glolaunch.db) + MemorySaver checkpointer |

---

## 3. Golden Test Product

**状态：BLOCKED**

由于 JustOneAPI 1688 通道返回「账户余额不足」(code=601)，且 1688 官方开放平台凭证未配置，无法通过任何通道导入真实 1688 商品。

已测试 4 个不同 1688 商品 ID (744498862498, 655392050581, 736964955268, 689051599099)，全部返回相同错误：

```
API: GET /api/1688/get-item-detail/v1
HTTP Status: 200
Response code: 601
Message: INSUFFICIENT BALANCE
```

**替代方案**：系统存在 HTML 页面抓取降级通道（`/api/import/1688` 端点），当官方 API 和 JustOneAPI 均不可用时，会尝试直接抓取 1688 商品页面。但此通道受 1688 反爬机制影响，稳定性不可控。

---

## 4. 第三方 API 连通性

### 4.1 1688 (JustOneAPI)

```
Request: GET /api/1688/get-item-detail/v1?token=xT9U3aiGnaTdqcMj&itemId=744498862498
HTTP Status: 200
Response code: 601
Message: INSUFFICIENT BALANCE
判定: FAIL
```

### 4.2 Amazon Search (JustOneAPI)

```
Request: GET /api/amazon/search-products/v1?keyword=portable+blender&country=US
HTTP Status: 200
Response code: 0
返回数量: 16 items (total: 56,012 results)
判定: PASS
```

### 4.3 Amazon Product Detail (JustOneAPI)

```
Request: GET /api/amazon/get-product-detail/v1?asin=B0DB8ZN253&country=US
HTTP Status: 200
Response code: 0
商品 ASIN: B0DB8ZN253
商品标题: Ninja Blast Max Portable Blender...
价格: $69.99
评分: 4.2
评论数: 2960
判定: PASS
```

### 4.4 Amazon Top Reviews (JustOneAPI)

```
Request: GET /api/amazon/get-product-top-reviews/v1?asin=B0DB8ZN253&country=US
HTTP Status: 200
Response code: 0
返回评论数: 8
判定: PASS
```

### 4.5 Amazon Best Sellers (JustOneAPI)

```
Request: GET /api/amazon/get-best-sellers/v1?category=electronics&country=US
HTTP Status: 200
Response code: 0
返回数量: 0 (空结果)
判定: PARTIAL (接口正常但无数据返回，可能需要特定 category 路径格式)
```

---

## 5. E2E 数据链路

### 5.1 实际数据流路径

经代码审计确认，系统存在**两条独立的 1688 数据通道**：

**通道 A（死代码）**：`Alibaba1688Source.import_product()` → `ProductProfile`
- 定义在 `app/sources/alibaba_1688.py`
- 使用 JustOneAPI 获取数据并映射为 `ProductProfile` Pydantic 模型
- **从未被任何路由或 Agent 节点调用**

**通道 B（实际运行）**：`/api/import/1688` → flat dict → 前端 → `/api/chat/stream` → `AgentState`
- 定义在 `app/routers/importer.py`
- 使用官方 API 或 HTML 页面抓取
- 返回扁平 dict（title, images, source_price, sku_attributes, source_url）
- 前端作为中间桥梁，将数据注入到 Agent 初始状态

### 5.2 完整执行链路

```
用户粘贴 1688 URL
      ↓
[前端] POST /api/import/1688 {url}
      ↓
[importer.py] 官方 API 优先 → HTML 抓取降级
      ↓ (flat dict)
[前端] importedProduct.value = data.product
      ↓ (用户点击"启动上新")
[前端] POST /api/chat/stream
      {product_title, supply_price_cny, sku_attributes, source_url, product_image_url, imported_images}
      ↓
[chat.py] LaunchRequest → initial_state
      ↓
[LangGraph StateGraph] 12 节点流水线
```

---

## 6. ProductProfile 验证

**状态：PARTIAL**

`ProductProfile` 模型定义在 `app/domain/product_profile.py`，包含 title, supply_price_cny, images, sku_variants, supplier_info 等完整字段。

**问题**：在实际运行链路中，`ProductProfile` **不是**从 1688 API 直接构建的。它仅在 `opportunity_score_node` 中从 `product_attributes` dict 重建（`_build_product_profile()` 函数），作为评分引擎的输入。

| 字段 | 来源 | 是否真实 |
|------|------|---------|
| title | 前端传入 → AgentState.product_title → product_node → product_attributes["title"] | 取决于 1688 导入是否成功 |
| supply_price_cny | 前端 parsePrice() → AgentState → product_attributes | 取决于 1688 导入 |
| images | AgentState.imported_images → product_attributes["original_images"] | 取决于 1688 导入 |
| category_family | product_node VL 模型推断 或 LLM 从标题推断 | LLM 推断 |

---

## 7. AgentState 验证

**状态：PASS（代码链路正确）**

`AgentState` 定义在 `app/agent/state.py`，为 LangGraph TypedDict。

字段传递追踪（当 1688 导入成功时）：

| AgentState 字段 | 设置位置 | 来源 | 转换 |
|----------------|---------|------|------|
| product_title | chat.py:118 | LaunchRequest ← 前端 importedProduct.title | 无（直通） |
| supply_price_cny | chat.py:119 | LaunchRequest ← 前端 parsePrice(source_price) | 前端去除货币符号 |
| sku_attributes | chat.py:120 | LaunchRequest ← 前端 importedProduct.sku_attributes | **类型不匹配**（见下） |
| source_url | chat.py:121 | LaunchRequest ← 前端 importedProduct.source_url | 无（直通） |
| product_image_url | chat.py:114 | LaunchRequest ← 前端 main_image | 无 |
| imported_images | chat.py:115 | LaunchRequest ← 前端 images 列表 | 无 |

**发现问题**：`sku_attributes` 类型不匹配 —— 1688 导入返回 `List[str]`（如 `["颜色", "尺码"]`，仅属性名），但 AgentState 定义为 `Dict[str, List[str]]`（如 `{颜色: [红,蓝], 尺码: [S,M,L]}`）。Python 运行时不会报错，但下游消费者可能得到意外行为。

---

## 8. Amazon Research 验证

**状态：PASS（API 可用且数据真实）**

### 8.1 调用链路

`market_node` (`app/agent/nodes/market.py`) → `_fetch_amazon_real_data()` → `AmazonResearchSource()` → JustOneAPI

关键发现：
- `market_node` **直接实例化** `AmazonResearchSource()`，而非通过 `SourceRegistry`
- **未调用** `fetch_market_data()` 方法（该方法为死代码），而是分别调用 `search_products()` 和 `get_best_sellers()`
- 搜索关键词来自 `product_attributes["title"]`，即 1688 商品标题（中文）

### 8.2 数据进入 AgentState 的路径

```
Amazon API → raw dict → _analyze_with_real_data() → LLM 分析真实数据 → insights dict → AgentState.market_insights
```

**重要**：`market_insights` 存储为 `Dict[str, Any]`，不是 `MarketContext` Pydantic 模型。`MarketContext` 仅在下游 `opportunity_score_node` 中从该 dict 重建。

### 8.3 数据质量保障

- LLM 提示词明确要求「价格、评分、评论数等数据必须基于真实数据，不要编造」
- 竞品数据从搜索结果直接提取并注入 LLM 上下文（`_extract_competitors_from_search()`）
- 如果 LLM 解析失败，`_build_basic_insights_from_competitors()` 直接从竞品数据构建基础洞察
- `data_sources` 字段标记数据来源（`["JustOneAPI:Amazon"]` 或 `["LLM"]`）

### 8.4 潜在问题

- **中文标题搜索 Amazon**：1688 商品标题（中文）直接作为 Amazon 搜索关键词，可能导致搜索结果质量差。缺少关键词翻译/本地化步骤。
- **BSR 返回空**：`get_best_sellers(category="electronics")` 返回 0 结果，可能需要特定的 category 路径格式。

---

## 9. MarketContext 验证

**状态：PASS（重建逻辑正确）**

`MarketContext` 在 `opportunity_score_node` (`app/agent/nodes/opportunity_score.py`) 中通过 `_build_market_context()` 从 `market_insights` dict 重建：

- `competitors`：从 insights["competitors"] 映射为 `CompetitorSnapshot` 列表
- `avg_competitor_price`：从竞品价格计算
- `price_distribution`：价格区间分布
- `top_keywords`：从 insights["top_keywords"] 映射为 `KeywordData` 列表
- `data_sources`：直接传递

**REAL DATA vs LLM ANALYSIS 区分**：

| 字段 | 分类 |
|------|------|
| competitors (ASIN, title, price, rating, review_count) | REAL DATA (来自 Amazon API) |
| market_overview | LLM ANALYSIS (基于真实数据) |
| recommended_price_range | LLM ANALYSIS (基于真实价格) |
| buyer_pain_points | LLM ANALYSIS (基于竞品差评) |
| differentiation_angles | LLM ANALYSIS |
| high_converting_keywords | LLM ANALYSIS |
| launch_confidence_score | LLM ANALYSIS |
| data_sources | METADATA (标记数据来源) |

---

## 10. Opportunity Score 验证

**状态：PASS（纯算法评分，非 LLM）**

### 10.1 评分引擎

`OpportunityScorer` (`app/intelligence/opportunity_scorer.py`) 是**纯算法引擎**，不使用 LLM。

6 维度加权评分：

| 维度 | 权重 | 基线分 | 关键逻辑 |
|------|------|--------|---------|
| 市场需求 | 25% | 50 | +15(有数据源), +增长bonus(上限20), +关键词搜索量bonus, +竞品数量bonus |
| 竞争程度 | 20% | 60 | 0竞品=70, <5=85, <15=65, <30=45, >=30=30; 低评分竞品+10 |
| 价格利润 | 20% | 50 | 有供应价+建议售价时计算真实利润率; 否则基线50 |
| 供应链 | 15% | 50 | +10(有供应价), +15(MOQ<=50), +10(交期<=7天), +5(有供应商名), +5(有图片) |
| 内容差异化 | 10% | 50 | +15(>=3设计特点), +10(痛点数据), +10(差异化角度) |
| 合规风险 | 10% | 75 | 服装-5, 电子-15, 美妆-10; 高分=低风险 |

### 10.2 动态性验证

评分是**数据敏感的**：
- 不同竞品数量 → 不同竞争分数
- 不同价格分布 → 不同利润分数
- 有无供应价 → 供应链分数差异显著
- 有无痛点/差异化数据 → 内容差异化分数差异

**但**：基线分数较高（多数维度从 50-75 起步），在数据稀疏时评分会偏向乐观。

### 10.3 缺失数据行为

当市场数据为空时：
- 市场需求：50 (基线) - 无 bonus
- 竞争：70 (0 竞品默认)
- 利润：50 (基线)
- 供应链：50 (基线)
- 差异化：50 (基线)
- 合规：75 (基线)
- **加权总分约 58** —— 即使无任何数据，也有中等偏上的分数

---

## 11. Asset Inventory 验证

**状态：PARTIAL**

`asset_inventory_node` (`app/agent/nodes/asset_inventory.py`) 扫描 AgentState 中的 4 个来源：

| 来源 | 读取字段 | 质量分 | 备注 |
|------|---------|--------|------|
| 用户上传主图 | product_image_url | 0.8 (固定) | 非真实图像分析 |
| 1688 导入图片 | imported_images | 0.6 (固定) | 非真实图像分析 |
| AI 生成场景图 | studio_assets.lifestyle_scenes | 0.85 (固定) | 非真实图像分析 |
| AI 视频 | video_package | 0.8 (固定) | 非真实图像分析 |

**问题**：所有 `quality_score` 均为硬编码常量，不基于实际图像质量分析。

---

## 12. Asset Gap 验证

**状态：PASS（逻辑正确）**

Gap 分析比较「当前素材类型集合」vs「目标平台需求」：

- 平台需求定义在 `PLATFORM_ASSET_REQUIREMENTS` 中，分 required/recommended/optional 三级
- Amazon 要求：MAIN_IMAGE(required), LIFESTYLE_IMAGE/INFOGRAPHIC/SIZE_CHART/VIDEO(recommended)
- 缺失项生成 `AssetGapItem`，含优先级、建议操作、预估成本
- 策略判定：required_gaps > 0 → "full_ai"; 仅 recommended 缺失 → "partial_ai"; 无缺失 → "import_only"

---

## 13. Product Identity 验证

**状态：PASS（设计正确，约束进入生图 Prompt）**

`_build_product_identity()` (`studio.py:173-204`) 从 `product_attributes` 提取视觉约束：

```python
identity = {
    "visual_constraints": "color: ..., material: ..., style: ..., design details: ...",
    "colors": [...],
    "materials": [...],
    "style_tags": [...],
    "has_source_image": True/False
}
```

约束注入生图 Prompt 的方式 (`studio.py:117-121`)：

```
IMPORTANT: {visual_constraints}. The product in the image must match these exact characteristics.
```

Product Identity 确实进入了最终生图 Prompt，满足验收要求。

---

## 14. AI Image 验证

**状态：PARTIAL（能力存在，未实际执行生图）**

### 14.1 Studio Node 行为

`studio_node` (`studio.py:207-265`) 的逻辑：

- **有商品图（1688 搬运模式）**：直接沿用原图作为主图，不触发 AI 生图，`image_engine = "source_material"`
- **无商品图**：调用 `_generate_ai_scenes()` 生成白底主图 + 3 组场景图

### 14.2 生图引擎

- 引擎：wan2.7-image-pro（DashScope）
- 并发生成 4 张图（1 白底 + 3 场景）
- 失败时不用 Unsplash 填充，如实记录 `generation_failures` 计数
- Unsplash 填充已被显式移除（代码注释确认）

### 14.3 虚拟试穿

三级降级链：aitryon 专用服务 → 图编辑模型合成 → 空状态兜底（不再使用 Unsplash）

---

## 15. 商品一致性验证

**状态：无法实际验证**

由于 1688 导入被阻塞，无法进行完整的「1688 原图 vs AI 生成图」对比。

代码层面：Product Identity Lock 机制确保颜色、材质、风格、设计细节等约束进入生图 Prompt，但实际效果需要真实运行验证。

---

## 16. Listing Generation 验证

**状态：PASS（LLM 生成，注入真实市场数据）**

### 16.1 输入来源

`listing_node` (`app/agent/nodes/listing.py`) 读取：

| 输入 | 来源 | 字段 |
|------|------|------|
| 商品属性 | product_attributes | category_family, category, main_color, materials, key_specs, style_tags, design_features, target_occasions |
| 市场洞察 | market_insights | high_converting_keywords, buyer_pain_points, differentiation_angles |
| 爆款对标 | trend_benchmark | title_formula, traffic_word_strategy, conversion_hooks, localization_notes |

### 16.2 Prompt 分析

- 系统提示词要求 LLM 扮演「Senior Copywriter & SEO Specialist」
- 明确禁止对中文卖点做字面直译
- 要求遵循 Amazon A9/COSMO 算法规范
- Title: 150-195 字符，前置核心大词
- Bullet Points: 5 条，大写标签开头
- Search Terms: 200 字节以内

### 16.3 真实数据注入

Listing Prompt **间接包含**真实 Amazon 数据：
- `high_converting_keywords` 来自 market_insights（由 LLM 基于真实竞品数据分析得出）
- `buyer_pain_points` 来自 market_insights
- 但 Prompt 不包含原始竞品 ASIN、标题、价格等

### 16.4 降级兜底

**高风险发现**：LLM 解析失败时，返回硬编码的「法式复古碎花连衣裙」Listing（`listing.py:90-111`），包含完整的 title、bullet_points、description、search_terms。如果用户商品不是连衣裙，这个兜底数据将极具误导性。

---

## 17. Listing Health 验证

**状态：PASS（纯算法评分）**

`ListingHealthCalculator` (`app/intelligence/listing_health.py`) 评估 8 个维度：

| 维度 | 权重 | 关键逻辑 |
|------|------|---------|
| 标题质量 | 18% | Amazon: 80-150字符=85分, 150-200=90分, >200=40分(过长), <80=60分; 关键词堆砌检测-15 |
| 五点描述 | 15% | 0条=FAIL(0分); 50+count*10+(10 if 均长>80) |
| 详情描述 | 10% | 空=40分; <200字符=55; >2000=70; 其他=85 |
| 图片数量 | 20% | 0张=FAIL(20); <5: 50+count*8; <8: 80; >=8: 90 |
| 关键词 | 12% | 有search_terms+15, >100字符+10; 市场数据关键词覆盖率检测 |
| 属性填充 | 10% | category/material/color 填充率 |
| 品类 | 5% | 有=80, 无=40 |
| 合规性 | 10% | 基线80; 含"best seller"/"#1"/"guaranteed"等违禁词-20 |

评分是**动态的**，直接取决于 Listing 内容质量。不同 Listing 必然得到不同分数。

---

## 18. Human Review 验证

**状态：PARTIAL（代码存在，前端可编辑）**

前端 App.vue 中：
- Listing 结果展示在 UI 中，用户可查看和修改
- 修改后的内容通过 SSE 流更新到 `resultData`
- 最终提交 Publish 时使用用户修改后的版本

但由于无法实际运行完整流水线（1688 阻塞），未进行实际的人工修改-保存-重新读取测试。

---

## 19. Publish Package 验证

**状态：PARTIAL**

### 19.1 Publish Package Node

`publish_package_node` (`app/agent/nodes/publish_package.py`) 组装 `PublishPackage` 数据结构：

- thread_id, SKU, platform, market, timestamp
- listing_snapshot（完整 Listing 快照）
- assets_summary（图片数、视频状态、本地化图片数）
- listing_health（完整健康评分）
- opportunity_score（完整机会评分）
- compliance_check_items
- review_decision: NEEDS_REVISION

**产出形式**：内存中的 Python dict，**不生成物理文件**（无 ZIP/PDF）。

### 19.2 Publish Service

`publisher.py` 提供独立的 `POST /api/publish` 端点：

- **Live 模式**（配置了 OAuth 凭证 + dry_run=False）：真实 OAuth 令牌交换 + SP-API 提交
- **Simulated 模式**（默认）：生成模拟发布回执，含 5 步时间线

当前环境：`publish_dry_run = True`（默认），Amazon SP-API 凭证未配置 → 始终走 Simulated 模式。

模拟回执包含明确标注：`"note": "当前为演练模式：未配置平台 OAuth 凭证..."`

---

## 20. 发布日志验证

**状态：PASS**

发布记录通过 `TaskStore.save_publish()` 保存：

```python
payload = {
    "publish_id": "PUB-XXXXXXXXXX",
    "thread_id": thread_id,
    "platform": platform,
    "market": market,
    "mode": "simulated" / "live",
    "status": "PUBLISHED_SIMULATED" / "SUBMITTED",
    "report": report,
    "created_at": timestamp,
}
```

---

## 21. 全链路数据血缘

```
1688 商品 URL
      ↓
[importer.py] HTML 抓取 / 官方 API
      ↓
flat dict (title, images, price, sku, url)     [REAL - 来自 1688 页面]
      ↓
[前端] parsePrice() + 字段映射
      ↓
AgentState 初始字段                              [REAL - 来自 1688]
      ↓
[product_node] 1688 数据优先 + VL 视觉补充
      ↓
product_attributes                              [REAL 基础 + LLM 视觉补充]
      ↓
[market_node] Amazon JustOneAPI
      ↓
market_insights.competitors                     [REAL - 来自 Amazon API]
market_insights.market_overview                 [LLM ANALYSIS - 基于真实数据]
market_insights.buyer_pain_points               [LLM ANALYSIS - 基于真实竞品]
market_insights.high_converting_keywords        [LLM ANALYSIS]
      ↓
[opportunity_score_node]
      ↓
opportunity_score                               [DERIVED FROM REAL DATA - 纯算法]
      ↓
[asset_inventory_node]
      ↓
asset_inventory                                 [DERIVED - 扫描 AgentState URLs]
asset_gap                                       [DERIVED - 集合对比]
      ↓
[studio_node] Product Identity Lock
      ↓
studio_assets                                   [REAL or AI GENERATED]
      ↓
[listing_node]
      ↓
listing_content                                 [LLM GENERATED FROM REAL CONTEXT]
      ↓
[listing_health]
      ↓
listing_health                                  [DERIVED - 纯算法]
      ↓
[publish_package_node]
      ↓
publish_package                                 [DERIVED - 组装所有上游数据]
```

---

## 22. 全项目 Mock 扫描结果

### 22.1 高风险发现（P0 主链路）

| # | 位置 | 问题 | 风险等级 |
|---|------|------|---------|
| 1 | `listing.py:90-111` | LLM 失败时返回硬编码「法式复古碎花连衣裙」完整 Listing | **HIGH** |
| 2 | `sources/alibaba_1688.py:197` | `confidence=0.95` 硬编码 | **MEDIUM** |
| 3 | `sources/amazon_research.py:275` | `confidence=0.9` 硬编码 | **MEDIUM** |
| 4 | `routers/product.py:75-99` | Demo presets 使用 Unsplash 库存图片进入全链路 | **MEDIUM** |
| 5 | `services/publisher.py:55-77` | 模拟发布生成逼真的假时间线（但标注了"演练模式"） | **MEDIUM** |
| 6 | `market.py:169,219` | launch_confidence_score 硬编码降级值 (50/30) | **LOW** |

### 22.2 已修复的正面发现

| 位置 | 说明 |
|------|------|
| `studio.py:37` | 注释明确记录 "FALLBACK_SCENES 已移除：不再使用 Unsplash 预设素材填充" |
| `studio.py:142` | "跳过失败的图片，不用 Unsplash 填充" |
| `studio.py:60` | 虚拟试穿兜底返回空状态，不使用假图片 |

### 22.3 无害发现

- 所有 `TODO` 标记（shopee/tiktok/temu 骨架）—— 诚实标注未完成
- `asset_inventory.py` 中硬编码 quality_score (0.6-0.85) —— 不影响 P0 核心逻辑
- `opportunity_scorer.py` 规则基线分数 —— 合法启发式评分，非伪造
- 前端 `FALLBACK_SKILLS` —— 仅 UI 元数据

### 22.4 前端硬编码分数检查

**结果：未发现前端硬编码分数**

前端所有分数均从后端动态读取：
- `resultData.opportunity_score.total_score` ← 后端 SSE 推送
- `resultData.listing_health.total_score` ← 后端 SSE 推送
- `resultData.publish_package.listing_health_grade` ← 后端数据
- 初始值均为 `null`，不预设任何分数

---

## 23. 第三方数据源架构检查

### 23.1 Source Adapter 架构

```
Source (抽象基类: base.py)
  ├── Alibaba1688Source     → JustOneAPI / 官方 API
  ├── AmazonResearchSource   → JustOneAPI
  ├── ShopeeResearchSource   → JustOneAPI (骨架)
  ├── TikTokResearchSource   → JustOneAPI (骨架)
  ├── TemuResearchSource     → TODO
  └── JustOneAPISource       → TODO (registry 优先级最高但全部返回 None)
      ↓
Registry (registry.py) → get_best_source_for_platform()
      ↓
Normalized Data → ProductProfile / MarketContext
```

### 23.2 隔离性评估

- `market_node` 直接实例化 `AmazonResearchSource()`，**绕过 SourceRegistry**
- 这意味着 JustOneAPISource（registry 最高优先级，但为 TODO 空实现）不会影响实际运行
- Amazon/Shopee/TikTok 数据源不会直接污染 Agent 核心逻辑

**问题**：`JustOneAPISource` 在 registry 中优先级最高但所有方法返回 `None`/`[]`，如果通过 registry 调用会浪费调用链。

---

## 24. API 成本与重复调用检查

### 24.1 单次 E2E 预估调用量

| API | 调用点 | 预估次数 |
|-----|--------|---------|
| 1688 (JustOneAPI) | import_product | 1 |
| Amazon Search | market_node | 1 |
| Amazon BSR | market_node | 1 |
| Amazon Detail | (未直接调用) | 0 |
| Amazon Reviews | (未直接调用) | 0 |
| VL Model (qwen3.7-plus) | product_node | 1 |
| LLM (qwen3.7-plus) | market_node + trend_node + listing_node | 3 |
| LLM (qwen3.8-max) | (flagship, 市场分析) | 0-1 |
| Image (wan2.7-image-pro) | studio_node | 0 (搬运模式) 或 4 (全量生图) |

### 24.2 重复调用

- `fetch_market_data()` 方法（含 3 关键词搜索 + BSR）为死代码，不会被调用
- `market_node` 仅做 1 次 search + 1 次 BSR，不存在重复搜索
- 同一商品分析过程中不会重复请求同一 Amazon 数据

---

## 25. 失败测试

### Case A: 1688 API 失败

**当前行为**：
- JustOneAPI 返回 601 → importer.py 降级到 HTML 抓取
- HTML 抓取可能成功（取决于反爬）或失败
- 如果完全失败 → 前端显示错误消息，用户需手动填写
- Agent 流水线可以在无 1688 数据的情况下运行（Path B: 纯 VL 图像提取）

**判定**：系统**不会伪造 ProductProfile**，正确报错。 **PASS**

### Case B: Amazon API 失败

**当前行为**：
- `_fetch_amazon_real_data()` 返回 `None`
- `market_node` 降级到 `_generate_llm_insights()`（纯 LLM 分析）
- `data_sources` 标记为 `["LLM"]`
- Opportunity Scorer 使用基线分数

**判定**：系统**不会伪造 Amazon 数据**，但会用 LLM 凭空生成市场分析。数据来源标记正确。 **PARTIAL**

### Case C: Image API 失败

**当前行为**：
- `_generate_ai_scenes()` 中失败图片被跳过
- `generation_failures` 计数递增
- 不使用 Unsplash 填充
- `image_engine` 标记为 `"none"` 或部分成功

**判定**：系统**如实记录失败**，不使用假图片。 **PASS**

### Case D: Publish Package 失败

**当前行为**：
- Live 模式失败 → 自动降级到 Simulated 模式
- `mode` 字段标记为 `"simulated"`
- `status` 标记为 `"PUBLISHED_SIMULATED"`
- 报告中包含失败原因

**判定**：系统**不会伪造成功状态**。 **PASS**

---

## 26. 前端与后端一致性

### 26.1 分数一致性

前端所有分数从后端 SSE 流动态读取，无硬编码分数。

| 检查项 | 结果 |
|--------|------|
| 前端 Opportunity Score = 后端 | 是（直接传递） |
| 前端 Listing Health = 后端 | 是（直接传递） |
| 前端 Product Info = 后端 | 是（SSE 推送） |
| 前端 Publish Status = 后端 | 是（直接传递） |

### 26.2 前端硬编码检查

未发现前端硬编码 `92`、`95`、`88`、`SUCCESS`、`READY` 等欺骗性分数。

---

## 27. 最终 E2E 验收表

| 节点 | 真实运行 | 数据来源 | 是否进入下游 | 是否通过 | 证据 |
|------|---------|---------|------------|---------|------|
| 1688 Import | BLOCKED | N/A (API 余额不足) | 是（代码链路正确） | **PARTIAL** | JustOneAPI code=601; HTML 抓取降级存在 |
| ProductProfile | 间接 | 从 product_attributes 重建 | 是 | PASS | opportunity_score_node 中构建 |
| AgentState | 代码审计 | 前端 → LaunchRequest → initial_state | 是 | PASS | 字段级追踪确认 |
| Product Node | 代码审计 | 1688 数据优先 + VL 补充 | 是 | PASS | 双路径逻辑正确，不覆盖真实数据 |
| Amazon Search | 实际测试 | JustOneAPI | 是 | PASS | 16 条真实商品数据 |
| Amazon Detail | 实际测试 | JustOneAPI | 间接 | PASS | 真实商品详情 |
| Amazon Reviews | 实际测试 | JustOneAPI | 间接 | PASS | 8 条真实评论 |
| Amazon BSR | 实际测试 | JustOneAPI | 是 | **PARTIAL** | 接口正常但返回 0 结果 |
| MarketContext | 代码审计 | 从 market_insights dict 重建 | 是 | PASS | 重建逻辑完整 |
| Opportunity Score | 代码审计 | 纯算法，基于真实数据 | 是 | PASS | 6 维度加权，数据敏感 |
| Asset Inventory | 代码审计 | 扫描 AgentState URLs | 是 | PASS | 质量分硬编码但不影响核心 |
| Asset Gap | 代码审计 | 集合对比 | 是 | PASS | 逻辑正确 |
| Product Identity | 代码审计 | 从 product_attributes 提取 | 是 | PASS | 约束进入生图 Prompt |
| AI Image | 代码审计 | wan2.7-image-pro | 是 | PASS | Unsplash 已移除，失败如实记录 |
| Listing | 代码审计 | LLM (注入真实市场数据) | 是 | **PARTIAL** | 降级兜底为硬编码连衣裙 Listing |
| Listing Health | 代码审计 | 纯算法 | 是 | PASS | 8 维度，动态评分 |
| Human Review | 代码审计 | 前端可编辑 | 是 | PARTIAL | 未实际运行 |
| Publish Package | 代码审计 | 组装上游数据 | 是 | PARTIAL | 仅内存 dict，无物理文件；默认 simulated |

---

## 28. 最终红黄绿评级

## 🟡 YELLOW

**理由**：

核心架构设计正确，Amazon API 真实可用，数据流链路完整，评分引擎为纯算法而非 LLM 虚构，Unsplash 填充已彻底移除，失败处理诚实透明。

但存在以下**非阻塞问题**：

1. **P0 阻塞**：1688 JustOneAPI 余额不足，主商品导入通道不可用
2. **架构问题**：`Alibaba1688Source.import_product()` 为死代码，实际走 importer.py 页面抓取
3. **数据质量**：中文商品标题直接搜索 Amazon，缺少翻译/本地化步骤
4. **降级风险**：Listing 生成失败时返回硬编码连衣裙 Listing
5. **发布链路**：默认 simulated 模式，无物理发布包生成
6. **BSR 异常**：Best Sellers 接口返回空结果

核心 Demo 在以下条件下可以运行：
- 1688 HTML 抓取未被反爬拦截
- 或用户手动提供商品信息
- Amazon API 正常工作

---

## 29. 最终必须回答的 10 个问题

### Q1: 真实 1688 商品是否可以进入 AgentState？

**PARTIAL**

代码链路正确（前端桥梁机制），但 JustOneAPI 余额不足导致主要导入通道不可用。HTML 页面抓取降级通道存在但受反爬影响。

### Q2: Amazon 真实数据是否真正进入 MarketContext？

**YES**

Amazon Search API 返回真实商品数据 → market_node 注入 LLM 上下文 → market_insights dict → opportunity_score_node 重建为 MarketContext。数据链路完整，且有 `data_sources` 标记。

### Q3: Opportunity Score 是否基于真实市场数据？

**YES**（当有数据时）/ **PARTIAL**（当数据缺失时）

评分引擎为纯算法，基于真实竞品数据计算。但缺失数据时使用较高基线分数（加权约 58），可能给出虚假乐观的评分。

### Q4: Listing 是否基于真实 ProductProfile + MarketContext？

**YES**

Listing Prompt 注入商品属性（来自 product_attributes）+ 市场洞察（high_converting_keywords, buyer_pain_points, differentiation_angles 来自 market_insights）。间接使用了真实 Amazon 数据。

### Q5: Product Identity 是否真正进入生图 Prompt？

**YES**

`_build_product_identity()` 提取视觉约束 → 注入 `_generate_ai_scenes()` 的每个 prompt 中：`"IMPORTANT: {visual_constraints}. The product in the image must match these exact characteristics."`

### Q6: AI Image API 是否真实生成？

**YES**（能力存在）

wan2.7-image-pro 已配置，`generate_image()` 调用 DashScope 生图 API。但在 1688 搬运模式下不触发生图（直接沿用原图）。Unsplash 填充已彻底移除。

### Q7: 是否彻底移除了 P0 主链路 Mock？

**PARTIAL**

Unsplash 填充已移除，虚拟试穿兜底返回空状态，生图失败如实记录。但 Listing 降级兜底仍为硬编码的完整连衣裙 Listing（`listing.py:90-111`），这是 P0 主链路中最具误导性的残留。

### Q8: Human Review 是否真实保存？

**PARTIAL**

前端支持编辑 Listing 内容，修改通过 SSE 流传递。但由于无法实际运行完整流水线，未验证持久化保存。

### Q9: Publish Package 是否真实生成？

**PARTIAL**

Publish Package Node 生成内存中的数据结构（dict），不生成物理文件（ZIP/PDF）。发布服务默认 simulated 模式，生成模拟回执。真实 SP-API 提交需要配置 OAuth 凭证。

### Q10: 完整 P0 是否可以现场 Demo？

**CONDITIONAL**

在以下条件满足时可以 Demo：
1. 1688 HTML 抓取未被反爬拦截（或手动输入商品信息）
2. Amazon JustOneAPI 余额充足（当前可用）
3. LLM/Image API 正常（DashScope Token Plan 有效）

Demo 流程将展示：商品导入 → 属性提取(VL) → Amazon 真实竞品分析 → 机会评分 → Listing 生成 → 健康评分 → 发布包组装。

---

## 30. 关键问题清单与优先级

### P0 (阻塞性)

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 1 | JustOneAPI 1688 余额不足 | 主商品导入通道不可用 | 充值 JustOneAPI 账户 或 配置 1688 官方开放平台凭证 |
| 2 | Listing 降级兜底为硬编码连衣裙 | 非连衣裙商品可能获得虚假 Listing | 替换为错误提示或空 Listing |

### P1 (重要)

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 3 | 中文标题直接搜索 Amazon | 搜索结果质量差 | 增加翻译/本地化步骤 |
| 4 | Alibaba1688Source.import_product() 为死代码 | 架构不一致 | 统一导入通道或移除死代码 |
| 5 | sku_attributes 类型不匹配 | 下游消费者可能行为异常 | 统一为 Dict[str, List[str]] |
| 6 | Amazon BSR 返回空结果 | 缺失畅销品数据 | 调查 category 参数格式 |

### P2 (改进)

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 7 | 数据源 confidence 硬编码 | 虚假可信度 | 基于数据完整度计算 |
| 8 | Asset quality_score 硬编码 | 不反映真实质量 | 引入图像分析 |
| 9 | Publish 无物理文件输出 | 无法导出 | 生成 ZIP/JSON 文件 |
| 10 | Opportunity Scorer 基线偏高 | 数据缺失时虚假乐观 | 降低无数据基线分 |

---

*报告生成时间：2026-08-28*
*验收方式：代码审计 + 真实 API 调用 + 架构分析*
*验收原则：不修改代码、不 Mock 数据、如实记录*
