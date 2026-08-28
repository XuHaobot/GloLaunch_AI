import time
from typing import Dict, Any
from langchain_core.messages import AIMessage
from app.agent.state import AgentState

async def respond_node(state: AgentState) -> Dict[str, Any]:
    """总结执行成果并生成自然语言回复"""
    attrs = state.get("product_attributes", {})
    insights = state.get("market_insights", {})
    benchmark = state.get("trend_benchmark", {})
    listing = state.get("listing_content", {})
    video = state.get("video_package", {})
    localized = state.get("localized_images", {})
    platform = state.get("target_platform", "Amazon")
    sku = state.get("platform_package", {}).get("export_package", {}).get("sku", "GLO-2026-001")

    category = attrs.get("category", "跨境商品")
    price = insights.get("recommended_price_range") or "待市场验证"
    title = listing.get("title", "")
    bullet_count = len(listing.get("bullet_points", []))
    localized_count = len((localized or {}).get("items", []))
    video_shots = len((video or {}).get("storyboard", []))
    video_mode_label = {"rendered": "成片已合成", "narrated_storyboard": "分镜+配音已就绪", "storyboard_only": "分镜脚本已就绪"}.get(
        (video or {}).get("mode"), "")

    materials_str = ', '.join(attrs.get('materials', [])) or "待补充"
    style_str = ', '.join(attrs.get('style_tags', [])) or "待补充"
    profit_str = insights.get('profit_margin_est') or "待估算"
    diff_angles = insights.get('differentiation_angles', [])
    diff_str = ', '.join(diff_angles[:2]) if diff_angles else "待挖掘"
    formula_str = benchmark.get('title_formula') or "待生成"

    # 合规状态：基于实际 platform_package 结果
    compliance_status = state.get("platform_package", {}).get("compliance_status", "UNKNOWN")
    compliance_label = {"PASS": "全部通过 (PASS)", "FAIL": "存在不合规项 (FAIL)", "UNKNOWN": "待复核"}.get(compliance_status, "待复核")

    # ── 动态读取 studio 真实结果 ──
    studio = state.get("studio_assets", {}) or {}
    scene_count = len(studio.get("lifestyle_scenes", []))
    image_engine = studio.get("image_engine", "source_material")
    has_tryon = bool(studio.get("virtual_tryon", {}).get("tryon_image_url"))
    material_mode = studio.get("material_mode", "source")

    if material_mode == "generated" and scene_count > 0:
        studio_line = f"AI 影棚已生成白底主图 + {scene_count} 组海外生活方式场景图（引擎：{image_engine}）"
    elif material_mode == "source" and state.get("product_image_url"):
        studio_line = f"商品原图已导入（{scene_count} 组场景图，可通过「按需补充」触发 AI 生成）"
    else:
        studio_line = "暂无素材（可上传商品图片后触发 AI 影棚生成）"

    tryon_line = "✅ AI 模特虚拟试穿效果图已生成" if has_tryon else "虚拟试穿：可通过增值服务按需触发"

    summary_text = f"""🎉 **GloLaunch AI 全链路智能上新任务已圆满完成！**

---

### 1. 🔍 商品智能识别
- **识别品类**：`{category}`
- **提取面料/风格**：{materials_str} | {style_str}

### 2. 📊 出海市场洞察
- **建议售价**：**{price}** (预估毛利率 {profit_str})
- **核心差异化卖点**：{diff_str}
- **挖掘高转化关键词**：{len(insights.get('high_converting_keywords', []))} 个

### 3. 🔥 爆款对标 + ✍️ 平台 Listing 撰写 ({platform})
- **对标标题公式**：{formula_str}
- **标题**：*{title[:90]}...*
- **生成内容**：{bullet_count} 条卖点描述 (Bullet Points) + 完整长描述 + Search Terms 后台关键词

### 4. 👗 AI 商品拍摄 + 🎬 带货视频 + 🌐 图片本地化
- 素材状态：{studio_line}
- {tryon_line}
- 商品展示视频：{video_shots} 个分镜脚本（{video_mode_label}）。
- 详情页图片已本地化处理 **{localized_count}** 张。

### 5. 🚀 平台发布包就绪
- 标准合规校验：{compliance_label}
- 生成系统 SKU：`{sku}`，已生成标准导出数据包。
"""

    trace_item = {
        "node": "respond",
        "status": "completed",
        "summary": "Agent 编排任务完成，已生成完整出海发布成果报告",
        "timestamp": time.time(),
        "detail": {"status": "SUCCESS"}
    }

    current_trace = state.get("trace", []) or []

    return {
        "messages": [AIMessage(content=summary_text)],
        "current_node": "respond",
        "trace": current_trace + [trace_item]
    }
