"""Amazon 数据采集源 —— JustOneAPI 统一接入。

接口清单（P0）：
  1. 商品搜索   GET /api/amazon/search-products/v1
  2. 商品详情   GET /api/amazon/get-product-detail/v1
  3. 热门评论   GET /api/amazon/get-product-top-reviews/v1
  4. 热销商品   GET /api/amazon/get-best-sellers/v1

所有接口共用 JustOneAPI token 鉴权，120s 超时，统一错误码体系。
"""
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.domain.enums import DataSourceType
from app.domain.product_profile import ProductProfile
from app.domain.market_context import MarketContext, CompetitorSnapshot, KeywordData
from app.sources.base import ResearchSource, _compute_confidence

logger = logging.getLogger(__name__)

# ── JustOneAPI 统一错误码 ──────────────────────────────────────────────────────

_JUSTONE_SUCCESS = 0
_JUSTONE_ERRORS = {
    100: "Token 无效或已失效",
    301: "采集失败，请重试",
    302: "超出速率限制",
    303: "超出每日配额",
    400: "参数错误",
    500: "内部服务器错误",
    600: "权限不足",
    601: "账户余额不足",
    602: "TOKEN 限额超限",
}

# ── Amazon 国家代码映射 ────────────────────────────────────────────────────────

AMAZON_COUNTRIES = {
    "US": "US", "AU": "AU", "BR": "BR", "CA": "CA", "CN": "CN",
    "FR": "FR", "DE": "DE", "IN": "IN", "IT": "IT", "MX": "MX",
    "NL": "NL", "SG": "SG", "ES": "ES", "TR": "TR", "AE": "AE",
    "GB": "GB", "JP": "JP", "SA": "SA", "PL": "PL", "SE": "SE",
    "BE": "BE", "EG": "EG", "ZA": "ZA", "IE": "IE",
}

# ── 辅助函数 ───────────────────────────────────────────────────────────────────


def _extract_asin(url_or_asin: str) -> Optional[str]:
    """从 Amazon URL 或纯 ASIN 中提取 ASIN（10 位字母数字）"""
    url_or_asin = url_or_asin.strip()
    # 纯 ASIN
    if re.match(r"^[A-Z0-9]{10}$", url_or_asin, re.IGNORECASE):
        return url_or_asin.upper()
    # URL 中提取 /dp/ASIN 或 /gp/product/ASIN
    m = re.search(r"/(?:dp|gp/product|ASIN)/([A-Z0-9]{10})", url_or_asin, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # 查询参数 asin=
    m = re.search(r"[?&]asin=([A-Z0-9]{10})", url_or_asin, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None


def _parse_price(price_val: Any) -> Optional[float]:
    """安全解析价格"""
    if price_val is None:
        return None
    if isinstance(price_val, (int, float)):
        return float(price_val)
    if isinstance(price_val, str):
        m = re.search(r"[\d.]+", price_val.replace(",", ""))
        return float(m.group()) if m else None
    return None


def _map_search_to_competitors(items: List[Dict], top_k: int = 10) -> List[CompetitorSnapshot]:
    """将搜索结果映射为竞品快照列表（无 BSR 排名）"""
    competitors = []
    for item in items[:top_k]:
        asin = item.get("asin", "")
        title = item.get("title", "") or item.get("product_title", "")
        price = _parse_price(
            item.get("price") or item.get("price_value") or item.get("display_price")
        )
        rating = _parse_price(item.get("rating") or item.get("star_rating"))
        review_count = int(item.get("review_count", 0) or item.get("reviews", 0) or 0)
        img = item.get("image", "") or item.get("main_image", "") or item.get("thumbnail", "")
        url = item.get("url", "") or item.get("product_url", "")
        if not url and asin:
            url = f"https://www.amazon.com/dp/{asin}"

        competitors.append(CompetitorSnapshot(
            asin_or_id=asin,
            title=title[:200],
            price=price,
            currency="USD",
            rating=rating,
            review_count=review_count,
            listing_url=url,
        ))
    return competitors


def _map_bsr_to_competitors(items: List[Dict], top_k: int = 10) -> List[CompetitorSnapshot]:
    """将热销榜结果映射为竞品快照列表，位置索引即为 BSR 排名"""
    competitors = []
    for idx, item in enumerate(items[:top_k], start=1):
        asin = item.get("asin", "")
        title = item.get("title", "") or item.get("product_title", "")
        price = _parse_price(
            item.get("price") or item.get("price_value") or item.get("display_price")
        )
        rating = _parse_price(item.get("rating") or item.get("star_rating"))
        review_count = int(item.get("review_count", 0) or item.get("reviews", 0) or 0)
        img = item.get("image", "") or item.get("main_image", "") or item.get("thumbnail", "")
        url = item.get("url", "") or item.get("product_url", "")
        if not url and asin:
            url = f"https://www.amazon.com/dp/{asin}"

        # BSR 排名：优先 API 返回的 rank 字段，否则用位置索引
        bsr_rank = item.get("rank") or item.get("bsr_rank") or item.get("index") or idx

        competitors.append(CompetitorSnapshot(
            asin_or_id=asin,
            title=title[:200],
            price=price,
            currency="USD",
            rating=rating,
            review_count=review_count,
            bsr_rank=int(bsr_rank),
            listing_url=url,
        ))
    return competitors


# ── 主类 ───────────────────────────────────────────────────────────────────────


class AmazonResearchSource(ResearchSource):
    """Amazon 市场数据采集 —— JustOneAPI 4 接口集成"""

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.AMAZON

    @property
    def display_name(self) -> str:
        return "Amazon 市场数据 (JustOneAPI)"

    async def is_available(self) -> bool:
        from app.config import get_settings
        s = get_settings()
        return bool(s.justoneapi_api_key)

    # ── 底层 HTTP 调用 ─────────────────────────────────────────────────────

    async def _request(self, path: str, params: Dict[str, Any]) -> Optional[Dict]:
        """统一请求方法：自动注入 token、处理错误码"""
        from app.config import get_settings
        s = get_settings()
        if not s.justoneapi_api_key:
            return None

        url = f"{s.justoneapi_base_url}{path}"
        params["token"] = s.justoneapi_api_key

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                body = resp.json()
        except httpx.TimeoutException:
            logger.warning("Amazon JustOneAPI 请求超时 path=%s params=%s", path, params)
            return None
        except httpx.HTTPStatusError as e:
            logger.warning("Amazon JustOneAPI HTTP %s path=%s", e.response.status_code, path)
            return None
        except Exception as e:
            logger.warning("Amazon JustOneAPI 异常: %s path=%s", e, path)
            return None

        code = body.get("code", -1)
        if code != _JUSTONE_SUCCESS:
            msg = _JUSTONE_ERRORS.get(code, f"未知错误 (code={code})")
            logger.warning("Amazon JustOneAPI 业务错误: %s path=%s", msg, path)
            return None

        return body

    # ── 接口 1: 商品搜索 ──────────────────────────────────────────────────

    async def search_products(
        self,
        keyword: str,
        country: str = "US",
        sort_by: str = "RELEVANCE",
        product_condition: str = "ALL",
        is_prime: Optional[bool] = None,
        deals_and_discounts: Optional[str] = None,
        page: int = 1,
    ) -> Optional[Dict]:
        """
        商品搜索 (V1)
        GET /api/amazon/search-products/v1

        用途：搜索竞品、关键词验证、价格分布分析
        """
        params: Dict[str, Any] = {
            "keyword": keyword,
            "country": country.upper(),
            "sortBy": sort_by,
            "productCondition": product_condition,
            "page": page,
        }
        if is_prime is not None:
            params["isPrime"] = str(is_prime).lower()
        if deals_and_discounts:
            params["dealsAndDiscounts"] = deals_and_discounts

        return await self._request("/api/amazon/search-products/v1", params)

    # ── 接口 2: 商品详情 ──────────────────────────────────────────────────

    async def get_product_detail(
        self,
        asin: str,
        country: str = "US",
    ) -> Optional[Dict]:
        """
        商品详情 (V1)
        GET /api/amazon/get-product-detail/v1

        用途：获取竞品 Listing 结构、价格、卖点、图片
        """
        params = {"asin": asin, "country": country.upper()}
        return await self._request("/api/amazon/get-product-detail/v1", params)

    # ── 接口 3: 热门评论 ──────────────────────────────────────────────────

    async def get_product_top_reviews(
        self,
        asin: str,
        country: str = "US",
    ) -> Optional[Dict]:
        """
        商品热门评论 (V1)
        GET /api/amazon/get-product-top-reviews/v1

        用途：痛点挖掘、差异化文案方向、买家关注点分析
        """
        params = {"asin": asin, "country": country.upper()}
        return await self._request("/api/amazon/get-product-top-reviews/v1", params)

    # ── 接口 4: 热销商品 ──────────────────────────────────────────────────

    async def get_best_sellers(
        self,
        category: str,
        country: str = "US",
        page: int = 1,
    ) -> Optional[Dict]:
        """
        热销商品 (V1)
        GET /api/amazon/get-best-sellers/v1

        用途：品类热销趋势、BSR 排名追踪
        category: 亚马逊热销分类路径（如 "aps" 或 "electronics"）
        """
        params = {"category": category, "country": country.upper(), "page": page}
        return await self._request("/api/amazon/get-best-sellers/v1", params)

    # ── ResearchSource 抽象方法实现 ────────────────────────────────────────

    async def import_product(self, url_or_id: str) -> Optional[ProductProfile]:
        """从 Amazon ASIN 导入商品数据（用于竞品参考）"""
        asin = _extract_asin(url_or_id)
        if not asin:
            logger.warning("无法从输入中提取 ASIN: %s", url_or_id)
            return None

        body = await self.get_product_detail(asin)
        if not body:
            return None

        data = body.get("data", {})
        title = data.get("title", "") or data.get("product_title", "")
        price = _parse_price(data.get("price") or data.get("price_value"))
        images = data.get("images", []) or data.get("image_list", [])
        main_img = images[0] if images else ""

        import hashlib
        fingerprint = hashlib.sha256(f"{asin}:{title}".encode()).hexdigest()[:16]

        # 动态置信度：基于字段完整性
        confidence = _compute_confidence(
            data,
            required_fields=["title", "price", "images"],
            optional_fields=["description", "bullet_points", "rating", "review_count"],
        )

        return ProductProfile(
            product_id=asin,
            source_url=f"https://www.amazon.com/dp/{asin}",
            source_platform="amazon",
            title=title,
            supply_price_cny=None,
            original_images=images,
            main_image_url=main_img,
            confidence=confidence,
            model_used="JustOneAPI Amazon Product Detail V1",
            raw_extraction=data,
            identity_fingerprint=fingerprint,
        )

    async def fetch_market_data(
        self,
        category: str,
        market: str = "US",
        platform: str = "Amazon",
        keywords: Optional[List[str]] = None,
    ) -> Optional[MarketContext]:
        """
        获取 Amazon 市场数据 —— 聚合搜索 + 热销 + 评论。
        这是 Amazon 数据源的核心能力。
        """
        competitors: List[CompetitorSnapshot] = []
        raw_data: Dict[str, Any] = {}

        # 1) 关键词搜索 → 竞品列表
        if keywords:
            for kw in keywords[:3]:  # 最多搜 3 个关键词避免配额消耗
                result = await self.search_products(keyword=kw, country=market)
                if result:
                    items = result.get("data", {}).get("items", []) or result.get("data", {}).get("products", [])
                    competitors.extend(_map_search_to_competitors(items, top_k=5))
                    raw_data[f"search_{kw}"] = result.get("data", {})

        # 2) 热销榜 → 补充竞品（含 BSR 排名）
        bs_result = await self.get_best_sellers(category=category, country=market)
        if bs_result:
            bs_items = bs_result.get("data", {}).get("items", []) or bs_result.get("data", {}).get("products", [])
            competitors.extend(_map_bsr_to_competitors(bs_items, top_k=5))
            raw_data["best_sellers"] = bs_result.get("data", {})

        # 3) 去重（按 ASIN）
        seen_asins = set()
        unique_competitors = []
        for c in competitors:
            if c.asin_or_id and c.asin_or_id not in seen_asins:
                seen_asins.add(c.asin_or_id)
                unique_competitors.append(c)
            elif not c.asin_or_id:
                unique_competitors.append(c)
        competitors = unique_competitors[:15]

        # 4) 价格统计
        prices = [c.price for c in competitors if c.price and c.price > 0]
        avg_price = sum(prices) / len(prices) if prices else None
        price_dist: Dict[str, int] = {}
        for p in prices:
            bucket = f"${int(p // 10) * 10}-{int(p // 10) * 10 + 10}"
            price_dist[bucket] = price_dist.get(bucket, 0) + 1

        if not competitors and not raw_data:
            return None

        return MarketContext(
            data_sources=["JustOneAPI Amazon Search", "JustOneAPI Amazon Best Sellers"],
            competitors=competitors,
            avg_competitor_price=round(avg_price, 2) if avg_price else None,
            price_distribution=price_dist,
            raw_data=raw_data,
        )

    async def fetch_keywords(
        self,
        query: str,
        market: str = "US",
        platform: str = "Amazon",
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """基于搜索结果提取关键词（搜索结果的标题分词作为近似）"""
        result = await self.search_products(keyword=query, country=market)
        if not result:
            return []

        data = result.get("data", {})
        items = data.get("items", []) or data.get("products", [])
        keyword_results = []
        for item in items[:top_k]:
            title = item.get("title", "") or item.get("product_title", "")
            asin = item.get("asin", "")
            keyword_results.append({
                "keyword": title[:80],
                "asin": asin,
                "relevance": 1.0,
                "source": "JustOneAPI Amazon Search",
            })
        return keyword_results

    async def fetch_competitors(
        self,
        category: str,
        market: str = "US",
        platform: str = "Amazon",
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Amazon BSR 竞品数据采集（含 BSR 排名）"""
        result = await self.get_best_sellers(category=category, country=market)
        if not result:
            return []

        data = result.get("data", {})
        items = data.get("items", []) or data.get("products", [])
        competitors = []
        for idx, item in enumerate(items[:top_k], start=1):
            competitors.append({
                "asin": item.get("asin", ""),
                "title": item.get("title", "") or item.get("product_title", ""),
                "price": _parse_price(item.get("price") or item.get("price_value")),
                "rating": _parse_price(item.get("rating") or item.get("star_rating")),
                "review_count": int(item.get("review_count", 0) or item.get("reviews", 0) or 0),
                "bsr_rank": item.get("rank") or item.get("bsr_rank") or idx,
                "source": "JustOneAPI Amazon Best Sellers",
            })
        return competitors

    # ── 高级方法：评论分析 ────────────────────────────────────────────────

    async def analyze_reviews(
        self,
        asin: str,
        country: str = "US",
    ) -> Dict[str, Any]:
        """
        分析商品热门评论，提取痛点和买家关注点。
        供 OpportunityScorer 和 Listing 文案生成使用。
        """
        body = await self.get_product_top_reviews(asin=asin, country=country)
        if not body:
            return {"asin": asin, "reviews": [], "pain_points": [], "highlights": []}

        data = body.get("data", {})
        reviews_raw = data.get("reviews", []) or data.get("items", [])

        reviews = []
        for r in reviews_raw:
            reviews.append({
                "title": r.get("title", "") or r.get("review_title", ""),
                "body": r.get("body", "") or r.get("review_body", "") or r.get("content", ""),
                "rating": _parse_price(r.get("rating") or r.get("star_rating") or r.get("score")),
                "verified": r.get("verified_purchase", False),
                "helpful_count": int(r.get("helpful_count", 0) or 0),
            })

        return {
            "asin": asin,
            "reviews": reviews,
            "raw_data": data,
            "source": "JustOneAPI Amazon Top Reviews V1",
        }
