import json
import time
from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import AgentState
from app.services.llm import get_flagship_llm
from app.services.vector_store import search_knowledge_base

PROMPT_MARKET_INSIGHT = """你是一名资深跨境电商选品操盘手与出海市场数据分析专家。
你需要结合商品属性信息、目标市场与本地电商知识库，对该商品进行深度出海市场洞察与选品评估。

请严格输出合法的 JSON 对象，不要包含任何 markdown 代码块标记，不要包含多余文字。
JSON 字段规范：
{
  "market_overview": "目标市场行业趋势概述（100字以内）",
  "recommended_price_range": "建议售价区间（如：$32.99 - $45.99）",
  "profit_margin_est": "预估毛利率空间（如：55% - 68%）",
  "target_audience": "核心目标客群画像描述",
  "buyer_pain_points": ["海外买家常见核心痛点/差评关注点（3-4点）"],
  "differentiation_angles": ["差异化打法与视觉卖点包装建议（3点）"],
  "high_converting_keywords": ["高转化搜索词/长尾词列表（5-8个）"],
  "launch_confidence_score": 0
}

注意：launch_confidence_score 必须基于你的真实分析判断，取值 0-100，不要编造固定值。
"""

PROMPT_MARKET_WITH_REAL_DATA = """你是一名资深跨境电商选品操盘手。
请基于以下【目标平台真实竞品数据】进行市场分析。
注意：价格、评分、评论数等数据必须基于下述真实数据，不要编造。

请严格输出合法的 JSON 对象，不要包含任何 markdown 代码块标记。
JSON 字段规范：
{
  "market_overview": "基于真实竞品数据的市场趋势概述（100字以内）",
  "recommended_price_range": "基于竞品价格分布的建议售价区间",
  "profit_margin_est": "基于供应价和竞品售价的预估毛利率",
  "target_audience": "核心目标客群画像描述",
  "buyer_pain_points": ["从竞品差评中提取的买家痛点（3-4点）"],
  "differentiation_angles": ["基于竞品缺口的差异化建议（3点）"],
  "high_converting_keywords": ["高转化搜索词/长尾词列表（5-8个）"],
  "launch_confidence_score": 0,
  "competitors": [
    {"asin": "", "title": "", "price": 0.0, "rating": 0.0, "review_count": 0}
  ],
  "top_keywords": [
    {"keyword": "", "search_volume": 0, "competition": "low/medium/high"}
  ]
}

注意：launch_confidence_score 必须基于真实数据分析，取值 0-100。
competitors 和 top_keywords 字段请从真实数据中提取填充。
"""

PROMPT_SEARCH_QUERY_GEN = """You are an e-commerce search query localization expert.
Your task: convert a Chinese product's key attributes into 2-5 natural English search queries
that an Amazon buyer would actually type into the search bar.

Rules:
1. Each query must be 2-6 words, concise and natural.
2. Only use facts explicitly present in the product attributes — NEVER invent features.
3. Prioritize the core product category, then material, then key features.
4. The first query should be the most general/high-volume one.
5. Subsequent queries can be more specific (long-tail).
6. Output ONLY a JSON array of strings, no markdown, no extra text.

Example input:  女士真丝连衣裙 夏季 碎花 V领
Example output: ["silk midi dress women", "floral v-neck summer dress", "women's casual silk dress"]
"""


async def _generate_search_queries(attrs: Dict) -> list:
    """Generate 2-5 English Amazon search queries from Chinese product attributes.

    Uses a lightweight LLM call to translate the product's core concepts
    (category, material, features) into natural English search queries
    that Amazon buyers would use.

    Returns:
        List of English search query strings (2-5 items).
        Falls back to [category] if LLM call fails.
    """
    from app.services.llm import get_fast_llm

    title = attrs.get("title", "")
    category = attrs.get("category", "")
    materials = attrs.get("materials", [])
    key_specs = attrs.get("key_specs", [])
    style_tags = attrs.get("style_tags", [])
    design_features = attrs.get("design_features", [])
    target_occasions = attrs.get("target_occasions", [])

    # If there's nothing to work with, fall back early
    if not title and not category:
        return []

    # Build a concise attribute summary for the LLM
    attr_parts = []
    if title:
        attr_parts.append(f"商品标题: {title}")
    if category:
        attr_parts.append(f"品类: {category}")
    if materials:
        attr_parts.append(f"材质: {', '.join(materials)}")
    if key_specs:
        attr_parts.append(f"关键规格: {', '.join(key_specs)}")
    if style_tags:
        attr_parts.append(f"风格/卖点: {', '.join(style_tags)}")
    if design_features:
        attr_parts.append(f"核心细节: {', '.join(design_features)}")
    if target_occasions:
        attr_parts.append(f"适用场景: {', '.join(target_occasions)}")

    attr_text = "\n".join(attr_parts)

    user_prompt = f"""Please generate 2-5 English Amazon search queries for this product:

{attr_text}

Output ONLY a JSON array of strings."""

    llm = get_fast_llm(temperature=0.2)
    try:
        messages = [
            SystemMessage(content=PROMPT_SEARCH_QUERY_GEN),
            HumanMessage(content=user_prompt),
        ]
        response = await llm.ainvoke(messages)
        content = response.content.strip()

        # Strip markdown code fences if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        queries = json.loads(content)
        if isinstance(queries, list) and len(queries) >= 1:
            # Ensure all items are strings and limit to 5
            queries = [str(q).strip() for q in queries[:5] if str(q).strip()]
            if queries:
                return queries
    except Exception:
        pass

    # Fallback: use category or title as-is (single query)
    fallback = title or category
    return [fallback] if fallback else []


async def _fetch_amazon_real_data(title: str, category: str, market: str, search_query: Optional[str] = None) -> Optional[Dict]:
    """调用 AmazonResearchSource 获取真实市场数据"""
    try:
        from app.sources.amazon_research import AmazonResearchSource
        source = AmazonResearchSource()
        if not await source.is_available():
            return None

        # Use the localized English search query if provided, otherwise fall back
        # to title/category (which may be Chinese and yield no Amazon results)
        search_query = search_query or title or category
        if not search_query:
            return None

        # 调用搜索和畅销榜
        search_results = await source.search_products(search_query, country=market)
        best_sellers = await source.get_best_sellers(category, country=market)

        if not search_results and not best_sellers:
            return None

        return {
            "sources": ["JustOneAPI:Amazon"],
            "freshness": time.strftime("%Y-%m"),
            "search_results": search_results,
            "best_sellers": best_sellers,
        }
    except Exception:
        return None


def _extract_competitors_from_search(search_data: Dict) -> list:
    """从 JustOneAPI Amazon 搜索结果中提取竞品列表"""
    competitors = []
    products = search_data.get("data", {}).get("products", []) if search_data else []
    for p in products[:15]:
        competitors.append({
            "asin": p.get("asin", ""),
            "title": p.get("title", "")[:80],
            "price": p.get("price"),
            "rating": p.get("rating"),
            "review_count": p.get("reviews", 0) if isinstance(p.get("reviews"), int) else 0,
        })
    return competitors


def _extract_competitors_from_tiktok(search_data: Dict) -> list:
    """从 JustOneAPI TikTok Shop 搜索结果中提取竞品列表
    实际响应结构: data.data.products (双层嵌套)
    价格: product_price_info.sale_price_decimal
    评分: rate_info.score
    """
    competitors = []
    if not search_data:
        return competitors
    # TikTok 响应为双层嵌套: body.data.data.products
    inner = search_data.get("data", {})
    if isinstance(inner, dict) and "data" in inner:
        inner = inner["data"]
    products = inner.get("products", []) or inner.get("items", [])
    for p in products[:15]:
        pid = str(p.get("product_id", "") or p.get("id", ""))
        title = (p.get("title", "") or p.get("name", ""))[:80]
        # 价格: product_price_info.sale_price_decimal 或 直接 price
        price_info = p.get("product_price_info", {})
        price = price_info.get("sale_price_decimal") if price_info else None
        if price is None:
            price = p.get("price") or p.get("min_price")
        # 评分: rate_info.score 或 直接 rating
        rate_info = p.get("rate_info", {})
        rating = rate_info.get("score") if rate_info else None
        if rating is None:
            rating = p.get("rating")
        review_count = 0
        if rate_info and rate_info.get("count"):
            review_count = rate_info["count"]
        elif isinstance(p.get("review_count"), int):
            review_count = p["review_count"]
        competitors.append({
            "asin": pid,
            "title": title,
            "price": price,
            "rating": rating,
            "review_count": review_count,
        })
    return competitors


def _extract_competitors_from_shopee(search_data: Dict) -> list:
    """从 JustOneAPI Shopee 搜索结果中提取竞品列表
    实际响应结构: data.cards
    价格: display_price (已解析的数值)
    """
    competitors = []
    if not search_data:
        return competitors
    data = search_data.get("data", {})
    # Shopee 响应: data.cards 列表
    cards = data.get("cards", []) or data.get("items", []) or data.get("products", [])
    for p in cards[:15]:
        item_id = str(p.get("item_id", "") or p.get("itemid", "") or p.get("id", ""))
        title = (p.get("title", "") or p.get("name", ""))[:80]
        # 价格: display_price (数值) 或 price_texts
        price = p.get("display_price")
        if price is None:
            price = p.get("price") or p.get("price_min")
        competitors.append({
            "asin": item_id,
            "title": title,
            "price": price,
            "rating": p.get("rating"),
            "review_count": 0,  # Shopee 搜索结果不直接提供评论数
        })
    return competitors


async def _fetch_tiktok_real_data(title: str, category: str, market: str) -> Optional[Dict]:
    """调用 TikTokResearchSource 获取 TikTok Shop 真实市场数据"""
    try:
        from app.sources.tiktok_research import TikTokResearchSource
        source = TikTokResearchSource()
        if not await source.is_available():
            return None

        search_query = title or category
        if not search_query:
            return None

        region = market if market in ("US", "GB", "FR", "SG", "MY", "PH", "TH", "VN", "ID") else "US"
        search_results = await source.search_products(search_query, region=region)

        if not search_results:
            return None

        return {
            "sources": ["JustOneAPI:TikTokShop"],
            "freshness": time.strftime("%Y-%m"),
            "search_results": search_results,
            "best_sellers": None,  # TikTok Shop 暂无 BSR 接口
        }
    except Exception:
        return None


async def _fetch_shopee_real_data(title: str, category: str, market: str) -> Optional[Dict]:
    """调用 ShopeeResearchSource 获取 Shopee 真实市场数据"""
    try:
        from app.sources.shopee_research import ShopeeResearchSource
        source = ShopeeResearchSource()
        if not await source.is_available():
            return None

        search_query = title or category
        if not search_query:
            return None

        site = market if market in ("TW", "ID", "TH") else "TW"
        search_results = await source.search_products(search_query, site=site)

        if not search_results:
            return None

        return {
            "sources": ["JustOneAPI:Shopee"],
            "freshness": time.strftime("%Y-%m"),
            "search_results": search_results,
            "best_sellers": None,  # Shopee 暂无 BSR 接口
        }
    except Exception:
        return None


async def _analyze_with_real_data(
    real_data: Dict, attrs: Dict, platform: str, market: str, kb_context: str
) -> Dict:
    """让 LLM 在真实数据基础上做分析，而非凭空生成"""
    # 根据平台选择对应的竞品提取器
    search_results = real_data.get("search_results") or {}
    if platform == "TikTok":
        competitors = _extract_competitors_from_tiktok(search_results)
    elif platform == "Shopee":
        competitors = _extract_competitors_from_shopee(search_results)
    else:
        competitors = _extract_competitors_from_search(search_results)

    competitors_summary = "\n".join([
        f"- {c.get('title','')[:60]} | ${c.get('price','')} | ★{c.get('rating','')} | {c.get('review_count',0)} reviews"
        for c in competitors[:10]
    ]) or "（无竞品数据）"

    supply_price = attrs.get("supply_price_cny")
    supply_price_text = f"¥{supply_price}" if supply_price else "未知"
    source_label = f"{platform} 真实竞品数据"

    user_prompt = f"""
【目标上架平台】：{platform} ({market} 站点)
【商品】：{attrs.get('title', attrs.get('category', ''))}
【供应价】：{supply_price_text}

【{source_label}】（来自 JustOneAPI）：
{competitors_summary}

【参考电商知识库】：
{kb_context}

请基于以上真实竞品数据，分析市场机会并输出 JSON 报告。
注意：价格分析必须基于上述真实竞品价格，不要编造。
"""
    llm = get_flagship_llm(temperature=0.3)
    try:
        messages = [
            SystemMessage(content=PROMPT_MARKET_WITH_REAL_DATA),
            HumanMessage(content=user_prompt)
        ]
        response = await llm.ainvoke(messages)
        content = response.content.strip()

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        insights = json.loads(content)
        # 确保真实竞品数据被保留到输出中
        if competitors and not insights.get("competitors"):
            insights["competitors"] = competitors
        return insights
    except Exception:
        # LLM 解析失败，返回基于真实数据的基本结构
        return _build_basic_insights_from_competitors(competitors, attrs, market)


def _build_basic_insights_from_competitors(competitors: list, attrs: Dict, market: str) -> Dict:
    """从竞品数据直接构建基本洞察（LLM 失败时的降级）"""
    prices = [c.get("price") for c in competitors if c.get("price")]
    avg_price = sum(prices) / len(prices) if prices else 0
    min_price = min(prices) if prices else 0
    max_price = max(prices) if prices else 0

    return {
        "market_overview": f"{market} 市场已有 {len(competitors)} 个同类竞品在售，价格区间 ${min_price:.0f}-${max_price:.0f}。",
        "recommended_price_range": f"${min_price:.2f} - ${max_price:.2f}" if prices else "",
        "profit_margin_est": "",
        "target_audience": "",
        "buyer_pain_points": [],
        "differentiation_angles": [],
        "high_converting_keywords": [],
        "launch_confidence_score": 0,
        "competitors": competitors,
        "top_keywords": [],
    }


async def _generate_llm_insights(attrs: Dict, platform: str, market: str, kb_context: str) -> Dict:
    """纯 LLM 生成（无真实数据时的降级路径）"""
    category = attrs.get("category", "商品")
    llm = get_flagship_llm(temperature=0.3)

    user_prompt = f"""
【目标上架平台】：{platform} ({market} 站点)
【商品识别属性】：
- 品类大类：{attrs.get('category_family', 'general')}
- 品类：{attrs.get('category', category)}
- 材质：{', '.join(attrs.get('materials', []))}
- 关键规格：{', '.join(attrs.get('key_specs', [])) or '未识别'}
- 风格/卖点：{', '.join(attrs.get('style_tags', []))}
- 核心细节：{', '.join(attrs.get('design_features', []))}
- 适用场景：{', '.join(attrs.get('target_occasions', []))}

【参考电商知识库】：
{kb_context}

请输出针对该商品的详细选品与出海市场洞察 JSON 报告。
"""
    try:
        messages = [
            SystemMessage(content=PROMPT_MARKET_INSIGHT),
            HumanMessage(content=user_prompt)
        ]
        response = await llm.ainvoke(messages)
        content = response.content.strip()

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return json.loads(content)
    except Exception:
        return {
            "market_overview": f"当前 {market} 市场数据获取失败，建议手动验证后再决策。",
            "recommended_price_range": "",
            "profit_margin_est": "",
            "target_audience": "",
            "buyer_pain_points": [],
            "differentiation_angles": [],
            "high_converting_keywords": [],
            "launch_confidence_score": 0,
            "data_sources": [],
        }


async def market_node(state: AgentState) -> Dict[str, Any]:
    """跨境出海市场洞察与选品决策节点
    优先调用 Amazon JustOneAPI 获取真实数据，LLM 在真实数据基础上分析。
    API 不可用时降级为纯 LLM 分析。
    """
    attrs = state.get("product_attributes", {})
    platform = state.get("target_platform", "Amazon")
    market = state.get("target_market", "US")
    category = attrs.get("category", state.get("product_category", ""))
    title = attrs.get("title", "")

    # 检索知识库上下文
    kb_context = search_knowledge_base(f"{market} {platform} {category} 趋势 痛点", top_k=2)

    # ── 搜索查询本地化：将中文标题转为英文 Amazon 搜索词 ──
    localized_search_queries = []
    amazon_search_query = None
    if platform == "Amazon":
        localized_search_queries = await _generate_search_queries(attrs)
        amazon_search_query = localized_search_queries[0] if localized_search_queries else None

    # ── 根据目标平台获取真实市场数据 ──
    real_market_data = None
    if platform == "Amazon":
        real_market_data = await _fetch_amazon_real_data(title, category, market, search_query=amazon_search_query)
    elif platform == "TikTok":
        real_market_data = await _fetch_tiktok_real_data(title, category, market)
    elif platform == "Shopee":
        real_market_data = await _fetch_shopee_real_data(title, category, market)

    if real_market_data:
        # 路径 A：有真实平台数据，LLM 在真实数据基础上分析
        insights = await _analyze_with_real_data(real_market_data, attrs, platform, market, kb_context)
        insights["data_sources"] = real_market_data.get("sources", [f"JustOneAPI:{platform}"])
        insights["data_freshness"] = real_market_data.get("freshness", "")
    else:
        # 路径 B：无真实数据，降级为纯 LLM
        insights = await _generate_llm_insights(attrs, platform, market, kb_context)
        insights["data_sources"] = ["LLM"]
        insights["data_freshness"] = ""

    # 将本地化搜索词附加到市场洞察输出中（供下游节点使用）
    if localized_search_queries:
        insights["localized_search_queries"] = localized_search_queries

    trace_item = {
        "node": "analyze_market",
        "status": "completed",
        "summary": (
            f"市场洞察完成（数据源: {', '.join(insights.get('data_sources', ['LLM']))}）："
            f"建议定价 {insights.get('recommended_price_range', '待定')}，"
            f"挖掘 {len(insights.get('high_converting_keywords', []))} 个高转化词"
        ),
        "timestamp": time.time(),
        "detail": insights
    }

    current_trace = state.get("trace", []) or []

    return {
        "market_insights": insights,
        "current_node": "analyze_market",
        "trace": current_trace + [trace_item]
    }
