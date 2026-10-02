'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

function ResetForm() {
  const params  = useSearchParams();
  const router  = useRouter();
  const token   = params.get('token') || '';

  const [password,  setPassword]  = useState('');
  const [password2, setPassword2] = useState('');
  const [error,     setError]     = useState('');
  const [msg,       setMsg]       = useState('');
  const [loading,   setLoading]   = useState(false);

  useEffect(() => {
    if (!token) setError('Missing reset token. Request a new link.');
  }, [token]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(''); setMsg('');
    if (password !== password2) { setError('Passwords do not match'); return; }
    if (password.length < 8)    { setError('Password must be at least 8 characters'); return; }

    setLoading(true);
    try {
      const res  = await fetch(`${BACKEND}/auth/reset-password`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ token, password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Reset failed');
      setMsg('Password updated! Redirecting to sign in…');
      setTimeout(() => router.push('/studio'), 2000);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

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
          <p className="text-white/40 text-sm">Set your new password</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="password" placeholder="New password" value={password}
            onChange={e => setPassword(e.target.value)} required
            className="w-full bg-black/40 border border-white/5 rounded-xl px-4 py-3 text-white placeholder:text-white/20 focus:outline-none focus:border-[#d9ff00]/40 transition-colors"
          />
          <input
            type="password" placeholder="Confirm new password" value={password2}
            onChange={e => setPassword2(e.target.value)} required
            className="w-full bg-black/40 border border-white/5 rounded-xl px-4 py-3 text-white placeholder:text-white/20 focus:outline-none focus:border-[#d9ff00]/40 transition-colors"
          />
          {error && <p className="text-red-400 text-sm">{error}</p>}
          {msg   && <p className="text-green-400 text-sm">{msg}</p>}
          <button type="submit" disabled={loading || !token}
            className="w-full bg-[#d9ff00] text-black font-black py-3 rounded-xl hover:opacity-90 transition-opacity disabled:opacity-50">
            {loading ? '…' : 'Update Password'}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetForm />
    </Suspense>
  );
}
