# -*- coding: utf-8 -*-
"""
圖片生成服務 - 升級版
支援 9:16 Shorts 和 16:9 長片
使用 FLUX Schnell（可擴展到其他模型）
"""
import os
import logging
import asyncio
import replicate
from typing import Literal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ImageService:
    """圖片生成服務（升級版）"""
    
    # 模型定價（美元/張）
    MODEL_PRICING = {
        "flux-schnell": 0.003,
        "flux-dev": 0.025,
        "flux-1.1-pro": 0.04,
    }
    
    def __init__(self):
        """初始化服務"""
        self.api_token = os.getenv("REPLICATE_API_TOKEN")
        if not self.api_token:
            logger.warning("REPLICATE_API_TOKEN not found, image generation will fail")
        
        # 設定 API token
        if self.api_token:
            os.environ["REPLICATE_API_TOKEN"] = self.api_token
        
        # 預設使用 FLUX Schnell（成本最低）
        self.default_model = "flux-schnell"
    
    def get_model_cost(self, model: str = "flux-schnell") -> float:
        """
        獲取模型單價
        
        Args:
            model: 模型名稱
            
        Returns:
            單價（美元）
        """
        return self.MODEL_PRICING.get(model, 0.003)
    
    def _optimize_prompt_for_aspect_ratio(
        self,
        prompt: str,
        aspect_ratio: str
    ) -> str:
        """
        根據比例優化 prompt
        
        16:9 橫屏：
        - 強調寬景、橫向動態
        - 左右構圖
        
        9:16 豎屏：
        - 強調縱向、垂直動態
        - 上下構圖
        
        Args:
            prompt: 原始 prompt
            aspect_ratio: 畫面比例
            
        Returns:
            優化後的 prompt
        """
        if aspect_ratio == "16:9":
            # 橫屏優化
            enhancements = [
                "wide-angle composition",
                "landscape format",
                "horizontal dynamics",
                "cinematic framing",
            ]
            
            # 如果 prompt 中沒有提到橫向，加入提示
            if "landscape" not in prompt.lower() and "16:9" not in prompt:
                prompt = f"{prompt}, {', '.join(enhancements)}"
            
        elif aspect_ratio == "9:16":
            # 豎屏優化
            enhancements = [
                "vertical portrait orientation",
                "9:16 aspect ratio",
                "portrait format",
                "vertical composition",
            ]
            
            # 如果 prompt 中沒有提到豎向，加入提示
            if "portrait" not in prompt.lower() and "9:16" not in prompt:
                prompt = f"{prompt}, {', '.join(enhancements)}"
        
        return prompt
    
    def _enhance_quality_keywords(
        self,
        prompt: str,
        aspect_ratio: str
    ) -> str:
        """
        加入品質關鍵字
        
        Args:
            prompt: 原始 prompt
            aspect_ratio: 畫面比例
            
        Returns:
            增強後的 prompt
        """
        quality_keywords = [
            "professional photography",
            "high quality",
            "sharp focus",
            "cinematic lighting",
            "vibrant colors",
        ]
        
        # 檢查是否已有品質關鍵字
        has_quality = any(kw in prompt.lower() for kw in ["professional", "high quality", "cinematic"])
        
        if not has_quality:
            prompt = f"{prompt}, {', '.join(quality_keywords)}"
        
        return prompt
    
    def _build_negative_prompt(
        self,
        base_negative: str,
        aspect_ratio: str,
        avoid_hands: bool = True
    ) -> str:
        """
        構建強化的 negative prompt
        
        Args:
            base_negative: 基礎 negative prompt
            aspect_ratio: 畫面比例
            avoid_hands: 是否避免手部（預設 True）
            
        Returns:
            完整的 negative prompt
        """
        # 基礎品質問題
        quality_negatives = [
            "low quality",
            "blurry",
            "distorted",
            "bad anatomy",
            "deformed",
            "ugly",
            "poorly drawn",
            "mutation",
            "text",
            "watermark",
            "signature",
        ]
        
        # 避免人物（如果需要）
        if avoid_hands:
            human_negatives = [
                "people",
                "person",
                "human",
                "face",
                "hands",
                "fingers",
                "body",
                "man",
                "woman",
                "portrait",
                "selfie",
                "holding",
                "touching",
                "applying",
                "deformed hands",
                "extra fingers",
                "mutated hands",
                "poorly drawn hands",
            ]
            quality_negatives.extend(human_negatives)
        
        # 合併所有 negative
        all_negatives = set(base_negative.split(", ")) if base_negative else set()
        all_negatives.update(quality_negatives)
        
        return ", ".join(sorted(all_negatives))
    
    async def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "low quality, blurry, distorted, text, watermark",
        aspect_ratio: Literal["9:16", "16:9", "1:1"] = "9:16",
        model: str = "flux-schnell",
        output_quality: int = 95,
        avoid_hands: bool = True
    ) -> str:
        """
        生成圖片（升級版，支援多種比例）
        
        Args:
            prompt: 圖片提示詞（英文）
            negative_prompt: 負面提示詞
            aspect_ratio: 畫面比例（9:16/16:9/1:1）
            model: 使用的模型（flux-schnell/flux-dev/flux-1.1-pro）
            output_quality: 輸出品質（1-100）
            avoid_hands: 是否避免手部
            
        Returns:
            圖片 URL
        """
        try:
            if not self.api_token:
                raise ValueError("REPLICATE_API_TOKEN not configured")
            
            logger.info(f"🎨 生成圖片 ({model}, {aspect_ratio})")
            logger.info(f"📝 Prompt: {prompt[:80]}...")
            
            # 優化 prompt（根據比例）
            optimized_prompt = self._optimize_prompt_for_aspect_ratio(prompt, aspect_ratio)
            
            # 加入品質關鍵字
            enhanced_prompt = self._enhance_quality_keywords(optimized_prompt, aspect_ratio)
            
            # 構建完整 negative prompt
            full_negative = self._build_negative_prompt(
                negative_prompt, 
                aspect_ratio, 
                avoid_hands
            )
            
            logger.info(f"✨ 優化後 Prompt: {enhanced_prompt[:100]}...")
            logger.info(f"🚫 Negative: {full_negative[:100]}...")
            
            # 根據模型選擇生成參數
            if model == "flux-schnell":
                model_id = "black-forest-labs/flux-schnell"
                generation_params = {
                    "prompt": enhanced_prompt,
                    "go_fast": True,
                    "num_outputs": 1,
                    "aspect_ratio": aspect_ratio,
                    "output_format": "webp",
                    "output_quality": output_quality,
                    "num_inference_steps": 4,
                }
            
            elif model == "flux-dev":
                model_id = "black-forest-labs/flux-dev"
                generation_params = {
                    "prompt": enhanced_prompt,
                    "num_outputs": 1,
                    "aspect_ratio": aspect_ratio,
                    "output_format": "webp",
                    "output_quality": output_quality,
                    "num_inference_steps": 28,
                }
            
            elif model == "flux-1.1-pro":
                model_id = "black-forest-labs/flux-1.1-pro"
                generation_params = {
                    "prompt": enhanced_prompt,
                    "aspect_ratio": aspect_ratio,
                    "output_format": "webp",
                    "output_quality": output_quality,
                    "safety_tolerance": 2,
                }
            
            else:
                # 預設使用 Schnell
                model_id = "black-forest-labs/flux-schnell"
                generation_params = {
                    "prompt": enhanced_prompt,
                    "go_fast": True,
                    "num_outputs": 1,
                    "aspect_ratio": aspect_ratio,
                    "output_format": "webp",
                    "output_quality": output_quality,
                    "num_inference_steps": 4,
                }
            
            # 呼叫 Replicate（async，90秒逾時）
            logger.info(f"📡 呼叫 Replicate API（逾時: 90秒）...")
            try:
                output = await asyncio.wait_for(
                    replicate.async_run(model_id, input=generation_params),
                    timeout=90.0
                )
            except asyncio.TimeoutError:
                logger.error("❌ Replicate API 呼叫逾時（90秒）")
                raise ValueError("圖片生成 API 逾時（90秒），請稍後再試")

            # 處理輸出（list 或單一 FileOutput）
            if isinstance(output, list) and len(output) > 0:
                image_url = str(output[0])
            elif output:
                image_url = str(output)
            else:
                logger.error(f"❌ 未知的輸出格式: {type(output)}")
                raise ValueError("Image generation returned unexpected format")

            logger.info(f"✅ 圖片生成成功 ({aspect_ratio}): {image_url}")
            return image_url
                
        except Exception as e:
            logger.error(f"❌ 圖片生成失敗: {e}")
            raise
    
    async def generate_batch(
        self,
        prompts: list[str],
        aspect_ratio: str = "9:16",
        model: str = "flux-schnell"
    ) -> list[str]:
        """
        批次生成圖片（降低成本）
        
        Args:
            prompts: prompt 列表
            aspect_ratio: 畫面比例
            model: 使用的模型
            
        Returns:
            圖片 URL 列表
        """
        logger.info(f"📦 批次生成 {len(prompts)} 張圖片")
        
        urls = []
        for idx, prompt in enumerate(prompts):
            try:
                url = await self.generate_image(
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    model=model
                )
                urls.append(url)
                logger.info(f"✅ [{idx+1}/{len(prompts)}] 完成")
            except Exception as e:
                logger.error(f"❌ [{idx+1}/{len(prompts)}] 失敗: {e}")
                urls.append(None)
        
        success_count = len([u for u in urls if u])
        logger.info(f"🎉 批次完成：{success_count}/{len(prompts)} 成功")
        
        return urls
    
    def estimate_cost(
        self,
        image_count: int,
        model: str = "flux-schnell"
    ) -> dict:
        """
        預估成本
        
        Args:
            image_count: 圖片數量
            model: 使用的模型
            
        Returns:
            成本資訊
        """
        price_per_image = self.get_model_cost(model)
        total_cost = image_count * price_per_image
        
        return {
            "image_count": image_count,
            "model": model,
            "price_per_image": price_per_image,
            "total_cost": round(total_cost, 4),
            "currency": "USD"
        }


# 全局服務實例
image_service = ImageService()


def get_image_service() -> ImageService:
    """依賴注入用的工廠函數"""
    return image_service