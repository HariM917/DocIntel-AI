import React, { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Download,
  Bot,
  CheckCircle2,
  AlertCircle,
  FileSpreadsheet,
  Cpu,
  ShieldCheck,
  Eye,
  Copy,
  Calendar,
  Layers,
  FileText,
} from 'lucide-react';
import { documentApi } from '../services/api';
import { DocumentItem } from '../types';
import { PipelineVisualizer } from '../components/PipelineVisualizer';
import { useToast } from '../components/Toast';

export const DocumentDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [doc, setDoc] = useState<DocumentItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'structured' | 'entities' | 'pii' | 'comparison' | 'pipeline'>('structured');
  const [copiedRaw, setCopiedRaw] = useState(false);
  const [copiedRedacted, setCopiedRedacted] = useState(false);

  const { showToast } = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    const fetchDoc = async () => {
      if (!id) return;
      try {
        const data = await documentApi.get(id);
        setDoc(data);
      } catch (err) {
        console.error('Error fetching document:', err);
        showToast(`Document ${id} not found`, 'error');
        navigate('/archive');
      } finally {
        setLoading(false);
      }
    };
    fetchDoc();
  }, [id]);

  const copyToClipboard = (text: string, isRedacted: boolean) => {
    navigator.clipboard.writeText(text);
    if (isRedacted) {
      setCopiedRedacted(true);
      setTimeout(() => setCopiedRedacted(false), 2000);
    } else {
      setCopiedRaw(true);
      setTimeout(() => setCopiedRaw(false), 2000);
    }
    showToast('Copied to clipboard', 'info');
  };

  if (loading) {
    return (
      <div className="py-24 text-center">
        <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="mt-4 text-xs font-semibold text-slate-500">Loading document record...</p>
      </div>
    );
  }

  if (!doc) {
    return (
      <div className="py-16 text-center">
        <h2 className="text-base font-bold text-slate-800">Document Not Found</h2>
        <Link to="/archive" className="mt-4 inline-block text-xs font-semibold text-blue-600 hover:underline">
          Return to Archive
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Breadcrumb & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            to="/archive"
            className="p-2 rounded-xl bg-white border border-slate-200 text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-mono font-black text-slate-900">{doc.document_id}</h1>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 font-semibold border border-slate-200">
                {doc.document_type}
              </span>
              <span
                className={`text-xs px-2.5 py-0.5 rounded-full font-semibold flex items-center gap-1 ${
                  doc.status === 'Verified'
                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : 'bg-amber-50 text-amber-700 border border-amber-200'
                }`}
              >
                {doc.status === 'Verified' ? (
                  <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                ) : (
                  <AlertCircle className="w-3 h-3 text-amber-600" />
                )}
                {doc.status}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Filename: {doc.filename} • Ingested: {new Date(doc.created_at).toLocaleString()}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <Link
            to="/assistant"
            state={{ initialDocId: doc.document_id }}
            className="px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-blue-600/20 transition-all"
          >
            <Bot className="w-3.5 h-3.5" />
            <span>Chat With Document</span>
          </Link>
          <a
            href={documentApi.getDownloadUrl(doc.document_id)}
            target="_blank"
            rel="noreferrer"
            className="px-3.5 py-2 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 shadow-2xs transition-all"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download Original</span>
          </a>
        </div>
      </div>

      {/* Main Details Card */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
        {/* Navigation Tabs */}
        <div className="flex border-b border-slate-200 px-6 bg-slate-50/70 overflow-x-auto">
          {[
            { id: 'structured', label: 'Structured Fields', icon: FileSpreadsheet },
            { id: 'entities', label: `Entities (${doc.entities?.length || 0})`, icon: Cpu },
            { id: 'pii', label: `Masked PII (${doc.pii_entities?.length || 0})`, icon: ShieldCheck },
            { id: 'comparison', label: 'OCR & Redacted Text', icon: Eye },
            { id: 'pipeline', label: 'Pipeline Steps', icon: Layers },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`py-3.5 px-4 text-xs font-bold border-b-2 flex items-center gap-2 whitespace-nowrap transition-all ${
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

        {/* Tab Content Panels */}
        <div className="p-6">
          {/* 1. Structured Tab */}
          {activeTab === 'structured' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                  Extracted {doc.document_type} Schema Attributes
                </h3>
                <span className="text-xs text-slate-400">Validated against JSON schema</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {Object.entries(doc.structured_data || {}).map(([key, val]) => (
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
            <div className="space-y-4">
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                Named Entities Recognized (RoBERTa + Rule Engine)
              </h3>
              {(!doc.entities || doc.entities.length === 0) ? (
                <p className="text-xs text-slate-400 italic">No named entities detected.</p>
              ) : (
                <div className="flex flex-wrap gap-2.5">
                  {doc.entities.map((ent, idx) => (
                    <div
                      key={idx}
                      className="px-3.5 py-2 rounded-xl border border-slate-200 bg-white shadow-2xs flex items-center gap-2.5"
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

          {/* 3. PII Tab */}
          {activeTab === 'pii' && (
            <div className="space-y-4">
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                Sensitive Identifiers & Applied Masking
              </h3>
              <div className="overflow-x-auto border border-slate-200 rounded-xl">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 font-semibold uppercase tracking-wider border-b border-slate-200">
                    <tr>
                      <th className="py-3 px-4">Identifier Type</th>
                      <th className="py-3 px-4">Masked Value</th>
                      <th className="py-3 px-4">Confidence</th>
                      <th className="py-3 px-4">Source</th>
                      <th className="py-3 px-4">Validation Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-medium">
                    {doc.pii_entities.map((pii, idx) => (
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
                            <span>Verified</span>
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* 4. Comparison Tab */}
          {activeTab === 'comparison' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <div className="border border-slate-200 rounded-xl overflow-hidden">
                <div className="px-4 py-3 bg-slate-100 border-b border-slate-200 flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-700 uppercase">
                    Raw Tesseract OCR Text
                  </span>
                  <button
                    onClick={() => copyToClipboard(doc.raw_text, false)}
                    className="p-1 rounded text-slate-500 hover:text-slate-800"
                    title="Copy Raw Text"
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                </div>
                <pre className="p-4 text-xs font-mono text-slate-800 whitespace-pre-wrap max-h-[500px] overflow-y-auto bg-slate-50/50">
                  {doc.raw_text || 'No text available.'}
                </pre>
              </div>

              <div className="border border-blue-200 rounded-xl overflow-hidden bg-blue-50/20">
                <div className="px-4 py-3 bg-blue-50 border-b border-blue-200 flex items-center justify-between">
                  <span className="text-xs font-bold text-blue-900 uppercase flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-blue-600" />
                    Secure Redacted Text (PII Masked)
                  </span>
                  <button
                    onClick={() => copyToClipboard(doc.redacted_text, true)}
                    className="p-1 rounded text-blue-600 hover:text-blue-800"
                    title="Copy Redacted Text"
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                </div>
                <pre className="p-4 text-xs font-mono text-slate-900 whitespace-pre-wrap max-h-[500px] overflow-y-auto bg-white">
                  {doc.redacted_text || 'No text available.'}
                </pre>
              </div>
            </div>
          )}

          {/* 5. Pipeline Steps Tab */}
          {activeTab === 'pipeline' && (
            <div className="space-y-4">
              <PipelineVisualizer steps={doc.pipeline_steps} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
