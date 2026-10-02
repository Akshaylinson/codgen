'use client';

import { useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export default function VerifyEmailPage() {
  const params = useSearchParams();
  const router = useRouter();
  const [status, setStatus] = useState('verifying'); // verifying | success | error

  useEffect(() => {
    const token = params.get('token');
    if (!token) { setStatus('error'); return; }
    fetch(`${BACKEND}/auth/verify-email?token=${encodeURIComponent(token)}`, { redirect: 'follow' })
      .then(r => { setStatus(r.ok || r.redirected ? 'success' : 'error'); })
      .catch(() => setStatus('error'));
  }, [params]);

  return (
    <div className="min-h-screen bg-[#050505] flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-[#0a0a0a] border border-white/10 rounded-3xl p-8 text-center">
        <h1 className="text-2xl font-black text-white uppercase tracking-wider mb-4">Codgen</h1>
        {status === 'verifying' && <p className="text-white/50">Verifying your email…</p>}
        {status === 'success'   && (
          <>
            <p className="text-green-400 mb-6">Email verified! You can now generate.</p>
            <button onClick={() => router.push('/studio')}
              className="bg-[#d9ff00] text-black font-black py-3 px-8 rounded-xl hover:opacity-90 transition-opacity">
              Go to Studio
            </button>
          </>
        )}
        {status === 'error' && (
          <>
            <p className="text-red-400 mb-6">Invalid or expired verification link.</p>
            <button onClick={() => router.push('/studio')}
              className="bg-white/10 text-white py-3 px-8 rounded-xl hover:bg-white/20 transition-colors">
              Back to Studio
            </button>
          </>
        )}
      </div>
    </div>
  );
}
