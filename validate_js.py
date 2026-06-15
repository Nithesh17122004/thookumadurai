"""validate_js.py - extracts the inline <script> from the dashboard and runs it through
Node.js syntax check, then prints the first 60 lines so we can see what actually runs."""
import urllib.request, subprocess, os, sys

r = urllib.request.urlopen('http://127.0.0.1:5500/restaurant-dashboard.html', timeout=5)
html = r.read().decode('utf-8', errors='replace')

# Extract last <script> block
start = html.rfind('<script>')
end   = html.rfind('</script>')
script = html[start+8:end]

# Write to temp file
tmp = 'd:/abc/abc/check_script.js'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(script)

print('Script length:', len(script))
print('Has openModal:', 'function openModal' in script)
print('Has addCategory:', 'function addCategory' in script)
print('Has menuSave:', 'function menuSave' in script)
print('Has _TM_AUTH_FALLBACK:', '_TM_AUTH_FALLBACK' in script)
print('Has async:', 'async function' in script)
print()

# Check for common syntax issues
lines = script.split('\n')
print('=== First 30 lines of script ===')
for i, l in enumerate(lines[:30], 1):
    print(f'{i:3}: {l[:110]}')

print()
print('=== Lines near addCategory ===')
for i, l in enumerate(lines, 1):
    if 'function addCategory' in l or 'function openModal' in l:
        start_i = max(0, i-2)
        end_i   = min(len(lines), i+8)
        for j in range(start_i, end_i):
            print(f'{j+1:3}: {lines[j][:110]}')
        print()

# Try node syntax check
try:
    result = subprocess.run(['node', '--check', tmp], capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        print('NODE SYNTAX CHECK: PASSED')
    else:
        print('NODE SYNTAX CHECK: FAILED')
        print(result.stderr[:500])
except FileNotFoundError:
    print('node not installed, skipping syntax check')
except Exception as e:
    print('node check error:', e)
