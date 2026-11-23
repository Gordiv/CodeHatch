-- Minimal Roblox API mock for running Core.luau, Live.luau and Report.luau (the server scripts of the kit) under plain Lua.
-- Used by tests/test_kit_server_scripts.py; returns the mock table M (stores, fired remotes, warnings, services).
-- Copied from the project scratch tests; keep it small: only what the kit scripts touch.
local M = {}
-- Roblox adds table.find (plain Lua has none): the first index of a value in a list, nil when absent
if not table.find then
	function table.find(list, value, init)
		for i = init or 1, #list do if list[i] == value then return i end end
		return nil
	end
end
M.fired = {}       -- RemoteEvent payloads: {target = player or "all", payload = table}
M.warnings = {}
M.delayed = {}
M.subscriptions = {}
M.now = os.time()

function warn(...)
	local parts = {}
	for i = 1, select("#", ...) do parts[#parts + 1] = tostring(select(i, ...)) end
	table.insert(M.warnings, table.concat(parts, " "))
end
print = function() end

math.clamp = function(x, a, b) if x < a then return a elseif x > b then return b end return x end
local realTime = os.time
os.time = function(t) if t then return realTime(t) end return M.now end

-- task: spawn runs in a coroutine (loops stop at their first wait), delay is queued for M.flush()
task = {}
function task.spawn(fn, ...)
	local co = coroutine.create(fn)
	local ok, err = coroutine.resume(co, ...)
	if not ok then error(err) end
end
function task.wait() coroutine.yield() end
function task.delay(_, fn, ...)
	table.insert(M.delayed, { fn = fn, args = { ... }, n = select("#", ...) })
end
function M.flush()
	local guard = 0
	while #M.delayed > 0 and guard < 1000 do
		guard = guard + 1
		local item = table.remove(M.delayed, 1)
		task.spawn(item.fn, table.unpack(item.args, 1, item.n))
	end
end

-- Signals
local function newSignal()
	local s = { handlers = {} }
	function s:Connect(fn) table.insert(self.handlers, fn); return { Disconnect = function() end } end
	function s:Fire(...) for _, h in ipairs(self.handlers) do h(...) end end
	return s
end
M.newSignal = newSignal

-- Value types
Vector3 = {}
local V3 = {}
V3.__index = V3
V3.__add = function(a, b) return Vector3.new(a.X + b.X, a.Y + b.Y, a.Z + b.Z) end
function Vector3.new(x, y, z) return setmetatable({ X = x or 0, Y = y or 0, Z = z or 0 }, V3) end
CFrame = {}
local CF = {}
CF.__index = CF
CF.__mul = function(a, b) return CFrame.new(a.Position.X + b.Position.X, a.Position.Y + b.Position.Y, a.Position.Z + b.Position.Z) end
CF.__add = function(a, v) return CFrame.new(a.Position.X + v.X, a.Position.Y + v.Y, a.Position.Z + v.Z) end
-- no turn: the axes point the usual way (a test turns a part by setting its own vectors)
function CFrame.new(x, y, z)
	return setmetatable({ Position = Vector3.new(x, y, z), RightVector = Vector3.new(1, 0, 0), UpVector = Vector3.new(0, 1, 0),
		LookVector = Vector3.new(0, 0, -1) }, CF)
end
Color3 = { fromRGB = function(r, g, b) return { r, g, b } end, fromHSV = function(h, s, v) return { h, s, v } end }
UDim2 = { new = function() return {} end, fromScale = function(x, y) return { X = x, Y = y } end, fromOffset = function() return {} end }
UDim = { new = function() return {} end }
CFrame.Angles = function() return CFrame.new(0, 0, 0) end
Vector2 = { new = function(x, y) return { X = x, Y = y } end }
Font = { new = function(family, weight) return { Family = family, Weight = weight } end }
ColorSequence = { new = function(...) return { ... } end }
NumberSequence = { new = function(...) return { ... } end }
NumberRange = { new = function(...) return { ... } end }
Enum = setmetatable({}, { __index = function(_, k)
	return setmetatable({}, { __index = function(_, kk) return k .. "." .. kk end })
end })
Random = { new = function() return { NextNumber = function() return math.random() end,
	NextInteger = function(_, a, b) return math.random(a, b) end } end }
-- the time with milliseconds (Core.Now): M.now plus M.millis
DateTime = { now = function() return { UnixTimestampMillis = M.now * 1000 + (M.millis or 0) } end }

-- Instances
local CLASS_PARENTS = { Part = "BasePart", MeshPart = "BasePart", IntValue = "ValueBase", NumberValue = "ValueBase",
	BoolValue = "ValueBase", BillboardGui = "LayerCollector", TextLabel = "GuiObject" }
local methods = {}
local function new(class, props)
	local raw = { ClassName = class, Name = class, _children = {}, _attrs = {}, _signals = {} }
	local obj
	obj = setmetatable({}, {
		__index = function(_, k)
			if methods[k] then return methods[k] end
			if k == "Event" or k == "Triggered" or k == "OnServerEvent" or k == "OnClientEvent" or k == "Changed" then
				raw._signals[k] = raw._signals[k] or newSignal()
				return raw._signals[k]
			end
			return raw[k]
		end,
		__newindex = function(_, k, v)
			if k == "Parent" then
				local old = raw.Parent
				if old then
					local kids = rawget(getmetatable(old), "raw")._children
					for i, c in ipairs(kids) do if c == obj then table.remove(kids, i) break end end
				end
				if v then table.insert(rawget(getmetatable(v), "raw")._children, obj) end
			end
			raw[k] = v
		end,
		raw = raw,
	})
	for k, v in pairs(props or {}) do obj[k] = v end
	return obj
end
M.new = new
local function R(o) return rawget(getmetatable(o), "raw") end
function methods:IsA(class) return self.ClassName == class or CLASS_PARENTS[self.ClassName] == class or class == "Instance" end
function methods:GetChildren() local t = {} for i, c in ipairs(R(self)._children) do t[i] = c end return t end
function methods:GetDescendants()
	local out = {}
	local function walk(o) for _, c in ipairs(R(o)._children) do table.insert(out, c); walk(c) end end
	walk(self)
	return out
end
function methods:FindFirstChild(name) for _, c in ipairs(R(self)._children) do if c.Name == name then return c end end return nil end
methods.WaitForChild = methods.FindFirstChild
function methods:FindFirstChildOfClass(class) for _, c in ipairs(R(self)._children) do if c.ClassName == class then return c end end return nil end
function methods:FindFirstChildWhichIsA(class, recursive)
	for _, c in ipairs(recursive and self:GetDescendants() or self:GetChildren()) do if c:IsA(class) then return c end end
	return nil
end
function methods:Destroy() self.Parent = nil end
function methods:Clone()
	local copy = new(self.ClassName)
	for k, v in pairs(R(self)) do if k ~= "_children" and k ~= "_attrs" and k ~= "_signals" and k ~= "Parent" then copy[k] = v end end
	for _, c in ipairs(R(self)._children) do c:Clone().Parent = copy end
	return copy
end
function methods:SetAttribute(k, v) R(self)._attrs[k] = v end
function methods:GetAttribute(k) return R(self)._attrs[k] end
function methods:GetAttributes() local t = {} for k, v in pairs(R(self)._attrs) do t[k] = v end return t end
function methods:IsDescendantOf(o) local p = self.Parent while p do if p == o then return true end p = p.Parent end return false end
function methods:GetFullName() local n = self.Name local p = self.Parent while p do n = p.Name .. "." .. n p = p.Parent end return n end
function methods:PivotTo(cf) R(self)._pivot = cf end
function methods:GetPivot() return R(self)._pivot or CFrame.new(0, 0, 0) end
function methods:GetBoundingBox() return self:GetPivot(), Vector3.new(4, 5.2, 4) end
function methods:Fire(...) self.Event:Fire(...) end
function methods:FireClient(player, payload) table.insert(M.fired, { target = player, payload = payload }) end
function methods:FireAllClients(payload) table.insert(M.fired, { target = "all", payload = payload }) end
Instance = { new = function(class) return new(class) end }

-- Services
-- Roblox keeps a GetAsync read in the server's cache for 4 s; with M.readCache = true the mock does the same, and a
-- DataStoreGetOptions with UseCache = false skips it (as on Roblox). M.reads counts the reads per store/key.
M.readCache = false
M.cached = {}
M.reads = {}
local function deepCopy(value)
	if type(value) ~= "table" then return value end
	local copy = {}
	for k, v in pairs(value) do copy[k] = deepCopy(v) end
	return copy
end
M.deepCopy = deepCopy
local function newStore(name)
	local store = { name = name, data = {} }
	function store:GetAsync(key, options)
		local id = self.name .. "/" .. tostring(key)
		M.reads[id] = (M.reads[id] or 0) + 1
		if M.readCache and not (options and options.UseCache == false) then
			local hit = M.cached[id]
			if hit and M.now - hit.at < 4 then return hit.value end
			M.cached[id] = { value = self.data[key], at = M.now }
		end
		return self.data[key]
	end
	function store:SetAsync(key, value) self.data[key] = value end
	function store:RemoveAsync(key) self.data[key] = nil end
	-- like Roblox, the function gets a copy: what it changes and doesn't return is not saved
	function store:UpdateAsync(key, fn)
		if M.updateError then error(M.updateError, 0) end
		local result = fn(deepCopy(self.data[key]))
		if result ~= nil then self.data[key] = result end
		return result
	end
	function store:ListKeysAsync(prefix)
		local keys = {}
		for k in pairs(self.data) do if string.sub(k, 1, #prefix) == prefix then table.insert(keys, { KeyName = k }) end end
		table.sort(keys, function(a, b) return a.KeyName < b.KeyName end)
		return { GetCurrentPage = function() return keys end }
	end
	return store
end
M.stores = {}
local services = {}
services.DataStoreService = { GetDataStore = function(_, name) M.stores[name] = M.stores[name] or newStore(name); return M.stores[name] end }
-- M.published: what a server told the others ({ topic, data }); M.publishError: a failing PublishAsync
M.published = {}
services.MessagingService = {
	SubscribeAsync = function(_, topic, cb) M.subscriptions[topic] = cb end,
	PublishAsync = function(_, topic, data)
		if M.publishError then error(M.publishError, 0) end
		table.insert(M.published, { topic = topic, data = data })
	end,
}
-- M.policy[userId] = what Roblox says about a player (default: may buy paid random items); M.policyError = a failing call
M.policy = {}
M.policyCalls = 0
services.PolicyService = { GetPolicyInfoForPlayerAsync = function(_, player)
	M.policyCalls = M.policyCalls + 1
	if M.policyError then error(M.policyError, 0) end
	return M.policy[player.UserId] or { ArePaidRandomItemsRestricted = false }
end }
M.players = {}
-- Roblox accounts (M.accounts[userId] = name; every player who joined has one) and bans (M.bans, M.unbans; M.banError
-- = a failing BanAsync / UnbanAsync)
M.accounts = {}
M.bans = {}
M.unbans = {}
services.Players = {
	PlayerAdded = newSignal(), PlayerRemoving = newSignal(),
	GetPlayers = function() local t = {} for i, p in ipairs(M.players) do t[i] = p end return t end,
	GetPlayerByUserId = function(_, id) for _, p in ipairs(M.players) do if p.UserId == id then return p end end return nil end,
	GetNameFromUserIdAsync = function(_, id)
		if not M.accounts[id] then error("HTTP 400 (Bad Request)", 0) end
		return M.accounts[id]
	end,
	GetUserIdFromNameAsync = function(_, name)
		for id, account in pairs(M.accounts) do
			if string.lower(account) == string.lower(name) then return id end
		end
		error("HTTP 400 (Bad Request)", 0)
	end,
	BanAsync = function(_, config)
		if M.banError then error(M.banError, 0) end
		table.insert(M.bans, config)
	end,
	UnbanAsync = function(_, config)
		if M.banError then error(M.banError, 0) end
		table.insert(M.unbans, config)
	end,
}
local guids = 0
services.HttpService = {
	JSONEncode = function(_, value) return M.encode(value) end,
	JSONDecode = function(_, text) return M.decode(text) end,
	GenerateGUID = function() guids = guids + 1; return "guid-" .. guids end,
}
services.ReplicatedStorage = new("ReplicatedStorage")
services.Workspace = new("Workspace")
M.tagged = {}
services.CollectionService = {
	GetTagged = function(_, tag) return M.tagged[tag] or {} end,
	GetInstanceAddedSignal = function() return newSignal() end,
	GetInstanceRemovedSignal = function() return newSignal() end,
}
M.blocked = {}
M.blockedWords = {} -- a text with one of these words is hidden whole, like Roblox does
M.pauseOn = {} -- text -> true: filtering it waits (like Roblox's real filter) until a test resumes M.paused
services.TextService = {
	FilterStringAsync = function(_, text)
		if M.pauseOn[text] then
			M.pauseOn[text] = nil
			M.paused = coroutine.running()
			coroutine.yield()
		end
		return { GetNonChatStringForBroadcastAsync = function()
			if M.blocked[text] then return string.rep("#", #text) end
			for _, word in ipairs(M.blockedWords) do
				if string.find(text, word, 1, true) then return string.rep("#", #text) end
			end
			return text
		end }
	end,
}
services.StarterPlayer = new("StarterPlayer")
services.ServerScriptService = new("ServerScriptService")
services.ServerStorage = new("ServerStorage")
M.studio = false
services.RunService = { IsStudio = function() return M.studio end }
services.LogService = { MessageOut = newSignal(), GetLogHistory = function() return {} end }
game = { CreatorType = "CreatorType.User", CreatorId = 1, JobId = "job", PlaceId = 555,
	GetService = function(_, name) return services[name] end }
M.services = services

function M.addPlayer(userId, coins, pets)
	local player = new("Player", { Name = "Player" .. userId, UserId = userId })
	local stats = new("Folder", { Name = "leaderstats" })
	stats.Parent = player
	new("IntValue", { Name = "Coins", Value = coins }).Parent = stats
	local folder = new("Folder", { Name = "Pets" })
	folder.Parent = player
	for _, pet in ipairs(pets or {}) do new("IntValue", { Name = pet, Value = 0 }).Parent = folder end
	player.Parent = new("Players")
	table.insert(M.players, player)
	M.accounts[userId] = player.Name
	return player
end

return M
