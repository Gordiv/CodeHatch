"""What the game's ⚙️ Manager panel does, seen from the bot.

Since DiscordCodes file 40 the Manager makes codes, events, eggs, gifts, announcements and bans BY ITSELF, also when
the bot is off (scripts/DiscordCodes/Control.luau), and writes each change to its log in the game's DataStore
(DiscordLiveContent -> "PanelLog", the newest 100). The bot reads that log every few seconds: each change is written to
the log channel set in /setup (also the ones made while the bot was off), and the codes, events and eggs it made are
copied into the bot's database right away (utils/game_sync.py), so Discord lists them and can change them. The number
of the last change read is kept in the game too ("PanelLogRead"), so a bot that lost its own file never writes a
change twice.

Older DiscordCodes files send REQUESTS instead, and the bot does them exactly like from Discord (the same functions,
so the same checks). How they travel (the game can't call the bot, which runs on the owner's PC):
- the game writes the request into its DataStore (DiscordLiveContent -> "ManagerRequests"), only after its server
  checked that the player is the game's owner;
- the bot reads that entry every few seconds (more often for 10 minutes after a request), does each new request once,
  writes the results to "ManagerResults" and tells the game servers through MessagingService, so the panel shows the
  answer at once; every request is also written to the log channel set in /setup.
"Done" is kept in ManagerResults too, so a bot that lost its own file (or moved to another PC) never does a request
twice. A request older than REQUEST_MAX_AGE (the bot was off), or one that waited before this bot ever answered the
game, is answered "send it again" and never done later by surprise. Run ONE bot per game: two would both do it.
"""
import json
import logging
import re
import time

import discord
from discord.ext import commands, tasks

from cogs.game_codes import CODE_VALIDITY, ITEM_DURATIONS, MAX_AMOUNT, NONE, CodeError, code_params, is_live
from utils import action_log, cloud_sync, config_store, database, game_sync, open_cloud, roblox_api
from utils.i18n import t

log = logging.getLogger("game_requests")

REQUESTS_KEY = "ManagerRequests"  # must match Manager.luau of older DiscordCodes files
RESULTS_KEY = "ManagerResults"
STATE_FILE = "manager_requests_state.json"
PANEL_LOG_KEY = "PanelLog"  # must match Control.luau
PANEL_READ_KEY = "PanelLogRead"
PANEL_STATE_FILE = "panel_log_state.json"
FIRST_READ_POSTS = 10  # a bot reading a game's log for the first time writes only the newest changes
# what a change made in the game means for the bot's database
SYNC_KINDS = {"code_add": "codes", "code_remove": "codes", "event_start": "events", "event_stop": "events",
              "egg_create": "eggs", "egg_move": "eggs", "egg_remove": "eggs"}
FAST_SECONDS, SLOW_SECONDS = 3, 12  # how often the entry is read: right after a request, and when nothing happens
FAST_FOR = 600  # seconds of fast reading after the last request
REQUEST_MAX_AGE = 600
MAX_RESULTS = 30
MAX_TEXT = 280  # the answer shown in the panel (a MessagingService message has at most 1 kB)
BAN_DURATIONS = {"1h": 3600, "24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400, "permanent": 0}
ANNOUNCE_SECONDS = (5, 10, 15, 30, 60)


def _live():
    # live_game and roblox_admin are loaded by the bot after this module: importing them at the top would make a
    # second copy of each (discord.py loads every extension again), so they are taken when a request runs
    from cogs import live_game
    return live_game


def _admin():
    from cogs import roblox_admin
    return roblox_admin


class RequestError(Exception):
    pass


class GameUser:
    """The author of a request in the shape the shared functions take (they were written for Discord users)."""

    def __init__(self, name: str, user_id: int):
        self.id = 0  # no Discord account: what the game's owner created is saved like an automatic action
        self.display_name = t("grequest.author", name=name)
        self.mention = self.display_name
        self.roblox_id = user_id

    def __str__(self):
        return self.display_name


def plain(text: str) -> str:
    """Discord formatting turned into plain text for the game: no **bold** or `code`, times as dates in UTC."""
    text = re.sub(r"<t:(\d+)(?::\w)?>", lambda m: time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(int(m.group(1)))), text)
    text = re.sub(r"<[@#][!&]?\d+>", "", text)
    return text.replace("**", "").replace("`", "").replace("__", "").strip()


def embed_text(embed) -> str:
    parts = [embed.title or "", embed.description or ""]
    parts += [f"{field.name}: {field.value}" for field in embed.fields]
    return plain("\n".join(p for p in parts if p))


def _text(data: dict, key: str, limit: int, required: bool = False) -> str:
    """A text from the form; longer than the same field on Discord (or missing when required) is refused, never cut."""
    value = data.get(key)
    value = value.strip() if isinstance(value, str) else ""
    if len(value) > limit or (required and not value):
        raise RequestError(t("grequest.bad"))
    return value


def _number(data: dict, key: str, low: int = 0, high: int = MAX_AMOUNT) -> int:
    value = data.get(key)
    if value in (None, ""):
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or not low <= value <= high:
        raise RequestError(t("grequest.bad"))
    return int(value)


def _choice(data: dict, key: str, choices, default):
    value = data.get(key) or default
    if value not in choices:
        raise RequestError(t("grequest.bad"))
    return value


def _reward(data: dict) -> dict:
    return _live().build_reward(_text(data, "currency", 100) or NONE, _number(data, "amount"), _number(data, "exp"),
                                _text(data, "item", 100) or NONE, _choice(data, "item_duration", ITEM_DURATIONS, "permanent"))


def _at(request: dict) -> float:
    at = request.get("at")
    return float(at) if isinstance(at, (int, float)) and not isinstance(at, bool) else 0.0


# ---------- The log of the game's ⚙️ Manager ----------

def _whole(value) -> int:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) < 2 ** 53
    return int(value) if ok else 0


def _shown(value, limit: int = 100) -> str:
    """A name typed in the game, safe to show on Discord (no formatting, no mentions)."""
    text = value.strip()[:limit] if isinstance(value, str) else ""
    return discord.utils.escape_mentions(discord.utils.escape_markdown(text)) or "?"


def _code(value) -> str:
    """A code in `code` formatting: shown as it is (no escaping inside it), only a backtick can't be in it."""
    return (value.strip()[:30] if isinstance(value, str) else "").replace("`", "") or "?"


def _until(timestamp) -> str:
    timestamp = _whole(timestamp)
    return f"<t:{timestamp}:R>" if timestamp > 0 else t("codes.unlimited")


def panel_details(change: dict) -> str:
    """What one change from the game's log did, as text for the log channel (in the bot's language)."""
    live_game = _live()
    kind = change.get("kind")
    data = change.get("data") if isinstance(change.get("data"), dict) else {}
    if kind in ("code_add", "code_remove"):
        text = f"`{_code(data.get('code'))}`"
        if kind == "code_add":
            reward = game_sync.clean_reward(data.get("reward"))
            ends = reward.get("expires_at", 0)
            text += (" — " + (live_game.reward_text(reward).replace("\n", ", ") or "?") + " · "
                     + (t("codes.expires_in", time=f"<t:{ends}:R>") if ends > 0 else t("codes.expires_never")))
        return text
    if kind in ("event_start", "event_stop"):
        text = f"**{_shown(data.get('name'), 50)}**"
        if kind == "event_start":
            text += (f" — {live_game.multipliers_text(game_sync.clean_multipliers(data.get('multipliers')))} · "
                     f"{t('events.ends')}: {_until(data.get('ends_at'))}")
            animation = live_game.animation_name(data.get("animation")) if isinstance(data.get("animation"), str) else ""
            if animation:
                text += f" · ✨ {animation}"
        if kind in ("event_start", "event_stop") and data.get("scope") == "server":
            text += " · " + t("panellog.this_server")
        return text
    if kind in ("egg_create", "egg_move", "egg_remove"):
        text = f"**{_shown(data.get('name'), 40)}**"
        if kind == "egg_create":
            pets = ", ".join(f"{_shown(p['name'], 50)} {live_game.chance_text(p['chance'])}"
                             for p in game_sync.clean_pets(data.get("pets"))[:25])
            text += f" — {_whole(data.get('price')):,} {_shown(data.get('currency'))} · {pets}"
        if kind != "egg_remove":
            spot = _shown(data.get("spot"), 30) if isinstance(data.get("spot"), str) and data["spot"].strip() else None
            text += " · " + (f"{t('eggs.spot')}: {spot}" if spot else t("panellog.any_spot"))
        return text
    if kind == "gift":
        reward = game_sync.clean_reward(data.get("reward"))
        text = t("panellog.gift", username=_shown(data.get("username"), 30), user_id=_whole(data.get("user_id")),
                 reward=live_game.reward_text(reward).replace("\n", ", ") or "?")
        message = data.get("message")
        if isinstance(message, str) and message.strip():
            text += f"\n{t('give.message')}: {_shown(message, 150)}"
        return text
    if kind == "announce":
        return t("panellog.announce", text=_shown(data.get("text"), 200), seconds=_whole(data.get("seconds")))
    if kind in ("ban", "unban"):
        text = f"**{_shown(data.get('username'), 30)}** (`{_whole(data.get('user_id'))}`)"
        if kind == "ban":
            seconds = _whole(data.get("seconds"))
            until = t("rban.permanent") if seconds <= 0 else f"<t:{_whole(change.get('at')) + seconds}:f>"
            text += " · " + t("panellog.ban", until=until, reason=_shown(data.get("reason"), 200))
        return text
    return ""


def chunks(lines: list, limit: int = 1800) -> list:
    """Lines joined into as few messages as fit (a burst of changes is not one message per line)."""
    messages, current = [], ""
    for line in lines:
        line = line[:limit]
        if current and len(current) + 1 + len(line) > limit:
            messages.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    return messages + ([current] if current else [])


class GameRequests(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_request = 0.0
        self.last_read = 0.0
        self.failures = 0
        self.read_loop.start()

    def cog_unload(self):
        self.read_loop.cancel()

    # ---------- What each request does ----------

    async def _code_add(self, data: dict, author: GameUser) -> str:
        params = code_params(_text(data, "code", 30, True), _choice(data, "validity", CODE_VALIDITY, "unlimited"),
                             _text(data, "currency", 100) or NONE, _number(data, "amount"), _number(data, "exp"),
                             _text(data, "item", 100) or NONE, _choice(data, "item_duration", ITEM_DURATIONS, "permanent"))
        if is_live(await database.get_game_code(params["code"])):  # on Discord this asks first; here it is refused
            raise RequestError(t("grequest.code_exists", code=params["code"]))
        cog = self.bot.get_cog("GameCodes")
        if not cog:
            raise RequestError(t("grequest.unknown"))
        return embed_text(await cog.store_code(author, **params))

    async def _code_remove(self, data: dict, author: GameUser) -> str:
        cog = self.bot.get_cog("GameCodes")
        code = _text(data, "code", 30, True).upper()
        if not cog:
            raise RequestError(t("grequest.unknown"))
        return plain(await cog.remove_codes([code]))

    async def _event_start(self, data: dict, author: GameUser) -> str:
        live_game = _live()
        multipliers = live_game.build_multipliers(
            _text(data, "currency", 100) or NONE,
            _choice(data, "currency_x", [""] + live_game.MULTIPLIERS, ""),
            _choice(data, "exp_x", [""] + live_game.MULTIPLIERS, ""),
            _choice(data, "luck_x", [""] + live_game.MULTIPLIERS, ""))
        embed = await live_game.start_event(_text(data, "name", 50, True), _text(data, "duration", 20, True), multipliers, 0)
        return embed_text(embed)

    async def _event_stop(self, data: dict, author: GameUser) -> str:
        live_game = _live()
        if not await database.stop_live_event(_number(data, "id", 1, 2 ** 31)):
            raise RequestError(t("events.not_found"))
        ok, error = await live_game.push_live("events")
        return plain(t("events.stopped") + "\n" + live_game.sync_note(ok, error))

    async def _egg_create(self, data: dict, author: GameUser) -> str:
        live_game = _live()
        embed = await live_game.create_egg(_text(data, "name", 40, True), _text(data, "currency", 100, True),
                                           _number(data, "price", 1, live_game.MAX_PRICE), _text(data, "pets", 1000, True),
                                           duration=_choice(data, "duration", live_game.EGG_DURATIONS, "unlimited"),
                                           spot=_text(data, "spot", 30))
        return embed_text(embed)

    async def _egg_move(self, data: dict, author: GameUser) -> str:
        return embed_text(await _live().edit_egg(_number(data, "id", 1, 2 ** 31), spot=_text(data, "spot", 30)))

    async def _egg_remove(self, data: dict, author: GameUser) -> str:
        live_game = _live()
        egg_id = _number(data, "id", 1, 2 ** 31)
        row = await database.get_egg(egg_id)
        if not row or not await database.remove_egg(egg_id):
            raise RequestError(t("eggs.not_found"))
        ok, error = await live_game.push_live("eggs")
        return plain(t("eggs.removed", name=row["name"]) + "\n" + live_game.sync_note(ok, error))

    async def _gift(self, data: dict, author: GameUser) -> str:
        embed = await _live().send_gift(_text(data, "player", 25, True), _reward(data), _text(data, "message", 150),
                                        author.display_name, 0, by_id=True)
        return embed_text(embed)

    async def _announce(self, data: dict, author: GameUser) -> str:
        seconds = _choice(data, "seconds", ANNOUNCE_SECONDS, 10)
        return plain(await _live().announce(_text(data, "text", 200, True), seconds))

    async def _find_player(self, data: dict, author: GameUser) -> tuple:
        """(text, extra): the account a ban would hit, shown before the ban like the account check on Discord."""
        user_id, username = await _live().find_player(_text(data, "player", 25, True), by_id=True)
        return t("grequest.found", username=username, user_id=user_id), {"user_id": user_id, "username": username}

    async def _ban(self, data: dict, author: GameUser) -> str:
        # only an account the owner saw (find_player above), so a typo never bans someone else with their alts
        user_id = _number(data, "user_id", 1, 2 ** 53)
        seconds = BAN_DURATIONS[_choice(data, "duration", BAN_DURATIONS, "24h")]
        reason = _text(data, "reason", 200) or t("grequest.ban_reason")
        if not user_id:
            raise RequestError(t("grequest.bad"))
        if _live().has_link(reason):  # the player sees the reason: a link would be hidden by Roblox anyway
            raise RequestError(t("grequest.ban_link"))
        try:
            user = await roblox_api.get_user(user_id)
            game = await roblox_api.get_game(cloud_sync.universe_id())
        except roblox_api.RobloxApiError as e:
            raise RequestError(str(e))
        if not user:
            raise RequestError(t("card.not_found", player=user_id))
        creator = (game or {}).get("creator") or {}
        if user_id == author.roblox_id or (creator.get("type") == "User" and creator.get("id") == user_id):
            raise RequestError(t("grequest.ban_self"))
        username = str(user.get("name") or user_id)
        await open_cloud.set_ban(user_id, True, seconds, reason, f"by {author.display_name} ({author.roblox_id}) via the game")
        until = t("rban.permanent") if not seconds else f"<t:{int(time.time()) + seconds}:f>"
        return plain(t("rban.banned", username=username, until=until, reason=reason))

    async def _unban(self, data: dict, author: GameUser) -> str:
        user_id, username = await _live().find_player(_text(data, "player", 25, True), by_id=True)
        await open_cloud.set_ban(user_id, False)
        return plain(t("rban.unbanned", username=username))

    HANDLERS = {"code_add": _code_add, "code_remove": _code_remove, "event_start": _event_start, "event_stop": _event_stop,
                "egg_create": _egg_create, "egg_move": _egg_move, "egg_remove": _egg_remove, "gift": _gift,
                "announce": _announce, "find_player": _find_player, "ban": _ban, "unban": _unban}

    async def run_request(self, request: dict) -> tuple:
        """(ok, text for the panel, extra data for the panel, text for the log) of one request. Never raises."""
        name = request.get("name") if isinstance(request.get("name"), str) else "?"
        name = name[:40] or "?"
        user_id = request.get("by") if isinstance(request.get("by"), int) else 0
        author = GameUser(name, user_id)
        handler = self.HANDLERS.get(request.get("kind"))
        data = request.get("data") if isinstance(request.get("data"), dict) else {}
        extra = None
        try:
            if time.time() - _at(request) > REQUEST_MAX_AGE:
                raise RequestError(t("grequest.too_old"))
            if not handler:
                raise RequestError(t("grequest.unknown"))
            ok, text = True, await handler(self, data, author)
            if isinstance(text, tuple):
                text, extra = text
        except (RequestError, CodeError, _live().RuleError, open_cloud.OpenCloudError) as e:
            ok, text = False, plain(str(e))
        except Exception:
            log.exception("A request from the game failed: %s", request.get("kind"))
            ok, text = False, t("grequest.error")
        log_text = t("grequest.log_ok" if ok else "grequest.log_failed", name=name, user_id=user_id,
                     kind=action_log.kind_label(request.get("kind")), text=text[:1500])
        return ok, text[:MAX_TEXT], extra, log_text

    # ---------- Reading the requests ----------

    def _state(self, universe: int) -> dict:
        state = config_store.read_json(STATE_FILE, {})
        if not isinstance(state, dict) or state.get("universe") != universe:  # another game: its own numbers
            state = {"universe": universe, "done": None, "results": {}}
        return state

    async def _first_state(self, requests: list) -> tuple:
        """(done, results) for a game this bot hasn't read yet: what any bot already answered (kept in the game, in
        ManagerResults), or, when no bot ever answered, everything waiting now counts as done: it waited before a bot
        knew the game, so it is answered "send it again", never done."""
        answered = await open_cloud.read_entry(open_cloud.live_settings()["datastore"], RESULTS_KEY)
        done = answered.get("done") if isinstance(answered, dict) else None
        if isinstance(done, int) and not isinstance(done, bool):
            kept = answered.get("results")
            return done, {str(k): v for k, v in kept.items() if isinstance(v, dict)} if isinstance(kept, dict) else {}
        results = {str(r["id"]): {"ok": False, "text": t("grequest.too_old"), "at": int(time.time())} for r in requests}
        return max((r["id"] for r in requests), default=0), results

    async def check_requests(self) -> int:
        """Does the new requests once. Returns how many there were."""
        universe = cloud_sync.universe_id()
        state = self._state(universe)
        entry = await open_cloud.read_entry(open_cloud.live_settings()["datastore"], REQUESTS_KEY)
        entry = entry if isinstance(entry, dict) else {}  # a broken entry must never stop the reading for good
        listed = entry.get("requests") if isinstance(entry.get("requests"), list) else []
        requests = [r for r in listed if isinstance(r, dict) and isinstance(r.get("id"), int) and not isinstance(r.get("id"), bool)]
        results = state.get("results") if isinstance(state.get("results"), dict) else {}
        if state.get("done") is None:
            state["done"], results = await self._first_state(requests)
            state["results"], state["results_unsaved"] = results, bool(requests)
        next_id = entry.get("next")
        if isinstance(next_id, int) and next_id - 1 < state["done"]:
            state["done"] = next_id - 1  # the entry was cleared (e.g. in Creator Hub): the numbers start again
        new = sorted((r for r in requests if r["id"] > state["done"]), key=lambda r: r["id"])
        if not new:
            config_store.write_json(STATE_FILE, state)
            if state.get("results_unsaved"):  # the last write failed: the panel still waits for these answers
                await self._save_results(state)
            return 0
        for request in new:
            # remembered as done BEFORE it runs: a crash in the middle never does a gift or a ban twice
            state["done"] = request["id"]
            config_store.write_json(STATE_FILE, state)
            ok, text, extra, log_text = await self.run_request(request)
            result = {"ok": ok, "text": text, "by": request.get("by"), "at": int(time.time())}
            if extra:
                result["extra"] = extra
            results[str(request["id"])] = result
            state["results"] = {key: results[key] for key in sorted(results, key=int)[-MAX_RESULTS:]}
            state["results_unsaved"] = True
            config_store.write_json(STATE_FILE, state)  # the answer is kept even if something below fails
            for guild in self.bot.guilds:
                try:
                    await _admin().log_action(guild, log_text)
                except Exception as e:
                    log.warning("Could not write request %s to the log channel: %s", request["id"], e)
            try:  # the panel shows the answer at once; without the message it reads ManagerResults a moment later
                await open_cloud.publish({"type": "manager_result", "id": request["id"], **result})
            except Exception as e:
                log.warning("Could not tell the game the result of request %s: %s", request["id"], e)
        await self._save_results(state)
        return len(new)

    async def _save_results(self, state: dict) -> None:
        await open_cloud.write_entry(open_cloud.live_settings()["datastore"], RESULTS_KEY,
                                     {"done": state["done"], "results": state.get("results") or {}})
        state["results_unsaved"] = False
        config_store.write_json(STATE_FILE, state)

    # ---------- The log of what the Manager did by itself (DiscordCodes file 40 and newer) ----------

    def _panel_state(self, universe: int) -> dict:
        state = config_store.read_json(PANEL_STATE_FILE, {})
        if not isinstance(state, dict) or state.get("universe") != universe:  # another game: its own numbers
            state = {"universe": universe, "seen": None}
        return state

    async def check_panel_log(self) -> int:
        """Writes the new changes from the game's log to the log channel and copies the codes, events and eggs they made
        into the database. Returns how many changes there were."""
        universe = cloud_sync.universe_id()
        datastore = open_cloud.live_settings()["datastore"]
        entry = await open_cloud.read_entry(datastore, PANEL_LOG_KEY)
        entry = entry if isinstance(entry, dict) else {}  # a broken entry must never stop the reading for good
        listed = entry.get("entries") if isinstance(entry.get("entries"), list) else []
        changes = sorted((c for c in listed if isinstance(c, dict) and _whole(c.get("seq")) > 0), key=lambda c: _whole(c["seq"]))
        state = self._panel_state(universe)
        first_ever = False
        if state.get("seen") is None:
            read = await open_cloud.read_entry(datastore, PANEL_READ_KEY)  # what any bot already wrote to the channel
            seen = read.get("seen") if isinstance(read, dict) else None
            if isinstance(seen, int) and not isinstance(seen, bool) and seen >= 0:
                state["seen"] = seen
            else:  # no bot ever read this game's log: only the newest changes, the earlier ones are counted
                first_ever = True
                state["seen"] = _whole(changes[-FIRST_READ_POSTS - 1]["seq"]) if len(changes) > FIRST_READ_POSTS else 0
        next_seq = entry.get("next")
        if isinstance(next_seq, int) and not isinstance(next_seq, bool) and next_seq - 1 < state["seen"]:
            state["seen"] = 0  # the log was cleared (e.g. in Creator Hub): what it has now came after that
        new = [c for c in changes if _whole(c["seq"]) > state["seen"]]
        if not new:
            config_store.write_json(PANEL_STATE_FILE, state)
            return 0
        lines = []
        # the changes before the first one written now that no bot wrote (the game keeps only the newest 100)
        skipped = _whole(new[0]["seq"]) - 1 - (0 if first_ever else state["seen"])
        if skipped > 0:
            lines.append(t("panellog.skipped", count=skipped))
        kinds = set()
        for change in new:
            kind = str(change.get("kind"))[:20]
            name = change.get("name") if isinstance(change.get("name"), str) else "?"
            try:
                details = panel_details(change)
            except Exception:  # an odd value from the game must not stop the log
                log.exception("Could not describe change %s from the game's log", change.get("seq"))
                details = ""
            lines.append(t("grequest.log_ok", name=_shown(name, 40), user_id=_whole(change.get("by")),
                           kind=action_log.kind_label(kind), text=details or "-"))
            kinds.add(SYNC_KINDS.get(kind, ""))
            if kind == "gift":
                await self._remember_gift(change)
        # remembered BEFORE writing to the channel: a crash in the middle never writes a change twice
        state["seen"] = _whole(new[-1]["seq"])
        config_store.write_json(PANEL_STATE_FILE, state)
        for guild in self.bot.guilds:
            for message in chunks(lines):
                try:
                    await _admin().log_action(guild, message)
                except Exception as e:
                    log.warning("Could not write the game's changes to the log channel: %s", e)
        try:
            await open_cloud.write_entry(datastore, PANEL_READ_KEY, {"seen": state["seen"], "at": int(time.time())})
        except Exception as e:  # only a bot that loses its own file would write these changes again
            log.warning("Could not save in the game which changes were read: %s", e)
        for kind in sorted(k for k in kinds if k):
            await self._sync(kind)
        return len(new)

    async def _remember_gift(self, change: dict) -> None:
        """A gift sent from the game: kept like a /give, so the player card on Discord shows it."""
        data = change.get("data") if isinstance(change.get("data"), dict) else {}
        key, user_id = data.get("key"), _whole(data.get("user_id"))
        if not isinstance(key, str) or not key or user_id <= 0 or await database.has_gift(key[:100]):
            return
        reward = game_sync.clean_reward(data.get("reward"))
        reward.pop("expires_at", None)
        message = data.get("message") if isinstance(data.get("message"), str) else ""
        username = data.get("username") if isinstance(data.get("username"), str) else str(user_id)
        await database.add_gift(key[:100], user_id, username[:30], json.dumps(reward), message[:150], 0,
                                author=str(change.get("name") or "")[:40])

    async def _sync(self, kind: str) -> None:
        """Copies right away what the game made into the database (the 2-minute syncs would do it a bit later)."""
        try:
            if kind == "codes":
                result = await cloud_sync.push_codes(force=False)
                ok, error = result.ok, result.message
            else:
                ok, error = await _live().push_live(kind)
        except Exception as e:
            ok, error = False, str(e)
        if not ok:
            log.warning("Could not copy the game's %s into the database: %s", kind, error)

    @tasks.loop(seconds=FAST_SECONDS)
    async def read_loop(self):
        if cloud_sync.status() != "ready":
            return
        now = time.time()
        wait = FAST_SECONDS if now - self.last_request < FAST_FOR else SLOW_SECONDS
        if now - self.last_read < wait - 0.5:
            return
        self.last_read = now
        try:
            found = await self.check_panel_log()
            found += await self.check_requests()
            if found:
                self.last_request = time.time()
            if self.failures:
                log.info("Reading requests from the game works again.")
            self.failures = 0
        except Exception as e:  # never stop the loop for good (Roblox may not answer for a moment)
            self.failures += 1
            if self.failures & (self.failures - 1) == 0:  # the 1st, 2nd, 4th, 8th... failure in a row
                log.warning("Could not read requests from the game (%s time(s) in a row): %s", self.failures, e)

    @read_loop.before_loop
    async def before_read_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(GameRequests(bot))
