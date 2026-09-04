import React from 'react';
import {
  UploadCloud,
  FileScan,
  Tag,
  Cpu,
  ShieldAlert,
  ShieldCheck,
  FileSpreadsheet,
  Database,
  CheckCircle2,
  Clock,
  AlertTriangle,
} from 'lucide-react';
import { PipelineStep } from '../types';

interface PipelineVisualizerProps {
  steps?: PipelineStep[];
  activeStepIndex?: number;
  isProcessing?: boolean;
}

const DEFAULT_STEP_NAMES = [
  { name: 'UPLOAD', label: 'Upload', icon: UploadCloud },
  { name: 'OCR', label: 'Tesseract OCR', icon: FileScan },
  { name: 'CLASSIFICATION', label: 'Classification', icon: Tag },
  { name: 'RoBERTa NER', label: 'RoBERTa NER', icon: Cpu },
  { name: 'PII DETECTION', label: 'PII Detection', icon: ShieldAlert },
  { name: 'VALIDATION & REDACTION', label: 'Redaction', icon: ShieldCheck },
  { name: 'STRUCTURED EXTRACTION', label: 'Extraction', icon: FileSpreadsheet },
  { name: 'INDEXING & STORAGE', label: 'FAISS Storage', icon: Database },
];

export const PipelineVisualizer: React.FC<PipelineVisualizerProps> = ({
  steps = [],
  activeStepIndex,
  isProcessing = false,
}) => {
  return (
    <div className="w-full bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
            Intelligence Processing Pipeline
            {isProcessing && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200 animate-pulse">
                Processing Active
              </span>
            )}
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Real-time pipeline execution sequence across OCR, Neural NER, deterministic PII redaction and FAISS vector indexing.
          </p>
        </div>
      </div>

      {/* Horizontal Pipeline Sequence */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 relative">
        {DEFAULT_STEP_NAMES.map((stepDef, idx) => {
          const Icon = stepDef.icon;
          const stepData = steps.find(
            (s) => s.name.toUpperCase().includes(stepDef.name.toUpperCase()) || stepDef.name.toUpperCase().includes(s.name.toUpperCase())
          );

          let status = 'pending';
          if (stepData) {
            status = stepData.status || 'completed';
          } else if (isProcessing) {
            if (activeStepIndex !== undefined) {
              if (idx < activeStepIndex) status = 'completed';
              else if (idx === activeStepIndex) status = 'in_progress';
              else status = 'pending';
            }
          }

          const isCompleted = status === 'completed';
          const isInProgress = status === 'in_progress';
          const isWarning = status === 'warning';

          return (
            <div
              key={stepDef.name}
              className={`p-3 rounded-xl border flex flex-col items-center text-center transition-all duration-200 relative group ${
                isInProgress
                  ? 'bg-blue-50/80 border-blue-500 shadow-md shadow-blue-500/10 ring-2 ring-blue-500/20'
                  : isCompleted
                  ? 'bg-slate-50 border-slate-200 hover:border-slate-300'
                  : isWarning
                  ? 'bg-amber-50 border-amber-300'
                  : 'bg-white border-dashed border-slate-200 opacity-60'
              }`}
            >
              {/* Status indicator icon */}
              <div
                className={`w-9 h-9 rounded-xl flex items-center justify-center mb-2 shadow-xs transition-colors ${
                  isInProgress
                    ? 'bg-blue-600 text-white animate-pulse'
                    : isCompleted
                    ? 'bg-emerald-600 text-white'
                    : isWarning
                    ? 'bg-amber-500 text-white'
                    : 'bg-slate-100 text-slate-400'
                }`}
              >
                <Icon className="w-4 h-4" />
              </div>

              <span className="text-[11px] font-bold text-slate-800 leading-tight">
                {stepDef.label}
              </span>

              {/* Timing or Status */}
              <div className="mt-1.5 flex items-center gap-1 text-[10px] text-slate-500 font-medium">
                {isInProgress && (
                  <span className="text-blue-600 font-semibold flex items-center gap-1">
                    <Clock className="w-3 h-3 animate-spin" />
                    Running
                  </span>
                )}
                {isCompleted && (
                  <span className="text-emerald-700 font-medium flex items-center gap-0.5">
                    <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                    {stepData?.duration_ms ? `${stepData.duration_ms}ms` : 'Done'}
                  </span>
                )}
                {isWarning && (
                  <span className="text-amber-700 font-medium flex items-center gap-0.5">
                    <AlertTriangle className="w-3 h-3 text-amber-600" />
                    Warning
                  </span>
                )}
                {status === 'pending' && <span className="text-slate-400">Waiting</span>}
              </div>

              {/* Tooltip on hover if details present */}
              {stepData?.details && (
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 p-2 bg-slate-900 text-white text-[10px] rounded-lg opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-20 shadow-xl">
                  {stepData.details}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
