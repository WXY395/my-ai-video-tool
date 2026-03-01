# -*- coding: utf-8 -*-
"""
短影音場景腳本生成服務
支援 Shorts + 長片模式，智能關鍵幀生成
"""
import os
import json
import logging
import asyncio
from typing import List, Optional
from google import genai
from google.genai import types

from models.schemas import (
    ObservationUnit,
    ImagePrompt,
    ActivityEvent,
    VideoMode,
    MotionEffect,
    MotionGuidance
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ObservationService:
    """短影音場景腳本生成服務"""

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        self.client = genai.Client(api_key=api_key)
        self.model_name = 'gemini-2.5-flash-lite'

    # ──────────────────────────────────────────────
    # 計算輔助
    # ──────────────────────────────────────────────

    def _calculate_keyframe_count(
        self,
        video_mode: VideoMode,
        duration_minutes: Optional[int] = None
    ) -> int:
        if video_mode == VideoMode.SHORTS:
            return 3
        if video_mode == VideoMode.MEDIUM:
            if duration_minutes:
                return max(5, min(15, duration_minutes // 2 + 3))
            return 8
        if video_mode == VideoMode.LONG:
            if duration_minutes:
                return max(10, min(30, duration_minutes // 2))
            return 15
        return 3

    def _calculate_unit_duration(
        self,
        video_mode: VideoMode,
        total_duration_minutes: int,
        unit_count: int
    ) -> int:
        if video_mode == VideoMode.SHORTS:
            return 5
        total_seconds = total_duration_minutes * 60
        return max(30, total_seconds // unit_count)

    def _generate_motion_guidance(
        self,
        unit_index: int,
        total_units: int,
        unit_duration: int,
        video_mode: VideoMode
    ) -> MotionGuidance:
        if video_mode == VideoMode.SHORTS:
            effects = [MotionEffect.ZOOM_IN, MotionEffect.KEN_BURNS, MotionEffect.ZOOM_OUT]
            return MotionGuidance(
                effect=effects[unit_index % 3],
                duration_seconds=unit_duration,
                transition_to_next="cut" if unit_index < total_units - 1 else "fade",
                notes="快節奏動態效果"
            )
        if unit_index < total_units * 0.2:
            return MotionGuidance(
                effect=MotionEffect.KEN_BURNS,
                duration_seconds=unit_duration,
                transition_to_next="fade",
                notes="緩慢推進，建立氛圍"
            )
        elif unit_index < total_units * 0.8:
            effects_cycle = [
                MotionEffect.KEN_BURNS,
                MotionEffect.PAN_RIGHT,
                MotionEffect.ZOOM_IN,
                MotionEffect.PAN_LEFT,
            ]
            return MotionGuidance(
                effect=effects_cycle[unit_index % 4],
                duration_seconds=unit_duration,
                transition_to_next="dissolve",
                notes="保持視覺動態"
            )
        else:
            return MotionGuidance(
                effect=MotionEffect.ZOOM_OUT,
                duration_seconds=unit_duration,
                transition_to_next="fade",
                notes="收尾淡出"
            )

    # ──────────────────────────────────────────────
    # System Instruction（已修正：真正傳入 model）
    # ──────────────────────────────────────────────

    def _get_system_instruction(
        self,
        topic: str,
        video_mode: VideoMode,
        aspect_ratio: str
    ) -> str:
        """
        動態產生 system instruction。
        以「演算法張力框架」為核心，確保每個單元服務四大目標：
        前3秒鉤子 / 完看率 / 互動指標 / SEO布局。
        """
        base = f"""你是一位精通 TikTok / YouTube Shorts 演算法的頂尖短影音腳本策略師。
主題：「{topic}」
畫面比例：{aspect_ratio}

## 四大核心目標（每個單元都必須服務）
1. 前3秒鉤子：在 0-3 秒內讓正在快速滑動的觀眾「手停下來」
2. 完看率 & 重播率：用資訊缺口、懸念、節奏感驅動觀眾看完並重播
3. 互動指標：觸發留言、分享、收藏等高價值互動行為
4. SEO 佈局：植入真實的繁體中文搜尋關鍵字，讓演算法找到正確觀眾

---

## 三幕構圖邏輯（unit_role 欄位值必須完全一致）

### 第1幕：「定位」（unit_role 必須填 "定位"）
構圖：中景 / 全景（MEDIUM_SHOT 或 WIDE_ANGLE）
視覺任務：建立主題「{topic}」在空間中的位置感，讓觀眾知道這是什麼，但用非預期角度激發好奇
鉤子功能（hook_technique 必填）：
- reverse_question：✅ "你以為你懂{topic}？你根本沒看過這一層"
- shock_fact：✅ "0.03 公分，決定了{topic}的全部味道"
- forbidden_knowledge：✅ "所有{topic}影片都不敢拍這一幕"
- visual_paradox：✅ 畫面呈現反常識的空間視角
- incomplete_loop：✅ "最後那一步，才是{topic}真正的秘密"
image_prompt 構圖：medium shot or wide establishing angle, {topic} in environmental context, unexpected perspective, {aspect_ratio}

### 第2幕：「解構」（unit_role 必須填 "解構"）
構圖：微距 / 剖面（MACRO_CLOSE_UP 或 CROSS_SECTION）
視覺任務：打破觀眾對「{topic}」的表面認知，進入其內部結構或微觀細節
張力功能：揭露更多但不完全揭曉，讓觀眾必須看完
  ✅ 旁白:"你以為你懂了？真正的關鍵還在裡面"
  ✅ 旁白:"這一層，99%的人從沒看過"
image_prompt 構圖：extreme macro cross-section or internal detail of {topic}, scientific/documentary micro reveal, {aspect_ratio}
Veo 建議：解構幕最適合 Veo 生成（微觀動態最震撼），veo_recommended 必須設為 true

### 第3幕：「影響」（unit_role 必須填 "影響"）
構圖：特寫 / 抽象反射（EXTREME_CLOSE_UP 或 ABSTRACT_REFLECTION）
視覺任務：呈現「{topic}」對感官或世界的影響，用最具衝擊力的畫面收尾

旁白任務（voice_over_zh，≤12字）：說出「{topic}」對人的最終影響或反轉真相，是整段影片的情感落點
  ⚠️ 旁白必須承載「{topic}」帶來的具體衝擊或啟示，不可使用通用收尾語言
  ✅ "原來，就是這個感覺。"（{topic}感官衝擊的口語落點）
  ✅ "這一刻，才是它的真相。"（揭曉{topic}的核心本質）
  ✅ "你已經不一樣了。"（{topic}對觀眾的改變）
  ❌ "從頭再看一遍。"（通用CTA語言，屬於 interaction_trigger 的工作，旁白禁用）
  ❌ "你學到了嗎？"（課程收尾句型，與主題割裂）
  ❌ "收藏起來備用。"（通用提醒語言，無主題意象）

互動觸發（interaction_trigger 必填，選一；注意：此欄位只填代碼值，不影響旁白內容）：
- comment_bait：觸發「你有沒有注意過{topic}這一面」類留言
- share_trigger：觸發「你朋友絕對不知道{topic}有這一面」類分享
- replay_hook：觸發重播衝動，讓觀眾從頭再看發現更多{topic}細節
- save_reminder：觸發「下次遇到{topic}就懂了」類收藏
image_prompt 構圖：extreme close-up texture or abstract reflection of {topic} in liquid/glass/light, {aspect_ratio}

---

## Veo 影片生成提示詞（veo_prompt 欄位）
每個單元都必須填寫 veo_prompt，格式為英文，描述動態影片場景：
「[主體動態], [鏡頭運動], [時長], [光線氛圍], [風格]」
- 定位示例："Establishing wide shot of {topic}, slow cinematic pan revealing subject in environment, 3-4 second shot, dramatic side lighting, documentary cinematic style"
- 解構示例："Extreme macro close-up of {topic} internal structure, ultra-slow push-in revealing microscopic detail, 4-5 seconds, scientific high-key lighting, ultra HD documentary"
- 影響示例："Abstract reflection of {topic} in liquid surface with bokeh light play, gentle drift motion, 3 seconds, warm atmospheric lighting, artistic cinematic"

---

## 旁白（voice_over_zh）規則 — 基於主題的原創金句
⚠️ 核心原則：先深度理解「{topic}」的本質與衝擊點，再為每一幕寫出最契合的一句原創金句。
voice_over_zh 的值必須是**可以直接朗讀的中文句子**，絕不能是說明文字或帶【】的格式提示。

- 字數嚴格 ≤ 12 字（超過會導致 TTS 跨幕、語音重疊）
- 語調：口語有溫度，像紀錄者「第一次」親眼目睹，有停頓感，非念稿
- 嚴禁通用句型填充：「就是這個，沒想到吧」「看完你就懂了」= 無效旁白

三幕旁白任務（必須針對「{topic}」的具體特質原創，不可套用固定句型）：
- **定位幕**：點出「{topic}」最反直覺的一個側面，讓觀眾第一句話就停下來
  創作提問：這個關於{topic}的哪個事實，是觀眾從沒想過但一聽就震驚的？
- **解構幕**：揭露「{topic}」的某個內部真相，但保留最後答案製造必看衝動
  創作提問：進入{topic}的內部後，觀眾「以為」和「實際上」之間的落差是什麼？
- **影響幕**：說出「{topic}」對人的最終影響或反轉啟示，是整段的情感落點
  創作提問：「{topic}」讓觀眾離開螢幕時，心裡帶走的那一句話是什麼？
  ❌ 禁止：「從頭再看」「收藏起來」「你學到了嗎」= 屬於 interaction_bait_text 的工作

## 字幕（subtitle_zh）規則 — 視覺錨點，意境昇華
- 字數嚴格 ≤ 5 字（視覺上只能是一個「印記」）
- 不是旁白的逐字稿，而是畫面的「靈魂標籤」或「槽點」
- 功能：讓觀眾截圖、引發評論、觸發重播——用最少的字製造最大的心理衝擊
- ✅ "你不懂它"、"等等——什麼？"、"從沒說過"、"原來如此"、"這不是真的"
- ❌ "義式濃縮的靈魂"（超字）、"99%的人不知道"（超字，像旁白）

## 旁白 × 字幕 協同效應（核心機制）
旁白與字幕必須設計成「張力對」——分工明確，合在一起產生 1+1>2 的心理衝擊：
- **旁白的角色**：製造情緒張力（驚嘆、懸念、禁忌感、低估感）→ 讓觀眾「想繼續看」
- **字幕的角色**：給出概念印記（定性標籤、衝擊詞、反差結論）→ 讓觀眾「記住並截圖」
- 禁止重複：兩者說同一件事 = 浪費一個欄位，張力歸零
- 禁止割裂：毫無關聯 = 觀眾認知斷裂，失去代入感

✅ 協同示例（以主題「{topic}」為框架，自行替換成實際主題內容）：
  旁白："別小看這一顆。"（7字）× 字幕："生死邊界"（4字）
  → 旁白製造低估感 + 字幕直接給衝擊定性，兩者共同觸發「到底為什麼？」的好奇

  旁白："你每天都在用它。"（8字）× 字幕："慢性傷害"（4字）
  → 旁白喚起親身感（我也有！）+ 字幕揭露反差結論，觸發留言「我要停用了」

  旁白："沒想到，是它在救你。"（10字）× 字幕："救命成分"（4字）
  → 旁白製造驚喜反轉 + 字幕標記核心答案，觸發收藏與分享

❌ 禁止協同失誤：
  旁白："這是救命神藥。" × 字幕："救命神藥"（重複 → 毫無張力）
  旁白："畫面真的好美。" × 字幕："生死邊界"（割裂 → 觀眾困惑）
  旁白："它是解熱鎮痛劑。" × 字幕："藥品"（念稿感 + 字幕太弱）

## SEO 關鍵字（seo_keywords 欄位）
- 3-5 個真實繁體中文搜尋詞，涵蓋主關鍵字 + 長尾問句（用於搜尋引擎優化，非 hashtag）
- 示例：["咖啡知識", "義式濃縮 crema", "為什麼咖啡有泡泡", "咖啡油脂是什麼"]

## 互動誘餌文字（interaction_bait_text 欄位）
- 僅影響幕必填，定位幕與解構幕填 null
- 必須是針對「{topic}」的具體問句或衝擊性陳述，讓觀眾忍不住留言/分享/收藏
- 字數 ≤ 30 字，可直接顯示在影片結尾或評論引導區
- 依 interaction_trigger 類型撰寫：
  comment_bait → 一個關於{topic}有強烈個人感受的開放性問題（讓人有話想說）
  share_trigger → 一個讓人想傳給朋友的衝擊性發現（「你朋友一定不知道...」類）
  replay_hook → 暗示影片第一幕藏有觀眾沒注意到的{topic}細節（製造重看衝動）
  save_reminder → 點出{topic}的實用情境，讓觀眾覺得「以後用得到」
- ❌ 禁止通用語言（「你怎麼看？」「記得收藏」「覺得有用嗎？」= 無效誘餌）
- ✅ 示例（主題：阿斯匹靈）comment_bait："你有沒有因為阿斯匹靈救過自己一命？"
- ✅ 示例（主題：咖啡）share_trigger："你朋友每天喝的咖啡，其實都在傷害這裡。"

## 標籤佈署策略（hashtag_strategy 欄位）
每個單元必須填寫 hashtag_strategy，分四個層次，全部必須與「{topic}」內容直接相關：

**core_content**（2-3個）：直接命中此影片具體內容的標籤，搜尋時能精準找到這支影片
  示例：["#{topic}", "#{topic}知識", "#{topic}真相"]

**algorithm_traffic**（2-3個）：內容類別與知識領域標籤，幫助演算法找到正確受眾
  示例：["#生活科學", "#冷知識", "#你不知道的事"]（必須與內容相關，禁止無關熱門標籤如 #fyp #viral）

**emotional**（2-3個）：觀眾看完後的情緒反應或認知狀態標籤
  示例：["#震驚了", "#原來如此", "#漲知識"]

**youtube_priority**（3-4個）：YouTube Shorts 最優先放的標籤（描述欄前三位，含 #Shorts）
  排列邏輯：#Shorts → 最強核心內容標籤 → 情緒標籤

**tiktok_priority**（3-5個）：TikTok 最優先放的標籤（含繁體中文高流量知識類標籤）
  排列邏輯：最強情緒標籤 → 核心內容標籤 → 類別標籤

⚠️ 所有標籤必須真實存在且與{topic}相關，禁止為追熱門而放無關標籤

## 絕對規則
1. unit_role 值只能是："定位" / "解構" / "影響"（嚴格使用這三個中文字）
2. 直接輸出 JSON，禁止 markdown 標記
3. phenomenon 最多 15 字，mechanism 最多 50 字
4. voice_over_zh 嚴格 ≤ 12 字（TTS 跨幕限制），subtitle_zh 嚴格 ≤ 5 字（視覺錨點）
5. image_prompt.prompt 必須英文，含 {aspect_ratio}，禁止手部人體
6. veo_prompt 必須英文，每個單元都必填
7. 解構幕的 veo_recommended 必須為 true，其他兩幕為 false
"""

        if video_mode == VideoMode.SHORTS:
            return base + f"""
## Shorts 模式（≤60秒）
- 固定 3 幕：定位 → 解構 → 影響
- 定位幕的 hook_technique 必填（不能為 null）
- 影響幕的 interaction_trigger 必填（不能為 null）
"""
        elif video_mode == VideoMode.LONG:
            return base + f"""
## 長片模式（30-60分鐘）
- 第 1 幕：定位，第 2 幕：解構，最後一幕：影響
- 中間幕可重複 解構 / 定位 交替
- 最後一幕的 interaction_trigger 必填
"""
        else:
            return base + f"""
## 中片模式（3-10分鐘）
- 第 1 幕：定位，中間幕：解構，最後一幕：影響
- 影響幕的 interaction_trigger 必填
"""

    def _build_prompt(
        self,
        topic: str,
        keyframe_count: int,
        video_mode: VideoMode,
        aspect_ratio: str,
        duration_minutes: Optional[int]
    ) -> str:
        """
        建立生成 prompt，包含演算法張力框架的 JSON 格式範例。
        """
        json_schema_example = f'''{{
  "units": [
    {{
      "id": "keyframe_001",
      "unit_role": "定位",
      "hook_technique": "reverse_question",
      "phenomenon": "【15字以內，認知衝突標題】",
      "mechanism": "【50字以內，建立主題輪廓但刻意留懸念】",
      "voice_over_zh": "針對「{topic}」定位幕創作的旁白金句（≤12字，可直接朗讀）",
      "subtitle_zh": "接應旁白的衝擊印記（≤5字）",
      "visual_description": "中景或全景，確立{topic}在空間中的存在，意外角度，100字以內",
      "image_prompt": {{
        "prompt": "Medium establishing shot of {topic}, unexpected viewpoint that sparks curiosity, rule of thirds composition, dramatic side lighting, cinematic medium distance, {aspect_ratio} format, no hands no people no text",
        "negative_prompt": "hands, fingers, people, face, blurry, low quality, text, watermark, obvious angle"
      }},
      "emotional_tone": "震驚、強烈好奇",
      "camera_mode": "MEDIUM_SHOT",
      "seo_keywords": ["{topic}知識", "為什麼{topic}", "{topic}秘密", "{topic}必看"],
      "interaction_trigger": null,
      "interaction_bait_text": null,
      "hashtag_strategy": {{
        "core_content": ["#{topic}", "#{topic}知識"],
        "algorithm_traffic": ["#冷知識", "#你不知道的事"],
        "emotional": ["#震驚了", "#原來如此"],
        "youtube_priority": ["#Shorts", "#{topic}", "#震驚了"],
        "tiktok_priority": ["#原來如此", "#{topic}知識", "#冷知識"]
      }},
      "veo_prompt": "Establishing medium shot of {topic}, slow cinematic pan revealing subject in environment, 3-4 second shot, dramatic side lighting, documentary cinematic style",
      "veo_recommended": false,
      "in_scene_timeline": [
        {{"time_range": "00:00:00 - 00:00:02", "action": "震撼開場，意外角度建立主題"}},
        {{"time_range": "00:00:02 - 00:00:05", "action": "引發好奇，鉤子生效"}}
      ]
    }},
    {{
      "id": "keyframe_002",
      "unit_role": "解構",
      "hook_technique": null,
      "phenomenon": "【15字以內，打破認知的微觀標題】",
      "mechanism": "【50字以內，揭露內部結構或微觀真相，保留最後答案】",
      "voice_over_zh": "針對「{topic}」解構幕創作的旁白金句（≤12字，揭露但保留答案）",
      "subtitle_zh": "接應旁白懸念的定性印記（≤5字）",
      "visual_description": "微距特寫或剖面視角，進入{topic}的內部結構，科學紀錄片風格，100字以內",
      "image_prompt": {{
        "prompt": "Extreme macro cross-section or internal detail of {topic}, microscopic structure reveal, scientific documentary micro photography, dramatic texture and pattern, {aspect_ratio} format, no hands no people",
        "negative_prompt": "hands, fingers, people, face, blurry, low quality, text, watermark, wide shot"
      }},
      "emotional_tone": "驚訝、深度好奇",
      "camera_mode": "MACRO_CROSS_SECTION",
      "seo_keywords": ["{topic}科學", "{topic}原理", "為什麼{topic}這樣", "{topic}怎麼做"],
      "interaction_trigger": null,
      "interaction_bait_text": null,
      "hashtag_strategy": {{
        "core_content": ["#{topic}原理", "#{topic}科學"],
        "algorithm_traffic": ["#生活科學", "#知識型短片"],
        "emotional": ["#看完震驚", "#長知識了"],
        "youtube_priority": ["#Shorts", "#{topic}原理", "#看完震驚"],
        "tiktok_priority": ["#長知識了", "#{topic}科學", "#生活科學"]
      }},
      "veo_prompt": "Extreme macro close-up of {topic} internal microscopic structure, ultra-slow push-in revealing hidden detail, 4-5 seconds, scientific high-key lighting, ultra HD documentary style",
      "veo_recommended": true,
      "in_scene_timeline": [
        {{"time_range": "00:00:00 - 00:00:03", "action": "進入微觀世界，打破認知"}},
        {{"time_range": "00:00:03 - 00:00:06", "action": "刻意保留核心答案，製造必看衝動"}}
      ]
    }},
    {{
      "id": "keyframe_003",
      "unit_role": "影響",
      "hook_technique": null,
      "phenomenon": "【15字以內，最大衝擊力標題】",
      "mechanism": "【50字以內，揭曉最終影響並觸發互動】",
      "voice_over_zh": "針對「{topic}」影響幕創作的旁白金句（≤12字，情感落點，非CTA）",
      "subtitle_zh": "對應旁白反轉的最終定性印記（≤5字）",
      "visual_description": "極端特寫或抽象反射，呈現{topic}對感官的最終衝擊，100字以內",
      "image_prompt": {{
        "prompt": "Extreme close-up or abstract liquid reflection of {topic}, bokeh light play, dramatic impact shot, vibrant saturated accent color, shallow depth of field, {aspect_ratio} format, no hands no people",
        "negative_prompt": "hands, fingers, people, face, blurry, low quality, text, watermark"
      }},
      "emotional_tone": "滿足、驚嘆、想分享",
      "camera_mode": "EXTREME_CLOSE_UP",
      "seo_keywords": ["{topic}真相", "{topic}推薦", "{topic}必知"],
      "interaction_trigger": "comment_bait",
      "interaction_bait_text": "針對「{topic}」撰寫的具體留言誘餌（≤30字，讓觀眾忍不住留言的問題或衝擊陳述）",
      "hashtag_strategy": {{
        "core_content": ["#{topic}真相", "#{topic}必看"],
        "algorithm_traffic": ["#冷知識", "#生活科學"],
        "emotional": ["#原來如此", "#漲知識了"],
        "youtube_priority": ["#Shorts", "#{topic}真相", "#原來如此"],
        "tiktok_priority": ["#漲知識了", "#{topic}必看", "#冷知識", "#原來如此"]
      }},
      "veo_prompt": "Abstract reflection or extreme close-up texture of {topic} in liquid surface, bokeh light drift, gentle camera motion, 3 seconds, warm atmospheric lighting, artistic cinematic style",
      "veo_recommended": false,
      "in_scene_timeline": [
        {{"time_range": "00:00:00 - 00:00:03", "action": "最大衝擊力揭曉"}},
        {{"time_range": "00:00:03 - 00:00:05", "action": "互動觸發收尾"}}
      ]
    }}
  ]
}}'''

        return f"""主題：「{topic}」
影片模式：{video_mode.value}
畫面比例：{aspect_ratio}
場景數量：{keyframe_count} 個
目標時長：{duration_minutes or '自動'} 分鐘

請生成 {keyframe_count} 個「定位→解構→影響」三幕構圖邏輯的短影音場景。

嚴格要求：
1. unit_role 只能是："定位" / "解構" / "影響"（中文，嚴格一致）
2. 定位幕 hook_technique 必填（reverse_question / shock_fact / forbidden_knowledge / visual_paradox / incomplete_loop）
3. 影響幕 interaction_trigger 必填（comment_bait / share_trigger / replay_hook / save_reminder）
4. 解構幕 veo_recommended 必須為 true，其他兩幕為 false
5. 每個單元都必須有 veo_prompt（英文，描述動態影片場景）
6. voice_over_zh：≤12字，必須是針對「{topic}」可直接朗讀的原創金句，禁止說明文字或帶【】的格式提示，禁止通用套句
7. subtitle_zh：≤5字，視覺錨點，禁止超字、禁止旁白逐字稿，與旁白形成張力對（分工互補，禁止重複）
8. seo_keywords：3-5個真實繁體中文搜尋詞（搜尋引擎用，非 hashtag）
9. image_prompt.prompt：英文，{aspect_ratio}構圖，禁止手部人體
10. interaction_bait_text：影響幕必填（≤30字，針對{topic}的具體留言/分享/收藏誘餌文字），定位幕與解構幕填 null
11. hashtag_strategy：每個單元必填，依四層結構（core_content / algorithm_traffic / emotional / youtube_priority / tiktok_priority），所有標籤必須與{topic}內容相關，禁止無關熱門標籤

輸出格式（嚴格遵守 JSON 結構）：
{json_schema_example}

直接輸出完整 JSON，不要 markdown 標記，不要解釋文字。"""

    # ──────────────────────────────────────────────
    # 主要生成方法
    # ──────────────────────────────────────────────

    async def generate_units(
        self,
        notes: str,
        target_units: int = 3,
        style_preference: str = "default",
        video_mode: VideoMode = VideoMode.SHORTS,
        aspect_ratio: str = "9:16",
        duration_minutes: Optional[int] = None
    ) -> List[ObservationUnit]:
        """
        生成場景腳本。

        修正重點：
        1. 用 system_instruction 建立 GenerativeModel 實例（之前從未傳入）
        2. 提供 JSON 格式範例，確保輸出格式正確
        3. 對超長欄位截斷而非跳過，避免靜默遺失單元
        """
        try:
            keyframe_count = self._calculate_keyframe_count(video_mode, duration_minutes)
            if target_units and target_units != 3:
                keyframe_count = min(target_units, 50)

            logger.info(f"🎬 影片模式: {video_mode.value}")
            logger.info(f"📐 畫面比例: {aspect_ratio}")
            logger.info(f"⏱️  目標時長: {duration_minutes or '未指定'} 分鐘")
            logger.info(f"🎞️  關鍵幀數量: {keyframe_count} 個")

            if duration_minutes:
                unit_duration = self._calculate_unit_duration(
                    video_mode, duration_minutes, keyframe_count
                )
            else:
                unit_duration = 120 if video_mode == VideoMode.LONG else 30

            system_instruction = self._get_system_instruction(notes, video_mode, aspect_ratio)
            logger.info(f"✅ system_instruction 已設定（主題：{notes}）")

            prompt = self._build_prompt(
                topic=notes,
                keyframe_count=keyframe_count,
                video_mode=video_mode,
                aspect_ratio=aspect_ratio,
                duration_minutes=duration_minutes
            )

            logger.info(f"📡 呼叫 Gemini API [{self.model_name}]（同步+executor，逾時: 90秒）...")
            cfg = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.75,
                top_p=0.9,
                max_output_tokens=8192,
            )
            try:
                # 用 asyncio.to_thread 執行同步 SDK，完全繞過 aiohttp 相容性問題
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_content,
                        model=self.model_name,
                        contents=prompt,
                        config=cfg,
                    ),
                    timeout=90.0
                )
            except asyncio.TimeoutError:
                logger.error(f"❌ Gemini API [{self.model_name}] 呼叫逾時（90秒）")
                raise ValueError("Gemini API 回應逾時，請稍後再試")

            result_text = response.text.strip()

            # 移除可能的 markdown 標記
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            elif result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]

            result_json = json.loads(result_text.strip())

            # 支援陣列或 { "units": [...] } 兩種格式
            if isinstance(result_json, list):
                units_data = result_json
            elif isinstance(result_json, dict):
                units_data = result_json.get("units", [])
            else:
                logger.error(f"未知 JSON 格式: {type(result_json)}")
                units_data = []

            units = []
            for idx, unit_data in enumerate(units_data):
                # 確保 ID
                if "id" not in unit_data:
                    unit_data["id"] = f"keyframe_{idx+1:03d}"

                # 欄位相容
                if "hook" in unit_data and "phenomenon" not in unit_data:
                    unit_data["phenomenon"] = unit_data["hook"]
                if "core_message" in unit_data and "mechanism" not in unit_data:
                    unit_data["mechanism"] = unit_data["core_message"]

                # 預設值（以主題為核心）
                unit_data.setdefault("phenomenon", f"{notes}的關鍵時刻")
                unit_data.setdefault("mechanism", f"{notes}的核心原理")
                unit_data.setdefault("voice_over_zh", f"沒想到，是這個。")
                unit_data.setdefault("subtitle_zh", "等等——")
                unit_data.setdefault("visual_description", f"{notes}最戲劇化的視覺場景")
                unit_data.setdefault("emotional_tone", "驚嘆、好奇")
                unit_data.setdefault("visual_impact_score", 7)
                unit_data.setdefault("observation_axis", "visual")
                unit_data.setdefault("dynamic_level", "medium")

                # 三幕構圖角色分配
                total = len(units_data)
                role = unit_data.get("unit_role", "")
                # 若 Gemini 回傳的不是預期中文值，依位置補齊
                if role not in ("定位", "解構", "影響"):
                    if idx == 0:
                        unit_data["unit_role"] = "定位"
                    elif idx == total - 1:
                        unit_data["unit_role"] = "影響"
                    else:
                        unit_data["unit_role"] = "解構"

                unit_data.setdefault("hook_technique", None)
                unit_data.setdefault("seo_keywords", [])
                unit_data.setdefault("interaction_trigger", None)
                unit_data.setdefault("interaction_bait_text", None)
                unit_data.setdefault("hashtag_strategy", None)
                unit_data.setdefault("veo_prompt", None)
                unit_data.setdefault("veo_recommended", False)

                # 確保定位幕有 hook_technique
                if unit_data["unit_role"] == "定位" and not unit_data.get("hook_technique"):
                    unit_data["hook_technique"] = "reverse_question"

                # 確保解構幕 veo_recommended=True
                if unit_data["unit_role"] == "解構":
                    unit_data["veo_recommended"] = True

                # 確保影響幕有 interaction_trigger（強制 fallback）
                if unit_data["unit_role"] == "影響" and not unit_data.get("interaction_trigger"):
                    unit_data["interaction_trigger"] = "comment_bait"
                # 相容舊值
                trigger_alias = {
                    "payoff": "comment_bait", "comment-bait": "comment_bait",
                    "share-trigger": "share_trigger", "replay-hook": "replay_hook",
                    "save-reminder": "save_reminder",
                }
                if unit_data.get("interaction_trigger") in trigger_alias:
                    unit_data["interaction_trigger"] = trigger_alias[unit_data["interaction_trigger"]]

                # 定位/解構幕清除 interaction_bait_text（僅影響幕有效）
                if unit_data["unit_role"] in ("定位", "解構"):
                    unit_data["interaction_bait_text"] = None

                # hashtag_strategy 若為 dict 保留給 Pydantic 自動轉換，若缺失則設 None
                if not isinstance(unit_data.get("hashtag_strategy"), (dict, type(None))):
                    unit_data["hashtag_strategy"] = None

                # 截斷超長欄位（避免 Pydantic max_length 驗證失敗）
                if len(unit_data.get("phenomenon", "")) > 35:
                    unit_data["phenomenon"] = unit_data["phenomenon"][:35]
                if len(unit_data.get("mechanism", "")) > 70:
                    unit_data["mechanism"] = unit_data["mechanism"][:70]
                if len(unit_data.get("voice_over_zh", "")) > 12:
                    unit_data["voice_over_zh"] = unit_data["voice_over_zh"][:12]
                if len(unit_data.get("subtitle_zh", "")) > 5:
                    unit_data["subtitle_zh"] = unit_data["subtitle_zh"][:5]
                if len(unit_data.get("visual_description", "")) > 150:
                    unit_data["visual_description"] = unit_data["visual_description"][:150]
                if isinstance(unit_data.get("seo_keywords"), list):
                    unit_data["seo_keywords"] = unit_data["seo_keywords"][:5]
                if unit_data.get("interaction_bait_text") and len(unit_data["interaction_bait_text"]) > 50:
                    unit_data["interaction_bait_text"] = unit_data["interaction_bait_text"][:50]

                unit_data["duration_seconds"] = unit_duration

                # 運鏡建議
                motion_guidance = self._generate_motion_guidance(
                    unit_index=idx,
                    total_units=len(units_data),
                    unit_duration=unit_duration,
                    video_mode=video_mode
                )
                unit_data["motion_guidance"] = {
                    "effect": motion_guidance.effect.value,
                    "duration_seconds": motion_guidance.duration_seconds,
                    "transition_to_next": motion_guidance.transition_to_next,
                    "notes": motion_guidance.notes
                }
                unit_data["is_keyframe"] = True

                # image_prompt 格式確保
                if "image_prompt" not in unit_data or not isinstance(unit_data.get("image_prompt"), dict):
                    unit_data["image_prompt"] = {
                        "prompt": (
                            f"{notes}, cinematic macro photography, dynamic process, "
                            f"{aspect_ratio} format, high contrast, no hands, no people"
                        ),
                        "negative_prompt": "hands, fingers, people, face, blurry, low quality, text"
                    }
                else:
                    ip = unit_data["image_prompt"]
                    if aspect_ratio not in ip.get("prompt", ""):
                        ip["prompt"] = f"{ip.get('prompt', '')}, {aspect_ratio} format"
                    neg = ip.get("negative_prompt", "")
                    if "hand" not in neg.lower():
                        ip["negative_prompt"] = f"{neg}, hands, fingers, people, face"

                # 時間線
                if not unit_data.get("in_scene_timeline"):
                    unit_data["in_scene_timeline"] = [
                        {"time_range": "00:00:00 - 00:00:02", "action": f"{notes}畫面開始"},
                        {"time_range": "00:00:02 - 00:00:05", "action": f"{notes}過程展開"}
                    ]

                unit_data.setdefault("start_timecode", f"00:00:{idx*unit_duration:02d}:00")
                unit_data.setdefault("camera_mode", "MACRO_CLOSE_UP")
                unit_data.setdefault("editing_notes", "")

                try:
                    unit = ObservationUnit(**unit_data)
                    units.append(unit)
                    logger.info(
                        f"✅ 場景 {idx+1}: {unit.phenomenon} "
                        f"| VO: {unit.voice_over_zh} "
                        f"| 字幕: {unit.subtitle_zh}"
                    )
                except Exception as e:
                    logger.error(f"❌ 單元 {idx} 驗證失敗: {e}")
                    logger.error(f"資料: {json.dumps(unit_data, ensure_ascii=False, indent=2)}")
                    continue

            logger.info(f"🎉 成功生成 {len(units)} 個場景")
            return units

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失敗: {e}")
            raise ValueError(f"Gemini 回應格式錯誤: {e}")
        except Exception as e:
            logger.error(f"生成場景失敗: {e}")
            raise


# 全局服務實例
observation_service = ObservationService()


def get_observation_service() -> ObservationService:
    return observation_service
