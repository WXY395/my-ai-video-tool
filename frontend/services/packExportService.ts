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

  // ── 5. run_log.json ───────────────────────────────────────────────────────────
  const runLog = {
    generated_at : now.toISOString(),
    video_mode   : videoMode,
    aspect_ratio : aspectRatio,
    units_total  : units.length,
    units_exported: readyUnits.length,
    log_entries  : logs,
  };
  zip.file(`${rootDir}/run_log.json`, JSON.stringify(runLog, null, 2));

  // ── 6. 產生 zip 並下載 ────────────────────────────────────────────────────────
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
