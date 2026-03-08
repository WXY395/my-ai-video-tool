/**
 * Pack Export Service
 * 產生符合 pack_meta_v1 規格的素材包 zip。
 */

import JSZip from 'jszip';
import { ObservationUnit, UnitPlanEntry } from '../types';
import { VideoMode, AspectRatio } from './geminiService';

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * 將任意字串轉成 ASCII-safe slug：只允許 [a-z0-9-_]。
 * 其他字元（含中文）一律替換為 `-`，連續 `-` 合併，頭尾修剪。
 */
export function slugify(text: string): string {
  const ascii = text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')   // 去除 accent
    .replace(/[^a-z0-9\-_\s]/g, '-')  // 非 ASCII-safe → -
    .replace(/\s+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 24);
  // 全中文等無 ASCII 字元時，用 unicode code point 組成短 hash 作為 fallback
  if (!ascii) {
    const hash = Array.from(text)
      .slice(0, 4)
      .map(c => c.codePointAt(0)!.toString(36))
      .join('');
    return hash.slice(0, 12) || 'obs';
  }
  return ascii;
}

/** YYYYMMDD_HHMMSS */
function fmtTimestamp(d: Date): string {
  const p = (n: number, l = 2) => String(n).padStart(l, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

/**
 * data URL 或 HTTP URL → Uint8Array。
 * data URL：直接 atob decode。
 * HTTP URL：fetch → arrayBuffer。
 */
async function urlToBytes(url: string): Promise<Uint8Array> {
  if (url.startsWith('data:')) {
    const b64 = url.split(',')[1];
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch image: ${url}`);
  return new Uint8Array(await res.arrayBuffer());
}

// ── Shorts Cuts ───────────────────────────────────────────────────────────────

interface CropRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface CropPresetEntry {
  keyframe: number;        // 1-indexed
  img_w: number;
  img_h: number;
  zoom: number;
  cut_a: CropRect;         // center crop
  cut_b: CropRect;         // highest-detail grid cell (or rule-of-thirds fallback)
  cut_b_score: number;     // grayscale-variance score of winning cell
  cut_b_fallback: boolean; // true when rule-of-thirds fallback was used
  overlap_ratio: number;   // intersection(A,B)/area(B) — should be ≤ DIVERSITY_OVERLAP_MAX
  b_choice_rank: number;   // 1=top cell, 2=2nd, 3=3rd, 0=rule-of-thirds fallback
}

const SHORTS_MAX_ZOOM  = 1.25;
const SHORTS_MIN_ROI_W = 600;
const DETAIL_GRID      = 3;    // 3×3 grid scan
const DETAIL_THRESHOLD = 150;  // variance below this → rule-of-thirds upper-third fallback
const DIVERSITY_OVERLAP_MAX    = 0.6;   // max allowed intersection(A,B)/area(B)
const DIVERSITY_DIST_MIN_RATIO = 0.15; // min centre-to-centre distance / roiW

/**
 * Step 2-B feature flag.
 * false (default) — skip images/cuts/*, crop_presets.json, and cut timecode
 *   sequence in EDITING_GUIDE; guide references images/full/* only.
 * true  — enable full Shorts cuts pipeline (re-enable after Step 2-C QA).
 * Crop code is NOT removed; only gated by this flag.
 */
const ENABLE_SHORTS_CUTS = false;

/**
 * Terms leaked from previous sessions (eye/lens topic) that must be stripped
 * from ALL prompts before writing to meta.json, regardless of goal.
 */
const TOPIC_BANNED_TERMS = [
  'crystallin', 'lens cortex', 'cataract', 'protein strand',
  'refraction anomaly', 'optical aberration', 'photorealistic microscopy style',
  'crystallin fiber', 'crystallin layer', 'crystallin deposit',
  'lens deposit', 'cortex surface', 'microscopy style',
];

/**
 * Strip TOPIC_BANNED_TERMS from any prompt.
 * Applied to all image_prompts (cover, KF001, KF002, KF003) before writing to meta.json.
 */
function sanitizeImagePrompt(prompt: string): string {
  let s = prompt;
  for (const term of TOPIC_BANNED_TERMS) {
    s = s.replace(new RegExp(',?\\s*' + term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'), '');
  }
  return s.replace(/,(\s*,)+/g, ',').trim().replace(/,\s*$/, '').replace(/^,\s*/, '');
}

// ── Variant-mode library ───────────────────────────────────────────────────

type VariantMode = 'BIO' | 'OBJECT' | 'PHENOM';

/**
 * Topic keyword rules → VariantMode.
 * Matches Chinese and English keywords; defaults to BIO.
 */
function selectVariantMode(topic: string): VariantMode {
  const t = topic.toLowerCase();
  if (/生物|昆蟲|蟲|蜻蜓|蝴蝶|蜘蛛|甲蟲|蜜蜂|螞蟻|植物|苔蘚|蕨|細菌|微生物|動物|鳥|魚|藻|真菌|孢子|細胞|組織|皮膚|羽毛|鱗片|角質|insect|dragonfly|butterfly|spider|beetle|bee|ant|plant|moss|fern|bacteria|microbe|animal|bird|fish|algae|fungi|spore|cell|tissue|skin|feather|scale|chitin/.test(t)) return 'BIO';
  if (/晶體|礦物|金屬|玻璃|陶瓷|塑膠|纖維|岩石|砂|土壤|木材|紙|合金|聚合物|crystal|mineral|metal|glass|ceramic|plastic|fiber|stone|rock|sand|soil|wood|paper|alloy|polymer|composite|textile|concrete/.test(t)) return 'OBJECT';
  if (/光|火|水|霧|雲|電|化學|氣泡|物理|光學|折射|繞射|反射|泡|煙|塵|水滴|氣流|聲波|磁場|電場|light|fire|water|fog|cloud|electric|chemical|bubble|physics|optical|refract|diffract|reflect|smoke|dust|droplet|airflow|wave|magnetic|plasma/.test(t)) return 'PHENOM';
  return 'BIO';
}

/**
 * Three variant-mode libraries. {TOPIC_SUBJECT} is replaced with the
 * actual topic string at inject time — no topic is hardcoded here.
 *
 * Each mode shares the same four observation tasks (a/b/c/d):
 *   a = micro surface texture
 *   b = structural / boundary detail
 *   c = optical property / anomaly
 *   d = material / compositional contrast
 */
const VARIANT_LIBRARIES: Record<VariantMode, Record<'a' | 'b' | 'c' | 'd', string>> = {
  BIO: {
    a: 'BIO_SURFACE_TEXTURE, {TOPIC_SUBJECT} surface micro texture, biological membrane or cuticle detail, extreme macro close-up, photorealistic macro photography',
    b: 'BIO_BOUNDARY_DETAIL, {TOPIC_SUBJECT} structural boundary, joint or vein edge contour, micro-scale border anomaly, photorealistic macro photography',
    c: 'BIO_OPTICAL_PROPERTY, {TOPIC_SUBJECT} iridescent or refractive surface anomaly, micro-scale optical contrast, specular highlight, photorealistic macro photography',
    d: 'BIO_MATERIAL_CONTRAST, {TOPIC_SUBJECT} adjacent tissue material contrast, micro-scale surface heterogeneity, photorealistic macro photography',
  },
  OBJECT: {
    a: 'OBJ_GRAIN_TEXTURE, {TOPIC_SUBJECT} surface grain and micro texture, material crystal or lattice detail, extreme macro close-up, photorealistic macro photography',
    b: 'OBJ_FRACTURE_BOUNDARY, {TOPIC_SUBJECT} edge fracture or cleavage boundary, structural break micro detail, photorealistic macro photography',
    c: 'OBJ_SPECULAR_ANOMALY, {TOPIC_SUBJECT} specular highlight inconsistency, surface refraction or gloss contrast, micro-scale optical aberration, photorealistic macro photography',
    d: 'OBJ_LAYER_CONTRAST, {TOPIC_SUBJECT} material layer contrast, surface vs subsurface strata difference, micro-scale composition, photorealistic macro photography',
  },
  PHENOM: {
    a: 'PHN_MICRO_TEXTURE, {TOPIC_SUBJECT} fine micro texture within phenomenon, structural detail at micro scale, extreme macro close-up, photorealistic macro photography',
    b: 'PHN_EDGE_BOUNDARY, {TOPIC_SUBJECT} phenomenon boundary transition, micro-scale interface detail, sharp phase contrast, photorealistic macro photography',
    c: 'PHN_OPTICAL_EFFECT, {TOPIC_SUBJECT} optical effect within phenomenon, light interaction micro detail, interference or diffraction pattern, photorealistic macro photography',
    d: 'PHN_MATERIAL_CONTRAST, {TOPIC_SUBJECT} material or phase contrast, micro-scale compositional difference within phenomenon, photorealistic macro photography',
  },
};

// ── KF001 anchor + body/cover prompt builders ────────────────────────────────

/**
 * Regex matching style / lighting / format / quality / framing terms.
 * Used to skip non-subject segments when extracting the KF001 anchor.
 * No `g` flag — safe to call `.test()` multiple times without lastIndex drift.
 */
const ANCHOR_SKIP_RE =
  /chiaroscuro|dramatic|moody|low[\s-]key|dark\s+atmosphere|dark\s+shadow|deep\s+shadow|silhouette|noir|underexposed|cinematic|professional\s+photography|high\s+quality|sharp\s+focus|vibrant\s+colou?r|bokeh|depth[.-]of[.-]field|wide[- ]angle|portrait\s+format|vertical\s+composition|landscape\s+format|horizontal\s+dynamics|no\s+(people|hands|fingers|text|watermark|logo)|watermark|signature|\d+:\d+\s+(format|aspect)|portrait\s+vertical|landscape\s+horizontal|widescreen|orientation|rim\s+light|key\s+light|(extreme\s+)?macro\s+close.up|focal\s+point|thumbnail|aspect\s+ratio|well.exposed|readable\s+silhouette|clear\s+focal|photorealistic\s+macro\s+photography|wide\s+establishing|establishing\s+shot|wide\s+shot|aerial\s+view|drone\s+(shot|view)|full\s+scene/i;

/**
 * Extract up to `maxSegments` subject/visual noun segments from a KF001 image_prompt.
 * Skips style, lighting, format, quality, and framing terms; keeps descriptive nouns
 * (e.g. "dragonfly compound eye, faceted dome structure, iridescent surface").
 * Returns '' when nothing passes — caller should fall back to topic.
 */
function extractKf001Anchor(prompt: string, maxSegments = 4): string {
  const keep: string[] = [];
  for (const seg of prompt.split(',')) {
    const s = seg.trim();
    if (!s || s.length < 4) continue;
    if (ANCHOR_SKIP_RE.test(s)) continue;
    keep.push(s);
    if (keep.length >= maxSegments) break;
  }
  return keep.join(', ');
}

/**
 * Build a body (KF002) prompt from the shared KF001 subject anchor + variant-goal suffix.
 *
 * ALL body units use the SAME kf002Base (= KF001 anchor), so they stay on the same
 * subject + environment.  Only the observation-task suffix (goal a/b/c/d) differs:
 *   a = micro surface texture
 *   b = structural / boundary detail
 *   c = optical property / anomaly
 *   d = material / compositional contrast
 *
 * sanitizeImagePrompt is applied internally to strip any TOPIC_BANNED_TERMS.
 */
function buildBodyPrompt(
  kf002Base: string,
  goal: 'a' | 'b' | 'c' | 'd',
  mode: VariantMode,
  topicSubject: string,
): string {
  const template = VARIANT_LIBRARIES[mode][goal].replace(/\{TOPIC_SUBJECT\}/g, topicSubject);
  return sanitizeImagePrompt(`${kf002Base}, VARIANT_GOAL: ${template}`);
}

/**
 * Build a representative cover prompt for meta.json > prompts.cover_prompt.
 * V32.0: all portrait/rim-light/silhouette cues replaced with V32.0 industrial constants.
 */
function buildCoverPromptMeta(
  kf001Anchor: string,
  fallbackTopic: string,
  aspectRatio: string,
): string {
  const subject     = kf001Anchor || fallbackTopic;
  const orientation = aspectRatio === '9:16'
    ? 'portrait vertical orientation'
    : 'landscape horizontal widescreen orientation';
  return [
    subject,
    'macro engineering close-up capture, raw metallic component, macro industrial inspection',
    'cold industrial inspection light, sharp mechanical texture, clear focal point',
    'high micro detail focal point on most distinctive mechanical feature',
    'archival depth behind subject — subject fully lit and identifiable',
    'cold industrial background, flat archival depth-of-field',
    'vivid saturated colors on subject, archival scan quality',
    `${aspectRatio} format, ${orientation}`,
    'no people, no hands, no fingers, no face, no text, no watermark, no logo',
  ].join(', ');
}

// ── Cover hooks ───────────────────────────────────────────────────────────────

interface CoverHooks {
  title_zh:    string;
  title_en:    string;
  subtitle_zh: string;
  subtitle_en: string;
}

const HOOK_EN_MAP: Record<string, string> = {
  reverse_question:    "You Never Knew This",
  shock_fact:          "The Shocking Truth",
  forbidden_knowledge: "What They Don't Tell You",
  visual_paradox:      "See What's Really There",
  incomplete_loop:     "The Secret Revealed",
};

/**
 * 從 units[0] 推導封面文字疊層建議（ZH + EN 主標 + 副標）。
 * 不寫入圖片 — 由剪輯師在 CapCut 手動疊加文字。
 */
function buildCoverHooks(units: ObservationUnit[], topic: string): CoverHooks {
  const u = units[0];
  if (!u) {
    return {
      title_zh:    topic.slice(0, 6),
      title_en:    "You Won't Believe This",
      subtitle_zh: topic.slice(0, 12),
      subtitle_en: "Discover what's inside",
    };
  }
  const title_zh    = (u.subtitle_zh ?? '').slice(0, 8) || topic.slice(0, 6);
  const vo          = u.voice_over_zh ?? '';
  const subParts    = vo.split(/[，。！？]/);
  const subtitle_zh = (subParts[0] ?? '').slice(0, 12).trim()
    || (u.phenomenon ?? '').slice(0, 8);
  const title_en    = HOOK_EN_MAP[u.hook_technique ?? ''] ?? "You Won't Believe This";
  const subtitle_en = "Discover what's inside";
  return { title_zh, title_en, subtitle_zh, subtitle_en };
}

/** CapCut cut sequence (frames at 30 fps) */
const CUT_FULL_F = 11;   // ≈ 0.35 s
const CUT_A_F    = 17;   // ≈ 0.55 s
const CUT_B_F    = 14;   // ≈ 0.45 s

/**
 * Compute grayscale variance for one grid cell — used as a detail / texture
 * richness proxy. variance = E[x²] − E[x]²  (always ≥ 0).
 */
function regionDetailScore(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  w: number, h: number,
): number {
  const data = ctx.getImageData(x, y, w, h).data;
  const n    = data.length / 4;
  let sum = 0, sumSq = 0;
  for (let i = 0; i < data.length; i += 4) {
    const gray = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    sum   += gray;
    sumSq += gray * gray;
  }
  const mean = sum / n;
  return sumSq / n - mean * mean;
}

/** Intersection-over-B-area ratio (0–1). Same-size rects → pure overlap fraction. */
function overlapRatio(a: CropRect, b: CropRect): number {
  const ix = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
  const iy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
  return (ix * iy) / (b.w * b.h);
}

/** Euclidean distance between rect centres. */
function centerDist(a: CropRect, b: CropRect): number {
  const dx = (a.x + a.w / 2) - (b.x + b.w / 2);
  const dy = (a.y + a.h / 2) - (b.y + b.h / 2);
  return Math.sqrt(dx * dx + dy * dy);
}

interface GridCell { cx: number; cy: number; score: number }

/**
 * Scan DETAIL_GRID×DETAIL_GRID grid; return all cells sorted by score desc.
 * Used by computeShortsCrops to try rank-1 → rank-2 → rank-3 for Cut B.
 */
function rankGridCells(
  img: HTMLImageElement,
  imgW: number,
  imgH: number,
): GridCell[] {
  const canvas = document.createElement('canvas');
  canvas.width  = imgW;
  canvas.height = imgH;
  const ctx = canvas.getContext('2d')!;
  ctx.drawImage(img, 0, 0);

  const cellW = Math.floor(imgW / DETAIL_GRID);
  const cellH = Math.floor(imgH / DETAIL_GRID);
  const cells: GridCell[] = [];

  for (let gy = 0; gy < DETAIL_GRID; gy++) {
    for (let gx = 0; gx < DETAIL_GRID; gx++) {
      const rx = gx * cellW;
      const ry = gy * cellH;
      cells.push({
        cx: Math.round(rx + cellW / 2),
        cy: Math.round(ry + cellH / 2),
        score: regionDetailScore(ctx, rx, ry, cellW, cellH),
      });
    }
  }
  cells.sort((p, q) => q.score - p.score);
  return cells;
}

/**
 * Compute crop rects for a loaded image:
 *   Cut A — universal centre crop (safe framing for any subject)
 *   Cut B — highest-detail grid cell that is sufficiently diverse from A:
 *              overlap(A,B)/area(B) ≤ DIVERSITY_OVERLAP_MAX  AND
 *              centre_dist(A,B) ≥ roiW × DIVERSITY_DIST_MIN_RATIO
 *            Tries rank-1 → rank-2 → rank-3; falls back to rule-of-thirds
 *            upper-third (cx=½W, cy=⅓H) if all three fail OR image is flat.
 */
function computeShortsCrops(img: HTMLImageElement): {
  a: CropRect;
  b: CropRect;
  zoom: number;
  cut_b_score: number;
  cut_b_fallback: boolean;
  overlap_ratio: number;
  b_choice_rank: number;
} {
  const imgW = img.naturalWidth;
  const imgH = img.naturalHeight;
  const roiW = Math.max(SHORTS_MIN_ROI_W, Math.round(imgW / SHORTS_MAX_ZOOM));
  const roiH = Math.round(roiW * imgH / imgW);
  const zoom = imgW / roiW;

  // Cut A: centre
  const a: CropRect = {
    x: Math.max(0, Math.min(imgW - roiW, Math.round((imgW - roiW) / 2))),
    y: Math.max(0, Math.min(imgH - roiH, Math.round((imgH - roiH) / 2))),
    w: roiW,
    h: roiH,
  };

  const distMin = roiW * DIVERSITY_DIST_MIN_RATIO;
  const ranked  = rankGridCells(img, imgW, imgH);
  const topScore = ranked[0]?.score ?? 0;

  // Cut B: try top-3 ranked cells; pick first that passes diversity check
  let b: CropRect | null = null;
  let chosenScore  = topScore;
  let chosenRank   = 0;   // 0 = rule-of-thirds fallback
  let chosenOverlap = 0;

  if (topScore >= DETAIL_THRESHOLD) {
    const MAX_TRY = Math.min(3, ranked.length);
    for (let r = 0; r < MAX_TRY; r++) {
      const cell = ranked[r];
      const candidate: CropRect = {
        x: Math.max(0, Math.min(imgW - roiW, Math.round(cell.cx - roiW / 2))),
        y: Math.max(0, Math.min(imgH - roiH, Math.round(cell.cy - roiH / 2))),
        w: roiW,
        h: roiH,
      };
      const ov   = overlapRatio(a, candidate);
      const dist = centerDist(a, candidate);
      if (ov <= DIVERSITY_OVERLAP_MAX && dist >= distMin) {
        b            = candidate;
        chosenScore  = cell.score;
        chosenRank   = r + 1;
        chosenOverlap = ov;
        break;
      }
    }
  }

  // Fallback: rule-of-thirds upper-third
  if (!b) {
    const fbX = Math.max(0, Math.min(imgW - roiW, Math.round(imgW / 2 - roiW / 2)));
    const fbY = Math.max(0, Math.min(imgH - roiH, Math.round(imgH / 3 - roiH / 2)));
    b = { x: fbX, y: fbY, w: roiW, h: roiH };
    chosenScore   = topScore;
    chosenRank    = 0;
    chosenOverlap = overlapRatio(a, b);
  }

  return {
    a,
    b,
    zoom,
    cut_b_score:    Math.round(chosenScore * 10) / 10,
    cut_b_fallback: chosenRank === 0,
    overlap_ratio:  Math.round(chosenOverlap * 1000) / 1000,
    b_choice_rank:  chosenRank,
  };
}

/** Uint8Array → HTMLImageElement（via Blob URL） */
function loadImageEl(bytes: Uint8Array): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const blob = new Blob([bytes], { type: 'image/png' });
    const url  = URL.createObjectURL(blob);
    const img  = new Image();
    img.onload  = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Failed to load image')); };
    img.src = url;
  });
}

/** Canvas 裁切 → Uint8Array（PNG） */
function cropImageEl(
  img: HTMLImageElement,
  crop: CropRect,
  outW: number,
  outH: number,
): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const canvas = document.createElement('canvas');
    canvas.width  = outW;
    canvas.height = outH;
    const ctx = canvas.getContext('2d');
    if (!ctx) { reject(new Error('No 2D context')); return; }
    ctx.drawImage(img, crop.x, crop.y, crop.w, crop.h, 0, 0, outW, outH);
    canvas.toBlob(blob => {
      if (!blob) { reject(new Error('Canvas toBlob failed')); return; }
      blob.arrayBuffer().then(ab => resolve(new Uint8Array(ab))).catch(reject);
    }, 'image/png');
  });
}

// ── CapCut Editing Guide ───────────────────────────────────────────────────────

const FPS        = 30;
const SEG_SEC    = 5;
const SEG_FRAMES = SEG_SEC * FPS; // 150 frames

/** Chinese reading rate used to derive per-segment char limits (incl. punctuation). */
const VO_CPS  = 4.5;  // chars/sec — natural VO reading rate
const SUB_CPS = 2.2;  // chars/sec — subtitle display rate

/** 總 frames → HH:MM:SS:FF（30fps） */
function framesToTC(f: number): string {
  const p  = (n: number) => String(n).padStart(2, '0');
  const ff = f % FPS;
  const ss = Math.floor(f / FPS) % 60;
  const mm = Math.floor(f / (FPS * 60)) % 60;
  const hh = Math.floor(f / (FPS * 3600));
  return `${p(hh)}:${p(mm)}:${p(ss)}:${p(ff)}`;
}

function beatLabel(i: number, n: number): string {
  if (i === 0)       return 'HOOK';
  if (i === n - 1)   return 'PAYOFF';
  return 'BODY';
}

/**
 * emotional_tone 關鍵字 → SFX 推薦；無命中時 fallback 到 beat 預設值。
 */
function sfxRec(unit: ObservationUnit, beat: string): string {
  const tone = (unit.emotional_tone ?? '').toLowerCase();
  if (/震撼|衝擊|dramatic|impact/.test(tone))        return 'Cinematic Impact Hit';
  if (/恐懼|緊張|tension|horror|suspense/.test(tone)) return 'Suspense Sting / Tension Rise';
  if (/神秘|mystery|詭異|eerie/.test(tone))           return 'Eerie Ambient Tone';
  if (/懷舊|nostalgic|vintage|溫情/.test(tone))       return 'Vinyl Crackle / Soft Piano';
  if (/溫柔|溫暖|gentle|warm|soft/.test(tone))        return 'Soft Chime / Wind Bell';
  if (/開心|活潑|lively|energetic|輕快/.test(tone))   return 'Upbeat Swish / Pop';
  if (/悲傷|哀愁|melancholy|sad/.test(tone))          return 'Somber Low Tone';
  if (/自然|生態|nature|forest|ocean/.test(tone))     return 'Nature Ambience Layer';
  if (/科技|未來|tech|digital|cyber/.test(tone))      return 'Digital Blip / UI Sweep';
  // fallback: beat-based defaults
  if (beat === 'HOOK')   return 'Dramatic Rise / Sting';
  if (beat === 'PAYOFF') return 'Outro Impact / Resolution';
  return 'Ambient Texture / Whoosh';
}

function motionLabel(unit: ObservationUnit): string {
  if (!unit.motion_guidance) return 'NONE';
  const map: Record<string, string> = {
    ken_burns: 'Ken Burns (slow push)',
    zoom_in:   'Zoom In',
    zoom_out:  'Zoom Out',
    pan_left:  'Pan Left',
    pan_right: 'Pan Right',
    static:    'Static',
  };
  return map[unit.motion_guidance.effect] ?? unit.motion_guidance.effect;
}

/**
 * editing_notes 或 emotional_tone 的關鍵字 → CapCut 特效名稱。
 * 兩欄合併後做不區分大小寫的正規比對，依優先順序取第一個命中。
 */
function effectLabel(unit: ObservationUnit): string {
  const src = `${unit.editing_notes ?? ''} ${unit.emotional_tone ?? ''}`.toLowerCase();
  if (/震撼|衝擊|dramatic|shock|flash|閃白/.test(src))  return '閃白 (Flash White)';
  if (/恐懼|緊張|tension|horror|glitch|色差/.test(src)) return '色差 (Chromatic Aberration)';
  if (/神秘|mystery|霧|fog|haze/.test(src))             return '霧化 (Haze)';
  if (/懷舊|nostalgic|vintage|膠片/.test(src))          return '膠片顆粒 (Film Grain)';
  if (/溫柔|溫暖|gentle|warm|soft|blur|模糊/.test(src)) return '暈染邊緣 (Blur Edge)';
  if (/開心|活潑|lively|energetic|輕快/.test(src))      return '色調提亮 (Brightness Boost)';
  return 'NONE';
}

function bgmLine(mode: string, totalFrames: number): string {
  const tc = framesToTC(totalFrames);
  const styles: Record<string, string> = {
    shorts: '電子 / 氛圍  |  強度: 高',
    medium: '輕器樂 / 紀錄  |  強度: 中',
    long:   '古典 / 環境音  |  強度: 低',
  };
  const style = styles[mode] ?? '未指定  |  強度: 中';
  return `${style}  |  00:00:00:00 – ${tc}`;
}

function voText(unit: ObservationUnit, topic: string, i: number): string {
  if (unit.voice_over_zh) return unit.voice_over_zh;
  const core = topic.slice(0, 10);
  const txt  = `${core}，第${i + 1}段`;
  return txt.length >= 8 ? txt : txt + '觀測說明';
  // NOTE: no fixed char limit here — semanticCompress() enforces the dynamic limit
}

function subText(unit: ObservationUnit, topic: string, i: number): string {
  if (unit.subtitle_zh) return unit.subtitle_zh;
  const core = topic.slice(0, 5);
  const txt  = `${core}${i + 1}`;
  return txt.length >= 3 ? txt : txt + '摘要';
  // NOTE: no fixed char limit here — semanticCompress() enforces the dynamic limit
}

/**
 * Truncate `text` to `maxChars` at the last complete sentence or clause boundary.
 * Priority: 。！？ > ，、 > hard cut (last resort, flagged as truncated).
 * Returns { text, truncated } so the caller can annotate the guide.
 */
function semanticCompress(
  text: string,
  maxChars: number,
): { text: string; truncated: boolean } {
  if (text.length <= maxChars) return { text, truncated: false };
  const slice = text.slice(0, maxChars);
  // Full-sentence boundary
  const sentEnd = Math.max(
    slice.lastIndexOf('。'), slice.lastIndexOf('！'), slice.lastIndexOf('？'),
  );
  if (sentEnd > 0) return { text: slice.slice(0, sentEnd + 1), truncated: true };
  // Clause boundary
  const clauseEnd = Math.max(slice.lastIndexOf('，'), slice.lastIndexOf('、'));
  if (clauseEnd > 0) return { text: slice.slice(0, clauseEnd + 1), truncated: true };
  // Hard-cut fallback
  return { text: slice, truncated: true };
}

/**
 * Returns a warning string when `text` shares no Chinese bigram with
 * `topic + phenomenon` — likely off-topic or hallucination bleed.
 * Returns null when at least one bigram matches (consistent content).
 */
function topicGuardWarn(text: string, topic: string, phenomenon: string): string | null {
  const keySource = (topic + phenomenon).replace(/[^\u4e00-\u9fff]/g, '');
  if (keySource.length < 2) return null;
  for (let j = 0; j < keySource.length - 1; j++) {
    if (text.includes(keySource.slice(j, j + 2))) return null;
  }
  return '⚠ TOPIC_GUARD: may contain off-topic content — review';
}

/**
 * 產生 EDITING_GUIDE_CAPCUT.txt 全文。
 * 段落數 = units.length（保證與 keyframes 一致）。
 * cropPresets: Shorts 模式傳入，提供裁切時碼序列；其他模式不傳。
 */
function buildCapcutGuide(
  topic: string,
  videoMode: string,
  units: ObservationUnit[],
  unitPlan: UnitPlanEntry[],
  cropPresets?: CropPresetEntry[],
  coverHooks?: CoverHooks,
): string {
  const N           = units.length;
  const totalFrames = N * SEG_FRAMES;
  const bgm         = bgmLine(videoMode, totalFrames);
  const isShorts    = videoMode === 'shorts';

  const H = '═'.repeat(57);
  const D = '─'.repeat(57);

  const out: string[] = [
    H,
    '  EDITING_GUIDE_CAPCUT.txt',
    '  CapCut 國際版 Pro  ·  30 fps  ·  HH:MM:SS:FF',
    H,
    `  專案     : ${topic}`,
    `  模式     : ${videoMode}  |  片段數: ${N}  |  全片: ${framesToTC(totalFrames)}`,
    `  BGM      : ${bgm}`,
    '',
    '  時間偏移（相對於各段起始 IMAGE IN）',
    '  VO   +00:00:00:10 → +00:00:03:08',
    '  SUB  +00:00:00:15 → +00:00:02:23',
    '  SFX  +00:00:02:20 → +00:00:03:00',
    `  字數限制  VO ≤ ${Math.floor(SEG_SEC * VO_CPS)} 字 (4.5 CPS × ${SEG_SEC}s)  |  SUB ≤ ${Math.floor(SEG_SEC * SUB_CPS)} 字 (2.2 CPS × ${SEG_SEC}s)`,
    '',
  ];

  // ── COVER TEXT OVERLAYS ──────────────────────────────────────────────────
  const hooks = coverHooks ?? buildCoverHooks(units, topic);
  out.push(H);
  out.push('  COVER TEXT OVERLAYS');
  out.push('  （封面文字疊層建議 — 在 CapCut 封面圖上手動疊加，不寫入圖片）');
  out.push(D);
  out.push(`  ZH 主標題   : ${hooks.title_zh}`);
  out.push(`  ZH 副標題   : ${hooks.subtitle_zh}`);
  out.push(`  EN 主標題   : ${hooks.title_en}`);
  out.push(`  EN 副標題   : ${hooks.subtitle_en}`);
  out.push('');
  out.push('  ★ 字型建議');
  out.push('    主標  粗黑體 / Impact  字級 ≥ 60px  白字 + 黑色描邊 2px');
  out.push('    副標  細明體 / Noto Sans TC  字級 ≥ 36px  白字 + 半透明底條');
  out.push('  ★ 位置建議');
  out.push('    主標  畫面垂直 28–35%  水平置中');
  out.push('    副標  畫面垂直 42–48%  水平置中');
  out.push('  ★ 規則: 總字數 ≤ 10 字，禁止超出畫面邊距，禁止覆蓋主體臉部/特徵');
  out.push('');

  for (let i = 0; i < N; i++) {
    const u       = units[i];
    const base    = i * SEG_FRAMES;
    const imgPad  = String(i + 1).padStart(3, '0');
    const beat    = beatLabel(i, N);
    const plan    = unitPlan[i];
    const unitIdx = String(i).padStart(2, '0');
    const kfId    = plan?.keyframe_id ?? (beat === 'HOOK' ? 'KF001' : beat === 'PAYOFF' ? 'KF003' : 'KF002');
    const varId   = plan?.variant_id  ?? 'a';

    out.push(D);
    out.push(`  UNIT ${unitIdx}  [${beat}]  ${kfId}  ${varId}  ${u.phenomenon ?? ''}`);
    out.push(D);
    out.push('');

    // IMAGE block: Shorts uses cut timecode sequence; other modes use single full image
    if (isShorts && cropPresets?.find(p => p.keyframe === i + 1)) {
      const cutAIn  = base + CUT_FULL_F;
      const cutBIn  = cutAIn + CUT_A_F;
      const fullRtn = cutBIn + CUT_B_F;
      out.push(`  IMAGE FULL    images/full/keyframe_${imgPad}.png`);
      out.push(`  IMAGE CUT A   images/cuts/keyframe_${imgPad}_A.png`);
      out.push(`  IMAGE CUT B   images/cuts/keyframe_${imgPad}_B.png`);
      out.push(`  IMAGE IN      ${framesToTC(base)}`);
      out.push(`  CUT A IN      ${framesToTC(cutAIn)}   (+${CUT_FULL_F}f / 0.35 s)`);
      out.push(`  CUT B IN      ${framesToTC(cutBIn)}   (+${CUT_A_F}f / 0.55 s)`);
      out.push(`  FULL RTN IN   ${framesToTC(fullRtn)}   (+${CUT_B_F}f / 0.45 s)`);
      out.push(`  IMAGE OUT     ${framesToTC(base + SEG_FRAMES)}`);
    } else {
      out.push(`  IMAGE         keyframe_${imgPad}.png`);
      out.push(`  IMAGE IN      ${framesToTC(base)}`);
      out.push(`  IMAGE OUT     ${framesToTC(base + SEG_FRAMES)}`);
    }

    // ── VO / SUB — dynamic char limits, semantic compression, topic guard ──
    const voMax  = Math.floor(SEG_SEC * VO_CPS);   // e.g. floor(5×4.5)=22
    const subMax = Math.floor(SEG_SEC * SUB_CPS);  // e.g. floor(5×2.2)=11
    const { text: voFinal,  truncated: voTrunc  } = semanticCompress(voText(u, topic, i),  voMax);
    const { text: subFinal, truncated: subTrunc } = semanticCompress(subText(u, topic, i), subMax);
    const voWarn  = topicGuardWarn(voFinal,  topic, u.phenomenon ?? '');
    const subWarn = topicGuardWarn(subFinal, topic, u.phenomenon ?? '');

    out.push('');
    out.push(`  VO IN         ${framesToTC(base + 10)}`);
    out.push(`  VO OUT        ${framesToTC(base + 98)}`);
    out.push(`  VO TEXT       ${voFinal}${voTrunc ? '  [COMPRESSED]' : ''}${voWarn ? `  ${voWarn}` : ''}`);
    out.push(`  VO LIMIT      ${voMax} chars (${SEG_SEC}s × ${VO_CPS} CPS)  |  actual: ${voFinal.length}`);
    out.push('');
    out.push(`  SUB IN        ${framesToTC(base + 15)}`);
    out.push(`  SUB OUT       ${framesToTC(base + 83)}`);
    out.push(`  SUB TEXT      ${subFinal}${subTrunc ? '  [COMPRESSED]' : ''}${subWarn ? `  ${subWarn}` : ''}`);
    out.push(`  SUB LIMIT     ${subMax} chars (${SEG_SEC}s × ${SUB_CPS} CPS)  |  actual: ${subFinal.length}`);
    out.push('');
    out.push(`  SFX IN        ${framesToTC(base + 80)}`);
    out.push(`  SFX OUT       ${framesToTC(base + 90)}`);
    out.push(`  SFX REC       ${sfxRec(u, beat)}`);
    out.push('');
    out.push(`  FAKE MOTION   ${motionLabel(u)}`);
    out.push(`  EFFECT        ${effectLabel(u)}`);
    out.push(`  BGM           ${bgm}`);
    out.push('');
  }

  out.push(H);
  out.push(`  段落數驗收: ${N}  |  格式: 30fps HH:MM:SS:FF  ✓`);
  out.push(H);

  return out.join('\n');
}

// ── Public API ────────────────────────────────────────────────────────────────

export interface ExportPackOptions {
  /** 第一行筆記 / 主題，用於 slug 和 meta */
  topic: string;
  /** 可選的明確專案名稱 */
  projectName?: string;
  videoMode: VideoMode;
  aspectRatio: AspectRatio;
  coverImageUrl: string;
  /** 只有 imageUrl 非空的 unit 才會被打進 zip */
  units: ObservationUnit[];
  /** 結構計畫，寫入 meta.json > unit_plan */
  unitPlan?: UnitPlanEntry[];
  /** Diagnostic log 列表，寫入 run_log.json */
  logs?: string[];
}

/**
 * 組裝素材包 zip 並觸發瀏覽器下載。
 *
 * 輸出檔名：pack_<slug>_<YYYYMMDD_HHMMSS>_<mode>_<aspect>.zip
 * 解壓根目錄：pack_<slug>_<timestamp>/
 *
 * Shorts 模式額外輸出：
 *   images/full/   原圖
 *   images/cuts/   keyframe_###_A.png / _B.png
 *   crop_presets.json
 */
export async function exportPack(opts: ExportPackOptions): Promise<void> {
  const { topic, projectName, videoMode, aspectRatio, coverImageUrl, units, unitPlan = [], logs = [] } = opts;

  const now        = new Date();
  const slug       = slugify(projectName || topic);
  const timestamp  = fmtTimestamp(now);
  const aspectSafe = aspectRatio.replace(':', 'x');
  const zipName    = `pack_${slug}_${timestamp}_${videoMode}_${aspectSafe}.zip`;
  const rootDir    = `pack_${slug}_${timestamp}`;

  const isShorts    = videoMode === 'shorts';
  const imgRootPath = isShorts ? 'images/full' : 'images';
  const variantMode = selectVariantMode(topic); // BIO | OBJECT | PHENOM

  // ── KF001 anchor: extract subject+environment nouns from first unit ────────
  // All KF002 (body) prompts are built from this shared base → same subject.
  const kf001RawPrompt = (() => {
    const u = units[0]; // index 0 is always KF001 (hook)
    if (!u) return '';
    const ip = u.image_prompt;
    return typeof ip === 'string' ? ip : (ip?.prompt ?? '');
  })();
  const kf001Anchor   = extractKf001Anchor(kf001RawPrompt) || topic;
  const kf002Base     = kf001Anchor;  // shared subject base for ALL body units
  const coverPromptMeta = buildCoverPromptMeta(kf001Anchor, topic, aspectRatio);

  const zip = new JSZip();
  const fullImgFolder = zip.folder(`${rootDir}/${imgRootPath}`);
  if (!fullImgFolder) throw new Error('JSZip: 無法建立 images/ 資料夾');
  const cutsFolder = (isShorts && ENABLE_SHORTS_CUTS) ? zip.folder(`${rootDir}/images/cuts`) : null;

  // ── 1. Cover ──────────────────────────────────────────────────────────────
  fullImgFolder.file('cover.png', await urlToBytes(coverImageUrl));

  // ── 2. Keyframes（只含有 imageUrl 的 units）──────────────────────────────
  const readyUnits = units.filter(u => u.imageUrl);

  const keyframesMeta:    { id: number; path: string }[]   = [];
  const imagePromptsMeta: { id: number; prompt: string }[] = [];
  const cropPresetsList:  CropPresetEntry[]                 = [];

  for (let i = 0; i < readyUnits.length; i++) {
    const unit     = readyUnits[i];
    const pad      = String(i + 1).padStart(3, '0');
    const filename = `keyframe_${pad}.png`;

    const imgBytes = await urlToBytes(unit.imageUrl!);
    fullImgFolder.file(filename, imgBytes);

    // Shorts only: generate cut A / cut B derivatives via Canvas API
    if (isShorts && cutsFolder) {
      const imgEl = await loadImageEl(imgBytes);
      const { a, b, zoom, cut_b_score, cut_b_fallback, overlap_ratio, b_choice_rank } = computeShortsCrops(imgEl);
      const [aBytes, bBytes] = await Promise.all([
        cropImageEl(imgEl, a, imgEl.naturalWidth, imgEl.naturalHeight),
        cropImageEl(imgEl, b, imgEl.naturalWidth, imgEl.naturalHeight),
      ]);
      cutsFolder.file(`keyframe_${pad}_A.png`, aBytes);
      cutsFolder.file(`keyframe_${pad}_B.png`, bBytes);
      cropPresetsList.push({
        keyframe: i + 1,
        img_w: imgEl.naturalWidth,
        img_h: imgEl.naturalHeight,
        zoom,
        cut_a: a,
        cut_b: b,
        cut_b_score,
        cut_b_fallback,
        overlap_ratio,
        b_choice_rank,
      });
    }

    keyframesMeta.push({ id: i + 1, path: `${imgRootPath}/${filename}` });

    const rawPrompt = typeof unit.image_prompt === 'string'
      ? unit.image_prompt
      : (unit.image_prompt?.prompt ?? '');
    const planEntry = unitPlan[i];
    const promptId  = i + 1;
    // KF002 (body): build from shared kf002Base anchor + goal-specific observation suffix.
    //   → ALL body units stay on the same subject+environment; only task changes (a/b/c/d).
    // KF001/KF003: use unit's own rawPrompt (sanitized for topic-banned terms only).
    const finalPrompt = (planEntry?.keyframe_id === 'KF002' && planEntry.variant_goal)
      ? buildBodyPrompt(kf002Base, planEntry.variant_goal, variantMode, topic)
      : sanitizeImagePrompt(rawPrompt);
    imagePromptsMeta.push({ id: promptId, prompt: finalPrompt });
  }

  // ── 3. meta.json ──────────────────────────────────────────────────────────
  const meta = {
    version: 'pack_meta_v1',
    project: {
      topic,
      project_name: projectName || topic,
      slug,
    },
    render: {
      mode: videoMode,
      aspect_ratio: aspectRatio,
      units_count: readyUnits.length,
      created_at: now.toISOString(),
    },
    assets: {
      cover: { path: `${imgRootPath}/cover.png` },
      keyframes: keyframesMeta,
    },
    prompts: {
      topic_prompt:  topic,
      cover_prompt:  coverPromptMeta,   // mirrors backend _build_cover_prompt; uses KF001 anchor
      kf001_anchor:  kf001Anchor,       // extracted subject+environment nouns for audit/debug
      image_prompts: imagePromptsMeta,
    },
    unit_plan:    unitPlan,
    variant_mode: variantMode,   // BIO | OBJECT | PHENOM — determined from topic keywords
  };
  zip.file(`${rootDir}/meta.json`, JSON.stringify(meta, null, 2));

  // ── 4. README_START_HERE.txt ──────────────────────────────────────────────
  const structureLines = isShorts
    ? [
        `  ${imgRootPath}/cover.png               → 封面圖`,
        ...keyframesMeta.map(k => `  ${k.path.padEnd(36)}→ Keyframe ${k.id} (原圖)`),
        ...(ENABLE_SHORTS_CUTS ? [
          `  images/cuts/keyframe_###_A/B.png      → Shorts cut A / B  (各 ${cropPresetsList.length} 張)`,
          '  crop_presets.json                      → 裁切座標 (crop_presets_v1)',
        ] : []),
      ]
    : [
        '  images/cover.png                        → 封面圖',
        ...keyframesMeta.map(k => `  ${k.path.padEnd(40)}→ Keyframe ${k.id}`),
      ];

  const nextStepsLines = isShorts
    ? ENABLE_SHORTS_CUTS
      ? [
          '  1. 匯入 images/full/ 原圖與 images/cuts/ 衍生圖到 CapCut',
          '  2. 依 EDITING_GUIDE_CAPCUT.txt IMAGE 時碼排列鏡頭切換',
          '     FULL (0.35s) → CUT A (0.55s) → CUT B (0.45s) → FULL RTN',
          '  3. Cut A/B 裁切座標見 crop_presets.json',
          '  4. 旁白與字幕以各段 VO TEXT / SUB TEXT 為準',
          '     （目前未輸出獨立 VO/SRT 檔）',
        ]
      : [
          '  1. 匯入 images/full/ 原圖到 CapCut',
          '  2. 依 EDITING_GUIDE_CAPCUT.txt 逐段剪輯（Full image sequence）',
          '  3. 旁白與字幕以各段 VO TEXT / SUB TEXT 為準',
          '     （目前未輸出獨立 VO/SRT 檔）',
        ]
    : [
        '  1. 匯入 images/ 到剪輯軟體（CapCut / Premiere / DaVinci Resolve）',
        '  2. 依照 meta.json > assets.keyframes 排列鏡頭順序',
        '  3. 開啟 EDITING_GUIDE_CAPCUT.txt，依時碼逐段剪輯',
        '  4. 旁白與字幕以各段 VO TEXT / SUB TEXT 為準',
        '     （目前未輸出獨立 VO/SRT 檔）',
      ];

  const readmeLines = [
    `OBSERVATION PACK — ${projectName || topic}`,
    `Generated : ${now.toLocaleString()}`,
    `Mode      : ${videoMode}  |  Aspect: ${aspectRatio}  |  Units: ${readyUnits.length}`,
    '',
    'STRUCTURE',
    '─────────',
    ...structureLines,
    '  meta.json                        → 機器可讀元數據 (pack_meta_v1)',
    '  EDITING_GUIDE_CAPCUT.txt         → CapCut 剪輯指南 (30fps)',
    '  run_log.json                     → 本次生成日誌',
    '',
    'NEXT STEPS',
    '──────────',
    ...nextStepsLines,
    '',
    '─────────────────────────────────────────────',
    'Pack schema : pack_meta_v1',
    'Generator   : Shorts Factory React',
  ];
  zip.file(`${rootDir}/README_START_HERE.txt`, readmeLines.join('\n'));

  // ── 5. EDITING_GUIDE_CAPCUT.txt ───────────────────────────────────────────
  const coverHooks = buildCoverHooks(readyUnits, topic);
  zip.file(
    `${rootDir}/EDITING_GUIDE_CAPCUT.txt`,
    buildCapcutGuide(topic, videoMode, readyUnits, unitPlan, cropPresetsList, coverHooks),
  );

  // ── 6. crop_presets.json（Shorts only）────────────────────────────────────
  if (isShorts && cropPresetsList.length > 0) {
    zip.file(`${rootDir}/crop_presets.json`, JSON.stringify({
      version:   'crop_presets_v1',
      max_zoom:  SHORTS_MAX_ZOOM,
      min_roi_w: SHORTS_MIN_ROI_W,
      presets:   cropPresetsList,
    }, null, 2));
  }

  // ── 7. run_log.json ───────────────────────────────────────────────────────
  const runLog = {
    generated_at:   now.toISOString(),
    video_mode:     videoMode,
    aspect_ratio:   aspectRatio,
    units_total:    units.length,
    units_exported: readyUnits.length,
    log_entries:    logs,
  };
  zip.file(`${rootDir}/run_log.json`, JSON.stringify(runLog, null, 2));

  // ── 8. 產生 zip 並下載 ────────────────────────────────────────────────────
  const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE', compressionOptions: { level: 6 } });
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = zipName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);
}
