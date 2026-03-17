import React, { useState, useEffect } from 'react';
import BreathingRing from './BreathingRing';
import SoftButton from './SoftButton';

/**
 * DashboardView — Postboard tile grid.
 * GM Gerald, Nest, Kart, Binder, Jeles, UTETY, Fleet, Settings.
 * Each tile: icon area, label, live status dot where applicable.
 */

const TILES = [
  {
    id: 'gerald',
    label: 'GM Gerald',
    desc: 'Dispatches from Reality',
    icon: '\uD83C\uDFB2',
    color: '#d4a017',
  },
  {
    id: 'nest',
    label: 'Nest',
    desc: 'File intake & routing',
    icon: '\uD83E\uDEB9',
    color: '#7a9a6d',
    statusUrl: '/api/nest/queue?status=pending',
    statusKey: 'count',
  },
  {
    id: 'kart',
    label: 'Kart',
    desc: 'Infrastructure & tasks',
    icon: '\u2692',
    color: '#6b5b4e',
  },
  {
    id: 'binder',
    label: 'Binder',
    desc: 'The back stacks',
    icon: '\uD83D\uDCDA',
    color: '#8a6d3b',
  },
  {
    id: 'jeles',
    label: 'Jeles',
    desc: 'Special Collections',
    icon: '\uD83D\uDD0D',
    color: '#5b7a8a',
  },
  {
    id: 'utety',
    label: 'UTETY',
    desc: 'Faculty & personas',
    icon: '\uD83C\uDFDB',
    color: '#8a5b6d',
  },
  {
    id: 'fleet',
    label: 'Fleet',
    desc: 'Manage APIs',
    icon: '\u26A1',
    color: '#4a90d9',
    statusUrl: '/api/fleet/providers',
    statusKey: 'providers',
  },
  {
    id: 'settings',
    label: 'Settings',
    desc: 'System configuration',
    icon: '\u2699',
    color: '#6b5b4e',
  },
];

function StatusDot({ alive }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: 6,
        height: 6,
        borderRadius: '50%',
        background: alive ? 'var(--leaf, #7a9a6d)' : 'var(--pencil-faint)',
        marginLeft: 6,
        verticalAlign: 'middle',
      }}
    />
  );
}

function Tile({ tile, status }) {
  const [hovered, setHovered] = useState(false);

  let statusText = null;
  if (tile.id === 'nest' && status?.items) {
    const pending = status.items.length;
    if (pending > 0) statusText = `${pending} pending`;
  }
  if (tile.id === 'fleet' && status?.providers) {
    const active = status.providers.filter(p => p.active).length;
    const total = status.providers.length;
    statusText = `${active}/${total} active`;
  }

  return (
    <button
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="bg-transparent border-0 cursor-pointer text-left p-0 w-full"
      style={{
        outline: 'none',
      }}
    >
      <div
        style={{
          background: hovered ? 'var(--cream, #f5f0e8)' : 'transparent',
          border: `1px solid ${hovered ? 'var(--pencil)' : 'var(--pencil-faint)'}`,
          padding: '20px 18px',
          transition: 'all 200ms ease',
          position: 'relative',
          minHeight: 120,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
        }}
      >
        {/* Icon */}
        <div
          style={{
            fontSize: 28,
            marginBottom: 12,
            opacity: hovered ? 0.8 : 0.5,
            transition: 'opacity 200ms',
            filter: 'grayscale(60%)',
          }}
        >
          {tile.icon}
        </div>

        {/* Label + description */}
        <div>
          <div
            className="font-ernie"
            style={{
              fontSize: 16,
              color: 'var(--bark, #6b5b4e)',
              opacity: hovered ? 0.8 : 0.55,
              transition: 'opacity 200ms',
              lineHeight: 1.2,
            }}
          >
            {tile.label}
          </div>
          <div
            className="font-ernie"
            style={{
              fontSize: 11,
              color: 'var(--bark, #6b5b4e)',
              opacity: 0.3,
              marginTop: 3,
              lineHeight: 1.3,
            }}
          >
            {tile.desc}
          </div>
        </div>

        {/* Status badge */}
        {statusText && (
          <div
            className="font-ernie"
            style={{
              position: 'absolute',
              top: 10,
              right: 12,
              fontSize: 10,
              color: 'var(--leaf, #7a9a6d)',
              opacity: 0.6,
            }}
          >
            <StatusDot alive={true} />
            {' '}{statusText}
          </div>
        )}
      </div>
    </button>
  );
}

export default function DashboardView({ onNavigate }) {
  const [statuses, setStatuses] = useState({});
  const [daemons, setDaemons] = useState(null);
  const [system, setSystem] = useState(null);

  useEffect(() => {
    // Fetch live status for tiles that have statusUrl
    TILES.forEach(tile => {
      if (tile.statusUrl) {
        fetch(tile.statusUrl)
          .then(r => r.json())
          .then(data => setStatuses(prev => ({ ...prev, [tile.id]: data })))
          .catch(() => {});
      }
    });

    // Fetch daemon status
    fetch('/api/skills/status').then(r => r.json()).then(setDaemons).catch(() => {});
    fetch('/api/status').then(r => r.json()).then(setSystem).catch(() => {});
  }, []);

  const daemonList = daemons?.daemons ? Object.entries(daemons.daemons) : [];
  const aliveCount = daemonList.filter(([, v]) => v).length;

  return (
    <div className="min-h-screen bg-page">
      {/* Header */}
      <header
        className="flex items-center justify-between px-6 py-5"
        style={{ borderBottom: '1px solid var(--pencil-faint)' }}
      >
        <div className="flex items-center gap-4">
          <button
            onClick={() => onNavigate('/')}
            className="font-ernie text-2xl bg-transparent border-0 cursor-pointer"
            style={{ color: 'var(--bark, #6b5b4e)', opacity: 0.6 }}
          >
            shiva
          </button>
          <span
            className="font-ernie text-sm"
            style={{ color: 'var(--bark)', opacity: 0.25 }}
          >
            /
          </span>
          <span
            className="font-ernie text-sm"
            style={{ color: 'var(--bark)', opacity: 0.45 }}
          >
            dashboard
          </span>
        </div>

        {/* System status summary */}
        <div className="flex items-center gap-4">
          {daemons && (
            <span className="font-ernie text-xs" style={{ opacity: 0.35 }}>
              {aliveCount}/{daemonList.length} daemons
            </span>
          )}
          {system && (
            <span className="font-ernie text-xs" style={{ opacity: 0.35 }}>
              <StatusDot alive={true} /> server
              {system.ollama && <><StatusDot alive={true} /> ollama</>}
            </span>
          )}
          <BreathingRing
            size={28}
            onClick={() => onNavigate('/')}
          />
        </div>
      </header>

      {/* Tile grid */}
      <div className="px-6 py-8 max-w-4xl mx-auto">
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
            gap: 12,
          }}
        >
          {TILES.map(tile => (
            <Tile
              key={tile.id}
              tile={tile}
              status={statuses[tile.id]}
            />
          ))}
        </div>
      </div>

      {/* Daemon strip — bottom context */}
      {daemonList.length > 0 && (
        <div
          className="px-6 py-4 max-w-4xl mx-auto"
          style={{ borderTop: '1px solid var(--pencil-faint)' }}
        >
          <span
            className="font-ernie text-xs block mb-2"
            style={{ color: 'var(--bark)', opacity: 0.3 }}
          >
            daemons
          </span>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {daemonList.map(([name, alive]) => (
              <span
                key={name}
                className="font-ernie text-xs"
                style={{ opacity: alive ? 0.4 : 0.15 }}
              >
                <StatusDot alive={alive} />
                {' '}{name.replace(/^WILLOW-/, '')}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
