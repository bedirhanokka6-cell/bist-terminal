/* Firebase Cloud Messaging service worker */
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: 'AIzaSyBEFi-qs6C3_yOIFu1j6_SNKE2lb-ggtXM',
  authDomain: 'borsa-analiz-c4611.firebaseapp.com',
  projectId: 'borsa-analiz-c4611',
  storageBucket: 'borsa-analiz-c4611.firebasestorage.app',
  messagingSenderId: '774790915785',
  appId: '1:774790915785:web:b5fbf17c9ea1ae7fe18f18',
  measurementId: 'G-YPTN8WC9D7'
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const title = payload?.notification?.title || 'BIST Terminal';
  const options = {
    body: payload?.notification?.body || 'Yeni bildirim',
    icon: '/favicon.ico'
  };
  self.registration.showNotification(title, options);
});
