/**
 * bridge_adapter.ts — V35.7 Plan B
 * Thin wrapper over sacred services/gemini.ts.
 * Locks aspect_ratio="9:16". No business logic here.
 */
import { GoogleGenAI } from "@google/genai";
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

/** Nano Banana 2 — cover-only model with 1K resolution lock. */
const COVER_MODEL = "gemini-3.1-flash-image-preview";

/** Returns raw PNG bytes (9:16 locked via official imageConfig). Scene_001 path. */
export async function generateImageOfficial(prompt: string): Promise<Buffer> {
  const b64 = await generateImage(prompt, ASPECT_RATIO);
  if (!b64) throw new Error(`No image returned for: ${prompt.slice(0, 60)}`);
  return Buffer.from(b64, "base64");
}

/**
 * Cover-specific generator.
 * Model : gemini-3.1-flash-image-preview (Nano Banana 2)
 * Config: aspectRatio="9:16", imageSize="1K"
 * Sacred gemini.ts is bypassed; direct API call here.
 */
export async function generateCoverImageOfficial(prompt: string): Promise<Buffer> {
  const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY || "" });
  const response = await ai.models.generateContent({
    model: COVER_MODEL,
    contents: [{ parts: [{ text: prompt }] }],
    config: {
      imageConfig: {
        aspectRatio: ASPECT_RATIO,
        imageSize:   "1K",
      },
    },
  });
  const parts = response.candidates?.[0]?.content?.parts ?? [];
  for (const part of parts) {
    if (part.inlineData?.data) {
      return Buffer.from(part.inlineData.data, "base64");
    }
  }
  throw new Error(`No image from ${COVER_MODEL} for: ${prompt.slice(0, 60)}`);
}

/** Renders ContentPack from SSOT using official model chain. */
export async function renderPackOfficial(ssot: SSOT): Promise<ContentPack> {
  return renderContentPack(ssot, IMAGE_MODE);
}

/** Generates SSOT from topic string. */
export async function generateSSOTOfficial(topic: string): Promise<SSOT> {
  return generateSSOT(topic, IMAGE_MODE);
}
