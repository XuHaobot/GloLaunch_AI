"""publish_package_node —— 发布包组装与人工审核节点。

在 Listing 生成、素材准备、合规检查完成后，
将所有成果打包为 PublishPackage，等待人工审核。
实现 Human-in-the-loop 的人机协同模式。
"""
import json
import logging
import os
import time
import zipfile
from pathlib import Path
from typing import Dict, Any

import httpx

from app.agent.state import AgentState
from app.domain.enums import ComplianceStatus, PublishDecision
from app.domain.publish import PublishPackage, PublishCheckItem
from app.domain.listing import ListingHealth
from app.domain.opportunity import OpportunityScore
from app.intelligence.listing_health import ListingHealthCalculator

logger = logging.getLogger(__name__)


def _generate_package_zip(package_data: dict, output_dir: str) -> str:
    """Generate a real ZIP file containing all publish package data.

    Args:
        package_data: The full PublishPackage dict (from model_dump).
        output_dir: Directory where the ZIP will be written.

    Returns:
        Absolute path to the generated ZIP file.
    """
    os.makedirs(output_dir, exist_ok=True)
    zip_path = os.path.join(output_dir, "GloLaunch_Product_Package.zip")

    # Collect image URLs from various sections
    image_urls: list[str] = []
    listing_snapshot = package_data.get("listing_snapshot", {})
    if isinstance(listing_snapshot, dict):
        for key in ("main_image_url", "images"):
            val = listing_snapshot.get(key)
            if isinstance(val, str) and val:
                image_urls.append(val)
            elif isinstance(val, list):
                image_urls.extend(u for u in val if isinstance(u, str) and u)

    assets_summary = package_data.get("assets_summary", {})
    # Try to pull extra image URLs from state-level data stored in the package
    for extra_key in ("image_urls", "imported_images", "studio_images"):
        extra = package_data.get(extra_key, [])
        if isinstance(extra, list):
            image_urls.extend(u for u in extra if isinstance(u, str) and u)

    # Build README content
    sku = package_data.get("sku", "N/A")
    platform = package_data.get("platform", "N/A")
    market = package_data.get("market", "N/A")
    compliance = package_data.get("compliance_status", "N/A")
    health = package_data.get("listing_health", {})
    health_score = health.get("overall_score", "N/A")
    health_grade = health.get("grade", "N/A")

    readme_lines = [
        f"# GloLaunch Product Package",
        f"",
        f"- **SKU**: {sku}",
        f"- **Platform**: {platform}",
        f"- **Market**: {market}",
        f"- **Compliance**: {compliance}",
        f"- **Listing Health**: {health_score}/100 (Grade {health_grade})",
        f"",
        f"## Contents",
        f"",
        f"| File | Description |",
        f"|------|-------------|",
        f"| product.json | Product attributes |",
        f"| listing.json | Listing content |",
        f"| market-analysis.json | Market insights |",
        f"| opportunity-score.json | Opportunity score data |",
        f"| health-check.json | Listing health data |",
        f"| images/ | Product images (if available) |",
        f"",
    ]
    readme_content = "\n".join(readme_lines)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # JSON files from package sections
        json_files = {
            "product.json": package_data.get("listing_snapshot", {}).get("product_attributes", {}),
            "listing.json": package_data.get("listing_snapshot", {}),
            "market-analysis.json": package_data.get("market_analysis", package_data.get("listing_snapshot", {}).get("market_data", {})),
            "opportunity-score.json": package_data.get("opportunity_score", {}),
            "health-check.json": package_data.get("listing_health", {}),
        }

        for filename, data in json_files.items():
            zf.writestr(filename, json.dumps(data, indent=2, ensure_ascii=False, default=str))

        # README
        zf.writestr("README.md", readme_content)

        # Download images into images/ directory inside the ZIP
        if image_urls:
            _download_images_into_zip(zf, image_urls)

    logger.info("Package ZIP generated: %s", zip_path)
    return zip_path


def _download_images_into_zip(zf: zipfile.ZipFile, urls: list[str]) -> None:
    """Attempt to download images from URLs and write them into the ZIP.

    Silently skips any URL that fails to download.
    """
    seen: set[str] = set()
    idx = 0
    timeout = httpx.Timeout(10.0)

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            try:
                resp = client.get(url)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                # Determine extension from content-type or URL
                ext = _ext_from_content_type(content_type)
                if not ext:
                    ext = _ext_from_url(url)
                if not ext:
                    ext = ".jpg"
                idx += 1
                arcname = f"images/image_{idx:03d}{ext}"
                zf.writestr(arcname, resp.content)
            except Exception as exc:
                logger.debug("Skipping image %s: %s", url, exc)


def _ext_from_content_type(ct: str) -> str:
    """Map a Content-Type header to a file extension."""
    ct = ct.lower().split(";")[0].strip()
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/svg+xml": ".svg",
    }
    return mapping.get(ct, "")


def _ext_from_url(url: str) -> str:
    """Extract file extension from a URL path."""
    path = url.split("?")[0].split("#")[0]
    _, ext = os.path.splitext(path)
    return ext.lower() if ext else ""


async def publish_package_node(state: AgentState) -> Dict[str, Any]:
    """发布包组装节点：汇总成果、计算 Listing Health、等待审核"""
    platform = state.get("target_platform", "Amazon")
    market = state.get("target_market", "US")
    # 安全提取 thread_id：messages 是 LangChain Message 对象，不是 dict
    thread_id = ""
    messages = state.get("messages", [])
    if messages:
        first_msg = messages[0]
        if hasattr(first_msg, "additional_kwargs"):
            thread_id = first_msg.additional_kwargs.get("thread_id", "")
        elif isinstance(first_msg, dict):
            thread_id = first_msg.get("additional_kwargs", {}).get("thread_id", "")

    listing = state.get("listing_content", {})
    platform_pkg = state.get("platform_package", {})
    studio = state.get("studio_assets", {})
    video = state.get("video_package", {})
    opportunity_data = state.get("opportunity_score")
    attrs = state.get("product_attributes", {})

    # ── 将 product_attributes 的品类注入 listing（供 Health 类目匹配维度使用）──
    if not listing.get("category") and attrs.get("category"):
        listing = dict(listing)  # 浅拷贝避免污染原始 state
        listing["category"] = attrs["category"]

    # ── 计算 Listing Health Score ──
    calculator = ListingHealthCalculator()
    # 将 product_attributes 注入计算器，供属性完整度维度使用
    calculator._product_attrs = attrs
    # 合并所有图片数据到 assets，供图片维度评分
    health_assets = dict(studio or {})
    if state.get("product_image_url") and not health_assets.get("white_background_main"):
        health_assets["white_background_main"] = state["product_image_url"]
    if state.get("imported_images") and not health_assets.get("original_images"):
        health_assets["original_images"] = state["imported_images"]
    health = calculator.calculate(
        listing=listing,
        platform=platform,
        assets=health_assets,
    )

    # ── 组装合规检查项 ──
    check_items = []

    # 从 platform_package 中提取已有的合规检查结果
    rule_results = platform_pkg.get("rule_check_results", [])
    for rule in rule_results:
        status_str = rule.get("status", "PASS")
        try:
            status = ComplianceStatus(status_str)
        except ValueError:
            status = ComplianceStatus.PASS
        check_items.append(PublishCheckItem(
            name=rule.get("rule_name", "Unknown"),
            status=status,
            details=rule.get("details", ""),
        ))

    # Listing Health 维度的检查
    if health.status == ComplianceStatus.FAIL:
        check_items.append(PublishCheckItem(
            name="Listing Quality Check",
            status=ComplianceStatus.FAIL,
            details=f"Listing 质量评分 {health.overall_score}/100 ({health.grade})，存在必须修复的问题",
        ))
    elif health.status == ComplianceStatus.WARNING:
        check_items.append(PublishCheckItem(
            name="Listing Quality Check",
            status=ComplianceStatus.WARNING,
            details=f"Listing 质量评分 {health.overall_score}/100 ({health.grade})，建议优化",
        ))
    else:
        check_items.append(PublishCheckItem(
            name="Listing Quality Check",
            status=ComplianceStatus.PASS,
            details=f"Listing 质量评分 {health.overall_score}/100 ({health.grade})，质量良好",
        ))

    # 综合合规状态
    if any(ci.status == ComplianceStatus.FAIL for ci in check_items):
        overall_compliance = ComplianceStatus.FAIL
    elif any(ci.status == ComplianceStatus.WARNING for ci in check_items):
        overall_compliance = ComplianceStatus.WARNING
    else:
        overall_compliance = ComplianceStatus.PASS

    # ── 组装 SKU：优先用 platform_node 生成的确定性 SKU，绝不使用硬编码 ──
    sku = platform_pkg.get("export_package", {}).get("sku", "")
    if not sku:
        # 降级：用与 platform.py _build_deterministic_sku 相同的逻辑重新生成
        import re as _re
        platform_code = {"Amazon": "AMZ", "Shopee": "SPE", "TikTok": "TTK"}.get(platform, "GLO")
        cat_raw = attrs.get("category") or "PROD"
        cat_clean = _re.sub(r"[^\w]", "", str(cat_raw))[:10].upper() or "PROD"
        ts_suffix = str(int(time.time()))[-5:]
        sku = f"GLO-{platform_code}-{cat_clean}-{ts_suffix}"

    # ── 素材摘要 ──
    assets_summary = {
        "total_images": len(studio.get("lifestyle_scenes", [])) + (1 if state.get("product_image_url") else 0),
        "has_video": bool(video and video.get("mode")),
        "has_tryon": bool(studio.get("tryon_result")),
        "localized_images": len((state.get("localized_images") or {}).get("items", [])),
    }

    # ── 构建 PublishPackage ──
    # 构建 OpportunityScore（如果有数据）
    opp_score = None
    if opportunity_data:
        try:
            opp_score = OpportunityScore(**opportunity_data)
        except Exception:
            pass

    package = PublishPackage(
        thread_id=thread_id,
        sku=sku,
        platform=platform,
        market=market,
        created_at=time.time(),
        listing_snapshot=listing,
        assets_summary=assets_summary,
        video_summary=video if video else None,
        listing_health=health,
        opportunity_score=opp_score,
        compliance_status=overall_compliance,
        check_items=check_items,
        rule_check_results=rule_results,
        review_decision=PublishDecision.NEEDS_REVISION,  # 默认需要审核
        ready_to_publish=overall_compliance != ComplianceStatus.FAIL,
        standard_feed_ready=overall_compliance == ComplianceStatus.PASS,
        export_formats=["json", "csv"],
    )

    # ── 生成 ZIP 发布包 ──
    backend_root = Path(__file__).resolve().parent.parent.parent.parent
    packages_dir = str(backend_root / "packages")

    # Merge extra image URLs into package dump for ZIP generation
    package_dump = package.model_dump()
    package_dump["image_urls"] = []
    if state.get("product_image_url"):
        package_dump["image_urls"].append(state["product_image_url"])
    for u in state.get("imported_images", []):
        package_dump["image_urls"].append(u)
    for scene in studio.get("lifestyle_scenes", []):
        scene_url = scene.get("image_url", "") if isinstance(scene, dict) else str(scene)
        if scene_url:
            package_dump["image_urls"].append(scene_url)

    package_file_path = _generate_package_zip(package_dump, packages_dir)
    package_id = f"pkg-{thread_id or sku}-{int(time.time())}"

    trace_item = {
        "node": "publish_package",
        "status": "completed",
        "summary": (
            f"发布包已组装 (SKU: {sku})，"
            f"Listing Health: {health.overall_score}/100 ({health.grade})，"
            f"合规状态: {overall_compliance.value}，"
            f"ZIP: {package_file_path}，"
            f"待人工审核"
        ),
        "timestamp": time.time(),
        "detail": package_dump,
    }

    current_trace = state.get("trace", []) or []

    return {
        "publish_package": package_dump,
        "listing_health": health.model_dump(),
        "package_file_path": package_file_path,
        "package_id": package_id,
        "current_node": "publish_package",
        "trace": current_trace + [trace_item],
    }
