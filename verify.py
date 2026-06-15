with open('d:/abc/abc/frontend/restaurant-dashboard.html', encoding='utf-8') as f:
    html = f.read()

checks = [
    ('No main.css link',      'href="css/main.css"' not in html),
    ('Local FA',              'css/fa/all.min.css' in html),
    ('No auth-guard',         'auth-guard.js' not in html),
    ('Session script',        '_TM_FALLBACK' in html),
    ('modal-wrap used',       'modal-wrap' in html),
    ('No old modal-overlay',  'class="modal-overlay"' not in html),
    ('openModal sets display','el.style.display' in html),
    ('saveCategory fn',       'function saveCategory' in html),
    ('saveItem fn',           'function saveItem' in html),
    ('openAddCatModal fn',    'function openAddCatModal' in html),
    ('No async',              'async function' not in html),
    ('Escape key closes modal','Escape' in html),
]
for label, result in checks:
    print('OK  ' + label if result else 'FAIL ' + label)

print()
print('File size:', len(html), 'bytes,', html.count('\n'), 'lines')
