import React, { useState } from 'react';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Info,
  Search,
} from 'lucide-react';
import { NetworkEvent } from '../../api/types';

interface EventTimelineProps {
  events: NetworkEvent[];
  maxHeight?: string;
  onSeverityChange?: (severity: string | undefined) => void;
  selectedSeverity?: string;
}

export const EventTimeline: React.FC<EventTimelineProps> = ({
  events,
  maxHeight = 'max-h-[500px]',
  onSeverityChange,
  selectedSeverity,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);

  const filteredEvents = events.filter((e) => {
    if (selectedSeverity && e.severity !== selectedSeverity) return false;
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      e.message.toLowerCase().includes(term) ||
      e.event_type.toLowerCase().includes(term) ||
      e.id.toLowerCase().includes(term) ||
      (e.entity_id && e.entity_id.toLowerCase().includes(term))
    );
  });

  const getSeverityIcon = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical':
      case 'error':
        return <AlertCircle className="w-3.5 h-3.5 text-rose-400" />;
      case 'warning':
        return <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />;
      default:
        return <Info className="w-3.5 h-3.5 text-cyan-400" />;
    }
  };

  const formatTimestamp = (ts: string) => {
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString();
    } catch {
      return ts;
    }
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-[#0D1322] p-5 shadow-xl flex flex-col">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-semibold text-white font-mono uppercase tracking-wide">
            Telemetry &amp; Security Event Stream
          </h3>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
            {filteredEvents.length} events
          </span>
        </div>

        {/* Filter controls */}
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search events..."
              className="pl-8 pr-3 py-1 text-xs rounded-md bg-slate-900 border border-slate-700 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 font-mono w-40"
            />
          </div>

          <select
            value={selectedSeverity || ''}
            onChange={(e) =>
              onSeverityChange && onSeverityChange(e.target.value ? e.target.value : undefined)
            }
            className="px-2.5 py-1 text-xs rounded-md bg-slate-900 border border-slate-700 text-slate-300 focus:outline-none focus:border-cyan-500 font-mono"
          >
            <option value="">All Severities</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="error">Error</option>
            <option value="critical">Critical</option>
          </select>
        </div>
      </div>

      {/* Events List */}
      <div className={`mt-3 space-y-2 overflow-y-auto ${maxHeight} pr-1`}>
        {filteredEvents.map((evt) => {
          const isExpanded = expandedEventId === evt.id;
          return (
            <div
              key={evt.id}
              className="p-3 rounded-lg bg-slate-900/60 border border-slate-800/80 hover:border-slate-700 transition-all font-mono text-xs"
            >
              <div
                className="flex items-start justify-between gap-3 cursor-pointer select-none"
                onClick={() => setExpandedEventId(isExpanded ? null : evt.id)}
              >
                <div className="flex items-start gap-2.5 min-w-0">
                  <div className="mt-0.5">{getSeverityIcon(evt.severity)}</div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-slate-200">{evt.event_type}</span>
                      <span className="text-[10px] text-slate-500 px-1.5 py-0.2 rounded bg-slate-800 border border-slate-700">
                        {evt.source}
                      </span>
                      {evt.entity_id && (
                        <span className="text-[10px] text-cyan-400 font-medium">
                          target:{evt.entity_id}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-slate-300 break-words leading-relaxed">
                      {evt.message}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0 text-slate-500 text-[11px]">
                  <span>{formatTimestamp(evt.timestamp)}</span>
                  {isExpanded ? (
                    <ChevronDown className="w-3.5 h-3.5" />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5" />
                  )}
                </div>
              </div>

              {/* Expanded details */}
              {isExpanded && (
                <div className="mt-3 pt-3 border-t border-slate-800 space-y-2">
                  <div className="text-[10px] text-slate-500">Event ID: {evt.id}</div>
                  <div className="text-[10px] text-slate-500">Timestamp: {evt.timestamp}</div>
                  {evt.details && Object.keys(evt.details).length > 0 && (
                    <pre className="p-2.5 rounded bg-black/40 border border-slate-800 text-[10px] text-slate-300 overflow-x-auto leading-relaxed">
                      {JSON.stringify(evt.details, null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {filteredEvents.length === 0 && (
          <div className="p-8 text-center text-xs text-slate-500 font-mono italic">
            No events match the current filter criteria.
          </div>
        )}
      </div>
    </div>
  );
};
