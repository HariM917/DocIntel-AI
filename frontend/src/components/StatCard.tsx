import React from 'react';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  color?: 'blue' | 'emerald' | 'amber' | 'indigo' | 'purple';
  trend?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtitle,
  icon: Icon,
  color = 'blue',
  trend,
}) => {
  const colorStyles = {
    blue: {
      bg: 'bg-blue-50/80',
      border: 'border-blue-100',
      iconBg: 'bg-blue-600',
      iconText: 'text-white',
      accent: 'text-blue-600',
    },
    emerald: {
      bg: 'bg-emerald-50/80',
      border: 'border-emerald-100',
      iconBg: 'bg-emerald-600',
      iconText: 'text-white',
      accent: 'text-emerald-600',
    },
    amber: {
      bg: 'bg-amber-50/80',
      border: 'border-amber-100',
      iconBg: 'bg-amber-600',
      iconText: 'text-white',
      accent: 'text-amber-600',
    },
    indigo: {
      bg: 'bg-indigo-50/80',
      border: 'border-indigo-100',
      iconBg: 'bg-indigo-600',
      iconText: 'text-white',
      accent: 'text-indigo-600',
    },
    purple: {
      bg: 'bg-purple-50/80',
      border: 'border-purple-100',
      iconBg: 'bg-purple-600',
      iconText: 'text-white',
      accent: 'text-purple-600',
    },
  };

  const style = colorStyles[color];

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs hover:shadow-md transition-all duration-200">
      <div className="flex items-start justify-between">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">{title}</span>
          <div className="mt-2 text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">{value}</div>
        </div>
        <div className={`w-12 h-12 rounded-xl ${style.iconBg} ${style.iconText} flex items-center justify-center shadow-md`}>
          <Icon className="w-6 h-6" />
        </div>
      </div>

      {(subtitle || trend) && (
        <div className="mt-3 flex items-center gap-2 pt-3 border-t border-slate-100 text-xs">
          {trend && (
            <span className="font-semibold text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded-md border border-emerald-200/60">
              {trend}
            </span>
          )}
          {subtitle && <span className="text-slate-500 font-medium">{subtitle}</span>}
        </div>
      )}
    </div>
  );
};
