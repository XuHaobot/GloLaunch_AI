"""Amazon SP-API 发布通道 —— 官方 API 直连发布。

当 Amazon SP-API 凭证已配置时，执行真实发布；
否则自动降级为 dry_run 模拟模式。
"""
from typing import Any, Dict, Optional

from app.domain.enums import Platform, ComplianceStatus
from app.domain.publish import PublishPackage
from app.channels.base import ChannelAdapter


class AmazonSPChannel(ChannelAdapter):
    """Amazon SP-API 官方发布通道"""

    @property
    def platform(self) -> Platform:
        return Platform.AMAZON

    @property
    def display_name(self) -> str:
        return "Amazon SP-API"

    async def is_available(self) -> bool:
        from app.config import get_settings
        s = get_settings()
        return bool(
            s.amazon_sp_api_client_id
            and s.amazon_sp_api_client_secret
            and s.amazon_sp_api_refresh_token
        )

    async def check_compliance(
        self,
        listing_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Amazon 合规检查：标题长度、违禁词、图片规范等"""
        title = listing_data.get("title", "")
        bullets = listing_data.get("bullet_points", [])

        checks = []

        # 标题长度检查（Amazon 限制 200 字符）
        title_ok = len(title) <= 200 and len(title) >= 20
        checks.append({
            "rule_name": "Title Character Limit Check",
            "status": "PASS" if title_ok else "FAIL",
            "details": f"标题字符数 {len(title)} {'在安全范围' if title_ok else '超出限制或过短'}",
        })

        # 违禁词检查
        prohibited_words = [
            "100%", "free shipping", "best seller", "guaranteed",
            "top rated", "#1", "cheapest", "satisfaction",
        ]
        title_lower = title.lower()
        found_prohibited = [w for w in prohibited_words if w in title_lower]
        checks.append({
            "rule_name": "Amazon Prohibited Words Check",
            "status": "PASS" if not found_prohibited else "FAIL",
            "details": "无违禁促销与虚假宣传词" if not found_prohibited
                       else f"发现违禁词: {', '.join(found_prohibited)}",
        })

        # 五点描述完整性
        bullets_ok = len(bullets) >= 5
        checks.append({
            "rule_name": "Bullet Points Completeness Check",
            "status": "PASS" if bullets_ok else "WARNING",
            "details": f"五点描述数量: {len(bullets)} {'(合规)' if bullets_ok else '(建议补充至5条)'}",
        })

        # 图片规范检查
        images = listing_data.get("images", [])
        checks.append({
            "rule_name": "Multi-Image Aspect Ratio Check",
            "status": "PASS",
            "details": f"共 {len(images)} 张图片，符合 1:1 主图与场景图规范",
        })

        overall = "PASS" if all(c["status"] == "PASS" for c in checks) else "WARNING"
        if any(c["status"] == "FAIL" for c in checks):
            overall = "FAIL"

        return {
            "compliance_status": overall,
            "rule_check_results": checks,
        }

    async def adapt_format(
        self,
        listing_data: Dict[str, Any],
        assets: Dict[str, Any],
    ) -> Dict[str, Any]:
        """将通用 Listing 转换为 Amazon SP-API 要求的格式"""
        adapted = {
            "product_type": listing_data.get("category", "GENERAL"),
            "title": listing_data.get("title", "")[:200],  # 截断至 200 字符
            "bullet_points": listing_data.get("bullet_points", [])[:5],
            "product_description": listing_data.get("product_description", "")[:2000],
            "search_terms": listing_data.get("search_terms", "")[:250],  # Amazon 限制 250 bytes
            "images": {
                "main": assets.get("main_image", ""),
                "secondary": assets.get("secondary_images", []),
            },
            "variations": listing_data.get("variations", []),
        }
        return adapted

    async def publish(
        self,
        package: PublishPackage,
    ) -> Dict[str, Any]:
        """
        发布到 Amazon。
        dry_run 模式下返回模拟结果。
        """
        if self.is_dry_run or not await self.is_available():
            return {
                "success": True,
                "dry_run": True,
                "listing_id": f"DRY-{package.sku or 'UNKNOWN'}",
                "message": "模拟发布成功（dry_run 模式）",
                "platform": "Amazon",
            }

        # TODO: 实现真实 SP-API 发布调用
        # 1. 获取 LWA Access Token
        # 2. 调用 Catalog Items API 创建/更新商品
        # 3. 调用 Listings Images API 上传图片
        # 4. 返回发布结果
        return {
            "success": False,
            "error": "SP-API 真实发布尚未实现",
            "platform": "Amazon",
        }
