import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Search,
  Filter,
  Eye,
  Download,
  Trash2,
  CheckCircle2,
  AlertCircle,
  FileText,
  RefreshCw,
  FolderOpen,
} from 'lucide-react';
import { documentApi } from '../services/api';
import { DocumentItem } from '../types';
import { useToast } from '../components/Toast';

export const DocumentArchive: React.FC = () => {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState('All');
  const [filterStatus, setFilterStatus] = useState('All');
  const [searchTerm, setSearchTerm] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const { showToast } = useToast();

  const loadDocuments = async () => {
    setLoading(true);
    try {
      const data = await documentApi.list({
        type: filterType === 'All' ? undefined : filterType,
        status: filterStatus === 'All' ? undefined : filterStatus,
        search: searchTerm.trim() || undefined,
        page,
        limit: 15,
      });
      setDocuments(data.documents);
      setTotal(data.total);
    } catch (err) {
      console.error('Failed to load archive:', err);
      showToast('Could not load documents from archive.', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, [filterType, filterStatus, page]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    loadDocuments();
  };

  const handleDelete = async (docId: string) => {
    if (!window.confirm(`Are you sure you want to delete document ${docId}? This action cannot be undone.`)) {
      return;
    }

    setDeletingId(docId);
    try {
      await documentApi.delete(docId);
      showToast(`Document ${docId} deleted successfully.`, 'success');
      setDocuments((prev) => prev.filter((d) => d.document_id !== docId));
      setTotal((prev) => Math.max(0, prev - 1));
    } catch (err) {
      showToast('Failed to delete document.', 'error');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">Document Archive</h1>
          <p className="text-xs text-slate-500 mt-1">
            Browse and query securely extracted documents stored in MongoDB collections.
          </p>
        </div>
        <button
          onClick={loadDocuments}
          className="self-start sm:self-auto px-3.5 py-2 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 shadow-2xs transition-all"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Records</span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        <form onSubmit={handleSearchSubmit} className="relative flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by ID, filename, or text content..."
            className="w-full pl-9 pr-20 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-blue-500 focus:bg-white transition-all"
          />
          <button
            type="submit"
            className="absolute right-1.5 top-1/2 -translate-y-1/2 px-3 py-1 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-xs font-semibold transition-colors"
          >
            Search
          </button>
        </form>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5 text-xs text-slate-500 font-semibold mr-1">
            <Filter className="w-3.5 h-3.5" />
            <span>Filter:</span>
          </div>

          <select
            value={filterType}
            onChange={(e) => {
              setFilterType(e.target.value);
              setPage(1);
            }}
            className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-700 focus:outline-none focus:border-blue-500"
          >
            <option value="All">All Types</option>
            <option value="Invoice">Invoice</option>
            <option value="Contract">Contract</option>
            <option value="Identity">Identity</option>
            <option value="Application">Application</option>
            <option value="Form">Form</option>
            <option value="Other">Other</option>
          </select>

          <select
            value={filterStatus}
            onChange={(e) => {
              setFilterStatus(e.target.value);
              setPage(1);
            }}
            className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-700 focus:outline-none focus:border-blue-500"
          >
            <option value="All">All Statuses</option>
            <option value="Verified">Verified</option>
            <option value="Flagged">Flagged</option>
          </select>
        </div>
      </div>

      {/* Archive Records Table */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
        {loading ? (
          <div className="py-20 text-center">
            <div className="w-8 h-8 border-3 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="mt-3 text-xs font-semibold text-slate-500">Querying database collection...</p>
          </div>
        ) : documents.length === 0 ? (
          <div className="py-16 px-4 text-center">
            <FolderOpen className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <h3 className="text-sm font-bold text-slate-700">No Records Match Filters</h3>
            <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
              Try adjusting your search criteria or document type filter.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/80 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider">
                <tr>
                  <th className="py-3 px-5">Document ID</th>
                  <th className="py-3 px-5">Filename & Type</th>
                  <th className="py-3 px-5">PII Entities</th>
                  <th className="py-3 px-5">Date Processed</th>
                  <th className="py-3 px-5">Accuracy</th>
                  <th className="py-3 px-5">Status</th>
                  <th className="py-3 px-5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {documents.map((doc) => (
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
                    <td className="py-3.5 px-5">
                      <span className="text-slate-600 font-semibold">
                        {doc.pii_entities?.length || 0} sensitive items
                      </span>
                    </td>
                    <td className="py-3.5 px-5 text-slate-500">
                      {doc.created_at ? new Date(doc.created_at).toLocaleString() : 'N/A'}
                    </td>
                    <td className="py-3.5 px-5 font-semibold text-slate-800">
                      {(doc.confidence * 100).toFixed(1)}%
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
                      <div className="inline-flex items-center gap-1">
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
                        <button
                          onClick={() => handleDelete(doc.document_id)}
                          disabled={deletingId === doc.document_id}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                          title="Delete Document"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Bar */}
        {total > 15 && (
          <div className="p-4 border-t border-slate-100 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
            <span>
              Showing {documents.length} of {total} documents
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 bg-white border border-slate-200 rounded-lg disabled:opacity-50 font-semibold"
              >
                Previous
              </button>
              <span className="font-semibold text-slate-700">Page {page}</span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={documents.length < 15}
                className="px-3 py-1 bg-white border border-slate-200 rounded-lg disabled:opacity-50 font-semibold"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
