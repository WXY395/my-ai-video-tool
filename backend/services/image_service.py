# -*- coding: utf-8 -*-
"""
圖片生成服務 - 升級版
支援 9:16 Shorts 和 16:9 長片
使用 FLUX Schnell（可擴展到其他模型）
"""
import os
import re
import logging
import asyncio
import random
import replicate
from datetime import datetime
from typing import Literal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ImageService:
    """圖片生成服務（升級版）"""
    
    # 模型定價（美元/張）
    MODEL_PRICING = {
        "flux-schnell":  0.003,
        "flux-dev":      0.025,
        "flux-1.1-pro":  0.04,
        "nano-banana-2": 0.025,   # V33.9: maps to flux-dev billing tier
    }

    # V33.9 — Nano Banana 2 premium model identifier (Scene_Index <= 1)
    NANO_BANANA_2 = "nano-banana-2"

    # V33.9 Nocturia Medical Theme — Global Color System
    MIDNIGHT_BLUE  = "#0B1F3A"   # 夜間、睡眠主色
    CLINICAL_TEAL  = "#1A9FAA"   # 腎臟、泌尿系統
    BIO_AMBER      = "#F4A122"   # 逼尿肌應力警示
    SOFT_LAVENDER  = "#8B7FC7"   # AVP 神經荷爾蒙路徑
    ARCHIVAL_CREAM = "#F5F0E8"   # 存檔掃描底紙色

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
        logger.info("[V33.9_MEDICAL_INIT] - Nocturia theme engine active.")

    # V33.9 Scene-Index routing table
    # Scene_Index 0 (Cover) and 1 (Unit_001) → Nano Banana 2 (flux-dev tier, medical labels)
    # Scene_Index >= 2                        → flux-schnell (cost-efficient)
    _SCENE_MODEL_MAP: dict[str, str] = {"premium": "nano-banana-2", "standard": "flux-schnell"}

    def select_model_for_scene(self, scene_index: int) -> str:
        """V33.9 dispatcher: Scene_Index <= 1 → Nano Banana 2, others → flux-schnell."""
        selected = self._SCENE_MODEL_MAP["premium"] if scene_index <= 1 else self._SCENE_MODEL_MAP["standard"]
        logger.info(f"[V33.9_ROUTER] scene_index={scene_index} → model={selected}")
        return selected

    def select_model_for_unit(self, tier: int | None = None, is_cover: bool = False) -> str:
        """V33.0 dispatcher (legacy): route tier:1 or cover images to premium model."""
        if is_cover or tier == 1:
            selected = "flux-dev"
        else:
            selected = "flux-schnell"
        logger.info(f"[V33_ROUTER_LEGACY] tier={tier} is_cover={is_cover} → model={selected}")
        return selected

    def _inject_medical_labels(self, scene_index: int) -> str:
        """
        V33.9 Medical Label Injector — returns archival scan tag + medical badge string
        based on scene position. Scene_Index <= 1 receives premium Nocturia medical labels.
        """
        if scene_index == 0:
            return (
                f"[MEDICAL LABEL: Nocturnal Polyuria · AVP Deficiency · Sleep Disruption], "
                f"archival scan texture, film grain overlay, aged medical chart paper background, "
                f"deep midnight blue {self.MIDNIGHT_BLUE} and clinical teal {self.CLINICAL_TEAL} palette"
            )
        elif scene_index == 1:
            return (
                f"[MEDICAL LABEL: Nocturia · Night-time Voids · Detrusor Overactivity], "
                f"archival scan texture, subtle paper grain, clinical chart aesthetic, "
                f"bio-amber {self.BIO_AMBER} stress indicators, soft lavender {self.SOFT_LAVENDER} hormone pathway"
            )
        else:
            return f"clinical documentation style, medical illustration aesthetic"

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
            "archival scan quality",    # V32.0: replaces "professional photography" (portrait cue)
            "high quality",
            "sharp focus",
            "bright even lighting",     # replaces "cinematic lighting" (avoids dark/moody bias)
            "vivid saturated colors",
        ]

        # 檢查是否已有品質關鍵字
        has_quality = any(kw in prompt.lower() for kw in ["professional", "high quality", "cinematic"])

        if not has_quality:
            prompt = f"{prompt}, {', '.join(quality_keywords)}"

        return prompt

    def _add_topic_guard_terms(self, prompt: str) -> str:
        """
        Append FLUX-compatible subject-clarity avoidance terms to the positive prompt.

        FLUX ignores negative_prompt (API silently discards it). To prevent the model
        from generating abstract bokeh / random organic macro textures / unrelated foliage,
        we must state avoidance in the positive prompt.

        Only appended once — skips if terms already present (e.g. cover prompts that
        already include _AVOID via _build_cover_prompt_v2).
        """
        if "avoid abstract bokeh" in prompt.lower() or "avoid random organic" in prompt.lower():
            return prompt  # Already guarded (e.g. from _build_cover_prompt_v2)
        return (
            f"{prompt}, "
            f"sharp identifiable subject, "
            f"avoid abstract bokeh, avoid random organic shapes, "
            f"avoid unrelated flowers or foliage"
        )
    
    def _cull_biological_terms(self, prompt: str) -> str:
        """
        V33.9 Medical Cull — final term purge + medical theme injection.
        Called as the LAST step before prompt is sent to Replicate.

        Replaces portrait/industrial artifacts with medical illustration equivalents.
        \b guards preserve "surface", "interface", "artifact", etc.
        "portrait" bare word is NOT replaced — required for 9:16 FLUX orientation.
        """
        # ── Exact-phrase map (most specific first) ────────────────────────────
        _PHRASE_MAP: list[tuple[str, str]] = [
            ("professional photography",                    "archival scan documentation"),
            ("documentary photography",                     "archival scan documentation"),
            ("portrait photography",                        "archival scan documentation"),
            ("cinematic thumbnail quality",                 "archival scan quality"),
            ("bright studio rim light",                     "diffused clinical examination light"),
            ("bright rim/key light",                        "diffused clinical examination light"),
            ("cold industrial inspection light",            "diffused clinical examination light"),
            ("cold industrial key light",                   "diffused archival light"),
            ("rim light",                                   "diffused archival light"),
            ("silhouette outline",                          ""),
            ("readable silhouette",                         "anatomical diagram outline"),
            ("high-key well-lit surface",                   "clean clinical background"),
            ("sharp mechanical texture",                    "clean clinical background"),
            ("detailed close-up photograph",                "medical illustration close-up"),
            ("extreme macro close-up",                      "anatomical detail illustration"),
            ("macro engineering close-up capture",          "medical illustration close-up"),
            ("intricate metallic components",               "anatomical cross-section diagram"),
            ("raw metallic components clearly rendered",    "anatomical diagram clearly rendered"),
            ("raw metallic components",                     "anatomical diagram components"),
            ("raw mechanical components composition",       "anatomical diagram composition"),
            ("mechanical component",                        "anatomical marker"),
            ("precision-machined steel",                    "clinical teal medical palette"),
            ("brushed aluminum surface grain",              "film grain overlay on archival paper"),
            ("rusted iron oxide patina",                    "aged medical chart texture"),
            ("oxidized copper texture, industrial macro focus", "clinical teal highlight, medical macro focus"),
            ("hyper-detailed mechanical surface",           "painterly medical illustration surface"),
            ("technical blueprint aesthetic",               "archival scan aesthetic"),
            ("vintage technical blueprint aesthetic",       "archival scan aesthetic"),
        ]
        for _old, _new in _PHRASE_MAP:
            prompt = prompt.replace(_old, _new)

        # ── Word-boundary regex for isolated biological / portrait nouns ──────
        # ⚠️ \b guards prevent substring corruption:
        #   "face"      → NOT "surface" / "interface" / "artifact"
        #   "skin"      → NOT "skinny" / "desktop skin"
        #   "silhouette"→ catches any remaining instances after phrase map
        prompt = re.sub(r'\bfaces?\b',    "anatomical cross-section",   prompt, flags=re.IGNORECASE)
        prompt = re.sub(r'\bskin\b',      "mucosal tissue",             prompt, flags=re.IGNORECASE)
        prompt = re.sub(r'\bsilhouette\b',"anatomical diagram outline", prompt, flags=re.IGNORECASE)

        # ── Clean up orphaned commas from empty replacements ──────────────────
        prompt = re.sub(r',\s*,+', ',', prompt)
        prompt = re.sub(r',\s*$',  '',  prompt).strip()

        # ── V33.9 物理最終防線：強制轉碼為醫學存檔風格 ───────────────────────
        # \b guards preserve "surface", "interface", "artifact" etc.
        prompt = re.sub(r'\b(face|skin|human|portrait|silhouette|rim light)\b', "anatomical_marker", prompt, flags=re.IGNORECASE)
        # 植入 V33.9 醫學主題品牌識別度（Nocturia 配色）
        prompt += (
            f", deep midnight blue {self.MIDNIGHT_BLUE} and clinical teal {self.CLINICAL_TEAL} "
            f"medical color palette, archival scan aesthetic, painterly medical illustration"
        )

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
        # NOTE: "portrait" 已移除 — 9:16 豎向封面本身就是 portrait orientation，
        #       放進 negative 會讓模型自打架產生暗色/抽象圖
        if avoid_hands:
            human_negatives = [
                "people",
                "person",
                "human",
                "face",
                "hands",
                "body",
                "man",
                "woman",
                "selfie",
                "holding",
                "touching",
                "applying",
                "deformed hands",
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
        avoid_hands: bool = True,
        seed: int | None = None,
        guidance: float | None = None,
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

            # V33.9: Nano Banana 2 → internally routes to flux-dev on Replicate
            if model == self.NANO_BANANA_2:
                logger.info(f"[V33.9_ROUTER] {self.NANO_BANANA_2} → flux-dev (Replicate dispatch)")
                model = "flux-dev"

            logger.info(f"🎨 生成圖片 ({model}, {aspect_ratio})")
            logger.info(f"📝 Prompt (input): {prompt}")
            
            # 優化 prompt（根據比例）
            optimized_prompt = self._optimize_prompt_for_aspect_ratio(prompt, aspect_ratio)

            # 加入品質關鍵字
            enhanced_prompt = self._enhance_quality_keywords(optimized_prompt, aspect_ratio)

            # 加入主體清晰度守衛詞（FLUX 無 negative_prompt，避免隨機花瓣/有機紋理）
            enhanced_prompt = self._add_topic_guard_terms(enhanced_prompt)

            # 構建完整 negative prompt
            full_negative = self._build_negative_prompt(
                negative_prompt,
                aspect_ratio,
                avoid_hands
            )

            # 注入 ts: 時間戳 + salt，物理性打破 Replicate 快取
            # 格式：ts:{YYYYMMDDHHMMSS}_{salt_id}（前置注入，leading token 快取權重最強）
            _ts_stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            _salt_id  = format(random.randint(0, 0xFFFFFF), '06x')
            enhanced_prompt = f"ts:{_ts_stamp}_{_salt_id}, {enhanced_prompt}"

            # V32.0 Global Cull — final biological/portrait-term purge (last gate)
            enhanced_prompt = self._cull_biological_terms(enhanced_prompt)

            logger.info(f"📡 FINAL PROMPT → Replicate: {enhanced_prompt}")
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
                if seed is not None:
                    generation_params["seed"] = seed

            elif model == "flux-dev":
                # ⚠️ FLUX 架構不支援 negative_prompt（Replicate 靜默忽略）
                # 亮度/品質控制完全依賴正面 prompt + guidance
                model_id = "black-forest-labs/flux-dev"
                generation_params = {
                    "prompt": enhanced_prompt,
                    "num_outputs": 1,
                    "aspect_ratio": aspect_ratio,
                    "output_format": "webp",
                    "output_quality": output_quality,
                    "num_inference_steps": 28,
                    "guidance": guidance if guidance is not None else 3.5,
                }
                if seed is not None:
                    generation_params["seed"] = seed

            elif model == "flux-1.1-pro":
                model_id = "black-forest-labs/flux-1.1-pro"
                generation_params = {
                    "prompt": enhanced_prompt,
                    "aspect_ratio": aspect_ratio,
                    "output_format": "webp",
                    "output_quality": output_quality,
                    "safety_tolerance": 2,
                }
                if seed is not None:
                    generation_params["seed"] = seed

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
                if seed is not None:
                    generation_params["seed"] = seed
            
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