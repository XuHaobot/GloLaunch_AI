"""AI 虚拟试穿服务 —— 从 E:\\aitryon 移植的核心模块。

使用阿里云百炼 DashScope aitryon 专用虚拟试穿模型：
  - 输入: 模特全身照 + 衣物平拍图
  - 输出: 模特穿着该衣物的合成效果图
  - 保留模特面部特征，衣物颜色/纹理/版型与参考图一致

流程:
  1. 下载商品图 → 本地 bytes
  2. 生成模特底图（wan2.7 白底全身模特照）
  3. 两张图分别上传 DashScope OSS → oss:// URL
  4. 调用 aitryon API（异步任务）
  5. 轮询获取结果 → 下载到本地 uploads/
"""
import asyncio
import io
import json
import logging
import os
import sys
import time
import uuid
from typing import Dict, Any, Optional

import httpx
from PIL import Image

from app.config import get_settings
from app.services.media import generate_image, _gateway_root

logger = logging.getLogger("aitryon")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("[aitryon] %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


# ── 图片预处理 ──

def _resize_image(image_bytes: bytes, max_size: int = 1024) -> bytes:
    """缩放图片，最长边不超过 max_size，转为 RGB JPEG"""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


# ── DashScope OSS 上传 ──

async def _upload_to_dashscope(image_bytes: bytes, filename: str = "image.jpg") -> Optional[str]:
    """上传图片到 DashScope，获取 oss:// 临时 URL"""
    settings = get_settings()
    api_key = settings.model_router_api_key

    try:
        # Step 1: 获取上传策略
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://dashscope.aliyuncs.com/api/v1/uploads",
                params={"action": "getPolicy", "model": "aitryon"},
                headers={"Authorization": f"Bearer {api_key}"},
            )
        policy_data = resp.json()
        if "data" not in policy_data:
            logger.error(f"获取上传策略失败: {json.dumps(policy_data, ensure_ascii=False)[:300]}")
            return None

        data = policy_data["data"]
        upload_host = data.get("upload_host", "") or data.get("host", "")
        upload_dir = data.get("upload_dir", "") or data.get("dir", "")
        policy = data.get("policy", "")
        signature = data.get("signature", "")
        access_id = data.get("oss_access_key_id", "") or data.get("OSSAccessKeyId", "")

        if upload_host and not upload_host.startswith("http"):
            upload_host = "https://" + upload_host

        file_key = f"{upload_dir}/{uuid.uuid4().hex}_{filename}"

        # Step 2: 上传到 OSS
        form_data = {
            "key": file_key,
            "policy": policy,
            "OSSAccessKeyId": access_id,
            "signature": signature,
            "x-oss-object-acl": data.get("x_oss_object_acl", "private"),
            "x-oss-forbid-overwrite": data.get("x_oss_forbid_overwrite",
                                                data.get("x_oss_forbidden_overwrite", "true")),
            "success_action_status": "200",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                upload_host,
                data=form_data,
                files={"file": (filename, io.BytesIO(image_bytes), "image/jpeg")},
            )

        if resp.status_code in (200, 204):
            oss_url = f"oss://{file_key}"
            logger.info(f"已上传到 DashScope: {oss_url}")
            return oss_url
        else:
            logger.error(f"OSS 上传失败: HTTP {resp.status_code}, {resp.text[:200]}")
            return None

    except Exception as e:
        logger.error(f"上传异常: {e}")
        return None


# ── aitryon API 调用 ──

async def _call_aitryon_api(
    person_oss_url: str,
    garment_oss_url: str,
) -> Dict[str, Any]:
    """调用 DashScope aitryon 虚拟试穿 API，返回 {success, image_url, message}"""
    settings = get_settings()
    api_key = settings.model_router_api_key

    payload = {
        "model": "aitryon",
        "input": {
            "person_image_url": person_oss_url,
            "top_garment_url": garment_oss_url,
        },
        "parameters": {
            "resolution": -1,
            "restore_face": True,
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
        "X-DashScope-OssResourceResolve": "enable",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://dashscope.aliyuncs.com/api/v1/services/aigc/image2image/image-synthesis",
                headers=headers,
                json=payload,
            )
        data = resp.json()
        task_id = data.get("output", {}).get("task_id")
        if not task_id:
            msg = data.get("message", "aitryon API 提交失败")
            logger.error(f"提交失败: {json.dumps(data, ensure_ascii=False)[:300]}")
            return {"success": False, "image_url": None, "message": msg}

        logger.info(f"aitryon 任务已提交: {task_id}")
        return await _poll_result(task_id, api_key)

    except Exception as e:
        logger.error(f"aitryon API 异常: {e}")
        return {"success": False, "image_url": None, "message": f"aitryon API 异常: {e}"}


async def _poll_result(task_id: str, api_key: str, timeout: int = 180) -> Dict[str, Any]:
    """轮询 aitryon 异步任务结果"""
    start = time.time()
    while time.time() - start < timeout:
        await asyncio.sleep(3)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            result = resp.json()
            status = result.get("output", {}).get("task_status", "")

            if status == "SUCCEEDED":
                image_url = result.get("output", {}).get("image_url")
                if not image_url:
                    results = result.get("output", {}).get("results", [])
                    if results:
                        image_url = results[0].get("url")
                if image_url:
                    local_url = await _download_and_save(image_url)
                    return {"success": True, "image_url": local_url or image_url, "message": "AI 试穿生成成功"}
                logger.warning(f"成功但无 image_url: {json.dumps(result, ensure_ascii=False)[:500]}")
                return {"success": False, "image_url": None, "message": "生成完成但未获取到图片"}

            elif status == "FAILED":
                msg = result.get("output", {}).get("message", "AI 试穿生成失败")
                logger.error(f"任务失败: {msg}")
                return {"success": False, "image_url": None, "message": msg}

            else:
                logger.debug(f"轮询中... status={status}")

        except Exception as e:
            logger.error(f"轮询异常: {e}")
            continue

    return {"success": False, "image_url": None, "message": "AI 试穿生成超时"}


async def _download_and_save(url: str) -> Optional[str]:
    """下载远程图片并保存到本地 uploads/"""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            filename = f"tryon_{uuid.uuid4().hex[:12]}.jpg"
            filepath = os.path.join(settings.upload_dir, filename)
            os.makedirs(settings.upload_dir, exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(resp.content)
            return f"/uploads/{filename}"
    except Exception as e:
        logger.error(f"下载图片失败: {e}")
    return None


# ── 下载远程图片到 bytes ──

async def _download_image_bytes(url: str) -> Optional[bytes]:
    """下载远程图片，返回 bytes"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            return resp.content
    except Exception as e:
        logger.error(f"下载图片失败: {url} -> {e}")
    return None


# ============================================================
# 主入口：GloLaunch AI 虚拟试穿
# ============================================================

async def generate_tryon(product_image_url: str, product_desc: str = "") -> Dict[str, Any]:
    """虚拟试穿主入口 —— 适配 GloLaunch AI 场景。

    输入: 商品（衣物）图片 URL
    流程:
      1. 下载商品图 → resize
      2. 用 wan2.7 生成一张模特底图
      3. 两张图上传 DashScope OSS
      4. 调用 aitryon 合成试穿效果
      5. 下载结果到本地 uploads/
    返回: {success, image_url, message, engine}
    """
    settings = get_settings()
    if not settings.model_router_api_key:
        return {"success": False, "image_url": None, "message": "模型网关 API Key 未配置", "engine": "none"}

    # Step 1: 下载并预处理商品图
    logger.info(f"开始虚拟试穿，商品图: {product_image_url}")
    garment_bytes_raw = await _download_image_bytes(product_image_url)
    if not garment_bytes_raw:
        return {"success": False, "image_url": None, "message": "商品图下载失败", "engine": "none"}
    garment_bytes = _resize_image(garment_bytes_raw)

    # Step 2: 生成模特底图（同步调用 wan2.7）
    logger.info("生成模特底图...")
    model_prompt = (
        "a young European female fashion model, full body standing pose, "
        "natural studio lighting, white seamless background, "
        "e-commerce lookbook photo, neutral expression, hands at sides"
    )
    model_image_url = await asyncio.to_thread(generate_image, model_prompt)
    if not model_image_url:
        return {"success": False, "image_url": None, "message": "模特底图生成失败", "engine": "none"}

    model_bytes_raw = await _download_image_bytes(model_image_url)
    if not model_bytes_raw:
        return {"success": False, "image_url": None, "message": "模特底图下载失败", "engine": "none"}
    model_bytes = _resize_image(model_bytes_raw)

    # Step 3: 上传到 DashScope OSS
    logger.info("上传图片到 DashScope OSS...")
    person_url, garment_url = await asyncio.gather(
        _upload_to_dashscope(model_bytes, "person.jpg"),
        _upload_to_dashscope(garment_bytes, "garment.jpg"),
    )
    if not person_url:
        return {"success": False, "image_url": None, "message": "模特图上传 OSS 失败", "engine": "none"}
    if not garment_url:
        return {"success": False, "image_url": None, "message": "商品图上传 OSS 失败", "engine": "none"}

    # Step 4: 调用 aitryon
    logger.info("调用 aitryon 虚拟试穿...")
    result = await _call_aitryon_api(person_url, garment_url)

    return {
        "success": result.get("success", False),
        "image_url": result.get("image_url"),
        "message": result.get("message", ""),
        "engine": "aitryon" if result.get("success") else "none",
    }
