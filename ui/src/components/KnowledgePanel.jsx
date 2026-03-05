import React, { useState, useEffect } from 'react';
import { searchKnowledge, fetchGaps, fetchStats, ingestFile } from '../api';
import SoftButton from './SoftButton';

/**
 * KnowledgePanel — Search, gaps, stats.
 * Slides in from right. Pencil dividers, no boxes.
 */
export default function KnowledgePanel({ onClose }) {
  const [tab, setTab] = useState('search'); // search | gaps | stats
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [gaps, setGaps] = useState([]);
  const [stats, setStats] = useState(null);
  const fileInputRef = React.useRef(null);

  useEffect(() => {
    if (tab === 'gaps') {
      fetchGaps().then(data => setGaps(data.gaps || []));
    } else if (tab === 'stats') {
      fetchStats().then(data => setStats(data));
    }
  }, [tab]);

  async function handleSearch() {
    if (!query.trim()) return;
    const data = await searchKnowledge(query);
    setResults(data.results || []);
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') handleSearch();
  }

  async function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    await ingestFile(file);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  return (
    <div className="h-full flex flex-col px-4 py-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-4">
        <span className="font-ernie text-lg opacity-active">knowledge</span>
        <SoftButton onClick={onClose}>&times;</SoftButton>
      </div>

      {/* Tabs — pencil divider */}
      <div className="flex gap-4 mb-4 pencil-line-faint pb-2">
        <SoftButton active={tab === 'search'} onClick={() => setTab('search')}>search</SoftButton>
        <SoftButton active={tab === 'gaps'} onClick={() => setTab('gaps')}>gaps</SoftButton>
        <SoftButton active={tab === 'stats'} onClick={() => setTab('stats')}>stats</SoftButton>
      </div>

      {/* Search tab */}
      {tab === 'search' && (
        <div className="flex-1 overflow-y-auto">
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="search knowledge..."
            className="w-full bg-transparent font-journal outline-none py-1 mb-4
              placeholder:font-ernie placeholder:opacity-faint"
            style={{ borderBottom: '1px solid var(--pencil)' }}
          />
          {results.map((r, i) => (
            <div key={i} className="mb-4 pencil-line-faint pb-2">
              <span className="font-ernie text-sm opacity-faint block">{r.filename || r.category || 'atom'}</span>
              <p className="font-journal text-sm opacity-active leading-relaxed mt-1">
                {(r.content_text || r.summary || '').slice(0, 200)}
              </p>
            </div>
          ))}
          {results.length === 0 && query && (
            <p className="font-ernie text-sm opacity-faint">no results</p>
          )}
        </div>
      )}

      {/* Gaps tab */}
      {tab === 'gaps' && (
        <div className="flex-1 overflow-y-auto">
          {gaps.length === 0 && <p className="font-ernie text-sm opacity-faint">no gaps recorded yet</p>}
          {gaps.map((g, i) => (
            <div key={i} className="mb-3 pencil-line-faint pb-2">
              <span className="font-journal text-sm">{g.query}</span>
              <span className="font-ernie text-xs opacity-faint ml-2">
                {g.times_hit}x &middot; {g.source}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Stats tab */}
      {tab === 'stats' && (
        <div className="flex-1 overflow-y-auto font-ernie text-sm opacity-pencil space-y-2">
          {stats ? (
            <>
              <div>knowledge atoms: {stats.knowledge || 0}</div>
              <div>conversations: {stats.conversation_memory || 0}</div>
              <div>entities: {stats.entities || 0}</div>
              <div>gaps: {stats.knowledge_gaps || 0}</div>
            </>
          ) : (
            <p>loading...</p>
          )}
        </div>
      )}

      {/* File upload button — bottom of panel */}
      <div className="mt-4 pt-2 pencil-line-faint">
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,.pdf,.docx,.json,.csv,.html"
          onChange={handleFileUpload}
          className="hidden"
        />
        <SoftButton onClick={() => fileInputRef.current?.click()}>
          + drop or browse files
        </SoftButton>
      </div>
    </div>
  );
}
