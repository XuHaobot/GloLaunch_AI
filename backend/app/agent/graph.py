import os
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.config import get_settings
from app.agent.state import AgentState
from app.agent.nodes.product import product_node
from app.agent.nodes.market import market_node
from app.agent.nodes.trend import trend_node
from app.agent.nodes.listing import listing_node
from app.agent.nodes.studio import studio_node
from app.agent.nodes.video import video_node
from app.agent.nodes.localization import localization_node
from app.agent.nodes.platform import platform_node
from app.agent.nodes.respond import respond_node
from app.agent.nodes.opportunity_score import opportunity_score_node
from app.agent.nodes.asset_inventory import asset_inventory_node
from app.agent.nodes.publish_package import publish_package_node

NextNode = Literal[
    "extract_attributes", "analyze_market", "opportunity_score", "asset_inventory",
    "trend_benchmark", "generate_listing",
    "studio_generation", "video_production", "image_localization",
    "adapt_platform", "publish_package", "respond",
]

def route_next_step(state: AgentState) -> NextNode:
    """条件路由分发器：根据用户意图和已完成节点决定下一步"""
    intent = state.get("user_intent", "full_launch")
    attrs = state.get("product_attributes")
    insights = state.get("market_insights")
    opp_score = state.get("opportunity_score")
    asset_inv = state.get("asset_inventory")
    benchmark = state.get("trend_benchmark")
    listing = state.get("listing_content")
    studio = state.get("studio_assets")
    video = state.get("video_package")
    localized = state.get("localized_images")
    pkg = state.get("platform_package")
    publish_pkg = state.get("publish_package")

    # 1. 属性未提取时，先提取属性
    if not attrs:
        return "extract_attributes"

    # 2. 如果只要市场洞察
    if intent == "market_only":
        if not insights:
            return "analyze_market"
        if not opp_score:
            return "opportunity_score"
        return "respond"

    # 3. 如果只要文案
    if intent == "listing_only":
        if not listing:
            return "generate_listing"
        if not publish_pkg:
            return "publish_package"
        return "respond"

    # 4. 默认全链路上新流程 (full_launch)
    disabled = state.get("disabled_stages") or []

    # 阶段 1: 商品理解
    if not attrs:
        return "extract_attributes"

    # 阶段 2: 市场洞察 + 上架决策
    if not insights:
        return "analyze_market"
    if not opp_score:
        return "opportunity_score"

    # 阶段 3: 爆款对标
    if not benchmark:
        return "trend_benchmark"

    # 阶段 4: 内容生产
    if not listing:
        return "generate_listing"
    if not studio:
        return "studio_generation"

    # 阶段 4.5: 素材盘点（必须在 studio_generation 之后，才能盘点到 studio_assets）
    if not asset_inv:
        return "asset_inventory"

    # 阶段 4.6: 视频 + 本地化
    if not video and "video_production" not in disabled:
        return "video_production"
    if not localized and "image_localization" not in disabled:
        return "image_localization"

    # 阶段 5: 合规发布
    if not pkg:
        return "adapt_platform"
    if not publish_pkg:
        return "publish_package"

    return "respond"

def build_glolaunch_graph():
    """构建 GloLaunch AI 核心 Agent 图"""
    workflow = StateGraph(AgentState)

    # 注册节点（原有 9 个 + 新增 3 个）
    workflow.add_node("extract_attributes", product_node)
    workflow.add_node("analyze_market", market_node)
    workflow.add_node("opportunity_score", opportunity_score_node)
    workflow.add_node("asset_inventory", asset_inventory_node)
    workflow.add_node("trend_benchmark", trend_node)
    workflow.add_node("generate_listing", listing_node)
    workflow.add_node("studio_generation", studio_node)
    workflow.add_node("video_production", video_node)
    workflow.add_node("image_localization", localization_node)
    workflow.add_node("adapt_platform", platform_node)
    workflow.add_node("publish_package", publish_package_node)
    workflow.add_node("respond", respond_node)

    # 入口：先做商品属性解析
    workflow.add_edge(START, "extract_attributes")

    # 条件路由编排
    routing_map = {name: name for name in [
        "extract_attributes", "analyze_market", "opportunity_score", "asset_inventory",
        "trend_benchmark", "generate_listing",
        "studio_generation", "video_production", "image_localization",
        "adapt_platform", "publish_package", "respond",
    ]}
    for node_name in [
        "extract_attributes", "analyze_market", "opportunity_score", "asset_inventory",
        "trend_benchmark", "generate_listing", "studio_generation", "video_production",
        "image_localization", "adapt_platform", "publish_package",
    ]:
        workflow.add_conditional_edges(node_name, route_next_step, routing_map)

    # 总结回复 -> 结束
    workflow.add_edge("respond", END)

    # 编译图并附加内存 Checkpointer
    memory = MemorySaver()
    compiled_graph = workflow.compile(checkpointer=memory)
    return compiled_graph

# 全局单例编译图
_agent_graph = None

def get_agent_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_glolaunch_graph()
    return _agent_graph
