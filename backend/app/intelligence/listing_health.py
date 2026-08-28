"""ListingHealthCalculator —— Listing 质量评分引擎。

在 Listing 生成后、发布前进行多维度质量评估，
输出可操作的改进建议。
"""
from typing import Any, Dict, List, Optional

from app.domain.enums import ComplianceStatus
from app.domain.listing import ListingHealth, HealthDimension
from app.domain.market_context import MarketContext


class ListingHealthCalculator:
    """Listing 质量评分计算器"""

    def calculate(
        self,
        listing: Dict[str, Any],
        platform: str = "Amazon",
        market_data: Optional[MarketContext] = None,
        assets: Optional[Dict[str, Any]] = None,
    ) -> ListingHealth:
        """
        计算 Listing 综合质量评分。

        Args:
            listing: Listing 内容字典
            platform: 目标平台
            market_data: 市场数据（用于关键词覆盖度评估）
            assets: 素材信息（用于图片评估）
        """
        # 各维度评分
        title_h = self._evaluate_title(listing, platform)
        bullets_h = self._evaluate_bullets(listing, platform)
        desc_h = self._evaluate_description(listing, platform)
        images_h = self._evaluate_images(listing, assets or {})
        keywords_h = self._evaluate_keywords(listing, market_data)
        attrs_h = self._evaluate_attributes(listing)
        category_h = self._evaluate_category(listing)
        compliance_h = self._evaluate_compliance(listing, platform)

        # 综合评分（加权平均）
        dimensions = [title_h, bullets_h, desc_h, images_h, keywords_h, attrs_h, category_h, compliance_h]
        weights = [0.18, 0.15, 0.10, 0.20, 0.12, 0.10, 0.05, 0.10]
        overall = int(sum(d.score * w for d, w in zip(dimensions, weights)))

        # 等级
        grade = self._get_grade(overall)

        # 综合合规状态
        statuses = [d.status for d in dimensions]
        if ComplianceStatus.FAIL in statuses:
            status = ComplianceStatus.FAIL
        elif ComplianceStatus.WARNING in statuses:
            status = ComplianceStatus.WARNING
        else:
            status = ComplianceStatus.PASS

        # 改进优先级
        priorities = self._generate_priorities(dimensions)

        # 平台适配度
        platform_fit = self._evaluate_platform_fit(listing, platform)

        return ListingHealth(
            overall_score=overall,
            grade=grade,
            status=status,
            title_health=title_h,
            bullets_health=bullets_h,
            description_health=desc_h,
            images_health=images_h,
            keywords_health=keywords_h,
            attributes_health=attrs_h,
            category_health=category_h,
            compliance_health=compliance_h,
            platform=platform,
            platform_fit_score=platform_fit,
            improvement_priorities=priorities,
        )

    def _evaluate_title(self, listing: Dict[str, Any], platform: str) -> HealthDimension:
        """标题质量评估"""
        title = listing.get("title", "")
        char_count = len(title)
        suggestions = []

        if platform == "Amazon":
            if char_count > 200:
                score = 40
                status = ComplianceStatus.FAIL
                suggestions.append(f"标题超出 Amazon 200 字符限制（当前 {char_count}）")
            elif char_count < 80:
                score = 60
                status = ComplianceStatus.WARNING
                suggestions.append("标题偏短，建议补充核心卖点和关键词")
            elif char_count < 150:
                score = 85
                status = ComplianceStatus.PASS
            else:
                score = 90
                status = ComplianceStatus.PASS
        else:
            # 其他平台相对宽松
            if char_count > 255:
                score = 50
                status = ComplianceStatus.WARNING
                suggestions.append("标题较长，部分平台可能截断")
            elif char_count < 30:
                score = 55
                status = ComplianceStatus.WARNING
                suggestions.append("标题过短")
            else:
                score = 80
                status = ComplianceStatus.PASS

        # 检查关键词堆砌
        words = title.lower().split()
        unique_words = set(words)
        if len(words) > 0 and len(unique_words) / len(words) < 0.5:
            score -= 15
            suggestions.append("标题存在关键词堆砌嫌疑，建议优化可读性")

        return HealthDimension(
            name="标题质量",
            score=max(0, min(100, score)),
            status=status,
            details=f"标题字符数: {char_count}",
            suggestions=suggestions,
        )

    def _evaluate_bullets(self, listing: Dict[str, Any], platform: str) -> HealthDimension:
        """五点描述评估"""
        bullets = listing.get("bullet_points", [])
        suggestions = []

        if len(bullets) == 0:
            return HealthDimension(
                name="五点描述",
                score=0,
                status=ComplianceStatus.FAIL,
                details="缺少五点描述",
                suggestions=["必须添加五点描述"],
            )

        if platform == "Amazon" and len(bullets) < 5:
            suggestions.append(f"Amazon 建议 5 条五点描述（当前 {len(bullets)} 条）")

        # 评估每条 bullet 的长度和质量
        avg_len = sum(len(b) for b in bullets) / len(bullets) if bullets else 0
        if avg_len < 50:
            suggestions.append("五点描述偏短，建议每条 100-250 字符")

        score = min(100, 50 + len(bullets) * 10 + (10 if avg_len > 80 else 0))
        status = ComplianceStatus.PASS if score >= 70 else ComplianceStatus.WARNING

        return HealthDimension(
            name="五点描述",
            score=max(0, score),
            status=status,
            details=f"共 {len(bullets)} 条，平均长度 {avg_len:.0f} 字符",
            suggestions=suggestions,
        )

    def _evaluate_description(self, listing: Dict[str, Any], platform: str) -> HealthDimension:
        """商品描述评估"""
        desc = listing.get("product_description", "")
        suggestions = []

        if not desc:
            return HealthDimension(
                name="商品描述",
                score=40,
                status=ComplianceStatus.WARNING,
                details="缺少商品长描述",
                suggestions=["建议添加商品描述以提升转化率"],
            )

        char_count = len(desc)
        if char_count < 200:
            score = 55
            suggestions.append("描述偏短，建议 500-2000 字符")
        elif char_count > 2000 and platform == "Amazon":
            score = 70
            suggestions.append("描述较长，注意 Amazon 折叠展示规则")
        else:
            score = 85

        return HealthDimension(
            name="商品描述",
            score=score,
            status=ComplianceStatus.PASS if score >= 70 else ComplianceStatus.WARNING,
            details=f"描述字符数: {char_count}",
            suggestions=suggestions,
        )

    def _evaluate_images(self, listing: Dict[str, Any], assets: Dict[str, Any]) -> HealthDimension:
        """图片素材评估"""
        suggestions = []
        images = listing.get("images", [])
        lifestyle = assets.get("lifestyle_scenes", [])

        # 统计所有有效图片：listing 图片列表 + 生活方式场景图 + 白底主图 + 商品原图
        has_main = bool(
            assets.get("white_background_main")
            or listing.get("main_image_url")
        )
        # 也计算 imported_images（1688 搬运带入的详情图）
        imported = assets.get("original_images", [])
        total = len(images) + len(lifestyle) + len(imported) + (1 if has_main else 0)

        if total == 0:
            return HealthDimension(
                name="图片素材",
                score=20,
                status=ComplianceStatus.FAIL,
                details="无图片素材",
                suggestions=["必须上传至少 1 张主图"],
            )

        if total < 3:
            suggestions.append(f"建议至少 5 张图片（当前 {total} 张）")
            # 有主图时给更友好的基线分
            base = 60 if has_main else 40
            score = base + total * 8
        elif total < 5:
            suggestions.append(f"建议补充至 5 张以上图片（当前 {total} 张）")
            score = 75
        elif total < 8:
            score = 85
        else:
            score = 92

        if not lifestyle and not has_main:
            suggestions.append("缺少生活方式场景图，建议补充以提升转化")
        elif not lifestyle:
            suggestions.append("已有主图，建议补充生活方式场景图")

        return HealthDimension(
            name="图片素材",
            score=min(100, score),
            status=ComplianceStatus.PASS if score >= 70 else ComplianceStatus.WARNING,
            details=f"共 {total} 张图片（主图: {'有' if has_main else '无'}, 场景图: {len(lifestyle)} 张）",
            suggestions=suggestions,
        )

    def _evaluate_keywords(
        self, listing: Dict[str, Any], market_data: Optional[MarketContext],
    ) -> HealthDimension:
        """关键词覆盖度评估"""
        search_terms = listing.get("search_terms", "")
        title = listing.get("title", "").lower()
        suggestions = []

        if not search_terms and not market_data:
            return HealthDimension(
                name="关键词覆盖",
                score=50,
                status=ComplianceStatus.WARNING,
                details="无搜索关键词数据",
                suggestions=["建议填写 Search Terms"],
            )

        score = 60
        if search_terms:
            score += 15
            if len(search_terms) > 100:
                score += 10

        # 如果有市场数据，检查高转化词是否被覆盖
        if market_data and market_data.high_converting_keywords:
            covered = 0
            total = len(market_data.high_converting_keywords)
            all_text = (title + " " + search_terms).lower()
            for kw in market_data.high_converting_keywords:
                if kw.lower() in all_text:
                    covered += 1
            coverage = covered / total if total > 0 else 0
            if coverage > 0.7:
                score += 15
            elif coverage < 0.3:
                suggestions.append(f"高转化词覆盖率仅 {coverage:.0%}，建议补充")

        return HealthDimension(
            name="关键词覆盖",
            score=min(100, score),
            status=ComplianceStatus.PASS if score >= 70 else ComplianceStatus.WARNING,
            details=f"Search Terms: {len(search_terms)} 字符",
            suggestions=suggestions,
        )

    def _evaluate_attributes(self, listing: Dict[str, Any]) -> HealthDimension:
        """属性完整度评估：优先读取 _product_attrs（由 calculate 注入），其次读 listing.attributes。
        检查 6 个维度字段，每填充一个给分，有任意 1 个即给基线分。"""
        # 优先用节点传入的 product_attributes（字段更丰富）
        attrs = getattr(self, "_product_attrs", None) or listing.get("attributes", {})
        suggestions = []

        if not attrs:
            return HealthDimension(
                name="属性完整度",
                score=30,
                status=ComplianceStatus.WARNING,
                details="未填写商品属性",
                suggestions=["建议填写品类、材质、颜色等核心属性"],
            )

        # 检查 6 个维度（核心 3 个 + 扩展 3 个）
        has_category = bool(attrs.get("category") or attrs.get("category_family"))
        has_material = bool(attrs.get("materials") or attrs.get("material"))
        has_color = bool(attrs.get("main_color") or attrs.get("color") or attrs.get("colors"))
        has_style = bool(attrs.get("style_tags"))
        has_specs = bool(attrs.get("key_specs"))
        has_occasions = bool(attrs.get("target_occasions"))

        core_filled = sum([has_category, has_material, has_color])
        ext_filled = sum([has_style, has_specs, has_occasions])
        total_filled = core_filled + ext_filled

        # 评分曲线：基线 15 + 核心字段 ×20 + 扩展字段 ×8，上限 100
        score = 15 + core_filled * 20 + ext_filled * 8
        # 如果核心字段全空但有扩展字段，额外加 10 分
        if core_filled == 0 and ext_filled > 0:
            score += 10

        if not has_category:
            suggestions.append("缺少品类信息")
        if not has_material:
            suggestions.append("缺少材质/面料信息")
        if not has_color:
            suggestions.append("缺少颜色信息")

        return HealthDimension(
            name="属性完整度",
            score=min(100, score),
            status=ComplianceStatus.PASS if score >= 70 else ComplianceStatus.WARNING,
            details=f"核心属性填充率: {core_filled}/3，扩展属性: {ext_filled}/3",
            suggestions=suggestions,
        )

    def _evaluate_category(self, listing: Dict[str, Any]) -> HealthDimension:
        """类目匹配评估"""
        category = listing.get("category", "")
        if not category:
            return HealthDimension(
                name="类目匹配",
                score=40,
                status=ComplianceStatus.WARNING,
                details="未指定类目",
                suggestions=["请选择准确的商品类目"],
            )

        return HealthDimension(
            name="类目匹配",
            score=80,
            status=ComplianceStatus.PASS,
            details=f"类目: {category}",
        )

    def _evaluate_compliance(self, listing: Dict[str, Any], platform: str) -> HealthDimension:
        """合规检查评估"""
        # 基础合规检查
        title = listing.get("title", "")
        suggestions = []
        score = 80

        # 检查常见违禁词
        prohibited = ["best seller", "#1", "100% free", "guaranteed", "cheap"]
        found = [w for w in prohibited if w in title.lower()]
        if found:
            score -= 20
            suggestions.append(f"标题含违禁词: {', '.join(found)}")

        return HealthDimension(
            name="合规检查",
            score=max(0, score),
            status=ComplianceStatus.PASS if score >= 70 else ComplianceStatus.WARNING,
            details="基础合规检查通过" if score >= 70 else "存在合规风险",
            suggestions=suggestions,
        )

    def _evaluate_platform_fit(self, listing: Dict[str, Any], platform: str) -> int:
        """评估与目标平台的适配度"""
        score = 70  # 基线

        title_len = len(listing.get("title", ""))
        if platform == "Amazon":
            if 80 <= title_len <= 200:
                score += 15
            elif title_len > 200:
                score -= 20
        elif platform == "Shopee":
            if title_len <= 255:
                score += 10

        bullets_count = len(listing.get("bullet_points", []))
        if bullets_count >= 5:
            score += 10

        return max(0, min(100, score))

    def _get_grade(self, score: int) -> str:
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 65:
            return "C"
        elif score >= 50:
            return "D"
        else:
            return "F"

    def _generate_priorities(self, dimensions: List[HealthDimension]) -> List[str]:
        """按优先级生成改进建议"""
        priorities = []
        # 按分数排序，优先改进分数最低的维度
        sorted_dims = sorted(dimensions, key=lambda d: d.score)
        for dim in sorted_dims:
            if dim.score < 70 and dim.suggestions:
                priorities.append(f"[{dim.name}] {dim.suggestions[0]}")
        return priorities[:5]  # 最多 5 条优先建议
