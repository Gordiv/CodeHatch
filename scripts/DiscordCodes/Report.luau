--!nonstrict
--[[
	DiscordCodes / Report  (ModuleScript)

	Tells the Discord bot two things, so /setup-roblox can help the game's owner:
	- which version of the DiscordCodes file runs in each place (published game and Studio separately),
	- what the game has: names of the values in player data (e.g. leaderstats.Coins, Pets.Dragon), egg spots and
	  models, the multipliers your code asks Live.GetMultiplier for and which of your own functions are set
	  (Core.OnReward, Core.OnSpend, Live.OnHatch, Live.OnAnnouncement) and the limit Settings -> MaxCurrencyPerCode,
	- the game catalog, if the game has the ModuleScript "DiscordCatalog" (DiscordCatalog.rbxmx from the bot's "scripts"
	  folder): the exact names of currencies, items, pets, eggs and multipliers, so the bot suggests them in its commands.
	Only names are sent, never amounts or player names (a folder called like a player is sent as "Player"). At most one
	small DataStore write per server start, and later only when something changed (or every 12 hours).
	Every server sees only its own players, so the names from all servers are joined in the saved report (up to
	ScanMaxValues); a report older than 12 hours starts again from scratch, so removed names disappear. Egg spots, egg
	models and the functions are the same on every server, so the newest report replaces them at once.
]]

local CollectionService = game:GetService("CollectionService")
local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local ServerScriptService = game:GetService("ServerScriptService")
local ServerStorage = game:GetService("ServerStorage")
local Workspace = game:GetService("Workspace")

local Core = require(script.Parent:WaitForChild("Core"))

local CONFIG = {
	DataStore = "DiscordLiveContent", -- these names must match the bot
	VersionKey = "KitVersions",
	ScanKey = "GameScan",
	RefreshSeconds = 43200,
	MaxPlaces = 20,
	ScanDelaySeconds = 15, -- wait after joining so your game can load the player's data first
	ScanIntervalSeconds = 30,
	ScanMaxValues = 150,
	ScanMaxList = 100, -- spots, models, multipliers, attributes, functions: at most this many of each in the report
	EggSpotTag = "DiscordEggSpot",
	EggTemplatesFolder = "DiscordEggs",
	CatalogKey = "GameCatalog",
	CatalogName = "DiscordCatalog", -- a ModuleScript in ServerScriptService (or ServerStorage / ReplicatedStorage)
	CatalogMaxNameLength = 100, -- characters; a longer name is reported, never cut (it must stay exact)
	CatalogTimeoutSeconds = 10, -- a DiscordCatalog that takes longer to load is reported as a problem
	CatalogLimits = { Currencies = 50, Items = 300, Pets = 500, Eggs = 100, Multipliers = 50, EggPets = 100, SoldForRobux = 500 },
}

local Report = { Config = CONFIG }

local store = DataStoreService:GetDataStore(CONFIG.DataStore)
local options = { version = 0, edition = "full", live = nil }
local started = false

local scanValues = {} -- path -> class, from every player on this server
local scanValueCount = 0
local scanAttributes = {} -- name -> "number" / "boolean"
local scannedPlayers = 0
local lastScanSignature = ""
local lastScanWrite = 0
local lastCatalogSignature = ""
local lastCatalogWrite = 0
local lastCatalogPrinted = ""

local function isStudioError(err)
	return Core.IsStudioError(err)
end

local function lastReport(place)
	local newest = 0
	for _, kind in ipairs({ "live", "studio" }) do
		if type(place) == "table" and type(place[kind]) == "table" then
			newest = math.max(newest, tonumber(place[kind].at) or 0)
		end
	end
	return newest
end

-- Keeps only the places that reported most recently
local function trimPlaces(places)
	local keys = {}
	for key in pairs(places) do
		table.insert(keys, key)
	end
	if #keys > CONFIG.MaxPlaces then
		table.sort(keys, function(a, b)
			return lastReport(places[a]) > lastReport(places[b])
		end)
		for i = CONFIG.MaxPlaces + 1, #keys do
			places[keys[i]] = nil
		end
	end
end

-- Writes `entry` for this place (published game or Studio) unless the same is already saved (and not too old)
-- keep(current), optional: true = the saved entry must stay (e.g. it comes from a newer version of the game)
-- merge(current, entry), optional: joins a fresh saved entry with this server's entry (servers see different players)
local function save(key, entry, same, keep, merge)
	local kind = RunService:IsStudio() and "studio" or "live"
	local placeKey = tostring(game.PlaceId)
	local now = os.time()
	return pcall(function()
		store:UpdateAsync(key, function(old)
			local data = type(old) == "table" and old or {}
			if type(data.places) ~= "table" then
				data.places = {}
			end
			local place = type(data.places[placeKey]) == "table" and data.places[placeKey] or {}
			local current = place[kind]
			if type(current) == "table" and keep and keep(current) then
				return nil
			end
			local fresh = type(current) == "table" and now - (tonumber(current.at) or 0) < CONFIG.RefreshSeconds
			local value = entry
			if merge and fresh then
				value = merge(current, entry)
			end
			if fresh and same(current, value) then
				return nil -- already known, nothing to write
			end
			local copy = {}
			for k, v in pairs(value) do
				copy[k] = v
			end
			copy.at = (merge and fresh) and (tonumber(current.at) or now) or now
			copy.saved = now -- "at" is the start of the 12-hour window of a joined report; this is the newest write
			place[kind] = copy
			data.places[placeKey] = place
			trimPlaces(data.places)
			return data
		end)
	end)
end

function Report.Setup(newOptions)
	for key, value in pairs(newOptions or {}) do
		options[key] = value
	end
end

-- ---------- File version ----------

function Report.ReportVersion(version)
	version = tonumber(version or options.version)
	if not version then
		return false
	end
	local edition = options.edition
	local ok, err = save(CONFIG.VersionKey, { version = version, edition = edition }, function(current)
		return tonumber(current.version) == version and (current.edition or "full") == edition
	end, function(current)
		-- a server still running an older file (started before the publish) never hides the newer one. Not in Studio:
		-- there only one file runs, so an older file put back into Studio is reported at once
		return not RunService:IsStudio() and tonumber(current.version) ~= nil and tonumber(current.version) > version
			and os.time() - (tonumber(current.at) or 0) < CONFIG.RefreshSeconds
	end)
	if not ok and not isStudioError(err) then
		warn("[DiscordCodes] Could not report the file version to the bot: " .. tostring(err))
	end
	return ok
end

-- ---------- What the game has ----------

local function sortedKeys(map)
	local keys = {}
	for key in pairs(map) do
		table.insert(keys, key)
	end
	table.sort(keys)
	return keys
end

local function spotName(spot)
	local name = spot:GetAttribute("Spot")
	if type(name) == "string" and name ~= "" then
		return name
	end
	return spot.Name
end

function Report.ScanPlayer(player)
	if not player.Parent then
		return
	end
	local ok, values, attributes = pcall(Core.DescribePlayerData, player, CONFIG.ScanMaxValues)
	if not ok then
		return
	end
	scannedPlayers = scannedPlayers + 1
	for _, value in ipairs(values) do
		if not scanValues[value.path] and scanValueCount < CONFIG.ScanMaxValues then
			scanValues[value.path] = value.class
			scanValueCount = scanValueCount + 1
		end
	end
	for _, attribute in ipairs(attributes) do
		scanAttributes[attribute.name] = attribute.type
	end
end

function Report.ScanGame()
	local values, attributes, spots, templates, multipliers, hooks = {}, {}, {}, {}, {}, {}
	for _, path in ipairs(sortedKeys(scanValues)) do
		table.insert(values, path .. ":" .. scanValues[path])
	end
	for _, name in ipairs(sortedKeys(scanAttributes)) do
		table.insert(attributes, name .. ":" .. scanAttributes[name])
	end
	for _, spot in ipairs(CollectionService:GetTagged(CONFIG.EggSpotTag)) do
		if spot:IsDescendantOf(Workspace) and (spot:IsA("BasePart") or spot:IsA("Model")) then
			table.insert(spots, spotName(spot))
		end
	end
	table.sort(spots)
	local folder = ReplicatedStorage:FindFirstChild(CONFIG.EggTemplatesFolder)
	if folder then
		for _, child in ipairs(folder:GetChildren()) do
			if child:IsA("Model") or child:IsA("BasePart") then
				table.insert(templates, child.Name)
			end
		end
		table.sort(templates)
	end
	local live = options.live
	if live and live.GetUsedMultipliers then
		multipliers = live.GetUsedMultipliers()
	end
	local functions = { { "OnReward", Core.OnReward }, { "OnSpend", Core.OnSpend } }
	if live then
		table.insert(functions, { "OnHatch", live.OnHatch })
		table.insert(functions, { "OnAnnouncement", live.OnAnnouncement })
	end
	for _, hook in ipairs(functions) do
		if hook[2] then
			table.insert(hooks, hook[1])
		end
	end
	return {
		values = values,
		attributes = attributes,
		spots = spots,
		spotCount = #spots, -- copies of one part keep its name: the list of names alone would count them once
		templates = templates,
		multipliers = multipliers,
		hooks = hooks,
		maxCurrency = Core.CurrencyLimit(), -- 0 = no limit
		players = scannedPlayers,
	}
end

local SCAN_LISTS = { "values", "attributes", "spots", "templates", "multipliers", "hooks" }

local function scanSignature(scan)
	local parts = {}
	for _, key in ipairs(SCAN_LISTS) do
		-- the same names in another order are the same report (no new write just for the order)
		local list = table.clone and table.clone(type(scan[key]) == "table" and scan[key] or {}) or { table.unpack(scan[key] or {}) }
		table.sort(list)
		table.insert(parts, key .. "=" .. table.concat(list, ","))
	end
	table.insert(parts, "maxCurrency=" .. tostring(tonumber(scan.maxCurrency) or 0))
	table.insert(parts, "spotCount=" .. tostring(tonumber(scan.spotCount) or 0))
	return table.concat(parts, "|")
end

-- For the names in player data: leaderstats first, then short paths, then the rest (letter case ignored), so a cut at
-- the limit drops deep names (pets, items by id) and never the currencies
local function usefulFirst(x, y)
	local function rank(value)
		local lower = string.lower(value)
		local _, depth = string.gsub(value, "%.", "")
		return string.sub(lower, 1, 12) == "leaderstats." and 0 or 1, depth, lower
	end
	local xLeader, xDepth, xName = rank(x)
	local yLeader, yDepth, yName = rank(y)
	if xLeader ~= yLeader then
		return xLeader < yLeader
	end
	if xDepth ~= yDepth then
		return xDepth < yDepth
	end
	return xName < yName
end

-- Sorted list of the entries of both lists (no duplicates), at most `limit`
local function union(a, b, limit, order)
	local seen, result = {}, {}
	for _, list in ipairs({ a, b }) do
		for _, value in ipairs(type(list) == "table" and list or {}) do
			if type(value) == "string" and not seen[value] then
				seen[value] = true
				table.insert(result, value)
			end
		end
	end
	table.sort(result, order)
	while #result > limit do
		table.remove(result)
	end
	return result
end

-- Lists that are the same on every server of one place version (egg spots, egg models, the game's own functions; the
-- currency limit too): the newest scan replaces them, so a removed spot, model or function disappears at once instead of after 12 hours.
-- A server still running an older version of the place (started before a publish) never replaces the newer lists.
local GAME_WIDE = { spots = true, templates = true, hooks = true }

-- The saved report of the other servers joined with this server's report
local function mergeScan(current, scan)
	local currentVersion, scanVersion = tonumber(current.placeVersion) or 0, tonumber(scan.placeVersion) or 0
	local merged = { players = math.max(tonumber(current.players) or 0, tonumber(scan.players) or 0),
		placeVersion = math.max(currentVersion, scanVersion),
		maxCurrency = tonumber(scanVersion >= currentVersion and scan.maxCurrency or current.maxCurrency) or 0,
		spotCount = tonumber(scanVersion >= currentVersion and scan.spotCount or current.spotCount) or 0 }
	for _, key in ipairs(SCAN_LISTS) do
		if GAME_WIDE[key] then
			merged[key] = union(scanVersion >= currentVersion and scan[key] or current[key], nil, CONFIG.ScanMaxList)
		else
			merged[key] = union(current[key], scan[key], key == "values" and CONFIG.ScanMaxValues or CONFIG.ScanMaxList,
				key == "values" and usefulFirst or nil)
		end
	end
	merged.sig = scanSignature(merged)
	return merged
end

-- Saves the report when something changed (or every 12 hours)
function Report.ReportGame()
	local scan = Report.ScanGame()
	local signature = scanSignature(scan)
	local now = os.time()
	if signature == lastScanSignature and now - lastScanWrite < CONFIG.RefreshSeconds then
		return true
	end
	scan.sig = signature
	scan.placeVersion = game.PlaceVersion
	local ok, err = save(CONFIG.ScanKey, scan, function(current, value)
		return current.sig == value.sig
	end, nil, mergeScan)
	if ok then
		lastScanSignature = signature
		lastScanWrite = now
	elseif not isStudioError(err) then
		warn("[DiscordCodes] Could not send the game report to the bot: " .. tostring(err))
	end
	return ok
end

-- ---------- The game catalog (the optional ModuleScript "DiscordCatalog") ----------
-- The owner lists there what the game has (currencies, items, pets with rarity, eggs, multipliers). Only the names go
-- to the bot, so its commands can suggest them and refuse names the game doesn't have.
-- The module is read once per server (it doesn't change while the server runs), in its own thread with a time limit,
-- so a module that waits forever can't stop the other reports.

-- Deterministic text of a table (sorted keys), used to notice changes
local function stableText(value)
	if type(value) ~= "table" then
		return tostring(value)
	end
	local keys = {}
	for key in pairs(value) do
		table.insert(keys, key)
	end
	table.sort(keys, function(a, b)
		return tostring(a) < tostring(b)
	end)
	local parts = {}
	for _, key in ipairs(keys) do
		table.insert(parts, tostring(key) .. "=" .. stableText(value[key]))
	end
	return "{" .. table.concat(parts, ",") .. "}"
end

-- A number that can be saved (not NaN, not math.huge), or nil
local function finiteNumber(value)
	local number = tonumber(value)
	if number == nil or number ~= number or number == math.huge or number == -math.huge then
		return nil
	end
	return number
end

-- The name as text, or nil; a second result "long" when the name is too long (it is never cut, so it stays exact)
local function cleanName(value)
	if type(value) ~= "string" and type(value) ~= "number" then
		return nil
	end
	local text = string.match(tostring(value), "^%s*(.-)%s*$")
	if text == nil or text == "" then
		return nil
	end
	local length = utf8.len(text)
	if length == nil or length > CONFIG.CatalogMaxNameLength then
		return nil, "long"
	end
	return text
end

-- A problem in the catalog: a code for the bot (translated there) and an English text for the Output window
local function addProblem(catalog, code, what, detail, text)
	if #catalog.problems < 20 then
		table.insert(catalog.problems, { code = code, what = what, detail = detail })
		warn("[DiscordCodes] DiscordCatalog: " .. text)
	end
end

local function tooLong(catalog, what, value)
	local text = tostring(value)
	local cut = utf8.len(text) and utf8.offset(text, 21) -- whole characters only, so the text stays valid UTF-8
	local preview = cut and string.sub(text, 1, cut - 1) or (utf8.len(text) and text or "?")
	addProblem(catalog, "name_too_long", what, preview, what .. ": the name '" .. preview .. "...' is longer than "
		.. CONFIG.CatalogMaxNameLength .. " characters")
end

-- Entries of a list ({ "Coins", "Gems" }) or of a dictionary ({ Coins = true }), as { key, value, position }
local function entriesOf(value)
	local entries = {}
	if #value > 0 then
		for index, entry in ipairs(value) do
			table.insert(entries, { index, entry, index })
		end
	else
		for key, entry in pairs(value) do
			table.insert(entries, { key, entry, tostring(key) })
		end
		table.sort(entries, function(a, b)
			return tostring(a[1]) < tostring(b[1])
		end)
	end
	return entries
end

-- The name of an entry: the value in a list ({ "Coins" }), the key in a dictionary ({ Coins = true })
local function entryName(entry, field)
	if type(entry[1]) == "number" then
		if type(entry[2]) == "table" then
			return entry[2][field] or entry[2][string.lower(field)]
		end
		return entry[2]
	end
	return entry[1]
end

local function nameList(catalog, value, what)
	local result, seen = {}, {}
	if value == nil then
		return result
	end
	if type(value) ~= "table" then
		addProblem(catalog, "not_list", what, nil, what .. " must be a list, e.g. { 'Coins', 'Gems' }")
		return result
	end
	local limit = CONFIG.CatalogLimits[what]
	for _, entry in ipairs(entriesOf(value)) do
		local raw = entryName(entry, "Name")
		local name, problem = cleanName(raw)
		if problem == "long" then
			tooLong(catalog, what, raw)
		elseif not name then
			addProblem(catalog, "bad_name", what, tostring(entry[3]), what .. " #" .. tostring(entry[3]) .. " is not a name")
		elseif not seen[string.lower(name)] then
			if #result >= limit then
				addProblem(catalog, "too_many", what, tostring(limit), what .. ": only the first " .. limit .. " are sent")
				break
			end
			seen[string.lower(name)] = true
			table.insert(result, name)
		end
	end
	return result
end

local function petList(catalog, value)
	local result, seen = {}, {}
	if value == nil then
		return result
	end
	if type(value) ~= "table" then
		addProblem(catalog, "not_list", "Pets", nil, "Pets must be a list, e.g. { { Name = 'Dog', Rarity = 'Common' } }")
		return result
	end
	local limit = CONFIG.CatalogLimits.Pets
	for _, entry in ipairs(entriesOf(value)) do
		-- { Name = "Dog", Rarity = "Common" } or "Dog" in a list; Dog = "Common" or Dog = { Rarity = "Common" } by name
		local rarity = nil
		if type(entry[2]) == "table" then
			rarity = entry[2].Rarity or entry[2].rarity
		elseif type(entry[1]) ~= "number" then
			rarity = entry[2]
		end
		local raw = entryName(entry, "Name")
		local name, problem = cleanName(raw)
		if problem == "long" then
			tooLong(catalog, "Pets", raw)
		elseif not name then
			addProblem(catalog, "pet_no_name", "Pets", tostring(entry[3]), "Pets #" .. tostring(entry[3]) .. " has no Name")
		elseif not seen[string.lower(name)] then
			if #result >= limit then
				addProblem(catalog, "too_many", "Pets", tostring(limit), "Pets: only the first " .. limit .. " are sent")
				break
			end
			seen[string.lower(name)] = true
			table.insert(result, { name = name, rarity = (cleanName(rarity)) })
		end
	end
	return result
end

local function eggPets(catalog, value, egg)
	local pets = {}
	if type(value) ~= "table" then
		return pets
	end
	for _, pet in ipairs(entriesOf(value)) do
		-- Dog = 60 (a chance), "Dog" in a list (no chance), or { Name = "Dog", Chance = 60 } (Weight works too)
		local chance = nil
		if type(pet[2]) == "table" then
			chance = pet[2].Chance or pet[2].chance or pet[2].Weight or pet[2].weight
		elseif type(pet[1]) ~= "number" then
			chance = pet[2]
		end
		local raw = entryName(pet, "Name")
		local name, problem = cleanName(raw)
		if problem == "long" then
			tooLong(catalog, "Eggs", raw)
		elseif name and #pets < CONFIG.CatalogLimits.EggPets then
			table.insert(pets, { name = name, chance = finiteNumber(chance) })
		end
	end
	return pets
end

local function eggList(catalog, value)
	local result, seen = {}, {}
	if value == nil then
		return result
	end
	if type(value) ~= "table" then
		addProblem(catalog, "not_list", "Eggs", nil, "Eggs must be a list, e.g. { { Name = 'Basic Egg', Pets = { Dog = 60 } } }")
		return result
	end
	for _, entry in ipairs(entriesOf(value)) do
		local data = type(entry[2]) == "table" and entry[2] or {}
		local raw = entryName(entry, "Name")
		local name, problem = cleanName(raw)
		if problem == "long" then
			tooLong(catalog, "Eggs", raw)
		elseif not name then
			addProblem(catalog, "egg_no_name", "Eggs", tostring(entry[3]), "Eggs #" .. tostring(entry[3]) .. " has no Name")
		elseif not seen[string.lower(name)] and #result < CONFIG.CatalogLimits.Eggs then
			seen[string.lower(name)] = true
			local pets = eggPets(catalog, data.Pets or data.pets, name)
			if #pets == 0 then
				addProblem(catalog, "egg_no_pets", "Eggs", name, "the egg " .. name .. " has no Pets")
			end
			table.insert(result, {
				name = name,
				currency = (cleanName(data.Currency or data.currency)),
				price = finiteNumber(data.Price or data.price),
				pets = pets,
			})
		end
	end
	return result
end

-- The example names of the DiscordCatalog template from older bot versions: such a catalog was never filled in
local TEMPLATE = { currencies = { "coins", "gems" }, items = { "speed coil", "vip pass" } }

local function lowerSorted(list, field)
	local result = {}
	for _, entry in ipairs(list) do
		table.insert(result, string.lower(tostring(field and entry[field] or entry)))
	end
	table.sort(result)
	return table.concat(result, ",")
end

local function isTemplate(catalog)
	return lowerSorted(catalog.currencies) == table.concat(TEMPLATE.currencies, ",")
		and lowerSorted(catalog.items) == table.concat(TEMPLATE.items, ",")
		and (#catalog.pets == 0 or lowerSorted(catalog.pets, "name") == "cat,dog,dragon")
end

function Report.FindCatalog()
	for _, service in ipairs({ ServerScriptService, ServerStorage, ReplicatedStorage }) do
		local module = service:FindFirstChild(CONFIG.CatalogName)
		if module and module:IsA("ModuleScript") then
			return module
		end
	end
	return nil
end

-- The catalog as plain lists of names, or nil when the game has no DiscordCatalog
function Report.ReadCatalog()
	local module = Report.FindCatalog()
	if not module then
		return nil
	end
	local catalog = { currencies = {}, items = {}, pets = {}, eggs = {}, multipliers = {}, robux = {}, problems = {} }
	local ok, data = pcall(require, module)
	if not ok then
		addProblem(catalog, "error", nil, string.sub(tostring(data), 1, 200), "it has an error: " .. tostring(data))
		return catalog
	end
	if type(data) ~= "table" then
		addProblem(catalog, "no_return", nil, nil, "the last line must be: return Catalog")
		return catalog
	end
	catalog.currencies = nameList(catalog, data.Currencies, "Currencies")
	catalog.items = nameList(catalog, data.Items, "Items")
	catalog.pets = petList(catalog, data.Pets)
	catalog.eggs = eggList(catalog, data.Eggs)
	catalog.multipliers = nameList(catalog, data.Multipliers, "Multipliers")
	-- what players can buy with Robux: the bot warns when a code or a gift gives it (Roblox rules on promo codes)
	catalog.robux = nameList(catalog, data.SoldForRobux, "SoldForRobux")
	if isTemplate(catalog) then
		addProblem(catalog, "template", nil, nil, "it still has only the example names of the template (Coins, Gems, VIP Pass, "
			.. "Speed Coil...). Write your game's real names into it; until then the bot does not use it.")
	end
	return catalog
end

-- Reads the catalog once per server, in its own thread. A module that waits forever (for example WaitForChild for
-- something that isn't there) is reported as a problem after CatalogTimeoutSeconds instead of stopping the reports.
local catalogLoad = { state = "new", value = nil }

local function loadCatalog()
	if catalogLoad.state == "done" then
		return true, catalogLoad.value
	end
	if catalogLoad.state == "loading" then
		return false
	end
	catalogLoad.state = "loading"
	local finished = false
	task.spawn(function()
		local value = Report.ReadCatalog()
		if not finished then
			finished = true
			catalogLoad.value = value
		end
	end)
	local waited = 0
	while not finished and waited < CONFIG.CatalogTimeoutSeconds do
		task.wait(0.5)
		waited = waited + 0.5
	end
	if not finished then
		finished = true
		local catalog = { currencies = {}, items = {}, pets = {}, eggs = {}, multipliers = {}, robux = {}, problems = {} }
		addProblem(catalog, "timeout", nil, tostring(CONFIG.CatalogTimeoutSeconds), "it did not finish loading in "
			.. CONFIG.CatalogTimeoutSeconds .. " s (is it waiting with WaitForChild for something that isn't there?)")
		catalogLoad.value = catalog
	end
	catalogLoad.state = "done"
	return true, catalogLoad.value
end

-- Reads DiscordCatalog again on the next report (for example after editing it while the server runs)
function Report.ForgetCatalog()
	catalogLoad.state, catalogLoad.value = "new", nil
	lastCatalogSignature = ""
	lastCatalogPrinted = ""
end

local function describeCatalog(catalog)
	if not catalog then
		return "none (optional: DiscordCatalog lets the bot know the exact names)"
	end
	local parts = { #catalog.currencies .. " currencies", #catalog.items .. " items" }
	if options.live then
		table.insert(parts, #catalog.pets .. " pets")
		table.insert(parts, #catalog.eggs .. " eggs")
		table.insert(parts, #catalog.multipliers .. " multipliers")
	end
	if catalog.robux and #catalog.robux > 0 then
		table.insert(parts, #catalog.robux .. " sold for Robux")
	end
	return table.concat(parts, ", ")
end

-- Sends the catalog when it changed (or every 12 hours). A game without one says so, so the bot can tell the owner.
-- A server running an older published version never overwrites the catalog of a newer one.
function Report.ReportCatalog()
	local loaded, catalog = loadCatalog()
	if not loaded then
		return false
	end
	local placeVersion = tonumber(game.PlaceVersion) or 0
	local entry = { placeVersion = placeVersion } -- a fresh table: saving adds "at" to it
	for key, value in pairs(catalog or { missing = true }) do
		entry[key] = value
	end
	local signature = stableText(entry)
	local now = os.time()
	if signature == lastCatalogSignature and now - lastCatalogWrite < CONFIG.RefreshSeconds then
		return true
	end
	local ok, err = save(CONFIG.CatalogKey, entry, function(current)
		local copy = {}
		for key, value in pairs(current) do
			if key ~= "at" and key ~= "saved" then -- the times of saving are not part of the catalog
				copy[key] = value
			end
		end
		return stableText(copy) == signature
	end, function(current)
		return (tonumber(current.placeVersion) or 0) > placeVersion
	end)
	if ok then
		lastCatalogSignature = signature
		lastCatalogWrite = now
		if signature ~= lastCatalogPrinted then
			lastCatalogPrinted = signature
			print("[DiscordCodes] Game catalog: " .. describeCatalog(catalog))
		end
	elseif isStudioError(err) then
		if signature ~= lastCatalogPrinted then
			lastCatalogPrinted = signature
			print("[DiscordCodes] Game catalog: " .. describeCatalog(catalog)
				.. " (not sent to the bot: turn on File -> Experience Settings -> Security -> Enable Studio Access to API Services, then Save)")
		end
	else
		warn("[DiscordCodes] Could not send the game catalog to the bot: " .. tostring(err))
	end
	return ok
end

-- ---------- Start ----------

function Report.Start(newOptions)
	Report.Setup(newOptions)
	if started then
		return
	end
	started = true
	task.spawn(Report.ReportVersion, options.version)
	task.spawn(Report.ReportCatalog)
	local function onPlayer(player)
		task.delay(CONFIG.ScanDelaySeconds, Report.ScanPlayer, player)
	end
	Players.PlayerAdded:Connect(onPlayer)
	for _, player in ipairs(Players:GetPlayers()) do
		onPlayer(player)
	end
	task.spawn(function()
		while true do
			task.wait(CONFIG.ScanIntervalSeconds)
			Report.ReportGame()
			Report.ReportCatalog()
		end
	end)
end

return Report
