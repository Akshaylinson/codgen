import './style.css';
import { Header } from './components/Header.js';
import { ImageStudio } from './components/ImageStudio.js';
import { AuthModal } from './components/AuthModal.js';

const app = document.querySelector('#app');
let contentArea;

// Router
function navigate(page) {
  if (!contentArea) return;
  contentArea.innerHTML = '';

  if (page === 'image') {
    contentArea.appendChild(ImageStudio());
  } else if (page === 'video') {
    import('./components/VideoStudio.js').then(({ VideoStudio }) => {
      contentArea.appendChild(VideoStudio());
    });
  } else if (page === 'cinema') {
    import('./components/CinemaStudio.js').then(({ CinemaStudio }) => {
      contentArea.appendChild(CinemaStudio());
    });
  } else if (page === 'lipsync') {
    import('./components/LipSyncStudio.js').then(({ LipSyncStudio }) => {
      contentArea.appendChild(LipSyncStudio());
    });
  }
}

function boot() {
  app.innerHTML = '';
  app.appendChild(Header(navigate));

  contentArea = document.createElement('main');
  contentArea.id = 'content-area';
  contentArea.className = 'flex-1 relative w-full overflow-hidden flex flex-col bg-app-bg';
  app.appendChild(contentArea);

  navigate('image');

  window.addEventListener('navigate', (e) => {
    if (e.detail.page === 'settings') {
      import('./components/SettingsModal.js').then(({ SettingsModal }) => {
        document.body.appendChild(SettingsModal());
      });
    } else {
      navigate(e.detail.page);
    }
  });
}

// Auth gate
if (localStorage.getItem('codgen_token')) {
  boot();
} else {
  AuthModal(boot);
}

// Handle session expiry from anywhere in the app
window.addEventListener('unhandledrejection', (e) => {
  if (e.reason?.message === 'SESSION_EXPIRED') {
    localStorage.removeItem('codgen_token');
    localStorage.removeItem('codgen_refresh');
    localStorage.removeItem('codgen_email');
    document.body.innerHTML = '';
    AuthModal(boot);
  }
});

