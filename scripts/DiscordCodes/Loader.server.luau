--!nonstrict
--[[
	DiscordCodes  (Script, ServerScriptService)

	Starts the code system and the live content from Discord: creates the remotes, gives players their windows and
	starts the modules. Inside this script there are: the ModuleScripts "Core" (codes and rewards), "Report" (tells the
	bot the file version and what the game has) and "Live" (events, eggs, gifts, announcements),
	the LocalScripts "DiscordCodesClient" and "DiscordLiveClient", the ⚙️ Manager for the game's owner ("Manager",
	"Control" which makes its changes in the game by itself, and the ScreenGui "DiscordManager", given only to the
	owner) and the "Settings" folder (the default settings;
	change yours in the ModuleScript ServerScriptService.DiscordSettings, which an update never touches).
	The DiscordCodes.rbxmx file inserts all of it automatically.

	After a bot update that changes this file, /setup-roblox on Discord says so: move this script to ServerStorage (a
	safe backup, scripts there do not run), insert the new DiscordCodes.rbxmx from the bot's "scripts" folder the same
	way as the first time, test with Play, then publish the game. Keep your own things OUTSIDE this script (your own
	scripts, the window template DiscordCodesGui in StarterGui) and an update never touches them.
	The game also tells the bot what it has (value names in player data, egg spots and models, multipliers used by your
	code), so /setup-roblox can offer the right names.
]]

-- Version of this file. Every game server reports it to the bot (/setup-roblox shows whether the game has the newest file).
-- Set by tools/build_roblox_kit.py, do not change it.
local KIT_VERSION = 83

local Players = game:GetService("Players")
local ServerScriptService = game:GetService("ServerScriptService")
local StarterGui = game:GetService("StarterGui")
local StarterPlayer = game:GetService("StarterPlayer")

local Core = require(script:WaitForChild("Core"))
local Report = require(script:WaitForChild("Report"))
local Live = require(script:WaitForChild("Live"))
local Control = require(script:WaitForChild("Control"))
local Manager = require(script:WaitForChild("Manager"))
local settings = script:FindFirstChild("Settings")
local templates = { script:WaitForChild("DiscordCodesClient"), script:WaitForChild("DiscordLiveClient") }

-- The owner's settings live in the ModuleScript ServerScriptService.DiscordSettings (DiscordSettings.rbxmx), outside
-- this script, so an update of this file never resets them. They are copied into the Settings folder here, before the
-- players' windows get a copy of it; everything else reads the folder.
local VALUE_TYPES = { BoolValue = "boolean", StringValue = "string", IntValue = "number" }
-- Places on the screen: a name, optionally moved by pixels ("BottomRight", "Left 0,-80")
local PLACE_SETTINGS = { ButtonPosition = true, ManagerPosition = true, EventPosition = true, AnnouncementPosition = true,
	NotificationPosition = true }
local PLACES = { left = true, right = true, top = true, bottom = true, center = true, topleft = true, topright = true,
	bottomleft = true, bottomright = true }
local function isPlace(text)
	local name, x, y = string.match(text, "^%s*(%a+)%s*([%+%-]?%d*)%s*,?%s*([%+%-]?%d*)%s*$")
	return name ~= nil and PLACES[string.lower(name)] == true and math.abs(tonumber(x) or 0) <= 2000
		and math.abs(tonumber(y) or 0) <= 2000
end
local function applyOwnSettings()
	local module = ServerScriptService:FindFirstChild("DiscordSettings")
	if not module or not settings then
		return
	end
	if not module:IsA("ModuleScript") then
		warn("[DiscordCodes] ServerScriptService.DiscordSettings must be a ModuleScript: insert DiscordSettings.rbxmx again.")
		return
	end
	local ok, values = pcall(require, module)
	if not ok or type(values) ~= "table" then
		warn("[DiscordCodes] DiscordSettings could not be read (" .. tostring(values) .. "): the default settings are used.")
		return
	end
	local used = {}
	for name, value in pairs(values) do
		local target = settings:FindFirstChild(tostring(name))
		local wanted = target and VALUE_TYPES[target.ClassName]
		if not wanted then
			warn("[DiscordCodes] DiscordSettings: there is no setting named " .. tostring(name) .. " (check the spelling).")
		elseif type(value) ~= wanted or (wanted == "number" and value ~= math.floor(value)) then
			warn("[DiscordCodes] DiscordSettings: " .. tostring(name) .. " must be " .. (wanted == "number" and "a whole number"
				or wanted == "boolean" and "true or false" or "text in quotes") .. ", the default is used.")
		elseif PLACE_SETTINGS[name] and not isPlace(value) then
			warn("[DiscordCodes] DiscordSettings: " .. tostring(name) .. " must be a place like \"Left\", \"BottomRight\" or "
				.. "\"Left 0,-80\" (Left, Right, Top, Bottom, Center, TopLeft, TopRight, BottomLeft, BottomRight), the default is used.")
		elseif name == "EventEffects" and value ~= "full" and value ~= "light" and value ~= "off" then
			warn("[DiscordCodes] DiscordSettings: EventEffects must be \"full\", \"light\" or \"off\", the default is used.")
		else
			target.Value = value
			table.insert(used, tostring(name))
		end
	end
	table.sort(used)
	print("[DiscordCodes] Your settings from DiscordSettings: " .. (#used > 0 and table.concat(used, ", ") or "none"))
end
applyOwnSettings()

local remote = Core.FindRemote("DiscordCodesRedeem", "RemoteFunction")
remote.OnServerInvoke = function(player, codeText)
	return Core.RedeemCode(player, codeText)
end

local function makeClient(template)
	local client = template:Clone()
	if settings then
		settings:Clone().Parent = client
	end
	client.Disabled = false
	return client
end

-- The template window (if the game has it) must not be recreated after every respawn: the client wires it once
local windowTemplate = StarterGui:FindFirstChild("DiscordCodesGui")
if windowTemplate and windowTemplate:IsA("ScreenGui") then
	windowTemplate.ResetOnSpawn = false
end

-- New players get the windows from StarterPlayerScripts
local starterScripts = StarterPlayer:WaitForChild("StarterPlayerScripts")
for _, template in ipairs(templates) do
	if not starterScripts:FindFirstChild(template.Name) then
		makeClient(template).Parent = starterScripts
	end
end

-- Players who joined before this script started (e.g. in Studio) get the windows right away
for _, player in ipairs(Players:GetPlayers()) do
	local playerGui = player:FindFirstChildOfClass("PlayerGui")
	if playerGui then
		for _, template in ipairs(templates) do
			if not playerGui:FindFirstChild(template.Name) then
				makeClient(template).Parent = playerGui
			end
		end
	end
end

print("[DiscordCodes] File version " .. KIT_VERSION)

-- Hints for the most common mistakes after installing or updating (nothing here changes how the codes work)
local copies = 0
for _, sibling in ipairs(script.Parent:GetChildren()) do
	if sibling:IsA("Script") and sibling.Name == script.Name then
		copies = copies + 1
	end
end
if copies > 1 then
	warn(
		"[DiscordCodes] Found "
			.. copies
			.. " DiscordCodes scripts next to each other. Keep only the new one and move the old one to ServerStorage, "
			.. "otherwise the codes run twice."
	)
end
if script.Parent ~= ServerScriptService then
	warn("[DiscordCodes] This script is in " .. script:GetFullName() .. ". Drag it into ServerScriptService.")
end
print(
	"[DiscordCodes] Code window: "
		.. (windowTemplate and "your template (StarterGui.DiscordCodesGui)" or "built-in (no DiscordCodesGui in StarterGui)")
)
Core.Start()
Live.Start()
Report.Start({ version = KIT_VERSION, live = Live })
Control.Start({ core = Core, live = Live, report = Report })
Manager.Start({
	core = Core,
	live = Live,
	control = Control,
	version = KIT_VERSION,
	settings = settings,
	template = script:FindFirstChild("DiscordManager"),
})
