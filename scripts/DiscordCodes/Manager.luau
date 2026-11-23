--!nonstrict
--[[
	DiscordCodes / Manager  (ModuleScript)

	The ⚙️ Manager: lets the game's owner check the kit inside their own game (codes, player data, events, eggs,
	gifts, settings, the kit's messages) without opening Discord, change the settings while the game runs (only the
	owner), test a code without using it up, preview what players see, and create codes, events, eggs, gifts,
	announcements and bans (only the owner). The game does those by itself, also when the Discord bot is off (the
	Control module); the bot, when it runs, writes each change to the Discord log channel. Only these people get it:
	- the game's owner (or the owner of the group that owns the game): everything,
	- the Roblox players the owner added in the panel's 🛡️ tab (found by their name) or an administrator added on
	  Discord (/setup -> 🛡️ Permissions -> Manager in the game), each with what was ticked for them (codes, events,
	  eggs, gifts, announcements, bans, settings); both write one list, the DataStore entry ManagerAccess, which every
	  server reads again every minute and at once on a notice. Each sees only the tabs of what they may do (and Start),
	- the UserIds in ServerScriptService -> DiscordSettings -> ManagerUsers (separated by commas, e.g. "123456, 987654"):
	  they get only the Start tab,
	- everyone in Studio (Play in Studio is only you).
	Others never receive the panel, and every action is checked again here on the server. Nothing in the panel gives
	free currency: eggs are opened for their normal price, a simulation only counts results, a preview gives nothing.
	(A helper with "codes" or "gifts" can make a code or a gift, never one for themselves as a gift; the currency limit
	per code stays the owner's.) The only other exception is the "my currency" buttons, which work only in Studio (your own test; when your game saves player
	data in Studio too, the change is saved like any other).
	Turn it off: DiscordSettings -> Manager = false.
]]

local LogService = game:GetService("LogService")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local Manager = {}

local MAX_LOG = 80
local MAX_SIMULATION = 1000

local Core, Live, Control, version, settings
local allowedCache = setmetatable({}, { __mode = "k" })
local DataStoreService = game:GetService("DataStoreService")
local HttpService = game:GetService("HttpService")

-- Who the bot allowed (Discord -> /setup -> 🛡️ Permissions -> Manager in the game): [userId] = { permission = true }
local ACCESS_KEY = "ManagerAccess"
local ACCESS_POLL_SECONDS = 60
local PERMISSIONS = { "codes", "events", "eggs", "gifts", "announce", "players", "bans", "settings" }
-- what the owner ticks in the 🛡️ tab (the same as on Discord; "players" is only a Discord command)
local GAME_PERMISSIONS = { "codes", "events", "eggs", "gifts", "announce", "bans", "settings" }
local MAX_ACCESS_USERS = 25 -- the same limit as the bot's
local accessUsers = {}
local accessNames = {} -- [userId] = the Roblox name saved with them
local accessSignature = ""
local accessStore = "DiscordLiveContent" -- set by Manager.Start (the kit's live DataStore)
local refreshPlayers = function() end -- set by Manager.Start: gives or takes the panel after the list changed
local accessReads = 0 -- a read that ends after a newer one is thrown away
local busy = {}
local lastCodes = setmetatable({}, { __mode = "k" }) -- the codes the player's panel shows, in order: "forget" names a code by its place in this list
local lastValues = setmetatable({}, { __mode = "k" }) -- the values the player's Players tab shows, in order: "currency" names one by its place
local lastCall = setmetatable({}, { __mode = "k" }) -- [player][action] = os.clock() of the last call of an action with a cooldown
local log = {}
-- seconds between two calls of one player (refresh and gifts read DataStores, change saves, the others show things)
local COOLDOWNS = { refresh = 5, gifts = 5, preview = 2, testCode = 1, change = 1 }
local POSITIONS = { left = true, right = true, top = true, bottom = true, center = true, topleft = true, topright = true,
	bottomleft = true, bottomright = true }
-- A place on the screen: its name, optionally moved by pixels ("BottomRight", "BottomRight -20,30")
local function isPlace(value)
	if type(value) ~= "string" or #value > 40 then
		return false
	end
	local name, x, y = string.match(value, "^%s*(%a+)%s*([%+%-]?%d*)%s*,?%s*([%+%-]?%d*)%s*$")
	return name ~= nil and POSITIONS[string.lower(name)] == true and math.abs(tonumber(x) or 0) <= 2000
		and math.abs(tonumber(y) or 0) <= 2000
end
-- The settings the owner can change while the game runs (for this server only: DiscordSettings keeps them after a
-- restart). The players' windows get them as attributes on the kit's remotes, which every player can see.
local LIVE_SETTINGS = {
	ShowButton = function(value)
		return type(value) == "boolean"
	end,
	ButtonPosition = isPlace,
	ManagerPosition = isPlace,
	EventPosition = isPlace,
	EventEffects = function(value)
		return value == "full" or value == "light" or value == "off"
	end,
	AnnouncementPosition = isPlace,
	NotificationPosition = isPlace,
	Language = function(value)
		return value == "auto" or value == "en" or value == "pl" or value == "es"
	end,
	MaxCurrencyPerCode = function(value)
		return type(value) == "number" and value == math.floor(value) and value >= 0 and value <= 1e12
	end,
}
local SERVER_ONLY = { MaxCurrencyPerCode = true } -- the players' windows don't use it
local startValues = {} -- the values from DiscordSettings, for Reset
local ownerCache = setmetatable({}, { __mode = "k" })

local function setting(name, default)
	local value = settings and settings:FindFirstChild(name)
	if value == nil then
		return default
	end
	return value.Value
end

local function listedUsers()
	local users = {}
	for id in string.gmatch(tostring(setting("ManagerUsers", "")), "%d+") do
		users[tonumber(id)] = true
	end
	return users
end

-- Takes the saved list ({ users = { ["<id>"] = { name, permissions = {...} } } }). Returns true when it changed.
local function useAccess(data)
	local users, names = {}, {}
	local raw = type(data) == "table" and type(data.users) == "table" and data.users or {}
	for id, entry in pairs(raw) do
		local userId = tonumber(id)
		if userId and type(entry) == "table" and type(entry.permissions) == "table" then
			local perms = {}
			for _, name in ipairs(entry.permissions) do
				if table.find(PERMISSIONS, name) then
					perms[name] = true
				end
			end
			users[userId] = perms
			names[userId] = type(entry.name) == "string" and string.sub(entry.name, 1, 40) or ""
		end
	end
	local okJson, signature = pcall(HttpService.JSONEncode, HttpService, raw)
	signature = okJson and signature or ""
	local changed = signature ~= accessSignature
	accessUsers, accessNames, accessSignature = users, names, signature
	return changed
end

-- Reads the list (written by the bot or by the owner in the 🛡️ tab). Returns true when it changed since the last read.
local function loadAccess(storeName)
	accessReads = accessReads + 1
	local mine = accessReads
	local ok, data = pcall(function()
		return DataStoreService:GetDataStore(storeName):GetAsync(ACCESS_KEY)
	end)
	if mine ~= accessReads then
		return false -- a newer read started meanwhile: it decides
	end
	if not ok then
		return false -- Roblox didn't answer (or API access is off in Studio): the last list stays
	end
	return useAccess(data)
end

-- Who may use the panel (asked once per player; the group rank is asked from Roblox)
function Manager.IsAllowed(player)
	if RunService:IsStudio() then
		return true
	end
	if accessUsers[player.UserId] then
		return true
	end
	if allowedCache[player] ~= nil then
		return allowedCache[player]
	end
	local allowed = listedUsers()[player.UserId] == true
	local sure = true
	if not allowed then
		if game.CreatorType == Enum.CreatorType.User then
			allowed = player.UserId == game.CreatorId
		else
			local ok, rank = pcall(function()
				return player:GetRankInGroup(game.CreatorId)
			end)
			allowed = ok and rank == 255
			sure = ok -- Roblox didn't answer: asked again next time instead of a "no" for the whole session
		end
	end
	if sure and player.Parent then
		allowedCache[player] = allowed
	end
	return allowed
end

-- Only the game's owner (or the group's owner) changes settings; the people in ManagerUsers only look
function Manager.IsOwner(player)
	if RunService:IsStudio() then
		return true
	end
	if ownerCache[player] ~= nil then
		return ownerCache[player]
	end
	local owner, sure = false, true
	if game.CreatorType == Enum.CreatorType.User then
		owner = player.UserId == game.CreatorId
	else
		local ok, rank = pcall(function()
			return player:GetRankInGroup(game.CreatorId)
		end)
		owner, sure = ok and rank == 255, ok
	end
	if sure and player.Parent then
		ownerCache[player] = owner
	end
	return owner
end

-- Whether this player may do this (the owner and Studio everything; a player from the bot's list what was ticked
-- for them; the people in ManagerUsers nothing, they only look)
function Manager.Can(player, permission)
	if Manager.IsOwner(player) then
		return true
	end
	local perms = accessUsers[player.UserId]
	return perms ~= nil and perms[permission] == true
end

local function canTable(player)
	local result = {}
	for _, name in ipairs(PERMISSIONS) do
		result[name] = Manager.Can(player, name)
	end
	return result
end

-- Text written on Discord is filtered before anyone sees it, also in the panel
local function filtered(text, player)
	return Core.FilterText(tostring(text), player.UserId) or "?"
end

-- The names of the kit's own objects, as its messages write them. Roblox hides a whole line that names another
-- platform, even inside such a name, so for the filter each one becomes a neutral word (DiscordSettings ->
-- KitSettings) and comes back after it. Only these exact names: anything else (a name typed on Discord) is filtered.
local KIT_NAMES = { "DiscordCodesRedeem", "DiscordCodesWindow", "DiscordCodesClient",
	"DiscordCodesScale", "DiscordCodesBound", "DiscordCodesGui", "DiscordCodes", "DiscordCodeSync", "DiscordSettings",
	"DiscordCatalog", "DiscordManagerClient", "DiscordManager", "DiscordLiveContent", "DiscordLiveClient",
	"DiscordLiveEvent", "DiscordLiveGui", "DiscordLive", "DiscordEggStands", "DiscordEggSpot", "DiscordEggs",
	"DiscordEgg", "DiscordPedestal", "DiscordFloat", "DiscordGifts" }

-- A line Roblox's filter hid whole (only #): the panel writes in the owner's language that the filter hid it
local HIDDEN_LINE = "[filtered]"

-- One line, filtered whole (one call, the filter sees all of it)
local function filteredLine(line, player)
	local swapped = {}
	local text = line
	for i, name in ipairs(KIT_NAMES) do
		text, swapped[i] = string.gsub(text, "%f[%w_]" .. name .. "%f[^%w_]", "Kit" .. string.sub(name, 8))
	end
	text = filtered(text, player)
	if string.find(line, "[%w\128-\255]") and not string.find(text, "[^#%s]") then
		return HIDDEN_LINE
	end
	for i, name in ipairs(KIT_NAMES) do
		if swapped[i] > 0 then -- only as many as were swapped: a "KitEggs" typed by someone stays as typed
			text = string.gsub(text, "%f[%w_]Kit" .. string.sub(name, 8) .. "%f[^%w_]", name, swapped[i])
		end
	end
	return text
end

local function rewardText(reward, player)
	local parts = {}
	if type(reward) ~= "table" then
		return ""
	end
	if type(reward.currency) == "table" and (tonumber(reward.currency.amount) or 0) > 0 then
		table.insert(parts, "+" .. tostring(reward.currency.amount) .. " " .. filtered(reward.currency.name, player))
	end
	if (tonumber(reward.exp) or 0) > 0 then
		table.insert(parts, "+" .. tostring(reward.exp) .. " EXP")
	end
	if type(reward.item) == "table" and reward.item.name then
		local item = filtered(reward.item.name, player)
		if reward.item.is_temporary and (tonumber(reward.item.duration_seconds) or 0) > 0 then
			item = item .. " (" .. math.floor(tonumber(reward.item.duration_seconds) / 60) .. " min)"
		end
		table.insert(parts, item)
	end
	return table.concat(parts, ", ")
end

-- The value at a path like "leaderstats.Coins" in the player
local function valueAt(player, path)
	local current = player
	for name in string.gmatch(path, "[^%.]+") do
		current = current and current:FindFirstChild(name)
	end
	if current and current:IsA("ValueBase") then
		return current.Value
	end
	return nil
end

local actions = {}

actions.state = function(player)
	-- which of your own functions are set
	local hooks = { OnReward = Core.OnReward ~= nil, OnSpend = Core.OnSpend ~= nil }
	if Live then
		hooks.OnHatch = Live.OnHatch ~= nil
		hooks.OnAnnouncement = Live.OnAnnouncement ~= nil
	end
	local codes = 0
	for _ in pairs(Core.GetActiveCodes()) do
		codes = codes + 1
	end
	return {
		version = version,
		studio = RunService:IsStudio(),
		codes = codes,
		events = Live and #Live.GetEvents() or nil,
		eggs = Live and #Live.GetEggs() or nil,
		maxCurrency = setting("MaxCurrencyPerCode", 0),
		hooks = hooks,
		player = player.Name,
		-- the settings as they work now (Settings tab)
		owner = Manager.IsOwner(player),
		can = canTable(player),
		discordHelpers = (function()
			local count = 0
			for _ in pairs(accessUsers) do
				count = count + 1
			end
			return count
		end)(),
		settings = {
			ShowButton = setting("ShowButton", true),
			ButtonPosition = setting("ButtonPosition", "Left"),
			ManagerPosition = setting("ManagerPosition", "TopRight"),
			EventPosition = setting("EventPosition", "BottomRight"),
			EventEffects = setting("EventEffects", "full"),
			AnnouncementPosition = setting("AnnouncementPosition", "Top"),
			NotificationPosition = setting("NotificationPosition", "Bottom"),
			Language = setting("Language", "auto"),
			MaxCurrencyPerCode = setting("MaxCurrencyPerCode", 0),
			ManagerUsers = setting("ManagerUsers", ""),
		},
	}
end

-- Reads go through Core.RefreshUntilFresh like a notification from the bot, so an older read never wins over a newer one
actions.refresh = function(player)
	Core.RefreshUntilFresh(Core.Refresh)
	if Live then
		Core.RefreshUntilFresh(Live.RefreshEvents)
		Core.RefreshUntilFresh(Live.RefreshEggs)
	end
	return actions.state(player)
end

-- Where a code, event or egg was made: "game" (this panel) with the name of who made it, or "discord"
local function madeBy(meta, player)
	if type(meta) ~= "table" or meta.origin ~= "game" then
		return "discord", nil
	end
	return "game", type(meta.by) == "string" and meta.by ~= "" and filtered(meta.by, player) or nil
end

actions.codes = function(player)
	local list = {}
	local meta = Core.GetCodeMeta()
	for code, reward in pairs(Core.GetActiveCodes()) do
		if type(reward) == "table" then
			local canGive, why = Core.CanGive(player, reward)
			local origin, by = madeBy(meta[code], player)
			table.insert(list, {
				raw = code,
				code = filtered(code, player),
				reward = rewardText(reward, player),
				expires = tonumber(reward.expires_at) or 0,
				ok = canGive,
				why = why and filtered(why, player) or nil, -- the reason may name a currency written on Discord
				origin = origin,
				by = by,
			})
		end
	end
	table.sort(list, function(a, b)
		return a.raw < b.raw
	end)
	local raw = {}
	for i, entry in ipairs(list) do
		raw[i] = entry.raw
		entry.raw = nil -- the panel gets only filtered text
	end
	lastCodes[player] = raw
	-- custom: your OnReward gives the rewards, so CanGive does not look at the player data
	return { list = list, now = os.time(), studio = RunService:IsStudio(), custom = Core.OnReward ~= nil }
end

-- Only in Studio: in the published game it would let the owner (or a tester) redeem one code again and again
actions.forget = function(player, index)
	if not RunService:IsStudio() then
		return { ok = false, studioOnly = true }
	end
	local code = lastCodes[player] and lastCodes[player][tonumber(index) or 0]
	if not code then
		return { ok = false }
	end
	local ok, err = Core.ForgetRedeemed(player, code)
	return { ok = ok, err = err }
end

-- The game's names from DiscordCatalog (read by the Control module, which checks the forms with them)
local function readCatalog()
	return Control.Catalog()
end

-- A currency: named in the catalog, an egg's price, or (when the catalog names none) anything in leaderstats
-- (Level or Rebirths there are not currencies)
local function isCurrency(path)
	local names = readCatalog().lower
	local name = string.lower(string.match(path, "([^%.]+)$") or "")
	if names[name] or (next(names) == nil and string.sub(path, 1, 12) == "leaderstats.") then
		return true
	end
	for _, egg in ipairs(Live and Live.GetEggs() or {}) do
		if type(egg) == "table" and string.lower(tostring(egg.currency)) == name then
			return true
		end
	end
	return false
end

actions.player = function(player)
	local values, attributes = Core.DescribePlayerData(player)
	local list = {}
	local paths = {}
	for i, entry in ipairs(values) do
		local value = valueAt(player, entry.path)
		paths[i] = entry.path
		table.insert(list, { path = entry.path, class = entry.class, value = value ~= nil and tostring(value) or "",
			currency = RunService:IsStudio() and type(value) == "number" and isCurrency(entry.path) })
	end
	lastValues[player] = paths
	local attrs = {}
	for _, entry in ipairs(attributes) do
		table.insert(attrs, { name = entry.name, value = tostring(player:GetAttribute(entry.name)) })
	end
	return { values = list, attributes = attrs, studio = RunService:IsStudio() }
end

-- Only in Studio: adds to or takes from a number in your player data (in the published game it would be free
-- currency for the owner and the helpers)
local STEPS = { [1000] = true, [-1000] = true, [10000] = true, [-10000] = true }
actions.currency = function(player, arg)
	if not RunService:IsStudio() then
		return { ok = false, studioOnly = true, what = "currency" }
	end
	if type(arg) ~= "table" or not STEPS[tonumber(arg.delta) or 0] then
		return { ok = false }
	end
	local path = lastValues[player] and lastValues[player][tonumber(arg.index) or 0]
	local current = player
	for name in string.gmatch(path or "", "[^%.]+") do
		current = current and current:FindFirstChild(name)
	end
	if not path or not isCurrency(path) or not current or not (current:IsA("IntValue") or current:IsA("NumberValue")) then
		return { ok = false }
	end
	current.Value = math.max(0, current.Value + tonumber(arg.delta))
	return actions.player(player)
end

-- What redeeming a code would do for you now; nothing is used up or given
actions.testCode = function(player, input)
	local key, reason, reward = Core.TestCode(player, string.sub(tostring(input or ""), 1, 60))
	return { ok = true, key = key, reason = reason and filtered(reason, player) or nil,
		reward = reward and rewardText(reward, player) or nil, custom = Core.OnReward ~= nil }
end

-- A gift for the preview: 100 of the first number in the player's data (a real name from the game), or 100 EXP
local function sampleReward(player)
	for _, entry in ipairs((Core.DescribePlayerData(player))) do
		if type(valueAt(player, entry.path)) == "number" then
			return { currency = { name = string.match(entry.path, "([^%.]+)$"), amount = 100 } }
		end
	end
	return { exp = 100 }
end

-- Shows only you what players would see: an announcement, a gift, a hatch or an event icon (nothing is given)
actions.preview = function(player, arg)
	if not Live or type(arg) ~= "table" then
		return { ok = false }
	end
	local data = { text = arg.text, egg = arg.egg, name = arg.name, message = arg.message, animation = arg.animation }
	if arg.kind == "gift" then
		data.reward = sampleReward(player)
	end
	return { ok = Live.Preview(player, arg.kind, data) == true }
end

local function liveRemotes()
	return { Core.FindRemote("DiscordCodesRedeem", "RemoteFunction"), Core.FindRemote("DiscordLiveEvent", "RemoteEvent") }
end

-- reset = back to DiscordSettings: the attribute goes away and the windows use their own copy of the settings again
-- (after a change the attribute stays even for the DiscordSettings value: a template window may have its own one)
local function applySetting(name, value, reset)
	local target = settings and settings:FindFirstChild(name)
	if not target then
		return false
	end
	target.Value = value
	if not SERVER_ONLY[name] then
		for _, remote in ipairs(liveRemotes()) do
			if reset then
				remote:SetAttribute(name, nil)
			else
				remote:SetAttribute(name, value)
			end
		end
	end
	print("[DiscordCodes] Manager: " .. name .. " = " .. tostring(value) .. " on this server (until it restarts)")
	return true
end

actions.setting = function(player, arg)
	if not Manager.Can(player, "settings") then
		return { ok = false, noPermission = true }
	end
	-- the currency limit guards codes and gifts: only the owner changes it
	if type(arg) == "table" and arg.name == "MaxCurrencyPerCode" and not Manager.IsOwner(player) then
		return { ok = false, ownerOnly = true }
	end
	local check = type(arg) == "table" and LIVE_SETTINGS[arg.name]
	if not check or not check(arg.value) or not applySetting(arg.name, arg.value) then
		return { ok = false }
	end
	return actions.state(player)
end

actions.resetSettings = function(player)
	if not Manager.Can(player, "settings") then
		return { ok = false, ownerOnly = true }
	end
	local owner = Manager.IsOwner(player)
	for name in pairs(LIVE_SETTINGS) do
		-- the currency limit stays the owner's: a helper's Reset leaves it as the owner set it
		if startValues[name] ~= nil and (owner or name ~= "MaxCurrencyPerCode") then
			applySetting(name, startValues[name], true)
		end
	end
	return actions.state(player)
end

actions.events = function(player)
	if not Live then
		return { list = {}, used = {} }
	end
	local list = {}
	for _, event in ipairs(Live.GetEvents()) do
		local multipliers = {}
		if type(event.multipliers) == "table" then
			for key, value in pairs(event.multipliers) do
				local name = tostring(key)
				if string.sub(name, 1, 9) == "currency:" then
					local currency = string.sub(name, 10)
					name = currency == "*" and "*" or filtered(currency, player)
				end
				table.insert(multipliers, { name = name, value = tonumber(value) or 1 })
			end
		end
		local origin, by = madeBy(event, player)
		-- the id as it is: a number from the bot, "g5" for one made in this panel
		table.insert(list, { id = event.id, name = filtered(event.name or "", player), ends = tonumber(event.ends_at) or 0,
			starts = tonumber(event.starts_at) or 0,
			multipliers = multipliers, origin = origin, by = by, scope = event.scope == "server" and "server" or "all",
			animation = type(event.animation) == "string" and event.animation or nil })
	end
	-- what your code gets now from Live.GetMultiplier, only for the names it already asked for (asking for a new name
	-- here would tell the bot that your game uses that multiplier)
	local used = {}
	for _, kind in ipairs(Live.GetUsedMultipliers()) do
		table.insert(used, { name = tostring(kind), value = Live.PeekMultiplier(kind) })
	end
	return { list = list, used = used, now = os.time() }
end

actions.eggs = function(player)
	if not Live then
		return { list = {} }
	end
	local list = {}
	local spots = {}
	for _, name in ipairs(Live.GetSpotNames()) do
		spots[name] = true
	end
	for _, egg in ipairs(Live.GetEggs()) do
		if type(egg) == "table" and egg.id ~= nil then
			local pets = {}
			for _, pet in ipairs(Live.GetChances(egg.id)) do
				table.insert(pets, { name = filtered(pet.name, player), chance = pet.chance })
			end
			local origin, by = madeBy(egg, player)
			table.insert(list, {
				id = egg.id,
				name = filtered(egg.name or "", player),
				price = tonumber(egg.price) or 0,
				currency = filtered(egg.currency or "", player),
				ends = tonumber(egg.ends_at) or 0,
				pets = pets,
				-- the spot only when the game has it (then it is the game's own name, not text from Discord)
				spot = spots[egg.spot] and egg.spot or "",
				origin = origin,
				by = by,
			})
		end
	end
	return { list = list, now = os.time() }
end

-- Rolls the egg many times with the chances players get now and only counts the results: nothing is given
actions.simulate = function(player, arg)
	if not Live or type(arg) ~= "table" then
		return { ok = false }
	end
	local times = math.clamp(math.floor(tonumber(arg.times) or 100), 1, MAX_SIMULATION)
	local chances = Live.GetChances(arg.id)
	local total = 0
	for _, pet in ipairs(chances) do
		total = total + math.max(0, tonumber(pet.chance) or 0)
	end
	if total <= 0 then
		return { ok = false }
	end
	-- like a real opening, a pet with 0% never comes out (a rounding rest goes to the last pet that can)
	local lastPossible = 0
	for i, pet in ipairs(chances) do
		if (tonumber(pet.chance) or 0) > 0 then
			lastPossible = i
		end
	end
	local counts = {}
	local random = Random.new()
	for _ = 1, times do
		local roll = random:NextNumber() * total
		local got = lastPossible
		for i, pet in ipairs(chances) do
			local chance = math.max(0, tonumber(pet.chance) or 0)
			roll = roll - chance
			if chance > 0 and roll <= 0 then
				got = i
				break
			end
		end
		counts[got] = (counts[got] or 0) + 1
	end
	local result = {}
	for i, pet in ipairs(chances) do
		table.insert(result, { name = filtered(pet.name, player), chance = pet.chance, got = counts[i] or 0 })
	end
	return { ok = true, times = times, list = result }
end

-- A normal purchase, for the egg's price (the result appears like for any player)
actions.open = function(player, id)
	if not Live then
		return { ok = false }
	end
	Live.OpenEgg(player, id)
	return { ok = true }
end

actions.gifts = function(player)
	if not Live then
		return { ok = false }
	end
	Live.DeliverGifts(player)
	return { ok = true }
end

-- The kit's messages may name codes, eggs or currencies written on Discord: filtered like everything else
actions.log = function(player)
	local entries, list = {}, {}
	for i, entry in ipairs(log) do -- a copy: new lines may come while the filter answers
		entries[i] = entry
	end
	for i, entry in ipairs(entries) do
		-- the kit's own tag is not filtered: Roblox hides a whole line that names another platform
		local text = string.gsub(string.gsub(entry.text, "^%[DiscordCodes%]%s*", ""), "^%[DiscordLive%]%s*", "")
		list[i] = { text = text == "" and "" or filteredLine(text, player), kind = entry.kind }
	end
	return { list = list }
end

-- ---------- 🛡️ Manager access (only the owner) ----------
-- Who besides the owner may open the panel and what each may do. The same list as on Discord (/setup -> 🛡️
-- Permissions -> Manager in the game): saved in the DataStore entry ManagerAccess, the bot reads it from there.

local function accessEntry(userId)
	local list = {}
	local perms = accessUsers[userId] or {}
	for _, name in ipairs(GAME_PERMISSIONS) do
		if perms[name] then
			table.insert(list, name)
		end
	end
	return { id = userId, name = accessNames[userId] or "", permissions = list, listed = accessUsers[userId] ~= nil }
end

local function accessList()
	local users = {}
	for userId in pairs(accessUsers) do
		table.insert(users, accessEntry(userId))
	end
	table.sort(users, function(a, b)
		return string.lower(a.name) < string.lower(b.name)
	end)
	return { ok = true, users = users, max = MAX_ACCESS_USERS, permissions = GAME_PERMISSIONS }
end

-- Changes the saved list (change(users) edits it; false cancels with that reason) and tells the other servers
local function saveAccess(change)
	local saved, refused
	local ok, err = pcall(function()
		DataStoreService:GetDataStore(accessStore):UpdateAsync(ACCESS_KEY, function(old)
			local data = type(old) == "table" and old or {}
			local users = type(data.users) == "table" and data.users or {}
			refused = change(users)
			if refused then
				return nil -- nothing is written
			end
			-- always later than the last change (the bot's clock may run ahead of Roblox's: the newer list must win)
			local stamp = math.max(os.time(), (tonumber(data.updated_at) or 0) + 1)
			saved = { version = 1, users = users, updated_at = stamp, by = "game" }
			return saved
		end)
	end)
	if not ok then
		warn("[DiscordCodes] Manager: could not save who may use the Manager: " .. tostring(err))
		return { ok = false, key = RunService:IsStudio() and "accessStudio" or "accessFailed" }
	end
	if refused then
		return { ok = false, key = refused }
	end
	accessReads = accessReads + 1 -- a read that started before this save would bring back the old list
	useAccess(saved)
	refreshPlayers()
	if Live and Live.Config then -- the other servers read the list at once (otherwise within a minute)
		Core.Publish(Live.Config.MessagingTopic or "DiscordLive", { type = "access", at = os.time() })
	end
	return accessList()
end

actions.access = function(player, arg)
	if not Manager.IsOwner(player) then
		return { ok = false, ownerOnly = true }
	end
	arg = type(arg) == "table" and arg or {}
	if arg.op == "find" then
		local typed = string.gsub(tostring(arg.name or ""), "^@", "")
		if not string.match(typed, "^[%w_]+$") or #typed > 20 then
			return { ok = false, key = "accessNotFound" }
		end
		local okId, userId = pcall(function()
			return Players:GetUserIdFromNameAsync(typed)
		end)
		if not okId or not userId then
			return { ok = false, key = "accessNotFound" }
		end
		local okName, name = pcall(function()
			return Players:GetNameFromUserIdAsync(userId)
		end)
		if userId == player.UserId or (Control and userId == Control.GameOwnerId()) then
			return { ok = false, key = "accessOwner" }
		end
		local entry = accessEntry(userId)
		entry.name = okName and name or typed
		return { ok = true, user = entry }
	elseif arg.op == "save" or arg.op == "remove" then
		local userId = tonumber(arg.userId)
		if not userId or userId <= 0 or userId ~= math.floor(userId) then
			return { ok = false }
		end
		if userId == player.UserId or (Control and userId == Control.GameOwnerId()) then
			return { ok = false, key = "accessOwner" }
		end
		local perms = {}
		for _, name in ipairs(type(arg.permissions) == "table" and arg.permissions or {}) do
			if table.find(GAME_PERMISSIONS, name) and not table.find(perms, name) then
				table.insert(perms, name)
			end
		end
		-- the name as Roblox has it (the panel's text is not trusted: the bot shows it on Discord)
		local name = ""
		if arg.op == "save" then
			local okName, robloxName = pcall(function()
				return Players:GetNameFromUserIdAsync(userId)
			end)
			name = okName and type(robloxName) == "string" and string.sub(robloxName, 1, 40) or ""
		end
		return saveAccess(function(users)
			local key = tostring(userId)
			if arg.op == "remove" then
				users[key] = nil
				return nil
			end
			if users[key] == nil then
				local count = 0
				for _ in pairs(users) do
					count = count + 1
				end
				if count >= MAX_ACCESS_USERS then
					return "accessFull"
				end
			end
			users[key] = { name = name ~= "" and name or (type(users[key]) == "table" and users[key].name) or key,
				permissions = perms }
			return nil
		end)
	end
	return accessList()
end


-- ---------- Changes ----------
-- The owner creates and removes codes, events, eggs, gifts, announcements and bans here, and the game does them at
-- once, by itself (the Control module, the same checks as on Discord). The bot doesn't have to run: when it does, it
-- writes each change to the Discord log channel.
-- each change and the permission it needs (Discord -> /setup -> 🛡️ Permissions -> Manager in the game)
local KINDS = { code_add = "codes", code_remove = "codes", event_start = "events", event_stop = "events",
	egg_create = "eggs", egg_move = "eggs", egg_remove = "eggs", gift = "gifts", announce = "announce",
	find_player = "bans", ban = "bans", unban = "bans" }

-- Only plain short values from the form (Control checks each of them again)
local function cleanData(data)
	local clean = {}
	for key, value in pairs(data) do
		local fits = type(value) == "boolean" or (type(value) == "string" and #value <= 1500)
			or (type(value) == "number" and value == value and math.abs(value) <= 1e13)
		if type(key) == "string" and #key <= 20 and fits then
			clean[key] = value
		end
	end
	return clean
end

-- A value of the answer as the panel shows it: texts typed by someone are filtered, a reward becomes its text, a
-- Roblox user name ({ plain = }) stays as it is (a ban must name exactly that account), { duration = } and
-- { text = } are said by the panel in its own language
local function shownValue(value, player)
	if type(value) == "table" then
		if value.reward then
			return rewardText(value.reward, player)
		elseif value.plain then
			return tostring(value.plain)
		end
		return { duration = value.duration, text = value.text }
	elseif type(value) == "string" then
		return filteredLine(value, player)
	end
	return tostring(value)
end

local function shownValues(list, player)
	local result = {}
	for i, value in ipairs(type(list) == "table" and list or {}) do
		result[i] = shownValue(value, player)
	end
	return result
end

actions.change = function(player, arg)
	if type(arg) ~= "table" or not KINDS[arg.kind] or type(arg.data) ~= "table" or not Control then
		return { ok = false }
	end
	if not Manager.Can(player, KINDS[arg.kind]) then
		return { ok = false, noPermission = true }
	end
	-- a helper never sends a gift to themselves (the owner may: their own test)
	if arg.kind == "gift" and not Manager.IsOwner(player)
		and string.lower(tostring(arg.data.player or "")) == string.lower(player.Name) then
		return { ok = true, done = false, key = "giftSelf", args = {}, warns = {} }
	end
	local data = cleanData(arg.data)
	if arg.kind == "gift" and not Manager.IsOwner(player) then
		data.notToSelf = true -- Control checks the player it found (a typed UserId or name with spaces is the same person)
	end
	if arg.kind == "code_remove" then -- the panel names a code by its place in the list it showed (it got filtered text)
		data = { code = lastCodes[player] and lastCodes[player][tonumber(arg.data.index) or 0] }
		if not data.code then
			return { ok = false }
		end
	end
	local result = Control.Do(player, arg.kind, data)
	local warns = {}
	for i, entry in ipairs(result.warns or {}) do
		warns[i] = { key = entry.key, args = shownValues(entry.args, player) }
	end
	local extra = result.extra and { user_id = tonumber(result.extra.user_id), username = tostring(result.extra.username or "") } or nil
	return { ok = true, done = result.ok == true, key = result.key, args = shownValues(result.args, player), warns = warns,
		extra = extra }
end

-- What the forms offer: the game's currencies and items (DiscordCatalog, egg prices) and the egg spots
actions.forms = function(player)
	local catalog = readCatalog()
	local currencies, seen = {}, {}
	local function add(name)
		name = tostring(name or "")
		if name ~= "" and not seen[string.lower(name)] then
			seen[string.lower(name)] = true
			table.insert(currencies, name)
		end
	end
	for _, name in ipairs(catalog.currencies) do
		add(name)
	end
	-- the egg prices' currencies only when the catalog names none (otherwise a name outside it would be refused)
	for _, egg in ipairs(#catalog.currencies == 0 and Live and Live.GetEggs() or {}) do
		if type(egg) == "table" then
			add(egg.currency)
		end
	end
	-- names from the catalog or Discord are shown filtered, but sent back exactly as the game has them
	local function both(list)
		local result = {}
		for _, name in ipairs(list) do
			table.insert(result, { value = name, label = filtered(name, player) })
		end
		return result
	end
	-- a code or a gift can give an item or a pet (the same as on Discord)
	local items, seenItems = {}, {}
	for _, list in ipairs({ catalog.items, catalog.pets }) do
		for _, name in ipairs(list) do
			if not seenItems[string.lower(name)] then
				seenItems[string.lower(name)] = true
				table.insert(items, name)
			end
		end
	end
	return { owner = Manager.IsOwner(player), can = canTable(player), currencies = both(currencies), items = both(items),
		spots = Live and Live.GetSpotNames() or {}, animations = Control and Control.Animations or {} }
end

-- What a tab's reads need (any one of them): a helper sees only the tabs of what they may do, and the server refuses
-- the rest too (the codes list must not reach someone who may only run events). Start (state, refresh, log) and the
-- forms' lists are for everyone who has the panel; the changes check their own permission.
local NEEDS = { codes = { "codes" }, forget = { "codes" }, events = { "events" }, eggs = { "eggs" }, simulate = { "eggs" },
	open = { "eggs" }, gifts = { "gifts" }, player = { "bans", "players" }, currency = { "bans", "players" },
	preview = { "settings" }, testCode = { "codes" } }

local function mayRead(player, action, arg)
	local needs = NEEDS[action]
	-- the event form's 👁 shows its animation: also for whoever may run events
	if action == "preview" and type(arg) == "table" and arg.kind == "animation" then
		needs = { "settings", "events" }
	end
	if not needs then
		return true
	end
	for _, permission in ipairs(needs) do
		if Manager.Can(player, permission) then
			return true
		end
	end
	return false
end

local function onInvoke(player, action, arg)
	if not Manager.IsAllowed(player) then
		return { ok = false, denied = true }
	end
	local handler = type(action) == "string" and actions[action]
	if not handler then
		return { ok = false }
	end
	if not mayRead(player, action, arg) then
		return { ok = false, noPermission = true }
	end
	if busy[player] then
		return { ok = false, busy = true }
	end
	local cooldown = COOLDOWNS[action]
	if cooldown then
		lastCall[player] = lastCall[player] or {}
		local last = lastCall[player][action]
		if last and os.clock() - last < cooldown then
			return { ok = false, wait = math.ceil(cooldown - (os.clock() - last)) }
		end
		lastCall[player][action] = os.clock()
	end
	busy[player] = true
	local ok, result = pcall(handler, player, arg)
	busy[player] = nil
	if not ok then
		warn("[DiscordCodes] Manager: " .. tostring(result))
		return { ok = false, error = true }
	end
	return result
end

-- The kit's own lines from the Output window, newest last
local function onMessage(message, messageType)
	local ours = string.find(message, "[Discord", 1, true) == 1
		or (messageType == Enum.MessageType.MessageError and string.find(message, "DiscordCodes", 1, true) ~= nil)
	if not ours then
		return
	end
	local kind = messageType == Enum.MessageType.MessageWarning and "warn"
		or messageType == Enum.MessageType.MessageError and "error"
		or "info"
	table.insert(log, { text = string.sub(message, 1, 300), kind = kind, at = os.time() })
	if #log > MAX_LOG then
		table.remove(log, 1)
	end
end

-- template: the ScreenGui with the panel's LocalScript, given only to allowed players
function Manager.Start(options)
	Core, Live, Control = options.core, options.live, options.control
	version, settings = options.version, options.settings
	for name in pairs(LIVE_SETTINGS) do
		local value = settings and settings:FindFirstChild(name)
		startValues[name] = value and value.Value
	end
	if setting("Manager", true) == false then
		return
	end
	local remote = Core.FindRemote("DiscordManager", "RemoteFunction")
	remote.OnServerInvoke = onInvoke
	for _, entry in ipairs(LogService:GetLogHistory()) do
		onMessage(entry.message, entry.messageType)
	end
	LogService.MessageOut:Connect(onMessage)

	local template = options.template
	local function give(player)
		if not template then
			return
		end
		-- a group game asks Roblox for the rank: when Roblox doesn't answer, it is asked again a few times
		local allowed = Manager.IsAllowed(player)
		for _ = 1, 3 do
			if allowed or allowedCache[player] ~= nil or not player.Parent then
				break
			end
			task.wait(10)
			allowed = Manager.IsAllowed(player)
		end
		if not allowed then
			return
		end
		local playerGui = player:WaitForChild("PlayerGui", 30)
		-- asked again: the list from Discord may have changed while waiting
		if playerGui and not playerGui:FindFirstChild(template.Name) and Manager.IsAllowed(player) then
			local copy = template:Clone()
			if settings then
				settings:Clone().Parent = copy
			end
			copy.Parent = playerGui
			local client = copy:FindFirstChildWhichIsA("LocalScript")
			if client then
				client.Disabled = false
			end
		end
	end
	Players.PlayerAdded:Connect(function(player)
		task.spawn(give, player)
	end)

	-- The list from Discord: read now, every minute and at once when the bot sends a notice. Who was added gets the
	-- panel without rejoining; who was removed loses it (the server checks every action anyway).
	local storeName = Live and Live.Config and Live.Config.LiveDataStore or "DiscordLiveContent"
	accessStore = storeName
	refreshPlayers = function()
		for _, player in ipairs(Players:GetPlayers()) do
			allowedCache[player] = nil
			if Manager.IsAllowed(player) then
				task.spawn(give, player)
			elseif allowedCache[player] == false then -- a sure "no" (not Roblox failing to answer for a group game)
				local playerGui = player:FindFirstChild("PlayerGui")
				local shown = template and playerGui and playerGui:FindFirstChild(template.Name)
				if shown then
					shown:Destroy()
				end
			end
		end
	end
	local function applyAccess()
		if loadAccess(storeName) then
			refreshPlayers()
		end
	end
	loadAccess(storeName)
	if Live then
		Live.OnAccess = function()
			task.spawn(applyAccess)
		end
	end
	task.spawn(function()
		while true do
			task.wait(ACCESS_POLL_SECONDS)
			applyAccess()
		end
	end)
	for _, player in ipairs(Players:GetPlayers()) do
		task.spawn(give, player)
	end
	Players.PlayerRemoving:Connect(function(player)
		allowedCache[player] = nil
		busy[player] = nil
		lastCodes[player] = nil
		lastValues[player] = nil
		ownerCache[player] = nil
		lastCall[player] = nil
	end)
end

return Manager
