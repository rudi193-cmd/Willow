import React, { useState } from 'react';
import useChat from './hooks/useChat';
import useEmergencyDetection from './hooks/useEmergencyDetection';
import ChatPanel from './components/ChatPanel';
import Sidebar from './components/Sidebar';
import KnowledgePanel from './components/KnowledgePanel';
import EmergencyTrigger from './components/EmergencyTrigger';
import DropZone from './components/DropZone';
import DrivePanel from './components/DrivePanel';
import SoftButton from './components/SoftButton';

/**
 * App — JournalShell.
 * Two-zone layout: main chat + slide-in panels.
 * 314 exchange π harmonic limit. Emergency trigger always present.
 */
export default function App() {
  const { messages, isStreaming, exchangeCount, piLimit, coherence, sendMessage, clearMessages, atLimit } = useChat();
  const { isDistressed, check: checkEmergency } = useEmergencyDetection();
  const [persona, setPersona] = useState('Willow');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);
  const [driveOpen, setDriveOpen] = useState(false);

  function handleSend(text) {
    sendMessage(text, persona);
  }

  function handleNewSession() {
    clearMessages();
    setSidebarOpen(false);
  }

  return (
    <div className="h-screen flex bg-page">
      {/* Sidebar — slides from left */}
      {sidebarOpen && (
        <>
          <div
            className="fixed inset-0 bg-page/50 md:hidden"
            style={{ zIndex: 40 }}
            onClick={() => setSidebarOpen(false)}
          />
          <aside
            className="fixed md:relative w-64 h-full bg-page pencil-line"
            style={{ zIndex: 50, borderRight: '1px solid var(--pencil-faint)' }}
          >
            <Sidebar
              persona={persona}
              onPersonaChange={setPersona}
              exchangeCount={exchangeCount}
              piLimit={piLimit}
              onKnowledgeOpen={() => { setKnowledgeOpen(true); setDriveOpen(false); setSidebarOpen(false); }}
              onDriveOpen={() => { setDriveOpen(true); setKnowledgeOpen(false); setSidebarOpen(false); }}
              onNewSession={handleNewSession}
            />
          </aside>
        </>
      )}

      {/* Main chat area */}
      <main className="flex-1 h-full relative">
        {/* Menu toggle — top left, faint */}
        <div className="absolute top-4 left-4" style={{ zIndex: 30 }}>
          <SoftButton onClick={() => setSidebarOpen(!sidebarOpen)}>
            {sidebarOpen ? '\u2190' : '\u2261'}
          </SoftButton>
        </div>

        <DropZone>
          <ChatPanel
            messages={messages}
            isStreaming={isStreaming}
            coherence={coherence}
            onSend={handleSend}
            atLimit={atLimit}
            onCheckEmergency={checkEmergency}
          />
        </DropZone>
      </main>

      {/* Knowledge panel — slides from right */}
      {knowledgeOpen && (
        <>
          <div
            className="fixed inset-0 bg-page/30 md:hidden"
            style={{ zIndex: 40 }}
            onClick={() => setKnowledgeOpen(false)}
          />
          <aside
            className="fixed right-0 md:relative w-80 h-full bg-page"
            style={{ zIndex: 50, borderLeft: '1px solid var(--pencil-faint)' }}
          >
            <KnowledgePanel onClose={() => setKnowledgeOpen(false)} />
          </aside>
        </>
      )}

      {/* Drive panel — slides from right */}
      {driveOpen && (
        <>
          <div
            className="fixed inset-0 bg-page/30 md:hidden"
            style={{ zIndex: 40 }}
            onClick={() => setDriveOpen(false)}
          />
          <aside
            className="fixed right-0 md:relative w-80 h-full bg-page"
            style={{ zIndex: 50, borderLeft: '1px solid var(--pencil-faint)' }}
          >
            <DrivePanel onClose={() => setDriveOpen(false)} />
          </aside>
        </>
      )}

      {/* Emergency trigger — always present, never disabled */}
      <EmergencyTrigger isDistressed={isDistressed} />
    </div>
  );
}
