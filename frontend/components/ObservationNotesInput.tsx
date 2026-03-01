
import React from 'react';
import { Terminal } from 'lucide-react';

interface ObservationNotesInputProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

const ObservationNotesInput: React.FC<ObservationNotesInputProps> = ({ 
  value, 
  onChange, 
  disabled 
}) => {
  return (
    <div className="flex flex-col space-y-3 w-full group">
      <div className="flex justify-between items-center">
        <label className="text-[9px] uppercase tracking-[0.2em] text-zinc-500 font-black flex items-center">
          <Terminal className="w-3.5 h-3.5 mr-2 opacity-50" /> Signal_Buffer_Input
        </label>
        <span className="text-[9px] mono text-zinc-700 bg-zinc-900 px-1.5 py-0.5 rounded border border-zinc-800">
          {value.length.toString().padStart(4, '0')}_BYTES
        </span>
      </div>
      
      <div className="relative">
        <textarea
          id="observation-notes"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder="ENTER_RAW_OBSERVATION_DATA..."
          className={`
            w-full min-h-[180px] bg-black/40 border border-zinc-800 rounded-sm p-4
            text-zinc-300 mono text-[11px] leading-relaxed focus:outline-none focus:ring-1 
            focus:ring-emerald-500/30 focus:border-emerald-500/30 transition-all resize-none
            placeholder:text-zinc-800 scrollbar-thin
            ${disabled ? 'opacity-30 cursor-not-allowed' : 'opacity-100'}
          `}
          spellCheck={false}
          autoComplete="off"
        />
        <div className="absolute bottom-3 right-3 opacity-10 pointer-events-none group-focus-within:opacity-40 transition-opacity">
           <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" className="text-emerald-500">
             <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
           </svg>
        </div>
      </div>
      <p className="text-[8px] mono text-zinc-600 leading-normal uppercase italic tracking-tighter">
        Note: Focus on observable phenomenon. Avoid narrative interpretation or causal explanation.
      </p>
    </div>
  );
};

export default ObservationNotesInput;