# GloLaunch AI 当前实现审计报告

> 审计日期：2026-08-27
> 审计原则：以实际代码、实际 API 调用、实际数据流为唯一依据。不以注释、README、TODO 作为"已完成"判断标准。

---

## 1. 总体完成度

```
总体完成度：45%

P0 核心链路：35%

1688 商品导入：       65%
Amazon Research：     60%
Market Intelligence： 40%
Opportunity Score：   50%
Asset Inventory：     45%
Asset Gap Analysis：  40%
AI Product Photography： 35%
Listing Generation：  50%
Listing Health：      55%
Human Review：        30%
Publish Package：     15%

P1：15%
P2：5%
```

百分比说明：代码存在但存在数据断裂、Mock 降级、或未接入 E2E 主流程的功能，按实际可用程度打折计算。

---

## 2. P0 核心链路完成度

P0 链路设计目标：

```
1688 商品 → ProductProfile → Amazon Research → MarketContext → Opportunity Score
→ Asset Inventory → Asset Gap Analysis → AI Product Photography → Listing Generation
→ Listing Health → Human Review → Publish Package
```

当前实际状态：

| 环节 | 状态 | 说明 |
|------|------|------|
| 1688 商品导入 | ⚠️ 半完成 | JustOneAPI 接口已接入，可获取商品数据并映射为 ProductProfile，但官方 API 是 TODO 桩 |
| ProductProfile → AgentState | ❌ 断裂 | ResearchSource 产出的 ProductProfile 从未进入 LangGraph AgentState |
| Amazon Research | ⚠️ 半完成 | 4 个 JustOneAPI 端点已实现，但数据未流入 OpportunityScorer |
| MarketContext | ⚠️ 双路径 | 真实数据路径存在，但实际使用的是 LLM 生成的 market_insights |
| Opportunity Score | ⚠️ 半完成 | 6 维加权评分模型完整，但输入数据来自 LLM 幻觉而非真实数据 |
| Asset Inventory | ⚠️ 半完成 | 模型存在，AI 分类部分实现，但依赖上游数据 |
| Asset Gap Analysis | ⚠️ 半完成 | 逻辑存在，但依赖 Asset Inventory 的真实输入 |
| AI Product Photography | ⚠️ 半完成 | 调用 wan2.7-image-pro，失败时降级为 Unsplash 静态图 |
| Listing Generation | ⚠️ 半完成 | LLM 生成文案，但未充分使用 MarketContext 真实数据 |
| Listing Health | ✅ 基本完成 | 8 维规则评分，有实际计算逻辑 |
| Human Review | ❌ 不完整 | 前端有编辑界面，后端 /v2/publish/review 是空操作 |
| Publish Package | ❌ 未完成 | publish_dry_run=True 默认模拟，/v2/publish/execute 返回 not_implemented |

**关键断裂点：**

```
1688 URL
  ↓
JustOneAPI → ProductProfile ✅ （真实数据）
  ↓
  ✗ 断裂 — ProductProfile 未进入 AgentState
  ↓
LangGraph Agent → LLM 自行生成 market_insights （非真实数据）
  ↓
OpportunityScorer → 基于 LLM 幻觉数据评分
  ↓
... 后续节点全部基于非真实数据运行
```

---

## 3. 第三方采集接入情况

| 数据源 | 已接入 | 实际调用 | 数据结构已统一 | 当前主流程使用 | 建议 |
|--------|--------|----------|---------------|---------------|------|
| 1688 | ✅ | ✅ JustOneAPI /api/1688/get-item-detail/v1 | ✅ → ProductProfile | ⚠️ 可调用但未接入 AgentState | 保留，修复数据断裂 |
| Amazon | ✅ | ✅ JustOneAPI 4 个端点 | ✅ → MarketContext | ❌ 未接入主流程 | 保留，必须接入 E2E |
| Shopee | ✅ | ✅ JustOneAPI 2 个端点 | ✅ → MarketContext | ❌ P1 不在当前主流程 | 保留，冻结至 P1 |
| TikTok Shop | ✅ | ✅ JustOneAPI 2 个端点 | ✅ → MarketContext | ❌ P1 不在当前主流程 | 保留，冻结至 P1 |
| Temu | ❌ | ❌ | ❌ | ❌ | 冻结，代码为 TODO 桩 |
| TikTok (内容) | ❌ | ❌ | ❌ | ❌ | 冻结，P2 |
| Instagram | ❌ | ❌ | ❌ | ❌ | 冻结，P2 |
| YouTube | ❌ | ❌ | ❌ | ❌ | 冻结，P2 |
| Reddit | ❌ | ❌ | ❌ | ❌ | 冻结，P2 |
| 今日头条/知乎等 | ❌ | ❌ | ❌ | ❌ | 冻结，P2 |

**结论：当前应优先使用的第三方采集能力：**

1. **1688 JustOneAPI** — 商品导入的入口，必须修复数据断裂
2. **Amazon JustOneAPI** — 4 个端点已实现，必须接入主流程让真实市场数据驱动评分
3. Shopee / TikTok Shop — 代码已就绪但不在 P0 主流程内，暂时冻结

---

## 4. ProductProfile

**存在状态：** ✅ 已定义

文件：`backend/app/domain/product_profile.py`

包含 27 个字段，涵盖：title, category, price, currency, images, specifications, description, sku_variants, supplier_info 等。

**实际数据流检查：**

```
1688 JustOneAPI → Alibaba1688Source.import_product() → ProductProfile ✅
图片上传 → 前端 Upload → 后端 /v2/import/upload → ProductProfile ✅
AI 视觉识别 → qwen3.7-plus VL → ProductProfile.attributes ✅
Amazon Research → 读取 ProductProfile? ❌ 未读取，Agent 自行从 state 取数据
Listing Generation → 读取 ProductProfile? ❌ 未直接读取，从 state.product 取（可能是 LLM 生成）
```

**核心问题：**

> ResearchSource 层产出的 ProductProfile 与 LangGraph AgentState 中的 state.product 是两套独立数据。
> 1688 导入的真实商品数据从未被注入到 AgentState 中。
> Agent 节点运行时的 state.product 来自 LLM 自行构造，而非上游真实数据。

**数据断裂位置：**

```
Alibaba1688Source.import_product()
  ↓
  返回 ProductProfile（真实数据）✅
  ↓
  API 层 /v2/import/1688 → 返回给前端 ✅
  ↓
  用户点击"开始分析" → /v2/agent/run
  ↓
  _build_initial_state() → 从哪读取 ProductProfile？
  ↓
  ❌ 断裂 — 构造的 state.product 不是上游的 ProductProfile
```

---

## 5. ProductIdentity

**存在状态：** ⚠️ 部分存在

ProductProfile 中有 `identity_fingerprint` 字段（str），在 `product_profile.py` 中定义。

**实际检查：**

```
product_name        → ✅ 有 title 字段
category            → ✅ 有 category 字段
shape               → ❌ 无独立字段
color               → ❌ 无独立字段
material            → ❌ 无独立字段
logo                → ❌ 无独立字段
visual_features     → ❌ 无独立字段
reference_images    → ✅ 有 images 字段
identity_fingerprint → ✅ 有字段，但是 dead code
```

**关键发现：**

> `identity_fingerprint` 在代码中被计算（基于 title + category + images 的 hash），但在整个项目中**没有任何地方读取或使用它**。
> 它是一个被计算但从未被消费的字段。
> AI 生图时不参考 identity_fingerprint，因此无法保证商品主体一致性。

**结论：**

```
原商品图片
  ↓
identity_fingerprint（计算了但没人用）
  ↓
AI Image Generation（不使用 fingerprint，商品主体可能变化）
```

> ❌ ProductIdentity 机制未真正建立。identity_fingerprint 是 dead code。

---

## 6. Amazon Research

**文件：** `backend/app/sources/amazon_research.py`

**已实现的 JustOneAPI 端点：**

| 端点 | 方法 | 状态 |
|------|------|------|
| /api/amazon/search-products/v1 | search_products() | ✅ 已实现 |
| /api/amazon/get-product-detail/v1 | get_product_detail() | ✅ 已实现 |
| /api/amazon/get-product-top-reviews/v1 | get_product_top_reviews() | ✅ 已实现 |
| /api/amazon/get-best-sellers/v1 | get_best_sellers() | ✅ 已实现 |

**功能检查：**

| 检查项 | 状态 |
|--------|------|
| 搜索竞品 | ✅ search_products() 支持关键词、国家、排序、Prime 筛选 |
| 商品标题 | ✅ get_product_detail() 可获取 |
| 价格 | ✅ 有 _parse_price() 解析 |
| 评分 | ✅ get_product_detail() 可获取 |
| 评论 | ✅ get_product_top_reviews() 可获取 |
| 图片 | ✅ get_product_detail() 可获取 |
| 多竞品 | ✅ search_products 返回多个结果 |
| 缓存 | ❌ 无缓存层 |
| 错误处理 | ✅ 有错误码映射（100/301/302/400/500/600 等） |

**核心问题：**

> **当前"市场洞察"的真实数据与 LLM 推理比例：**

```
真实数据（JustOneAPI）：
- search_products → 竞品列表、价格、评分
- get_best_sellers → BSR 排名数据
- 这些数据可以构建 MarketContext ✅

LLM 推理/幻觉：
- market_overview（趋势概述）→ LLM 生成
- target_audience（客群画像）→ LLM 生成
- buyer_pain_points → LLM 生成
- differentiation_angles → LLM 生成
- recommended_price_range → LLM 生成
- launch_confidence_score → LLM 生成

Mock：
- 无直接 Mock，但真实数据从未流入 OpportunityScorer
```

**结论：** Amazon Research 的 API 层已实现，但存在"数据孤岛"问题 — 真实数据获取了，但没被下游使用。

---

## 7. MarketContext

**文件：** `backend/app/domain/market_context.py`

**结构检查：**

```
platform              → ❌ 无独立字段（在 raw_data 中）
region                → ❌ 无独立字段
category              → ❌ 无独立字段
price_range           → ✅ recommended_price_range
competitors           → ✅ List[CompetitorSnapshot]
common_keywords       → ✅ top_keywords: List[KeywordData]
common_selling_points → ❌ 无独立字段
review_insights       → ❌ 无独立字段
visual_patterns       → ❌ 无独立字段
market_risks          → ❌ 无独立字段
```

**真实数据 vs LLM 生成：**

```
真实数据计算：
- competitors（来自 JustOneAPI search_products）
- avg_competitor_price（来自竞品价格计算）
- price_distribution（来自竞品价格分布）
- data_sources（记录数据来源）

LLM 生成：
- market_overview
- target_audience
- buyer_pain_points
- buyer_preferences
- differentiation_angles
- launch_confidence_score
- recommended_price_range（可能混合真实数据+LLM推理）
```

**核心问题：** MarketContext 模型设计合理，但实际构建过程中 LLM 填充了过多字段。真实数据（竞品、价格）获取了但可能未传入下游评分。

---

## 8. Opportunity Score

**文件：** `backend/app/intelligence/opportunity_scorer.py`

**评分模型：**

```
评分：0-100 分

评分维度（6 维加权）：
- 市场需求 (market_demand)     — 权重 25%
- 竞争程度 (competition)       — 权重 20%
- 价格利润 (price_margin)      — 权重 20%
- 供应链优势 (supply_chain)    — 权重 15%
- 内容差异化 (content_diff)    — 权重 10%
- 合规风险 (compliance_risk)   — 权重 10%

计算公式：加权求和 → 0-100 分
数据来源：MarketContext + ProductProfile
是否真实计算：✅ 有实际计算逻辑，非固定值
是否可解释：✅ 每个维度有独立得分和说明
```

**核心问题：**

> 评分模型本身是真实的（不是 LLM 拍脑袋给分），但输入数据来自 LLM 幻觉的 market_insights，而非 JustOneAPI 真实数据。
>
> 公式：垃圾进 → 垃圾出。评分逻辑正确，但评分依据不可靠。

```
❌ 不符合目标设计的根本原因：

期望：
1688 真实数据 + Amazon 真实竞品数据 → OpportunityScorer → 可信评分

实际：
LLM 生成的 market_insights → OpportunityScorer → 看似精确但依据虚假的评分
```

---

## 9. Supply-Market Fit

**存在状态：** ❌ 不存在

项目中没有独立的 Supply-Market Fit 模块。当前 Opportunity Score 中的 `supply_chain` 维度部分覆盖了供应链评估，但没有实现：

```
1688供应链数据
+
Amazon市场数据
  ↓
匹配度计算
```

的完整逻辑。

> 标记为 P0 缺失。这是投资人/评委关注的核心差异化能力。

---

## 10. Asset Inventory

**文件：** `backend/app/domain/asset_inventory.py`

**素材识别能力：**

| 素材类型 | 能否识别 | 识别方式 |
|----------|----------|----------|
| 主图 | ⚠️ | AI 分类（基于图片特征推断） |
| SKU图 | ⚠️ | AI 分类 |
| 细节图 | ⚠️ | AI 分类 |
| 功能图 | ⚠️ | AI 分类 |
| 场景图 | ⚠️ | AI 分类 |
| 尺寸图 | ⚠️ | AI 分类 |
| Logo | ⚠️ | AI 分类 |
| 视频 | ❌ | 未实现 |

**关键判断：**

> AI 图片分类存在（使用 qwen3.7-plus 多模态能力），但分类准确度依赖图片质量。
> 不是用户手动上传后标记，而是 AI 自动识别 — 这点是好的。
> 但上游输入（1688 商品图片）的完整度直接决定了 Inventory 的质量。

---

## 11. Asset Gap Analysis

**文件：** `backend/app/intelligence/asset_gap_analyzer.py`

**存在状态：** ⚠️ 已实现但依赖上游

**检查逻辑：**

```
已有素材（Asset Inventory）
+
目标平台需求（Amazon 要求主图+场景图+信息图+视频等）
  ↓
Gap 分析 → 输出缺失清单
```

**核心问题：**

> Gap 分析的逻辑存在，能判断"缺什么素材"。
> 但它依赖 Asset Inventory 的真实输入，而 Asset Inventory 依赖 1688 图片的真实导入。
> 如果 1688 导入的图片不全，Gap 分析的结果虽然正确但意义有限。
> 它目前不根据目标平台的具体需求做精细化判断（如 Amazon 要求纯白背景主图 2000x2000px）。

---

## 12. AI Product Photography

**文件：** `backend/app/intelligence/image_generator.py`

**检查结果：**

```
真实 AI 生图：✅（有条件）

模型：wan2.7-image-pro（同步调用，场景图/白底主图）
      wan2.5-i2i-preview（异步任务，图片编辑/虚拟试穿）

API Key 来源：model_router_api_key（环境变量 .env）

商品参考图：⚠️ 部分支持
  - 白底图生成时可传入原图作为参考
  - 但 identity_fingerprint 不参与生成过程

ProductIdentity：❌ 未使用
  - identity_fingerprint 是 dead code
  - 生图时不参考 ProductIdentity

Mock/降级：✅ 存在
  - 生图失败时降级为 Unsplash 静态图片 URL（10+ 个预设 URL）
  - 按品类匹配：厨房用品、电子产品、户外等各有对应 Unsplash 图

当前生成类型：
  - 白底主图 ✅
  - 场景图 ✅
  - 信息图/功能图 ❌（未实现）
  - 尺寸图 ❌（未实现）
```

**核心风险：**

> 1. 生图失败时展示 Unsplash 图片，用户/评委无法区分真假
> 2. ProductIdentity 不参与生图，商品主体可能变化
> 3. API Key 如果过期或额度用完，全部降级为 Unsplash

---

## 13. Listing Generation

**文件：** `backend/app/intelligence/listing_generator.py`

**实际数据流：**

```
实际代码：

AgentState.product（可能是 LLM 构造的，非真实 ProductProfile）
+
AgentState.market_insights（LLM 生成，非真实 MarketContext）
  ↓
LLM（qwen3.7-plus）
  ↓
直接生成文案（Title / Bullets / Description / Keywords）
```

**检查项：**

```
Title            → ✅ LLM 生成
Bullet Points    → ✅ LLM 生成
Description      → ✅ LLM 生成
Keywords         → ✅ LLM 生成
Attributes       → ⚠️ 部分字段有，不完整
```

**核心问题：**

> 属于审计模板中的"第二种"情况：
>
> ```
> 1688 商品（或 LLM 构造的 product）
>   ↓
> LLM
>   ↓
> 直接生成文案
> ```
>
> 而非期望的：
>
> ```
> ProductProfile（真实）
> +
> MarketContext（真实竞品数据）
> +
> 竞品分析
> +
> Opportunity Score
>   ↓
> Listing
> ```

> ⚠️ 需要升级。Listing 生成未使用真实市场数据驱动。

---

## 14. Listing Health

**文件：** `backend/app/intelligence/health_checker.py`

**存在状态：** ✅ 基本完成

**检查维度（8 维）：**

| 维度 | 是否真实检查 |
|------|-------------|
| 标题 (title) | ✅ 长度、关键词密度 |
| Bullet Points | ✅ 数量、长度、关键词 |
| Description | ✅ 长度、结构 |
| Keywords | ✅ 数量、相关性 |
| 图片 (images) | ✅ 数量检查 |
| 素材完整度 | ✅ 检查各类型素材 |
| 合规 (compliance) | ✅ 禁用词检查 |
| 属性 (attributes) | ✅ 必填字段检查 |

**关键判断：**

> 不是固定数字。有实际计算逻辑，根据 Listing 内容动态评分。
> 评分结果分为 A/B/C/D/F 五个等级。
> 这是项目中完成度较高的模块之一。

---

## 15. Human Review

**存在状态：** ⚠️ 不完整

**前端能力：**

| 操作 | 状态 |
|------|------|
| 查看 AI 生成的 Listing | ✅ |
| 修改标题 | ✅ 前端可编辑 |
| 修改 Bullet | ✅ 前端可编辑 |
| 修改 Description | ✅ 前端可编辑 |
| 替换图片 | ⚠️ 前端有 UI，后端支持有限 |
| 重新生成 | ⚠️ 有按钮，后端逻辑不完整 |
| 忽略建议 | ❌ 未实现 |
| 最终确认 | ❌ /v2/publish/review 是空操作 |

> ⚠️ Human-in-the-loop 不完整。前端编辑能力存在，但后端的 review/confirm/reject 流程未实现。

---

## 16. Publish Package

**存在状态：** ❌ 未完成

```
真实 Amazon 官方发布：❌
  - publish_dry_run = True（默认值）
  - Amazon SP-API 凭证未配置
  - ChannelAdapter 全部是 dry_run 模式

Publish Package 导出：❌
  - /v2/publish/execute → 返回 not_implemented
  - 无实际的 Package 打包逻辑
  - 无法导出：商品信息、Listing、Keywords、Attributes、图片、SKU、价格、合规结果
```

**当前状态：**

> 生成一个"发布准备"页面 ≠ 完成 Amazon 发布。
> 当前连 Package 打包都不存在，更不用说对接 Amazon SP-API。

---

## 17. P1/P2

### P1 功能

| 功能 | 当前状态 | 建议 |
|------|----------|------|
| Shopee Research | ⚠️ 代码已实现（JustOneAPI 2 端点），不在 P0 主流程 | 保留，冻结 |
| TikTok Shop Research | ⚠️ 代码已实现（JustOneAPI 2 端点），不在 P0 主流程 | 保留，冻结 |
| Temu Research | ❌ TODO 桩，无实际代码 | 冻结 |
| Product Video | ❌ 未实现 | 冻结 |
| TTS | ⚠️ config 中有模型配置（qwen-audio-3.0-tts-plus），未接入流水线 | 冻结 |
| Virtual Try-On | ⚠️ config 中有 aitryon 配置，未接入流水线 | 冻结 |
| Channel Recommendation | ❌ 未实现 | 冻结 |

### P2 功能

| 功能 | 当前状态 | 建议 |
|------|----------|------|
| Amazon Official Publish | ❌ dry_run 模式 | 冻结 |
| Shopee Official Publish | ❌ 未实现 | 冻结 |
| TikTok Shop Official Publish | ❌ 未实现 | 冻结 |
| Shopify | ❌ 未实现 | 冻结 |
| Social Research | ❌ 未实现 | 冻结 |
| 多市场自动扩展 | ❌ 未实现 | 冻结 |

> 所有 P1/P2 功能建议暂时冻结，集中资源打通 P0 链路。

---

## 18. API / Key / Cache / Logging

### Key 管理

| 检查项 | 状态 |
|--------|------|
| API Key 是否环境变量 | ✅ 全部通过 pydantic-settings 从 .env 读取 |
| 是否写死在代码中 | ✅ 未发现硬编码 Key |
| 是否暴露在前端 | ✅ 未暴露，所有 Key 仅后端使用 |

### Error Handling

| 错误类型 | 处理状态 |
|----------|----------|
| 401 Unauthorized | ✅ JustOneAPI 有错误码映射 |
| 403 Forbidden | ✅ 有处理 |
| 429 Rate Limit | ⚠️ 有错误码 429 映射，但无自动重试 |
| 500 Server Error | ✅ 有处理 |
| Timeout | ✅ 120s 超时设置 |
| Empty Response | ⚠️ 部分处理 |
| Invalid Response | ⚠️ 部分处理 |

### Cache

```
Query
  ↓
Cache → ❌ 不存在
  ↓
API
```

> ❌ 无缓存层。每次调用都直接请求第三方 API，存在额度和延迟风险。

### Logging

| 检查项 | 状态 |
|--------|------|
| Task 记录 | ⚠️ 有 checkpoint 机制 |
| Input 记录 | ❌ 无结构化日志 |
| Source 记录 | ✅ MarketContext.data_sources |
| Start/End | ⚠️ 部分节点有 |
| Status | ⚠️ 部分有 |
| Error | ⚠️ 有 try/except 但日志不规范 |

> ❌ 缺少结构化日志系统。调试和演示时难以追踪问题。

---

## 19. Mock 污染

全项目搜索结果：

| 文件/位置 | 功能 | 当前状态 | 影响比赛 Demo | 建议 |
|-----------|------|----------|--------------|------|
| channel_adapters/ (6 处) | 电商发布 | simulated/dry_run | 是 | 必须标注"演示模式" |
| image_generator.py (10+ URL) | AI 生图降级 | Unsplash 静态图 | **严重** | 必须移除或明确标注 |
| demo_presets (2 处) | 演示预设 | 硬编码数据 | 是 | 可保留但必须标注 |
| TODO 桩 (18 处) | 各模块 | 未实现 | 间接影响 | 不影响 Demo 但需知晓 |
| listing_generator.py | Listing 降级 | 硬编码商品文案 | 是 | 必须移除 |
| 前端 confidence score | 选品置信度 | 硬编码 "92/100" | **严重** | 必须改为动态值 |
| temu_research.py | Temu 数据 | TODO 桩返回 None | 否 | 不影响 P0 |
| justone.py | JustOneAPI 通用源 | TODO 桩返回 None | 否 | 不影响 P0 |

**最严重的 Mock 污染：**

1. **Unsplash 降级图** — AI 生图失败时展示无关库存图片，评委可能以为是 AI 生成的
2. **前端硬编码 92/100** — 选品置信度是固定值，不随数据变化
3. **dry_run 发布** — 演示时如果展示"发布成功"但实际没有发布，属于虚假演示

---

## 20. E2E 实际链路

**期望链路：**

```
1688 URL → ProductProfile → Amazon Research → MarketContext → Opportunity Score
→ Asset Inventory → Asset Gap → AI Image → Listing → Listing Health
→ Human Review → Publish Package
```

**实际已打通：**

```
1688 URL
  ↓
JustOneAPI → ProductProfile ✅ （真实数据，可获取商品标题/价格/图片/规格）
  ↓
  ✗ 断裂 — ProductProfile 未注入 AgentState
  ↓
LangGraph Agent 启动
  ↓
LLM 自行构造 product 数据 （非真实 1688 数据）
  ↓
LLM 生成 market_insights （非真实 Amazon 数据）
  ↓
OpportunityScorer → 基于 LLM 数据评分
  ↓
AssetInventory → 基于 state 中的图片列表（可能是空的）
  ↓
AssetGap → 基于 Inventory 结果
  ↓
AI Image → 调用 wan2.7-image-pro ✅（真实 AI 生图，但不用 ProductIdentity）
  ↓                    ↓ 失败时降级为 Unsplash
Listing → LLM 生成文案 ✅
  ↓
ListingHealth → 规则评分 ✅
  ↓
Human Review → ⚠️ 前端可编辑，后端 review 是空操作
  ↓
  ✗ 断裂 — Publish Package 不存在
  ↓
STOP
```

**实际打通段：**

```
1688 → ProductProfile ✅（独立，未接入 Agent）
Agent → AI Image → Listing → Health ✅（但数据非真实）
```

**断裂点：**

1. **1688 → AgentState**：ProductProfile 未注入
2. **Amazon Research → AgentState**：真实市场数据未注入
3. **Human Review → Publish**：review 空操作，publish 未实现

---

## 21. 红黄绿地图

### 🟢 已完成

真正可运行、真实数据、真实接口：

- JustOneAPI 1688 商品详情获取（API 层）
- JustOneAPI Amazon 4 端点（搜索/详情/评论/畅销）
- JustOneAPI Shopee 2 端点（搜索/详情）
- JustOneAPI TikTok Shop 2 端点（搜索/详情）
- OpportunityScorer 6 维评分模型（计算逻辑真实）
- ListingHealthCalculator 8 维规则评分
- ProductProfile 数据模型（27 字段完整）
- MarketContext 数据模型（结构合理）
- LangGraph 12 节点流水线（框架运行）
- API Key 环境变量管理（安全）
- SSE 事件推送协议（plan → node_start → node_update → complete）
- 前端 V2 面板（6 个面板组件，数据绑定完整）

### 🟡 半完成

代码存在，但依赖 Key / 权限 / 部分 Mock / 未接入 E2E：

- 1688 → AgentState 数据注入（代码存在但断裂）
- Amazon Research → MarketContext 真实数据路径（存在但未使用）
- AI Product Photography（真实调用，但有 Unsplash 降级）
- Asset Inventory AI 分类（存在，依赖上游输入）
- Asset Gap Analysis（逻辑存在，依赖 Inventory）
- Listing Generation（LLM 生成，未用真实市场数据驱动）
- Human Review 前端编辑（前端有，后端空操作）
- SourceRegistry 数据源路由（框架完整，但部分源是桩）
- 前端 V2 数据展示（绑定完整，但后端 2 个端点未实现）

### 🔴 未完成

- ProductIdentity 机制（identity_fingerprint 是 dead code）
- Supply-Market Fit 模块
- Publish Package 打包
- Amazon SP-API 真实发布
- 结构化日志系统
- API 缓存层
- Human Review 后端流程（review/confirm/reject）
- Temu Research（TODO 桩）
- Product Video / TTS / Virtual Try-On（配置存在，未接入）
- 多市场自动扩展
- Shopify 渠道

---

## 22. Top 10 下一步任务

| 优先级 | 任务 | 原因 | 预计影响 | 是否阻塞 P0 |
|--------|------|------|----------|------------|
| P0-1 | **修复 1688 → AgentState 数据注入** | 真实商品数据从未进入流水线，整个 Agent 基于 LLM 幻觉运行 | 解决根本性数据断裂，让 Demo 可以展示"真实 1688 商品 → 真实分析" | **是** |
| P0-2 | **接入 Amazon Research 真实数据到 OpportunityScorer** | 4 个端点已实现但数据未流入评分，市场洞察是伪数据 | 让评分有据可依，Demo 可展示真实竞品数据 | **是** |
| P0-3 | **移除 Unsplash 降级 + 前端硬编码 92/100** | Mock 污染是比赛演示的致命风险 | 避免评委发现虚假数据导致信任崩塌 | **是** |
| P0-4 | **实现 ProductIdentity 并接入 AI 生图** | 商品主体一致性是核心体验 | 生图时保持商品外观一致，提升 Demo 说服力 | **是** |
| P0-5 | **实现 Supply-Market Fit 基础版** | 1688 供应链 + Amazon 市场匹配度是核心差异化 | 评委最关注的"为什么用你"的答案 | **是** |
| P0-6 | **完善 Human Review 后端流程** | /v2/publish/review 是空操作，用户无法真正确认/修改 | Demo 时展示人机协作能力 | 否 |
| P0-7 | **实现 Publish Package 打包导出** | 最终交付物不存在 | 至少能导出 PDF/ZIP 形式的发布包 | 否 |
| P1-1 | **添加 API 缓存层** | 无缓存导致重复请求浪费额度 | 降低 API 成本，提升响应速度 | 否 |
| P1-2 | **添加结构化日志** | 调试困难，Demo 出问题时无法快速定位 | 提升工程成熟度 | 否 |
| P1-3 | **实现 Asset Gap 精细化平台需求** | 当前 Gap 分析不够精细 | 提升素材建议的准确度 | 否 |

---

## 23. 最终结论

### 如果今天就参加复赛演示，当前项目最大的 3 个风险是什么？

**风险 1：数据链路断裂 — "真实"不真实**

1688 导入的真实商品数据从未进入 Agent 流水线。Amazon Research 获取的真实竞品数据从未驱动评分。整个 Demo 看起来在"分析"，但实际上 LLM 在"编故事"。如果评委追问数据来源或要求复现，会立刻暴露。

**风险 2：Mock 污染 — Unsplash 图和硬编码分数**

AI 生图失败时展示 Unsplash 库存图片，前端选品置信度硬编码为 92/100。如果评委注意到图片与商品无关，或分数不随输入变化，项目可信度直接归零。

**风险 3：Publish 链路完全缺失 — 没有终点**

流水线在 Listing Health 之后就断了。没有 Publish Package，没有真实或模拟的发布流程。Demo 无法展示"从选品到上架"的完整闭环，只能展示到"生成建议"为止。

### 如果只给我们剩余时间做 3 件事，最应该做哪 3 件？

**第一件：打通 1688 → Agent → Amazon Research 的真实数据链路**

让一个 1688 商品 URL 的真实数据流入 AgentState，让 Amazon JustOneAPI 的真实竞品数据流入 OpportunityScorer。这是从"LLM 编故事"到"真实数据驱动"的根本转变。没有这一步，其他一切都是空中楼阁。

**第二件：清除 Mock 污染 + 实现 ProductIdentity**

移除所有 Unsplash 降级图（改为明确提示"生图失败"），移除前端硬编码分数（改为动态计算），让 AI 生图时参考 ProductIdentity 保持商品主体一致。这决定了 Demo 的可信度。

**第三件：实现最小可用的 Publish Package**

不需要对接 Amazon SP-API，但至少能生成一个包含 Listing + 图片 + Keywords + 定价建议的导出包（PDF 或 ZIP）。让 Demo 有一个明确的"完成"终点，而不是停在"建议已生成"。

---

> 审计完成。以上所有结论基于实际代码检查，未做任何美化。
