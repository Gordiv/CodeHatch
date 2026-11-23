--!nonstrict
--[[
	DiscordCodes / Control  (ModuleScript)

	What the game's owner creates and removes in the ⚙️ Manager: codes, events, eggs, gifts, announcements and bans.
	The game does all of it BY ITSELF, the Discord bot doesn't have to run:
	- codes, events and eggs go into the same DataStore entries the bot uses (DiscordCodeSync -> ActiveCodes,
	  DiscordLiveContent -> Events and Eggs), each change in one UpdateAsync, so two servers (or the bot) never
	  overwrite each other, and every server shows it within a second or two;
	- a gift is saved in DiscordGifts like a /give from Discord (the player gets it now, or when they join next time);
	- an announcement goes to every server through MessagingService;
	- a ban uses Players:BanAsync for every place of the game. It needs Players -> BanningEnabled turned on (Studio:
	  select Players in the Explorer, Properties), then publish.
	Every change is also written to DiscordLiveContent -> "PanelLog" (the newest 100). The bot, when it runs, writes
	them to the Discord log channel and keeps a copy of the codes, events and eggs, so Discord lists and changes them.
	The checks are the same as on Discord: names from DiscordCatalog, MaxCurrencyPerCode, at most 10 events and 20 eggs.
	Only the Manager module calls Control.Do, and only for the game's owner.

	Control.Do returns { ok = true/false, key = the panel's message, args = its values, warns = { { key, args } },
	extra = data for the panel }. Texts typed by the owner stay as they were typed: the Manager filters them.
]]

local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local Control = {}

local LOG_KEY = "PanelLog" -- the bot reads it (cogs/game_requests.py in the bot)
local MAX_LOG = 100
local MAX_EVENTS, MAX_EGGS, MAX_PETS = 10, 20, 25 -- the same limits as the bot
local MAX_AMOUNT = 1000000000
local MAX_PRICE = 1000000000000
local MAX_WEIGHT = 1000000000
local WHITE = "#F5F5F5" -- the egg color the bot uses when none is picked
local UNITS = { m = 60, h = 3600, d = 86400 }

-- The choices of the panel's forms (the same keys as the bot's commands)
local function set(list)
	local result = {}
	for _, value in ipairs(list) do
		result[value] = true
	end
	return result
end
local CODE_VALIDITY = set({ "24h", "3d", "7d", "14d", "30d", "unlimited" })
local ITEM_DURATIONS = set({ "permanent", "1h", "3h", "6h", "12h", "24h", "3d", "7d", "14d", "30d" })
local EVENT_DURATIONS = set({ "1m", "5m", "10m", "20m", "1h", "3h", "6h", "12h", "24h", "3d", "7d" })
local EGG_DURATIONS = set({ "unlimited", "24h", "3d", "7d", "14d", "30d" })
local BAN_DURATIONS = set({ "1h", "24h", "7d", "30d", "permanent" })
local ANNOUNCE_SECONDS = { [5] = true, [10] = true, [15] = true, [30] = true, [60] = true }
local MAX_MULTIPLIER = 100 -- the same as Live.Config.MaxMultiplier
local COUNTDOWN = 10 -- seconds from making an event to its start (the players see a countdown); the bot waits the same
-- The event animations the players' devices have (Effects.Names() in DiscordLiveClient -> Effects; a test keeps them equal)
Control.Animations = { "coin_storm", "aurora", "lucky_breeze", "meteor_shower", "sakura_festival" }
local ANIMATIONS = set(Control.Animations)

local Core, Live, Report, liveStore

-- ---------- Small helpers ----------

-- "7d" -> 604800; "unlimited" and "permanent" -> 0
local function seconds(key)
	local amount, unit = string.match(tostring(key), "^(%d+)([mhd])$")
	return amount and tonumber(amount) * UNITS[unit] or 0
end

local function trim(text)
	return (string.match(tostring(text or ""), "^%s*(.-)%s*$"))
end

-- Length in letters (a Polish letter or an emoji is one)
local function length(text)
	return utf8.len(text) or #text
end

local function contains(list, value)
	for _, entry in ipairs(list) do
		if entry == value then
			return true
		end
	end
	return false
end

-- A whole number from the form (empty = 0), or nil
local function wholeNumber(value)
	if value == nil or value == "" then
		return 0
	end
	value = tonumber(value)
	if not value or value ~= value or value < 0 or value ~= math.floor(value) or value > 1e15 then
		return nil
	end
	return value
end

local function fail(key, ...)
	return { ok = false, key = key, args = { ... } }
end

local function done(key, ...)
	return { ok = true, key = key, args = { ... }, warns = {} }
end

local function warnAbout(result, key, ...)
	table.insert(result.warns, { key = key, args = { ... } })
	return result
end

local function saveFailed(err)
	return fail(Core.IsStudioError(err) and "studioApi" or "saveFailed", tostring(err))
end

-- The same rule as the bot (has_link in cogs/live_game.py): Roblox shows a whole text with a link as #### to every
-- player. A domain with a path (youtu.be/abc), or a known ending (roblox.com); "Awww." or "v1.2" are not links.
local ENDINGS = set({ "com", "net", "org", "gg", "io", "xyz", "pl", "ru", "de", "tv", "ly", "link", "app", "dev", "uk", "es",
	"fr", "info", "site", "online", "shop", "store", "ee", "gl", "eu", "tk", "cc", "mx", "ar", "cl", "pe" })
function Control.HasLink(text)
	local lower = string.lower(tostring(text or ""))
	if string.find(lower, "https?://") or string.find(lower, "www%.%w") or string.find(lower, "discord%s*%.%s*gg/")
		or string.find(lower, "[%w_%-]%.%a%a+/") then
		return true
	end
	for ending, after in string.gmatch(lower, "[%w_%-]%.(%a+)(.?)") do
		if ENDINGS[ending] and not string.match(after, "[%w_]") then
			return true
		end
	end
	return false
end
local hasLink = Control.HasLink

-- ---------- The game's names (DiscordCatalog) ----------

-- { currencies, items, pets, robux = lists of names, lower = { [currency in lowercase] = true } }. Read once, at
-- most 2 s (a module that waits forever must not stop the panel); a failed read is tried again next time, and a
-- catalog that still has only the template's example names (Coins, Gems...) counts as empty.
local EMPTY_CATALOG = { currencies = {}, items = {}, pets = {}, robux = {}, lower = {} }
local catalogNames = nil
local catalogLoading = false
function Control.Catalog()
	if catalogNames then
		return catalogNames
	end
	if catalogLoading then
		local waited = 0
		while catalogLoading and waited < 2 do
			waited = waited + task.wait(0.1)
		end
		return catalogNames or EMPTY_CATALOG
	end
	catalogLoading = true
	local result = nil
	task.spawn(function()
		local ok, catalog = pcall(function()
			return Report and Report.ReadCatalog()
		end)
		local names = { currencies = {}, items = {}, pets = {}, robux = {}, lower = {} }
		local template = false
		for _, problem in ipairs(ok and type(catalog) == "table" and catalog.problems or {}) do
			template = template or problem.code == "template"
		end
		if ok and type(catalog) == "table" and not template then
			for _, name in ipairs(catalog.currencies or {}) do
				table.insert(names.currencies, tostring(name))
				names.lower[string.lower(tostring(name))] = true
			end
			for _, name in ipairs(catalog.items or {}) do
				table.insert(names.items, tostring(name))
			end
			for _, pet in ipairs(catalog.pets or {}) do
				table.insert(names.pets, tostring(type(pet) == "table" and pet.name or pet))
			end
			for _, name in ipairs(catalog.robux or {}) do
				table.insert(names.robux, tostring(name))
			end
		end
		result = ok and names or false
	end)
	local waited = 0
	while result == nil and waited < 2 do
		waited = waited + task.wait(0.1)
	end
	catalogNames = result or nil
	catalogLoading = false
	return catalogNames or EMPTY_CATALOG
end

-- How the bot compares names: letter case and extra spaces don't matter
local function nameKey(name)
	return string.lower((string.gsub(trim(name), "%s+", " ")))
end

local function loose(name)
	return string.lower((string.gsub(tostring(name), "[^%w]", "")))
end

-- The name in the catalog's spelling; nil when the list has names and this isn't one of them. An empty list
-- accepts any name (like the bot: the owner hasn't filled that list in).
local function resolve(list, name)
	name = trim(name)
	if name == "" then
		return nil
	end
	if #list == 0 then
		return name
	end
	for _, candidate in ipairs(list) do
		if nameKey(candidate) == nameKey(name) then
			return candidate
		end
	end
	local found = nil
	for _, candidate in ipairs(list) do -- the game's looser rule ("Uncle Pet" = "UnclePet"), only for one name
		if loose(candidate) ~= "" and loose(candidate) == loose(name) then
			if found then
				return nil
			end
			found = candidate
		end
	end
	return found
end

-- What a code or a gift can give: the catalog's items and pets
local function rewardNames(catalog)
	local names = {}
	for _, list in ipairs({ catalog.items, catalog.pets }) do
		for _, name in ipairs(list) do
			table.insert(names, name)
		end
	end
	return names
end

-- The names in a reward that players can buy with Robux (DiscordCatalog -> SoldForRobux)
local function robuxNames(reward, catalog)
	local found = {}
	for _, name in ipairs({ reward.currency and reward.currency.name, reward.item and reward.item.name }) do
		for _, sold in ipairs(catalog.robux) do
			if name and nameKey(sold) == nameKey(name) then
				table.insert(found, name)
				break
			end
		end
	end
	return table.concat(found, ", ")
end

-- A reward from the form (codes and gifts): { currency, exp, item } or nil and the answer for the panel
local function buildReward(data)
	local catalog = Control.Catalog()
	local reward = {}
	local amount = wholeNumber(data.amount)
	local exp = wholeNumber(data.exp)
	if not amount or not exp or amount > MAX_AMOUNT or exp > MAX_AMOUNT then
		return nil, fail("badValue")
	end
	local currency = trim(data.currency)
	if (currency ~= "") ~= (amount > 0) then
		return nil, fail("currencyAmount")
	end
	if currency ~= "" then
		local name = resolve(catalog.currencies, currency)
		if not name then
			return nil, fail("unknownName", currency)
		end
		local limit = Core.CurrencyLimit()
		if limit > 0 and amount > limit then
			return nil, fail("tooMuch", amount, limit)
		end
		reward.currency = { name = name, amount = amount }
	end
	if exp > 0 then
		reward.exp = exp
	end
	local item = trim(data.item)
	if item ~= "" then
		local name = resolve(rewardNames(catalog), item)
		local duration = data.item_duration or "permanent"
		if not name then
			return nil, fail("unknownName", item)
		end
		if not ITEM_DURATIONS[duration] then
			return nil, fail("badValue")
		end
		reward.item = { name = name, is_temporary = seconds(duration) > 0, duration_seconds = seconds(duration) }
	end
	if next(reward) == nil then
		return nil, fail("noReward")
	end
	return reward
end

-- "Cat:60, Dog:35, Dragon:5" -> { { name = "Cat", chance = 60 }, ... } with the chances turned into percentages,
-- the names in the catalog's spelling (the same rule as /egg-create). nil and the answer for the panel otherwise.
local function parsePets(text, known)
	text = string.gsub(tostring(text or ""), "(%d),(%d)", "%1.%2") -- "0,5" is a decimal number, not two entries
	local pets, seen, total = {}, {}, 0
	for piece in string.gmatch(text .. ",", "([^,;\n]*)[,;\n]") do
		local part = trim(piece)
		if part ~= "" then
			local typed, number = string.match(part, "^(.-)%s*[:=]%s*(%d+%.?%d*)%s*%%?$")
			local name = trim(typed)
			local weight = tonumber(number or "")
			if name == "" or not weight or weight <= 0 or weight > MAX_WEIGHT or length(name) > 50 then
				return nil, fail("badPets", part)
			end
			if seen[string.lower(name)] then
				return nil, fail("petTwice", name)
			end
			seen[string.lower(name)] = true
			table.insert(pets, { name = name, weight = weight })
			total = total + weight
		end
	end
	if #pets == 0 then
		return nil, fail("badPets", "")
	end
	if #pets > MAX_PETS then
		return nil, fail("tooManyPets", MAX_PETS)
	end
	local unknown = {}
	for _, pet in ipairs(pets) do
		local name = resolve(known, pet.name)
		if name then
			pet.name = name
		else
			table.insert(unknown, pet.name)
		end
	end
	if #unknown > 0 then
		return nil, fail("unknownPets", table.concat(unknown, ", "))
	end
	local result = {}
	for _, pet in ipairs(pets) do
		-- never rounded down to 0: a pet that has a chance must be able to drop
		local chance = math.floor(pet.weight * 100 / total * 10000 + 0.5) / 10000
		table.insert(result, { name = pet.name, chance = math.max(chance, 0.0001) })
	end
	return result
end

-- ---------- Players (gifts and bans) ----------

local function nameOf(userId)
	local ok, name = pcall(function()
		return Players:GetNameFromUserIdAsync(userId)
	end)
	return ok and type(name) == "string" and name or nil
end

-- The account a gift or a ban is for: a username or a user ID. A number that is the ID of one account and the name
-- of another is refused instead of guessed. Returns { id, name } or nil and the message key.
local function findPlayer(text)
	text = trim(text)
	if text == "" or #text > 25 then
		return nil, "noPlayer"
	end
	local byId, byName = nil, nil
	if string.match(text, "^%d+$") then
		local name = nameOf(tonumber(text))
		if name then
			byId = { id = tonumber(text), name = name }
		end
	end
	if string.match(text, "^[%w_]+$") and #text >= 3 and #text <= 20 then
		local ok, id = pcall(function()
			return Players:GetUserIdFromNameAsync(text)
		end)
		if ok and tonumber(id) then
			byName = { id = tonumber(id), name = nameOf(tonumber(id)) or text }
		end
	end
	if byId and byName and byId.id ~= byName.id then
		return nil, "ambiguous"
	end
	local found = byName or byId
	if not found then
		return nil, "noPlayer"
	end
	return found
end

-- ---------- The log for the bot ----------

-- One change, for the bot to write to the Discord log channel (and to copy what it made). Never stops the change.
local function logChange(player, kind, data)
	task.spawn(function()
		local ok, err = pcall(function()
			liveStore:UpdateAsync(LOG_KEY, function(old)
				old = type(old) == "table" and old or {}
				local entries = type(old.entries) == "table" and old.entries or {}
				local seq = math.max(math.floor(tonumber(old.next) or 1), 1)
				table.insert(entries, { seq = seq, at = os.time(), by = player.UserId, name = player.Name, kind = kind, data = data })
				while #entries > MAX_LOG do
					table.remove(entries, 1)
				end
				return { next = seq + 1, entries = entries }
			end)
		end)
		if not ok and not Core.IsStudioError(err) then
			warn("[DiscordCodes] Manager: " .. kind .. " was done, but the log for the bot could not be saved: " .. tostring(err))
		end
	end)
end

-- ---------- What each change does ----------

local handlers = {}

function handlers.code_add(player, data)
	local code = string.upper((string.gsub(tostring(data.code or ""), "%s+", "")))
	if code == "" or #code > 30 or not string.match(code, "^[A-Z0-9_%-]+$") then
		return fail("badCode")
	end
	if not CODE_VALIDITY[data.validity or ""] then
		return fail("badValue")
	end
	local reward, problem = buildReward(data)
	if not reward then
		return problem
	end
	local valid = seconds(data.validity)
	reward.expires_at = valid > 0 and os.time() + valid or 0
	local exists = false
	local ok, err = Core.ChangeCodes(function(saved)
		exists = saved.codes[code] ~= nil
		if exists then
			return false
		end
		saved.codes[code] = reward
		saved.meta[code] = { origin = "game", by = player.Name, by_id = player.UserId, at = os.time() }
		return true
	end)
	if not ok then
		return saveFailed(err)
	end
	if exists then
		return fail("codeExists", code)
	end
	logChange(player, "code_add", { code = code, reward = reward })
	local result = done("codeAdded", code, { reward = reward }, { duration = data.validity })
	local robux = robuxNames(reward, Control.Catalog())
	if robux ~= "" then
		warnAbout(result, "warnRobux", robux)
	end
	return result
end

function handlers.code_remove(player, data)
	local code = string.upper(tostring(data.code or ""))
	local found = false
	local ok, err = Core.ChangeCodes(function(saved)
		found = saved.codes[code] ~= nil
		if not found then
			return false
		end
		saved.codes[code] = nil
		saved.meta[code] = nil
		return true
	end)
	if not ok then
		return saveFailed(err)
	end
	if not found then
		return fail("notFound")
	end
	logChange(player, "code_remove", { code = code })
	return done("codeRemoved", code)
end

function handlers.event_start(player, data)
	local name = trim(data.name)
	if name == "" or not EVENT_DURATIONS[data.duration or ""] then
		return fail("badValue")
	end
	if length(name) > 50 then
		return fail("longText", { text = "name" }, 50)
	end
	-- any multiplier from 1.1 to 100 (two decimals at most): the form's list or a number typed in
	local factor = tonumber((string.gsub(tostring(data.currency_x or data.exp_x or data.luck_x or ""), ",", ".")))
	if not factor or factor ~= factor or factor < 1.1 or factor > MAX_MULTIPLIER then
		return fail("badMultiplier", MAX_MULTIPLIER)
	end
	factor = math.floor(factor * 100 + 0.5) / 100
	local animation = data.animation or ""
	if animation ~= "" and not ANIMATIONS[animation] then
		return fail("badValue")
	end
	local scope = data.scope or "all"
	if scope ~= "all" and scope ~= "server" then
		return fail("badValue")
	end
	local multipliers = {}
	if data.exp_x then
		multipliers.exp = factor
	elseif data.luck_x then
		multipliers.luck = factor
	elseif trim(data.currency) == "" then
		multipliers["currency:*"] = factor
	else
		local currency = resolve(Control.Catalog().currencies, data.currency)
		if not currency then
			return fail("unknownName", trim(data.currency))
		end
		multipliers["currency:" .. currency] = factor
	end
	-- the event starts after a 10 s countdown every player sees
	local now = os.time() + COUNTDOWN
	local event = { name = name, multipliers = multipliers, starts_at = now, ends_at = now + seconds(data.duration),
		origin = "game", by = player.Name, by_id = player.UserId, animation = animation ~= "" and animation or nil }
	if scope == "server" then -- this server only: not saved, the other servers and the bot never see it
		local count = 0
		for _ in ipairs(Live.GetEvents()) do
			count = count + 1
		end
		if count >= MAX_EVENTS then
			return fail("tooManyEvents", MAX_EVENTS)
		end
		Live.AddLocalEvent(event)
		logChange(player, "event_start", { id = event.id, name = name, multipliers = multipliers, ends_at = event.ends_at,
			animation = event.animation, scope = "server" })
		return done("eventStartedHere", name, { duration = data.duration })
	end
	local full = false
	local ok, err = Live.ChangeEvents(function(saved)
		full = #saved.events >= MAX_EVENTS
		if full then
			return false
		end
		event.id = Live.NewId(saved)
		table.insert(saved.events, event)
		return true
	end)
	if not ok then
		return saveFailed(err)
	end
	if full then
		return fail("tooManyEvents", MAX_EVENTS)
	end
	logChange(player, "event_start", { id = event.id, name = name, multipliers = multipliers, ends_at = event.ends_at,
		animation = event.animation, scope = "all" })
	return done("eventStarted", name, { duration = data.duration })
end

-- Takes one event or egg (by its id) out of the saved list; returns the result and the removed one
local function removeFrom(changeList, field, id)
	local removed = nil
	local ok, err = changeList(function(saved)
		removed = nil
		for i, item in ipairs(saved[field]) do
			if tostring(item.id) == id then
				removed = item
				table.remove(saved[field], i)
				return true
			end
		end
		return false
	end)
	return ok, err, removed
end

function handlers.event_stop(player, data)
	local here = Live.RemoveLocalEvent(tostring(data.id or "")) -- an event of this server only
	if here then
		logChange(player, "event_stop", { id = here.id, name = here.name, scope = "server" })
		return done("eventStopped", tostring(here.name or ""))
	end
	local ok, err, event = removeFrom(Live.ChangeEvents, "events", tostring(data.id or ""))
	if not ok then
		return saveFailed(err)
	end
	if not event then
		return fail("notFound")
	end
	logChange(player, "event_stop", { id = event.id, name = event.name })
	return done("eventStopped", tostring(event.name or ""))
end

function handlers.egg_create(player, data)
	local name = trim(data.name)
	local price = wholeNumber(data.price)
	if name == "" or not price or price < 1 or price > MAX_PRICE or not EGG_DURATIONS[data.duration or "unlimited"] then
		return fail("badValue")
	end
	if length(name) > 40 then
		return fail("longText", { text = "name" }, 40)
	end
	local catalog = Control.Catalog()
	local currency = resolve(catalog.currencies, data.currency)
	if not currency then
		return fail("unknownName", trim(data.currency))
	end
	local pets, problem = parsePets(data.pets, catalog.pets)
	if not pets then
		return problem
	end
	local spot = trim(data.spot)
	local spots = Live.GetSpotNames()
	if spot ~= "" and not contains(spots, spot) then
		return fail("badSpot", spot)
	end
	local lasts = seconds(data.duration or "unlimited")
	local egg = { name = name, currency = currency, price = price, pets = pets, color = WHITE, spot = spot, template = "",
		ends_at = lasts > 0 and os.time() + lasts or 0, origin = "game", by = player.Name, by_id = player.UserId }
	local why = nil
	local ok, err = Live.ChangeEggs(function(saved)
		why = nil
		if #saved.eggs >= MAX_EGGS then
			why = "tooManyEggs"
			return false
		end
		for _, other in ipairs(saved.eggs) do
			if string.lower(tostring(other.name)) == string.lower(name) then
				why = "eggExists"
				return false
			end
		end
		egg.id = Live.NewId(saved)
		table.insert(saved.eggs, egg)
		return true
	end)
	if not ok then
		return saveFailed(err)
	end
	if why == "tooManyEggs" then
		return fail(why, MAX_EGGS)
	elseif why then
		return fail(why, name)
	end
	logChange(player, "egg_create", { id = egg.id, name = name, currency = currency, price = price, pets = pets, spot = spot,
		ends_at = egg.ends_at })
	local result = done("eggCreated", name, price, currency)
	if #spots == 0 then
		warnAbout(result, "warnNoSpots")
	end
	return result
end

function handlers.egg_move(player, data)
	local spot = trim(data.spot)
	if spot ~= "" and not contains(Live.GetSpotNames(), spot) then
		return fail("badSpot", spot)
	end
	local id = tostring(data.id or "")
	local moved = nil
	local ok, err = Live.ChangeEggs(function(saved)
		moved = nil
		for _, egg in ipairs(saved.eggs) do
			if tostring(egg.id) == id then
				moved = egg
				egg.spot = spot
				return true
			end
		end
		return false
	end)
	if not ok then
		return saveFailed(err)
	end
	if not moved then
		return fail("notFound")
	end
	logChange(player, "egg_move", { id = moved.id, name = moved.name, spot = spot })
	return done("eggMoved", tostring(moved.name or ""), spot ~= "" and spot or { text = "anySpot" })
end

function handlers.egg_remove(player, data)
	local ok, err, egg = removeFrom(Live.ChangeEggs, "eggs", tostring(data.id or ""))
	if not ok then
		return saveFailed(err)
	end
	if not egg then
		return fail("notFound")
	end
	logChange(player, "egg_remove", { id = egg.id, name = egg.name })
	return done("eggRemoved", tostring(egg.name or ""))
end

function handlers.gift(player, data)
	local reward, problem = buildReward(data)
	if not reward then
		return problem
	end
	local message = trim(data.message)
	if length(message) > 150 then
		return fail("longText", { text = "message" }, 150)
	end
	local found, why = findPlayer(data.player)
	if not found then
		return fail(why, trim(data.player))
	end
	-- a helper never sends a gift to themselves, also when they typed their UserId (the Manager sets notToSelf)
	if data.notToSelf == true and found.id == player.UserId then
		return fail("giftSelf")
	end
	local ok, key = Live.SendGift(found.id, reward, message, player.Name)
	if not ok then
		return saveFailed(key)
	end
	logChange(player, "gift", { user_id = found.id, username = found.name, reward = reward, message = message, key = key })
	local result = done("giftSent", { plain = found.name }, { reward = reward })
	local robux = robuxNames(reward, Control.Catalog())
	if robux ~= "" then
		warnAbout(result, "warnRobuxGift", robux)
	end
	if hasLink(message) then
		warnAbout(result, "warnLink")
	end
	return result
end

function handlers.announce(player, data)
	local text = trim(data.text)
	local onScreen = tonumber(data.seconds) or 10
	if text == "" or not ANNOUNCE_SECONDS[onScreen] then
		return fail("badValue")
	end
	if length(text) > 200 then
		return fail("longText", { text = "announceText" }, 200)
	end
	if hasLink(text) then
		return fail("hasLink")
	end
	local told, err = Live.Announce(text, onScreen)
	logChange(player, "announce", { text = text, seconds = onScreen })
	if not told then -- shown on this server; the others couldn't be told
		return warnAbout(done("announcedHere"), "warnNotTold", tostring(err))
	end
	return done("announced")
end

function handlers.find_player(_player, data)
	local found, why = findPlayer(data.player)
	if not found then
		return fail(why, trim(data.player))
	end
	local result = done("found", { plain = found.name }, found.id)
	result.extra = { user_id = found.id, username = found.name }
	return result
end

-- The owner of a group game: the group's owner (asked from Roblox once)
local groupOwner = nil
local function gameOwnerId()
	if game.CreatorType == Enum.CreatorType.User then
		return game.CreatorId
	end
	if groupOwner == nil then
		local ok, info = pcall(function()
			return game:GetService("GroupService"):GetGroupInfoAsync(game.CreatorId)
		end)
		if ok and type(info) == "table" and type(info.Owner) == "table" then
			groupOwner = tonumber(info.Owner.Id) or 0
		end
	end
	return groupOwner or 0
end
Control.GameOwnerId = gameOwnerId -- the Manager's access tab: the owner is never put on the list

local function isOwnerOrSelf(player, userId)
	return userId == player.UserId or userId == gameOwnerId()
end

local function banProblem(err)
	local text = string.lower(tostring(err))
	if string.find(text, "banningenabled", 1, true) or string.find(text, "not enabled", 1, true) then
		return fail("banOff")
	end
	return fail("robloxBusy", tostring(err))
end

function handlers.ban(player, data)
	local userId = wholeNumber(data.user_id)
	if not userId or userId < 1 or not BAN_DURATIONS[data.duration or ""] then
		return fail("badValue")
	end
	local reason = trim(data.reason)
	if reason == "" then
		reason = "Breaking the game's rules"
	end
	if length(reason) > 200 then
		return fail("longText", { text = "reason" }, 200)
	end
	if hasLink(reason) then -- the player sees the reason: Roblox would hide it
		return fail("hasLink")
	end
	if isOwnerOrSelf(player, userId) then
		return fail("banSelf")
	end
	local name = nameOf(userId)
	if not name then
		return fail("noPlayer", tostring(userId))
	end
	local banSeconds = seconds(data.duration)
	local ok, err = pcall(function()
		Players:BanAsync({
			UserIds = { userId },
			ApplyToUniverse = true,
			Duration = banSeconds > 0 and banSeconds or -1,
			DisplayReason = banSeconds > 0 and reason or (reason .. " (permanent ban)"),
			PrivateReason = "Banned by " .. player.Name .. " (" .. player.UserId .. ") in the game's Manager",
			ExcludeAltAccounts = false,
		})
	end)
	if not ok then
		return banProblem(err)
	end
	logChange(player, "ban", { user_id = userId, username = name, seconds = banSeconds, reason = reason })
	local result = done("banned", { plain = name }, banSeconds > 0 and { duration = data.duration } or { text = "permanentBan" })
	if RunService:IsStudio() then
		warnAbout(result, "warnStudioBan")
	end
	return result
end

function handlers.unban(player, data)
	local found, why = findPlayer(data.player)
	if not found then
		return fail(why, trim(data.player))
	end
	local ok, err = pcall(function()
		Players:UnbanAsync({ UserIds = { found.id }, ApplyToUniverse = true })
	end)
	if not ok then
		return banProblem(err)
	end
	logChange(player, "unban", { user_id = found.id, username = found.name })
	local result = done("unbanned", { plain = found.name })
	if RunService:IsStudio() then
		warnAbout(result, "warnStudioBan")
	end
	return result
end

-- ---------- Start ----------

-- One change from the ⚙️ Manager (the Manager checked that the player may do this kind of change)
function Control.Do(player, kind, data)
	local handler = handlers[kind]
	if not handler or type(data) ~= "table" or not Live then
		return fail("badValue")
	end
	local ok, result = pcall(handler, player, data)
	if not ok then
		warn("[DiscordCodes] Manager: " .. tostring(kind) .. " failed: " .. tostring(result))
		return fail("changeError")
	end
	print("[DiscordCodes] Manager: " .. player.Name .. ": " .. kind .. (result.ok and " done" or " refused (" .. tostring(result.key) .. ")"))
	return result
end

function Control.Start(options)
	Core, Live, Report = options.core, options.live, options.report
	liveStore = DataStoreService:GetDataStore(Live and Live.Config.LiveDataStore or "DiscordLiveContent")
end

return Control
