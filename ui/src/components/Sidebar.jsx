import React, { useState, useEffect } from 'react';
import { fetchPersonas, fetchStatus } from '../api';
import SoftButton from './SoftButton';

/**
 * Sidebar — Persona picker, system status, nav.
 * Faint pencil dividers between sections.
 */
export default function Sidebar({ persona, onPersonaChange, exchangeCount, piLimit, onKnowledgeOpen, onDriveOpen, onNewSession }) {
  const [personas, setPersonas] = useState({});
  const [status, setStatus] = useState(null);

  useEffect(() => {
    fetchPersonas().then(setPersonas).catch(() => {});
    fetchStatus().then(setStatus).catch(() => {});
  }, []);

  return (
    <div className="h-full flex flex-col px-4 py-6">
      {/* Title */}
      <h1 className="font-ernie text-2xl opacity-active mb-6">willow</h1>

      {/* Persona picker */}
      <div className="mb-4 pencil-line-faint pb-3">
        <span className="font-ernie text-xs opacity-faint block mb-2">persona</span>
        <select
          value={persona}
          onChange={e => onPersonaChange(e.target.value)}
          className="w-full bg-transparent font-ernie opacity-pencil hover:opacity-active
            outline-none border-0 cursor-pointer transition-opacity duration-300"
          style={{ borderBottom: '1px solid var(--pencil)' }}
        >
          {Object.keys(personas).length > 0 ? (
            Object.keys(personas).map(name => (
              <option key={name} value={name}>{name}</option>
            ))
          ) : (
            <option value="Willow">Willow</option>
          )}
        </select>
      </div>

      {/* Session counter */}
      <div className="mb-4 pencil-line-faint pb-3">
        <span className="font-ernie text-xs opacity-faint block mb-1">session</span>
        <span className="font-ernie text-sm opacity-pencil">
          {exchangeCount} / {piLimit} exchanges
        </span>
      </div>

      {/* Actions */}
      <div className="space-y-2 mb-4 pencil-line-faint pb-3">
        <SoftButton onClick={onKnowledgeOpen} className="block text-left">
          knowledge
        </SoftButton>
        <SoftButton onClick={onDriveOpen} className="block text-left">
          drive
        </SoftButton>
        <SoftButton onClick={onNewSession} className="block text-left">
          new session
        </SoftButton>
      </div>

      {/* System status — bottom */}
      <div className="mt-auto">
        <span className="font-ernie text-xs opacity-faint block mb-1">system</span>
        {status ? (
          <div className="font-ernie text-xs opacity-faint space-y-0.5">
            <div>ollama: {status.ollama ? 'online' : 'offline'}</div>
            <div>models: {status.models?.length || 0}</div>
            <div>gemini: {status.gemini ? 'yes' : 'no'}</div>
            <div>knowledge: {status.knowledge?.atoms || 0} atoms</div>
          </div>
        ) : (
          <span className="font-ernie text-xs opacity-faint">connecting...</span>
        )}
      </div>
    </div>
  );
}
