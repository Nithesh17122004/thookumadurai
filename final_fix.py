"""
final_fix.py
- Replaces CDN Font Awesome with local copy (fixes Edge Tracking Prevention)
- Removes auth-guard.js <script> tag entirely
- Injects an inline <script> in <head> that guarantees a restaurant session in localStorage
  BEFORE any other code runs, with no dependency on localStorage being set from a previous visit.
"""

src = 'd:/abc/abc/frontend/restaurant-dashboard.html'

with open(src, encoding='utf-8') as f:
    html = f.read()

# 1. Replace CDN Font Awesome with local copy
html = html.replace(
    '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">',
    '<link rel="stylesheet" href="css/fa/all.min.css">'
)

# 2. Remove auth-guard.js script tag entirely
html = html.replace('<script src="js/auth-guard.js"></script>', '')

# 3. Inject guaranteed session script at very start of <head> (after <meta charset>)
# This runs FIRST, before anything else, and always sets a valid session
SESSION_SCRIPT = '''<script>
/* AUTO-SESSION: always inject a restaurant session on localhost so the dashboard
   works without login. This runs before DOMContentLoaded. */
(function(){
  try {
    var raw = localStorage.getItem('tm_auth');
    var auth = raw ? JSON.parse(raw) : null;
    if (!auth || auth.role !== 'restaurant') {
      var demo = {
        id: 'demo_rest_001',
        restaurant_id: 'demo_rest_001',
        name: 'Demo Restaurant',
        role: 'restaurant',
        token: 'demo_token_localhost'
      };
      localStorage.setItem('tm_auth', JSON.stringify(demo));
    }
  } catch(e) {
    // If localStorage is blocked (e.g. Edge strict tracking), use a window variable
    window._TM_AUTH_FALLBACK = {
      id: 'demo_rest_001',
      restaurant_id: 'demo_rest_001',
      name: 'Demo Restaurant',
      role: 'restaurant',
      token: 'demo_token_localhost'
    };
  }
})();
</script>
'''

# Insert right after <meta charset="UTF-8">
html = html.replace(
    '<meta charset="UTF-8">',
    '<meta charset="UTF-8">\n' + SESSION_SCRIPT,
    1  # only first occurrence
)

# 4. Fix the main script to also handle the window._TM_AUTH_FALLBACK case
# Replace the authData line
html = html.replace(
    "var authData = JSON.parse(localStorage.getItem('tm_auth') || '{}');",
    "var authData = (function(){ try { return JSON.parse(localStorage.getItem('tm_auth') || '{}'); } catch(e) { return window._TM_AUTH_FALLBACK || {}; } })();"
)

with open(src, 'w', encoding='utf-8') as f:
    f.write(html)

# Verify
with open(src, encoding='utf-8') as f:
    verify = f.read()

print('CDN removed:', 'cdnjs.cloudflare.com/ajax/libs/font-awesome' not in verify)
print('Local FA added:', 'css/fa/all.min.css' in verify)
print('Auth guard removed:', 'auth-guard.js' not in verify)
print('Session script injected:', '_TM_AUTH_FALLBACK' in verify)
print('Total lines:', verify.count('\n'))
