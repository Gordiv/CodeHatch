--!nonstrict
--[[
	DiscordLiveClient  (LocalScript)

	What players see from the Live module: announcements at the top of the screen, active events as round icons with
	the multiplier and the time left (hovering or tapping one tells what the event does), egg results and gifts.
	Everything is created from code. In ServerScriptService -> DiscordSettings:
	- Language       auto, en, pl or es
	- EventPosition  where the event icons are: BottomRight (default), BottomLeft, TopRight, TopLeft, Right, Left, Top, Bottom
	- EventIcons     your icons, e.g. "Coins=💰, Strength=💪, EXP=⭐, Luck=🍀" (an emoji or rbxassetid://123 of an image),
	                 by the multiplied currency, EXP, Luck, All (every currency) or the event's name
	- EventEffects   the animations of events (the Effects module inside this script): "full", "light" or "off"
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local UserInputService = game:GetService("UserInputService")
local Workspace = game:GetService("Workspace")

local GOLD_COLOR = Color3.fromRGB(255, 200, 61)
local SUCCESS_COLOR = Color3.fromRGB(70, 209, 106)
local ERROR_COLOR = Color3.fromRGB(255, 92, 103)

local settingsFolder = script:FindFirstChild("Settings")
local function setting(name, default)
	local value = settingsFolder and settingsFolder:FindFirstChild(name)
	if value == nil then
		return default
	end
	return value.Value
end

local TEXTS = {
	en = {
		exp = "EXP",
		luck = "Luck",
		all = "all currencies",
		hatch = "You hatched %s!",
		rare = "Rare!",
		gift = "Gift from the developers",
		poor = "Not enough %s (you need %s).",
		closed = "This egg is not available anymore.",
		unsupported = "This egg isn't ready in this game yet.",
		restricted = "Eggs aren't available for your account (Roblox rules in your country).",
		try_again = "Couldn't open the egg right now. Try again in a moment.",
		chances_changed = "The chances of this egg just changed. Check them and try again.",
		error = "Something went wrong. Your currency was refunded.",
		event = "Event",
		startsIn = "Starts in",
		serverWide = "Server-wide event",
		lasts = "Lasts %s",
		go = "START!",
		eventStarts = "EVENT STARTS!",
		ends = "Ends in %s",
		more_currency = "%s more %s",
		more_all = "%s more of every currency",
		more_exp = "%s more EXP",
		more_luck = "Rare pets %s more often",
	},
	pl = {
		exp = "EXP",
		luck = "Szczęście",
		all = "wszystkie waluty",
		hatch = "Nowy zwierzak: %s!",
		rare = "Rzadki!",
		gift = "Prezent od twórców gry",
		poor = "Za mało %s (potrzebujesz %s).",
		closed = "To jajko nie jest już dostępne.",
		unsupported = "To jajko nie jest jeszcze gotowe w tej grze.",
		restricted = "Jajka nie są dostępne dla Twojego konta (zasady Robloxa w Twoim kraju).",
		try_again = "Nie udało się teraz otworzyć jajka. Spróbuj za chwilę.",
		chances_changed = "Szanse tego jajka właśnie się zmieniły. Sprawdź je i spróbuj jeszcze raz.",
		error = "Coś poszło nie tak. Waluta została zwrócona.",
		event = "Event",
		startsIn = "Start za",
		serverWide = "Event na całym serwerze",
		lasts = "Trwa %s",
		go = "START!",
		eventStarts = "EVENT STARTUJE!",
		ends = "Koniec za %s",
		more_currency = "%s więcej: %s",
		more_all = "%s więcej każdej waluty",
		more_exp = "%s więcej EXP",
		more_luck = "Rzadkie zwierzaki %s częściej",
	},
	es = {
		exp = "EXP",
		luck = "Suerte",
		all = "todas las monedas",
		hatch = "¡Has sacado %s!",
		rare = "¡Rara!",
		gift = "Regalo de los creadores",
		poor = "No tienes suficiente %s (necesitas %s).",
		closed = "Este huevo ya no está disponible.",
		unsupported = "Este huevo aún no está listo en este juego.",
		restricted = "Los huevos no están disponibles para tu cuenta (normas de Roblox en tu país).",
		try_again = "No se pudo abrir el huevo ahora. Inténtalo de nuevo en un momento.",
		chances_changed = "Las probabilidades de este huevo acaban de cambiar. Revísalas e inténtalo otra vez.",
		error = "Algo salió mal. Se te devolvió la moneda.",
		event = "Evento",
		startsIn = "Empieza en",
		serverWide = "Evento para todo el servidor",
		lasts = "Dura %s",
		go = "¡YA!",
		eventStarts = "¡EMPIEZA EL EVENTO!",
		ends = "Termina en %s",
		more_currency = "%s más de %s",
		more_all = "%s más de todas las monedas",
		more_exp = "%s más EXP",
		more_luck = "Mascotas raras %s más a menudo",
	},
}

local player = Players.LocalPlayer
local T
-- live: the code remote's attribute set by the ⚙️ Manager while the game runs (nil = the Settings folder)
local function readLanguage(live)
	local language = string.lower(tostring(live or setting("Language", "auto")))
	if language == "auto" then
		language = string.sub(string.lower(tostring(player.LocaleId or "en")), 1, 2)
	end
	T = TEXTS[language] or TEXTS.en
end
readLanguage()

-- By name AND class: another system's object with the same name must not be used by mistake
local function findRemote(name, className, timeout)
	local deadline = os.clock() + timeout
	repeat
		for _, child in ipairs(ReplicatedStorage:GetChildren()) do
			if child.Name == name and child:IsA(className) then
				return child
			end
		end
		task.wait(0.5)
	until os.clock() > deadline
	return nil
end

local remote = findRemote("DiscordLiveEvent", "RemoteEvent", 30)
if not remote then
	warn("[DiscordLive] DiscordLiveEvent was not found. Is the DiscordCodes script in ServerScriptService?")
	return
end
readLanguage(remote:GetAttribute("Language"))

-- The animations of events (Effects, inside this script); a game without it shows only the icons
local Effects = nil
do
	local module = script:FindFirstChild("Effects")
	if module then
		local ok, result = pcall(require, module)
		if ok then
			Effects = result
		else
			warn("[DiscordLive] The event animations could not start: " .. tostring(result))
		end
	end
end

local function formatNumber(value)
	local digits = tostring(math.floor(tonumber(value) or 0))
	local grouped = ""
	while #digits > 3 do
		grouped = "," .. string.sub(digits, -3) .. grouped
		digits = string.sub(digits, 1, -4)
	end
	return digits .. grouped
end

-- The same precision as the egg's stand (Roblox: rounded only to four decimal places below the first non-zero digit)
local function chanceText(chance)
	chance = tonumber(chance) or 0
	if chance <= 0 then
		return "0%"
	end
	local decimals = math.max(0, 4 - math.floor(math.log(chance, 10)))
	local text = string.format("%." .. decimals .. "f", chance)
	if string.find(text, ".", 1, true) then
		text = string.gsub(text, "0+$", "")
		text = string.gsub(text, "%.$", "")
	end
	return text .. "%"
end

local function timeLeft(seconds)
	seconds = math.max(0, math.floor(seconds))
	local hours = math.floor(seconds / 3600)
	local minutes = math.floor((seconds % 3600) / 60)
	local secs = seconds % 60
	if hours >= 24 then
		return math.floor(hours / 24) .. "d " .. (hours % 24) .. "h"
	elseif hours > 0 then
		return hours .. "h " .. string.format("%02d", minutes) .. "m"
	end
	return minutes .. ":" .. string.format("%02d", secs)
end

local function factorText(value)
	local n = tonumber(value) or 1
	if n == math.floor(n) then
		return tostring(math.floor(n)) .. "x"
	end
	return tostring(n) .. "x"
end

-- What an event does, one entry per multiplier: the named currencies first (by name), then EXP, Luck, every currency
local function eventParts(multipliers)
	local parts = {}
	if type(multipliers) == "table" then
		for name, value in pairs(multipliers) do
			local factor = tonumber(value)
			if factor and factor > 0 and type(name) == "string" then
				if name == "exp" then
					table.insert(parts, { kind = "exp", order = 2, name = "", factor = factor })
				elseif name == "luck" then
					table.insert(parts, { kind = "luck", order = 3, name = "", factor = factor })
				elseif string.sub(name, 1, 9) == "currency:" then
					local currency = string.sub(name, 10)
					if currency == "*" then
						table.insert(parts, { kind = "all", order = 4, name = "", factor = factor })
					elseif currency ~= "" then
						table.insert(parts, { kind = "currency", order = 1, name = currency, factor = factor })
					end
				end
			end
		end
	end
	table.sort(parts, function(a, b)
		if a.order ~= b.order then
			return a.order < b.order
		end
		return a.name < b.name
	end)
	return parts
end

local function partText(part)
	local factor = factorText(part.factor)
	if part.kind == "currency" then
		return string.format(T.more_currency, factor, part.name)
	elseif part.kind == "exp" then
		return string.format(T.more_exp, factor)
	elseif part.kind == "luck" then
		return string.format(T.more_luck, factor)
	end
	return string.format(T.more_all, factor)
end

-- The icon of an event: EventIcons in DiscordSettings ("Coins=💰, Strength=💪, Luck=🍀", by the event's name or its
-- first multiplier: a currency, EXP, Luck or All), else a default one. An emoji, or rbxassetid://123 for an image.
local DEFAULT_ICONS = { currency = "💰", all = "💰", exp = "⭐", luck = "🍀" }
local function normalize(text)
	return string.lower((string.gsub(tostring(text or ""), "[^%w]", "")))
end
local customIcons = {}
for entry in string.gmatch(tostring(setting("EventIcons", "")), "[^,;\n]+") do
	local name, icon = string.match(entry, "^%s*(.-)%s*=%s*(.-)%s*$")
	if name and icon and normalize(name) ~= "" and icon ~= "" then
		customIcons[normalize(name)] = icon
	end
end
local function iconFor(event, first)
	local byName = normalize(event.name)
	local assets = Effects and type(event.animation) == "string" and Effects.Assets[event.animation]
	if byName ~= "" and customIcons[byName] then
		return customIcons[byName]
	elseif assets and assets.Icon then -- an event with an animation has that animation's own icon
		return assets.Icon
	elseif not first then
		return "⚡"
	elseif first.kind == "currency" then
		return customIcons[normalize(first.name)] or DEFAULT_ICONS.currency
	elseif first.kind == "exp" then
		return customIcons.exp or customIcons.xp or DEFAULT_ICONS.exp
	end
	return customIcons[first.kind] or DEFAULT_ICONS[first.kind]
end

local function rewardText(reward)
	local parts = {}
	if type(reward) == "table" then
		if type(reward.currency) == "table" then
			table.insert(parts, "+" .. formatNumber(reward.currency.amount) .. " " .. tostring(reward.currency.name))
		end
		if reward.exp then
			table.insert(parts, "+" .. formatNumber(reward.exp) .. " EXP")
		end
		if type(reward.item) == "table" then
			table.insert(parts, tostring(reward.item.name))
		end
	end
	return table.concat(parts, ", ")
end

-- ---------- Look (the same style as the code window: thick dark outlines, rounded, chunky) ----------
local WHITE = Color3.fromRGB(255, 255, 255)
local SHADOW = Color3.fromRGB(24, 12, 46)
local TEXT_EDGE = Color3.fromRGB(70, 24, 120) -- a soft outline around white letters on a gradient
local TITLE_FONT = Font.new("rbxasset://fonts/families/FredokaOne.json")
-- Fredoka One has no Polish letters (ą, ę, ń...): texts with such letters use Nunito, which has them all
local BODY_FONT = Font.new("rbxasset://fonts/families/Nunito.json", Enum.FontWeight.Heavy)
local BOLD_FONT = Font.new("rbxasset://fonts/families/Nunito.json", Enum.FontWeight.Bold)
-- The event icons have the look of the Codes and ⚙️ Manager buttons: a pink-violet gradient with a light edge
local PINK, VIOLET = Color3.fromRGB(224, 107, 255), Color3.fromRGB(138, 68, 255)
local LIGHT_EDGE = Color3.fromRGB(245, 214, 255)
local CARD = Color3.fromRGB(30, 18, 51)
local GLOW = Color3.fromRGB(179, 107, 255)
local SOFT = Color3.fromRGB(201, 184, 255)
local function fontFor(text)
	return string.find(text, "[\196-\197]") and BODY_FONT or TITLE_FONT
end

local function rounded(instance, radius)
	local corner = Instance.new("UICorner")
	corner.CornerRadius = UDim.new(0, radius)
	corner.Parent = instance
end

local function outline(instance, color, thickness)
	local stroke = Instance.new("UIStroke")
	stroke.Color = color
	stroke.Thickness = thickness
	stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	stroke.Parent = instance
	return stroke
end

-- From top to bottom (a UIGradient also tints its object's own text: only frames without text get one)
local function gradient(instance, top, bottom)
	local shade = Instance.new("UIGradient")
	shade.Color = ColorSequence.new(top, bottom)
	shade.Rotation = 90
	shade.Parent = instance
	return shade
end

-- ---------- The new look: navy panels, thin gold borders, a soft shine (the mockup of 3.11) ----------
local NAVY_TOP = Color3.fromRGB(36, 44, 92)
local NAVY = Color3.fromRGB(20, 26, 58)
local NAVY_DEEP = Color3.fromRGB(10, 13, 34)
local GOLD_LIGHT = Color3.fromRGB(255, 233, 150)
local GOLD_MID = Color3.fromRGB(245, 184, 52)
local GOLD_DARK = Color3.fromRGB(176, 112, 18)
local GOLD_EDGE = Color3.fromRGB(222, 178, 82) -- the thin border of every panel
local BROWN = Color3.fromRGB(70, 40, 6) -- text on gold
local RED_RING = Color3.fromRGB(255, 84, 96)
local ORB_TOP = Color3.fromRGB(128, 94, 238)
local ORB_BOTTOM = Color3.fromRGB(34, 20, 92)

-- Capital letters also for Polish and Spanish letters (string.upper changes only a-z: "Tęczowe" would be "TęCZOWE")
local CAPITALS = { ["ą"] = "Ą", ["ć"] = "Ć", ["ę"] = "Ę", ["ł"] = "Ł", ["ń"] = "Ń", ["ó"] = "Ó", ["ś"] = "Ś", ["ź"] = "Ź", ["ż"] = "Ż",
	["á"] = "Á", ["é"] = "É", ["í"] = "Í", ["ú"] = "Ú", ["ü"] = "Ü", ["ñ"] = "Ñ" }
local function upper(text)
	return (string.gsub(string.upper(tostring(text)), "[\195\196\197][\128-\191]", function(letter)
		return CAPITALS[letter] or letter
	end))
end

local function sequence(...)
	local keys = {}
	for _, key in ipairs({ ... }) do
		table.insert(keys, ColorSequenceKeypoint.new(key[1], key[2]))
	end
	return ColorSequence.new(keys)
end

-- Gold from light to dark, top to bottom (a frame without text only: a UIGradient tints the text of its object too)
local function goldFill(instance)
	local shade = Instance.new("UIGradient")
	shade.Color = sequence({ 0, GOLD_LIGHT }, { 0.45, GOLD_MID }, { 1, GOLD_DARK })
	shade.Rotation = 90
	shade.Parent = instance
	return shade
end

local function circle(parent, size, position, color, name)
	local disc = Instance.new("Frame")
	disc.Name = name or "Disc"
	disc.AnchorPoint = Vector2.new(0.5, 0.5)
	disc.Position = position or UDim2.fromScale(0.5, 0.5)
	disc.Size = UDim2.fromOffset(size, size)
	disc.BackgroundColor3 = color or WHITE
	disc.BorderSizePixel = 0
	disc.Parent = parent
	rounded(disc, size)
	return disc
end

-- A ring that fills clockwise from the top (the time left). It is a gold pie: a smooth round disc in two clipped
-- halves, each with a half transparent gradient that turns with the progress. What is drawn after it in the middle
-- (a darker disc) leaves only its edge visible, so the ring has smooth round edges. ring.set(0..1), ring.color(Color3)
local function makeRing(parent, size, thickness, color)
	local ring = Instance.new("Frame")
	ring.Name = "Ring"
	ring.BackgroundTransparency = 1
	ring.AnchorPoint = Vector2.new(0.5, 0.5)
	ring.Position = UDim2.fromScale(0.5, 0.5)
	ring.Size = UDim2.fromOffset(size, size)
	ring.Parent = parent
	local discs, shades = {}, {}
	for i = 1, 2 do
		local half = Instance.new("Frame")
		half.Name = i == 1 and "Right" or "Left"
		half.BackgroundTransparency = 1
		half.ClipsDescendants = true
		half.Size = UDim2.fromScale(0.5, 1)
		half.Position = UDim2.fromScale(i == 1 and 0.5 or 0, 0)
		half.Parent = ring
		local disc = Instance.new("Frame")
		disc.Name = "Disc"
		disc.BackgroundColor3 = color
		disc.BorderSizePixel = 0
		disc.Size = UDim2.fromScale(2, 1)
		disc.Position = UDim2.fromScale(i == 1 and -1 or 0, 0)
		disc.Parent = half
		local corner = Instance.new("UICorner")
		corner.CornerRadius = UDim.new(0.5, 0)
		corner.Parent = disc
		local shade = Instance.new("UIGradient")
		shade.Transparency = NumberSequence.new({
			NumberSequenceKeypoint.new(0, 0), NumberSequenceKeypoint.new(0.5, 0),
			NumberSequenceKeypoint.new(0.501, 1), NumberSequenceKeypoint.new(1, 1),
		})
		shade.Parent = disc
		discs[i], shades[i] = disc, shade
	end
	local api = { frame = ring }
	function api.set(progress)
		local angle = math.max(0, math.min(1, progress)) * 360
		shades[1].Rotation = math.min(angle, 180)
		shades[2].Rotation = math.max(180, math.min(angle, 360))
	end
	function api.color(value)
		discs[1].BackgroundColor3 = value
		discs[2].BackgroundColor3 = value
	end
	api.set(1)
	return api
end

local function putIcon(holder, icon)
	for _, child in ipairs(holder:GetChildren()) do
		if child.Name == "Icon" then
			child:Destroy()
		end
	end
	local picture = string.match(icon, "^%d+$") and ("rbxassetid://" .. icon) or (string.find(icon, "^rbxasset") and icon)
	local object = Instance.new(picture and "ImageLabel" or "TextLabel")
	object.Name = "Icon"
	object.BackgroundTransparency = 1
	object.AnchorPoint = Vector2.new(0.5, 0.5)
	object.Position = UDim2.fromScale(0.5, 0.5)
	object.Size = UDim2.fromScale(picture and 0.92 or 0.62, picture and 0.92 or 0.62)
	if picture then
		object.Image = picture
		object.ScaleType = Enum.ScaleType.Fit
	else
		object.Text = icon
		object.TextScaled = true
		object.FontFace = BODY_FONT
	end
	object.Parent = holder
end

-- A violet orb in a thin gold ring (the icon of an event); returns the orb, the place of its Icon
local function iconCircle(parent, size, position, anchor)
	local ringFrame = Instance.new("Frame")
	ringFrame.Name = "IconCircle"
	ringFrame.Size = UDim2.fromOffset(size, size)
	ringFrame.Position = position
	ringFrame.AnchorPoint = anchor or Vector2.new(0, 0)
	ringFrame.BackgroundColor3 = WHITE
	ringFrame.BorderSizePixel = 0
	ringFrame.Parent = parent
	rounded(ringFrame, size)
	goldFill(ringFrame)
	local orb = circle(ringFrame, size - 6, nil, WHITE, "Orb")
	gradient(orb, ORB_TOP, ORB_BOTTOM)
	outline(orb, Color3.fromRGB(14, 8, 40), 1.5)
	return orb
end

local function label(parent, name, size, position, textSize, color, font)
	local text = Instance.new("TextLabel")
	text.Name = name
	text.BackgroundTransparency = 1
	text.Size = size
	text.Position = position
	text.TextSize = textSize
	text.TextColor3 = color
	text.FontFace = font
	text.TextXAlignment = Enum.TextXAlignment.Left
	text.TextTruncate = Enum.TextTruncate.AtEnd
	text.Parent = parent
	return text
end

local function durationText(seconds)
	seconds = math.floor((tonumber(seconds) or 0) + 0.5)
	if seconds >= 86400 then
		return math.floor(seconds / 86400) .. " d"
	elseif seconds >= 3600 then
		return math.floor(seconds / 3600) .. " h"
	elseif seconds >= 60 then
		return math.floor(seconds / 60) .. " min"
	end
	return seconds .. " s"
end

-- How much of an event is left, 0..1 (nil when its length is unknown)
local function eventProgress(event, now)
	local ends = tonumber(event.ends_at) or 0
	local starts = tonumber(event.starts_at) or 0
	local total = ends - starts
	if starts <= 0 or total <= 0 then
		return nil, nil
	end
	return math.max(0, math.min(1, (ends - now) / total)), total
end

local playerGui = player:WaitForChild("PlayerGui")
local old = playerGui:FindFirstChild("DiscordLiveGui")
if old then
	old:Destroy()
end
local screenGui = Instance.new("ScreenGui")
screenGui.Name = "DiscordLiveGui"
screenGui.ResetOnSpawn = false
screenGui.DisplayOrder = 60
screenGui.IgnoreGuiInset = false
screenGui.Parent = playerGui

-- A place's name in lower case and the pixels to move it by: "Top" or "Top 0,40" (40 px lower)
local function readPlace(value)
	local name, x, y = string.match(tostring(value or ""), "^%s*(%a+)%s*([%+%-]?%d*)%s*,?%s*([%+%-]?%d*)%s*$")
	local function pixels(text)
		return math.max(-2000, math.min(2000, tonumber(text) or 0))
	end
	return name and string.lower(name) or "", pixels(x), pixels(y)
end

-- A setting as it works now: the ⚙️ Manager's change on the remote first (while the game runs), else the Settings folder
local function live(name, default)
	local value = remote:GetAttribute(name)
	if value ~= nil then
		return value
	end
	return setting(name, default)
end

-- Two things in the same place: the second one moves away from the screen's edge
local function apart(anchor, amount)
	return anchor.Y == 1 and -amount or amount
end

-- Announcement banner (AnnouncementPosition, top center by default): a purple chunky bar with a darker 3D edge under
-- it, slides in from the nearest edge (from the top in the middle of the screen)
local BANNER_PLACES = {
	top = { UDim2.new(0.5, 0, 0, 12), Vector2.new(0.5, 0) },
	bottom = { UDim2.new(0.5, 0, 1, -110), Vector2.new(0.5, 1) },
	center = { UDim2.fromScale(0.5, 0.5), Vector2.new(0.5, 0.5) },
	left = { UDim2.new(0, 12, 0.5, 0), Vector2.new(0, 0.5) },
	right = { UDim2.new(1, -12, 0.5, 0), Vector2.new(1, 0.5) },
	topleft = { UDim2.fromOffset(12, 12), Vector2.new(0, 0) },
	topright = { UDim2.new(1, -12, 0, 64), Vector2.new(1, 0) }, -- below the ⚙️ Manager button
	bottomleft = { UDim2.new(0, 12, 1, -12), Vector2.new(0, 1) },
	bottomright = { UDim2.new(1, -12, 1, -12), Vector2.new(1, 1) },
}
local HIDDEN = UDim2.new(0.5, 0, 0, -100)
local SHOWN = UDim2.new(0.5, 0, 0, 12)
local bannerHolder = Instance.new("Frame")
bannerHolder.Name = "AnnouncementHolder"
bannerHolder.AnchorPoint = Vector2.new(0.5, 0)
bannerHolder.Position = HIDDEN
bannerHolder.Size = UDim2.new(0.6, 0, 0, 62)
bannerHolder.BackgroundTransparency = 1
bannerHolder.Visible = false
bannerHolder.Parent = screenGui
local bannerWidth = Instance.new("UISizeConstraint")
bannerWidth.MaxSize = Vector2.new(640, 62)
bannerWidth.Parent = bannerHolder
-- the look of the Codes and ⚙️ Manager buttons: a soft shadow, a pink-violet gradient with a light edge and a shine,
-- the 📢 icon in a light circle and the text
local bannerShadow = Instance.new("Frame")
bannerShadow.Name = "Shadow"
bannerShadow.Size = UDim2.fromScale(1, 1)
bannerShadow.Position = UDim2.fromOffset(0, 5)
bannerShadow.BackgroundColor3 = SHADOW
bannerShadow.BackgroundTransparency = 0.5
bannerShadow.Parent = bannerHolder
rounded(bannerShadow, 18)
local bannerCard = Instance.new("Frame")
bannerCard.Name = "Card"
bannerCard.Size = UDim2.fromScale(1, 1)
bannerCard.BackgroundColor3 = WHITE
bannerCard.Parent = bannerHolder
rounded(bannerCard, 18)
outline(bannerCard, LIGHT_EDGE, 1.5)
gradient(bannerCard, Color3.fromRGB(236, 96, 214), Color3.fromRGB(132, 70, 245)).Rotation = 0
local bannerGloss = Instance.new("Frame")
bannerGloss.Name = "Gloss"
bannerGloss.Size = UDim2.new(1, -16, 0.42, 0)
bannerGloss.Position = UDim2.fromOffset(8, 4)
bannerGloss.BackgroundColor3 = WHITE
bannerGloss.BackgroundTransparency = 0.82
bannerGloss.Parent = bannerCard
rounded(bannerGloss, 12)
local bannerIcon = Instance.new("TextLabel")
bannerIcon.Name = "Icon"
bannerIcon.AnchorPoint = Vector2.new(0, 0.5)
bannerIcon.Position = UDim2.new(0, 10, 0.5, 0)
bannerIcon.Size = UDim2.fromOffset(42, 42)
bannerIcon.BackgroundColor3 = Color3.fromRGB(255, 120, 196)
bannerIcon.BackgroundTransparency = 0
bannerIcon.Text = "📢"
bannerIcon.TextSize = 24
bannerIcon.Parent = bannerCard
rounded(bannerIcon, 21)
outline(bannerIcon, LIGHT_EDGE, 1.5)
local banner = Instance.new("TextLabel")
banner.Name = "Announcement"
banner.Position = UDim2.fromOffset(62, 0)
banner.Size = UDim2.new(1, -76, 1, 0)
banner.BackgroundTransparency = 1
banner.FontFace = TITLE_FONT
banner.TextSize = 22
banner.TextWrapped = true
banner.TextXAlignment = Enum.TextXAlignment.Left
banner.TextColor3 = WHITE
banner.TextStrokeColor3 = TEXT_EDGE
banner.TextStrokeTransparency = 0.45
banner.Parent = bannerCard
local bannerSize = Instance.new("UITextSizeConstraint")
bannerSize.MaxTextSize = 24
bannerSize.MinTextSize = 12
bannerSize.Parent = banner
banner.TextScaled = true

local announcements = {}
local showingAnnouncement = false

local function placeBanner()
	local key, x, y = readPlace(live("AnnouncementPosition", "Top"))
	local place = BANNER_PLACES[key] or BANNER_PLACES.top
	SHOWN = place[1] + UDim2.fromOffset(x, y)
	HIDDEN = SHOWN + UDim2.fromOffset(0, place[2].Y == 1 and 220 or place[2].Y == 0 and -220 or -40)
	bannerHolder.AnchorPoint = place[2]
	bannerHolder.Position = showingAnnouncement and SHOWN or HIDDEN
end
placeBanner()

local function nextAnnouncement()
	if showingAnnouncement or #announcements == 0 then
		return
	end
	showingAnnouncement = true
	local item = table.remove(announcements, 1)
	banner.Text = item.text
	banner.FontFace = fontFor(item.text)
	bannerHolder.Position = HIDDEN
	bannerHolder.Visible = true
	TweenService:Create(bannerHolder, TweenInfo.new(0.45, Enum.EasingStyle.Back, Enum.EasingDirection.Out), { Position = SHOWN }):Play()
	task.delay(item.seconds, function()
		local tween = TweenService:Create(bannerHolder, TweenInfo.new(0.3, Enum.EasingStyle.Quad, Enum.EasingDirection.In), { Position = HIDDEN })
		tween:Play()
		tween.Completed:Wait()
		bannerHolder.Visible = false
		showingAnnouncement = false
		nextAnnouncement()
	end)
end

-- Active events: a row of round icons (bottom right by default, EventPosition in DiscordSettings). Each one has the
-- event's icon, its biggest multiplier ("2x") and the time left; hovering it (a tap on a phone) shows what it does.
local EVENT_PLACES = {
	bottomright = { UDim2.new(1, -16, 1, -16), Vector2.new(1, 1) },
	bottomleft = { UDim2.new(0, 16, 1, -16), Vector2.new(0, 1) },
	topright = { UDim2.new(1, -16, 0, 64), Vector2.new(1, 0) }, -- below the ⚙️ Manager button
	topleft = { UDim2.fromOffset(16, 16), Vector2.new(0, 0) },
	right = { UDim2.new(1, -16, 0.5, 0), Vector2.new(1, 0.5) },
	left = { UDim2.new(0, 16, 0.5, 0), Vector2.new(0, 0.5) },
	top = { UDim2.new(0.5, 0, 0, 84), Vector2.new(0.5, 0) }, -- below the announcements
	bottom = { UDim2.new(0.5, 0, 1, -16), Vector2.new(0.5, 1) },
	center = { UDim2.fromScale(0.5, 0.5), Vector2.new(0.5, 0.5) },
}
local eventsHolder = Instance.new("Frame")
eventsHolder.Name = "Events"
eventsHolder.BackgroundTransparency = 1
eventsHolder.Size = UDim2.fromOffset(460, 104)
eventsHolder.Parent = screenGui
local eventsRow = Instance.new("Frame")
eventsRow.Name = "Row"
eventsRow.BackgroundTransparency = 1
eventsRow.Size = UDim2.fromScale(1, 1)
eventsRow.Parent = eventsHolder
local layout = Instance.new("UIListLayout")
layout.FillDirection = Enum.FillDirection.Horizontal
layout.SortOrder = Enum.SortOrder.LayoutOrder
layout.VerticalAlignment = Enum.VerticalAlignment.Bottom
layout.Padding = UDim.new(0, 10)
layout.Parent = eventsRow

-- The code window's remote: its ButtonPosition (also changed in the ⚙️ Manager) keeps the icons off the Codes button
local codesRemote = nil
for _, child in ipairs(ReplicatedStorage:GetChildren()) do
	if child.Name == "DiscordCodesRedeem" and child:IsA("RemoteFunction") then
		codesRemote = child
	end
end

-- Where the Codes button is (also changed in the ⚙️ Manager while the game runs)
local function codesPlace()
	local live = codesRemote and codesRemote:GetAttribute("ButtonPosition")
	return (readPlace(live or setting("ButtonPosition", "Left")))
end

local function placeEvents()
	local key, x, y = readPlace(live("EventPosition", "BottomRight"))
	local place = EVENT_PLACES[key] or EVENT_PLACES.bottomright
	local anchor = place[2]
	local push = 0
	if codesPlace() == key then
		push = apart(anchor, 70)
	end
	-- a phone has the thumbstick and the jump button in the bottom corners
	if anchor.Y == 1 and UserInputService.TouchEnabled and not UserInputService.KeyboardEnabled then
		push = push - 130
	end
	eventsHolder.AnchorPoint = anchor
	eventsHolder.Position = place[1] + UDim2.fromOffset(x, y + push)
	layout.HorizontalAlignment = anchor.X == 1 and Enum.HorizontalAlignment.Right
		or anchor.X == 0 and Enum.HorizontalAlignment.Left
		or Enum.HorizontalAlignment.Center
	layout.VerticalAlignment = anchor.Y == 0 and Enum.VerticalAlignment.Top or Enum.VerticalAlignment.Bottom
end
placeEvents()

-- What an event does: a navy card ABOVE the icon (below it when the icons are at the top), a gold arrow to the medallion
local tipArrow = Instance.new("Frame")
tipArrow.Name = "EventTipArrow"
tipArrow.Visible = false
tipArrow.AnchorPoint = Vector2.new(0.5, 0.5)
tipArrow.Size = UDim2.fromOffset(20, 20)
tipArrow.Rotation = 45
tipArrow.BackgroundColor3 = GOLD_EDGE
tipArrow.BorderSizePixel = 0
tipArrow.Parent = eventsHolder
local tip = Instance.new("Frame")
tip.Name = "EventTip"
tip.Visible = false
tip.BackgroundColor3 = WHITE
tip.Size = UDim2.fromOffset(262, 0)
tip.AutomaticSize = Enum.AutomaticSize.Y
tip.Parent = eventsHolder
rounded(tip, 14)
outline(tip, GOLD_EDGE, 2)
gradient(tip, NAVY_TOP, NAVY_DEEP)
local tipPadding = Instance.new("UIPadding")
tipPadding.PaddingTop = UDim.new(0, 12)
tipPadding.PaddingBottom = UDim.new(0, 10)
tipPadding.PaddingLeft = UDim.new(0, 12)
tipPadding.PaddingRight = UDim.new(0, 12)
tipPadding.Parent = tip
local tipLayout = Instance.new("UIListLayout")
tipLayout.SortOrder = Enum.SortOrder.LayoutOrder
tipLayout.Padding = UDim.new(0, 8)
tipLayout.Parent = tip
local function setTipVisible(value)
	tip.Visible = value
	tipArrow.Visible = value
end
local function tipRow(order, height)
	local row = Instance.new("Frame")
	row.LayoutOrder = order
	row.BackgroundTransparency = 1
	row.Size = UDim2.new(1, 0, 0, height)
	row.Parent = tip
	return row
end
local tipHead = tipRow(1, 40)
local tipIcon = iconCircle(tipHead, 40, UDim2.fromOffset(0, 0))
local tipTitle = label(tipHead, "Title", UDim2.new(1, -50, 0, 22), UDim2.fromOffset(50, 0), 18, WHITE, BODY_FONT)
local tipSub = label(tipHead, "Sub", UDim2.new(1, -50, 0, 16), UDim2.fromOffset(50, 23), 13, SOFT, BOLD_FONT)
-- the gold chip with what the event gives
local tipChip = Instance.new("Frame")
tipChip.Name = "Chip"
tipChip.LayoutOrder = 2
tipChip.BackgroundColor3 = WHITE
tipChip.Size = UDim2.new(1, 0, 0, 0)
tipChip.Parent = tip
rounded(tipChip, 15)
goldFill(tipChip)
outline(tipChip, BROWN, 1.5)
local tipLines = Instance.new("TextLabel")
tipLines.Name = "Lines"
tipLines.BackgroundTransparency = 1
tipLines.Size = UDim2.fromScale(1, 1)
tipLines.FontFace = BODY_FONT
tipLines.TextSize = 15
tipLines.TextColor3 = BROWN
tipLines.TextTruncate = Enum.TextTruncate.AtEnd
tipLines.Parent = tipChip
local chipPadding = Instance.new("UIPadding")
chipPadding.PaddingTop = UDim.new(0, 5)
chipPadding.PaddingBottom = UDim.new(0, 5)
chipPadding.PaddingLeft = UDim.new(0, 8)
chipPadding.PaddingRight = UDim.new(0, 8)
chipPadding.Parent = tipChip
-- the time left as a gold bar
local tipTrack = tipRow(3, 10)
tipTrack.BackgroundTransparency = 0
tipTrack.BackgroundColor3 = Color3.fromRGB(8, 8, 28)
rounded(tipTrack, 5)
outline(tipTrack, Color3.fromRGB(112, 86, 200), 1)
local tipFill = Instance.new("Frame")
tipFill.Name = "Fill"
tipFill.Size = UDim2.fromScale(1, 1)
tipFill.BackgroundColor3 = WHITE
tipFill.BorderSizePixel = 0
tipFill.Parent = tipTrack
rounded(tipFill, 5)
goldFill(tipFill)
local tipFoot = tipRow(4, 20)
local tipEnds = label(tipFoot, "Ends", UDim2.new(0.7, 0, 1, 0), UDim2.fromOffset(0, 0), 14, GOLD_LIGHT, BOLD_FONT)
local tipPercent = label(tipFoot, "Percent", UDim2.new(0.3, 0, 1, 0), UDim2.fromScale(0.7, 0), 14, SOFT, BOLD_FONT)
tipPercent.TextXAlignment = Enum.TextXAlignment.Right

local events = {}
local timeOffset = 0
local eventBadges = {}
local badgeInfo = {} -- [badge] = { event = ..., parts = ... }
local shownIds = {} -- events already on the screen: only a new one pops in
local tipBadge, tipPinnedUntil = nil, 0

local function fillTip(badge)
	local info = badgeInfo[badge]
	if not info then
		return
	end
	local name = tostring(info.event.name or "")
	tipTitle.Text = name ~= "" and name or T.event
	tipTitle.FontFace = fontFor(tipTitle.Text)
	tipSub.Text = T.serverWide
	local lines = {}
	for _, part in ipairs(info.parts) do
		table.insert(lines, partText(part))
	end
	tipLines.Text = table.concat(lines, "\n")
	tipChip.Size = UDim2.new(1, 0, 0, math.max(1, #lines) * 20 + 10)
	tipChip.Visible = #lines > 0
	tipLines.Visible = #lines > 0
	putIcon(tipIcon, iconFor(info.event, info.parts[1]))
	local left = (tonumber(info.event.ends_at) or 0) - (os.time() + timeOffset)
	tipEnds.Text = string.format(T.ends, timeLeft(left))
	local progress = eventProgress(info.event, os.time() + timeOffset)
	tipTrack.Visible = progress ~= nil
	tipFill.Size = UDim2.fromScale(progress or 1, 1)
	tipPercent.Text = progress and (math.floor(progress * 100 + 0.5) .. "%") or ""
end

-- Above the icon (below it at the top of the screen), on the side away from the edge; the arrow points at the medallion
local function placeTip(badge)
	local anchor = eventsHolder.AnchorPoint
	local at = badge.AbsolutePosition - eventsHolder.AbsolutePosition
	local size = badge.AbsoluteSize
	local below = anchor.Y == 0
	local x = anchor.X == 1 and at.X + size.X or (anchor.X == 0 and at.X or at.X + size.X / 2)
	local edge = below and at.Y + size.Y + 16 or at.Y - 16
	tip.AnchorPoint = Vector2.new(anchor.X, below and 0 or 1)
	tip.Position = UDim2.fromOffset(x, edge)
	tipArrow.Position = UDim2.fromOffset(at.X + size.X / 2, edge)
end

local function showTip(badge, pinSeconds)
	tipBadge = badge
	fillTip(badge)
	placeTip(badge)
	setTipVisible(true)
	if pinSeconds then
		tipPinnedUntil = os.clock() + pinSeconds
	end
end

local function hideTip(badge, force)
	if tipBadge == badge and (force or os.clock() >= tipPinnedUntil) then
		setTipVisible(false)
		tipBadge = nil
	end
end

-- The event icon: a medallion with a gold ring that shows the time left, the multiplier on a tilted gold chip and the
-- time on a navy pill. The last seconds: the ring and the time go red and a glow pulses.
local function makeBadge(event, parts, order)
	local badge = Instance.new("TextButton")
	badge.Name = "Event"
	badge.LayoutOrder = order
	badge.AutoButtonColor = false
	badge.Text = ""
	badge.BackgroundTransparency = 1
	badge.Size = UDim2.fromOffset(80, 104)
	badge.Parent = eventsRow
	local scale = Instance.new("UIScale")
	scale.Parent = badge
	local center = UDim2.fromOffset(40, 40)
	local glow = circle(badge, 92, center, RED_RING, "Glow")
	glow.BackgroundTransparency = 1
	local bezel = circle(badge, 76, center, Color3.fromRGB(86, 58, 20), "Bezel")
	outline(bezel, Color3.fromRGB(52, 30, 4), 1.5)
	local ring = makeRing(badge, 76, 7, GOLD_MID)
	ring.frame.Position = center
	local groove = circle(badge, 62, center, Color3.fromRGB(14, 10, 34), "Groove")
	local orb = circle(badge, 54, center, WHITE, "Circle")
	gradient(orb, ORB_TOP, ORB_BOTTOM)
	outline(orb, Color3.fromRGB(14, 8, 40), 1.5)
	local gloss = Instance.new("Frame")
	gloss.Name = "Gloss"
	gloss.AnchorPoint = Vector2.new(0.5, 0)
	gloss.Size = UDim2.fromOffset(36, 15)
	gloss.Position = UDim2.new(0.5, 0, 0, 5)
	gloss.BackgroundColor3 = WHITE
	gloss.BackgroundTransparency = 0.8
	gloss.BorderSizePixel = 0
	gloss.Parent = orb
	rounded(gloss, 8)
	putIcon(orb, iconFor(event, parts[1]))
	local iconObject = orb:FindFirstChild("Icon")
	iconObject.Size = UDim2.fromOffset(34, 34)
	local biggest = nil
	for _, part in ipairs(parts) do
		biggest = math.max(biggest or 0, part.factor)
	end
	local factor = Instance.new("TextLabel")
	factor.Name = "Factor"
	factor.AnchorPoint = Vector2.new(1, 0)
	factor.Position = UDim2.fromOffset(80, 0)
	factor.Size = UDim2.fromOffset(40, 22)
	factor.Rotation = 10
	factor.BackgroundColor3 = GOLD_MID
	factor.FontFace = BODY_FONT
	factor.TextSize = 15
	factor.TextColor3 = BROWN
	factor.Text = biggest and factorText(biggest) or ""
	factor.Visible = biggest ~= nil
	factor.Parent = badge
	rounded(factor, 11)
	outline(factor, BROWN, 1.5)
	local timeLabel = Instance.new("TextLabel")
	timeLabel.Name = "Time"
	timeLabel.AnchorPoint = Vector2.new(0.5, 1)
	timeLabel.Position = UDim2.fromOffset(40, 104)
	timeLabel.Size = UDim2.fromOffset(68, 24)
	timeLabel.BackgroundColor3 = NAVY
	timeLabel.FontFace = BODY_FONT
	timeLabel.TextSize = 15
	timeLabel.TextColor3 = WHITE
	timeLabel.Parent = badge
	rounded(timeLabel, 12)
	local timeStroke = outline(timeLabel, GOLD_EDGE, 1.5)
	-- sparks around the medallion
	local sparks = {}
	for i, spot in ipairs({ { 4, 14, 7 }, { 76, 64, 5 }, { 8, 70, 4 } }) do
		local spark = Instance.new("Frame")
		spark.Name = "Spark"
		spark.AnchorPoint = Vector2.new(0.5, 0.5)
		spark.Position = UDim2.fromOffset(spot[1], spot[2])
		spark.Size = UDim2.fromOffset(spot[3], spot[3])
		spark.Rotation = 45
		spark.BackgroundColor3 = i == 2 and GOLD_LIGHT or WHITE
		spark.BorderSizePixel = 0
		spark.Parent = badge
		sparks[i] = spark
	end
	badge:SetAttribute("EndsAt", tonumber(event.ends_at) or 0)
	badgeInfo[badge] = { event = event, parts = parts, ring = ring, glow = glow, time = timeLabel, timeStroke = timeStroke,
		sparks = sparks, red = false }

	badge.MouseEnter:Connect(function()
		TweenService:Create(scale, TweenInfo.new(0.12), { Scale = 1.08 }):Play()
		showTip(badge)
	end)
	badge.MouseLeave:Connect(function()
		TweenService:Create(scale, TweenInfo.new(0.12), { Scale = 1 }):Play()
		hideTip(badge)
	end)
	-- a tap (or a click) keeps the card for a few seconds: a phone has no hovering
	badge.Activated:Connect(function()
		if tipBadge == badge and tip.Visible and os.clock() < tipPinnedUntil then
			hideTip(badge, true)
			return
		end
		showTip(badge, 4)
		task.delay(4, function()
			hideTip(badge)
		end)
	end)
	return badge, scale
end

-- The glow and the sparks move every frame (the rest changes once a second)
RunService.RenderStepped:Connect(function()
	local clock = os.clock()
	for badge, info in pairs(badgeInfo) do
		if info.red then
			info.glow.BackgroundTransparency = 0.7 + 0.2 * math.sin(clock * 7)
		end
		for i, spark in ipairs(info.sparks) do
			spark.BackgroundTransparency = 0.15 + 0.8 * (0.5 + 0.5 * math.sin(clock * (2 + i) + i * 2))
		end
	end
end)

local function renderEvents()
	setTipVisible(false)
	tipBadge = nil
	for _, badge in ipairs(eventBadges) do
		badge:Destroy()
	end
	eventBadges, badgeInfo = {}, {}
	local seen = {}
	local now = os.time() + timeOffset
	for i, event in ipairs(events) do
		if type(event) == "table" and (tonumber(event.starts_at) or 0) <= now then
			local badge, scale = makeBadge(event, eventParts(event.multipliers), i)
			local id = tostring(event.id or i)
			if not shownIds[id] then
				scale.Scale = 0.2
				TweenService:Create(scale, TweenInfo.new(0.35, Enum.EasingStyle.Back, Enum.EasingDirection.Out), { Scale = 1 }):Play()
			end
			seen[id] = true
			table.insert(eventBadges, badge)
		end
	end
	shownIds = seen
end

local function updateEffects()
	if Effects then
		local ok, err = pcall(Effects.Update, events, os.time() + timeOffset, live("EventEffects", "full"))
		if not ok then
			warn("[DiscordLive] Event animation: " .. tostring(err))
		end
	end
end

local function updateEventTimers()
	updateEffects()
	local now = os.time() + timeOffset
	local changed = false
	for _, badge in ipairs(eventBadges) do
		local left = (badge:GetAttribute("EndsAt") or 0) - now
		if left <= 0 then
			changed = true
		else
			local info = badgeInfo[badge]
			badge:FindFirstChild("Time").Text = timeLeft(left)
			local progress, total = eventProgress(info.event, now)
			info.ring.set(progress or 1)
			-- the last seconds: a red ring and time, a pulsing glow
			local red = left <= math.min(10, (total or 40) * 0.25)
			if red ~= info.red then
				info.red = red
				info.ring.color(red and RED_RING or GOLD_MID)
				info.timeStroke.Color = red and RED_RING or GOLD_EDGE
				info.time.TextColor3 = red and Color3.fromRGB(255, 196, 202) or WHITE
				info.time.BackgroundColor3 = red and Color3.fromRGB(70, 14, 30) or NAVY
				if not red then
					info.glow.BackgroundTransparency = 1
				end
			end
		end
	end
	if tipBadge and tip.Visible then
		fillTip(tipBadge)
	end
	if changed then
		local active = {}
		for _, event in ipairs(events) do
			if type(event) == "table" and (tonumber(event.ends_at) or 0) > now then
				table.insert(active, event)
			end
		end
		events = active
		renderEvents()
		updateEventTimers()
	end
end

-- The ⚙️ Manager changed the language while the game runs: the event cards are written again in it
remote:GetAttributeChangedSignal("Language"):Connect(function()
	readLanguage(remote:GetAttribute("Language"))
	renderEvents()
	updateEventTimers()
end)

-- ---------- An event's start: a countdown card next to the event icons, then a big 3-2-1 at the top ----------
-- A new event starts 10 s after it was made. The card shows its icon, name, what it does and the seconds left; the last
-- 3 seconds are a big number at the top center (no background, the game stays visible), then "EVENT STARTS!".
local clockAtEvents, serverAtEvents = os.clock(), os.time()
local function preciseNow()
	return serverAtEvents + (os.clock() - clockAtEvents)
end

-- The corner card (10 to 4 s): navy, thin gold border, the orb, the name, a green chip with what it gives, "lasts ..."
-- and a gold box with the seconds; a gold bar shrinks under it
local countdownCard = Instance.new("Frame")
countdownCard.Name = "EventCountdown"
countdownCard.Size = UDim2.fromOffset(344, 98)
countdownCard.BackgroundColor3 = WHITE
countdownCard.Visible = false
countdownCard.Parent = screenGui
rounded(countdownCard, 16)
outline(countdownCard, GOLD_EDGE, 2)
gradient(countdownCard, NAVY_TOP, NAVY_DEEP)
local cardScale = Instance.new("UIScale")
cardScale.Parent = countdownCard
local cardIcon = iconCircle(countdownCard, 62, UDim2.fromOffset(14, 10))
local cardTitle = label(countdownCard, "Title", UDim2.fromOffset(176, 24), UDim2.fromOffset(88, 8), 19, WHITE, BODY_FONT)
local cardLine = label(countdownCard, "Line", UDim2.fromOffset(176, 22), UDim2.fromOffset(88, 34), 13, Color3.fromRGB(150, 240, 172),
	BODY_FONT)
cardLine.BackgroundTransparency = 0.35
cardLine.BackgroundColor3 = Color3.fromRGB(24, 92, 52)
cardLine.TextXAlignment = Enum.TextXAlignment.Center
rounded(cardLine, 11)
outline(cardLine, SUCCESS_COLOR, 1.5)
local cardNote = label(countdownCard, "Note", UDim2.fromOffset(176, 18), UDim2.fromOffset(88, 59), 13, SOFT, BOLD_FONT)
local cardBox = Instance.new("Frame")
cardBox.Name = "Box"
cardBox.AnchorPoint = Vector2.new(1, 0)
cardBox.Position = UDim2.new(1, -12, 0, 8)
cardBox.Size = UDim2.fromOffset(62, 70)
cardBox.BackgroundColor3 = WHITE
cardBox.Parent = countdownCard
rounded(cardBox, 12)
outline(cardBox, GOLD_MID, 2)
gradient(cardBox, Color3.fromRGB(46, 30, 50), Color3.fromRGB(20, 12, 28))
local cardCaption = label(cardBox, "Caption", UDim2.new(1, 0, 0, 16), UDim2.fromOffset(0, 5), 11, GOLD_EDGE, BOLD_FONT)
cardCaption.TextXAlignment = Enum.TextXAlignment.Center
local cardNumber = label(cardBox, "Seconds", UDim2.new(1, 0, 0, 46), UDim2.fromOffset(0, 20), 40, GOLD_LIGHT, TITLE_FONT)
cardNumber.TextXAlignment = Enum.TextXAlignment.Center
local numberStroke = Instance.new("UIStroke")
numberStroke.Color = BROWN
numberStroke.Thickness = 2
numberStroke.Parent = cardNumber
local numberScale = Instance.new("UIScale")
numberScale.Parent = cardNumber
local cardTrack = Instance.new("Frame")
cardTrack.Name = "Track"
cardTrack.Position = UDim2.new(0, 14, 1, -18)
cardTrack.Size = UDim2.new(1, -28, 0, 8)
cardTrack.BackgroundColor3 = Color3.fromRGB(8, 8, 28)
cardTrack.Parent = countdownCard
rounded(cardTrack, 4)
local cardFill = Instance.new("Frame")
cardFill.Name = "Fill"
cardFill.Size = UDim2.fromScale(1, 1)
cardFill.BackgroundColor3 = WHITE
cardFill.BorderSizePixel = 0
cardFill.Parent = cardTrack
rounded(cardFill, 4)
goldFill(cardFill)

-- The big 3-2-1 (no panel, the game stays visible): a navy medallion, a gold ring that shrinks every second, the gold
-- number, the event's orb above it, its name on a plate and one line of what it gives. The last picture: START!
local big = Instance.new("Frame")
big.Name = "EventStart"
big.BackgroundTransparency = 1
big.AnchorPoint = Vector2.new(0.5, 0)
big.Position = UDim2.new(0.5, 0, 0, 96)
big.Size = UDim2.fromOffset(460, 290)
big.Visible = false
big.Parent = screenGui
local bigScale = Instance.new("UIScale")
bigScale.Parent = big
local bigGlow = circle(big, 190, UDim2.fromOffset(230, 108), GOLD_MID, "Glow")
bigGlow.BackgroundTransparency = 0.88
local medal = circle(big, 156, UDim2.fromOffset(230, 108), WHITE, "Medal")
gradient(medal, NAVY_TOP, NAVY_DEEP)
outline(medal, GOLD_EDGE, 2.5)
local bigRing = makeRing(medal, 156, 8, GOLD_MID)
local medalInner = circle(medal, 134, nil, WHITE, "Inner")
gradient(medalInner, Color3.fromRGB(40, 50, 104), Color3.fromRGB(14, 18, 46))
local bigNumber = label(medal, "Number", UDim2.fromScale(1, 1), UDim2.fromScale(0, 0), 96, GOLD_LIGHT, TITLE_FONT)
bigNumber.TextXAlignment = Enum.TextXAlignment.Center
local bigStroke = Instance.new("UIStroke")
bigStroke.Color = BROWN
bigStroke.Thickness = 3.5
bigStroke.Parent = bigNumber
local bigCenter = Instance.new("Frame")
bigCenter.Name = "CenterIcon"
bigCenter.BackgroundTransparency = 1
bigCenter.AnchorPoint = Vector2.new(0.5, 0.5)
bigCenter.Position = UDim2.fromScale(0.5, 0.5)
bigCenter.Size = UDim2.fromOffset(96, 96)
bigCenter.Visible = false
bigCenter.Parent = medal
local bigIcon = iconCircle(big, 50, UDim2.fromOffset(230, 0), Vector2.new(0.5, 0))
local bigIconRing = bigIcon.Parent
local bigPlate = Instance.new("Frame")
bigPlate.Name = "Plate"
bigPlate.AnchorPoint = Vector2.new(0.5, 0)
bigPlate.Position = UDim2.fromOffset(230, 202)
bigPlate.Size = UDim2.fromOffset(250, 38)
bigPlate.BackgroundColor3 = WHITE
bigPlate.Parent = big
rounded(bigPlate, 10)
local plateStroke = outline(bigPlate, GOLD_EDGE, 2)
local plateShade = gradient(bigPlate, NAVY_TOP, NAVY_DEEP)
local bigText = label(bigPlate, "Text", UDim2.fromScale(1, 1), UDim2.fromScale(0, 0), 20, GOLD_LIGHT, BODY_FONT)
bigText.TextXAlignment = Enum.TextXAlignment.Center
local bigLine = label(big, "Line", UDim2.fromOffset(460, 24), UDim2.fromOffset(0, 248), 16, WHITE, BODY_FONT)
bigLine.TextXAlignment = Enum.TextXAlignment.Center
bigLine.TextStrokeColor3 = NAVY_DEEP
bigLine.TextStrokeTransparency = 0.25

-- the plate is navy with the event's name, or (the last picture) a gold button with START!
local function plateStyle(gold)
	plateShade.Color = gold and sequence({ 0, GOLD_LIGHT }, { 0.45, GOLD_MID }, { 1, GOLD_DARK }) or sequence({ 0, NAVY_TOP }, { 1, NAVY_DEEP })
	plateStroke.Color = gold and BROWN or GOLD_EDGE
	bigText.TextColor3 = gold and BROWN or GOLD_LIGHT
	bigText.TextSize = gold and 26 or 20
	bigPlate.Size = gold and UDim2.fromOffset(200, 46) or UDim2.fromOffset(250, 38)
end

-- the card sits next to the event icons (above them at the bottom of the screen, below them at the top); the big
-- 3-2-1 goes below the icons when they are at the top
local function placeCountdown()
	countdownCard.AnchorPoint = eventsHolder.AnchorPoint
	local away = eventsHolder.AnchorPoint.Y >= 0.5 and -114 or 114
	countdownCard.Position = eventsHolder.Position + UDim2.fromOffset(0, away)
	local top = eventsHolder.AnchorPoint.Y < 0.5 and eventsHolder.Position.Y.Scale == 0
	big.Position = UDim2.new(0.5, 0, 0, top and math.max(96, eventsHolder.Position.Y.Offset + 120) or 96)
end

local function pop(scale, from, to)
	scale.Scale = from
	TweenService:Create(scale, TweenInfo.new(0.35, Enum.EasingStyle.Back, Enum.EasingDirection.Out), { Scale = to or 1 }):Play()
end

local shown = { card = nil, number = nil, big = nil, bigNumber = nil, started = {} }

local function eventName(event)
	local name = tostring(event.name or "")
	return name ~= "" and name or T.event
end

local function hideCountdown()
	countdownCard.Visible = false
	shown.card, shown.number = nil, nil
end

-- what the event gives and for how long, one line
local function givesLine(event, parts)
	local _, total = eventProgress(event, 0)
	local text = parts[1] and partText(parts[1]) or ""
	if total then
		text = (text ~= "" and (text .. " · ") or "") .. string.format(T.lasts, durationText(total))
	end
	return text
end

local function showStart(event)
	putIcon(bigCenter, iconFor(event, eventParts(event.multipliers)[1]))
	bigCenter.Visible = true
	bigIconRing.Visible = false
	bigLine.Visible = false
	bigNumber.Text = ""
	bigRing.set(1)
	plateStyle(true)
	bigText.Text = T.go
	bigText.FontFace = fontFor(bigText.Text)
	big.Visible = true
	pop(bigScale, 0.95, 0.68)
	task.delay(1.8, function()
		if shown.big == "done:" .. tostring(event.id) then
			big.Visible = false
			shown.big = nil
		end
	end)
end

local function countdownStep()
	local now = preciseNow()
	shown.ringStart = nil
	local event = nil
	local missed = false
	for _, candidate in ipairs(events) do
		local starts = type(candidate) == "table" and tonumber(candidate.starts_at)
		local id = type(candidate) == "table" and tostring(candidate.id)
		if starts and not shown.started[id] and (tonumber(candidate.ends_at) or 0) > now then
			if starts <= now - 1 then -- it started while this screen wasn't looking (a frozen device): just its icon
				shown.started[id] = true
				missed = true
			elseif not event or starts < tonumber(event.starts_at) then
				event = candidate
			end
		end
	end
	if missed then
		renderEvents()
		updateEventTimers()
	end
	if not event then
		hideCountdown()
		if shown.big and string.sub(shown.big, 1, 5) ~= "done:" then -- stopped during its 3-2-1
			big.Visible = false
			shown.big = nil
		end
		return
	end
	local id = tostring(event.id)
	local left = tonumber(event.starts_at) - now
	if left > 3 then
		if shown.card ~= id then
			shown.card = id
			local parts = eventParts(event.multipliers)
			putIcon(cardIcon, iconFor(event, parts[1]))
			cardTitle.Text = eventName(event)
			cardTitle.FontFace = fontFor(cardTitle.Text)
			cardLine.Text = parts[1] and partText(parts[1]) or ""
			cardLine.Visible = cardLine.Text ~= ""
			cardLine.FontFace = fontFor(cardLine.Text)
			local _, total = eventProgress(event, 0)
			cardNote.Text = total and string.format(T.lasts, durationText(total)) or ""
			cardNote.FontFace = fontFor(cardNote.Text)
			cardCaption.Text = upper(T.startsIn)
			cardCaption.FontFace = fontFor(cardCaption.Text)
			placeCountdown()
			countdownCard.Visible = true
			pop(cardScale, 0.3)
		end
		cardFill.Size = UDim2.fromScale(math.max(0, math.min(1, left / 10)), 1)
		local number = math.ceil(left)
		if number ~= shown.number then
			shown.number = number
			cardNumber.Text = tostring(number)
			pop(numberScale, 1.35)
		end
	elseif left > 0 then
		hideCountdown()
		local number = math.ceil(left)
		local parts = eventParts(event.multipliers)
		if shown.big ~= id .. ":" .. number then
			shown.big = id .. ":" .. number
			placeCountdown()
			putIcon(bigIcon, iconFor(event, parts[1]))
			bigIconRing.Visible = true
			bigCenter.Visible = false
			bigLine.Visible = true
			bigLine.Text = givesLine(event, parts)
			bigLine.FontFace = fontFor(bigLine.Text)
			big.Visible = true
			plateStyle(false)
			bigNumber.Text = tostring(number)
			bigText.Text = upper(eventName(event))
			bigText.FontFace = fontFor(bigText.Text)
			pop(bigScale, 0.95, 0.68)
		end
		shown.ringStart = tonumber(event.starts_at) -- the ring shrinks smoothly, every frame (below)
	else
		hideCountdown()
		shown.started[id] = true
		shown.big = "done:" .. id
		showStart(event)
		renderEvents()
		updateEventTimers()
	end
end

-- the ring of the big number shrinks once a second: full when the number changes, empty when the next one comes
RunService.RenderStepped:Connect(function()
	if shown.ringStart then
		local left = shown.ringStart - preciseNow()
		if left > 0 and left <= 3 then
			bigRing.set(left - (math.ceil(left) - 1))
		end
	end
end)

task.spawn(function()
	while true do
		task.wait(0.1)
		local ok, err = pcall(countdownStep)
		if not ok then
			warn("[DiscordLive] Event countdown: " .. tostring(err))
		end
	end
end)

-- Toast for eggs and gifts (NotificationPosition, bottom center by default): a dark card with a colored outline, an
-- icon, a title, a colored line and a note (the gift's message). Long texts wrap and the card grows away from the
-- screen's edge, so nothing is cut.
local TOAST_PLACES = {
	bottom = { UDim2.new(0.5, 0, 1, -110), Vector2.new(0.5, 1) },
	top = { UDim2.new(0.5, 0, 0, 90), Vector2.new(0.5, 0) }, -- below the announcements
	center = { UDim2.fromScale(0.5, 0.5), Vector2.new(0.5, 0.5) },
	left = { UDim2.new(0, 16, 0.5, 0), Vector2.new(0, 0.5) },
	right = { UDim2.new(1, -16, 0.5, 0), Vector2.new(1, 0.5) },
	topleft = { UDim2.fromOffset(16, 16), Vector2.new(0, 0) },
	topright = { UDim2.new(1, -16, 0, 64), Vector2.new(1, 0) }, -- below the ⚙️ Manager button
	bottomleft = { UDim2.new(0, 16, 1, -16), Vector2.new(0, 1) },
	bottomright = { UDim2.new(1, -16, 1, -16), Vector2.new(1, 1) },
}
-- the look of the ⚙️ Manager's cards: dark violet with a gradient, a colored glowing edge and a shine on top
local toast = Instance.new("Frame")
toast.Name = "Toast"
toast.Size = UDim2.fromOffset(400, 0)
toast.AutomaticSize = Enum.AutomaticSize.Y
toast.BackgroundColor3 = WHITE
toast.Visible = false
toast.Parent = screenGui
rounded(toast, 18)
local toastShade = gradient(toast, Color3.fromRGB(58, 36, 104), CARD)

local function placeToast()
	local key, x, y = readPlace(live("NotificationPosition", "Bottom"))
	local place = TOAST_PLACES[key] or TOAST_PLACES.bottom
	local push = 0
	if (readPlace(live("EventPosition", "BottomRight"))) == key then -- the event icons are there
		push = push + apart(place[2], 110)
	end
	if codesPlace() == key then
		push = push + apart(place[2], 70)
	end
	toast.AnchorPoint = place[2]
	toast.Position = place[1] + UDim2.fromOffset(x, y + push)
end
placeToast()

-- The ⚙️ Manager moved something while the game runs
remote:GetAttributeChangedSignal("EventPosition"):Connect(function()
	placeEvents()
	placeToast()
end)
remote:GetAttributeChangedSignal("AnnouncementPosition"):Connect(placeBanner)
remote:GetAttributeChangedSignal("NotificationPosition"):Connect(placeToast)
if codesRemote then
	codesRemote:GetAttributeChangedSignal("ButtonPosition"):Connect(function()
		placeEvents()
		placeToast()
	end)
end
local toastStroke = outline(toast, GOLD_COLOR, 2.5)
local toastGloss = Instance.new("Frame")
toastGloss.Name = "Gloss"
toastGloss.Size = UDim2.new(1, -20, 0, 16)
toastGloss.Position = UDim2.fromOffset(10, 4)
toastGloss.BackgroundColor3 = WHITE
toastGloss.BackgroundTransparency = 0.9
toastGloss.Parent = toast
rounded(toastGloss, 8)
local toastScale = Instance.new("UIScale")
toastScale.Parent = toast
-- a rare pet: gold corner ornaments on the gold frame
local toastCorners = {}
for i, corner in ipairs({ { 0, 0 }, { 1, 0 }, { 0, 1 }, { 1, 1 } }) do
	local piece = Instance.new("Frame")
	piece.Name = "Ornament"
	piece.AnchorPoint = Vector2.new(0.5, 0.5)
	piece.Position = UDim2.new(corner[1], corner[1] == 0 and 6 or -6, corner[2], corner[2] == 0 and 6 or -6)
	piece.Size = UDim2.fromOffset(16, 16)
	piece.Rotation = 45
	piece.BackgroundColor3 = WHITE
	piece.BorderSizePixel = 0
	piece.Visible = false
	piece.ZIndex = 2
	piece.Parent = toast
	goldFill(piece)
	outline(piece, BROWN, 1.5)
	toastCorners[i] = piece
end
-- the looks: gift = dark violet with a green edge, hatch = blue, rare = dark violet in a gold frame, error = a red edge
local TOAST_LOOKS = {
	gift = { top = Color3.fromRGB(56, 34, 98), bottom = Color3.fromRGB(26, 15, 46), edge = Color3.fromRGB(130, 230, 170), thick = 2 },
	hatch = { top = Color3.fromRGB(86, 160, 255), bottom = Color3.fromRGB(40, 84, 214), edge = Color3.fromRGB(196, 228, 255), thick = 2 },
	rare = { top = Color3.fromRGB(58, 34, 96), bottom = Color3.fromRGB(26, 15, 46), edge = GOLD_MID, thick = 3, corners = true },
	error = { top = Color3.fromRGB(56, 24, 52), bottom = Color3.fromRGB(26, 12, 30), edge = ERROR_COLOR, thick = 2 },
}
-- the icon in a round gradient of the card's color (the emoji is in a label inside: a gradient would tint it)
local toastCircle = Instance.new("Frame")
toastCircle.Name = "IconCircle"
toastCircle.Size = UDim2.fromOffset(48, 48)
toastCircle.Position = UDim2.fromOffset(12, 11)
toastCircle.BackgroundColor3 = WHITE
toastCircle.Parent = toast
rounded(toastCircle, 24)
outline(toastCircle, LIGHT_EDGE, 2)
local toastCircleShade = gradient(toastCircle, GOLD_COLOR, GOLD_COLOR)
local toastIcon = Instance.new("TextLabel")
toastIcon.Name = "Icon"
toastIcon.Size = UDim2.fromScale(1, 1)
toastIcon.BackgroundTransparency = 1
toastIcon.TextSize = 26
toastIcon.Parent = toastCircle
local toastTexts = Instance.new("Frame")
toastTexts.Name = "Texts"
toastTexts.BackgroundTransparency = 1
toastTexts.Position = UDim2.fromOffset(70, 0)
toastTexts.Size = UDim2.new(1, -82, 0, 0)
toastTexts.AutomaticSize = Enum.AutomaticSize.Y
toastTexts.Parent = toast
local textsLayout = Instance.new("UIListLayout")
textsLayout.SortOrder = Enum.SortOrder.LayoutOrder
textsLayout.Padding = UDim.new(0, 2)
textsLayout.Parent = toastTexts
local textsPadding = Instance.new("UIPadding")
textsPadding.PaddingTop = UDim.new(0, 12)
textsPadding.PaddingBottom = UDim.new(0, 12)
textsPadding.Parent = toastTexts
-- the card is at least as tall as the icon with its margins (a UISizeConstraint here would stop it from shrinking)
local toastMinimum = Instance.new("Frame")
toastMinimum.Name = "MinimumHeight"
toastMinimum.BackgroundTransparency = 1
toastMinimum.Size = UDim2.fromOffset(1, 70)
toastMinimum.Parent = toast

local function toastText(name, order, font, size)
	local text = Instance.new("TextLabel")
	text.Name = name
	text.LayoutOrder = order
	text.BackgroundTransparency = 1
	text.Size = UDim2.fromScale(1, 0)
	text.AutomaticSize = Enum.AutomaticSize.Y
	text.FontFace = font
	text.TextSize = size
	text.TextColor3 = WHITE
	text.TextWrapped = true
	text.TextXAlignment = Enum.TextXAlignment.Left
	text.Parent = toastTexts
	return text
end
local toastTitle = toastText("Title", 1, TITLE_FONT, 20)
local toastLine = toastText("Line", 2, BODY_FONT, 15)
local toastNote = toastText("Note", 3, BOLD_FONT, 15)
toastNote.TextColor3 = SOFT

-- An empty line takes no room (a hidden label that still grows with its text would keep the card tall)
local function setToastText(text, value)
	text.Text = value
	text.Visible = value ~= ""
	text.AutomaticSize = value ~= "" and Enum.AutomaticSize.Y or Enum.AutomaticSize.None
end

local toastId = 0
-- icon: an emoji, color: the edge, the icon's circle and the line; line and note: "" when not needed
local function showToast(icon, title, line, color, seconds, note, look)
	toastId = toastId + 1
	local myId = toastId
	note = note or ""
	look = TOAST_LOOKS[look] or TOAST_LOOKS.gift
	toastShade.Color = ColorSequence.new(look.top, look.bottom)
	toastStroke.Thickness = look.thick
	for _, piece in ipairs(toastCorners) do
		piece.Visible = look.corners == true
	end
	toastIcon.Text = icon
	toastCircleShade.Color = ColorSequence.new(color:Lerp(WHITE, 0.3), color:Lerp(SHADOW, 0.2))
	toastTitle.Text = title
	toastTitle.FontFace = fontFor(title)
	setToastText(toastLine, line)
	toastLine.TextColor3 = color
	setToastText(toastNote, note)
	toastStroke.Color = look.edge
	toast.Visible = true
	toastScale.Scale = 0.7
	TweenService:Create(toastScale, TweenInfo.new(0.3, Enum.EasingStyle.Back, Enum.EasingDirection.Out), { Scale = 1 }):Play()
	task.delay(seconds or 3.5, function()
		if toastId == myId then
			toast.Visible = false
		end
	end)
end

remote.OnClientEvent:Connect(function(data)
	if type(data) ~= "table" then
		return
	end
	if data.type == "announce" then
		table.insert(announcements, { text = tostring(data.text), seconds = tonumber(data.seconds) or 10 })
		nextAnnouncement()
	elseif data.type == "events" then
		timeOffset = (tonumber(data.server_time) or os.time()) - os.time()
		events = type(data.events) == "table" and data.events or {}
		clockAtEvents, serverAtEvents = os.clock(), tonumber(data.server_time) or os.time()
		renderEvents()
		updateEventTimers()
	elseif data.type == "effect_preview" then -- the ⚙️ Manager's preview of an animation: only on this screen
		if Effects and type(data.animation) == "string" then
			Effects.Preview(data.animation, 12)
		end
	elseif data.type == "hatch" then
		-- rare = a rare pet of the egg (a luck event may show it with a higher chance); older servers send no flag
		local rare = data.rare == true or (data.rare == nil and (tonumber(data.chance) or 100) <= 5)
		local line = rare and (T.rare .. " · " .. chanceText(data.chance)) or chanceText(data.chance)
		showToast(rare and "🌟" or "🐣", string.format(T.hatch, tostring(data.pet)), line, rare and GOLD_COLOR or Color3.fromRGB(170, 255, 190),
			rare and 5 or 3, nil, rare and "rare" or "hatch")
		if rare and Effects then -- an event's animation may answer a rare pet (Lucky Breeze: clovers around the egg)
			pcall(Effects.Hatched, data.egg_id)
		end
	elseif data.type == "gift" then
		local note = type(data.message) == "string" and data.message or ""
		showToast("🎁", T.gift, rewardText(data.reward), SUCCESS_COLOR, note ~= "" and 8 or 6, note, "gift")
	elseif data.type == "egg_error" then
		local text = T[data.key] or T.error
		if data.key == "poor" then
			text = string.format(T.poor, tostring(data.currency), formatNumber(data.price))
		end
		showToast("⚠️", text, "", ERROR_COLOR, 4, nil, "error")
	end
end)

-- ---------- Floating eggs ----------
-- The server builds the egg stands (Live module) and marks the eggs that may move: attribute DiscordFloat = the egg's
-- middle. Here, on this player's device only, such an egg floats up and down and turns slowly around that point; its
-- pedestal stays still. Stands far from the camera are skipped.
local FLOAT_DISTANCE = 120
local stands = {} -- [model] = { center = Vector3, parts = { part... }, offsets = { CFrame... } }

local function addFloatingEgg(model)
	if stands[model] or not model:IsA("Model") then
		return
	end
	local center = model:GetAttribute("DiscordFloat")
	if typeof(center) ~= "Vector3" then
		return -- not floating (or a stand from an older server)
	end
	local pedestal = model:FindFirstChild("DiscordPedestal")
	local parts, offsets = {}, {}
	local pivot = CFrame.new(center)
	for _, part in ipairs(model:GetDescendants()) do
		if part:IsA("BasePart") and not (pedestal and part:IsDescendantOf(pedestal)) then
			table.insert(parts, part)
			table.insert(offsets, pivot:ToObjectSpace(part.CFrame))
		end
	end
	if #parts > 0 then -- with streaming the parts may come a moment after the model: tried again next second
		stands[model] = { center = center, parts = parts, offsets = offsets }
	end
end

local function findStands()
	for model in pairs(stands) do
		if not model.Parent then
			stands[model] = nil -- the stand was rebuilt or removed
		end
	end
	local folder = Workspace:FindFirstChild("DiscordEggStands")
	if folder then
		for _, model in ipairs(folder:GetChildren()) do
			addFloatingEgg(model)
		end
	end
end

RunService.RenderStepped:Connect(function()
	local camera = Workspace.CurrentCamera
	if not camera then
		return
	end
	local clock = os.clock()
	-- only up from where the egg stands, so it never sinks into the pedestal
	local lift = CFrame.new(0, (math.sin(clock * 2) + 1) * 0.3, 0) * CFrame.Angles(0, clock * 0.8, 0)
	local moving, places = {}, {}
	for model, stand in pairs(stands) do
		if model.Parent and (camera.CFrame.Position - stand.center).Magnitude < FLOAT_DISTANCE then
			local base = CFrame.new(stand.center) * lift
			for i, part in ipairs(stand.parts) do
				if part.Parent then
					table.insert(moving, part)
					table.insert(places, base * stand.offsets[i])
				end
			end
		end
	end
	if #moving > 0 then
		Workspace:BulkMoveTo(moving, places, Enum.BulkMoveMode.FireCFrameChanged)
	end
end)

task.spawn(function()
	while true do
		task.wait(1)
		updateEventTimers()
		findStands()
	end
end)

remote:FireServer("hello")
