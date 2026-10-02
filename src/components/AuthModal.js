const BACKEND = window.__CODGEN_BACKEND_URL__ || import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

export function AuthModal(onSuccess) {
    let mode = 'login'; // login | register | forgot

    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm px-6';

    function render() {
        overlay.innerHTML = '';
        const modal = document.createElement('div');
        modal.className = 'w-full max-w-md bg-panel-bg border border-white/10 rounded-3xl p-8 shadow-3xl';

        const modeLabel = mode === 'login' ? 'Sign in to your account'
                        : mode === 'register' ? 'Create your account'
                        : 'Reset your password';

        modal.innerHTML = `
            <div class="flex flex-col items-center text-center mb-8">
                <div class="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center border border-primary/20 mb-6">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#d9ff00" stroke-width="2">
                        <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3m-3-3l-2.25-2.25"/>
                    </svg>
                </div>
                <h2 class="text-2xl font-black text-white uppercase tracking-wider mb-2">Codgen</h2>
                <p class="text-secondary text-sm">${modeLabel}</p>
            </div>

            <div class="space-y-4">
                <input id="auth-email" type="email" placeholder="Email"
                    class="w-full bg-black/40 border border-white/5 rounded-2xl px-5 py-4 text-white placeholder:text-muted focus:outline-none focus:border-primary/50 transition-colors" />
                ${mode !== 'forgot' ? `
                <input id="auth-pass" type="password" placeholder="Password"
                    class="w-full bg-black/40 border border-white/5 rounded-2xl px-5 py-4 text-white placeholder:text-muted focus:outline-none focus:border-primary/50 transition-colors" />
                ` : ''}
                <p id="auth-error" class="text-red-400 text-sm hidden"></p>
                <p id="auth-msg"   class="text-green-400 text-sm hidden"></p>
                <button id="auth-submit" class="w-full bg-primary text-black font-black py-4 rounded-2xl hover:shadow-glow transition-all">
                    ${mode === 'login' ? 'Sign In' : mode === 'register' ? 'Create Account' : 'Send Reset Link'}
                </button>
                <div class="flex justify-between text-sm text-white/30">
                    ${mode !== 'forgot' ? `
                    <button id="auth-toggle" class="text-primary hover:underline">
                        ${mode === 'login' ? 'Register' : 'Sign In'}
                    </button>` : ''}
                    ${mode === 'login' ? `<button id="auth-forgot" class="hover:text-white transition-colors">Forgot password?</button>` : ''}
                    ${mode !== 'login' ? `<button id="auth-back" class="hover:text-white transition-colors">Back to sign in</button>` : ''}
                </div>
            </div>
        `;

        overlay.appendChild(modal);

        modal.querySelector('#auth-toggle')?.addEventListener('click', () => {
            mode = mode === 'login' ? 'register' : 'login'; render();
        });
        modal.querySelector('#auth-forgot')?.addEventListener('click', () => { mode = 'forgot'; render(); });
        modal.querySelector('#auth-back')?.addEventListener('click',   () => { mode = 'login';  render(); });

        modal.querySelector('#auth-submit').addEventListener('click', async () => {
            const email  = modal.querySelector('#auth-email').value.trim().toLowerCase();
            const pass   = modal.querySelector('#auth-pass')?.value || '';
            const errEl  = modal.querySelector('#auth-error');
            const msgEl  = modal.querySelector('#auth-msg');
            const btn    = modal.querySelector('#auth-submit');

            errEl.classList.add('hidden');
            msgEl.classList.add('hidden');

            if (!email) { errEl.textContent = 'Email required'; errEl.classList.remove('hidden'); return; }
            if (mode !== 'forgot' && !pass) { errEl.textContent = 'Password required'; errEl.classList.remove('hidden'); return; }

            btn.textContent = '…'; btn.disabled = true;

            try {
                if (mode === 'forgot') {
                    const res  = await fetch(`${BACKEND}/auth/forgot-password`, {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email }),
                    });
                    const data = await res.json();
                    msgEl.textContent = data.message || 'Check your email for a reset link.';
                    msgEl.classList.remove('hidden');
                    btn.textContent = 'Sent'; return;
                }

                const res  = await fetch(`${BACKEND}/auth/${mode}`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password: pass }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Authentication failed');

                localStorage.setItem('codgen_token',   data.access_token);
                localStorage.setItem('codgen_refresh',  data.refresh_token);
                localStorage.setItem('codgen_email',    data.email);
                document.body.removeChild(overlay);
                if (onSuccess) onSuccess(data.access_token);
            } catch (err) {
                errEl.textContent = err.message;
                errEl.classList.remove('hidden');
                btn.textContent = mode === 'login' ? 'Sign In' : mode === 'register' ? 'Create Account' : 'Send Reset Link';
                btn.disabled = false;
            }
        });
    }

    render();
    document.body.appendChild(overlay);
    return overlay;
}
