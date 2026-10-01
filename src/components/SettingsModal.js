export function SettingsModal(onClose) {
    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 bg-black/80 flex items-center justify-center z-50';

    const modal = document.createElement('div');
    modal.className = 'bg-card p-6 rounded-xl border border-border-color w-96 glass';

    const email = localStorage.getItem('codgen_email') || 'Unknown';

    modal.innerHTML = `
        <h2 class="text-xl font-bold mb-4">Settings</h2>
        <p class="text-sm text-secondary mb-1">Signed in as</p>
        <p class="text-white font-mono text-sm mb-6">${email}</p>
        <div class="flex justify-end gap-2">
            <button id="settings-signout" class="px-4 py-2 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 text-sm transition-colors">Sign Out</button>
            <button id="settings-close" class="px-4 py-2 rounded hover:bg-white/5 text-sm">Close</button>
        </div>
    `;

    modal.querySelector('#settings-signout').onclick = () => {
        localStorage.removeItem('codgen_token');
        localStorage.removeItem('codgen_email');
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

    overlay.appendChild(modal);
    return overlay;
}
