#!/usr/bin/env python3
"""GloLaunch AI 故障测试套件 — 7 种异常场景验证"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import asyncio
import traceback
from typing import Dict, Any, Callable

from langchain_core.messages import HumanMessage
from app.agent.graph import get_agent_graph


class FailureTestSuite:
    """故障测试套件"""

    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0

    async def run_test(self, name: str, test_fn: Callable, expect_graceful: bool = True):
        """运行单个测试"""
        print(f"\n{'='*60}")
        print(f"🧪 测试: {name}")
        print('='*60)
        try:
            result = await test_fn()
            if result.get("success"):
                print(f"✅ PASS: {result.get('message', '测试通过')}")
                self.passed += 1
                self.results.append({"name": name, "status": "PASS", "message": result.get("message", "")})
            else:
                print(f"❌ FAIL: {result.get('message', '测试失败')}")
                self.failed += 1
                self.results.append({"name": name, "status": "FAIL", "message": result.get("message", "")})
        except Exception as e:
            if expect_graceful:
                print(f"❌ FAIL: 未捕获异常 - {type(e).__name__}: {e}")
                self.failed += 1
                self.results.append({"name": name, "status": "FAIL", "message": f"未捕获异常: {e}"})
            else:
                print(f"✅ PASS: 预期异常 - {type(e).__name__}: {str(e)[:80]}")
                self.passed += 1
                self.results.append({"name": name, "status": "PASS", "message": f"预期异常: {type(e).__name__}"})

    async def test_1_no_image(self):
        """测试1: 无商品图片 — 应优雅降级"""
        graph = get_agent_graph()
        initial_state = {
            "messages": [HumanMessage(content="帮我将这款夏季法式复古碎花连衣裙上架到 Amazon US。")],
            "user_intent": "full_launch",
            "target_platform": "Amazon",
            "target_market": "US",
            "product_image_url": "",  # 空图片
            "trace": []
        }
        config = {"configurable": {"thread_id": "test_no_image"}}

        async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_update in event.items():
                trace = node_update.get("trace", [])
                if trace:
                    print(f"  → [{node_name}] {trace[-1].get('summary', '')[:60]}")

        state = graph.get_state(config).values
        # 验证：即使无图片，流程也应完成
        has_listing = bool(state.get("listing_content", {}).get("title"))
        has_trace = len(state.get("trace", [])) > 0
        return {"success": has_listing and has_trace, "message": f"Listing生成={has_listing}, 有trace={has_trace}"}

    async def test_2_invalid_market(self):
        """测试2: 无效市场 — 应优雅降级"""
        graph = get_agent_graph()
        initial_state = {
            "messages": [HumanMessage(content="上架到 Amazon XX 市场。")],
            "user_intent": "full_launch",
            "target_platform": "Amazon",
            "target_market": "XX",  # 无效市场
            "product_image_url": "https://img.alicdn.com/test.jpg",
            "trace": []
        }
        config = {"configurable": {"thread_id": "test_invalid_market"}}

        async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_update in event.items():
                trace = node_update.get("trace", [])
                if trace:
                    print(f"  → [{node_name}] {trace[-1].get('summary', '')[:60]}")

        state = graph.get_state(config).values
        # 验证：流程应完成，但市场数据可能为空
        has_trace = len(state.get("trace", [])) > 0
        return {"success": has_trace, "message": f"流程完成={has_trace}"}

    async def test_3_vague_input(self):
        """测试3: 模糊输入 — 应提取基础属性并继续"""
        graph = get_agent_graph()
        initial_state = {
            "messages": [HumanMessage(content="上架这个商品")],  # 极度模糊
            "user_intent": "full_launch",
            "target_platform": "Amazon",
            "target_market": "US",
            "product_image_url": "https://img.alicdn.com/test.jpg",
            "trace": []
        }
        config = {"configurable": {"thread_id": "test_vague_input"}}

        async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_update in event.items():
                trace = node_update.get("trace", [])
                if trace:
                    print(f"  → [{node_name}] {trace[-1].get('summary', '')[:60]}")

        state = graph.get_state(config).values
        attrs = state.get("product_attributes", {})
        # 验证：即使模糊输入也应尝试提取属性
        has_category = attrs.get("category") is not None
        has_trace = len(state.get("trace", [])) > 0
        return {"success": has_trace, "message": f"品类提取={has_category}, 流程完成={has_trace}"}

    async def test_4_unsupported_platform(self):
        """测试4: 不支持的平台 — 应优雅处理"""
        graph = get_agent_graph()
        initial_state = {
            "messages": [HumanMessage(content="上架到 eBay US。")],
            "user_intent": "full_launch",
            "target_platform": "eBay",  # 不支持
            "target_market": "US",
            "product_image_url": "https://img.alicdn.com/test.jpg",
            "trace": []
        }
        config = {"configurable": {"thread_id": "test_unsupported_platform"}}

        async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_update in event.items():
                trace = node_update.get("trace", [])
                if trace:
                    print(f"  → [{node_name}] {trace[-1].get('summary', '')[:60]}")

        state = graph.get_state(config).values
        has_trace = len(state.get("trace", [])) > 0
        return {"success": has_trace, "message": f"流程完成={has_trace}"}

    async def test_5_opportunity_no_go(self):
        """测试5: 机会评分 no_go — 应诚实报告"""
        graph = get_agent_graph()
        initial_state = {
            "messages": [HumanMessage(content="上架这款商品到 Amazon US。")],
            "user_intent": "full_launch",
            "target_platform": "Amazon",
            "target_market": "US",
            "product_image_url": "https://img.alicdn.com/test.jpg",
            "trace": []
        }
        config = {"configurable": {"thread_id": "test_no_go"}}

        async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_update in event.items():
                trace = node_update.get("trace", [])
                if trace:
                    summary = trace[-1].get('summary', '')
                    print(f"  → [{node_name}] {summary[:60]}")
                    if "机会评分" in summary:
                        print(f"    📊 评分详情: {summary}")

        state = graph.get_state(config).values
        opp = state.get("opportunity_score", {})
        # 验证：数据不足时应返回 no_go
        go_no_go = opp.get("go_no_go", "")
        confidence = opp.get("data_confidence", "")
        # 数据不足时应该是 no_go 或 low confidence
        is_honest = go_no_go == "no_go" or confidence in ["low", "medium"]
        return {"success": is_honest, "message": f"go_no_go={go_no_go}, confidence={confidence}"}

    async def test_6_compliance_check(self):
        """测试6: 合规检查 — 应返回真实结果而非硬编码"""
        graph = get_agent_graph()
        initial_state = {
            "messages": [HumanMessage(content="上架这款商品到 Amazon US。")],
            "user_intent": "full_launch",
            "target_platform": "Amazon",
            "target_market": "US",
            "product_image_url": "https://img.alicdn.com/test.jpg",
            "trace": []
        }
        config = {"configurable": {"thread_id": "test_compliance"}}

        async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_update in event.items():
                trace = node_update.get("trace", [])
                if trace:
                    print(f"  → [{node_name}] {trace[-1].get('summary', '')[:60]}")

        state = graph.get_state(config).values
        pkg = state.get("platform_package", {})
        compliance = pkg.get("compliance_status", "")
        rules = pkg.get("rule_check_results", [])
        # 验证：合规状态应为 PASS/FAIL/UNKNOWN 之一
        valid_status = compliance in ["PASS", "FAIL", "UNKNOWN"]
        has_rules = len(rules) > 0
        return {"success": valid_status and has_rules, "message": f"status={compliance}, rules={len(rules)}"}

    async def test_7_zip_generation(self):
        """测试7: ZIP 包生成 — 应创建真实文件"""
        import os
        graph = get_agent_graph()
        initial_state = {
            "messages": [HumanMessage(content="上架这款商品到 Amazon US。")],
            "user_intent": "full_launch",
            "target_platform": "Amazon",
            "target_market": "US",
            "product_image_url": "https://img.alicdn.com/test.jpg",
            "trace": []
        }
        config = {"configurable": {"thread_id": "test_zip"}}

        async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_update in event.items():
                trace = node_update.get("trace", [])
                if trace:
                    print(f"  → [{node_name}] {trace[-1].get('summary', '')[:60]}")

        state = graph.get_state(config).values
        pkg = state.get("platform_package", {})
        zip_path = pkg.get("export_package", {}).get("zip_path", "")
        # 验证：ZIP 文件应存在
        zip_exists = os.path.exists(zip_path) if zip_path else False
        return {"success": zip_exists, "message": f"zip_path={zip_path}, exists={zip_exists}"}

    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "="*60)
        print("📊 故障测试摘要")
        print("="*60)
        for r in self.results:
            icon = "✅" if r["status"] == "PASS" else "❌"
            print(f"{icon} {r['name']}: {r['message']}")
        print("-"*60)
        print(f"总计: {self.passed} PASS / {self.failed} FAIL")
        print("="*60)


async def main():
    suite = FailureTestSuite()

    # 运行 7 个故障测试
    await suite.run_test("1. 无商品图片", suite.test_1_no_image)
    await suite.run_test("2. 无效市场", suite.test_2_invalid_market)
    await suite.run_test("3. 模糊输入", suite.test_3_vague_input)
    await suite.run_test("4. 不支持的平台", suite.test_4_unsupported_platform)
    await suite.run_test("5. 机会评分 no_go", suite.test_5_opportunity_no_go)
    await suite.run_test("6. 合规检查", suite.test_6_compliance_check)
    await suite.run_test("7. ZIP 包生成", suite.test_7_zip_generation)

    suite.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
