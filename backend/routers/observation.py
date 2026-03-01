# -*- coding: utf-8 -*-
"""
觀測單元 API 路由（升級版）
支援 Shorts + 長片模式，含成本預估
"""
import logging
from fastapi import APIRouter, HTTPException, status
from datetime import datetime

from models.schemas import (
    ObservationNotesInput,
    ObservationResponse,
    ErrorResponse,
    VideoMode,
    CostEstimate,
)
from services.observation_service import get_observation_service
from services.image_service import get_image_service

logger = logging.getLogger(__name__)

# 建立路由器
router = APIRouter(
    prefix="/api/observation",
    tags=["觀測單元"],
)


def _build_cover_prompt(topic: str, aspect_ratio: str) -> tuple[str, str]:
    """
    建立能勾起觀眾好奇心的封面 prompt。

    策略：
    - 直接以主題為主體，保持相關性
    - 極端特寫／非預期角度，只露出一部分，留下懸念
    - 戲劇性明暗對比（chiaroscuro），強烈光源製造張力
    - 讓觀眾感到「我想看更多」，但看不透全局
    """
    prompt = (
        f"{topic}, "
        f"extreme macro close-up of the most unexpected hidden detail, "
        f"dramatic chiaroscuro lighting, single strong spotlight, "
        f"deep rich shadows covering most of frame, "
        f"one sharp highlight revealing just enough to intrigue, "
        f"unusual angle viewer has never seen before, "
        f"tight cropped composition — subject partially out of frame, "
        f"vibrant saturated accent color against near-black background, "
        f"cinematic thumbnail that makes viewer desperately want to know more, "
        f"ultra sharp focus on the one key detail, shallow depth of field, "
        f"{aspect_ratio} format, "
        f"{'portrait vertical orientation' if aspect_ratio == '9:16' else 'landscape horizontal widescreen orientation'}, "
        f"no people, no hands, no fingers, no face, no text, no watermark, no logo"
    )
    negative = (
        "people, person, human, face, hands, fingers, body parts, "
        "boring generic composition, flat lighting, overexposed wash, "
        "blurry, low quality, stock photo look, "
        "wide shot that shows everything, obvious predictable angle, "
        "text, watermark, logo, signature"
    )
    return prompt, negative


@router.post(
    "/generate",
    response_model=ObservationResponse,
    responses={
        400: {"model": ErrorResponse, "description": "輸入錯誤"},
        500: {"model": ErrorResponse, "description": "伺服器錯誤"},
    },
    summary="生成觀測單元（升級版：支援長片）",
    description="根據觀測筆記生成短影音或長片觀測單元，自動生成封面和成本預估"
)
async def generate_observation_units(request: ObservationNotesInput):
    """
    生成觀測單元 + 封面 API（升級版）
    
    新增功能：
    - 支援 Shorts/中片/長片模式
    - 支援 9:16 和 16:9 比例
    - 智能關鍵幀數量計算
    - 運鏡建議生成
    - 成本預估
    """
    try:
        logger.info("=" * 60)
        logger.info("🎬 收到觀測單元生成請求")
        logger.info(f"📝 主題: {request.notes}")
        logger.info(f"🎞️  模式: {request.video_mode.value}")
        logger.info(f"📐 比例: {request.aspect_ratio.value}")
        logger.info(f"⏱️  時長: {request.duration_minutes or '自動'} 分鐘")
        logger.info(f"🔢 目標單元數: {request.target_units}")
        logger.info("=" * 60)
        
        # 取得服務實例
        obs_service = get_observation_service()
        img_service = get_image_service()
        
        # 生成觀測單元
        units = await obs_service.generate_units(
            notes=request.notes,
            target_units=request.target_units,
            style_preference=request.style_preference,
            video_mode=request.video_mode,
            aspect_ratio=request.aspect_ratio.value,
            duration_minutes=request.duration_minutes
        )
        
        logger.info(f"✅ 成功生成 {len(units)} 個觀測單元")
        
        # 計算成本預估
        model_used = "flux-schnell"  # 預設使用最便宜的模型
        image_count = len(units) + 1  # 單元 + 封面
        cost_estimate = CostEstimate(
            image_count=image_count,
            cost_per_image=img_service.get_model_cost(model_used),
            total_cost=round(image_count * img_service.get_model_cost(model_used), 4),
            model_used=model_used
        )
        
        logger.info(f"💰 成本預估: ${cost_estimate.total_cost} ({image_count} 張 × ${cost_estimate.cost_per_image})")
        
        # 生成封面圖（主題相關，懸念構圖，勾起好奇心）
        cover_url = None
        try:
            topic = request.notes.strip()
            cover_prompt, enhanced_negative = _build_cover_prompt(topic, request.aspect_ratio.value)

            logger.info(f"🎨 封面 Prompt: {cover_prompt[:120]}...")
            
            cover_url = await img_service.generate_image(
                prompt=cover_prompt,
                negative_prompt=enhanced_negative,
                aspect_ratio=request.aspect_ratio.value,
                model=model_used
            )
            
            logger.info(f"✅ 封面生成成功: {cover_url}")
            
        except Exception as e:
            logger.warning(f"⚠️ 封面生成失敗: {e}")
            cover_url = None
        
        # 構建回應
        response = ObservationResponse(
            success=True,
            units=units,
            video_mode=request.video_mode,
            aspect_ratio=request.aspect_ratio.value,
            cost_estimate=cost_estimate,
            metadata={
                "request": {
                    "notes": request.notes,
                    "notes_length": len(request.notes),
                    "target_units": request.target_units,
                    "style_preference": request.style_preference,
                    "video_mode": request.video_mode.value,
                    "aspect_ratio": request.aspect_ratio.value,
                    "duration_minutes": request.duration_minutes,
                },
                "result": {
                    "units_generated": len(units),
                    "cover_url": cover_url,
                    "keyframes_only": True,  # 標記這是關鍵幀模式
                    "post_production_required": True,  # 需要後製運鏡
                },
                "cover_url": cover_url,
                "cost": {
                    "image_count": cost_estimate.image_count,
                    "total_cost_usd": cost_estimate.total_cost,
                    "model_used": cost_estimate.model_used,
                },
                "production_notes": {
                    "workflow": "keyframe_to_motion",
                    "motion_effects_included": True,
                    "recommended_tools": ["CapCut", "Premiere Pro", "Final Cut Pro"],
                    "estimated_editing_time": f"{len(units) * 2}-{len(units) * 3} minutes"
                }
            },
            generated_at=datetime.now()
        )
        
        logger.info("=" * 60)
        logger.info("🎉 完整回應已建立")
        logger.info(f"📊 單元: {len(units)} 個")
        logger.info(f"💰 成本: ${cost_estimate.total_cost}")
        logger.info(f"🎬 運鏡: {len([u for u in units if u.motion_guidance])} 個單元有建議")
        logger.info("=" * 60)
        
        return response
        
    except ValueError as e:
        logger.error(f"❌ 輸入驗證錯誤: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": str(e),
                "error_type": "ValidationError"
            }
        )
        
    except Exception as e:
        logger.error(f"❌ 生成觀測單元時發生錯誤: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "內部伺服器錯誤，請稍後再試",
                "error_type": "InternalServerError",
                "debug_info": str(e) if logger.level == logging.DEBUG else None
            }
        )


@router.post(
    "/estimate-cost",
    summary="預估成本",
    description="根據影片模式和時長預估生成成本"
)
async def estimate_cost(request: ObservationNotesInput):
    """
    成本預估 API（不實際生成）
    
    用途：
    - 讓用戶在生成前了解成本
    - 幫助用戶選擇合適的模式
    """
    try:
        obs_service = get_observation_service()
        img_service = get_image_service()
        
        # 計算關鍵幀數量
        keyframe_count = obs_service._calculate_keyframe_count(
            request.video_mode,
            request.duration_minutes
        )
        
        # 計算成本（單元 + 封面）
        image_count = keyframe_count + 1
        model_used = "flux-schnell"
        
        cost_info = img_service.estimate_cost(image_count, model_used)
        
        return {
            "success": True,
            "video_mode": request.video_mode.value,
            "aspect_ratio": request.aspect_ratio.value,
            "duration_minutes": request.duration_minutes,
            "keyframe_count": keyframe_count,
            "cost_estimate": cost_info,
            "savings_vs_full_generation": {
                "full_generation_units": request.duration_minutes * 2 if request.duration_minutes else keyframe_count * 3,
                "keyframe_units": keyframe_count,
                "savings_percentage": round((1 - keyframe_count / (request.duration_minutes * 2 if request.duration_minutes else keyframe_count * 3)) * 100, 1) if request.duration_minutes else 66.7
            }
        }
        
    except Exception as e:
        logger.error(f"成本預估失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "error": str(e)}
        )


@router.get(
    "/modes",
    summary="獲取可用模式",
    description="返回所有支援的影片模式和比例"
)
async def get_available_modes():
    """
    獲取可用的影片模式和比例
    
    用途：
    - 前端動態生成選項
    - API 文檔參考
    """
    return {
        "video_modes": [
            {
                "value": "shorts",
                "label": "Shorts (≤60秒)",
                "duration_range": "9-60 秒",
                "keyframe_count": 3,
                "recommended_aspect_ratio": "9:16"
            },
            {
                "value": "medium",
                "label": "中片 (3-10分鐘)",
                "duration_range": "3-10 分鐘",
                "keyframe_count": "5-15",
                "recommended_aspect_ratio": "16:9"
            },
            {
                "value": "long",
                "label": "長片 (30-60分鐘)",
                "duration_range": "30-60 分鐘",
                "keyframe_count": "15-30",
                "recommended_aspect_ratio": "16:9"
            }
        ],
        "aspect_ratios": [
            {
                "value": "9:16",
                "label": "豎屏 (Shorts)",
                "description": "適合 TikTok, Instagram Reels, YouTube Shorts"
            },
            {
                "value": "16:9",
                "label": "橫屏 (標準)",
                "description": "適合 YouTube, 電視, 電影"
            },
            {
                "value": "1:1",
                "label": "方形",
                "description": "適合 Instagram 貼文"
            }
        ],
        "models": [
            {
                "value": "flux-schnell",
                "label": "FLUX Schnell (快速)",
                "price_per_image": 0.003,
                "quality": "中等",
                "speed": "快"
            },
            {
                "value": "flux-dev",
                "label": "FLUX Dev (平衡)",
                "price_per_image": 0.025,
                "quality": "高",
                "speed": "中等"
            },
            {
                "value": "flux-1.1-pro",
                "label": "FLUX 1.1 Pro (專業)",
                "price_per_image": 0.04,
                "quality": "最高",
                "speed": "較慢"
            }
        ]
    }


@router.get(
    "/health",
    summary="健康檢查",
    description="檢查觀測單元服務是否正常運作"
)
async def health_check():
    """觀測單元服務健康檢查"""
    try:
        service = get_observation_service()
        return {
            "status": "healthy",
            "service": "observation",
            "version": "2.0_upgraded",
            "features": {
                "shorts_support": True,
                "long_form_support": True,
                "aspect_ratios": ["9:16", "16:9", "1:1"],
                "motion_guidance": True,
                "cost_estimation": True
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"健康檢查失敗: {e}")
        return {
            "status": "unhealthy",
            "service": "observation",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }