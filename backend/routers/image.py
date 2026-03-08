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
    # V34.0: scene_index 決定模型路由
    # 0 (封面) 或 1 (第一幕) → nano-banana-2 (Google Imagen 3)
    # >= 2 → flux-schnell (Replicate)
    scene_index: int = Field(
        default=2,
        ge=0,
        description="場景索引：0/1 → nano-banana-2；>=2 → flux-schnell",
    )


class ImageGenerateResponse(BaseModel):
    """圖片生成回應"""
    model_config = {"protected_namespaces": ()}
    success: bool
    image_url: Optional[str] = None
    model_used: Optional[str] = None
    error: Optional[str] = None


@router.post("/generate", response_model=ImageGenerateResponse)
async def generate_image(
    request: ImageGenerateRequest,
    service: ImageService = Depends(get_image_service)
):
    """
    生成圖片。
    scene_index <= 1 → nano-banana-2 (Google Imagen 3, 物理鎖定)
    scene_index >= 2 → flux-schnell (Replicate)
    """
    try:
        # V34.0: 依 scene_index 選擇模型（物理鎖定 Index 0/1 → nano-banana-2）
        model = service.select_model_for_scene(request.scene_index)

        image_url = await service.generate_image(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            aspect_ratio=request.aspect_ratio,
            model=model,
        )

        return ImageGenerateResponse(
            success=True,
            image_url=image_url,
            model_used=model,
        )

    except Exception as e:
        return ImageGenerateResponse(
            success=False,
            error=str(e)
        )
