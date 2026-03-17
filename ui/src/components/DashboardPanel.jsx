import React, { useState, useEffect } from 'react';
import SoftButton from './SoftButton';

/**
 * DashboardPanel — System health at a glance.
 * Pulls from /api/skills/status (daemons) and /api/status (system).
 * Warm palette: cream, bark, leaf.
 */

function StatusDot({ alive }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: 7, height: 7,
        borderRadius: '50%',
        background: alive ? 'var(--leaf, #7a9a6d)' : 'var(--pencil-faint)',
        marginRight: 8,
        verticalAlign: 'middle',
      }}
    />
  );
}

export default function DashboardPanel({ onClose }) {
  const [daemons, setDaemons] = useState(null);
  const [system, setSystem] = useState(null);
  const [stats, setStats] = useState(null);

  const [fleet, setFleet] = useState(null);

  useEffect(() => {
    fetch('/api/skills/status').then(r => r.json()).then(setDaemons).catch(() => {});
    fetch('/api/status').then(r => r.json()).then(setSystem).catch(() => {});
    fetch('/api/knowledge/stats').then(r => r.json()).then(setStats).catch(() => {});
    fetch('/api/fleet/providers').then(r => r.json()).then(setFleet).catch(() => {});
  }, []);

  const daemonList = daemons?.daemons ? Object.entries(daemons.daemons) : [];
  const aliveCount = daemonList.filter(([, v]) => v).length;

  return (
    <div className="h-full flex flex-col px-5 py-6 overflow-y-auto" style={{ background: 'var(--page)' }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-ernie text-lg" style={{ color: 'var(--bark, #6b5b4e)' }}>dashboard</h2>
        <SoftButton onClick={onClose}>&times;</SoftButton>
      </div>

      {/* Daemons */}
      <section className="mb-5 pencil-line-faint pb-4">
        <h3 className="font-ernie text-xs mb-2" style={{ color: 'var(--bark, #6b5b4e)', opacity: 0.6 }}>
          daemons ({aliveCount}/{daemonList.length})
        </h3>
        {daemonList.length > 0 ? (
          <div className="space-y-1">
            {daemonList.map(([name, alive]) => (
              <div key={name} className="font-ernie text-xs" style={{ color: 'var(--ink)' }}>
                <StatusDot alive={alive} />
                {name.replace(/^WILLOW-/, '')}
              </div>
            ))}
          </div>
        ) : (
          <span className="font-ernie text-xs" style={{ opacity: 0.4 }}>loading...</span>
        )}
      </section>

      {/* Knowledge */}
      <section className="mb-5 pencil-line-faint pb-4">
        <h3 className="font-ernie text-xs mb-2" style={{ color: 'var(--bark, #6b5b4e)', opacity: 0.6 }}>
          knowledge
        </h3>
        {stats ? (
          <div className="font-ernie text-xs space-y-1" style={{ color: 'var(--ink)' }}>
            <div>{(stats.knowledge || 0).toLocaleString()} atoms</div>
            <div>{(stats.entities || 0).toLocaleString()} entities</div>
            {stats.conversation_memory > 0 && (
              <div style={{ opacity: 0.6 }}>{stats.conversation_memory} conversations</div>
            )}
            {stats.knowledge_gaps > 0 && (
              <div style={{ opacity: 0.6 }}>{stats.knowledge_gaps} gaps</div>
            )}
          </div>
        ) : (
          <span className="font-ernie text-xs" style={{ opacity: 0.4 }}>loading...</span>
        )}
      </section>

      {/* System */}
      <section className="mb-5 pencil-line-faint pb-4">
        <h3 className="font-ernie text-xs mb-2" style={{ color: 'var(--bark, #6b5b4e)', opacity: 0.6 }}>
          system
        </h3>
        {system ? (
          <div className="font-ernie text-xs space-y-1" style={{ color: 'var(--ink)' }}>
            <div><StatusDot alive={true} />server (8420)</div>
            <div><StatusDot alive={system.ollama} />ollama</div>
            <div><StatusDot alive={system.gemini} />gemini</div>
            <div><StatusDot alive={system.claude} />claude</div>
            {system.knowledge && (
              <div style={{ opacity: 0.6 }}>
                {(system.knowledge.atoms || 0).toLocaleString()} atoms, {(system.knowledge.entities || 0).toLocaleString()} entities
              </div>
            )}
          </div>
        ) : (
          <span className="font-ernie text-xs" style={{ opacity: 0.4 }}>loading...</span>
        )}
      </section>

      {/* Fleet */}
      <section className="mb-5">
        <h3 className="font-ernie text-xs mb-2" style={{ color: 'var(--bark, #6b5b4e)', opacity: 0.6 }}>
          fleet
        </h3>
        {fleet?.providers ? (
          <div className="font-ernie text-xs space-y-1" style={{ color: 'var(--ink)' }}>
            <div>
              {fleet.providers.filter(p => p.active).length}/{fleet.providers.length} providers active
            </div>
            <div className="mt-2 space-y-0.5" style={{ opacity: 0.6 }}>
              {fleet.providers.filter(p => p.active).slice(0, 8).map(p => (
                <div key={p.name}><StatusDot alive={true} />{p.name}</div>
              ))}
              {fleet.providers.filter(p => p.active).length > 8 && (
                <div style={{ opacity: 0.5 }}>+{fleet.providers.filter(p => p.active).length - 8} more</div>
              )}
            </div>
          </div>
        ) : (
          <span className="font-ernie text-xs" style={{ opacity: 0.4 }}>loading...</span>
        )}
      </section>
    </div>
  );
}
