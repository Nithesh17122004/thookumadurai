"""
debug_overlay.py
Injects a floating debug panel into the dashboard that shows:
1. localStorage status
2. Whether openModal/addCategory are defined
3. A direct "Test Add Category" button that bypasses onclick
"""
src = 'd:/abc/abc/frontend/restaurant-dashboard.html'

with open(src, encoding='utf-8') as f:
    html = f.read()

debug_panel = '''
<!-- DEBUG OVERLAY — remove after fixing -->
<div id="__debug" style="position:fixed;bottom:20px;right:20px;z-index:99999;background:#0a2a10;border:2px solid #4caf50;border-radius:12px;padding:16px;font-family:monospace;font-size:12px;color:#81c784;width:300px;max-height:400px;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,0.8)">
  <div style="font-weight:bold;margin-bottom:8px;color:#4caf50">DEBUG PANEL</div>
  <div id="__dbLS"></div>
  <div id="__dbFns"></div>
  <div style="margin-top:10px;display:flex;flex-direction:column;gap:6px">
    <button onclick="__dbTest()" style="background:#1b6b3a;color:#fff;border:none;padding:6px;border-radius:6px;cursor:pointer;font-size:11px">Direct: openModal(addCatModal)</button>
    <button onclick="__dbAddCat()" style="background:#1b6b3a;color:#fff;border:none;padding:6px;border-radius:6px;cursor:pointer;font-size:11px">Direct: addCategory() with test data</button>
    <button onclick="showPage('menu')" style="background:#1b6b3a;color:#fff;border:none;padding:6px;border-radius:6px;cursor:pointer;font-size:11px">Go to Menu page</button>
    <button onclick="document.getElementById('__debug').remove()" style="background:#333;color:#aaa;border:none;padding:6px;border-radius:6px;cursor:pointer;font-size:11px">Close Debug</button>
  </div>
  <div id="__dbLog" style="margin-top:8px;color:#ffc107;font-size:11px"></div>
</div>
<script>
function __dbLog(msg) {
  var el = document.getElementById('__dbLog');
  if (el) el.textContent = new Date().toLocaleTimeString() + ': ' + msg;
  console.log('[DEBUG]', msg);
}
function __dbTest() {
  __dbLog('Calling openModal...');
  if (typeof openModal !== 'function') { __dbLog('ERROR: openModal not a function!'); return; }
  openModal('addCatModal');
  __dbLog('openModal called OK');
}
function __dbAddCat() {
  __dbLog('Forcing addCategory...');
  var ni = document.getElementById('newCatName');
  var ei = document.getElementById('editCatId');
  if (!ni) { __dbLog('ERROR: newCatName not found!'); return; }
  ni.value = 'Test Category';
  if (ei) ei.value = '';
  if (typeof addCategory !== 'function') { __dbLog('ERROR: addCategory not a function!'); return; }
  addCategory();
  __dbLog('addCategory called');
}
document.addEventListener('DOMContentLoaded', function() {
  // Check localStorage
  var lsEl = document.getElementById('__dbLS');
  try {
    localStorage.setItem('__t','1'); localStorage.removeItem('__t');
    if (lsEl) lsEl.innerHTML = 'localStorage: <span style="color:#4caf50">WORKING</span>';
  } catch(e) {
    if (lsEl) lsEl.innerHTML = 'localStorage: <span style="color:#ef5350">BLOCKED: '+e.message+'</span>';
  }
  // Check functions
  var fns = ['openModal','closeModal','addCategory','saveItem','menuSave','showPage'];
  var missing = fns.filter(function(f){ return typeof window[f] !== 'function'; });
  var fnEl = document.getElementById('__dbFns');
  if (fnEl) {
    if (missing.length) {
      fnEl.innerHTML = 'Missing fns: <span style="color:#ef5350">'+missing.join(', ')+'</span>';
    } else {
      fnEl.innerHTML = 'All fns: <span style="color:#4caf50">OK</span>';
    }
  }
  // Auto go to menu
  if (typeof showPage === 'function') showPage('menu');
  __dbLog('Debug ready');
});
</script>
'''

# Insert debug panel right before </body>
html = html.replace('</body>', debug_panel + '\n</body>', 1)

with open(src, 'w', encoding='utf-8') as f:
    f.write(html)

print('Debug overlay injected. Lines:', html.count('\n'))
