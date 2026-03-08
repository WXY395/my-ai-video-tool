import React, { useState, useEffect } from 'react';
import { Loader2, Zap, Activity, Terminal, Image as ImageIcon, DollarSign, Film, Maximize2, Layers, Package, GripVertical } from 'lucide-react';
import { Toaster, toast } from 'sonner';
import Lightbox from 'yet-another-react-lightbox';
import 'yet-another-react-lightbox/styles.css';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  rectSortingStrategy,
  useSortable,
  arrayMove,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import ObservationNotesInput from './components/ObservationNotesInput';
import ObservationUnitCard from './components/ObservationUnitCard';
import {
  generateObservationUnitsStream,
  generateAssetImage,
  estimateCost,
  type VideoMode,
  type AspectRatio,
  type CostEstimateResult,
  type StreamEvent,
} from './services/geminiService';
import { ObservationUnit, ObservationConfig, UnitPlanEntry, VisualDensity, InformationFocus, GuidanceLevel, ImageIntent, ReferencePlane, ScaleCue, VisualContinuity } from './types';
import { PACING_PROFILES, formatDurationRange, assignBeats, buildUnitPlan } from './config/pacingProfiles';
import { exportPack, slugify } from './services/packExportService';

// ── beat 色票 ─────────────────────────────────────────────────────────────────
const BEAT_CONFIG = {
  hook:   { label: 'HOOK',   color: 'text-orange-400', border: 'border-orange-500/30', bg: 'bg-orange-500/8'  },
  body:   { label: 'BODY',   color: 'text-zinc-400',   border: 'border-zinc-700',      bg: 'bg-zinc-800/20'  },
  payoff: { label: 'PAYOFF', color: 'text-emerald-400',border: 'border-emerald-500/30',bg: 'bg-emerald-500/8' },
} as const;

// ── UnitPlan Badge ────────────────────────────────────────────────────────────
const BEAT_BADGE_STYLE: Record<UnitPlanEntry['beat'], string> = {
  hook:   'text-orange-400 border-orange-500/30 bg-orange-500/10',
  body:   'text-zinc-500   border-zinc-700      bg-zinc-800/20',
  payoff: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10',
};

const UnitPlanBadge: React.FC<{ entry: UnitPlanEntry | undefined }> = ({ entry }) => {
  if (!entry) return null;
  return (
    <div className="flex items-center gap-1.5 px-1">
      <span className={`text-[8px] mono font-black px-1.5 py-0.5 rounded border ${BEAT_BADGE_STYLE[entry.beat]}`}>
        {entry.beat.toUpperCase()}
      </span>
      <span className="text-[8px] mono text-zinc-600">{entry.keyframe_id}</span>
      <span className="text-[8px] mono text-zinc-700">·</span>
      <span className="text-[8px] mono text-zinc-500 font-bold">{entry.variant_id}</span>
    </div>
  );
};

// ── Sortable card wrapper ────────────────────────────────────────────────────
const SortableCardWrapper: React.FC<{
  id: string;
  index: number;
  unit: ObservationUnit;
  unitPlanEntry: UnitPlanEntry | undefined;
  onGenerateImage: (id: string) => void;
  aspectRatio: AspectRatio;
}> = ({ id, index, unit, unitPlanEntry, onGenerateImage, aspectRatio }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
    zIndex: isDragging ? 50 : undefined,
  };

  return (
    <div ref={setNodeRef} style={style} className="flex flex-col gap-1">
      <div className="flex items-center gap-1">
        <div
          {...attributes}
          {...listeners}
          className="cursor-grab active:cursor-grabbing p-1 text-zinc-800 hover:text-zinc-500 transition-colors touch-none"
          title="拖曳排序"
        >
          <GripVertical className="w-3 h-3" />
        </div>
        <UnitPlanBadge entry={unitPlanEntry} />
      </div>
      <ObservationUnitCard
        unit={unit}
        onGenerateImage={onGenerateImage}
        aspectRatio={aspectRatio}
      />
    </div>
  );
};

// ── Placeholder card（mock，無真實資料）────────────────────────────────────────
const PlaceholderCard: React.FC<{
  index: number;
  beat: 'hook' | 'body' | 'payoff';
  aspectRatio: AspectRatio;
}> = ({ index, beat, aspectRatio }) => {
  const cfg = BEAT_CONFIG[beat];
  const imageAspectClass = aspectRatio === '16:9' ? 'aspect-[16/9]' : 'aspect-[9/16]';

  return (
    <div className={`glass-card dossier-clip overflow-hidden flex flex-col border ${cfg.border} opacity-50`}>
      {/* Header */}
      <div className={`p-3 border-b ${cfg.bg} ${cfg.border} flex items-center justify-between`}>
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-zinc-700 animate-pulse" />
          <span className="text-[9px] mono font-bold text-zinc-600">UNIT_{String(index + 1).padStart(2, '0')}</span>
          <span className={`text-[8px] mono font-black px-2 py-0.5 rounded-sm border ${cfg.color} ${cfg.border} ${cfg.bg}`}>
            {cfg.label}
          </span>
        </div>
        <span className="text-[9px] mono text-zinc-700">—s</span>
      </div>

      {/* Visual slot */}
      <div className={`${imageAspectClass} bg-zinc-950 border-b border-zinc-900 flex items-center justify-center`}>
        <ImageIcon className="w-6 h-6 text-zinc-800" />
      </div>

      {/* Body */}
      <div className="p-4 space-y-3 bg-zinc-950/40 flex-1">
        <div className="space-y-2">
          <div className="h-2.5 w-3/4 bg-zinc-800 rounded animate-pulse" />
          <div className="h-2 w-full bg-zinc-900 rounded animate-pulse" />
          <div className="h-2 w-5/6 bg-zinc-900 rounded animate-pulse" />
        </div>
        <div className="h-px bg-zinc-800/50 mt-3" />
        <div className="h-4 w-2/3 bg-zinc-900 rounded animate-pulse" />
        <div className="mt-auto pt-3 border-t border-zinc-800/50 flex items-center">
          <span className="text-[8px] mono text-zinc-800 uppercase tracking-widest">Awaiting_Signal</span>
        </div>
      </div>
    </div>
  );
};

// ── Main App ──────────────────────────────────────────────────────────────────
const App: React.FC = () => {
  const [notes, setNotes] = useState('');

  const [videoMode, setVideoMode] = useState<VideoMode>('shorts');
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>('9:16');
  const [durationMinutes, setDurationMinutes] = useState<number | undefined>(undefined);

  // 當前 Profile（隨 videoMode 更新）
  const profile = PACING_PROFILES[videoMode];

  // 成本預估
  const [costEstimate, setCostEstimate] = useState<CostEstimateResult | null>(null);
  const [isEstimating, setIsEstimating] = useState(false);

  // 素材包輸出
  const [isExporting, setIsExporting] = useState(false);

  // 封面燈箱
  const [coverLightbox, setCoverLightbox] = useState(false);

  const [config] = useState<ObservationConfig>({
    unitCount: 3,
    visualDensity: VisualDensity.MEDIUM,
    informationFocus: InformationFocus.SINGLE_SUBJECT,
    guidanceLevel: GuidanceLevel.NORMAL,
    imageIntent: ImageIntent.EDITING_FIRST,
    referencePlane: ReferencePlane.UNDEFINED,
    scaleCue: ScaleCue.NONE,
    visualContinuity: VisualContinuity.CONSISTENT_FRAMING
  });

  const [state, setState] = useState({
    isProcessing: false,
    units: [] as ObservationUnit[],
    error: null as string | null,
    coverImageUrl: null as string | null,
    coverPrompt: null as string | null,
    coverModel: null as string | null,
    coverStyle: null as string | null,
    productionNotes: null as any,
  });

  const [logs, setLogs] = useState<string[]>(["SYSTEM_STABLE: AWAITING_SIGNAL"]);

  const addLog = (msg: string) => {
    setLogs(prev => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev].slice(0, 100));
  };

  // 拖曳排序
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setState(prev => {
      const oldIndex = prev.units.findIndex(u => u.id === active.id);
      const newIndex = prev.units.findIndex(u => u.id === over.id);
      return { ...prev, units: arrayMove(prev.units, oldIndex, newIndex) };
    });
    addLog(`REORDER: ${active.id} → ${over.id}`);
  };

  // 切換 VideoMode → 載入 Profile、重設時長
  const handleModeChange = (mode: VideoMode) => {
    setVideoMode(mode);
    const p = PACING_PROFILES[mode];
    if (mode === 'shorts') {
      setAspectRatio('9:16');
      setDurationMinutes(undefined);
    } else {
      setAspectRatio('16:9');
      // 預設取 target_duration_range 下限轉為分鐘
      setDurationMinutes(Math.round(p.target_duration_range[0] / 60));
    }
    addLog(`PROFILE_LOADED: ${p.label.toUpperCase()} | UNITS: ${p.unit_range[0]}–${p.unit_range[1]} | DUR: ${formatDurationRange(p.target_duration_range)}`);
  };

  // 自動預估成本
  useEffect(() => {
    if (notes.trim() && videoMode && aspectRatio) {
      handleEstimateCost();
    }
  }, [videoMode, aspectRatio, durationMinutes]);

  const handleEstimateCost = async () => {
    if (!notes.trim()) return;

    setIsEstimating(true);
    addLog("ESTIMATING_COST...");

    try {
      const estimate = await estimateCost(notes, videoMode, aspectRatio, durationMinutes);
      setCostEstimate(estimate);
      addLog(`COST_ESTIMATED: $${estimate.costEstimate.total_cost} (${estimate.keyframeCount} keyframes)`);
      toast.success(`預估 $${estimate.costEstimate.total_cost.toFixed(3)}（${estimate.keyframeCount} 個 KF）`);
    } catch (err: any) {
      addLog(`ESTIMATE_ERROR: ${err.message}`);
      toast.error(`成本預估失敗：${err.message}`);
    } finally {
      setIsEstimating(false);
    }
  };

  const handleGenerate = async () => {
    if (!notes.trim()) return;

    setState({ isProcessing: true, units: [], error: null, coverImageUrl: null, coverPrompt: null, coverModel: null, coverStyle: null, productionNotes: null });
    addLog("THREAD_OPEN: NEURAL_OBSERVATION_MAPPING");
    addLog(`MODE: ${videoMode.toUpperCase()} | RATIO: ${aspectRatio} | DURATION: ${durationMinutes || 'AUTO'}`);
    toast.loading("Gemini 腳本生成中…", { id: 'gen' });

    let unitCount = 0;

    try {
      await generateObservationUnitsStream(
        notes, config, videoMode, aspectRatio, durationMinutes,
        (event: StreamEvent) => {
          switch (event.type) {
            case 'step':
              addLog(event.message.toUpperCase().replace(/[…\s]/g, '_').replace(/_+/g, '_'));
              toast.loading(event.message, { id: 'gen' });
              break;

            case 'units':
              unitCount = event.units.length;
              setState(prev => ({ ...prev, units: event.units }));
              addLog(`SIGNAL_PARSED: ${unitCount} KEYFRAMES`);
              if (event.cost_estimate) {
                addLog(`COST_CONFIRMED: $${event.cost_estimate.total_cost}`);
                setCostEstimate({
                  success: true,
                  videoMode: event.video_mode as VideoMode,
                  aspectRatio: event.aspect_ratio,
                  keyframeCount: unitCount,
                  costEstimate: event.cost_estimate,
                });
              }
              toast.loading("封面生成中…", { id: 'gen' });
              break;

            case 'cover':
              setState(prev => ({
                ...prev,
                coverImageUrl: event.cover_url,
                coverPrompt: event.cover_prompt ?? null,
                coverModel: event.cover_model ?? null,
                coverStyle: event.cover_style ?? null,
              }));
              addLog("COVER_IMAGE_READY");
              break;

            case 'done':
              setState(prev => ({
                ...prev,
                isProcessing: false,
                productionNotes: event.production_notes,
              }));
              if (event.production_notes?.workflow) {
                addLog(`POST_PRODUCTION: ${event.production_notes.workflow}`);
              }
              if (event.production_notes?.estimatedEditingTime) {
                addLog(`EDITING_TIME: ${event.production_notes.estimatedEditingTime}`);
              }
              addLog("OBSERVATION_UNITS_READY_FOR_REVIEW");
              toast.success(`${unitCount} 個單元就緒 · 封面已生成`, { id: 'gen' });
              break;

            case 'error':
              setState(prev => ({ ...prev, isProcessing: false, error: event.message }));
              addLog(`FATAL_ERROR: ${event.message}`);
              toast.error(event.message || "生成失敗", { id: 'gen' });
              break;
          }
        }
      );
    } catch (err: any) {
      addLog(`FATAL_ERROR: ${err.message}`);
      setState(prev => ({ ...prev, isProcessing: false, error: err.message || "Protocol failure." }));
      toast.error(err.message || "生成失敗", { id: 'gen' });
    }
  };

  const handleGenerateImage = async (unitId: string) => {
    const unitIndex = state.units.findIndex(u => u.id === unitId);
    const unit = unitIndex >= 0 ? state.units[unitIndex] : undefined;
    if (!unit) return;

    setState(prev => ({
      ...prev,
      units: prev.units.map(u =>
        u.id === unitId ? { ...u, isGeneratingImage: true } : u
      )
    }));

    addLog(`SYNTHESIZING_FRAME_ID_${unitId}`);
    toast.loading(`合成 ${unitId}…`, { id: `img-${unitId}` });

    try {
      const promptText = typeof unit.image_prompt === 'string'
        ? unit.image_prompt
        : unit.image_prompt?.prompt || unit.visual_description || 'A scene';

      // V34.0: 傳遞 scene_index，讓後端路由至正確模型
      // unitIndex 0 (第一幕) → nano-banana-2；其餘 → flux-schnell
      const imageUrl = await generateAssetImage(promptText, aspectRatio, unitIndex);

      setState(prev => ({
        ...prev,
        units: prev.units.map(u =>
          u.id === unitId ? { ...u, imageUrl, isGeneratingImage: false } : u
        )
      }));

      addLog(`FRAME_ID_${unitId}_VERIFIED`);
      toast.success(`${unitId} 圖片就緒`, { id: `img-${unitId}` });
    } catch (err: any) {
      addLog(`ERROR: ASSET_RENDER_FAILURE_ID_${unitId}`);
      setState(prev => ({
        ...prev,
        units: prev.units.map(u =>
          u.id === unitId ? { ...u, isGeneratingImage: false } : u
        )
      }));
      toast.error(`${unitId} 生成失敗`, { id: `img-${unitId}` });
    }
  };

  const handleExportPack = async () => {
    if (!state.coverImageUrl || state.units.length === 0) return;

    setIsExporting(true);
    addLog("EXPORT_PACK: ASSEMBLING_ZIP...");
    toast.loading("打包素材包…", { id: 'export' });

    // slug 取筆記第一行（最多 60 字）
    const topic = notes.split('\n')[0].trim().slice(0, 60) || 'observation';
    const readyCount = state.units.filter(u => u.imageUrl).length;

    try {
      await exportPack({
        topic,
        videoMode,
        aspectRatio,
        coverImageUrl: state.coverImageUrl,
        units: state.units,
        unitPlan,
        logs,
      });
      addLog(`EXPORT_PACK: OK — pack_${slugify(topic)}_*.zip  (cover + ${readyCount} keyframes)`);
      toast.success(`ZIP 已下載（封面 + ${readyCount} 張 KF）`, { id: 'export' });
    } catch (err: any) {
      addLog(`EXPORT_PACK_ERROR: ${err.message}`);
      toast.error(`打包失敗：${err.message}`, { id: 'export' });
    } finally {
      setIsExporting(false);
    }
  };

  // Deck 顯示邏輯
  const hasUnits      = state.units.length > 0;
  const deckUnitCount = hasUnits ? state.units.length : profile.unit_range[0];
  const deckBeats     = assignBeats(profile.beats, deckUnitCount);
  const unitPlan      = buildUnitPlan(videoMode, profile, deckUnitCount);

  return (
    <div className="h-screen flex flex-col bg-zinc-950 text-zinc-300 overflow-hidden">
      <Toaster theme="dark" position="bottom-right" richColors closeButton />
      {state.coverImageUrl && (
        <Lightbox
          open={coverLightbox}
          close={() => setCoverLightbox(false)}
          slides={[{ src: state.coverImageUrl }]}
        />
      )}
      {/* Header */}
      <header className="h-14 border-b border-zinc-800 flex items-center justify-between px-6 bg-zinc-900/40 backdrop-blur-md">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded border border-emerald-500/30 flex items-center justify-center bg-emerald-500/5">
            <Activity className="w-4 h-4 text-emerald-500" />
          </div>
          <div>
            <h1 className="text-[11px] font-bold tracking-[0.2em] uppercase leading-none text-zinc-100">
              Observation Workstation v2.0
            </h1>
            <span className="text-[8px] mono text-zinc-500 uppercase tracking-tighter">LONG_FORM_ENABLED</span>
          </div>
        </div>
        <div className="flex items-center space-x-2 px-3 py-1.5 bg-zinc-950/50 border border-zinc-800 rounded text-[9px] mono text-zinc-500">
          <div className={`w-1.5 h-1.5 rounded-full ${state.isProcessing ? 'bg-amber-500 animate-pulse' : 'bg-emerald-500'}`}></div>
          <span>SYNC: LOCKED</span>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel */}
        <aside className="w-[420px] border-r border-zinc-800 bg-zinc-900/20 flex flex-col overflow-hidden">
          <div className="p-6 space-y-6 overflow-y-auto">
            <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
              Buffer_Input
            </h3>

            <ObservationNotesInput
              value={notes}
              onChange={setNotes}
              placeholder="輸入觀測筆記..."
            />

            {/* 模式選擇 */}
            <div className="space-y-3">
              <label className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">Video_Mode</label>
              <div className="grid grid-cols-3 gap-2">
                {(['shorts', 'medium', 'long'] as VideoMode[]).map(mode => (
                  <button
                    key={mode}
                    onClick={() => handleModeChange(mode)}
                    className={`
                      px-3 py-2 rounded text-[9px] font-bold mono uppercase transition-all
                      ${videoMode === mode
                        ? 'bg-emerald-500 text-zinc-950'
                        : 'bg-zinc-800 text-zinc-500 hover:bg-zinc-700'}
                    `}
                  >
                    {PACING_PROFILES[mode].label}
                  </button>
                ))}
              </div>
            </div>

            {/* Profile 資訊面板 */}
            <div className="p-4 bg-zinc-900/50 border border-zinc-800 rounded space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest flex items-center gap-1.5">
                  <Layers className="w-3 h-3" /> Profile_Info
                </span>
                <span className="text-[9px] mono text-emerald-500 font-bold">{profile.label}</span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[9px] mono">
                {/* Duration range */}
                <div className="space-y-0.5">
                  <div className="text-zinc-600 uppercase tracking-wider">Duration</div>
                  <div className="text-zinc-200 font-bold">{formatDurationRange(profile.target_duration_range)}</div>
                </div>
                {/* Unit range */}
                <div className="space-y-0.5">
                  <div className="text-zinc-600 uppercase tracking-wider">Units</div>
                  <div className="text-zinc-200 font-bold">{profile.unit_range[0]} – {profile.unit_range[1]}</div>
                </div>
                {/* Veo budget */}
                <div className="space-y-0.5">
                  <div className="text-zinc-600 uppercase tracking-wider">Veo Budget</div>
                  <div className="text-violet-400 font-bold">{profile.veo_budget} clips</div>
                </div>
                {/* Cut frequency */}
                <div className="space-y-0.5">
                  <div className="text-zinc-600 uppercase tracking-wider">Cut</div>
                  <div className="text-blue-400 font-bold uppercase">{profile.cut_frequency}</div>
                </div>
              </div>

              {/* Beats 視覺化 */}
              <div className="space-y-1">
                <div className="text-[8px] mono text-zinc-600 uppercase tracking-wider">Beat Structure</div>
                <div className="flex h-2 rounded overflow-hidden gap-px">
                  <div
                    className="bg-orange-500/60 transition-all"
                    style={{ width: `${profile.beats.hook * 100}%` }}
                    title={`Hook ${Math.round(profile.beats.hook * 100)}%`}
                  />
                  <div
                    className="bg-zinc-600/60 transition-all"
                    style={{ width: `${profile.beats.body * 100}%` }}
                    title={`Body ${Math.round(profile.beats.body * 100)}%`}
                  />
                  <div
                    className="bg-emerald-500/60 transition-all"
                    style={{ width: `${profile.beats.payoff * 100}%` }}
                    title={`Payoff ${Math.round(profile.beats.payoff * 100)}%`}
                  />
                </div>
                <div className="flex justify-between text-[8px] mono text-zinc-600">
                  <span className="text-orange-500/70">Hook {Math.round(profile.beats.hook * 100)}%</span>
                  <span>Body {Math.round(profile.beats.body * 100)}%</span>
                  <span className="text-emerald-500/70">Payoff {Math.round(profile.beats.payoff * 100)}%</span>
                </div>
              </div>

              {/* Caption density */}
              <div className="flex items-center justify-between text-[9px] mono">
                <span className="text-zinc-600 uppercase tracking-wider">Captions</span>
                <span className={`font-bold uppercase ${
                  profile.caption_density === 'dense'  ? 'text-amber-400' :
                  profile.caption_density === 'normal' ? 'text-zinc-400'  : 'text-zinc-600'
                }`}>{profile.caption_density}</span>
              </div>
            </div>

            {/* 比例選擇 */}
            <div className="space-y-3">
              <label className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">Aspect_Ratio</label>
              <div className="grid grid-cols-2 gap-2">
                {(['9:16', '16:9'] as AspectRatio[]).map(ratio => (
                  <button
                    key={ratio}
                    onClick={() => setAspectRatio(ratio)}
                    className={`
                      px-3 py-2 rounded text-[9px] font-bold mono uppercase transition-all flex items-center justify-center space-x-2
                      ${aspectRatio === ratio
                        ? 'bg-blue-500 text-zinc-950'
                        : 'bg-zinc-800 text-zinc-500 hover:bg-zinc-700'}
                    `}
                  >
                    <Maximize2 className="w-3 h-3" />
                    <span>{ratio}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* 時長設定（長片/中片） */}
            {videoMode !== 'shorts' && (
              <div className="space-y-3">
                <label className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">
                  Duration (Minutes)
                  <span className="ml-2 text-zinc-600 normal-case">
                    推薦 {Math.round(profile.target_duration_range[0] / 60)}–{Math.round(profile.target_duration_range[1] / 60)} min
                  </span>
                </label>
                <input
                  type="number"
                  value={durationMinutes || ''}
                  onChange={(e) => setDurationMinutes(parseInt(e.target.value) || undefined)}
                  min={Math.round(profile.target_duration_range[0] / 60)}
                  max={Math.round(profile.target_duration_range[1] / 60)}
                  placeholder={String(Math.round(profile.target_duration_range[0] / 60))}
                  className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 rounded text-zinc-300 text-sm mono focus:border-emerald-500 focus:outline-none"
                />
              </div>
            )}

            {/* 成本預估 */}
            {costEstimate && (
              <div className="p-4 bg-zinc-900/50 border border-zinc-800 rounded space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">Cost_Estimate</span>
                  <DollarSign className="w-4 h-4 text-emerald-500" />
                </div>
                <div className="text-2xl font-bold text-emerald-400 mono">
                  ${costEstimate.costEstimate.total_cost.toFixed(3)}
                </div>
                <div className="text-[9px] text-zinc-500 space-y-1">
                  <div>KF ×{costEstimate.keyframeCount} · ${costEstimate.costEstimate.kf_cost?.toFixed(3) ?? '—'} (flux-schnell $0.003/張)</div>
                  <div>封面 ×1 · ${costEstimate.costEstimate.cover_cost?.toFixed(3) ?? '—'} (flux-dev $0.025/張)</div>
                  <div>共 {costEstimate.keyframeCount + 1} 張圖片</div>
                </div>
              </div>
            )}

            <button
              onClick={handleGenerate}
              disabled={!notes.trim() || state.isProcessing}
              className={`
                w-full flex items-center justify-center space-x-2 px-6 py-3 rounded text-[10px] font-black mono tracking-widest transition-all uppercase
                ${!notes.trim() || state.isProcessing
                  ? 'bg-zinc-900 text-zinc-700 border border-zinc-800 cursor-not-allowed'
                  : 'bg-zinc-100 text-zinc-950 hover:bg-white border border-white'}
              `}
            >
              {state.isProcessing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
              <span>INIT_PROTOCOL</span>
            </button>

            {/* Export Pack 按鈕：有 cover + 至少一張 keyframe 圖才顯示 */}
            {state.coverImageUrl && state.units.some(u => u.imageUrl) && (
              <button
                onClick={handleExportPack}
                disabled={isExporting}
                className={`
                  w-full flex items-center justify-center space-x-2 px-6 py-3 rounded text-[10px] font-black mono tracking-widest transition-all uppercase
                  ${isExporting
                    ? 'bg-zinc-900 text-zinc-700 border border-zinc-800 cursor-not-allowed'
                    : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20 hover:border-emerald-500/50'}
                `}
              >
                {isExporting
                  ? <Loader2 className="w-4 h-4 animate-spin" />
                  : <Package className="w-4 h-4" />}
                <span>{isExporting ? 'PACKAGING...' : 'EXPORT_PACK'}</span>
              </button>
            )}
          </div>

          {/* Diagnostic Log */}
          <div className="mt-auto border-t border-zinc-800 h-48 flex flex-col bg-black/40">
            <div className="h-6 border-b border-zinc-800 flex items-center px-4 bg-zinc-900/40">
              <Terminal className="w-3 h-3 text-zinc-600 mr-2" />
              <span className="text-[8px] font-bold text-zinc-500 uppercase tracking-widest">Diagnostic_Log</span>
            </div>
            <div className="flex-1 p-3 overflow-y-auto font-mono text-[9px] space-y-1 flex flex-col-reverse">
              {logs.map((log, i) => (
                <div key={i} className={`${log.includes('ERROR') ? 'text-rose-500' : log.includes('SIGNAL') || log.includes('COST') || log.includes('PROFILE') ? 'text-emerald-500' : 'text-zinc-600'}`}>
                  {log}
                </div>
              ))}
            </div>
          </div>
        </aside>

        {/* Center - Observation Deck */}
        <section className="flex-1 bg-zinc-950 overflow-hidden flex flex-col">
          <div className="h-12 border-b border-zinc-800 flex items-center justify-between px-6 bg-zinc-900/20">
            <h2 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
              Observation_Deck
            </h2>
            <div className="flex items-center space-x-4 text-[9px] mono text-zinc-600">
              {/* Unit range hint from profile */}
              <span className="text-zinc-700">
                SLOTS: {profile.unit_range[0]}–{profile.unit_range[1]}
              </span>
              <span className={hasUnits ? 'text-emerald-500' : 'text-zinc-600'}>
                {hasUnits ? `${state.coverImageUrl ? state.units.length + 1 : state.units.length} UNITS` : `— / ${profile.unit_range[1]} MAX`}
              </span>
              {state.productionNotes && (
                <span className="text-emerald-500">🎬 {state.productionNotes.estimatedEditingTime}</span>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            {state.error && (
              <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded text-rose-400 text-sm mb-4">
                {state.error}
              </div>
            )}

            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <div className={`grid ${aspectRatio === '16:9' ? 'grid-cols-2' : 'grid-cols-3'} gap-6`}>
              {/* 封面卡片（只在有真實資料時顯示） */}
              {state.coverImageUrl && (
                <div className="glass-card dossier-clip overflow-hidden flex flex-col">
                  {/* Header */}
                  <div className="p-3 border-b bg-emerald-500/10 border-emerald-500/20 flex items-center justify-between">
                    <span className="text-[10px] mono font-bold tracking-widest text-emerald-400">ROOT_MANIFEST</span>
                    <div className="flex items-center gap-2">
                      {state.coverStyle && (
                        <span className="text-[8px] mono px-1.5 py-0.5 rounded border border-emerald-500/20 text-emerald-500/70 uppercase">
                          {state.coverStyle}
                        </span>
                      )}
                      {state.coverModel && (
                        <span className="text-[8px] mono px-1.5 py-0.5 rounded border border-violet-500/20 text-violet-400 uppercase">
                          {state.coverModel}
                        </span>
                      )}
                    </div>
                  </div>
                  {/* Image */}
                  <div
                    className={`${aspectRatio === '9:16' ? 'aspect-[9/16]' : 'aspect-[16/9]'} bg-black relative border-b border-zinc-800 overflow-hidden flex items-center justify-center cursor-zoom-in`}
                    onClick={() => setCoverLightbox(true)}
                    title="點擊放大"
                  >
                    <img
                      src={state.coverImageUrl}
                      alt="Cover"
                      className="w-full h-full object-contain"
                    />
                  </div>
                  {/* Metadata */}
                  <div className="p-4 space-y-3 bg-zinc-950/40 flex-1">
                    <div className="flex items-center justify-between">
                      <h3 className="text-[11px] font-bold text-emerald-400">封面圖</h3>
                      <span className="text-[8px] mono text-zinc-600">SCENE_INDEX: 0</span>
                    </div>
                    <p className="text-[9px] text-zinc-500">Collection Cover · 點擊放大</p>
                    {state.coverPrompt && (
                      <div className="space-y-1">
                        <div className="text-[8px] mono text-zinc-600 uppercase tracking-wider">Cover_Prompt</div>
                        <p className="text-[8px] mono text-zinc-500 leading-relaxed line-clamp-4 break-all">
                          {state.coverPrompt}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* 真實觀測單元（可拖曳排序） */}
              {hasUnits && (
                <SortableContext items={state.units.map(u => u.id)} strategy={rectSortingStrategy}>
                  {state.units.map((unit, i) => (
                    <SortableCardWrapper
                      key={unit.id}
                      id={unit.id}
                      index={i}
                      unit={unit}
                      unitPlanEntry={unitPlan[i]}
                      onGenerateImage={handleGenerateImage}
                      aspectRatio={aspectRatio}
                    />
                  ))}
                </SortableContext>
              )}

              {/* 生成中 skeleton */}
              {state.isProcessing && Array.from({ length: profile.unit_range[0] }).map((_, i) => (
                <div key={`skel-${i}`} className="flex flex-col gap-1">
                  <UnitPlanBadge entry={unitPlan[i]} />
                  <div className="aspect-[9/22] bg-zinc-900/10 border border-dashed border-zinc-800 rounded flex items-center justify-center animate-pulse">
                    <Loader2 className="w-8 h-8 text-zinc-800 animate-spin" />
                  </div>
                </div>
              ))}

              {/* Placeholder cards（空狀態，依 profile.unit_range[0] 渲染） */}
              {!hasUnits && !state.isProcessing && Array.from({ length: profile.unit_range[0] }).map((_, i) => (
                <div key={`ph-${i}`} className="flex flex-col gap-1">
                  <UnitPlanBadge entry={unitPlan[i]} />
                  <PlaceholderCard
                    index={i}
                    beat={deckBeats[i] ?? 'body'}
                    aspectRatio={aspectRatio}
                  />
                </div>
              ))}
            </div>
            </DndContext>
          </div>
        </section>
      </div>

      {/* Footer */}
      <footer className="h-8 border-t border-zinc-800 bg-zinc-900/80 flex items-center justify-between px-6 text-[10px] mono text-zinc-500">
        <div className="flex items-center space-x-2">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
          <span>STATION_ALPHA_ONLINE_V2</span>
        </div>
        <div className="flex items-center space-x-4">
          <span>MODE: {videoMode.toUpperCase()}</span>
          <span>RATIO: {aspectRatio}</span>
          <span>DUR: {formatDurationRange(profile.target_duration_range)}</span>
          <span>LATENCY: {state.isProcessing ? 'COMPUTING' : 'IDLE'}</span>
        </div>
      </footer>
    </div>
  );
};

export default App;
