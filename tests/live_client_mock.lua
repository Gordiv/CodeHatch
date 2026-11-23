-- Roblox mock for running scripts/DiscordCodes/LiveClient.client.luau under plain Lua (lupa): just enough of Instance, services and
-- tasks for the banner, the event icons with their card and the toast. Used by tests/test_kit_live_client.py (skipped when lupa is not installed).
local M = { warnings = {}, threads = {}, delayed = {} }

local realTime = os.time
M.now = realTime()
os.time = function() return M.now end
os.clock = function() return M.now end -- the script's precise clock follows the mock's time too

function warn(...)
	local parts = {}
	for i = 1, select("#", ...) do parts[#parts + 1] = tostring(select(i, ...)) end
	table.insert(M.warnings, table.concat(parts, " "))
end

local function newSignal()
	local s = { handlers = {} }
	function s:Connect(fn) table.insert(self.handlers, fn); return { Disconnect = function() end } end
	function s:Fire(...) for _, h in ipairs(self.handlers) do h(...) end end
	function s:Wait() end
	return s
end

local methods = {}
local function R(o) return rawget(getmetatable(o), "raw") end
local function new(class)
	local raw = { ClassName = class, Name = class, _kids = {}, _attrs = {}, _sig = {}, AbsolutePosition = Vector2.new(0, 0),
		AbsoluteSize = Vector2.new(0, 0) }
	local obj
	obj = setmetatable({}, {
		__index = function(_, k)
			if methods[k] then return methods[k] end
			if k == "OnClientEvent" or k == "Completed" or k == "MouseEnter" or k == "MouseLeave" or k == "Activated" then
				raw._sig[k] = raw._sig[k] or newSignal()
				return raw._sig[k]
			end
			return raw[k]
		end,
		__newindex = function(_, k, v)
			if k == "Parent" then
				local old = raw.Parent
				if old then
					local kids = R(old)._kids
					for i, c in ipairs(kids) do if c == obj then table.remove(kids, i) break end end
				end
				if v then table.insert(R(v)._kids, obj) end
			end
			raw[k] = v
		end,
		raw = raw,
	})
	return obj
end
local PARENT_CLASS = { Part = "BasePart", MeshPart = "BasePart" }
function methods:IsA(class) return self.ClassName == class or PARENT_CLASS[self.ClassName] == class or class == "Instance" end
function methods:GetDescendants()
	local out = {}
	local function walk(o) for _, c in ipairs(R(o)._kids) do table.insert(out, c); walk(c) end end
	walk(self)
	return out
end
function methods:IsDescendantOf(o) local p = self.Parent while p do if p == o then return true end p = p.Parent end return false end
function methods:BulkMoveTo(parts, cframes) M.moved = { parts = parts, cframes = cframes } end
function methods:GetChildren() local t = {} for i, c in ipairs(R(self)._kids) do t[i] = c end return t end
function methods:FindFirstChild(name, recursive)
	for _, c in ipairs(R(self)._kids) do if c.Name == name then return c end end
	if recursive then
		for _, c in ipairs(R(self)._kids) do
			local found = c:FindFirstChild(name, true)
			if found then return found end
		end
	end
	return nil
end
methods.WaitForChild = methods.FindFirstChild
function methods:Destroy() self.Parent = nil end
function methods:SetAttribute(k, v)
	R(self)._attrs[k] = v
	local signal = R(self)._sig["attr:" .. k]
	if signal then signal:Fire() end
end
function methods:GetAttribute(k) return R(self)._attrs[k] end
-- the ⚙️ Manager changes the players' language by an attribute on the remote
function methods:GetAttributeChangedSignal(k)
	local sig = R(self)._sig
	sig["attr:" .. k] = sig["attr:" .. k] or newSignal()
	return sig["attr:" .. k]
end
function methods:FireServer(...) M.hello = select(1, ...) end

Instance = { new = function(class) return new(class) end }
local C3 = {}
C3.__index = { Lerp = function(a) return a end }
Color3 = { fromRGB = function(r, g, b) return setmetatable({ r, g, b }, C3) end }
ColorSequence = { new = function(...) return { ... } end }
ColorSequenceKeypoint = { new = function(t, c) return { t, c } end }
NumberSequence = { new = function(...) return { ... } end }
NumberSequenceKeypoint = { new = function(t, v) return { t, v } end }
-- UDim2 keeps its numbers (the tests read where the event icons are) and adds up like Roblox's
local U2 = {}
U2.__add = function(a, b) return setmetatable({ xs = a.xs + b.xs, xo = a.xo + b.xo, ys = a.ys + b.ys, yo = a.yo + b.yo }, U2) end
local function udim2(xs, xo, ys, yo) return setmetatable({ xs = xs or 0, xo = xo or 0, ys = ys or 0, yo = yo or 0 }, U2) end
UDim2 = { new = udim2, fromScale = function(x, y) return udim2(x, 0, y, 0) end, fromOffset = function(x, y) return udim2(0, x, 0, y) end }
UDim = { new = function() return {} end }
local V2 = {}
V2.__sub = function(a, b) return setmetatable({ X = a.X - b.X, Y = a.Y - b.Y }, V2) end
V2.__add = function(a, b) return setmetatable({ X = a.X + b.X, Y = a.Y + b.Y }, V2) end
Vector2 = { new = function(x, y) return setmetatable({ X = x or 0, Y = y or 0 }, V2) end }
Font = { new = function(family, weight) return { family, weight } end }
-- Positions only (no rotation): enough to see that an egg moves up from its place and its pedestal stays
local V3 = {}
V3.__index = V3
Vector3 = { new = function(x, y, z) return setmetatable({ X = x or 0, Y = y or 0, Z = z or 0 }, V3) end }
V3.__sub = function(a, b) return Vector3.new(a.X - b.X, a.Y - b.Y, a.Z - b.Z) end
V3.__index = function(v, k) if k == "Magnitude" then return math.sqrt(v.X * v.X + v.Y * v.Y + v.Z * v.Z) end end
local CF = {}
CFrame = {}
function CFrame.new(x, y, z) if type(x) == "table" then x, y, z = x.X, x.Y, x.Z end return setmetatable({ Position = Vector3.new(x, y, z) }, CF) end
CFrame.Angles = function() return CFrame.new(0, 0, 0) end
CF.__index = { ToObjectSpace = function(a, b) return CFrame.new(b.Position.X - a.Position.X, b.Position.Y - a.Position.Y, b.Position.Z - a.Position.Z) end }
CF.__mul = function(a, b) return CFrame.new(a.Position.X + b.Position.X, a.Position.Y + b.Position.Y, a.Position.Z + b.Position.Z) end
function typeof(v) if getmetatable(v) == V3 then return "Vector3" end return type(v) end
TweenInfo = { new = function() return {} end }
Enum = setmetatable({}, { __index = function(_, k)
	return setmetatable({}, { __index = function(_, kk) return k .. "." .. kk end })
end })

task = {}
function task.spawn(fn, ...)
	local co = coroutine.create(fn)
	table.insert(M.threads, co)
	local ok, err = coroutine.resume(co, ...)
	if not ok then error(err) end
end
function task.wait() coroutine.yield() end
function task.delay(_, fn) table.insert(M.delayed, fn) end

-- A fresh world. language: the player's LocaleId ("en-us", "pl-pl"...), setting: the value of Settings.Language ("auto", "pl"...),
-- extra: more settings, e.g. { EventIcons = "Strength=💪", EventPosition = "TopLeft", ButtonPosition = "BottomRight" }; touch: a phone
function M.start(source, locale, setting, extra, touch)
	M.warnings, M.threads, M.delayed = {}, {}, {}
	M.playerGui = new("PlayerGui")
	M.workspace = new("Workspace")
	M.workspace.CurrentCamera = { CFrame = CFrame.new(0, 10, 20) }
	M.renderStepped = newSignal()
	M.moved = nil
	local remote = new("RemoteEvent")
	remote.Name = "DiscordLiveEvent"
	M.remote = remote
	local player = { LocaleId = locale, WaitForChild = function() return M.playerGui end }
	local services = {
		Players = { LocalPlayer = player },
		ReplicatedStorage = { GetChildren = function() return { remote } end },
		TweenService = { Create = function() return { Play = function() end, Completed = newSignal() } end },
		RunService = { RenderStepped = M.renderStepped },
		UserInputService = { TouchEnabled = touch == true, KeyboardEnabled = touch ~= true },
		Workspace = M.workspace,
	}
	game = { GetService = function(_, name) return services[name] end }
	local settings = new("Configuration")
	settings.Name = "Settings"
	local language = new("StringValue")
	language.Name, language.Value = "Language", setting or "auto"
	language.Parent = settings
	if extra then
		for name, value in pairs(extra) do
			local object = new("StringValue")
			object.Name, object.Value = name, value
			object.Parent = settings
		end
	end
	script = { FindFirstChild = function(_, name) if name == "Settings" then return settings end end }
	local fn, err = load(source, "LiveClient")
	assert(fn, err)
	fn()
end

function M.fire(payload) M.remote.OnClientEvent:Fire(payload) end

-- Time passes: the one-second loop of the script runs once per call
function M.tick(seconds)
	M.now = M.now + seconds
	for _, co in ipairs(M.threads) do
		if coroutine.status(co) == "suspended" then
			local ok, err = coroutine.resume(co)
			if not ok then error(err) end
		end
	end
end

-- The event icons, in order: the icon (a text, or the image of an ImageLabel), the multiplier and the time left
function M.badges()
	local holder = M.playerGui:FindFirstChild("DiscordLiveGui"):FindFirstChild("Events")
	local result = {}
	for _, badge in ipairs(holder:FindFirstChild("Row"):GetChildren()) do
		if badge.Name == "Event" then
			local icon = badge:FindFirstChild("Circle"):FindFirstChild("Icon")
			local factor = badge:FindFirstChild("Factor")
			result[#result + 1] = { icon = icon.ClassName == "ImageLabel" and ("image:" .. icon.Image) or icon.Text,
				factor = factor.Visible == false and "" or factor.Text, time = badge:FindFirstChild("Time").Text, object = badge }
		end
	end
	return result
end

-- Where something is (AnchorPoint and Position): the row of icons, or another part ("AnnouncementHolder", "Toast")
function M.place(name)
	local holder = M.playerGui:FindFirstChild("DiscordLiveGui"):FindFirstChild(name or "Events")
	return { ax = holder.AnchorPoint.X, ay = holder.AnchorPoint.Y, xs = holder.Position.xs, xo = holder.Position.xo, ys = holder.Position.ys,
		yo = holder.Position.yo }
end

-- The card that tells what an event does
function M.tip()
	local tip = M.playerGui:FindFirstChild("DiscordLiveGui"):FindFirstChild("Events"):FindFirstChild("EventTip")
	local lines = tip:FindFirstChild("Lines", true)
	return { visible = tip.Visible, title = tip:FindFirstChild("Title", true).Text, lines = lines.Visible == false and "" or lines.Text,
		ends = tip:FindFirstChild("Ends", true).Text, percent = tip:FindFirstChild("Percent", true).Text }
end

-- An event's start: the countdown card next to the icons and the big 3-2-1 at the top ("" when hidden)
function M.countdown()
	local gui = M.playerGui:FindFirstChild("DiscordLiveGui")
	local card, big = gui:FindFirstChild("EventCountdown"), gui:FindFirstChild("EventStart")
	return { card = card.Visible and card:FindFirstChild("Seconds", true).Text or "", title = card:FindFirstChild("Title", true).Text,
		line = card:FindFirstChild("Line", true).Text, note = card:FindFirstChild("Note", true).Text,
		big = big.Visible and big:FindFirstChild("Number", true).Text or "", text = big.Visible and big:FindFirstChild("Text", true).Text or "" }
end

-- Runs what the script left for later (task.delay)
function M.runDelayed()
	local delayed = M.delayed
	M.delayed = {}
	for _, fn in ipairs(delayed) do fn() end
end

-- The toast at the bottom: its title, colored line and note ("" when hidden)
function M.toast()
	local toast = M.playerGui:FindFirstChild("DiscordLiveGui"):FindFirstChild("Toast")
	local texts = toast:FindFirstChild("Texts")
	local function shown(name) local t = texts:FindFirstChild(name) return t.Visible == false and "" or t.Text end
	return { visible = toast.Visible, title = shown("Title"), line = shown("Line"), note = shown("Note") }
end

-- An egg stand like the Live module builds it: egg part at y=5, pedestal part below, DiscordFloat = the egg's middle
function M.addStand(float)
	local folder = M.workspace:FindFirstChild("DiscordEggStands") or new("Folder")
	folder.Name = "DiscordEggStands"
	folder.Parent = M.workspace
	local model = new("Model")
	model.Name = "DiscordEgg_1"
	if float then model:SetAttribute("DiscordFloat", Vector3.new(0, 5, 0)) end
	local egg = new("Part")
	egg.Name, egg.CFrame = "Egg", CFrame.new(0, 5, 0)
	egg.Parent = model
	local pedestal = new("Model")
	pedestal.Name = "DiscordPedestal"
	pedestal.Parent = model
	local base = new("Part")
	base.Name, base.CFrame = "Base", CFrame.new(0, 1, 0)
	base.Parent = pedestal
	model.Parent = folder
	return model, egg, base
end

return M
