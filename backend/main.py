"""
Shorts Factory v2 - Backend API
FastAPI 主程式
"""
import logging

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 1. 先 import 所有東西
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

# 取得前端 URL
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

# 2. 建立 app
app = FastAPI(
    title="Shorts Factory v2 Backend",
    description="觀測單元生成 API",
    version="2.0.0"
)

# 3. 設定 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000",
                   "http://localhost:3001", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. 最後才 import 和註冊 routers
from routers import observation_router, image_router

app.include_router(observation_router)
app.include_router(image_router)

# 5. 健康檢查
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "services": {
            "api": True,
            "observation": True,
            "image": True
        }
    }

# 啟動事件
@app.on_event("startup")
async def startup_event():
    """應用啟動時執行"""
    logger.info("[BOOT] VERSION 33.9 - NOCTURIA_MEDICAL_THEME - [SCENE_INDEX_ROUTER_ACTIVE] - [NANO_BANANA_2_READY]")
    logger.info("🚀 Shorts Factory v2 Backend 啟動中...")
    _port = os.getenv("PORT", "8001")
    logger.info(f"📍 API 文檔: http://127.0.0.1:{_port}/docs")
    logger.info(f"🌐 前端位置: {frontend_url}")
    
    # 檢查環境變數
    required_vars = ["GEMINI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.warning(f"⚠️  缺少環境變數: {', '.join(missing_vars)}")
        logger.warning("⚠️  請設定 .env 檔案")
    else:
        logger.info("✅ 環境變數檢查通過")

# 關閉事件
@app.on_event("shutdown")
async def shutdown_event():
    """應用關閉時執行"""
    logger.info("👋 Shorts Factory v2 Backend 關閉中...")


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 8001))
    debug = os.getenv("DEBUG", "True").lower() == "true"
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )
