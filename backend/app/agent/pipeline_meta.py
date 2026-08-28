"""管道元数据：节点展示信息、阶段泳道分组与预估耗时。

供 SSE 事件协议（plan / node_start / node_update）与前端阶段泳道渲染共用，
保证后端推送的进度/ETA 与前端展示口径一致。
"""
from typing import Dict, List, Any

# 阶段泳道定义（对标阿里系工作台的阶段分组体验）
STAGES: List[Dict[str, str]] = [
    {"id": "understand", "label": "① 商品理解", "desc": "解析商品并提取结构化属性"},
    {"id": "insight", "label": "② 市场洞察", "desc": "出海市场与选品评估"},
    {"id": "decision", "label": "③ 上架决策", "desc": "机会评分与素材缺口分析"},
    {"id": "benchmark", "label": "④ 爆款对标", "desc": "同类爆款标题公式与流量词策略"},
    {"id": "content", "label": "⑤ 内容生产", "desc": "Listing 撰写、视觉素材、带货视频与图片本地化"},
    {"id": "publish", "label": "⑥ 合规发布", "desc": "Listing 质检、发布包组装与人工审核"},
]

# 节点元数据：展示名、所属阶段、预估耗时（秒，用于 ETA 估算）
PIPELINE_NODES: Dict[str, Dict[str, Any]] = {
    "extract_attributes": {
        "name": "商品智能解析", "stage": "understand", "model": "Qwen-VL 多模态",
        "icon": "Search", "eta": 8,
    },
    "analyze_market": {
        "name": "出海市场洞察", "stage": "insight", "model": "Qwen 旗舰 + RAG",
        "icon": "DataAnalysis", "eta": 14,
    },
    "trend_benchmark": {
        "name": "爆款对标研究", "stage": "benchmark", "model": "Qwen 旗舰 + 爆款语料 RAG",
        "icon": "TrendCharts", "eta": 12,
    },
    "generate_listing": {
        "name": "爆款化 Listing 撰写", "stage": "content", "model": "Qwen-Plus",
        "icon": "EditPen", "eta": 16,
    },
    "studio_generation": {
        "name": "AI 商品摄影", "stage": "content", "model": "搬运原素材优先 / Wan2.7 按需",
        "icon": "Camera", "eta": 14,
    },
    "video_production": {
        "name": "带货视频生产", "stage": "content", "model": "分镜 + TTS 配音 + 合成",
        "icon": "VideoCamera", "eta": 20,
    },
    "image_localization": {
        "name": "图片文字本地化", "stage": "content", "model": "阿里图翻 / Qwen-VL",
        "icon": "MapLocation", "eta": 18,
    },
    "adapt_platform": {
        "name": "平台合规质检", "stage": "publish", "model": "Qwen-Flash",
        "icon": "Stamp", "eta": 7,
    },
    "opportunity_score": {
        "name": "上架机会评分", "stage": "decision", "model": "Intelligence Engine",
        "icon": "TrendCharts", "eta": 3,
    },
    "asset_inventory": {
        "name": "素材盘点与缺口分析", "stage": "decision", "model": "Asset Analyzer",
        "icon": "Files", "eta": 2,
    },
    "publish_package": {
        "name": "发布包组装与审核", "stage": "publish", "model": "Listing Health + Compliance",
        "icon": "Finished", "eta": 4,
    },
    "respond": {
        "name": "成果汇总打包", "stage": "publish", "model": "LangGraph Core",
        "icon": "Box", "eta": 2,
    },
}

# 不同意图下实际执行的节点序列（与 graph.route_next_step 条件路由保持一致）
INTENT_PIPEELINES: Dict[str, List[str]] = {
    "full_launch": [
        "extract_attributes", "analyze_market", "opportunity_score", "asset_inventory",
        "trend_benchmark", "generate_listing",
        "studio_generation", "video_production", "image_localization",
        "adapt_platform", "publish_package", "respond",
    ],
    "market_only": ["extract_attributes", "analyze_market", "opportunity_score", "respond"],
    "listing_only": ["extract_attributes", "generate_listing", "publish_package", "respond"],
}

# 可被用户关闭的可选节点（工作流 hub 技能开关；其余为核心节点不可关闭）
OPTIONAL_NODES = ("video_production", "image_localization")

def _effective_nodes(intent: str, disabled: List[str] = None) -> List[str]:
    """某意图下实际执行的节点序列，剔除用户关闭的可选节点"""
    node_ids = INTENT_PIPEELINES.get(intent, INTENT_PIPEELINES["full_launch"])
    off = set(disabled or []) & set(OPTIONAL_NODES)
    return [n for n in node_ids if n not in off]

def build_plan(intent: str, disabled: List[str] = None) -> Dict[str, Any]:
    """生成某意图下的执行计划（含阶段分组与总预估耗时），用于 SSE plan 事件"""
    node_ids = _effective_nodes(intent, disabled)
    nodes = []
    for node_id in node_ids:
        meta = PIPELINE_NODES[node_id]
        nodes.append({"id": node_id, **meta})
    return {
        "intent": intent,
        "stages": STAGES,
        "nodes": nodes,
        "total_eta": sum(n["eta"] for n in nodes),
    }

def estimate_remaining_eta(intent: str, completed: List[str], running: str = None,
                           disabled: List[str] = None) -> int:
    """估算剩余耗时：未开始节点按预估耗时累加，正在执行的节点按一半估算"""
    node_ids = _effective_nodes(intent, disabled)
    remaining = 0
    for node_id in node_ids:
        if node_id in completed:
            continue
        eta = PIPELINE_NODES[node_id]["eta"]
        remaining += eta // 2 if node_id == running else eta
    return remaining
