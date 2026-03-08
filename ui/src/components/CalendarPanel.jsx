import React, { useState, useEffect } from 'react';
import SoftButton from './SoftButton';

const BASE = '';

async function fetchEvents(from, to) {
  const params = new URLSearchParams({ from_dt: from, to_dt: to });
  const res = await fetch(`${BASE}/api/calendar/events?${params}`);
  return res.json();
}

async function fetchTodos(status = 'open') {
  const res = await fetch(`${BASE}/api/calendar/todos?status=${status}`);
  return res.json();
}

async function createEvent(data) {
  const res = await fetch(`${BASE}/api/calendar/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

async function createTodo(data) {
  const res = await fetch(`${BASE}/api/calendar/todos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

async function patchEvent(id, data) {
  const res = await fetch(`${BASE}/api/calendar/events/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

async function patchTodo(id, data) {
  const res = await fetch(`${BASE}/api/calendar/todos/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

const CATEGORIES = ['personal', 'legal', 'medical', 'work', 'school', 'co-parenting', 'bankruptcy', 'other'];
const PRIORITIES  = ['low', 'normal', 'high', 'urgent'];

function formatDate(dt) {
  if (!dt) return '';
  const d = new Date(dt);
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

function formatTime(dt) {
  if (!dt) return '';
  const d = new Date(dt);
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

function groupByDate(events) {
  const groups = {};
  for (const e of events) {
    const day = e.start_dt?.slice(0, 10) || 'unknown';
    if (!groups[day]) groups[day] = [];
    groups[day].push(e);
  }
  return groups;
}

function priorityDot(p) {
  const dots = { urgent: '●●', high: '●', normal: '', low: '·' };
  return dots[p] || '';
}

/**
 * CalendarPanel — Events and personal todos.
 * Slides in from right. Same pencil aesthetic as KnowledgePanel.
 */
export default function CalendarPanel({ onClose }) {
  const [tab, setTab]         = useState('events');
  const [events, setEvents]   = useState([]);
  const [todos, setTodos]     = useState([]);
  const [showDone, setShowDone] = useState(false);
  const [adding, setAdding]   = useState(false);

  // New event form
  const [evTitle, setEvTitle]   = useState('');
  const [evDate, setEvDate]     = useState('');
  const [evTime, setEvTime]     = useState('');
  const [evCat, setEvCat]       = useState('personal');
  const [evAllDay, setEvAllDay] = useState(false);

  // New todo form
  const [tdTitle, setTdTitle] = useState('');
  const [tdDue, setTdDue]     = useState('');
  const [tdPri, setTdPri]     = useState('normal');
  const [tdCat, setTdCat]     = useState('personal');

  const today = new Date().toISOString().slice(0, 10);
  const in30  = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);

  useEffect(() => {
    if (tab === 'events') {
      fetchEvents(today, in30).then(d => setEvents(d.events || []));
    } else {
      fetchTodos(showDone ? 'done' : 'open').then(d => setTodos(d.todos || []));
    }
  }, [tab, showDone]);

  async function submitEvent() {
    if (!evTitle || !evDate) return;
    const start_dt = evAllDay ? evDate : `${evDate}T${evTime || '00:00'}:00`;
    await createEvent({ title: evTitle, start_dt, all_day: evAllDay ? 1 : 0, category: evCat });
    setEvTitle(''); setEvDate(''); setEvTime(''); setEvCat('personal'); setEvAllDay(false);
    setAdding(false);
    fetchEvents(today, in30).then(d => setEvents(d.events || []));
  }

  async function submitTodo() {
    if (!tdTitle) return;
    await createTodo({ title: tdTitle, due_date: tdDue || null, priority: tdPri, category: tdCat });
    setTdTitle(''); setTdDue(''); setTdPri('normal'); setTdCat('personal');
    setAdding(false);
    fetchTodos('open').then(d => setTodos(d.todos || []));
  }

  async function cancelEvent(id) {
    await patchEvent(id, { status: 'cancelled' });
    setEvents(ev => ev.filter(e => e.id !== id));
  }

  async function completeTodo(id) {
    await patchTodo(id, { status: 'done' });
    setTodos(td => td.filter(t => t.id !== id));
  }

  const grouped = groupByDate(events);

  return (
    <div className="h-full flex flex-col px-4 py-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-4">
        <span className="font-ernie text-lg opacity-active">calendar</span>
        <SoftButton onClick={onClose}>&times;</SoftButton>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 mb-4 pencil-line-faint pb-2">
        <SoftButton active={tab === 'events'} onClick={() => { setTab('events'); setAdding(false); }}>
          events
        </SoftButton>
        <SoftButton active={tab === 'todos'} onClick={() => { setTab('todos'); setAdding(false); }}>
          todos
        </SoftButton>
      </div>

      {/* ── Events tab ── */}
      {tab === 'events' && (
        <div className="flex-1 overflow-y-auto">
          {Object.keys(grouped).length === 0 && !adding && (
            <p className="font-ernie text-sm opacity-faint">no events in the next 30 days</p>
          )}

          {Object.entries(grouped).map(([day, dayEvents]) => (
            <div key={day} className="mb-4">
              <span className="font-ernie text-xs opacity-faint block mb-1">{formatDate(day)}</span>
              {dayEvents.map(e => (
                <div key={e.id} className="flex items-start gap-2 mb-2 pencil-line-faint pb-2">
                  <div className="flex-1">
                    <span className="font-ernie text-xs opacity-faint mr-2">
                      {e.all_day ? 'all day' : formatTime(e.start_dt)}
                    </span>
                    <span className="font-journal text-sm opacity-active">{e.title}</span>
                    {e.category !== 'personal' && (
                      <span className="font-ernie text-xs opacity-faint ml-2">[{e.category}]</span>
                    )}
                  </div>
                  <SoftButton onClick={() => cancelEvent(e.id)} className="text-xs opacity-faint">
                    ×
                  </SoftButton>
                </div>
              ))}
            </div>
          ))}

          {adding && (
            <div className="mt-2 space-y-2 pencil-line-faint pb-3">
              <input
                value={evTitle}
                onChange={e => setEvTitle(e.target.value)}
                placeholder="event title"
                className="w-full bg-transparent font-journal text-sm outline-none py-1"
                style={{ borderBottom: '1px solid var(--pencil)' }}
              />
              <input
                type="date"
                value={evDate}
                onChange={e => setEvDate(e.target.value)}
                className="w-full bg-transparent font-ernie text-sm outline-none py-1"
                style={{ borderBottom: '1px solid var(--pencil)' }}
              />
              {!evAllDay && (
                <input
                  type="time"
                  value={evTime}
                  onChange={e => setEvTime(e.target.value)}
                  className="w-full bg-transparent font-ernie text-sm outline-none py-1"
                  style={{ borderBottom: '1px solid var(--pencil)' }}
                />
              )}
              <label className="flex items-center gap-2 font-ernie text-xs opacity-faint cursor-pointer">
                <input type="checkbox" checked={evAllDay} onChange={e => setEvAllDay(e.target.checked)} />
                all day
              </label>
              <select
                value={evCat}
                onChange={e => setEvCat(e.target.value)}
                className="w-full bg-transparent font-ernie text-sm outline-none py-1 opacity-pencil"
                style={{ borderBottom: '1px solid var(--pencil)' }}
              >
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              <div className="flex gap-2 pt-1">
                <SoftButton onClick={submitEvent}>save</SoftButton>
                <SoftButton onClick={() => setAdding(false)}>cancel</SoftButton>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Todos tab ── */}
      {tab === 'todos' && (
        <div className="flex-1 overflow-y-auto">
          <div className="flex justify-between items-center mb-3">
            <span className="font-ernie text-xs opacity-faint">
              {showDone ? 'completed' : 'open'}
            </span>
            <SoftButton onClick={() => setShowDone(s => !s)} className="text-xs">
              {showDone ? 'show open' : 'show done'}
            </SoftButton>
          </div>

          {todos.length === 0 && !adding && (
            <p className="font-ernie text-sm opacity-faint">
              {showDone ? 'nothing completed yet' : 'no open todos'}
            </p>
          )}

          {todos.map(t => (
            <div key={t.id} className="flex items-start gap-2 mb-3 pencil-line-faint pb-2">
              {!showDone && (
                <button
                  onClick={() => completeTodo(t.id)}
                  className="mt-0.5 w-4 h-4 rounded-sm opacity-pencil hover:opacity-active transition-opacity"
                  style={{ border: '1px solid var(--pencil)', flexShrink: 0 }}
                />
              )}
              <div className="flex-1">
                <span className="font-journal text-sm opacity-active">{t.title}</span>
                <div className="font-ernie text-xs opacity-faint mt-0.5 space-x-2">
                  {t.due_date && <span>due {formatDate(t.due_date)}</span>}
                  {t.priority !== 'normal' && <span>{priorityDot(t.priority)} {t.priority}</span>}
                  {t.category !== 'personal' && <span>[{t.category}]</span>}
                </div>
              </div>
            </div>
          ))}

          {adding && (
            <div className="mt-2 space-y-2 pencil-line-faint pb-3">
              <input
                value={tdTitle}
                onChange={e => setTdTitle(e.target.value)}
                placeholder="what needs doing"
                className="w-full bg-transparent font-journal text-sm outline-none py-1"
                style={{ borderBottom: '1px solid var(--pencil)' }}
              />
              <input
                type="date"
                value={tdDue}
                onChange={e => setTdDue(e.target.value)}
                placeholder="due date (optional)"
                className="w-full bg-transparent font-ernie text-sm outline-none py-1"
                style={{ borderBottom: '1px solid var(--pencil)' }}
              />
              <select
                value={tdPri}
                onChange={e => setTdPri(e.target.value)}
                className="w-full bg-transparent font-ernie text-sm outline-none py-1 opacity-pencil"
                style={{ borderBottom: '1px solid var(--pencil)' }}
              >
                {PRIORITIES.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
              <select
                value={tdCat}
                onChange={e => setTdCat(e.target.value)}
                className="w-full bg-transparent font-ernie text-sm outline-none py-1 opacity-pencil"
                style={{ borderBottom: '1px solid var(--pencil)' }}
              >
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              <div className="flex gap-2 pt-1">
                <SoftButton onClick={submitTodo}>save</SoftButton>
                <SoftButton onClick={() => setAdding(false)}>cancel</SoftButton>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Add button — bottom */}
      {!adding && (
        <div className="mt-4 pt-2 pencil-line-faint">
          <SoftButton onClick={() => setAdding(true)}>
            + add {tab === 'events' ? 'event' : 'todo'}
          </SoftButton>
        </div>
      )}
    </div>
  );
}
