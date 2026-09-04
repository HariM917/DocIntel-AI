/**
 * Formatting and utility helpers for DocIntel AI Frontend.
 */

export function formatBytes(bytes: number, decimals: number = 1): string {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

export function formatDate(isoString?: string): string {
  if (!isoString) return 'N/A';
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoString;
  }
}

export function getConfidenceColor(confidence: number): {
  badgeBg: string;
  badgeText: string;
  barColor: string;
} {
  const pct = confidence > 1 ? confidence : confidence * 100;
  if (pct >= 90) {
    return {
      badgeBg: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      badgeText: 'text-emerald-700',
      barColor: 'bg-emerald-500',
    };
  } else if (pct >= 75) {
    return {
      badgeBg: 'bg-blue-50 text-blue-700 border-blue-200',
      badgeText: 'text-blue-700',
      barColor: 'bg-blue-500',
    };
  } else {
    return {
      badgeBg: 'bg-amber-50 text-amber-700 border-amber-200',
      badgeText: 'text-amber-700',
      barColor: 'bg-amber-500',
    };
  }
}

export function getEntityTypeColor(type: string): string {
  const t = type.toUpperCase();
  switch (t) {
    case 'PERSON':
      return 'bg-blue-50 text-blue-700 border-blue-200';
    case 'ORGANIZATION':
      return 'bg-purple-50 text-purple-700 border-purple-200';
    case 'LOCATION':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    case 'AADHAAR':
    case 'PAN':
    case 'CREDIT_CARD':
    case 'BANK_ACCOUNT':
      return 'bg-rose-50 text-rose-700 border-rose-200';
    case 'EMAIL':
    case 'PHONE':
      return 'bg-amber-50 text-amber-700 border-amber-200';
    default:
      return 'bg-slate-100 text-slate-700 border-slate-200';
  }
}
