import React, { useState, useEffect } from 'react';
import { fetchApps, setAppConsent } from '../api';
import SoftButton from './SoftButton';

/**
 * AppsPanel — Toggle which SAFE apps can push documents to your Willow.
 * Slides in from right. Same pencil-divider pattern as KnowledgePanel.
 */
export default function AppsPanel({ onClose }) {
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(null); // app_id being toggled

  useEffect(() => {
    fetchApps()
      .then(data => setApps(data.apps || []))
      .catch(() => setApps([]))
      .finally(() => setLoading(false));
  }, []);

  async function handleToggle(app) {
    setToggling(app.app_id);
    try {
      const next = !app.consented;
      await setAppConsent(app.app_id, next);
      setApps(prev => prev.map(a =>
        a.app_id === app.app_id
          ? { ...a, consented: next, granted_at: next ? new Date().toISOString() : null }
          : a
      ));
    } catch (e) {
      // leave state unchanged on error
    } finally {
      setToggling(null);
    }
  }

  return (
    <div className="h-full flex flex-col px-4 py-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-2">
        <span className="font-ernie text-lg opacity-active">connected apps</span>
        <SoftButton onClick={onClose}>&times;</SoftButton>
      </div>
      <p className="font-ernie text-xs opacity-faint mb-4 pencil-line-faint pb-3">
        toggle which apps can share documents with your willow
      </p>

      {/* App list */}
      <div className="flex-1 overflow-y-auto">
        {loading && (
          <p className="font-ernie text-sm opacity-faint">loading...</p>
        )}
        {!loading && apps.length === 0 && (
          <p className="font-ernie text-sm opacity-faint">no apps registered</p>
        )}
        {apps.map(app => (
          <div key={app.app_id} className="mb-4 pencil-line-faint pb-3">
            <div className="flex items-center justify-between">
              {/* Toggle */}
              <button
                onClick={() => handleToggle(app)}
                disabled={toggling === app.app_id}
                className="flex items-center gap-2 transition-opacity duration-200"
                style={{ opacity: toggling === app.app_id ? 0.4 : 1 }}
                aria-label={app.consented ? `Disconnect ${app.name}` : `Connect ${app.name}`}
              >
                <span
                  className="font-ernie text-base"
                  style={{ color: app.consented ? 'var(--pencil)' : 'var(--pencil-faint)' }}
                >
                  {app.consented ? '●' : '○'}
                </span>
                <span className="font-ernie text-sm opacity-active">{app.name}</span>
              </button>
              <span className="font-ernie text-xs opacity-faint">{app.privacy_tier || ''}</span>
            </div>
            {app.description && (
              <p className="font-journal text-xs opacity-faint mt-1 ml-6 leading-relaxed">
                {app.description.slice(0, 120)}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
