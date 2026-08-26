import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import express from 'express';
import QRCode from 'qrcode';
import pino from 'pino';
import makeWASocket, {
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} from '@whiskeysockets/baileys';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const AUTH_DIR = path.resolve(__dirname, '..', 'whatsapp_auth');

if (!fs.existsSync(AUTH_DIR)) {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
}

const app = express();
app.use(express.json());

let sock = null;
let connectionState = {
  status: 'STARTING',
  qr: null,
  user: null,
  lastUpdated: new Date().toISOString(),
};

const logger = pino({ level: 'silent' });

async function initWhatsApp() {
  try {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
      version,
      auth: state,
      printQRInTerminal: false,
      logger,
      browser: ['Imou Safety Monitor', 'Chrome', '1.0.0'],
      syncFullHistory: false,
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        try {
          const qrDataUrl = await QRCode.toDataURL(qr, { margin: 2, scale: 6 });
          connectionState = {
            status: 'QR_READY',
            qr: qrDataUrl,
            user: null,
            lastUpdated: new Date().toISOString(),
          };
          console.log('[WhatsApp] QR Barcode generated. Ready for scanning.');
        } catch (err) {
          console.error('[WhatsApp] Failed to generate QR DataURL:', err);
        }
      }

      if (connection === 'close') {
        const statusCode = lastDisconnect?.error?.output?.statusCode;
        const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
        console.log(`[WhatsApp] Connection closed (code: ${statusCode}). Reconnecting: ${shouldReconnect}`);

        connectionState = {
          status: 'DISCONNECTED',
          qr: null,
          user: null,
          lastUpdated: new Date().toISOString(),
        };

        if (shouldReconnect) {
          setTimeout(initWhatsApp, 3000);
        } else {
          // Logged out: remove auth files and re-init fresh QR
          fs.rmSync(AUTH_DIR, { recursive: true, force: true });
          fs.mkdirSync(AUTH_DIR, { recursive: true });
          setTimeout(initWhatsApp, 2000);
        }
      } else if (connection === 'open') {
        const userJid = sock.user?.id || '';
        const phone = userJid.split(':')[0] || userJid.split('@')[0];
        connectionState = {
          status: 'CONNECTED',
          qr: null,
          user: phone,
          lastUpdated: new Date().toISOString(),
        };
        console.log(`[WhatsApp] Successfully connected! Logged in as: ${phone}`);
      }
    });
  } catch (err) {
    console.error('[WhatsApp] Init error:', err);
    connectionState.status = 'ERROR';
    setTimeout(initWhatsApp, 5000);
  }
}

function formatJid(target) {
  if (!target) return null;
  let clean = target.toString().trim().replace(/[\s\-\+]/g, '');
  if (clean.endsWith('@s.whatsapp.net') || clean.endsWith('@g.us')) {
    return clean;
  }
  if (clean.startsWith('08')) {
    clean = '628' + clean.slice(2);
  } else if (clean.startsWith('8')) {
    clean = '628' + clean.slice(1);
  }
  return clean + '@s.whatsapp.net';
}

app.get('/status', (req, res) => {
  res.json(connectionState);
});

app.get('/groups', async (req, res) => {
  try {
    if (!sock || connectionState.status !== 'CONNECTED') {
      return res.json({ ok: true, groups: [] });
    }
    const groupData = await sock.groupFetchAllParticipating();
    const list = Object.values(groupData).map((g) => ({
      id: g.id,
      name: g.subject,
      participants: g.participants?.length || 0,
    }));
    res.json({ ok: true, groups: list });
  } catch (err) {
    console.error('[WhatsApp] Fetch groups error:', err);
    res.json({ ok: false, error: err.message, groups: [] });
  }
});

app.post('/send', async (req, res) => {
  try {
    const { to, message, image_path } = req.body;
    if (!to || !message) {
      return res.status(400).json({ ok: false, error: 'Parameter "to" and "message" are required.' });
    }

    if (connectionState.status !== 'CONNECTED' || !sock) {
      return res.status(503).json({ ok: false, error: 'WhatsApp is not connected. Scan QR code first.' });
    }

    const jid = formatJid(to);
    if (!jid) {
      return res.status(400).json({ ok: false, error: 'Invalid destination phone number.' });
    }

    let sentMsg = null;
    if (image_path && fs.existsSync(image_path)) {
      const buffer = fs.readFileSync(image_path);
      sentMsg = await sock.sendMessage(jid, {
        image: buffer,
        caption: message,
      });
    } else {
      sentMsg = await sock.sendMessage(jid, {
        text: message,
      });
    }

    res.json({ ok: true, messageId: sentMsg?.key?.id, to: jid });
  } catch (err) {
    console.error('[WhatsApp] Send error:', err);
    res.status(500).json({ ok: false, error: err.message });
  }
});

app.post('/logout', async (req, res) => {
  try {
    if (sock) {
      try {
        await sock.logout();
      } catch (e) {}
    }
    fs.rmSync(AUTH_DIR, { recursive: true, force: true });
    fs.mkdirSync(AUTH_DIR, { recursive: true });
    connectionState = {
      status: 'STARTING',
      qr: null,
      user: null,
      lastUpdated: new Date().toISOString(),
    };
    setTimeout(initWhatsApp, 1000);
    res.json({ ok: true, message: 'Logged out successfully. Generating new QR code.' });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, '127.0.0.1', () => {
  console.log(`WhatsApp Bridge running on http://127.0.0.1:${PORT}`);
  initWhatsApp();
});
