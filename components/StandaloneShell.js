'use client';

import { useState, useEffect, useCallback } from 'react';
import { ImageStudio, VideoStudio, LipSyncStudio, CinemaStudio } from 'studio';

const TABS = [
  { id: 'image',   label: 'Image Studio' },
  { id: 'video',   label: 'Video Studio' },
  { id: 'lipsync', label: 'Lip Sync' },
  { id: 'cinema',  label: 'Cinema Studio' },
];

const TOKEN_KEY  = 'codgen_token';
const EMAIL_KEY  = 'codgen_email';
const BACKEND    = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export default function StandaloneShell() {
  const [token,       setToken]       = useState(null);
  const [email,       setEmail]       = useState('');
  const [activeTab,   setActiveTab]   = useState('image');
  const [showSettings,setShowSettings]= useState(false);
  const [hasMounted,  setHasMounted]  = useState(false);
  const [authMode,    setAuthMode]    = useState('login'); // 'login' | 'register'
  const [formEmail,   setFormEmail]   = useState('');
  const [formPass,    setFormPass]    = useState('');
  const [authError,   setAuthError]   = useState('');
  const [authLoading, setAuthLoading] = useState(false);

  useEffect(() => {
    setHasMounted(true);
    const t = localStorage.getItem(TOKEN_KEY);
    const e = localStorage.getItem(EMAIL_KEY);
    if (t) { setToken(t); setEmail(e || ''); }
  }, []);

  const handleAuth = useCallback(async (e) => {
    e.preventDefault();
    setAuthError('');
    setAuthLoading(true);
    try {
      const res = await fetch(`${BACKEND}/auth/${authMode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: formEmail.trim().toLowerCase(), password: formPass }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Authentication failed');
      localStorage.setItem(TOKEN_KEY, data.token);
      localStorage.setItem(EMAIL_KEY, data.email);
      setToken(data.token);
      setEmail(data.email);
    } catch (err) {
      setAuthError(err.message);
    } finally {
      setAuthLoading(false);
    }
  }, [authMode, formEmail, formPass]);

  const handleLogout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(EMAIL_KEY);
    setToken(null);
    setEmail('');
  }, []);

  if (!hasMounted) return (
    <div className="min-h-screen bg-[#050505] flex items-center justify-center">
      <div className="animate-spin text-[#d9ff00] text-3xl">◌</div>
    </div>
  );

  if (!token) {
    return (
      <div className="min-h-screen bg-[#050505] flex items-center justify-center px-4">
        <div className="w-full max-w-md bg-[#0a0a0a] border border-white/10 rounded-3xl p-8">
          <div className="flex flex-col items-center text-center mb-8">
            <div className="w-16 h-16 bg-[#d9ff00]/10 rounded-2xl flex items-center justify-center border border-[#d9ff00]/20 mb-6">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#d9ff00" strokeWidth="1.5">
                <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L12 17.25l-4.5-4.5L15.5 7.5z"/>
              </svg>
            </div>
            <h1 className="text-2xl font-black text-white uppercase tracking-wider mb-2">Codgen</h1>
            <p className="text-white/40 text-sm">{authMode === 'login' ? 'Sign in to your account' : 'Create your account'}</p>
          </div>

          <form onSubmit={handleAuth} className="space-y-4">
            <input
              type="email"
              placeholder="Email"
              value={formEmail}
              onChange={e => setFormEmail(e.target.value)}
              required
              className="w-full bg-black/40 border border-white/5 rounded-xl px-4 py-3 text-white placeholder:text-white/20 focus:outline-none focus:border-[#d9ff00]/40 transition-colors"
            />
            <input
              type="password"
              placeholder="Password"
              value={formPass}
              onChange={e => setFormPass(e.target.value)}
              required
              className="w-full bg-black/40 border border-white/5 rounded-xl px-4 py-3 text-white placeholder:text-white/20 focus:outline-none focus:border-[#d9ff00]/40 transition-colors"
            />
            {authError && <p className="text-red-400 text-sm">{authError}</p>}
            <button
              type="submit"
              disabled={authLoading}
              className="w-full bg-[#d9ff00] text-black font-black py-3 rounded-xl hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {authLoading ? '...' : authMode === 'login' ? 'Sign In' : 'Create Account'}
            </button>
          </form>

          <p className="text-center text-white/30 text-sm mt-4">
            {authMode === 'login' ? "Don't have an account? " : 'Already have an account? '}
            <button
              onClick={() => { setAuthMode(authMode === 'login' ? 'register' : 'login'); setAuthError(''); }}
              className="text-[#d9ff00] hover:underline"
            >
              {authMode === 'login' ? 'Register' : 'Sign In'}
            </button>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-[#050505] flex flex-col overflow-hidden">
      <header className="flex-shrink-0 flex items-center justify-between px-4 pt-4 pb-0 border-b border-white/5">
        <span className="text-white font-black text-lg tracking-wider uppercase">Codgen</span>

        <nav className="flex items-center gap-1">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                activeTab === tab.id ? 'bg-[#d9ff00] text-black' : 'text-white/50 hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <button onClick={() => setShowSettings(true)} className="text-white/40 hover:text-white text-sm transition-colors">
          ⚙ Settings
        </button>
      </header>

      <div className="flex-1">
        {activeTab === 'image'   && <ImageStudio   apiKey={token} />}
        {activeTab === 'video'   && <VideoStudio   apiKey={token} />}
        {activeTab === 'lipsync' && <LipSyncStudio apiKey={token} />}
        {activeTab === 'cinema'  && <CinemaStudio  apiKey={token} />}
      </div>

      {showSettings && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
          <div className="bg-[#111] border border-white/10 rounded-2xl p-8 w-full max-w-md">
            <h2 className="text-white font-bold text-xl mb-6">Settings</h2>
            <p className="text-white/50 text-sm mb-6">
              Signed in as <span className="text-white/80">{email}</span>
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => { handleLogout(); setShowSettings(false); }}
                className="flex-1 py-2 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 text-sm transition-colors"
              >
                Sign Out
              </button>
              <button
                onClick={() => setShowSettings(false)}
                className="flex-1 py-2 rounded-lg bg-white/5 text-white hover:bg-white/10 text-sm transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
