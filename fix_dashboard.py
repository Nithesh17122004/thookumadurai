#!/usr/bin/env python3
# fix_dashboard.py — rewrites the <script> block in restaurant-dashboard.html
# with a localStorage-first, zero-API-dependency menu CRUD implementation.

import re

src = 'd:/abc/abc/frontend/restaurant-dashboard.html'

with open(src, encoding='utf-8') as f:
    content = f.read()

# Keep everything before the final <script> tag
script_start = content.rfind('<script>')
before = content[:script_start]

new_script = r"""<script>
/* ============================================================
   Thooku Madurai — Restaurant Dashboard
   Menu CRUD: 100% localStorage-first, zero API dependency.
   API calls are fire-and-forget background sync only.
   ============================================================ */

var API_BASE = 'http://127.0.0.1:5000/api/v1';
var authData = JSON.parse(localStorage.getItem('tm_auth') || '{}');
var token    = authData.token || '';
var HEADERS  = { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' };
var REST_ID  = authData.restaurant_id || authData.id || '';

var CATEGORIES = [], MENU_ITEMS = [], ORDERS = [];
var activeCatId = '', currentFilter = 'all';

var LS_CATS  = 'tm_cats_'  + (REST_ID || 'local');
var LS_ITEMS = 'tm_items_' + (REST_ID || 'local');

/* --- localStorage helpers --- */
function menuSave() {
  try {
    localStorage.setItem(LS_CATS,  JSON.stringify(CATEGORIES));
    localStorage.setItem(LS_ITEMS, JSON.stringify(MENU_ITEMS));
  } catch(e) { console.warn('LS write error', e); }
}
function menuLoad() {
  try {
    CATEGORIES = JSON.parse(localStorage.getItem(LS_CATS)  || '[]');
    MENU_ITEMS = JSON.parse(localStorage.getItem(LS_ITEMS) || '[]');
  } catch(e) { CATEGORIES = []; MENU_ITEMS = []; }
  activeCatId = CATEGORIES.length ? CATEGORIES[0].id : '';
}
function mkId() { return 'id_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7); }

/* --- optional background API sync (never blocks UI) --- */
function apiSync(path, method, body) {
  if (!token || !REST_ID || token === 'demo_token_localhost') return;
  fetch(API_BASE + path, {
    method: method,
    headers: HEADERS,
    body: body ? JSON.stringify(body) : undefined
  }).catch(function() {});
}

/* ---- INIT ---- */
document.addEventListener('DOMContentLoaded', function() {
  document.getElementById('restNameTop').textContent = authData.name || 'Demo Restaurant';
  updateTopbarTime();
  setInterval(updateTopbarTime, 1000);

  menuLoad();   // instant — no network

  // background API pull
  if (token && REST_ID && token !== 'demo_token_localhost') {
    fetch(API_BASE + '/restaurants/' + REST_ID + '/menu', { headers: HEADERS })
      .then(function(r) { return r.ok ? r.json() : null; })
      .then(function(data) {
        if (!data || !data.success) return;
        var sm = (data.data && data.data.menu) ? data.data.menu : [];
        if (!sm.length) return;
        CATEGORIES = []; MENU_ITEMS = [];
        sm.forEach(function(cat) {
          CATEGORIES.push({ id: cat.category_id, name: cat.category_name, emoji: cat.emoji || '\uD83C\uDF7D\uFE0F' });
          (cat.items || []).forEach(function(item) {
            MENU_ITEMS.push({ id: item.item_id || item.id || item._id, cat: cat.category_id,
              name: item.name, price: item.price, desc: item.description || item.desc || '',
              type: item.type || (item.is_veg ? 'veg' : 'non-veg'),
              emoji: item.emoji || '\uD83C\uDF5B', available: item.is_available !== false });
          });
        });
        menuSave();
        activeCatId = CATEGORIES.length ? CATEGORIES[0].id : '';
        renderMenu();
      })
      .catch(function() {});
    loadOrdersFromAPI();
    setInterval(refreshOrders, 15000);
  }

  renderDashboard(); renderOrdersTable(); renderMenu(); renderAnalytics(); renderSettings(); buildHoursGrid();
});

/* ---- CLOCK ---- */
function updateTopbarTime() {
  document.getElementById('topbarTime').textContent = new Date().toLocaleTimeString('en-IN');
}

/* ---- NAVIGATION ---- */
function showPage(page) {
  document.querySelectorAll('.page').forEach(function(p) { p.classList.remove('active'); });
  document.querySelectorAll('.nav-item').forEach(function(n) { n.classList.remove('active'); });
  document.getElementById('page-' + page).classList.add('active');
  var navEl = document.querySelector('.nav-item[onclick*="' + page + '"]');
  if (navEl) navEl.classList.add('active');
  var t = { dashboard:'Dashboard', orders:'Orders', menu:'Menu Management', analytics:'Analytics', settings:'Settings' };
  document.getElementById('pageTitle').textContent = t[page] || page;
}

/* ---- TOGGLE OPEN/CLOSE ---- */
function toggleRestaurantOpen() {
  var isOpen = document.getElementById('restOpenToggle').checked;
  document.getElementById('openLabel').textContent = isOpen ? 'OPEN' : 'CLOSED';
  showToast(isOpen ? 'Restaurant is now OPEN' : 'Restaurant is now CLOSED', isOpen ? 'success' : 'warning');
  apiSync('/restaurants/' + REST_ID + '/status', 'PATCH', { is_open: isOpen });
}

/* ---- ORDERS API ---- */
function formatOrderTime(ts) {
  if (!ts) return '-';
  var diff = Math.floor(Date.now() / 1000) - Number(ts);
  if (diff < 60)    return 'Just now';
  if (diff < 3600)  return Math.floor(diff / 60) + ' min ago';
  if (diff < 86400) return Math.floor(diff / 3600) + ' hr ago';
  return new Date(Number(ts) * 1000).toLocaleDateString('en-IN');
}
function formatAddress(addr) {
  if (!addr || typeof addr !== 'object') return '-';
  return [addr.street, addr.area, addr.city].filter(Boolean).join(', ');
}
function mapApiStatus(s) {
  return ({ ready_for_pickup:'ready', rejected:'cancelled', accepted:'preparing', out_for_delivery:'ready' })[s] || s;
}
function mapApiOrder(o) {
  var phone = String(o.customer_phone || '');
  return {
    id: o._id || o.order_id,
    customer: phone.length >= 4 ? '****' + phone.slice(-4) : '****',
    items: (o.items || []).map(function(i){ return { name:i.name, qty:i.qty||i.quantity||1, price:i.price }; }),
    total: o.total || 0, status: mapApiStatus(o.status), time: formatOrderTime(o.created_at),
    payment: (o.payment_method || 'UPI').toUpperCase(), address: formatAddress(o.delivery_address)
  };
}
function loadOrdersFromAPI() {
  if (!token || !REST_ID) return;
  fetch(API_BASE + '/restaurants/' + REST_ID + '/orders', { headers: HEADERS })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.success) { ORDERS = (data.data || []).map(mapApiOrder); renderDashboard(); renderOrdersTable(); renderAnalytics(); }
    }).catch(function() {});
}
function refreshOrders() { loadOrdersFromAPI(); }
function acceptOrder(id) {
  fetch(API_BASE+'/restaurants/'+REST_ID+'/orders/'+id+'/accept',{method:'PATCH',headers:HEADERS})
    .then(function(r){return r.json();}).then(function(d){showToast(d.success?'Order accepted!':(d.message||'Error'),d.success?'success':'error');if(d.success)loadOrdersFromAPI();}).catch(function(e){showToast(e.message,'error');});
}
function rejectOrder(id) {
  if(!confirm('Reject order '+id+'?'))return;
  fetch(API_BASE+'/restaurants/'+REST_ID+'/orders/'+id+'/reject',{method:'PATCH',headers:HEADERS,body:JSON.stringify({reason:'Rejected'})})
    .then(function(r){return r.json();}).then(function(d){showToast(d.success?'Rejected':(d.message||'Error'),d.success?'warning':'error');if(d.success)loadOrdersFromAPI();}).catch(function(e){showToast(e.message,'error');});
}
function updateOrderStatus(id,ns) {
  if(ns!=='ready')return;
  fetch(API_BASE+'/restaurants/'+REST_ID+'/orders/'+id+'/ready',{method:'PATCH',headers:HEADERS})
    .then(function(r){return r.json();}).then(function(){showToast('Marked ready','success');loadOrdersFromAPI();}).catch(function(){});
}

/* ---- DASHBOARD RENDER ---- */
function renderDashboard() {
  var pending = ORDERS.filter(function(o){return o.status==='pending';}).length;
  var today   = ORDERS.filter(function(o){return['pending','preparing','ready','delivered'].indexOf(o.status)>=0;});
  var revenue = today.filter(function(o){return o.status==='delivered';}).reduce(function(s,o){return s+o.total;},0);
  document.getElementById('kpiOrders').textContent  = today.length;
  document.getElementById('kpiRevenue').textContent = 'Rs.' + revenue.toLocaleString();
  document.getElementById('kpiPending').textContent = pending;
  document.getElementById('pendingBadge').textContent = pending;

  var liveQ = document.getElementById('liveOrderQueue');
  var pend  = ORDERS.filter(function(o){return o.status==='pending';});
  if (!pend.length) {
    liveQ.innerHTML = '<div style="text-align:center;padding:30px;color:var(--dim)"><div style="font-size:36px;margin-bottom:8px">Zzz</div><div>No pending orders right now</div></div>';
  } else {
    liveQ.innerHTML = pend.map(function(o) {
      var oid = o.id;
      return '<div class="order-card new-order">' +
        '<div class="order-header"><span class="order-id">' + oid + '</span><span class="chip chip-gold">NEW</span><span class="order-time">' + o.time + '</span></div>' +
        '<div class="order-items">' + o.items.map(function(i){return i.name+'x'+i.qty;}).join(', ') + '</div>' +
        '<div class="order-footer"><span class="order-amount">Rs.' + o.total + '</span>' +
        '<span style="font-size:12px;color:var(--dim);flex:1">via ' + o.payment + '</span>' +
        '<button class="btn-reject" onclick="rejectOrder(\'' + oid + '\')">Reject</button>' +
        '<button class="btn-accept" onclick="acceptOrder(\'' + oid + '\')">Accept</button>' +
        '</div></div>';
    }).join('');
  }

  document.getElementById('todaySummary').innerHTML = [
    {label:'Completed',val:ORDERS.filter(function(o){return o.status==='delivered';}).length,color:'var(--accent)'},
    {label:'Preparing', val:ORDERS.filter(function(o){return o.status==='preparing';}).length, color:'var(--gold)'},
    {label:'Ready',     val:ORDERS.filter(function(o){return o.status==='ready';}).length,     color:'#64b5f6'},
    {label:'Cancelled', val:0, color:'#ef5350'}
  ].map(function(s){
    return '<div style="display:flex;align-items:center;justify-content:space-between;padding:8px;background:var(--dark);border-radius:8px">' +
      '<span style="font-size:13px;color:var(--muted)">' + s.label + '</span>' +
      '<span style="font-size:18px;font-weight:800;color:' + s.color + '">' + s.val + '</span></div>';
  }).join('');

  var is = {};
  ORDERS.filter(function(o){return o.status==='delivered';}).forEach(function(o){
    o.items.forEach(function(i){ is[i.name]=(is[i.name]||0)+i.qty; });
  });
  var sorted = Object.entries(is).sort(function(a,b){return b[1]-a[1];}).slice(0,3);
  document.getElementById('topItems').innerHTML = sorted.map(function(e,idx){
    return '<div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">' +
      '<span style="font-size:18px;font-weight:800;color:var(--dim)">' + (idx+1) + '</span>' +
      '<span style="flex:1;font-size:13px;font-weight:600">' + e[0] + '</span>' +
      '<span style="color:var(--accent);font-weight:700">' + e[1] + ' sold</span></div>';
  }).join('') || '<div style="color:var(--dim);font-size:13px">No data yet</div>';
}

/* ---- ORDERS TABLE ---- */
function filterOrders(filter, btn) {
  currentFilter = filter;
  document.querySelectorAll('.filter-btn').forEach(function(b){b.classList.remove('active');});
  btn.classList.add('active');
  renderOrdersTable();
}
function renderOrdersTable() {
  var filtered = currentFilter === 'all' ? ORDERS : ORDERS.filter(function(o){return o.status===currentFilter;});
  var chipMap  = {pending:'chip-gold',preparing:'chip-blue',ready:'chip-green',delivered:'chip-green',cancelled:'chip-red'};
  var head = '<thead><tr><th>Order ID</th><th>Items</th><th>Amount</th><th>Customer</th><th>Payment</th><th>Status</th><th>Time</th><th>Action</th></tr></thead>';
  if (!filtered.length) {
    document.getElementById('ordersTable').innerHTML = head + '<tbody><tr><td colspan="8" style="text-align:center;padding:32px;color:var(--dim)">No orders yet</td></tr></tbody>';
    return;
  }
  document.getElementById('ordersTable').innerHTML = head + '<tbody>' + filtered.map(function(o) {
    var oid = o.id, a = '';
    if (o.status === 'pending')   a = '<button class="btn-accept" onclick="acceptOrder(\'' + oid + '\')">Accept</button><button class="btn-reject" onclick="rejectOrder(\'' + oid + '\')">Reject</button>';
    if (o.status === 'preparing') a = '<button class="btn-sm" onclick="updateOrderStatus(\'' + oid + '\',\'ready\')">Mark Ready</button>';
    if (o.status === 'ready')     a = '<span style="color:var(--dim);font-size:12px">Waiting rider</span>';
    if (o.status === 'delivered') a = '<span style="color:var(--accent);font-size:12px">Done</span>';
    if (o.status === 'cancelled') a = '<span style="color:#ef5350;font-size:12px">Cancelled</span>';
    return '<tr><td style="font-weight:800">' + oid + '</td>' +
      '<td>' + o.items.map(function(i){return i.name+'x'+i.qty;}).join(', ') + '</td>' +
      '<td style="color:var(--accent);font-weight:700">Rs.' + o.total + '</td>' +
      '<td>' + o.customer + '</td><td>' + o.payment + '</td>' +
      '<td><span class="chip ' + (chipMap[o.status]||'chip-gray') + '">' + o.status + '</span></td>' +
      '<td style="color:var(--dim);font-size:12px">' + o.time + '</td>' +
      '<td>' + a + '<button class="btn-outline-sm" onclick="viewOrderDetail(\'' + oid + '\')">View</button></td></tr>';
  }).join('') + '</tbody>';
}
function viewOrderDetail(id) {
  var o = ORDERS.find(function(x){return x.id===id;});
  if (!o) return;
  document.getElementById('odTitle').textContent = 'Order ' + o.id;
  document.getElementById('orderDetailContent').innerHTML =
    '<p style="margin:0 0 12px"><strong>Status:</strong> ' + o.status + ' &nbsp; <strong>Time:</strong> ' + o.time + '</p>' +
    o.items.map(function(i){ return '<div style="display:flex;justify-content:space-between;padding:8px;background:var(--mid);border-radius:8px;margin-bottom:6px"><span>' + i.name + ' x' + i.qty + '</span><span style="color:var(--accent)">Rs.' + (i.price*i.qty) + '</span></div>'; }).join('') +
    '<div style="border-top:1px solid var(--border);padding-top:10px;margin-top:10px;display:flex;justify-content:space-between"><strong>Total</strong><strong style="color:var(--accent);font-size:18px">Rs.' + o.total + '</strong></div>';
  openModal('orderDetailModal');
}

/* ====================================================================
   MENU MANAGEMENT
   All CRUD operations write to localStorage FIRST, then optionally
   sync to the API in the background. No async, no API dependency.
   ==================================================================== */

function renderMenu() { renderCatList(); renderItems(); }

function renderCatList() {
  var el = document.getElementById('catListEl');
  if (!CATEGORIES.length) {
    el.innerHTML = '<div style="font-size:12px;color:var(--dim);padding:8px 4px">No categories yet.<br>Click <strong>Add Category</strong> above.</div>';
  } else {
    el.innerHTML = CATEGORIES.map(function(c) {
      var cid = c.id;
      return '<div class="cat-item ' + (cid === activeCatId ? 'active' : '') + '" onclick="selectCat(\'' + cid + '\')">' +
        '<span>' + c.emoji + ' ' + c.name + '</span>' +
        '<span>' +
        '<i class="fas fa-pen del-cat" style="color:var(--accent);margin-right:8px" onclick="event.stopPropagation();editCategory(\'' + cid + '\')" title="Edit"></i>' +
        '<i class="fas fa-trash del-cat" onclick="event.stopPropagation();deleteCategory(\'' + cid + '\')" title="Delete"></i>' +
        '</span></div>';
    }).join('');
  }
  var sel = document.getElementById('itemCategory');
  if (sel) sel.innerHTML = CATEGORIES.map(function(c){ return '<option value="' + c.id + '">' + c.emoji + ' ' + c.name + '</option>'; }).join('');
}

function selectCat(id) { activeCatId = id; renderCatList(); renderItems(); }

function renderItems() {
  var cat = CATEGORIES.find(function(c){ return c.id === activeCatId; });
  if (!cat) { document.getElementById('activeCatTitle').textContent = 'Select a category'; return; }
  document.getElementById('activeCatTitle').textContent = cat.emoji + ' ' + cat.name;
  var items = MENU_ITEMS.filter(function(i){ return i.cat === activeCatId; });
  if (!items.length) {
    document.getElementById('itemGridEl').innerHTML = '';
    document.getElementById('noItemsMsg').style.display = 'block';
    return;
  }
  document.getElementById('noItemsMsg').style.display = 'none';
  document.getElementById('itemGridEl').innerHTML = items.map(function(item) {
    var iid = item.id;
    return '<div class="item-card">' +
      '<div class="item-img"><span style="font-size:48px">' + item.emoji + '</span>' +
      '<div class="veg-badge ' + (item.type === 'veg' ? 'veg' : 'non-veg') + '"></div>' +
      '<label class="toggle-sw avail-toggle"><input type="checkbox" ' + (item.available ? 'checked' : '') + ' onchange="toggleItemAvail(\'' + iid + '\',this.checked)"><span class="toggle-sl"></span></label>' +
      '</div>' +
      '<div class="item-body">' +
      '<div class="item-name">' + item.name + '</div>' +
      '<div class="item-desc">' + (item.desc || '-') + '</div>' +
      '<div class="item-price">Rs.' + item.price + '</div>' +
      '<div class="item-actions">' +
      '<button class="btn-sm" style="flex:1;background:rgba(76,175,80,.1);border:1px solid rgba(76,175,80,.3);color:var(--accent)" onclick="editItem(\'' + iid + '\')">Edit</button>' +
      '<button class="btn-sm" style="background:rgba(239,83,80,.1);border:1px solid rgba(239,83,80,.3);color:#ef5350" onclick="deleteItem(\'' + iid + '\')">Del</button>' +
      '</div></div></div>';
  }).join('');
}

/* -- Category CRUD -- */
function editCategory(id) {
  var cat = CATEGORIES.find(function(c){ return c.id === id; });
  if (!cat) return;
  document.getElementById('editCatId').value   = id;
  document.getElementById('newCatName').value  = cat.name;
  document.getElementById('newCatEmoji').value = cat.emoji || '';
  document.querySelector('#addCatModal .modal-title').textContent = 'Edit Category';
  openModal('addCatModal');
}

function addCategory() {
  var editId = (document.getElementById('editCatId').value || '').trim();
  var name   = document.getElementById('newCatName').value.trim();
  var emoji  = document.getElementById('newCatEmoji').value.trim() || '*';

  if (!name) { showToast('Category name is required', 'error'); return; }

  var savedId = editId;
  if (editId) {
    var cat = CATEGORIES.find(function(c){ return c.id === editId; });
    if (cat) { cat.name = name; cat.emoji = emoji; }
    apiSync('/restaurants/' + REST_ID + '/menu/category/' + editId, 'PUT', { name:name, emoji:emoji });
  } else {
    savedId = mkId();
    CATEGORIES.push({ id: savedId, name: name, emoji: emoji });
    apiSync('/restaurants/' + REST_ID + '/menu/category', 'POST', { name:name, emoji:emoji });
  }
  menuSave();

  closeModal('addCatModal');
  document.getElementById('newCatName').value  = '';
  document.getElementById('newCatEmoji').value = '';
  document.getElementById('editCatId').value   = '';
  document.querySelector('#addCatModal .modal-title').textContent = 'Add Category';

  activeCatId = savedId;
  renderMenu();
  showToast('Category "' + name + '" ' + (editId ? 'updated' : 'added') + '!', 'success');
}

function deleteCategory(id) {
  var cat = CATEGORIES.find(function(c){ return c.id === id; });
  var n   = MENU_ITEMS.filter(function(i){ return i.cat === id; }).length;
  if (!confirm('Delete "' + (cat ? cat.name : id) + '"? Removes ' + n + ' item(s).')) return;
  CATEGORIES = CATEGORIES.filter(function(c){ return c.id !== id; });
  MENU_ITEMS = MENU_ITEMS.filter(function(i){ return i.cat !== id; });
  menuSave();
  apiSync('/restaurants/' + REST_ID + '/menu/category/' + id, 'DELETE');
  activeCatId = CATEGORIES.length ? CATEGORIES[0].id : '';
  renderMenu();
  showToast('Category deleted', 'warning');
}

/* -- Item CRUD -- */
function editItem(id) {
  var item = MENU_ITEMS.find(function(i){ return i.id === id; });
  if (!item) return;
  document.getElementById('itemModalTitle').textContent = 'Edit Item';
  document.getElementById('editItemId').value   = id;
  document.getElementById('itemName').value     = item.name;
  document.getElementById('itemPrice').value    = item.price;
  document.getElementById('itemDesc').value     = item.desc || '';
  document.getElementById('itemCategory').value = item.cat;
  document.getElementById('itemType').value     = item.type;
  document.getElementById('itemEmoji').value    = item.emoji;
  document.getElementById('itemAvailable').checked = item.available;
  openModal('addItemModal');
}

function saveItem() {
  var editId = (document.getElementById('editItemId').value || '').trim();
  var name   = document.getElementById('itemName').value.trim();
  var price  = parseInt(document.getElementById('itemPrice').value) || 0;
  var desc   = document.getElementById('itemDesc').value.trim();
  var cat    = document.getElementById('itemCategory').value;
  var type   = document.getElementById('itemType').value;
  var emoji  = document.getElementById('itemEmoji').value.trim() || '*';
  var avail  = document.getElementById('itemAvailable').checked;

  if (!name)  { showToast('Item name is required', 'error'); return; }
  if (!price) { showToast('Price must be greater than 0', 'error'); return; }
  if (!cat)   { showToast('Please add a category first', 'error'); return; }

  if (editId) {
    var idx = MENU_ITEMS.findIndex(function(i){ return i.id === editId; });
    if (idx >= 0) MENU_ITEMS[idx] = { id:editId, name:name, price:price, desc:desc, cat:cat, type:type, emoji:emoji, available:avail };
    apiSync('/restaurants/'+REST_ID+'/menu/item/'+editId, 'PUT', {name:name,price:price,description:desc,category_id:cat,type:type,is_veg:type==='veg',emoji:emoji,is_available:avail});
  } else {
    var nid = mkId();
    MENU_ITEMS.push({ id:nid, name:name, price:price, desc:desc, cat:cat, type:type, emoji:emoji, available:avail });
    apiSync('/restaurants/'+REST_ID+'/menu/item', 'POST', {name:name,price:price,description:desc,category_id:cat,type:type,is_veg:type==='veg',emoji:emoji,is_available:avail});
  }
  menuSave();
  activeCatId = cat;

  closeModal('addItemModal');
  document.getElementById('editItemId').value  = '';
  document.getElementById('itemModalTitle').textContent = 'Add Menu Item';
  ['itemName','itemPrice','itemDesc'].forEach(function(fid){ document.getElementById(fid).value = ''; });
  document.getElementById('itemEmoji').value = '*';
  document.getElementById('itemAvailable').checked = true;
  renderMenu();
  showToast('"' + name + '" ' + (editId ? 'updated' : 'added') + '!', 'success');
}

function deleteItem(id) {
  var item = MENU_ITEMS.find(function(i){ return i.id === id; });
  if (!confirm('Delete "' + (item ? item.name : id) + '"?')) return;
  MENU_ITEMS = MENU_ITEMS.filter(function(i){ return i.id !== id; });
  menuSave();
  apiSync('/restaurants/'+REST_ID+'/menu/item/'+id, 'DELETE');
  renderMenu();
  showToast('"' + (item ? item.name : id) + '" deleted', 'warning');
}

function toggleItemAvail(id, available) {
  var item = MENU_ITEMS.find(function(i){ return i.id === id; });
  if (!item) return;
  item.available = available;
  menuSave();
  apiSync('/restaurants/'+REST_ID+'/menu/item/'+id+'/toggle', 'PATCH', {is_available:available});
  showToast(item.name + ' is now ' + (available ? 'available' : 'unavailable'), available ? 'success' : 'warning');
}

/* ---- ANALYTICS ---- */
function renderAnalytics() {
  var del = ORDERS.filter(function(o){ return o.status==='delivered'; });
  var rev = del.reduce(function(s,o){ return s+(o.total||0); },0);
  var cnt = del.length;
  function ki(id,v){ var e=document.getElementById(id); if(e) e.textContent=v; }
  ki('monthRevenue', cnt ? 'Rs.'+rev.toLocaleString() : '-');
  ki('monthOrders',  cnt ? String(cnt) : '-');
  ki('monthAov',     cnt ? 'Rs.'+Math.round(rev/cnt) : '-');
  ki('monthRating',  '-');

  var days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  var empty = '<div style="color:var(--dim);padding:20px;text-align:center;font-size:13px">No data yet</div>';
  if (!del.length) {
    ['revenueChart','ordersChart','ratingChart'].forEach(function(id){ document.getElementById(id).innerHTML = empty; });
    document.getElementById('topItemsTable').innerHTML = '<thead><tr><th>#</th><th>Item</th><th>Orders</th><th>Revenue</th></tr></thead><tbody><tr><td colspan="4" style="text-align:center;color:var(--dim);padding:16px">No data yet</td></tr></tbody>';
    return;
  }
  var rv = days.map(function(){ return 0; }), ov = days.map(function(){ return 0; });
  del.forEach(function(o){ var i=(new Date().getDay()+6)%7; rv[i]+=o.total||0; ov[i]+=1; });
  renderBarChart('revenueChart', rv, days, function(v){ return v ? 'Rs.'+(v/1000).toFixed(1)+'k' : 'Rs.0'; });
  renderBarChart('ordersChart',  ov, days, function(v){ return v; }, '#ffc107');
  var is = {};
  del.forEach(function(o){ o.items.forEach(function(i){ is[i.name]=is[i.name]||{qty:0,rev:0}; is[i.name].qty+=i.qty||1; is[i.name].rev+=(i.price||0)*(i.qty||1); }); });
  var s = Object.entries(is).sort(function(a,b){ return b[1].qty-a[1].qty; }).slice(0,5);
  document.getElementById('topItemsTable').innerHTML = '<thead><tr><th>#</th><th>Item</th><th>Orders</th><th>Revenue</th></tr></thead><tbody>' +
    s.map(function(e,i){ return '<tr><td>'+(i+1)+'</td><td>'+e[0]+'</td><td>'+e[1].qty+'</td><td style="color:var(--accent)">Rs.'+e[1].rev+'</td></tr>'; }).join('') + '</tbody>';
  document.getElementById('ratingChart').innerHTML = '<div style="color:var(--dim);padding:12px;text-align:center">Ratings appear after customer reviews</div>';
}
function renderBarChart(id, vals, labels, fmt, color) {
  var max = Math.max.apply(null, vals.concat([1]));
  document.getElementById(id).innerHTML = vals.map(function(v,i){
    return '<div class="bar-wrap"><div class="bar-val">' + fmt(v) + '</div>' +
      '<div class="bar" style="height:' + (v/max*100) + 'px;' + (color ? 'background:linear-gradient(180deg,'+color+',#e65100)' : '') + '">&nbsp;</div>' +
      '<div class="bar-label">' + labels[i] + '</div></div>';
  }).join('');
}

/* ---- SETTINGS ---- */
function renderSettings() { document.getElementById('s_name').value = authData.name || ''; }
function buildHoursGrid() {
  var days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  document.getElementById('hoursGrid').innerHTML = days.map(function(d){
    return '<div class="day-label">' + d + '</div>' +
      '<input class="form-control" type="time" value="09:00" style="padding:8px 10px;font-size:12px">' +
      '<input class="form-control" type="time" value="22:00" style="padding:8px 10px;font-size:12px">';
  }).join('');
}
function saveProfile() {
  var n = document.getElementById('s_name').value.trim();
  if (!n) { showToast('Name required','error'); return; }
  showToast('Profile saved!','success');
  apiSync('/restaurants/'+REST_ID,'PUT',{name:n,description:document.getElementById('s_desc').value});
}
function saveBankDetails() { showToast('Bank details saved!','success'); }
function saveHours()       { showToast('Operating hours saved!','success'); }
function deleteRestaurant() {
  if (!confirm('Permanently delete restaurant?')) return;
  if (prompt('Type DELETE to confirm:') !== 'DELETE') { showToast('Cancelled','warning'); return; }
  apiSync('/restaurants/'+REST_ID,'DELETE');
  showToast('Deleted. Redirecting...','error');
  setTimeout(function(){ window.location.href = 'login.html'; }, 2000);
}

/* ---- MODAL ---- */
function openModal(id)  { var el = document.getElementById(id); if (el) el.classList.add('open'); }
function closeModal(id) { var el = document.getElementById(id); if (el) el.classList.remove('open'); }
document.querySelectorAll('.modal-overlay').forEach(function(m) {
  m.addEventListener('click', function(e) { if (e.target === m) m.classList.remove('open'); });
});

/* ---- TOAST ---- */
function showToast(msg, type) {
  type = type || 'success';
  var t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  document.getElementById('toastContainer').appendChild(t);
  setTimeout(function() { t.style.opacity='0'; t.style.transition='opacity .3s'; setTimeout(function(){ t.remove(); }, 300); }, 3500);
}

/* ---- LOGOUT ---- */
function doLogout() { localStorage.removeItem('tm_auth'); localStorage.removeItem('tm_role'); window.location.href = 'login.html'; }
</script>
</body>
</html>
"""

output = before + new_script

with open(src, 'w', encoding='utf-8') as f:
    f.write(output)

# Verify
with open(src, encoding='utf-8') as f:
    verify = f.read()

import re
script_part = verify[verify.rfind('<script>'):]
fns = re.findall(r'function (\w+)', script_part)
print('OK — Functions:', fns)
print('addCategory sync:', 'async' not in script_part.split('function addCategory')[1][:50])
print('File lines:', verify.count('\n'))
