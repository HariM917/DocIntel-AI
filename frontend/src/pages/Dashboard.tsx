import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  FileText,
  Target,
  ShieldAlert,
  Clock,
  ArrowUpRight,
  Eye,
  Download,
  FileUp,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  FolderOpen,
} from 'lucide-react';
import { StatCard } from '../components/StatCard';
import { dashboardApi, documentApi } from '../services/api';
import { DashboardStats, RecentDocumentItem } from '../types';
import { useToast } from '../components/Toast';

export const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const { showToast } = useToast();

  const fetchStats = async () => {
    try {
      const data = await dashboardApi.getStats();
      setStats(data);
    } catch (err) {
      console.error('Failed to load dashboard stats:', err);
      showToast('Could not load live analytics from backend.', 'error');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchStats();
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
        <p className="mt-4 text-sm font-semibold text-slate-500">Loading intelligence dashboard metrics...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">Intelligence Dashboard</h1>
          <p className="text-xs text-slate-500 mt-1">
            Real-time telemetry and extraction analytics from processed enterprise documents.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="px-3.5 py-2 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 shadow-2xs transition-all disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            <span>Sync</span>
          </button>
          <Link
            to="/process"
            className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-blue-600/20 transition-all"
          >
            <FileUp className="w-3.5 h-3.5" />
            <span>Process New Document</span>
          </Link>
        </div>
      </div>

      {/* 4 Core Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Processed"
          value={stats?.total_processed || 0}
          subtitle="All ingested documents"
          icon={FileText}
          color="blue"
          trend="+100% automated"
        />
        <StatCard
          title="Extraction Accuracy"
          value={`${stats?.extraction_accuracy || 0}%`}
          subtitle="RoBERTa & rule model score"
          icon={Target}
          color="emerald"
          trend="Enterprise Grade"
        />
        <StatCard
          title="Protected Entities"
          value={stats?.protected_entities || 0}
          subtitle="Aadhaar, PAN, Emails, Cards"
          icon={ShieldAlert}
          color="amber"
          trend="Masked & Encrypted"
        />
        <StatCard
          title="Time Saved"
          value={stats?.time_saved || '0 hrs'}
          subtitle="Vs. manual document review"
          icon={Clock}
          color="indigo"
          trend="~6 min/doc"
        />
      </div>

      {/* Distribution by Document Type */}
      <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold text-slate-900">Document Type Distribution</h2>
          <span className="text-xs text-slate-400 font-medium">Automatic multi-class classification</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {['Invoice', 'Contract', 'Identity', 'Application', 'Form', 'Other'].map((type) => {
            const count = stats?.type_distribution?.[type] || 0;
            return (
              <div
                key={type}
                className="p-3 rounded-xl bg-slate-50 border border-slate-100 flex flex-col items-center text-center"
              >
                <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">{type}</span>
                <span className="text-xl font-bold text-slate-800 mt-1">{count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Recent Documents Table */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-slate-900">Recent Ingested Documents</h2>
            <p className="text-xs text-slate-500 mt-0.5">Latest documents parsed through OCR and neural NER</p>
          </div>
          <Link
            to="/archive"
            className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1 transition-colors"
          >
            <span>View Full Archive</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {(!stats?.recent_documents || stats.recent_documents.length === 0) ? (
          <div className="py-16 px-4 text-center">
            <FolderOpen className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <h3 className="text-sm font-bold text-slate-700">No Documents Found</h3>
            <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
              You have not processed any documents yet. Upload your first invoice, contract or identity document to begin.
            </p>
            <Link
              to="/process"
              className="inline-flex items-center gap-2 mt-4 px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-semibold shadow-md shadow-blue-600/20"
            >
              <FileUp className="w-3.5 h-3.5" />
              <span>Process Document</span>
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/80 border-b border-slate-100 text-slate-500 font-semibold uppercase tracking-wider">
                <tr>
                  <th className="py-3 px-5">Document ID</th>
                  <th className="py-3 px-5">File & Type</th>
                  <th className="py-3 px-5">Extracted Vendor / Name</th>
                  <th className="py-3 px-5">Date Processed</th>
                  <th className="py-3 px-5">Confidence</th>
                  <th className="py-3 px-5">Status</th>
                  <th className="py-3 px-5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {stats.recent_documents.map((doc) => (
                  <tr key={doc.document_id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-3.5 px-5 font-mono text-blue-600 font-bold">
                      <Link to={`/documents/${doc.document_id}`} className="hover:underline">
                        {doc.document_id}
                      </Link>
                    </td>
                    <td className="py-3.5 px-5">
                      <div className="font-semibold text-slate-800 truncate max-w-xs">{doc.filename}</div>
                      <span className="inline-block mt-0.5 text-[10px] px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 font-medium">
                        {doc.document_type}
                      </span>
                    </td>
                    <td className="py-3.5 px-5 text-slate-700 font-semibold">
                      {doc.extracted_vendor_or_name}
                    </td>
                    <td className="py-3.5 px-5 text-slate-500">
                      {doc.created_at ? new Date(doc.created_at).toLocaleString() : 'N/A'}
                    </td>
                    <td className="py-3.5 px-5 font-semibold text-slate-800">
                      {doc.confidence}%
                    </td>
                    <td className="py-3.5 px-5">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold ${
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
                    </td>
                    <td className="py-3.5 px-5 text-right">
                      <div className="inline-flex items-center gap-1.5">
                        <Link
                          to={`/documents/${doc.document_id}`}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                          title="View Details"
                        >
                          <Eye className="w-4 h-4" />
                        </Link>
                        <a
                          href={documentApi.getDownloadUrl(doc.document_id)}
                          target="_blank"
                          rel="noreferrer"
                          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                          title="Download Original"
                        >
                          <Download className="w-4 h-4" />
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
