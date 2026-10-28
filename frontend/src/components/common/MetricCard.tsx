import React from 'react';
import { LucideIcon } from 'lucide-react';

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: LucideIcon;
  variant?: 'cyan' | 'violet' | 'amber' | 'emerald' | 'rose' | 'default';
  badge?: string;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subtitle,
  icon: Icon,
  variant = 'default',
  badge,
}) => {
  const getBorderAndBg = () => {
    switch (variant) {
      case 'cyan':
        return 'border-cyan-500/20 bg-[#111827] hover:border-cyan-500/40';
      case 'violet':
        return 'border-violet-500/20 bg-[#111827] hover:border-violet-500/40';
      case 'amber':
        return 'border-amber-500/20 bg-[#111827] hover:border-amber-500/40';
      case 'emerald':
        return 'border-emerald-500/20 bg-[#111827] hover:border-emerald-500/40';
      case 'rose':
        return 'border-rose-500/20 bg-[#111827] hover:border-rose-500/40';
      default:
        return 'border-slate-800 bg-[#111827] hover:border-slate-700';
    }
  };

  const getIconColor = () => {
    switch (variant) {
      case 'cyan':
        return 'text-cyan-400 bg-cyan-950/40 border border-cyan-500/20';
      case 'violet':
        return 'text-violet-400 bg-violet-950/40 border border-violet-500/20';
      case 'amber':
        return 'text-amber-400 bg-amber-950/40 border border-amber-500/20';
      case 'emerald':
        return 'text-emerald-400 bg-emerald-950/40 border border-emerald-500/20';
      case 'rose':
        return 'text-rose-400 bg-rose-950/40 border border-rose-500/20';
      default:
        return 'text-slate-400 bg-slate-800 border border-slate-700';
    }
  };

  return (
    <div
      className={`rounded-lg p-5 border transition-all duration-200 shadow-sm ${getBorderAndBg()}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
          {title}
        </span>
        {Icon && (
          <div className={`p-2 rounded-md ${getIconColor()}`}>
            <Icon className="w-4 h-4" />
          </div>
        )}
      </div>
      <div className="mt-3 flex items-baseline justify-between">
        <div className="text-2xl font-bold font-mono tracking-tight text-white">
          {value}
        </div>
        {badge && (
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
            {badge}
          </span>
        )}
      </div>
      {subtitle && (
        <div className="mt-1 text-xs text-slate-400 font-normal">
          {subtitle}
        </div>
      )}
    </div>
  );
};

