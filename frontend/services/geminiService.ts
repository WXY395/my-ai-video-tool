/**
 * Gemini API 服務（升級版）
 * 支援 Shorts + 長片模式
 */

import { ObservationUnit, ObservationConfig } from '../types';
import { DEV_SHORTS_UNIT_OVERRIDE } from '../config/pacingProfiles';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8001';

/**
 * 影片模式
 */
export type VideoMode = 'shorts' | 'medium' | 'long';

/**
 * 畫面比例
 */
export type AspectRatio = '9:16' | '16:9' | '1:1';

/**
 * 成本預估
 */
export interface CostEstimate {
  image_count: number;
  cost_per_image: number;
  total_cost: number;
  model_used: string;
}

/**
 * 運鏡建議
 */
export interface MotionGuidance {
  effect: 'ken_burns' | 'zoom_in' | 'zoom_out' | 'pan_left' | 'pan_right' | 'static';
  duration_seconds: number;
  transition_to_next: string;
  notes?: string;
}

/**
 * 生成請求參數
 */
export interface GenerateRequest {
  notes: string;
  unitCount?: number;
  videoMode?: VideoMode;
  aspectRatio?: AspectRatio;
  durationMinutes?: number;
}

/**
 * 生成結果
 */
export interface GenerateResult {
  units: ObservationUnit[];
  coverUrl: string | null;
  videoMode: VideoMode;
  aspectRatio: string;
  costEstimate: CostEstimate | null;
  productionNotes?: {
    workflow: string;
    motionEffectsIncluded: boolean;
    recommendedTools: string[];
    estimatedEditingTime: string;
  };
}

/**
 * 成本預估結果
 */
export interface CostEstimateResult {
  success: boolean;
  videoMode: VideoMode;
  aspectRatio: string;
  durationMinutes?: number;
  keyframeCount: number;
  costEstimate: {
    image_count: number;
    price_per_image: number;   // KF 單價（flux-schnell）
    kf_cost?: number;          // KF 圖片小計
    cover_cost?: number;       // 封面小計（flux-dev）
    total_cost: number;        // KF + 封面合計
    model_used: string;
    currency: string;
  };
}

/**
 * 預估成本（不實際生成）
 */
export async function estimateCost(
  notes: string,
  videoMode: VideoMode = 'shorts',
  aspectRatio: AspectRatio = '9:16',
  durationMinutes?: number
): Promise<CostEstimateResult> {
  console.log('💰 呼叫成本預估 API');
  console.log('📤 模式:', videoMode);
  console.log('📤 比例:', aspectRatio);
  console.log('📤 時長:', durationMinutes, '分鐘');

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000);

  try {
    const response = await fetch(`${API_BASE_URL}/api/observation/estimate-cost`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        rawInput: notes,
        unitCount: 0, // 由後端自動計算
        video_mode: videoMode,
        aspect_ratio: aspectRatio,
        duration_minutes: durationMinutes,
      }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    console.log('📥 成本預估回應:', response.status);

    if (!response.ok) {
      throw new Error(`成本預估失敗: ${response.status}`);
    }

    const data = await response.json();
    console.log('✅ 成本預估完成:', data);

    // 相容後端 snake_case 欄位
    return data;

  } catch (error: any) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      throw new Error('成本預估逾時（30秒），請稍後再試');
    }
    console.error('❌ 成本預估失敗:', error);
    throw new Error(error.message || '無法預估成本');
  }
}

/**
 * 生成觀測單元（升級版，支援長片）
 */
export async function generateObservationUnits(
  notes: string,
  config: ObservationConfig,
  videoMode: VideoMode = 'shorts',
  aspectRatio: AspectRatio = '9:16',
  durationMinutes?: number
): Promise<GenerateResult> {
  console.log('🚀 呼叫 Backend API（升級版）');
  console.log('📤 筆記內容:', notes);
  console.log('📤 影片模式:', videoMode);
  console.log('📤 畫面比例:', aspectRatio);
  console.log('📤 目標時長:', durationMinutes, '分鐘');

  // 驗證
  if (!notes || notes.trim().length === 0) {
    throw new Error('請輸入觀測筆記');
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 150000); // 150秒逾時

  try {
    const response = await fetch(`${API_BASE_URL}/api/observation/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        rawInput: notes,
        unitCount: (videoMode === 'shorts' && DEV_SHORTS_UNIT_OVERRIDE !== null)
          ? DEV_SHORTS_UNIT_OVERRIDE
          : config.unitCount,
        video_mode: videoMode,
        aspect_ratio: aspectRatio,
        duration_minutes: durationMinutes,
      }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    console.log('📥 回應狀態:', response.status);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail?.error || errorData.error || `API 錯誤: ${response.status}`);
    }

    const data = await response.json();
    console.log('✅ Backend 成功回應');
    console.log('📊 單元數量:', data.units?.length);
    console.log('💰 成本:', data.cost_estimate);

    if (!data.success || !data.units) {
      throw new Error('Backend 回應格式錯誤');
    }

    // 提取資訊
    const coverUrl = data.metadata?.cover_url || null;
    const costEstimate = data.cost_estimate || null;
    const productionNotes = data.metadata?.production_notes || null;

    if (coverUrl) {
      console.log('🖼️ 封面 URL:', coverUrl);
    }

    // 轉換格式
    const units: ObservationUnit[] = data.units.map((unit: any, index: number) =>
      _parseUnit(unit, index, data.units.length)
    );

    console.log('✅ 成功轉換', units.length, '個觀測單元');
    
    // 記錄運鏡建議
    const unitsWithMotion = units.filter(u => u.motion_guidance);
    console.log('🎬 運鏡建議:', unitsWithMotion.length, '個單元');

    return { 
      units, 
      coverUrl,
      videoMode: data.video_mode || videoMode,
      aspectRatio: data.aspect_ratio || aspectRatio,
      costEstimate,
      productionNotes
    };

  } catch (error: any) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      throw new Error('生成逾時（150秒），Gemini API 回應過慢，請稍後再試');
    }
    console.error('❌ 生成失敗:', error);
    throw new Error(error.message || '無法生成觀測單元');
  }
}

/**
 * 生成圖片資源（升級版，支援比例選擇）
 */
export async function generateAssetImage(
  prompt: string,
  aspectRatio: AspectRatio = '9:16',
  sceneIndex: number = 2   // V34.0: 0/1 → nano-banana-2; >=2 → flux-schnell
): Promise<string> {
  console.log('🎨 呼叫圖片生成 API');
  console.log('📤 Prompt:', prompt);
  console.log('📤 比例:', aspectRatio);

  if (!prompt || prompt.trim().length === 0) {
    throw new Error('圖片提示詞不能為空');
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 60000);

  try {
    const response = await fetch(`${API_BASE_URL}/api/image/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        prompt: prompt,
        negative_prompt: 'low quality, blurry, distorted, text, watermark, hands, fingers, people',
        aspect_ratio: aspectRatio,
        scene_index: sceneIndex,   // V34.0: 路由至正確模型
      }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    console.log('📥 圖片 API 回應狀態:', response.status);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error || `圖片生成 API 錯誤: ${response.status}`);
    }

    const data = await response.json();

    if (!data.success || !data.image_url) {
      throw new Error(data.error || '圖片生成失敗');
    }

    console.log('✅ 圖片生成成功:', data.image_url);
    return data.image_url;

  } catch (error: any) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      throw new Error('圖片生成逾時（60秒），請重試');
    }
    console.error('❌ 圖片生成失敗:', error);
    throw new Error(error.message || '無法生成圖片');
  }
}

/**
 * 獲取可用的模式和比例
 */
export async function getAvailableModes(): Promise<{
  videoModes: any[];
  aspectRatios: any[];
  models: any[];
}> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/observation/modes`);
    
    if (!response.ok) {
      throw new Error('無法獲取可用模式');
    }

    const data = await response.json();
    console.log('📋 可用模式:', data);
    
    return {
      videoModes: data.video_modes || [],
      aspectRatios: data.aspect_ratios || [],
      models: data.models || []
    };

  } catch (error: any) {
    console.error('❌ 獲取模式失敗:', error);
    // 返回預設值
    return {
      videoModes: [
        { value: 'shorts', label: 'Shorts (≤60秒)' },
        { value: 'medium', label: '中片 (3-10分鐘)' },
        { value: 'long', label: '長片 (30-60分鐘)' }
      ],
      aspectRatios: [
        { value: '9:16', label: '豎屏 (Shorts)' },
        { value: '16:9', label: '橫屏 (標準)' }
      ],
      models: []
    };
  }
}

// ── 單元解析 helper（被 generateObservationUnits 和串流版共用）──────────────────
function _parseUnit(unit: any, index: number, totalCount: number): ObservationUnit {
  return {
    id: unit.id || `unit_${index + 1}`,
    phenomenon: unit.phenomenon || unit.hook || '現象描述',
    mechanism: unit.mechanism || unit.core_message || '機制說明',
    voice_over_zh: unit.voice_over_zh || '旁白文字',
    subtitle_zh: unit.subtitle_zh || '字幕標籤',
    visual_description: unit.visual_description || unit.visualDescription || '',
    image_prompt: unit.image_prompt || { prompt: '', negative_prompt: '' },
    emotional_tone: unit.emotional_tone || unit.emotionalTone || '',
    start_timecode: unit.start_timecode || '00:00:00:00',
    duration_seconds: unit.duration_seconds || 3,
    camera_mode: unit.camera_mode || 'CLOSE_UP',
    in_scene_timeline: unit.in_scene_timeline || [],
    editing_notes: unit.editing_notes || unit.editingNotes || '',
    motion_guidance: unit.motion_guidance ? {
      effect: unit.motion_guidance.effect,
      duration_seconds: unit.motion_guidance.duration_seconds,
      transition_to_next: unit.motion_guidance.transition_to_next,
      notes: unit.motion_guidance.notes,
    } : null,
    is_keyframe: unit.is_keyframe !== false,
    unit_role: unit.unit_role || (index === 0 ? '定位' : index === totalCount - 1 ? '影響' : '解構'),
    hook_technique: unit.hook_technique || null,
    seo_keywords: unit.seo_keywords || [],
    interaction_trigger: unit.interaction_trigger || null,
    interaction_bait_text: unit.interaction_bait_text || null,
    veo_prompt: unit.veo_prompt || null,
    veo_recommended: unit.veo_recommended === true,
    imageUrl: '',
    isGeneratingImage: false,
    imageStatus: 'pending' as const,
  };
}

// ── SSE 事件型別 ──────────────────────────────────────────────────────────────
export type StreamEvent =
  | { type: 'step';  message: string }
  | { type: 'units'; units: ObservationUnit[]; cost_estimate: any; video_mode: VideoMode; aspect_ratio: string }
  | { type: 'cover'; cover_url: string; cover_prompt?: string; cover_model?: string; cover_style?: string }
  | { type: 'done';  production_notes: any; cost_estimate: any }
  | { type: 'error'; message: string };

/**
 * 生成觀測單元（SSE 串流版）
 * 透過 Server-Sent Events 即時回傳進度，可在收到 units 事件時立刻渲染卡片，
 * 收到 cover 事件時立刻渲染封面，無需等待整個流程完成。
 */
export async function generateObservationUnitsStream(
  notes: string,
  config: ObservationConfig,
  videoMode: VideoMode = 'shorts',
  aspectRatio: AspectRatio = '9:16',
  durationMinutes: number | undefined,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  if (!notes || notes.trim().length === 0) {
    throw new Error('請輸入觀測筆記');
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 180000); // 3 分鐘

  try {
    const response = await fetch(`${API_BASE_URL}/api/observation/generate-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rawInput: notes,
        unitCount: (videoMode === 'shorts' && DEV_SHORTS_UNIT_OVERRIDE !== null)
          ? DEV_SHORTS_UNIT_OVERRIDE
          : config.unitCount,
        video_mode: videoMode,
        aspect_ratio: aspectRatio,
        duration_minutes: durationMinutes,
      }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail?.error || errorData.error || `API 錯誤: ${response.status}`);
    }

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop()!; // keep incomplete last line

        for (const line of lines) {
          const trimmed = line.trimEnd();
          if (!trimmed.startsWith('data: ')) continue;
          const dataStr = trimmed.slice(6);
          if (!dataStr) continue;

          try {
            const raw = JSON.parse(dataStr);
            // Parse unit arrays before forwarding
            if (raw.type === 'units' && Array.isArray(raw.units)) {
              const units = raw.units.map((u: any, i: number) =>
                _parseUnit(u, i, raw.units.length)
              );
              onEvent({ ...raw, units } as StreamEvent);
            } else {
              onEvent(raw as StreamEvent);
            }
          } catch {
            // skip malformed SSE line
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

  } catch (error: any) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      throw new Error('串流逾時（3分鐘），請稍後再試');
    }
    throw new Error(error.message || '串流連線失敗');
  }
}

/**
 * 健康檢查
 */
export async function healthCheck(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/observation/health`);
    const data = await response.json();
    return data.status === 'healthy';
  } catch {
    return false;
  }
}