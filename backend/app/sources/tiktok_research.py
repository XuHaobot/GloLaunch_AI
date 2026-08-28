"""TikTok Shop 数据采集源 —— JustOneAPI 统一接入。

接口清单（P1）：
  1. 商品搜索   GET /api/tiktok-shop/search-products/v1
  2. 商品详情   GET /api/tiktok-shop/get-product-detail/v1

区域代码: US / GB / FR / SG / MY / PH / TH / VN / ID
"""
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.domain.enums import DataSourceType
from app.domain.product_profile import ProductProfile
from app.domain.market_context import MarketContext, CompetitorSnapshot
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

# ── TikTok Shop 区域代码 ───────────────────────────────────────────────────────

TIKTOK_REGIONS = {
    "US": "US", "GB": "GB", "FR": "FR", "SG": "SG", "MY": "MY",
    "PH": "PH", "TH": "TH", "VN": "VN", "ID": "ID",
}


def _parse_price(price_val: Any) -> Optional[float]:
    if price_val is None:
        return None
    if isinstance(price_val, (int, float)):
        return float(price_val)
    if isinstance(price_val, str):
        m = re.search(r"[\d.]+", price_val.replace(",", ""))
        return float(m.group()) if m else None
    return None


class TikTokResearchSource(ResearchSource):
    """TikTok Shop 市场数据采集 —— JustOneAPI 2 接口集成"""

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.TIKTOK_SHOP

    @property
    def display_name(self) -> str:
        return "TikTok Shop 市场数据 (JustOneAPI)"

    async def is_available(self) -> bool:
        from app.config import get_settings
        s = get_settings()
        return bool(s.justoneapi_api_key)

    # ── 底层 HTTP 调用 ─────────────────────────────────────────────────────

    async def _request(self, path: str, params: Dict[str, Any]) -> Optional[Dict]:
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
            logger.warning("TikTok Shop JustOneAPI 请求超时 path=%s", path)
            return None
        except httpx.HTTPStatusError as e:
            logger.warning("TikTok Shop JustOneAPI HTTP %s path=%s", e.response.status_code, path)
            return None
        except Exception as e:
            logger.warning("TikTok Shop JustOneAPI 异常: %s path=%s", e, path)
            return None

        code = body.get("code", -1)
        if code != _JUSTONE_SUCCESS:
            msg = _JUSTONE_ERRORS.get(code, f"未知错误 (code={code})")
            logger.warning("TikTok Shop JustOneAPI 业务错误: %s path=%s", msg, path)
            return None

        return body

    # ── 接口 1: 商品搜索 ──────────────────────────────────────────────────

    async def search_products(
        self,
        keyword: str,
        region: str = "US",
        offset: int = 0,
        page_token: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        商品搜索 (V1)
        GET /api/tiktok-shop/search-products/v1
        """
        params: Dict[str, Any] = {
            "keyword": keyword,
            "region": region.upper(),
            "offset": offset,
        }
        if page_token:
            params["pageToken"] = page_token

        return await self._request("/api/tiktok-shop/search-products/v1", params)

    # ── 接口 2: 商品详情 ──────────────────────────────────────────────────

    async def get_product_detail(
        self,
        product_id: str,
        region: str = "US",
    ) -> Optional[Dict]:
        """
        商品详情 (V1)
        GET /api/tiktok-shop/get-product-detail/v1
        """
        params = {"productId": product_id, "region": region.upper()}
        return await self._request("/api/tiktok-shop/get-product-detail/v1", params)

    # ── ResearchSource 抽象方法实现 ────────────────────────────────────────

    async def import_product(self, url_or_id: str) -> Optional[ProductProfile]:
        """从 TikTok Shop 导入商品数据"""
        # 尝试提取 product_id（纯数字或 URL）
        product_id = url_or_id.strip()
        m = re.search(r"product[=/](\d+)", url_or_id, re.IGNORECASE)
        if m:
            product_id = m.group(1)
        elif not product_id.isdigit():
            logger.warning("无法从输入中提取 TikTok Shop product_id: %s", url_or_id)
            return None

        body = await self.get_product_detail(product_id=product_id)
        if not body:
            return None

        data = body.get("data", {})
        title = data.get("title", "") or data.get("name", "")
        images = data.get("images", []) or data.get("image_list", [])
        main_img = images[0] if images else ""

        import hashlib
        fingerprint = hashlib.sha256(f"tiktok:{product_id}:{title}".encode()).hexdigest()[:16]

        # 动态置信度：基于字段完整性
        confidence = _compute_confidence(
            data,
            required_fields=["title", "images", "price"],
            optional_fields=["description", "min_price", "sold_count"],
        )

        return ProductProfile(
            product_id=product_id,
            source_url=url_or_id if url_or_id.startswith("http") else "",
            source_platform="tiktok_shop",
            title=title,
            original_images=images,
            main_image_url=main_img,
            confidence=confidence,
            model_used="JustOneAPI TikTok Shop Product Detail V1",
            raw_extraction=data,
            identity_fingerprint=fingerprint,
        )

    async def fetch_market_data(
        self,
        category: str,
        market: str = "US",
        platform: str = "TikTok",
        keywords: Optional[List[str]] = None,
    ) -> Optional[MarketContext]:
        """获取 TikTok Shop 市场数据"""
        competitors: List[CompetitorSnapshot] = []
        raw_data: Dict[str, Any] = {}

        if keywords:
            for kw in keywords[:3]:
                result = await self.search_products(keyword=kw, region=market)
                if result:
                    items = result.get("data", {}).get("products", []) or result.get("data", {}).get("items", [])
                    for item in items[:5]:
                        pid = item.get("product_id", "") or item.get("id", "")
                        title = item.get("title", "") or item.get("name", "")
                        price = _parse_price(item.get("price") or item.get("min_price"))
                        img = (item.get("images", []) or [""])[0] if item.get("images") else item.get("image", "")

                        competitors.append(CompetitorSnapshot(
                            asin_or_id=str(pid),
                            title=title[:200],
                            price=price,
                            currency="USD",
                            listing_url=item.get("url", ""),
                        ))
                    raw_data[f"search_{kw}"] = result.get("data", {})

        if not competitors:
            return None

        # 去重
        seen = set()
        unique = []
        for c in competitors:
            if c.asin_or_id not in seen:
                seen.add(c.asin_or_id)
                unique.append(c)

        prices = [c.price for c in unique if c.price and c.price > 0]
        avg_price = sum(prices) / len(prices) if prices else None

        return MarketContext(
            data_sources=["JustOneAPI TikTok Shop Search"],
            competitors=unique[:15],
            avg_competitor_price=round(avg_price, 2) if avg_price else None,
            raw_data=raw_data,
        )
