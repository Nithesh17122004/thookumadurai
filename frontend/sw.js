// Thooku Madurai — Service Worker for Web Push
const API_BASE = 'https://thookumadurai.onrender.com';
const API_BASE_SOCKET = 'https://thookumadurai.onrender.com';

function isCustomer() { return !self.location.pathname.startsWith('/rider-dashboard'); }

self.addEventListener('push', function (event) {
  if (!event.data) return;
  let data;
  try {
    data = event.data.json();
  } catch (e) { return; }
  if (!data.callId) return;
  const tag = 'thooku-call-' + data.callId;
  const key = 'thooku_pending_call_' + data.callId;
  event.waitUntil((async () => {
    const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    // If any matching client is already focused, tell it instead of showing notification
    for (const c of clients) {
      const url = c.url || '';
      if (isCustomer() && !url.includes('rider-dashboard')) {
        c.postMessage({ type: 'THOOKU_INCOMING_CALL', ...data });
        return;
      }
      if (!isCustomer() && url.includes('rider-dashboard')) {
        c.postMessage({ type: 'THOOKU_INCOMING_CALL', ...data });
        return;
      }
    }
    self.__thooku_pending = self.__thooku_pending || {};
    self.__thooku_pending[key] = data;
    self.registration.showNotification('Thooku Madurai', {
      body: data.callerName ? data.callerName + ' is calling...' : 'Incoming call...',
      icon: '/icon-192.png',
      badge: '/icon-72.png',
      tag: tag,
      data: data,
      requireInteraction: true,
      vibrate: [200, 100, 200, 100, 400],
      actions: [{ action: 'answer', title: 'Answer' }, { action: 'decline', title: 'Decline' }]
    });
  })());
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  const data = event.notification.data;
  if (!data || !data.callId) return;
  if (event.action === 'decline') {
    fetch(API_BASE + '/api/v1/push/call-declined', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ callId: data.callId, orderId: data.orderId })
    }).catch(() => {});
    return;
  }
  // answer — open/focus the right page
  const targetUrl = data.callerRole === 'rider' ? '/' : '/rider-dashboard';
  event.waitUntil((async () => {
    const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const c of clients) {
      const url = c.url || '';
      if (data.callerRole === 'rider' && !url.includes('rider-dashboard')) {
        c.focus();
        c.postMessage({ type: 'THOOKU_INCOMING_CALL', ...data });
        return;
      }
      if (data.callerRole !== 'rider' && url.includes('rider-dashboard')) {
        c.focus();
        c.postMessage({ type: 'THOOKU_INCOMING_CALL', ...data });
        return;
      }
    }
    const win = await self.clients.openWindow(targetUrl);
    // The opened page will call /api/v1/push/page-ready to get the SDP
  })());
});

self.addEventListener('message', function (event) {
  if (event.data && event.data.type === 'THOOKU_MARK_HANDLED') {
    const key = 'thooku_pending_call_' + event.data.callId;
    if (self.__thooku_pending) delete self.__thooku_pending[key];
  }
});
