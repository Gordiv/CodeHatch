--!nonstrict
--[[
	DiscordCodes / Core  (ModuleScript)

	Core of the code system: loads the codes sent by the Discord bot, makes sure each player redeems a code only once
	and gives the rewards. The game's ⚙️ Manager saves its own codes into the same list (Core.ChangeCodes, used by the
	Control module), so codes work also when the bot is off.

	RULE: the script NEVER invents a place for a reward. It only adds rewards where your game already keeps them.
	If it can't find exactly one such place, the player sees a message and the code is NOT used up.

	AUTOMATIC REWARDS (names from the bot; letter case, spaces and underscores don't matter):
	- Currency:       an IntValue/NumberValue named like the currency (e.g. leaderstats.Coins, player.Data.Coins)
	                  or an existing numeric player attribute with that name.
	- EXP:            a value or attribute named EXP, XP or Experience.
	- Permanent item: a BoolValue (set to true) or IntValue/NumberValue (+1) named like the item or "Has<Item>",
	                  or an existing attribute with that name.
	- Timed item:     a value or numeric attribute named "<Item>_ExpiresAt" (an os.time() timestamp),
	                  extended by the reward duration.
	The player's data is searched, skipping Backpack, StarterGear, PlayerGui and PlayerScripts.
	If several places match (e.g. leaderstats.Coins and Data.Coins), the script doesn't guess: it lists them in the server log.
	If an error interrupts giving a reward, every change already made is undone.

	YOUR OWN SAVE SYSTEM (e.g. ProfileStore, data tables)
	No external script can see such data, so add ONE function in your own server script:

		local Core = require(game.ServerScriptService:WaitForChild("DiscordCodes"):WaitForChild("Core"))
		Core.OnReward = function(player, reward)
			-- reward.currency = { name = "Coins", amount = 500 }                                     (may be nil)
			-- reward.exp      = 2000                                                                 (may be nil)
			-- reward.item     = { name = "VIP Pass", is_temporary = true, duration_seconds = 86400 } (may be nil)
			-- reward.refund   = true when this gives BACK the price of an egg that couldn't hatch: add exactly
			--                   that amount, never multiply it (no 2x gamepass, no Live.GetMultiplier)
			-- 1. First check that you can give EVERYTHING. If not, return false (add nothing).
			-- 2. Then add the rewards and return true.
			return true
		end

	true      = rewards given.
	false/nil = nothing was given and the code is NOT used up (the player can try again, a gift keeps waiting). The
	automatic mode is NOT tried: with your own save system it would write into a copy (e.g. leaderstats) that is lost
	on the next join. Return false when the player's data isn't ready yet (e.g. the profile is still loading).
	An error in OnReward = the code is marked as redeemed (so an error halfway through can't be used to get the
	reward over and over) and the server log shows the error.

	ORDER OF REDEEMING: the code is saved as used by this player FIRST, then the reward is given. If the reward can't be
	given (an error in the automatic mode), the code is released again. If the server stops in the very moment between
	the two steps, the player keeps the code used without the reward (never the other way round: a reward twice).

	LIMIT: MaxCurrencyPerCode in ServerScriptService -> DiscordSettings (0 = no limit). A code or a gift from Discord with more currency than this is
	refused (the code is NOT used up) and the server log says so, so a mistake on Discord can't flood your economy.

	PLAYER DATA (privacy): the DataStore "PlayerRedeemedCodes_v1" keeps "<UserId>_<CODE>" for every redeemed code, and
	"DiscordGifts" keeps gifts waiting under "gift_<UserId>_...". When Roblox asks you to delete a player's data (a "Right to
	erasure" request), remove that player's keys from both DataStores (Creator Hub -> your game -> Data Stores).

	Event after a successful redeem: Core.CodeRedeemed:Connect(function(player, code, reward) ... end)

	PAYING WITH YOUR OWN SAVE SYSTEM (eggs from Discord take currency through Core.Spend)
	The automatic mode takes currency from the same values as above. With your own save system add:

		Core.OnSpend = function(player, currencyName, amount)
			-- return true if you took the amount, false if the player doesn't have enough (take nothing then)
			return false
		end

	With OnSpend set, set Core.OnReward too: when a pet can't be given, the price goes back through it (reward.refund),
	into your own save system and not into a copy such as leaderstats.
]]

local DataStoreService = game:GetService("DataStoreService")
local HttpService = game:GetService("HttpService")
local MessagingService = game:GetService("MessagingService")
local Players = game:GetService("Players")
local TextService = game:GetService("TextService")

local CONFIG = {
	CodesDataStore = "DiscordCodeSync", -- these three values must match the bot (/setup-roblox -> Game connection)
	CodesEntryKey = "ActiveCodes",
	MessagingTopic = "DiscordCodes",
	RedeemedDataStore = "PlayerRedeemedCodes_v1", -- remembers who already redeemed which code
	PollIntervalSeconds = 60,
	MaxCodeLength = 30, -- the redeemed code is saved as "UserId_CODE" and Roblox keys hold at most 50 characters
	CooldownSeconds = 2,
	ExpNames = { "EXP", "XP", "Experience" },
	IgnoredContainers = { Backpack = true, StarterGear = true, PlayerGui = true, PlayerScripts = true },
}

local Core = { Config = CONFIG, OnReward = nil }

local codeRedeemedEvent = Instance.new("BindableEvent")
Core.CodeRedeemed = codeRedeemedEvent.Event

local codesStore = DataStoreService:GetDataStore(CONFIG.CodesDataStore)
local redeemedStore = DataStoreService:GetDataStore(CONFIG.RedeemedDataStore)

-- Reads of what the bot wrote skip the server's DataStore cache (Roblox keeps a read for 4 s): otherwise a second
-- change made on Discord a moment after the first one reads the old copy and waits for the next poll (up to a minute)
local freshRead = nil
do
	local ok, options = pcall(function()
		local o = Instance.new("DataStoreGetOptions")
		o.UseCache = false
		return o
	end)
	if ok then
		freshRead = options
	end
end
Core.FreshRead = freshRead

local NUMBER_CLASSES = { "IntValue", "NumberValue" }
local ITEM_CLASSES = { "BoolValue", "IntValue", "NumberValue" }

local activeCodes = {}
local codeMeta = {} -- [CODE] = { origin = "game" | "discord", by = the Roblox name of who made it in the game }
local started = false
local busy = {}
local lastAttempt = {}
local redeemedCache = {}
local lastMissRefresh = -100
local warned = {}
local filterCache = {}
local filterCacheSize = 0

local function normalize(text)
	return string.lower((string.gsub(tostring(text), "[^%w]", "")))
end

-- Roblox attribute names may only contain letters, digits and underscores
local function safeName(text)
	return (string.gsub(tostring(text), "[^%w_]", ""))
end

local function warnOnce(key, message)
	if not warned[key] then
		warned[key] = true
		warn("[DiscordCodes] " .. message)
	end
end

-- Text typed on Discord (names of rewards, pets, currencies, events) is filtered like any other text shown to players.
-- Returns nil if it can't be filtered yet (e.g. no player on this server).
function Core.FilterText(text, fromUserId)
	text = tostring(text or "")
	if text == "" then
		return ""
	end
	if filterCache[text] then
		return filterCache[text]
	end
	local senders = {}
	if fromUserId then
		table.insert(senders, fromUserId)
	end
	if game.CreatorType == Enum.CreatorType.User then
		table.insert(senders, game.CreatorId)
	end
	for _, other in ipairs(Players:GetPlayers()) do
		table.insert(senders, other.UserId)
	end
	for i, userId in ipairs(senders) do
		if i > 3 then -- the filter is down or busy, not this sender: don't ask it once per player on the server
			break
		end
		local ok, result = pcall(function()
			local filtered = TextService:FilterStringAsync(text, userId, Enum.TextFilterContext.PublicChat)
			return filtered:GetNonChatStringForBroadcastAsync()
		end)
		if ok and type(result) == "string" then
			if filterCacheSize > 500 then
				filterCache, filterCacheSize = {}, 0
			end
			filterCache[text] = result
			filterCacheSize = filterCacheSize + 1
			return result
		end
	end
	return nil
end

-- The RemoteFunction / RemoteEvent of this kit in ReplicatedStorage. An object with the same name but another class
-- (from another system) is left alone: ours is made next to it and the log says what to rename.
function Core.FindRemote(name, className)
	local ReplicatedStorage = game:GetService("ReplicatedStorage")
	local other = nil
	for _, child in ipairs(ReplicatedStorage:GetChildren()) do
		if child.Name == name then
			if child:IsA(className) then
				return child
			end
			other = child
		end
	end
	if other then
		warn("[DiscordCodes] ReplicatedStorage has '" .. name .. "' that is a " .. other.ClassName .. ", not a " .. className
			.. ". Rename that object (it belongs to something else); the players' windows need this name.")
	end
	local remote = Instance.new(className)
	remote.Name = name
	remote.Parent = ReplicatedStorage
	return remote
end

-- Settings -> MaxCurrencyPerCode (0 or missing = no limit)
local function currencyLimit()
	local ok, limit = pcall(function()
		local value = script.Parent:FindFirstChild("Settings"):FindFirstChild("MaxCurrencyPerCode")
		return tonumber(value.Value) or 0
	end)
	return ok and limit or 0
end

-- The limit as the bot sees it (Report sends it, so the bot warns about a code or gift above it)
function Core.CurrencyLimit()
	return currencyLimit()
end

-- A text for the server log when the reward is above the owner's limit, otherwise nil
local function overLimit(reward)
	local limit = currencyLimit()
	local currency = type(reward) == "table" and reward.currency or nil
	if limit > 0 and type(currency) == "table" and (tonumber(currency.amount) or 0) > limit then
		return "currency '" .. tostring(currency.name) .. "' amount " .. tostring(currency.amount)
			.. " is above Settings -> MaxCurrencyPerCode (" .. limit .. ")"
	end
	return nil
end

local function isOneOf(instance, classNames)
	for _, className in ipairs(classNames) do
		if instance:IsA(className) then
			return true
		end
	end
	return false
end

-- Finds EXACTLY ONE place in the player's data with one of the given names.
-- Returns the target, or nil + "missing" / "ambiguous" (+ the list of found paths).
local function findTarget(player, names, classNames, attributeTypes)
	local wanted = {}
	for _, name in ipairs(names) do
		wanted[normalize(name)] = true
	end
	local found = {}
	local function consider(instance)
		if wanted[normalize(instance.Name)] and isOneOf(instance, classNames) then
			table.insert(found, { kind = "value", instance = instance, path = instance:GetFullName() })
		end
	end
	for _, child in ipairs(player:GetChildren()) do
		if not CONFIG.IgnoredContainers[child.ClassName] and not CONFIG.IgnoredContainers[child.Name] then
			consider(child)
			for _, descendant in ipairs(child:GetDescendants()) do
				consider(descendant)
			end
		end
	end
	for attributeName, value in pairs(player:GetAttributes()) do
		if wanted[normalize(attributeName)] and attributeTypes[type(value)] then
			table.insert(found, { kind = "attribute", name = attributeName, path = "player attribute '" .. attributeName .. "'" })
		end
	end
	if #found == 1 then
		return found[1]
	end
	if #found == 0 then
		return nil, "missing"
	end
	local paths = {}
	for _, target in ipairs(found) do
		table.insert(paths, target.path)
	end
	return nil, "ambiguous", paths
end

local function readTarget(player, target)
	if target.kind == "value" then
		return target.instance.Value
	end
	return player:GetAttribute(target.name)
end

local function writeTarget(player, target, value)
	if target.kind == "value" then
		target.instance.Value = value
	else
		player:SetAttribute(target.name, value)
	end
end

-- A reward step that can be undone
local function makeStep(player, target, transform)
	local previous
	local applied = false
	return {
		apply = function()
			previous = readTarget(player, target)
			writeTarget(player, target, transform(previous))
			applied = true
		end,
		undo = function()
			if applied then
				writeTarget(player, target, previous)
			end
		end,
	}
end

local function describeProblem(label, problem, paths)
	if problem == "ambiguous" then
		return label .. " - several places match (" .. table.concat(paths, ", ") .. "), not sure which one to use"
	end
	return label .. " - not found"
end

-- Plan for giving a reward: a list of steps, or nil + a list of problems. Changes nothing yet.
local function buildPlan(player, reward)
	local steps = {}
	local problems = {}
	local function add(label, target, problem, paths, transform)
		if target then
			table.insert(steps, makeStep(player, target, transform))
		else
			table.insert(problems, describeProblem(label, problem, paths))
		end
	end

	local currency = reward.currency
	if type(currency) == "table" and (tonumber(currency.amount) or 0) > 0 then
		local amount = tonumber(currency.amount)
		local target, problem, paths = findTarget(player, { currency.name }, NUMBER_CLASSES, { number = true })
		add("currency '" .. tostring(currency.name) .. "'", target, problem, paths, function(old)
			return (tonumber(old) or 0) + amount
		end)
	end

	if (tonumber(reward.exp) or 0) > 0 then
		local amount = tonumber(reward.exp)
		local target, problem, paths = findTarget(player, CONFIG.ExpNames, NUMBER_CLASSES, { number = true })
		add("EXP (EXP, XP or Experience)", target, problem, paths, function(old)
			return (tonumber(old) or 0) + amount
		end)
	end

	local item = reward.item
	if type(item) == "table" and item.name then
		if item.is_temporary then
			local duration = tonumber(item.duration_seconds) or 0
			local target, problem, paths = findTarget(player, { item.name .. "ExpiresAt" }, NUMBER_CLASSES, { number = true })
			add(
				"timed item '" .. tostring(item.name) .. "' (value " .. safeName(item.name) .. "_ExpiresAt)",
				target,
				problem,
				paths,
				function(old)
					local now = os.time()
					local base = now
					if type(old) == "number" and old > now then
						base = old
					end
					return base + duration
				end
			)
		else
			local target, problem, paths =
				findTarget(player, { item.name, "Has" .. item.name }, ITEM_CLASSES, { number = true, boolean = true })
			add("item '" .. tostring(item.name) .. "'", target, problem, paths, function(old)
				if type(old) == "boolean" then
					return true
				end
				return (tonumber(old) or 0) + 1
			end)
		end
	end

	if #problems > 0 then
		return nil, problems
	end
	return steps, nil
end

-- Runs all steps or none: on an error it undoes whatever was already changed
local function executePlan(steps)
	local done = {}
	for _, step in ipairs(steps) do
		local ok, err = pcall(step.apply)
		if not ok then
			pcall(step.undo)
			for i = #done, 1, -1 do
				pcall(done[i].undo)
			end
			return false, err
		end
		table.insert(done, step)
	end
	return true
end

-- ---------- Used by the Live module (gifts, eggs, the game report for /setup-roblox) ----------

-- The path of a value inside the player (e.g. "leaderstats.Coins"). A part named after the player (some games keep
-- data in a folder called like the player) becomes "Player", so no player names are ever sent to the bot.
local function relativePath(player, instance)
	local parts = {}
	local current = instance
	local userId = tostring(player.UserId)
	while current and current ~= player do
		local name = current.Name
		local lower = string.lower(name)
		if name == player.Name or name == player.DisplayName or string.find(name, userId, 1, true)
			or (#player.Name >= 5 and string.find(lower, string.lower(player.Name), 1, true)) then
			name = "Player"
		end
		table.insert(parts, 1, name)
		current = current.Parent
	end
	return table.concat(parts, ".")
end

-- Names (never amounts) of the values and attributes in a player's data that rewards can use, searched the same way
-- as for rewards. The bot shows them in /setup-roblox -> "What your game has", so the owner picks exact names.
function Core.DescribePlayerData(player, limit)
	limit = limit or 150
	local values = {}
	local function consider(instance)
		if #values < 2000 and isOneOf(instance, ITEM_CLASSES) then
			table.insert(values, { path = relativePath(player, instance), class = instance.ClassName })
		end
	end
	-- leaderstats is read first: a huge folder before it (e.g. Pets) never pushes it past the 2000 above
	local children = player:GetChildren()
	for pass = 1, 2 do
		for _, child in ipairs(children) do
			local ignored = CONFIG.IgnoredContainers[child.ClassName] or CONFIG.IgnoredContainers[child.Name]
			if not ignored and (child.Name == "leaderstats") == (pass == 1) then
				consider(child)
				for _, descendant in ipairs(child:GetDescendants()) do
					consider(descendant)
				end
			end
		end
	end
	-- the most useful first, so the limit cuts deep names (e.g. a big Pets folder) and never leaderstats
	local ranks = {}
	for _, entry in ipairs(values) do
		local lower = string.lower(entry.path)
		local _, depth = string.gsub(entry.path, "%.", "")
		ranks[entry] = { string.sub(lower, 1, 12) == "leaderstats." and 0 or 1, depth, lower }
	end
	table.sort(values, function(a, b)
		local aRank, bRank = ranks[a], ranks[b]
		if aRank[1] ~= bRank[1] then
			return aRank[1] < bRank[1]
		end
		if aRank[2] ~= bRank[2] then
			return aRank[2] < bRank[2]
		end
		return aRank[3] < bRank[3]
	end)
	while #values > limit do
		table.remove(values)
	end
	local attributes = {}
	for name, value in pairs(player:GetAttributes()) do
		if type(value) == "number" or type(value) == "boolean" then
			table.insert(attributes, { name = name, type = type(value) })
		end
	end
	table.sort(attributes, function(a, b)
		return a.name < b.name
	end)
	return values, attributes
end

-- Gives a reward right away, with the same rules as codes: Core.OnReward first, then the automatic mode.
-- refund: true when it gives back what the player paid (an egg's price): Settings -> MaxCurrencyPerCode limits codes
-- and gifts, never the player's own money.
-- Returns true, or false + "unsupported" / "error" / "hook_error" + details.
function Core.GiveReward(player, reward, refund)
	if type(reward) ~= "table" then
		return false, "error", "no reward"
	end
	local tooMuch = not refund and overLimit(reward)
	if tooMuch then
		return false, "unsupported", tooMuch
	end
	if refund then
		reward.refund = true -- your OnReward gives exactly this back (no multipliers): see the top of this file
	end
	if Core.OnReward then
		local hookOk, handled = pcall(Core.OnReward, player, reward)
		if not hookOk then
			return false, "hook_error", tostring(handled)
		end
		if handled == true then
			return true
		end
		-- your own save system decides: the automatic mode would write into a copy that is lost on the next join
		return false, "unsupported", "Core.OnReward returned false (nothing was given)"
	end
	local plan, problems = buildPlan(player, reward)
	if not plan then
		return false, "unsupported", table.concat(problems, "; ")
	end
	local applied, applyError = executePlan(plan)
	if not applied then
		return false, "error", tostring(applyError)
	end
	return true
end

-- Whether a reward can be given (always true when Core.OnReward is set, because then your code decides)
function Core.CanGive(player, reward)
	local tooMuch = overLimit(reward)
	if tooMuch then
		return false, tooMuch
	end
	if Core.OnReward then
		return true
	end
	local plan, problems = buildPlan(player, reward)
	if plan then
		return true
	end
	return false, table.concat(problems, "; ")
end

-- Takes currency from the player: Core.OnSpend if you set it, otherwise the automatic mode.
-- Returns true, or false + "poor" (not enough) / "unsupported" (currency not found) / "error".
function Core.Spend(player, currencyName, amount)
	amount = tonumber(amount) or 0
	if amount <= 0 then
		return true
	end
	if Core.OnSpend then
		local hookOk, paid = pcall(Core.OnSpend, player, currencyName, amount)
		if not hookOk then
			warn("[DiscordCodes] Error in Core.OnSpend: " .. tostring(paid))
			return false, "error"
		end
		if paid == true then
			return true
		end
		return false, "poor"
	end
	local target, problem, paths = findTarget(player, { currencyName }, NUMBER_CLASSES, { number = true })
	if not target then
		warnOnce(
			"spend|" .. tostring(currencyName) .. "|" .. tostring(problem),
			describeProblem("currency '" .. tostring(currencyName) .. "'", problem, paths)
				.. ". Use the same currency name as in the game or add Core.OnSpend (see the top of the Core file)."
		)
		return false, "unsupported"
	end
	local balance = tonumber(readTarget(player, target)) or 0
	if balance < amount then
		return false, "poor"
	end
	local ok, err = pcall(writeTarget, player, target, balance - amount)
	if not ok then
		warn("[DiscordCodes] Could not take currency: " .. tostring(err))
		return false, "error"
	end
	return true
end

-- A DataStore error of Studio without "Enable Studio Access to API Services" (Roblox writes "studio" in lower case
-- in some of these errors, e.g. "Cannot write to DataStore from studio if API access is disabled")
function Core.IsStudioError(err)
	return string.find(string.lower(tostring(err)), "studio", 1, true) ~= nil
end

-- Reads what the bot saved (refresh = Core.Refresh, Live.RefreshEvents or Live.RefreshEggs), one read of an entry at
-- a time: a read that started before a change and ended after a newer read would put the older data back. A
-- notification during a read asks for one more read after it. `at` = when the bot saved the change: if the data read
-- is older (or the read failed), it is read again 5 s later, at most 3 times, instead of waiting for the next poll.
local refreshes = {}

function Core.RefreshUntilFresh(refresh, at)
	local state = refreshes[refresh]
	if not state then
		state = { attempts = 0 }
		refreshes[refresh] = state
	end
	at = tonumber(at)
	if at and at > (state.at or 0) then
		state.at = at
		state.attempts = 0
	end
	if state.running then
		state.again = true
		return
	end
	state.running = true
	state.again = false
	local called, ok, updatedAt = pcall(refresh)
	state.running = false
	if not called then
		warn("[DiscordCodes] Error while reading the data from the bot: " .. tostring(ok))
		ok = false
	end
	if state.again then
		Core.RefreshUntilFresh(refresh)
	elseif state.at and (not ok or (tonumber(updatedAt) or 0) < state.at) and state.attempts < 3 then
		state.attempts = state.attempts + 1
		task.delay(5, Core.RefreshUntilFresh, refresh)
	end
end

-- Returns ok and the time the bot saved the codes (updated_at)
function Core.Refresh()
	local ok, result = pcall(function()
		return codesStore:GetAsync(CONFIG.CodesEntryKey, freshRead)
	end)
	if not ok then
		local text = tostring(result)
		if Core.IsStudioError(text) then
			warnOnce(
				"studio",
				"DataStore is not available in Studio. Turn on: File -> Experience Settings -> Security -> Enable Studio Access to API Services, then Save."
			)
		else
			warn("[DiscordCodes] Could not load the codes: " .. text)
		end
		return false
	end
	if type(result) == "table" and type(result.codes) == "table" then
		activeCodes = result.codes
		codeMeta = type(result.meta) == "table" and result.meta or {}
	else
		activeCodes = {}
		codeMeta = {}
	end
	return true, type(result) == "table" and tonumber(result.updated_at) or nil
end

function Core.GetActiveCodes()
	return activeCodes
end

-- Who made each code: { [CODE] = { origin = "game" or "discord", by = name } } (codes from older bots have none)
function Core.GetCodeMeta()
	return codeMeta
end

-- ---------- Changes made by the game itself (the ⚙️ Manager, see the Control module) ----------

-- This server's own mark in its notifications: a server never reads again what it just saved itself
local serverMark = HttpService:GenerateGUID(false)

-- Seconds since 1970 with milliseconds (two saves in one second still differ)
function Core.Now()
	local ok, now = pcall(function()
		return DateTime.now().UnixTimestampMillis / 1000
	end)
	return ok and now or os.time()
end

-- The time to save as updated_at: now, and never older than the save before it (the bot's clock may be ahead)
function Core.SaveTime(previous)
	local value = math.max(Core.Now(), (tonumber(previous) or 0) + 0.001)
	return math.floor(value * 1000 + 0.5) / 1000
end

-- Tells every game server (this one too, on older files) that something changed. Returns ok, error.
function Core.Publish(topic, payload)
	payload.from = serverMark
	local ok, err = pcall(function()
		MessagingService:PublishAsync(topic, HttpService:JSONEncode(payload))
	end)
	if not ok then
		warn("[DiscordCodes] Could not tell the other servers (they read it within " .. CONFIG.PollIntervalSeconds
			.. " s by themselves): " .. tostring(err))
	end
	return ok, err
end

-- A notification this server sent itself
function Core.IsOwnMessage(data)
	return type(data) == "table" and data.from == serverMark
end

-- Changes the codes saved in the game: change(data) gets the entry (data.codes, data.meta) inside one UpdateAsync
-- (two servers saving at once never overwrite each other; the function may run more than once) and returns true to
-- save it. Ended codes are left out. Returns ok and the saved entry (nil when change() saved nothing), or false and
-- the error. Every server reads the new codes at once; this one uses them right away.
function Core.ChangeCodes(change)
	local saved = nil
	local ok, err = pcall(function()
		codesStore:UpdateAsync(CONFIG.CodesEntryKey, function(old)
			saved = nil
			local data = type(old) == "table" and old or {}
			data.codes = type(data.codes) == "table" and data.codes or {}
			data.meta = type(data.meta) == "table" and data.meta or {}
			local now = os.time()
			for code, reward in pairs(data.codes) do
				local ends = type(reward) == "table" and tonumber(reward.expires_at) or 0
				if type(reward) ~= "table" or (ends > 0 and ends <= now) then
					data.codes[code] = nil
				end
			end
			for code in pairs(data.meta) do
				if data.codes[code] == nil then
					data.meta[code] = nil
				end
			end
			if not change(data) then
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
		activeCodes = saved.codes
		codeMeta = saved.meta
		Core.Publish(CONFIG.MessagingTopic, { type = "refresh", at = saved.updated_at })
	end
	return true, saved
end

-- For testing (the ⚙️ Manager): forget that this player redeemed the code, so they can redeem it again.
-- Returns true, or false + the error.
function Core.ForgetRedeemed(player, code)
	code = string.upper((string.gsub(tostring(code), "%s+", "")))
	local ok, err = pcall(function()
		redeemedStore:RemoveAsync(tostring(player.UserId) .. "_" .. code)
	end)
	if ok and redeemedCache[player] then
		redeemedCache[player][code] = nil
	end
	return ok, ok and nil or tostring(err)
end

-- For the ⚙️ Manager: what redeeming this code would do now for this player, without using it up or giving anything.
-- Returns the message key a real attempt would get (ok, invalid, expired, already, unsupported, unknown), the
-- reason in words for "unsupported" (may name things written on Discord: filter it before showing) and the reward.
function Core.TestCode(player, input)
	if type(input) ~= "string" then
		return "invalid"
	end
	local code = string.upper((string.gsub(input, "%s+", "")))
	if #code == 0 or #code > CONFIG.MaxCodeLength then
		return "invalid"
	end
	local reward = activeCodes[code]
	if reward == nil and os.clock() - lastMissRefresh > 10 then
		-- added on Discord a moment ago: refreshed like for a real attempt (at most every 10 s per server)
		lastMissRefresh = os.clock()
		Core.Refresh()
		reward = activeCodes[code]
	end
	if type(reward) ~= "table" then
		return "invalid"
	end
	if (tonumber(reward.expires_at) or 0) > 0 and os.time() >= tonumber(reward.expires_at) then
		return "expired", nil, reward
	end
	local tooMuch = overLimit(reward)
	if tooMuch then
		return "unsupported", tooMuch, reward
	end
	if not Core.OnReward then
		local plan, problems = buildPlan(player, reward)
		if not plan then
			return "unsupported", table.concat(problems, "; "), reward
		end
	end
	if redeemedCache[player] and redeemedCache[player][code] then
		return "already", nil, reward
	end
	local ok, value = pcall(function()
		return redeemedStore:GetAsync(tostring(player.UserId) .. "_" .. code)
	end)
	if not ok then
		return "unknown", nil, reward
	end
	return value ~= nil and "already" or "ok", nil, reward
end

-- Copy of the reward sent to the player's window to show exactly what they got (names filtered like chat text)
function Core.RewardSummary(reward, player)
	local summary = {}
	local userId = player and player.UserId or nil
	if type(reward.currency) == "table" and (tonumber(reward.currency.amount) or 0) > 0 then
		summary.currency = {
			name = Core.FilterText(reward.currency.name, userId) or "?",
			amount = tonumber(reward.currency.amount),
		}
	end
	if (tonumber(reward.exp) or 0) > 0 then
		summary.exp = tonumber(reward.exp)
	end
	if type(reward.item) == "table" and reward.item.name then
		summary.item = {
			name = Core.FilterText(reward.item.name, userId) or "?",
			is_temporary = reward.item.is_temporary == true,
			duration_seconds = tonumber(reward.item.duration_seconds) or 0,
		}
	end
	return summary
end
local rewardSummary = Core.RewardSummary

local function redeemInner(player, input)
	if type(input) ~= "string" then
		return false, "invalid"
	end
	local code = string.upper((string.gsub(input, "%s+", "")))
	if #code == 0 or #code > CONFIG.MaxCodeLength then
		return false, "invalid"
	end

	local now = os.clock()
	if lastAttempt[player] and now - lastAttempt[player] < CONFIG.CooldownSeconds then
		return false, "cooldown"
	end
	lastAttempt[player] = now

	local cache = redeemedCache[player]
	if cache and cache[code] then
		return false, "already"
	end

	local reward = activeCodes[code]
	if reward == nil and now - lastMissRefresh > 10 then
		-- the code may have been added a moment ago: refresh the list (at most every 10 s per server)
		lastMissRefresh = now
		Core.Refresh()
		reward = activeCodes[code]
	end
	if type(reward) ~= "table" then
		return false, "invalid"
	end
	if (tonumber(reward.expires_at) or 0) > 0 and os.time() >= tonumber(reward.expires_at) then
		return false, "expired"
	end
	local tooMuch = overLimit(reward)
	if tooMuch then
		warnOnce(code .. "|limit", "Code '" .. code .. "' can't be redeemed: " .. tooMuch .. ". The code was NOT used up.")
		return false, "unsupported"
	end

	-- Without a custom OnReward we check BEFORE using up the code that the whole reward can be given
	local plan, problems
	if not Core.OnReward then
		plan, problems = buildPlan(player, reward)
		if not plan then
			warnOnce(
				code .. "|" .. table.concat(problems, "|"),
				"Code '"
					.. code
					.. "' can't be redeemed: "
					.. table.concat(problems, "; ")
					.. ". The code was NOT used up. Use the same names in the bot (/setup-roblox -> What your game has) as in the game "
					.. "or add Core.OnReward (see the top of the Core file)."
			)
			return false, "unsupported"
		end
	end

	local key = tostring(player.UserId) .. "_" .. code
	local alreadyRedeemed = false
	local ok, err = pcall(function()
		redeemedStore:UpdateAsync(key, function(old)
			alreadyRedeemed = old ~= nil
			if old ~= nil then
				return nil
			end
			return os.time()
		end)
	end)
	if not ok then
		warn("[DiscordCodes] Could not save the redeemed code: " .. tostring(err))
		return false, "error"
	end

	local function remember()
		redeemedCache[player] = redeemedCache[player] or {}
		redeemedCache[player][code] = true
	end
	local function release()
		pcall(function()
			redeemedStore:RemoveAsync(key)
		end)
	end

	if alreadyRedeemed then
		remember()
		return false, "already"
	end
	if not player.Parent then
		release()
		return false, "left"
	end

	if Core.OnReward then
		local hookOk, handled = pcall(Core.OnReward, player, reward)
		if not hookOk then
			remember()
			warn(
				"[DiscordCodes] Error in Core.OnReward for code '"
					.. code
					.. "': "
					.. tostring(handled)
					.. ". The code was marked as redeemed so an error halfway through can't be used to get the reward again. Fix OnReward."
			)
			return false, "error"
		end
		if handled == true then
			remember()
			codeRedeemedEvent:Fire(player, code, reward)
			return true, "ok", rewardSummary(reward, player)
		end
		-- false/nil: your save system can't give it now (e.g. the profile isn't loaded): the code is released
		release()
		warnOnce(
			code .. "|hook",
			"Code '" .. code .. "': Core.OnReward returned false, so nothing was given. The code was NOT used up."
		)
		return false, "unsupported"
	end

	local applied, applyError = executePlan(plan)
	if not applied then
		release()
		warn("[DiscordCodes] Error while giving the reward (changes undone, code not used up): " .. tostring(applyError))
		return false, "error"
	end
	remember()
	codeRedeemedEvent:Fire(player, code, reward)
	return true, "ok", rewardSummary(reward, player)
end

-- (player, text) -> (boolean, message key, rewards on success)
-- Keys: ok, invalid, expired, already, busy, cooldown, unsupported, error, left
function Core.RedeemCode(player, input)
	if busy[player] then
		return false, "busy"
	end
	busy[player] = true
	local ok, success, messageKey, rewards = pcall(redeemInner, player, input)
	busy[player] = nil
	if not ok then
		warn("[DiscordCodes] Unexpected error: " .. tostring(success))
		return false, "error"
	end
	return success, messageKey, rewards
end

function Core.Start()
	if started then
		return
	end
	started = true

	Players.PlayerRemoving:Connect(function(player)
		busy[player] = nil
		lastAttempt[player] = nil
		redeemedCache[player] = nil
	end)

	Core.RefreshUntilFresh(Core.Refresh)

	task.spawn(function()
		while true do
			task.wait(CONFIG.PollIntervalSeconds)
			Core.RefreshUntilFresh(Core.Refresh)
		end
	end)

	task.spawn(function()
		-- Roblox may refuse for a moment (e.g. right after the server starts): tried again later, the codes still
		-- refresh every PollIntervalSeconds in the meantime
		for attempt = 1, 8 do
			local ok, err = pcall(function()
				MessagingService:SubscribeAsync(CONFIG.MessagingTopic, function(message)
					local decoded, data = pcall(function()
						return HttpService:JSONDecode(message.Data)
					end)
					if decoded and Core.IsOwnMessage(data) then
						return -- saved here a moment ago: this server already has it
					end
					local at = decoded and type(data) == "table" and data.at or nil
					-- random delay so that all servers don't load the data in the same second
					task.delay(math.random() * 3, Core.RefreshUntilFresh, Core.Refresh, at)
				end)
			end)
			if ok then
				return
			end
			if attempt == 1 then
				warn("[DiscordCodes] Could not subscribe to notifications, trying again (codes still refresh every "
					.. CONFIG.PollIntervalSeconds .. " s): " .. tostring(err))
			elseif attempt == 8 then
				warn("[DiscordCodes] Gave up subscribing to notifications on this server: new codes show here within "
					.. CONFIG.PollIntervalSeconds .. " s instead of at once: " .. tostring(err))
				return
			end
			task.wait(math.min(15 * 2 ^ attempt, 600))
		end
	end)

	local count = 0
	for _ in pairs(activeCodes) do
		count = count + 1
	end
	print("[DiscordCodes] Ready. Active codes: " .. count .. (freshRead and "" or " (fresh reads unavailable: changes may take up to 5 s longer)"))
end

return Core
