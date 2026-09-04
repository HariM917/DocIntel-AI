import React, { useState, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  UploadCloud,
  FileText,
  CheckCircle2,
  AlertCircle,
  ShieldCheck,
  Cpu,
  Eye,
  FileSpreadsheet,
  Copy,
  ExternalLink,
  Bot,
  RefreshCw,
  X,
  File,
  Sparkles,
} from 'lucide-react';
import { documentApi } from '../services/api';
import { DocumentItem } from '../types';
import { PipelineVisualizer } from '../components/PipelineVisualizer';
import { useToast } from '../components/Toast';

export const ProcessDocument: React.FC = () => {
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [processedResult, setProcessedResult] = useState<DocumentItem | null>(null);
  const [activeTab, setActiveTab] = useState<'structured' | 'entities' | 'pii' | 'comparison'>('structured');
  const [copiedRaw, setCopiedRaw] = useState(false);
  const [copiedRedacted, setCopiedRedacted] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const { showToast } = useToast();
  const navigate = useNavigate();

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const validateAndSetFile = (file: File) => {
    const validExtensions = ['.pdf', '.jpg', '.jpeg', '.png'];
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!validExtensions.includes(ext)) {
      showToast(`Invalid file type (${ext}). Please upload a PDF, JPG, or PNG document.`, 'error');
      return;
    }

    if (file.size > 15 * 1024 * 1024) {
      showToast('File exceeds maximum size limit of 15MB.', 'error');
      return;
    }

    setSelectedFile(file);
    setProcessedResult(null);
  };

  const handleProcess = async () => {
    if (!selectedFile) return;

    setIsProcessing(true);
    setCurrentStepIndex(0);
    setUploadProgress(10);

    // Simulated progress timer for pipeline visualization
    const interval = setInterval(() => {
      setCurrentStepIndex((prev) => (prev < 6 ? prev + 1 : prev));
    }, 700);

    try {
      const result = await documentApi.process(selectedFile, (progressEvent) => {
        if (progressEvent.total) {
          const pct = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setUploadProgress(pct);
        }
      });

      clearInterval(interval);
      setCurrentStepIndex(7);
      setProcessedResult(result);
      showToast(`Document ${result.document_id} processed successfully!`, 'success');
    } catch (err: any) {
      clearInterval(interval);
      const msg = err.response?.data?.detail || 'Document processing failed. Please check server logs.';
      showToast(msg, 'error');
    } finally {
      setIsProcessing(false);
    }
  };

  const copyToClipboard = (text: string, isRedacted: boolean) => {
    navigator.clipboard.writeText(text);
    if (isRedacted) {
      setCopiedRedacted(true);
      setTimeout(() => setCopiedRedacted(false), 2000);
    } else {
      setCopiedRaw(true);
      setTimeout(() => setCopiedRaw(false), 2000);
    }
    showToast('Copied text to clipboard', 'info');
  };

  return (
    <div className="space-y-6">
      {/* Title */}
      <div>
        <h1 className="text-2xl font-black text-slate-900 tracking-tight">Process Document</h1>
        <p className="text-xs text-slate-500 mt-1">
          Upload any enterprise Invoice, Contract, Identity Card, or Application to extract text and mask sensitive PII.
        </p>
      </div>

      {/* Upload Box */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleFileDrop}
          onClick={() => !isProcessing && fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-2xl p-8 sm:p-12 text-center cursor-pointer transition-all duration-200 ${
            dragOver
              ? 'border-blue-500 bg-blue-50/50'
              : selectedFile
              ? 'border-emerald-300 bg-emerald-50/20'
              : 'border-slate-300 hover:border-slate-400 bg-slate-50/50'
          }`}
        >
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileSelect}
            accept=".pdf,.jpg,.jpeg,.png"
            className="hidden"
            disabled={isProcessing}
          />

          <div className="w-14 h-14 rounded-2xl bg-white shadow-md border border-slate-200/60 mx-auto flex items-center justify-center mb-3">
            {selectedFile ? (
              <FileText className="w-7 h-7 text-emerald-600" />
            ) : (
              <UploadCloud className="w-7 h-7 text-blue-600" />
            )}
          </div>

          {selectedFile ? (
            <div>
              <div className="text-sm font-bold text-slate-900 flex items-center justify-center gap-2">
                <span>{selectedFile.name}</span>
                <span className="text-xs text-slate-500 font-normal">
                  ({(selectedFile.size / 1024).toFixed(1)} KB)
                </span>
              </div>
              <p className="text-xs text-emerald-600 font-medium mt-1">
                File ready for enterprise intelligence extraction. Click below to process.
              </p>
            </div>
          ) : (
            <div>
              <div className="text-sm font-bold text-slate-800">
                Drag and drop your document here, or <span className="text-blue-600">Browse Files</span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Supports PDF, JPG, JPEG, PNG formats (Max size: 15MB)
              </p>
            </div>
          )}
        </div>

        {/* Action Controls */}
        {selectedFile && (
          <div className="mt-4 flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 border-t border-slate-100">
            <button
              type="button"
              onClick={() => {
                setSelectedFile(null);
                setProcessedResult(null);
              }}
              disabled={isProcessing}
              className="text-xs text-slate-500 hover:text-rose-600 font-semibold flex items-center gap-1"
            >
              <X className="w-4 h-4" />
              <span>Clear selection</span>
            </button>

            <button
              type="button"
              onClick={handleProcess}
              disabled={isProcessing}
              className="w-full sm:w-auto px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-sm shadow-md shadow-blue-600/25 flex items-center justify-center gap-2 transition-all disabled:opacity-50"
            >
              {isProcessing ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Executing Pipeline...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Start Extraction & Redaction</span>
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Live Pipeline Visualizer */}
      <PipelineVisualizer
        steps={processedResult?.pipeline_steps}
        activeStepIndex={currentStepIndex}
        isProcessing={isProcessing}
      />

      {/* Processing Results Display */}
      {processedResult && (
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden space-y-0">
          {/* Header Summary Bar */}
          <div className="p-6 bg-slate-900 text-white flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-blue-600/30 border border-blue-500/40 flex items-center justify-center text-blue-400">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-base font-black text-blue-400">
                    {processedResult.document_id}
                  </span>
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300 font-semibold">
                    {processedResult.document_type}
                  </span>
                  <span
                    className={`text-xs px-2.5 py-0.5 rounded-full font-semibold ${
                      processedResult.status === 'Verified'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                    }`}
                  >
                    {processedResult.status}
                  </span>
                </div>
                <div className="text-xs text-slate-400 mt-1">
                  Filename: {processedResult.filename} • Confidence: {(processedResult.confidence * 100).toFixed(1)}%
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Link
                to={`/assistant`}
                state={{ initialDocId: processedResult.document_id }}
                className="px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors"
              >
                <Bot className="w-4 h-4" />
                <span>Ask AI About This</span>
              </Link>
              <Link
                to={`/documents/${processedResult.document_id}`}
                className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold flex items-center gap-1.5 border border-slate-700 transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>View Full Record</span>
              </Link>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex border-b border-slate-200 px-6 bg-slate-50/70">
            {[
              { id: 'structured', label: 'Structured Schema', icon: FileSpreadsheet },
              { id: 'entities', label: `Entities (${processedResult.entities.length})`, icon: Cpu },
              { id: 'pii', label: `Detected PII (${processedResult.pii_entities.length})`, icon: ShieldCheck },
              { id: 'comparison', label: 'Raw vs. Redacted OCR', icon: Eye },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`py-3 px-4 text-xs font-bold border-b-2 flex items-center gap-2 transition-all ${
                  activeTab === tab.id
                    ? 'border-blue-600 text-blue-600 bg-white shadow-2xs'
                    : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
              >
                <tab.icon className="w-3.5 h-3.5" />
                <span>{tab.label}</span>
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="p-6">
            {/* 1. Structured Data Tab */}
            {activeTab === 'structured' && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {Object.entries(processedResult.structured_data || {}).map(([key, val]) => (
                    <div key={key} className="p-4 rounded-xl bg-slate-50 border border-slate-200/70">
                      <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                        {key.replace(/_/g, ' ')}
                      </span>
                      <div className="mt-1 text-sm font-semibold text-slate-800 break-words">
                        {Array.isArray(val) ? val.join(', ') || 'N/A' : String(val ?? 'N/A')}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 2. Entities Tab */}
            {activeTab === 'entities' && (
              <div>
                {processedResult.entities.length === 0 ? (
                  <p className="text-xs text-slate-400 italic">No named entities detected.</p>
                ) : (
                  <div className="flex flex-wrap gap-2.5">
                    {processedResult.entities.map((ent, idx) => (
                      <div
                        key={idx}
                        className="px-3 py-1.5 rounded-xl border border-slate-200 bg-white shadow-2xs flex items-center gap-2"
                      >
                        <span className="text-xs font-semibold text-slate-800">{ent.text}</span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${
                            ent.type === 'PERSON'
                              ? 'bg-blue-100 text-blue-800'
                              : ent.type === 'ORGANIZATION'
                              ? 'bg-purple-100 text-purple-800'
                              : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          {ent.type}
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono">
                          {(ent.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* 3. PII & Masking Tab */}
            {activeTab === 'pii' && (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 font-semibold uppercase tracking-wider border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-4">Entity Type</th>
                      <th className="py-2.5 px-4">Masked / Redacted Value</th>
                      <th className="py-2.5 px-4">Confidence</th>
                      <th className="py-2.5 px-4">Source</th>
                      <th className="py-2.5 px-4">Validation</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-medium">
                    {processedResult.pii_entities.map((pii, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/80">
                        <td className="py-3 px-4 font-bold text-slate-800">
                          <span className="px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200 font-mono">
                            {pii.type}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-mono font-bold text-blue-600">
                          {pii.masked_value}
                        </td>
                        <td className="py-3 px-4 text-slate-600 font-semibold">
                          {(pii.confidence * 100).toFixed(0)}%
                        </td>
                        <td className="py-3 px-4 uppercase text-[10px] font-semibold text-slate-400">
                          {pii.source}
                        </td>
                        <td className="py-3 px-4">
                          <span className="inline-flex items-center gap-1 text-emerald-600 font-semibold">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            <span>Passed</span>
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* 4. Text Comparison Tab */}
            {activeTab === 'comparison' && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Raw OCR Text */}
                <div className="border border-slate-200 rounded-xl overflow-hidden">
                  <div className="px-4 py-2.5 bg-slate-100 border-b border-slate-200 flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-700 uppercase">
                      Raw Tesseract OCR Text
                    </span>
                    <button
                      onClick={() => copyToClipboard(processedResult.raw_text, false)}
                      className="p-1 rounded text-slate-500 hover:text-slate-800"
                      title="Copy Raw Text"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <pre className="p-4 text-xs font-mono text-slate-800 whitespace-pre-wrap max-h-96 overflow-y-auto bg-slate-50/50">
                    {processedResult.raw_text || 'No text extracted.'}
                  </pre>
                </div>

                {/* Redacted Text */}
                <div className="border border-blue-200 rounded-xl overflow-hidden bg-blue-50/20">
                  <div className="px-4 py-2.5 bg-blue-50 border-b border-blue-200 flex items-center justify-between">
                    <span className="text-xs font-bold text-blue-900 uppercase flex items-center gap-1.5">
                      <ShieldCheck className="w-4 h-4 text-blue-600" />
                      Secure Redacted Text (PII Masked)
                    </span>
                    <button
                      onClick={() => copyToClipboard(processedResult.redacted_text, true)}
                      className="p-1 rounded text-blue-600 hover:text-blue-800"
                      title="Copy Redacted Text"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <pre className="p-4 text-xs font-mono text-slate-900 whitespace-pre-wrap max-h-96 overflow-y-auto bg-white">
                    {processedResult.redacted_text || 'No text available.'}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
