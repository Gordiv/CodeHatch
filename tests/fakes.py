"""Strict stand-ins for Discord objects, shared by the tests that click through panels.

They behave like Discord, not like a friendly mock:
- answering an interaction twice, or a follow-up before the first answer, raises (Discord refuses it),
- every message, embed, view and form that is sent is checked against Discord's limits.
A bug that Discord would answer with "This interaction failed" or HTTP 400 fails the test here."""
import discord

LIMIT_CONTENT = 2000
LIMIT_EMBED_TOTAL = 6000


class DiscordRefused(AssertionError):
    """The bot did something Discord would refuse."""


def _fail(message: str):
    raise DiscordRefused(message)


# ---------- limits ----------

def check_embed(embed: discord.Embed, where: str = "embed") -> None:
    if embed is None:
        return
    data = embed.to_dict()
    if len(embed) > LIMIT_EMBED_TOTAL:
        _fail(f"{where}: {len(embed)} characters in total (max {LIMIT_EMBED_TOTAL})")
    if len(data.get("title", "")) > 256:
        _fail(f"{where}: title {len(data['title'])} > 256")
    if len(data.get("description", "")) > 4096:
        _fail(f"{where}: description {len(data['description'])} > 4096")
    if len(data.get("fields", [])) > 25:
        _fail(f"{where}: {len(data['fields'])} fields > 25")
    for field in data.get("fields", []):
        if not field.get("name") or not field.get("value"):
            _fail(f"{where}: an empty field name or value: {field}")
        if len(field["name"]) > 256 or len(field["value"]) > 1024:
            _fail(f"{where}: field '{field['name'][:30]}' name {len(field['name'])} / value {len(field['value'])}")
    if len(data.get("footer", {}).get("text", "")) > 2048:
        _fail(f"{where}: footer too long")
    if len(data.get("author", {}).get("name", "")) > 256:
        _fail(f"{where}: author too long")


def check_select(data: dict, where: str) -> None:
    options = data.get("options", [])
    if not 1 <= len(options) <= 25:
        _fail(f"{where}: {len(options)} options (1-25)")
    if len(data.get("placeholder", "")) > 150:
        _fail(f"{where}: placeholder > 150")
    if len(data.get("custom_id", "")) > 100:
        _fail(f"{where}: custom_id > 100")
    values = [o["value"] for o in options]
    if len(set(values)) != len(values):
        _fail(f"{where}: two options with the same value: {values}")
    for option in options:
        if not option["label"] or len(option["label"]) > 100 or len(option["value"]) > 100 or not option["value"]:
            _fail(f"{where}: option {option['label'][:30]!r}: label/value out of 1-100")
        if len(option.get("description", "")) > 100:
            _fail(f"{where}: option description > 100")
    if data.get("max_values", 1) > len(options):
        _fail(f"{where}: max_values {data['max_values']} > {len(options)} options")


def check_view(view, where: str = "view") -> None:
    if view is None:
        return
    rows = view.to_components()
    if len(rows) > 5:
        _fail(f"{where}: {len(rows)} rows (max 5)")
    for index, row in enumerate(rows):
        items = row["components"]
        if not 1 <= len(items) <= 5:
            _fail(f"{where}: row {index} holds {len(items)} buttons")
        if any(i["type"] == 3 for i in items) and len(items) != 1:
            _fail(f"{where}: a menu shares row {index}")
        for item in items:
            if item["type"] == 2:  # button
                label = item.get("label", "")
                if label is None or len(label) > 80:
                    _fail(f"{where}: button label {label!r} is {len(label or '')} characters (max 80)")
                if not label and not item.get("emoji"):
                    _fail(f"{where}: a button without label and emoji")
                if len(item.get("custom_id", "")) > 100:
                    _fail(f"{where}: custom_id > 100")
            elif item["type"] == 3:
                check_select(item, where)


def check_modal(modal, where: str = "modal") -> None:
    data = modal.to_dict()
    if not 1 <= len(data["title"]) <= 45:
        _fail(f"{where}: title {data['title']!r} is {len(data['title'])} characters (max 45)")
    components = data["components"]
    if not 1 <= len(components) <= 5:
        _fail(f"{where}: {len(components)} components (max 5)")

    def walk(item):
        kind = item.get("type")
        if kind == 1:
            for child in item["components"]:
                walk(child)
        elif kind == 4:
            if not 1 <= len(item.get("label", "")) <= 45:
                _fail(f"{where}: field label {item.get('label')!r} is {len(item.get('label', ''))} characters (1-45)")
            if len(item.get("placeholder", "")) > 100:
                _fail(f"{where}: placeholder {item['placeholder'][:30]!r} is over 100 characters")
            if len(item.get("value", "")) > item.get("max_length", 4000):
                _fail(f"{where}: the prefilled value is longer than max_length")
            if item.get("min_length", 0) > item.get("max_length", 4000):
                _fail(f"{where}: min_length > max_length")
        elif kind == 18:
            if not 1 <= len(item.get("label", "")) <= 45:
                _fail(f"{where}: menu label {item.get('label')!r} is {len(item.get('label', ''))} characters (1-45)")
            if len(item.get("description", "")) > 100:
                _fail(f"{where}: label description > 100")
            if item["component"].get("type") == 3:  # a menu of options (a file upload or a user menu has none)
                check_select(item["component"], where)

    for item in components:
        walk(item)


def check_payload(content=None, embed=None, embeds=None, view=None, where: str = "message") -> None:
    if content is not None and len(content) > LIMIT_CONTENT:
        _fail(f"{where}: content is {len(content)} characters (max {LIMIT_CONTENT})")
    for e in ([embed] if embed is not None else []) + list(embeds or []):
        check_embed(e, where)
    check_view(view, where)


# ---------- the interaction ----------

class Response:
    def __init__(self):
        self.done = False
        self.sent, self.edits, self.modals, self.defers = [], [], [], []

    def is_done(self) -> bool:
        return self.done

    def _take(self, what: str):
        if self.done:
            _fail(f"the interaction was answered twice ({what} after an earlier answer)")
        self.done = True

    async def send_message(self, content=None, **kwargs):
        self._take("send_message")
        check_payload(content, kwargs.get("embed"), kwargs.get("embeds"), kwargs.get("view"), "send_message")
        self.sent.append((content, kwargs))

    async def edit_message(self, **kwargs):
        self._take("edit_message")
        check_payload(kwargs.get("content"), kwargs.get("embed"), kwargs.get("embeds"), kwargs.get("view"), "edit_message")
        self.edits.append(kwargs)

    async def send_modal(self, modal):
        self._take("send_modal")
        check_modal(modal)
        self.modals.append(modal)

    async def defer(self, **kwargs):
        self._take("defer")
        self.defers.append(kwargs)


class Followup:
    def __init__(self, response: Response):
        self.response = response
        self.sent = []

    async def send(self, content=None, **kwargs):
        if not self.response.done:
            _fail("followup.send before the interaction was answered")
        kwargs.pop("wait", None)
        check_payload(content, kwargs.get("embed"), kwargs.get("embeds"), kwargs.get("view"), "followup")
        self.sent.append((content, kwargs))


class Admin:
    id, mention, display_name = 7, "<@7>", "Admin"
    guild_permissions = discord.Permissions(administrator=True)

    def __str__(self):
        return "admin#0"


class Channel:
    def __init__(self):
        self.sent = []

    async def send(self, text=None, **kwargs):
        if text is not None and len(text) > LIMIT_CONTENT:
            _fail(f"log message is {len(text)} characters")
        self.sent.append(text)


class Guild:
    id = 4242

    def __init__(self):
        self.log = Channel()

    def get_channel(self, channel_id):
        return self.log if channel_id == 500 else None


class Client:
    def __init__(self, **cogs):
        self.cogs = cogs

    def get_cog(self, name):
        return self.cogs.get(name)


class Interaction:
    def __init__(self, **cogs):
        self.user, self.guild = Admin(), Guild()
        self.guild_id = self.guild.id
        self.response = Response()
        self.followup = Followup(self.response)
        self.client = Client(**cogs)
        self.edited = []
        self.deleted = False

    async def edit_original_response(self, **kwargs):
        if not self.response.done:
            _fail("edit_original_response before the interaction was answered")
        if self.deleted:
            _fail("edit_original_response after the message was deleted")
        check_payload(kwargs.get("content"), kwargs.get("embed"), kwargs.get("embeds"), kwargs.get("view"), "edit_original")
        self.edited.append(kwargs)

    async def delete_original_response(self):
        if not self.response.done:
            _fail("delete_original_response before the interaction was answered")
        self.deleted = True

    async def original_response(self):
        return None

    # what the admin finally sees
    def messages(self) -> list:
        """Every message text sent as an answer or follow-up, in order."""
        return [c for c, _ in self.response.sent + self.followup.sent if c]
