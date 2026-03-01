# -*- coding: utf-8 -*-
"""
圖片生成 API 路由
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from services.image_service import ImageService, get_image_service

router = APIRouter(prefix="/api/image", tags=["image"])


class ImageGenerateRequest(BaseModel):
    """圖片生成請求"""
    prompt: str = Field(..., description="圖片提示詞（英文）")
    negative_prompt: str = Field(default="low quality, blurry, distorted", description="負面提示詞")
    aspect_ratio: str = Field(default="9:16", description="畫面比例")


class ImageGenerateResponse(BaseModel):
    """圖片生成回應"""
    success: bool
    image_url: Optional[str] = None
    error: Optional[str] = None


@router.post("/generate", response_model=ImageGenerateResponse)
async def generate_image(
    request: ImageGenerateRequest,
    service: ImageService = Depends(get_image_service)
):
    """
    生成圖片
    """
    try:
        image_url = await service.generate_image(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            aspect_ratio=request.aspect_ratio
        )
        
        return ImageGenerateResponse(
            success=True,
            image_url=image_url
        )
        
    except Exception as e:
        return ImageGenerateResponse(
            success=False,
            error=str(e)
        )