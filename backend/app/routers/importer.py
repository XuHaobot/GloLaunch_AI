"""商品导入：解析 1688 商品链接，提取标题/主图/属性，预填充上新表单。

双通道策略：
1. 官方 API 优先：配置了 1688 开放平台凭证（AppKey/AppSecret/access_token）时，
   调用 com.alibaba.product.getProductInfo 稳定获取结构化商品信息（HMAC-SHA1 签名）
2. 页面抓取兜底：未配置凭证或官方调用失败时，尽力而为（best-effort）解析详情页：
   优先从页面内嵌的全局数据对象（如 window.__INIT_DATA / detailData）中抽取结构化字段，
   失败时返回明确提示，引导用户手动填写。
"""
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
import httpx

from app.config import get_settings

router = APIRouter(prefix="/api/import", tags=["商品导入"])

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.1688.com/",
}

class ImportRequest(BaseModel):
    url: str

def _extract_offer_id(url: str) -> Optional[str]:
    """从 1688 商品链接中提取 offerId（detail.1688.com/offer/{id}.html）"""
    m = re.search(r"offer/(\d+)", url)
    return m.group(1) if m else None

def _sign_params(app_secret: str, path_segment: str, params: Dict[str, str]) -> str:
    """1688 开放平台签名：HMAC-SHA1(密钥, 路径段 + 参数按键升序拼接 keyvalue)，结果转大写十六进制"""
    sign_src = path_segment + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(app_secret.encode("utf-8"), sign_src.encode("utf-8"), hashlib.sha1).digest()
    return digest.hex().upper()

def _normalize_image_url(img: str) -> str:
    """官方 API 返回的图片可能无协议前缀，统一补全"""
    if img.startswith("http"):
        return img
    return f"https://cbu01.alicdn.com/{img.lstrip('/')}"

def _token_file_path() -> str:
    return os.path.join(get_settings().data_dir, "ali1688_token.json")

def _load_saved_token() -> Dict[str, Any]:
    """读取 OAuth 授权后本地保存的 token（免去手动粘贴 .env）"""
    try:
        with open(_token_file_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

def _resolve_access_token() -> str:
    """优先 .env 手动配置，其次本地 OAuth 保存的 token"""
    settings = get_settings()
    if settings.ali1688_access_token:
        return settings.ali1688_access_token
    return _load_saved_token().get("access_token", "")

async def _import_via_open_api(url: str) -> Dict[str, Any]:
    """官方 API 通道：com.alibaba.product.getProductInfo，返回与抓取通道一致的 product 结构"""
    settings = get_settings()
    offer_id = _extract_offer_id(url)
    if not offer_id:
        raise ValueError("无法从链接中解析出商品 ID")

    namespace, api_name = "cn.alibaba.open", "com.alibaba.product.getProductInfo"
    params = {
        "offerId": offer_id,
        "webSite": "1688",
        "access_token": _resolve_access_token(),
    }
    path_segment = f"param2/1/{namespace}/{api_name}/{settings.ali1688_app_key}"
    params["_aop_signature"] = _sign_params(settings.ali1688_app_secret, path_segment, params)
    target = f"{settings.ali1688_gateway.rstrip('/')}/{path_segment}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(target, data=params)
        data = resp.json()

    if "error_code" in data or "error_message" in data:
        raise RuntimeError(f"官方 API 返回错误: {data.get('error_code')} {data.get('error_message')}")

    info = (data.get("result") or {}).get("result") or {}
    if not info:
        raise RuntimeError("官方 API 未返回商品信息（可能凭证失效或商品已下架）")

    images: List[str] = [_normalize_image_url(i) for i in (info.get("imageList") or [])]
    extra_images = (info.get("image") or {}).get("images") or []
    for img in extra_images:
        u = _normalize_image_url(img)
        if u not in images and len(images) < 8:
            images.append(u)

    sale = info.get("productSaleInfo") or {}
    price_ranges = sale.get("priceRanges") or []
    price = f"¥{price_ranges[0].get('price')}" if price_ranges and price_ranges[0].get("price") else None

    sku_attributes: Dict[str, List[str]] = {}
    for sku in (info.get("productSkuInfos") or [])[:20]:
        for attr in (sku.get("skuAttributes") or []):
            name = attr.get("name") or attr.get("attributeName")
            value = attr.get("value") or attr.get("attributeValue") or ""
            if name:
                sku_attributes.setdefault(name, [])
                if value and value not in sku_attributes[name]:
                    sku_attributes[name].append(value)
    # 降级：从 productAttribute 补充（只有名称，无具体值）
    if not sku_attributes:
        for attr in (info.get("productAttribute") or [])[:8]:
            name = attr.get("attributeName")
            values = attr.get("attributeValues") or []
            if name:
                sku_attributes[name] = [v for v in values if v] if values else []
    # 限制最多 8 个属性
    sku_attributes = dict(list(sku_attributes.items())[:8])

    return {
        "success": True,
        "message": "官方 API 解析成功",
        "product": {
            "title": info.get("subject"),
            "main_image": images[0] if images else None,
            "images": images,
            "source_price": price,
            "sku_attributes": sku_attributes,
            "source_url": url,
        },
    }

def _extract_title(html: str) -> Optional[str]:
    # 页面标题通常形如 "xxx-批发价格-厂家货源 -阿里巴巴"
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    if not m:
        return None
    title = m.group(1).strip()
    title = re.split(r"[-_|]", title)[0].strip()
    return title or None

def _extract_images(html: str) -> list:
    # 1688 商品图通常托管在 cbu01.alicdn.com
    imgs = re.findall(r"https://cbu01\.alicdn\.com/[^\s\"'<>\\]+\.(?:jpg|jpeg|png|webp)", html)
    # 去重并保持顺序，取前 8 张
    seen = set()
    result = []
    for url in imgs:
        if url not in seen:
            seen.add(url)
            result.append(url)
        if len(result) >= 8:
            break
    return result

def _extract_json_blobs(html: str) -> list:
    """抽取页面内嵌的全局数据对象文本（不同页面版本字段名不同）"""
    blobs = []
    for pattern in [
        r"window\.__INIT_DATA\s*=\s*(\{.*?\});?\s*</script>",
        r"window\.detailData\s*=\s*(\{.*?\});?\s*</script>",
    ]:
        for m in re.finditer(pattern, html, re.S):
            blobs.append(m.group(1))
    return blobs

def _parse_from_blobs(blobs: list) -> Dict[str, Any]:
    info: Dict[str, Any] = {}
    for blob in blobs:
        try:
            data = json.loads(blob)
        except (json.JSONDecodeError, ValueError):
            continue
        text = json.dumps(data, ensure_ascii=False)
        if not info.get("price"):
            m = re.search(r'"price"\s*:\s*"?([\d.]+)', text)
            if m:
                info["price"] = f"¥{m.group(1)}"
        if not info.get("sku_attributes"):
            # 尽力抽取 SKU 属性，构建 Dict[str, List[str]]
            sku_map: Dict[str, List[str]] = {}
            # 尝试匹配 name-value 对
            pairs = re.findall(
                r'"(?:prop|attrName|skuName)"\s*:\s*"([^"]{1,12})"\s*[,}].*?"(?:value|attrValue|skuValue)"\s*:\s*"([^"]{0,50})"',
                text,
            )
            for name, value in pairs:
                if name:
                    sku_map.setdefault(name, [])
                    if value and value not in sku_map[name]:
                        sku_map[name].append(value)
            # 降级：只有名称无值
            if not sku_map:
                keys = re.findall(r'"(?:prop|attrName|skuName)"\s*:\s*"([^"]{1,12})"', text)
                for k in dict.fromkeys(keys)[:8]:
                    sku_map[k] = []
            info["sku_attributes"] = dict(list(sku_map.items())[:8])
    return info

@router.get("/1688/oauth/start")
async def oauth_start():
    """跳转 1688 授权页：用户登录并确认授权后携带 code 回调本服务"""
    settings = get_settings()
    if not settings.ali1688_app_key or not settings.ali1688_app_secret:
        return HTMLResponse(
            "<meta charset='utf-8'><h3>❌ 请先在 backend/.env 配置 ALI1688_APP_KEY / ALI1688_APP_SECRET 后重启后端</h3>",
            status_code=400,
        )
    auth_url = (
        "https://auth.1688.com/oauth/authorize"
        f"?client_id={settings.ali1688_app_key}&site=1688"
        f"&redirect_uri={quote(settings.ali1688_redirect_uri, safe='')}"
    )
    return RedirectResponse(auth_url)

@router.get("/1688/oauth/callback")
async def oauth_callback(code: str = "", error: str = ""):
    """授权回调：用 code 换取 access_token/refresh_token 并落盘保存"""
    if error or not code:
        return HTMLResponse("<meta charset='utf-8'><h3>❌ 授权已取消或失败，请关闭页面后重新发起授权</h3>", status_code=400)
    settings = get_settings()
    payload = {
        "grant_type": "authorization_code",
        "need_refresh_token": "true",
        "client_id": settings.ali1688_app_key,
        "client_secret": settings.ali1688_app_secret,
        "redirect_uri": settings.ali1688_redirect_uri,
        "code": code,
    }
    token_url = f"{settings.ali1688_gateway.rstrip('/')}/http/1/system.oauth2/getToken/{settings.ali1688_app_key}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            data = (await client.post(token_url, data=payload)).json()
    except httpx.HTTPError as e:
        return HTMLResponse(f"<meta charset='utf-8'><h3>❌ 换取令牌失败: {type(e).__name__}</h3>", status_code=502)
    if not data.get("access_token"):
        detail = data.get("error_description") or data.get("error_message") or data
        return HTMLResponse(f"<meta charset='utf-8'><h3>❌ 换取令牌失败: {detail}</h3>", status_code=502)
    data["saved_at"] = int(time.time())
    os.makedirs(settings.data_dir, exist_ok=True)
    with open(_token_file_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return HTMLResponse("<meta charset='utf-8'><h3>✅ 1688 授权成功，令牌已保存。可关闭本页，回到工作台试用一键搬运</h3>")

@router.post("/1688")
async def import_from_1688(req: ImportRequest):
    """解析 1688 商品链接：官方 API 优先，未配置/失败时降级页面抓取"""
    url = req.url.strip()
    if "1688.com" not in url and "alibaba" not in url:
        return {
            "success": False,
            "message": "仅支持 1688 商品链接（如 https://detail.1688.com/offer/xxx.html）",
        }

    # 通道一：官方 API（凭证齐全时优先，稳定不受反爬影响；token 可来自 .env 或 OAuth 本地保存）
    settings = get_settings()
    api_error = None
    if settings.ali1688_app_key and settings.ali1688_app_secret and _resolve_access_token():
        try:
            return await _import_via_open_api(url)
        except Exception as e:
            # 官方通道失败（权限不足/凭证过期/商品下架等），记录错误码用于降级提示
            api_error = str(e)

    # 通道二：页面抓取兜底（未配置凭证或官方调用失败时）
    try:
        async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True, timeout=12.0) as client:
            resp = await client.get(url)
            html = resp.text
    except httpx.HTTPError as e:
        msg = f"抓取失败（{type(e).__name__}），1688 可能触发了反爬验证。"
        if api_error:
            msg += f" 官方 API 亦返回错误：{api_error}"
        msg += " 请在浏览器打开链接后手动复制标题与主图链接，或稍后接入 1688 开放平台官方 API。"
        return {"success": False, "message": msg}

    title = _extract_title(html)
    images = _extract_images(html)
    extra = _parse_from_blobs(_extract_json_blobs(html))

    # 判定是否被反爬拦截（页面没有商品图基本可确认）
    if not images and not title:
        msg = "页面被反爬拦截或未渲染完成。"
        if api_error:
            msg += (
                f" 官方 API 返回错误：{api_error}"
                "（错误码通常提示缺少对应权限包，如商品详情接口需订购「跨境综合解决方案（自用）」）。"
            )
        msg += " 可配置 1688 开放平台凭证启用官方 API 稳定导入，或手动粘贴商品标题与主图链接继续上新。"
        return {"success": False, "message": msg}

    # 官方 API 失败但页面抓取成功：保留错误码提醒（步骤七的 ⚠️ 降级分支）
    message = "解析成功" if images else "部分解析成功（未抓到主图，请手动补充）"
    if api_error:
        message += (
            f"；⚠️ 官方 API 返回错误：{api_error}"
            "（若提示权限不足，多半需订购对应权限包，把错误码发我即可判断）"
        )
    return {
        "success": True,
        "message": message,
        "product": {
            "title": title,
            "main_image": images[0] if images else None,
            "images": images,
            "source_price": extra.get("price"),
            "sku_attributes": extra.get("sku_attributes", {}),
            "source_url": url,
        },
    }
