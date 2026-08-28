"""
技能注册中心：内置技能（对应 9 节点 + 试穿）+ 用户自定义技能。
- 自定义技能 = 用户自定义提示词模板 + 执行上下文，由 LLM 真实执行，
  模拟 Agent 平台的插件扩展点（如"西班牙语文案润色""尺码表生成"）。
- 存储：data/custom_skills.json（轻量 JSON，避免引入新依赖）。
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.services.llm import get_fast_llm

router = APIRouter(prefix="/api/skills", tags=["skills"])

# ---------- 内置技能（与工作流 hub 技能页一致） ----------
BUILTIN_SKILLS = [
    {"id": "extract_attributes", "name": "商品智能解析", "icon": "Search", "tag": "core",
     "desc": "多模态识别商品主图，自动抽取类目、类目关键词、核心属性、卖点与尺码表。"},
    {"id": "analyze_market", "name": "出海市场洞察", "icon": "DataAnalysis", "tag": "core",
     "desc": "旗舰模型 + 知识库检索，输出目标市场机会、竞争格局与差异化建议。"},
    {"id": "trend_benchmark", "name": "爆款对标研究", "icon": "TrendCharts", "tag": "core",
     "desc": "RAG 召回同类目爆款语料，提炼卖点框架与痛点场景，输出改写策略。"},
    {"id": "generate_listing", "name": "爆款化 Listing", "icon": "EditPen", "tag": "core",
     "desc": "标题/五点/描述/后台词全套英文 Listing，自动植入类目关键词。"},
    {"id": "studio_generation", "name": "AI 商品摄影", "icon": "Camera", "tag": "core",
     "desc": "优先搬运原素材，素材不足时调用文生图补充电商场景图。"},
    {"id": "video_production", "name": "带货视频生产", "icon": "VideoCamera", "tag": "optional",
     "desc": "分镜故事板 + TTS 配音，本地 ffmpeg 自动合成 15-30 秒成片。可在技能页关闭。"},
    {"id": "image_localization", "name": "图片文字本地化", "icon": "MapLocation", "tag": "optional",
     "desc": "检测图片中文并翻译为目标语言，优先阿里图翻官方接口。可在技能页关闭。"},
    {"id": "adapt_platform", "name": "平台合规质检", "icon": "Stamp", "tag": "core",
     "desc": "按目标平台类目规则校验 Listing 合规性，输出合规报告。"},
    {"id": "respond", "name": "成果汇总打包", "icon": "Box", "tag": "core",
     "desc": "LangGraph Core 聚合全链路产物，一键打包交付。"},
    {"id": "tryon", "name": "虚拟试穿生成", "icon": "User", "tag": "ondemand",
     "desc": "上传服装平铺图 + 模特图，生成真人上身效果图。按需触发。"},
]

# ---------- 自定义技能存储 ----------
_SKILLS_FILE = Path(__file__).resolve().parents[2] / "data" / "custom_skills.json"


def _load_custom() -> List[dict]:
    if not _SKILLS_FILE.exists():
        return []
    try:
        return json.loads(_SKILLS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_custom(skills: List[dict]):
    _SKILLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SKILLS_FILE.write_text(json.dumps(skills, ensure_ascii=False, indent=2), encoding="utf-8")


class SkillCreate(BaseModel):
    name: str
    description: str
    prompt_template: str
    icon: str = "MagicStick"


class SkillRunRequest(BaseModel):
    context: str = ""  # 可选：商品/任务背景描述，注入到提示词 {context} 占位符


@router.get("")
def list_skills():
    return {"builtin": BUILTIN_SKILLS, "custom": _load_custom()}


@router.post("")
def create_skill(body: SkillCreate):
    skills = _load_custom()
    skill = {
        "id": f"custom_{uuid.uuid4().hex[:8]}",
        "name": body.name.strip(),
        "description": body.description.strip(),
        "prompt_template": body.prompt_template,
        "icon": body.icon,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    skills.append(skill)
    _save_custom(skills)
    return skill


@router.delete("/{skill_id}")
def delete_skill(skill_id: str):
    skills = _load_custom()
    rest = [s for s in skills if s["id"] != skill_id]
    if len(rest) == len(skills):
        raise HTTPException(status_code=404, detail="技能不存在")
    _save_custom(rest)
    return {"ok": True}


@router.post("/{skill_id}/run")
def run_skill(skill_id: str, body: SkillRunRequest):
    """真实执行自定义技能：提示词模板 + 上下文 → LLM 输出"""
    skill = next((s for s in _load_custom() if s["id"] == skill_id), None)
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    prompt = skill["prompt_template"]
    if "{context}" in prompt:
        prompt = prompt.replace("{context}", body.context or "（未提供）")
    elif body.context:
        prompt = f"{prompt}\n\n【当前商品/任务背景】\n{body.context}"
    try:
        llm = get_fast_llm(temperature=0.5)
        resp = llm.invoke([
            SystemMessage(content=f"你是 GloLaunch AI 平台上的自定义技能「{skill['name']}」。严格按用户给定的指令模板执行，输出可直接使用的结果。"),
            HumanMessage(content=prompt),
        ])
        return {"ok": True, "result": resp.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"技能执行失败：{str(e)[:200]}")
