--!nonstrict
--[[
	DiscordCodesClient  (LocalScript)

	The "Codes" button and the window for entering a code. Two ways, you do not have to choose in advance:

	1. NOTHING TO DO: the button and the window are created from code (a purple "Codes" button at the left edge of the
	   screen). Change them in the ModuleScript ServerScriptService -> DiscordSettings (insert DiscordSettings.rbxmx once;
	   an update of DiscordCodes never touches it):
	   - ShowButton (true/false)  - whether to show the "Codes" button
	   - ButtonPosition           - Left, Right, Top, Bottom, Center, TopLeft, TopRight, BottomLeft, BottomRight, and
	                                optionally pixels to move it: "Left 0,-80" = 80 px higher
	   - Language                 - auto (from the player's settings), en, pl or es

	2. YOUR OWN LOOK (survives updates): insert the template DiscordCodesWindow.rbxmx into StarterGui (right-click
	   StarterGui -> Insert -> Import Roblox Model). It is a normal window you can restyle in Studio (colors, texts,
	   size, position, fonts, pictures). This script finds it by the name DiscordCodesGui and only connects the
	   buttons, so it keeps your design when DiscordCodes is updated. Keep the names of the parts (see findParts below).
	   Texts you leave as they are follow the player's language; texts you write yourself stay as you wrote them.

	YOUR OWN WINDOW FROM SCRATCH: set ShowButton = false and call it yourself:
		local ok, messageKey, rewards = game.ReplicatedStorage.DiscordCodesRedeem:InvokeServer(codeText)
	-- rewards (on success) = { currency = { name, amount }, exp, item = { name, is_temporary, duration_seconds } }
	Message keys: ok, invalid, expired, already, busy, cooldown, unsupported, error, left.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterGui = game:GetService("StarterGui")
local TweenService = game:GetService("TweenService")

local GUI_NAME = "DiscordCodesGui" -- the name of the window (ScreenGui), also of the template in StarterGui
local BOUND = "DiscordCodesBound" -- attribute: this window is already wired

local ACCENT_COLOR = Color3.fromRGB(179, 107, 255) -- the code box's edge while the player types
local SUCCESS_COLOR = Color3.fromRGB(110, 230, 140)
local ERROR_COLOR = Color3.fromRGB(255, 125, 150)
local NEUTRAL_COLOR = Color3.fromRGB(201, 184, 255)

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")
if not game:IsLoaded() then
	game.Loaded:Wait()
end
-- The template window from StarterGui (if the game has it) is copied into PlayerGui by Roblox itself
local templateGui = nil
if StarterGui:FindFirstChild(GUI_NAME) then
	templateGui = playerGui:WaitForChild(GUI_NAME, 20)
	if not templateGui then
		warn(
			"[DiscordCodes] StarterGui."
				.. GUI_NAME
				.. " was not copied to the player within 20 seconds (does the character spawn?), so the built-in window is used."
		)
	end
end

-- Settings: the template's own folder first, then the one inside DiscordCodes. "auto" means "not chosen".
local settingsFolders = {
	templateGui and templateGui:FindFirstChild("Settings") or false,
	script:FindFirstChild("Settings") or false,
}
local function setting(name, default)
	for _, folder in ipairs(settingsFolders) do
		local value = folder and folder:FindFirstChild(name) or nil
		if value ~= nil and value.Value ~= "auto" then
			return value.Value
		end
	end
	return default
end

local POSITIONS = {
	left = { UDim2.new(0, 12, 0.5, 0), Vector2.new(0, 0.5) },
	right = { UDim2.new(1, -12, 0.5, 0), Vector2.new(1, 0.5) },
	top = { UDim2.new(0.5, 0, 0, 12), Vector2.new(0.5, 0) },
	bottom = { UDim2.new(0.5, 0, 1, -12), Vector2.new(0.5, 1) },
	topleft = { UDim2.new(0, 12, 0, 12), Vector2.new(0, 0) },
	topright = { UDim2.new(1, -12, 0, 12), Vector2.new(1, 0) },
	bottomleft = { UDim2.new(0, 12, 1, -12), Vector2.new(0, 1) },
	bottomright = { UDim2.new(1, -12, 1, -12), Vector2.new(1, 1) },
	center = { UDim2.fromScale(0.5, 0.5), Vector2.new(0.5, 0.5) },
}

-- A place's name in lower case and the pixels to move it by: "Left" or "Left 0,-80" (80 px higher)
local function readPlace(value)
	local name, x, y = string.match(tostring(value or ""), "^%s*(%a+)%s*([%+%-]?%d*)%s*,?%s*([%+%-]?%d*)%s*$")
	local function pixels(text)
		return math.max(-2000, math.min(2000, tonumber(text) or 0))
	end
	return name and string.lower(name) or "", pixels(x), pixels(y)
end

local SHOW_BUTTON, position -- read by readSettings below

local TEXTS = {
	en = {
		button = "CODES",
		title = "REDEEM CODE",
		placeholder = "Enter code",
		redeem = "REDEEM",
		hint = "Check back for new codes!",
		ok = "Code redeemed! Rewards added.",
		got = "Code redeemed! You got:",
		separator = ",",
		days = function(n) return n == 1 and "1 day" or (n .. " days") end,
		hours = function(n) return n .. "h" end,
		minutes = function(n) return n .. " min" end,
		invalid = "Invalid or expired code.",
		expired = "This code has expired.",
		already = "You already redeemed this code.",
		busy = "Please wait...",
		cooldown = "Please wait a moment before trying again.",
		unsupported = "This code can't be redeemed in this game yet.",
		error = "Something went wrong. Try again in a moment.",
		left = "Something went wrong. Try again.",
	},
	pl = {
		button = "KODY",
		title = "ODBIERZ KOD",
		placeholder = "Wpisz kod",
		redeem = "ODBIERZ",
		hint = "Zaglądaj tu po nowe kody!",
		ok = "Kod odebrany! Nagrody dodane.",
		got = "Kod odebrany! Otrzymujesz:",
		separator = "\u{A0}", -- a space that does not break the line inside a number
		days = function(n) return n == 1 and "1 dzień" or (n .. " dni") end,
		hours = function(n) return n .. " godz." end,
		minutes = function(n) return n .. " min" end,
		invalid = "Nieprawidłowy lub wygasły kod.",
		expired = "Ten kod już wygasł.",
		already = "Odebrałeś już ten kod.",
		busy = "Poczekaj chwilę...",
		cooldown = "Poczekaj chwilę przed kolejną próbą.",
		unsupported = "Tego kodu nie można jeszcze odebrać w tej grze.",
		error = "Coś poszło nie tak. Spróbuj za chwilę.",
		left = "Coś poszło nie tak. Spróbuj ponownie.",
	},
	es = {
		button = "CÓDIGOS",
		title = "CANJEAR CÓDIGO",
		placeholder = "Escribe el código",
		redeem = "CANJEAR",
		hint = "¡Vuelve a por nuevos códigos!",
		ok = "¡Código canjeado! Recompensas añadidas.",
		got = "¡Código canjeado! Recibes:",
		separator = ".",
		days = function(n) return n == 1 and "1 día" or (n .. " días") end,
		hours = function(n) return n .. " h" end,
		minutes = function(n) return n .. " min" end,
		invalid = "Código no válido o caducado.",
		expired = "Este código ha caducado.",
		already = "Ya canjeaste este código.",
		busy = "Espera un momento...",
		cooldown = "Espera un momento antes de volver a intentarlo.",
		unsupported = "Este código aún no se puede canjear en este juego.",
		error = "Algo salió mal. Inténtalo de nuevo en un momento.",
		left = "Algo salió mal. Inténtalo de nuevo.",
	},
}

-- The ⚙️ Manager can change ShowButton, ButtonPosition and Language while the game runs: the server puts them as
-- attributes on the code remote, and they win over the Settings folders
local liveSettings = nil
local language, T
local function readSettings()
	local function current(name, default)
		local live = liveSettings and liveSettings:GetAttribute(name)
		if live ~= nil then
			return live
		end
		return setting(name, default)
	end
	SHOW_BUTTON = current("ShowButton", true) ~= false
	local place, x, y = readPlace(current("ButtonPosition", "Left"))
	local base = POSITIONS[place] or POSITIONS.left
	position = { base[1] + UDim2.fromOffset(x, y), base[2] }
	language = string.lower(tostring(current("Language", "auto")))
	if language == "auto" then
		language = string.sub(string.lower(tostring(player.LocaleId or "en")), 1, 2)
	end
	T = TEXTS[language] or TEXTS.en
end
readSettings()

local function formatNumber(value)
	local digits = tostring(math.floor(tonumber(value) or 0))
	local negative = string.sub(digits, 1, 1) == "-"
	if negative then
		digits = string.sub(digits, 2)
	end
	local grouped = ""
	while #digits > 3 do
		grouped = T.separator .. string.sub(digits, -3) .. grouped
		digits = string.sub(digits, 1, -4)
	end
	return (negative and "-" or "") .. digits .. grouped
end

local function formatDuration(seconds)
	seconds = math.floor(tonumber(seconds) or 0)
	if seconds >= 86400 and seconds % 86400 == 0 then
		return T.days(math.floor(seconds / 86400))
	elseif seconds >= 3600 and seconds % 3600 == 0 then
		return T.hours(math.floor(seconds / 3600))
	end
	return T.minutes(math.max(1, math.floor(seconds / 60 + 0.5)))
end

-- Success text with the reward list, e.g. "Code redeemed! You got: +50,000 Coins, +2,000 EXP, VIP Pass (1 day)"
local function describeRewards(rewards)
	if type(rewards) ~= "table" then
		return T.ok
	end
	local parts = {}
	if type(rewards.currency) == "table" then
		table.insert(parts, "+" .. formatNumber(rewards.currency.amount) .. " " .. tostring(rewards.currency.name))
	end
	if rewards.exp then
		table.insert(parts, "+" .. formatNumber(rewards.exp) .. " EXP")
	end
	if type(rewards.item) == "table" then
		local item = tostring(rewards.item.name)
		if rewards.item.is_temporary and (tonumber(rewards.item.duration_seconds) or 0) > 0 then
			item = item .. " (" .. formatDuration(rewards.item.duration_seconds) .. ")"
		end
		table.insert(parts, item)
	end
	if #parts == 0 then
		return T.ok
	end
	return T.got .. " " .. table.concat(parts, ", ")
end

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

local remote = findRemote("DiscordCodesRedeem", "RemoteFunction", 30)
if not remote then
	warn("[DiscordCodes] DiscordCodesRedeem was not found. Is the DiscordCodes script in ServerScriptService?")
	return
end
liveSettings = remote
readSettings()

-- ---------- Look of the built-in window: the style of the ⚙️ Manager (the template DiscordCodesWindow.rbxmx has the same look) ----------
local FONT = Enum.Font.FredokaOne -- the title (it has no ą, ę, ń...: the texts there are ours)
local BODY_FONT = Font.new("rbxasset://fonts/families/Nunito.json", Enum.FontWeight.Heavy) -- every Polish and Spanish letter
local WHITE = Color3.fromRGB(255, 255, 255)
local WINDOW = Color3.fromRGB(30, 18, 51) -- the panel
local FIELD = Color3.fromRGB(24, 14, 44) -- the code box and the result line
local FIELD_EDGE = Color3.fromRGB(70, 48, 120)
local GLOW = Color3.fromRGB(179, 107, 255) -- the panel's edge
local MUTED = Color3.fromRGB(168, 151, 214)
local SHADOW = Color3.fromRGB(14, 8, 28)
local TEXT_EDGE = Color3.fromRGB(70, 24, 120) -- a soft outline around white letters on a gradient
local LIGHT_EDGE = Color3.fromRGB(245, 214, 255)
local GRADIENTS = {
	primary = { Color3.fromRGB(214, 112, 255), Color3.fromRGB(128, 64, 240) },
	green = { Color3.fromRGB(96, 226, 128), Color3.fromRGB(30, 160, 72) },
	red = { Color3.fromRGB(255, 107, 138), Color3.fromRGB(224, 51, 90) },
}
-- Background of the result line (only when Message has a visible background, as in the built-in window)
local RESULT_BACKGROUND = {
	success = Color3.fromRGB(28, 66, 48),
	error = Color3.fromRGB(78, 28, 52),
	neutral = FIELD,
}
-- The edge of the result line: a red pill after a wrong code, a green one after a good one (the built-in window)
local RESULT_EDGE = {
	success = Color3.fromRGB(80, 210, 120),
	error = Color3.fromRGB(255, 84, 110),
}

local function rounded(instance, radius)
	local corner = Instance.new("UICorner")
	corner.CornerRadius = UDim.new(0, radius)
	corner.Parent = instance
end

local function outline(instance, color, thickness)
	local stroke = Instance.new("UIStroke")
	stroke.Color = color
	stroke.Thickness = thickness
	stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border -- the edge of the box, not the letters
	stroke.Parent = instance
end

local function frame(name, parent, color, size, position, radius)
	local part = Instance.new("Frame")
	part.Name = name
	part.BackgroundColor3 = color
	part.BorderSizePixel = 0
	part.Size = size
	part.Position = position
	part.Parent = parent
	if radius then
		rounded(part, radius)
	end
	return part
end

-- From top to bottom (a UIGradient also tints its object's own text: only objects without text get one)
local function gradient(instance, top, bottom)
	local shade = Instance.new("UIGradient")
	shade.Color = ColorSequence.new(top, bottom)
	shade.Rotation = 90
	shade.Parent = instance
end

local function label(name, parent, text, size, color, font)
	local object = Instance.new("TextLabel")
	object.Name = name
	object.BackgroundTransparency = 1
	object.FontFace = font or BODY_FONT
	object.Text = text
	object.TextSize = size
	object.TextColor3 = color
	object.Parent = parent
	return object
end

-- A button in the look of the ⚙️ Manager buttons: a gradient with a light edge and a shine on its top half. The text
-- (and an icon) are TextLabels named Label (and Icon) inside: a UIGradient would tint the button's own text.
local function gradientButton(name, parent, kind, text, size, position, anchor, textSize, icon)
	local button = Instance.new("TextButton")
	button.Name = name
	button.AutoButtonColor = false
	button.Text = ""
	button.BackgroundColor3 = WHITE
	button.BorderSizePixel = 0
	button.Size = size
	button.Position = position
	button.AnchorPoint = anchor
	button.Parent = parent
	rounded(button, 14)
	outline(button, LIGHT_EDGE, 1.5)
	gradient(button, GRADIENTS[kind][1], GRADIENTS[kind][2])
	local gloss = frame("Gloss", button, WHITE, UDim2.new(1, -12, 0.42, 0), UDim2.fromOffset(6, 4), 10)
	gloss.BackgroundTransparency = 0.8
	local left = 0
	if icon then
		local iconLabel = label("Icon", button, icon, textSize + 2, WHITE, Font.fromEnum(Enum.Font.GothamBold))
		iconLabel.Size = UDim2.new(0, 30, 1, 0)
		iconLabel.Position = UDim2.fromOffset(12, 0)
		left = 40
	end
	local caption = label("Label", button, text, textSize, WHITE)
	caption.Size = UDim2.new(1, -(left + 12), 1, 0)
	caption.Position = UDim2.fromOffset(left + 6, 0)
	caption.TextStrokeColor3 = TEXT_EDGE
	caption.TextStrokeTransparency = 0.55
	caption.TextXAlignment = icon and Enum.TextXAlignment.Left or Enum.TextXAlignment.Center
	return button
end

-- The game buttons drawn in Figma (the file "CodeHatch - przyciski gry", PNGs in tools/ui_assets): one finished
-- picture each (the body, the icon and the word), made at the size the game shows it, so nothing is cut or stretched
-- and no stripes show at any size. The word is in the picture, so CODES has one per language. In Figma units the
-- body is 150 tall and as wide as `width`, with a margin of 30 around it for the glow and the gift.
local BUTTON_MARGIN = 30
local CODES_BUTTONS = {
	en = { image = "rbxassetid://127576122383640", width = 410 },
	pl = { image = "rbxassetid://85108833852310", width = 410 },
	es = { image = "rbxassetid://100003912326639", width = 480 },
}
local function codesButtonLook()
	return CODES_BUTTONS[language] or CODES_BUTTONS.en
end

-- height: the button's height in pixels (its width follows the picture)
local function pictureButton(name, parent, look, height, position, anchor, text)
	local k = height / 150
	local button = Instance.new("TextButton")
	button.Name = name
	button.AutoButtonColor = false
	button.Text = ""
	button.BackgroundTransparency = 1
	button.Size = UDim2.fromOffset(math.floor(look.width * k + 0.5), height)
	button.Position = position
	button.AnchorPoint = anchor
	button.Parent = parent
	local picture = Instance.new("ImageLabel")
	picture.Name = "Skin"
	picture.BackgroundTransparency = 1
	picture.Image = look.image
	picture.ScaleType = Enum.ScaleType.Stretch
	picture.Position = UDim2.fromOffset(-BUTTON_MARGIN * k, -BUTTON_MARGIN * k)
	picture.Size = UDim2.new(1, 2 * BUTTON_MARGIN * k, 1, 2 * BUTTON_MARGIN * k)
	picture.Parent = button
	-- the word is drawn in the picture; this hidden Label keeps it for the template's language switch
	local caption = label("Label", button, text, 18, WHITE)
	caption.Size = UDim2.fromScale(1, 1)
	caption.TextTransparency = 1
	return button
end

-- The window is wired up through parts found by NAME (anywhere inside the ScreenGui). The ready-made template
-- (DiscordCodesWindow.rbxmx) and the built-in window below have exactly the same names, so you can restyle, move
-- or hide things in Studio, only keep the names. Needed: Window (with CodeBox, Redeem and Message inside).
-- Optional: OpenCodes (opens the window), Close, Title, Hint. A frame named <button>Edge next to a button is its
-- 3D edge: pressing the button moves it down onto the edge.
local function findParts(gui)
	local window = gui:FindFirstChild("Window", true)
	local textBox = window and window:FindFirstChild("CodeBox", true)
	local redeemButton = window and window:FindFirstChild("Redeem", true)
	local message = window and window:FindFirstChild("Message", true)
	if
		not (
			window
			and window:IsA("GuiObject")
			and textBox
			and textBox:IsA("TextBox")
			and redeemButton
			and redeemButton:IsA("GuiButton")
			and message
			and message:IsA("TextLabel")
		)
	then
		return nil
	end
	return {
		window = window,
		textBox = textBox,
		redeem = redeemButton,
		message = message,
		title = window:FindFirstChild("Title", true),
		hint = window:FindFirstChild("Hint", true),
		close = window:FindFirstChild("Close", true),
		open = gui:FindFirstChild("OpenCodes", true),
	}
end

-- The built-in window (used when there is no template in StarterGui)
local function makeDefaultGui()
	local screenGui = Instance.new("ScreenGui")
	screenGui.Name = GUI_NAME
	screenGui.ResetOnSpawn = false
	screenGui.DisplayOrder = 50
	screenGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
	screenGui:SetAttribute(BOUND, true)
	screenGui.Parent = playerGui

	-- Window is an invisible holder: a soft shadow under the panel
	local window = Instance.new("Frame")
	window.Name = "Window"
	window.Size = UDim2.fromOffset(380, 300)
	window.AnchorPoint = Vector2.new(0.5, 0.5)
	window.Position = UDim2.fromScale(0.5, 0.5)
	window.BackgroundTransparency = 1
	window.Parent = screenGui
	frame("Shadow", window, SHADOW, UDim2.fromScale(1, 1), UDim2.fromOffset(0, 6), 22).BackgroundTransparency = 0.45

	-- the panel: dark violet from top to bottom with a glowing violet edge (the ⚙️ Manager's window)
	local panel = frame("Panel", window, WHITE, UDim2.fromScale(1, 1), UDim2.fromOffset(0, 0), 22)
	gradient(panel, Color3.fromRGB(40, 24, 68), Color3.fromRGB(18, 10, 32))
	outline(panel, GLOW, 2)

	local title = label("Title", panel, T.title, 26, WHITE, Font.fromEnum(FONT))
	title.Size = UDim2.new(1, -90, 0, 64)
	title.Position = UDim2.fromOffset(22, 0)
	title.TextXAlignment = Enum.TextXAlignment.Left

	gradientButton("Close", panel, "red", "X", UDim2.fromOffset(40, 40), UDim2.new(1, -54, 0, 12), Vector2.zero, 20)

	local textBox = Instance.new("TextBox")
	textBox.Name = "CodeBox"
	textBox.Size = UDim2.new(1, -40, 0, 52)
	textBox.Position = UDim2.fromOffset(20, 86)
	textBox.BackgroundColor3 = FIELD
	textBox.BorderSizePixel = 0
	textBox.FontFace = BODY_FONT
	textBox.TextSize = 22
	textBox.TextColor3 = WHITE
	textBox.PlaceholderText = T.placeholder
	textBox.PlaceholderColor3 = MUTED
	textBox.ClearTextOnFocus = false
	textBox.Text = ""
	textBox.Parent = panel
	rounded(textBox, 14)
	outline(textBox, FIELD_EDGE, 2)

	gradientButton("Redeem", panel, "green", T.redeem, UDim2.new(1, -40, 0, 52), UDim2.fromOffset(20, 150), Vector2.zero, 24)

	local message = label("Message", panel, "", 17, NEUTRAL_COLOR)
	message.BackgroundTransparency = 0
	message.BackgroundColor3 = RESULT_BACKGROUND.neutral
	local messageEdge = Instance.new("UIStroke")
	messageEdge.Name = "Edge"
	messageEdge.Thickness = 2
	messageEdge.Color = RESULT_EDGE.error
	messageEdge.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	messageEdge.Parent = message
	message.Size = UDim2.new(1, -40, 0, 48)
	message.Position = UDim2.fromOffset(20, 216)
	message.TextWrapped = true
	rounded(message, 12)

	local hint = label("Hint", panel, T.hint, 15, MUTED)
	hint.Size = UDim2.new(1, -40, 0, 22)
	hint.Position = UDim2.fromOffset(20, 270)

	if SHOW_BUTTON then
		pictureButton("OpenCodes", screenGui, codesButtonLook(), 54, position[1], position[2], T.button)
	end
	return screenGui
end

-- ---------- Animations (they only change sizes and positions, so a restyled template keeps its look) ----------
local POP_IN = TweenInfo.new(0.25, Enum.EasingStyle.Back, Enum.EasingDirection.Out)
local POP_OUT = TweenInfo.new(0.12, Enum.EasingStyle.Quad, Enum.EasingDirection.In)
local QUICK = TweenInfo.new(0.08, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)

-- A UIScale for the animations; nil when the part already has its own UIScale (that one is left alone)
local function animationScale(instance)
	local own = instance:FindFirstChildOfClass("UIScale")
	if own then
		return own.Name == "DiscordCodesScale" and own or nil
	end
	local scale = Instance.new("UIScale")
	scale.Name = "DiscordCodesScale"
	scale.Parent = instance
	return scale
end

-- A button with an edge (<name>Edge next to it) goes down onto it when pressed; one without an edge shrinks a bit
local function pressable(button)
	local edge = button.Parent and button.Parent:FindFirstChild(button.Name .. "Edge")
	local pressed = false
	if edge and edge:IsA("GuiObject") then
		-- The edge shows and hides with its button (a hidden or deleted button leaves no edge behind)
		local function followButton()
			edge.Visible = button.Visible and button.Parent == edge.Parent
		end
		button:GetPropertyChangedSignal("Visible"):Connect(followButton)
		button.AncestryChanged:Connect(followButton)
		local up = button.Position -- taken again at each press: a button your own code moves keeps its new place
		button.MouseButton1Down:Connect(function()
			if not pressed then
				pressed = true
				up = button.Position
				TweenService:Create(button, QUICK, { Position = up + UDim2.fromOffset(0, 4) }):Play()
			end
		end)
		local function release()
			if pressed then
				pressed = false
				TweenService:Create(button, QUICK, { Position = up }):Play()
			end
		end
		button.MouseButton1Up:Connect(release)
		button.MouseLeave:Connect(release)
		return
	end
	local scale = animationScale(button)
	if not scale then
		return
	end
	local hovered = false
	button.MouseButton1Down:Connect(function()
		pressed = true
		TweenService:Create(scale, QUICK, { Scale = 0.92 }):Play()
	end)
	local function release()
		pressed = false
		TweenService:Create(scale, QUICK, { Scale = hovered and 1.05 or 1 }):Play()
	end
	button.MouseButton1Up:Connect(release)
	-- a little bigger under the mouse
	button.MouseEnter:Connect(function()
		hovered = true
		if not pressed then
			TweenService:Create(scale, QUICK, { Scale = 1.05 }):Play()
		end
	end)
	button.MouseLeave:Connect(function()
		hovered = false
		release()
	end)
end

-- An edge whose button was deleted from the template (for example OpenCodesEdge without OpenCodes) is hidden
local function hideLoneEdges(gui)
	for _, part in ipairs(gui:GetDescendants()) do
		local name = string.match(part.Name, "^(.+)Edge$")
		if name and part:IsA("GuiObject") and part.Parent and not part.Parent:FindFirstChild(name) then
			part.Visible = false
		end
	end
end

-- ---------- Wiring ----------
local submitting = false -- one request at a time, also when a window was recreated

local function wire(parts)
	local window, textBox, message = parts.window, parts.textBox, parts.message
	window.Visible = false -- in Studio you see the window while designing; in the game it opens with the button
	local windowScale = animationScale(window)
	local open = false
	local animation = 0 -- a newer open/close cancels the end of an older one
	-- A Message with a visible background gets a green/red one by the result, hidden while it is empty
	local backgroundLevel = message.BackgroundTransparency
	local coloredBackground = backgroundLevel < 1

	local function setMessage(text, kind)
		message.Text = text
		message.TextColor3 = kind == "success" and SUCCESS_COLOR or kind == "error" and ERROR_COLOR or NEUTRAL_COLOR
		if coloredBackground then
			message.BackgroundColor3 = RESULT_BACKGROUND[kind] or RESULT_BACKGROUND.neutral
			message.BackgroundTransparency = text == "" and 1 or backgroundLevel
		end
		local edge = message:FindFirstChild("Edge")
		if edge and edge:IsA("UIStroke") then -- the built-in window's red / green pill (hidden while empty or neutral)
			edge.Color = RESULT_EDGE[kind] or RESULT_EDGE.error
			edge.Enabled = text ~= "" and RESULT_EDGE[kind] ~= nil
		end
	end
	setMessage("", "neutral") -- the template shows a sample text here

	local function setWindowVisible(visible)
		open = visible
		animation += 1
		local mine = animation
		if visible then
			setMessage("", "neutral")
			window.Visible = true
			if windowScale then
				windowScale.Scale = 0.6
				TweenService:Create(windowScale, POP_IN, { Scale = 1 }):Play()
			end
		elseif windowScale and window.Visible then
			local tween = TweenService:Create(windowScale, POP_OUT, { Scale = 0.6 })
			tween.Completed:Connect(function()
				if animation == mine then
					window.Visible = false
					windowScale.Scale = 1 -- your own code may open the window by setting Visible = true
				end
			end)
			tween:Play()
		else
			window.Visible = false
		end
	end

	-- Your own code may show or hide the window with Visible (for example your own button): follow it
	window:GetPropertyChangedSignal("Visible"):Connect(function()
		if window.Visible and not open then
			open = true
			animation += 1
			setMessage("", "neutral")
			if windowScale then
				windowScale.Scale = 1
			end
		elseif not window.Visible and open then
			open = false
			animation += 1
			if windowScale then
				windowScale.Scale = 1
			end
		end
	end)

	-- The window shakes a little when a code does not work
	local shaking = false
	local function shake()
		if shaking then
			return
		end
		shaking = true
		local start = window.Position
		task.spawn(function()
			for _, offset in ipairs({ -8, 8, -5, 5, 0 }) do
				TweenService:Create(window, TweenInfo.new(0.04), { Position = start + UDim2.fromOffset(offset, 0) }):Play()
				task.wait(0.04)
			end
			window.Position = start
			shaking = false
		end)
	end

	if parts.open then
		parts.open.Activated:Connect(function()
			setWindowVisible(not open)
		end)
		if parts.open:IsA("GuiButton") then
			pressable(parts.open)
		end
	end
	if parts.close then
		parts.close.Activated:Connect(function()
			setWindowVisible(false)
		end)
		if parts.close:IsA("GuiButton") then
			pressable(parts.close)
		end
	end
	pressable(parts.redeem)

	-- The outline of the code box turns purple while the player types
	local boxStroke = textBox:FindFirstChildOfClass("UIStroke")
	if boxStroke then
		local normal = boxStroke.Color
		textBox.Focused:Connect(function()
			boxStroke.Color = ACCENT_COLOR
		end)
		textBox.FocusLost:Connect(function()
			boxStroke.Color = normal
		end)
	end

	local function submit()
		if submitting then
			return
		end
		local text = textBox.Text
		if string.gsub(text, "%s+", "") == "" then
			return
		end
		submitting = true
		setMessage(T.busy, "neutral")
		local ok, success, key, rewards = pcall(function()
			return remote:InvokeServer(text)
		end)
		submitting = false
		if not ok then
			setMessage(T.error, "error")
			shake()
			return
		end
		if success then
			setMessage(describeRewards(rewards), "success")
			textBox.Text = ""
		else
			setMessage(T[key] or tostring(key), "error")
			shake()
		end
	end

	parts.redeem.Activated:Connect(submit)
	textBox.FocusLost:Connect(function(enterPressed)
		if enterPressed then
			submit()
		end
	end)
end

-- Only text objects have a Text property (a picture button or a frame does not)
local function hasText(instance)
	return instance:IsA("TextLabel") or instance:IsA("TextButton") or instance:IsA("TextBox")
end

-- Texts you did not change in the template follow the language (also when the ⚙️ Manager changes it while the game
-- runs); texts you wrote yourself stay as they are
local templateParts = nil -- the wired template, if the game uses one
local function localizeTemplate(parts)
	local function localize(instance, property, key)
		if not (instance and hasText(instance)) then
			return
		end
		for _, texts in pairs(TEXTS) do
			if instance[property] == texts[key] then
				instance[property] = T[key]
				return
			end
		end
	end
	-- the button's text: its own Text, or the TextLabel named Label in it (the template's gradient button)
	localize(parts.open and parts.open:FindFirstChild("Label") or parts.open, "Text", "button")
	localize(parts.title, "Text", "title")
	localize(parts.textBox, "PlaceholderText", "placeholder")
	localize(parts.redeem and parts.redeem:FindFirstChild("Label") or parts.redeem, "Text", "redeem")
	localize(parts.hint, "Text", "hint")
	-- the template's Codes picture: the one with the word in the player's language (unless you put your own picture)
	local picture = parts.open and parts.open:FindFirstChild("Skin")
	if picture and picture:IsA("ImageLabel") then
		for _, look in pairs(CODES_BUTTONS) do
			if picture.Image == look.image then
				local now = codesButtonLook()
				picture.Image = now.image
				local height = parts.open.Size.Y.Offset
				if height > 0 and parts.open.Size.X.Scale == 0 then
					parts.open.Size = UDim2.new(0, math.floor(now.width * height / 150 + 0.5), parts.open.Size.Y.Scale, height)
				end
				break
			end
		end
	end
end

-- Wires one copy of the template (once). false = it lacks the needed parts.
local function useTemplate(gui)
	if gui:GetAttribute(BOUND) then
		return true -- another copy of this script did it
	end
	local parts = findParts(gui)
	if not parts then
		return false
	end
	gui:SetAttribute(BOUND, true)
	gui.ResetOnSpawn = false
	localizeTemplate(parts)
	templateParts = parts
	hideLoneEdges(gui)
	wire(parts)
	return true
end

local function useDefault()
	local existing = playerGui:FindFirstChild(GUI_NAME)
	if existing and existing:GetAttribute(BOUND) then
		return existing -- already built and wired by another copy of this script
	end
	if existing then
		existing:Destroy()
	end
	local gui = makeDefaultGui()
	wire(findParts(gui))
	return gui
end

local defaultGui = nil
if templateGui then
	if not useTemplate(templateGui) then
		warn(
			"[DiscordCodes] StarterGui."
				.. GUI_NAME
				.. " is missing parts, so the built-in window is used instead. It needs a Frame named Window with a TextBox named CodeBox, "
				.. "a button named Redeem and a TextLabel named Message inside (see DOCS.html in the bot folder, or insert DiscordCodesWindow.rbxmx again)."
		)
		templateGui:Destroy()
		defaultGui = useDefault()
	end
else
	defaultGui = useDefault()
end

-- A copy of the template that arrives later (the character spawned late) replaces the built-in window
if StarterGui:FindFirstChild(GUI_NAME) then
	playerGui.ChildAdded:Connect(function(child)
		if child.Name ~= GUI_NAME or child:GetAttribute(BOUND) then
			return
		end
		if useTemplate(child) and defaultGui and defaultGui ~= child then
			defaultGui:Destroy()
			defaultGui = nil
		end
	end)
end

-- Settings changed in the ⚙️ Manager while the game runs: the built-in window is built again with them (an open
-- window stays open with the typed code). A template window from StarterGui keeps its own place for the button: only
-- its texts and whether the button shows follow.
local rebuildQueued = false
local function rebuild()
	rebuildQueued = false
	readSettings()
	if defaultGui then
		local old = findParts(defaultGui)
		local wasOpen, typed = old and old.window.Visible, old and old.textBox.Text or ""
		defaultGui:Destroy()
		defaultGui = useDefault()
		local new = findParts(defaultGui)
		if new then
			new.textBox.Text = typed
			new.window.Visible = wasOpen == true
		end
	elseif templateParts then
		localizeTemplate(templateParts)
		local show = remote:GetAttribute("ShowButton")
		if templateParts.open and show ~= nil then
			templateParts.open.Visible = show
		end
	end
end
remote.AttributeChanged:Connect(function()
	if not rebuildQueued then
		rebuildQueued = true
		task.defer(rebuild)
	end
end)
