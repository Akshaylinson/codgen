'use client';

import { useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';

const BACKEND   = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
const TOKEN_KEY = 'codgen_token';

export default function AcceptInvitePage() {
  const params = useSearchParams();
  const router = useRouter();
  const [status, setStatus] = useState('idle'); // idle | loading | success | error | no_auth
  const [msg, setMsg] = useState('');

  const token = params.get('token');

  useEffect(() => {
    if (!token) { setStatus('error'); setMsg('Missing invite token.'); }
  }, [token]);

  async function accept() {
    const jwt = localStorage.getItem(TOKEN_KEY);
    if (!jwt) { setStatus('no_auth'); return; }
    setStatus('loading');
    try {
      const res = await fetch(`${BACKEND}/teams/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${jwt}` },
        body: JSON.stringify({ token }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || 'Failed to accept invite');
      setStatus('success');
      setTimeout(() => router.push('/studio'), 1500);
    } catch (e) {
      setStatus('error'); setMsg(e.message);
    }
  }

  return (
    <div className="min-h-screen bg-[#050505] flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-[#0a0a0a] border border-white/10 rounded-3xl p-8 text-center">
        <h1 className="text-2xl font-black text-white uppercase tracking-wider mb-4">Team Invite</h1>
        {status === 'idle' && token && (
          <button onClick={accept}
            className="bg-[#d9ff00] text-black font-black py-3 px-8 rounded-xl hover:opacity-90 transition-opacity">
            Accept Invite
          </button>
        )}
        {status === 'loading' && <p className="text-white/50">Accepting…</p>}
        {status === 'success' && <p className="text-green-400">Joined! Redirecting…</p>}
        {status === 'no_auth' && (
          <p className="text-yellow-400">Please sign in first, then open this link again.</p>
        )}
        {status === 'error' && <p className="text-red-400">{msg || 'Invalid or expired invite.'}</p>}
      </div>
    </div>
  );
}
