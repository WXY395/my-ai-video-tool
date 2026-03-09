"""
V35.6 Audio-Visual Factory — bridge/main.py
Pipeline: [SSOT] → Gemini Pro (render) → GPT-4o (polish)
          → SRT SMPTE gen → Runbook CH-grouping → Image routing → Disk

V35.6 終極驗收規格：
  [SEO]      純文字輸出，嚴禁 ##、**、任何 Markdown 符號
  [Cover]    Nano Banana 2 | aspect_ratio=9:16 | East Asian wash painting
             | 繁中標題文字渲染（如「夜尿危機」）注入封面
  [Scene 2+] No-text block 置於提示詞最前方 | East Asian wash painting
             | aspect_ratio=9:16
  [SMPTE]    Frames = round(ms / 1000 * 30)，HH:MM:SS:FF @30fps
  [Log]      每幕列印 MODEL NAME + aspect_ratio + allow_text
"""

import argparse
import base64
import io
import json
import os
import re
import sys
import time
from collections import OrderedDict
from datetime import datetime

# V35.6.2: Force UTF-8 stdout on Windows to prevent cp950 encoding crashes
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from functools import wraps
from pathlib import Path
from typing import List, Optional

import requests
from dotenv import load_dotenv
from pydantic import BaseModel

# ── Env ────────────────────────────────────────────────────────────────────────
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"]
OPENAI_API_KEY      = os.environ["OPENAI_API_KEY"]
REPLICATE_API_TOKEN = os.environ["REPLICATE_API_TOKEN"]

# ── Model IDs ──────────────────────────────────────────────────────────────────
SSOT_MODEL   = "gemini-3-flash-preview"
TEXT_MODEL   = "gemini-3.1-pro-preview"
NANO_BANANA  = "gemini-2.5-flash-image"                        # V35.6.2: official model — generate_content + imageConfig
FLUX_MODEL   = "black-forest-labs/flux-schnell"
DALLE_MODEL  = "dall-e-3"

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG DNA
# ══════════════════════════════════════════════════════════════════════════════

DIRECTOR_SYSTEM_INSTRUCTION = """\
角色：百萬 YouTuber 影音導演。
核心原則：追求極致節奏、幽默感與社群病毒式傳播力。

幽默口吻規範：
1. 以「幽默、詼諧、逗趣」為主軸，適時加入反轉、吐槽或內心 OS。
2. 拒絕枯燥的說教，將複雜知識轉化為好玩的段子。
3. 保持專業底線，不胡編亂造，但表達方式必須有趣。

知識精準度要求：
1. 緊扣 SSOT（唯一真相）提供的大綱與事實。
2. 醫療或專業知識必須精確，但需轉化為大眾聽得懂的口語。\
"""

# ══════════════════════════════════════════════════════════════════════════════
# VISUAL RENDERING ENGINE (V35.6 終極驗收版)
# ══════════════════════════════════════════════════════════════════════════════

# Image generation config — hardened for all requests
IMAGE_ASPECT_RATIO = "9:16"
IMAGE_PIXEL_SIZE   = (720, 1280)   # pixel fallback when aspect_ratio rejected
IMAGE_SIZE         = "1K"          # aspirational; not yet exposed in Gemini SDK

# SMPTE timecode frame rate
SMPTE_FPS = 30

# ── Shared style core (East Asian wash painting, anti-hallucination V35.6) ───
# ── Cover / Nano Banana style (East Asian wash — text rendering allowed on cover) ──
_STYLE_CORE = (
    "East Asian wash painting style with ink wash technique, "
    "wild and rough brushstrokes, bold color block collisions, "
    "ink bleeding and dripping textures, abstract dynamism, "
    "imperfect hand-drawn feel, eschewing smooth details and photorealistic rendering, "
    "raw energy aura. Centered composition, high contrast, textured paper background, "
    "studio lighting. Primitive style, no blur, no plastic feel, avoid perfect symmetry."
)

# ── Flux scene style (V35.6.3: de-textualized — no painting/calligraphy words) ──
_FLUX_STYLE_CORE = (
    "Modern minimalist ink splash abstraction, "
    "organic fluid ink textures, monochromatic spills, "
    "wild and rough brushstrokes, bold color block collisions, "
    "ink bleeding and dripping textures, abstract dynamism, "
    "imperfect hand-drawn feel, eschewing smooth details and photorealistic rendering, "
    "raw energy aura. Centered composition, high contrast, textured paper background, "
    "studio lighting. Primitive style, no blur, no plastic feel, avoid perfect symmetry. "
    "Pure visual imagery only. Ensure no artistic signatures, no red stamps, "
    "no chop marks, and no pseudo-text characters appear anywhere in the composition."
)

# ── No-text prefix for cover/Nano scenes ─────────────────────────────────────
_NO_TEXT_PREFIX = (
    "(No text, no letters, no watermarks, no logos, "
    "no symbols, no alphabet characters)"
)

# ── Flux double-barrier prefix (V35.6.3: repeated twice to raise weight) ──────
_FLUX_NO_TEXT_PREFIX = (
    "(No text, no letters, no labels, no watermarks, no seals, no stamps) "
    "(No text, no letters, no labels, no watermarks, no seals, no stamps)"
)

# Keep for backward-compat log references
FLUX_NO_TEXT_SUFFIX = _FLUX_NO_TEXT_PREFIX


def apply_style_cover(prompt: str, title: str = "") -> str:
    """
    Cover image ONLY (Nano Banana 2):
      - East Asian wash painting style
      - Renders the Chinese topic title (e.g. '夜尿危機') in bold calligraphy
      - No no-text prefix (text rendering is intentionally allowed)
    """
    title_instr = (
        f"Render the title '\u300c{title}\u300d' in bold Traditional Chinese calligraphy, "
        "centered at the top of the frame, large and impactful. "
        if title else
        "Traditional Chinese title text rendering allowed. "
        "Clean, bold calligraphy centered at top of frame. "
    )
    return f"{prompt.strip()}\n\n{title_instr}{_STYLE_CORE}"


def apply_style_scene(prompt: str) -> str:
    """
    scene_001 via Nano Banana 2: standard no-text prefix + East Asian wash style.
    """
    return f"{_NO_TEXT_PREFIX}\n\n{prompt.strip()}\n\n{_STYLE_CORE}"


def apply_style_flux_scene(prompt: str) -> str:
    """
    V35.6.3 — scene_002+ via Flux-schnell: de-textualized style surgery.
    - Double-weight no-text barrier (seals / stamps / labels added)
    - Modern minimalist ink splash abstraction (painting/calligraphy removed)
    - Visual barrier suffix: no red stamps, no chop marks, no pseudo-text
    NOTE: flux-schnell has no negative_prompt param — all anti-text in main prompt.
    """
    return f"{_FLUX_NO_TEXT_PREFIX}\n\n{prompt.strip()}\n\n{_FLUX_STYLE_CORE}"


# Legacy alias for cover / Nano Banana — unchanged
apply_style_cover_scene1 = apply_style_cover


# ── Pydantic Schemas ───────────────────────────────────────────────────────────
class ImagePrompt(BaseModel):
    chapter:    str   # story-node name; multiple scenes may share the same chapter
    prompt:     str   # base image prompt (STYLE_TEMPLATE applied at generation time)
    filename:   str   # scene_001.png … scene_00N.png
    veo_prompt: str   # 物理交互: … | 鏡頭語言: … | 風格一致性: …


class ContentPack(BaseModel):
    topic:                str
    draft_vo_srt:         str   # SRT string — generated locally via generate_srt()
    draft_subtitles_srt:  str
    runbook_all_in_one:   str   # Markdown, built locally via build_runbook()
    seo_txt:              str
    cover_prompt:         str
    image_prompts:        List[ImagePrompt]


# ══════════════════════════════════════════════════════════════════════════════
# DIRECTOR — Core decision engine (V35.6)
# ══════════════════════════════════════════════════════════════════════════════
class Director:
    """
    V35.6 Director: orchestrates segmentation, visual metaphor, Veo decisions,
    1:1 VO-to-scene alignment, and runbook editorial logic.
    Call Director.initialize() at pipeline start to log capabilities.
    """

    MAX_SEGMENT_CHARS: int = 10

    # ── Dynamic verb set → Veo generation trigger ─────────────────────────────
    VEO_TRIGGER_VERBS: set = {
        "流出", "破碎", "閃爍", "奔跑", "爆炸",
        "衝", "噴", "顫抖", "燃燒", "墜落", "崩潰",
    }

    # ── Keyword → English visual metaphor ────────────────────────────────────
    METAPHOR_MAP: dict = {
        "壓力":   "a water balloon or pressure cooker on the verge of bursting",
        "攝護腺": "a crimson sphere tightly wrapped in straws, pearls clogging a boba tube",
        "前列腺": "a crimson sphere tightly wrapped in straws, pearls clogging a boba tube",
        "膀胱":   "a translucent overfull water bag, delicate membrane under strain",
        "夜尿":   "a crescent moon tangled in a dripping faucet, ink drops cascading",
        "頻尿":   "an overflowing ink well, drops cascading endlessly over parchment",
        "尿":     "cascading crystal water droplets on ancient ink-washed stone",
        "失眠":   "a ticking clock submerged in an ocean of inky darkness",
        "發炎":   "a glowing amber ember smoldering within soft tissue folds",
        "腎臟":   "twin filtration crystals glowing amber in swirling river current",
        "糖尿病": "sugar crystals overwhelming a delicate river filtration system",
        "老化":   "autumn leaves shedding from a gnarled ancient ink-wash tree",
        "睡眠":   "a peaceful ink-wash moon drifting over still water",
        "荷爾蒙": "invisible luminous rivers of fluid coursing through body channels",
    }

    # ── SFX assignments ───────────────────────────────────────────────────────
    _HUMOR_MARKERS  = {"吐槽", "哈", "笑", "傻", "竟然", "居然", "沒想到", "反轉", "OS", "白"}
    _SFX_TRANSITION = "Scene transition sound (soft whoosh)"
    _SFX_HUMOR      = "Funny pop sound (comedic sting)"
    _SFX_AMBIENT    = "Ambient soundscape (night crickets, distant city hum)"

    # ── Init ─────────────────────────────────────────────────────────────────
    @classmethod
    def initialize(cls) -> None:
        print("\n" + "═" * 60)
        print("  [Director] Logic Initialized — V35.6")
        print("═" * 60)
        print(f"  Veo trigger verbs  : {sorted(cls.VEO_TRIGGER_VERBS)}")
        print(f"  Metaphor keywords  : {len(cls.METAPHOR_MAP)} entries")
        print(f"  Segment max chars  : {cls.MAX_SEGMENT_CHARS} 字/段")
        print(f"  Duration formula   : 0.3s + N×0.19s + 0.5s")
        print(f"  SMPTE formula      : Frames = round(ms / 1000 × 30)")
        print(f"  Veo force-on       : Hook (scene_001) + Payoff (last scene)")
        print("═" * 60)

    # ── 1. Segmentation ───────────────────────────────────────────────────────
    @classmethod
    def segment_script(cls, text: str) -> List[str]:
        """
        Split text into micro-segments ≤ MAX_SEGMENT_CHARS using CJK punctuation.
        Force-split any segment still exceeding the limit character-by-character.
        """
        raw_parts = re.split(r"[。，、！？；…\n]+", text)
        segments: List[str] = []
        for part in raw_parts:
            part = part.strip()
            if not part:
                continue
            while len(part) > cls.MAX_SEGMENT_CHARS:
                segments.append(part[: cls.MAX_SEGMENT_CHARS])
                part = part[cls.MAX_SEGMENT_CHARS :]
            if part:
                segments.append(part)
        return segments

    # ── 2. Veo decision ───────────────────────────────────────────────────────
    @classmethod
    def needs_veo(cls, vo_text: str, scene_idx: int = -1,
                  total_scenes: int = 0) -> bool:
        """
        Returns True if:
          - scene is the Hook   (index 0, forces first-3-second veo)
          - scene is the Payoff (last index)
          - VO contains any dynamic trigger verb
        """
        if scene_idx == 0:
            return True
        if total_scenes > 0 and scene_idx == total_scenes - 1:
            return True
        return any(v in vo_text for v in cls.VEO_TRIGGER_VERBS)

    @staticmethod
    def make_veo_prompt(subject: str, action: str,
                        atmosphere: str = "night with ink-wash shadows") -> str:
        """
        Formula: [Subject] + [Action] + [Camera Movement]
                 + [Atmospheric Effects] + [Visual Style Consistency]
        """
        return (
            f"{subject} {action}, "
            "slow push-in camera tracking the subject, "
            f"{atmosphere}, "
            "East Asian wash painting style with Fauvism bold brushstroke borders "
            "and high-contrast color blocks."
        )

    # ── 3. Visual metaphor ────────────────────────────────────────────────────
    @classmethod
    def extract_metaphor(cls, vo_text: str) -> str:
        """Return first matching visual metaphor for keywords found in VO text."""
        for keyword, metaphor in cls.METAPHOR_MAP.items():
            if keyword in vo_text:
                return metaphor
        return ""

    @classmethod
    def enrich_scene_prompt(cls, base_prompt: str, vo_text: str) -> str:
        """Append visual metaphor to scene prompt when VO keyword matches."""
        metaphor = cls.extract_metaphor(vo_text)
        if metaphor:
            return f"{base_prompt}; visual metaphor: {metaphor}"
        return base_prompt

    # ── 4. 1:1 Scene alignment ────────────────────────────────────────────────
    @staticmethod
    def align_scenes(
        vo_lines: List[str],
        scenes: List["ImagePrompt"],
        topic: str,
    ) -> List["ImagePrompt"]:
        """
        Enforce strict 1:1 VO-to-scene mapping.
          - scenes < vo_lines → pad with generic auto-scenes
          - scenes > vo_lines → trim
        Re-index all filenames to scene_001.png … scene_00N.png.
        """
        n = len(vo_lines)
        aligned = list(scenes[:n])
        while len(aligned) < n:
            i = len(aligned)
            aligned.append(
                ImagePrompt(
                    chapter    = f"Auto_Segment_{i + 1:02d}",
                    prompt     = f"Abstract visual representation: {vo_lines[i]}",
                    filename   = f"scene_{i + 1:03d}.png",
                    veo_prompt = (
                        f"Abstract ink-wash composition for '{vo_lines[i]}', "
                        "slow zoom-in camera, East Asian wash painting style."
                    ),
                )
            )
        # Re-index filenames for strict sequential naming
        for i, s in enumerate(aligned):
            aligned[i] = s.model_copy(update={"filename": f"scene_{i + 1:03d}.png"})
        return aligned

    # ── 5. SFX decision ───────────────────────────────────────────────────────
    @classmethod
    def sfx_for_scene(cls, vo_text: str, sub_text: str = "",
                      scene_idx: int = 0, total_scenes: int = 1) -> str:
        """
        Auto-assign SFX based on scene position and content.
        Priority: Hook/Payoff transition > humor marker > ambient.
        """
        if scene_idx == 0 or (total_scenes > 0 and scene_idx == total_scenes - 1):
            return cls._SFX_TRANSITION
        combined = vo_text + sub_text
        if any(m in combined for m in cls._HUMOR_MARKERS):
            return cls._SFX_HUMOR
        return cls._SFX_AMBIENT

    # ── 6. Camera action for static images ───────────────────────────────────
    @staticmethod
    def static_action() -> str:
        return "Camera slow zoom in (1.2×) | Ken Burns effect"


# ── Timecode helpers ───────────────────────────────────────────────────────────
def compute_srt_duration(text: str) -> float:
    """0.3s lead-in + 0.19s/char + 0.5s tail → returns seconds."""
    return 0.3 + len(text.strip()) * 0.19 + 0.5


def ms_to_smpte(ms: float, fps: int = SMPTE_FPS) -> str:
    """
    Convert milliseconds → SMPTE HH:MM:SS:FF.
    V35.6 formula: Frames = round(ms / 1000 * fps)
    """
    total_frames = round(ms / 1000 * fps)
    ff      = total_frames % fps
    total_s = total_frames // fps
    h       = total_s // 3600
    m       = (total_s % 3600) // 60
    s       = total_s % 60
    return f"{h:02d}:{m:02d}:{s:02d}:{ff:02d}"


def float_to_smpte(seconds: float, fps: int = SMPTE_FPS) -> str:
    """Convert float seconds → SMPTE HH:MM:SS:FF (delegates to ms_to_smpte)."""
    return ms_to_smpte(seconds * 1000, fps)


def generate_srt(text_lines: List[str]) -> str:
    """
    Build SRT from plain text segments using SMPTE timecodes (HH:MM:SS:FF @ 30fps).
    Each content line ends with \\n per V35.6 spec.
    """
    blocks = []
    current_time = 0.0
    for i, text in enumerate(text_lines, 1):
        text = text.strip()
        if not text:
            continue
        duration = compute_srt_duration(text)
        t_in     = float_to_smpte(current_time)
        t_out    = float_to_smpte(current_time + duration)
        blocks.append(f"{i}\n{t_in} --> {t_out}\n{text}\n")
        current_time += duration + 0.1
    return "\n".join(blocks)


# ── Retry decorator ────────────────────────────────────────────────────────────
def exponential_retry(max_attempts: int = 3, base_delay: float = 2.0):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    print(f"  [retry {attempt+1}/{max_attempts-1}] {type(e).__name__}: {str(e)[:80]}")
                    print(f"  Waiting {delay:.0f}s...")
                    time.sleep(delay)
        return wrapper
    return decorator


# ── Countdown ─────────────────────────────────────────────────────────────────
def countdown(seconds: int, label: str = "Cooling down"):
    for remaining in range(seconds, 0, -1):
        print(f"\r  [{label}] {remaining:3d}s remaining...", end="", flush=True)
        time.sleep(1)
    print(f"\r  [{label}] Done!                         ")


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — SSOT Extraction (optional, --ssot flag)
# ══════════════════════════════════════════════════════════════════════════════
@exponential_retry(max_attempts=3)
def extract_ssot_facts(ssot_text: str, topic: str) -> str:
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    print(f"\n[PHASE 1] Extracting SSOT via {SSOT_MODEL}...")
    prompt = (
        f"從以下 SSOT 文件中，提取關於『{topic}』的關鍵事實與大綱。\n\n"
        "輸出 Markdown 格式：\n"
        "- 核心醫療 / 專業事實（精確數據）\n"
        "- 適合 YouTuber 的統計與對比\n"
        "- 章節大綱建議（8–12 段，分故事節點）\n"
        "- 可用的幽默切入點\n\n"
        f"SSOT：\n{ssot_text[:8000]}"
    )
    resp   = client.models.generate_content(model=SSOT_MODEL, contents=prompt)
    facts  = resp.text.strip()
    print(f"  SSOT extracted: {len(facts)} chars")
    return facts


# ── SEO post-processor ─────────────────────────────────────────────────────────
def clean_seo_txt(text: str) -> str:
    """
    Strip residual Markdown from SEO output.
    Rule: only strip heading markers (#+ followed by SPACE), preserving #hashtags.
    """
    # ## heading: # or ## or ### followed by at least one space → drop the hashes+space
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # **bold** and *italic* — line-safe, non-greedy
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*([^\n*]+?)\*",  r"\1", text)
    # __underline__ and _italic_ — line-safe
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_([^\n_]+?)_",  r"\1", text)
    return text.strip()


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — ContentPack Rendering (gemini-3.1-pro-preview)
# ══════════════════════════════════════════════════════════════════════════════
@exponential_retry(max_attempts=3)
def generate_content_pack(topic: str, ssot_facts: str = "") -> ContentPack:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)

    ssot_block = (
        f"\n\n【SSOT 事實庫】\n{ssot_facts}" if ssot_facts
        else "\n\n【無 SSOT — 根據主題自行生成，確保醫療事實精確】"
    )

    USER_PROMPT = (
        f"主題：{topic}{ssot_block}\n\n"
        "請生成完整的影片內容包。硬性規定：\n"
        "1. vo_lines：旁白極簡短句列表，共 8–12 項。"
        "【每項不超過 10 個字，禁止長句】語氣幽默、有反轉、有衝擊感。\n"
        "2. subtitle_lines：精簡字幕列表，每項 ≤ 8 字，與 vo_lines 完全等長（一對一）\n"
        "3. seo_txt：四平台 SEO 純文字。\n"
        "   ⚠️  硬性規定：輸出中絕對不得出現 ##、**、__、* 或任何 Markdown 符號。\n"
        "   嚴格遵循以下格式（以【平台名稱】開頭，--- 為唯一分隔符）：\n"
        "【YouTube】\n"
        "標題：{幽默反轉標題，含數字或反問，30字內}\n"
        "描述：{2–3句，痛點+解方+CTA}\n"
        "#標籤1 #標籤2 #標籤3 #標籤4 #標籤5 #標籤6\n"
        "---\n"
        "【TikTok】\n"
        "標題：{衝擊感強，15字內}\n"
        "描述：{1句，直擊痛點}\n"
        "#標籤1 #標籤2 #標籤3 #標籤4\n"
        "---\n"
        "【Instagram】\n"
        "標題：{視覺感強，20字內}\n"
        "描述：{2句，情境代入+行動號召}\n"
        "#標籤1 #標籤2 #標籤3 #標籤4 #標籤5\n"
        "---\n"
        "【Facebook】\n"
        "標題：{親切口語，引發共鳴，25字內}\n"
        "描述：{2–3句，故事切入+分享邀請}\n"
        "#標籤1 #標籤2 #標籤3\n"
        f"4. cover_prompt：電影級封面英文提示詞，"
        f"必須包含繁中標題文字渲染指令，範例："
        f"\"Render the title 『{topic}』 in bold Traditional Chinese calligraphy, centered at top.\"\n"
        "5. image_prompts：數量必須與 vo_lines 完全相等（每段 VO 對應唯一分鏡）。"
        "chapter 為該段故事節點，每個 scene 必須有獨立唯一的 chapter 名稱，"
        "filename 格式 scene_001.png，"
        "veo_prompt 必須為純英文，嚴格遵循公式："
        "[Subject] + [Action/Interaction] + [Camera Movement] + [Atmospheric Effects] + [Visual Style Consistency]。"
        "範例：'An exhausted elderly man slowly rises from bed and shuffles toward the bathroom, "
        "low-angle tracking shot following his feet, moonlight casting blue shadows through curtains, "
        "Fauvism ink-wash bold brushstroke borders with high-contrast color blocks.'\n"
        "輸出純 JSON，不含 markdown code block。"
    )

    # Gemini response schema (vo/subtitle as plain lines; SRT built locally)
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "topic":    {"type": "STRING"},
            "vo_lines": {"type": "ARRAY",  "items": {"type": "STRING"}},
            "subtitle_lines": {"type": "ARRAY", "items": {"type": "STRING"}},
            "seo_txt":        {"type": "STRING"},
            "cover_prompt":   {"type": "STRING"},
            "image_prompts": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "chapter":    {"type": "STRING"},
                        "prompt":     {"type": "STRING"},
                        "filename":   {"type": "STRING"},
                        "veo_prompt": {"type": "STRING"},
                    },
                    "required": ["chapter", "prompt", "filename", "veo_prompt"],
                },
            },
        },
        "required": ["topic", "vo_lines", "subtitle_lines",
                     "seo_txt", "cover_prompt", "image_prompts"],
    }

    # Print request body
    print("\n" + "=" * 60)
    print("  REQUEST BODY -> Gemini Phase 2")
    print("=" * 60)
    print(json.dumps({
        "model":  TEXT_MODEL,
        "system": DIRECTOR_SYSTEM_INSTRUCTION[:80] + "...",
        "user":   USER_PROMPT[:120] + "...",
        "config": {
            "response_mime_type": "application/json",
            "image_aspect_ratio": IMAGE_ASPECT_RATIO,
            "image_size":         IMAGE_SIZE,
            "style_template":     "STYLE_TEMPLATE (applied at generation time)",
        },
    }, ensure_ascii=False, indent=2))
    print("=" * 60)

    resp = client.models.generate_content(
        model=TEXT_MODEL,
        contents=USER_PROMPT,
        config=types.GenerateContentConfig(
            system_instruction=DIRECTOR_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=response_schema,
        ),
    )

    raw  = resp.text.strip()
    raw  = re.sub(r"^```(?:json)?\s*", "", raw)
    raw  = re.sub(r"\s*```$",          "", raw)
    data = json.loads(raw)

    # ── Director: safety-net segmentation ────────────────────────────────────
    raw_vo  = data["vo_lines"]
    raw_sub = data["subtitle_lines"]

    # Expand any VO line that exceeds MAX_SEGMENT_CHARS
    processed_vo:  List[str] = []
    processed_sub: List[str] = []
    for i, line in enumerate(raw_vo):
        sub = raw_sub[i] if i < len(raw_sub) else ""
        if len(line) > Director.MAX_SEGMENT_CHARS:
            segs = Director.segment_script(line)
            processed_vo.extend(segs)
            processed_sub.append(sub)
            processed_sub.extend([""] * (len(segs) - 1))  # pad sub for extra segs
        else:
            processed_vo.append(line)
            processed_sub.append(sub)

    print(
        f"  [Director] VO segments: {len(raw_vo)} raw → {len(processed_vo)} after segmentation"
    )

    # Build SRT from processed lines
    vo_srt  = generate_srt(processed_vo)
    sub_srt = generate_srt(processed_sub)

    # Build base scenes from LLM output (normalize filenames)
    raw_scenes: List[ImagePrompt] = []
    for i, s in enumerate(data["image_prompts"]):
        raw_scenes.append(ImagePrompt(
            chapter    = s["chapter"],
            prompt     = s["prompt"],
            filename   = f"scene_{i + 1:03d}.png",
            veo_prompt = s["veo_prompt"],
        ))

    # ── Director: 1:1 alignment + visual metaphor enrichment ─────────────────
    scenes = Director.align_scenes(processed_vo, raw_scenes, data["topic"])
    scenes = [
        s.model_copy(update={
            "prompt": Director.enrich_scene_prompt(s.prompt, processed_vo[i])
        })
        for i, s in enumerate(scenes)
    ]
    print(f"  [Director] Scenes aligned: {len(scenes)} (1:1 with VO segments)")

    return ContentPack(
        topic               = data["topic"],
        draft_vo_srt        = vo_srt,
        draft_subtitles_srt = sub_srt,
        runbook_all_in_one  = "",   # filled in by build_runbook()
        seo_txt             = clean_seo_txt(data["seo_txt"]),
        cover_prompt        = data["cover_prompt"],
        image_prompts       = scenes,
    )


# ══════════════════════════════════════════════════════════════════════════════
# GPT-4o POLISH
# ══════════════════════════════════════════════════════════════════════════════
@exponential_retry(max_attempts=3)
def polish_with_gpt4o(pack: ContentPack) -> ContentPack:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    prompt = (
        "以下是醫療健康影片的旁白 SRT。\n"
        "請用「百萬 YouTuber」語氣拋光：\n"
        "- 語氣生動有溫度、引發共鳴\n"
        "- 徹底移除 {UNIQUE_VALUE} 亂碼\n"
        "- 保持繁體中文，維持 SRT 格式（序號 + 時間碼 + 內容）\n"
        "- 只回傳修改後的 SRT，不要說明\n\n"
        f"旁白：\n{pack.draft_vo_srt}"
    )

    print("\n[GPT-4o] Polishing VO...")
    resp     = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2500, temperature=0.7,
    )
    polished = resp.choices[0].message.content.strip()
    polished = re.sub(r"\{[A-Z_]{2,}\}", "", polished)
    return pack.model_copy(update={"draft_vo_srt": polished})


# ══════════════════════════════════════════════════════════════════════════════
# SRT PARSER (for runbook alignment)
# ══════════════════════════════════════════════════════════════════════════════
def _parse_srt_segments(srt_text: str) -> List[dict]:
    """Parse SRT → [{index, text, t_in, t_out}]. Timecodes re-computed via algorithm."""
    segments = []
    current_time = 0.0
    for block in re.split(r"\n\s*\n", srt_text.strip()):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        text_lines = [l for l in lines
                      if not re.match(r"^\d+$", l) and "-->" not in l]
        text = " ".join(text_lines).strip()
        if not text:
            continue
        dur   = compute_srt_duration(text)
        t_in  = float_to_smpte(current_time)
        t_out = float_to_smpte(current_time + dur)
        segments.append({"text": text, "in": t_in, "out": t_out})
        current_time += dur + 0.1
    return segments


# ══════════════════════════════════════════════════════════════════════════════
# RUNBOOK BUILDER — Director-driven CH章節生成
# ══════════════════════════════════════════════════════════════════════════════
def build_runbook(pack: ContentPack) -> str:
    vo_segs      = _parse_srt_segments(pack.draft_vo_srt)
    sub_segs     = _parse_srt_segments(pack.draft_subtitles_srt)
    total_scenes = len(pack.image_prompts)

    # Total duration estimate
    total_sec = sum(compute_srt_duration(s["text"]) + 0.1 for s in vo_segs)
    total_tc  = float_to_smpte(total_sec)

    # Group scenes by chapter (story node), preserve insertion order
    ch_groups: OrderedDict[str, List[tuple]] = OrderedDict()
    for i, scene in enumerate(pack.image_prompts):
        ch_groups.setdefault(scene.chapter, []).append((i, scene))

    lines = [
        f"# {pack.topic} — 製作指南 (V35.6 Director Mode)",
        "",
        f"> 總時長估算：`{total_tc}` (SMPTE @{SMPTE_FPS}fps) | `0.3s + N×0.19s + 0.5s`",
        f"> 文字模型：`{TEXT_MODEL}` | 圖像比例：`{IMAGE_ASPECT_RATIO}` ({IMAGE_PIXEL_SIZE[0]}×{IMAGE_PIXEL_SIZE[1]}px fallback)",
        f"> 總章節數：**{len(ch_groups)}** | 總場景數：**{total_scenes}** (1:1 VO對齊)",
        "",
    ]

    for ch_num, (chapter, scenes_in_ch) in enumerate(ch_groups.items(), 1):
        lines += [f"## CH{ch_num} — {chapter}", ""]

        for scene_idx, scene in scenes_in_ch:
            vo_seg  = vo_segs[scene_idx]  if scene_idx < len(vo_segs)  else {"text": "", "in": "N/A", "out": "N/A"}
            sub_seg = sub_segs[scene_idx] if scene_idx < len(sub_segs) else {"text": ""}

            # ── Director decisions ─────────────────────────────────────────
            is_veo   = Director.needs_veo(vo_seg["text"], scene_idx, total_scenes)
            action   = "🎬 Veo Generation Required" if is_veo else Director.static_action()
            sfx      = Director.sfx_for_scene(
                vo_seg["text"], sub_seg["text"], scene_idx, total_scenes
            )
            metaphor = Director.extract_metaphor(vo_seg["text"])
            veo_cell = scene.veo_prompt if is_veo else f"— ({Director.static_action()})"

            lines += [
                f"### CH{ch_num} — Scene {scene_idx + 1} — `{scene.filename}`",
                "",
                "| 欄位 | 內容 |",
                "|------|------|",
                f"| **VO**       | {vo_seg['text']} |",
                f"| **字幕**     | {sub_seg['text']} |",
                f"| **隱喻**     | {metaphor if metaphor else '—'} |",
                f"| **Video**    | `{scene.filename}` |",
                f"| **Action**   | {action} |",
                f"| **🔊 SFX**   | {sfx} |",
                f"| **🎬 Veo**   | {veo_cell} |",
                f"| **時碼**     | `{vo_seg['in']} → {vo_seg['out']}` |",
                "",
            ]

        lines += ["---", ""]

    # ── Appendix ──────────────────────────────────────────────────────────────
    lines += [
        "## 完整旁白腳本", "", pack.draft_vo_srt, "",
        "---", "",
        "## 精簡字幕 (SMPTE)", "", pack.draft_subtitles_srt, "",
        "---", "",
        "## SEO 文案 (純文字)", "", pack.seo_txt, "",
        "---", "",
        "## 封面提示詞 (含繁中渲染)", "",
        f"```\n{apply_style_cover(pack.cover_prompt, title=pack.topic)}\n```", "",
        "---", "",
        "## 分鏡列表 (V35.6 風格注入 + 隱喻)", "",
    ]
    for i, scene in enumerate(pack.image_prompts):
        vo_text  = vo_segs[i]["text"] if i < len(vo_segs) else ""
        metaphor = Director.extract_metaphor(vo_text)
        is_veo   = Director.needs_veo(vo_text, i, total_scenes)
        lines += [
            f"### `{scene.filename}` — {scene.chapter}",
            "",
            f"> 隱喻: {metaphor if metaphor else '—'} | Veo: {'✅ Required' if is_veo else '⬜ Static'}",
            "",
            f"```\n{apply_style_scene(scene.prompt)}\n```",
            "",
            f"**Veo prompt:** {scene.veo_prompt if is_veo else Director.static_action()}",
            "",
        ]

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# IMAGE GENERATION
# ══════════════════════════════════════════════════════════════════════════════
def _nano_generate(prompt: str, label: str, allow_text: bool = False,
                   title: str = "") -> bytes:
    """
    V35.6.2: Official-matched implementation.
    Mirrors official_core/src/services/gemini.ts generateImage():
      generate_content() + config={"image_config": {"aspect_ratio": "9:16"}}
    No generate_images(), no types.ImageConfig (not in SDK 1.2.0).
    """
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    styled = apply_style_cover(prompt, title=title) if allow_text else apply_style_scene(prompt)

    title_tag = f"  title: [{title}]" if title else ""
    payload = {
        "model": NANO_BANANA,
        "method": "generate_content",
        "config": {"image_config": {"aspect_ratio": IMAGE_ASPECT_RATIO}},
        "prompt_chars": len(styled),
        "label": label,
        "allow_text": allow_text,
        "title": title or None,
    }
    print(
        f"\n  [MODEL] {NANO_BANANA}  (official: generate_content + imageConfig)\n"
        f"  label       : {label}\n"
        f"  aspect_ratio: {IMAGE_ASPECT_RATIO}  (image_config -- official spec)\n"
        f"  allow_text  : {allow_text}{title_tag}\n"
        f"  styled_len  : {len(styled)} chars\n"
        f"  payload     : {payload}"
    )

    # Official-matched: generate_content with imageConfig (raw dict bypasses Pydantic limits)
    resp = client.models.generate_content(
        model=NANO_BANANA,
        contents=styled,
        config={"image_config": {"aspect_ratio": IMAGE_ASPECT_RATIO}},
    )
    for part in resp.candidates[0].content.parts:
        if hasattr(part, "inline_data") and part.inline_data:
            data = part.inline_data.data
            img_bytes = base64.b64decode(data) if isinstance(data, str) else data
            print(f"  [generate_content OK] {label}  ({len(img_bytes):,} bytes)")
            return img_bytes
    raise RuntimeError(f"No image data from {NANO_BANANA} for: {label}")


def _dalle3_generate(prompt: str, label: str, allow_text: bool = False,
                     title: str = "") -> bytes:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    styled = apply_style_cover(prompt, title=title) if allow_text else apply_style_scene(prompt)
    print(f"  [MODEL: {DALLE_MODEL} fallback] {label}")
    resp   = client.images.generate(
        model=DALLE_MODEL, prompt=styled[:1000],
        n=1, size="1024x1792", response_format="b64_json",
    )
    return base64.b64decode(resp.data[0].b64_json)


@exponential_retry(max_attempts=3, base_delay=4.0)
def _nano_with_fallback(prompt: str, label: str, allow_text: bool = False,
                        title: str = "") -> bytes:
    try:
        return _nano_generate(prompt, label, allow_text=allow_text, title=title)
    except Exception as e:
        if any(k in str(e).lower() for k in ("429", "quota", "resource_exhausted")):
            print(f"  [429 detected] Falling back to {DALLE_MODEL}: {label}")
            return _dalle3_generate(prompt, label, allow_text=allow_text, title=title)
        raise


@exponential_retry(max_attempts=3, base_delay=3.0)
def _flux_generate(prompt: str, label: str) -> bytes:
    import replicate
    styled = apply_style_flux_scene(prompt)   # V35.6.3: double-barrier Flux style
    print(
        f"\n  [MODEL] {FLUX_MODEL}\n"
        f"  label       : {label}\n"
        f"  aspect_ratio: {IMAGE_ASPECT_RATIO}\n"
        f"  no_text     : prefix at absolute front\n"
        f"  styled_len  : {len(styled)} chars"
    )
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)
    # Primary: aspect_ratio; fallback pixel dims if aspect_ratio rejected
    try:
        output = client.run(
            FLUX_MODEL,
            input={"prompt": styled, "aspect_ratio": IMAGE_ASPECT_RATIO,
                   "output_format": "png", "num_outputs": 1},
        )
    except Exception as e:
        if "aspect_ratio" in str(e).lower():
            w, h = IMAGE_PIXEL_SIZE
            print(f"  [aspect_ratio fallback] using {w}x{h}")
            output = client.run(
                FLUX_MODEL,
                input={"prompt": styled, "width": w, "height": h,
                       "output_format": "png", "num_outputs": 1},
            )
        else:
            raise
    r = requests.get(str(output[0]), timeout=60)
    r.raise_for_status()
    return r.content


def generate_images(pack: ContentPack, out_dir: Path) -> dict:
    saved        = {}
    non_cover_ct = 0

    # ── Cover ─────────────────────────────────────────────────────────────────
    # Cover ONLY: allow_text=True + topic title injected for Chinese calligraphy
    print(f"\n{'=' * 60}")
    print(f"  COVER — MODEL: {NANO_BANANA} | aspect_ratio={IMAGE_ASPECT_RATIO}")
    print(f"  Chinese title: 『{pack.topic}』 | allow_text=True")
    styled_cover = apply_style_cover(pack.cover_prompt, title=pack.topic)
    print(f"  Styled prompt preview: {styled_cover[:120]}...")
    print("=" * 60)
    cover_path = out_dir / "cover.png"
    cover_bytes = _nano_with_fallback(pack.cover_prompt, "cover", allow_text=True, title=pack.topic)
    cover_path.write_bytes(cover_bytes)
    saved["cover"] = cover_path
    try:
        from PIL import Image as _PILImage
        import io as _io
        _img = _PILImage.open(_io.BytesIO(cover_bytes))
        print(f"  Saved: cover.png  [{_img.width}x{_img.height} px  ratio={_img.width}/{_img.height}={_img.width/_img.height:.3f}]")
    except Exception:
        print(f"  Saved: cover.png")

    # ── Scenes ────────────────────────────────────────────────────────────────
    # scene_001 → Nano Banana 2 (no-text at front)
    # scene_002+ → Flux-schnell (no-text at front)
    for i, scene in enumerate(pack.image_prompts):
        label = f"{scene.chapter} / {scene.filename}"

        if i == 0:
            # scene_001: Nano Banana 2, no Chinese text (cover-only rule)
            styled_s1 = apply_style_scene(scene.prompt)
            print("\n" + "=" * 60)
            print("  scene_001 — FULL RENDERING PARAMS")
            print("=" * 60)
            print(json.dumps({
                "model":         NANO_BANANA,
                "chapter":       scene.chapter,
                "filename":      scene.filename,
                "no_text_prefix": _NO_TEXT_PREFIX,
                "base_prompt":   scene.prompt,
                "styled_prompt": styled_s1,
                "allow_text":    False,
                "veo_prompt":    scene.veo_prompt,
                "aspect_ratio":  IMAGE_ASPECT_RATIO,
                "pixel_fallback": f"{IMAGE_PIXEL_SIZE[0]}x{IMAGE_PIXEL_SIZE[1]}",
                "smpte_fps":     SMPTE_FPS,
                "modalities":    ["IMAGE"],
            }, ensure_ascii=False, indent=2))
            if len(pack.image_prompts) > 1:
                s2        = pack.image_prompts[1]
                styled_s2 = apply_style_scene(s2.prompt)
                print("\n  scene_002 — FULL RENDERING PARAMS")
                print("=" * 60)
                print(json.dumps({
                    "model":         FLUX_MODEL,
                    "chapter":       s2.chapter,
                    "filename":      s2.filename,
                    "no_text_prefix": _NO_TEXT_PREFIX,
                    "base_prompt":   s2.prompt,
                    "styled_prompt": styled_s2,
                    "veo_prompt":    s2.veo_prompt,
                    "aspect_ratio":  IMAGE_ASPECT_RATIO,
                    "pixel_fallback": f"{IMAGE_PIXEL_SIZE[0]}x{IMAGE_PIXEL_SIZE[1]}",
                }, ensure_ascii=False, indent=2))
            print("=" * 60)
            img_data = _nano_with_fallback(scene.prompt, label, allow_text=False)
        else:
            img_data = _flux_generate(scene.prompt, label)

        img_path = out_dir / scene.filename
        img_path.write_bytes(img_data)
        saved[scene.filename] = img_path
        try:
            from PIL import Image as _PILImage
            import io as _io
            _img = _PILImage.open(_io.BytesIO(img_data))
            print(f"  Saved: {scene.filename}  [{_img.width}x{_img.height} px  ratio={_img.width}/{_img.height:.3f}]")
        except Exception:
            print(f"  Saved: {scene.filename}")

        non_cover_ct += 1
        if non_cover_ct % 5 == 0 and i < len(pack.image_prompts) - 1:
            print(f"\n  [5/120] {non_cover_ct} images — mandatory cooldown")
            countdown(120, "API cooldown")

    return saved


# ══════════════════════════════════════════════════════════════════════════════
# SAVE TO DISK
# ══════════════════════════════════════════════════════════════════════════════
def save_to_disk(pack: ContentPack, saved_images: dict, out_dir: Path) -> Path:
    (out_dir / "draft_vo.srt").write_text(pack.draft_vo_srt,        encoding="utf-8")
    (out_dir / "subtitles.srt").write_text(pack.draft_subtitles_srt, encoding="utf-8")
    (out_dir / "seo.txt").write_text(pack.seo_txt,                   encoding="utf-8")
    (out_dir / "runbook.md").write_text(pack.runbook_all_in_one,     encoding="utf-8")

    manifest = {
        "version":      "V35.6",
        "topic":        pack.topic,
        "generated":    datetime.now().isoformat(),
        "text_model":   TEXT_MODEL,
        "ssot_model":   SSOT_MODEL,
        "image_config": {"aspect_ratio": IMAGE_ASPECT_RATIO, "size": IMAGE_SIZE},
        "files": {
            "draft_vo_srt":   "draft_vo.srt",
            "subtitles_srt":  "subtitles.srt",
            "seo_txt":        "seo.txt",
            "runbook_md":     "runbook.md",
            "cover":          "cover.png",
            "scenes":         [s.filename for s in pack.image_prompts],
        },
        "image_prompts": [s.model_dump() for s in pack.image_prompts],
    }
    manifest_path = out_dir / "final_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[SAVE] {out_dir}")
    for f in sorted(out_dir.iterdir()):
        print(f"  {f.name:35s} {f.stat().st_size:>10,} bytes")
    return manifest_path


# ══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════════════
def run_factory(topic: str, ssot_path: Optional[str] = None) -> Path:
    slug    = re.sub(r"[^\w]", "_", topic)
    out_dir = Path("outputs") / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    Director.initialize()

    print(f"\n{'=' * 60}")
    print(f"  V35.6 Factory — Topic: {topic}")
    print(f"  Output dir: {out_dir}")
    print(f"{'=' * 60}")

    # Phase 1: SSOT (optional)
    ssot_facts = ""
    if ssot_path:
        ssot_facts = extract_ssot_facts(
            Path(ssot_path).read_text(encoding="utf-8"), topic
        )

    # Phase 2: ContentPack
    print(f"\n[PHASE 2] Rendering ContentPack via {TEXT_MODEL}...")
    pack = generate_content_pack(topic, ssot_facts)
    print(f"  scenes: {len(pack.image_prompts)}  VO segments: {pack.draft_vo_srt.count(chr(10)+'-->') + 1}")

    # GPT-4o polish
    pack = polish_with_gpt4o(pack)
    print("  VO polished.")

    # Runbook
    print("\n[RUNBOOK] Building CH-grouped Markdown guide...")
    runbook = build_runbook(pack)
    pack    = pack.model_copy(update={"runbook_all_in_one": runbook})
    print(f"  Runbook: {len(runbook):,} chars")

    # Images
    saved = generate_images(pack, out_dir)

    # Persist
    manifest = save_to_disk(pack, saved, out_dir)

    print(f"\n{'=' * 60}")
    print(f"  V35.6 COMPLETE — {manifest}")
    print(f"{'=' * 60}\n")
    return manifest


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V35.3 Audio-Visual Factory")
    parser.add_argument("topic",  nargs="?", default="夜間頻尿")
    parser.add_argument("--ssot", default=None, help="SSOT text file from NotebookLM")
    args = parser.parse_args()
    run_factory(args.topic, ssot_path=args.ssot)
