import { PacingProfile } from '../types';
import { VideoMode } from '../services/geminiService';

/**
 * 三種步調 Profile，對應 VideoMode。
 * target_duration_range 單位：秒
 * beats 為佔比（加總 = 1）
 */
export const PACING_PROFILES: Record<VideoMode, PacingProfile> = {
  shorts: {
    id: 'shorts',
    label: '⚡ Shorts',
    target_duration_range: [15, 60],
    unit_range: [3, 6],
    beats: { hook: 0.15, body: 0.70, payoff: 0.15 },
    veo_budget: 2,
    caption_density: 'dense',
    cut_frequency: 'fast',
  },
  medium: {
    id: 'medium',
    label: '🎬 中片',
    target_duration_range: [180, 600],
    unit_range: [6, 15],
    beats: { hook: 0.10, body: 0.75, payoff: 0.15 },
    veo_budget: 5,
    caption_density: 'normal',
    cut_frequency: 'medium',
  },
  long: {
    id: 'long',
    label: '🎞️ 長片',
    target_duration_range: [1800, 3600],
    unit_range: [15, 40],
    beats: { hook: 0.05, body: 0.80, payoff: 0.15 },
    veo_budget: 10,
    caption_density: 'sparse',
    cut_frequency: 'slow',
  },
};

/** 將秒數格式化成人類可讀字串 */
export function formatDurationRange([min, max]: [number, number]): string {
  const fmt = (s: number) => {
    if (s < 60) return `${s}s`;
    const m = Math.round(s / 60);
    return `${m}min`;
  };
  return `${fmt(min)} – ${fmt(max)}`;
}

/** 依照 beats 比例，為每個 unit slot 指派 beat 標籤 */
export function assignBeats(
  beats: PacingProfile['beats'],
  unitCount: number,
): ('hook' | 'body' | 'payoff')[] {
  const hookCount  = Math.max(1, Math.round(beats.hook   * unitCount));
  const payoffCount = Math.max(1, Math.round(beats.payoff * unitCount));
  const bodyCount  = Math.max(0, unitCount - hookCount - payoffCount);

  return [
    ...Array(hookCount).fill('hook' as const),
    ...Array(bodyCount).fill('body' as const),
    ...Array(payoffCount).fill('payoff' as const),
  ];
}
