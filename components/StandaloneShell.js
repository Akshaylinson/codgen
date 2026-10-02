'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { ImageStudio, VideoStudio, LipSyncStudio, CinemaStudio } from 'studio';

const TABS = [
  { id: 'image',   label: 'Image Studio' },
  { id: 'video',   label: 'Video Studio' },
  { id: 'lipsync', label: 'Lip Sync' },
  { id: 'cinema',  label: 'Cinema Studio' },
];

const TOKEN_KEY   = 'codgen_token';
const REFRESH_KEY = 'codgen_refresh';
const EMAIL_KEY   = 'codgen_email';
const BACKEND     = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

// ── API helper with automatic refresh-token rotation ─────────────────────────
async function apiFetch(path, options = {}, onNewTokens) {
  const token = localStorage.getItem(TOKEN_KEY);
  const res = await fetch(`${BACKEND}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers, Authorization: `Bearer ${token}` },
  });

  if (res.status === 401) {
    const refresh = localStorage.getItem(REFRESH_KEY);
    if (!refresh) throw new Error('SESSION_EXPIRED');

    const rr = await fetch(`${BACKEND}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!rr.ok) throw new Error('SESSION_EXPIRED');

    const rd = await rr.json();
    localStorage.setItem(TOKEN_KEY,   rd.access_token);
    localStorage.setItem(REFRESH_KEY, rd.refresh_token);
    if (onNewTokens) onNewTokens(rd);

    // Retry original request with new token
    return fetch(`${BACKEND}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers, Authorization: `Bearer ${rd.access_token}` },
    });
  }
  return res;
}

export default function StandaloneShell() {
  const [token,        setToken]        = useState(null);
  const [email,        setEmail]        = useState('');
  const [credits,      setCredits]      = useState(null);
  const [isVerified,   setIsVerified]   = useState(true);
  const [activeTab,    setActiveTab]    = useState('image');
  const [showSettings, setShowSettings] = useState(false);
  const [hasMounted,   setHasMounted]   = useState(false);

  // Auth form state
  const [authMode,    setAuthMode]    = useState('login'); // login | register | forgot
  const [formEmail,   setFormEmail]   = useState('');
  const [formPass,    setFormPass]    = useState('');
  const [authError,   setAuthError]   = useState('');
  const [authMsg,     setAuthMsg]     = useState('');
  const [authLoading, setAuthLoading] = useState(false);

  const onNewTokens = useCallback((rd) => {
    setToken(rd.access_token);
    if (rd.credits !== undefined) setCredits(rd.credits);
  }, []);

  useEffect(() => {
    setHasMounted(true);
    // Pick up OAuth tokens from URL (Google/GitHub callback redirect)
    const urlParams = new URLSearchParams(window.location.search);
    const oauthAccess  = urlParams.get('access_token');
    const oauthRefresh = urlParams.get('refresh_token');
    if (oauthAccess && oauthRefresh) {
      localStorage.setItem(TOKEN_KEY,   oauthAccess);
      localStorage.setItem(REFRESH_KEY, oauthRefresh);
      window.history.replaceState({}, '', window.location.pathname);
      setToken(oauthAccess);
      return;
    }
    const t = localStorage.getItem(TOKEN_KEY);
    const e = localStorage.getItem(EMAIL_KEY);
    if (t) { setToken(t); setEmail(e || ''); }
  }, []);

  // Fetch credits when settings opens
  useEffect(() => {
    if (!showSettings || !token) return;
    apiFetch('/auth/me', {}, onNewTokens)
      .then(r => r.json())
      .then(d => { if (d.credits !== undefined) setCredits(d.credits); if (d.is_verified !== undefined) setIsVerified(d.is_verified); })
      .catch(() => {});
  }, [showSettings, token, onNewTokens]);

  const handleAuth = useCallback(async (e) => {
    e.preventDefault();
    setAuthError(''); setAuthMsg(''); setAuthLoading(true);
    try {
      if (authMode === 'forgot') {
        const res = await fetch(`${BACKEND}/auth/forgot-password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: formEmail.trim().toLowerCase() }),
        });
        const d = await res.json();
        setAuthMsg(d.message || 'Check your email for a reset link.');
        return;
      }

      const res = await fetch(`${BACKEND}/auth/${authMode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: formEmail.trim().toLowerCase(), password: formPass }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Authentication failed');

      localStorage.setItem(TOKEN_KEY,   data.access_token);
      localStorage.setItem(REFRESH_KEY, data.refresh_token);
      localStorage.setItem(EMAIL_KEY,   data.email);
      setToken(data.access_token);
      setEmail(data.email);
      if (data.credits   !== undefined) setCredits(data.credits);
      if (data.is_verified !== undefined) setIsVerified(data.is_verified);
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') { setToken(null); return; }
      setAuthError(err.message);
    } finally {
      setAuthLoading(false);
    }
  }, [authMode, formEmail, formPass]);

  const handleLogout = useCallback(async () => {
    const refresh = localStorage.getItem(REFRESH_KEY);
    if (refresh) {
      fetch(`${BACKEND}/auth/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      }).catch(() => {});
    }
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(EMAIL_KEY);
    setToken(null); setEmail(''); setCredits(null); setIsVerified(true);
  }, []);

  const handleTopUp = useCallback(async () => {
    try {
      const res = await apiFetch('/billing/checkout', {
        method: 'POST',
        body: JSON.stringify({ quantity: 1 }),
      }, onNewTokens);
      const d = await res.json();
      if (d.checkout_url) window.location.href = d.checkout_url;
      else setAuthError(d.detail || 'Billing not available');
    } catch { setAuthError('Billing not available'); }
  }, [onNewTokens]);

  if (!hasMounted) return (
    <div className="min-h-screen bg-[#050505] flex items-center justify-center">
      <div className="animate-spin text-[#d9ff00] text-3xl">◌</div>
    </div>
  );

  // ── Auth screen ─────────────────────────────────────────────────────────────
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
            <p className="text-white/40 text-sm">
              {authMode === 'login' ? 'Sign in to your account' : authMode === 'register' ? 'Create your account' : 'Reset your password'}
            </p>
          </div>

          <form onSubmit={handleAuth} className="space-y-4">
            <input
              type="email" placeholder="Email" value={formEmail}
              onChange={e => setFormEmail(e.target.value)} required
              className="w-full bg-black/40 border border-white/5 rounded-xl px-4 py-3 text-white placeholder:text-white/20 focus:outline-none focus:border-[#d9ff00]/40 transition-colors"
            />
            {authMode !== 'forgot' && (
              <input
                type="password" placeholder="Password" value={formPass}
                onChange={e => setFormPass(e.target.value)} required
                className="w-full bg-black/40 border border-white/5 rounded-xl px-4 py-3 text-white placeholder:text-white/20 focus:outline-none focus:border-[#d9ff00]/40 transition-colors"
              />
            )}
            {authError && <p className="text-red-400 text-sm">{authError}</p>}
            {authMsg   && <p className="text-green-400 text-sm">{authMsg}</p>}
            <button type="submit" disabled={authLoading}
              className="w-full bg-[#d9ff00] text-black font-black py-3 rounded-xl hover:opacity-90 transition-opacity disabled:opacity-50">
              {authLoading ? '...' : authMode === 'login' ? 'Sign In' : authMode === 'register' ? 'Create Account' : 'Send Reset Link'}
            </button>
          </form>

          <div className="flex justify-between mt-4 text-sm text-white/30">
            {authMode !== 'forgot' && (
              <button onClick={() => { setAuthMode(authMode === 'login' ? 'register' : 'login'); setAuthError(''); setAuthMsg(''); }}
                className="text-[#d9ff00] hover:underline">
                {authMode === 'login' ? 'Register' : 'Sign In'}
              </button>
            )}
            {authMode === 'login' && (
              <button onClick={() => { setAuthMode('forgot'); setAuthError(''); setAuthMsg(''); }}
                className="hover:text-white transition-colors">
                Forgot password?
              </button>
            )}
            {authMode !== 'login' && (
              <button onClick={() => { setAuthMode('login'); setAuthError(''); setAuthMsg(''); }}
                className="hover:text-white transition-colors">
                Back to sign in
              </button>
            )}
          </div>

          {authMode !== 'forgot' && (
            <div className="mt-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex-1 h-px bg-white/10" />
                <span className="text-white/20 text-xs">or continue with</span>
                <div className="flex-1 h-px bg-white/10" />
              </div>
              <div className="flex gap-3">
                <a href={`${BACKEND}/auth/oauth/google`}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-white/5 border border-white/10 text-white/70 hover:bg-white/10 text-sm transition-colors">
                  <svg width="16" height="16" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
                  Google
                </a>
                <a href={`${BACKEND}/auth/oauth/github`}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-white/5 border border-white/10 text-white/70 hover:bg-white/10 text-sm transition-colors">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2z"/></svg>
                  GitHub
                </a>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Studio ──────────────────────────────────────────────────────────────────
  return (
    <div className="h-screen bg-[#050505] flex flex-col overflow-hidden">
      <header className="flex-shrink-0 flex items-center justify-between px-4 pt-4 pb-0 border-b border-white/5">
        <span className="text-white font-black text-lg tracking-wider uppercase">Codgen</span>

        <nav className="flex items-center gap-1">
          {TABS.map((tab) => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                activeTab === tab.id ? 'bg-[#d9ff00] text-black' : 'text-white/50 hover:text-white'
              }`}>
              {tab.label}
            </button>
          ))}
        </nav>

        <button onClick={() => setShowSettings(true)} className="text-white/40 hover:text-white text-sm transition-colors">
          ⚙ Settings
        </button>
      </header>

      {!isVerified && (
        <div className="flex-shrink-0 flex items-center justify-between bg-yellow-500/10 border-b border-yellow-500/20 px-4 py-2">
          <span className="text-yellow-400 text-sm">⚠ Please verify your email to unlock generation.</span>
          <button
            onClick={async () => {
              try {
                await apiFetch('/auth/resend-verification', { method: 'POST', body: '{}' }, onNewTokens);
                alert('Verification email sent — check your inbox.');
              } catch {}
            }}
            className="text-yellow-400 text-xs underline hover:text-yellow-300 ml-4">
            Resend email
          </button>
        </div>
      )}

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

            <p className="text-white/50 text-sm mb-1">Signed in as</p>
            <p className="text-white/80 text-sm mb-5">{email}</p>

            <div className="flex items-center justify-between bg-white/5 rounded-xl px-4 py-3 mb-2">
              <span className="text-white/50 text-sm">Credits remaining</span>
              <span className="text-[#d9ff00] font-black text-lg">{credits === null ? '…' : credits}</span>
            </div>

            <button onClick={handleTopUp}
              className="w-full mb-5 py-2 rounded-xl bg-[#d9ff00]/10 border border-[#d9ff00]/20 text-[#d9ff00] text-sm font-bold hover:bg-[#d9ff00]/20 transition-colors">
              + Buy 100 Credits
            </button>

            <div className="flex gap-3">
              <button onClick={() => { handleLogout(); setShowSettings(false); }}
                className="flex-1 py-2 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 text-sm transition-colors">
                Sign Out
              </button>
              <button onClick={() => setShowSettings(false)}
                className="flex-1 py-2 rounded-lg bg-white/5 text-white hover:bg-white/10 text-sm transition-colors">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
