# TASLIMA BOTH Movement — Termux (Python version)

Mineflayer is a Node.js library, so this Python port drives it through the
`javascript` (JSPyBridge) package. Node.js must be installed; the npm packages
(`mineflayer`, `mineflayer-pathfinder`) are downloaded automatically on first run.

Install in Termux:
```bash
pkg update && pkg upgrade -y
pkg install python nodejs-lts unzip nano -y
termux-setup-storage
cd ~/storage/downloads
unzip taslima-both-termux.zip
cd taslima-both-termux
pip install -r requirements.txt
termux-wake-lock
python index.py
```

Docker:
```bash
docker build -t taslima-bot .
docker run --rm -p 3000:3000 taslima-bot
```

Commands in Minecraft chat:
- `!come` — follow the player who sent the command
- `!follow PlayerName` — follow a visible player
- `!wander` — random nearby wandering
- `!stop` — stop following and wander
- `!stay` — stop and stay still
- `!status` — health, hunger, current mode
- `!help` — command list

Dashboard: http://127.0.0.1:3000 (JSON at `/status`)

Settings via environment variables (or edit CONFIG in index.py): `MC_HOST`
(default `UmbralSMP.aternos.me`), `MC_PORT` (`12081`), `BOT_USERNAME` (`TASLIMA`),
`MC_AUTH` (`offline`), `MC_VERSION` (auto-detect), `PORT` (`3000`).
Verify the current Java address and port in Aternos > Connect. Offline auth only
works if the server permits offline/cracked accounts.

The bot wanders using pathfinding and follows visible players; it cannot teleport.
It needs a walkable route and may fail around obstacles, water, cliffs, claims or
protected areas. Auto-eat needs food already in inventory; defense needs a sword
and sufficient health. This is not a full AI and cannot guarantee survival.

Termux cannot guarantee 24/7 uptime. Disable Android battery optimization for
Termux, keep it running and keep the phone charged. Aternos may stop the server
or enforce AFK/bot restrictions.
