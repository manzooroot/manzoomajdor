# TASLIMA BOTH Movement — Termux
Install in Termux:
```bash
pkg update && pkg upgrade -y
pkg install nodejs-lts unzip nano -y
termux-setup-storage
cd ~/storage/downloads
unzip taslima-both-termux.zip
cd taslima-both-termux
npm install
termux-wake-lock
npm start
```
Commands in Minecraft chat:
- `!come` — follow the player who sent the command
- `!follow PlayerName` — follow a visible player
- `!wander` — random nearby wandering
- `!stop` — stop following and wander
- `!stay` — stop and stay still
- `!status` — health, hunger, current mode
- `!help` — command list

Dashboard: http://127.0.0.1:3000

Defaults retained from previous setup: host `UmbralSMP.aternos.me`, port `12081`, username `TASLIMA`, auth `offline`. Verify current Java address and port in Aternos > Connect. Offline auth only works if the server permits offline/cracked accounts. If server address or port differs, edit CONFIG in index.js.

The bot wanders using pathfinding and follows visible players; it cannot teleport. It needs a walkable route and may fail around obstacles, water, cliffs, claims or protected areas. Auto-eat needs food already in inventory; defense needs a sword and sufficient health. This is not a full AI and cannot guarantee survival.

Termux cannot guarantee 24/7 uptime. Disable Android battery optimization for Termux, keep it running and keep the phone charged. Aternos may stop the server or enforce AFK/bot restrictions.
