import { GoogleGenAI, Type, Modality } from "@google/genai";

function getAI() {
  return new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY || "" });
}

export enum GenerationMode {
  EXPLAIN = "Explain",
  MYTH = "Myth",
}

export interface SSOT {
  topic: string;
  one_line_promise: string;
  hook_intent: string;
  key_claims: string[];
  chapter_outline: string[];
  visual_list: string[];
}

export interface ImageMetadata {
  chapter: string;
  type: "WIDE" | "MID" | "MACRO" | "DIAGRAM_CARD" | "KEYWORD_CARD";
  purpose: string;
  prompt: string;
  filename: string;
  need_veo?: boolean;
  veo_prompt_zh?: string;
  veo_prompt_en?: string;
  veo_window?: string;
}

export interface GeneratedImage extends ImageMetadata {
  data_16x9: string; // base64
  data_9x16: string; // base64
}

export interface ContentPack {
  draft_vo_srt: string;
  draft_subtitles_srt: string;
  runbook_all_in_one: string;
  seo_txt: string;
  cover_prompt?: string;
  image_prompts?: {
    chapter: string;
    prompt: string;
    filename: string;
  }[];
  is_degraded?: boolean;
}

export async function generateSSOT(topic: string, mode: GenerationMode, retries = 3): Promise<SSOT> {
  const ai = getAI();
  const systemInstruction = `你是一個「長影片內容包生成器」。
你的任務是根據主題與模式，產生一份 master_ssot.json 作為專案的唯一真相（SSOT）。

硬規則：
1) 只輸出 JSON 格式。
2) 包含 6 個欄位：topic, one_line_promise, hook_intent, key_claims(3), chapter_outline(至少4章), visual_list(至少6項)。
3) 內容需適合 3–10 分鐘或 30–60 分鐘長片的章節化敘事。
4) 禁止生成示範內容，若主題不明確請報錯。`;

  const prompt = `請針對主題「${topic}」以「${mode}」模式生成 master_ssot.json。`;

  let lastError: any;
  for (let i = 0; i < retries; i++) {
    try {
      const response = await ai.models.generateContent({
        model: "gemini-3-flash-preview", // Downgraded for speed and lower quota usage
        contents: [{ parts: [{ text: prompt }] }],
        config: {
          systemInstruction,
          responseMimeType: "application/json",
          responseSchema: {
            type: Type.OBJECT,
            properties: {
              topic: { type: Type.STRING },
              one_line_promise: { type: Type.STRING },
              hook_intent: { type: Type.STRING },
              key_claims: { type: Type.ARRAY, items: { type: Type.STRING } },
              chapter_outline: { type: Type.ARRAY, items: { type: Type.STRING } },
              visual_list: { type: Type.ARRAY, items: { type: Type.STRING } },
            },
            required: ["topic", "one_line_promise", "hook_intent", "key_claims", "chapter_outline", "visual_list"]
          }
        },
      });

      return JSON.parse(response.text || "{}");
    } catch (error: any) {
      lastError = error;
      if (error.message?.includes('429') || error.status === 429 || error.code === 429) {
        const waitTime = Math.pow(2, i) * 2000 + Math.random() * 1000;
        console.warn(`SSOT Rate limit hit, retrying in ${Math.round(waitTime)}ms...`);
        await sleep(waitTime);
        continue;
      }
      throw error;
    }
  }
  throw lastError;
}

async function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export async function generateImage(prompt: string, aspectRatio: "16:9" | "9:16" = "16:9", retries = 3, referenceImage?: { data: string, mimeType: string }): Promise<string | null> {
  const ai = getAI();
  let lastError: any;
  
  const styleSuffix = "Fauvism style fused with traditional Chinese ink painting, wild and rough brushstrokes, bold color block collisions, ink bleeding and dripping textures, abstract dynamism, imperfect hand-drawn feel, eschewing smooth details and photorealistic rendering, raw energy aura. Centered composition, high contrast, textured paper background, studio lighting. Primitive style, no blur, no plastic feel, avoid perfect symmetry.";
  
  for (let i = 0; i < retries; i++) {
    try {
      // Fallback strategy:
      // i=0: full prompt + reference image
      // i=1: full prompt (no reference image)
      // i=2: simple prompt (no style suffix, no reference image)
      const currentPrompt = i === 2 ? prompt : `${prompt}, ${styleSuffix}`;
      const currentRef = i === 0 ? referenceImage : undefined;
      
      const parts: any[] = [];
      if (currentRef) {
        parts.push({
          inlineData: {
            data: currentRef.data,
            mimeType: currentRef.mimeType
          }
        });
      }
      parts.push({ text: currentPrompt });

      const response = await ai.models.generateContent({
        model: 'gemini-2.5-flash-image',
        contents: { parts },
        config: {
          imageConfig: { aspectRatio }
        }
      });
      
      const candidate = response.candidates?.[0];
      const responseParts = candidate?.content?.parts || [];
      
      for (const part of responseParts) {
        if (part.inlineData) {
          return part.inlineData.data;
        }
      }
      
      const textPart = responseParts.find(p => p.text)?.text;
      const finishReason = candidate?.finishReason;
      const blockReason = response.promptFeedback?.blockReason;
      
      console.warn(`Attempt ${i+1} failed to return image:`, { finishReason, blockReason, text: textPart });
      
      if (i === retries - 1) {
        throw new Error(`No image data returned from API. Reason: ${finishReason || blockReason || 'Unknown'}. Text: ${textPart || 'None'}`);
      }
    } catch (error: any) {
      lastError = error;
      // If it's a rate limit error (429), wait and retry
      if (error.message?.includes('429') || error.status === 429 || error.code === 429) {
        const waitTime = Math.pow(2, i) * 2000 + Math.random() * 1000;
        console.warn(`Rate limit hit, retrying in ${Math.round(waitTime)}ms...`);
        await sleep(waitTime);
        continue;
      }
      
      console.warn(`Attempt ${i+1} failed with error:`, error.message);
      if (i === retries - 1) {
        throw error; 
      }
    }
  }
  console.error("Image generation failed after retries:", lastError);
  throw lastError || new Error("Image generation failed after retries");
}

export async function renderContentPack(ssot: SSOT, mode: GenerationMode, hookPreset: string = '8.0s', retries = 3): Promise<ContentPack> {
  const ai = getAI();
  const systemInstruction = `你現在是一位追求極致節奏與幽默感的「百萬YouTuber影音導演」。
你的任務是根據 master_ssot.json 渲染「長片一鍵交付作業包」，並嚴格遵守以下原則生成影片腳本與素材描述：

【Rule 0：幽默詼諧，拒絕無聊】
- 內容必須以「幽默、詼諧、逗趣」為主軸，可以有反轉和吐槽。
- 絕對不可胡言亂語、缺乏根據或胡編亂造，必須緊扣使用者給的主題，保持專業底線但用有趣的方式表達。

【Rule 1：旁白與畫面字幕的雙重協奏】
- 旁白 (VO)：說話要極短，每段旁白絕對不能超過 10 個中文字。
- 畫面字幕 (Subtitle)：每段必須配有一句 ≤ 8 個字的畫面字幕。
- 協同關係：畫面字幕不是旁白的重複！它必須與旁白產生「協同關係」，可以是「吐槽旁白」、「補強核心價值」、「搞笑反轉」或「內心OS」。

【Rule 2：嚴格執行「9-15 呼吸法」與時碼計算】
- 前留白：每段畫面開始後，請空出 0.3 秒 (9 幀) 再開始出現聲音。
- 後留白：旁白說完後，畫面必須多停留 0.5 秒 (15 幀) 才能切換到下一幕。
- 單段公式：段落總時長 = 0.3秒 + (旁白字數 * 0.19秒) + 0.5秒。
- 時間碼格式：
  - 剪輯指引使用 SMPTE 格式：[HH:MM:SS:FF] (以 30fps 計算，FF 為 00~29)。
  - SRT 字幕檔使用標準格式：HH:MM:SS,mmm --> HH:MM:SS,mmm (CapCut 可讀取)。
  - 請在 SRT 和 MD 檔案中精確反映這段停頓與時碼。注意：旁白 SRT 和畫面字幕 SRT 的時間碼必須完全一致。

【Rule 3：視覺 Prompt 要有電影感 (VEO_SPEC) 與節省成本】
- 核心原則：10 秒內的長旁白必須由 2 個素材組成：一個是描述細節的「高品質靜態圖」，另一個是展現變化瞬間的「Veo 動態影片」。
- 語言：素材描述必須使用「英文」。
- 公式：請套用 [Subject] + [Action] + [Scene Lighting] + [Lens Focal Length] + [Visual Style]。
- 拒絕空洞：絕對禁止出現「Veo 動態 1~2s」這種模糊字眼，請為每個素材寫出 30 字以上的英文視覺描述，確保與主題 100% 相關。
- 禁止事項：提示詞末尾必須加上 "(No text, no watermarks, no logos)"。

【Rule 4：音效 (SFX) 關鍵爆點設計】
- 每一幕的關鍵爆點、轉折或吐槽，必須配上適合的音效 (SFX)。
- 必須在剪輯指引中標示音效的 In/Out 時間碼 (使用 CapCut 支援的 SMPTE 格式 [HH:MM:SS:FF])。

【Rule 5：偽動作 (Pseudo-actions) 設計】
- 針對靜態圖，必須在剪輯指引中加入「偽動作(in/out)」(例如：鏡頭緩慢推進、畫面震動、閃爍等)，並標示 In/Out 時間碼。
- 註：Veo 動態影片幕可以略過偽動作設計。

【輸出格式要求】
1) runbook_all_in_one (剪輯總指揮檔)：
   - 必須以 Markdown 格式輸出，設計成「時間軸軌道 (Timeline Tracks)」。
   - 結構範例：
     ### CH1: [章節標題]
     **[00:00:00:00 - 00:00:02:15]**
     - 🎤 [VO]: "這裡填入旁白台詞" (字數: 8字, 估算: 2.3秒)
     - 🔤 [Subtitle]: "這裡填入畫面字幕" (字數: ≤8字, 吐槽/補強)
     - 🎬 [Video]: [靜態圖] (30字以上英文描述...)
     - 🏃 [Action]: [偽動作描述，例如：鏡頭緩慢推進、畫面震動等] (In: [00:00:00:00] - Out: [00:00:02:15]) (註：Veo幕可以略過)
     - 🔊 [SFX]: [音效名稱/描述] (In: [00:00:01:00] - Out: [00:00:01:15])
2) draft_vo_srt (旁白 SRT)：
   - 必須是標準 SRT 格式，只包含旁白台詞。
3) draft_subtitles_srt (畫面字幕 SRT)：
   - 必須是標準 SRT 格式，只包含畫面字幕(≤8字)。
4) image_prompts (圖片提示詞陣列)：
   - 包含上述規劃的靜態圖與 Veo 提示詞。
   - 欄位：chapter, prompt (英文，需包含 No text... 結尾), filename。
5) seo_txt (SEO 資訊檔)：
   - 必須以純文字格式輸出。
   - 請針對不同平台 (YouTube, TikTok, Instagram, Facebook) 分別撰寫專屬的 SEO 資訊，因為各平台受眾與演算法喜好不同：
     - 【YouTube】: 標題需具備搜尋意圖與點擊誘因 (繁/英，繁中約18字，英文約25字)；描述需包含影片大綱與關鍵字 (約50字)；Tags 著重長尾關鍵字與搜尋熱門詞 (約15組)。
     - 【TikTok】: 標題需極具話題性、吸睛且口語化 (繁/英，字數精簡)；描述需引發留言互動或懸念 (約30字)；Tags 著重當下流行趨勢、短影音熱搜 (約8組)。
     - 【Instagram】: 標題需具備美感或強烈共鳴 (繁/英)；描述需適合閱讀，可加入適當表情符號 (約40字)；Tags 著重生活風格、探索頁面熱門標籤 (約10-15組)。
     - 【Facebook】: 標題需引發社群討論或分享共鳴 (繁/英)；描述需像是在跟朋友分享故事，引導留言或分享 (約50字)；Tags 著重廣泛興趣與社群話題 (約5-8組)。
   - 英文標題不要直翻，要生活化、在地化。
   - Tags 前面都要加 "#" 符號。
   - PS: 列表的格式，請保持良好的換行與閱讀性，各平台之間請用分隔線隔開。
6) cover_prompt (封面提示詞)：
   - 必須是英文，用來生成這支影片的吸引人封面圖。
   - 提示詞末尾必須加上 "(No text, no watermarks, no logos)"。`;

  const prompt = `請根據以下 SSOT 渲染內容包：\n${JSON.stringify(ssot, null, 2)}`;

  let lastError: any;
  for (let i = 0; i < retries; i++) {
    try {
      const response = await ai.models.generateContent({
        model: "gemini-3.1-pro-preview",
        contents: [{ parts: [{ text: prompt }] }],
        config: {
          systemInstruction,
          responseMimeType: "application/json",
          responseSchema: {
            type: Type.OBJECT,
            properties: {
              draft_vo_srt: { type: Type.STRING },
              draft_subtitles_srt: { type: Type.STRING },
              runbook_all_in_one: { type: Type.STRING },
              seo_txt: { type: Type.STRING },
              cover_prompt: { type: Type.STRING },
              image_prompts: {
                type: Type.ARRAY,
                items: {
                  type: Type.OBJECT,
                  properties: {
                    chapter: { type: Type.STRING },
                    prompt: { type: Type.STRING },
                    filename: { type: Type.STRING }
                  },
                  required: ["chapter", "prompt", "filename"]
                }
              }
            },
            required: ["draft_vo_srt", "draft_subtitles_srt", "runbook_all_in_one", "seo_txt", "cover_prompt", "image_prompts"]
          }
        }
      });

      return JSON.parse(response.text || "{}");
    } catch (error: any) {
      lastError = error;
      if (error.message?.includes('429') || error.status === 429 || error.code === 429) {
        const waitTime = Math.pow(2, i) * 2000 + Math.random() * 1000;
        console.warn(`Render Rate limit hit, retrying in ${Math.round(waitTime)}ms...`);
        await sleep(waitTime);
        continue;
      }
      throw error;
    }
  }
  throw lastError;
}
