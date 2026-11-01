const express = require('express');
const mineflayer = require('mineflayer');

// ---------- ১. সেটিংস ----------
const CONFIG = {
  host: 'UmbralSMP.aternos.me',
  port: 12081,
  username: 'Majdoor24_7',
  version: false,
  auth: 'offline'
};

const MOVE_INTERVAL = 5 * 1000;   // বট প্রতি ৫ সেকেন্ড পর পর মুভ করবে
const RECONNECT_MIN = 10 * 1000;
const RECONNECT_MAX = 120 * 1000;

// ---------- ২. Web Server ----------
const app = express();
const status = { online: false, since: null, lastReason: null, reconnects: 0 };

app.get('/', (req, res) => {
  res.send(
    `AFK Bot: ${status.online ? '🟢 Online' : '🔴 Offline'}\n` +
    `Reconnects: ${status.reconnects}\n` +
    `Last disconnect: ${status.lastReason || 'none'}`
  );
});
app.get('/status', (req, res) => res.json(status));

app.listen(process.env.PORT || 3000, () => {
  console.log('Web Server চালু হয়েছে');
});

// ---------- ৩. Bot লজিক ----------
let bot = null;
let activityTimer = null;
let reconnectTimer = null;
let reconnectDelay = RECONNECT_MIN;

const rand = (min, max) => Math.random() * (max - min) + min;

function stopActivity() {
  if (activityTimer) clearTimeout(activityTimer);
  activityTimer = null;
}

function startActivity() {
  stopActivity();

  const actions = ['jump', 'forward', 'back', 'left', 'right', 'look', 'sneak'];

  const loop = () => {
    if (!bot || !bot.entity) return;

    const action = actions[Math.floor(Math.random() * actions.length)];

    try {
      if (action === 'look') {
        bot.look(rand(-Math.PI, Math.PI), rand(-0.5, 0.5), false);
      } else {
        bot.setControlState(action, true);
        setTimeout(() => {
          if (bot) bot.setControlState(action, false);
        }, rand(300, 1200));
      }
    } catch (e) {}

    activityTimer = setTimeout(loop, MOVE_INTERVAL);
  };

  activityTimer = setTimeout(loop, MOVE_INTERVAL);
}

function scheduleReconnect(reason) {
  status.online = false;
  status.lastReason = String(reason);
  stopActivity();

  if (reconnectTimer) return;

  console.log(`❌ ডিসকানেক্ট হয়েছে (${reason}). ${Math.round(reconnectDelay / 1000)} সেকেন্ড পর আবার চেষ্টা করবে...`);

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    status.reconnects++;
    createBot();
  }, reconnectDelay);

  reconnectDelay = Math.min(reconnectDelay * 1.5, RECONNECT_MAX);
}

function createBot() {
  console.log(`🔌 ${CONFIG.host}:${CONFIG.port} এ কানেক্ট হচ্ছে...`);

  bot = mineflayer.createBot(CONFIG);

  bot.once('spawn', () => {
    console.log('✅ বট সফলভাবে সার্ভারে ঢুকেছে!');
    status.online = true;
    status.since = new Date().toISOString();
    reconnectDelay = RECONNECT_MIN;
    startActivity();
  });

  bot.on('death', () => console.log('💀 বট মারা গেছে, অটো রেসপন হবে...'));

  bot.on('kicked', (reason) => {
    console.log('⚠️ বটকে কিক করা হয়েছে:', typeof reason === 'string' ? reason : JSON.stringify(reason));
  });

  bot.on('error', (err) => {
    console.log('Bot Error:', err.message);
  });

  bot.on('end', (reason) => {
    scheduleReconnect(reason);
  });
}

process.on('uncaughtException', (err) => console.log('Uncaught:', err.message));
process.on('unhandledRejection', (err) => console.log('Unhandled:', err && err.message));

createBot();
