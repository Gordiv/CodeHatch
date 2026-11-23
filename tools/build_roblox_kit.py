"""Assembles scripts/DiscordCodes/*.luau into one file, scripts/DiscordCodes.rbxmx.

Users insert the .rbxmx into Roblox Studio in one step (right-click ServerScriptService -> Insert -> Import Roblox Model;
called Insert from File in older Studio).
Run it after every change to the .luau files:   python tools/build_roblox_kit.py

When the scripts changed since the last build, the file version (KIT_VERSION in Loader.server.luau) goes up by one.
Games report this number to the bot, and /setup and /setup-roblox use it to tell the owner when the file in Studio
must be replaced.
"""
import hashlib
import json
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "scripts" / "DiscordCodes"
OUT = ROOT / "scripts" / "DiscordCodes.rbxmx"
# The code window as a ready template for StarterGui (see the end of this file).
OUT_WINDOW = ROOT / "scripts" / "DiscordCodesWindow.rbxmx"
# The game catalog template (a ModuleScript the game owner fills in once, see the end of this file).
CATALOG_SOURCE = ROOT / "tools" / "templates" / "DiscordCatalog.luau"
OUT_CATALOG = ROOT / "scripts" / "DiscordCatalog.rbxmx"
# The owner's settings (a ModuleScript inserted once, next to DiscordCodes): the Loader copies them into its Settings
SETTINGS_SOURCE = ROOT / "tools" / "templates" / "DiscordSettings.luau"
OUT_SETTINGS = ROOT / "scripts" / "DiscordSettings.rbxmx"
VERSION_RECORD = ROOT / "tools" / "roblox_kit_version.json"
KIT_LINE = re.compile(r"^local KIT_VERSION = (\d+)(?=\r?$)", re.M)
SOURCE_FILES = ["Core.luau", "Client.client.luau", "Loader.server.luau", "Report.luau", "Live.luau", "LiveClient.client.luau",
                "Control.luau", "Manager.luau", "ManagerClient.client.luau", "Effects.luau"]

HEADER = (
    '<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">\n'
    '\t<Meta name="ExplicitAutoJoints">true</Meta>\n'
    "\t<External>null</External>\n"
    "\t<External>nil</External>\n"
)


def read_source(name: str) -> str:
    text = (SRC / name).read_text(encoding="utf-8").replace("\r\n", "\n")
    if "]]>" in text:
        sys.exit(f"{name}: contains the sequence ']]>' which is not allowed in CDATA")
    return text


def item(cls: str, name: str, source: str, disabled=None, children="", depth=1) -> str:
    pad = "\t" * depth
    disabled_xml = "" if disabled is None else f'{pad}\t\t<bool name="Disabled">{str(disabled).lower()}</bool>\n'
    return (
        f'{pad}<Item class="{cls}" referent="RBX{uuid.uuid4().hex.upper()}">\n'
        f"{pad}\t<Properties>\n"
        f'{pad}\t\t<string name="Name">{name}</string>\n'
        f"{disabled_xml}"
        f'{pad}\t\t<ProtectedString name="Source"><![CDATA[{source}]]></ProtectedString>\n'
        f"{pad}\t</Properties>\n"
        f"{children}"
        f"{pad}</Item>\n"
    )


SETTINGS = [("BoolValue", "ShowButton", "bool", "true"),
            ("StringValue", "ButtonPosition", "string", "Left"),
            ("StringValue", "Language", "string", "auto"),
            # the event icons (LiveClient.client.luau): where they are and your own icons
            ("StringValue", "EventPosition", "string", "BottomRight"),
            ("StringValue", "EventIcons", "string", ""),
            # the animations of events (Effects.luau): full, light or off
            ("StringValue", "EventEffects", "string", "full"),
            # where announcements and the gift / egg messages show (LiveClient.client.luau)
            ("StringValue", "AnnouncementPosition", "string", "Top"),
            ("StringValue", "NotificationPosition", "string", "Bottom"),
            # the ⚙️ Manager button (ManagerClient.client.luau)
            ("StringValue", "ManagerPosition", "string", "TopRight"),
            # server side (Core.luau): the most currency one code or gift may give, 0 = no limit
            ("IntValue", "MaxCurrencyPerCode", "int64", "0"),
            # the ⚙️ Manager (Manager.luau): on/off and extra UserIds besides the game's owner
            ("BoolValue", "Manager", "bool", "true"),
            ("StringValue", "ManagerUsers", "string", "")]


def settings_folder(depth: int, settings=None) -> str:
    pad = "\t" * depth
    values = "".join(
        f'{pad}\t<Item class="{cls}" referent="RBX{uuid.uuid4().hex.upper()}">\n'
        f"{pad}\t\t<Properties>\n"
        f'{pad}\t\t\t<string name="Name">{name}</string>\n'
        f'{pad}\t\t\t<{xml_type} name="Value">{value}</{xml_type}>\n'
        f"{pad}\t\t</Properties>\n"
        f"{pad}\t</Item>\n"
        for cls, name, xml_type, value in (SETTINGS if settings is None else settings)
    )
    return (
        f'{pad}<Item class="Configuration" referent="RBX{uuid.uuid4().hex.upper()}">\n'
        f"{pad}\t<Properties>\n"
        f'{pad}\t\t<string name="Name">Settings</string>\n'
        f"{pad}\t</Properties>\n"
        f"{values}"
        f"{pad}</Item>\n"
    )


def sources_hash() -> str:
    digest = hashlib.sha256()
    for name in SOURCE_FILES:
        text = KIT_LINE.sub("local KIT_VERSION = 0", read_source(name))
        digest.update(name.encode() + b"\0" + text.encode("utf-8") + b"\0")
    return digest.hexdigest()


def stamp_version() -> int:
    """Raises the file version when the scripts changed since the last build and writes it into Loader.server.luau."""
    loader = SRC / "Loader.server.luau"
    text = loader.read_bytes().decode("utf-8")
    match = KIT_LINE.search(text)
    if not match:
        sys.exit("Loader.server.luau: missing the line 'local KIT_VERSION = <number>'")
    current = int(match.group(1))
    digest = sources_hash()
    try:
        record = json.loads(VERSION_RECORD.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
    if not record:
        version = max(current, 1)
    elif record.get("hash") == digest:
        version = int(record["version"])
    else:
        version = int(record.get("version", current)) + 1
    if version != current:
        loader.write_text(KIT_LINE.sub(f"local KIT_VERSION = {version}", text), encoding="utf-8", newline="")
    if record.get("hash") != digest or record.get("version") != version:
        VERSION_RECORD.write_text(json.dumps({"version": version, "hash": digest}, indent=2) + "\n", encoding="utf-8")
    return version


def build(out: Path, sources: dict, version: int) -> dict:
    children = item("ModuleScript", "Core", sources["Core"], depth=2) + item("ModuleScript", "Report", sources["Report"], depth=2)
    children += item("ModuleScript", "Live", sources["Live"], depth=2)
    children += item("LocalScript", "DiscordCodesClient", sources["Client"], disabled=True, depth=2)
    # the event animations run on each player's device: a module inside the players' script
    children += item("LocalScript", "DiscordLiveClient", sources["LiveClient"], disabled=True, depth=2,
                     children=item("ModuleScript", "Effects", sources["Effects"], depth=3))
    # the ⚙️ Manager: its changes (Control), a module, and a ScreenGui with its LocalScript that the server gives only to
    # the game's owner
    children += item("ModuleScript", "Control", sources["Control"], depth=2)
    children += item("ModuleScript", "Manager", sources["Manager"], depth=2)
    panel_script = item("LocalScript", "DiscordManagerClient", sources["ManagerClient"], disabled=True, depth=3)
    gui_props = gprop("string", "Name", "DiscordManager") + gprop("bool", "ResetOnSpawn", False)
    tab = "\t"
    children += (f'{tab * 2}<Item class="ScreenGui" referent="RBX{uuid.uuid4().hex.upper()}">\n'
                 f'{tab * 3}<Properties>{gui_props}</Properties>\n{panel_script}{tab * 2}</Item>\n')
    children += settings_folder(depth=2)
    xml = HEADER + item("Script", "DiscordCodes", sources["Loader"], disabled=False, children=children) + "</roblox>\n"
    out.write_text(xml, encoding="utf-8", newline="\n")

    # verification: valid XML and identical code inside
    root = ET.fromstring(out.read_text(encoding="utf-8"))
    top = root.find("Item")
    assert top.get("class") == "Script" and top.find("Properties/string[@name='Name']").text == "DiscordCodes"
    assert top.find("Properties/ProtectedString[@name='Source']").text == sources["Loader"]
    kids = {i.find("Properties/string[@name='Name']").text: i for i in top.findall("Item")}
    for name, cls, source in (("Core", "ModuleScript", "Core"), ("Report", "ModuleScript", "Report"),
                              ("DiscordCodesClient", "LocalScript", "Client")):
        assert kids[name].get("class") == cls and kids[name].find("Properties/ProtectedString").text == sources[source], name
    assert kids["DiscordCodesClient"].find("Properties/bool[@name='Disabled']").text == "true"
    assert kids["Live"].get("class") == "ModuleScript" and kids["Live"].find("Properties/ProtectedString").text == sources["Live"]
    assert kids["DiscordLiveClient"].get("class") == "LocalScript"
    assert kids["DiscordLiveClient"].find("Properties/ProtectedString").text == sources["LiveClient"]
    assert kids["DiscordLiveClient"].find("Properties/bool[@name='Disabled']").text == "true"
    effects = kids["DiscordLiveClient"].find("Item")
    assert effects.get("class") == "ModuleScript" and effects.find("Properties/ProtectedString").text == sources["Effects"]
    assert kids["Manager"].get("class") == "ModuleScript"
    assert kids["Manager"].find("Properties/ProtectedString").text == sources["Manager"]
    assert kids["Control"].get("class") == "ModuleScript"
    assert kids["Control"].find("Properties/ProtectedString").text == sources["Control"]
    panel_gui = kids["DiscordManager"]
    assert panel_gui.get("class") == "ScreenGui"
    panel_client = panel_gui.find("Item")
    assert panel_client.get("class") == "LocalScript"
    assert panel_client.find("Properties/ProtectedString").text == sources["ManagerClient"]
    assert panel_client.find("Properties/bool[@name='Disabled']").text == "true"
    settings = {v.find("Properties/string[@name='Name']").text: (v.get("class"), v.find("Properties/*[@name='Value']").text or "")
                for v in kids["Settings"].findall("Item")}
    assert kids["Settings"].get("class") == "Configuration"
    assert settings == {name: (cls, value) for cls, name, _xml_type, value in SETTINGS}, settings
    assert KIT_LINE.search(sources["Loader"]).group(1) == str(version)
    return kids


# ---------- Template of the code window: scripts/DiscordCodesWindow.rbxmx ----------
# A normal ScreenGui the game owner inserts into StarterGui ONCE and restyles in Studio. It lives outside the DiscordCodes
# script, so updating DiscordCodes never touches it. The names of the parts are the contract with Client.client.luau.

WINDOW_NOTE = ("Change colors, texts, sizes and positions in the Properties window. Keep these names: Window, CodeBox, Redeem, "
               "Message (and OpenCodes, Close, Title, Hint). The text of a button (OpenCodes, Redeem, Close) is the TextLabel Label "
               "inside it: its gradient is a UIGradient on the button. Message colors its background by the result only when it "
               "has a visible background. Do not delete this window when you update DiscordCodes. "
               "The Window is hidden so it does not cover the screen in Studio: to edit it, select Window and tick Visible, then untick it again when you finish. "
               "In the game it opens with the OpenCodes button.")
# The look of the ⚙️ Manager (Client.client.luau builds the same window when there is no template)
WHITE = (255, 255, 255)
WINDOW = (30, 18, 51)
FIELD = (24, 14, 44)
FIELD_EDGE = (70, 48, 120)
GLOW = (179, 107, 255)
MUTED = (168, 151, 214)
SHADOW = (14, 8, 28)
TEXT_EDGE = (70, 24, 120)
LIGHT_EDGE = (245, 214, 255)
GRADIENTS = {"primary": ((214, 112, 255), (128, 64, 240)), "green": ((96, 226, 128), (30, 160, 72)),
             "codes": ((240, 104, 238), (136, 50, 222)),
             "red": ((255, 107, 138), (224, 51, 90))}
FONT_FREDOKA = 26  # Enum.Font.FredokaOne: the title (it has no Polish letters like ą, ę, ń)
FONT_GOTHAM_BOLD = 18  # Enum.Font.GothamBold: the icon of a button
BODY_FONT = ("rbxasset://fonts/families/Nunito.json", 900)  # Nunito Heavy: buttons, the code box, the result and the hint
ALIGN_LEFT = 0  # Enum.TextXAlignment
STROKE_BORDER = 1  # Enum.ApplyStrokeMode.Border


def _c(value: float) -> str:
    return str(round(value / 255, 6))


def gprop(kind: str, name: str, value) -> str:
    if kind == "string":
        return f'<string name="{name}">{escape(value)}</string>'
    if kind == "bool":
        return f'<bool name="{name}">{str(value).lower()}</bool>'
    if kind in ("int", "float", "token"):
        return f'<{kind} name="{name}">{value}</{kind}>'
    if kind == "UDim2":
        xs, xo, ys, yo = value
        return f'<UDim2 name="{name}"><XS>{xs}</XS><XO>{xo}</XO><YS>{ys}</YS><YO>{yo}</YO></UDim2>'
    if kind == "Vector2":
        return f'<Vector2 name="{name}"><X>{value[0]}</X><Y>{value[1]}</Y></Vector2>'
    if kind == "Color3":
        return f'<Color3 name="{name}"><R>{_c(value[0])}</R><G>{_c(value[1])}</G><B>{_c(value[2])}</B></Color3>'
    if kind == "UDim":
        return f'<UDim name="{name}"><S>{value[0]}</S><O>{value[1]}</O></UDim>'
    if kind == "ColorSequence":  # two colors, from left to right
        (r1, g1, b1), (r2, g2, b2) = value
        return f'<ColorSequence name="{name}">0 {_c(r1)} {_c(g1)} {_c(b1)} 0 1 {_c(r2)} {_c(g2)} {_c(b2)} 0 </ColorSequence>'
    if kind == "Content":  # an image: rbxassetid://...
        return f'<Content name="{name}"><url>{escape(value)}</url></Content>'
    if kind == "Rect2D":  # (min x, min y, max x, max y)
        return (f'<Rect2D name="{name}"><min><X>{value[0]}</X><Y>{value[1]}</Y></min>'
                f'<max><X>{value[2]}</X><Y>{value[3]}</Y></max></Rect2D>')
    if kind == "FontFace":
        family, weight = value
        return (f'<Font name="{name}"><Family><url>{family}</url></Family><Weight>{weight}</Weight>'
                f'<Style>Normal</Style></Font>')
    raise ValueError(kind)


def gitem(cls: str, name: str, props: list, children: str = "", depth: int = 1) -> str:
    pad = "\t" * depth
    lines = [gprop("string", "Name", name)] + [gprop(*p) for p in props]
    body = "".join(f"{pad}\t\t{line}\n" for line in lines)
    return (f'{pad}<Item class="{cls}" referent="RBX{uuid.uuid4().hex.upper()}">\n{pad}\t<Properties>\n{body}{pad}\t</Properties>\n'
            f"{children}{pad}</Item>\n")


def corner(radius: int, depth: int) -> str:
    return gitem("UICorner", "UICorner", [("UDim", "CornerRadius", (0, radius))], depth=depth)


def outline(color, thickness, depth: int) -> str:
    return gitem("UIStroke", "UIStroke", [("Color3", "Color", color), ("float", "Thickness", thickness),
                                          ("token", "ApplyStrokeMode", STROKE_BORDER)], depth=depth)


def gradient(top, bottom, depth: int) -> str:
    """From top to bottom (a UIGradient also tints its object's own text: only objects without text get one)."""
    return gitem("UIGradient", "UIGradient", [("ColorSequence", "Color", (top, bottom)), ("float", "Rotation", 90)], depth=depth)


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def text_props(text, size, color, font=None):
    """Nunito Heavy (every Polish and Spanish letter); font: another one as an Enum.Font number."""
    return [("token", "Font", font) if font else ("FontFace", "FontFace", BODY_FONT), ("string", "Text", text),
            ("float", "TextSize", size), ("Color3", "TextColor3", color)]


def box(name, color, size, position, radius, depth, extra=(), children="", transparency=0):
    props = [("UDim2", "Size", size), ("UDim2", "Position", position), ("Color3", "BackgroundColor3", color),
             ("int", "BorderSizePixel", 0), ("float", "BackgroundTransparency", transparency)] + list(extra)
    return gitem("Frame", name, props, (corner(radius, depth + 1) if radius else "") + children, depth)


def gradient_button(name, kind, text, size, position, anchor, text_size, depth, icon=None, edge=None, title_font=False, icon_size=None):
    """A button in the look of the ⚙️ Manager buttons, like gradientButton in Client.client.luau: a gradient with a light
    edge and a shine on its top half; the text (and an icon) are TextLabels named Label (and Icon) inside it."""
    inner = depth + 1
    top, bottom = GRADIENTS[kind]
    gloss = box("Gloss", WHITE, (1, -12, 0.42, 0), (0, 6, 0, 4), 10, inner, transparency=0.8)
    left = 40 if icon else 0
    icon_label = gitem("TextLabel", "Icon", [("float", "BackgroundTransparency", 1), ("UDim2", "Size", (0, 30, 1, 0)),
                                             ("UDim2", "Position", (0, 12, 0, 0))]
                       + text_props(icon, icon_size or text_size + 2, WHITE, FONT_GOTHAM_BOLD), depth=inner) if icon else ""
    label = gitem("TextLabel", "Label", [
        ("float", "BackgroundTransparency", 1), ("UDim2", "Size", (1, -(left + 12), 1, 0)), ("UDim2", "Position", (0, left + 6, 0, 0)),
        ("Color3", "TextStrokeColor3", edge or TEXT_EDGE), ("float", "TextStrokeTransparency", 1 if edge else 0.55),
    ] + text_props(text, text_size, WHITE, FONT_FREDOKA if title_font else None) + ([("token", "TextXAlignment", ALIGN_LEFT)] if icon else []),
        # the Codes button: a thicker dark outline around the letters
        gitem("UIStroke", "UIStroke", [("Color3", "Color", edge), ("float", "Thickness", 2)], depth=inner + 1) if edge else "", depth=inner)
    return gitem("TextButton", name, [
        ("UDim2", "Size", size), ("UDim2", "Position", position), ("Vector2", "AnchorPoint", anchor),
        ("Color3", "BackgroundColor3", WHITE), ("int", "BorderSizePixel", 0), ("bool", "AutoButtonColor", False), ("string", "Text", ""),
    ], corner(14, inner) + outline(edge or LIGHT_EDGE, 2 if edge else 1.5, inner) + gradient(top, bottom, inner) + gloss + icon_label + label, depth)


# The Codes button drawn in Figma (the file "CodeHatch - przyciski gry", PNGs in tools/ui_assets), the same as
# pictureButton in Client.client.luau: one finished picture (body, gift and word), no slicing; the script swaps it for
# the player's language. In Figma units the body is 410 x 150 with a margin of 30 around it.
CODES_PICTURE = "rbxassetid://127576122383640"


def picture_button(name, text, height, position, anchor, picture, body_width, depth):
    inner = depth + 1
    k = height / 150
    skin = gitem("ImageLabel", "Skin", [
        ("float", "BackgroundTransparency", 1), ("Content", "Image", picture),
        ("UDim2", "Position", (0, round(-30 * k, 2), 0, round(-30 * k, 2))), ("UDim2", "Size", (1, round(60 * k, 2), 1, round(60 * k, 2))),
    ], depth=inner)
    label = gitem("TextLabel", "Label", [
        ("float", "BackgroundTransparency", 1), ("UDim2", "Size", (1, 0, 1, 0)), ("float", "TextTransparency", 1),
    ] + text_props(text, 18, WHITE), depth=inner)
    return gitem("TextButton", name, [
        ("UDim2", "Size", (0, int(body_width * k + 0.5), 0, height)), ("UDim2", "Position", position), ("Vector2", "AnchorPoint", anchor),
        ("float", "BackgroundTransparency", 1), ("int", "BorderSizePixel", 0), ("bool", "AutoButtonColor", False), ("string", "Text", ""),
    ], skin + label, depth)


def window_xml() -> str:
    d = 2
    p = d + 2  # parts inside Window -> Panel
    title = gitem("TextLabel", "Title", [
        ("float", "BackgroundTransparency", 1), ("UDim2", "Size", (1, -90, 0, 64)), ("UDim2", "Position", (0, 22, 0, 0)),
        ("token", "TextXAlignment", ALIGN_LEFT),
    ] + text_props("REDEEM CODE", 26, WHITE, FONT_FREDOKA), depth=p)
    close = gradient_button("Close", "red", "X", (0, 40, 0, 40), (1, -54, 0, 12), (0, 0), 20, p)
    code_box = gitem("TextBox", "CodeBox", [
        ("UDim2", "Size", (1, -40, 0, 52)), ("UDim2", "Position", (0, 20, 0, 86)),
        ("Color3", "BackgroundColor3", FIELD), ("int", "BorderSizePixel", 0),
        ("string", "PlaceholderText", "Enter code"), ("Color3", "PlaceholderColor3", MUTED),
        ("bool", "ClearTextOnFocus", False),
    ] + text_props("", 22, WHITE), corner(14, p + 1) + outline(FIELD_EDGE, 2, p + 1), p)
    redeem = gradient_button("Redeem", "green", "REDEEM", (1, -40, 0, 52), (0, 20, 0, 150), (0, 0), 24, p)
    message = gitem("TextLabel", "Message", [
        ("float", "BackgroundTransparency", 0), ("Color3", "BackgroundColor3", (28, 66, 48)),
        ("UDim2", "Size", (1, -40, 0, 48)), ("UDim2", "Position", (0, 20, 0, 216)), ("bool", "TextWrapped", True),
    ] + text_props("Result of the code appears here", 17, (110, 230, 140)), corner(12, p + 1)
        + gitem("UIStroke", "Edge", [("Color3", "Color", (80, 210, 120)), ("float", "Thickness", 2), ("token", "ApplyStrokeMode", STROKE_BORDER)],
                depth=p + 1), p)
    hint = gitem("TextLabel", "Hint", [
        ("float", "BackgroundTransparency", 1), ("UDim2", "Size", (1, -40, 0, 22)), ("UDim2", "Position", (0, 20, 0, 270)),
    ] + text_props("Check back for new codes!", 15, MUTED), depth=p)
    panel = box("Panel", WHITE, (1, 0, 1, 0), (0, 0, 0, 0), 22, d + 1,
                children=gradient((40, 24, 68), (18, 10, 32), p) + outline(GLOW, 2, p) + title + close + code_box + redeem + message + hint)
    shadow = box("Shadow", SHADOW, (1, 0, 1, 0), (0, 0, 0, 6), 22, d + 1, transparency=0.45)
    window = gitem("Frame", "Window", [
        ("UDim2", "Size", (0, 380, 0, 300)), ("UDim2", "Position", (0.5, 0, 0.5, 0)), ("Vector2", "AnchorPoint", (0.5, 0.5)),
        ("float", "BackgroundTransparency", 1), ("int", "BorderSizePixel", 0), ("bool", "Visible", False),
    ], shadow + panel, d)
    button = picture_button("OpenCodes", "CODES", 54, (0, 12, 0.5, 0), (0, 0.5), CODES_PICTURE, 410, d)
    note = gitem("StringValue", "READ_ME_FIRST", [("string", "Value", WINDOW_NOTE)], depth=d)
    settings = settings_folder(d, [("StringValue", "Language", "string", "auto")])
    gui = gitem("ScreenGui", "DiscordCodesGui", [
        ("bool", "ResetOnSpawn", False), ("int", "DisplayOrder", 50), ("token", "ZIndexBehavior", 1),
    ], button + window + note + settings, 1)
    return HEADER + gui + "</roblox>\n"


def build_window(out: Path) -> dict:
    out.write_text(window_xml(), encoding="utf-8", newline="\n")
    root = ET.fromstring(out.read_text(encoding="utf-8"))
    top = root.find("Item")
    assert top.get("class") == "ScreenGui" and top.find("Properties/string[@name='Name']").text == "DiscordCodesGui"
    assert top.find("Properties/bool[@name='ResetOnSpawn']").text == "false"
    by_name = {}
    for node in top.iter("Item"):
        by_name[node.find("Properties/string[@name='Name']").text] = node.get("class")
    expected = {"OpenCodes": "TextButton", "Window": "Frame", "Title": "TextLabel", "Close": "TextButton", "CodeBox": "TextBox",
                "Hint": "TextLabel", "Label": "TextLabel", "Skin": "ImageLabel", "Redeem": "TextButton", "Message": "TextLabel",
                "Settings": "Configuration", "Language": "StringValue"}
    for name, cls in expected.items():
        assert by_name.get(name) == cls, (name, by_name.get(name))
    window_node = [n for n in top.findall("Item") if n.find("Properties/string[@name='Name']").text == "Window"][0]
    inside = {n.find("Properties/string[@name='Name']").text for n in window_node.iter("Item")}
    assert {"CodeBox", "Redeem", "Message"} <= inside
    return by_name


# ---------- Template of the game catalog: scripts/DiscordCatalog.rbxmx ----------

def catalog_source() -> str:
    text = CATALOG_SOURCE.read_text(encoding="utf-8").replace("\r\n", "\n")
    if "]]>" in text:
        sys.exit("DiscordCatalog.luau: contains the sequence ']]>' which is not allowed in CDATA")
    return text


def build_catalog(out: Path) -> str:
    source = catalog_source()
    out.write_text(HEADER + item("ModuleScript", "DiscordCatalog", source) + "</roblox>\n", encoding="utf-8", newline="\n")
    top = ET.fromstring(out.read_text(encoding="utf-8")).find("Item")
    assert top.get("class") == "ModuleScript" and top.find("Properties/string[@name='Name']").text == "DiscordCatalog"
    assert top.find("Properties/ProtectedString[@name='Source']").text == source
    assert "Catalog.Currencies" in source and source.rstrip().endswith("return Catalog")
    return source


def build_settings(out: Path) -> str:
    """The settings template: every name in it must be one of SETTINGS (the Loader refuses other names)."""
    source = SETTINGS_SOURCE.read_text(encoding="utf-8").replace("\r\n", "\n")
    if "]]>" in source:
        sys.exit("DiscordSettings.luau: contains the sequence ']]>' which is not allowed in CDATA")
    names = set(re.findall(r"^\t([A-Za-z]+) = ", source, re.M))
    assert names == {name for _cls, name, _xml_type, _value in SETTINGS}, names
    out.write_text(HEADER + item("ModuleScript", "DiscordSettings", source) + "</roblox>\n", encoding="utf-8", newline="\n")
    top = ET.fromstring(out.read_text(encoding="utf-8")).find("Item")
    assert top.find("Properties/ProtectedString[@name='Source']").text == source
    return source


def main() -> int:
    version = stamp_version()
    sources = {
        "Core": read_source("Core.luau"),
        "Client": read_source("Client.client.luau"),
        "Loader": read_source("Loader.server.luau"),
        "Report": read_source("Report.luau"),
        "Live": read_source("Live.luau"),
        "LiveClient": read_source("LiveClient.client.luau"),
        "Control": read_source("Control.luau"),
        "Effects": read_source("Effects.luau"),
        "Manager": read_source("Manager.luau"),
        "ManagerClient": read_source("ManagerClient.client.luau"),
    }
    parts = build(OUT, sources, version)
    window = build_window(OUT_WINDOW)
    build_catalog(OUT_CATALOG)
    build_settings(OUT_SETTINGS)
    print(f"Saved {OUT.name} ({OUT.stat().st_size // 1024} KB), file version {version}. Parts: {sorted(parts)}. "
          f"Window template: {OUT_WINDOW.name} ({OUT_WINDOW.stat().st_size // 1024} KB, {len(window)} parts). "
          f"Templates: {OUT_CATALOG.name}, {OUT_SETTINGS.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
