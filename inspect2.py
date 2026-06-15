with open('d:/abc/abc/frontend/restaurant-dashboard.html', encoding='utf-8') as f:
    lines = f.readlines()

# Find modal CSS
print('=== MODAL CSS ===')
in_modal_css = False
for i,l in enumerate(lines, 1):
    if '.modal-overlay' in l or '.modal-' in l or 'modal-overlay' in l:
        print(i, l.rstrip()[:120])

print()
print('=== FIRST 20 LINES ===')
for i,l in enumerate(lines[:20], 1):
    print(i, l.rstrip()[:120])
