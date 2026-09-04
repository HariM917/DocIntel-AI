import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  Lock,
  RefreshCw,
  Info,
  CheckCircle2,
  AlertTriangle,
  Sliders,
} from 'lucide-react';
import { securityApi } from '../services/api';
import { SecurityRule } from '../types';
import { useToast } from '../components/Toast';

export const SecurityRules: React.FC = () => {
  const [rules, setRules] = useState<SecurityRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const { showToast } = useToast();

  const loadRules = async () => {
    setLoading(true);
    try {
      const data = await securityApi.getRules();
      setRules(data);
    } catch (err) {
      console.error('Failed to load security rules:', err);
      showToast('Could not load security rules.', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRules();
  }, []);

  const handleToggle = async (rule: SecurityRule) => {
    setUpdatingId(rule.rule_id);
    const newStatus = !rule.enabled;
    try {
      const updated = await securityApi.updateRule(rule.rule_id, { enabled: newStatus });
      setRules((prev) =>
        prev.map((r) => (r.rule_id === rule.rule_id ? { ...r, enabled: updated.enabled } : r))
      );
      showToast(
        `${rule.name} is now ${newStatus ? 'ENABLED' : 'DISABLED'}`,
        newStatus ? 'success' : 'warning'
      );
    } catch (err) {
      showToast('Failed to update security rule status.', 'error');
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">Enterprise Security Rules</h1>
          <p className="text-xs text-slate-500 mt-1">
            Configure automated PII redaction and compliance policies applied during document ingestion.
          </p>
        </div>
        <button
          onClick={loadRules}
          className="self-start sm:self-auto px-3.5 py-2 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 shadow-2xs transition-all"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Reload Rules</span>
        </button>
      </div>

      {/* Info Notice */}
      <div className="p-4 rounded-2xl bg-blue-50/70 border border-blue-200/80 flex items-start gap-3">
        <Info className="w-5 h-5 text-blue-600 shrink-0 mt-0.5" />
        <div className="text-xs text-blue-950 leading-relaxed">
          <span className="font-bold">Automated Redaction Engine:</span> Active security rules are executed during
          step 6 of the document intelligence pipeline. Any entity identified by RoBERTa or deterministic rule matching is
          sanitized before being indexed in the FAISS vector store or returned in unprivileged API responses.
        </div>
      </div>

      {/* Rules Grid */}
      {loading ? (
        <div className="py-20 text-center">
          <div className="w-8 h-8 border-3 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="mt-3 text-xs font-semibold text-slate-500">Loading security policies...</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {rules.map((rule) => {
            const isUpdating = updatingId === rule.rule_id;

            return (
              <div
                key={rule.rule_id}
                className={`p-5 rounded-2xl border transition-all duration-200 bg-white ${
                  rule.enabled
                    ? 'border-slate-200/90 shadow-xs hover:border-slate-300'
                    : 'border-slate-200/60 bg-slate-50/50 opacity-75'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-10 h-10 rounded-xl flex items-center justify-center shadow-xs ${
                        rule.enabled ? 'bg-blue-600 text-white' : 'bg-slate-200 text-slate-500'
                      }`}
                    >
                      <ShieldCheck className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-slate-900">{rule.name}</h3>
                      <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 uppercase">
                        {rule.entity_type}
                      </span>
                    </div>
                  </div>

                  {/* Toggle Switch */}
                  <button
                    type="button"
                    onClick={() => handleToggle(rule)}
                    disabled={isUpdating}
                    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      rule.enabled ? 'bg-blue-600' : 'bg-slate-300'
                    } ${isUpdating ? 'opacity-50' : ''}`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                        rule.enabled ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>

                <p className="text-xs text-slate-600 mt-3 leading-relaxed">
                  {rule.description}
                </p>

                <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-[11px]">
                  <div className="flex items-center gap-1.5 font-mono text-slate-500">
                    <span className="text-slate-400 font-sans">Pattern:</span>
                    <span className="bg-slate-100 px-2 py-0.5 rounded font-semibold text-slate-700">
                      {rule.mask_pattern}
                    </span>
                  </div>
                  <span
                    className={`font-semibold flex items-center gap-1 ${
                      rule.enabled ? 'text-emerald-600' : 'text-slate-400'
                    }`}
                  >
                    {rule.enabled ? (
                      <>
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Active</span>
                      </>
                    ) : (
                      <>
                        <AlertTriangle className="w-3.5 h-3.5" />
                        <span>Disabled</span>
                      </>
                    )}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
