/**
 * DirectorService.ts — V35.7 Plan B
 * 1:1 port of bridge/main.py Director class.
 * Pure logic: no API calls, no file I/O.
 */

export const SMPTE_FPS = 30;
export const MAX_SEGMENT_CHARS = 10;
export const VO_CHAR_DURATION = 0.19;   // seconds per character
export const VO_LEAD_IN       = 0.3;    // seconds
export const VO_TAIL          = 0.5;    // seconds

export interface SceneSpec {
  chapter:    string;
  prompt:     string;
  filename:   string;
  veo_prompt: string;
}

export interface AlignedScene extends SceneSpec {
  vo_text:    string;
  scene_idx:  number;
}

// ── SMPTE ────────────────────────────────────────────────────────────────────

/** Frames = round(ms / 1000 * fps). Returns HH:MM:SS:FF */
export function msToSmpte(ms: number, fps = SMPTE_FPS): string {
  const totalFrames = Math.round(ms / 1000 * fps);
  const ff      = totalFrames % fps;
  const totalS  = Math.floor(totalFrames / fps);
  const h       = Math.floor(totalS / 3600);
  const m       = Math.floor((totalS % 3600) / 60);
  const s       = totalS % 60;
  return [h, m, s].map(n => String(n).padStart(2, "0")).join(":") +
         ":" + String(ff).padStart(2, "0");
}

export function floatToSmpte(seconds: number): string {
  return msToSmpte(seconds * 1000);
}

// ── Duration ─────────────────────────────────────────────────────────────────

/** 0.3s lead-in + 0.19s/char + 0.5s tail → seconds */
export function voDuration(voText: string): number {
  return VO_LEAD_IN + voText.length * VO_CHAR_DURATION + VO_TAIL;
}

/** Convert whole-frame count to ms (avoids cumulative float drift). */
export function frameToMs(frames: number): number {
  return Math.round(frames * 1000 / SMPTE_FPS);
}

// ── Dynamic scene duration ────────────────────────────────────────────────────
// Each scene occupies [startF, startF + durationF).
//   VO IN  = startF + 9
//   SUB IN = startF + 15
//   VO OUT = startF + 9 + voFrames
//   Scene end (breath) = VO OUT + breathFrames  →  clamped [45f, 120f]

const VO_F_PER_CHAR = SMPTE_FPS * VO_CHAR_DURATION;  // 5.7 f/char
const VO_IN_F       = 9;
const BREATH_F_NORMAL  = 10;   // 1/3 s
const BREATH_F_VEO     = 25;   // midpoint of 20-30 f spec
const MIN_SCENE_F      = 45;   // 1.5 s
const MAX_SCENE_F      = 120;  // 4.0 s

const HUMOR_DUR_KW  = ["哈","笑","蠢","傻","瘋","搞笑","OMG","WTF","崩了","笑死","不行"];
const VISUAL_DUR_KW = ["金字塔","帝國","文明","宏偉","壯觀","一統","征服","神祇","大沙漠","尼羅河"];

/**
 * Returns total scene duration in WHOLE FRAMES.
 * isVeo / SUB punchline → extended breath (20–30f).
 * Clamped to [1.5s, 4.0s].
 */
export function sceneDurationFrames(
  voText:  string,
  subText: string,
  isVeo:   boolean,
): number {
  const combined  = voText + subText;
  const voF       = Math.round(voText.length * VO_F_PER_CHAR);
  const hasHumor  = HUMOR_DUR_KW.some(k => combined.includes(k));
  const hasVisual = VISUAL_DUR_KW.some(k => combined.includes(k));
  const bonusF    = (hasHumor ? 9 : 0) + (hasVisual ? 6 : 0);   // 0.3s / 0.2s
  const breathF   = (isVeo || hasHumor) ? BREATH_F_VEO : BREATH_F_NORMAL;
  const total     = VO_IN_F + voF + bonusF + breathF;
  return Math.max(MIN_SCENE_F, Math.min(MAX_SCENE_F, total));
}

// ── Script segmentation ───────────────────────────────────────────────────────

const SPLIT_RE = /[。，、！？；…\n]+/;

/** Split text into ≤10 char segments (mirrors Python Director.segment_script) */
export function segmentScript(text: string): string[] {
  const rawParts = text.split(SPLIT_RE);
  const segments: string[] = [];
  for (const raw of rawParts) {
    let part = raw.trim();
    if (!part) continue;
    while (part.length > MAX_SEGMENT_CHARS) {
      segments.push(part.slice(0, MAX_SEGMENT_CHARS));
      part = part.slice(MAX_SEGMENT_CHARS);
    }
    if (part) segments.push(part);
  }
  return segments;
}

// ── Veo anchor logic ─────────────────────────────────────────────────────────

/**
 * Returns 0-based indices of scenes that get Veo video.
 * N≤4: [0, N-1]
 * 5≤N≤8: [0, round(N/2)-1, N-1]
 * N≥9: [0, round(N/2)-1, round(0.8*N)-1, N-1]
 */
export function veoScenes(n: number): number[] {
  if (n <= 4)  return [0, n - 1];
  if (n <= 8)  return [0, Math.round(n / 2) - 1, n - 1];
  return [0, Math.round(n / 2) - 1, Math.round(0.8 * n) - 1, n - 1];
}

export function needsVeo(voText: string, sceneIdx: number, totalScenes: number): boolean {
  return veoScenes(totalScenes).includes(sceneIdx);
}

export function dioramaVeoPrompt(prompt: string, chapter: string): string {
  return (
    `Surreal miniature diorama, 3D clay texture figurines, macro lens close-up, ` +
    `tilt-shift bokeh, slapstick physical comedy action: ` +
    `${prompt.slice(0, 120)}. ` +
    `Scene chapter: ${chapter}. ` +
    `Absurd humorous physical movement, clay stop-motion feel, vibrant studio lighting.`
  );
}

// ── Visual metaphor ───────────────────────────────────────────────────────────

const METAPHOR_MAP = new Map<string, string>([
  ["攝護腺", "a crimson sphere tightly wrapped in straws, pearls clogging a boba tube"],
  ["壓力",   "a water balloon or pressure cooker on the verge of bursting"],
  ["發炎",   "a smouldering ember or glowing red coal radiating heat"],
  ["尿液",   "a golden stream cutting through dry sand"],
  ["膀胱",   "a translucent water balloon stretched to its limit"],
  ["荷爾蒙", "a molecular key fitting a glowing lock"],
  ["神經",   "electric sparks jumping along a frayed wire"],
  ["血管",   "a highway of rushing red cars at rush hour"],
  ["細菌",   "tiny green invaders storming a walled city"],
  ["腫瘤",   "a dark seed growing inside a translucent sphere"],
  ["藥物",   "a golden capsule floating through a river of cells"],
  ["手術",   "precise mechanical arms operating on a glowing core"],
  ["老化",   "a clock face with accelerating hands, leaves turning brown"],
  ["免疫",   "armoured knights defending a glowing castle gate"],
]);

export function extractMetaphor(text: string): string {
  for (const [kw, metaphor] of METAPHOR_MAP) {
    if (text.includes(kw)) return metaphor;
  }
  return "";
}

// ── SFX ──────────────────────────────────────────────────────────────────────

// SFX driven primarily by SUB text (the sharpened punchline)
const SFX_BOING_KW    = ["哈","笑","蠢","傻","瘋","搞笑","OMG","WTF","不行","死了","崩了","笑死"];
const SFX_CASH_KW     = ["錢","財","寶","金","收","賺","搖錢","帝國","征服","贏","發財","cha"];
const SFX_HAMMER_KW   = ["打","砸","撞","擊","衝","爆","炸","飛","崩","摔","踢","一統"];
const SFX_SYSBOOT_KW  = ["登入","開機","啟動","伺服器","系統","矩陣","AI","科技","誕生","開始"];

export function sfxForScene(
  voText: string, subText: string,
  _sceneIdx: number, _totalScenes: number,
): string {
  // SUB text first (punchline), then VO fallback
  for (const src of [subText, voText]) {
    if (SFX_BOING_KW.some(k => src.includes(k)))    return "Boing";
    if (SFX_CASH_KW.some(k => src.includes(k)))     return "Cash Register";
    if (SFX_HAMMER_KW.some(k => src.includes(k)))   return "Hammer Impact";
    if (SFX_SYSBOOT_KW.some(k => src.includes(k)))  return "System Boot";
  }
  return "Magic Chime";  // default: wonder / discovery
}

// ── Camera action — CapCut International built-in only ───────────────────────

const CC_SHAKE_KW   = ["哈","笑","蠢","傻","瘋","崩潰","搞笑","OMG","WTF","吐槽","不行"];
const CC_WHIP_KW    = ["衝","跑","奔","飛","快","速","追","逃","一統","打"];
const CC_ZOOMIN_KW  = ["發現","揭露","誕生","崛起","開機","啟動","揭開"];
const CC_ZOOMOUT_KW = ["全","整","宏","壯","帝國","文明","天下","世界"];

const CC_POOL = ["Zoom In", "Zoom Out", "Whip", "Shake", "Slide"];

export function dynamicCamera(voText: string, sceneIdx: number): string {
  if (CC_SHAKE_KW.some(k => voText.includes(k)))   return "Shake";
  if (CC_WHIP_KW.some(k => voText.includes(k)))    return "Whip";
  if (CC_ZOOMIN_KW.some(k => voText.includes(k)))  return "Zoom In";
  if (CC_ZOOMOUT_KW.some(k => voText.includes(k))) return "Zoom Out";
  return CC_POOL[sceneIdx % CC_POOL.length];
}

/** @deprecated use dynamicCamera() */
export function staticAction(): string {
  return dynamicCamera("", 0);
}

// ── 1:1 Scene alignment ───────────────────────────────────────────────────────

/** Pad or trim scenes to match vo_lines count, inject scene filenames. */
export function alignScenes(
  voLines: string[],
  scenes:  SceneSpec[],
  topic:   string,
): AlignedScene[] {
  const n = voLines.length;
  const base: SceneSpec[] = [...scenes.slice(0, n)];
  while (base.length < n) {
    const i = base.length;
    base.push({
      chapter:    `Auto_Segment_${String(i + 1).padStart(2, "0")}`,
      prompt:     `Visual representation of "${topic}" scene ${i + 1}`,
      filename:   `scene_${String(i + 1).padStart(3, "0")}.png`,
      veo_prompt: `Cinematic scene for "${topic}", scene ${i + 1}.`,
    });
  }
  return base.map((s, i) => ({
    ...s,
    filename:  `scene_${String(i + 1).padStart(3, "0")}.png`,
    vo_text:   voLines[i],
    scene_idx: i,
  }));
}
