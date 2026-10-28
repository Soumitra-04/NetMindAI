import React from 'react';

interface StatusBadgeProps {
  status: string;
  variant?: 'status' | 'stage' | 'severity' | 'health';
  size?: 'sm' | 'md';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  size = 'md',
}) => {
  const norm = (status || '').toLowerCase().replace(/[\s-]/g, '_');

  let colorClasses = 'bg-slate-800 text-slate-300 border-slate-700';
  let dotColor = 'bg-slate-400';

  // Green / Success states
  if (
    norm === 'healthy' ||
    norm === 'completed' ||
    norm === 'completed_healthy' ||
    norm === 'approved' ||
    norm === 'verified_success' ||
    norm === 'success' ||
    norm === 'active' ||
    norm === 'true'
  ) {
    colorClasses = 'bg-emerald-950/60 text-emerald-300 border-emerald-500/30';
    dotColor = 'bg-emerald-400';
  }
  // Amber / Warning / Pending states
  else if (
    norm === 'pending' ||
    norm === 'pending_approval' ||
    norm === 'request_human_approval' ||
    norm === 'warning' ||
    norm === 'investigation_required' ||
    norm === 'partial_success' ||
    norm === 'partial_recovery' ||
    norm === 'running' ||
    norm === 'executing'
  ) {
    colorClasses = 'bg-amber-950/60 text-amber-300 border-amber-500/30';
    dotColor = norm === 'running' ? 'bg-cyan-400 animate-pulse' : 'bg-amber-400';
  }
  // Red / Critical / Error states
  else if (
    norm === 'failed' ||
    norm === 'critical' ||
    norm === 'error' ||
    norm === 'verification_failed' ||
    norm === 'rejected' ||
    norm === 'anomaly_detected' ||
    norm === 'inactive' ||
    norm === 'false'
  ) {
    colorClasses = 'bg-rose-950/60 text-rose-300 border-rose-500/30';
    dotColor = 'bg-rose-500';
  }
  // Cyan / Info states
  else if (
    norm === 'info' ||
    norm === 'initialized' ||
    norm === 'plan_disruption' ||
    norm === 'execute_disruption' ||
    norm === 'detect_anomaly' ||
    norm === 'evaluate_detection' ||
    norm === 'recommend_recovery' ||
    norm === 'validate_recommendation' ||
    norm === 'execute_recovery' ||
    norm === 'verify_recovery' ||
    norm === 'finalize_run'
  ) {
    colorClasses = 'bg-cyan-950/60 text-cyan-300 border-cyan-500/30';
    dotColor = 'bg-cyan-400';
  }

  const formatText = (text: string) => {
    return text.replace(/_/g, ' ');
  };

  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs';

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono uppercase tracking-wider font-semibold rounded border ${sizeClasses} ${colorClasses}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
      {formatText(status)}
    </span>
  );
};
