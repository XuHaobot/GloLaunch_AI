"""Shopee 数据采集源 —— JustOneAPI 统一接入。

接口清单（P1）：
  1. 商品搜索   GET /api/shopee/search-item-list/v1
  2. 商品详情   GET /api/shopee/get-item-detail/v1

站点代码: TW(台湾) / ID(印尼) / TH(泰国)
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

# ── Shopee 站点代码 ────────────────────────────────────────────────────────────

SHOPEE_SITES = {
    "TW": "TW",   # 台湾
    "ID": "ID",   # 印度尼西亚
    "TH": "TH",   # 泰国
}

# 站点 → 货币映射
_SITE_CURRENCY = {"TW": "TWD", "ID": "IDR", "TH": "THB"}


def _parse_price(price_val: Any) -> Optional[float]:
    if price_val is None:
        return None
    if isinstance(price_val, (int, float)):
        return float(price_val)
    if isinstance(price_val, str):
        m = re.search(r"[\d.]+", price_val.replace(",", ""))
        return float(m.group()) if m else None
    return None


def _extract_item_id(url_or_id: str) -> Optional[str]:
    """从 Shopee URL 或纯 ID 中提取商品 ID"""
    url_or_id = url_or_id.strip()
    if url_or_id.isdigit():
        return url_or_id
    # i.{shop_id}.{item_id} 格式（Shopee 标准 URL）
    m = re.search(r"i\.\d+\.(\d+)", url_or_id)
    if m:
        return m.group(1)
    # /item/ 或 -i.{shopid}.{itemid} 路径
    m = re.search(r"/item[/.](\d+)", url_or_id, re.IGNORECASE)
    if m:
        return m.group(1)
    # 兜底：从 URL 路径中提取最后一段纯数字（>=8 位）
    parts = url_or_id.rstrip("/").split("/")
    for part in reversed(parts):
        clean = re.sub(r"[^0-9]", "", part.split("-")[-1] if "-" in part else part)
        if len(clean) >= 8 and clean.isdigit():
            return clean
    return None


def _infer_site_from_url(url: str) -> Optional[str]:
    """从 URL 推断 Shopee 站点"""
    url_lower = url.lower()
    if "shopee.tw" in url_lower:
        return "TW"
    if "shopee.co.id" in url_lower or "shopee.id" in url_lower:
        return "ID"
    if "shopee.co.th" in url_lower or "shopee.th" in url_lower:
        return "TH"
    return None


class ShopeeResearchSource(ResearchSource):
    """Shopee 市场数据采集 —— JustOneAPI 2 接口集成"""

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.SHOPEE

    @property
    def display_name(self) -> str:
        return "Shopee 市场数据 (JustOneAPI)"

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
            logger.warning("Shopee JustOneAPI 请求超时 path=%s", path)
            return None
        except httpx.HTTPStatusError as e:
            logger.warning("Shopee JustOneAPI HTTP %s path=%s", e.response.status_code, path)
            return None
        except Exception as e:
            logger.warning("Shopee JustOneAPI 异常: %s path=%s", e, path)
            return None

        code = body.get("code", -1)
        if code != _JUSTONE_SUCCESS:
            msg = _JUSTONE_ERRORS.get(code, f"未知错误 (code={code})")
            logger.warning("Shopee JustOneAPI 业务错误: %s path=%s", msg, path)
            return None

        return body

    # ── 接口 1: 商品搜索 ──────────────────────────────────────────────────

    async def search_products(
        self,
        keyword: str,
        site: str = "TW",
    ) -> Optional[Dict]:
        """
        商品搜索 (V1)
        GET /api/shopee/search-item-list/v1
        """
        params = {"keyword": keyword, "site": site.upper()}
        return await self._request("/api/shopee/search-item-list/v1", params)

    # ── 接口 2: 商品详情 ──────────────────────────────────────────────────

    async def get_product_detail(
        self,
        item_id: str,
        site: str = "TW",
    ) -> Optional[Dict]:
        """
        商品详情 (V1)
        GET /api/shopee/get-item-detail/v1
        """
        params = {"itemId": item_id, "site": site.upper()}
        return await self._request("/api/shopee/get-item-detail/v1", params)

    # ── ResearchSource 抽象方法实现 ────────────────────────────────────────

    async def import_product(self, url_or_id: str) -> Optional[ProductProfile]:
        """从 Shopee 导入商品数据"""
        item_id = _extract_item_id(url_or_id)
        if not item_id:
            logger.warning("无法从输入中提取 Shopee item_id: %s", url_or_id)
            return None

        # 推断站点
        site = _infer_site_from_url(url_or_id) or "TW"

        body = await self.get_product_detail(item_id=item_id, site=site)
        if not body:
            return None

        data = body.get("data", {})
        title = data.get("name", "") or data.get("title", "")
        images = data.get("images", []) or data.get("image_list", [])
        main_img = images[0] if images else ""
        price = _parse_price(data.get("price") or data.get("price_min"))

        import hashlib
        fingerprint = hashlib.sha256(f"shopee:{site}:{item_id}:{title}".encode()).hexdigest()[:16]

        # 动态置信度：基于字段完整性
        confidence = _compute_confidence(
            data,
            required_fields=["name", "price", "images"],
            optional_fields=["description", "models", "categories", "shop_location"],
        )

        return ProductProfile(
            product_id=item_id,
            source_url=url_or_id if url_or_id.startswith("http") else "",
            source_platform="shopee",
            title=title,
            supply_price_cny=price,  # Shopee 价格作为参考
            original_images=images,
            main_image_url=main_img,
            confidence=confidence,
            model_used="JustOneAPI Shopee Item Detail V1",
            raw_extraction=data,
            identity_fingerprint=fingerprint,
        )

    async def fetch_market_data(
        self,
        category: str,
        market: str = "TW",
        platform: str = "Shopee",
        keywords: Optional[List[str]] = None,
    ) -> Optional[MarketContext]:
        """获取 Shopee 市场数据"""
        competitors: List[CompetitorSnapshot] = []
        raw_data: Dict[str, Any] = {}
        site = market.upper() if market.upper() in SHOPEE_SITES else "TW"
        currency = _SITE_CURRENCY.get(site, "TWD")

        if keywords:
            for kw in keywords[:3]:
                result = await self.search_products(keyword=kw, site=site)
                if result:
                    # Shopee 响应: data.cards 列表（非 items/products）
                    data = result.get("data", {})
                    cards = data.get("cards", []) or data.get("items", []) or data.get("products", [])
                    for item in cards[:5]:
                        item_id = str(item.get("item_id", "") or item.get("itemid", "") or item.get("id", ""))
                        title = (item.get("title", "") or item.get("name", ""))[:80]
                        # 价格: display_price (数值) -> price -> price_min
                        price = _parse_price(item.get("display_price"))
                        if price is None:
                            price = _parse_price(item.get("price") or item.get("price_min"))
                        # Shopee 价格通常需要除以 100000（IDR）或 100（TWD/THB），
                        # 但 JustOneAPI 可能已做转换，这里保持原值
                        img = (item.get("images", []) or [""])[0] if item.get("images") else item.get("image", "")
                        sold = int(item.get("sold", 0) or item.get("historical_sold", 0) or 0)

                        competitors.append(CompetitorSnapshot(
                            asin_or_id=item_id,
                            title=title[:200],
                            price=price,
                            currency=currency,
                            monthly_sales_est=sold if sold else None,
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
            data_sources=["JustOneAPI Shopee Search"],
            competitors=unique[:15],
            avg_competitor_price=round(avg_price, 2) if avg_price else None,
            raw_data=raw_data,
        )
