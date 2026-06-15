/**
 * THOOKU MADURAI — Auth Guard
 * Include this script in all protected pages.
 * Checks localStorage for valid session and redirects to login if missing.
 */
(function authGuard() {
  const PAGE_ROLES = {
    'index.html': ['customer'],
    'restaurant-dashboard.html': ['restaurant'],
    'rider-dashboard.html': ['rider'],
    'admin-panel.html': ['admin', 'superadmin'],
    'super-admin.html': ['superadmin'],
  };

  const page = window.location.pathname.split('/').pop() || 'index.html';
  const allowedRoles = PAGE_ROLES[page];

  // Pages that don't need auth guard
  if (!allowedRoles) return;

  const raw = localStorage.getItem('tm_auth');
  if (!raw) {
    const isDevMode = ['127.0.0.1', 'localhost', ''].includes(window.location.hostname);
    if (page === 'login.html') return; // already on login

    // ── Dev-mode auto-session ──────────────────────────────────
    // On localhost, inject a demo restaurant session so developers
    // can use the dashboard CRUD without needing a real login.
    if (isDevMode && page === 'restaurant-dashboard.html') {
      const demoAuth = {
        id: 'demo_rest_001',
        restaurant_id: 'demo_rest_001',
        name: 'Demo Restaurant',
        role: 'restaurant',
        token: 'demo_token_localhost'
      };
      localStorage.setItem('tm_auth', JSON.stringify(demoAuth));
      window.TM_USER = demoAuth;
      console.warn('[AuthGuard] Dev mode: injected demo restaurant session');
      return; // allow page to load
    }
    // ──────────────────────────────────────────────────────────

    redirectToLogin();
    return;
  }

  let auth;
  try { auth = JSON.parse(raw); } catch { redirectToLogin(); return; }

  // Check role
  if (!allowedRoles.includes(auth.role)) {
    // Wrong role — redirect them to correct dashboard
    const REDIRECT = {
      customer: 'index.html',
      restaurant: 'restaurant-dashboard.html',
      rider: 'rider-dashboard.html',
      admin: 'admin-panel.html',
      superadmin: 'super-admin.html',
    };
    const correct = REDIRECT[auth.role];
    if (correct && correct !== page) {
      window.location.href = correct;
    } else {
      redirectToLogin();
    }
    return;
  }

  // Inject user info into page
  window.TM_USER = auth;

  // Inject floating avatar + logout button into any .navbar element
  document.addEventListener('DOMContentLoaded', () => {
    injectUserNavbar(auth);
  });

  function injectUserNavbar(auth) {
    const navbarRight = document.querySelector('.navbar-right') ||
                        document.querySelector('.rider-header > div:last-child') ||
                        document.querySelector('.admin-topbar > div:last-child');

    if (!navbarRight) return;

    // Create user chip
    const chip = document.createElement('div');
    chip.style.cssText = 'display:flex;align-items:center;gap:8px;cursor:pointer;padding:6px 12px;background:rgba(76,175,80,0.08);border:1px solid rgba(76,175,80,0.2);border-radius:40px;transition:all 0.2s;';
    chip.innerHTML = `
      <img src="${auth.picture || `https://ui-avatars.com/api/?name=${encodeURIComponent(auth.name||'U')}&background=1b6b3a&color=4caf50&bold=true`}"
           style="width:28px;height:28px;border-radius:50%;border:2px solid rgba(76,175,80,0.4)"
           onerror="this.src='https://ui-avatars.com/api/?name=U&background=1b6b3a&color=4caf50'">
      <span style="font-size:13px;font-weight:600;color:#81c784;max-width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${(auth.name||'User').split(' ')[0]}</span>
      <i class="fas fa-chevron-down" style="font-size:10px;color:#4a7c59"></i>
    `;

    // Dropdown menu
    const dropdown = document.createElement('div');
    dropdown.style.cssText = 'position:absolute;top:56px;right:16px;background:#0f2016;border:1px solid rgba(76,175,80,0.2);border-radius:12px;padding:8px;min-width:180px;z-index:9999;display:none;box-shadow:0 12px 32px rgba(0,0,0,0.5);';
    dropdown.innerHTML = `
      <div style="padding:10px 12px;border-bottom:1px solid rgba(76,175,80,0.1);margin-bottom:4px">
        <div style="font-weight:700;font-size:13px">${auth.name || auth.email || 'User'}</div>
        <div style="font-size:11px;color:#4a7c59;margin-top:2px">${auth.role.toUpperCase()} · ${auth.loginMethod === 'google' ? '🔵 Google' : '📱 OTP'}</div>
      </div>
      <a href="login.html" style="display:flex;align-items:center;gap:8px;padding:9px 12px;color:#81c784;text-decoration:none;font-size:13px;border-radius:8px;transition:0.2s" 
         onmouseover="this.style.background='rgba(76,175,80,0.08)'" onmouseout="this.style.background=''"
         onclick="localStorage.removeItem('tm_auth');localStorage.removeItem('tm_role')">
        <i class="fas fa-sign-out-alt" style="width:14px;color:#4a7c59"></i> Logout
      </a>
    `;

    chip.onclick = (e) => {
      e.stopPropagation();
      dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
    };
    document.addEventListener('click', () => dropdown.style.display = 'none');

    const wrapper = document.createElement('div');
    wrapper.style.position = 'relative';
    wrapper.appendChild(chip);
    wrapper.appendChild(dropdown);
    navbarRight.appendChild(wrapper);
  }

  function redirectToLogin() {
    window.location.href = 'login.html';
  }
})();
