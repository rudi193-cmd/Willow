import React, { useState, useEffect, useCallback } from 'react';
import { fetchNestQueue, scanNest, reviewNestItem, skipNestItem } from '../api';
import SoftButton from './SoftButton';

/**
 * NestReviewPanel — Review files staged from the Nest.
 *
 * Each item shows:
 *   - Filename + app source (inferred from name)
 *   - Willow's proposed category + destination path
 *   - Matched entities from the knowledge graph
 *   - OCR preview (what Willow read)
 *   - Editable summary/category fields
 *   - Three action buttons: Keep Everything / Delete File Keep Data / Delete Everything
 */
export default function NestReviewPanel({ onClose }) {
  const [items, setItems]       = useState([]);
  const [loading, setLoading]   = useState(true);
  const [scanning, setScanning] = useState(false);
  const [active, setActive]     = useState(null);   // item being reviewed
  const [editing, setEditing]   = useState({});      // { summary, category, path }
  const [working, setWorking]   = useState(false);   // action in flight

  const load = useCallback(() => {
    setLoading(true);
    fetchNestQueue('pending')
      .then(d => setItems(d.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleScan() {
    setScanning(true);
    try {
      await scanNest();
      load();
    } finally {
      setScanning(false);
    }
  }

  function openItem(item) {
    setActive(item);
    setEditing({
      summary:  item.proposed_summary  || '',
      category: item.proposed_category || 'media',
      path:     item.proposed_path     || '',
    });
  }

  function closeItem() {
    setActive(null);
    setEditing({});
  }

  async function handleDecision(dispose_file, dispose_data, move_file = false) {
    if (!active) return;
    setWorking(true);
    try {
      await reviewNestItem(active.id, {
        user_summary:  editing.summary  || null,
        user_category: editing.category || null,
        user_path:     editing.path     || null,
        dispose_file,
        dispose_data,
        move_file,
      });
      closeItem();
      load();
    } catch (e) {
      // surface error inline
    } finally {
      setWorking(false);
    }
  }

  async function handleSkip() {
    if (!active) return;
    setWorking(true);
    try {
      await skipNestItem(active.id);
      closeItem();
      load();
    } finally {
      setWorking(false);
    }
  }

  // ── List view ──────────────────────────────────────────────────────────────
  if (!active) {
    return (
      <div className="h-full flex flex-col px-4 py-6">
        {/* Header */}
        <div className="flex items-start justify-between mb-1">
          <div>
            <h2 className="text-base font-semibold text-stone-800">Nest Inbox</h2>
            <p className="text-xs text-stone-400 mt-0.5">
              Review files before they enter your knowledge graph.
            </p>
          </div>
          <button onClick={onClose} className="text-stone-400 hover:text-stone-600 text-lg leading-none">×</button>
        </div>

        <div className="border-t border-dashed border-stone-200 my-3" />

        {/* Scan button */}
        <div className="mb-4">
          <SoftButton onClick={handleScan} disabled={scanning} className="w-full text-sm">
            {scanning ? 'Scanning…' : 'Scan Nest for new files'}
          </SoftButton>
        </div>

        {/* List */}
        {loading ? (
          <p className="text-xs text-stone-400">Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-xs text-stone-400">No files waiting for review.</p>
        ) : (
          <ul className="flex-1 overflow-y-auto space-y-2">
            {items.map(item => (
              <li key={item.id}>
                <button
                  onClick={() => openItem(item)}
                  className="w-full text-left px-3 py-2.5 rounded-lg border border-stone-200 hover:border-stone-400 hover:bg-stone-50 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-stone-700 truncate max-w-[180px]">
                      {item.filename}
                    </span>
                    <span className="text-[10px] text-stone-400 bg-stone-100 rounded px-1.5 py-0.5 ml-2 shrink-0">
                      {item.proposed_category || 'unknown'}
                    </span>
                  </div>
                  {item.matched_entities?.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {item.matched_entities.slice(0, 3).map(e => (
                        <span key={e.id} className="text-[10px] text-stone-500 bg-stone-100 rounded px-1.5">
                          {e.name}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="text-[10px] text-stone-400 mt-1">
                    {new Date(item.staged_at).toLocaleDateString()}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  // ── Detail / review view ───────────────────────────────────────────────────
  return (
    <div className="h-full flex flex-col px-4 py-6">
      {/* Header */}
      <div className="flex items-start justify-between mb-1">
        <button onClick={closeItem} className="text-stone-400 hover:text-stone-600 text-sm flex items-center gap-1">
          ← Back
        </button>
        <button onClick={onClose} className="text-stone-400 hover:text-stone-600 text-lg leading-none">×</button>
      </div>

      <div className="border-t border-dashed border-stone-200 my-3" />

      {/* Filename */}
      <div className="mb-3">
        <p className="text-xs text-stone-400 mb-0.5">File</p>
        <p className="text-sm font-medium text-stone-800 break-all">{active.filename}</p>
      </div>

      {/* OCR preview — what Willow read */}
      {active.ocr_preview && (
        <div className="mb-3">
          <p className="text-xs text-stone-400 mb-0.5">What I read</p>
          <div className="text-xs text-stone-600 bg-stone-50 rounded p-2 border border-stone-200 max-h-24 overflow-y-auto whitespace-pre-wrap">
            {active.ocr_preview}
          </div>
        </div>
      )}

      {/* Matched entities */}
      {active.matched_entities?.length > 0 && (
        <div className="mb-3">
          <p className="text-xs text-stone-400 mb-1">Looks related to</p>
          <div className="flex flex-wrap gap-1.5">
            {active.matched_entities.slice(0, 6).map(e => (
              <span key={e.id} className="text-xs text-stone-600 bg-stone-100 rounded-full px-2 py-0.5">
                {e.name}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="border-t border-dashed border-stone-200 my-3" />

      {/* Editable summary */}
      <div className="mb-3">
        <label className="text-xs text-stone-400 block mb-1">Summary — correct if wrong</label>
        <textarea
          className="w-full text-xs border border-stone-200 rounded p-2 text-stone-700 focus:outline-none focus:border-stone-400 resize-none"
          rows={3}
          value={editing.summary}
          onChange={e => setEditing(prev => ({ ...prev, summary: e.target.value }))}
          placeholder="What is this file for?"
        />
      </div>

      {/* Editable category */}
      <div className="mb-3">
        <label className="text-xs text-stone-400 block mb-1">Category</label>
        <select
          className="w-full text-xs border border-stone-200 rounded p-2 text-stone-700 focus:outline-none focus:border-stone-400"
          value={editing.category}
          onChange={e => setEditing(prev => ({ ...prev, category: e.target.value }))}
        >
          {['media', 'legal', 'personal', 'personal_document', 'narrative',
            'reference', 'code', 'handoff', 'archive'].map(c => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      {/* Proposed destination */}
      <div className="mb-4">
        <label className="text-xs text-stone-400 block mb-1">File destination</label>
        <input
          className="w-full text-xs border border-stone-200 rounded p-2 text-stone-600 focus:outline-none focus:border-stone-400"
          value={editing.path}
          onChange={e => setEditing(prev => ({ ...prev, path: e.target.value }))}
        />
      </div>

      {/* Actions */}
      <div className="space-y-2 mt-auto">
        <button
          onClick={() => handleDecision(false, false, true)}
          disabled={working}
          className="w-full text-sm font-ernie px-3 py-2 rounded bg-stone-800 text-white hover:bg-stone-700 disabled:opacity-40 transition-colors"
        >
          Accept data + move to destination
        </button>
        <SoftButton
          onClick={() => handleDecision(false, false, false)}
          disabled={working}
          className="w-full text-sm"
        >
          Keep in Nest + keep data
        </SoftButton>
        <SoftButton
          onClick={() => handleDecision(true, false)}
          disabled={working}
          className="w-full text-sm"
        >
          Delete file, keep data
        </SoftButton>
        <SoftButton
          onClick={() => handleDecision(true, true)}
          disabled={working}
          className="w-full text-sm text-red-600 border-red-200 hover:border-red-400"
        >
          Delete everything
        </SoftButton>
        <SoftButton
          onClick={handleSkip}
          disabled={working}
          className="w-full text-xs text-stone-400"
        >
          Skip for now
        </SoftButton>
      </div>
    </div>
  );
}
