import json
import time
from typing import Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import AgentState
from app.services.llm import get_flagship_llm
from app.services.vector_store import search_knowledge_base

PROMPT_TREND_BENCHMARK = """你是一名跨境电商爆款操盘手与流量策略专家。
请基于知识库中检索到的同类爆款打法与标题公式，为该商品制定"对标爆款"的 Listing 创作策略。
核心原则：绝对不是中文资料的简单翻译，而是模仿目标平台同类爆款的标题结构、流量词布局与卖点表达习惯，做原生化的改写策划。

请严格输出合法的 JSON 对象，不要包含任何 markdown 代码块标记，不要包含多余文字。
JSON 字段规范：
{
  "benchmark_products": [
    {"name": "对标爆款画像描述（含平台与类目）", "why_hit": "它能爆的核心原因", "title_pattern": "其标题结构公式"}
  ],
  "title_formula": "为该商品定制的标题公式（含词位顺序与字符数建议）",
  "traffic_word_strategy": ["必须埋入标题的高流量词（5-8个，附埋词位置建议）"],
  "conversion_hooks": ["五点描述中应使用的转化钩子/痛点化解话术（3-4条）"],
  "localization_notes": "相对中文原始卖点需做的跨文化改写要点（如计量单位、尺码体系、表达习惯）"
}
"""

async def trend_node(state: AgentState) -> Dict[str, Any]:
    """爆款对标研究节点：检索同类爆款打法，产出标题公式与流量词策略（供 Listing 改写注入）"""
    attrs = state.get("product_attributes", {})
    insights = state.get("market_insights", {})
    platform = state.get("target_platform", "Amazon")
    market = state.get("target_market", "US")
    category = attrs.get("category", state.get("product_category", "跨境商品"))
    family = attrs.get("category_family", "general")

    # 双路检索：爆款标题公式 + 平台规则
    kb_trend = search_knowledge_base(f"{platform} {market} {family} {category} 爆款 标题公式 流量词", top_k=4)
    kb_rule = search_knowledge_base(f"{platform} Listing 规范 改写 本地化", top_k=2)

    llm = get_flagship_llm(temperature=0.3)

    user_prompt = f"""
【目标平台】：{platform} ({market} 站点)
【商品】：{category}（品类大类：{family}）
【核心卖点】：{', '.join(attrs.get('style_tags', []))} / {', '.join(attrs.get('design_features', []))}
【市场洞察摘要】：{insights.get('market_overview', '')}
【已挖掘高转化词】：{', '.join(insights.get('high_converting_keywords', []))}

【爆款对标知识库】：
{kb_trend}

【平台规范知识库】：
{kb_rule}

请输出该商品的对标爆款 Listing 创作策略 JSON。
"""

    try:
        messages = [
            SystemMessage(content=PROMPT_TREND_BENCHMARK),
            HumanMessage(content=user_prompt)
        ]
        response = await llm.ainvoke(messages)
        content = response.content.strip()

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        benchmark = json.loads(content)
    except Exception as e:
        # 降级兜底：给出通用爆款公式骨架（明确标注为通用模板，非真实对标数据）
        benchmark = {
            "benchmark_products": [],
            "title_formula": "[核心类目大词] + [材质/核心参数] + [2-3个差异化细节] + [适用场景/人群]，总长 150-195 字符",
            "traffic_word_strategy": [
                "将高转化关键词前置到标题前 80 字符内",
                "标题尾部补充长尾场景词承接精准流量"
            ],
            "conversion_hooks": [
                "首条五点直击类目最高频差评痛点",
                "用具体数据（尺寸/时长/容量）替代模糊形容词"
            ],
            "localization_notes": "采用目标市场原生表达与计量单位，避免中文卖点直译",
            "_fallback": True,
            "_note": "爆款对标分析未完成，以上为通用模板，建议补充真实竞品数据后优化"
        }

    trace_item = {
        "node": "trend_benchmark",
        "status": "completed",
        "summary": f"爆款对标完成：提炼 {len(benchmark.get('benchmark_products', []))} 个对标画像，产出定制标题公式与 {len(benchmark.get('traffic_word_strategy', []))} 条埋词策略",
        "timestamp": time.time(),
        "detail": benchmark
    }

    current_trace = state.get("trace", []) or []

    return {
        "trend_benchmark": benchmark,
        "current_node": "trend_benchmark",
        "trace": current_trace + [trace_item]
    }
