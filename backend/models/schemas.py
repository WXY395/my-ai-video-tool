"""
資料結構定義（Pydantic Models）- 升級版
支援 Shorts + 長片
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum


# ===== 新增：內容格式 =====

class ContentFormat(str, Enum):
    """內容格式"""
    SHORTS = "9:16"  # Shorts（豎屏）
    MEDIUM = "16:9"  # 中片（橫屏）
    LONG = "16:9"    # 長片（橫屏）


class VideoMode(str, Enum):
    """影片模式"""
    SHORTS = "shorts"        # ≤60秒，3個單元
    MEDIUM = "medium"        # 3-10分鐘，8-15個關鍵幀
    LONG = "long"           # 30-60分鐘，15-30個關鍵幀


class MotionEffect(str, Enum):
    """運鏡效果"""
    KEN_BURNS = "ken_burns"      # Ken Burns（緩慢推進）
    ZOOM_IN = "zoom_in"          # 放大
    ZOOM_OUT = "zoom_out"        # 縮小
    PAN_LEFT = "pan_left"        # 向左平移
    PAN_RIGHT = "pan_right"      # 向右平移
    STATIC = "static"            # 靜態


# ===== 觀測單元相關 =====

class ObservationNotesInput(BaseModel):
    """觀測筆記輸入（升級版）"""
    notes: str = Field(..., description="觀測原始筆記", alias="rawInput")
    target_units: int = Field(default=3, ge=1, le=50, description="目標單元數量（自動根據模式調整）", alias="unitCount")
    style_preference: str = Field(default="default", description="風格偏好")
    
    # 新增欄位
    video_mode: VideoMode = Field(default=VideoMode.SHORTS, description="影片模式")
    aspect_ratio: ContentFormat = Field(default=ContentFormat.SHORTS, description="畫面比例")
    duration_minutes: Optional[int] = Field(None, description="目標時長（分鐘），用於長片")
    # V31.0 — 手動觀點注入（優先權高於 AI 生成）
    manual_viewpoint: Optional[str] = Field(
        None,
        description="使用者手動輸入的核心立場（≤ 50 字）。注入後覆蓋 AI 的 central_thesis，優先權最高。",
        max_length=50,
    )

    class Config:
        populate_by_name = True


class ImagePrompt(BaseModel):
    """圖片提示詞"""
    prompt: str = Field(..., description="FLUX 提示詞（英文）")
    negative_prompt: str = Field(default="low quality, blurry, distorted", description="負面提示詞")


class ActivityEvent(BaseModel):
    """活動事件（場景時間線）"""
    time_range: str = Field(..., description="時間範圍", example="00:00:00 - 00:00:03")
    action: str = Field(..., description="動作描述")


class MotionGuidance(BaseModel):
    """運鏡指導（新增）"""
    effect: MotionEffect = Field(..., description="推薦運鏡效果")
    duration_seconds: int = Field(..., description="建議展示時長（秒）")
    transition_to_next: str = Field(default="fade", description="到下一幕的轉場", example="fade/cut/dissolve")
    notes: Optional[str] = Field(None, description="運鏡說明")


class HashtagStrategy(BaseModel):
    """分類標籤佈署策略（跨平台）"""
    core_content: List[str] = Field(
        default_factory=list,
        description="核心內容標籤：直接命中此影片的具體內容，搜尋時能找到這支影片（2-3個）"
    )
    algorithm_traffic: List[str] = Field(
        default_factory=list,
        description="流量演算法標籤：內容類別與知識領域，幫助演算法找到正確受眾（2-3個，必須與內容相關，禁止無關熱門標籤）"
    )
    emotional: List[str] = Field(
        default_factory=list,
        description="情緒心理標籤：觀眾看完後的情緒反應或認知狀態（2-3個）"
    )
    youtube_priority: List[str] = Field(
        default_factory=list,
        description="YouTube Shorts 優先佈署標籤組合（放在描述欄前三位，含 #Shorts）"
    )
    tiktok_priority: List[str] = Field(
        default_factory=list,
        description="TikTok 優先佈署標籤組合（最多5個，含繁體中文高流量標籤）"
    )


class ObservationUnit(BaseModel):
    """單一觀測單元（升級版）"""
    model_config = {"protected_namespaces": ()}   # V34.0: allow model_tag field

    id: str = Field(..., description="唯一識別碼", example="unit_001")
    
    # 核心內容
    phenomenon: str = Field(..., description="現象描述（主標題）", max_length=35)
    mechanism: str = Field(..., description="機制說明（副標題）", max_length=70)
    
    # 語音與字幕
    voice_over_zh: str = Field(..., description="中文旁白（TTS 7.0字/秒；max=floor((unit_sec-1.0)*7.0)字，不得跨幕）", max_length=50)
    subtitle_zh: str = Field(..., description="中文字幕（由旁白濃縮，≤12字）", max_length=12)
    
    # 視覺與圖片
    visual_description: str = Field(..., description="視覺場景描述", max_length=150)
    image_prompt: ImagePrompt = Field(..., description="圖片生成提示詞")
    
    # 情緒與氛圍
    emotional_tone: str = Field(..., description="情緒基調", example="驚嘆、好奇")
    
    # 時間線與鏡頭
    start_timecode: str = Field(default="00:00:00:00", description="開始時間碼")
    duration_seconds: int = Field(default=3, description="持續秒數", ge=1, le=120)
    camera_mode: str = Field(default="CLOSE_UP", description="鏡頭模式", example="CLOSE_UP")
    in_scene_timeline: List[ActivityEvent] = Field(default_factory=list, description="場景內時間線")
    
    # 新增：運鏡指導
    motion_guidance: Optional[MotionGuidance] = Field(None, description="運鏡指導")
    is_keyframe: bool = Field(default=True, description="是否為關鍵幀")

    # 編輯資訊
    editing_notes: Optional[str] = Field(default="", description="剪輯建議")

    # ── 演算法張力欄位 ──
    unit_role: str = Field(
        default="content",
        description="構圖角色: 定位 / 解構 / 影響 / content"
    )
    hook_technique: Optional[str] = Field(
        None,
        description="鉤子技術（定位單元）: reverse_question / shock_fact / forbidden_knowledge / visual_paradox / incomplete_loop"
    )
    seo_keywords: List[str] = Field(
        default_factory=list,
        description="SEO 搜尋關鍵字（繁體中文真實搜尋詞）"
    )
    interaction_trigger: Optional[str] = Field(
        None,
        description="互動觸發器: comment_bait / share_trigger / replay_hook / save_reminder"
    )
    interaction_bait_text: Optional[str] = Field(
        None,
        description="互動誘餌實際文字（對應 interaction_trigger 類型，≤30字，可直接顯示在影片末尾或評論引導）",
        max_length=50
    )
    hashtag_strategy: Optional[HashtagStrategy] = Field(
        None,
        description="分類標籤佈署策略（核心內容 / 演算法流量 / 情緒心理 / 平台專屬）"
    )

    # ── V33.0 視覺優先級 ──
    tier: Optional[int] = Field(None, description="V33.0 視覺優先級 (1=Hook衝擊, 2=Body展開, 3=Payoff落點)")

    # ── V34.0 模型標籤 ──
    model_tag: Optional[str] = Field(None, description="V34: 圖像模型標籤 (nano-banana-2 / flux-schnell)")

    # ── Veo 影片生成 ──
    veo_prompt: Optional[str] = Field(
        None,
        description="Veo/AI 影片生成提示詞（英文，描述動態場景）"
    )
    veo_recommended: bool = Field(
        default=False,
        description="是否建議此幕轉 Veo 影片（解構幕最適合）"
    )

    # 舊版相容性欄位（optional）
    hook: Optional[str] = Field(None, description="鉤子標題（舊版相容）")
    core_message: Optional[str] = Field(None, description="核心訊息（舊版相容）")
    script_outline: Optional[List[str]] = Field(None, description="腳本大綱（舊版相容）")


class CostEstimate(BaseModel):
    """成本預估（新增）"""
    model_config = {"protected_namespaces": ()}  # V34.0: allow model_used field
    image_count: int = Field(..., description="圖片數量")
    cost_per_image: float = Field(..., description="單價（美元）")
    total_cost: float = Field(..., description="總成本（美元）")
    model_used: str = Field(..., description="使用的模型")


class SEOMetadata(BaseModel):
    """SEO 元數據"""
    youtube_shorts_title_zh: str = Field(..., description="YouTube Shorts 標題（40字內）", max_length=45)
    tiktok_title_zh: str = Field(..., description="TikTok 標題（40字內）", max_length=45)
    description_zh: str = Field(..., description="描述文字", max_length=250)
    tags: List[str] = Field(..., description="標籤列表", min_length=3, max_length=12)


class ExportPackage(BaseModel):
    """匯出包資訊"""
    cover_prompt: str = Field(..., description="封面圖提示詞（英文）")
    seo: SEOMetadata = Field(..., description="SEO 元數據")


class ObservationResponse(BaseModel):
    """觀測單元生成回應（升級版）"""
    success: bool = Field(..., description="是否成功")
    units: List[ObservationUnit] = Field(..., description="觀測單元列表")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="額外資訊")
    generated_at: datetime = Field(default_factory=datetime.now, description="生成時間")
    export_pkg: Optional[ExportPackage] = Field(None, description="匯出包（可選）")
    
    # 新增欄位
    video_mode: VideoMode = Field(default=VideoMode.SHORTS, description="影片模式")
    aspect_ratio: str = Field(default="9:16", description="畫面比例")
    cost_estimate: Optional[CostEstimate] = Field(None, description="成本預估")


# ===== SEO 相關 =====

class SEOGenerateRequest(BaseModel):
    """SEO 生成請求"""
    unit: ObservationUnit = Field(..., description="觀測單元")
    platforms: List[str] = Field(
        default=["youtube", "instagram", "tiktok"],
        description="目標平台"
    )
    language: str = Field(default="zh-TW", description="語言")


class PlatformSEO(BaseModel):
    """單一平台 SEO"""
    platform: str = Field(..., description="平台名稱")
    title: str = Field(..., description="標題")
    description: str = Field(..., description="描述")
    hashtags: List[str] = Field(..., description="標籤列表")
    keywords: Optional[List[str]] = Field(None, description="關鍵字")


class SEOResponse(BaseModel):
    """SEO 生成回應"""
    success: bool = Field(..., description="是否成功")
    unit_id: str = Field(..., description="關聯的單元 ID")
    platforms: List[PlatformSEO] = Field(..., description="各平台 SEO")
    generated_at: datetime = Field(default_factory=datetime.now, description="生成時間")


# ===== 圖片生成相關 =====

class ImageGenerateRequest(BaseModel):
    """圖片生成請求"""
    prompt: str = Field(..., description="圖片提示詞")
    negative_prompt: Optional[str] = Field(None, description="負面提示詞")
    unit_id: str = Field(..., description="關聯的單元 ID")
    aspect_ratio: str = Field(default="9:16", description="畫面比例")


class ImageGenerateResponse(BaseModel):
    """圖片生成回應"""
    success: bool = Field(..., description="是否成功")
    unit_id: str = Field(..., description="關聯的單元 ID")
    image_url: Optional[str] = Field(None, description="圖片 URL（Replicate）")
    image_base64: Optional[str] = Field(None, description="Base64 編碼圖片")
    prompt_used: str = Field(..., description="實際使用的提示詞")
    generated_at: datetime = Field(default_factory=datetime.now, description="生成時間")


# ===== 錯誤回應 =====

class ErrorResponse(BaseModel):
    """統一錯誤回應格式"""
    success: bool = Field(default=False, description="必定為 False")
    error: str = Field(..., description="錯誤訊息")
    error_type: str = Field(..., description="錯誤類型")
    detail: Optional[Dict[str, Any]] = Field(None, description="詳細資訊")


# ===== 健康檢查 =====

class HealthResponse(BaseModel):
    """健康檢查回應"""
    status: str = Field(..., description="服務狀態")
    timestamp: datetime = Field(default_factory=datetime.now, description="檢查時間")
    services: Dict[str, bool] = Field(..., description="各服務狀態")