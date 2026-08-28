import json
import time
from typing import Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import AgentState
from app.services.llm import get_llm

PROMPT_LISTING_WRITER = """你是一名精通 Amazon/TikTok/Shopee 等各大跨境电商平台的 Senior Copywriter & SEO Specialist。
你需要依据商品结构化属性、出海市场洞察报告与爆款对标策略，为目标平台撰写高转化、高权重的原生英语多语言 Listing。

❗核心原则：严禁对中文卖点做字面直译！必须严格遵循爆款对标策略给出的标题公式与埋词策略，
模仿目标平台同类爆款的表达习惯，将卖点重组为目标市场买家搜索语境下的原生文案。

严格遵循 Amazon A9/COSMO 算法规范：
1. Title: 150-195字符之间，前置核心大词，埋入品牌词、面料、核心版型、适用场景。
2. Bullet Points (五点描述): 5条，每条以大写的卖点标签开头，如 [PREMIUM BREATHABLE FABRIC]、[ELEGANT FRENCH COTTAGECORE DESIGN]，正文阐明利益点与痛点解决方案。
3. Description: 富文本长描述，包含故事化场景代入、护理洗涤说明与尺码指引。
4. Search Terms (Backend Keywords): 精选 200 字节以内高相关长尾词，空格分隔，不带标点，不重复标题词汇。

请严格输出合法的 JSON 对象，不要包含任何 markdown 代码块标记，不要包含多余文字。
JSON 字段规范：
{
  "title": "Amazon 英文主标题",
  "bullet_points": [
    "[CAPITALIZED FEATURE TAG] 详细卖点描述内容...",
    "[CAPITALIZED FEATURE TAG] 详细卖点描述内容...",
    "[CAPITALIZED FEATURE TAG] 详细卖点描述内容...",
    "[CAPITALIZED FEATURE TAG] 详细卖点描述内容...",
    "[CAPITALIZED FEATURE TAG] 详细卖点描述内容..."
  ],
  "product_description": "完整的商品详情长描述文本（可分段落）",
  "search_terms": "backend keywords 搜索词列表",
  "title_char_count": 182,
  "chinese_summary": {
    "title_zh": "中文标题对照翻译",
    "core_selling_points_zh": ["中文卖点1", "中文卖点2", "中文卖点3"]
  }
}
"""

async def listing_node(state: AgentState) -> Dict[str, Any]:
    """AI 爆款化 Listing 智能撰写节点 (Qwen3.7-Plus，注入爆款对标策略)"""
    attrs = state.get("product_attributes", {})
    insights = state.get("market_insights", {})
    benchmark = state.get("trend_benchmark", {})
    platform = state.get("target_platform", "Amazon")

    llm = get_llm(temperature=0.4)

    user_prompt = f"""
【目标平台】：{platform}
【商品特征属性】：
- 品类大类：{attrs.get('category_family', 'general')}
- 细分品类：{attrs.get('category')}
- 颜色材质：{attrs.get('main_color')} / {', '.join(attrs.get('materials', []))}
- 关键规格：{', '.join(attrs.get('key_specs', [])) or '未识别'}
- 卖点标签与细节：{', '.join(attrs.get('style_tags', []))} / {', '.join(attrs.get('design_features', []))}
- 适用场景：{', '.join(attrs.get('target_occasions', []))}

【市场洞察注入（必须融入这些高转化词与痛点应对）】：
- 高转化SEO关键词：{', '.join(insights.get('high_converting_keywords', []))}
- 需化解的买家痛点：{', '.join(insights.get('buyer_pain_points', []))}
- 差异化卖点方向：{', '.join(insights.get('differentiation_angles', []))}

【🔥 爆款对标策略（必须严格遵循，严禁直译）】：
- 标题公式：{benchmark.get('title_formula', '核心大词前置 + 材质功能词 + 细节卖点 + 场景词')}
- 埋词策略：{'; '.join(benchmark.get('traffic_word_strategy', [])) or '参照市场洞察高转化词前置'}
- 转化钩子：{'; '.join(benchmark.get('conversion_hooks', [])) or '首条五点直击类目高频痛点'}
- 跨文化改写要点：{benchmark.get('localization_notes', '采用目标市场原生表达与计量单位')}

请为该商品撰写完整的专业级出海 Listing JSON。
"""

    MAX_RETRIES = 2
    listing_data = None
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            messages = [
                SystemMessage(content=PROMPT_LISTING_WRITER),
                HumanMessage(content=user_prompt)
            ]
            response = await llm.ainvoke(messages)
            content = response.content.strip()

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            listing_data = json.loads(content)

            # 校验必要字段是否存在
            if not listing_data.get("title"):
                raise ValueError("LLM 返回的 Listing 缺少 title 字段")
            if not listing_data.get("bullet_points"):
                raise ValueError("LLM 返回的 Listing 缺少 bullet_points 字段")

            break  # 成功，跳出重试循环
        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                continue  # 重试

    # 所有重试均失败 → 明确错误状态，禁止返回任何硬编码/虚假 Listing
    if listing_data is None:
        error_state = {
            "status": "failed",
            "error_code": "LISTING_GENERATION_FAILED",
            "error_detail": last_error or "LLM 未能生成有效 Listing",
            "title": None,
            "bullet_points": [],
            "product_description": None,
            "search_terms": None,
        }
        trace_item = {
            "node": "generate_listing",
            "status": "failed",
            "summary": f"Listing 生成失败（已重试 {MAX_RETRIES} 次）: {last_error}",
            "timestamp": time.time(),
            "detail": error_state,
        }
        current_trace = state.get("trace", []) or []
        return {
            "listing_content": error_state,
            "current_node": "generate_listing",
            "trace": current_trace + [trace_item],
        }

    trace_item = {
        "node": "generate_listing",
        "status": "completed",
        "summary": f"已生成符合 {platform} 规范的高转化 Listing（五点描述+长描述+Search Terms）",
        "timestamp": time.time(),
        "detail": {
            "title": listing_data.get("title"),
            "bullet_points_count": len(listing_data.get("bullet_points", []))
        }
    }

    current_trace = state.get("trace", []) or []

    return {
        "listing_content": listing_data,
        "current_node": "generate_listing",
        "trace": current_trace + [trace_item]
    }
