"""轻量本地验证：不调外部 API，只验证修复逻辑"""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ═══════════════════════════════════════════════════════════════
# Fix 1: category 兜底验证
# ═══════════════════════════════════════════════════════════════
print("=" * 50)
print("Fix 1: category 兜底逻辑验证")
print("=" * 50)

# 模拟 VL 返回 category=None 的情况
test_cases = [
    {"name": "VL 返回 category=None", "attrs": {"category": None, "category_family": "apparel"}, "expected": "跨境商品"},
    {"name": "VL 返回 category='' 空串", "attrs": {"category": "", "category_family": "home"}, "expected": "跨境商品"},
    {"name": "VL 返回 category='N/A'", "attrs": {"category": "N/A", "category_family": "general"}, "expected": "跨境商品"},
    {"name": "VL 返回正常 category", "attrs": {"category": "连衣裙", "category_family": "apparel"}, "expected": "连衣裙"},
    {"name": "VL 返回 category='  ' 纯空白", "attrs": {"category": "  ", "category_family": "toys"}, "expected": "跨境商品"},
    {"name": "category_family 无效值", "attrs": {"category": "T恤", "category_family": "invalid"}, "expected_cf": "general"},
    {"name": "category_family=None", "attrs": {"category": "裤子", "category_family": None}, "expected_cf": "general"},
]

passed = 0
for tc in test_cases:
    attrs = dict(tc["attrs"])

    # 复制 product.py 的兜底逻辑
    _cf = attrs.get("category_family")
    _valid_families = ("apparel", "electronics", "home", "beauty", "toys", "outdoor", "general")
    if not _cf or str(_cf).strip().lower() not in _valid_families:
        attrs["category_family"] = "general"

    _cat = attrs.get("category")
    if not _cat or (isinstance(_cat, str) and not _cat.strip()) or str(_cat).strip().lower() in ("n/a", "none", "null", "unknown", "未知"):
        # 无 product_category 和 title_1688 传入
        attrs["category"] = "跨境商品"

    ok = True
    if "expected" in tc:
        ok = ok and attrs.get("category") == tc["expected"]
    if "expected_cf" in tc:
        ok = ok and attrs.get("category_family") == tc["expected_cf"]

    status = "✅" if ok else "❌"
    print(f"  {status} {tc['name']}: category={attrs.get('category')}, family={attrs.get('category_family')}")
    if ok:
        passed += 1

print(f"\n  结果: {passed}/{len(test_cases)} 通过\n")


# ═══════════════════════════════════════════════════════════════
# Fix 2: SKU 生成验证
# ═══════════════════════════════════════════════════════════════
print("=" * 50)
print("Fix 2: SKU 生成逻辑验证")
print("=" * 50)

import re, time

def _build_deterministic_sku(platform, category, title):
    platform_code = {"Amazon": "AMZ", "Shopee": "SPE", "TikTok": "TTK"}.get(platform, "GLO")
    cat_clean = re.sub(r"[^\w]", "", category or "")[:10].upper() or "PROD"
    ts_suffix = str(int(time.time()))[-5:]
    return f"GLO-{platform_code}-{cat_clean}-{ts_suffix}"

sku_tests = [
    {"platform": "Amazon", "category": "跨境商品", "expect_prefix": "GLO-AMZ-"},
    {"platform": "Shopee", "category": "连衣裙", "expect_prefix": "GLO-SPE-"},
    {"platform": "TikTok", "category": None, "expect_prefix": "GLO-TTK-PROD-"},
    {"platform": "eBay", "category": "", "expect_prefix": "GLO-PROD-"},
]

for tc in sku_tests:
    sku = _build_deterministic_sku(tc["platform"], tc["category"], "")
    ok = sku.startswith(tc["expect_prefix"])
    status = "✅" if ok else "❌"
    print(f"  {status} {tc['platform']}/{tc['category']}: {sku}")

# 验证不会出现旧格式 ORG-BAMBOO-DESK-001
sku = _build_deterministic_sku("Amazon", "Bamboo Desk Organizer", "")
assert "ORG-" not in sku, f"SKU 包含旧格式前缀: {sku}"
assert "GLO-AMZ-" in sku, f"SKU 格式不正确: {sku}"
print(f"  ✅ 无旧格式串台: {sku}")
print()


# ═══════════════════════════════════════════════════════════════
# Fix 4: Listing Health Score 验证
# ═══════════════════════════════════════════════════════════════
print("=" * 50)
print("Fix 4: Listing Health Score 评分验证")
print("=" * 50)

from app.intelligence.listing_health import ListingHealthCalculator

calc = ListingHealthCalculator()

# 模拟 E2E 测试场景：有主图、无场景图、有品类但无材质/颜色
test_listing = {
    "title": "Bamboo Desktop Organizer for Vanity Office, Multi-Compartment Storage Box with Drawers, Natural Wood Makeup Stationery Holder for Women",
    "bullet_points": [
        "[PREMIUM BAMBOO MATERIAL] Made from natural bamboo with smooth finish...",
        "[MULTI-COMPARTMENT DESIGN] Multiple drawers and sections for organized storage...",
        "[SPACE-SAVING] Compact design perfect for vanity, desk, or dresser...",
        "[EASY ASSEMBLY] Simple setup with clear instructions included...",
        "[GIFT IDEA] Perfect gift for women who love organized spaces...",
    ],
    "product_description": "This bamboo desktop organizer is crafted from premium natural bamboo...",
    "search_terms": "bamboo organizer vanity storage box makeup stationery holder desk accessories",
    "main_image_url": "https://img.alicdn.com/test.jpg",
}

# 模拟 product_attributes（VL 提取了品类和风格但无材质/颜色）
test_attrs = {
    "category": "桌面收纳架",
    "category_family": "home",
    "main_color": "",  # VL 未提取到
    "materials": [],   # VL 未提取到
    "style_tags": ["简约", "收纳"],
    "key_specs": ["多格设计", "带抽屉"],
    "target_occasions": ["办公", "化妆台"],
    "target_gender": "女",
    "season": "四季通用",
}
calc._product_attrs = test_attrs

# 模拟 publish_package.py 的品类注入逻辑
if not test_listing.get("category") and test_attrs.get("category"):
    test_listing = dict(test_listing)
    test_listing["category"] = test_attrs["category"]

# 模拟 assets（有主图，无场景图）
test_assets = {
    "white_background_main": "https://img.alicdn.com/test.jpg",
    "lifestyle_scenes": [],
    "original_images": [],
}

health = calc.calculate(
    listing=test_listing,
    platform="Amazon",
    assets=test_assets,
)

print(f"  Overall Score: {health.overall_score}/100 ({health.grade})")
print(f"  Status: {health.status}")
print(f"  维度明细:")

dimensions = [
    ("标题质量", health.title_health),
    ("五点描述", health.bullets_health),
    ("商品描述", health.description_health),
    ("图片素材", health.images_health),
    ("关键词覆盖", health.keywords_health),
    ("属性完整度", health.attributes_health),
    ("类目匹配", health.category_health),
    ("合规检查", health.compliance_health),
]

for name, dim in dimensions:
    icon = "✅" if dim.score >= 70 else "⚠️"
    print(f"    {icon} {name}: {dim.score}/100 — {dim.details}")

print(f"\n  改进建议: {health.improvement_priorities}")

# 验证分数提升
if health.overall_score >= 75:
    print(f"\n  ✅ Health Score {health.overall_score} >= 75 (B 级以上)")
elif health.overall_score >= 65:
    print(f"\n  🟡 Health Score {health.overall_score} 在 65-74 区间 (C 级)")
else:
    print(f"\n  ❌ Health Score {health.overall_score} < 65")

print("\n" + "=" * 50)
print("本地验证完成")
print("=" * 50)
