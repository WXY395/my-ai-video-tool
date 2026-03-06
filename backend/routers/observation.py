# -*- coding: utf-8 -*-
"""
觀測單元 API 路由（升級版）
支援 Shorts + 長片模式，含成本預估
"""
import json as _json
import logging
import random
import re
from fastapi import APIRouter, HTTPException, status
from datetime import datetime
from sse_starlette.sse import EventSourceResponse

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


# ── Cover quality thresholds ──────────────────────────────────────────────────
COVER_MIN_BRIGHTNESS = 45   # avg luminance 0-255; below → too dark
COVER_MIN_VARIANCE   = 300  # pixel variance; below → no visible subject (flat/obscured)

# ── KF001 anchor extraction ───────────────────────────────────────────────────
# Regex matching style / lighting / format / quality segments to skip.
# Subject noun segments (e.g. "Egyptian pyramids", "dragonfly wing") pass through.
_ANCHOR_SKIP_RE = re.compile(
    r'\b('
    r'chiaroscuro|dramatic|moody|low[- ]key|dark\s+atmosphere|dark\s+shadow|'
    r'deep\s+shadow|silhouette|noir|underexposed|cinematic|'
    r'professional\s+photography|high\s+quality|sharp\s+focus|'
    r'vibrant\s+colou?r|bokeh|depth.of.field|wide.angle|'
    r'portrait\s+format|vertical\s+composition|landscape\s+format|'
    r'horizontal\s+dynamics|no\s+people|no\s+hands|'
    r'no\s+text|no\s+watermark|no\s+logo|watermark|signature|'
    r'\d+:\d+\s+format|\d+:\d+\s+aspect|portrait\s+vertical|'
    r'landscape\s+horizontal|widescreen|orientation|rim\s+light|'
    r'key\s+light|macro\s+close.up|focal\s+point|thumbnail|'
    r'aspect\s+ratio|output\s+format|output\s+quality|'
    r'well.exposed|readable\s+silhouette|clear\s+focal'
    r')\b',
    re.IGNORECASE,
)

# Segments starting with an ACTION VERB (not a noun/adjective) are NOT subject-noun
# phrases — skip them.  We use an EXPLICIT list rather than a broad -ing regex to
# avoid false-positives on legitimate subjects like "Lightning bolt", "Spring flower",
# "Morning dew", "Leaning Tower of Pisa" etc.
_FILLER_START_RE = re.compile(
    r'^\s*('
    # descriptive action verbs that reference the subject without naming it
    r'emphasizing|showing|revealing|displaying|featuring|highlighting|'
    r'depicting|capturing|suggesting|creating|evoking|presenting|'
    r'demonstrating|illustrating|portraying|exposing|examining|'
    r'exploring|focusing|zooming|magnifying|rendering|representing|'
    r'positioned|located|placed|surrounded|covered|filled|'
    # prepositions / pronouns that open a description, not a noun phrase
    r'against|above|below|within|through|across|around|between|beside|'
    r'behind|upon|over|under|from|into|'
    # pronoun starters — subject was named implicitly, not explicitly
    r'its|their|this|that|'
    # generic compositional labels that are NOT the subject
    r'subject|background|style|color|colour|with'
    r')\b',
    re.IGNORECASE,
)


def _extract_cover_anchor(kf001_prompt: str) -> str:
    """
    Extract the subject-noun anchor from a KF001 image_prompt string.

    - Skips segments containing style/lighting/format/quality terms
    - Skips segments starting with explicit action verbs, prepositions, or
      pronouns (they describe the subject without naming it)
    - Sorts remaining candidates by word count ascending — shortest is most
      likely a pure noun phrase (e.g. "Great Pyramid of Giza" = 4 words)
    - Returns the shortest valid candidate, or '' if none found
    """
    candidates: list[tuple[int, str]] = []   # (word_count, segment)

    for seg in kf001_prompt.split(','):
        seg = seg.strip()
        if not seg or len(seg) < 4:
            continue
        if _ANCHOR_SKIP_RE.search(seg):
            continue
        if _FILLER_START_RE.search(seg):
            continue
        candidates.append((len(seg.split()), seg))

    if not candidates:
        return ''

    # Prefer the shortest segment — most likely to be the subject noun phrase
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


# ── Topic subject extraction ──────────────────────────────────────────────────
# Matches style / format / quality / motion descriptors to skip when extracting
# the core paintable noun phrase from an anchor or topic string.
_SUBJECT_SKIP_RE = re.compile(
    r'\b('
    r'extreme|macro|close[- ]up|medium\s+shot|medium|wide[- ]angle|establishing|'
    r'cinematic|dramatic|documentary|professional|scientific|'
    r'high\s+quality|sharp\s+focus|razor[- ]sharp|ultra\s*hd|'
    r'vibrant|bokeh|depth.of.field|portrait|vertical|landscape|'
    r'horizontal|widescreen|format|aspect|ratio|orientation|'
    r'thumbnail|photography|photograph|photo|style|'
    r'lighting|shadow|dark|bright|colou?r|quality|'
    r'shot|view|angle|composition|framing|focus|detail|reveal|'
    r'slow|fast|motion|camera|pan|push|pull|zoom|'
    r'no\s+\w+|high[- ]speed|ultra[- ]slow'
    r')\b',
    re.IGNORECASE,
)

# English stop words (articles / prepositions / conjunctions) to strip from subject
_STOP_WORDS: frozenset[str] = frozenset({
    'a', 'an', 'the', 'of', 'in', 'at', 'on', 'by', 'for', 'with',
    'to', 'from', 'as', 'and', 'or', 'that', 'this', 'these', 'those',
    'is', 'are', 'was', 'were', 'into', 'upon', 'its', 'their',
})

# CJK Unicode ranges (to detect Chinese / Japanese / Korean characters)
_CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]')

# ── Prohibited-subject guard ───────────────────────────────────────────────────
# If extracted subject contains any of these human / biological terms, or the
# original topic mentions birth / origin / Bell, replace with a safe industrial
# fallback so no human anatomy ever reaches the cover prompt.
PROHIBITED_SUBJECTS: frozenset[str] = frozenset({
    'face', 'faces', 'eye', 'eyes', 'skin', 'infant', 'baby',
    'person', 'man', 'woman', 'body',
})

# ── V31.5 Hard-Coded Subject Re-mapping firewall ──────────────────────────────
# BANNED_BIOLOGICAL_TERMS: physical firewall list checked at the TOP of
# _extract_topic_subject. Any extracted subject containing these words is
# discarded and force-remapped to an industrial / mineral noun phrase.
BANNED_BIOLOGICAL_TERMS: frozenset[str] = frozenset({
    'face', 'faces', 'skin', 'person', 'human', 'eye', 'eyes',
    'man', 'woman', 'body', 'infant', 'baby',
})
_BIO_FALLBACKS: tuple[str, str] = (
    "anatomical cross-section diagram",   # V33.9: medical fallback replaces industrial
    "clinical specimen illustration",
)
# Time / soul / spiritual topics → luminous glass fragments (checked before
# ABSTRACT_TOPIC_MAP so CJK spiritual phrases are also caught).
_TIME_SOUL_RE = re.compile(
    r'\b(time|soul|spirit|essence|eternity|infinity|mind|emotion|feeling|'
    r'consciousness|existence|void|energy|light|love|beauty|truth|'
    r'時間|靈魂|精神|存在|意識|永恆|愛|宇宙)\b',
    re.IGNORECASE,
)
# All firewall replacement strings — used by _build_cover_prompt_v2 to detect
# when portrait-style lighting / photography terms must be stripped.
_FIREWALL_SUBJECTS: frozenset[str] = frozenset({
    "intricate metallic components",
    "weathered stone texture",
    "luminous glass fragments",
    "identifiable historical artifact",
    "1876 patent manuscript",
    "identifiable close-up subject",
})

# ── Abstract → Physical mapping (checked BEFORE all other logic) ──────────────
# When topic is an abstract concept, religion, or ideology, force-replace it with
# a concrete, paintable noun phrase so FLUX produces a real object, not a vague blob.
ABSTRACT_TOPIC_MAP: list[tuple[re.Pattern, str]] = [
    # Islam / mosque / Arabic geometric art
    (re.compile(
        r'\b(伊斯蘭|islam|muslim|mosque|quran|arabic|arab|koran|mecca|hijab)\b',
        re.IGNORECASE),
     "geometric arabesque pattern, blue mosque tile"),
    # Buddhism / lotus / dharma
    (re.compile(
        r'\b(佛教|buddhism|buddhist|buddha|dharma|nirvana|lotus|sutra|禪|zen|寺廟|temple)\b',
        re.IGNORECASE),
     "sandalwood texture, bronze lotus statue"),
    # Generic abstract concepts (philosophy, consciousness, soul, theory…)
    (re.compile(
        r'\b(abstract|概念|理論|抽象|意識|靈魂|精神|哲學|consciousness|spirit|soul|'
        r'philosophy|ideology|ethics|metaphysics|existence|infinity|freedom|justice)\b',
        re.IGNORECASE),
     "abstract geometric crystal structure"),
]

# Topics that invoke the Bell / birth / origin narrative → period-accurate fallback
_PROHIBITED_TOPICS_RE = re.compile(r'誕生|起源|貝爾', re.IGNORECASE)


# ── V30.0 Dynamic Domain Translator ─────────────────────────────────────────
# Global avoidance blacklist — appended to ALL cover prompts (every style/mode).
# Mandatory per V30.0 spec: includes fingers, skin, flesh-colored tissue.
_GLOBAL_AVOID = (
    "sharp identifiable subject fills frame, "
    "avoid abstract bokeh, avoid random organic shapes, "
    "avoid unrelated flowers or foliage, avoid generic textures, "
    "avoid skin-like gloss, avoid fleshy shapes, avoid organic tissue, "
    "avoid biological bulbs, avoid fingerprints, avoid amorphous blobs, "
    "avoid fingers, avoid fingertips, avoid fingernails, "
    "avoid skin tone, avoid skin texture, avoid flesh-colored surfaces, "
    "avoid human tissue, avoid organic flesh"
)

# Domain-specific material style descriptors (appended to subject noun phrase)
_PROXY_STYLE        = "Bronze relief sculpture, engraved sketch on aged parchment, warm sepia ink wash"
_TEXTURE_STYLE      = "micro fiber cross-section, geometric macro structure, botanical specimen plate"
_HARD_SURFACE_STYLE = "machined metallic surface, technical blueprint precision, industrial engineering detail"

# Domain → material style descriptor
_DOMAIN_STYLE: dict[str, str] = {
    "human":   _PROXY_STYLE,
    "biology": _TEXTURE_STYLE,
    "physics": _HARD_SURFACE_STYLE,
}

# Birth / origin concept → domain-specific visual translation
# Examples: Human Birth → Bronze relief; Plant Birth → seed coat macro; Star Birth → nebula crystal
_BIRTH_DOMAIN_TRANSLATION: dict[str, str] = {
    "human":   "Bronze relief of birth allegory on aged parchment",
    "biology": "Macro view of seed coat cracking with mechanical tension",
    "physics": "Nebula plasma textures in crystalline lattice structure",
    "":        "Ancient diagram of origin formation event",
}

_BIRTH_KEYWORD_RE = re.compile(
    r'\b(birth|誕生|origin|起源|formation|創生|beginning|genesis|誕|born)\b',
    re.IGNORECASE,
)

# Domain classifier patterns (checked in order — first match wins)
_DOMAIN_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Human / Biography
    (re.compile(
        r'\b(人物|傳記|biography|inventor|scientist|historical figure|portrait|'
        r'bell|tesla|einstein|newton|darwin|galileo|人類|human|生平|肖像)\b',
        re.IGNORECASE), "human"),
    # Biology / Nature
    (re.compile(
        r'\b(生物|自然|biology|nature|plant|animal|insect|species|organism|'
        r'cell|蜻蜓|dragonfly|butterfly|moss|fungus|spore|seed|leaf|root|'
        r'pollen|bacteria|virus|flora|fauna|marine|flower|bird|fish|tree|'
        r'coral|algae|botany|zoology|ecology)\b',
        re.IGNORECASE), "biology"),
    # Physics / Mechanics / Astronomy
    (re.compile(
        r'\b(物理|機械|physics|mechanical|engine|gear|circuit|electron|'
        r'quantum|atom|molecule|crystal|metal|steel|alloy|turbine|'
        r'mechanism|machine|力學|電路|工程|engineering|optics|wave|'
        r'nuclear|particle|satellite|star|stellar|nebula|galaxy|cosmos|'
        r'solar|supernova|plasma|黑洞|星雲|恆星|宇宙)\b',
        re.IGNORECASE), "physics"),
]


def _classify_domain(topic: str, anchor: str = "") -> str:
    """
    Classify topic + anchor into: 'human' | 'biology' | 'physics' | ''.
    First matching pattern wins. Returns '' if no domain matched.
    """
    combined = f"{topic} {anchor}"
    for pattern, domain in _DOMAIN_PATTERNS:
        if pattern.search(combined):
            return domain
    return ""


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _extract_topic_subject(text: str) -> str:
    """
    Extract a paintable noun phrase (1–6 words) to anchor the cover prompt.

    - Short CJK input (≤20 chars, no ASCII space): returns '' (caller uses
      safe English fallback — never put CJK into a FLUX prompt).
    - English / mixed: take first comma-segment, strip style / format /
      quality / motion / stop words, return up to 6 remaining words.
    - Prohibited-subject guard: if result contains human/biological terms, or
      topic mentions birth/origin/Bell, returns a safe industrial fallback.

    Examples:
      "Medium establishing shot of dragonfly wing, ..." → "dragonfly wing"
      "aspirin tablet, extreme close-up, scientific"    → "aspirin tablet"
      "蜻蜓翅膀"                                        → "" (CJK → fallback)
      "貝爾誕生"                                        → "1876 patent manuscript"
      "face close-up"                                   → "intricate metallic components" | "weathered stone texture"
      "human eye detail"                                → "intricate metallic components" | "weathered stone texture"
      "consciousness"                                   → "luminous glass fragments"  (V31.5 firewall, before ABSTRACT_MAP)
      "時間"                                            → "luminous glass fragments"
      "靈魂"                                            → "luminous glass fragments"
      "伊斯蘭"                                          → "geometric arabesque pattern, blue mosque tile"
      "佛教"                                            → "sandalwood texture, bronze lotus statue"
    """
    stripped = text.strip()

    # ── V31.5 Hard-coded subject firewall — runs before ALL other logic ───────
    # Time / soul / spirit / abstract input → force luminous glass fragments.
    if _TIME_SOUL_RE.search(stripped):
        return "luminous glass fragments"

    # ── Abstract → Physical forced mapping (highest priority) ────────────────
    # Check before CJK guard so Chinese abstract topics are also translated.
    for pattern, concrete_noun in ABSTRACT_TOPIC_MAP:
        if pattern.search(stripped):
            return concrete_noun

    # CJK-only phrase — return empty so caller can use a safe English fallback
    if _has_cjk(stripped):
        # Even for CJK input, check if topic triggers the prohibited-topics guard
        if _PROHIBITED_TOPICS_RE.search(stripped):
            return "1876 patent manuscript"
        return ''

    # Use first comma-segment as primary candidate
    first_seg = stripped.split(',')[0].strip()
    words = first_seg.split()

    # Filter: skip style/format words AND stop words
    kept: list[str] = []
    for word in words:
        w_lower = word.lower().rstrip('.,;:')
        if w_lower in _STOP_WORDS:
            continue
        if _SUBJECT_SKIP_RE.search(word):
            continue
        kept.append(word)
        if len(kept) >= 6:
            break

    result = ' '.join(kept) if kept else ''

    # ── Prohibited-topic guard (Bell / birth / origin) ────────────────────────
    if _PROHIBITED_TOPICS_RE.search(text):
        return "1876 patent manuscript"

    # ── BANNED_BIOLOGICAL_TERMS firewall ──────────────────────────────────────
    # Hard-coded re-mapping: bio terms → metallic/stone (not generic "artifact").
    # Deterministic alternation via topic hash ensures visual variety.
    result_words = {w.lower().rstrip('.,;:') for w in result.split()}
    if result_words & BANNED_BIOLOGICAL_TERMS:
        return _BIO_FALLBACKS[hash(text) % 2]

    return result


# ── Cover style selection ─────────────────────────────────────────────────────
# hook_technique → cover style mapping
#   visual_paradox      → paradox  (impossible visual is the whole point)
#   forbidden_knowledge → evidence (hidden-record / file-card aesthetic)
#   reverse_question    → closeup  (reveals the overlooked detail)
#   shock_fact          → closeup  (macro reveal of the shocking fact)
#   incomplete_loop     → closeup  (partial crop matches the "incomplete" hook)
#   None / unknown      → closeup  (universally safe default)
_HOOK_TO_STYLE: dict[str, str] = {
    "visual_paradox":      "paradox",
    "forbidden_knowledge": "evidence",
}

# If primary style fails quality check, try styles in this order
_STYLE_FALLBACK: dict[str, list[str]] = {
    "closeup":  ["evidence", "paradox"],
    "evidence": ["closeup",  "paradox"],
    "paradox":  ["closeup",  "evidence"],
}


def _select_cover_style(hook_technique: str | None) -> str:
    """
    Select the most appropriate cover style based on the hook_technique
    chosen by the AI for this topic's 定位幕.

    Falls back to 'closeup' for any unknown or missing technique.
    """
    return _HOOK_TO_STYLE.get(hook_technique or "", "closeup")


def _build_cover_hooks(units: list, topic: str) -> dict:
    """
    從首個 unit 推導封面文字疊層建議（主標 + 副標，繁中 / 英各一）。
    純文字建議，不寫入圖片，由剪輯師在 CapCut 手動疊加。
    """
    if not units:
        return {}

    hook_unit = units[0]
    # ZH 主標題：subtitle_zh 已是最精煉的 hook（≤12字取前8）
    title_zh = (getattr(hook_unit, 'subtitle_zh', '') or '').strip()[:8] or topic[:6]

    # ZH 副標題：voice_over_zh 首子句（標點前，≤12字）
    vo = getattr(hook_unit, 'voice_over_zh', '') or ''
    sub_zh_parts = re.split(r'[，。！？]', vo)
    subtitle_zh = sub_zh_parts[0][:12].strip() if sub_zh_parts else ''
    if not subtitle_zh:
        subtitle_zh = (getattr(hook_unit, 'phenomenon', '') or '')[:8]

    # EN 主標題：hook_technique → 對應英文 hook 句
    HOOK_EN_MAP = {
        'reverse_question':    "You Never Knew This",
        'shock_fact':          "The Shocking Truth",
        'forbidden_knowledge': "What They Don't Tell You",
        'visual_paradox':      "See What's Really There",
        'incomplete_loop':     "The Secret Revealed",
    }
    technique = getattr(hook_unit, 'hook_technique', '') or ''
    title_en = HOOK_EN_MAP.get(technique, "You Won't Believe This")

    # EN 副標題：固定短句（簡單易讀）
    subtitle_en = "Discover what's inside"

    return {
        'title_zh':    title_zh,
        'title_en':    title_en,
        'subtitle_zh': subtitle_zh,
        'subtitle_en': subtitle_en,
    }


# ── 三種封面風格 ──────────────────────────────────────────────────────────────
# closeup  : 主體特寫（40-60% 構圖，局部陰影製造神祕，不整張變黑）
# evidence : 證物檔案（博物館/檔案卡主視覺，紅圈/印章圖形，乾淨留白）
# paradox  : 對比悖論（同主體加入不合理對比，邊光打亮主體，背景可暗但主體不黑糊）
COVER_STYLES: list[str] = ["closeup", "evidence", "paradox"]

# 統一 negative：所有風格都要禁止的基礎項目
_COVER_BASE_NEG = (
    "text, letters, numbers, words, writing, handwriting, printed text, "
    "watermark, logo, signature, "
    "people, person, human, face, hands, body parts, "
    "blurry, low quality, low resolution, jpeg artifacts"
)


def _build_cover_prompt_v2(
    topic: str,
    aspect_ratio: str,
    style: str,
    kf001_anchor: str | None = None,
    salt_id: str | None = None,
) -> tuple[str, str]:
    """
    三風格封面 prompt 產生器（FLUX 架構最佳化）。

    ⚠️ FLUX 模型不支援 negative_prompt — 所有品質/亮度控制必須用正面描述。
    核心策略：不說「禁止暗」，直接說「要亮」、「要高調打光」、「要鮮豔」。
    去除 "mystery" / "cinematic" / "shadow" 等在訓練資料中對應暗調的詞。

    style = "closeup"  → 主體特寫：高調打光，40-60% 構圖，主體鮮明
    style = "evidence" → 證物檔案：暖色系紙卡，紅圈圖形，乾淨留白
    style = "paradox"  → 對比悖論：強打光主體，悖論元素，戲劇性對比
    """
    orientation = (
        'portrait vertical orientation'
        if aspect_ratio == '9:16'
        else 'landscape horizontal widescreen orientation'
    )
    # Priority: kf001_anchor (English noun from KF001 prompt) > topic
    # kf001_anchor is '' when extraction failed — fall through to topic
    subject_desc  = kf001_anchor if kf001_anchor else topic
    topic_subject = _extract_topic_subject(subject_desc)

    # If both failed (e.g. Chinese topic + bad anchor), try topic alone
    if not topic_subject and kf001_anchor:
        topic_subject = _extract_topic_subject(topic)

    topic_subject = topic_subject or "identifiable close-up subject"

    # ── Hard override: original topic triggers Bell/birth/origin guard ─────────
    # _extract_topic_subject only sees the English anchor text; the CJK topic
    # itself must also be checked so "貝爾誕生" always maps to the period fallback.
    _prohibited_override = bool(_PROHIBITED_TOPICS_RE.search(topic))
    if _prohibited_override:
        topic_subject = "1876 patent manuscript"

    # ── V30.0: Dynamic Domain Translator ─────────────────────────────────────
    # Classify domain from topic + anchor, then apply domain-specific material
    # translation. Skipped when the prohibited-override already locked in a subject.
    if not _prohibited_override:
        domain = _classify_domain(topic, kf001_anchor or "")
        combined_text = f"{topic} {kf001_anchor or ''}"
        if _BIRTH_KEYWORD_RE.search(combined_text):
            # Birth / origin concept → domain-specific visual metaphor
            topic_subject = _BIRTH_DOMAIN_TRANSLATION.get(domain, _BIRTH_DOMAIN_TRANSLATION[""])
        elif domain:
            # Non-birth domain → append domain material style descriptor
            topic_subject = f"{topic_subject}, {_DOMAIN_STYLE[domain]}"
        logger.debug(f"🌐 domain={domain!r}  topic_subject={topic_subject!r}")

    # ── V30.0 Global avoidance blacklist (fingers / skin / flesh) ────────────
    # _GLOBAL_AVOID is the module-level constant; aliased here for prompt clarity.
    _AVOID = _GLOBAL_AVOID

    # ── V33.9 Medical brand DNA: randomised clinical detail per render ────────
    _MEDICAL_DETAIL_POOL = [
        "film grain overlay on archival cream paper",
        "aged medical chart texture, foxed paper edges",
        "painterly ink wash anatomical diagram style",
        "clinical teal highlight on deep midnight blue background",
        "soft lavender vasopressin molecule glow accent",
    ]
    _brand_detail = random.choice(_MEDICAL_DETAIL_POOL)

    if style == "closeup":
        # V33.9 主體特寫：醫學插圖局部，約 1/2 構圖，邊緣出框，臨床存檔打光
        prompt = (
            f"{topic_subject}, "
            f"medical illustration close-up, partial crop — upper half of subject fills frame, "
            f"lower edge exits frame cleanly, sharp anatomical details clearly visible, "
            f"diffused clinical examination light, clean clinical background, "
            f"vivid saturated colors on subject, anatomical diagram clearly rendered, "
            f"archival scan documentation, {_brand_detail}, {_AVOID}, "
            f"{aspect_ratio} format, {orientation}"
        )

    elif style == "evidence":
        # V33.9 證物檔案：醫學標本卡，局部 1/2 出框，乾淨打光留白
        prompt = (
            f"{topic_subject} as labeled medical specimen on clinical evidence card, "
            f"partial crop — left half of subject clearly visible and fully lit, "
            f"right edge exits card frame cleanly, vivid natural colors on visible portion, "
            f"bold clinical teal circle outline graphic partially framing visible area, "
            f"archival cream card background, generous open whitespace on right, "
            f"bright even diffused light, archival scan documentation, {_brand_detail}, {_AVOID}, "
            f"{aspect_ratio} format, {orientation}"
        )

    else:  # paradox
        # V33.9 對比悖論：醫學視覺，局部 1/2 出框，臨床打光，悖論元素形成對比
        prompt = (
            f"{topic_subject} at diagnostic scale, "
            f"partial crop — left half of subject brightly lit and fully identifiable, "
            f"right edge exits frame cleanly with anatomical surface details visible, "
            f"diffused archival key light illuminating visible left portion, vivid saturated subject colors, "
            f"right side: stark contrasting clinical element for paradox effect, "
            f"anatomical diagram composition, diffused clinical examination light on subject, "
            f"{_brand_detail}, {_AVOID}, "
            f"{aspect_ratio} format, {orientation}"
        )

    # ── Salt + timestamp prefix: bust Replicate cache ─────────────────────────
    # Prepend at the START so Replicate treats this as a unique prompt every time.
    # Appending at the end was insufficient — leading tokens have stronger cache weight.
    if salt_id:
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        prompt = f"ts:{ts}_{salt_id}, {prompt}"

    # negative 對 FLUX 無效（API 靜默忽略），保留供未來切換模型用
    negative = "text, letters, numbers, watermark, logo, people, hands, blurry, low quality"
    return prompt, negative


async def _check_cover_quality(url: str) -> tuple[float, float] | None:
    """
    Fetch the generated cover and compute (avg_brightness, pixel_variance)
    on a 64×64 grayscale downsample.

    avg_brightness : 0-255 mean luminance (low → too dark)
    pixel_variance : grayscale variance  (low → flat / no visible subject)

    Returns None if httpx / Pillow are unavailable or the request fails —
    caller must treat None as "check unavailable, skip retry threshold".
    Returning a fake passing score would mask real quality failures.
    """
    try:
        import httpx
        from PIL import Image
        import io

        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url)
            r.raise_for_status()

        img = Image.open(io.BytesIO(r.content)).convert('L')
        img_small = img.resize((64, 64))
        pixels = list(img_small.getdata())
        n = len(pixels)
        mean = sum(pixels) / n
        variance = sum((p - mean) ** 2 for p in pixels) / n
        return mean, variance

    except ImportError as e:
        logger.warning(f"🔍 封面品質檢查不可用（缺少套件）: {e} — 跳過重試閾值判斷")
        return None
    except Exception as e:
        logger.warning(f"🔍 封面品質檢查失敗（網路/解碼）: {e} — 跳過重試閾值判斷")
        return None


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
    print("[BOOT] VERSION 33.9 - NOCTURIA_MEDICAL_THEME - [SCENE_INDEX_ROUTER] - " + datetime.now().isoformat(), flush=True)
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
            duration_minutes=request.duration_minutes,
            manual_viewpoint=getattr(request, 'manual_viewpoint', None),
        )

        logger.info(f"✅ 成功生成 {len(units)} 個觀測單元")

        # ── 封面主體錨點：topic 優先，CJK 時掃全單元 ─────────────────────────
        # 策略：
        #  1. topic 是英文 → 直接萃取英文主體名詞（最可靠）
        #  2. topic 是中文 → Fix A 已確保每個 image_prompt.prompt 以英文主體名詞開頭，
        #                    掃全部單元取最短有效錨點（比只看 KF001 更穩健）
        topic_raw = request.notes.strip()
        kf001_anchor: str | None = None

        if not _has_cjk(topic_raw):
            # Case 1: English / Latin input — extract directly from topic string
            kf001_anchor = _extract_topic_subject(topic_raw) or None
            logger.info(f"🔑 anchor (from English topic): {kf001_anchor!r}")
        else:
            # Case 2: CJK input — scan all units for English subject noun
            all_candidates: list[tuple[int, str]] = []
            for unit in units:
                ip = getattr(unit, 'image_prompt', None)
                raw = ip.get('prompt', '') if isinstance(ip, dict) else (ip if isinstance(ip, str) else str(ip) if ip else '')
                if not raw:
                    continue
                anchor = _extract_cover_anchor(raw)
                if anchor and not re.search(r'\bfingers?\b|\bhands?\b|\bskin\b|\bflesh\b', anchor, re.IGNORECASE):
                    all_candidates.append((len(anchor.split()), anchor))
            if all_candidates:
                all_candidates.sort(key=lambda x: x[0])
                kf001_anchor = all_candidates[0][1]
            logger.info(f"🔑 anchor (scanned {len(units)} units): {kf001_anchor!r}")

        # Randomized seed per request — ensures different outputs even for the same topic
        cover_seed = random.randint(0, 2 ** 32 - 1)
        logger.info(f"🎲 cover_seed={cover_seed} (randomized)")

        # V33.9 Scene-Index model routing:
        # Scene_Index 0 (Cover) + 1 (Unit_001) → Nano Banana 2 (via img_service router)
        # Scene_Index >= 2 → flux-schnell (cost-efficient)
        kf_model    = img_service.select_model_for_scene(2)   # Scene_Index >=2 standard tier
        cover_model = img_service.select_model_for_scene(0)   # Scene_Index 0 → nano-banana-2
        image_count = len(units) + 1  # 單元 + 封面
        kf_cost     = len(units) * img_service.get_model_cost(kf_model)
        cover_cost  = img_service.get_model_cost(cover_model)
        model_used  = kf_model   # backward-compat field (KF model)
        cost_estimate = CostEstimate(
            image_count=image_count,
            cost_per_image=img_service.get_model_cost(kf_model),
            total_cost=round(kf_cost + cover_cost, 4),
            model_used=f"{kf_model}(KF) + {cover_model}(cover)"
        )

        logger.info(
            f"💰 成本預估: ${cost_estimate.total_cost} "
            f"({len(units)} KF×${img_service.get_model_cost(kf_model)} + "
            f"1 cover×${img_service.get_model_cost(cover_model)})"
        )
        
        # 生成封面圖（三風格隨機選擇：closeup / evidence / paradox）
        cover_url  = None
        cover_meta = {"retry": False, "brightness": None, "variance": None,
                      "cover_anchor_used": None, "cover_seed": cover_seed,
                      "cover_style": None, "retry_style": None}
        try:
            topic = request.notes.strip()

            # 依 hook_technique 選擇最適封面風格（非隨機）
            # units[0] 是定位幕，其 hook_technique 反映主題本質
            first_hook = getattr(units[0], 'hook_technique', None) if units else None
            cover_style = _select_cover_style(first_hook)
            retry_style = _STYLE_FALLBACK[cover_style][0]
            cover_meta["cover_style"] = cover_style

            # ── COVER PROMPT DIAGNOSTIC ──────────────────────────────────
            salt_id = format(random.randint(0, 0xFFFFFF), '06x')
            logger.info("─" * 60)
            logger.info("📋 COVER PROMPT DIAGNOSTIC")
            logger.info(f"  topic        : {topic}")
            logger.info(f"  aspect_ratio : {request.aspect_ratio.value}")
            logger.info(f"  kf001_anchor : {kf001_anchor!r}")
            logger.info(f"  abstract→phys: {_extract_topic_subject(kf001_anchor or topic)!r}")
            logger.info(f"  cover_style  : {cover_style}  (retry → {retry_style})")
            logger.info(f"  cover_seed   : {cover_seed}")
            logger.info(f"  salt_id      : #{salt_id}")
            logger.info("─" * 60)

            cover_meta["cover_anchor_used"] = kf001_anchor or topic
            cover_prompt, enhanced_negative = _build_cover_prompt_v2(
                topic, request.aspect_ratio.value,
                style=cover_style, kf001_anchor=kf001_anchor,
                salt_id=salt_id,
            )
            # V33.9: inject Nocturia medical labels into cover prompt (Scene_Index=0)
            medical_label_0 = img_service._inject_medical_labels(0)
            cover_prompt = f"{medical_label_0}, {cover_prompt}"

            logger.info("📝 cover_prompt (full):")
            logger.info(f"  {cover_prompt}")
            logger.info("─" * 60)

            cover_url = await img_service.generate_image(
                prompt=cover_prompt,
                aspect_ratio=request.aspect_ratio.value,
                model=cover_model,
                seed=cover_seed,
                guidance=4.5,   # 高 guidance → 更嚴格跟隨亮度/打光指令
            )
            logger.info(f"✅ 封面生成成功 [{cover_style}]: {cover_url}")

            # ── 品質檢查：亮度 + 細節方差（僅封面，最多重試 1 次）────────────
            quality = await _check_cover_quality(cover_url)
            if quality is None:
                # 套件不可用或網路失敗 — 不觸發重試，保留封面原樣
                logger.warning("🔍 品質檢查不可用，跳過重試閾值（封面將直接使用）")
                cover_meta["brightness"] = None
                cover_meta["variance"]   = None
            else:
                brightness, variance = quality
                cover_meta["brightness"] = round(brightness, 1)
                cover_meta["variance"]   = round(variance, 1)
                logger.info(
                    f"🔍 封面品質檢測  "
                    f"brightness={brightness:.1f}/255 (閾值≥{COVER_MIN_BRIGHTNESS})  "
                    f"variance={variance:.1f} (閾値≥{COVER_MIN_VARIANCE})  "
                    f"→ {'✅ PASS' if brightness >= COVER_MIN_BRIGHTNESS and variance >= COVER_MIN_VARIANCE else '❌ FAIL — 觸發重試'}"
                )

            if quality is not None and (brightness < COVER_MIN_BRIGHTNESS or variance < COVER_MIN_VARIANCE):
                logger.warning(
                    f"⚠️ 封面品質不足（亮度={brightness:.1f} < {COVER_MIN_BRIGHTNESS} "
                    f"或方差={variance:.1f} < {COVER_MIN_VARIANCE}），"
                    f"切換風格 [{cover_style} → {retry_style}] 重試一次..."
                )
                retry_prompt, retry_negative = _build_cover_prompt_v2(
                    topic, request.aspect_ratio.value,
                    style=retry_style, kf001_anchor=kf001_anchor,
                    salt_id=salt_id,
                )
                cover_meta["retry_style"] = retry_style
                logger.info(f"📝 retry cover_prompt [{retry_style}] (full):")
                logger.info(f"  {retry_prompt}")
                logger.info("─" * 60)
                cover_url = await img_service.generate_image(
                    prompt=retry_prompt,
                    aspect_ratio=request.aspect_ratio.value,
                    model=cover_model,
                    seed=cover_seed,
                    guidance=5.0,   # 重試時更強 guidance，強制跟隨亮度指令
                )
                cover_meta["retry"] = True
                logger.info(f"✅ 封面重試成功 [{retry_style}]: {cover_url}")
                # Re-check quality after retry
                retry_quality = await _check_cover_quality(cover_url)
                if retry_quality is None:
                    logger.warning("🔍 重試後品質檢查不可用，保留重試封面")
                    cover_meta["brightness"] = None
                    cover_meta["variance"]   = None
                else:
                    r_brightness, r_variance = retry_quality
                    cover_meta["brightness"] = round(r_brightness, 1)
                    cover_meta["variance"]   = round(r_variance, 1)
                    logger.info(
                        f"🔍 封面品質檢測 [retry/{retry_style}]  "
                        f"brightness={r_brightness:.1f}/255 (閾值≥{COVER_MIN_BRIGHTNESS})  "
                        f"variance={r_variance:.1f} (閾值≥{COVER_MIN_VARIANCE})  "
                        f"→ {'✅ PASS' if r_brightness >= COVER_MIN_BRIGHTNESS and r_variance >= COVER_MIN_VARIANCE else '⚠️ 仍不足（已無重試）'}"
                    )

        except Exception as e:
            logger.warning(f"⚠️ 封面生成失敗: {e}")
            cover_url = None

        # 封面文字 Hook 建議（供剪輯指南使用，不寫入圖片）
        cover_hooks = _build_cover_hooks(units, topic)

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
                    "cover_url":     cover_url,
                    "cover_quality": cover_meta,
                    "cover_hooks":   cover_hooks,
                    "keyframes_only": True,  # 標記這是關鍵幀模式
                    "post_production_required": True,  # 需要後製運鏡
                },
                "cover_url":     cover_url,
                "cover_quality": cover_meta,
                "cover_hooks":   cover_hooks,
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
    "/generate-stream",
    summary="生成觀測單元（SSE 即時串流版）",
    description="與 /generate 相同邏輯，但以 Server-Sent Events 即時回傳進度"
)
async def generate_observation_units_stream(request: ObservationNotesInput):
    """
    SSE 事件類型：
    - step:  {type, message}                     — 進度步驟
    - units: {type, units, cost_estimate, ...}   — 腳本就緒（可立即渲染卡片）
    - cover: {type, cover_url}                   — 封面就緒
    - done:  {type, production_notes, cost_estimate} — 全部完成
    - error: {type, message}                     — 失敗
    """
    async def generator():
        try:
            yield {"data": _json.dumps({"type": "step", "message": "解析輸入中"}, ensure_ascii=False)}

            obs_service = get_observation_service()
            img_service = get_image_service()

            yield {"data": _json.dumps({"type": "step", "message": "Gemini 腳本生成中…"}, ensure_ascii=False)}

            units = await obs_service.generate_units(
                notes=request.notes,
                target_units=request.target_units,
                style_preference=request.style_preference,
                video_mode=request.video_mode,
                aspect_ratio=request.aspect_ratio.value,
                duration_minutes=request.duration_minutes,
                manual_viewpoint=getattr(request, 'manual_viewpoint', None),
            )
            logger.info(f"✅ SSE: 成功生成 {len(units)} 個觀測單元")

            # V33.9 Scene-Index routing (SSE path)
            kf_model    = img_service.select_model_for_scene(2)   # Scene_Index >=2
            cover_model = img_service.select_model_for_scene(0)   # Scene_Index 0 → nano-banana-2
            kf_cost     = len(units) * img_service.get_model_cost(kf_model)
            cover_cost  = img_service.get_model_cost(cover_model)
            cost_info = {
                "image_count":     len(units) + 1,
                "model_used":      f"{kf_model}(KF×{len(units)}) + {cover_model}(cover×1)",
                "price_per_image": img_service.get_model_cost(kf_model),
                "kf_cost":         round(kf_cost, 4),
                "cover_cost":      round(cover_cost, 4),
                "total_cost":      round(kf_cost + cover_cost, 4),
                "currency":        "USD",
            }

            # Emit units immediately so frontend can render cards
            yield {"data": _json.dumps({
                "type":          "units",
                "units":         [u.model_dump(mode="json") for u in units],
                "cost_estimate": cost_info,
                "video_mode":    request.video_mode.value,
                "aspect_ratio":  request.aspect_ratio.value,
            }, ensure_ascii=False)}

            # Cover anchor extraction (same logic as /generate)
            topic_raw = request.notes.strip()
            kf001_anchor: str | None = None
            if not _has_cjk(topic_raw):
                kf001_anchor = _extract_topic_subject(topic_raw) or None
            else:
                all_candidates: list[tuple[int, str]] = []
                for unit in units:
                    ip = getattr(unit, "image_prompt", None)
                    raw = ip.get("prompt", "") if isinstance(ip, dict) else (ip if isinstance(ip, str) else str(ip) if ip else "")
                    if raw:
                        anchor = _extract_cover_anchor(raw)
                        if anchor and not re.search(r'\bfingers?\b|\bhands?\b|\bskin\b|\bflesh\b', anchor, re.IGNORECASE):
                            all_candidates.append((len(anchor.split()), anchor))
                if all_candidates:
                    all_candidates.sort(key=lambda x: x[0])
                    kf001_anchor = all_candidates[0][1]

            yield {"data": _json.dumps({"type": "step", "message": "封面生成中…"}, ensure_ascii=False)}

            cover_seed  = random.randint(0, 2 ** 32 - 1)
            salt_id     = format(random.randint(0, 0xFFFFFF), '06x')
            first_hook  = getattr(units[0], "hook_technique", None) if units else None
            cover_style = _select_cover_style(first_hook)
            retry_style = _STYLE_FALLBACK[cover_style][0]
            topic       = topic_raw

            logger.info("─" * 60)
            logger.info("📋 SSE COVER PROMPT DIAGNOSTIC")
            logger.info(f"  topic        : {topic}")
            logger.info(f"  kf001_anchor : {kf001_anchor!r}")
            logger.info(f"  abstract→phys: {_extract_topic_subject(kf001_anchor or topic)!r}")
            logger.info(f"  cover_style  : {cover_style}  (retry → {retry_style})")
            logger.info(f"  cover_seed   : {cover_seed}")
            logger.info(f"  salt_id      : #{salt_id}")
            logger.info("─" * 60)

            cover_url: str | None = None
            try:
                cover_prompt, _ = _build_cover_prompt_v2(
                    topic, request.aspect_ratio.value,
                    style=cover_style, kf001_anchor=kf001_anchor,
                    salt_id=salt_id,
                )
                # V33.9: inject Nocturia medical labels (Scene_Index=0)
                cover_prompt = f"{img_service._inject_medical_labels(0)}, {cover_prompt}"
                logger.info(f"📡 SSE FINAL PROMPT → Replicate: {cover_prompt}")
                cover_url = await img_service.generate_image(
                    prompt=cover_prompt,
                    aspect_ratio=request.aspect_ratio.value,
                    model=cover_model,
                    seed=cover_seed,
                    guidance=4.5,
                )
                quality = await _check_cover_quality(cover_url)
                if quality is not None:
                    brightness, variance = quality
                    if brightness < COVER_MIN_BRIGHTNESS or variance < COVER_MIN_VARIANCE:
                        retry_prompt, _ = _build_cover_prompt_v2(
                            topic, request.aspect_ratio.value,
                            style=retry_style, kf001_anchor=kf001_anchor,
                            salt_id=salt_id,
                        )
                        cover_url = await img_service.generate_image(
                            prompt=retry_prompt,
                            aspect_ratio=request.aspect_ratio.value,
                            model=cover_model,
                            seed=cover_seed,
                            guidance=5.0,
                        )
                logger.info(f"✅ SSE: 封面生成成功: {cover_url}")
                yield {"data": _json.dumps({"type": "cover", "cover_url": cover_url}, ensure_ascii=False)}
            except Exception as e:
                logger.warning(f"⚠️ SSE: 封面生成失敗，繼續: {e}")

            # Done
            cover_hooks = _build_cover_hooks(units, topic)
            production_notes = {
                "workflow":              "keyframe_to_motion",
                "motionEffectsIncluded": True,
                "recommendedTools":      ["CapCut", "Premiere Pro", "Final Cut Pro"],
                "estimatedEditingTime":  f"{len(units) * 2}-{len(units) * 3} minutes",
            }
            yield {"data": _json.dumps({
                "type":             "done",
                "production_notes": production_notes,
                "cover_hooks":      cover_hooks,
                "cost_estimate":    cost_info,
            }, ensure_ascii=False)}

        except Exception as e:
            logger.error(f"❌ SSE 生成失敗: {e}", exc_info=True)
            yield {"data": _json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)}

    return EventSourceResponse(generator())


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
        
        # V33.9 Scene-Index routing (cost estimate)
        kf_model    = img_service.select_model_for_scene(2)   # Scene_Index >=2 → flux-schnell
        cover_model = img_service.select_model_for_scene(0)   # Scene_Index 0 → nano-banana-2
        image_count = keyframe_count + 1
        kf_cost     = keyframe_count * img_service.get_model_cost(kf_model)
        cover_cost  = img_service.get_model_cost(cover_model)

        cost_info = {
            "image_count":    image_count,
            "model_used":     f"{kf_model}(KF×{keyframe_count}) + {cover_model}(cover×1)",
            "price_per_image": img_service.get_model_cost(kf_model),   # KF 單價（參考）
            "kf_cost":        round(kf_cost, 4),
            "cover_cost":     round(cover_cost, 4),
            "total_cost":     round(kf_cost + cover_cost, 4),
            "currency":       "USD",
        }
        
        return {
            "success": True,
            "video_mode": request.video_mode.value,
            "aspect_ratio": request.aspect_ratio.value,
            "duration_minutes": request.duration_minutes,
            "keyframe_count": keyframe_count,
            "cost_estimate": cost_info
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