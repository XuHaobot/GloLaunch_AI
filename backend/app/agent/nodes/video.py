import json
import time
from typing import Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import AgentState
from app.services.llm import get_fast_llm
from app.services.media import synthesize_speech, compose_slideshow_video

PROMPT_VIDEO_STORYBOARD = """你是一名跨境电商短视频导演与带货脚本策划。请为该商品策划一支 15 秒以内的商品展示带货视频分镜脚本。
要求：分镜画面必须能用已生成的场景图素材呈现；配音文案使用目标市场语言，口播风格有钩子、有卖点、有行动号召。

请严格输出合法的 JSON 对象，不要包含任何 markdown 代码块标记，不要包含多余文字。
JSON 字段规范：
{
  "title_hook": "视频标题钩子（含热门标签建议）",
  "bgm_style": "背景音乐风格建议",
  "shots": [
    {"scene": "画面描述（需匹配场景素材）", "duration": 秒数, "voiceover": "该镜头配音文案", "camera": "镜头运动建议"}
  ]
}
分镜数量 3-4 个，总时长不超过 15 秒。
"""

FALLBACK_STORYBOARD = {
    "title_hook": "Product Showcase Template 🔥 #MustHave",
    "bgm_style": "Upbeat Pop, 100-110 BPM",
    "shots": [
        {"scene": "白底主图特写开场", "duration": 3, "voiceover": "Check out this amazing product — perfect for your daily needs.", "camera": "Slow push-in"},
        {"scene": "生活方式场景一", "duration": 4, "voiceover": "Premium quality, designed with attention to every detail.", "camera": "Pan left to right"},
        {"scene": "生活方式场景二", "duration": 4, "voiceover": "Versatile and practical — a great addition to your collection.", "camera": "Zoom out"},
        {"scene": "场景三 + 行动号召", "duration": 4, "voiceover": "Link in bio — get yours today!", "camera": "Static + text overlay"},
    ],
    "_fallback": True,
    "_note": "视频分镜生成未完成，以上为通用模板，建议根据实际商品定制内容",
}

async def video_node(state: AgentState) -> Dict[str, Any]:
    """商品展示视频生产节点：LLM 分镜脚本 → TTS 配音 → ffmpeg 图片轮播合成（无 ffmpeg 时输出故事板模式）"""
    attrs = state.get("product_attributes", {})
    studio = state.get("studio_assets", {}) or {}
    listing = state.get("listing_content", {}) or {}
    market = state.get("target_market", "US")
    platform = state.get("target_platform", "TikTok")
    category = attrs.get("category", state.get("product_category", "跨境商品"))

    # 1. LLM 生成分镜脚本（失败降级通用脚本）
    storyboard = None
    try:
        llm = get_fast_llm(temperature=0.5)
        user_prompt = (
            f"【商品】{category}\n【核心卖点】{', '.join(attrs.get('style_tags', []) + attrs.get('design_features', []))[:200]}\n"
            f"【Listing 标题】{listing.get('title', '')[:120]}\n【目标市场】{market}（配音用该市场语言）\n【投放平台】{platform}"
        )
        resp = await llm.ainvoke([
            SystemMessage(content=PROMPT_VIDEO_STORYBOARD),
            HumanMessage(content=user_prompt),
        ])
        content = resp.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        storyboard = json.loads(content)
        if not isinstance(storyboard.get("shots"), list) or not storyboard["shots"]:
            raise ValueError("分镜为空")
    except Exception:
        storyboard = FALLBACK_STORYBOARD

    shots = storyboard.get("shots", [])
    narration_script = " ".join(s.get("voiceover", "") for s in shots if s.get("voiceover"))

    # 2. TTS 自动配音（失败降级为无声/故事板）
    audio_path = await _run_in_thread(synthesize_speech, narration_script) if narration_script else None

    # 3. 素材选帧：白底主图 + 场景图（与分镜数对齐，最多 4 帧）
    frames = []
    if studio.get("white_background_main"):
        frames.append(studio["white_background_main"])
    frames += [s.get("image_url") for s in studio.get("lifestyle_scenes", []) if s.get("image_url")]
    frames = [f for f in frames if f][: max(len(shots), 3)]

    # 4. ffmpeg 合成（未安装时返回 None，自动故事板模式）
    video_url = None
    if frames:
        video_url = await compose_slideshow_video(frames, audio_path)

    mode = "rendered" if video_url else ("narrated_storyboard" if audio_path else "storyboard_only")
    total_duration = sum(s.get("duration", 4) for s in shots)

    result = {
        "mode": mode,
        "platform": platform,
        "title_hook": storyboard.get("title_hook", ""),
        "bgm_style": storyboard.get("bgm_style", ""),
        "storyboard": shots,
        "narration_script": narration_script,
        "audio_url": audio_path,
        "video_url": video_url,
        "duration_seconds": total_duration,
        "engine": "ffmpeg_slideshow" if video_url else "storyboard_engine",
        "fallback_note": None if video_url else ("未检测到 ffmpeg，已输出分镜故事板与配音文案，安装 ffmpeg 后可自动合成成片"
                                                  if audio_path else "未检测到 ffmpeg 或 TTS 服务，已输出分镜故事板脚本"),
    }

    trace_item = {
        "node": "video_production",
        "status": "completed",
        "summary": (f"带货视频生产完成：{len(shots)} 个分镜 / 约 {total_duration}s"
                    + (f"，成片已合成" if video_url else ("，配音已合成" if audio_path else "，故事板模式"))),
        "timestamp": time.time(),
        "detail": {"mode": mode, "shots": len(shots)},
    }

    current_trace = state.get("trace", []) or []

    return {
        "video_package": result,
        "current_node": "video_production",
        "trace": current_trace + [trace_item],
    }

async def _run_in_thread(func, *args):
    """将同步阻塞调用放入线程池执行"""
    import asyncio
    try:
        return await asyncio.to_thread(func, *args)
    except Exception:
        return None


async def run_video_storyboard(
    title: str,
    bullet_points: list,
    category: str,
    platform: str = "TikTok",
    market: str = "US",
) -> Dict[str, Any]:
    """独立调用：生成带货视频分镜脚本（不含 TTS / ffmpeg 合成）。

    供前端「按需生成」按钮调用，不依赖主流水线状态。
    """
    llm = get_fast_llm(temperature=0.5)
    bp_text = "\n".join(f"- {bp}" for bp in bullet_points[:5]) if bullet_points else "无"

    try:
        messages = [
            SystemMessage(content=PROMPT_VIDEO_STORYBOARD),
            HumanMessage(content=(
                f"商品：{title}\n"
                f"品类：{category}\n"
                f"目标平台：{platform} ({market} 站点)\n"
                f"卖点：\n{bp_text}"
            )),
        ]
        response = await llm.ainvoke(messages)
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        storyboard = json.loads(content)
    except Exception:
        storyboard = dict(FALLBACK_STORYBOARD)

    shots = storyboard.get("shots", [])
    duration = sum(s.get("duration", 3) for s in shots)

    return {
        "mode": "storyboard_only",
        "platform": platform,
        "title_hook": storyboard.get("title_hook", ""),
        "bgm_style": storyboard.get("bgm_style", ""),
        "storyboard": shots,
        "narration_script": " ".join(s.get("voiceover", "") for s in shots),
        "audio_url": None,
        "video_url": None,
        "duration_seconds": duration,
        "engine": "storyboard_engine",
        "fallback_note": storyboard.get("_note") if storyboard.get("_fallback") else None,
    }
