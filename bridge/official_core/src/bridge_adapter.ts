/**
 * bridge_adapter.ts — V35.7 Plan B
 * Thin wrapper over sacred services/gemini.ts.
 * Locks aspect_ratio="9:16". No business logic here.
 */
import {
  generateImage,
  renderContentPack,
  generateSSOT,
  GenerationMode,
  type SSOT,
  type ContentPack,
} from "./services/gemini.js";

export { GenerationMode, type SSOT, type ContentPack };

export const ASPECT_RATIO = "9:16" as const;
export const IMAGE_MODE   = GenerationMode.EXPLAIN;

/** Returns raw PNG bytes (9:16 locked via official imageConfig). */
export async function generateImageOfficial(prompt: string): Promise<Buffer> {
  const b64 = await generateImage(prompt, ASPECT_RATIO);
  if (!b64) throw new Error(`No image returned for: ${prompt.slice(0, 60)}`);
  return Buffer.from(b64, "base64");
}

/** Renders ContentPack from SSOT using official model chain. */
export async function renderPackOfficial(ssot: SSOT): Promise<ContentPack> {
  return renderContentPack(ssot, IMAGE_MODE);
}

/** Generates SSOT from topic string. */
export async function generateSSOTOfficial(topic: string): Promise<SSOT> {
  return generateSSOT(topic, IMAGE_MODE);
}
