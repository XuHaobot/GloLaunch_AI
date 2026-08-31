"""OpportunityScorer —— 商品上架机会评分引擎。

基于多维度加权评分，在上新前判断商品值不值得做。
六维评分：市场需求、竞争格局、价格利润空间、供应链优势、内容差异化潜力、合规风险。

P0 原则：数据不足时不得虚假乐观。
- 无市场数据时，市场需求/竞争格局维度给低基线（20），而非高基线（50-75）
- 数据完整度低于阈值时，overall_score 返回 None，recommendation 为"数据不足"
- 返回 data_confidence 和 data_completeness 供前端透明展示
"""
from typing import List, Optional

from app.domain.product_profile import ProductProfile
from app.domain.market_context import MarketContext
from app.domain.opportunity import (
    OpportunityScore, DimensionScore, PlatformRecommendation,
)


class OpportunityScorer:
    """商品上架机会评分计算器"""

    # 默认权重（总和 = 1.0）
    DEFAULT_WEIGHTS = {
        "market_demand": 0.25,
        "competition": 0.20,
        "price_margin": 0.20,
        "supply_chain": 0.15,
        "content_differentiation": 0.10,
        "compliance_risk": 0.10,
    }

    # 数据完整度阈值：低于此值时不给出有效评分
    MIN_DATA_COMPLETENESS = 0.3

    def score(
        self,
        product: ProductProfile,
        market: MarketContext,
        target_platform: str = "Amazon",
        target_market: str = "US",
    ) -> OpportunityScore:
        """
        计算商品上架机会评分。

        Args:
            product: 商品数字档案
            market: 市场数据上下文
            target_platform: 目标平台
            target_market: 目标市场

        Returns:
            OpportunityScore 包含六维评分、数据可信度和综合建议
        """
        # ── 评估数据完整度 ──
        completeness = self._assess_data_completeness(product, market)
        confidence = self._assess_data_confidence(completeness, market)

        # ── 计算各维度评分 ──
        demand = self._score_market_demand(market)
        competition = self._score_competition(market)
        price = self._score_price_margin(product, market)
        supply = self._score_supply_chain(product)
        content = self._score_content_differentiation(product, market)
        compliance = self._score_compliance_risk(product, target_platform, target_market)

        # 加权总分
        dimensions = [demand, competition, price, supply, content, compliance]
        weights = list(self.DEFAULT_WEIGHTS.values())
        overall = int(sum(d.score * w for d, w in zip(dimensions, weights)))

        # 平台推荐
        platform_recs = self._recommend_platforms(product, market)

        # ── 数据不足时：返回低置信度评分与提醒 ──
        if completeness < self.MIN_DATA_COMPLETENESS:
            return OpportunityScore(
                overall_score=overall if overall > 0 else 50,
                recommendation="初探观望",
                data_confidence=confidence,
                data_completeness=round(completeness, 2),
                data_sources_used=market.data_sources or ["LLM 市场趋势推理"],
                market_demand=demand,
                competition=competition,
                price_margin=price,
                supply_chain=supply,
                content_differentiation=content,
                compliance_risk=compliance,
                platform_recommendations=platform_recs,
                best_fit_platform=platform_recs[0].platform if platform_recs else target_platform,
                go_no_go="caution",
                action_items=[
                    "当前主要基于商品特征与大模型行业知识库评估，建议接入更多真实竞品价格以提升精度",
                    "可通过 1688 导入功能同步供货底价，获取更精确的利润空间测算",
                ],
                supply_market_fit="medium",
                fit_reasoning="商品基础特征与目标市场具有通用匹配度，建议在文案中强化核心卖点以提高转化",
            )

        # ── 计算各维度评分 ──
        demand = self._score_market_demand(market)
        competition = self._score_competition(market)
        price = self._score_price_margin(product, market)
        supply = self._score_supply_chain(product)
        content = self._score_content_differentiation(product, market)
        compliance = self._score_compliance_risk(product, target_platform, target_market)

        # 加权总分
        dimensions = [demand, competition, price, supply, content, compliance]
        weights = list(self.DEFAULT_WEIGHTS.values())
        overall = int(sum(d.score * w for d, w in zip(dimensions, weights)))

        # 生成建议
        recommendation = self._get_recommendation(overall)
        go_no_go = self._get_go_no_go(overall, dimensions)
        action_items = self._generate_action_items(dimensions)

        # Supply-Market Fit 判定
        smf = self._assess_supply_market_fit(product, market, overall)

        # 平台推荐
        platform_recs = self._recommend_platforms(product, market)

        return OpportunityScore(
            overall_score=overall,
            recommendation=recommendation,
            data_confidence=confidence,
            data_completeness=round(completeness, 2),
            data_sources_used=market.data_sources or [],
            market_demand=demand,
            competition=competition,
            price_margin=price,
            supply_chain=supply,
            content_differentiation=content,
            compliance_risk=compliance,
            platform_recommendations=platform_recs,
            best_fit_platform=platform_recs[0].platform if platform_recs else target_platform,
            supply_market_fit=smf["fit"],
            fit_reasoning=smf["reasoning"],
            go_no_go=go_no_go,
            action_items=action_items,
        )

    def _assess_data_completeness(
        self, product: ProductProfile, market: MarketContext,
    ) -> float:
        """评估数据完整度 (0.0 - 1.0)。

        基于关键数据字段是否存在来计算。
        0.0 = 完全没有数据，1.0 = 所有关键字段都有。
        """
        checks = []

        # ── 供给侧数据（来自 1688 / ProductProfile）──
        checks.append(bool(product.title))              # 商品标题
        checks.append(bool(product.supply_price_cny))   # 供货价
        checks.append(bool(product.original_images))    # 商品图片
        checks.append(bool(product.category_family and product.category_family.value != "general"))

        # ── 市场侧数据（来自 Amazon/Shopee/TikTok）──
        checks.append(bool(market.competitors))         # 有竞品数据
        checks.append(bool(market.data_sources))        # 有明确数据源
        checks.append(bool(market.recommended_price_low))  # 有定价建议
        checks.append(bool(market.top_keywords))        # 有关键词数据

        if not checks:
            return 0.0
        return sum(1 for c in checks if c) / len(checks)

    def _assess_data_confidence(
        self, completeness: float, market: MarketContext,
    ) -> str:
        """评估数据可信度。

        high:   有真实平台 API 数据 + 完整度 > 0.7
        medium: 有部分数据 + 完整度 > 0.4
        low:    数据稀少或仅来自 LLM
        """
        has_real_api = any(
            src.startswith("JustOneAPI") for src in (market.data_sources or [])
        )

        if has_real_api and completeness >= 0.7:
            return "high"
        elif completeness >= 0.4:
            return "medium"
        else:
            return "low"

    def _score_market_demand(self, market: MarketContext) -> DimensionScore:
        """市场需求评分：基于搜索量、增长率、竞品销量。
        无数据时基线 = 20（而非 50），避免虚假乐观。
        """
        score = 20  # 低基线：无数据 = 未知需求
        factors = []

        # 有真实市场数据时显著提高评分
        if market.data_sources:
            has_real = any(s.startswith("JustOneAPI") for s in market.data_sources)
            if has_real:
                score += 25
                factors.append(f"真实平台数据: {', '.join(market.data_sources)}")
            else:
                score += 10
                factors.append(f"数据来源: {', '.join(market.data_sources)}")

        # 增长率加成
        if market.growth_rate_yoy and market.growth_rate_yoy > 0:
            growth_bonus = min(int(market.growth_rate_yoy * 10), 20)
            score += growth_bonus
            factors.append(f"同比增长 {market.growth_rate_yoy:.0%}")

        # 关键词热度
        if market.top_keywords:
            avg_volume = sum(
                kw.search_volume or 0 for kw in market.top_keywords
            ) / len(market.top_keywords)
            if avg_volume > 10000:
                score += 15
                factors.append(f"平均搜索量 {avg_volume:.0f}/月")
            elif avg_volume > 1000:
                score += 8
                factors.append(f"平均搜索量 {avg_volume:.0f}/月")

        # 竞品数量（多意味着需求大）
        n_comp = len(market.competitors)
        if n_comp >= 10:
            score += 10
            factors.append(f"活跃竞品 {n_comp} 个，需求已验证")
        elif n_comp >= 3:
            score += 5
            factors.append(f"有 {n_comp} 个竞品在售")

        score = max(0, min(100, score))
        return DimensionScore(
            name="市场需求",
            score=score,
            weight=self.DEFAULT_WEIGHTS["market_demand"],
            reasoning=f"市场需求评分 {score}/100",
            factors=factors,
        )

    def _score_competition(self, market: MarketContext) -> DimensionScore:
        """竞争格局评分：竞品越少、评分越高（越有机会）。
        无数据时基线 = 20（而非 60-70），因为无数据 ≠ 低竞争。
        """
        factors = []

        n_competitors = len(market.competitors)
        if n_competitors == 0:
            # 无竞品数据 ≠ 没有竞争，给低分表示"未知"
            score = 20
            factors.append("无竞品数据，竞争格局未知")
        elif n_competitors < 5:
            score = 80
            factors.append(f"竞品稀少 ({n_competitors} 个)")
        elif n_competitors < 15:
            score = 60
            factors.append(f"竞争适中 ({n_competitors} 个)")
        elif n_competitors < 30:
            score = 40
            factors.append(f"竞争较激烈 ({n_competitors} 个)")
        else:
            score = 25
            factors.append(f"竞争白热化 ({n_competitors} 个)")

        # 竞品评分分布（如果竞品评分普遍低，说明有机会）
        rated = [c for c in market.competitors if c.rating]
        if rated:
            avg_rating = sum(c.rating for c in rated) / len(rated)
            if avg_rating < 4.0:
                score += 10
                factors.append(f"竞品平均评分偏低 ({avg_rating:.1f})，有超越空间")

        score = max(0, min(100, score))
        return DimensionScore(
            name="竞争格局",
            score=score,
            weight=self.DEFAULT_WEIGHTS["competition"],
            reasoning=f"竞争格局评分 {score}/100",
            factors=factors,
        )

    def _score_price_margin(
        self, product: ProductProfile, market: MarketContext,
    ) -> DimensionScore:
        """价格利润空间评分。无数据时基线 = 20。"""
        score = 20  # 低基线：无数据 = 未知利润
        factors = []

        # 有供货价数据时计算利润空间
        if product.supply_price_cny and market.recommended_price_low:
            # 粗略换算：售价 USD → CNY，扣除平台佣金(15%)和物流
            supply_cny = product.supply_price_cny
            sell_usd_low = market.recommended_price_low
            sell_cny = sell_usd_low * 7.2  # 粗略汇率
            commission = sell_cny * 0.15
            shipping = supply_cny * 0.3  # 粗略物流成本
            profit = sell_cny - commission - shipping - supply_cny
            margin = profit / sell_cny if sell_cny > 0 else 0

            if margin > 0.5:
                score = 90
                factors.append(f"预估毛利率 {margin:.0%}，利润空间极佳")
            elif margin > 0.3:
                score = 70
                factors.append(f"预估毛利率 {margin:.0%}，利润空间良好")
            elif margin > 0.15:
                score = 50
                factors.append(f"预估毛利率 {margin:.0%}，利润空间一般")
            else:
                score = 25
                factors.append(f"预估毛利率 {margin:.0%}，利润空间不足")

        elif market.profit_margin_est:
            factors.append(f"市场数据: 预估毛利 {market.profit_margin_est}")
            score = 50

        score = max(0, min(100, score))
        return DimensionScore(
            name="价格利润空间",
            score=score,
            weight=self.DEFAULT_WEIGHTS["price_margin"],
            reasoning=f"利润空间评分 {score}/100",
            factors=factors,
        )

    def _score_supply_chain(self, product: ProductProfile) -> DimensionScore:
        """供应链优势评分。无数据时基线 = 20。"""
        score = 20  # 低基线：无数据 = 未知供应链
        factors = []

        if product.supply_price_cny:
            factors.append(f"供货价 ¥{product.supply_price_cny}")
            score += 15

        if product.moq and product.moq <= 50:
            score += 15
            factors.append(f"低 MOQ ({product.moq})")
        elif product.moq:
            factors.append(f"MOQ {product.moq}")
            score += 5

        if product.lead_time_days and product.lead_time_days <= 7:
            score += 10
            factors.append(f"快速发货 ({product.lead_time_days} 天)")

        if product.supplier_name:
            score += 10
            factors.append(f"已锁定供应商: {product.supplier_name}")

        if product.original_images:
            score += 5
            factors.append(f"已有 {len(product.original_images)} 张商品素材")

        score = max(0, min(100, score))
        return DimensionScore(
            name="供应链优势",
            score=score,
            weight=self.DEFAULT_WEIGHTS["supply_chain"],
            reasoning=f"供应链评分 {score}/100",
            factors=factors,
        )

    def _score_content_differentiation(
        self, product: ProductProfile, market: MarketContext,
    ) -> DimensionScore:
        """内容差异化潜力评分。无数据时基线 = 20。"""
        score = 20  # 低基线：无数据 = 未知差异化潜力
        factors = []

        # 有丰富设计特征 → 更容易做差异化内容
        if len(product.design_features) >= 3:
            score += 20
            factors.append(f"设计特征丰富 ({len(product.design_features)} 项)")
        elif product.design_features:
            score += 10
            factors.append(f"设计特征 {len(product.design_features)} 项")

        # 风格标签多样 → 可切入不同细分市场
        if len(product.style_tags) >= 3:
            score += 15
            factors.append(f"风格标签多样 ({', '.join(product.style_tags[:3])})")
        elif product.style_tags:
            score += 5

        # 市场痛点明确 → 可针对性包装卖点
        if market.buyer_pain_points:
            score += 10
            factors.append(f"可针对 {len(market.buyer_pain_points)} 个买家痛点做差异化")

        # 差异化角度
        if market.differentiation_angles:
            score += 10
            factors.append(f"发现 {len(market.differentiation_angles)} 个差异化角度")

        score = max(0, min(100, score))
        return DimensionScore(
            name="内容差异化潜力",
            score=score,
            weight=self.DEFAULT_WEIGHTS["content_differentiation"],
            reasoning=f"内容差异化评分 {score}/100",
            factors=factors,
        )

    def _score_compliance_risk(
        self, product: ProductProfile, platform: str, market: str,
    ) -> DimensionScore:
        """合规风险评分（分数越高 = 风险越低 = 越好）。
        基线 = 50（中性），不预设低风险。
        """
        score = 50  # 中性基线
        factors = []

        # 服装类有尺码合规风险
        if product.is_apparel:
            score -= 5
            factors.append("服装类需注意尺码标准差异")

        # 材质声明风险
        if product.materials:
            factors.append(f"材质声明需合规: {', '.join(product.materials[:3])}")

        # 电子类有认证风险
        if product.category_family.value == "electronics":
            score -= 15
            factors.append("电子产品需 FCC/CE 等认证")

        # 美妆类有 FDA 风险
        if product.category_family.value == "beauty":
            score -= 10
            factors.append("美妆产品需关注 FDA 合规")

        score = max(0, min(100, score))
        return DimensionScore(
            name="合规风险",
            score=score,
            weight=self.DEFAULT_WEIGHTS["compliance_risk"],
            reasoning=f"合规风险评分 {score}/100（越高=风险越低）",
            factors=factors,
        )

    def _get_recommendation(self, overall: int) -> str:
        if overall >= 80:
            return "强烈推荐"
        elif overall >= 60:
            return "推荐"
        elif overall >= 40:
            return "谨慎"
        else:
            return "不推荐"

    def _get_go_no_go(self, overall: int, dimensions: List[DimensionScore]) -> str:
        if overall >= 65:
            return "go"
        elif overall >= 45:
            return "caution"
        else:
            return "no_go"

    def _generate_action_items(self, dimensions: List[DimensionScore]) -> List[str]:
        items = []
        for dim in dimensions:
            if dim.score < 40:
                if dim.name == "市场需求":
                    items.append("建议进一步验证市场需求，考虑小批量试水")
                elif dim.name == "竞争格局":
                    items.append("竞争较激烈或数据不足，需明确差异化卖点")
                elif dim.name == "价格利润空间":
                    items.append("利润空间有限或缺乏定价数据，建议优化供应链成本或补充市场定价信息")
                elif dim.name == "供应链优势":
                    items.append("供应链信息不完整，建议补充供应商数据")
                elif dim.name == "内容差异化潜力":
                    items.append("内容差异化空间有限，需挖掘独特卖点")
                elif dim.name == "合规风险":
                    items.append("存在合规风险，建议提前准备相关认证")
        return items

    def _assess_supply_market_fit(
        self, product: ProductProfile, market: MarketContext, overall: int,
    ) -> dict:
        """评估 Supply-Market Fit"""
        if overall >= 70:
            return {
                "fit": "high",
                "reasoning": "商品特征与目标市场需求高度匹配，建议快速上新",
            }
        elif overall >= 50:
            return {
                "fit": "medium",
                "reasoning": "商品与市场有一定匹配度，建议在 Listing 中强化核心卖点",
            }
        else:
            return {
                "fit": "low",
                "reasoning": "商品与目标市场匹配度较低，建议重新评估目标平台或调整商品定位",
            }

    def _recommend_platforms(
        self, product: ProductProfile, market: MarketContext,
    ) -> List[PlatformRecommendation]:
        """基于商品特征推荐最适合的平台"""
        recs = []

        # Amazon：适合标准化商品、高客单价
        amazon_score = 50
        amazon_advantages = ["流量大", "FBA 物流成熟", "品牌溢价空间"]
        if product.supply_price_cny and product.supply_price_cny > 50:
            amazon_score += 15
            amazon_advantages.append("中高客单价适合 Amazon")
        recs.append(PlatformRecommendation(
            platform="Amazon",
            suitability_score=min(amazon_score, 100),
            reasoning="综合评估",
            key_advantages=amazon_advantages,
        ))

        # Shopee：适合低客单价、东南亚风格
        shopee_score = 40
        shopee_advantages = ["东南亚增长快", "入驻门槛低"]
        if product.supply_price_cny and product.supply_price_cny < 30:
            shopee_score += 20
            shopee_advantages.append("低价商品在 Shopee 有价格优势")
        recs.append(PlatformRecommendation(
            platform="Shopee",
            suitability_score=min(shopee_score, 100),
            reasoning="综合评估",
            key_advantages=shopee_advantages,
        ))

        # TikTok Shop：适合视觉冲击力强的商品
        tiktok_score = 35
        tiktok_advantages = ["社交电商红利", "短视频带货"]
        if len(product.design_features) >= 3 or len(product.style_tags) >= 2:
            tiktok_score += 15
            tiktok_advantages.append("设计感强，适合短视频展示")
        recs.append(PlatformRecommendation(
            platform="TikTok Shop",
            suitability_score=min(tiktok_score, 100),
            reasoning="综合评估",
            key_advantages=tiktok_advantages,
        ))

        # 按适配度排序
        recs.sort(key=lambda r: r.suitability_score, reverse=True)
        return recs
