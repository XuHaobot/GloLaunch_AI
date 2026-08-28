# GloLaunch AI P0 收敛重构方案

> 日期：2026-08-27
> 原则：不加新功能，只把已有能力串成一条真实数据链路。
> 目标：让 1688 真实商品数据 → Amazon 真实市场数据 → 真实评分 → 真实素材决策 → 真实 Listing → 可导出的上架包。

---

## 一、当前架构的 5 个致命断裂点

经过逐文件审计，P0 链路存在以下精确断裂：

### 断裂 1：1688 真实数据从未进入 Agent

**位置：** `app/routers/chat.py` 第 103-112 行

```python
initial_state = {
    "messages": [HumanMessage(content=req.message or "执行全链路智能上新")],
    "user_intent": intent,
    "disabled_stages": disabled,
    "target_platform": req.target_platform,
    "target_market": req.target_market,
    "product_image_url": req.product_image_url,       # ← 只传了图片 URL
    "imported_images": req.imported_images or [],      # ← 只传了图片列表
    "trace": []
}
```

1688 导入接口 (`importer.py`) 返回了 `title`、`source_price`、`sku_attributes`、`images`，但前端只把 `main_image` → `product_image_url`、`images` → `imported_images` 传给流水线。**标题、价格、SKU 全部丢弃。**

### 断裂 2：product_node 完全依赖 LLM 视觉猜测

**位置：** `app/agent/nodes/product.py` 第 46-110 行

product_node 拿到 `product_image_url` 后，调用 Qwen-VL 多模态模型从图片猜属性。即使 1688 已经告诉我们商品标题是"法式复古碎花连衣裙 棉麻材质 ¥39"，product_node 也不知道——它只看图。

输出 `product_attributes` 中没有 `title`、`supply_price_cny`、`moq`、`supplier_name` 等关键字段。

### 断裂 3：market_node 完全依赖 LLM 幻觉

**位置：** `app/agent/nodes/market.py` 第 27-111 行

market_node 不调用任何 Amazon API。它用 Qwen3.8-Max 凭空生成市场洞察 JSON。`market_insights` 只有 8 个字段（market_overview, recommended_price_range, profit_margin_est, target_audience, buyer_pain_points, differentiation_angles, high_converting_keywords, launch_confidence_score）。

而 `AmazonResearchSource` 已经实现了 4 个 JustOneAPI 端点（search_products, get_product_detail, get_product_top_reviews, get_best_sellers），但这些能力完全没有被 market_node 使用。

### 断裂 4：OpportunityScorer 收到空数据

**位置：** `app/agent/nodes/opportunity_score.py` 第 47-59 行

`_build_market_context()` 把 LLM 幻觉的 `market_insights` 映射到 `MarketContext`，但以下字段永远为空：

- `competitors`（竞品列表）→ 空 → `_score_competition()` 默认 70 分
- `top_keywords`（关键词数据）→ 空 → `_score_market_demand()` 缺失关键词维度
- `market_size_usd` / `growth_rate_yoy` → 空
- `avg_competitor_price` / `price_distribution` → 空
- `recommended_price_low` / `recommended_price_high` → 空 → `_score_price_margin()` 无法计算真实利润率

同时 `_build_product_profile()` 中 `supply_price_cny` 永远为 None（因为 product_node 不输出价格），导致利润率计算彻底失效。

### 断裂 5：Asset Inventory 时序错误

**位置：** `app/agent/graph.py` 中的节点顺序

`asset_inventory` 节点在 `studio_generation` 之前执行。当 asset_inventory 检查 `state["studio_assets"]` 时，它永远是空的——因为 studio 还没运行。Gap 分析看不到即将生成的 AI 素材。

---

## 二、重构后的目标数据流

```
1688 URL
  ↓
JustOneAPI / 官方 API / 页面抓取
  ↓
{ title, price, images[], sku_attrs, source_url }
  ↓
┌─────────────────────────────────────────────────┐
│  AgentState（注入完整 1688 数据）                    │
│  product_image_url  = main_image                 │
│  imported_images    = images                     │
│  product_title      = title          ← 新增       │
│  supply_price_cny   = price          ← 新增       │
│  sku_attributes     = sku_attrs      ← 新增       │
│  source_url         = url            ← 新增       │
└─────────────────────────────────────────────────┘
  ↓
product_node
  ├── 有 1688 真实数据 → 直接使用 title/price/sku，VL 仅补充视觉属性
  └── 无 1688 数据（拍照/上传）→ VL 全量提取（现有逻辑）
  ↓
market_node
  ├── 从 product_attributes 提取搜索关键词
  ├── 调用 AmazonResearchSource.search_products()    ← 新增
  ├── 调用 AmazonResearchSource.get_best_sellers()   ← 新增
  ├── 构建真实 MarketContext（competitors, prices, keywords）
  └── LLM 仅在真实数据基础上做分析总结                 ← 改造
  ↓
opportunity_score_node
  ├── _build_product_profile() 包含 supply_price_cny  ← 修复
  ├── _build_market_context() 包含 competitors/prices ← 修复
  └── OpportunityScorer 基于真实数据评分               ← 自动修复
  ↓
asset_inventory_node（第一次：预分析）
  ├── 盘点已有素材（1688 图片 + 用户上传）
  └── 输出初步 Gap 分析（供 studio_node 参考）
  ↓
studio_generation
  ├── 有原图 → 沿用（现有逻辑）
  ├── 无原图 → AI 生图（去掉 Unsplash 降级）          ← 修复
  └── 参考 ProductIdentity 视觉特征                   ← 新增
  ↓
asset_inventory_node（第二次：最终盘点）                ← 新增
  ├── 纳入 AI 生成素材
  └── 输出最终 Gap 分析 + 覆盖率
  ↓
trend_benchmark → generate_listing → ...
  ↓
publish_package_node
  ├── ListingHealth 评分
  ├── 构建 PublishPackage
  └── 生成可导出的上架包（JSON + 图片清单）             ← 新增
```

---

## 三、逐文件修改清单

### 3.1 打通 1688 → AgentState

#### 文件 1：`backend/app/routers/chat.py`

**修改 LaunchRequest（第 22-31 行）：**

新增字段：

```python
class LaunchRequest(BaseModel):
    message: str = ""
    product_image_url: Optional[str] = None
    imported_images: Optional[List[str]] = None
    target_platform: Optional[str] = "Amazon"
    target_market: Optional[str] = "US"
    intent: Optional[str] = "full_launch"
    disabled_stages: Optional[List[str]] = None
    thread_id: Optional[str] = None
    resume: Optional[bool] = False
    # ── 新增：1688 导入的真实商品数据 ──
    product_title: Optional[str] = None          # 商品标题
    supply_price_cny: Optional[float] = None     # 供应价格（人民币）
    sku_attributes: Optional[Dict[str, List[str]]] = None  # SKU 属性（如 {颜色: [红,蓝], 尺码: [S,M,L]}）
    source_url: Optional[str] = None             # 来源链接
```

**修改 initial_state（第 103-112 行）：**

```python
initial_state = {
    "messages": [HumanMessage(content=req.message or "执行全链路智能上新")],
    "user_intent": intent,
    "disabled_stages": disabled,
    "target_platform": req.target_platform,
    "target_market": req.target_market,
    "product_image_url": req.product_image_url,
    "imported_images": req.imported_images or [],
    "trace": [],
    # ── 新增：注入 1688 真实数据 ──
    "product_title": req.product_title or "",
    "supply_price_cny": req.supply_price_cny,
    "sku_attributes": req.sku_attributes or {},
    "source_url": req.source_url or "",
}
```

#### 文件 2：`backend/app/agent/state.py`

**新增 AgentState 字段：**

```python
# 1688 导入的真实商品数据（由 initial_state 注入）
"product_title": str,
"supply_price_cny": Optional[float],
"sku_attributes": Dict[str, List[str]],
"source_url": str,
```

#### 文件 3：`frontend/src/App.vue`

**修改 importAndLaunch()（约第 1168-1182 行）和 applyImported()（约第 1155-1165 行）：**

将 `importedProduct` 中的 title、source_price、sku_attributes 传入流水线请求体：

```javascript
// 在 runPipeline() 的请求体中新增：
body.product_title = importedProduct.value?.title || ''
body.supply_price_cny = parsePrice(importedProduct.value?.source_price)  // "¥39" → 39
body.sku_attributes = importedProduct.value?.sku_attributes || {}
body.source_url = importedProduct.value?.source_url || ''
```

---

### 3.2 改造 product_node：真实数据优先

#### 文件 4：`backend/app/agent/nodes/product.py`

**核心改造逻辑：**

```python
async def product_node(state: AgentState) -> Dict[str, Any]:
    # 1. 检查是否有 1688 真实数据
    title_1688 = state.get("product_title", "")
    price_1688 = state.get("supply_price_cny")
    sku_attrs = state.get("sku_attributes", {})
    image_url = state.get("product_image_url")

    if title_1688:
        # ── 路径 A：1688 导入，真实数据为主 ──
        attributes = {
            "title": title_1688,
            "supply_price_cny": price_1688,
            "source_url": state.get("source_url", ""),
            "sku_attributes": sku_attrs,
            "main_image_url": image_url or "",
            "original_images": state.get("imported_images", []),
        }
        # 如果有图片，仍用 VL 补充视觉属性（颜色、材质、风格等）
        if image_url:
            vision_attrs = await _extract_vision_attributes(image_url, title_1688)
            attributes.update(vision_attrs)  # VL 结果补充，不覆盖真实数据
        else:
            # 无图片的纯数据模式，用 LLM 从标题推断品类
            text_attrs = await _infer_from_title(title_1688)
            attributes.update(text_attrs)
    else:
        # ── 路径 B：拍照/上传，VL 全量提取（现有逻辑不变）──
        attributes = await _extract_vision_attributes(image_url, "")

    # 确保关键字段存在
    attributes.setdefault("title", title_1688 or "未命名商品")
    attributes.setdefault("supply_price_cny", price_1688)
    attributes.setdefault("category_family", "general")
    ...
```

**关键变化：**

- 有 1688 数据时，`title`、`supply_price_cny`、`sku_attributes` 来自真实数据，不再依赖 LLM 猜测
- VL 模型仅用于补充视觉属性（颜色、材质、风格），不覆盖已知的真实数据
- 无 1688 数据时（拍照场景），保持现有 VL 全量提取逻辑
- `supply_price_cny` 被写入 `product_attributes`，下游 OpportunityScorer 可以读取

---

### 3.3 改造 market_node：接入 Amazon 真实数据

#### 文件 5：`backend/app/agent/nodes/market.py`

**核心改造逻辑：**

```python
async def market_node(state: AgentState) -> Dict[str, Any]:
    attrs = state.get("product_attributes", {})
    platform = state.get("target_platform", "Amazon")
    market = state.get("target_market", "US")
    category = attrs.get("category", state.get("product_category", ""))
    title = attrs.get("title", "")

    # ── 新增：尝试调用 Amazon JustOneAPI 获取真实数据 ──
    real_market_data = None
    if platform == "Amazon":
        real_market_data = await _fetch_amazon_real_data(title, category, market)

    if real_market_data:
        # ── 路径 A：有真实 Amazon 数据 ──
        # LLM 在真实数据基础上做分析总结，而非凭空生成
        insights = await _analyze_with_real_data(real_market_data, attrs, platform, market)
    else:
        # ── 路径 B：无真实数据（API Key 未配置/调用失败），降级为纯 LLM ──
        insights = await _generate_llm_insights(attrs, platform, market)

    # 确保输出结构中包含数据溯源标记
    insights["data_sources"] = real_market_data.get("sources", []) if real_market_data else ["LLM"]
    insights["data_freshness"] = real_market_data.get("freshness", "") if real_market_data else ""

    return {"market_insights": insights, ...}
```

**新增 `_fetch_amazon_real_data()` 函数：**

```python
async def _fetch_amazon_real_data(title: str, category: str, market: str) -> Optional[Dict]:
    """调用 AmazonResearchSource 获取真实市场数据"""
    try:
        from app.sources.amazon_research import AmazonResearchSource
        source = AmazonResearchSource()
        if not await source.is_available():
            return None

        # 从标题/品类中提取搜索关键词
        search_query = title or category
        if not search_query:
            return None

        # 并行调用搜索和畅销榜
        search_results = await source.search_products(search_query, country=market)
        best_sellers = await source.get_best_sellers(category, country=market)

        if not search_results and not best_sellers:
            return None

        return {
            "sources": ["JustOneAPI:Amazon"],
            "freshness": time.strftime("%Y-%m"),
            "competitors": search_results or [],
            "best_sellers": best_sellers or [],
        }
    except Exception:
        return None
```

**新增 `_analyze_with_real_data()` 函数：**

```python
async def _analyze_with_real_data(real_data: Dict, attrs: Dict, platform: str, market: str) -> Dict:
    """让 LLM 在真实数据基础上做分析，而非凭空生成"""
    competitors_summary = "\n".join([
        f"- {c.get('title','')[:60]} | ${c.get('price','')} | ★{c.get('rating','')} | {c.get('review_count',0)} reviews"
        for c in real_data.get("competitors", [])[:10]
    ])

    # 构建包含真实数据的 LLM prompt
    user_prompt = f"""
【目标市场】：{platform} ({market})
【商品】：{attrs.get('title', '')}

【Amazon 真实竞品数据】（来自 JustOneAPI）：
{competitors_summary}

请基于以上真实竞品数据，分析市场机会。
注意：价格、评分、评论数等数据必须基于上述真实数据，不要编造。
...
"""
    # 调用 LLM 分析（有真实数据作为锚点，LLM 不会完全幻觉）
    ...
```

**同时修改 PROMPT_MARKET_INSIGHT（第 10-25 行）：**

移除 `"launch_confidence_score": 92` 这个硬编码示例值，改为 `"launch_confidence_score": 0`（让 LLM 自己判断，不暗示固定值）。

---

### 3.4 修复 OpportunityScorer 输入

#### 文件 6：`backend/app/agent/nodes/opportunity_score.py`

**修改 `_build_product_profile()`（第 15-44 行）：**

确保从 `product_attributes` 中读取 `supply_price_cny`（现在 product_node 会输出这个字段）：

```python
def _build_product_profile(attrs: Dict[str, Any]) -> ProductProfile:
    return ProductProfile(
        ...
        supply_price_cny=attrs.get("supply_price_cny"),  # 现在会有值了
        moq=attrs.get("moq"),
        supplier_name=attrs.get("supplier_name", ""),
        original_images=attrs.get("original_images", []),
        main_image_url=attrs.get("main_image_url", ""),
        ...
    )
```

**修改 `_build_market_context()`（第 47-59 行）：**

增加对真实数据字段的映射：

```python
def _build_market_context(insights: Dict[str, Any]) -> MarketContext:
    ctx = MarketContext(
        data_sources=insights.get("data_sources", ["LLM"]),
        market_overview=insights.get("market_overview", ""),
        ...
    )

    # 新增：映射真实竞品数据
    competitors_raw = insights.get("competitors", [])
    if competitors_raw:
        from app.domain.market_context import CompetitorSnapshot
        ctx.competitors = [
            CompetitorSnapshot(
                asin_or_id=c.get("asin", ""),
                title=c.get("title", ""),
                price=float(c["price"]) if c.get("price") else None,
                rating=float(c["rating"]) if c.get("rating") else None,
                review_count=int(c.get("review_count", 0)),
            )
            for c in competitors_raw[:15]
        ]
        # 计算真实均价
        prices = [c.price for c in ctx.competitors if c.price]
        if prices:
            ctx.avg_competitor_price = sum(prices) / len(prices)

    # 新增：映射真实关键词数据
    keywords_raw = insights.get("top_keywords", [])
    if keywords_raw:
        from app.domain.market_context import KeywordData
        ctx.top_keywords = [
            KeywordData(keyword=kw.get("keyword", ""), search_volume=kw.get("search_volume"))
            for kw in keywords_raw[:10]
        ]

    return ctx
```

---

### 3.5 清除 Mock 污染

#### 文件 7：`backend/app/agent/nodes/studio.py`

**删除 FALLBACK_SCENES（第 40-51 行）：**

```python
# 删除整个 FALLBACK_SCENES 字典
```

**修改 `_generate_ai_scenes()`（第 123-163 行）：**

```python
async def _generate_ai_scenes(product_desc, family, fallback_main=""):
    ...
    results = await asyncio.gather(*(asyncio.to_thread(generate_image, p) for p in prompts))

    white_main = results[0]
    if not white_main:
        white_main = fallback_main or ""   # 不再降级到 Unsplash
        image_engine = "none" if not any(results) else image_engine

    lifestyle_scenes = []
    for i, t in enumerate(templates):
        url = results[i + 1]
        if not url:
            continue  # 跳过失败的图片，不用 Unsplash 填充
        lifestyle_scenes.append({...})

    return {
        "white_background_main": white_main,
        "lifestyle_scenes": lifestyle_scenes,
        "image_engine": image_engine,
        "material_mode": "generated",
        "generation_failures": len([r for r in results if not r]),  # 新增：记录失败数
    }
```

**删除 `_fallback_tryon()`（第 75-83 行）中的 Unsplash URL：**

改为返回 None 或抛出异常，让上层决定如何处理。

#### 文件 8：`frontend/src/App.vue`

**修复硬编码 "92 / 100"（第 233 行）：**

```html
<!-- 修改前 -->
<div class="metric-val score">92 / 100</div>

<!-- 修改后 -->
<div class="metric-val score">{{ resultData.opportunity_score?.total_score || resultData.market_insights?.launch_confidence_score || '--' }} / 100</div>
```

---

### 3.6 实现 Product Identity Lock

#### 文件 9：`backend/app/agent/nodes/studio.py`

**在 `studio_node` 中提取视觉特征并传入生图 prompt：**

```python
async def studio_node(state: AgentState) -> Dict[str, Any]:
    attrs = state.get("product_attributes", {})
    ...
    source_img = state.get("product_image_url") or ""

    # ── 新增：构建 Product Identity ──
    product_identity = _build_product_identity(attrs, source_img)

    if source_img:
        # 搬运模式：沿用原图（现有逻辑不变）
        ...
    else:
        # AI 生图模式：将 Product Identity 传入 prompt
        generated_assets = await _generate_ai_scenes(
            product_desc, family,
            identity=product_identity,  # 新增参数
        )
```

**新增 `_build_product_identity()` 函数：**

```python
def _build_product_identity(attrs: Dict, image_url: str) -> Dict:
    """从 product_attributes 提取视觉身份特征，确保 AI 生图时商品主体一致"""
    return {
        "product_name": attrs.get("title", ""),
        "category": attrs.get("category", ""),
        "main_color": attrs.get("main_color", ""),
        "materials": ", ".join(attrs.get("materials", [])),
        "design_features": ", ".join(attrs.get("design_features", [])[:5]),
        "reference_image": image_url,
        "visual_constraints": (
            f"Must preserve: {attrs.get('main_color', '')} color, "
            f"{', '.join(attrs.get('materials', []))} material, "
            f"{', '.join(attrs.get('design_features', [])[:3])} design elements"
        ),
    }
```

**修改 `_generate_ai_scenes()` 的 prompt 构建：**

```python
async def _generate_ai_scenes(product_desc, family, fallback_main="", identity=None):
    ...
    identity_constraint = ""
    if identity:
        identity_constraint = f"\nIMPORTANT: {identity['visual_constraints']}. The product in the image must match these exact characteristics."

    prompts = [
        f"professional e-commerce product photography, pure white background, {product_desc}{identity_constraint}, high detail, studio lighting"
    ]
    prompts += [
        f"lifestyle photography of {product_desc}{identity_constraint}, {t['scene']}, photorealistic, e-commerce hero image"
        for t in templates
    ]
```

---

### 3.7 修复 Asset Inventory 时序

#### 文件 10：`backend/app/agent/graph.py`

**方案：将 asset_inventory 拆为两个节点，或调整执行顺序。**

推荐方案：**调整执行顺序，让 asset_inventory 在 studio_generation 之后执行。**

修改 `route_next_step()` 中的节点顺序判断逻辑：

```python
# 修改前的顺序：
# ... → opportunity_score → asset_inventory → trend_benchmark → generate_listing → studio_generation → ...

# 修改后的顺序：
# ... → opportunity_score → trend_benchmark → generate_listing → studio_generation → asset_inventory → ...
```

**注意：** 这意味着 trend_benchmark 和 generate_listing 不再看到 asset_gap 的预分析结果。但这实际上是合理的——Listing 生成不需要知道素材缺口，素材缺口应该在内容生成后做最终盘点。

**或者，更保守的方案：保留两次 asset_inventory。**

第一次（opportunity_score 之后）：预分析，告诉 studio_node 需要生成什么。
第二次（studio_generation 之后）：最终盘点，包含 AI 生成的素材。

这需要在 graph.py 中添加一个新节点 `asset_inventory_final`，在 `studio_generation` 之后执行。

**推荐保守方案**，因为改动最小且不影响现有逻辑。

---

### 3.8 实现最小可用 Publish Package

#### 文件 11：`backend/app/agent/nodes/publish_package.py`

**新增导出功能：**

在 PublishPackage 构建完成后，生成一个可导出的 JSON 结构（后续可扩展为 ZIP）：

```python
# 在 publish_package_node 末尾新增
export_package = {
    "listing": listing_content,
    "keywords": listing_content.get("search_terms", []),
    "images": {
        "main": studio_assets.get("white_background_main", ""),
        "lifestyle": [s.get("image_url", "") for s in studio_assets.get("lifestyle_scenes", [])],
    },
    "pricing": {
        "supply_price_cny": attrs.get("supply_price_cny"),
        "recommended_range": market_insights.get("recommended_price_range", ""),
        "margin_est": market_insights.get("profit_margin_est", ""),
    },
    "compliance": platform_package.get("compliance_status", {}),
    "opportunity": opportunity_score,
    "health": listing_health,
    "metadata": {
        "platform": target_platform,
        "market": target_market,
        "generated_at": datetime.now().isoformat(),
        "source_url": attrs.get("source_url", ""),
    },
}
```

#### 文件 12：`backend/app/routers/v2.py`

**修复 `/v2/publish/review`（第 39-62 行）：**

```python
@router.post("/publish/review")
async def submit_publish_review(req: ReviewRequest):
    # 实际更新 TaskStore 中的审核状态
    store = TaskStore.get_instance()
    task = store.load_task(req.thread_id)
    if not task:
        raise HTTPException(404, "Task not found")

    # 更新审核决策
    publish_pkg = task.get("publish_package", {})
    publish_pkg["review_decision"] = req.decision
    publish_pkg["review_notes"] = req.notes
    publish_pkg["reviewed_at"] = time.time()

    store.save_task(req.thread_id, {**task, "publish_package": publish_pkg})

    return {
        "thread_id": req.thread_id,
        "decision": req.decision,
        "status": "updated",
        "publish_package": publish_pkg,
    }
```

**修复 `/v2/publish/execute`（第 65-78 行）：**

返回实际的 PublishPackage 数据而非 not_implemented：

```python
@router.post("/publish/execute")
async def execute_publish(req: ExecuteRequest):
    store = TaskStore.get_instance()
    task = store.load_task(req.thread_id)
    if not task:
        raise HTTPException(404, "Task not found")

    # 返回完整的 Publish Package（供前端导出）
    return {
        "status": "ready",
        "thread_id": req.thread_id,
        "package": task.get("publish_package"),
        "export_formats": ["json"],  # 后续可扩展 pdf/zip
    }
```

---

## 四、不改动的文件（明确保留）

| 文件 | 原因 |
|------|------|
| `app/intelligence/opportunity_scorer.py` | 评分算法本身正确，只需修复输入数据 |
| `app/intelligence/listing_health.py` | 8 维评分逻辑完整，无需修改 |
| `app/domain/*.py` | 领域模型设计合理，字段充足 |
| `app/sources/amazon_research.py` | 4 个 JustOneAPI 端点已实现，无需修改 |
| `app/sources/alibaba_1688.py` | JustOneAPI 1688 接口已实现 |
| `app/sources/shopee_research.py` | P1 冻结，代码保留不动 |
| `app/sources/tiktok_research.py` | P1 冻结，代码保留不动 |
| `app/channels/*.py` | 发布通道保持 dry_run，暂不实现 |
| `app/services/publisher.py` | 保持模拟发布，暂不对接 SP-API |
| `app/agent/nodes/trend.py` | 趋势分析节点无需修改 |
| `app/agent/nodes/listing.py` | Listing 生成逻辑无需修改（它读取的 market_insights 改善后自然改善）|
| `app/agent/nodes/localization.py` | 图片本地化无需修改 |
| `app/agent/nodes/video.py` | 视频生产冻结，保留现有逻辑 |
| `app/agent/nodes/respond.py` | 响应生成无需修改 |

---

## 五、需要新增的文件

**无。** 所有修改均在现有文件上进行。不需要创建新模块、新模型、新服务。

这是刻意为之——当前项目的核心问题不是缺代码，而是已有代码没有串起来。在 P0 链路打通之前，新增任何模块都是干扰。

---

## 六、实施顺序（建议按此顺序执行）

| 步骤 | 涉及文件 | 预计影响 | 验证方式 |
|------|----------|----------|----------|
| **Step 1：打通 1688 数据注入** | chat.py, state.py, App.vue | 解决断裂 1 | 在 initial_state 中打印 product_title/supply_price_cny 确认注入 |
| **Step 2：改造 product_node** | product.py | 解决断裂 2 | 检查 product_attributes 中是否包含 title 和 supply_price_cny |
| **Step 3：接入 Amazon 真实数据** | market.py | 解决断裂 3 | 检查 market_insights 中是否包含 competitors 和 data_sources |
| **Step 4：修复 OpportunityScorer 输入** | opportunity_score.py | 解决断裂 4 | 检查评分是否基于真实竞品和价格数据 |
| **Step 5：清除 Mock 污染** | studio.py, App.vue | 消除演示风险 | 生图失败时不再出现 Unsplash 图片 |
| **Step 6：Product Identity Lock** | studio.py | 提升生图一致性 | 对比生图前后的商品特征 |
| **Step 7：修复 Asset Inventory 时序** | graph.py | 解决断裂 5 | 检查最终 asset_inventory 是否包含 AI 生成素材 |
| **Step 8：Publish Package 可用化** | publish_package.py, v2.py | 闭环 | 能导出完整的上架包 JSON |

---

## 七、每个修改的验证标准

完成所有修改后，用一个 1688 商品 URL 跑一次完整流水线，检查：

| 检查点 | 期望结果 | 当前状态 |
|--------|----------|----------|
| initial_state 中有 title | `state["product_title"]` = "xxx" | ❌ 不存在 |
| initial_state 中有 price | `state["supply_price_cny"]` = 39.0 | ❌ 不存在 |
| product_attributes 有 title | `attrs["title"]` = 1688 真实标题 | ❌ 只有 VL 猜的 |
| product_attributes 有 price | `attrs["supply_price_cny"]` = 39.0 | ❌ 不存在 |
| market_insights 有竞品 | `insights["competitors"]` 非空 | ❌ 空 |
| market_insights 有数据源标记 | `insights["data_sources"]` 包含 "JustOneAPI" | ❌ 只有 "LLM" |
| OpportunityScore 有真实依据 | `score.supply_market_fit` 基于真实价格 | ❌ 基于默认值 |
| 前端置信度是动态值 | 分数随输入变化 | ❌ 固定 92/100 |
| 生图失败时无 Unsplash | `studio_assets.lifestyle_scenes` 只含 AI 图 | ❌ 含 Unsplash |
| asset_inventory 含 AI 素材 | `inventory.ai_generated_count` > 0 | ❌ 始终为 0 |
| publish_package 可导出 | `/v2/publish/execute` 返回完整包 | ❌ not_implemented |

---

## 八、风险控制

### 如果 JustOneAPI Key 失效怎么办？

market_node 有明确的降级路径：
1. 尝试 JustOneAPI → 成功 → 真实数据分析
2. JustOneAPI 失败 → 降级为纯 LLM 分析（现有逻辑）

不会导致流水线崩溃。

### 如果 1688 导入没有 title？

product_node 有明确降级：
1. 有 title + 有图片 → 真实数据 + VL 补充
2. 有 title + 无图片 → LLM 从标题推断
3. 无 title + 有图片 → VL 全量提取（现有逻辑）
4. 都没有 → 硬编码兜底（现有逻辑）

### 如果去掉 Unsplash 后生图全部失败？

studio_assets 中 lifestyle_scenes 为空列表。前端应显示"AI 场景图生成失败，请重试"而非空白。asset_inventory 会标记这些为缺口，gap analysis 会建议重新生成。

---

## 九、最终确认

这份方案**不新增任何功能模块**，只做 8 步修复，目标是把已有的真实能力（1688 数据、Amazon 数据、评分算法、AI 生图）串成一条不断的数据链。

完成后，GloLaunch 的 Demo 故事变为：

```
粘贴 1688 链接 → 真实商品数据导入 → Amazon 真实竞品分析 → 基于真实数据的机会评分
→ 素材缺口识别 → AI 场景图生成 → Listing 文案 → 质量评分 → 上架包导出
```

每一步都有真实数据支撑，没有 Mock，没有硬编码，没有 LLM 幻觉。
