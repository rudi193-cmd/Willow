import React, { useState, useCallback } from 'react';
import { ingestFile } from '../api';

const ACCEPTED = ['.txt', '.md', '.pdf', '.docx', '.json', '.csv', '.html', '.htm'];

/**
 * DropZone — Full-area drag-and-drop file intake.
 * No dedicated box — the entire children area is the drop target.
 * On dragover: faint pencil-line border. On drop: ingest via API.
 */
export default function DropZone({ children, onIngest }) {
  const [isDragging, setIsDragging] = useState(false);
  const [status, setStatus] = useState(null); // { type: 'success'|'error', text: string }

  const clearStatus = useCallback(() => {
    setTimeout(() => setStatus(null), 3000);
  }, []);

  function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }

  async function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    for (const file of files) {
      const ext = '.' + file.name.split('.').pop().toLowerCase();
      if (!ACCEPTED.includes(ext)) {
        setStatus({ type: 'error', text: `skipped: ${file.name} (unsupported)` });
        clearStatus();
        continue;
      }

      try {
        const result = await ingestFile(file);
        if (result.error) {
          setStatus({ type: 'error', text: `${file.name}: ${result.error}` });
        } else {
          setStatus({ type: 'success', text: `ingested: ${file.name}` });
          if (onIngest) onIngest(result);
        }
      } catch (err) {
        setStatus({ type: 'error', text: `failed: ${file.name}` });
      }
      clearStatus();
    }
  }

  return (
    <div
      className={`relative ${isDragging ? 'drop-active' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {children}

      {/* Ingest status notification — faint Ernie text */}
      {status && (
        <div
          className={`absolute bottom-2 left-1/2 -translate-x-1/2 font-ernie text-sm
            ${status.type === 'error' ? 'opacity-pencil' : 'opacity-faint'}
            transition-opacity duration-500`}
        >
          {status.text}
        </div>
      )}
    </div>
  );
}
