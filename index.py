#!/usr/bin/env python3
# TASLIMA Mineflayer bot - Python version
# Mineflayer ek Node.js library, tai Python theke "javascript" (JSPyBridge) package diye chalano hoy.
# Node.js install thaka lagbe (Termux: pkg install nodejs-lts).

import html
import json
import math
import os
import random
import re
import signal
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from javascript import On, Once, globalThis, require

mineflayer = require("mineflayer", "^4.23.0")
_pf = require("mineflayer-pathfinder", "^2.4.5")
pathfinder, Movements, goals = _pf.pathfinder, _pf.Movements, _pf.goals

CONFIG = {
    "host": os.getenv("MC_HOST", "UmbralSMP.aternos.me"),
    "port": int(os.getenv("MC_PORT", "12081")),
    "username": os.getenv("BOT_USERNAME", "TASLIMA"),
    "auth": os.getenv("MC_AUTH", "offline"),
}
if os.getenv("MC_VERSION"):  # na dile auto-detect hobe
    CONFIG["version"] = os.environ["MC_VERSION"]

DASHBOARD_PORT = int(os.getenv("PORT", "3000"))
FOOD_LEVEL, FOLLOW_DISTANCE, WANDER_RADIUS = 16, 2, 5
WANDER_INTERVAL = 3.0  # proti 3 second-e notun jaygay move korbe
DEFEND_RADIUS, DEFEND_MIN_HEALTH = 5, 10
RECONNECT_MIN, RECONNECT_MAX = 10.0, 120.0
STUCK_MOVE_MIN = 0.25  # 1 second-e eta kom norle "atke gese"
STUCK_TICKS = 3        # koyta tick atke thakle sidestep korbe

HOSTILE = {
    "zombie", "husk", "drowned", "skeleton", "stray", "bogged", "creeper", "spider",
    "cave_spider", "witch", "pillager", "vindicator", "evoker", "ravager", "phantom",
    "slime", "magma_cube", "blaze", "ghast", "piglin_brute", "hoglin", "zoglin",
    "warden", "silverfish", "endermite",
}
FOOD_RE = re.compile(
    r"bread|cooked_|golden_apple|apple|carrot|potato|beetroot|melon|sweet_berries|"
    r"glow_berries|cookie|pumpkin_pie|mushroom_stew|rabbit_stew|beetroot_soup|honey_bottle"
)
SWORD_RANK = {"netherite": 6, "diamond": 5, "iron": 4, "stone": 3, "golden": 2, "wooden": 1}

status = {
    "online": False, "username": CONFIG["username"],
    "server": f"{CONFIG['host']}:{CONFIG['port']}", "since": None, "lastReason": None,
    "reconnects": 0, "mode": "offline", "health": None, "food": None,
    "lastAction": "Starting", "unstuckCount": 0,
}


# ---------------- Dashboard ----------------
def render_dashboard():
    e = lambda v: html.escape(str(v))
    d = lambda v: "-" if v is None else v
    return (
        "<h2>TASLIMA Bot</h2>"
        f"<p>Status: <b>{'ONLINE' if status['online'] else 'OFFLINE'}</b></p>"
        f"<p>Mode: {e(status['mode'])}</p><p>Health: {e(d(status['health']))}</p>"
        f"<p>Food: {e(d(status['food']))}</p><p>Reconnects: {status['reconnects']}</p>"
        f"<p>Unstuck: {status['unstuckCount']}</p><p>Last action: {e(status['lastAction'])}</p>"
        f"<p>Last disconnect: {e(status['lastReason'] or 'none')}</p>"
    )


class Dashboard(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/status":
            body, ctype = json.dumps(status).encode(), "application/json"
        else:
            body, ctype = render_dashboard().encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


# ---------------- Helpers ----------------
def ent_pos(e):
    p = e.position
    return (float(p.x), float(p.y), float(p.z))


def is_hostile(e):
    return e is not None and e.type == "mob" and bool(e.name) and str(e.name).lower() in HOSTILE


class TaslimaBot:
    def __init__(self):
        self.bot = None
        self.reconnect_timer = None
        self.reconnect_delay = RECONNECT_MIN
        self.stopping = threading.Event()
        self.loop_stop = None
        self.action_busy = False
        self.follow_target = None
        self.wander_goal_active = False
        self.unsticking = False
        self.last_pos = None
        self.stuck_ticks = 0
        self.no_path_count = 0

    # ---- basic utils ----
    def log_action(self, s):
        status["lastAction"] = s
        print(s, flush=True)

    def clear_loops(self):
        if self.loop_stop:
            self.loop_stop.set()
        self.loop_stop = None

    def stop_path(self):
        try:
            self.bot.pathfinder.setGoal(None)
        except Exception:
            pass

    def player_entity(self, name):
        try:
            p = self.bot.players[name]
            return None if p is None else p.entity
        except Exception:
            return None

    def wander_mode(self):
        self.follow_target = None
        self.wander_goal_active = False
        status["mode"] = "wandering"
        self.stop_path()
        self.log_action("Wander mode enabled")

    # ---- movement ----
    def start_wandering(self):
        b = self.bot
        if b is None or b.entity is None or self.follow_target or self.unsticking or status["mode"] == "staying":
            return
        radius = 4 if self.no_path_count >= 2 else WANDER_RADIUS  # beshi bar atkle choto radius
        p = b.entity.position
        x = math.floor(p.x + (random.random() * 2 - 1) * radius)
        z = math.floor(p.z + (random.random() * 2 - 1) * radius)
        try:
            b.pathfinder.setGoal(goals.GoalNearXZ(x, z, 1))
            self.wander_goal_active = True
            status["mode"] = "wandering"
            self.log_action(f"Wandering toward {x}, {z}")
        except Exception as e:
            self.log_action(f"Wander error: {e}")

    def unstick(self, reason):
        # Atke gele bame/dane sore jabe, lafabe, tarpor abar notun path nibe. Kono block bhangbe na.
        b = self.bot
        if self.unsticking or b is None or b.entity is None or status["mode"] == "staying":
            return
        self.unsticking = True
        self.stuck_ticks = 0
        status["unstuckCount"] += 1
        side = random.choice(["left", "right"])
        self.log_action(f"Stuck ({reason}); sidestep {side}")
        try:
            self.stop_path()
            b.clearControlStates()
            turn = random.choice([1, -1]) * (math.pi / 3 + random.random() * math.pi / 3)
            b.look(b.entity.yaw + turn, 0, True)
            b.setControlState(side, True)
            b.setControlState("jump", True)
            time.sleep(0.6)
            b.clearControlStates()
            if random.random() < 0.5:
                b.setControlState("back", True)
                time.sleep(0.4)
                b.clearControlStates()
            b.setControlState("forward", True)
            b.setControlState("jump", True)
            time.sleep(1.2)
        except Exception as e:
            print("Unstick error:", e, flush=True)
        finally:
            try:
                b.clearControlStates()
            except Exception:
                pass
            self.unsticking = False
            self.last_pos = None
            if self.follow_target:
                self.follow_player(self.follow_target, False)
            elif status["mode"] == "wandering":
                self.start_wandering()

    def check_stuck(self):
        b = self.bot
        if b is None or b.entity is None or self.unsticking or self.action_busy:
            return
        pos = ent_pos(b.entity)
        wants_move = False
        if self.follow_target:
            pe = self.player_entity(self.follow_target)
            wants_move = pe is not None and math.dist(pos, ent_pos(pe)) > FOLLOW_DISTANCE + 2
        elif status["mode"] == "wandering":
            wants_move = self.wander_goal_active
        if not wants_move:
            self.stuck_ticks = 0
            self.last_pos = pos
            return
        if self.last_pos and math.dist(pos, self.last_pos) < STUCK_MOVE_MIN:
            self.stuck_ticks += 1
        else:
            self.stuck_ticks = 0
            self.no_path_count = 0
        self.last_pos = pos
        if self.stuck_ticks >= STUCK_TICKS:
            self.unstick("not moving")

    def follow_player(self, name, reply=True):
        b = self.bot
        pe = self.player_entity(name)
        if pe is None:
            if reply:
                b.chat(f"I cannot see {name} nearby. Come closer and try again.")
            return False
        self.follow_target = name
        self.wander_goal_active = False
        status["mode"] = f"following {name}"
        b.pathfinder.setGoal(goals.GoalFollow(pe, FOLLOW_DISTANCE), True)
        if reply:
            b.chat(f"Following {name}.")
        self.log_action(f"Following {name}")
        return True

    # ---- survival ----
    def eat_if_hungry(self):
        b = self.bot
        if b is None or b.entity is None or self.action_busy or self.unsticking or b.food is None or b.food > FOOD_LEVEL:
            return
        food = next((i for i in list(b.inventory.items()) if FOOD_RE.search(str(i.name))), None)
        if food is None:
            self.log_action("Hungry: no food in inventory")
            return
        self.action_busy = True
        try:
            b.equip(food, "hand")
            b.consume()
            self.log_action(f"Ate {food.name}")
        except Exception as e:
            self.log_action(f"Could not eat: {e}")
        finally:
            self.action_busy = False

    def defend_nearby(self):
        b = self.bot
        if b is None or b.entity is None or self.action_busy or self.unsticking or b.health is None or b.health < DEFEND_MIN_HEALTH:
            return
        me = ent_pos(b.entity)
        target, best = None, None
        for e in list(globalThis.Object.values(b.entities)):
            if not is_hostile(e) or e.position is None:
                continue
            d = math.dist(me, ent_pos(e))
            if d <= DEFEND_RADIUS and (best is None or d < best):
                target, best = e, d
        if target is None:
            return
        swords = [i for i in list(b.inventory.items()) if str(i.name).endswith("_sword")]
        if not swords:
            self.log_action(f"Hostile nearby ({target.name}); no sword in inventory")
            return
        sword = max(swords, key=lambda i: SWORD_RANK.get(str(i.name).split("_")[0], 0))
        self.action_busy = True
        try:
            b.equip(sword, "hand")
            b.attack(target)
            self.log_action(f"Defending against {target.name}")
        except Exception as e:
            self.log_action(f"Defense error: {e}")
        finally:
            self.action_busy = False

    # ---- chat commands ----
    def handle_chat(self, username, message):
        b = self.bot
        if b is None or username == b.username:
            return
        parts = str(message).strip().split()
        cmd = parts[0].lower() if parts else ""
        if cmd == "!help":
            b.chat("Commands: !come, !follow <player>, !wander, !stop, !stay, !status")
        elif cmd == "!come":
            self.follow_player(username)
        elif cmd == "!follow" and len(parts) > 1:
            self.follow_player(parts[1])
        elif cmd == "!wander":
            self.wander_mode()
            b.chat("I will wander around.")
            self.start_wandering()
        elif cmd == "!stop":
            self.wander_mode()
            b.chat("Stopped following; wandering nearby.")
            self.start_wandering()
        elif cmd == "!stay":
            self.follow_target = None
            status["mode"] = "staying"
            self.wander_goal_active = False
            self.stop_path()
            b.chat("I will stay here.")
            self.log_action("Stay mode")
        elif cmd == "!status":
            b.chat(f"Health {int(round(b.health or 0))}, food {b.food or 0}, mode {status['mode']}")

    # ---- background loop (food / defense / wander / stuck) ----
    def brain(self, stop_evt):
        now = time.time()
        last = {"food": 0.0, "defense": 0.0, "wander": now - WANDER_INTERVAL + 1.2, "stuck": 0.0}
        while not stop_evt.is_set():
            now = time.time()
            try:
                if now - last["food"] >= 4:
                    last["food"] = now
                    status["health"], status["food"] = self.bot.health, self.bot.food
                    self.eat_if_hungry()
                if now - last["defense"] >= 1.5:
                    last["defense"] = now
                    self.defend_nearby()
                    self.refresh_follow()
                if now - last["wander"] >= WANDER_INTERVAL:
                    last["wander"] = now
                    if not self.unsticking and not self.follow_target and status["mode"] == "wandering":
                        self.start_wandering()
                if now - last["stuck"] >= 1:
                    last["stuck"] = now
                    self.check_stuck()
            except Exception as e:
                print("Loop error:", e, flush=True)
            stop_evt.wait(0.25)

    def refresh_follow(self):
        if self.unsticking or not self.follow_target:
            return
        pe = self.player_entity(self.follow_target)
        if pe is not None:
            self.bot.pathfinder.setGoal(goals.GoalFollow(pe, FOLLOW_DISTANCE), True)
        else:
            lost = self.follow_target
            self.wander_mode()
            self.bot.chat(f"Lost sight of {lost}; wandering again.")

    # ---- connection ----
    def schedule_reconnect(self, reason):
        status["online"] = False
        status["lastReason"] = str(reason or "Connection ended")
        status["mode"] = "offline"
        self.clear_loops()
        if self.stopping.is_set() or self.reconnect_timer:
            return
        print(f"Disconnected: {status['lastReason']}. Retry in {round(self.reconnect_delay)}s", flush=True)

        def retry():
            self.reconnect_timer = None
            status["reconnects"] += 1
            self.create_bot()

        self.reconnect_timer = threading.Timer(self.reconnect_delay, retry)
        self.reconnect_timer.daemon = True
        self.reconnect_timer.start()
        self.reconnect_delay = min(round(self.reconnect_delay * 1.5), RECONNECT_MAX)

    def on_spawn(self):
        b = self.bot
        status["online"] = True
        status["since"] = datetime.now(timezone.utc).isoformat()
        self.reconnect_delay = RECONNECT_MIN
        m = Movements(b)
        m.canDig = False            # kono block bhangbe na
        m.allow1by1towers = False   # block boshiye uthbe na
        m.allowParkour = False
        m.allowSprinting = False
        m.scafoldingBlocks = []     # block place korbe na (pathfinder-er nijer spelling)
        b.pathfinder.setMovements(m)
        b.pathfinder.thinkTimeout = 3000  # path khujte beshi somoy nibe na
        status["mode"] = "wandering"
        self.log_action("Joined server; random movement starting")
        self.clear_loops()
        self.loop_stop = threading.Event()
        threading.Thread(target=self.brain, args=(self.loop_stop,), daemon=True).start()

    def create_bot(self):
        if self.stopping.is_set():
            return
        print(f"Connecting to {CONFIG['host']}:{CONFIG['port']} as {CONFIG['username']}...", flush=True)
        self.unsticking = False
        self.last_pos = None
        self.stuck_ticks = 0
        self.no_path_count = 0
        try:
            b = mineflayer.createBot(CONFIG)
            b.loadPlugin(pathfinder)
        except Exception as e:
            self.schedule_reconnect(str(e))
            return
        self.bot = b
        me = self

        @Once(b, "spawn")
        def _spawn(this, *a):
            me.on_spawn()

        @On(b, "goal_reached")
        def _goal(this, *a):
            me.wander_goal_active = False
            me.no_path_count = 0

        @On(b, "path_update")
        def _path(this, r, *a):
            try:
                st = str(r.status)
            except Exception:
                return
            if st in ("noPath", "timeout"):
                me.no_path_count += 1
                me.wander_goal_active = False
                if not me.follow_target and status["mode"] == "wandering":
                    threading.Timer(0.3, lambda: me.unstick("no path")).start()

        @On(b, "health")
        def _health(this, *a):
            status["health"], status["food"] = b.health, b.food

        @On(b, "death")
        def _death(this, *a):
            me.log_action("Died; attempting respawn")

            def respawn():
                try:
                    if b.entity is not None and b.health <= 0:
                        b.respawn()
                except Exception as e:
                    print(e, flush=True)

            threading.Timer(1.5, respawn).start()

        @On(b, "chat")
        def _chat(this, username, message, *a):
            try:
                me.handle_chat(username, message)
            except Exception as e:
                print("Chat error:", e, flush=True)

        @On(b, "kicked")
        def _kicked(this, reason, *a):
            status["lastReason"] = f"Kicked: {reason}"
            print(status["lastReason"], flush=True)

        @On(b, "error")
        def _error(this, err, *a):
            print("Bot error:", err, flush=True)

        @On(b, "end")
        def _end(this, *a):
            me.schedule_reconnect(a[0] if a else None)

    def shutdown(self):
        self.clear_loops()
        if self.reconnect_timer:
            self.reconnect_timer.cancel()
        try:
            if self.bot is not None:
                self.bot.quit("Stopped from Termux")
        except Exception:
            pass
        print("Bot stopped.", flush=True)
        time.sleep(0.7)


def main():
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", DASHBOARD_PORT), Dashboard)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"Dashboard: http://127.0.0.1:{DASHBOARD_PORT}", flush=True)
    except OSError as e:
        print(f"Dashboard start hoyni ({e}); bot cholbe.", flush=True)

    app = TaslimaBot()
    signal.signal(signal.SIGINT, lambda *_: app.stopping.set())
    signal.signal(signal.SIGTERM, lambda *_: app.stopping.set())
    app.create_bot()
    while not app.stopping.is_set():
        app.stopping.wait(0.5)
    app.shutdown()


if __name__ == "__main__":
    main()
