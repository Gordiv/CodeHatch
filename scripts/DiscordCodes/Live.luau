--!nonstrict
--[[
	DiscordCodes / Live  (ModuleScript)

	Live content from the Discord bot, on every server within seconds and without publishing the game:
	- /event-start  -> multipliers (e.g. 2x Coins, 2x EXP, 1.5x luck in eggs) with a timer on the screen
	- /egg-create   -> eggs on stands, with pets and chances, bought with game currency
	- /give         -> a reward for one player (also delivered later if they are offline now)
	- /announce-game -> a message on the screen of every player

	EGGS: put a Part (or Model) where an egg should stand and give it the tag "DiscordEggSpot"
	(select the part, Properties -> Tags -> +, or CollectionService:AddTag). Optional: a "Spot" text attribute with a name,
	used by the bot's "spot" option. Your egg models go into ReplicatedStorage -> Folder "DiscordEggs"
	(a model named "Default" is used when the bot gives no template). Without models a simple colored egg is used.
	A rolled pet is given like a code item (a BoolValue/IntValue named like the pet in the player's data), or by
	your own function:

		local Live = require(game.ServerScriptService:WaitForChild("DiscordCodes"):WaitForChild("Live"))
		Live.OnHatch = function(player, egg, petName)
			-- add the pet to YOUR pet system here; return false if you couldn't (the price is refunded)
			return true
		end

	MULTIPLIERS: use one line where your game gives currency or EXP:
		amount = amount * Live.GetMultiplier("Coins")      -- or "EXP"; luck is used by eggs automatically

	YOUR OWN EGG SHOP OR DATA LOADING:
		Live.OpenEgg(player, eggId)   -- buy an egg from your own button/UI (Live.GetEggs() lists them)
		Live.GetChances(eggId)        -- the chances to SHOW in your UI ({ {name, chance}, ... }, with a luck event)
		Live.Config.PaidRandomItems = false  -- in your own script, only if no egg currency can be bought with Robux
		Live.Config.Pedestal = false     -- your egg spots already are pedestals (EggAnimation = false: eggs stand still)
		Live.DeliverGifts(player)     -- deliver waiting gifts right after your game loaded the player's data

	EVENTS FOR YOUR OWN CODE:
		Live.EventsChanged:Connect(function(events) ... end)
		Live.Hatched:Connect(function(player, egg, petName) ... end)
		Live.GiftReceived:Connect(function(player, reward, message) ... end)
		Live.OnAnnouncement = function(text, seconds) ... return true end  -- your own announcement UI

	Text written on Discord (announcements, egg, pet, currency and event names) is filtered by Roblox before players
	see it.

	The Report module tells the bot which multipliers your code asks for and which of the functions above you set,
	so /setup-roblox on Discord can warn about options that can't work in your game.
]]

local CollectionService = game:GetService("CollectionService")
local DataStoreService = game:GetService("DataStoreService")
local HttpService = game:GetService("HttpService")
local MessagingService = game:GetService("MessagingService")
local Players = game:GetService("Players")
local PolicyService = game:GetService("PolicyService")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local Core = require(script.Parent:WaitForChild("Core"))

local CONFIG = {
	LiveDataStore = "DiscordLiveContent", -- these three values must match the bot (config.json -> cloud_sync)
	GiftsDataStore = "DiscordGifts",
	MessagingTopic = "DiscordLive",
	PollIntervalSeconds = 60,
	EggSpotTag = "DiscordEggSpot",
	EggTemplatesFolder = "DiscordEggs",
	PromptText = "Open",
	Pedestal = true, -- a round pedestal with a glowing ring under each egg; false if your egg spots are pedestals already
	EggAnimation = true, -- eggs float up and down and turn slowly (on the players' devices only)
	RareChance = 5, -- pets with a chance up to this % count as rare: luck events make them more likely
	LuckLine = "⚡ Luck x%s", -- above the chances on an egg while a luck event runs (the chances shown include it)
	-- under the chances when one of them is rounded: the sentence Roblox requires for paid random items (keep it as is)
	RoundedLine = "Probabilities are rounded; total of displayed individual probabilities may not equal 100%.",
	-- Eggs bought with a currency players can buy with Robux are "paid random items" (Roblox Community Standards):
	-- players Roblox doesn't allow to buy them (PolicyService ArePaidRandomItemsRestricted) can't open eggs. Set false
	-- only if no egg currency in your game can be bought with Robux, directly or indirectly, and in YOUR OWN script
	-- (Live.Config.PaidRandomItems = false after require), not here: updating this file would bring it back.
	PaidRandomItems = true,
	OpenCooldownSeconds = 1,
	MaxMultiplier = 100,
	GiftDelaySeconds = 8, -- wait after joining so your game can load the player's data first
	-- A gift claimed by a server that stopped before finishing is given again only after this long. Long on purpose:
	-- a shorter time could give a gift twice if that server stopped right after giving it.
	StuckClaimSeconds = 86400,
	MaxGiftPages = 10, -- gifts read per join: up to 10 pages of 50
	RefundRetries = 3,
}

local Live = { Config = CONFIG, OnHatch = nil, OnAnnouncement = nil }

local eventsChanged = Instance.new("BindableEvent")
local hatchedEvent = Instance.new("BindableEvent")
local giftReceived = Instance.new("BindableEvent")
Live.EventsChanged = eventsChanged.Event
Live.Hatched = hatchedEvent.Event
Live.GiftReceived = giftReceived.Event

local remoteName = "DiscordLiveEvent"
local liveStore = DataStoreService:GetDataStore(CONFIG.LiveDataStore)
local giftsStore = DataStoreService:GetDataStore(CONFIG.GiftsDataStore)
local random = Random.new()

local remote = nil
local started = false
local activeEvents = {}
local localEvents = {} -- events of this server only (the ⚙️ Manager's "this server"): never saved, gone with the server
local localNumber = 0
local activeEggs = {}
local eventsSignature = ""
local eggsSignature = ""
local rendered = {}
local lastSpots = {} -- egg id -> the spot it stood on, so a change elsewhere doesn't move it
local standsFolder = nil
local pendingFilter = false
local renderQueued = false
local renderGeneration = 0 -- each drawing of the stands has its number: an older one that waited stops (see renderEggs)
local warned = {}
local lastOpen = {}
local lastHello = {}
local giftBusy = {}
local giftAgain = {}
local randomItemsAllowed = {} -- player -> true/false from PolicyService (nil: not checked yet)
local shownLuck = 1 -- the luck in the chances on the eggs; eggs roll with exactly this (see currentChances)

local function warnOnce(key, message)
	if not warned[key] then
		warned[key] = true
		warn("[DiscordLive] " .. message)
	end
end

local function normalize(text)
	return string.lower((string.gsub(tostring(text), "[^%w]", "")))
end

-- At most count characters (not bytes: a Polish letter takes 2 bytes, an emoji 4, and a cut inside one breaks the text)
local function firstChars(text, count)
	text = tostring(text or "")
	if not utf8.len(text) then -- not valid UTF-8 (never from Discord): cut by bytes, the filter checks it anyway
		return string.sub(text, 1, count)
	end
	local cut = utf8.offset(text, count + 1)
	return cut and string.sub(text, 1, cut - 1) or text
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

-- Roblox (paid random items): the odds are shown as percentages; a chance may be rounded only to four or more decimal
-- places below its first non-zero digit (33.3333 -> 33.333, 0.0042 -> 0.0042), and a list with a rounded chance needs
-- the sentence in CONFIG.RoundedLine. Returns the text and whether it was rounded.
local function chanceText(chance)
	chance = tonumber(chance) or 0
	if chance <= 0 then
		return "0%", false
	end
	local decimals = math.max(0, 4 - math.floor(math.log(chance, 10)))
	local text = string.format("%." .. decimals .. "f", chance)
	local rounded = math.abs((tonumber(text) or 0) - chance) > 1e-9
	if string.find(text, ".", 1, true) then
		text = string.gsub(text, "0+$", "")
		text = string.gsub(text, "%.$", "")
	end
	return text .. "%", rounded
end

local function timeLeft(seconds)
	seconds = math.max(0, math.floor(seconds))
	local days = math.floor(seconds / 86400)
	local hours = math.floor((seconds % 86400) / 3600)
	local minutes = math.floor((seconds % 3600) / 60)
	if days > 0 then
		return days .. "d " .. hours .. "h"
	elseif hours > 0 then
		return hours .. "h " .. minutes .. "m"
	end
	return math.max(1, minutes) .. "m"
end

local function loadEntry(key)
	local ok, result = pcall(function()
		return liveStore:GetAsync(key, Core.FreshRead)
	end)
	if not ok then
		local text = tostring(result)
		if Core.IsStudioError(text) then
			warnOnce("studio", "DataStore is not available in Studio. Turn on: File -> Experience Settings -> Security -> Enable Studio Access to API Services, then Save.")
		else
			warn("[DiscordLive] Could not load " .. key .. ": " .. text)
		end
		return false, nil
	end
	return true, result
end

-- Text typed on Discord is filtered like any other text shown to players. Returns nil if it can't be filtered yet.
local function filterText(text, fromUserId)
	return Core.FilterText(text, fromUserId)
end

-- Multipliers as the players see them: currency names typed on Discord are filtered too
local function filteredMultipliers(multipliers)
	local result = {}
	if type(multipliers) ~= "table" then
		return result
	end
	for key, value in pairs(multipliers) do
		local name = tostring(key)
		if string.sub(name, 1, 9) == "currency:" and string.sub(name, 10) ~= "*" then
			local currency = filterText(string.sub(name, 10))
			if currency then
				result["currency:" .. currency] = value
			end
		else
			result[name] = value
		end
	end
	return result
end

-- A reward as the players see it (gift messages): currency and item names filtered
local function filteredReward(reward, userId)
	if type(reward) ~= "table" then
		return {}
	end
	return Core.RewardSummary(reward, { UserId = userId })
end

local function notify(player, payload)
	if remote and player and player.Parent then
		remote:FireClient(player, payload)
	end
end

-- ---------- Multiplier events ----------

local function eventActive(event)
	return type(event) == "table" and (tonumber(event.ends_at) or 0) > os.time()
end

local EXP_KEYS = { exp = true, xp = true, experience = true }
local usedMultipliers = {} -- what your code asks Live.GetMultiplier for (reported to the bot)
local usedMultiplierCount = 0

local function multiplierFor(kind)
	local key = normalize(kind)
	local total = 1
	for _, event in ipairs(Live.GetActiveEvents()) do
		if type(event.multipliers) == "table" then
			for name, value in pairs(event.multipliers) do
				local factor = tonumber(value) or 1
				local matches = false
				if name == "exp" then
					matches = EXP_KEYS[key] == true
				elseif name == "luck" then
					matches = key == "luck"
				elseif string.sub(name, 1, 9) == "currency:" then
					local currency = string.sub(name, 10)
					matches = key ~= "luck" and not EXP_KEYS[key] and (currency == "*" or normalize(currency) == key)
				end
				if matches and factor > 0 then
					total = total * factor
				end
			end
		end
	end
	return math.min(total, CONFIG.MaxMultiplier)
end

-- Product of the active multipliers for "Coins" (any currency name), "EXP" or "Luck"
function Live.GetMultiplier(kind)
	local key = normalize(kind)
	if key ~= "" and not usedMultipliers[key] and usedMultiplierCount < 30 then
		usedMultipliers[key] = string.sub(tostring(kind), 1, 50)
		usedMultiplierCount = usedMultiplierCount + 1
	end
	return multiplierFor(kind)
end

-- The same number without remembering the name (the ⚙️ Manager shows it; GetMultiplier would tell the bot that your
-- game uses that multiplier)
function Live.PeekMultiplier(kind)
	return multiplierFor(kind)
end

-- Names your code asked Live.GetMultiplier for (the Report module tells the bot which multipliers really work)
function Live.GetUsedMultipliers()
	local list = {}
	for _, name in pairs(usedMultipliers) do
		table.insert(list, name)
	end
	table.sort(list)
	return list
end

-- The events that haven't ended: those of every server (saved) and those of this server only (scope "server"),
-- also the ones still counting down to their start (starts_at in the future)
function Live.GetEvents()
	local list = {}
	for _, source in ipairs({ activeEvents, localEvents }) do
		for _, event in ipairs(source) do
			if eventActive(event) then
				table.insert(list, event)
			end
		end
	end
	return list
end

-- The events running now (their multipliers work): started and not ended. A new event starts 10 s after it was made,
-- so every player sees its countdown first.
function Live.GetActiveEvents()
	local list = {}
	local now = os.time()
	for _, event in ipairs(Live.GetEvents()) do
		if (tonumber(event.starts_at) or 0) <= now then
			table.insert(list, event)
		end
	end
	return list
end

-- EventsChanged fires when the list changes and again when a counting-down event starts
local startTimers = {}
local function eventsUpdated()
	eventsChanged:Fire(Live.GetActiveEvents())
	for _, event in ipairs(Live.GetEvents()) do
		local wait = (tonumber(event.starts_at) or 0) - os.time()
		local key = tostring(event.id) .. ":" .. tostring(event.starts_at)
		if wait > 0 and not startTimers[key] then
			startTimers[key] = true
			task.delay(wait, function()
				startTimers[key] = nil
				eventsChanged:Fire(Live.GetActiveEvents())
			end)
		end
	end
end

-- A start further away than the countdown comes from a PC whose clock is ahead of Roblox's: the event starts after
-- the countdown instead (the first time this server saw it, so it doesn't move on every refresh)
local COUNTDOWN = 10
local fixedStarts = {}
local function fixStarts(list)
	local now = os.time()
	for _, event in ipairs(list) do
		local starts = type(event) == "table" and tonumber(event.starts_at)
		if starts and starts > now + COUNTDOWN then
			local key = tostring(event.id) .. ":" .. tostring(starts)
			fixedStarts[key] = fixedStarts[key] or now + COUNTDOWN
			event.starts_at = fixedStarts[key]
		end
	end
end

local function sendEvents(target)
	if not remote then
		return
	end
	local list = {}
	for _, event in ipairs(Live.GetEvents()) do
		-- the animation and the start: the players' devices count down to the start, then show the animation
		table.insert(list, { id = event.id, name = filterText(event.name) or "", ends_at = event.ends_at,
			starts_at = tonumber(event.starts_at), animation = type(event.animation) == "string" and event.animation or nil,
			multipliers = filteredMultipliers(event.multipliers) })
	end
	local payload = { type = "events", events = list, server_time = os.time() }
	if target then
		remote:FireClient(target, payload)
	else
		remote:FireAllClients(payload)
	end
end

local function applyEvents(data)
	local list = {}
	if type(data) == "table" and type(data.events) == "table" then
		list = data.events
	end
	local signature = HttpService:JSONEncode(list)
	fixStarts(list)
	activeEvents = list
	if signature ~= eventsSignature then
		eventsSignature = signature
		eventsUpdated()
		sendEvents(nil)
	end
end

-- Returns ok and the time the bot (or the ⚙️ Manager) saved the events (updated_at)
function Live.RefreshEvents()
	local ok, data = loadEntry("Events")
	if not ok then
		return false
	end
	applyEvents(data)
	return true, type(data) == "table" and tonumber(data.updated_at) or nil
end

-- ---------- Eggs ----------

local function eggOpen(egg)
	local endsAt = tonumber(egg.ends_at) or 0
	return endsAt == 0 or endsAt > os.time()
end

local function eggById(id)
	for _, egg in ipairs(activeEggs) do
		if tostring(egg.id) == tostring(id) then
			return egg
		end
	end
	return nil
end

local function parseColor(text)
	if type(text) ~= "string" then
		return nil
	end
	local r, g, b = string.match(text, "^#?(%x%x)(%x%x)(%x%x)$")
	if not r then
		return nil
	end
	return Color3.fromRGB(tonumber(r, 16), tonumber(g, 16), tonumber(b, 16))
end

local function spotName(spot)
	local name = spot:GetAttribute("Spot")
	if type(name) == "string" and name ~= "" then
		return name
	end
	return spot.Name
end

local function getSpots()
	local spots = {}
	for _, spot in ipairs(CollectionService:GetTagged(CONFIG.EggSpotTag)) do
		if spot:IsDescendantOf(Workspace) and (spot:IsA("BasePart") or spot:IsA("Model")) then
			table.insert(spots, spot)
		end
	end
	table.sort(spots, function(a, b)
		return spotName(a) < spotName(b)
	end)
	return spots
end

-- The middle of a spot's top in world space, standing straight: a Cylinder turned 90° to stand as a round pedestal,
-- or a part turned upside down, still gets the egg on its highest side and upright. The egg keeps only the spot's turn
-- around the vertical axis (which way it faces).
local atan2 = math.atan2 or math.atan
local function spotTop(spot)
	local cframe, size
	if spot:IsA("BasePart") then
		cframe, size = spot.CFrame, spot.Size
	else
		cframe, size = spot:GetBoundingBox()
	end
	local halfHeight = (math.abs(cframe.RightVector.Y) * size.X + math.abs(cframe.UpVector.Y) * size.Y
		+ math.abs(cframe.LookVector.Y) * size.Z) / 2
	local look = cframe.LookVector
	local yaw = (math.abs(look.X) + math.abs(look.Z) > 0.001) and atan2(-look.X, -look.Z) or 0
	local position = cframe.Position
	return CFrame.new(position.X, position.Y + halfHeight, position.Z) * CFrame.Angles(0, yaw, 0)
end

-- A model in the egg models folder (only a Model or a Part, like the ones the Report module tells the bot about)
local function eggTemplate(folder, name)
	local child = folder:FindFirstChild(name)
	if child and (child:IsA("Model") or child:IsA("BasePart")) then
		return child
	end
	return nil
end

local function makeEggModel(egg)
	local folder = ReplicatedStorage:FindFirstChild(CONFIG.EggTemplatesFolder)
	local template = nil
	if folder then
		local wanted = (type(egg.template) == "string" and egg.template ~= "") and egg.template or "Default"
		template = eggTemplate(folder, wanted) or eggTemplate(folder, "Default")
		if not template and wanted ~= "Default" then
			warnOnce("template|" .. wanted, "Egg template '" .. wanted .. "' not found in ReplicatedStorage." .. CONFIG.EggTemplatesFolder .. ". A simple egg is used.")
		end
	end
	local model
	if template and (template:IsA("Model") or template:IsA("BasePart")) then
		local copy = template:Clone()
		if copy:IsA("BasePart") then
			model = Instance.new("Model")
			copy.Parent = model
			model.PrimaryPart = copy
		else
			model = copy
		end
	else
		model = Instance.new("Model")
		local part = Instance.new("Part")
		part.Name = "Egg"
		part.Size = Vector3.new(4, 4, 4)
		part.Material = Enum.Material.SmoothPlastic
		part.Color = parseColor(egg.color) or Color3.fromRGB(245, 245, 245)
		local mesh = Instance.new("SpecialMesh")
		mesh.MeshType = Enum.MeshType.Sphere
		mesh.Scale = Vector3.new(1, 1.3, 1)
		mesh.Parent = part
		part:SetAttribute("Rainbow", egg.color == "rainbow")
		part.Parent = model
		model.PrimaryPart = part
	end
	for _, descendant in ipairs(model:GetDescendants()) do
		if descendant:IsA("BasePart") then
			descendant.Anchored = true
			descendant.CanCollide = false
		end
	end
	if not model.PrimaryPart then
		model.PrimaryPart = model:FindFirstChildWhichIsA("BasePart", true)
	end
	return model
end

-- ---------- Look of the stand (the same style as the code window) ----------
local INK = Color3.fromRGB(27, 29, 41)
local GOLD = Color3.fromRGB(255, 200, 61)
local GOLD_EDGE = Color3.fromRGB(222, 178, 82) -- the thin border of the sign
local TITLE_FONT = Font.new("rbxasset://fonts/families/FredokaOne.json")
-- Fredoka One has no Polish letters (ą, ę, ń...): a name with such letters uses Nunito, which has them all
local BODY_FONT = Font.new("rbxasset://fonts/families/Nunito.json", Enum.FontWeight.Heavy)
local function fontFor(text)
	return string.find(text, "[\196-\197]") and BODY_FONT or TITLE_FONT
end

-- The stand is sized in studs, so it gets smaller with distance: its texts fill their box and scale with it (up to
-- textSize pixels: big and readable up close, never bigger than their box)
-- Capital letters also for Polish and Spanish letters (string.upper changes only a-z: "Tęczowe" would be "TęCZOWE")
local CAPITALS = { ["ą"] = "Ą", ["ć"] = "Ć", ["ę"] = "Ę", ["ł"] = "Ł", ["ń"] = "Ń", ["ó"] = "Ó", ["ś"] = "Ś", ["ź"] = "Ź", ["ż"] = "Ż",
	["á"] = "Á", ["é"] = "É", ["í"] = "Í", ["ú"] = "Ú", ["ü"] = "Ü", ["ñ"] = "Ñ" }
local function upper(text)
	return (string.gsub(string.upper(tostring(text)), "[\195\196\197][\128-\191]", function(letter)
		return CAPITALS[letter] or letter
	end))
end

local function label(parent, name, size, position, textSize, font)
	local text = Instance.new("TextLabel")
	text.Name = name
	text.BackgroundTransparency = 1
	text.Size = size
	text.Position = position
	text.FontFace = font or BODY_FONT
	text.TextScaled = true
	local largest = Instance.new("UITextSizeConstraint")
	largest.MaxTextSize = textSize
	largest.Parent = text
	text.TextColor3 = Color3.fromRGB(255, 255, 255)
	text.TextStrokeColor3 = INK
	text.TextStrokeTransparency = 0
	text.TextWrapped = true
	text.Parent = parent
	return text
end

-- A dark rounded box behind a label (price, chances, timer); roundness: a part of the box's height, so it scales too
local function darkBox(text, roundness)
	text.BackgroundColor3 = INK
	text.BackgroundTransparency = 0.12
	text.TextStrokeTransparency = 1
	local corner = Instance.new("UICorner")
	corner.CornerRadius = UDim.new(roundness, 0)
	corner.Parent = text
end

local function pedestalPart(name, parent, size, cframe, color, material)
	local part = Instance.new("Part")
	part.Name = name
	part.Shape = Enum.PartType.Cylinder
	part.Size = size
	part.CFrame = cframe * CFrame.Angles(0, 0, math.pi / 2) -- a cylinder lies on its side: stand it up
	part.Color = color
	part.Material = material or Enum.Material.SmoothPlastic
	part.Anchored = true
	part.CanCollide = false
	part.CastShadow = false
	part.TopSurface = Enum.SurfaceType.Smooth
	part.BottomSurface = Enum.SurfaceType.Smooth
	part.Parent = parent
	return part
end

-- The round pedestal under an egg: a purple base, a glowing gold ring, a soft light and a few sparkles. Off with
-- Live.Config.Pedestal = false (in your own script) when your egg spots already are pedestals. Returns the model and
-- its height in studs.
local function makePedestal(top, eggSize, glow)
	local width = math.clamp(math.max(eggSize.X, eggSize.Z) * 1.6, 5, 14)
	local pedestal = Instance.new("Model")
	pedestal.Name = "DiscordPedestal"
	local base = pedestalPart("Base", pedestal, Vector3.new(1.2, width, width), top * CFrame.new(0, 0.6, 0), Color3.fromRGB(106, 80, 240))
	base.CanCollide = true
	pedestalPart("Rim", pedestal, Vector3.new(0.3, width * 0.9, width * 0.9), top * CFrame.new(0, 1.35, 0), Color3.fromRGB(157, 137, 255))
	local ring = pedestalPart("Ring", pedestal, Vector3.new(0.1, width * 0.72, width * 0.72), top * CFrame.new(0, 1.53, 0), GOLD, Enum.Material.Neon)
	pedestalPart("RingInside", pedestal, Vector3.new(0.12, width * 0.6, width * 0.6), top * CFrame.new(0, 1.54, 0), Color3.fromRGB(157, 137, 255))
	pedestal.PrimaryPart = base

	local light = Instance.new("PointLight")
	light.Color = glow
	light.Brightness = 1.2
	light.Range = 12
	light.Parent = ring
	local sparkles = Instance.new("ParticleEmitter")
	sparkles.Name = "Sparkles"
	sparkles.Texture = "rbxasset://textures/particles/sparkles_main.dds"
	sparkles.Color = ColorSequence.new(GOLD)
	sparkles.LightEmission = 1
	sparkles.Size = NumberSequence.new(0.35, 0)
	sparkles.Lifetime = NumberRange.new(1.2, 2)
	sparkles.Speed = NumberRange.new(1.5, 3)
	sparkles.SpreadAngle = Vector2.new(25, 25)
	sparkles.Rate = 4
	sparkles.EmissionDirection = Enum.NormalId.Top
	sparkles.Parent = ring
	return pedestal, 1.6
end

-- The chance of each pet (in %) that a player really gets now: a luck event multiplies the weight of the rare pets.
-- The egg shows these and rolls with these, with the same luck (shownLuck): Roblox requires the odds of paid random
-- items to be shown accurately before the purchase.
local function currentChances(egg, luck)
	luck = luck or shownLuck
	local weights, total = {}, 0
	for i, pet in ipairs(egg.pets) do
		local weight = math.max(0, tonumber(pet.chance) or 0)
		if weight > 0 and weight <= CONFIG.RareChance then
			weight = weight * luck
		end
		weights[i] = weight
		total = total + weight
	end
	-- chances that already add up to 100 (as the bot saves them) stay exactly as written
	local scale = math.abs(total - 100) < 0.01 and 1 or (total > 0 and 100 / total or 0)
	local chances = {}
	for i, weight in ipairs(weights) do
		chances[i] = weight * scale
	end
	return chances, total
end

-- Every pet with its chance: none may be hidden (Roblox: all odds shown before the purchase); the stand grows for long
-- lists. Names are filtered first (that may wait) and the chances read after, so the sign always has the current luck.
-- Returns { pets = { {name, chance, was, tier} sorted by chance }, luckLine = text or nil, rounded = bool }:
-- was = the chance without luck (only where luck changes it), tier 1..4 = grey, green, blue, gold by how rare it is.
local function petsData(egg)
	local names = {}
	for i, pet in ipairs(egg.pets) do
		names[i] = filterText(pet.name)
		if names[i] == nil then
			names[i] = "?"
			pendingFilter = true -- filtered again when a player joins
		end
	end
	local pets = {}
	local chances = currentChances(egg)
	local plain = currentChances(egg, 1)
	local rare, common = false, false
	for i, pet in ipairs(egg.pets) do
		local base = tonumber(pet.chance) or 0
		if base > 0 and base <= CONFIG.RareChance then
			rare = true
		elseif base > 0 then
			common = true
		end
	end
	local luckShown = shownLuck > 1 and rare and common -- only where luck really changes the chances
	for i, pet in ipairs(egg.pets) do
		local base = tonumber(pet.chance) or 0
		local tier = 1
		if base > 0 and base <= CONFIG.RareChance then
			tier = 4
		elseif plain[i] <= 20 then
			tier = 3
		elseif plain[i] <= 35 then
			tier = 2
		end
		local was = nil
		if luckShown and math.abs(plain[i] - chances[i]) > 1e-6 then
			was = plain[i]
		end
		table.insert(pets, { name = names[i], chance = chances[i], was = was, tier = tier })
	end
	table.sort(pets, function(a, b)
		return a.chance > b.chance
	end)
	local luckLine = nil
	if luckShown then
		luckLine = string.format(CONFIG.LuckLine, string.format("%g", math.floor(shownLuck * 100 + 0.5) / 100))
	end
	local anyRounded = false
	for _, pet in ipairs(pets) do
		local _, rounded = chanceText(pet.chance)
		anyRounded = anyRounded or rounded
	end
	return { pets = pets, luckLine = luckLine, rounded = anyRounded }
end

local openEgg -- defined below

local function buildStand(egg, spot)
	local model = makeEggModel(egg)
	local primary = model.PrimaryPart
	if not primary then
		model:Destroy()
		warnOnce("template-empty|" .. tostring(egg.template), "Egg template has no parts.")
		return
	end
	model.Name = "DiscordEgg_" .. tostring(egg.id)
	model:SetAttribute("EggId", egg.id)
	local top = spotTop(spot)
	model:PivotTo(top)
	local boxCFrame, boxSize = model:GetBoundingBox()
	local pedestal, pedestalHeight = nil, 0
	if CONFIG.Pedestal then
		local glow = parseColor(egg.color) or GOLD
		-- standing straight even on a turned or tilted spot part
		pedestal, pedestalHeight = makePedestal(CFrame.new(top.Position.X, top.Position.Y, top.Position.Z), boxSize, glow)
	end
	local lift = top.Position.Y + pedestalHeight - (boxCFrame.Position.Y - boxSize.Y / 2) + 0.05
	model:PivotTo(model:GetPivot() + Vector3.new(0, lift, 0))
	if pedestal then
		pedestal.Parent = model -- after placing the egg, so the egg's size above did not count the pedestal
	end
	-- The players' devices let the egg float up and down and turn slowly around its middle (DiscordLiveClient); the
	-- server keeps it still. Streamed as a whole, so a player's device never gets half an egg.
	if CONFIG.EggAnimation then
		model:SetAttribute("DiscordFloat", Vector3.new(top.Position.X, boxCFrame.Position.Y + lift, top.Position.Z))
	end
	model.ModelStreamingMode = Enum.ModelStreamingMode.Atomic

	local displayName = filterText(egg.name)
	if displayName == nil then
		displayName = "Egg"
		pendingFilter = true
	end
	local currencyName = filterText(egg.currency)
	if currencyName == nil then
		currencyName = ""
		pendingFilter = true
	end

	-- The sign (navy panel, thin gold border, gold title, a crown on top): in studs from the top of the sign. The pets are
	-- one dark pill each, 4 at least; the sign grows by a row's height for each pet more, so every chance stays readable.
	-- Under the pets a line for the rounding note and the timer of an egg that ends.
	local data = petsData(egg)
	local WIDTH = 8
	local ROW, STRIDE, FIRST = 0.58, 0.66, 3.55
	local rowsEnd = FIRST + math.max(4, #data.pets) * STRIDE
	-- room for the rounding note always (luck may make a chance rounded later), for the timer only on an egg that ends
	local timed = (tonumber(egg.ends_at) or 0) > 0
	local height = rowsEnd + 0.6 + (timed and 0.9 or 0) + 0.15
	local gui = Instance.new("BillboardGui")
	gui.Name = "EggInfo"
	gui.Size = UDim2.fromScale(WIDTH, height)
	-- Above the egg. With a pedestal it hangs on a point of the pedestal, so it stays still while the egg floats: a
	-- point placed straight (the pedestal's cylinder lies turned, and an offset from it would turn with it)
	local above = boxSize.Y / 2 + height / 2 + 1.1 -- the sign's bottom stays above the egg (it floats a little)
	if pedestal then
		local point = Instance.new("Attachment")
		point.Name = "InfoPoint"
		point.Parent = pedestal.PrimaryPart
		point.WorldCFrame = CFrame.new(top.Position.X, boxCFrame.Position.Y + lift + above, top.Position.Z)
		gui.Adornee = point
	else
		gui.StudsOffsetWorldSpace = Vector3.new(0, above, 0)
		gui.Adornee = primary
	end
	gui.MaxDistance = 70
	gui.Parent = primary
	-- a box in studs: x, y from the sign's top left corner, w, h its size
	local function put(object, x, y, w, h)
		object.Position = UDim2.fromScale(x / WIDTH, y / height)
		object.Size = UDim2.fromScale(w / WIDTH, h / height)
		return object
	end
	local function frame(parent, name, x, y, w, h, color)
		local item = Instance.new("Frame")
		item.Name = name
		item.BackgroundColor3 = color or Color3.fromRGB(255, 255, 255)
		item.BorderSizePixel = 0
		item.Parent = parent
		return put(item, x, y, w, h)
	end
	local function round(item, part)
		local corner = Instance.new("UICorner")
		corner.CornerRadius = UDim.new(part, 0)
		corner.Parent = item
	end
	local function edge(item, color, thickness)
		local stroke = Instance.new("UIStroke")
		stroke.Color = color
		stroke.Thickness = thickness
		stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
		stroke.Parent = item
		return stroke
	end
	local function shade(item, top, bottom)
		local gradient = Instance.new("UIGradient")
		gradient.Color = ColorSequence.new(top, bottom)
		gradient.Rotation = 90
		gradient.Parent = item
		return gradient
	end
	local function goldShade(item)
		return shade(item, Color3.fromRGB(255, 232, 140), Color3.fromRGB(214, 138, 22))
	end

	-- the navy panel starts a little below the top: the crown sits on its edge
	local panel = frame(gui, "Panel", 0, 0.8, WIDTH, height - 0.8)
	round(panel, 0.07)
	shade(panel, Color3.fromRGB(36, 44, 92), Color3.fromRGB(20, 26, 60))
	edge(panel, GOLD_EDGE, 2)

	-- the crown: a gold band, three spikes with balls and a violet gem
	local crown = frame(gui, "Crown", 3.05, 0, 1.9, 1.1)
	crown.BackgroundTransparency = 1
	local function crownPart(x, y, w, h, turn, round_, fill)
		local part = Instance.new("Frame")
		part.AnchorPoint = Vector2.new(0.5, 0.5)
		part.Position = UDim2.fromScale(x / 1.9, y / 1.1)
		part.Size = UDim2.fromScale(w / 1.9, h / 1.1)
		part.Rotation = turn
		part.BackgroundColor3 = fill or Color3.fromRGB(255, 255, 255)
		part.BorderSizePixel = 0
		part.Parent = crown
		if round_ then
			round(part, 0.5)
		end
		return part
	end
	for _, spike in ipairs({ { 0.45, 0.52, 0.5 }, { 1.45, 0.52, 0.5 }, { 0.95, 0.42, 0.66 } }) do
		local part = crownPart(spike[1], spike[2], spike[3], spike[3] * (1.9 / 1.9), 45, false)
		goldShade(part)
		edge(part, Color3.fromRGB(110, 64, 6), 1)
	end
	for _, ball in ipairs({ { 0.2, 0.34 }, { 0.95, 0.1 }, { 1.7, 0.34 } }) do
		local part = crownPart(ball[1], ball[2], 0.17, 0.17, 0, true, Color3.fromRGB(255, 226, 120))
		edge(part, Color3.fromRGB(110, 64, 6), 1)
	end
	local band = crownPart(0.95, 0.92, 1.6, 0.3, 0, false)
	round(band, 0.5)
	goldShade(band)
	edge(band, Color3.fromRGB(110, 64, 6), 1)
	local gem = crownPart(0.95, 0.6, 0.28, 0.28, 45, false, Color3.fromRGB(150, 80, 240))
	edge(gem, Color3.fromRGB(60, 20, 110), 1)

	local title = label(gui, "Title", UDim2.fromScale(1, 0), UDim2.fromScale(0, 0), 60, fontFor(displayName))
	put(title, 0.3, 1.1, WIDTH - 0.6, 1.2)
	title.Text = upper(displayName)
	title.TextColor3 = Color3.fromRGB(255, 255, 255)
	title.TextStrokeColor3 = Color3.fromRGB(70, 40, 6)
	title.TextStrokeTransparency = 0.3
	goldShade(title)

	-- the price: a gold pill with a coin, or a blue one with a gem (a currency called Gems or Gem)
	local gems = string.find(string.lower(currencyName), "gem", 1, true) ~= nil
	local priceBox = frame(gui, "PriceBox", 2.15, 2.45, 3.7, 0.86)
	round(priceBox, 0.5)
	if gems then
		shade(priceBox, Color3.fromRGB(110, 190, 255), Color3.fromRGB(34, 98, 214))
		edge(priceBox, Color3.fromRGB(10, 30, 80), 2)
	else
		shade(priceBox, Color3.fromRGB(255, 226, 120), Color3.fromRGB(226, 148, 24))
		edge(priceBox, Color3.fromRGB(80, 46, 6), 2)
	end
	local icon = frame(gui, "PriceIcon", 2.5, 2.6, 0.55, 0.55)
	icon.BackgroundTransparency = 1
	if gems then
		icon.Rotation = 45
		icon.Size = UDim2.fromScale(0.4 / WIDTH, 0.4 / height)
		icon.Position = UDim2.fromScale(2.62 / WIDTH, 2.68 / height)
		edge(icon, Color3.fromRGB(255, 255, 255), 2.5)
	else
		icon.BackgroundTransparency = 0
		goldShade(icon)
		round(icon, 0.5)
		edge(icon, Color3.fromRGB(110, 64, 6), 2)
	end
	local price = label(gui, "Price", UDim2.fromScale(1, 0), UDim2.fromScale(0, 0), 44, fontFor(formatNumber(egg.price) .. " " .. currencyName))
	put(price, 3.15, 2.52, 2.55, 0.72)
	price.TextStrokeTransparency = 1
	price.TextColor3 = gems and Color3.fromRGB(8, 24, 66) or Color3.fromRGB(70, 40, 6)
	price.Text = formatNumber(egg.price) .. " " .. currencyName

	-- the luck tag: tilted, green, over the corner of the title
	local luckTag = label(gui, "LuckTag", UDim2.fromScale(1, 0), UDim2.fromScale(0, 0), 30, BODY_FONT)
	put(luckTag, 5.35, 0.95, 2.45, 0.55)
	luckTag.Rotation = -8
	luckTag.BackgroundColor3 = Color3.fromRGB(70, 200, 100)
	luckTag.BackgroundTransparency = 0
	luckTag.TextStrokeTransparency = 1
	luckTag.TextColor3 = Color3.fromRGB(12, 66, 28)
	round(luckTag, 0.3)
	edge(luckTag, Color3.fromRGB(16, 98, 44), 2)
	local tagPadding = Instance.new("UIPadding")
	tagPadding.PaddingTop = UDim.new(0.1, 0)
	tagPadding.PaddingBottom = UDim.new(0.1, 0)
	tagPadding.PaddingLeft = UDim.new(0.05, 0)
	tagPadding.PaddingRight = UDim.new(0.05, 0)
	tagPadding.Parent = luckTag

	-- the rows: the pet with a dot, its name and its chance (the rarer, the warmer the colors)
	local pets = frame(gui, "Pets", 0, 0, WIDTH, height)
	pets.BackgroundTransparency = 1
	local TIERS = {
		{ dot = Color3.fromRGB(205, 208, 222), text = Color3.fromRGB(215, 218, 232) },
		{ dot = Color3.fromRGB(96, 224, 128), text = Color3.fromRGB(96, 224, 128) },
		{ dot = Color3.fromRGB(88, 178, 255), text = Color3.fromRGB(88, 178, 255) },
		{ dot = Color3.fromRGB(255, 196, 64), text = Color3.fromRGB(255, 200, 70) },
	}
	local function fillRows(info)
		for _, child in ipairs(pets:GetChildren()) do
			child:Destroy()
		end
		for i, pet in ipairs(info.pets) do
			local y = FIRST + (i - 1) * STRIDE
			local tier = TIERS[pet.tier]
			local row = frame(pets, "Row", 0.45, y, WIDTH - 0.9, ROW)
			round(row, 0.5)
			if pet.tier == 4 then
				shade(row, Color3.fromRGB(104, 66, 14), Color3.fromRGB(54, 32, 6))
				edge(row, GOLD_EDGE, 2)
			else
				shade(row, Color3.fromRGB(34, 42, 86), Color3.fromRGB(16, 20, 46))
				edge(row, Color3.fromRGB(70, 82, 132), 1.5)
			end
			local dot = Instance.new("Frame")
			dot.Name = "Dot"
			dot.AnchorPoint = Vector2.new(0.5, 0.5)
			dot.Position = UDim2.fromScale(0.34 / (WIDTH - 0.9), 0.5)
			dot.Size = UDim2.fromScale(0.26 / (WIDTH - 0.9), 0.26 / ROW)
			dot.BackgroundColor3 = tier.dot
			dot.BorderSizePixel = 0
			dot.Parent = row
			round(dot, 0.5)
			local name = label(row, "Name", UDim2.fromScale(0.52, 0.8), UDim2.fromScale(0.1, 0.1), 34, fontFor(pet.name))
			name.TextXAlignment = Enum.TextXAlignment.Left
			name.Text = pet.name
			name.TextStrokeTransparency = 1
			local percent = label(row, "Percent", UDim2.fromScale(0.26, 0.8), UDim2.fromScale(0.72, 0.1), 34, BODY_FONT)
			percent.TextXAlignment = Enum.TextXAlignment.Right
			percent.Text = (chanceText(pet.chance))
			percent.TextColor3 = tier.text
			percent.TextStrokeTransparency = 1
			if pet.was then -- luck changed it: the old chance struck through next to the new one
				local was = label(row, "Was", UDim2.fromScale(0.2, 0.7), UDim2.fromScale(0.5, 0.15), 24, BODY_FONT)
				was.TextXAlignment = Enum.TextXAlignment.Right
				was.RichText = true
				was.Text = "<s>" .. (chanceText(pet.was)) .. "</s>"
				was.TextColor3 = Color3.fromRGB(150, 156, 180)
				was.TextStrokeTransparency = 1
			end
		end
	end
	local note = label(gui, "RoundedNote", UDim2.fromScale(1, 0), UDim2.fromScale(0, 0), 16)
	put(note, 0.2, rowsEnd + 0.04, WIDTH - 0.4, 0.5)
	note.TextColor3 = Color3.fromRGB(225, 225, 235)
	note.Text = CONFIG.RoundedLine
	local function refresh()
		local info = petsData(egg)
		fillRows(info)
		note.Visible = info.rounded
		luckTag.Visible = info.luckLine ~= nil
		luckTag.Text = info.luckLine or ""
	end
	refresh()
	local timer = label(gui, "Timer", UDim2.fromScale(0.62, 0), UDim2.fromScale(0, 0), 36, BODY_FONT)
	put(timer, 1.52, rowsEnd + 0.6, 4.96, 0.8)
	timer.TextColor3 = GOLD
	darkBox(timer, 0.5)
	local timerPadding = Instance.new("UIPadding")
	timerPadding.PaddingTop = UDim.new(0.14, 0) -- the text never touches the pill's edge
	timerPadding.PaddingBottom = UDim.new(0.14, 0)
	timerPadding.Parent = timer
	timer.Visible = false -- shown by updateTimers for an egg that ends

	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText = CONFIG.PromptText
	prompt.ObjectText = displayName .. " - " .. formatNumber(egg.price) .. " " .. currencyName
	prompt.HoldDuration = 0.25
	prompt.MaxActivationDistance = 12
	prompt.RequiresLineOfSight = false
	prompt.Parent = primary
	prompt.Triggered:Connect(function(player)
		openEgg(player, egg.id)
	end)

	model.Parent = standsFolder
	return { model = model, egg = egg, timer = timer, pets = pets, refresh = refresh }
end

local function updateTimers()
	local now = os.time()
	local expired = false
	for _, stand in pairs(rendered) do
		local endsAt = tonumber(stand.egg.ends_at) or 0
		if endsAt > 0 then
			if endsAt <= now then
				expired = true
			elseif stand.timer and stand.timer.Parent then
				stand.timer.Text = "⏳ " .. timeLeft(endsAt - now)
				stand.timer.Visible = true
			end
		end
	end
	return expired
end

local function renderEggs()
	renderQueued = false
	renderGeneration = renderGeneration + 1
	local mine = renderGeneration
	shownLuck = multiplierFor("Luck")
	if not standsFolder or not standsFolder.Parent then
		standsFolder = Workspace:FindFirstChild("DiscordEggStands")
		if not standsFolder then
			standsFolder = Instance.new("Folder")
			standsFolder.Name = "DiscordEggStands"
			standsFolder.Parent = Workspace
		end
	end
	for _, stand in pairs(rendered) do
		stand.model:Destroy()
	end
	rendered = {}
	pendingFilter = false

	local open = {}
	for _, egg in ipairs(activeEggs) do
		if type(egg) == "table" and eggOpen(egg) and type(egg.pets) == "table" and #egg.pets > 0 then
			table.insert(open, egg)
		end
	end
	local spots = getSpots()
	if #open > 0 and #spots == 0 then
		warnOnce("nospots", "Eggs were added by the bot, but the game has no egg spots. Give a part the tag '" .. CONFIG.EggSpotTag .. "' where an egg should stand.")
		return
	end
	local used, placed = {}, {}
	-- 1) eggs that asked for a named spot
	for _, egg in ipairs(open) do
		if type(egg.spot) == "string" and egg.spot ~= "" then
			for _, spot in ipairs(spots) do
				if not used[spot] and normalize(spotName(spot)) == normalize(egg.spot) then
					used[spot] = true
					placed[egg] = spot
					break
				end
			end
			if not placed[egg] then
				warnOnce("spot|" .. egg.spot, "Egg spot '" .. egg.spot .. "' not found (or already taken); the egg goes to a free spot.")
			end
		end
	end
	-- 2) the rest stay where they stood, if that spot is still there and free (each server remembers its own eggs,
	--    so after changes two servers may show an egg on different spots; the bot's "spot" option fixes the spot)
	local present = {}
	for _, spot in ipairs(spots) do
		present[spot] = true
	end
	for _, egg in ipairs(open) do
		local spot = egg.id ~= nil and lastSpots[egg.id] or nil
		if not placed[egg] and spot and present[spot] and not used[spot] then
			used[spot] = true
			placed[egg] = spot
		end
	end
	-- 3) and the others on free spots, in order
	for _, egg in ipairs(open) do
		if not placed[egg] then
			for _, spot in ipairs(spots) do
				if not used[spot] then
					used[spot] = true
					placed[egg] = spot
					break
				end
			end
			if not placed[egg] then
				warnOnce("full|" .. tostring(egg.id), "Not enough egg spots for '" .. tostring(egg.name) .. "'. Add another part with the tag '" .. CONFIG.EggSpotTag .. "'.")
			end
		end
	end
	lastSpots = {}
	for egg, spot in pairs(placed) do
		if egg.id ~= nil then
			lastSpots[egg.id] = spot
		end
	end
	for _, egg in ipairs(open) do
		if placed[egg] then
			local ok, stand = pcall(buildStand, egg, placed[egg])
			if mine ~= renderGeneration then
				-- building waits for Roblox's text filter; a newer drawing started meanwhile and draws every stand
				-- itself. This one removes what it just built and stops, so no stand with old chances stays behind.
				if ok and stand then
					stand.model:Destroy()
				end
				return
			end
			if not ok then
				warn("[DiscordLive] Could not build the stand for '" .. tostring(egg.name) .. "': " .. tostring(stand))
			elseif stand then
				rendered[egg.id] = stand
			end
		end
	end
	updateTimers()
end

local function queueRender()
	if not renderQueued then
		renderQueued = true
		task.delay(0.5, renderEggs)
	end
end

local function applyEggs(data)
	local list = {}
	if type(data) == "table" and type(data.eggs) == "table" then
		list = data.eggs
	end
	local signature = HttpService:JSONEncode(list)
	if signature ~= eggsSignature then
		-- replaced only when something changed: openEgg compares the egg with the one its stand shows
		activeEggs = list
		eggsSignature = signature
		queueRender()
	end
end

-- Returns ok and the time the bot (or the ⚙️ Manager) saved the eggs (updated_at)
function Live.RefreshEggs()
	local ok, data = loadEntry("Eggs")
	if not ok then
		return false
	end
	applyEggs(data)
	return true, type(data) == "table" and tonumber(data.updated_at) or nil
end

-- ---------- Changes made by the game itself (the ⚙️ Manager, see the Control module) ----------

local LISTS = { Events = "events", Eggs = "eggs" }

-- An entry ended: an event after its time, an egg after its end (0 = no end)
local function ended(key, item, now)
	local ends = type(item) == "table" and tonumber(item.ends_at) or 0
	if key == "Events" then
		return ends <= now
	end
	return ends > 0 and ends <= now
end

-- Changes the saved events (key "Events") or eggs ("Eggs"): change(data) gets the entry (data.events or data.eggs,
-- a list) inside one UpdateAsync and returns true to save it; it may run more than once. Ended ones are left out.
-- Returns ok and the saved entry (nil when nothing was saved), or false and the error. Every server shows it at once.
local function change(key, edit)
	local field = LISTS[key]
	local saved = nil
	local ok, err = pcall(function()
		liveStore:UpdateAsync(key, function(old)
			saved = nil
			local data = type(old) == "table" and old or {}
			local list = {}
			local now = os.time()
			for _, item in ipairs(type(data[field]) == "table" and data[field] or {}) do
				if type(item) == "table" and item.id ~= nil and not ended(key, item, now) then
					table.insert(list, item)
				end
			end
			data[field] = list
			if not edit(data) then
				return nil
			end
			data.version = math.max(2, tonumber(data.version) or 0)
			data.updated_at = Core.SaveTime(data.updated_at)
			saved = data
			return data
		end)
	end)
	if not ok then
		return false, tostring(err)
	end
	if saved then
		if key == "Events" then
			applyEvents(saved)
		else
			applyEggs(saved)
		end
		Core.Publish(CONFIG.MessagingTopic, { type = field, at = saved.updated_at })
	end
	return true, saved
end

-- An event of this server only (the ⚙️ Manager's "this server"): it runs until its end or until this server stops,
-- other servers and the bot never see it. Returns the event with its id ("s1", "s2"...).
function Live.AddLocalEvent(event)
	localNumber = localNumber + 1
	event.id = "s" .. localNumber
	event.scope = "server"
	local kept = {}
	for _, old in ipairs(localEvents) do
		if eventActive(old) then
			table.insert(kept, old)
		end
	end
	table.insert(kept, event)
	localEvents = kept
	eventsUpdated()
	sendEvents(nil)
	return event
end

-- Stops an event of this server only; returns it (nil when there is none with this id)
function Live.RemoveLocalEvent(id)
	for i, event in ipairs(localEvents) do
		if tostring(event.id) == tostring(id) then
			table.remove(localEvents, i)
			eventsUpdated()
			sendEvents(nil)
			return event
		end
	end
	return nil
end

function Live.ChangeEvents(edit)
	return change("Events", edit)
end

function Live.ChangeEggs(edit)
	return change("Eggs", edit)
end

-- A new id for an event or egg made in the game ("g1", "g2"...; the bot's own ones are numbers). Call it inside
-- change(): the counter is saved with the entry.
function Live.NewId(data)
	local number = math.max(math.floor(tonumber(data.next_id) or 1), 1)
	-- never an id the entry already has (e.g. the entry was made again without its counter)
	for _, field in pairs(LISTS) do
		for _, item in ipairs(type(data[field]) == "table" and data[field] or {}) do
			local used = type(item) == "table" and tonumber(string.match(tostring(item.id), "^g(%d+)$"))
			if used and used >= number then
				number = used + 1
			end
		end
	end
	data.next_id = number + 1
	return "g" .. number
end

function Live.GetEggs()
	return activeEggs
end

-- Returns the pet and its chance (%) as the egg shows it
local function rollPet(egg)
	local chances, total = currentChances(egg)
	if total <= 0 then
		return nil
	end
	local roll = random:NextNumber() * 100
	for i, pet in ipairs(egg.pets) do
		roll = roll - chances[i]
		if roll <= 0 and chances[i] > 0 then
			return pet, chances[i]
		end
	end
	for i = #egg.pets, 1, -1 do
		if chances[i] > 0 then
			return egg.pets[i], chances[i]
		end
	end
	return nil
end

-- A luck event started or ended: the chances on the eggs (and the rolls) follow at once, without rebuilding the stands
-- Returns true when the luck changed. The labels change in their own thread (filtering pet names may wait).
local function updateLuck()
	local luck = multiplierFor("Luck")
	if luck == shownLuck then
		return false
	end
	shownLuck = luck
	task.spawn(function()
		for _, stand in pairs(rendered) do
			if stand.pets and stand.pets.Parent and stand.refresh then
				stand.refresh()
			end
		end
	end)
	return true
end
Live.UpdateLuck = updateLuck

-- The chances of an egg as players get them now, for your own egg shop UI: { { name = "Cat", chance = 60 }, ... }
function Live.GetChances(eggId)
	local egg = eggById(eggId)
	if not egg or type(egg.pets) ~= "table" then
		return {}
	end
	local list = {}
	for i, chance in ipairs((currentChances(egg))) do
		table.insert(list, { name = egg.pets[i].name, chance = chance })
	end
	return list
end

-- Roblox doesn't let some players buy paid random items (PolicyService ArePaidRandomItemsRestricted). Asked once per
-- player (also in the background when they join). Returns true, false, or nil when the check failed (the egg is not
-- opened then and the next try asks again; in Studio a failed check lets the egg open, so testing isn't blocked).
local function checkPaidRandomItems(player)
	if randomItemsAllowed[player] ~= nil then
		return randomItemsAllowed[player]
	end
	local ok, info = pcall(function()
		return PolicyService:GetPolicyInfoForPlayerAsync(player)
	end)
	if not ok or type(info) ~= "table" then
		warnOnce("policy", "Could not check PolicyService for paid random items (" .. tostring(info) .. "). Eggs stay closed "
			.. "for that player until the check works. If no egg currency in your game can be bought with Robux, set "
			.. "Live.Config.PaidRandomItems = false in your own script."
			.. (RunService:IsStudio() and " (In Studio a failed check doesn't block eggs, so you can test.)" or ""))
		return nil
	end
	if player.Parent then -- not for a player who left while Roblox was answering
		randomItemsAllowed[player] = info.ArePaidRandomItemsRestricted ~= true
	end
	return info.ArePaidRandomItemsRestricted ~= true
end

local function mayOpenEggs(player)
	if not CONFIG.PaidRandomItems then
		return true
	end
	local allowed = checkPaidRandomItems(player)
	if allowed == nil and RunService:IsStudio() then
		return true
	end
	return allowed
end

openEgg = function(player, eggId)
	local clock = os.clock()
	if lastOpen[player] and clock - lastOpen[player] < CONFIG.OpenCooldownSeconds then
		return
	end
	lastOpen[player] = clock
	local egg = eggById(eggId)
	if not egg or not eggOpen(egg) or type(egg.pets) ~= "table" or #egg.pets == 0 then
		notify(player, { type = "egg_error", key = "closed" })
		return
	end
	local allowed = mayOpenEggs(player)
	if allowed ~= true then -- false: Roblox's rules for this player; nil: the check failed for now
		notify(player, { type = "egg_error", key = allowed == false and "restricted" or "try_again" })
		return
	end
	local stand = rendered[egg.id]
	if updateLuck() or (stand and stand.egg ~= egg) then
		-- a luck event started or ended, or the egg was edited on Discord, a moment ago and its stand doesn't show
		-- that yet: the player didn't see these chances, nothing is taken
		notify(player, { type = "egg_error", key = "chances_changed" })
		return
	end
	local pet, chance = rollPet(egg)
	if not pet then
		return
	end
	local petReward = { item = { name = tostring(pet.name) } }
	if not Live.OnHatch then
		local can, problems = Core.CanGive(player, petReward)
		if not can then
			warnOnce(
				"hatch|" .. tostring(pet.name),
				"Egg '" .. tostring(egg.name) .. "': can't give the pet '" .. tostring(pet.name) .. "' (" .. tostring(problems)
					.. "). Add Live.OnHatch (see the top of the Live file) or a value named like the pet in the player's data."
			)
			notify(player, { type = "egg_error", key = "unsupported" })
			return
		end
	end
	local paid, reason = Core.Spend(player, egg.currency, egg.price)
	if not paid then
		notify(player, { type = "egg_error", key = reason == "poor" and "poor" or "unsupported",
			currency = filterText(egg.currency, player.UserId) or "?", price = egg.price })
		return
	end
	local given, problem
	if Live.OnHatch then
		local ok, result = pcall(Live.OnHatch, player, { id = egg.id, name = egg.name, currency = egg.currency, price = egg.price }, pet.name)
		given = ok and result ~= false
		problem = ok and "Live.OnHatch returned false" or tostring(result)
	else
		local ok, _, details = Core.GiveReward(player, petReward)
		given = ok
		problem = details
	end
	if not given then
		-- The price goes back; a failed refund is tried again and, if it still fails, written to the log with
		-- everything the owner needs to give it back by hand
		local refunded, refundReason, refundDetails = false, nil, nil
		for attempt = 1, CONFIG.RefundRetries do
			refunded, refundReason, refundDetails = Core.GiveReward(player, { currency = { name = egg.currency, amount = egg.price } }, true)
			if refunded or not player.Parent then
				break
			end
			task.wait(attempt)
		end
		if refunded then
			warn("[DiscordLive] Could not give the pet '" .. tostring(pet.name) .. "' from '" .. tostring(egg.name) .. "', the price was refunded: " .. tostring(problem))
		else
			warn("[DiscordLive] Could not give the pet '" .. tostring(pet.name) .. "' from '" .. tostring(egg.name) .. "' (" .. tostring(problem)
				.. ") and the price could NOT be refunded (" .. tostring(refundReason) .. ": " .. tostring(refundDetails) .. "). Give "
				.. player.Name .. " (" .. player.UserId .. ") " .. tostring(egg.price) .. " " .. tostring(egg.currency) .. " back by hand.")
		end
		notify(player, { type = "egg_error", key = "error" })
		return
	end
	hatchedEvent:Fire(player, egg, pet.name)
	notify(player, { type = "hatch", pet = filterText(pet.name, player.UserId) or "?", chance = chance,
		rare = (tonumber(pet.chance) or 0) <= CONFIG.RareChance,
		egg = filterText(egg.name, player.UserId) or "", egg_id = egg.id })
end

-- ---------- Gifts from /give ----------

local function deliverWaitingGifts(player)
	local ok, pages = pcall(function()
		return giftsStore:ListKeysAsync("gift_" .. player.UserId .. "_", 50)
	end)
	local keys = {}
	if ok then
		-- Every waiting gift, not only the first page of 50
		for _ = 1, CONFIG.MaxGiftPages do
			local pageOk, page = pcall(function()
				return pages:GetCurrentPage()
			end)
			if not pageOk then
				break
			end
			for _, keyInfo in ipairs(page) do
				table.insert(keys, keyInfo.KeyName)
			end
			if pages.IsFinished then
				break
			end
			local nextOk = pcall(function()
				pages:AdvanceToNextPageAsync()
			end)
			if not nextOk then
				break
			end
		end
	elseif not Core.IsStudioError(pages) then
		warn("[DiscordLive] Could not check gifts for " .. player.Name .. ": " .. tostring(pages))
	end

	for _, key in ipairs(keys) do
		if not player.Parent then
			break
		end
		local gift = nil
		local claimOk, claimError = pcall(function()
			giftsStore:UpdateAsync(key, function(old)
				gift = nil
				if type(old) ~= "table" or old.given then
					return nil
				end
				if old.claimed and os.time() - (tonumber(old.claimed) or 0) < CONFIG.StuckClaimSeconds then
					return nil
				end
				old.claimed = os.time()
				gift = old
				return old
			end)
		end)
		if not claimOk then
			warn("[DiscordLive] Could not claim a gift: " .. tostring(claimError))
		elseif gift and type(gift.reward) == "table" then
			local given, reason, details = false, "left", nil
			if player.Parent then
				given, reason, details = Core.GiveReward(player, gift.reward)
			end
			if given then
				local removed = pcall(function()
					giftsStore:RemoveAsync(key)
				end)
				if not removed then
					pcall(function()
						giftsStore:UpdateAsync(key, function(old)
							if type(old) == "table" then
								old.given = os.time()
							end
							return old
						end)
					end)
				end
				notify(player, { type = "gift", reward = filteredReward(gift.reward, player.UserId),
					message = filterText(gift.message, player.UserId) or "" })
				giftReceived:Fire(player, gift.reward, gift.message)
			elseif reason == "unsupported" or reason == "left" then
				-- give it back: it is delivered on a later join, after the game is fixed
				pcall(function()
					giftsStore:UpdateAsync(key, function(old)
						if type(old) == "table" then
							old.claimed = nil
						end
						return old
					end)
				end)
				if reason == "unsupported" then
					warnOnce("gift|" .. tostring(details), "A gift for " .. player.Name .. " can't be given yet: " .. tostring(details) .. ". It keeps waiting and is delivered when the reward fits the game.")
				end
			else
				-- an error halfway through: never repeat it, so it can't be used to get the reward twice
				pcall(function()
					giftsStore:UpdateAsync(key, function(old)
						if type(old) == "table" then
							old.given = os.time()
							old.error = tostring(details)
						end
						return old
					end)
				end)
				warn("[DiscordLive] Error while giving a gift to " .. player.Name .. ": " .. tostring(details) .. ". It was marked as given.")
			end
		end
	end
end

local function deliverGifts(player)
	if not player.Parent then
		return
	end
	if giftBusy[player] then
		-- a gift sent while the earlier ones are being given (two /give a second apart): its key may not have been on
		-- the list read a moment ago, so the list is read again when they are done (gifts have no 60 s poll)
		giftAgain[player] = true
		return
	end
	giftBusy[player] = true
	repeat
		giftAgain[player] = nil
		-- an error must not leave giftBusy set: the player's later gifts would wait until they rejoin
		local ok, err = pcall(deliverWaitingGifts, player)
		if not ok then
			warn("[DiscordLive] Error while giving gifts to " .. player.Name .. ": " .. tostring(err))
		end
	until not giftAgain[player] or not player.Parent
	giftBusy[player] = nil
	giftAgain[player] = nil
end

-- Public versions for your own egg shop UI and your own data loading
function Live.OpenEgg(player, eggId)
	openEgg(player, eggId)
end

function Live.DeliverGifts(player)
	deliverGifts(player)
end

-- A gift from the ⚙️ Manager, saved like a /give from Discord: the player gets it now (on any server) or when they
-- join next time. reward: { currency = { name, amount }, exp = n, item = { name, is_temporary, duration_seconds } }.
-- Returns true and the gift's key, or false and the error.
function Live.SendGift(userId, reward, message, from)
	userId = math.floor(tonumber(userId) or 0)
	local key = "gift_" .. userId .. "_" .. os.time() .. string.format("%04x", random:NextInteger(0, 65535))
	local ok, err = pcall(function()
		giftsStore:SetAsync(key, { reward = reward, message = message or "", from = from or "", created_at = os.time() }, { userId })
	end)
	if not ok then
		return false, tostring(err)
	end
	local target = Players:GetPlayerByUserId(userId)
	if target then
		task.spawn(deliverGifts, target)
	end
	Core.Publish(CONFIG.MessagingTopic, { type = "gift", user_id = userId })
	return true, key
end

-- ---------- Announcements ----------

local function announce(data)
	local text = filterText(firstChars(data.text, 200))
	if not text or text == "" then
		warnOnce("announce-filter", "An announcement could not be shown: the text could not be filtered (no players on this server).")
		return
	end
	local seconds = math.clamp(tonumber(data.seconds) or 10, 3, 60)
	if Live.OnAnnouncement then
		local ok, handled = pcall(Live.OnAnnouncement, text, seconds)
		if ok and handled == true then
			return
		end
	end
	if remote then
		remote:FireAllClients({ type = "announce", text = text, seconds = seconds })
	end
end

-- An announcement from the ⚙️ Manager: on this server at once, on every other one within a second or two.
-- Returns ok and the error when the other servers couldn't be told.
function Live.Announce(text, seconds)
	local data = { type = "announce", text = firstChars(text, 200), seconds = seconds }
	task.spawn(announce, data)
	return Core.Publish(CONFIG.MessagingTopic, { type = "announce", text = data.text, seconds = seconds })
end

-- ---------- For the ⚙️ Manager ----------

-- The names of the egg spots in the game (the "Spot" attribute or the part's name), for the egg form
function Live.GetSpotNames()
	local names = {}
	for _, spot in ipairs(getSpots()) do
		table.insert(names, spotName(spot))
	end
	return names
end

-- ---------- Previews for the ⚙️ Manager ----------

-- Shows ONE player what everyone would see, without giving, spending or saving anything. kind:
-- "announce" (arg.text), "gift" (arg.reward, arg.message), "hatch" (arg.egg = an egg id), "event" (arg.name: an event
-- bar for 30 s with 2x on every currency, next to the real events). Returns false when there is nothing to show.
function Live.Preview(player, kind, arg)
	arg = type(arg) == "table" and arg or {}
	if kind == "announce" then
		local text = filterText(firstChars(arg.text, 200), player.UserId)
		if not text or text == "" then
			return false
		end
		notify(player, { type = "announce", text = text, seconds = 6 })
	elseif kind == "gift" then
		notify(player, { type = "gift", reward = filteredReward(arg.reward, player.UserId),
			message = filterText(firstChars(arg.message, 200), player.UserId) or "" })
	elseif kind == "hatch" then
		local egg = eggById(arg.egg)
		if not egg then
			return false
		end
		local pet, chance = rollPet(egg)
		if not pet then
			return false
		end
		notify(player, { type = "hatch", pet = filterText(pet.name, player.UserId) or "?", chance = chance,
			rare = (tonumber(pet.chance) or 0) <= CONFIG.RareChance, egg = filterText(egg.name, player.UserId) or "",
			egg_id = egg.id })
	elseif kind == "animation" then
		if type(arg.animation) ~= "string" or #arg.animation > 40 then
			return false
		end
		notify(player, { type = "effect_preview", animation = arg.animation })
	elseif kind == "event" then
		local list = {}
		for _, event in ipairs(Live.GetEvents()) do
			table.insert(list, { id = event.id, name = filterText(event.name) or "", starts_at = event.starts_at, ends_at = event.ends_at,
				animation = event.animation, multipliers = filteredMultipliers(event.multipliers) })
		end
		table.insert(list, { name = filterText(firstChars(arg.name, 60), player.UserId) or "", ends_at = os.time() + 30,
			multipliers = { ["currency:*"] = 2 } })
		notify(player, { type = "events", events = list, server_time = os.time() })
	else
		return false
	end
	return true
end

-- ---------- Start ----------

function Live.Start()
	if started then
		return
	end
	started = true

	remote = Core.FindRemote(remoteName, "RemoteEvent")
	-- The player's window asks for the current events when it loads
	remote.OnServerEvent:Connect(function(player, request)
		if request == "hello" and (not lastHello[player] or os.clock() - lastHello[player] > 5) then
			lastHello[player] = os.clock()
			sendEvents(player)
		end
	end)

	local function onPlayer(player)
		task.delay(CONFIG.GiftDelaySeconds, deliverGifts, player)
		if CONFIG.PaidRandomItems then
			task.spawn(checkPaidRandomItems, player) -- ready before the first egg, so opening doesn't wait
		end
		if pendingFilter then
			queueRender()
		end
	end
	Players.PlayerAdded:Connect(onPlayer)
	for _, player in ipairs(Players:GetPlayers()) do
		onPlayer(player)
	end
	Players.PlayerRemoving:Connect(function(player)
		lastOpen[player] = nil
		lastHello[player] = nil
		giftBusy[player] = nil
		giftAgain[player] = nil
		randomItemsAllowed[player] = nil
	end)

	CollectionService:GetInstanceAddedSignal(CONFIG.EggSpotTag):Connect(queueRender)
	CollectionService:GetInstanceRemovedSignal(CONFIG.EggSpotTag):Connect(queueRender)

	Live.EventsChanged:Connect(updateLuck) -- a luck event from Discord: the chances on the eggs change at once
	Core.RefreshUntilFresh(Live.RefreshEvents)
	Core.RefreshUntilFresh(Live.RefreshEggs)

	task.spawn(function()
		while true do
			task.wait(CONFIG.PollIntervalSeconds)
			Core.RefreshUntilFresh(Live.RefreshEvents)
			Core.RefreshUntilFresh(Live.RefreshEggs)
		end
	end)

	-- Egg timers every 10 s, rainbow eggs change color
	task.spawn(function()
		local hue = 0
		local tick = 0
		while true do
			task.wait(0.2)
			hue = (hue + 0.01) % 1
			for _, stand in pairs(rendered) do
				local part = stand.model.PrimaryPart
				if part and part:GetAttribute("Rainbow") then
					part.Color = Color3.fromHSV(hue, 0.6, 1)
				end
			end
			tick = tick + 1
			if tick % 5 == 0 then
				updateLuck() -- a luck event ends by its time, without a notification: the chances follow within a second
			end
			if tick >= 50 then
				tick = 0
				if updateTimers() then
					queueRender()
				end
			end
		end
	end)

	task.spawn(function()
		-- Roblox may refuse for a moment: tried again later (announcements and instant gifts need it; the rest still
		-- refreshes every PollIntervalSeconds)
		for attempt = 1, 8 do
			local ok, err = pcall(function()
				MessagingService:SubscribeAsync(CONFIG.MessagingTopic, function(message)
					local decoded, data = pcall(function()
						return HttpService:JSONDecode(message.Data)
					end)
					if not decoded or type(data) ~= "table" or Core.IsOwnMessage(data) then
						return -- a message this server sent: it already did that itself
					end
					if data.type == "events" then
						task.delay(random:NextNumber() * 2, Core.RefreshUntilFresh, Live.RefreshEvents, data.at)
					elseif data.type == "eggs" then
						task.delay(random:NextNumber() * 2, Core.RefreshUntilFresh, Live.RefreshEggs, data.at)
					elseif data.type == "announce" then
						task.spawn(announce, data)
					elseif data.type == "access" then -- who may open the ⚙️ Manager changed on Discord
						if Live.OnAccess then
							Live.OnAccess()
						end
					elseif data.type == "gift" then
						local target = Players:GetPlayerByUserId(tonumber(data.user_id) or 0)
						if target then
							task.spawn(deliverGifts, target)
						end
					end
				end)
			end)
			if ok then
				return
			end
			if attempt == 1 then
				warn("[DiscordLive] Could not subscribe to notifications, trying again (data still refreshes every "
					.. CONFIG.PollIntervalSeconds .. " s): " .. tostring(err))
			elseif attempt == 8 then
				warn("[DiscordLive] Gave up subscribing to notifications on this server: announcements and instant gifts "
					.. "won't show here until it restarts (events and eggs still refresh every "
					.. CONFIG.PollIntervalSeconds .. " s, gifts on rejoin): " .. tostring(err))
				return
			end
			task.wait(math.min(15 * 2 ^ attempt, 600))
		end
	end)

	print("[DiscordLive] Ready. Events: " .. #Live.GetActiveEvents() .. ", eggs: " .. #activeEggs)
end

return Live
