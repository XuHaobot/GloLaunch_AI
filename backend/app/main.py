import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import chat, product, importer, tasks, publish, batch, system, skills, v2

settings = get_settings()

# 确保必要数据目录存在
os.makedirs(settings.data_dir, exist_ok=True)
os.makedirs(settings.upload_dir, exist_ok=True)

app = FastAPI(
    title="GloLaunch AI API",
    description="AI 全链路跨境智能上新引擎后端服务 (LangGraph 状态机驱动)",
    version="3.0.0"
)

# 配置 CORS 允许前端跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(chat.router)
app.include_router(product.router)
app.include_router(importer.router)
app.include_router(tasks.router)
app.include_router(publish.router)
app.include_router(batch.router)
app.include_router(system.router)
app.include_router(skills.router)
app.include_router(v2.router)

# 静态资源服务（上传目录）
if os.path.exists(settings.upload_dir):
    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

@app.get("/")
async def root():
    return {
        "app": "GloLaunch AI",
        "version": "3.0.0",
        "engine": "LangGraph StateGraph + Qwen3.8-Max / Qwen3.7-Plus",
        "status": "healthy"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
