# -*- coding: utf-8 -*-
"""
短影音場景腳本生成服務
支援 Shorts + 長片模式，智能關鍵幀生成
"""
import os
import sys
import json
import logging
import asyncio
import re
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
# Force a direct stderr handler so sentinel output is ALWAYS visible
# regardless of how uvicorn may override the root logger configuration.
logger.setLevel(logging.INFO)
if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    _sentinel_handler = logging.StreamHandler(sys.stderr)
    _sentinel_handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s: %(message)s"))
    logger.addHandler(_sentinel_handler)

# ── TTS 語速校準 ───────────────────────────────────────────────────────────────
TTS_CPS        = 7.0  # chars / second（實測）
TTS_END_MARGIN = 1.0  # seconds of buffer before scene boundary
MAX_VO_REWRITES = 3   # max rewrite attempts before giving up

# ── Script Sentinel: blocked term sets (quality_inspector.md) ────────────────
_SENTINEL_BIO_TERMS: frozenset[str] = frozenset({
    'fleshy', 'flesh', 'skin', 'skin-like', 'skinlike',
    'cell', 'cellular', 'organic', 'tissue', 'membrane',
    'mucus', 'mucous', 'gland', 'pore', 'follicle',
    'vein', 'vessel', 'blood', 'bone', 'muscle',
    'biological', 'anatomy', 'anatomical',
    'embryo', 'spore', 'bulb', 'mycelium', 'fungal',
    'barnacle', 'amoeba', 'epidermis', 'dermis',
    'keratin', 'collagen', 'organic texture', 'fleshy shape',
})
_SENTINEL_ABSTRACT_NOUNS: frozenset[str] = frozenset({
    'birth', 'origin', 'miracle', 'magic', 'spirit', 'soul',
    'essence', 'aura', 'divine', 'sacred', 'holy', 'cosmic',
    'concept', 'abstract', 'notion', 'emotion', 'feeling', 'sensation',
    'mystery', 'mystical', 'mythical', 'transcendent',
    'metaphysical', 'ethereal', 'infinity', 'eternity', 'timeless',
    'energy field', 'life force',
})
# Simplified-Chinese-only characters (not used in Traditional Chinese writing)
_SENTINEL_SIMP_ZH_RE = re.compile(
    r'[爱边变车从东动对国过汉开来乐联马门么农气认时书说问线现'
    r'学样义应员远运长这种转专发两随让给当经带头们]'
)
_SENTINEL_MAX_FIX_ATTEMPTS = 2  # max Gemini calls to re-physicalize one prompt
# Word-boundary regex: matches "finger" or "fingers" but NOT "fingerprint/fingerprints/fingertip"
_FINGER_RE = re.compile(r'\bfingers?\b', re.IGNORECASE)

# ── 字幕速率（content_guard.md §2，2026-03 實測更新）─────────────────────────
# 實測：8 字 ÷ 2.3 秒 ≈ 3.5 CPS（觀眾閱讀速率，非 TTS 朗讀速率）
# 動態公式：min(floor(unit_seconds × SUB_CPS), SUB_HARD_LIMIT)
SUB_CPS        = 3.5  # reading chars / second（舊值 2.2 → 更新為 3.5）
SUB_HARD_LIMIT = 30   # 任何時長的絕對上限（避免超長單元產生超長字幕）


def _sub_max_chars(unit_sec: float) -> int:
    """SUB 最大字數 = min(floor(unit_sec × SUB_CPS), SUB_HARD_LIMIT)
    5s → 17字；10s → 30字（上限）；符合 content_guard.md §2 動態公式。
    """
    return min(int(unit_sec * SUB_CPS), SUB_HARD_LIMIT)


# 向後相容：Shorts 5s 單元的預計算值（供 system instruction f-string 使用）
SUB_MAX_CHARS = _sub_max_chars(5)  # = 17

# ── Semantic VO / subtitle break helpers ─────────────────────────────────────
# Rule A (explicit): 禁止在「的/是/把/而/與/和/並/且/因/所以/但」後斷
# Rule B (general):  每段結尾不能是助詞/連接詞
_VO_FORBIDDEN_TAIL: frozenset[str] = frozenset(
    '的是把而與和並且因但就也都還又更可卻然後在為了到'
)
_VO_FORBIDDEN_TAIL_MULTI: tuple[str, ...] = (
    '所以', '但是', '因此', '而且', '並且', '不過', '然而', '雖然', '即使',
)
_VO_BREAK_SENT: frozenset[str] = frozenset('。！？…')   # sentence boundary (best)
_VO_BREAK_CLAUSE: frozenset[str] = frozenset('，；')     # clause boundary (OK)


def _vo_bad_tail(text: str) -> bool:
    """True if text ends with a particle/conjunction that cannot close a segment."""
    s = text.rstrip()
    if not s:
        return True
    if s[-1] in _VO_FORBIDDEN_TAIL:
        return True
    for w in _VO_FORBIDDEN_TAIL_MULTI:
        if s.endswith(w):
            return True
    return False


def _vo_find_break(text: str, max_chars: int) -> int:
    """
    Find best semantic break index ≤ max_chars (exclusive end of part1).
    Returns -1 if no valid break found.

    Priority:
      1. After sentence punctuation 。！？…
      2. After clause punctuation ，；  (trailing punct stripped when checking tail)
      3. Latest position whose prefix does not violate _vo_bad_tail
    """
    limit = min(max_chars, len(text))
    # Pass 1: sentence-ending punctuation
    for i in range(limit, 0, -1):
        if text[i - 1] in _VO_BREAK_SENT and not _vo_bad_tail(text[:i]):
            return i
    # Pass 2: clause punctuation
    for i in range(limit, 0, -1):
        if text[i - 1] in _VO_BREAK_CLAUSE:
            seg = text[:i].rstrip('，；').strip()
            if seg and not _vo_bad_tail(seg):
                return i
    # Pass 3: any position with a clean tail
    for i in range(limit, 0, -1):
        if not _vo_bad_tail(text[:i]):
            return i
    return -1


def _vo_semantic_split(text: str, max_chars: int) -> tuple[str, str]:
    """
    Split text → (part1, part2) at the best semantic break ≤ max_chars.
    Neither part ends with a forbidden tail.
    Falls back to raw index split only as absolute last resort.
    """
    if len(text) <= max_chars:
        return text, ''
    pos = _vo_find_break(text, max_chars)
    if pos > 0:
        part1 = text[:pos].rstrip('，；').strip()
        part2 = text[pos:].lstrip('，；').strip()
        return part1, part2
    # Absolute fallback (caller logs warning)
    return text[:max_chars], text[max_chars:]


def _vo_semantic_shorten(text: str, max_chars: int) -> str:
    """Return longest semantically valid prefix ≤ max_chars (part2 discarded)."""
    part1, _ = _vo_semantic_split(text, max_chars)
    return part1


# ── Gemini JSON control-character sanitizer ───────────────────────────────────
_CTRL_ESCAPE_MAP: dict[str, str] = {'\n': '\\n', '\r': '\\r', '\t': '\\t'}


def _sanitize_gemini_json(text: str) -> str:
    """
    Escape bare control characters that appear inside JSON string values.

    Gemini occasionally emits literal \\n / \\r / \\t inside string values
    instead of the escaped forms \\\\n / \\\\r / \\\\t, causing json.loads to
    raise: "Invalid control character at: line N col M (char C)".

    Strategy: walk the text character-by-character, track string context,
    and replace any control char (ord < 0x20) found inside a string with
    its safe escape sequence.  Structural whitespace outside strings is
    left untouched so JSON indentation / newlines survive intact.
    """
    result: list[str] = []
    in_string = False
    escaped = False

    for ch in text:
        if escaped:
            result.append(ch)
            escaped = False
            continue
        if ch == '\\' and in_string:
            result.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ord(ch) < 0x20:
            # Bare control char inside a string value — use safe escape or drop
            result.append(_CTRL_ESCAPE_MAP.get(ch, ''))
            continue
        result.append(ch)

    return ''.join(result)


# ── Image prompt CJK sanitizer ────────────────────────────────────────────────
_IP_CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+')


def _strip_cjk_from_prompt(prompt: str) -> str:
    """
    Remove CJK characters from image prompt strings.
    FLUX / Stable Diffusion models are trained on English-only prompts;
    CJK characters cause garbled text artifacts or off-topic image generation.
    Cleans up orphaned commas and whitespace left by removal.
    """
    cleaned = _IP_CJK_RE.sub('', prompt)
    cleaned = re.sub(r',\s*,+', ',', cleaned)   # merge consecutive commas
    cleaned = re.sub(r'^\s*,\s*', '', cleaned)  # drop leading comma
    cleaned = re.sub(r',\s*$', '', cleaned)     # drop trailing comma
    return re.sub(r'\s+', ' ', cleaned).strip()


# ── image_prompt noun-first enforcer (visual_director.md §4) ─────────────────
_IP_FORBIDDEN_STARTS: frozenset[str] = frozenset({
    'emphasizing', 'showing', 'revealing', 'capturing', 'depicting',
    'its', 'their', 'this', 'that', 'subject', 'background', 'with',
})

# content_guard.md §9 — 舊會話洩漏詞，任何主題的 image_prompt 禁止出現
# V30.0: 追加 face / faces（物化主體原則 §4.2）
_TOPIC_BANNED_TERMS: tuple[str, ...] = (
    'crystallin', 'lens cortex', 'cataract', 'protein strand',
    'refraction anomaly', 'optical aberration',
    'photorealistic microscopy style', 'crystallin fiber',
    'crystallin layer', 'crystallin deposit',
    'lens deposit', 'cortex surface', 'microscopy style',
    # §4.2 物化主體原則 — face / faces 禁止作為觀察主體
    'close-up of face', 'close-up of faces', 'macro of face', 'macro of faces',
    'face detail', 'faces detail', 'human face', 'human faces',
)
_IP_BANNED_RE = re.compile(
    '|'.join(re.escape(t) for t in _TOPIC_BANNED_TERMS),
    flags=re.IGNORECASE,
)


def _enforce_noun_first_prompt(prompt: str) -> str:
    """
    Reorder image_prompt so the first comma-segment starts with a subject noun.
    visual_director.md §4: first token must be an English subject noun.
    Forbidden first tokens: emphasizing/showing/revealing/capturing/depicting/
                            its/their/this/that/subject/background/with
    """
    segments = [s.strip() for s in prompt.split(',') if s.strip()]
    if not segments:
        return prompt
    first_token = segments[0].split()[0].lower().rstrip('.,') if segments[0].split() else ''
    if first_token not in _IP_FORBIDDEN_STARTS:
        return prompt  # Already compliant
    # Find the first segment whose leading token is a valid noun
    for i, seg in enumerate(segments):
        tok = seg.split()[0].lower().rstrip('.,') if seg.split() else ''
        if tok and tok not in _IP_FORBIDDEN_STARTS:
            reordered = [segments[i]] + [s for j, s in enumerate(segments) if j != i]
            logger.debug(
                f"  ⚙️ noun-first fix: '{segments[0][:40]}…' → '{segments[i][:40]}…'"
            )
            return ', '.join(reordered)
    return prompt  # Cannot auto-fix — return as-is


def _sanitize_banned_terms(prompt: str) -> str:
    """Strip topic-leaked banned terms from image prompt (content_guard.md §9)."""
    cleaned = _IP_BANNED_RE.sub('', prompt)
    cleaned = re.sub(r',\s*,+', ',', cleaned)
    cleaned = re.sub(r'^\s*,\s*', '', cleaned)
    cleaned = re.sub(r',\s*$', '', cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()


# ── Script Sentinel: cross-unit helpers (quality_inspector.md §C & §D) ───────

def _sentinel_check_duplicate_data(units_data: list[dict]) -> None:
    """ERR_DUPLICATE_DATA: 全片具體測量數值（帶單位）不得跨單元重複。"""
    num_pat = re.compile(
        r'\b\d+\.?\d*\s*(?:公分|公里|公尺|公克|毫米|cm|mm|km|kg|g|度|%|倍|秒|天|年|萬|億)\b'
    )
    seen: dict[str, list[int]] = {}
    for idx, ud in enumerate(units_data):
        for field in ("phenomenon", "voice_over_zh", "mechanism"):
            val = ud.get(field, "") or ""
            for m in num_pat.finditer(val):
                seen.setdefault(m.group(), []).append(idx + 1)
    for num, unit_list in seen.items():
        if len(unit_list) > 1:
            logger.warning(
                f"⚠️ ERR_DUPLICATE_DATA: 數值 {num!r} 重複於 Unit {unit_list} — "
                f"建議各單元使用不同具體數據"
            )


def _sentinel_check_strategy(units_data: list[dict]) -> None:
    """ERR_WEAK_HOOK / ERR_GENERIC_HASHTAG: 策略層審核（非阻塞，僅記錄）。"""
    if not units_data:
        return
    strong_hooks = {"forbidden_knowledge", "visual_paradox", "shock_fact", "reverse_question"}
    tech = (units_data[0].get("hook_technique") or "").strip()
    if tech not in strong_hooks:
        logger.warning(
            f"⚠️ ERR_WEAK_HOOK: Unit 1 hook_technique={tech!r} 非強力技巧 — "
            f"建議使用 forbidden_knowledge / visual_paradox / shock_fact / reverse_question"
        )
    for idx, ud in enumerate(units_data):
        hs = ud.get("hashtag_strategy") or {}
        if not isinstance(hs, dict):
            continue
        tags = hs.get("tags", []) or []
        # 若所有標籤長度都 ≤ 5 字（泛用短標，無具體槽點）
        if tags and all(len(t.lstrip("#")) <= 5 for t in tags):
            logger.warning(
                f"⚠️ ERR_GENERIC_HASHTAG: Unit {idx+1} hashtags={tags} 全為泛用詞 — "
                f"建議包含具體人名/事件（如 #格雷與貝爾的專利戰）"
            )


class ObservationService:
    """短影音場景腳本生成服務"""

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        self.client = genai.Client(api_key=api_key)
        self.model_name = 'gemini-2.5-flash-lite'
        # V31.5 — 全鏈路規範注入：自動讀取所有 experts/*.md
        self._expert_rules: dict[str, str] = self._load_expert_rules()
        # 向後相容性快捷參照
        self._content_guard_rules   = self._expert_rules.get('content_guard.md', '')
        self._visual_director_rules = self._expert_rules.get('visual_director.md', '')

    # ──────────────────────────────────────────────
    # 計算輔助
    # ──────────────────────────────────────────────

    def _calculate_keyframe_count(
        self,
        video_mode: VideoMode,
        duration_minutes: Optional[int] = None
    ) -> int:
        if video_mode == VideoMode.SHORTS:
            return 5   # V33.9.2: 預設 5 幕（前端 target_units 可覆蓋至 8）
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
    # 專家規範載入與注入
    # ──────────────────────────────────────────────

    def _load_expert_rules(self) -> dict[str, str]:
        """V31.5: Auto-read ALL .md files from .claudecode/experts/ at project root.
        Returns {filename: content} dict. Emits [INJECTION] boot marker on success.
        """
        services_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(services_dir))
        experts_dir  = os.path.join(project_root, '.claudecode', 'experts')
        rules: dict[str, str] = {}
        try:
            md_files = sorted(f for f in os.listdir(experts_dir) if f.endswith('.md'))
        except FileNotFoundError:
            logger.warning(f"⚠️ Experts directory not found: {experts_dir}")
            return rules
        for fname in md_files:
            path = os.path.join(experts_dir, fname)
            try:
                with open(path, encoding='utf-8') as f:
                    content = f.read()
                rules[fname] = content
                logger.info(f"  ✅ [{fname}] loaded ({len(content)} chars)")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load {fname}: {e}")
        logger.info(
            f"[INJECTION] V31.5 - Gemini System Prompt synchronized with {len(rules)} experts."
        )
        return rules

    def _load_expert_file(self, filename: str) -> str:
        """Load expert rule file from .claudecode/experts/ at project root."""
        services_dir = os.path.dirname(os.path.abspath(__file__))       # backend/services/
        project_root = os.path.dirname(os.path.dirname(services_dir))   # project root
        path = os.path.join(project_root, '.claudecode', 'experts', filename)
        try:
            with open(path, encoding='utf-8') as f:
                content = f.read()
            logger.info(f"✅ Expert rules loaded: {filename} ({len(content)} chars)")
            return content
        except FileNotFoundError:
            logger.warning(f"⚠️ Expert file not found: {path}")
            return ""

    @staticmethod
    def _extract_md_sections(content: str, section_prefixes: list[str]) -> str:
        """Extract heading-delimited sections from markdown by ## prefix match."""
        lines = content.split('\n')
        result: list[str] = []
        in_target = False
        for line in lines:
            if line.startswith('## '):
                in_target = any(line.startswith(p) for p in section_prefixes)
            if in_target:
                result.append(line)
        return '\n'.join(result)

    def _build_expert_guard_block(self) -> str:
        """
        V31.5: Build focused expert rule excerpts for system instruction injection.
        Injects all 4 active expert files:
          - content_guard §1-4    (language / pacing / subtitle / VO narrative)
          - visual_director §4    (FLUX image generation parameters)
          - material_auditor §1-7 (Subject Proxy Protocol + Brand DNA wall)
          - quality_inspector §A-D (sentinel checks + ERR codes)
        """
        blocks: list[str] = []

        # content_guard §1-4
        cg = self._expert_rules.get('content_guard.md', '')
        if cg:
            excerpt = self._extract_md_sections(cg, ['## 1.', '## 2.', '## 3.', '## 4.'])
            if excerpt:
                blocks.append("**[content_guard.md] 語言 / 節奏 / 字幕 / 旁白規範**\n" + excerpt)

        # visual_director §4
        vd = self._expert_rules.get('visual_director.md', '')
        if vd:
            excerpt = self._extract_md_sections(vd, ['## 4.'])
            if excerpt:
                blocks.append("**[visual_director.md] FLUX 圖片生成參數**\n" + excerpt)

        # material_auditor §1-7 (Subject Proxy Protocol + Brand DNA)
        ma = self._expert_rules.get('material_auditor.md', '')
        if ma:
            excerpt = self._extract_md_sections(
                ma, ['## 1.', '## 2.', '## 3.', '## 4.', '## 5.', '## 6.', '## 7.']
            )
            if excerpt:
                blocks.append("**[material_auditor.md] 主體代理人協定 + 品牌 DNA**\n" + excerpt)

        # quality_inspector §A-D (sentinel checks)
        qi = self._expert_rules.get('quality_inspector.md', '')
        if qi:
            excerpt = self._extract_md_sections(qi, ['## A', '## B', '## C', '## D'])
            if excerpt:
                blocks.append("**[quality_inspector.md] 品質哨兵規範**\n" + excerpt)

        return '\n\n---\n\n'.join(blocks)

    # ──────────────────────────────────────────────
    # TTS 語速校準
    # ──────────────────────────────────────────────

    @staticmethod
    def _vo_max_chars(unit_sec: float) -> int:
        """VO 最大字數 = floor((unit_sec − margin) × cps)"""
        return int((unit_sec - TTS_END_MARGIN) * TTS_CPS)

    async def _rewrite_vo_if_needed(
        self,
        voice_over: str,
        max_chars: int,
        topic: str,
        unit_role: str,
    ) -> tuple[str, str]:
        """
        若 voice_over 超過 max_chars，先嘗試 Gemini 重寫縮短（最多 MAX_VO_REWRITES 次）。
        全部重寫仍超長時，改用語意分割（_vo_semantic_split）取 part1；
        part2（續句）由呼叫者寫入 editing_notes，標註 [VO part2]。
        禁止 substring 硬截。

        Returns:
            (part1, part2) — part2 為 '' 代表無需分割。
        """
        if len(voice_over) <= max_chars:
            return voice_over, ''

        current = voice_over
        for attempt in range(1, MAX_VO_REWRITES + 1):
            logger.warning(
                f"⚠️ VO 超長（{len(current)}字 > {max_chars}字限制），"
                f"第 {attempt} 次重寫: {current!r}"
            )
            rewrite_prompt = (
                f"你是短影音旁白文案師。\n"
                f"主題：「{topic}」，幕：{unit_role}\n"
                f"以下旁白超過 TTS 跨幕上限 {max_chars} 字，"
                f"請重新創作一句意思相同但更精煉的旁白，"
                f"嚴格 ≤ {max_chars} 字，可直接朗讀，"
                f"禁止截斷原句，禁止格式說明或【】標記，"
                f"禁止以助詞（的/是/把/而/與/和/並/且/因/所以/但）結尾。\n"
                f"原旁白：{current}\n"
                f"只輸出新旁白，不加任何說明。"
            )
            cfg = types.GenerateContentConfig(temperature=0.5, max_output_tokens=64)
            try:
                resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_content,
                        model=self.model_name,
                        contents=rewrite_prompt,
                        config=cfg,
                    ),
                    timeout=30.0,
                )
                rewritten = resp.text.strip().strip("「」『』\"' \n")
                if len(rewritten) <= max_chars and not _vo_bad_tail(rewritten):
                    logger.info(f"✅ VO 重寫成功（{len(rewritten)}字）: {rewritten!r}")
                    return rewritten, ''
                logger.warning(
                    f"🔄 第 {attempt} 次重寫仍超長或結尾不合（{len(rewritten)}字），繼續..."
                )
                current = rewritten
            except Exception as e:
                logger.error(f"❌ VO 重寫失敗（第 {attempt} 次）: {e}")
                break

        # 所有重寫失敗 → 語意分割 part1 / part2（禁止硬截）
        part1, part2 = _vo_semantic_split(current, max_chars)
        if part2:
            logger.critical(
                f"❌ VO 重寫 {MAX_VO_REWRITES} 次仍超長，改為語意分割\n"
                f"  part1({len(part1)}字 ≈ {len(part1)/TTS_CPS:.1f}s): {part1!r}\n"
                f"  part2({len(part2)}字): {part2!r}"
            )
        else:
            logger.critical(
                f"❌ VO 重寫 {MAX_VO_REWRITES} 次仍超長，語意分割無 part2，"
                f"取最長有效前綴（{len(part1)}字）: {part1!r}"
            )
        return part1, part2

    # ──────────────────────────────────────────────
    # Script Sentinel（quality_inspector.md）
    # ──────────────────────────────────────────────

    async def _sentinel_fix_image_prompt(
        self,
        original_prompt: str,
        topic: str,
        aspect_ratio: str,
        unit_no: int,
        bio_hits: list[str],
        abstract_hits: list[str],
    ) -> str | None:
        """
        呼叫 Gemini 將含生物/抽象詞的 image_prompt 重新物理實體化。
        最多嘗試 _SENTINEL_MAX_FIX_ATTEMPTS 次；失敗返回 None（保留原始 prompt）。
        """
        issues_desc: list[str] = []
        if bio_hits:
            issues_desc.append(f"biological/fleshy terms: {', '.join(bio_hits)}")
        if abstract_hits:
            issues_desc.append(f"abstract nouns: {', '.join(abstract_hits)}")

        fix_prompt = (
            f"You are a FLUX image prompt engineer. A prompt was REJECTED by quality control.\n"
            f"Topic: \"{topic}\"  |  Unit: {unit_no}  |  Aspect ratio: {aspect_ratio}\n"
            f"\nREJECTED PROMPT:\n{original_prompt}\n"
            f"\nREJECT REASONS: {'; '.join(issues_desc)}\n"
            f"\nRULES FOR THE FIX:\n"
            f"1. Replace ALL biological/fleshy/organic terms with concrete PHYSICAL OBJECTS "
            f"(e.g. 'Patent document', 'Gear mechanism', 'Blueprint schematic', 'Metal component').\n"
            f"2. Replace ALL abstract nouns (Birth, Origin, Miracle, Spirit, Essence…) with "
            f"tangible man-made or natural physical objects directly related to the topic.\n"
            f"3. The prompt MUST start with a concrete physical noun (not a verb or adjective).\n"
            f"4. Keep all lighting, style, aspect ratio, and orientation terms intact.\n"
            f"5. Keep the prompt in English only. No Chinese characters.\n"
            f"6. Output ONLY the corrected prompt string. No explanation. No quotes."
        )
        cfg = types.GenerateContentConfig(temperature=0.3, max_output_tokens=200)
        for attempt in range(1, _SENTINEL_MAX_FIX_ATTEMPTS + 1):
            try:
                resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_content,
                        model=self.model_name,
                        contents=fix_prompt,
                        config=cfg,
                    ),
                    timeout=30.0,
                )
                fixed = resp.text.strip().strip("\"'「」")
                fixed_lower = fixed.lower()
                still_bio = [t for t in _SENTINEL_BIO_TERMS if t in fixed_lower]
                still_abs = [t for t in _SENTINEL_ABSTRACT_NOUNS if t in fixed_lower]
                if not still_bio and not still_abs:
                    logger.info(
                        f"✅ 哨兵修正成功 [Unit {unit_no}]（嘗試 {attempt}）: {fixed[:80]!r}"
                    )
                    return fixed
                logger.warning(
                    f"⚠️ 哨兵修正嘗試 {attempt} 仍有問題: bio={still_bio} abs={still_abs}"
                )
            except Exception as e:
                logger.error(f"❌ 哨兵修正失敗（Unit {unit_no}，嘗試 {attempt}）: {e}")
                break
        return None

    async def validate_script_logic(
        self,
        units_data: list[dict],
        notes: str,
        aspect_ratio: str,
        unit_duration: int,
    ) -> tuple[list[dict], bool]:
        """
        腳本哨兵：Gemini 產出後、flux-dev 渲染前的指令審核。
        (quality_inspector.md)

        審核項目：
          A. 視覺指令硬化 — image_prompt bio/abstract 詞攔截 + Gemini 重新物理實體化
          B. 繁體唯一性   — 簡體字偵測（記錄警告）
          C. 數據排他性   — 跨單元具體數值重複警告
          D. 策略層       — Hook 技巧 + Hashtag 品質警告

        Returns:
            (units_data, is_valid)
            is_valid=False 代表仍有無法自動修正的 CRITICAL 錯誤，
            呼叫方應觸發 while 迴圈重新向 Gemini 請求生成。
        """
        logger.info("─" * 60)
        logger.info("[SENTINEL] ─── 腳本哨兵啟動 ───────────────────────────────")
        logger.info("[SENTINEL] 審核 %d 個單元，主題：%r", len(units_data), notes)
        print(f"[SENTINEL] 🚀 啟動 — 審核 {len(units_data)} 個單元，主題: {notes!r}", file=sys.stderr, flush=True)

        # C. 數據排他性（跨單元，先掃全部）
        logger.info("[CHECK][C] 數據排他性：跨單元數值重複掃描…")
        _sentinel_check_duplicate_data(units_data)

        # D. 策略層（跨單元）
        logger.info("[CHECK][D] 策略層：Hook 強度 + Hashtag 槽點檢查…")
        _sentinel_check_strategy(units_data)

        # A + B + E. 逐單元審核
        critical_fail = False  # 若任何 CRITICAL 錯誤無法自動修正，設為 True
        for idx, unit_data in enumerate(units_data):
            unit_no = idx + 1
            errors: list[str] = []

            # ── 取出 image_prompt.prompt ─────────────────────────────────────
            ip = unit_data.get("image_prompt") or {}
            if isinstance(ip, dict):
                prompt_text = ip.get("prompt", "") or ""
            elif isinstance(ip, str):
                prompt_text = ip
            else:
                prompt_text = str(ip) if ip else ""

            prompt_lower = prompt_text.lower()

            # A-0. 隱藏手指硬攔截（ERR_FOUND_HIDDEN_FINGER）
            # Uses word-boundary regex: catches "finger" and "fingers" but NOT "fingerprint/fingertip"
            logger.info("[CHECK][A0] Unit %d — finger/macro 硬攔截…", unit_no)
            _finger_match = _FINGER_RE.search(prompt_text)
            if _finger_match:
                _detected_word = _finger_match.group()
                logger.warning("[CHECK][A0] ❌ REJECT Unit %d — '%s' in positive prompt！強制中斷重跑", unit_no, _detected_word)
                print(f"🚨 SENTINEL A-0 REJECT [Unit {unit_no}] — '{_detected_word}' detected. RAISING ValueError to force regeneration.", file=sys.stderr, flush=True)
                raise ValueError("DETECTED_FINGER_GHOST")
            elif "extreme macro" in prompt_lower:
                errors.append("ERR_EXTREME_MACRO: 'extreme macro' detected — high bio-render risk")
                bio_hits_finger = ["extreme macro"]
                logger.warning("[CHECK][A0] ❌ REJECT — 'extreme macro' 高生物渲染風險")
                critical_fail = True
            else:
                bio_hits_finger = []
                logger.info("[CHECK][A0] ✅ PASS")

            # A-1. 生物詞 (ERR_BIO_TERM)
            logger.info("[CHECK][A1] Unit %d — 生物詞掃描…", unit_no)
            _bio_only = [t for t in _SENTINEL_BIO_TERMS if t in prompt_lower]
            bio_hits = bio_hits_finger + _bio_only
            if _bio_only:
                errors.append(f"ERR_BIO_TERM: {_bio_only}")
                logger.warning("[CHECK][A1] ❌ REJECT — 生物詞命中: %s", bio_hits)
            else:
                logger.info("[CHECK][A1] ✅ PASS")

            # A-2. 抽象名詞 (ERR_ABSTRACT_NOUN)
            logger.info("[CHECK][A2] Unit %d — 抽象名詞掃描…", unit_no)
            abstract_hits = [t for t in _SENTINEL_ABSTRACT_NOUNS if t in prompt_lower]
            if abstract_hits:
                errors.append(f"ERR_ABSTRACT_NOUN: {abstract_hits}")
                logger.warning("[CHECK][A2] ❌ REJECT — 抽象名詞命中: %s", abstract_hits)
            else:
                logger.info("[CHECK][A2] ✅ PASS")

            # E. 內容消極怠工（ERR_CONTENT_LAZINESS）
            # 若字幕 < 5 字 且 VO > 15 字 → 字幕是單詞，沒有善用 17 字空間
            logger.info("[CHECK][E]  Unit %d — Insight Density 字幕密度…", unit_no)
            sub_text = unit_data.get("subtitle_zh", "") or ""
            vo_text  = unit_data.get("voice_over_zh", "") or ""
            sub_len  = len(sub_text)
            vo_len   = len(vo_text)
            if sub_len < 5 and vo_len > 15:
                err_msg = (
                    f"ERR_CONTENT_LAZINESS: subtitle_zh={sub_len}字 {sub_text!r} < 5字"
                    f"，VO={vo_len}字 > 15字 — 字幕為單詞型，資訊密度不足，需重構為 Insight 小句"
                )
                errors.append(err_msg)
                critical_fail = True
                logger.warning("[CHECK][E]  ❌ REJECT — %s", err_msg)
            else:
                hint = "✅" if sub_len >= 8 else "⚠️ 建議拉長至 8+ 字"
                logger.info("[CHECK][E]  %s PASS (subtitle=%d字: %r, VO=%d字)",
                            hint, sub_len, sub_text, vo_len)

            # B. 繁體唯一性 (ERR_SIMPLIFIED_ZH)
            logger.info("[CHECK][B]  Unit %d — 繁簡體檢查…", unit_no)
            simp_found = False
            for field in ("voice_over_zh", "subtitle_zh", "phenomenon", "mechanism"):
                val = unit_data.get(field, "") or ""
                simp_hits = _SENTINEL_SIMP_ZH_RE.findall(val)
                if simp_hits:
                    err_msg = f"ERR_SIMPLIFIED_ZH: {field} 含簡體字 {sorted(set(simp_hits))}"
                    errors.append(err_msg)
                    simp_found = True
                    logger.warning("[CHECK][B]  ❌ %s", err_msg)
            if not simp_found:
                logger.info("[CHECK][B]  ✅ PASS")

            # A-3. 視覺主體名詞優先（首詞是否為具體名詞）
            logger.info("[CHECK][A3] Unit %d — 視覺主體名詞優先…", unit_no)
            first_word = prompt_text.split(',')[0].split()[0].lower() if prompt_text else ""
            _VERB_STARTS = {
                'emphasizing', 'showing', 'revealing', 'displaying', 'featuring',
                'highlighting', 'depicting', 'capturing', 'creating', 'exploring',
            }
            if first_word in _VERB_STARTS:
                errors.append(f"ERR_NO_PHYSICAL_NOUN: prompt starts with verb '{first_word}'")
                logger.warning("[CHECK][A3] ❌ REJECT — prompt 以動詞開頭: %r", first_word)
            else:
                logger.info("[CHECK][A3] ✅ PASS (first token: %r)", first_word)

            if errors:
                logger.warning(
                    "[SENTINEL] 🚨 Unit %d REJECT — errors=%s\n   image_prompt: %r",
                    unit_no, errors, prompt_text[:100]
                )
                # 若有 image_prompt 的生物/抽象問題 → 呼叫 Gemini 修正
                needs_fix = any(
                    "ERR_BIO_TERM" in e or "ERR_ABSTRACT_NOUN" in e
                    or "ERR_NO_PHYSICAL_NOUN" in e
                    for e in errors
                )
                if needs_fix and prompt_text:
                    logger.info("[SENTINEL] 🔧 呼叫 Gemini 重新物理實體化 Unit %d…", unit_no)
                    fixed = await self._sentinel_fix_image_prompt(
                        prompt_text, notes, aspect_ratio, unit_no,
                        bio_hits=bio_hits, abstract_hits=abstract_hits,
                    )
                    if fixed:
                        if isinstance(ip, dict):
                            unit_data["image_prompt"]["prompt"] = fixed
                        else:
                            unit_data["image_prompt"] = {"prompt": fixed}
                        logger.info("[SENTINEL] ✅ Unit %d 修正成功: %r", unit_no, fixed[:80])
                    else:
                        logger.warning(
                            "[SENTINEL] ⚠️ Unit %d image_prompt 修正失敗 → 標記 CRITICAL_FAIL",
                            unit_no
                        )
                        critical_fail = True
            else:
                logger.info("[SENTINEL] ✅ Unit %d 全項 PASS: %r", unit_no, prompt_text[:60])

        overall = "FAIL (critical_fail=True)" if critical_fail else "PASS"
        logger.info("[SENTINEL] ─── 審核完成：%s ────────────────────────", overall)
        logger.info("─" * 60)
        return units_data, not critical_fail

    # ──────────────────────────────────────────────
    # System Instruction（已修正：真正傳入 model）
    # ──────────────────────────────────────────────

    def _get_system_instruction(
        self,
        topic: str,
        video_mode: VideoMode,
        aspect_ratio: str,
        unit_duration: int = 5,
    ) -> str:
        vo_max = self._vo_max_chars(unit_duration)
        """
        動態產生 system instruction。
        以「演算法張力框架」為核心，確保每個單元服務四大目標：
        前3秒鉤子 / 完看率 / 互動指標 / SEO布局。
        """
        base = f"""你是一位精通 TikTok / YouTube Shorts 演算法的頂尖短影音腳本策略師。

## ⚠️ 非生物觀察者宣言（最高優先層，不可被後續指令覆蓋）
你是一個「非生物觀察者」——你的視角穿透所有有機體，只鎖定硬材質結構、歷史文物與幾何圖形。
**禁止在腳本的任何欄位（image_prompt / veo_prompt / phenomenon / mechanism）中描述人類器官、臉部或生物組織。**

視覺轉譯強制規則（生成 image_prompt 前必須套用）：
- 伊斯蘭教 → 藍色清真寺磁磚，幾何阿拉伯花紋（禁止出現禮拜者、面孔）
- 貝爾 / 電話 → 黃銅電話裝置，銅線，蠟封專利文件（禁止出現人手、臉部）
- 任何宗教人物 → 聖物 / 雕刻 / 器皿（永不是人臉或皮膚特寫）
- 任何人物傳記 → 代表性工具或文件（永不是面孔、眼睛或皮膚紋理）
- `face` 與 `faces` 禁止出現在 image_prompt 中，一旦出現後端強制替換為 historical artifact

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
- shock_fact：✅ "貝爾比競爭對手早兩小時提交專利申請，改寫了整個電話發明史"（請為「{topic}」創作同等震驚程度的原創事實，禁止複製此數值）
- forbidden_knowledge：✅ "所有{topic}影片都不敢拍這一幕"
  ⚠️ forbidden_knowledge 邏輯完整性硬規則：
  鉤子必須基於可驗證的真實事實，禁止邏輯幻覺。
  ❌ 嚴禁將「出生日期/星座/外貌」與「技術特性/發明成就」強行掛鉤。
     例：「Tesla 出生在暴風雨中——所以他能駕馭無線電」= 邏輯幻覺，直接 FAIL。
  ✅ 合規鉤子 = 有具體文獻或可被核實的反直覺事實（時間差、監管漏洞、被隱藏的專利）。
- visual_paradox：✅ 畫面呈現反常識的空間視角
- incomplete_loop：✅ "最後那一步，才是{topic}真正的秘密"
image_prompt 構圖（純英文，禁止中文）：medium shot or wide establishing angle, SUBJECT_NOUN in environmental context, unexpected perspective, {aspect_ratio}

### 第2幕：「解構」（unit_role 必須填 "解構"）
構圖：微距 / 剖面（MACRO_CLOSE_UP 或 CROSS_SECTION）
視覺任務：打破觀眾對「{topic}」的表面認知，進入其內部結構或微觀細節
張力功能：揭露更多但不完全揭曉，讓觀眾必須看完
  ✅ 旁白:"你以為你懂了？真正的關鍵還在裡面"
  ✅ 旁白:"這一層，99%的人從沒看過"
image_prompt 構圖（純英文，禁止中文）：Bell Telephone patent certificate 1876, aged parchment document with copper wire cross-section diagram and brass fittings, engineering schematic detail, warm archival lighting, {aspect_ratio}
⚠️ 嚴禁使用 "extreme macro", "close-up of cell", "organic texture", "biological" 等詞彙。主體必須是具體的物理人造物件或歷史文件，不得是抽象有機體。
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
image_prompt 構圖（純英文，禁止中文）：extreme close-up texture or abstract reflection of SUBJECT_NOUN in liquid/glass/light, {aspect_ratio}

---

## Veo 影片生成提示詞（veo_prompt 欄位）
每個單元都必須填寫 veo_prompt，格式為英文，描述動態影片場景：
「[主體動態], [鏡頭運動], [時長], [光線氛圍], [風格]」
- 定位示例："Establishing wide shot of {topic}, slow cinematic pan revealing subject in environment, 3-4 second shot, dramatic side lighting, documentary cinematic style"
- 解構示例："Bell Telephone patent document 1876, slow push-in revealing copper wire cross-section schematic and engineering notation, 4-5 seconds, warm archival documentary lighting, ultra HD"（請為「{topic}」創作等效的具體工程/文件場景，禁止 extreme macro / biological / organic 等詞）
- 影響示例："Abstract reflection of {topic} in liquid surface with bokeh light play, gentle drift motion, 3 seconds, warm atmospheric lighting, artistic cinematic"

---

## 旁白（voice_over_zh）規則 — 連貫敘事，無模板
⚠️ 核心原則：三幕旁白是**同一個敘事者說的同一個故事**——開頭埋鉤、中段翻轉、結尾落點。
讀者聽完三幕應感覺像聽了一段完整的口述，而不是三個獨立的廣告台詞。
voice_over_zh 的值必須是**可以直接朗讀的中文句子**，絕不能是說明文字或帶【】的格式提示。

- 字數嚴格 ≤ {vo_max} 字（TTS 7.0字/秒 × ({unit_duration}s − 1.0s 緩衝)；超過導致跨幕重疊）
- 語調：口語有溫度，有說話停頓感，像紀錄者「第一次」親眼目睹
- 嚴禁模板句型：每幕禁止使用相同的開場方式（「你知道嗎」「沒想到」「原來是」不能三幕連用）
- 嚴禁通用填充：「就是這個，沒想到吧」「看完你就懂了」= 無效旁白
- 敘事遞進：情緒節奏必須遞進——好奇 → 懸念 → 衝擊/啟示

三幕旁白任務（針對「{topic}」原創，三幕情緒必須相互承接）：
- **定位幕**：拋出一個關於「{topic}」的反直覺事實，讓觀眾第一句話就停下來
  創作提問：關於{topic}，哪個事實是觀眾從沒想過但一聽就無法忽視的？
  情緒目標：好奇心 / 輕微不安 / 「等等，什麼？」
- **解構幕**：緊接定位幕的懸念，深入「{topic}」內部——但保留最後答案吊住觀眾
  創作提問：承接上一幕的問題，進一步揭露，但不給答案——讓觀眾必須撐到最後一幕
  情緒目標：懸念遞增 / 「還有更多？」的渴望
- **影響幕**：給出「{topic}」的最終衝擊或反轉真相，是整段的情感落點
  創作提問：聽完前兩幕後，「{topic}」帶給觀眾的那句「原來如此」是什麼具體啟示？
  情緒目標：恍然大悟 / 情緒落點 / 讓觀眾帶著這句話離開螢幕
  ❌ 禁止：「從頭再看」「收藏起來」「你學到了嗎」= 屬於 interaction_bait_text 的工作

## 字幕（subtitle_zh）規則 — 旁白的吐槽者或補充者
字幕≠旁白縮短版。字幕是旁白的**第二聲音**——對旁白進行補充、定性或反諷，產生雙聲道效果。
- 字數上限 ≤ {SUB_MAX_CHARS} 字（動態公式：min(floor(unit_sec × 3.5), 30)，{unit_duration}s 單元 = {SUB_MAX_CHARS}字）
- **【硬規則】目標範圍：8–{SUB_MAX_CHARS} 字。必須利用 {SUB_MAX_CHARS} 字空間產出具備 Insight 的完整短句。**
- 字幕可以是：衝擊定性完整句、核心數字 + 因果、反諷評語、觀眾心理聲音、完整衝擊短句
- ✅ 合規（Insight 小句）："比你想的早了兩小時"、"那個劑量正好卡在致命邊緣"、"0.03公分的關鍵震動"、"0.03公分決定聲音生死"
- ❌ 【硬性禁止】嚴禁 4 字以下的單詞字幕："生死邊界"、"救命成分"、"慢性傷害"、"藥品" → 視為空白格，直接判定 ERR_CONTENT_LAZINESS，強制重寫
- ❌ 超過 {SUB_MAX_CHARS} 字、旁白的縮短版、與旁白說同一件事
- ❌ **嚴禁截斷句末名詞或動詞**——字數超標時必須重構短句，而非刪尾字

⚠️ 17 字空間利用率硬規則（違反即觸發重生成）：
你有 {SUB_MAX_CHARS} 字的字幕空間，**必須利用 8–14 字產出具備 Insight 的短句**，例如「0.03公分的關鍵震動」。
嚴禁只寫 4 個字以下——4 字以下的字幕 = 字幕位置浪費 = 直接觸發 ERR_CONTENT_LAZINESS 並強制重跑整輪生成。
每個字幕必須能獨立回答：「觀眾看完這句話，得到了什麼他之前不知道的具體事實或因果判斷？」

## 旁白 × 字幕 協同效應（核心機制）
旁白與字幕是「張力對」——分工明確，合在一起產生 1+1>2 的心理衝擊：
- **旁白**：製造情緒張力（驚嘆 / 懸念 / 低估感）→ 讓觀眾想繼續看
- **字幕**：補充旁白沒說的核心事實，或吐槽旁白的情緒，給觀眾「截圖衝動」
- 禁止重複：說同一件事 = 浪費一個欄位，張力歸零
- 禁止割裂：毫無關聯 = 認知斷裂

✅ 協同示例（以主題「{topic}」為框架）：
  旁白："別小看這一顆。"（7字）× 字幕："它剛好卡在救命和致命之間"（13字 Insight）
  → 旁白低估感 + 字幕補出具體衝擊，觸發「到底為什麼？」截圖衝動

  旁白："你每天都在用它。"（8字）× 字幕："第一杯開始累積的慢性傷害"（13字 Insight）
  → 旁白喚起親身感 + 字幕補出時間線因果，觸發「我要停用了」留言

  旁白："沒想到，是它在救你。"（10字）× 字幕："那個成分從未獲得 FDA 主適應症認可"（17字 Insight）
  → 旁白反轉 + 字幕補出監管真相，觸發收藏分享

❌ 禁止協同失誤：
  旁白："這是救命神藥。" × 字幕："救命神藥"（重複 → 毫無張力）
  旁白："畫面真的好美。" × 字幕："生死邊界"（割裂 → 觀眾困惑）
  旁白："它是解熱鎮痛劑。" × 字幕："藥品"（2字，ERR_CONTENT_LAZINESS）
  旁白："你每天都在用它。" × 字幕："慢性傷害"（4字，ERR_CONTENT_LAZINESS）

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

## 抽象主題視覺實體化規則（必須執行）
模型只能繪製物理實體。若主題含「誕生/起源/革命/奇蹟/偉大」等抽象詞，
image_prompt.prompt 必須強制替換為對應的具體物件：
- 人物傳記 → 代表性文件/圖示（例：clinical case report, labeled anatomical diagram）
- 歷史事件 → 醫學文獻實物（例：archival medical chart, clinical specimen documentation）
- 科學發現 → 關鍵儀器（例：glass laboratory flask, measurement instrument close-up）
- 技術/醫學創新 → 核心圖解（例：molecular receptor diagram, anatomical cross-section illustration）

### 【硬規則】醫學/生理主題材質強制語彙（V33.9 — Nocturia 主題）
若主題涉及 夜間頻尿、泌尿、睡眠、荷爾蒙、生理機制 等，
image_prompt.prompt **必須** 包含以下材質關鍵字至少 2 個：
  archival cream paper / clinical teal highlight / midnight blue palette /
  painterly ink wash / film grain overlay / aged medical chart /
  anatomical cross-section / molecular pathway / labeled clinical specimen
範例（必須達到的材質感）：
  ✅ "nocturia bladder cross-section, labeled anatomical diagram, archival cream paper texture, clinical teal accent, midnight blue palette, film grain overlay, {aspect_ratio} format"
  ✅ "AVP vasopressin molecular pathway, painterly ink wash style, aged medical chart background, soft lavender hormone glow, archival scan documentation"
  ❌ 嚴禁工業/機械材質混入：brass fittings / mechanical gear / iron mechanism / riveted metal / blueprint schematic — 這些詞彙出現 = 主題錯置 = 圖像失真

❌ 絕對禁止用作視覺替代：birth, origin, miracle, life force, spirit, energy glow,
   skin-like gloss, fleshy shapes, organic tissue, biological bulbs, fingerprints

## ⚙️ 材質轉譯強制檢查（生成每個 image_prompt 前，內部必須逐步執行以下流程）

STEP 1 — 主題掃描：判斷主題「{topic}」是否包含人物 / 宗教 / 抽象概念。
  → 若是，激活「主體代理人協定」，禁止生成任何人體部位。
  → 代理載體選擇順序：Tier 1 醫學解剖圖解 → Tier 2 臨床文獻實物 → Tier 3 分子/細胞視覺化

STEP 2 — 材質合法性驗證：
  → 禁止出現：face / faces / fingers / skin / flesh / organic / biological 等詞彙
  → 禁止出現：mechanical / blueprint / gear / brass / copper wire / iron / riveted 等工業詞彙
  → 必須出現：至少 1 個醫學實體名詞（anatomical / clinical / molecular / archival / specimen…）

STEP 3 — 品牌 DNA 注入（V33.9 Nocturia 醫學配色）：
  → 科學/生理主題：末端附加「clinical teal highlight, archival scan documentation, film grain overlay」
  → 病理/症狀主題：末端附加「midnight blue palette, aged medical chart texture, painterly ink wash」
  → 分子/荷爾蒙主題：末端附加「soft lavender vasopressin glow, molecular diagram aesthetic, archival cream paper」

STEP 4 — 防演算法指紋（§7.3）：從以下詞庫隨機選 1 個加入 prompt 末端（每次呼叫必須輪替，不得固定）：
  archival scan artifact / photographic plate grain / presstype halftone dot /
  cyanotype blue / foxed paper edge texture / rotogravure print texture

## 🎲 動態隨機性指令（嚴格執行，違反視為 ERR_RHYTHM_CLONE）

每一支影片的節奏與視覺重點**必須隨機化**，嚴禁使用固定的轉場與開場模版：
- 三幕的旁白開頭禁止使用相同句型（「你知道嗎」「沒想到」「原來是」不得連續三幕出現）
- 每幕的 image_prompt 構圖角度必須不同（不得三幕皆為 close-up 或皆為 wide shot）
- 色溫偏移必須貫穿全片（定位幕偏冷 → 解構幕中性 → 影響幕高對比 或其他遞進組合）
- material_auditor.md §4.3 的防指紋詞每次生成必須從詞庫隨機選取，不得固定使用同一個詞

## 絕對規則
1. unit_role 值只能是："定位" / "解構" / "影響"（嚴格使用這三個中文字）
2. 直接輸出 JSON，禁止 markdown 標記
3. phenomenon 最多 15 字，mechanism 最多 50 字
4. voice_over_zh 嚴格 ≤ {vo_max} 字（TTS {TTS_CPS}字/秒 × {unit_duration-TTS_END_MARGIN:.1f}s，禁止跨幕），subtitle_zh 嚴格 ≤ {SUB_MAX_CHARS} 字（旁白濃縮）
5. image_prompt.prompt 必須純英文，絕對禁止任何中文字符（FLUX 模型不支援中文 prompt，中文字符會導致亂碼/跑題圖像），含 {aspect_ratio}，禁止手部人體
   ★ image_prompt.prompt 開頭第一個 token 必須是主體英語名詞（例："Great Pyramid, ...", "aspirin tablet, ..."）
   ★ 禁止以動詞/分詞（emphasizing / showing / revealing / capturing / depicting...）開頭
   ★ 禁止使用代名詞（it / its / they / their / this / that）— 必須明確寫出主體名稱
6. veo_prompt 必須英文，每個單元都必填
7. 解構幕的 veo_recommended 必須為 true，其他兩幕為 false
"""

        # ── 注入專家規範（最高優先權） ────────────────────────────────────────
        expert_guard = self._build_expert_guard_block()
        if expert_guard:
            base += (
                "\n\n---\n\n"
                "## ⚑ 最高優先權規範（.claudecode/experts/ 注入，覆蓋所有上述指令）\n\n"
                + expert_guard
            )

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
        duration_minutes: Optional[int],
        unit_duration: int = 5,
    ) -> str:
        vo_max = self._vo_max_chars(unit_duration)
        """
        建立生成 prompt，包含演算法張力框架的 JSON 格式範例。
        """
        # ── JSON 格式示範 ─────────────────────────────────────────────────────
        # 使用「阿斯匹靈」主題作為完整品質示範。
        # 重點：voice_over_zh / subtitle_zh 的語氣、長度、雙聲道效果是品質標準。
        # AI 必須為「{topic}」生成同等品質的原創內容，不可複製示範句。
        json_schema_example = f'''{{
  "units": [
    {{
      "id": "keyframe_001",
      "unit_role": "定位",
      "hook_technique": "reverse_question",
      "phenomenon": "你每天吃它退燒，但它根本不退燒",
      "mechanism": "阿斯匹靈主要機制是抑制血小板聚集，退燒不過是副作用，學名乙醯水楊酸。",
      "voice_over_zh": "你以為它是退燒藥——它從沒退過燒。",
      "subtitle_zh": "從沒退燒，副作用而已",
      "visual_description": "中景，意外低角度仰拍{topic}，確立主體的空間存在，製造反直覺視覺，100字以內",
      "image_prompt": {{
        "prompt": "SUBJECT_NOUN at unexpected low angle, medium establishing shot, dramatic side lighting, rule of thirds composition, {aspect_ratio} format, no people no text",
        "negative_prompt": "people, face, blurry, low quality, text, watermark"
      }},
      "emotional_tone": "震驚、強烈好奇",
      "camera_mode": "MEDIUM_SHOT",
      "seo_keywords": ["{topic}知識", "為什麼{topic}", "{topic}真相", "{topic}功效"],
      "interaction_trigger": null,
      "interaction_bait_text": null,
      "hashtag_strategy": {{
        "core_content": ["#{topic}", "#{topic}知識"],
        "algorithm_traffic": ["#冷知識", "#你不知道的事"],
        "emotional": ["#震驚了", "#原來如此"],
        "youtube_priority": ["#Shorts", "#{topic}", "#震驚了"],
        "tiktok_priority": ["#原來如此", "#{topic}知識", "#冷知識"]
      }},
      "veo_prompt": "SUBJECT_NOUN at dramatic low angle, slow cinematic pan revealing subject, 3-4 second shot, dramatic side lighting, documentary cinematic style",
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
      "phenomenon": "一片{{UNIQUE_VALUE}}，阻斷心肌梗塞",
      "mechanism": "心臟病發作時嚼碎服用，{{UNIQUE_VALUE}}內溶解凝血塊；但超過一粒的量，反而觸發胃出血。",
      "voice_over_zh": "一片{{UNIQUE_VALUE}}，剛好卡在救命和致命之間。",
      "subtitle_zh": "{{UNIQUE_VALUE}}就是那條線",
      "visual_description": "微距剖面視角，進入{topic}的內部結構或微觀細節，科學紀錄片風格，100字以內",
      "image_prompt": {{
        "prompt": "SUBJECT_NOUN cross-section detail, internal microscopic structure reveal, scientific documentary photography, high-key lighting, dramatic crystalline texture, {aspect_ratio} format, no people",
        "negative_prompt": "people, face, blurry, low quality, text, watermark, wide shot"
      }},
      "emotional_tone": "驚訝、深度好奇",
      "camera_mode": "MACRO_CROSS_SECTION",
      "seo_keywords": ["{topic}原理", "{topic}成分", "為什麼{topic}有效", "{topic}怎麼作用"],
      "interaction_trigger": null,
      "interaction_bait_text": null,
      "hashtag_strategy": {{
        "core_content": ["#{topic}原理", "#{topic}科學"],
        "algorithm_traffic": ["#生活科學", "#知識型短片"],
        "emotional": ["#看完震驚", "#長知識了"],
        "youtube_priority": ["#Shorts", "#{topic}原理", "#看完震驚"],
        "tiktok_priority": ["#長知識了", "#{topic}科學", "#生活科學"]
      }},
      "veo_prompt": "SUBJECT_NOUN internal structure ultra-slow push-in, microscopic crystalline detail reveal, 4-5 seconds, scientific high-key lighting, ultra HD documentary",
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
      "phenomenon": "每天一顆，改變心血管壽命",
      "mechanism": "長期低劑量服用降低心血管事件與結直腸癌風險，但有胃出血風險，需醫囑方可服用。",
      "voice_over_zh": "那個堅持服用的人，多出了{{UNIQUE_VALUE}}的緩衝時間。",
      "subtitle_zh": "多出{{UNIQUE_VALUE}}的機會",
      "visual_description": "極端特寫或液面反射，呈現{topic}對感官的最終衝擊，100字以內",
      "image_prompt": {{
        "prompt": "SUBJECT_NOUN reflected in water surface close-up, bokeh light play, vibrant saturated accent color, shallow depth of field, {aspect_ratio} format, no people",
        "negative_prompt": "people, face, blurry, low quality, text, watermark"
      }},
      "emotional_tone": "滿足、驚嘆、想分享",
      "camera_mode": "EXTREME_CLOSE_UP",
      "seo_keywords": ["{topic}副作用", "{topic}能長期吃嗎", "{topic}每日劑量", "每天吃{topic}好嗎"],
      "interaction_trigger": "comment_bait",
      "interaction_bait_text": "你身邊有人每天吃阿斯匹靈嗎？他們知道自己在吃什麼嗎？",
      "hashtag_strategy": {{
        "core_content": ["#{topic}真相", "#{topic}必看"],
        "algorithm_traffic": ["#冷知識", "#生活科學"],
        "emotional": ["#原來如此", "#漲知識了"],
        "youtube_priority": ["#Shorts", "#{topic}真相", "#原來如此"],
        "tiktok_priority": ["#漲知識了", "#{topic}必看", "#冷知識", "#原來如此"]
      }},
      "veo_prompt": "SUBJECT_NOUN in water surface reflection, bokeh light drift, gentle camera float, 3 seconds, warm atmospheric lighting, artistic cinematic macro",
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
6. voice_over_zh：≤{vo_max}字（TTS {TTS_CPS}字/秒，{unit_duration}s幕−1.0s緩衝），必須是針對「{topic}」可直接朗讀的原創金句，禁止說明文字或帶【】的格式提示，禁止通用套句
7. subtitle_zh：≤{SUB_MAX_CHARS}字（{unit_duration}s×3.5CPS），旁白的吐槽/補充（不是縮短版），說旁白沒說的那一面；嚴禁截斷句末名詞或動詞
8. seo_keywords：3-5個真實繁體中文搜尋詞（搜尋引擎用，非 hashtag）
9. image_prompt.prompt：英文，{aspect_ratio}構圖，禁止手部人體
10. interaction_bait_text：影響幕必填（≤30字，針對{topic}的具體留言/分享/收藏誘餌文字），定位幕與解構幕填 null
11. hashtag_strategy：每個單元必填，依四層結構（core_content / algorithm_traffic / emotional / youtube_priority / tiktok_priority），所有標籤必須與{topic}內容相關，禁止無關熱門標籤
12. 內容數據排他性（最高優先，每條都是硬規則）：
    ① 核心數值唯一原則：任何具體數值（如「0.03公分」「2小時」「28%」「1847年」）
       只能在全片出現一次。後續單元必須提供全新的知識增量，不得複述同一數據。
    ⚠️ USED-DATA INTERCEPTOR — MANDATORY PROTOCOL:
       This is a quality gate. Violation = automatic script failure.

       STEP 1 — Before writing unit[1]: list every specific number/date/percentage
         from unit[0] in your internal scratchpad. e.g. ["0.03cm", "1847年", "28%"]
       STEP 2 — Before writing unit[2]: list all values from units[0..1].
         If unit[2] would use any value already listed → STOP, choose a DIFFERENT value.
       STEP 3 — Repeat for every subsequent unit.

       CONCRETE EXAMPLE OF FAILURE (do NOT do this):
         unit[0] voice_over: "阿斯匹靈直徑只有 0.03 公分"  ← uses 0.03公分
         unit[1] voice_over: "這 0.03 公分的藥片..."        ← ❌ REPEAT = FAIL

       CONCRETE EXAMPLE OF PASS (do this):
         unit[0]: "直徑 0.03 公分"
         unit[1]: "每天低劑量 100毫克"   ← ✅ NEW value
         unit[2]: "降低 32% 心血管風險"  ← ✅ NEW value
    ② 知識層級遞進：
       定位幕 → 反直覺事實（What：打破表面認知）
       解構幕 → 實驗過程或內部機制（How/Why：揭露因果）
       影響幕 → 歷史影響或對人的改變（So What：長遠意義）
    ③ phenomenon 標題排他：三幕標題描述的知識點必須互不重疊，
       禁止「同一事實的不同說法」（例：「差兩小時」出現在第一幕後，
       後續幕禁止再提「時間差」，必須轉向「技術細節」或「影響結果」）
    ④ 槽點唯一原則：整部影片的最大衝擊事實只能在定位幕引爆一次，
       解構幕和影響幕必須建立在此基礎上提供新視角，而非重複引爆同一槽點

品質示範（主題「阿斯匹靈」的完整輸出樣本 — voice_over_zh / subtitle_zh 的語氣與長度是標準，請為「{topic}」生成同等品質的原創內容，禁止複製示範句）：
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
        duration_minutes: Optional[int] = None,
        manual_viewpoint: Optional[str] = None,   # V31.0: 使用者手動觀點，優先權最高
    ) -> List[ObservationUnit]:
        """
        生成場景腳本。

        修正重點：
        1. 用 system_instruction 建立 GenerativeModel 實例（之前從未傳入）
        2. 提供 JSON 格式範例，確保輸出格式正確
        3. 對超長欄位截斷而非跳過，避免靜默遺失單元
        """
        print("[DEBUG] SENTINEL_CHECK_START — generate_units entered", file=sys.stderr, flush=True)
        try:
            keyframe_count = self._calculate_keyframe_count(video_mode, duration_minutes)
            # V33.9.2: 移除 != 3 的錯誤過濾，始終以 target_units 為準（前端明確指定時）
            if target_units and target_units >= 1:
                keyframe_count = min(target_units, 50)

            # Shorts 模式硬上限：最多 8 個單元（含封面共 9）
            if video_mode == VideoMode.SHORTS:
                keyframe_count = min(keyframe_count, 8)

            logger.info(f"🎬 影片模式: {video_mode.value}")
            logger.info(f"📐 畫面比例: {aspect_ratio}")
            logger.info(f"⏱️  目標時長: {duration_minutes or '未指定'} 分鐘")
            logger.info(f"🎞️  關鍵幀數量: {keyframe_count} 個")

            if video_mode == VideoMode.SHORTS:
                unit_duration = 5
            elif duration_minutes:
                unit_duration = self._calculate_unit_duration(
                    video_mode, duration_minutes, keyframe_count
                )
            else:
                unit_duration = 120 if video_mode == VideoMode.LONG else 30

            system_instruction = self._get_system_instruction(
                notes, video_mode, aspect_ratio, unit_duration
            )
            # ── V31.0 手動觀點注入（最高優先權，覆蓋 AI 立場）────────────────
            if manual_viewpoint and manual_viewpoint.strip():
                _mv = manual_viewpoint.strip()
                system_instruction += (
                    f"\n\n## ⚑ 使用者手動觀點（最高優先權 — 覆蓋所有 AI 生成立場）\n"
                    f"central_thesis 必須固定為：「{_mv}」\n"
                    f"三幕旁白的論點發展必須服務此立場，不可偏離。\n"
                    f"禁止產出任何與此立場矛盾或中性化的敘述。"
                )
                logger.info(f"📌 V31 manual_viewpoint 注入: {_mv!r}")
            logger.info(
                f"✅ system_instruction 已設定（主題：{notes}，"
                f"unit_dur={unit_duration}s，VO上限={self._vo_max_chars(unit_duration)}字）"
            )

            prompt = self._build_prompt(
                topic=notes,
                keyframe_count=keyframe_count,
                video_mode=video_mode,
                aspect_ratio=aspect_ratio,
                duration_minutes=duration_minutes,
                unit_duration=unit_duration,
            )

            cfg = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.75,
                top_p=0.9,
                max_output_tokens=8192,
            )

            # ── 腳本哨兵 while 迴圈：最多 3 次重新向 Gemini 請求生成 ──────────
            _SENTINEL_MAX_RETRIES = 3
            units_data: list[dict] = []
            sentinel_passed = False

            for _sentinel_attempt in range(1, _SENTINEL_MAX_RETRIES + 1):
                logger.info(
                    "[SENTINEL] 🔄 生成嘗試 %d/%d — 呼叫 Gemini API [%s]（逾時: 90秒）…",
                    _sentinel_attempt, _SENTINEL_MAX_RETRIES, self.model_name
                )
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.client.models.generate_content,
                            model=self.model_name,
                            contents=prompt,
                            config=cfg,
                        ),
                        timeout=90.0,
                    )
                except asyncio.TimeoutError:
                    logger.error(f"❌ Gemini API [{self.model_name}] 呼叫逾時（90秒）")
                    raise ValueError("Gemini API 回應逾時，請稍後再試")

                result_text = response.text.strip()
                if result_text.startswith("```json"):
                    result_text = result_text[7:]
                elif result_text.startswith("```"):
                    result_text = result_text[3:]
                if result_text.endswith("```"):
                    result_text = result_text[:-3]

                clean_text = _sanitize_gemini_json(result_text.strip())
                try:
                    result_json = json.loads(clean_text)
                except json.JSONDecodeError as _je:
                    logger.error(
                        "❌ Gemini JSON 解析失敗（嘗試 %d）: %s\n"
                        "   原始回應（前 600 字）:\n%s",
                        _sentinel_attempt, _je, result_text[:600],
                    )
                    raise ValueError(
                        f"Gemini 回傳格式錯誤（第 {_sentinel_attempt} 次嘗試）: {_je}"
                    ) from _je

                if isinstance(result_json, list):
                    units_data = result_json
                elif isinstance(result_json, dict):
                    units_data = result_json.get("units", [])
                else:
                    logger.error(f"未知 JSON 格式: {type(result_json)}")
                    units_data = []

                # ── 腳本哨兵審核（quality_inspector.md）──────────────────────────
                try:
                    units_data, sentinel_passed = await self.validate_script_logic(
                        units_data, notes, aspect_ratio, unit_duration
                    )
                except ValueError as _sentinel_err:
                    if "DETECTED_FINGER_GHOST" in str(_sentinel_err):
                        logger.warning(
                            "[SENTINEL] 🚨 FINGER_GHOST 攔截 — 嘗試 %d 強制重跑 Gemini",
                            _sentinel_attempt
                        )
                        print(
                            f"[SENTINEL] 🚨 FINGER_GHOST on attempt {_sentinel_attempt}/{_SENTINEL_MAX_RETRIES} — forcing Gemini retry.",
                            file=sys.stderr, flush=True
                        )
                        sentinel_passed = False
                        if _sentinel_attempt >= _SENTINEL_MAX_RETRIES:
                            raise  # 耗盡重試次數 → 向上拋出 → 400
                        continue  # 回到迴圈頂端重新呼叫 Gemini
                    raise  # 其他 ValueError（逾時等）直接拋出

                if sentinel_passed:
                    logger.info("[SENTINEL] ✅ 嘗試 %d 通過，退出迴圈", _sentinel_attempt)
                    break

                if _sentinel_attempt < _SENTINEL_MAX_RETRIES:
                    logger.warning(
                        "[SENTINEL] ⚠️ 嘗試 %d 失敗，重新向 Gemini 請求生成…",
                        _sentinel_attempt
                    )
                else:
                    logger.warning(
                        "[SENTINEL] ⚠️ 已達最大重試次數 %d，以當前結果繼續",
                        _SENTINEL_MAX_RETRIES
                    )
                    logger.warning(
                        f"⚠️ 哨兵達到最大重試次數 {_SENTINEL_MAX_RETRIES}，繼續使用當前腳本"
                    )

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

                # V33.0 YT2026 互動注入：影響幕若無 bait_text，隨機選一條
                if unit_data["unit_role"] == "影響" and not unit_data.get("interaction_bait_text"):
                    _yt2026_baits = [
                        "你覺得這改變了什麼？留言告訴我⬇️",
                        "你身邊有人知道嗎？分享給他看！",
                        "A：早知道 B：剛學到 — 留言投票",
                        "這個你會用在哪裡？留言說說看👇",
                        "這讓你想到誰？分享給他們！",
                    ]
                    unit_data["interaction_bait_text"] = random.choice(_yt2026_baits)

                # hashtag_strategy 若為 dict 保留給 Pydantic 自動轉換，若缺失則設 None
                if not isinstance(unit_data.get("hashtag_strategy"), (dict, type(None))):
                    unit_data["hashtag_strategy"] = None

                # 截斷超長欄位（避免 Pydantic max_length 驗證失敗）
                if len(unit_data.get("phenomenon", "")) > 35:
                    unit_data["phenomenon"] = unit_data["phenomenon"][:35]
                if len(unit_data.get("mechanism", "")) > 70:
                    unit_data["mechanism"] = unit_data["mechanism"][:70]

                # VO：語意重寫或分割，禁止硬截
                vo_max = self._vo_max_chars(unit_duration)
                vo = unit_data.get("voice_over_zh", "")
                logger.debug(
                    f"  VO 校驗: {len(vo)}字 ≈ {len(vo)/TTS_CPS:.1f}s / {unit_duration}s"
                    f" (上限 {vo_max}字)"
                )
                if len(vo) > vo_max:
                    part1, part2 = await self._rewrite_vo_if_needed(
                        vo, vo_max, notes, unit_data.get("unit_role", "解構")
                    )
                    unit_data["voice_over_zh"] = part1
                    if part2:
                        existing = unit_data.get("editing_notes", "") or ""
                        part2_note = f"[VO part2] {part2}"
                        unit_data["editing_notes"] = (
                            f"{existing}\n{part2_note}".strip() if existing else part2_note
                        )
                        logger.info(f"📝 VO part2 → editing_notes: {part2!r}")

                # SUB：語意濃縮，禁止硬截字（content_guard.md §2 語法強制校驗）
                # 動態上限：min(floor(unit_duration × 3.5), 30)
                sub_max = _sub_max_chars(unit_duration)
                sub = unit_data.get("subtitle_zh", "")
                if len(sub) > sub_max:
                    shortened = _vo_semantic_shorten(sub, sub_max)
                    logger.debug(
                        f"  字幕語意截斷: {sub!r} → {shortened!r}"
                        f" ({len(sub)}字 → {len(shortened)}字 / 上限 {sub_max}字)"
                    )
                    unit_data["subtitle_zh"] = shortened

                if len(unit_data.get("visual_description", "")) > 150:
                    unit_data["visual_description"] = unit_data["visual_description"][:150]
                if isinstance(unit_data.get("seo_keywords"), list):
                    unit_data["seo_keywords"] = unit_data["seo_keywords"][:5]
                if unit_data.get("interaction_bait_text") and len(unit_data["interaction_bait_text"]) > 50:
                    unit_data["interaction_bait_text"] = unit_data["interaction_bait_text"][:50]

                # V33.0 Hybrid Pulse: VO-anchored duration with ±15-20% jitter
                _vo_final  = unit_data.get("voice_over_zh", "") or ""
                _vo_nat_s  = len(_vo_final) / TTS_CPS + TTS_END_MARGIN
                _jitter    = random.uniform(0.15, 0.20) * random.choice([-1, 1])
                _pulse_dur = _vo_nat_s * (1 + _jitter)
                # Clamp: no more than ±25% from the container duration
                _pulse_dur = max(unit_duration * 0.75, min(unit_duration * 1.25, _pulse_dur))
                unit_data["duration_seconds"] = max(1, round(_pulse_dur))

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

                # image_prompt 格式確保（禁止中文 — FLUX 模型只接受英文 prompt）
                _FALLBACK_PROMPT = (
                    "19th century vintage engineering components, brass and wood textures, "
                    f"soft natural lighting, {aspect_ratio} format"
                )
                if "image_prompt" not in unit_data or not isinstance(unit_data.get("image_prompt"), dict):
                    unit_data["image_prompt"] = {
                        "prompt": _FALLBACK_PROMPT,
                        "negative_prompt": "hands, people, face, blurry, low quality, text"
                    }
                else:
                    ip = unit_data["image_prompt"]
                    # 1. 移除 CJK（FLUX 不接受中文，會產生亂碼或跑題圖）
                    ip["prompt"]          = _strip_cjk_from_prompt(ip.get("prompt", ""))
                    ip["negative_prompt"] = _strip_cjk_from_prompt(ip.get("negative_prompt", ""))
                    # 2. 移除舊會話洩漏詞（content_guard.md §9 TOPIC_BANNED_TERMS）
                    ip["prompt"] = _sanitize_banned_terms(ip["prompt"])
                    # 3. 確保第一個 token 是英文主體名詞（visual_director.md §4）
                    ip["prompt"] = _enforce_noun_first_prompt(ip["prompt"])
                    if not ip["prompt"]:
                        ip["prompt"] = _FALLBACK_PROMPT
                    if aspect_ratio not in ip["prompt"]:
                        ip["prompt"] = f"{ip['prompt']}, {aspect_ratio} format"
                    neg = ip.get("negative_prompt", "")
                    if "hand" not in neg.lower():
                        ip["negative_prompt"] = f"{neg}, hands, people, face"
                    logger.debug(f"  image_prompt (sanitized): {ip['prompt'][:80]}")

                # V33.0 Tier assignment + visual shock for Hook unit
                _total_units = len(units_data)
                if idx == 0:
                    unit_data["tier"] = 1
                    ip = unit_data.get("image_prompt", {})
                    if isinstance(ip, dict) and ip.get("prompt"):
                        ip["prompt"] += ", extreme fast zoom burst, kinetic visual shock, high-contrast impact frame"
                elif idx == _total_units - 1:
                    unit_data["tier"] = 3
                else:
                    unit_data["tier"] = 2

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
                    vo_chars = len(unit.voice_over_zh)
                    vo_est_s = vo_chars / TTS_CPS
                    logger.info(
                        f"✅ 場景 {idx+1} [{unit.unit_role}]: {unit.phenomenon} "
                        f"| VO({vo_chars}字≈{vo_est_s:.1f}s/{unit_duration}s): {unit.voice_over_zh!r} "
                        f"| 字幕({len(unit.subtitle_zh)}字): {unit.subtitle_zh!r}"
                    )
                except Exception as e:
                    logger.error(f"❌ 單元 {idx} 驗證失敗: {e}")
                    logger.error(f"資料: {json.dumps(unit_data, ensure_ascii=False, indent=2)}")
                    continue

            # ── 單元數量鎖定（UNIT_COUNT_LOCK）────────────────────────────────
            # Gemini 有時會多產出單元；嚴格截斷至請求數量，禁止靜默溢出。
            if len(units) > keyframe_count:
                logger.warning(
                    f"⚠️ UNIT_COUNT_LOCK: Gemini 生成了 {len(units)} 個單元"
                    f"（超過請求的 {keyframe_count}），強制截斷至 {keyframe_count}"
                )
                units = units[:keyframe_count]
            elif len(units) < keyframe_count:
                logger.warning(
                    f"⚠️ UNIT_COUNT_UNDERFLOW: Gemini 只生成了 {len(units)} 個單元"
                    f"（請求 {keyframe_count}）"
                )

            logger.info(f"🎉 成功生成 {len(units)} 個場景（請求 {keyframe_count}）")
            self._check_duplicate_numbers(units, notes)
            return units

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失敗: {e}")
            raise ValueError(f"Gemini 回應格式錯誤: {e}")
        except Exception as e:
            logger.error(f"生成場景失敗: {e}")
            raise

    @staticmethod
    def _check_duplicate_numbers(units: list, topic: str) -> None:
        """
        Warn if multiple units share identical numbers in phenomenon/voice_over_zh.
        Helps catch narrative repetition (e.g. same '0.03公分' in hook + body).
        """
        num_pat = re.compile(r'\d+(?:\.\d+)?')
        seen: dict[str, int] = {}
        for i, unit in enumerate(units):
            text = f"{unit.phenomenon} {unit.voice_over_zh}"
            for n in num_pat.findall(text):
                if len(n) > 1:  # skip trivial single digits
                    if n in seen:
                        logger.warning(
                            f"⚠️ DUPLICATE_NUMBER [{topic}]: '{n}' 出現在"
                            f" unit[{seen[n]}]({units[seen[n]].unit_role}) 和"
                            f" unit[{i}]({unit.unit_role}) — 敘事遞進可能不足"
                        )
                    else:
                        seen[n] = i


# 全局服務實例
observation_service = ObservationService()


def get_observation_service() -> ObservationService:
    return observation_service
