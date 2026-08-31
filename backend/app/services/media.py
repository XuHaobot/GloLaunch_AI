"""多媒体生成服务：AI 生图（Wan2.7）、TTS 配音、ffmpeg 视频合成。

所有能力均带优雅降级：
- 生图失败/模型不可用 → 返回 None，由调用方使用预设素材兜底
- TTS 失败 → 返回 None，视频仅保留分镜脚本
- 未安装 ffmpeg → 跳过合成，返回分镜故事板模式
"""
import asyncio
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from typing import List, Optional

import httpx

from app.config import get_settings

def _gateway_root() -> str:
    """从 OpenAI 兼容 base_url 推导 DashScope 原生网关根地址（去掉 /compatible-mode/v1 后缀）"""
    root = get_settings().model_router_base_url.rstrip("/")
    for suffix in ("/compatible-mode/v1", "/compatible-mode", "/v1"):
        if root.endswith(suffix):
            return root[: -len(suffix)]
    return root

def generate_image(prompt: str, size: str = "1024*1024") -> Optional[str]:
    """调用 Wan2.7 生图（Token Plan 原生 multimodal-generation 接口），成功返回图片 URL，失败返回 None。
    注意：返回的 OSS 签名 URL 有效期约 24 小时。
    """
    settings = get_settings()
    if not settings.model_router_api_key or not settings.model_image:
        return None
    try:
        with httpx.Client(timeout=180) as client:
            resp = client.post(
                f"{_gateway_root()}/api/v1/services/aigc/multimodal-generation/generation",
                headers={
                    "Authorization": f"Bearer {settings.model_router_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.model_image,
                    "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
                    "parameters": {"size": size},
                },
            )
            resp.raise_for_status()
            choices = (resp.json().get("output") or {}).get("choices") or []
            for ch in choices:
                for part in (ch.get("message") or {}).get("content") or []:
                    if isinstance(part, dict) and part.get("image"):
                        return part["image"]
            return None
    except Exception:
        return None

def edit_image_async(prompt: str, image_url: str, size: str = "1024*1024",
                     poll_interval: float = 3.0, timeout_seconds: float = 240.0) -> Optional[str]:
    """图片编辑/图生图重绘（Token Plan multimodal-generation 同步接口）。
    支持公网 URL 和 Base64 Data URI，直接返回生成的图片 URL。失败返回 None。
    """
    settings = get_settings()
    if not settings.model_router_api_key or not image_url:
        return None
    
    # 若为本地文件路径（/uploads/ 或本地绝对路径），转换为 base64 data URI
    actual_image = image_url
    if not image_url.startswith(("http://", "https://", "data:")):
        from app.agent.nodes.product import _local_image_to_data_uri
        actual_image = _local_image_to_data_uri(image_url) or image_url

    try:
        with httpx.Client(timeout=180) as client:
            resp = client.post(
                f"{_gateway_root()}/api/v1/services/aigc/multimodal-generation/generation",
                headers={
                    "Authorization": f"Bearer {settings.model_router_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.model_image_edit,
                    "input": {
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"image": actual_image},
                                {"text": prompt}
                            ]
                        }]
                    },
                    "parameters": {"size": size},
                },
            )
            resp.raise_for_status()
            choices = (resp.json().get("output") or {}).get("choices") or []
            for ch in choices:
                for part in (ch.get("message") or {}).get("content") or []:
                    if isinstance(part, dict) and part.get("image"):
                        return part["image"]
            return None
    except Exception:
        return None

def _extract_task_image_url(task_data: dict) -> Optional[str]:
    """从异步任务响应中提取图片 URL（多版本结构兼容）"""
    output = task_data.get("output") or task_data
    results = output.get("results")
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict) and item.get("url"):
                return item["url"]
    if isinstance(output.get("image_url"), str):
        return output["image_url"]
    # 兜底：遍历查找 URL 字段
    stack = [task_data]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if isinstance(v, str) and v.startswith("http") and ("url" in k.lower() or "image" in k.lower()):
                    return v
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return None

def synthesize_speech(text: str) -> Optional[str]:
    """TTS 语音合成（Token Plan 原生 SpeechSynthesizer 接口）：文本 → 下载音频落盘，
    返回 /uploads/xxx.mp3 访问路径，失败返回 None"""
    settings = get_settings()
    if not settings.model_router_api_key or not text.strip():
        return None
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{_gateway_root()}/api/v1/services/audio/tts/SpeechSynthesizer",
                headers={
                    "Authorization": f"Bearer {settings.model_router_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.model_tts,
                    "input": {
                        "text": text,
                        "voice": settings.tts_voice,
                        "format": "mp3",
                        "sample_rate": 24000,
                    },
                },
            )
            resp.raise_for_status()
            audio_url = ((resp.json().get("output") or {}).get("audio") or {}).get("url")
            if not audio_url:
                return None
            audio_resp = client.get(audio_url, timeout=60, follow_redirects=True)
            audio_resp.raise_for_status()
            os.makedirs(settings.upload_dir, exist_ok=True)
            filename = f"tts_{uuid.uuid4().hex[:12]}.mp3"
            path = os.path.join(settings.upload_dir, filename)
            with open(path, "wb") as f:
                f.write(audio_resp.content)
            return f"/uploads/{filename}"
    except Exception:
        return None

def _download_to_temp(url: str, tmp_dir: str, index: int) -> Optional[str]:
    """将远程图片下载到临时目录（本地 /uploads/ 路径直接复制引用）"""
    if url.startswith("/uploads/"):
        settings = get_settings()
        local = os.path.join(settings.upload_dir, url.split("/uploads/", 1)[1])
        # 必须绝对路径：ffmpeg concat 清单以清单文件所在目录解析相对路径
        return os.path.abspath(local) if os.path.exists(local) else None
    try:
        resp = httpx.get(url, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        ext = ".jpg" if "jpeg" in resp.headers.get("content-type", "") or "jpg" in url else ".png"
        path = os.path.join(tmp_dir, f"shot_{index}{ext}")
        with open(path, "wb") as f:
            f.write(resp.content)
        return path
    except Exception:
        return None

def _ffmpeg_exe() -> Optional[str]:
    """解析 ffmpeg 可执行文件：系统 PATH 优先，未安装时回退 imageio-ffmpeg 内置静态版（免手动装 PATH）"""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

async def compose_slideshow_video(image_urls: List[str], audio_path: Optional[str],
                                  seconds_per_shot: float = 4.0) -> Optional[str]:
    """图片轮播 + 配音音轨 → mp4。优先系统 PATH 的 ffmpeg，其次 imageio-ffmpeg 内置静态版；均不可用返回 None"""
    ffmpeg_bin = _ffmpeg_exe()
    if not ffmpeg_bin or not image_urls:
        return None
    settings = get_settings()

    def _compose() -> Optional[str]:
        tmp_dir = tempfile.mkdtemp(prefix="glo_video_")
        try:
            local_images: List[str] = []
            for i, url in enumerate(image_urls):
                local = _download_to_temp(url, tmp_dir, i)
                if local:
                    local_images.append(local)
            if not local_images:
                return None

            # concat demuxer：每张图按固定时长轮播
            list_file = os.path.join(tmp_dir, "concat.txt")
            with open(list_file, "w", encoding="utf-8") as f:
                for img in local_images:
                    f.write(f"file '{img}'\nduration {seconds_per_shot}\n")
                f.write(f"file '{local_images[-1]}'\n")  # 尾帧补全时长

            os.makedirs(settings.upload_dir, exist_ok=True)
            out_name = f"video_{uuid.uuid4().hex[:12]}.mp4"
            out_path = os.path.join(settings.upload_dir, out_name)

            cmd = [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", list_file]
            local_audio = None
            if audio_path:
                local_audio = os.path.join(settings.upload_dir, audio_path.split("/uploads/", 1)[1]) \
                    if audio_path.startswith("/uploads/") else audio_path
                if os.path.exists(local_audio):
                    local_audio = os.path.abspath(local_audio)
                    cmd += ["-i", local_audio]
            cmd += [
                "-vf", "scale=720:720:force_original_aspect_ratio=decrease,"
                       "pad=720:720:(ow-iw)/2:(oh-ih)/2,fps=24,format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
            ]
            if local_audio and os.path.exists(local_audio):
                cmd += ["-c:a", "aac", "-shortest"]
            cmd.append(out_path)

            proc = subprocess.run(cmd, capture_output=True, timeout=180)
            return f"/uploads/{out_name}" if proc.returncode == 0 and os.path.exists(out_path) else None
        except Exception:
            return None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return await asyncio.to_thread(_compose)
