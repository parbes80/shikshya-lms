function getCSRFToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

function csrfFetch(url, options = {}) {
  const headers = options.headers || {};
  if (options.method && !['GET', 'HEAD'].includes(options.method.toUpperCase())) {
    headers['X-CSRFToken'] = getCSRFToken();
  }
  return fetch(url, { ...options, headers });
}

document.addEventListener('DOMContentLoaded', () => {
  const themeToggle = document.getElementById('theme-toggle');
  const activeTheme = localStorage.getItem('theme') || 'light';

  document.documentElement.setAttribute('data-theme', activeTheme);
  updateThemeIcon(activeTheme);

  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const currentTheme = document.documentElement.getAttribute('data-theme');
      const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

      document.documentElement.setAttribute('data-theme', newTheme);
      localStorage.setItem('theme', newTheme);
      updateThemeIcon(newTheme);
    });
  }

  function updateThemeIcon(theme) {
    if (!themeToggle) return;
    const icon = themeToggle.querySelector('i');
    icon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
  }

  document.querySelectorAll('.close-alert').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const alert = e.target.closest('.alert');
      alert.style.transform = 'translateX(120%)';
      alert.style.opacity = '0';
      setTimeout(() => alert.remove(), 300);
    });
  });

  const notifBtn = document.getElementById('notif-dropdown-btn');
  const notifPanel = document.getElementById('notif-panel');

  if (notifBtn && notifPanel) {
    notifBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      notifPanel.classList.toggle('active');
    });

    document.addEventListener('click', (e) => {
      if (!notifPanel.contains(e.target) && e.target !== notifBtn) {
        notifPanel.classList.remove('active');
      }
    });
  }

  const notifBadge = document.getElementById('notif-badge');
  const notifList = document.getElementById('notif-list');

  if (notifBadge && notifList) {
    pollNotifications();
    setInterval(pollNotifications, 30000);
  }

  function pollNotifications() {
    fetch('/api/notifications')
      .then(res => res.json())
      .then(data => {
        if (data.length > 0) {
          notifBadge.style.display = 'flex';
          notifBadge.textContent = data.length;

          notifList.innerHTML = '';
          data.forEach(item => {
            const row = document.createElement('div');
            row.className = `notif-item type-${item.type}`;
            row.innerHTML = `
              <div class="notif-title">${item.title}</div>
              <div class="notif-msg">${item.message}</div>
              <small style="color: var(--text-muted); font-size: 0.7rem; display: block; margin-top: 0.25rem;">${item.created_at}</small>
            `;

            row.addEventListener('click', () => {
              markAsRead(item.id, row);
            });
            notifList.appendChild(row);
          });
        } else {
          notifBadge.style.display = 'none';
          notifList.innerHTML = '<div style="text-align: center; padding: 1.5rem; color: var(--text-muted); font-size: 0.85rem;">No new notifications.</div>';
        }
      })
      .catch(err => console.log('Error fetching notifications:', err));
  }

  function markAsRead(id, element) {
    csrfFetch(`/api/notifications/${id}/read`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        element.style.opacity = '0.5';
        pollNotifications();
      }
    });
  }
});
