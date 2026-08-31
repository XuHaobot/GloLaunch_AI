import json
import time
import re
from typing import Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import AgentState
from app.services.llm import get_fast_llm

PROMPT_PLATFORM_VALIDATOR = """你是一名严格的跨境平台（Amazon/Shopee/TikTok）合规与规则质检专家。
请对即将上架的商品 Listing 与素材数据进行规则合规检查。

检查规则项：
1. 标题长度：不超过 200 字符，且无重复堆砌违禁词（如 100% Free Shipping, Best Seller, #1）。
2. 属性完整度：检查 product_attributes 中的品类 (category)、材质 (materials)、颜色 (main_color) 等核心字段是否齐全。注意：属性在独立的 attributes 对象中，不在 title 里。
3. 风险预警：是否包含侵权品牌或违禁敏感词。

请严格输出合法的 JSON 对象，不要包含任何 markdown 代码块标记，不要包含多余文字。
JSON 字段规范：
{
  "compliance_status": "PASS",
  "rule_check_results": [
    {"rule_name": "Title Character Limit Check", "status": "PASS", "details": "标题字符数合规"},
    {"rule_name": "Amazon Prohibited Words Check", "status": "PASS", "details": "无违禁促销与虚假宣传词"},
    {"rule_name": "Attribute Completeness Check", "status": "PASS", "details": "核心属性完整"}
  ]
}
"""

def _build_deterministic_sku(platform: str, category: str, title: str) -> str:
    """从确定性字段生成 SKU，避免 LLM 串台或随机值。
    格式：GLO-{平台缩写}-{品类关键词}-{时间戳后5位}
    """
    platform_code = {"Amazon": "AMZ", "Shopee": "SPE", "TikTok": "TTK"}.get(platform, "GLO")
    # 从 category 提取英文字母或拼音首字母（最多10位）
    cat_clean = re.sub(r"[^\w]", "", category or "")[:10].upper() or "PROD"
    ts_suffix = str(int(time.time()))[-5:]
    return f"GLO-{platform_code}-{cat_clean}-{ts_suffix}"

async def platform_node(state: AgentState) -> Dict[str, Any]:
    """多平台规则校验与发布包打包节点 (Qwen3.6-Flash)"""
    listing = state.get("listing_content", {})
    attrs = state.get("product_attributes", {})
    platform = state.get("target_platform", "Amazon")

    title = listing.get("title", "")
    category = attrs.get("category") or state.get("product_category") or "商品"
    bullets = listing.get("bullet_points", [])
    title_len = len(title)

    llm = get_fast_llm(temperature=0.1)

    try:
        # 构建属性摘要供 LLM 质检
        attrs_summary = (
            f"材质 (materials): {attrs.get('materials', [])}\n"
            f"颜色 (main_color): {attrs.get('main_color', '')}\n"
            f"品类 (category): {attrs.get('category', '')}\n"
            f"规格 (key_specs): {attrs.get('key_specs', [])}\n"
            f"风格 (style_tags): {attrs.get('style_tags', [])}"
        )
        messages = [
            SystemMessage(content=PROMPT_PLATFORM_VALIDATOR),
            HumanMessage(content=(
                f"请质检以下即将上架到 {platform} 的 Listing：\n"
                f"商品品类：{category}\n"
                f"Title（{title_len}字符）：{title}\n"
                f"Bullet Points 数量：{len(bullets)} 条\n"
                f"Search Terms 长度：{len(listing.get('search_terms', ''))} 字符\n"
                f"\n--- product_attributes 属性表 ---\n"
                f"{attrs_summary}\n"
                f"--- 属性表结束 ---"
            ))
        ]
        response = await llm.ainvoke(messages)
        content = response.content.strip()

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        llm_result = json.loads(content)
        compliance_status = llm_result.get("compliance_status", "PASS")
        rule_check_results = llm_result.get("rule_check_results", [])
    except Exception:
        compliance_status = "WARNING"
        rule_check_results = [
            {"rule_name": "Title Length Check", "status": "WARNING", "details": "LLM 质检未成功，需人工复核"},
            {"rule_name": "Attribute Completeness Check", "status": "WARNING", "details": "LLM 质检未成功，需人工复核"},
            {"rule_name": "Prohibited Words Check", "status": "WARNING", "details": "LLM 质检未成功，需人工复核"},
        ]

    # ── 基于真实数据生成确定性 SKU，绝不依赖 LLM ──
    sku = _build_deterministic_sku(platform, category, title)

    pkg = {
        "compliance_status": compliance_status,
        "rule_check_results": rule_check_results,
        "export_package": {
            "sku": sku,
            "ready_to_publish": compliance_status == "PASS",
            "target_platform": platform,
            "standard_feed_ready": compliance_status == "PASS",
        }
    }

    trace_item = {
        "node": "adapt_platform",
        "status": "completed",
        "summary": f"已完成 {platform} 平台 {len(rule_check_results)} 项合规质检，生成标准化上架发布包 (SKU: {sku})",
        "timestamp": time.time(),
        "detail": pkg
    }

    current_trace = state.get("trace", []) or []

    return {
        "platform_package": pkg,
        "current_node": "adapt_platform",
        "trace": current_trace + [trace_item]
    }
