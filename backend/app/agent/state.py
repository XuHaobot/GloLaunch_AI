from typing import List, Dict, Any, Optional, Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class TraceItem(TypedDict):
    node: str
    status: str
    summary: str
    timestamp: Optional[float]
    detail: Optional[Dict[str, Any]]

class AgentState(TypedDict):
    # 对话消息历史 (自动支持消息合并追加)
    messages: Annotated[list, add_messages]

    # 用户意图与指令
    user_intent: str                  # 如 "full_launch" (全链路上新), "market_only", "listing_only"
    disabled_stages: List[str]        # 用户关闭的可选节点（工作流 hub 技能开关，如 video_production）
    target_platform: str              # 如 "Amazon", "Shopee", "TikTok"
    target_market: str                # 如 "US", "Southeast Asia", "EU"
    product_category: str             # 如 "连衣裙", "女装"

    # 输入素材
    product_image_url: Optional[str]  # 主商品图片 URL 或 Base64
    imported_images: List[str]        # 1688 搬运带入的详情图列表（供图片本地化节点使用）

    # 1688 导入的真实商品数据（由 initial_state 注入）
    product_title: str                              # 商品标题
    supply_price_cny: Optional[float]               # 供应价格（人民币）
    sku_attributes: Dict[str, List[str]]            # SKU 属性（如 {颜色: [红,蓝], 尺码: [S,M,L]}）
    source_url: str                                 # 来源链接

    # ── 结构化节点输出（原有字段，保持向后兼容）──
    product_attributes: Dict[str, Any]    # 视觉/多模态提取出的属性 (品类、面料、版型、颜色等)
    market_insights: Dict[str, Any]       # 市场洞察结论 (竞品分析、定价策略、高转化关键词)
    trend_benchmark: Dict[str, Any]       # 爆款对标策略 (对标画像、标题公式、流量词埋词策略)
    listing_content: Dict[str, Any]       # 生成的标题、五点描述、长描述、Search Terms
    studio_assets: Dict[str, Any]         # 生成的商品场景图/试穿结果 URL 与标签
    video_package: Dict[str, Any]         # 商品展示视频包（分镜脚本/配音/成片）
    localized_images: Dict[str, Any]      # 详情页图片文字本地化结果（译后图/译文对照）
    platform_package: Dict[str, Any]      # 经平台规则校验和格式适配后的最终发布包

    # ── V2 新增：领域模型输出（Pydantic model_dump() 后的 dict）──
    opportunity_score: Optional[Dict[str, Any]]   # 上架机会评分（六维评分 + 平台推荐）
    asset_inventory: Optional[Dict[str, Any]]     # 素材盘点清单
    asset_gap: Optional[Dict[str, Any]]           # 素材缺口分析
    listing_health: Optional[Dict[str, Any]]      # Listing 质量评分
    publish_package: Optional[Dict[str, Any]]     # 发布包（含人工审核状态）

    # 节点执行追踪链路 (前端可视化图拓扑使用)
    current_node: Optional[str]
    trace: List[TraceItem]
