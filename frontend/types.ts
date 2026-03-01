// ===== Pacing Profiles =====

export interface PacingProfile {
  id: 'shorts' | 'medium' | 'long';
  label: string;
  /** 建議秒數範圍 [min, max] */
  target_duration_range: [number, number];
  /** 建議 Unit 數量範圍 [min, max] */
  unit_range: [number, number];
  /** 結構比例（加總為 1） */
  beats: {
    hook: number;
    body: number;
    payoff: number;
  };
  /** 最多幾個 Veo 片段 */
  veo_budget: number;
  caption_density: 'sparse' | 'normal' | 'dense';
  cut_frequency: 'slow' | 'medium' | 'fast';
}

// ===== 觀測單元相關 =====

export interface ImagePrompt {
  prompt: string;
  negative_prompt: string;
}

export interface MotionGuidance {
  effect: 'ken_burns' | 'zoom_in' | 'zoom_out' | 'pan_left' | 'pan_right' | 'static';
  duration_seconds: number;
  transition_to_next: string;
  notes?: string;
}

export interface ActivityEvent {
  time_range: string;
  action: string;
}

export interface ObservationUnit {
  id: string;
  
  // 核心內容
  phenomenon: string;
  mechanism: string;
  
  // 語音與字幕
  voice_over_zh: string;
  subtitle_zh: string;
  
  // 視覺與圖片
  visual_description: string;
  image_prompt: ImagePrompt | string;  // 支援舊格式
  
  // 情緒與氛圍
  emotional_tone: string;
  
  // 時間線與鏡頭
  start_timecode: string;
  duration_seconds: number;
  camera_mode: string;
  in_scene_timeline: ActivityEvent[];
  
  // 編輯資訊
  editing_notes?: string;

  // 運鏡建議（完整版）
  motion_guidance?: MotionGuidance | null;
  is_keyframe?: boolean;

  // 演算法張力欄位
  unit_role?: '定位' | '解構' | '影響' | 'content' | string;
  hook_technique?: 'reverse_question' | 'shock_fact' | 'forbidden_knowledge' | 'visual_paradox' | 'incomplete_loop' | string;
  seo_keywords?: string[];
  interaction_trigger?: 'comment_bait' | 'share_trigger' | 'replay_hook' | 'save_reminder' | string;

  // Veo 影片生成
  veo_prompt?: string;
  veo_recommended?: boolean;

  // UI 狀態
  imageUrl?: string;
  isGeneratingImage?: boolean;
  imageError?: string;

  // 舊版相容性（可選）
  hook?: string;
  coreMessage?: string;
  core_message?: string;
  visualDescription?: string;
  negativePrompt?: string;
  scriptOutline?: string[];
  imageStatus?: 'pending' | 'generating' | 'complete' | 'error';
}

// ===== SEO 相關 =====

export interface SEOMetadata {
  youtube_shorts_title_zh: string;
  tiktok_title_zh: string;
  description_zh: string;
  tags: string[];
}

export interface ExportPackage {
  cover_prompt: string;
  seo: SEOMetadata;
}

// ===== 應用狀態 =====

export interface AssetGenerationState {
  isProcessing: boolean;
  isExporting: boolean;
  units: ObservationUnit[];
  error: string | null;
  coverImageUrl?: string;
  isGeneratingCover: boolean;
  exportPkg?: ExportPackage;
}

// ===== 配置選項 =====

export enum VisualDensity {
  LOW = 'LOW',
  MEDIUM = 'MEDIUM',
  HIGH = 'HIGH',
}

export enum InformationFocus {
  SINGLE_SUBJECT = 'SINGLE_SUBJECT',
  RELATIONSHIP = 'RELATIONSHIP',
  CONTRAST = 'CONTRAST',
  BOUNDARY = 'BOUNDARY',
}

export enum GuidanceLevel {
  NORMAL = 'NORMAL',
  MINIMAL = 'MINIMAL',
  HEAVY = 'HEAVY',
}

export enum ImageIntent {
  EDITING_FIRST = 'EDITING_FIRST',
  DIRECT_OUTPUT = 'DIRECT_OUTPUT',
}

export enum ReferencePlane {
  UNDEFINED = 'UNDEFINED',
  HORIZONTAL = 'HORIZONTAL',
  VERTICAL = 'VERTICAL',
}

export enum ScaleCue {
  NONE = 'NONE',
  HUMAN = 'HUMAN',
  COMMON_OBJECT = 'COMMON_OBJECT',
}

export enum VisualContinuity {
  CONSISTENT_FRAMING = 'CONSISTENT_FRAMING',
  DYNAMIC_VARIATION = 'DYNAMIC_VARIATION',
}

export interface ObservationConfig {
  unitCount: number;
  visualDensity: VisualDensity;
  informationFocus: InformationFocus;
  guidanceLevel: GuidanceLevel;
  imageIntent: ImageIntent;
  referencePlane: ReferencePlane;
  scaleCue: ScaleCue;
  visualContinuity: VisualContinuity;
}