import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import asyncio
import json

from app.agent.graph import get_agent_graph
from langchain_core.messages import HumanMessage

async def main():
    print("=" * 60)
    print("🚀 测试 GloLaunch AI LangGraph 端到端执行链路")
    print("=" * 60)

    graph = get_agent_graph()

    initial_state = {
        "messages": [HumanMessage(content="帮我将这款夏季法式复古碎花连衣裙上架到 Amazon US。")],
        "user_intent": "full_launch",
        "target_platform": "Amazon",
        "target_market": "US",
        "product_image_url": "https://img.alicdn.com/imgextra/i1/6000000007892/O1CN01a2ZpQM1scXS5sBsAa_!!6000000007892-0-tps-400-400.jpg",
        "trace": []
    }

    config = {"configurable": {"thread_id": "test_thread_001"}}

    print("\n▶️ 开始逐步执行节点...")
    async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
        for node_name, node_update in event.items():
            trace = node_update.get("trace", [])
            last_trace = trace[-1] if trace else None
            summary = last_trace.get("summary") if last_trace else "完成"
            print(f"  ✅ [节点完成] {node_name:<20} -> {summary}")

    # 获取最终产出
    state = graph.get_state(config).values
    print("\n" + "=" * 60)
    print("🎉 最终执行成果摘要：")
    print("=" * 60)
    
    attrs = state.get("product_attributes", {})
    print(f"1. 识别品类: {attrs.get('category')} | 材质: {attrs.get('materials')}")

    insights = state.get("market_insights", {})
    print(f"2. 建议定价: {insights.get('recommended_price_range')} | 预估毛利: {insights.get('profit_margin_est')}")

    listing = state.get("listing_content", {})
    print(f"3. Amazon 标题: {listing.get('title')}")
    print(f"   五点描述数量: {len(listing.get('bullet_points', []))} 条")

    studio = state.get("studio_assets", {})
    print(f"4. 场景生成图: {len(studio.get('lifestyle_scenes', []))} 张 | 引擎: {studio.get('image_engine')}")

    pkg = state.get("platform_package", {})
    print(f"5. 发布合规状态: {pkg.get('compliance_status')} | SKU: {pkg.get('export_package', {}).get('sku')}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
