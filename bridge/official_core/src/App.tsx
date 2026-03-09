import React, { useState, useEffect } from 'react';
import { 
  FileText, 
  Download, 
  Globe, 
  CheckCircle2, 
  Loader2, 
  Copy, 
  ChevronRight, 
  FileJson, 
  Languages, 
  Youtube, 
  Zap,
  BookOpen,
  HelpCircle,
  AlertCircle,
  Video,
  Eye,
  Layout,
  FileCode,
  Folder,
  Image as ImageIcon,
  Upload,
  X
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import Markdown from 'react-markdown';
import JSZip from 'jszip';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { get, set, del } from 'idb-keyval';
import { generateSSOT, renderContentPack, generateImage, GenerationMode, ContentPack, SSOT, GeneratedImage, ImageMetadata } from './services/gemini';

type UserRole = 'EDITOR' | 'PUBLISHER' | 'VISUAL' | 'QA' | 'ALL';

const roleLabels: Record<UserRole, string> = {
  EDITOR: '剪輯師',
  PUBLISHER: '上架者',
  VISUAL: '視覺/設計',
  QA: '品管 (QA)',
  ALL: '全部 (預設)'
};

const roleGuides: Record<UserRole, { step1: string, step2: string, step3: string }> = {
  EDITOR: {
    step1: '打開「上架 / 視覺 / QA」中的「剪輯時間軸 (EDIT MAP)」',
    step2: '照時間軸排列素材，匯入旁白與 SRT 字幕',
    step3: '套用 BGM/SFX，並根據「素材索引」確認檔案用途'
  },
  PUBLISHER: {
    step1: '打開「上架 / 視覺 / QA」中的「上架與描述」與「封面包」',
    step2: '複製標題描述，並根據「封面包」製作或上傳封面',
    step3: '貼上至 YouTube 後台，完成一鍵發佈'
  },
  VISUAL: {
    step1: '打開「上架 / 視覺 / QA」中的「視覺素材包」與「圖片預覽」',
    step2: '查看鏡頭表與提示詞，下載已生成的圖片資產',
    step3: '根據「封面包」指引製作高品質影片封面'
  },
  QA: {
    step1: '打開「上架 / 視覺 / QA」中的「QA品質報告」',
    step2: '核對「剪輯時間軸」是否符合 SSOT 核心邏輯',
    step3: '檢查封面標題與上架標籤是否完整'
  },
  ALL: {
    step1: '瀏覽「原始規格」確認專案核心',
    step2: '依序檢查 EDIT MAP 與各分頁內容',
    step3: '點擊「Download Pack」下載一鍵發佈包'
  }
};

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export default function App() {
  const [topic, setTopic] = useState('');
  const [mode, setMode] = useState<GenerationMode>(GenerationMode.EXPLAIN);
  const [hookPreset, setHookPreset] = useState<'7.0s' | '8.0s' | '10.0s'>('8.0s');
  const [loadingSSOT, setLoadingSSOT] = useState(false);
  const [loadingPack, setLoadingPack] = useState(false);
  const [generationProgress, setGenerationProgress] = useState({ current: 0, total: 0, status: '' });
  const [ssot, setSsot] = useState<SSOT | null>(() => {
    const saved = localStorage.getItem('ssot');
    return saved ? JSON.parse(saved) : null;
  });
  const [pack, setPack] = useState<ContentPack | null>(() => {
    const saved = localStorage.getItem('pack');
    return saved ? JSON.parse(saved) : null;
  });
  const [generateImages, setGenerateImages] = useState(false); // Default to false for Text-Only mode
  const [iconMode, setIconMode] = useState<'text' | 'svg'>('text');
  const [selectedRole, setSelectedRole] = useState<UserRole>('ALL');
  const [activeTab, setActiveTab] = useState<'ssot' | 'pack' | 'images'>('ssot');
  const tabLabels: Record<string, string> = {
    ssot: '原始規格 (SSOT)',
    pack: '極簡兩件套',
    images: '圖片生成 (批次)'
  };
  const tabFolders: Record<string, string> = {
    ssot: '99_原始規格_SSOT/',
    pack: '02_剪輯(Edit)/',
    images: '04_視覺素材包/'
  };
  const [activeFile, setActiveFile] = useState<string>('draft_vo_srt');
  const [generatedImages, setGeneratedImages] = useState<Record<number, string | null>>({});
  const [generatedCoverImage, setGeneratedCoverImage] = useState<string | null>(null);
  const [isGeneratingImages, setIsGeneratingImages] = useState(false);
  const [isGeneratingCover, setIsGeneratingCover] = useState(false);
  const [imageProgress, setImageProgress] = useState({ current: 0, total: 0, status: '' });
  const [zoomedImage, setZoomedImage] = useState<string | null>(null);
  const [imageAspectRatio, setImageAspectRatio] = useState<"16:9" | "9:16">("16:9");
  const [referenceImage, setReferenceImage] = useState<{ data: string, mimeType: string } | null>(null);

  // Load generatedImages from IndexedDB on mount
  useEffect(() => {
    get('generatedImages').then((val) => {
      if (val) setGeneratedImages(val);
    });
    get('generatedCoverImage').then((val) => {
      if (val) setGeneratedCoverImage(val);
    });
  }, []);

  // Persist state to localStorage
  useEffect(() => {
    if (ssot) {
      localStorage.setItem('ssot', JSON.stringify(ssot));
    } else {
      localStorage.removeItem('ssot');
    }
  }, [ssot]);

  useEffect(() => {
    if (pack) {
      localStorage.setItem('pack', JSON.stringify(pack));
    } else {
      localStorage.removeItem('pack');
    }
  }, [pack]);

  // Prevent accidental reload during generation
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (loadingSSOT || loadingPack || isGeneratingImages || pack || ssot) {
        e.preventDefault();
        e.returnValue = '您有未儲存的進度，確定要離開嗎？'; // Required for Chrome
        return e.returnValue;
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [loadingSSOT, loadingPack, isGeneratingImages, pack, ssot]);

  // Prevent pull-to-refresh on mobile
  useEffect(() => {
    document.body.style.overscrollBehavior = 'none';
    return () => {
      document.body.style.overscrollBehavior = 'auto';
    };
  }, []);

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result as string;
      // result is in format: data:image/png;base64,iVBORw0KGgo...
      const [prefix, base64Data] = result.split(',');
      const mimeType = prefix.split(':')[1].split(';')[0];
      setReferenceImage({ data: base64Data, mimeType });
    };
    reader.readAsDataURL(file);
  };

  const handleGenerateCover = async () => {
    if (!pack || !pack.cover_prompt) return;
    setIsGeneratingCover(true);
    try {
      const base64Data = await generateImage(pack.cover_prompt, imageAspectRatio, 3, referenceImage || undefined);
      if (base64Data) {
        setGeneratedCoverImage(base64Data);
        set('generatedCoverImage', base64Data).catch(console.error);
      }
    } catch (error) {
      console.error("Failed to generate cover:", error);
      alert("封面生成失敗");
    } finally {
      setIsGeneratingCover(false);
    }
  };

  const handleRetrySingleImage = async (index: number) => {
    if (!pack || !pack.image_prompts || !pack.image_prompts[index]) return;
    
    // Set status to generating for this specific image
    setGeneratedImages(prev => ({ ...prev, [index]: undefined })); // undefined means generating/not generated yet
    
    try {
      const img = pack.image_prompts[index];
      const base64Data = await generateImage(img.prompt, imageAspectRatio, 3, referenceImage || undefined);
      if (base64Data) {
        setGeneratedImages(prev => {
          const next = { ...prev, [index]: base64Data };
          set('generatedImages', next).catch(console.error);
          return next;
        });
      }
    } catch (error: any) {
      console.error(`Failed to regenerate image ${index}:`, error);
      setGeneratedImages(prev => {
        const next = { ...prev, [index]: null }; // null means failed
        set('generatedImages', next).catch(console.error);
        return next;
      });
      if (error.message?.includes('429') || error.status === 429 || error.code === 429) {
        alert('API 限制 (429)，請稍後再試。');
      }
    }
  };

  const handleGenerateImagesBatch = async (startIndex: number) => {
    if (!pack || !pack.image_prompts) return;
    
    setIsGeneratingImages(true);
    let currentIndex = startIndex;
    const totalImages = pack.image_prompts.length;
    
    while (currentIndex < totalImages) {
      const batchSize = 5;
      const endIndex = Math.min(currentIndex + batchSize, totalImages);
      setImageProgress({ current: currentIndex, total: totalImages, status: '生成中...' });

      for (let i = currentIndex; i < endIndex; i++) {
        const img = pack.image_prompts[i];
        try {
          // Set current to i (0-based index being generated)
          setImageProgress(prev => ({ ...prev, current: i, status: `生成圖片 ${i + 1}/${totalImages}...` }));
          const base64Data = await generateImage(img.prompt, imageAspectRatio, 3, referenceImage || undefined);
          if (base64Data) {
            setGeneratedImages(prev => {
              const next = { ...prev, [i]: base64Data };
              set('generatedImages', next).catch(console.error);
              return next;
            });
          }
        } catch (error: any) {
          console.error(`Failed to generate image ${i}:`, error);
          if (error.message?.includes('429') || error.status === 429 || error.code === 429) {
            setImageProgress(prev => ({ ...prev, current: i, status: 'API 限制 (429)，已停止生成。請稍後再試。' }));
            setIsGeneratingImages(false);
            return; // Stop the entire batch process
          }
          // Mark as failed
          setGeneratedImages(prev => {
            const next = { ...prev, [i]: null };
            set('generatedImages', next).catch(console.error);
            return next;
          });
        }
      }
      
      currentIndex = endIndex;
      
      if (currentIndex < totalImages) {
        // Wait 2 minutes (120,000 ms) before the next batch
        setImageProgress(prev => ({ ...prev, current: currentIndex, status: '等待 2 分鐘以避免 API 限制...' }));
        
        // Update countdown every second
        let timeLeft = 120;
        while (timeLeft > 0) {
          setImageProgress(prev => ({ ...prev, current: currentIndex, status: `等待冷卻中... ${Math.floor(timeLeft / 60)}:${String(timeLeft % 60).padStart(2, '0')}` }));
          await new Promise(resolve => setTimeout(resolve, 1000));
          timeLeft--;
        }
      }
    }
    
    setIsGeneratingImages(false);
    setImageProgress({ current: totalImages, total: totalImages, status: '已完成' });
  };

  const handleGenerateSSOT = async () => {
    if (!topic.trim()) {
      alert('請先填寫主題。');
      return;
    }
    setLoadingSSOT(true);
    try {
      const result = await generateSSOT(topic, mode);
      setSsot(result);
      setPack(null); // Reset pack when SSOT changes
      setGeneratedImages({});
      setGeneratedCoverImage(null);
      del('generatedImages').catch(console.error);
      del('generatedCoverImage').catch(console.error);
      setActiveTab('ssot');
    } catch (error) {
      console.error('SSOT generation failed:', error);
      alert('SSOT 生成失敗，請稍後再試。');
    } finally {
      setLoadingSSOT(false);
    }
  };

  const handleRenderPack = async () => {
    if (!ssot) {
      alert('缺少 SSOT，請先按「產生 SSOT」。');
      return;
    }
    setLoadingPack(true);
    setGenerationProgress({ current: 0, total: 0, status: '正在生成腳本與結構...' });
    try {
      let result: ContentPack;
      try {
        result = await renderContentPack(ssot, mode, hookPreset);
      } catch (error: any) {
        console.error('LLM Render failed:', error);
        const is429 = error.message?.includes('429') || error.status === 429 || error.code === 429;
        
        // [Degraded Delivery Fallback]
        result = {
          is_degraded: true,
          draft_vo_srt: '1\n00:00:00,000 --> 00:00:05,000\n【待補旁白】\n\n[ALERT] 內容包腳本生成失敗，已啟動降級交付模式。',
          draft_subtitles_srt: '1\n00:00:00,000 --> 00:00:05,000\n【待補字幕】\n\n[ALERT] 內容包腳本生成失敗，已啟動降級交付模式。',
          runbook_all_in_one: `[ALERT] 內容包腳本生成失敗：${error.message || '未知錯誤'}。無法產生剪輯總指揮檔。`,
          seo_txt: `[ALERT] 內容包腳本生成失敗：${error.message || '未知錯誤'}。無法產生 SEO 資訊檔。`
        };
        
        if (is429) {
          alert('偵測到 API 配額限制 (429)，已啟動「降級交付」模式。您仍可下載包含 SSOT 與補跑提示詞的 zip 包。');
        } else {
          alert(`渲染腳本時發生錯誤：${error.message || '未知錯誤'}。已啟動「降級交付」模式。`);
        }
      }
      
      // Segmented Rendering: Show text content immediately
      setPack({ ...result });
      setGeneratedImages({});
      setGeneratedCoverImage(null);
      del('generatedImages').catch(console.error);
      del('generatedCoverImage').catch(console.error);
      setActiveTab('pack');
      setActiveFile('draft_vo_srt');
      
      setGenerationProgress({ current: 0, total: 0, status: '' });
    } catch (error: any) {
      console.error('Unexpected Pack rendering error:', error);
      alert(`渲染過程發生非預期錯誤：${error.message || '未知錯誤'}。但您仍可嘗試下載已生成的內容。`);
    } finally {
      setLoadingPack(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const downloadZip = async () => {
    if (!ssot || !pack) return;
    const zip = new JSZip();
    
    // 02_剪輯(Edit)/
    const editFolder = zip.folder('02_剪輯(Edit)');
    editFolder?.file('01_旁白_VO.srt', pack.draft_vo_srt?.trim() || '1\n00:00:00,000 --> 00:00:05,000\n【待補旁白】\n\n[ALERT] 無法生成 SRT');
    editFolder?.file('02_畫面字幕_Subtitles.srt', pack.draft_subtitles_srt?.trim() || '1\n00:00:00,000 --> 00:00:05,000\n【待補字幕】\n\n[ALERT] 無法生成 SRT');
    editFolder?.file('03_剪輯指引_ALL_IN_ONE.md', pack.runbook_all_in_one || '[ALERT] 無法產生剪輯總指揮檔');
    
    // 03_發布(Publish)/
    const publishFolder = zip.folder('03_發布(Publish)');
    publishFolder?.file('seo.txt', pack.seo_txt || '[ALERT] 無法產生 SEO 資訊檔');
    
    const content = await zip.generateAsync({ type: 'blob' });
    const url = URL.createObjectURL(content);
    const link = document.createElement('a');
    link.href = url;
    link.download = `ContentPack_${ssot.topic.replace(/\s+/g, '_')}.zip`;
    link.click();
  };

  const downloadImagesZip = async () => {
    if (!pack || !pack.image_prompts) return;
    const zip = new JSZip();
    
    const imagesFolder = zip.folder('04_視覺素材包');
    if (pack.cover_prompt) {
      imagesFolder?.file(`000_Cover.txt`, `[PROMPT]\n${pack.cover_prompt}\n\n[CHAPTER]\nCover`);
      if (generatedCoverImage) {
        imagesFolder?.file(`000_Cover.png`, generatedCoverImage, { base64: true });
      }
    }
    pack.image_prompts.forEach((img, index) => {
      imagesFolder?.file(`${String(index + 1).padStart(3, '0')}_${img.filename}.txt`, `[PROMPT]\n${img.prompt}\n\n[CHAPTER]\n${img.chapter}`);
      if (generatedImages[index]) {
        imagesFolder?.file(`${String(index + 1).padStart(3, '0')}_${img.filename}.png`, generatedImages[index], { base64: true });
      }
    });
    
    const content = await zip.generateAsync({ type: 'blob' });
    const url = URL.createObjectURL(content);
    const link = document.createElement('a');
    link.href = url;
    link.download = `Images_Batch_${ssot?.topic.replace(/\s+/g, '_') || 'pack'}.zip`;
    link.click();
  };

  const CopyBlock = ({ title, content, mono = false, role }: { title: string, content: string, mono?: boolean, role?: string }) => (
    <div className="bg-[#F5F5F3] border border-[#141414] rounded-sm overflow-hidden mb-6 group relative">
      <div className="flex justify-between items-center px-4 py-2 border-b border-[#141414] bg-white/50">
        <div className="flex items-center gap-2">
          <h5 className="text-[10px] uppercase tracking-widest font-bold opacity-60">{title}</h5>
          {role && <span className="text-[8px] bg-[#141414] text-white px-1 rounded-sm opacity-40">{role}</span>}
        </div>
        <button 
          onClick={() => copyToClipboard(content)}
          className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest hover:text-[#00A3FF] transition-colors"
        >
          <Copy size={12} />
          Copy
        </button>
      </div>
      <div className={cn(
        "p-4 text-sm whitespace-pre-wrap max-h-[200px] overflow-auto",
        mono && "font-mono text-xs"
      )}>
        {content}
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-[#E4E3E0] text-[#141414] font-sans selection:bg-[#141414] selection:text-[#E4E3E0]">
      {/* Header */}
      <header className="border-b border-[#141414] p-6 flex justify-between items-center bg-white/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-[#141414] flex items-center justify-center rounded-sm">
            <Zap className="text-[#E4E3E0] w-6 h-6" />
          </div>
          <div>
            <h1 className="font-serif italic text-2xl leading-none">長影片文本包生成器</h1>
            <p className="text-[10px] uppercase tracking-widest opacity-50 mt-1 font-mono">文本包模式 (Text-Only Pack)</p>
          </div>
        </div>
        
        {pack && (
          <div className="flex gap-2">
            {activeTab === 'images' ? (
              <button 
                onClick={downloadImagesZip}
                className="flex items-center gap-2 bg-[#00A3FF] text-white px-4 py-2 rounded-full text-sm font-medium hover:opacity-90 transition-opacity"
              >
                <Download size={16} />
                下載圖片提示詞包
              </button>
            ) : (
              <button 
                onClick={downloadZip}
                className="flex items-center gap-2 bg-[#141414] text-[#E4E3E0] px-4 py-2 rounded-full text-sm font-medium hover:opacity-90 transition-opacity"
              >
                <Download size={16} />
                下載素材包
              </button>
            )}
          </div>
        )}
      </header>

      <main className="max-w-7xl mx-auto p-6 grid grid-cols-1 lg:grid-cols-[350px_1fr] gap-8">
        {/* Sidebar Controls */}
        <aside className="space-y-6">
          <div className="bg-white border border-[#141414] p-6 rounded-sm shadow-[4px_4px_0px_0px_rgba(20,20,20,1)]">
            <div className="mb-6">
              <label className="block text-[11px] uppercase tracking-wider font-mono opacity-50 mb-2 italic">角色選擇 (Role Selection)</label>
              <select 
                value={selectedRole}
                onChange={(e) => setSelectedRole(e.target.value as UserRole)}
                className="w-full bg-transparent border-b border-[#141414] py-2 focus:outline-none text-sm font-bold"
              >
                {(Object.keys(roleLabels) as UserRole[]).map(role => (
                  <option key={role} value={role}>{roleLabels[role]}</option>
                ))}
              </select>
            </div>

            <label className="block text-[11px] uppercase tracking-wider font-mono opacity-50 mb-2 italic">主題 / 內容 (Topic / Subject)</label>
            <textarea 
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. The history of quantum computing..."
              className="w-full bg-transparent border-b border-[#141414] py-2 focus:outline-none resize-none h-24 text-lg"
            />

            <div className="mt-6">
              <label className="block text-[11px] uppercase tracking-wider font-mono opacity-50 mb-3 italic">生成模式 (Generation Mode)</label>
              <div className="grid grid-cols-2 gap-2">
                <button 
                  onClick={() => setMode(GenerationMode.EXPLAIN)}
                  className={cn(
                    "flex items-center justify-center gap-2 py-2 border border-[#141414] text-xs font-medium transition-all",
                    mode === GenerationMode.EXPLAIN ? "bg-[#141414] text-[#E4E3E0]" : "hover:bg-[#141414]/5"
                  )}
                >
                  <BookOpen size={14} />
                  知識解說
                </button>
                <button 
                  onClick={() => setMode(GenerationMode.MYTH)}
                  className={cn(
                    "flex items-center justify-center gap-2 py-2 border border-[#141414] text-xs font-medium transition-all",
                    mode === GenerationMode.MYTH ? "bg-[#141414] text-[#E4E3E0]" : "hover:bg-[#141414]/5"
                  )}
                >
                  <HelpCircle size={14} />
                  迷思破解
                </button>
              </div>
            </div>

            <div className="mt-6">
              <label className="block text-[11px] uppercase tracking-wider font-mono opacity-50 mb-3 italic">Hook 時長 (Hook Duration)</label>
              <div className="grid grid-cols-3 gap-2">
                <button 
                  onClick={() => setHookPreset('7.0s')}
                  className={cn(
                    "flex items-center justify-center gap-2 py-2 border border-[#141414] text-xs font-medium transition-all",
                    hookPreset === '7.0s' ? "bg-[#141414] text-[#E4E3E0]" : "hover:bg-[#141414]/5"
                  )}
                >
                  7.0s (快)
                </button>
                <button 
                  onClick={() => setHookPreset('8.0s')}
                  className={cn(
                    "flex items-center justify-center gap-2 py-2 border border-[#141414] text-xs font-medium transition-all",
                    hookPreset === '8.0s' ? "bg-[#141414] text-[#E4E3E0]" : "hover:bg-[#141414]/5"
                  )}
                >
                  8.0s (中)
                </button>
                <button 
                  onClick={() => setHookPreset('10.0s')}
                  className={cn(
                    "flex items-center justify-center gap-2 py-2 border border-[#141414] text-xs font-medium transition-all",
                    hookPreset === '10.0s' ? "bg-[#141414] text-[#E4E3E0]" : "hover:bg-[#141414]/5"
                  )}
                >
                  10.0s (慢)
                </button>
              </div>
            </div>

            <div className="mt-8 space-y-3">
              <button 
                onClick={handleGenerateSSOT}
                disabled={loadingSSOT || loadingPack || !topic}
                className="w-full bg-[#141414] text-[#E4E3E0] py-4 flex items-center justify-center gap-3 font-bold uppercase tracking-widest text-sm disabled:opacity-30 group"
              >
                {loadingSSOT ? (
                  <Loader2 className="animate-spin" size={20} />
                ) : (
                  <>
                    <FileJson size={18} />
                    產生 SSOT
                  </>
                )}
              </button>

              <button 
                onClick={handleRenderPack}
                disabled={loadingSSOT || loadingPack || !ssot}
                className={cn(
                  "w-full py-4 flex items-center justify-center gap-3 font-bold uppercase tracking-widest text-sm transition-all border border-[#141414]",
                  ssot ? "bg-white text-[#141414] hover:bg-[#141414] hover:text-[#E4E3E0]" : "opacity-30 cursor-not-allowed"
                )}
              >
                {loadingPack ? (
                  <Loader2 className="animate-spin" size={20} />
                ) : (
                  <>
                    <Video size={18} />
                    渲染內容包
                  </>
                )}
              </button>
            </div>
          </div>

          <div className="bg-[#141414] text-[#E4E3E0] p-6 rounded-sm font-mono text-[10px] leading-relaxed opacity-90">
            <p className="mb-2 text-[#00A3FF] uppercase tracking-widest font-bold">系統狀態 (System Status)</p>
            <p>• Gemini 3.1 Pro 啟動中</p>
            <p>• 輸出合約：V2.9 (視覺抗單調)</p>
            <p>• 多國語言引擎：已開啟</p>
            <p>• SSOT 驗證：{ssot ? '100% 通過' : '待命'}</p>
            <p>• 內容包狀態：{pack ? '渲染完成' : '未生成'}</p>
          </div>
        </aside>

        {/* Content Area */}
        <section className="min-h-[600px]">
          {!ssot && !loadingSSOT && (
            <div className="h-full border-2 border-dashed border-[#141414]/20 rounded-sm flex flex-col items-center justify-center text-[#141414]/40 p-12 text-center">
              <Zap size={48} className="mb-4 opacity-20" />
              <h3 className="font-serif italic text-2xl mb-2">準備就緒</h3>
              <p className="max-w-md text-sm">輸入主題並點擊「產生 SSOT」開始架構專案。</p>
            </div>
          )}

          {/* Loading State for SSOT or Initial Pack */}
          {(loadingSSOT || (loadingPack && !pack)) && (
            <div className="h-full flex flex-col items-center justify-center p-12 text-center">
              <Loader2 className="animate-spin mb-6 text-[#141414]" size={48} />
              <h3 className="font-serif italic text-2xl mb-2">
                {loadingSSOT ? '正在架構 SSOT' : '正在渲染內容包'}
              </h3>
              <p className="max-w-md text-sm opacity-60">
                {loadingSSOT ? '建立專案唯一真相來源...' : '正在撰寫雙語腳本並生成視覺資產...'}
              </p>
            </div>
          )}

          {ssot && !loadingSSOT && (pack || !loadingPack) && (
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-white border border-[#141414] rounded-sm shadow-[8px_8px_0px_0px_rgba(20,20,20,1)] overflow-hidden flex flex-col h-full relative"
            >
              {/* Background Generation Progress Bar */}
              {loadingPack && pack && generationProgress.total > 0 && (
                <div className="absolute top-0 left-0 right-0 h-1 bg-[#141414]/5 z-50">
                  <motion.div 
                    className="h-full bg-[#00A3FF]"
                    initial={{ width: 0 }}
                    animate={{ width: `${(generationProgress.current / generationProgress.total) * 100}%` }}
                  />
                  <div className="absolute top-1 right-2 text-[8px] font-mono opacity-40 bg-white/80 px-1 rounded-sm flex items-center gap-2">
                    <span>背景生成中: {generationProgress.status} ({Math.round((generationProgress.current / generationProgress.total) * 100)}%)</span>
                  </div>
                </div>
              )}
              {/* Tabs */}
              <div className="flex border-b border-[#141414] bg-[#F5F5F3]">
                {[
                  { id: 'ssot', label: tabLabels.ssot, icon: <FileJson size={14} />, enabled: true },
                  { id: 'pack', label: tabLabels.pack, icon: <Globe size={14} />, enabled: !!pack },
                  { id: 'images', label: tabLabels.images, icon: <ImageIcon size={14} />, enabled: !!pack && !!pack.image_prompts },
                ].map((tab) => (
                  <button
                    key={tab.id}
                    disabled={!tab.enabled}
                    onClick={() => {
                      setActiveTab(tab.id as any);
                      if (tab.id === 'pack') setActiveFile('draft_vo_srt');
                    }}
                    className={cn(
                      "flex items-center gap-2 px-6 py-4 text-xs font-bold uppercase tracking-widest border-r border-[#141414] transition-all",
                      activeTab === tab.id ? "bg-white border-b-2 border-b-white -mb-[1px]" : "opacity-50 hover:opacity-100",
                      !tab.enabled && "opacity-20 cursor-not-allowed"
                    )}
                  >
                    {tab.icon}
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Folder Guidance & Role Guide */}
              <div className="border-b border-[#141414]/10">
                <div className="px-8 py-2 bg-[#141414]/5 flex items-center justify-between border-b border-[#141414]/10">
                  <div className="flex items-center gap-2 text-[10px] font-mono opacity-50">
                    <Folder size={12} />
                    <span>對應下載資料夾：{tabFolders[activeTab]}</span>
                  </div>
                  <div className="text-[9px] font-bold text-[#141414] uppercase tracking-widest opacity-40">
                    適用角色：{selectedRole === 'ALL' ? '全部' : roleLabels[selectedRole]}
                  </div>
                </div>

                <div className="px-8 py-4 bg-[#00A3FF]/5">
                  <div className="flex items-start gap-4">
                    <div className="mt-1 p-1 bg-[#00A3FF] text-white rounded-sm">
                      <ChevronRight size={14} />
                    </div>
                    <div className="space-y-1">
                      <h4 className="text-[10px] uppercase tracking-widest font-bold text-[#00A3FF]">你現在該做什麼 (Guide)</h4>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="flex gap-2 items-center">
                          <span className="text-[10px] font-mono opacity-40">01</span>
                          <p className="text-xs font-medium">{roleGuides[selectedRole].step1}</p>
                        </div>
                        <div className="flex gap-2 items-center">
                          <span className="text-[10px] font-mono opacity-40">02</span>
                          <p className="text-xs font-medium">{roleGuides[selectedRole].step2}</p>
                        </div>
                        <div className="flex gap-2 items-center">
                          <span className="text-[10px] font-mono opacity-40">03</span>
                          <p className="text-xs font-medium">{roleGuides[selectedRole].step3}</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Sub-navigation for Pack Tab */}
              {activeTab === 'pack' && pack && (
                <div className="flex gap-4 px-6 py-3 bg-white border-b border-[#141414]/10">
                  {[
                    { id: 'draft_vo_srt', label: '旁白 (VO SRT)' },
                    { id: 'draft_subtitles_srt', label: '畫面字幕 (Sub SRT)' },
                    { id: 'runbook_all_in_one', label: '剪輯指引 (ALL_IN_ONE)' },
                    { id: 'seo_txt', label: 'SEO 資訊檔' },
                  ].map((file) => (
                    <button
                      key={file.id}
                      onClick={() => setActiveFile(file.id)}
                      className={cn(
                        "text-[10px] uppercase tracking-widest font-bold pb-1 transition-all",
                        activeFile === file.id ? "border-b-2 border-[#141414]" : "opacity-40 hover:opacity-100"
                      )}
                    >
                      {file.label}
                    </button>
                  ))}
                </div>
              )}

              {/* Content Display */}
              <div className="flex-1 overflow-auto p-8 relative group">
                {(activeTab === 'pack') && (
                  <button 
                    onClick={() => {
                      let content = '';
                      if (activeFile === 'runbook_all_in_one') {
                        content = pack.runbook_all_in_one || '';
                      } else if (activeFile === 'draft_vo_srt') {
                        content = pack.draft_vo_srt || '';
                      } else if (activeFile === 'draft_subtitles_srt') {
                        content = pack.draft_subtitles_srt || '';
                      } else {
                        content = pack.seo_txt || '';
                      }
                      copyToClipboard(content);
                    }}
                    className="absolute top-6 right-6 p-2 bg-[#141414] text-[#E4E3E0] rounded-sm opacity-0 group-hover:opacity-100 transition-opacity z-10"
                    title="Copy to clipboard"
                  >
                    <Copy size={16} />
                  </button>
                )}
                <div className="max-w-none prose prose-sm prose-neutral">
                  {activeTab === 'ssot' && (
                    <div className="space-y-8 font-mono text-sm">
                      <div className="flex justify-between items-center mb-4">
                        <h3 className="text-lg font-serif italic">原始規格摘要</h3>
                        <span className="text-[9px] font-bold text-[#141414]/40 uppercase tracking-widest">適用角色：品管 (QA) / 全部</span>
                      </div>
                      <section>
                        <h4 className="text-[11px] uppercase tracking-widest opacity-40 mb-2 italic">Topic</h4>
                        <p className="text-xl font-serif italic">{ssot.topic}</p>
                      </section>
                      <section>
                        <h4 className="text-[11px] uppercase tracking-widest opacity-40 mb-2 italic">One Line Promise</h4>
                        <p className="text-lg">{ssot.one_line_promise}</p>
                      </section>
                      <div className="grid grid-cols-2 gap-8">
                        <section>
                          <h4 className="text-[11px] uppercase tracking-widest opacity-40 mb-2 italic">Key Claims</h4>
                          <ul className="space-y-1 list-none p-0">
                            {ssot.key_claims.map((claim: string, i: number) => (
                              <li key={i} className="flex gap-2">
                                <span className="opacity-30">0{i+1}</span>
                                {claim}
                              </li>
                            ))}
                          </ul>
                        </section>
                        <section>
                          <h4 className="text-[11px] uppercase tracking-widest opacity-40 mb-2 italic">Chapter Outline</h4>
                          <ul className="space-y-1 list-none p-0">
                            {ssot.chapter_outline.map((chapter: string, i: number) => (
                              <li key={i} className="flex gap-2">
                                <span className="opacity-30">CH{i+1}</span>
                                {chapter}
                              </li>
                            ))}
                          </ul>
                        </section>
                      </div>
                      <section>
                        <h4 className="text-[11px] uppercase tracking-widest opacity-40 mb-2 italic">Visual List</h4>
                        <div className="grid grid-cols-2 gap-2">
                          {ssot.visual_list.map((visual: string, i: number) => (
                            <div key={i} className="flex gap-2 items-start">
                              <span className="opacity-30 mt-1">[{i+1}]</span>
                              <span>{visual}</span>
                            </div>
                          ))}
                        </div>
                      </section>
                    </div>
                  )}

                  {activeTab === 'pack' && pack && (
                    <div className="space-y-12">
                      {activeFile === 'runbook_all_in_one' && (
                        <div className="markdown-body">
                          <div className="flex justify-between items-center mb-6 pb-4 border-b border-[#141414]/10">
                            <h3 className="text-lg font-serif italic">剪輯總指揮 (ALL-IN-ONE)</h3>
                            <span className="text-[9px] font-bold text-[#141414]/40 uppercase tracking-widest">適用角色：剪輯師 / 全部</span>
                          </div>
                          <Markdown>{pack.runbook_all_in_one || 'No ALL-IN-ONE runbook generated.'}</Markdown>
                        </div>
                      )}

                      {activeFile === 'draft_vo_srt' && (
                        <div className="markdown-body">
                          <div className="flex justify-between items-center mb-6 pb-4 border-b border-[#141414]/10">
                            <h3 className="text-lg font-serif italic flex items-center gap-2">
                              旁白 (VO SRT)
                            </h3>
                            <div className="flex items-center gap-2">
                              <span className="text-[9px] font-bold text-[#141414]/40 uppercase tracking-widest">適用角色：剪輯師 / 全部</span>
                            </div>
                          </div>
                          <div className="space-y-2">
                            {pack.draft_vo_srt ? (
                              pack.draft_vo_srt.trim().split(/\n\s*\n/).map((block, idx) => {
                                const lines = block.split('\n');
                                if (lines.length < 3) {
                                  return <pre key={idx} className="whitespace-pre-wrap font-mono text-sm bg-gray-100 p-4 rounded-md">{block}</pre>;
                                }
                                const id = lines[0];
                                const time = lines[1];
                                const text = lines.slice(2).join('\n');
                                return (
                                  <div key={idx} className="flex items-start gap-4 p-4 bg-white border border-[#141414]/10 rounded-sm hover:border-[#141414]/30 transition-colors">
                                    <div className="flex-1">
                                      <div className="flex items-center gap-2 mb-1">
                                        <span className="text-[10px] font-mono opacity-40">#{id}</span>
                                        <span className="text-[10px] font-mono opacity-40">{time}</span>
                                      </div>
                                      <p className="text-sm font-medium">{text}</p>
                                    </div>
                                  </div>
                                );
                              })
                            ) : (
                              <div className="p-4 bg-gray-100 rounded-md text-sm font-mono">No VO SRT generated.</div>
                            )}
                          </div>
                        </div>
                      )}

                      {activeFile === 'draft_subtitles_srt' && (
                        <div className="markdown-body">
                          <div className="flex justify-between items-center mb-6 pb-4 border-b border-[#141414]/10">
                            <h3 className="text-lg font-serif italic">畫面字幕 (Subtitles SRT)</h3>
                            <span className="text-[9px] font-bold text-[#141414]/40 uppercase tracking-widest">適用角色：剪輯師 / 全部</span>
                          </div>
                          <pre className="whitespace-pre-wrap font-mono text-sm bg-gray-100 p-4 rounded-md">
                            {pack.draft_subtitles_srt || 'No Subtitles SRT generated.'}
                          </pre>
                        </div>
                      )}

                      {activeFile === 'seo_txt' && (
                        <div className="markdown-body">
                          <div className="flex justify-between items-center mb-6 pb-4 border-b border-[#141414]/10">
                            <h3 className="text-lg font-serif italic">SEO 資訊檔</h3>
                            <span className="text-[9px] font-bold text-[#141414]/40 uppercase tracking-widest">適用角色：社群小編 / 全部</span>
                          </div>
                          <pre className="whitespace-pre-wrap font-mono text-sm bg-gray-100 p-4 rounded-md">
                            {pack.seo_txt || 'No SEO txt generated.'}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}

                  {activeTab === 'images' && pack && pack.image_prompts && (
                    <div className="space-y-8">
                      <div className="flex justify-between items-center mb-6 pb-4 border-b border-[#141414]/10">
                        <div>
                          <h3 className="text-lg font-serif italic">圖片提示詞 (Image Prompts)</h3>
                          <span className="text-[9px] font-bold text-[#141414]/40 uppercase tracking-widest">適用角色：視覺設計師 / 全部</span>
                        </div>
                        <div className="flex items-center gap-4">
                          {isGeneratingImages && (
                            <div className="text-[10px] font-mono opacity-60 flex items-center gap-2">
                              {imageProgress.status.includes('等待') ? (
                                <span className="text-orange-500">{imageProgress.status}</span>
                              ) : (
                                <>
                                  <Loader2 size={12} className="animate-spin" />
                                  {imageProgress.status} ({Math.min(imageProgress.current + 1, imageProgress.total)}/{imageProgress.total})
                                </>
                              )}
                            </div>
                          )}
                          <div className="flex items-center gap-2">
                            <label className="bg-white border border-[#141414] text-[#141414] px-3 py-2 rounded-sm text-xs font-bold uppercase tracking-widest cursor-pointer hover:bg-[#141414] hover:text-white transition-colors whitespace-nowrap">
                              {referenceImage ? '已上傳參考圖' : '上傳參考圖'}
                              <input 
                                type="file" 
                                accept="image/*" 
                                className="hidden" 
                                onChange={handleImageUpload}
                                disabled={isGeneratingImages}
                              />
                            </label>
                            {referenceImage && (
                              <button 
                                onClick={() => setReferenceImage(null)}
                                className="text-[10px] text-red-500 hover:text-red-700 font-bold uppercase"
                              >
                                移除
                              </button>
                            )}
                          </div>
                          <select 
                            value={imageAspectRatio} 
                            onChange={(e) => setImageAspectRatio(e.target.value as "16:9" | "9:16")}
                            disabled={isGeneratingImages}
                            className="bg-white border border-[#141414] text-[#141414] px-3 py-2 rounded-sm text-xs font-bold uppercase tracking-widest focus:outline-none focus:ring-2 focus:ring-[#141414]/20"
                          >
                            <option value="16:9">16:9 (橫式)</option>
                            <option value="9:16">9:16 (直式)</option>
                          </select>
                          <button
                            onClick={() => handleGenerateImagesBatch(imageProgress.current)}
                            disabled={isGeneratingImages || imageProgress.current >= pack.image_prompts!.length}
                            className="bg-[#141414] text-white px-4 py-2 rounded-sm text-xs font-bold uppercase tracking-widest disabled:opacity-30 transition-opacity"
                          >
                            {imageProgress.current >= pack.image_prompts!.length ? '已完成' : `開始批次生成 (${imageProgress.current}/${pack.image_prompts!.length})`}
                          </button>
                        </div>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {pack.cover_prompt && (
                          <div className="bg-white border border-[#141414] rounded-sm overflow-hidden shadow-[4px_4px_0px_0px_rgba(20,20,20,1)] flex flex-col md:col-span-2">
                            <div className="p-4 bg-[#F5F5F3] border-b border-[#141414] flex justify-between items-center">
                              <span className="text-[10px] uppercase tracking-widest font-bold opacity-60">Cover Image (封面)</span>
                              <div className="flex items-center gap-4">
                                <button 
                                  onClick={() => copyToClipboard(pack.cover_prompt!)}
                                  className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest hover:text-[#00A3FF] transition-colors"
                                >
                                  <Copy size={12} />
                                  Copy Prompt
                                </button>
                                <button
                                  onClick={handleGenerateCover}
                                  disabled={isGeneratingCover}
                                  className="bg-[#141414] text-white px-3 py-1 rounded-sm text-[10px] font-bold uppercase tracking-widest disabled:opacity-30 transition-opacity"
                                >
                                  {isGeneratingCover ? '生成中...' : (generatedCoverImage ? '重新生成' : '生成封面')}
                                </button>
                              </div>
                            </div>
                            <div className="flex flex-col md:flex-row">
                              <div className="p-4 space-y-4 flex-1 border-b md:border-b-0 md:border-r border-[#141414]">
                                <div>
                                  <span className="text-[10px] uppercase tracking-widest font-bold opacity-40 block mb-1">Prompt</span>
                                  <p className="text-sm text-[#141414]">{pack.cover_prompt}</p>
                                </div>
                              </div>
                              <div className="flex-1 bg-gray-50 p-4 flex items-center justify-center min-h-[200px]">
                                {generatedCoverImage ? (
                                  <div 
                                    className="group relative cursor-pointer"
                                    onClick={() => setZoomedImage(generatedCoverImage)}
                                  >
                                    <img src={`data:image/png;base64,${generatedCoverImage}`} alt="Cover" className="max-h-64 object-contain rounded-sm shadow-md" />
                                    <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center rounded-sm">
                                      <span className="bg-[#141414]/80 text-white px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-widest backdrop-blur-sm shadow-lg">點擊放大</span>
                                    </div>
                                  </div>
                                ) : (
                                  <span className="text-[10px] uppercase tracking-widest font-bold opacity-30">尚未生成封面</span>
                                )}
                              </div>
                            </div>
                          </div>
                        )}
                        {pack.image_prompts.map((img, index) => (
                          <div key={index} className="bg-white border border-[#141414] rounded-sm overflow-hidden shadow-[4px_4px_0px_0px_rgba(20,20,20,1)] flex flex-col">
                            <div className="p-4 bg-[#F5F5F3] border-b border-[#141414] flex justify-between items-center">
                              <span className="text-[10px] uppercase tracking-widest font-bold opacity-60">Image {index + 1}</span>
                              <button 
                                onClick={() => copyToClipboard(img.prompt)}
                                className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest hover:text-[#00A3FF] transition-colors"
                              >
                                <Copy size={12} />
                                Copy Prompt
                              </button>
                            </div>
                            <div className="p-4 space-y-4 flex-1">
                              <div>
                                <span className="text-[10px] uppercase tracking-widest font-bold text-[#00A3FF] block mb-1">Chapter</span>
                                <span className="text-sm font-medium">{img.chapter}</span>
                              </div>
                              <div>
                                <span className="text-[10px] uppercase tracking-widest font-bold opacity-40 block mb-1">Filename</span>
                                <span className="text-xs font-mono opacity-80">{img.filename}</span>
                              </div>
                              <div>
                                <span className="text-[10px] uppercase tracking-widest font-bold opacity-40 block mb-1">Prompt</span>
                                <p className="text-sm text-[#141414]">{img.prompt}</p>
                              </div>
                            </div>
                            {generatedImages[index] ? (
                              <div 
                                className="group relative border-t border-[#141414] p-4 bg-gray-50 flex items-center justify-center cursor-pointer hover:bg-gray-100 transition-colors"
                                onClick={() => setZoomedImage(generatedImages[index])}
                              >
                                <div className="relative inline-flex">
                                  <img src={`data:image/png;base64,${generatedImages[index]}`} alt={img.filename} className="max-h-48 object-contain rounded-sm" />
                                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center rounded-sm">
                                    <span className="bg-[#141414]/80 text-white px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-widest backdrop-blur-sm shadow-lg">點擊放大</span>
                                  </div>
                                </div>
                              </div>
                            ) : (
                              <div className="border-t border-[#141414] p-4 bg-gray-50 flex items-center justify-center h-24 text-[10px] uppercase tracking-widest font-bold opacity-30">
                                {isGeneratingImages && imageProgress.current === index && !imageProgress.status.includes('等待') ? (
                                  <span className="flex items-center gap-2"><Loader2 size={12} className="animate-spin" /> 生成中...</span>
                                ) : (
                                  isGeneratingImages && imageProgress.status.includes('等待') && index >= imageProgress.current && index < imageProgress.current + 5 ? (
                                    <span className="text-orange-500">等待批次冷卻...</span>
                                  ) : generatedImages[index] === null ? (
                                    <div className="flex flex-col items-center gap-2">
                                      <span className="text-red-500">生成失敗</span>
                                      <button 
                                        onClick={() => handleRetrySingleImage(index)}
                                        className="bg-[#141414] text-white px-3 py-1 rounded-sm text-[10px] hover:bg-[#141414]/80 transition-colors"
                                      >
                                        重新生成
                                      </button>
                                    </div>
                                  ) : generatedImages[index] === undefined && !isGeneratingImages ? (
                                    <div className="flex flex-col items-center gap-2">
                                      <span>尚未生成</span>
                                      <button 
                                        onClick={() => handleRetrySingleImage(index)}
                                        className="bg-[#141414] text-white px-3 py-1 rounded-sm text-[10px] hover:bg-[#141414]/80 transition-colors"
                                      >
                                        單張生成
                                      </button>
                                    </div>
                                  ) : generatedImages[index] === undefined ? (
                                    <span>尚未生成</span>
                                  ) : (
                                    <span className="flex items-center gap-2"><Loader2 size={12} className="animate-spin" /> 生成中...</span>
                                  )
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Footer Status */}
              <div className="border-t border-[#141414] px-6 py-3 bg-[#F5F5F3] flex justify-between items-center">
                <div className="flex items-center gap-4 text-[10px] uppercase tracking-widest font-bold opacity-40">
                  <span className="flex items-center gap-1"><CheckCircle2 size={10} /> SSOT 驗證通過</span>
                  {pack && (
                    <>
                      <span className="flex items-center gap-1"><CheckCircle2 size={10} /> 極簡兩件套就緒</span>
                    </>
                  )}
                </div>
                <div className="text-[10px] font-mono opacity-40">
                  專案 ID: {Math.random().toString(36).substring(7).toUpperCase()}
                </div>
              </div>
            </motion.div>
          )}
        </section>
      </main>

      {/* Footer */}
      <footer className="mt-20 border-t border-[#141414] p-12 bg-white">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-12">
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Zap size={20} />
              <span className="font-serif italic text-xl">長影片內容包生成器</span>
            </div>
            <p className="text-sm opacity-60 leading-relaxed">
              專業級創作者工具，極簡兩件套輸出。
            </p>
          </div>
          <div>
            <h4 className="text-[11px] uppercase tracking-widest font-bold mb-4">輸出合約 V3.0</h4>
            <ul className="text-xs space-y-2 opacity-60 font-mono">
              <li>• 旁白字幕_zh.srt</li>
              <li>• 剪輯指引_ALL_IN_ONE.md</li>
            </ul>
          </div>
          <div>
            <h4 className="text-[11px] uppercase tracking-widest font-bold mb-4">檢查清單</h4>
            <ul className="text-xs space-y-2 opacity-60">
              <li className="flex items-center gap-2"><CheckCircle2 size={12} className="text-green-600" /> 極簡兩件套</li>
              <li className="flex items-center gap-2"><CheckCircle2 size={12} className="text-green-600" /> TTS 主導時間軸</li>
              <li className="flex items-center gap-2"><CheckCircle2 size={12} className="text-green-600" /> 節奏斷點控制</li>
            </ul>
          </div>
        </div>
        <div className="max-w-7xl mx-auto mt-12 pt-12 border-t border-[#141414]/10 text-[10px] uppercase tracking-[0.2em] opacity-30 text-center">
          © 2026 長影片內容包生成器 • 基於 Gemini 3.1 Pro 構建
        </div>
      </footer>
      {/* Image Zoom Modal */}
      {zoomedImage && (
        <div 
          className="fixed inset-0 z-[100] bg-black/90 flex items-center justify-center p-4 cursor-zoom-out"
          onClick={() => setZoomedImage(null)}
        >
          <img 
            src={`data:image/png;base64,${zoomedImage}`} 
            alt="Zoomed" 
            className="max-w-full max-h-full object-contain rounded-sm shadow-2xl"
          />
          <div className="absolute top-6 right-6 text-white/50 text-sm font-mono uppercase tracking-widest">
            點擊任意處關閉
          </div>
        </div>
      )}
    </div>
  );
}
