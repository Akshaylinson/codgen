const BACKEND = window.__CODGEN_BACKEND_URL__ || import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

export function SettingsModal(onClose) {
    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 bg-black/80 flex items-center justify-center z-50';

    const email = localStorage.getItem('codgen_email') || 'Unknown';

    const modal = document.createElement('div');
    modal.className = 'bg-card p-6 rounded-xl border border-border-color w-96 glass';
    modal.innerHTML = `
        <h2 class="text-xl font-bold mb-4">Settings</h2>
        <p class="text-sm text-secondary mb-1">Signed in as</p>
        <p class="text-white font-mono text-sm mb-4">${email}</p>
        <div class="flex items-center justify-between bg-white/5 rounded-xl px-4 py-3 mb-2">
            <span class="text-white/50 text-sm">Credits remaining</span>
            <span id="credits-val" class="text-primary font-black text-lg">…</span>
        </div>
        <button id="topup-btn" class="w-full mb-4 py-2 rounded-xl bg-primary/10 border border-primary/20 text-primary text-sm font-bold hover:bg-primary/20 transition-colors">
            + Buy 100 Credits
        </button>
        <div class="flex justify-end gap-2">
            <button id="settings-signout" class="px-4 py-2 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 text-sm transition-colors">Sign Out</button>
            <button id="settings-close" class="px-4 py-2 rounded hover:bg-white/5 text-sm">Close</button>
        </div>
    `;

    overlay.appendChild(modal);

    // Fetch live credits
    const token = localStorage.getItem('codgen_token');
    if (token) {
        fetch(`${BACKEND}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
            .then(r => r.json())
            .then(d => { if (d.credits !== undefined) modal.querySelector('#credits-val').textContent = d.credits; })
            .catch(() => {});
    }

    modal.querySelector('#topup-btn').onclick = async () => {
        try {
            const res  = await fetch(`${BACKEND}/billing/checkout`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify({ quantity: 1 }),
            });
            const data = await res.json();
            if (data.checkout_url) window.location.href = data.checkout_url;
        } catch { alert('Billing not available'); }
    };

    modal.querySelector('#settings-signout').onclick = () => {
        const refresh = localStorage.getItem('codgen_refresh');
        if (refresh) {
            fetch(`${BACKEND}/auth/logout`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refresh }),
            }).catch(() => {});
        }
        ['codgen_token', 'codgen_refresh', 'codgen_email'].forEach(k => localStorage.removeItem(k));
        document.body.removeChild(overlay);
        if (onClose) onClose();
        window.location.reload();
    };

    modal.querySelector('#settings-close').onclick = () => {
        document.body.removeChild(overlay);
        if (onClose) onClose();
    };

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            document.body.removeChild(overlay);
            if (onClose) onClose();
        }
    });

    return overlay;
}
