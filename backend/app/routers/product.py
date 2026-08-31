import os
import uuid
from typing import List, Optional
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.agent.nodes.studio import run_virtual_tryon, run_scene_generation
from app.agent.nodes.video import run_video_storyboard
from app.config import get_settings
from app.services.vector_store import KnowledgeStore

router = APIRouter(prefix="/api/products", tags=["商品与知识库"])

ALLOWED_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB

class KnowledgeQuery(BaseModel):
    query: str
    top_k: Optional[int] = 3

class TryOnRequest(BaseModel):
    image_url: str
    product_desc: str = "服装商品"

class SceneGenRequest(BaseModel):
    category: str = "跨境商品"
    category_family: str = "general"
    style_tags: List[str] = []
    design_features: List[str] = []
    product_image_url: str = ""

class VideoGenRequest(BaseModel):
    title: str
    bullet_points: List[str] = []
    category: str = "商品"
    platform: str = "TikTok"
    market: str = "US"

@router.post("/knowledge/search")
async def search_knowledge(req: KnowledgeQuery):
    """搜索跨境电商规则与品类知识"""
    kb = KnowledgeStore.get_instance()
    results = kb.search(req.query, top_k=req.top_k)
    return {"status": "success", "results": results}

@router.post("/upload")
async def upload_product_image(file: UploadFile = File(...)):
    """本地商品图上传，返回可通过 /uploads/ 访问的图片路径"""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/webp 格式图片")

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="图片大小不能超过 10MB")

    settings = get_settings()
    os.makedirs(settings.upload_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(settings.upload_dir, filename), "wb") as f:
        f.write(content)

    return {"status": "success", "url": f"/uploads/{filename}", "filename": filename}

@router.post("/studio/tryon")
async def generate_tryon(req: TryOnRequest):
    """按需增值服务：虚拟试穿（服装类）。不在主流水线内，用户手动触发，三级降级保障必返回结果"""
    if not req.image_url.strip():
        raise HTTPException(status_code=400, detail="缺少商品图片地址")
    result = await run_virtual_tryon(req.image_url.strip(), req.product_desc)
    return {"status": "success", "virtual_tryon": result}

@router.post("/studio/scenes")
async def generate_scenes(req: SceneGenRequest):
    """按需增值服务：AI 场景图补充（搬运商品缺海外生活方式素材时手动触发，不在主流水线内）"""
    assets = await run_scene_generation(
        category=req.category, category_family=req.category_family,
        style_tags=req.style_tags, design_features=req.design_features,
        product_image_url=req.product_image_url,
    )
    return {"status": "success", "studio_assets": assets}

@router.post("/studio/video")
async def generate_video(req: VideoGenRequest):
    """按需增值服务：带货视频分镜脚本生成（占位保留，按需触发，不在主流水线内）"""
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="缺少商品标题")
    result = await run_video_storyboard(
        title=req.title.strip(),
        bullet_points=req.bullet_points,
        category=req.category,
        platform=req.platform,
        market=req.market,
    )
    return {"status": "success", "video_package": result}

@router.get("/demo-presets")
async def get_demo_presets():
    """获取预设演示商品案例"""
    return {
        "presets": [
            {
                "id": "french_dress",
                "name": "法式复古方领碎花连衣裙",
                "category": "女装连衣裙",
                "default_platform": "Amazon",
                "default_market": "US",
                "image_url": "https://img.alicdn.com/imgextra/i1/6000000007892/O1CN01a2ZpQM1scXS5sBsAa_!!6000000007892-0-tps-400-400.jpg",
                "prompt": "帮我把这款夏季法式复古碎花连衣裙做全链路上新，目标市场为 Amazon 美区。"
            },
            {
                "id": "linen_shirt",
                "name": "极简亚麻透气宽松休闲衬衫",
                "category": "男士衬衫",
                "default_platform": "Shopee",
                "default_market": "Southeast Asia",
                "image_url": "https://img.alicdn.com/imgextra/i2/6000000005645/O1CN01JHgOqE1c5MKHI3RlN_!!6000000005645-0-tps-800-800.jpg",
                "prompt": "为这款极简透气亚麻休闲长袖衬衫生成 Shopee 东南亚站点的选品分析与双语 Listing。"
            }
        ]
    }
