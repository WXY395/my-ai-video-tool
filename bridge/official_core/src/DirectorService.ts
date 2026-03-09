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

// ── Veo decision ─────────────────────────────────────────────────────────────

const VEO_TRIGGER_VERBS = new Set([
  "流出","破碎","閃爍","奔跑","爆炸","衝","噴","顫抖","燃燒","墜落","崩潰",
]);

export function needsVeo(voText: string, sceneIdx: number, totalScenes: number): boolean {
  if (sceneIdx === 0) return true;                      // Hook forced
  if (sceneIdx === totalScenes - 1) return true;        // Payoff forced
  return [...VEO_TRIGGER_VERBS].some(v => voText.includes(v));
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

const SFX_TRANSITION = "Whoosh + deep impact drum";
const SFX_HUMOR      = "Cartoon boing / slide-whistle";
const SFX_AMBIENT    = "Soft atmospheric pad";
const HUMOR_MARKERS  = ["哈","笑","蠢","傻","瘋","搞笑","OMG","WTF","崩潰","傻眼"];

export function sfxForScene(
  voText: string, subText: string,
  sceneIdx: number, totalScenes: number,
): string {
  if (sceneIdx === 0 || sceneIdx === totalScenes - 1) return SFX_TRANSITION;
  if (HUMOR_MARKERS.some(m => (voText + subText).includes(m))) return SFX_HUMOR;
  return SFX_AMBIENT;
}

// ── Camera action ─────────────────────────────────────────────────────────────

export function staticAction(): string {
  return "Camera slow zoom in (1.2×) | Ken Burns effect";
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
