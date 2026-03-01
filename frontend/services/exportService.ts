
import JSZip from 'jszip';
import { ObservationUnit, ExportPackage } from '../types';

/**
 * Converts a base64 data URL to a Uint8Array.
 */
function base64ToUint8Array(base64: string): Uint8Array {
  const base64String = base64.split(',')[1];
  const binaryString = atob(base64String);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes;
}

/**
 * Bundles all assets into a single ZIP file for download.
 */
export const bundleAssets = async (
  units: ObservationUnit[], 
  exportPackage: ExportPackage,
  coverImageUrl: string
): Promise<Blob> => {
  const zip = new JSZip();

  // 1. IMAGES
  units.forEach((unit, index) => {
    if (unit.imageUrl) {
      const fileName = `scene_${String(index + 1).padStart(2, '0')}.png`;
      zip.file(fileName, base64ToUint8Array(unit.imageUrl));
    }
  });
  zip.file('cover_thumbnail.png', base64ToUint8Array(coverImageUrl));

  // 2. CONSOLIDATED EDITING GUIDE (Patch v1.4 enforced)
  let finalGuide = "【觀測素材剪輯清單｜CapCut 免費版專用｜30fps】\n";
  finalGuide += "=== 嚴格操作指令清單 (符合 30fps 規範) ===\n\n";
  
  units.forEach((unit, index) => {
    finalGuide += `[SCENE_${String(index + 1).padStart(2, '0')}] ${unit.start_timecode} – ${unit.end_timecode}\n`;
    finalGuide += `- 旁白內容：${unit.voice_over_zh}\n`;
    finalGuide += `- 字幕標籤：${unit.subtitle_zh} (與旁白不重疊)\n`;
    finalGuide += `- SFX 配置：${unit.sfx}\n`;
    finalGuide += `- BGM 動作：${unit.bgm}\n`;
    finalGuide += `- 剪輯路徑：${unit.editing_guidance}\n`;
    
    if (unit.veo_guidance) {
      finalGuide += `- [OPTIONAL: SAFE VEO PROMPT]\n  ZH: ${unit.veo_guidance.safe_prompt_zh}\n  EN: ${unit.veo_guidance.safe_prompt_en}\n`;
    }
    
    finalGuide += `------------------------------------\n\n`;
  });
  
  finalGuide += "\n備註：本指引僅含 CapCut 功能路徑。若找不到指定功能請明確略過。若時間對不上以旁白結束點為準。";
  zip.file('editing_guide_capcut.txt', finalGuide);

  // 3. SEO & PUBLISHING METADATA (Differentiated Titles)
  const seo = exportPackage.seo;
  let seoContent = "=== 輸出與發布元數據 (SEO Metadata) ===\n";
  seoContent += "=== 滿足 Title ≤ 40 字 / Tags = 5 / 雙語規範 ===\n\n";
  
  seoContent += `[PLATFORM_DIFFERENTIATED_TITLES]\n`;
  seoContent += `YouTube Shorts: ${seo.youtube_shorts_title_zh}\n`;
  seoContent += `TikTok Global: ${seo.tiktok_title_zh}\n`;
  seoContent += `Instagram Reels: ${seo.instagram_reels_title_zh}\n\n`;
  
  seoContent += `[HOOK_SIGNAL]\n`;
  seoContent += `ZH: ${seo.hook_sentence_zh}\n`;
  seoContent += `EN: ${seo.hook_sentence_en}\n\n`;
  
  seoContent += `[DESCRIPTION_BUFFER (Bilingual)]\n`;
  seoContent += `${seo.description_zh}\n`;
  seoContent += `${seo.description_en}\n\n`;
  
  seoContent += `[TAG_ARRAY]\n`;
  seoContent += `${seo.tags.join(' ')}\n\n`;
  
  zip.file('seo_publishing.txt', seoContent);

  return await zip.generateAsync({ type: 'blob' });
};

/**
 * Triggers the browser download for a blob.
 */
export const downloadBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};
