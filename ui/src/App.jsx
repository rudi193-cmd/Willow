import React, { useState } from 'react';
import useChat from './hooks/useChat';
import useEmergencyDetection from './hooks/useEmergencyDetection';
import ChatPanel from './components/ChatPanel';
import EmergencyTrigger from './components/EmergencyTrigger';
import DropZone from './components/DropZone';
import BreathingRing from './components/BreathingRing';
import SoftButton from './components/SoftButton';
import DashboardView from './components/DashboardView';

/**
 * App — Simple pathname router.
 *   /           → Shiva (chat interface)
 *   /dashboard  → Postboard (tile grid)
 */

function getRoute() {
  const path = window.location.pathname;
  if (path === '/dashboard' || path === '/dashboard/') return 'dashboard';
  return 'shiva';
}

function navigate(path) {
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export default function App() {
  const [route, setRoute] = useState(getRoute);

  // Listen for popstate (back/forward)
  React.useEffect(() => {
    function onPop() { setRoute(getRoute()); }
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  if (route === 'dashboard') {
    return <DashboardView onNavigate={navigate} />;
  }

  return <ShivaChat onNavigate={navigate} />;
}

/**
 * ShivaChat — The chat interface.
 * Always Shiva persona. Breathing ring landing → chat.
 * Hamburger on RIGHT for app menu.
 */
function ShivaChat({ onNavigate }) {
  const { messages, isStreaming, exchangeCount, piLimit, coherence, sendMessage, clearMessages, atLimit } = useChat();
  const { isDistressed, check: checkEmergency } = useEmergencyDetection();
  const [menuOpen, setMenuOpen] = useState(false);
  const [chatActive, setChatActive] = useState(false);

  function handleSend(text) {
    setChatActive(true);
    sendMessage(text, 'Shiva_Consumer');
  }

  function handleNewSession() {
    clearMessages();
    setChatActive(false);
    setMenuOpen(false);
  }

  const showLanding = !chatActive && messages.length === 0;

  return (
    <div className="h-screen flex flex-col bg-page relative">
      {/* Hamburger — top right */}
      <div className="absolute top-4 right-5" style={{ zIndex: 50 }}>
        <SoftButton onClick={() => setMenuOpen(!menuOpen)} className="text-2xl">
          {menuOpen ? '\u2715' : '\u2261'}
        </SoftButton>
      </div>

      {/* Dropdown menu — right-aligned */}
      {menuOpen && (
        <>
          <div
            className="fixed inset-0"
            style={{ zIndex: 39 }}
            onClick={() => setMenuOpen(false)}
          />
          <div
            className="absolute top-12 right-4 py-3 px-5"
            style={{
              zIndex: 50,
              background: 'var(--page)',
              border: '1px solid var(--pencil)',
              minWidth: 180,
            }}
          >
            <span
              className="font-ernie text-xs block mb-3"
              style={{ color: 'var(--bark)', opacity: 0.5 }}
            >
              apps
            </span>

            <MenuLink
              label="dashboard"
              onClick={() => { setMenuOpen(false); onNavigate('/dashboard'); }}
            />
            <MenuLink
              label="nest"
              onClick={() => { setMenuOpen(false); onNavigate('/dashboard'); }}
            />
            <MenuLink
              label="fleet"
              onClick={() => { setMenuOpen(false); onNavigate('/dashboard'); }}
            />

            <div className="pencil-line-faint my-3" />

            <span
              className="font-ernie text-xs block mb-2"
              style={{ color: 'var(--bark)', opacity: 0.5 }}
            >
              session
            </span>
            <div className="font-ernie text-xs mb-2" style={{ opacity: 0.4 }}>
              {exchangeCount} / {piLimit} exchanges
            </div>
            <MenuLink label="new session" onClick={handleNewSession} />
          </div>
        </>
      )}

      {showLanding ? (
        /* Landing — wordmark + breathing ring */
        <div className="h-full flex flex-col items-center justify-center select-none">
          <h1
            className="font-ernie text-4xl mb-8"
            style={{ color: 'var(--bark, #6b5b4e)', opacity: 0.7 }}
          >
            shiva
          </h1>
          <BreathingRing
            size={200}
            onClick={() => setChatActive(true)}
          />
          <p
            className="font-ernie text-sm mt-8"
            style={{ color: 'var(--bark, #6b5b4e)', opacity: 0.4 }}
          >
            click to begin, or just start typing
          </p>
        </div>
      ) : (
        /* Chat view */
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
      )}

      {/* Emergency trigger — always present */}
      <EmergencyTrigger isDistressed={isDistressed} />
    </div>
  );
}

/** Menu link — Ernie font, pencil opacity */
function MenuLink({ label, onClick }) {
  return (
    <button
      onClick={onClick}
      className="font-ernie text-sm bg-transparent border-0 cursor-pointer block w-full text-left py-1 opacity-pencil hover:opacity-active transition-opacity duration-200"
    >
      {label}
    </button>
  );
}
