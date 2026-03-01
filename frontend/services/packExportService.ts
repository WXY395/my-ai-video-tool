/**
 * Pack Export Service
 * 產生符合 pack_meta_v1 規格的素材包 zip。
 */

import JSZip from 'jszip';
import { ObservationUnit } from '../types';
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

// ── CapCut Editing Guide ───────────────────────────────────────────────────────

const FPS        = 30;
const SEG_SEC    = 5;
const SEG_FRAMES = SEG_SEC * FPS; // 150 frames

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
  return (txt.length >= 8 ? txt : txt + '觀測說明').slice(0, 18);
}

function subText(unit: ObservationUnit, topic: string, i: number): string {
  if (unit.subtitle_zh) return unit.subtitle_zh;
  const core = topic.slice(0, 5);
  const txt  = `${core}${i + 1}`;
  return (txt.length >= 3 ? txt : txt + '摘要').slice(0, 8);
}

/**
 * 產生 EDITING_GUIDE_CAPCUT.txt 全文。
 * 段落數 = units.length（保證與 keyframes 一致）。
 */
function buildCapcutGuide(
  topic: string,
  videoMode: string,
  units: ObservationUnit[],
): string {
  const N           = units.length;
  const totalFrames = N * SEG_FRAMES;
  const bgm         = bgmLine(videoMode, totalFrames);

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
    '',
  ];

  for (let i = 0; i < N; i++) {
    const u    = units[i];
    const base = i * SEG_FRAMES;
    const pad  = String(i + 1).padStart(3, '0');
    const beat = beatLabel(i, N);

    out.push(D);
    out.push(`  SEGMENT ${pad}  [${beat}]  ${u.phenomenon ?? ''}`);
    out.push(D);
    out.push('');
    out.push(`  IMAGE         keyframe_${pad}.png`);
    out.push(`  IMAGE IN      ${framesToTC(base)}`);
    out.push(`  IMAGE OUT     ${framesToTC(base + SEG_FRAMES)}`);
    out.push('');
    out.push(`  VO IN         ${framesToTC(base + 10)}`);
    out.push(`  VO OUT        ${framesToTC(base + 98)}`);
    out.push(`  VO TEXT       ${voText(u, topic, i)}`);
    out.push('');
    out.push(`  SUB IN        ${framesToTC(base + 15)}`);
    out.push(`  SUB OUT       ${framesToTC(base + 83)}`);
    out.push(`  SUB TEXT      ${subText(u, topic, i)}`);
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
  /** Diagnostic log 列表，寫入 run_log.json */
  logs?: string[];
}

/**
 * 組裝素材包 zip 並觸發瀏覽器下載。
 *
 * 輸出檔名：pack_<slug>_<YYYYMMDD_HHMMSS>_<mode>_<aspect>.zip
 * 解壓根目錄：pack_<slug>_<timestamp>/
 */
export async function exportPack(opts: ExportPackOptions): Promise<void> {
  const { topic, projectName, videoMode, aspectRatio, coverImageUrl, units, logs = [] } = opts;

  const now       = new Date();
  const slug      = slugify(projectName || topic);
  const timestamp = fmtTimestamp(now);
  const aspectSafe = aspectRatio.replace(':', 'x');   // "9:16" → "9x16"
  const zipName   = `pack_${slug}_${timestamp}_${videoMode}_${aspectSafe}.zip`;
  const rootDir   = `pack_${slug}_${timestamp}`;

  const zip = new JSZip();
  const imagesFolder = zip.folder(`${rootDir}/images`);
  if (!imagesFolder) throw new Error('JSZip: 無法建立 images/ 資料夾');

  // ── 1. Cover ────────────────────────────────────────────────────────────────
  imagesFolder.file('cover.png', await urlToBytes(coverImageUrl));

  // ── 2. Keyframes（只含有 imageUrl 的 units）────────────────────────────────
  const readyUnits = units.filter(u => u.imageUrl);

  const keyframesMeta: { id: number; path: string }[] = [];
  const imagePromptsMeta: { id: number; prompt: string }[] = [];

  for (let i = 0; i < readyUnits.length; i++) {
    const unit = readyUnits[i];
    const pad  = String(i + 1).padStart(3, '0');
    const filename = `keyframe_${pad}.png`;

    imagesFolder.file(filename, await urlToBytes(unit.imageUrl!));

    keyframesMeta.push({ id: i + 1, path: `images/${filename}` });

    const prompt = typeof unit.image_prompt === 'string'
      ? unit.image_prompt
      : (unit.image_prompt?.prompt ?? '');
    imagePromptsMeta.push({ id: i + 1, prompt });
  }

  // ── 3. meta.json ─────────────────────────────────────────────────────────────
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
      units_count: readyUnits.length,   // 與 keyframes 長度一致
      created_at: now.toISOString(),
    },
    assets: {
      cover: { path: 'images/cover.png' },
      keyframes: keyframesMeta,
    },
    prompts: {
      topic_prompt: topic,
      image_prompts: imagePromptsMeta,
    },
  };
  zip.file(`${rootDir}/meta.json`, JSON.stringify(meta, null, 2));

  // ── 4. README_START_HERE.txt ─────────────────────────────────────────────────
  const readmeLines = [
    `OBSERVATION PACK — ${projectName || topic}`,
    `Generated : ${now.toLocaleString()}`,
    `Mode      : ${videoMode}  |  Aspect: ${aspectRatio}  |  Units: ${readyUnits.length}`,
    '',
    'STRUCTURE',
    '─────────',
    '  images/cover.png                → 封面圖',
    ...keyframesMeta.map(k =>
      `  ${k.path.padEnd(36)}→ Keyframe ${k.id}`,
    ),
    '  meta.json                        → 機器可讀元數據 (pack_meta_v1)',
    '  run_log.json                     → 本次生成日誌',
    '',
    'NEXT STEPS',
    '──────────',
    '  1. 匯入 images/ 到剪輯軟體（CapCut / Premiere / DaVinci Resolve）',
    '  2. 依照 meta.json > assets.keyframes 排列鏡頭順序',
    '  3. 參考各 unit 的 voice_over_zh 錄製旁白',
    '  4. 字幕以 subtitle_zh 為準，不與旁白重疊',
    '',
    '─────────────────────────────────────────────',
    'Pack schema : pack_meta_v1',
    'Generator   : Shorts Factory React',
  ];
  zip.file(`${rootDir}/README_START_HERE.txt`, readmeLines.join('\n'));

  // ── 5. EDITING_GUIDE_CAPCUT.txt ──────────────────────────────────────────────
  zip.file(
    `${rootDir}/EDITING_GUIDE_CAPCUT.txt`,
    buildCapcutGuide(topic, videoMode, readyUnits),
  );

  // ── 6. run_log.json ───────────────────────────────────────────────────────────
  const runLog = {
    generated_at : now.toISOString(),
    video_mode   : videoMode,
    aspect_ratio : aspectRatio,
    units_total  : units.length,
    units_exported: readyUnits.length,
    log_entries  : logs,
  };
  zip.file(`${rootDir}/run_log.json`, JSON.stringify(runLog, null, 2));

  // ── 7. 產生 zip 並下載 ────────────────────────────────────────────────────────
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
