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

const HUMOR_MARKERS  = ["哈","笑","蠢","傻","瘋","搞笑","OMG","WTF","崩潰","傻眼"];
const ACTION_MARKERS = ["衝","爆","噴","砸","踢","摔","撞","炸","飛","崩"];
const MONEY_MARKERS  = ["錢","財","寶","金","收","賺","價值","帝國","征服"];

export function sfxForScene(
  voText: string, subText: string,
  sceneIdx: number, totalScenes: number,
): string {
  const text = voText + subText;
  if (sceneIdx === 0)               return "Whoosh → Impact drum [SUB IN aligned]";
  if (sceneIdx === totalScenes - 1) return "Cha-ching → Whoosh [SUB IN aligned]";
  if (MONEY_MARKERS.some(m => text.includes(m))) return "Cha-ching [SUB IN aligned]";
  if (ACTION_MARKERS.some(m => text.includes(m))) return "Squish → Impact [SUB IN aligned]";
  if (HUMOR_MARKERS.some(m => text.includes(m)))  return "Slide-whistle → Boing [SUB IN aligned]";
  return "Soft pad → Whoosh [SUB IN aligned]";
}

// ── Camera action (semantic, no Ken Burns) ────────────────────────────────────

const FAST_PAN_KW   = ["衝","跑","奔","飛","快","速","追","逃","掃"];
const TILT_UP_KW    = ["發現","揭露","升起","崛起","天空","壯觀","宏偉","誕生"];
const SHAKY_KW      = ["哈","笑","蠢","傻","瘋","崩潰","搞笑","吐槽","OMG","WTF"];
const DOLLY_ZOOM_KW = ["震驚","恐懼","驚","嚇","詭異","扭曲","深淵","顫抖"];

const CAMERA_POOL = [
  "Dolly Zoom — push in + warp",
  "Fast Pan — lateral whip cut",
  "Tilt Up — reveal shot 0→90°",
  "Macro Shaky Cam — handheld extreme close-up",
  "Arc Shot — 90° orbit around subject",
  "Push In — slow creep 1.0×→1.4×",
];

export function dynamicCamera(voText: string, sceneIdx: number): string {
  if (SHAKY_KW.some(k => voText.includes(k)))    return "Macro Shaky Cam — handheld extreme close-up";
  if (DOLLY_ZOOM_KW.some(k => voText.includes(k))) return "Dolly Zoom — push in + warp";
  if (FAST_PAN_KW.some(k => voText.includes(k)))   return "Fast Pan — lateral whip cut";
  if (TILT_UP_KW.some(k => voText.includes(k)))    return "Tilt Up — reveal shot 0→90°";
  // Deterministic rotation for remaining scenes
  return CAMERA_POOL[sceneIdx % CAMERA_POOL.length];
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
