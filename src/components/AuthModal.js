const BACKEND = window.__CODGEN_BACKEND_URL__ || import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

export function AuthModal(onSuccess) {
    let mode = 'login'; // 'login' | 'register'

    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm px-6';

    function render() {
        overlay.innerHTML = '';
        const modal = document.createElement('div');
        modal.className = 'w-full max-w-md bg-panel-bg border border-white/10 rounded-3xl p-8 shadow-3xl';

        modal.innerHTML = `
            <div class="flex flex-col items-center text-center mb-8">
                <div class="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center border border-primary/20 shadow-glow mb-6">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#d9ff00" stroke-width="2">
                        <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3m-3-3l-2.25-2.25"/>
                    </svg>
                </div>
                <h2 class="text-2xl font-black text-white uppercase tracking-wider mb-2">Codgen</h2>
                <p class="text-secondary text-sm">${mode === 'login' ? 'Sign in to your account' : 'Create your account'}</p>
            </div>

            <div class="space-y-4">
                <input id="auth-email" type="email" placeholder="Email"
                    class="w-full bg-black/40 border border-white/5 rounded-2xl px-5 py-4 text-white placeholder:text-muted focus:outline-none focus:border-primary/50 transition-colors" />
                <input id="auth-pass" type="password" placeholder="Password"
                    class="w-full bg-black/40 border border-white/5 rounded-2xl px-5 py-4 text-white placeholder:text-muted focus:outline-none focus:border-primary/50 transition-colors" />
                <p id="auth-error" class="text-red-400 text-sm hidden"></p>
                <button id="auth-submit" class="w-full bg-primary text-black font-black py-4 rounded-2xl hover:shadow-glow transition-all">
                    ${mode === 'login' ? 'Sign In' : 'Create Account'}
                </button>
                <p class="text-center text-white/30 text-sm">
                    ${mode === 'login' ? "Don't have an account?" : 'Already have an account?'}
                    <button id="auth-toggle" class="text-primary hover:underline ml-1">
                        ${mode === 'login' ? 'Register' : 'Sign In'}
                    </button>
                </p>
            </div>
        `;

        overlay.appendChild(modal);

        modal.querySelector('#auth-toggle').onclick = () => {
            mode = mode === 'login' ? 'register' : 'login';
            render();
        };

        modal.querySelector('#auth-submit').onclick = async () => {
            const email    = modal.querySelector('#auth-email').value.trim().toLowerCase();
            const password = modal.querySelector('#auth-pass').value;
            const errEl    = modal.querySelector('#auth-error');
            const btn      = modal.querySelector('#auth-submit');

            if (!email || !password) {
                errEl.textContent = 'Email and password required';
                errEl.classList.remove('hidden');
                return;
            }

            btn.textContent = '...';
            btn.disabled = true;
            errEl.classList.add('hidden');

            try {
                const res = await fetch(`${BACKEND}/auth/${mode}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Authentication failed');

                localStorage.setItem('codgen_token', data.token);
                localStorage.setItem('codgen_email', data.email);
                document.body.removeChild(overlay);
                if (onSuccess) onSuccess(data.token);
            } catch (err) {
                errEl.textContent = err.message;
                errEl.classList.remove('hidden');
                btn.textContent = mode === 'login' ? 'Sign In' : 'Create Account';
                btn.disabled = false;
            }
        };
    }

    render();
    document.body.appendChild(overlay);
    return overlay;
}
