import React, { useState } from 'react';
import { paScan, paPlan, paExecute, paStatus, paCorrect } from '../api';
import SoftButton from './SoftButton';
import ConsentDialog from './ConsentDialog';

/**
 * DrivePanel — PA Drive organizer.
 * Scan, review plan, consent-execute.
 * Aionic: pencil lines, no chrome.
 */
export default function DrivePanel({ onClose }) {
  const [phase, setPhase] = useState('idle'); // idle | scanning | scanned | executing | done
  const [summary, setSummary] = useState(null);
  const [plan, setPlan] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [consent, setConsent] = useState(null); // {scope, label} or null
  const [progress, setProgress] = useState(null);
  const [showCorrect, setShowCorrect] = useState(false);
  const [correctPath, setCorrectPath] = useState('');
  const [correctDest, setCorrectDest] = useState('');
  const [correctText, setCorrectText] = useState('');
  const [correctCategory, setCorrectCategory] = useState('');
  const [correctResult, setCorrectResult] = useState(null);

  async function handleScan() {
    setPhase('scanning');
    setError(null);
    try {
      const data = await paScan();
      if (data.error) { setError(data.error); setPhase('idle'); return; }
      setSummary(data.summary);
      const planData = await paPlan();
      setPlan(planData);
      setPhase('scanned');
    } catch (e) {
      setError(e.message);
      setPhase('idle');
    }
  }

  async function handleExecute(scope) {
    setConsent(null);
    setPhase('executing');
    setError(null);

    // Poll progress
    const interval = setInterval(async () => {
      try {
        const p = await paStatus();
        setProgress(p);
      } catch {}
    }, 1000);

    try {
      const data = await paExecute(scope);
      setResult(prev => ({ ...prev, [scope]: data.result }));
      clearInterval(interval);
      setPhase('done');
    } catch (e) {
      clearInterval(interval);
      setError(e.message);
      setPhase('scanned');
    }
  }

  function requestConsent(scope, label) {
    setConsent({ scope, label });
  }

  return (
    <div className="h-full flex flex-col px-4 py-6 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 pencil-line-faint pb-3">
        <h2 className="font-ernie text-lg opacity-active">drive organizer</h2>
        <SoftButton onClick={onClose}>&times;</SoftButton>
      </div>

      {/* Idle — scan prompt */}
      {phase === 'idle' && (
        <div className="flex-1 flex flex-col items-center justify-center">
          <p className="font-ernie text-sm opacity-faint mb-4 text-center">
            scan your drive to classify, deduplicate,<br />and organize everything
          </p>
          <SoftButton onClick={handleScan}>scan drive</SoftButton>
        </div>
      )}

      {/* Scanning */}
      {phase === 'scanning' && (
        <div className="flex-1 flex items-center justify-center">
          <p className="font-ernie text-sm opacity-faint animate-pulse">scanning...</p>
        </div>
      )}

      {/* Scanned — show summary + plan */}
      {phase === 'scanned' && summary && (
        <div className="flex-1 space-y-4">
          {/* Category breakdown */}
          <div className="pencil-line-faint pb-3">
            <span className="font-ernie text-xs opacity-faint block mb-2">
              {summary.total_files} files &middot; {summary.total_size_mb} MB
            </span>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              {Object.entries(summary.by_category || {}).map(([cat, count]) => (
                <div key={cat} className="flex justify-between font-ernie text-xs">
                  <span className="opacity-pencil">{cat}</span>
                  <span className="opacity-faint">{count}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Action breakdown */}
          {plan?.summary && (
            <div className="pencil-line-faint pb-3">
              <span className="font-ernie text-xs opacity-faint block mb-2">plan</span>
              <div className="font-ernie text-xs opacity-pencil space-y-0.5">
                <div>move: {plan.summary.files_to_move} files</div>
                <div>delete: {plan.summary.files_to_delete} files</div>
                <div>skip: {plan.summary.files_to_skip} files</div>
                <div>create: {plan.summary.folders_to_create} folders</div>
              </div>
            </div>
          )}

          {/* Destination breakdown */}
          {plan?.summary?.by_destination && (
            <div className="pencil-line-faint pb-3 max-h-48 overflow-y-auto">
              <span className="font-ernie text-xs opacity-faint block mb-2">destinations</span>
              {Object.entries(plan.summary.by_destination).map(([dest, count]) => (
                <div key={dest} className="flex justify-between font-ernie text-xs">
                  <span className="opacity-pencil truncate mr-2">{dest}</span>
                  <span className="opacity-faint flex-shrink-0">{count}</span>
                </div>
              ))}
            </div>
          )}

          {/* Duplicate count */}
          {summary.duplicate_count > 0 && (
            <div className="pencil-line-faint pb-3">
              <span className="font-ernie text-xs opacity-faint">
                {summary.duplicate_count} duplicates detected
              </span>
            </div>
          )}

          {/* Consent buttons */}
          <div className="space-y-2 pt-2">
            <SoftButton onClick={() => requestConsent('organize', 'Move files to organized folders?')} className="block">
              organize
            </SoftButton>
            {summary.duplicate_count > 0 && (
              <SoftButton onClick={() => requestConsent('dedupe', 'Remove duplicate files?')} className="block">
                deduplicate
              </SoftButton>
            )}
            {(summary.by_category?.cache || 0) > 0 && (
              <SoftButton onClick={() => requestConsent('cleanup', 'Delete cache files and empty folders?')} className="block">
                clean cache
              </SoftButton>
            )}
            <SoftButton onClick={handleScan} className="block">
              rescan
            </SoftButton>
            <SoftButton onClick={() => setShowCorrect(!showCorrect)} className="block">
              correct a file
            </SoftButton>
          </div>
        </div>
      )}

      {/* Executing */}
      {phase === 'executing' && (
        <div className="flex-1 flex flex-col items-center justify-center">
          <p className="font-ernie text-sm opacity-faint animate-pulse mb-2">
            {progress?.phase || 'working'}...
          </p>
          {progress?.files_total > 0 && (
            <p className="font-ernie text-xs opacity-faint">
              {progress.files_processed} / {progress.files_total}
            </p>
          )}
          {progress?.current_file && (
            <p className="font-ernie text-xs opacity-faint truncate max-w-full mt-1">
              {progress.current_file}
            </p>
          )}
        </div>
      )}

      {/* Done */}
      {phase === 'done' && result && (
        <div className="flex-1 space-y-3">
          <span className="font-ernie text-xs opacity-faint block">complete</span>
          {Object.entries(result).map(([scope, r]) => (
            <div key={scope} className="pencil-line-faint pb-2">
              <span className="font-ernie text-xs opacity-pencil block">{scope}</span>
              <div className="font-ernie text-xs opacity-faint">
                {r.moved != null && <div>moved: {r.moved}</div>}
                {r.ingested != null && <div>ingested: {r.ingested}</div>}
                {r.deleted != null && <div>deleted: {r.deleted}</div>}
                {r.empty_dirs_removed != null && <div>dirs cleaned: {r.empty_dirs_removed}</div>}
                {r.errors?.length > 0 && <div className="text-red-400">errors: {r.errors.length}</div>}
              </div>
            </div>
          ))}
          <SoftButton onClick={handleScan} className="block mt-4">scan again</SoftButton>
          <SoftButton onClick={() => setShowCorrect(!showCorrect)} className="block">
            correct a file
          </SoftButton>
        </div>
      )}

      {/* Correction form */}
      {showCorrect && (
        <div className="pencil-line-faint pb-3 pt-2 space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-ernie text-xs opacity-faint">correct a file</span>
            <SoftButton onClick={() => { setShowCorrect(false); setCorrectResult(null); }}>
              &times;
            </SoftButton>
          </div>
          <input
            value={correctPath}
            onChange={e => setCorrectPath(e.target.value)}
            placeholder="file path (relative to Drive root)"
            className="w-full bg-transparent font-ernie text-xs opacity-pencil outline-none pb-1"
            style={{ borderBottom: '1px solid var(--pencil)' }}
          />
          <input
            value={correctDest}
            onChange={e => setCorrectDest(e.target.value)}
            placeholder="move to folder (e.g. Creative/)"
            className="w-full bg-transparent font-ernie text-xs opacity-pencil outline-none pb-1"
            style={{ borderBottom: '1px solid var(--pencil)' }}
          />
          <input
            value={correctCategory}
            onChange={e => setCorrectCategory(e.target.value)}
            placeholder="new category (e.g. creative, personal)"
            className="w-full bg-transparent font-ernie text-xs opacity-pencil outline-none pb-1"
            style={{ borderBottom: '1px solid var(--pencil)' }}
          />
          <textarea
            value={correctText}
            onChange={e => setCorrectText(e.target.value)}
            placeholder="corrected text (leave empty to keep existing)"
            rows={3}
            className="w-full bg-transparent font-ernie text-xs opacity-pencil outline-none resize-none pb-1"
            style={{ borderBottom: '1px solid var(--pencil)' }}
          />
          <SoftButton onClick={async () => {
            setCorrectResult(null);
            const data = await paCorrect({
              path: correctPath,
              destination: correctDest || undefined,
              text: correctText || undefined,
              category: correctCategory || undefined,
            });
            setCorrectResult(data.result || data);
          }}>
            apply correction
          </SoftButton>
          {correctResult && (
            <div className="font-ernie text-xs opacity-faint">
              {correctResult.moved && <div>moved</div>}
              {correctResult.re_ingested && <div>re-ingested</div>}
              <div>{correctResult.details}</div>
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-2">
          <span className="font-ernie text-xs opacity-pencil">{error}</span>
        </div>
      )}

      {/* Consent dialog */}
      {consent && (
        <ConsentDialog
          title={consent.label}
          onConsent={() => handleExecute(consent.scope)}
          onDecline={() => setConsent(null)}
        />
      )}
    </div>
  );
}
