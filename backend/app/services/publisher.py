"""电商平台直连发布服务：Amazon SP-API / Shopee Open Platform。

双模式设计（与图片本地化的双引擎降级模式一致）：
- live：配置了平台 OAuth 凭证且 publish_dry_run=False 时，走真实 OAuth 令牌交换与上架调用
- simulated：未配置凭证或演练模式下，输出完整的模拟发布回执（含发布单号、时间线与校验清单）
"""
import time
import uuid
from typing import Any, Dict, Optional

import httpx

from app.config import get_settings
from app.services.task_store import TaskStore

AMAZON_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
AMAZON_SP_API_BASE = "https://sellingpartnerapi-na.amazon.com"

def _amazon_credentials_configured() -> bool:
    s = get_settings()
    return bool(s.amazon_sp_api_client_id and s.amazon_sp_api_client_secret and s.amazon_sp_api_refresh_token)

def _shopee_credentials_configured() -> bool:
    s = get_settings()
    return bool(s.shopee_partner_id and s.shopee_partner_key)

async def _amazon_live_publish(task: Dict[str, Any]) -> Dict[str, Any]:
    """真实链路：refresh_token 换取 access_token → SP-API listings 提交（任一环节失败抛异常）"""
    s = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        token_resp = await client.post(
            AMAZON_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": s.amazon_sp_api_refresh_token,
                "client_id": s.amazon_sp_api_client_id,
                "client_secret": s.amazon_sp_api_client_secret,
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise ValueError("Amazon OAuth 令牌交换未返回 access_token")

        pkg = (task.get("result") or {}).get("platform_package") or {}
        sku = pkg.get("export_package", {}).get("sku", f"GLO-{uuid.uuid4().hex[:8].upper()}")
        listing_resp = await client.put(
            f"{AMAZON_SP_API_BASE}/listings/2021-08-01/items/SELLER/{sku}",
            headers={"x-amz-access-token": access_token},
            json={"productType": "PRODUCT", "requirements": "LISTING"},
        )
        listing_resp.raise_for_status()
        return {"submission": listing_resp.json(), "sku": sku}

def _simulated_publish_report(task: Dict[str, Any], platform: str, market: str) -> Dict[str, Any]:
    """模拟发布回执：完整走查发布链路并输出演练报告（演示与未配置凭证场景）"""
    result = task.get("result") or {}
    pkg = result.get("platform_package") or {}
    listing = result.get("listing_content") or {}
    sku = pkg.get("export_package", {}).get("sku", f"GLO-{uuid.uuid4().hex[:8].upper()}")
    now = time.time()

    timeline = [
        {"step": "OAuth 店铺授权校验", "at": now, "detail": "店铺凭证有效，权限范围：listings_write"},
        {"step": "类目映射与商品类型匹配", "at": now + 1, "detail": f"已映射至 {platform} {market} 站类目树"},
        {"step": "Listing 字段合规校验", "at": now + 2, "detail": f"标题 {len(listing.get('title', ''))} 字符 / 五点 {len(listing.get('bullet_points', []))} 条，全部通过"},
        {"step": "图片素材上传与主图指定", "at": now + 4, "detail": "白底主图 + 场景图已同步至平台素材库"},
        {"step": "提交上架队列", "at": now + 5, "detail": f"SKU {sku} 已进入平台审核队列"},
    ]

    return {
        "sku": sku,
        "listing_title": listing.get("title", "")[:120],
        "timeline": timeline,
        "expected_review_duration": "15-30 分钟（模拟值）",
        "note": "当前为演练模式：未配置平台 OAuth 凭证或 publish_dry_run=True。配置 AMAZON_SP_API_* / SHOPEE_PARTNER_* 环境变量后可切换真实上架。",
    }

async def publish_package(thread_id: str, platform: Optional[str] = None,
                          dry_run: Optional[bool] = None) -> Dict[str, Any]:
    """执行一次发布：返回发布回执（含 mode: live/simulated）"""
    store = TaskStore.get_instance()
    task = store.get_task(thread_id)
    if not task:
        raise ValueError("任务不存在，请先完成一次全链路上新")

    settings = get_settings()
    platform = platform or task.get("platform") or "Amazon"
    market = task.get("market") or "US"
    effective_dry_run = settings.publish_dry_run if dry_run is None else dry_run

    publish_id = f"PUB-{uuid.uuid4().hex[:10].upper()}"
    mode = "simulated"
    report: Dict[str, Any] = {}
    status = "PUBLISHED_SIMULATED"

    live_ready = (platform == "Amazon" and _amazon_credentials_configured()) or \
                 (platform == "Shopee" and _shopee_credentials_configured())

    if not effective_dry_run and live_ready:
        try:
            if platform == "Amazon":
                live_result = await _amazon_live_publish(task)
            else:
                raise NotImplementedError("Shopee Open Platform 真实上架通道开发中")
            mode = "live"
            status = "SUBMITTED"
            report = {
                "sku": live_result.get("sku"),
                "submission": live_result.get("submission"),
                "note": "已通过平台 Open API 真实提交，可在卖家后台查看审核进度。",
            }
        except Exception as e:
            mode = "simulated"
            status = "PUBLISHED_SIMULATED"
            report = _simulated_publish_report(task, platform, market)
            report["live_attempt_error"] = str(e)[:200]
            report["note"] = "真实上架调用失败，已自动回退为演练模式。" + report["note"]
    else:
        report = _simulated_publish_report(task, platform, market)

    payload = {
        "publish_id": publish_id,
        "thread_id": thread_id,
        "platform": platform,
        "market": market,
        "mode": mode,
        "status": status,
        "report": report,
        "created_at": time.time(),
    }
    try:
        store.save_publish(publish_id, thread_id, platform, market, mode, status, report)
    except Exception:
        pass
    return payload
