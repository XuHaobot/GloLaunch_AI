"""
JustOneAPI 1688 商品详情接口 —— 独立测试脚本

用法:
  1. 设置环境变量 JUSTONEAPI_API_KEY（或在项目 .env 中配置）
  2. 运行: python test_1688_justoneapi.py <1688商品ID或链接>

示例:
  python test_1688_justoneapi.py 742831567023
  python test_1688_justoneapi.py "https://detail.1688.com/offer/742831567023.html"
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# 将 backend 目录加入 sys.path，以便导入 app.* 模块
BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

import httpx


# ─── 配置 ─────────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    """优先从环境变量读取，其次尝试从 .env 文件读取"""
    key = os.environ.get("JUSTONEAPI_API_KEY", "")
    if key:
        return key

    env_file = BACKEND_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("JUSTONEAPI_API_KEY="):
                val = line.split("=", 1)[1].strip().strip("\"'")
                if val:
                    return val

    return ""


BASE_URL = "https://api.justoneapi.com"
ENDPOINT = "/api/1688/get-item-detail/v1"


# ─── 工具函数（从 alibaba_1688.py 复制，保持独立无依赖）─────────────────────────

import re

_ITEM_ID_RE = re.compile(r"(?:offerId|id)[=/](\d{10,18})|/offer/(\d{10,18})")
_PURE_ID_RE = re.compile(r"^\d{10,18}$")


def extract_item_id(url_or_id: str):
    """从 URL 或纯 ID 中提取 1688 商品 ID"""
    url_or_id = url_or_id.strip()
    if _PURE_ID_RE.match(url_or_id):
        return url_or_id
    m = _ITEM_ID_RE.search(url_or_id)
    if m:
        return m.group(1) or m.group(2)
    parts = url_or_id.rstrip("/").split("/")
    for part in reversed(parts):
        if _PURE_ID_RE.match(part):
            return part
    return None


# ─── 主逻辑 ───────────────────────────────────────────────────────────────────

async def fetch_1688_detail(api_key: str, item_id: str) -> dict:
    """调用 JustOneAPI 1688 商品详情接口，返回完整 JSON"""
    url = f"{BASE_URL}{ENDPOINT}"
    params = {"token": api_key, "itemId": item_id}

    print(f"\n{'='*60}")
    print(f"请求接口: {url}")
    print(f"商品 ID:  {item_id}")
    print(f"{'='*60}\n")

    start = time.time()

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        body = resp.json()

    elapsed = time.time() - start
    print(f"耗时: {elapsed:.2f}s | HTTP {resp.status_code}")
    return body


def print_raw_response(body: dict):
    """格式化打印原始响应"""
    code = body.get("code", -1)
    message = body.get("message", "")
    data = body.get("data", {})
    request_id = body.get("requestId", "")

    print(f"\n{'─'*60}")
    print("原始响应概览")
    print(f"{'─'*60}")
    print(f"  code:      {code}")
    print(f"  message:   {message}")
    print(f"  requestId: {request_id}")

    if code != 0:
        print(f"\n  [错误] 接口返回非 0 状态码，详见 JustOneAPI 文档")
        return

    # 打印 data 层级的键
    print(f"\n  data 字段 ({len(data)} 个顶级键):")
    for k, v in data.items():
        vtype = type(v).__name__
        if isinstance(v, str):
            preview = v[:80] + ("..." if len(v) > 80 else "")
            print(f"    {k}: ({vtype}) \"{preview}\"")
        elif isinstance(v, list):
            print(f"    {k}: ({vtype}) [{len(v)} 项]")
        elif isinstance(v, dict):
            print(f"    {k}: ({vtype}) {{...}}")
        else:
            print(f"    {k}: ({vtype}) {v}")


def print_product_summary(body: dict):
    """从响应中提取关键商品信息并友好展示"""
    data = body.get("data", {})
    if not data:
        return

    print(f"\n{'─'*60}")
    print("商品信息摘要")
    print(f"{'─'*60}")

    # 基础
    title = data.get("title", "(无标题)")
    offer_id = data.get("offer_id", "(无 ID)")
    print(f"  商品标题: {title}")
    print(f"  Offer ID: {offer_id}")

    # 供应商
    supplier = data.get("supplier_info", {})
    if supplier:
        company = supplier.get("company_name") or supplier.get("shop_name", "")
        print(f"  供应商:   {company}")

    # 价格
    price_info = data.get("price_info", {})
    if price_info:
        retail = price_info.get("retail_price", "")
        step = price_info.get("step_price", [])
        if retail:
            print(f"  零售参考价: ¥{retail}")
        if step:
            steps_str = " / ".join(
                f"≥{s.get('begin_amount', '?')}件 ¥{s.get('price', '?')}"
                for s in step[:3]
            )
            print(f"  阶梯价:   {steps_str}")

    # 库存 & 发货
    stock = data.get("stock_info", {})
    if stock:
        moq = stock.get("moq", "")
        total = stock.get("total_stock", "")
        delivery = stock.get("delivery_time", "")
        parts = []
        if moq: parts.append(f"MOQ={moq}")
        if total: parts.append(f"库存={total}")
        if delivery: parts.append(f"发货={delivery}")
        if parts:
            print(f"  供货信息: {', '.join(parts)}")

    # 图片
    images = data.get("image_info", {})
    if images:
        main_imgs = images.get("main_images", [])
        detail_imgs = images.get("detail_images", [])
        print(f"  图片数量: 主图 {len(main_imgs)} 张, 详情图 {len(detail_imgs)} 张")

    # SKU
    sku_list = data.get("sku_list", [])
    if sku_list:
        print(f"  SKU 数量: {len(sku_list)} 个")
        # 展示前 5 个 SKU
        for sku in sku_list[:5]:
            spec = sku.get("spec_text", "")
            price = sku.get("price", "")
            stock_n = sku.get("stock", "")
            print(f"    - {spec}  ¥{price}  库存{stock_n}")
        if len(sku_list) > 5:
            print(f"    ... 及其他 {len(sku_list) - 5} 个 SKU")

    # 产品参数
    params = data.get("product_params", [])
    if params:
        print(f"  产品参数 ({len(params)} 项):")
        for p in params[:8]:
            print(f"    {p.get('name', '')}: {p.get('value', '')}")
        if len(params) > 8:
            print(f"    ... 及其他 {len(params) - 8} 项")


def save_response(body: dict, item_id: str):
    """将完整响应保存为 JSON 文件，方便调试"""
    out_dir = BACKEND_DIR / "test_output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"1688_{item_id}.json"
    out_path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完整响应已保存: {out_path}")


async def main():
    # ── 参数解析 ──
    if len(sys.argv) < 2:
        print(__doc__)
        print("错误: 请提供 1688 商品 ID 或链接")
        print("\n示例:")
        print('  python test_1688_justoneapi.py 742831567023')
        print('  python test_1688_justoneapi.py "https://detail.1688.com/offer/742831567023.html"')
        sys.exit(1)

    raw_input = sys.argv[1]

    # ── 获取 API Key ──
    api_key = get_api_key()
    if not api_key:
        print("错误: 未找到 JUSTONEAPI_API_KEY")
        print("请设置环境变量: set JUSTONEAPI_API_KEY=your_key")
        print("或在 backend/.env 中添加: JUSTONEAPI_API_KEY=your_key")
        sys.exit(1)

    # ── 提取商品 ID ──
    item_id = extract_item_id(raw_input)
    if not item_id:
        print(f"错误: 无法从输入中提取商品 ID: {raw_input}")
        print("请输入纯数字 ID 或完整的 1688 商品链接")
        sys.exit(1)

    print(f"提取到商品 ID: {item_id}")

    # ── 调用接口 ──
    try:
        body = await fetch_1688_detail(api_key, item_id)
    except httpx.TimeoutException:
        print("\n[超时] 请求超过 120 秒未响应，请检查网络或稍后重试")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"\n[HTTP 错误] 状态码: {e.response.status_code}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[异常] {type(e).__name__}: {e}")
        sys.exit(1)

    # ── 展示结果 ──
    print_raw_response(body)
    print_product_summary(body)
    save_response(body, item_id)

    # ── 同时测试 ProductProfile 映射（如果 app 模块可用）──
    try:
        from app.sources.alibaba_1688 import _map_to_product_profile
        profile = _map_to_product_profile(body, item_id)
        print(f"\n{'─'*60}")
        print("ProductProfile 映射结果")
        print(f"{'─'*60}")
        print(f"  product_id:       {profile.product_id}")
        print(f"  title:            {profile.title}")
        print(f"  category_family:  {profile.category_family.value}")
        print(f"  materials:        {profile.materials}")
        print(f"  colors:           {profile.colors}")
        print(f"  sizes:            {profile.sizes}")
        print(f"  supply_price_cny: {profile.supply_price_cny}")
        print(f"  moq:              {profile.moq}")
        print(f"  supplier_name:    {profile.supplier_name}")
        print(f"  images_count:     {len(profile.original_images)}")
        print(f"  main_image:       {profile.main_image_url[:80]}...")
        print(f"  confidence:       {profile.confidence}")
        print(f"  fingerprint:      {profile.identity_fingerprint}")
        print(f"\n映射成功!")
    except ImportError:
        print("\n[提示] app 模块未安装，跳过 ProductProfile 映射测试")
    except Exception as e:
        print(f"\n[映射异常] {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
