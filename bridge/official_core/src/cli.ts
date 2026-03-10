#!/usr/bin/env node
/**
 * cli.ts — V35.7 Plan B
 * Replaces bridge/main.py.
 * Run: npx tsx bridge/official_core/src/cli.ts "topic"
 * OR:  bash bridge/run.sh "topic"
 */
import "dotenv/config";
import { mkdirSync, writeFileSync, statSync, existsSync } from "fs";
import { join, resolve, dirname } from "path";
import { fileURLToPath } from "url";
import Replicate from "replicate";
import {
  generateSSOTOfficial,
  renderPackOfficial,
  generateImageOfficial,
  generateCoverImageOfficial,
  type SSOT,
  type ContentPack,
} from "./bridge_adapter.js";
import {
  alignScenes,
  segmentScript,
  voDuration,
  msToSmpte,
  frameToMs,
  sceneDurationFrames,
  sfxForScene,
  needsVeo,
  veoScenes,
  dioramaVeoPrompt,
  extractMetaphor,
  dynamicCamera,
  SMPTE_FPS,
  VO_CHAR_DURATION,
  type AlignedScene,
} from "./DirectorService.js";

// ── Constants ─────────────────────────────────────────────────────────────────
const __filename = fileURLToPath(import.meta.url);
const __dirname  = dirname(__filename);
// Locked to bridge/official_core/outputs regardless of cwd
const OUT_ROOT = resolve(__dirname, "../outputs");
mkdirSync(OUT_ROOT, { recursive: true });

// ── Style helpers ─────────────────────────────────────────────────────────────
const NANO_STYLE =
  "Hyper-realistic miniature diorama, macro lens photography, " +
  "clay and resin figurines with fine texture detail, " +
  "satirical arrangement, humorous subversion of history, " +
  "studio 3-point lighting, tilt-shift bokeh, vibrant saturated palette. " +
  "Surrealist diorama theatre, no flat design, no illustration, no painting, no drawing.";

const FLUX_NO_TEXT =
  "(Strictly NO letters, NO characters, NO red seals, NO text overlays, no labels, no watermarks, no stamps) " +
  "(Strictly NO letters, NO characters, NO red seals, NO text overlays, no labels, no watermarks, no stamps)";

const DIORAMA_STYLE =
  "A high-end surrealist miniature diorama captured with macro lens, " +
  "clay and resin textures, tilt-shift bokeh, soft studio 3-point lighting, " +
  "vibrant saturated colors, absolute zero text/seals. " +
  "9:16 vertical composition, cinematic depth of field, hyper-detailed craftsmanship, " +
  "no illustration, no painting, no drawing, no real human photography, no flat design.";

const NO_TEXT_PREFIX =
  "(No text, no letters, no watermarks, no logos, no symbols, no alphabet characters)";

function applyStyleFluxScene(prompt: string): string {
  return `${FLUX_NO_TEXT}\n\n${prompt.trim()}\n\n${DIORAMA_STYLE}`;
}

function applyStyleNanoScene(prompt: string): string {
  return `${NO_TEXT_PREFIX}\n\n${prompt.trim()}\n\n${NANO_STYLE}`;
}

const DIORAMA_COVER_STYLE =
  "Hyper-realistic miniature diorama cover art, macro lens photography, " +
  "clay and resin figurines, satirical and humorous historical subversion, " +
  "studio 3-point lighting, tilt-shift bokeh, vibrant saturated palette, " +
  "cinematic 9:16 vertical composition. " +
  "No flat design, no illustration, no painting, no drawing, no watermarks, no logos.";

function applyStyleCover(prompt: string, title: string): string {
  return (
    `${prompt.trim()}\n\n` +
    `If text is required, render the Traditional Chinese characters 『${title}』 ` +
    `in a bold, hand-written ink calligraphy style, integrated into the composition.\n\n` +
    DIORAMA_COVER_STYLE
  );
}

// ── SEO cleaner ───────────────────────────────────────────────────────────────
function cleanSeoTxt(text: string): string {
  return text
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*([^\n*]+?)\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/_([^\n_]+?)_/g, "$1")
    .trim();
}

// ── Timeline computation ───────────────────────────────────────────────────────
// Works entirely in FRAMES to avoid float drift.
// Each scene: [startF … startF + durationF)
//   VO  IN  = startF + 9
//   SUB IN  = startF + 15
//   VO  OUT = startF + 9 + voFrames
//   Scene end = startF + sceneDurationFrames(...)  ← start of next scene

interface SceneTc {
  startF:    number;   // scene start (absolute frames)
  voInF:     number;   // VO  IN
  subInF:    number;   // SUB IN
  voOutF:    number;   // VO  OUT
  sceneEndF: number;   // scene end  (= next scene's startF)
  durF:      number;   // scene duration in frames
}

function buildTimeline(
  scenes:        AlignedScene[],
  subtitleLines: string[],
  veoSet:        Set<number>,
): SceneTc[] {
  const timeline: SceneTc[] = [];
  let cursor = 0;
  for (let i = 0; i < scenes.length; i++) {
    const vo      = scenes[i].vo_text;
    const sub     = subtitleLines[i] ?? "";
    const isVeo   = veoSet.has(i);
    const voF     = Math.round(vo.length * SMPTE_FPS * VO_CHAR_DURATION);
    const durF    = sceneDurationFrames(vo, sub, isVeo);
    timeline.push({
      startF:    cursor,
      voInF:     cursor + 9,
      subInF:    cursor + 15,
      voOutF:    cursor + 9 + voF,
      sceneEndF: cursor + durF,
      durF,
    });
    cursor += durF;
  }
  return timeline;
}

// ── SRT builders (timeline-aware) ─────────────────────────────────────────────

function msSrtTimecode(ms: number): string {
  const h   = Math.floor(ms / 3_600_000);
  const m   = Math.floor((ms % 3_600_000) / 60_000);
  const s   = Math.floor((ms % 60_000) / 1000);
  const mil = ms % 1000;
  return (
    `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:` +
    `${String(s).padStart(2, "0")},${String(mil).padStart(3, "0")}`
  );
}

function buildVoSrt(lines: string[], tl: SceneTc[]): string {
  return lines.map((line, idx) => {
    const t = tl[idx];
    return `${idx + 1}\n${msSrtTimecode(frameToMs(t.voInF))} --> ${msSrtTimecode(frameToMs(t.voOutF))}\n${line}`;
  }).join("\n\n") + "\n";
}

function buildSubSrt(lines: string[], tl: SceneTc[]): string {
  return lines.map((line, idx) => {
    const t = tl[idx];
    return `${idx + 1}\n${msSrtTimecode(frameToMs(t.subInF))} --> ${msSrtTimecode(frameToMs(t.voOutF))}\n${line}`;
  }).join("\n\n") + "\n";
}

// ── Runbook builder (dynamic Cinematic Rhythm) ────────────────────────────────
// Scene duration = 1.5–4.0 s, driven by VO length + humor/visual weight.
// Normal breath = 10f | Veo/punchline breath = 25f (range 20–30).

const FPS = 30;

function buildRunbook(
  topic: string,
  scenes: AlignedScene[],
  subtitleLines: string[],
): string {
  const N   = scenes.length;
  const veo = new Set(veoScenes(N));
  const tl  = buildTimeline(scenes, subtitleLines, veo);

  // Total duration in seconds (for header)
  const totalFrames = tl[N - 1].sceneEndF;
  const totalSec    = (totalFrames / FPS).toFixed(1);

  const out: string[] = [
    `# Runbook — ${topic}`,
    `> V35.9 Cinematic Rhythm | ${N} scenes | ${totalSec}s total | 30fps CapCut`,
    `> Veo anchors: scenes ${[...veo].map(i => i + 1).join(", ")}`,
    `> Duration range: 1.5s–4.0s/scene | Normal breath +10f | Veo/punchline +25f`,
    "",
    `| CH | Chapter | Dur | VO IN | SUB IN | Scene OUT | Camera | SFX | Veo |`,
    `|----|---------|-----|-------|--------|-----------|--------|-----|-----|`,
  ];

  scenes.forEach((scene, i) => {
    const t       = tl[i];
    const subText = subtitleLines[i] ?? "";
    const camera  = dynamicCamera(scene.vo_text, i);
    const sfx     = sfxForScene(scene.vo_text, subText, i, N);
    const durSec  = (t.durF / FPS).toFixed(2) + "s";
    const veoMark = veo.has(i) ? "✅" : "—";
    out.push(
      `| ${String(i + 1).padStart(2)} | ${scene.chapter.slice(0, 16)} | ${durSec} | \`${msToSmpte(frameToMs(t.voInF))}\` | \`${msToSmpte(frameToMs(t.subInF))}\` | \`${msToSmpte(frameToMs(t.sceneEndF))}\` | ${camera} | ${sfx} | ${veoMark} |`,
    );
  });

  out.push("", "---", "");

  // Detailed blocks
  scenes.forEach((scene, i) => {
    const t        = tl[i];
    const subText  = subtitleLines[i] ?? "";
    const camera   = dynamicCamera(scene.vo_text, i);
    const sfx      = sfxForScene(scene.vo_text, subText, i, N);
    const isVeo    = veo.has(i);
    const metaphor = extractMetaphor(scene.vo_text + scene.prompt);
    const breathF  = t.sceneEndF - t.voOutF;
    const veoBody  = isVeo
      ? dioramaVeoPrompt(scene.veo_prompt || scene.prompt, scene.chapter) +
        ` | Suggest cutting from 6s raw: 01:00 -> 04:00`
      : "—";

    out.push(
      `### CH${String(i + 1).padStart(2, "0")}: ${scene.chapter}`,
      `| Field | Value |`,
      `|-------|-------|`,
      `| Scene | \`${msToSmpte(frameToMs(t.startF))}\` → \`${msToSmpte(frameToMs(t.sceneEndF))}\` (${(t.durF / FPS).toFixed(2)}s / ${t.durF}f) |`,
      `| VO IN / OUT | \`${msToSmpte(frameToMs(t.voInF))}\` (+9f) → \`${msToSmpte(frameToMs(t.voOutF))}\` |`,
      `| SUB IN / OUT | \`${msToSmpte(frameToMs(t.subInF))}\` (+15f) → \`${msToSmpte(frameToMs(t.voOutF))}\` |`,
      `| Breath | +${breathF}f (${(breathF / FPS * 1000).toFixed(0)}ms) |`,
      `| VO text | ${scene.vo_text} |`,
      `| SUB text | ${subText} |`,
      `| Image | \`${scene.filename}\` |`,
      `| Camera | ${camera} |`,
      `| SFX | ${sfx} |`,
      `| Veo | ${veoBody} |`,
      metaphor ? `| Metaphor | ${metaphor} |` : "",
      "",
    );
  });

  return out.filter(l => l !== null && l !== undefined).join("\n");
}

// ── Manifest builder ──────────────────────────────────────────────────────────
function buildManifest(
  topic: string,
  scenes: AlignedScene[],
  savedFiles: Record<string, string>,
  ssot: SSOT,
  pack: ContentPack,
): object {
  return {
    topic,
    version: "V35.7",
    generated_at: new Date().toISOString(),
    ssot,
    image_prompts: scenes.map((s) => ({
      chapter: s.chapter,
      filename: s.filename,
      prompt: s.prompt,
      vo_text: s.vo_text,
    })),
    saved_files: savedFiles,
    seo_txt: pack.seo_txt,
  };
}

// ── Sleep helper ──────────────────────────────────────────────────────────────
function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Main ──────────────────────────────────────────────────────────────────────
const topic = process.argv[2];
if (!topic) {
  console.error("Usage: npx tsx bridge/official_core/src/cli.ts <topic>");
  process.exit(1);
}

console.log(`\n${"=".repeat(60)}\n  V35.7 TypeScript CLI -- Topic: ${topic}\n${"=".repeat(60)}\n`);

// Phase 1: SSOT
console.log("[PHASE 1] Generating SSOT...");
const ssot = await generateSSOTOfficial(topic);
console.log(`  SSOT: ${ssot.chapter_outline.length} chapters`);

// Phase 2: ContentPack
console.log("[PHASE 2] Rendering ContentPack...");
const pack = await renderPackOfficial(ssot);

// Phase 3: Director alignment
// ContentPack has image_prompts (chapter/prompt/filename) but no vo_lines field.
// Extract VO lines: use draft_vo_srt SRT text content lines, or segment from topic.
const srtLines = pack.draft_vo_srt
  .split("\n")
  .filter((l) => l.trim() && !/^\d+$/.test(l.trim()) && !/-->/.test(l))
  .map((l) => l.trim());

const voLines: string[] =
  srtLines.length > 0 ? srtLines : segmentScript(pack.draft_vo_srt || topic);

const rawScenes = (pack.image_prompts ?? []).map((ip: any) => ({
  chapter:    ip.chapter ?? "Scene",
  prompt:     ip.prompt ?? "",
  filename:   ip.filename ?? "scene.png",
  veo_prompt: ip.veo_prompt ?? ip.prompt ?? "",
}));

const scenes = alignScenes(voLines, rawScenes, topic);
console.log(`[Director] ${scenes.length} scenes aligned 1:1 with ${voLines.length} VO lines`);

// Phase 4: Output directory
const outDir = join(OUT_ROOT, topic);
mkdirSync(outDir, { recursive: true });
const saved: Record<string, string> = {};

// Phase 5: Text outputs
const subtitleLines: string[] = pack.draft_subtitles_srt
  ? pack.draft_subtitles_srt
      .split("\n")
      .filter((l) => l.trim() && !/^\d+$/.test(l.trim()) && !/-->/.test(l))
      .map((l) => l.trim())
  : voLines.map((v) => v.slice(0, 8));

// Build shared timeline (used by both SRTs and runbook for consistency)
const veoSetForTl = new Set(veoScenes(scenes.length));
const timeline    = buildTimeline(scenes, subtitleLines, veoSetForTl);

writeFileSync(join(outDir, "draft_vo.srt"), buildVoSrt(voLines, timeline), "utf8");
saved["draft_vo.srt"] = join(outDir, "draft_vo.srt");

writeFileSync(join(outDir, "subtitles.srt"), buildSubSrt(subtitleLines, timeline), "utf8");
saved["subtitles.srt"] = join(outDir, "subtitles.srt");

writeFileSync(join(outDir, "seo.txt"), cleanSeoTxt(pack.seo_txt ?? ""), "utf8");
saved["seo.txt"] = join(outDir, "seo.txt");

writeFileSync(join(outDir, "runbook.md"), buildRunbook(topic, scenes, subtitleLines), "utf8");
saved["runbook.md"] = join(outDir, "runbook.md");

console.log("[Text] draft_vo.srt, subtitles.srt, seo.txt, runbook.md -- done");

// Phase 6: Cover image (Nano Banana 2 — gemini-3.1-flash-image-preview + imageSize=1K)
console.log("\n[COVER] Generating via gemini-3.1-flash-image-preview...");
const coverPrompt = applyStyleCover(pack.cover_prompt ?? `Epic cinematic image about ${topic}`, topic);
const coverBytes  = await generateCoverImageOfficial(coverPrompt);
writeFileSync(join(outDir, "cover.png"), coverBytes);
saved["cover.png"] = join(outDir, "cover.png");
console.log(`  Saved: cover.png  (${coverBytes.length.toLocaleString()} bytes)`);

// Phase 7: scene_001 (Nano Banana style, no text)
const scene1   = scenes[0];
const s1Prompt = applyStyleNanoScene(scene1.prompt);
console.log(`\n[scene_001] Generating via gemini-2.5-flash-image...`);
const s1Bytes  = await generateImageOfficial(s1Prompt);
writeFileSync(join(outDir, scene1.filename), s1Bytes);
saved[scene1.filename] = join(outDir, scene1.filename);
console.log(`  Saved: ${scene1.filename}  (${s1Bytes.length.toLocaleString()} bytes)`);

// Phase 8: scene_002+ via Replicate Flux-schnell
const replicate = new Replicate({ auth: process.env.REPLICATE_API_TOKEN });

let cooldownCount = 0;
for (let i = 1; i < scenes.length; i++) {
  const scene  = scenes[i];
  const destPath = join(outDir, scene.filename);
  if (existsSync(destPath)) {
    console.log(`\n[${scene.filename}] exists — skipping (delete to force regenerate).`);
    saved[scene.filename] = destPath;
    continue;
  }
  const styled = applyStyleFluxScene(scene.prompt);
  console.log(`\n[${scene.filename}] Flux-schnell...`);
  const output = await replicate.run("black-forest-labs/flux-schnell", {
    input: {
      prompt:        styled,
      aspect_ratio:  "9:16",
      output_format: "png",
      num_outputs:   1,
    },
  }) as unknown as string[];
  const url = Array.isArray(output) ? output[0] : String(output);
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`Fetch failed for ${scene.filename}: ${resp.status} ${resp.statusText}`);
  }
  const buf  = Buffer.from(await resp.arrayBuffer());
  writeFileSync(join(outDir, scene.filename), buf);
  saved[scene.filename] = join(outDir, scene.filename);
  console.log(`  Saved: ${scene.filename}  (${buf.length.toLocaleString()} bytes)`);

  cooldownCount++;
  if (cooldownCount % 5 === 0 && i < scenes.length - 1) {
    console.log("  [5/120 cooldown] waiting 120s...");
    await sleep(120_000);
  }
}

// Final manifest with all image paths
writeFileSync(
  join(outDir, "final_manifest.json"),
  JSON.stringify(buildManifest(topic, scenes, saved, ssot, pack), null, 2),
  "utf8",
);
saved["final_manifest.json"] = join(outDir, "final_manifest.json");

console.log(`\n${"=".repeat(60)}`);
console.log(`  V35.7 COMPLETE -- ${Object.keys(saved).length} files`);
console.log(`  Output: ${outDir}`);
console.log(`${"=".repeat(60)}\n`);

// Print file list
for (const [name, path] of Object.entries(saved)) {
  const size = statSync(path).size;
  console.log(`  ${name.padEnd(30)} ${size.toLocaleString()} bytes`);
}
