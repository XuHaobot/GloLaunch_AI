"""1688 数据采集源 —— JustOneAPI 第三方接口 + 官方 API 双通道。

JustOneAPI 文档: https://docs.justoneapi.com/zh/
接口: GET /api/1688/get-item-detail/v1?token=KEY&itemId=VALUE

多级降级策略：
  第一优先级：JustOneAPI 第三方接口（配置 token 即可用）
  第二优先级：1688 官方开放平台 API（需 app_key + app_secret + access_token）
  第三优先级：返回 None，由调用方触发页面抓取 / 图片识别降级
"""
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.domain.enums import CategoryFamily, DataSourceType
from app.domain.product_profile import ProductProfile
from app.domain.market_context import MarketContext
from app.sources.base import ResearchSource, _compute_confidence

logger = logging.getLogger(__name__)

# JustOneAPI 业务码含义
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

# 1688 商品 ID 正则（纯数字 10-18 位，或完整 URL 中提取）
_ITEM_ID_RE = re.compile(r"(?:offerId|id)[=/](\d{10,18})|/offer/(\d{10,18})")
_PURE_ID_RE = re.compile(r"^\d{10,18}$")


def _extract_item_id(url_or_id: str) -> Optional[str]:
    """从 1688 URL 或纯 ID 字符串中提取商品 ID"""
    url_or_id = url_or_id.strip()
    if _PURE_ID_RE.match(url_or_id):
        return url_or_id
    m = _ITEM_ID_RE.search(url_or_id)
    if m:
        return m.group(1) or m.group(2)
    # 尝试直接从 URL 路径中提取纯数字段
    parts = url_or_id.rstrip("/").split("/")
    for part in reversed(parts):
        if _PURE_ID_RE.match(part):
            return part
    return None


def _parse_1688_price(price_str: Any) -> Optional[float]:
    """将 1688 价格字符串转为 float"""
    if price_str is None:
        return None
    if isinstance(price_str, (int, float)):
        return float(price_str)
    if isinstance(price_str, str):
        m = re.search(r"[\d.]+", price_str)
        return float(m.group()) if m else None
    return None


def _infer_category_family(title: str, product_params: List[Dict]) -> CategoryFamily:
    """根据标题和参数粗略推断品类大类"""
    text = " ".join([title] + [p.get("value", "") for p in (product_params or [])]).lower()
    apparel_kw = {"裙", "裤", "衬衫", "t恤", "tshirt", "dress", "shirt", "jacket", "coat", "卫衣", "毛衣", "内衣", "泳衣"}
    shoes_kw = {"鞋", "靴", "sneaker", "shoe", "shoes", "boot", "boots", "sandal", "slipper", "拖鞋", "运动鞋"}
    bags_kw = {"包", "bag", "backpack", "handbag", "wallet", "钱包", "背包", "手提包"}
    electronics_kw = {"电子", "数码", "耳机", "earbud", "headphone", "charger", "cable", "手机壳", "手机膜"}
    home_kw = {"家居", "home", "kitchen", "bedding", "窗帘", "地毯", "收纳", "灯具"}
    beauty_kw = {"美妆", "beauty", "skincare", "makeup", "口红", "面膜", "护肤"}

    if any(kw in text for kw in apparel_kw):
        return CategoryFamily.APPAREL
    if any(kw in text for kw in shoes_kw):
        return CategoryFamily.SHOES
    if any(kw in text for kw in bags_kw):
        return CategoryFamily.BAGS
    if any(kw in text for kw in electronics_kw):
        return CategoryFamily.ELECTRONICS
    if any(kw in text for kw in home_kw):
        return CategoryFamily.HOME
    if any(kw in text for kw in beauty_kw):
        return CategoryFamily.BEAUTY
    return CategoryFamily.GENERAL


def _map_to_product_profile(raw: Dict[str, Any], item_id: str) -> ProductProfile:
    """将 JustOneAPI 返回的原始 data 字典映射为 ProductProfile"""
    data = raw.get("data", raw)  # 兼容直接传 data 或外层包裹

    # JustOneAPI 可能返回 JSON 编码字符串而非 dict，安全解析
    if isinstance(data, str):
        import json
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error("JustOneAPI data 字段 JSON 解析失败: %s", e)
            data = {}

    if not isinstance(data, dict):
        logger.error("JustOneAPI data 字段类型异常: %s (expected dict)", type(data).__name__)
        data = {}

    # -- 基础信息 (data.item.offerTitle) --
    item = data.get("item") or {}
    title = item.get("offerTitle", "") or ""
    # 降级：某些响应可能 title 在顶层（但非 tag 对象）
    if not title:
        top_title = data.get("title", "")
        if isinstance(top_title, str):
            title = top_title
    offer_id = str(item.get("offerId") or data.get("offer_id", item_id))

    # -- 供应商 --
    supplier = data.get("supplier_info") or data.get("supplierInfo") or {}
    supplier_name = supplier.get("company_name", "") or supplier.get("shop_name") or supplier.get("companyName", "")

    # -- 价格 (data.item.price -> data.price.priceModel.currentPrices) --
    raw_price = item.get("price")
    if raw_price:
        supply_price = _parse_1688_price(raw_price)
    else:
        price_data = data.get("price") or {}
        model = (price_data.get("priceModel") or {})
        tiers = model.get("currentPrices") or []
        supply_price = _parse_1688_price(tiers[0].get("price") if tiers else None)

    # -- 库存 / 发货 --
    stock_info = data.get("stock_info") or data.get("stockInfo") or {}
    moq = stock_info.get("moq")
    delivery_time_str = stock_info.get("delivery_time", "") or stock_info.get("deliveryTime", "")
    lead_time_days: Optional[int] = None
    dm = re.search(r"(\d+)", delivery_time_str)
    if dm:
        lead_time_days = int(dm.group(1))

    # -- 图片: mainPic.offerImgList -> mainPic.offerImages -> images 降级 --
    main_images: List[str] = []
    detail_images: List[str] = []
    main_pic = data.get("mainPic") or {}
    img_list = main_pic.get("offerImgList") or []
    main_images = [u for u in img_list if isinstance(u, str)]
    if not main_images:
        img_objs = main_pic.get("offerImages") or []
        for obj in img_objs:
            u = obj.get("imgUrl", "") if isinstance(obj, dict) else ""
            if u:
                main_images.append(u)
    if not main_images:
        for obj in (data.get("images") or []):
            if isinstance(obj, dict):
                u = obj.get("imageURI") or obj.get("size220x220ImageURI") or ""
            else:
                u = str(obj) if obj else ""
            if u:
                main_images.append(u)
            if len(main_images) >= 8:
                break
    all_images = main_images + detail_images

    # -- 产品参数 -> 属性提取 (data.attribute.propsList) --
    product_params: List[Dict] = []
    attr = data.get("attribute") or {}
    for prop in (attr.get("propsList") or []):
        product_params.append({"name": prop.get("name", ""), "value": prop.get("value", "")})
    # 降级：旧路径
    if not product_params:
        product_params = data.get("product_params", []) or []
    materials: List[str] = []
    design_features: List[str] = []
    key_specs: List[str] = []

    for param in product_params:
        name = (param.get("name") or "").lower()
        value = param.get("value", "")
        if not value:
            continue
        if any(kw in name for kw in ("面料", "材质", "material", "成分", "fabric")):
            materials.append(value)
        elif any(kw in name for kw in ("版型", "风格", "style", "design", "工艺")):
            design_features.append(value)
        else:
            key_specs.append(f"{param.get('name', '')}: {value}")

    # -- SKU -> 颜色 / 尺码 (从 propsList 的 value 中解析) --
    colors: List[str] = []
    sizes: List[str] = []
    _color_kw = {"红", "橙", "黄", "绿", "蓝", "紫", "黑", "白", "灰", "粉", "棕", "金", "银", "米", "卡其", "驼", "藏青", "军绿",
                 "red", "blue", "black", "white", "green", "pink", "gray", "grey", "yellow", "purple", "brown", "beige", "khaki"}
    _size_kw = {"xs", "s", "m", "l", "xl", "xxl", "xxxl", "均码", "one size", "free size", "cm", "码"}

    seen_colors, seen_sizes = set(), set()
    # 优先从 sku_list 解析（如果存在）
    sku_list: List[Dict] = data.get("sku_list") or data.get("skuList") or []
    for sku in sku_list:
        spec = (sku.get("spec_text", "") or sku.get("specText", "") or "").lower()
        for token in re.split(r"[\s,/，、]+", spec):
            token_stripped = token.strip()
            if not token_stripped:
                continue
            if any(kw in token_stripped for kw in _color_kw) and token_stripped not in seen_colors:
                colors.append(token_stripped)
                seen_colors.add(token_stripped)
            if any(kw in token_stripped for kw in _size_kw) and token_stripped not in seen_sizes:
                sizes.append(token_stripped)
                seen_sizes.add(token_stripped)
    # 降级：从产品参数的值中尝试提取颜色/尺码
    if not colors and not sizes:
        for param in product_params:
            value = param.get("value", "")
            if not value:
                continue
            for token in re.split(r"[,，、/\s]+", value):
                t = token.strip().lower()
                if not t:
                    continue
                if any(kw in t for kw in _color_kw) and t not in seen_colors:
                    colors.append(t)
                    seen_colors.add(t)
                if any(kw in t for kw in _size_kw) and t not in seen_sizes:
                    sizes.append(t)
                    seen_sizes.add(t)

    # ── 品类推断 ──
    category_family = _infer_category_family(title, product_params)

    # ── 身份指纹 ──
    import hashlib
    fingerprint_src = f"{offer_id}:{title}:{supplier_name}"
    identity_fingerprint = hashlib.sha256(fingerprint_src.encode()).hexdigest()[:16]

    # ── 动态置信度：基于字段完整性 ──
    confidence = _compute_confidence(
        data,
        required_fields=["item", "mainPic", "price", "attribute"],
        optional_fields=["stock_info", "stockInfo", "supplier_info"],
    )

    return ProductProfile(
        product_id=offer_id,
        source_url=data.get("source_url", "") or f"https://detail.1688.com/offer/{offer_id}.html",
        source_platform="1688",
        category_family=category_family,
        category=title[:50] if title else "",
        title=title,
        materials=materials,
        colors=colors,
        sizes=sizes,
        key_specs=key_specs[:10],
        design_features=design_features,
        supply_price_cny=supply_price,
        moq=moq,
        lead_time_days=lead_time_days,
        supplier_id=str(supplier.get("member_id", "")),
        supplier_name=supplier_name,
        original_images=all_images,
        main_image_url=main_images[0] if main_images else "",
        confidence=confidence,
        model_used="JustOneAPI 1688 Product Detail V1",
        raw_extraction=data,
        identity_fingerprint=identity_fingerprint,
    )


class Alibaba1688Source(ResearchSource):
    """1688 数据采集源 —— JustOneAPI 优先 + 官方 API 降级"""

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.ALIBABA_1688

    @property
    def display_name(self) -> str:
        return "1688 (JustOneAPI / 官方 API)"

    async def is_available(self) -> bool:
        """JustOneAPI token 或官方 API 凭证任一配置即可用"""
        from app.config import get_settings
        s = get_settings()
        has_justone = bool(s.justoneapi_api_key)
        has_official = bool(s.ali1688_app_key and s.ali1688_app_secret and s.ali1688_access_token)
        return has_justone or has_official

    async def import_product(self, url_or_id: str) -> Optional[ProductProfile]:
        """
        从 1688 导入商品。
        优先级：JustOneAPI → 官方 API → None（触发上层降级）
        """
        item_id = _extract_item_id(url_or_id)
        if not item_id:
            logger.warning("无法从输入中提取 1688 商品 ID: %s", url_or_id)
            return None

        # 第一优先级：JustOneAPI
        result = await self._fetch_via_justoneapi(item_id)
        if result is not None:
            return _map_to_product_profile(result, item_id)

        # 第二优先级：1688 官方 API
        result = await self._fetch_via_official_api(item_id)
        if result is not None:
            return _map_to_product_profile(result, item_id)

        logger.info("1688 数据获取失败（JustOneAPI + 官方 API 均不可用），返回 None 触发上层降级")
        return None

    async def _fetch_via_justoneapi(self, item_id: str) -> Optional[Dict[str, Any]]:
        """通过 JustOneAPI 获取 1688 商品详情"""
        from app.config import get_settings
        s = get_settings()
        if not s.justoneapi_api_key:
            return None

        url = f"{s.justoneapi_base_url}/api/1688/get-item-detail/v1"
        params = {"token": s.justoneapi_api_key, "itemId": item_id}

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                body = resp.json()
        except httpx.TimeoutException:
            logger.warning("JustOneAPI 1688 请求超时 (itemId=%s)", item_id)
            return None
        except httpx.HTTPStatusError as e:
            logger.warning("JustOneAPI 1688 HTTP 错误 %s (itemId=%s)", e.response.status_code, item_id)
            return None
        except Exception as e:
            logger.warning("JustOneAPI 1688 请求异常: %s (itemId=%s)", e, item_id)
            return None

        code = body.get("code", -1)
        if code != _JUSTONE_SUCCESS:
            msg = _JUSTONE_ERRORS.get(code, f"未知错误 (code={code})")
            logger.warning("JustOneAPI 1688 业务错误: %s (itemId=%s)", msg, item_id)
            return None

        # 验证 data 字段不为空（API 可能返回 code=0 但 data=""）
        data = body.get("data")
        if not data:
            logger.warning("JustOneAPI 1688 返回空数据 (code=0, data 为空, itemId=%s)", item_id)
            return None

        return body

    async def _fetch_via_official_api(self, item_id: str) -> Optional[Dict[str, Any]]:
        """通过 1688 官方开放平台 API 获取商品详情（骨架，待凭证配置后启用）"""
        from app.config import get_settings
        s = get_settings()
        if not (s.ali1688_app_key and s.ali1688_app_secret and s.ali1688_access_token):
            return None

        # TODO: 实现官方 API 调用（签名 + 请求）
        # 参考: https://open.1688.com/
        logger.info("1688 官方 API 调用待实现 (itemId=%s)", item_id)
        return None

    async def fetch_market_data(
        self,
        category: str,
        market: str = "US",
        platform: str = "Amazon",
        keywords: Optional[List[str]] = None,
    ) -> Optional[MarketContext]:
        """1688 主要提供供给侧数据（价格、MOQ、供应商），不直接提供目标市场数据"""
        return None

    async def fetch_supply_data(self, offer_id: str) -> Dict[str, Any]:
        """获取 1688 供给侧数据（供货价、MOQ、发货周期等）"""
        result = await self._fetch_via_justoneapi(offer_id)
        if not result:
            result = await self._fetch_via_official_api(offer_id)
        if not result:
            return {}

        data = result.get("data", result)

        # JustOneAPI 可能返回 JSON 编码字符串而非 dict
        if isinstance(data, str):
            import json
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                data = {}
        if not isinstance(data, dict):
            data = {}

        item = data.get("item") or {}
        # 价格: item.price -> price.priceModel.currentPrices
        raw_price = item.get("price")
        retail_price = None
        step_prices = []
        if raw_price:
            retail_price = _parse_1688_price(raw_price)
        else:
            price_data = data.get("price") or {}
            model = price_data.get("priceModel") or {}
            tiers = model.get("currentPrices") or []
            if tiers:
                retail_price = _parse_1688_price(tiers[0].get("price"))
                step_prices = [{"begin_amount": t.get("beginAmount"), "price": t.get("price")} for t in tiers]
        # 库存 / 发货
        stock_info = data.get("stock_info") or data.get("stockInfo") or {}
        supplier = data.get("supplier_info") or data.get("supplierInfo") or {}

        return {
            "offer_id": offer_id,
            "retail_price": retail_price,
            "step_prices": step_prices,
            "moq": stock_info.get("moq"),
            "total_stock": stock_info.get("total_stock") or stock_info.get("totalStock"),
            "delivery_time": stock_info.get("delivery_time") or stock_info.get("deliveryTime"),
            "delivery_place": stock_info.get("delivery_place") or stock_info.get("deliveryPlace"),
            "supplier_name": supplier.get("company_name") or supplier.get("shop_name") or supplier.get("companyName"),
            "month_sales": (data.get("sales_info") or data.get("salesInfo") or {}).get("month_sales"),
        }
