# -*- coding: utf-8 -*-
"""
封面生成輔助函數 - 微觀奇觀風格
根據觀測單元生成微觀動態封面提示詞
"""
from typing import List
from models.schemas import ObservationUnit


def generate_cover_prompt(units: List[ObservationUnit]) -> str:
    """
    根據所有觀測單元生成微觀奇觀風格的封面圖提示詞
    
    Args:
        units: 觀測單元列表
        
    Returns:
        封面圖英文提示詞（強調微觀動態、無人物）
    """
    if not units:
        return "Abstract micro phenomenon, dynamic process, macro photography, 9:16 vertical format, no people"
    
    # 收集主題關鍵字
    phenomena = []
    keywords = []
    
    for unit in units[:3]:  # 只取前 3 個最重要的單元
        # 從 phenomenon 提取主題
        if hasattr(unit, 'phenomenon') and unit.phenomenon:
            phenomena.append(unit.phenomenon)
        
        # 從 image_prompt 提取關鍵字
        if hasattr(unit, 'image_prompt'):
            if isinstance(unit.image_prompt, dict):
                prompt = unit.image_prompt.get('prompt', '')
            elif hasattr(unit.image_prompt, 'prompt'):
                prompt = unit.image_prompt.prompt
            else:
                prompt = str(unit.image_prompt)
            
            # 提取動態關鍵字（過濾掉人物相關）
            forbidden_words = ['hand', 'finger', 'people', 'person', 'man', 'woman', 'face', 'body']
            words = prompt.split(',')[:2]  # 只取前 2 個關鍵概念
            for word in words:
                word_clean = word.strip().lower()
                # 過濾掉禁止詞
                if not any(forbidden in word_clean for forbidden in forbidden_words):
                    keywords.append(word.strip())
    
    # 組合封面提示詞（微觀奇觀風格）
    if keywords:
        # 使用提取的關鍵字
        main_elements = ', '.join(keywords[:3])
        cover_prompt = (
            f"{main_elements}, "
            f"micro phenomenon collage, "
            f"dynamic process composition, "
            f"macro photography, "
            f"split screen layout, "
            f"high-speed capture, "
            f"9:16 vertical portrait format, "
            f"professional lighting, "
            f"vibrant colors, "
            f"cinematic quality, "
            f"no people, no hands"
        )
    elif phenomena:
        # 如果沒有關鍵字，使用現象描述
        theme_text = phenomena[0]  # 取第一個現象
        cover_prompt = (
            f"Micro wonder cover image, "
            f"{theme_text}, "
            f"dynamic process, "
            f"macro photography, "
            f"high-speed capture, "
            f"9:16 vertical format, "
            f"cinematic composition, "
            f"professional quality, "
            f"no people, no hands"
        )
    else:
        # 預設：抽象微觀動態
        cover_prompt = (
            f"Abstract micro phenomenon, "
            f"dynamic liquid motion, "
            f"macro photography, "
            f"high-speed capture, "
            f"9:16 vertical portrait format, "
            f"vibrant colors, "
            f"cinematic lighting, "
            f"professional quality, "
            f"no people, no hands"
        )
    
    return cover_prompt