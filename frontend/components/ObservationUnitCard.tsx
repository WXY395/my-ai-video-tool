import React, { useState } from 'react';
import { ObservationUnit } from '../types';
import { PlayCircle, Loader2, Image as ImageIcon, CheckCircle2, Sparkles, Camera, Mic, Film, ArrowRight, Tag, MousePointerClick, Video, ChevronDown, ChevronUp } from 'lucide-react';
import Lightbox from 'yet-another-react-lightbox';
import 'yet-another-react-lightbox/styles.css';

type AspectRatio = '9:16' | '16:9' | '1:1';

interface ObservationUnitCardProps {
  unit: ObservationUnit;
  onGenerateImage: (id: string) => void;
  aspectRatio?: AspectRatio;
  isSelected?: boolean;
  onClick?: () => void;
}

const MOTION_EFFECT_LABEL: Record<string, string> = {
  ken_burns: 'Ken Burns',
  zoom_in: 'Zoom In',
  zoom_out: 'Zoom Out',
  pan_left: 'Pan Left',
  pan_right: 'Pan Right',
  static: 'Static',
};

const UNIT_ROLE_CONFIG: Record<string, {
  label: string; color: string; border: string; bg: string; headerBg: string; headerBorder: string;
}> = {
  '定位': {
    label: '📍 定位',
    color: 'text-orange-400',
    border: 'border-orange-500/30',
    bg: 'bg-orange-500/10',
    headerBg: 'bg-orange-500/5',
    headerBorder: 'border-orange-500/20',
  },
  '解構': {
    label: '🔬 解構',
    color: 'text-yellow-400',
    border: 'border-yellow-500/30',
    bg: 'bg-yellow-500/10',
    headerBg: 'bg-yellow-500/5',
    headerBorder: 'border-yellow-500/20',
  },
  '影響': {
    label: '💥 影響',
    color: 'text-emerald-400',
    border: 'border-emerald-500/30',
    bg: 'bg-emerald-500/10',
    headerBg: 'bg-emerald-500/5',
    headerBorder: 'border-emerald-500/20',
  },
  content: {
    label: 'CONTENT',
    color: 'text-zinc-500',
    border: 'border-zinc-700',
    bg: 'bg-zinc-800/30',
    headerBg: 'bg-zinc-900/40',
    headerBorder: 'border-zinc-800',
  },
};

const HOOK_TECHNIQUE_LABEL: Record<string, string> = {
  reverse_question:    '↩ 顛覆認知',
  shock_fact:          '💢 震驚事實',
  forbidden_knowledge: '🔒 禁忌知識',
  visual_paradox:      '👁 視覺悖論',
  incomplete_loop:     '🔁 未完成迴圈',
};

const INTERACTION_LABEL: Record<string, { icon: string; label: string; color: string }> = {
  comment_bait:  { icon: '💬', label: '留言誘餌',  color: 'text-blue-400' },
  share_trigger: { icon: '🔁', label: '分享觸發',  color: 'text-green-400' },
  replay_hook:   { icon: '🔄', label: '重播誘導',  color: 'text-amber-400' },
  save_reminder: { icon: '🔖', label: '收藏提醒',  color: 'text-purple-400' },
};

const ObservationUnitCard: React.FC<ObservationUnitCardProps> = ({
  unit,
  onGenerateImage,
  aspectRatio = '9:16',
  isSelected,
  onClick,
}) => {
  const [veoExpanded, setVeoExpanded] = useState(false);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const imageAspectClass = aspectRatio === '16:9' ? 'aspect-[16/9]' : 'aspect-[9/16]';

  const title     = unit.phenomenon || unit.hook || '現象';
  const body      = unit.mechanism  || unit.coreMessage || unit.core_message || '機制說明';
  const voiceOver = unit.voice_over_zh || '';
  const subtitle  = unit.subtitle_zh   || '';

  const role    = unit.unit_role || 'content';
  const roleCfg = UNIT_ROLE_CONFIG[role] || UNIT_ROLE_CONFIG.content;

  const hookLabel    = unit.hook_technique ? (HOOK_TECHNIQUE_LABEL[unit.hook_technique] || unit.hook_technique) : null;
  const interactData = unit.interaction_trigger
    ? (INTERACTION_LABEL[unit.interaction_trigger] || { icon: '↗', label: unit.interaction_trigger, color: 'text-zinc-400' })
    : null;
  const keywords = unit.seo_keywords || [];

  return (
    <div
      onClick={onClick}
      className={`
        glass-card dossier-clip overflow-hidden flex flex-col transition-all duration-300 cursor-pointer
        ${isSelected ? 'ring-1 ring-emerald-500/40 border-emerald-500/40 translate-y-[-4px] shadow-2xl' : 'hover:border-zinc-700'}
      `}
    >
      {/* Card Header */}
      <div className={`p-3 border-b flex justify-between items-center ${roleCfg.headerBg} ${roleCfg.headerBorder}`}>
        <div className="flex items-center gap-2 flex-wrap">
          <div className={`w-1.5 h-1.5 rounded-full ${unit.imageUrl ? 'bg-emerald-500' : 'bg-zinc-800 animate-pulse'}`} />
          <span className="text-[9px] mono font-bold text-zinc-600">{unit.id || 'UNIT'}</span>

          {/* 構圖角色 Badge */}
          <span className={`text-[8px] mono font-black px-2 py-0.5 rounded-sm border ${roleCfg.color} ${roleCfg.border} ${roleCfg.bg}`}>
            {roleCfg.label}
          </span>

          {/* 鉤子技術（定位幕專用） */}
          {hookLabel && (
            <span className="text-[8px] mono px-1.5 py-0.5 rounded-sm bg-orange-500/10 border border-orange-500/20 text-orange-300/80">
              {hookLabel}
            </span>
          )}

          {/* Veo 推薦標記 */}
          {unit.veo_recommended && (
            <span className="text-[8px] mono px-1.5 py-0.5 rounded-sm bg-violet-500/15 border border-violet-500/30 text-violet-300 font-bold">
              ✦ VEO
            </span>
          )}
        </div>
        <span className="text-[9px] mono text-zinc-600 shrink-0">{unit.duration_seconds}s</span>
      </div>

      {/* Visual Slot */}
      {unit.imageUrl && (
        <Lightbox
          open={lightboxOpen}
          close={() => setLightboxOpen(false)}
          slides={[{ src: unit.imageUrl }]}
        />
      )}
      <div className={`${imageAspectClass} bg-black relative border-b border-zinc-800 overflow-hidden flex items-center justify-center`}>
        {unit.imageUrl ? (
          <img
            src={unit.imageUrl}
            alt={title}
            className="w-full h-full object-contain cursor-zoom-in"
            onClick={(e) => { e.stopPropagation(); setLightboxOpen(true); }}
            title="點擊放大"
          />
        ) : (
          <div className="flex flex-col items-center space-y-4 p-8 text-center">
            {unit.isGeneratingImage ? (
              <>
                <Loader2 className="w-8 h-8 text-zinc-700 animate-spin" />
                <span className="text-[9px] mono text-zinc-600 animate-pulse uppercase tracking-widest">Synthesizing_Frame</span>
              </>
            ) : (
              <>
                <div className="w-16 h-16 border border-zinc-900 rounded-lg flex items-center justify-center bg-zinc-950/40">
                  <ImageIcon className="w-6 h-6 text-zinc-800" />
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); onGenerateImage(unit.id); }}
                  className="px-5 py-2.5 bg-zinc-100 hover:bg-white text-zinc-950 text-[10px] font-black mono rounded-sm transition-all uppercase tracking-tight shadow-lg"
                >
                  Generate_Asset
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {/* Metadata */}
      <div className="p-4 space-y-3 bg-zinc-950/40 flex-1 flex flex-col">

        {/* Phenomenon + Mechanism */}
        <div className="space-y-1.5">
          <div className="flex items-start space-x-2">
            <Sparkles className="w-3 h-3 text-emerald-500/60 shrink-0 mt-0.5" />
            <h3 className="text-[11px] font-bold text-zinc-200 line-clamp-2">{title}</h3>
          </div>
          <p className="text-[10px] text-zinc-400 line-clamp-2 leading-relaxed">{body}</p>
        </div>

        {/* Voice Over */}
        {voiceOver && (
          <div className="space-y-1 pt-2 border-t border-zinc-800/50">
            <span className="text-[8px] mono text-zinc-600 uppercase font-bold flex items-center">
              <Mic className="w-2.5 h-2.5 mr-1.5" /> 旁白
            </span>
            <p className="text-[12px] text-zinc-100 leading-snug font-medium tracking-wide">
              {voiceOver}
            </p>
          </div>
        )}

        {/* Subtitle */}
        {subtitle && (
          <div className="flex items-center gap-2">
            <span className="text-[8px] mono text-zinc-600 uppercase font-bold flex items-center shrink-0">
              <PlayCircle className="w-2.5 h-2.5 mr-1.5" /> 字幕
            </span>
            <span className="text-[13px] font-black text-white bg-zinc-800 border border-zinc-700 px-2 py-0.5 rounded-sm tracking-wide inline-block">
              {subtitle}
            </span>
          </div>
        )}

        {/* Interaction Trigger + Bait Text */}
        {interactData && (
          <div className="space-y-1.5 pt-2 border-t border-zinc-800/50">
            <span className="text-[8px] mono text-zinc-600 uppercase font-bold flex items-center">
              <MousePointerClick className="w-2.5 h-2.5 mr-1.5" /> 互動觸發
            </span>
            <span className={`text-[10px] mono font-bold ${interactData.color}`}>
              {interactData.icon} {interactData.label}
            </span>
            {unit.interaction_bait_text && (
              <p className={`text-[11px] mono leading-snug ${interactData.color} opacity-80`}>
                「{unit.interaction_bait_text}」
              </p>
            )}
          </div>
        )}

        {/* SEO Keywords */}
        {keywords.length > 0 && (
          <div className="space-y-1.5 pt-2 border-t border-zinc-800/50">
            <span className="text-[8px] mono text-zinc-600 uppercase font-bold flex items-center">
              <Tag className="w-2.5 h-2.5 mr-1.5" /> SEO
            </span>
            <div className="flex flex-wrap gap-1">
              {keywords.slice(0, 4).map((kw, i) => (
                <span key={i} className="text-[8px] mono px-1.5 py-0.5 rounded bg-zinc-800/60 border border-zinc-700/50 text-zinc-500">
                  #{kw}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Veo Prompt */}
        {unit.veo_prompt && (
          <div className="pt-2 border-t border-zinc-800/50 space-y-1.5">
            <button
              onClick={(e) => { e.stopPropagation(); setVeoExpanded(v => !v); }}
              className={`w-full flex items-center justify-between text-[8px] mono uppercase font-bold transition-colors ${unit.veo_recommended ? 'text-violet-400' : 'text-zinc-600'}`}
            >
              <span className="flex items-center">
                <Video className="w-2.5 h-2.5 mr-1.5" />
                {unit.veo_recommended ? '✦ VEO 推薦轉片' : 'VEO 提示詞'}
              </span>
              {veoExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
            {veoExpanded && (
              <p className="text-[9px] text-zinc-500 leading-relaxed font-mono bg-zinc-900/50 p-2 rounded border border-zinc-800/50">
                {unit.veo_prompt}
              </p>
            )}
          </div>
        )}

        {/* Camera + Motion */}
        <div className="space-y-1.5 pt-2 border-t border-zinc-800/50">
          {unit.camera_mode && (
            <div className="flex items-center space-x-2">
              <Camera className="w-2.5 h-2.5 text-zinc-700 shrink-0" />
              <span className="text-[9px] mono text-zinc-600">{unit.camera_mode}</span>
            </div>
          )}
          {unit.motion_guidance && (
            <div className="flex items-center flex-wrap gap-2">
              <Film className="w-2.5 h-2.5 text-zinc-700 shrink-0" />
              <span className="text-[9px] mono px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400">
                {MOTION_EFFECT_LABEL[unit.motion_guidance.effect] || unit.motion_guidance.effect}
              </span>
              <span className="text-[9px] text-zinc-600 mono">{unit.motion_guidance.duration_seconds}s</span>
              {unit.motion_guidance.transition_to_next && (
                <div className="flex items-center space-x-1 text-[9px] text-zinc-700">
                  <ArrowRight className="w-2.5 h-2.5 shrink-0" />
                  <span>{unit.motion_guidance.transition_to_next}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Emotional Tone */}
        {unit.emotional_tone && (
          <p className="text-[9px] text-emerald-500/50 italic line-clamp-1">{unit.emotional_tone}</p>
        )}

        {/* Footer */}
        <div className="mt-auto pt-3 border-t border-zinc-800/50 flex items-center justify-between">
          <span className="text-[8px] mono text-zinc-700 uppercase font-bold tracking-widest">Unit_Ready</span>
          {unit.imageUrl && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500/40" />}
        </div>
      </div>
    </div>
  );
};

export default ObservationUnitCard;
