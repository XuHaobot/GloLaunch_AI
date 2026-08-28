"""ProductProfile —— 平台无关的商品数字档案。

作为全链路的「单一事实来源」(Single Source of Truth)，
所有节点围绕 ProductProfile 读写，而非散落的 Dict[str, Any]。
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .enums import CategoryFamily


class ProductProfile(BaseModel):
    """商品数字档案：从多模态提取到结构化属性的完整描述"""

    # ── 基础标识 ──
    product_id: str = ""                          # 内部唯一 ID（生成或 1688 offer_id）
    source_url: str = ""                          # 来源链接（1688 / 用户输入）
    source_platform: str = ""                     # 来源平台（1688 / manual / import）

    # ── 品类体系 ──
    category_family: CategoryFamily = CategoryFamily.GENERAL
    category: str = ""                            # 细分类目（如 "连衣裙"、"休闲衬衫"）
    sub_category: str = ""                        # 子类目

    # ── 物理属性 ──
    title: str = ""                               # 商品原始标题
    materials: List[str] = Field(default_factory=list)   # 材质成分
    colors: List[str] = Field(default_factory=list)      # 颜色
    sizes: List[str] = Field(default_factory=list)       # 可用尺码
    weight_grams: Optional[int] = None            # 重量（克）
    dimensions_cm: Optional[Dict[str, float]] = None  # 尺寸 {l, w, h}

    # ── 设计特征 ──
    key_specs: List[str] = Field(default_factory=list)       # 关键规格
    design_features: List[str] = Field(default_factory=list) # 设计细节（方领、泡泡袖…）
    style_tags: List[str] = Field(default_factory=list)      # 风格标签（法式、极简…）
    target_occasions: List[str] = Field(default_factory=list) # 适用场景

    # ── 供应链信息（搬运场景）──
    supply_price_cny: Optional[float] = None      # 供货价（人民币）
    moq: Optional[int] = None                     # 最低起订量
    lead_time_days: Optional[int] = None          # 发货周期
    supplier_id: str = ""                         # 供应商 ID
    supplier_name: str = ""                       # 供应商名称

    # ── 图片资产 ──
    original_images: List[str] = Field(default_factory=list)  # 原始图片 URL 列表
    main_image_url: str = ""                      # 主图 URL

    # ── AI 识别元数据 ──
    confidence: float = 0.0                       # 属性提取置信度 (0-1)
    model_used: str = ""                          # 使用的模型名称
    raw_extraction: Dict[str, Any] = Field(default_factory=dict)  # 原始提取结果

    # ── 商品身份指纹（用于跨平台一致性追踪）──
    identity_fingerprint: str = ""                # 基于核心属性生成的哈希指纹

    @property
    def is_apparel(self) -> bool:
        return self.category_family in (CategoryFamily.APPAREL, CategoryFamily.SHOES)

    @property
    def display_name(self) -> str:
        return self.title or self.category or "未命名商品"
