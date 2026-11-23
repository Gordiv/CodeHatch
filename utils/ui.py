"""Shared pieces of the panels: a view with a ✖️ Close button that removes itself when nobody uses it, the admin-only
and the game-staff views, and sending a panel so it can be removed later.

Lifetime of a private (ephemeral) panel message:
- nobody clicks it for CLOSE_AFTER seconds -> it removes itself (PANEL_TIMEOUT for windows that are read, and while a
  form opened from it is being filled in);
- Discord lets the bot edit or delete it only for 15 minutes with the token it was sent with, so at PANEL_TIMEOUT
  after that the panel removes itself even when it is still used (a fresh token from an answer in place starts the
  15 minutes again); otherwise its buttons would look active but fail;
- when another panel takes over the same message (an answer in place), the old one stops, so its timer can't remove
  the new content."""
import asyncio
import secrets
import time
import weakref

import discord

from utils import access
from utils.i18n import t

# Discord lets the bot edit (and delete) an ephemeral message only for 15 minutes after it was sent
PANEL_TIMEOUT = 840
# A panel nobody clicks for 5 minutes removes itself, so finished windows don't pile up under the control panel
CLOSE_AFTER = 300
CLOSE_ID = "ui-close"

_shown = weakref.WeakValueDictionary()  # message id -> the panel that message shows now
_token_ends = {}  # message id -> when the bot can no longer edit or delete it (time.monotonic())


def _remember_token(message, fresh: bool):
    """When the bot loses the right to edit/delete this message (fresh: it was just sent or edited with a new token)."""
    message_id = getattr(message, "id", None)
    if message_id is None:
        return None
    now = time.monotonic()
    for key in [k for k, ends in _token_ends.items() if ends < now - 60]:
        _token_ends.pop(key, None)
    if fresh or message_id not in _token_ends:
        _token_ends[message_id] = now + PANEL_TIMEOUT
    return _token_ends[message_id]


async def close_message(interaction: discord.Interaction, fallback: str = None):
    """Removes the message with the clicked button (an ephemeral one too). If Discord refuses, the message is emptied
    and keeps a short note instead."""
    if not interaction.response.is_done():
        await interaction.response.defer()
    try:
        await interaction.delete_original_response()
    except discord.HTTPException:
        try:
            await interaction.edit_original_response(content=fallback or t("ui.closed"), embed=None, view=None)
        except discord.HTTPException:
            pass


def is_close_click(interaction: discord.Interaction) -> bool:
    data = getattr(interaction, "data", None) or {}
    return str(data.get("custom_id", "")).startswith(CLOSE_ID)


class CloseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label=t("ui.close"), emoji="✖️", style=discord.ButtonStyle.secondary,
                         custom_id=f"{CLOSE_ID}:{secrets.token_hex(8)}")

    async def callback(self, interaction: discord.Interaction):
        if self.view is not None:
            self.view.stop()
        await close_message(interaction)


class Panel(discord.ui.View):
    """An ephemeral panel. It gets a ✖️ Close button under its own buttons when it is sent (if there is room) and
    removes itself when nobody uses it (see the top of this file). If Discord refuses that, its buttons and menus are
    shown turned off instead of looking active but failing."""

    close_button = True  # False for a panel whose own Cancel already closes it
    close_row = None  # a row for ✖️ Close when the panel's layout needs it elsewhere than the default place

    def __init__(self, timeout: float = CLOSE_AFTER):
        super().__init__(timeout=timeout)
        self._deadline_task = None
        self._message = None

    # ---------- the message it is shown in ----------

    @property
    def message(self):
        return self._message

    @message.setter
    def message(self, message):
        self._message = message
        message_id = getattr(message, "id", None)
        if message_id is None:
            return
        previous = _shown.get(message_id)
        if previous is not None and previous is not self:
            previous.stop()  # this message shows another panel now: the old one must not remove it later
        _shown[message_id] = self
        self._watch_deadline(_remember_token(message, fresh=False))

    def _watch_deadline(self, ends):
        if self._deadline_task is not None:
            self._deadline_task.cancel()
            self._deadline_task = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._deadline_task = loop.create_task(self._deadline(ends))

    async def _deadline(self, ends: float):
        await asyncio.sleep(max(0.0, ends - time.monotonic()))
        if self.is_finished():
            return
        self._deadline_task = None  # this task is running: stop() must not cancel it
        self.stop()
        await self.on_timeout()

    def hold_for_form(self):
        """A form opened from this panel will answer in it: give the person time to fill it in."""
        self.timeout = PANEL_TIMEOUT

    def stop(self) -> None:
        task, self._deadline_task = getattr(self, "_deadline_task", None), None
        if task is not None:
            try:
                current = asyncio.current_task()
            except RuntimeError:
                current = None
            if task is not current:
                task.cancel()
        super().stop()

    # ---------- ✖️ Close ----------

    def to_components(self):
        if self.close_button and not any(isinstance(item, CloseButton) for item in self.children):
            self._add_close_button()
        return super().to_components()

    def _add_close_button(self):
        """In the last row of buttons if it has room, else in a new row below; never next to a menu. When the last
        row is a menu (e.g. the language menu of /setup, which must stay last), the lowest button row with room is
        used instead."""
        rows = {}
        for item in self.children:
            row = getattr(item, "_rendered_row", None)
            rows.setdefault((item.row or 0) if row is None else row, []).append(item)
        buttons_only = {row for row, items in rows.items() if all(isinstance(i, discord.ui.Button) for i in items)}
        free = [row for row in buttons_only if sum(i.width for i in rows[row]) < 5]
        last = max(rows) if rows else -1
        if self.close_row is not None and (self.close_row in free or self.close_row not in rows):
            target = self.close_row
        elif last in free:
            target = last
        elif (last in buttons_only or last == -1) and last < 4:
            target = last + 1
        elif free:
            target = max(free)
        elif last < 4:
            target = last + 1
        else:
            return  # five full rows: the panel still closes itself after a while
        button = CloseButton()
        button.row = target
        try:
            self.add_item(button)
        except ValueError:
            pass

    def disable_all(self) -> None:
        for item in self.children:
            if getattr(item, "url", None):
                continue  # link buttons keep working
            if hasattr(item, "disabled"):
                item.disabled = True

    async def on_timeout(self) -> None:
        task, self._deadline_task = self._deadline_task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        message = self.message
        if message is None or _shown.get(getattr(message, "id", None), self) is not self:
            return  # another panel shows this message now
        try:
            await message.delete()
            return
        except (discord.HTTPException, ValueError, AttributeError):
            pass
        self.disable_all()
        try:
            await message.edit(view=self)
        except (discord.HTTPException, ValueError, AttributeError):
            pass


class CloseView(Panel):
    """Only a ✖️ Close button: under an answer (e.g. the result of a game action) that would otherwise stay until
    the reader dismisses it. It also removes itself after CLOSE_AFTER seconds."""


class AdminView(Panel):
    """A panel only server administrators may use (checked at every click)."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if access.is_admin(interaction):
            return True
        await interaction.response.send_message(t("errors.admin_only"), ephemeral=True)
        return False


async def staff_only(interaction: discord.Interaction, permission: str = None) -> bool:
    """For game actions (also when a form opened earlier is sent): administrators and the roles that have this
    permission in /setup -> 🛡️ Permissions (permission None: any game permission). Anyone else gets a short refusal
    naming what they lack; False then."""
    allowed = access.can(interaction, permission) if permission else access.is_game_staff(interaction)
    if allowed:
        return True
    text = t("perm.no_access", what=t(f"perm.{permission}")) if permission else t("gpanel.no_access")
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)
    return False


class StaffView(Panel):
    """A panel for game actions (codes, gifts, events, eggs, bans): administrators and the roles that have
    `permission` in /setup -> 🛡️ Permissions (checked at every click, so taking the role away works at once)."""

    permission = None  # e.g. "codes"; None = any game permission

    def __init__(self, *args, permission: str = None, **kwargs):
        super().__init__(*args, **kwargs)
        if permission:
            self.permission = permission

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_close_click(interaction):
            return True
        return await staff_only(interaction, self.permission)


async def send_panel(interaction: discord.Interaction, view: discord.ui.View = None, **kwargs):
    """Sends a panel as the answer (or a follow-up after defer) and remembers the message, so the panel can remove
    itself later. Returns the message."""
    kwargs.setdefault("ephemeral", True)
    if view is not None:
        kwargs["view"] = view
    if interaction.response.is_done():
        message = await interaction.followup.send(wait=True, **kwargs)
    else:
        await interaction.response.send_message(**kwargs)
        try:
            message = await interaction.original_response()
        except discord.HTTPException:
            message = None
    _remember_token(message, fresh=True)
    if view is not None and hasattr(view, "message"):
        view.message = message
    return message


async def defer_for(interaction: discord.Interaction, panel) -> None:
    """Acknowledges a form or a click whose answer goes in place of `panel`'s message. When that panel is gone (closed,
    or removed after a few minutes), the answer comes as a new private message instead."""
    if panel is not None and panel.is_finished():
        await interaction.response.defer(ephemeral=True, thinking=True)
    else:
        await interaction.response.defer()


async def show_in_place(interaction: discord.Interaction, view: discord.ui.View = None, **kwargs):
    """Replaces the message the clicked button or the sent form came from (after defer()). If that message is gone
    (closed, or removed after a few minutes), the answer comes as a new message only this person sees."""
    try:
        if view is not None:
            kwargs["view"] = view
        message = await interaction.edit_original_response(**kwargs)
        _remember_token(message, fresh=True)  # a fresh token: the panel may remove itself for 15 more minutes
        if view is not None and hasattr(view, "message"):
            view.message = message
    except discord.HTTPException:
        kwargs.pop("view", None)
        kwargs = {key: value for key, value in kwargs.items() if value is not None}
        await send_panel(interaction, view if view is not None else CloseView(), **kwargs)
