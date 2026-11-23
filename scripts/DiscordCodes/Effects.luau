--!nonstrict
--[[
	DiscordCodes / Effects  (ModuleScript, inside DiscordLiveClient: it runs on each player's device)

	The animations of events (an event made in the ⚙️ Manager or on Discord can have one, e.g. "coin_storm").
	One event at a time has its full animation: the newest one that has an animation. Each animation has four parts:
	- the start (only when the event started a moment ago, not for a player who joins later): a short show;
	- while it runs: a calm loop around the player;
	- the last minute: a little more of it;
	- the end: everything fades out in 2 s and the light goes back exactly as the game had it.
	Rules for every animation, so the game always stays playable: nothing comes closer than about 25 studs to the camera,
	no flashes of the screen, the light changes only a little and slowly. Phones and low graphics get a lighter version.
	DiscordSettings -> EventEffects: "full" (default), "light" or "off" (the ⚙️ Manager can change it while the game runs).
	The textures are made in Blender (tools/vfx in the bot) and are Open Use on Roblox, so they load in every game.
]]

local Lighting = game:GetService("Lighting")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local UserInputService = game:GetService("UserInputService")
local Workspace = game:GetService("Workspace")

local Effects = {}

-- The textures of each animation (rbxassetid, uploaded from tools/vfx/out by the bot's author)
Effects.Assets = {
	coin_storm = {
		CoinSpin = "rbxassetid://89934896355831", -- 8x8 flipbook: a gold coin turning once around
		CoinGlint = "rbxassetid://106062802639237", -- 4x4 flipbook: a star glint opening and closing
		GoldDust = "rbxassetid://83190800475097", -- a soft gold glow
		GoldRing = "rbxassetid://99316226641015", -- a soft gold shock ring
		Icon = "rbxassetid://113726138582814", -- the event's icon (the round icon, the start countdown)
	},
	aurora = {
		-- curtains of aurora for beams: green edge, violet tips; variants with the same edges (turned: see aurora.py)
		CurtainA = {
			"rbxassetid://82602981780404",
			"rbxassetid://81126774119326",
			"rbxassetid://109902153943815",
			"rbxassetid://90801715548379",
		},
		CurtainB = { -- turquoise and pink tips (the colors take turns)
			"rbxassetid://103985561782060",
			"rbxassetid://105921095949362",
			"rbxassetid://72753442265799",
			"rbxassetid://70423568076826",
		},
		Haze = { -- the soft glow around a curtain
			"rbxassetid://104924224594581",
			"rbxassetid://72430673003232",
			"rbxassetid://86500980060231",
		},
		ExpOrb = "rbxassetid://109722080215681", -- 4x4 flipbook: a glass orb of light with turning rings
		StarTwinkle = "rbxassetid://80851362108176", -- 4x4 flipbook: a cold star opening and closing
		Glow = "rbxassetid://112477620062528", -- a soft turquoise glow
		Ring = "rbxassetid://90099011858639", -- a soft turquoise ring (the wave on the ground)
		Icon = "rbxassetid://91996613202319",
	},
	lucky_breeze = {
		CloverTumble = "rbxassetid://135897347061561", -- 4x4 flipbook: a four-leaf clover tumbling (the leaves in the wind)
		CloverTurn = "rbxassetid://89899181886566", -- 4x4 flipbook: the clover turning upright, gold glow (over each egg)
		Rainbow = "rbxassetid://118996897668806", -- a soft rainbow band for beams (red outside; turned: see lucky_breeze.py)
		WindStreak = "rbxassetid://137063294341044", -- a thin soft streak of wind (flies along its length)
		Wisp = "rbxassetid://138831948392027", -- a ribbon of wind for a Trail: soft bright core, mint edges, glitter
		LightShafts = "rbxassetid://104988609683173", -- golden rays of sun for a Beam from the clouds down
		Icon = "rbxassetid://128732215811234",
	},
	meteor_shower = {
		CrystalTumble = "rbxassetid://83277975113735", -- 4x4 flipbook: a violet-blue crystal tumbling (the impacts)
		MeteorCore = "rbxassetid://97930189274268", -- the head of a meteor: a white-hot core in a violet-blue glow
		MeteorTrail = "rbxassetid://139243006169452", -- the tail for a Trail: white core, blue and violet edges, sparks
		ShockRing = "rbxassetid://136023763777061", -- a soft white ring with a violet edge (the wave of an impact)
		Dust = "rbxassetid://136876618809962", -- a soft cloud of dust (tinted in the game)
		Planet = "rbxassetid://91226138789942", -- a ringed planet of violet, pink and blue gas (it rises at the start)
		NebulaCloud = { -- big soft clouds of glowing gas with stars: pink and violet, blue and violet
			"rbxassetid://129944075633370",
			"rbxassetid://122810385251376",
		},
		CrystalCluster = "rbxassetid://108791677999763", -- five crystals growing out of one point (where a meteor fell)
		Icon = "rbxassetid://94161661355073",
	},
	sakura_festival = {
		PetalTumble = "rbxassetid://128062726849884", -- 4x4 flipbook: a cherry petal tumbling
		Lantern = "rbxassetid://75573904815122", -- 4x4 flipbook: a red paper lantern lit from inside, swaying
		Blossom = "rbxassetid://91077803069762", -- a big open cherry blossom with a soft pink glow (the start)
		SakuraTree = "rbxassetid://130089470109807", -- a cherry tree in full bloom (the horizon)
		Moon = "rbxassetid://79662437268873", -- a pale full moon in a pink halo
		Mist = "rbxassetid://140337350603461", -- a soft wide band of pink mist (the horizon)
		Mountain = "rbxassetid://108407132932548", -- a big snow-capped mountain fading into pink mist (the horizon)
		Pagoda = "rbxassetid://100862408987258", -- a five-roof pagoda with warm lit windows (the horizon)
		Torii = "rbxassetid://83793023379366", -- a red torii gate (the horizon)
		Icon = "rbxassetid://81810477884031",
	},
}

local previewing = false -- true while the ⚙️ Manager's preview builds an animation
local meteorSkyOwner = nil -- the Meteor Shower that shows the planet and the nebulae (one sky is enough)
local INTRO_WINDOW = 20 -- seconds after the start: a player who sees the event this early gets its start show
local FINAL_SECONDS = 60

local player = Players.LocalPlayer
local camera = Workspace.CurrentCamera
local folder = nil
local quality = "full"

-- ---------- Small helpers shared by the animations ----------

local function seq(...)
	local points = {}
	local args = { ... }
	for i = 1, #args, 2 do
		table.insert(points, NumberSequenceKeypoint.new(args[i], args[i + 1]))
	end
	return NumberSequence.new(points)
end

local function holderFolder()
	if not folder or not folder.Parent then
		folder = Instance.new("Folder")
		folder.Name = "DiscordEventFX"
		folder.Parent = Workspace
	end
	return folder
end

local function anchorPart(size)
	local part = Instance.new("Part")
	part.Name = "FX"
	part.Anchored = true
	part.CanCollide = false
	part.CanQuery = false
	part.CanTouch = false
	part.CastShadow = false
	part.Transparency = 1
	part.Size = size
	part.Parent = holderFolder()
	return part
end

local function emitter(parent, props)
	local e = Instance.new("ParticleEmitter")
	e.Rate = 0
	for key, value in pairs(props) do
		e[key] = value
	end
	e.Parent = parent
	return e
end

local params = RaycastParams.new()
params.FilterType = Enum.RaycastFilterType.Exclude

-- The ground under a point (the effects' own parts and the player don't count)
local function groundY(position, fallback)
	local ignore = { holderFolder() }
	if player.Character then
		table.insert(ignore, player.Character)
	end
	params.FilterDescendantsInstances = ignore
	local hit = Workspace:Raycast(position + Vector3.new(0, 80, 0), Vector3.new(0, -200, 0), params)
	return hit and hit.Position.Y or fallback
end

local function rootPart()
	local character = player.Character
	return character and character:FindFirstChild("HumanoidRootPart")
end

-- Light changes made by an animation: tweened in, and back to nothing at the end (the game's own light is never touched)
local function lightEffects(props)
	local made = {}
	for className, goal in pairs(props) do
		local effect = Instance.new(className)
		effect.Name = "DiscordEvent" .. className
		if className == "BloomEffect" then -- a new bloom glows at once (0.4): it starts at 0, only its strength changes
			effect.Intensity = 0
			effect.Size = goal.Size or 24
			effect.Threshold = goal.Threshold or 2
			goal = { Intensity = goal.Intensity }
		end
		local start = {}
		for key in pairs(goal) do
			start[key] = effect[key]
		end
		effect.Parent = Lighting
		TweenService:Create(effect, TweenInfo.new(2.5), goal):Play()
		table.insert(made, { effect = effect, start = start })
	end
	return function()
		for _, entry in ipairs(made) do
			local tween = TweenService:Create(entry.effect, TweenInfo.new(2), entry.start)
			tween:Play()
			task.delay(2.1, function()
				entry.effect:Destroy()
			end)
		end
	end
end

-- A mood of the sky for this player only (the night of Aurora, the golden hour of Lucky Breeze): the game's clock goes to
-- the mood's hour (go(1, seconds)) and back (stop), the air takes the mood's colors, and a mood with clearSky gives the
-- game's sky and clouds way to a clear (starry at night) sky while it holds. Two animations can hold a mood at once (an
-- event and a preview, or a new event while the old one fades out): the strongest one shows, the first one keeps the
-- game's day and the last one out gives it back. If the game moves its clock meanwhile (a day cycle), that moves the day.
local night = nil -- while any animation holds a mood: { users, day, written, air, airDay, hidden, watch }

local function hideSky()
	local hidden = { skies = {} }
	for _, sky in ipairs(Lighting:GetChildren()) do
		if sky:IsA("Sky") then
			table.insert(hidden.skies, sky)
			sky.Parent = nil
		end
	end
	local clouds = Workspace.Terrain:FindFirstChildOfClass("Clouds")
	if clouds and clouds.Enabled then
		hidden.clouds = clouds
		clouds.Enabled = false
	end
	local sky = Instance.new("Sky") -- Roblox's own clear sky: at night only stars
	sky.Name = "DiscordEventSky"
	sky.SkyboxBk, sky.SkyboxDn, sky.SkyboxFt, sky.SkyboxLf, sky.SkyboxRt, sky.SkyboxUp = "", "", "", "", "", ""
	sky.StarCount = 5000
	sky.Parent = Lighting
	hidden.sky = sky
	night.hidden = hidden
end

-- Each thing on its own: a sky the game destroyed or moved meanwhile stays as the game left it
local function showSky()
	local hidden = night.hidden
	night.hidden = nil
	if hidden.clouds then
		pcall(function()
			hidden.clouds.Enabled = true
		end)
	end
	hidden.sky:Destroy()
	for _, sky in ipairs(hidden.skies) do
		pcall(function()
			if sky.Parent == nil then
				sky.Parent = Lighting
			end
		end)
	end
end

-- Two moods at once mix by how strong each one is (no jump when one takes over from the other)
local function applyNight()
	local from = night.airDay
	local strength, weight, span, clear = 0, 0, 0, false
	local color, decay, haze, glare = Vector3.zero, Vector3.zero, 0, 0
	-- how far each mood's hour is (forward through the day, or back when it is close behind); moods that would go
	-- opposite ways round the clock all go the way of the strongest one (no bright day halfway between them)
	local function hoursTo(mood)
		local hours = (mood.clock - night.day) % 24
		return hours > 12 and hours - 24 or hours
	end
	local lead = nil
	for user in pairs(night.users) do
		if user.dark > 0 and (not lead or user.dark > lead.dark) then
			lead = user
		end
	end
	local way = lead and hoursTo(lead.mood) or 0
	for user in pairs(night.users) do
		local w, mood = user.dark, user.mood
		if w > 0 then
			strength, weight = math.max(strength, w), weight + w
			local hours = hoursTo(mood)
			if hours * way < 0 then
				hours = hours + (way > 0 and 24 or -24)
			end
			span = span + hours * w
			clear = clear or (mood.clearSky and w >= 0.6) -- the skies change when the mood is mostly there
			if from then
				local to = mood.air or from
				local c, d = to.Color, to.Decay
				color = color + Vector3.new(c.R, c.G, c.B) * w
				decay = decay + Vector3.new(d.R, d.G, d.B) * w
				haze = haze + (to.hazeDown and math.min(from.Haze, to.Haze) or to.Haze) * w -- hazeDown: never more haze
				glare = glare + to.Glare * w
			end
		end
	end
	span = weight > 0 and span / weight or 0
	night.written = (night.day + span * strength) % 24
	Lighting.ClockTime = night.written
	if clear and not night.hidden then
		hideSky()
	elseif not clear and night.hidden then
		showSky()
	end
	local air = night.air
	if air and from and weight > 0 then
		color, decay = color / weight, decay / weight
		air.Color = from.Color:Lerp(Color3.new(color.X, color.Y, color.Z), strength)
		air.Decay = from.Decay:Lerp(Color3.new(decay.X, decay.Y, decay.Z), strength)
		air.Haze = from.Haze + (haze / weight - from.Haze) * strength
		air.Glare = from.Glare + (glare / weight - from.Glare) * strength
	elseif air and from then
		for key, start in pairs(from) do
			air[key] = start
		end
	end
end

local function startNight()
	night = { users = {}, day = Lighting.ClockTime }
	local air = Lighting:FindFirstChildOfClass("Atmosphere")
	if air then
		night.air = air
		night.airDay = { Color = air.Color, Decay = air.Decay, Haze = air.Haze, Glare = air.Glare }
	end
	night.watch = Lighting:GetPropertyChangedSignal("ClockTime"):Connect(function()
		local off = (Lighting.ClockTime - night.written) % 24
		if off > 12 then
			off = off - 24
		end
		if math.abs(off) <= 0.01 then
			return -- our own change
		end
		-- a day cycle that adds a little to the clock moves the game's day on; a big change is a new time from the game
		night.day = math.abs(off) < 1 and (night.day + off) % 24 or Lighting.ClockTime
		applyNight()
	end)
end

local function endNight()
	night.watch:Disconnect()
	Lighting.ClockTime = night.day
	if night.hidden then
		showSky()
	end
	if night.air then
		for key, start in pairs(night.airDay) do
			night.air[key] = start
		end
	end
	night = nil
end

-- mood: { clock = the hour, air = { Color, Decay, Haze, Glare, hazeDown } of the Atmosphere (optional; hazeDown: the
-- haze only goes down to it, never up), clearSky = true/false }
local function skyMood(mood)
	if not night then
		startNight()
	end
	local user = { dark = 0, mood = mood }
	night.users[user] = true
	local value = Instance.new("NumberValue")
	value.Changed:Connect(function(v)
		user.dark = v
		applyNight()
	end)
	local handle = {}
	function handle.go(to, seconds)
		if seconds <= 0 then
			value.Value = to
			return
		end
		TweenService:Create(value, TweenInfo.new(seconds, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut), { Value = to }):Play()
	end
	function handle.stop(seconds)
		handle.go(0, seconds)
		task.delay(seconds + 0.1, function()
			value:Destroy()
			night.users[user] = nil
			if next(night.users) then
				applyNight()
			else
				endNight()
			end
		end)
	end
	return handle
end

-- Zones that follow the player: a ring of parts at a distance, each placed over the ground under it
local function followRing(rings, build)
	local zones = {}
	for _, ring in ipairs(rings) do
		for i = 1, ring.zones do
			local zone = build(ring)
			zone.radius = ring.radius
			zone.height = ring.height or 30
			zone.angle = (i - 1) / ring.zones * math.pi * 2 + ring.radius
			table.insert(zones, zone)
		end
	end
	local connection = RunService.Heartbeat:Connect(function()
		local root = rootPart()
		if not root then
			return
		end
		local center = root.Position
		for _, zone in ipairs(zones) do
			local spot = center + Vector3.new(math.cos(zone.angle) * zone.radius, 0, math.sin(zone.angle) * zone.radius)
			local y = groundY(spot, center.Y - 3)
			if zone.sky then
				zone.sky.CFrame = CFrame.new(spot.X, y + zone.height, spot.Z)
			end
			if zone.ground then
				zone.ground.CFrame = CFrame.new(spot.X, y + 0.3, spot.Z)
			end
		end
	end)
	return zones, connection
end

-- How much of an animation: 1 full, 0.5 on phones and low graphics
local function amount()
	return quality == "light" and 0.5 or 1
end

-- ---------- Coin Storm (a currency boost) ----------

local animations = {}

animations.coin_storm = function()
	local A = Effects.Assets.coin_storm
	local GOLD = ColorSequence.new(Color3.fromRGB(255, 214, 120))
	local scale = amount()
	local function coinProps(extra)
		local props = {
			Texture = A.CoinSpin, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid8x8,
			FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(30, 50),
			FlipbookStartRandom = true, Brightness = 1.15, LightInfluence = 0.35, RotSpeed = NumberRange.new(-90, 90),
		}
		for key, value in pairs(extra) do
			props[key] = value
		end
		return props
	end
	local rings = { { radius = 34, zones = 5, size = 18, rate = 3, height = 32 },
		{ radius = 60, zones = 8, size = 32, rate = 6, height = 32 } }
	local emitters = {}
	local zones, follow = followRing(rings, function(ring)
		local sky = anchorPart(Vector3.new(ring.size, 1, ring.size))
		local coins = emitter(sky, coinProps({ FlipbookFramerate = NumberRange.new(28, 46), Size = seq(0, 2.2, 1, 2.2),
			Transparency = seq(0, 1, 0.08, 0, 0.85, 0, 1, 1), Lifetime = NumberRange.new(1.7, 2.0),
			Speed = NumberRange.new(10, 16), EmissionDirection = Enum.NormalId.Bottom, SpreadAngle = Vector2.new(8, 8),
			Acceleration = Vector3.new(0, -32, 0), Rotation = NumberRange.new(-25, 25), RotSpeed = NumberRange.new(-40, 40) }))
		local glints = emitter(sky, { Texture = A.CoinGlint, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Size = seq(0, 3.2, 1, 3.2), Lifetime = NumberRange.new(0.55, 0.7),
			Speed = NumberRange.new(14, 18), EmissionDirection = Enum.NormalId.Bottom, Acceleration = Vector3.new(0, -28, 0),
			LightEmission = 1, LightInfluence = 0 })
		local ground = anchorPart(Vector3.new(ring.size, 1, ring.size))
		local dust = emitter(ground, { Texture = A.GoldDust, Color = GOLD, Size = seq(0, 0.6, 0.3, 2.6, 1, 0),
			Transparency = seq(0, 0.25, 1, 1), Lifetime = NumberRange.new(1.2, 1.8), Speed = NumberRange.new(0.5, 2),
			EmissionDirection = Enum.NormalId.Top, LightEmission = 0.8, LightInfluence = 0 })
		table.insert(emitters, { coins, ring.rate * scale })
		table.insert(emitters, { glints, ring.rate * 0.35 * scale })
		table.insert(emitters, { dust, 2 * scale })
		return { sky = sky, ground = ground }
	end)
	local function setRates(factor)
		for _, entry in ipairs(emitters) do
			entry[1].Rate = entry[2] * factor
		end
	end
	setRates(1)
	local restoreLight = lightEffects(quality == "light"
		and { ColorCorrectionEffect = { TintColor = Color3.fromRGB(255, 244, 222), Saturation = 0.1 } }
		or { ColorCorrectionEffect = { TintColor = Color3.fromRGB(255, 244, 222), Saturation = 0.12, Brightness = 0.03, Contrast = 0.04 },
			BloomEffect = { Intensity = 0.15, Size = 30, Threshold = 2.2 } })

	-- the start (about 6 s): the big coin falls, bursts into a coin fountain, leaves treasure, ends in a pillar of light
	local function intro()
		local root = rootPart()
		if not root then
			return
		end
		local look = camera.CFrame.LookVector
		local flat = Vector3.new(look.X, 0, look.Z)
		flat = flat.Magnitude > 0.01 and flat.Unit or Vector3.new(0, 0, -1)
		local target = root.Position + flat * 30
		local floor = groundY(target, root.Position.Y - 3)
		local impact = Vector3.new(target.X, floor + 0.4, target.Z)
		local mark = anchorPart(Vector3.new(1, 1, 1))
		mark.CFrame = CFrame.new(impact)
		local glow = emitter(mark, { Texture = A.GoldDust, Color = GOLD, Orientation = Enum.ParticleOrientation.VelocityPerpendicular,
			EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(0.01), LightEmission = 1, LightInfluence = 0,
			Size = seq(0, 2, 1, 14), Transparency = seq(0, 1, 0.3, 0.45, 1, 1), Lifetime = NumberRange.new(1.5) })
		glow.Rate = 6
		local holder = anchorPart(Vector3.new(1, 1, 1))
		holder.CFrame = CFrame.new(target.X, floor + 80, target.Z)
		local board = Instance.new("BillboardGui")
		board.Size = UDim2.fromScale(9, 9)
		board.LightInfluence = 0
		board.Brightness = 1.25
		board.Parent = holder
		local image = Instance.new("ImageLabel")
		image.BackgroundTransparency = 1
		image.Size = UDim2.fromScale(1, 1)
		image.Image = A.CoinSpin
		image.ImageRectSize = Vector2.new(128, 128)
		image.Parent = board
		local trail = emitter(holder, { Texture = A.GoldDust, Color = GOLD, Size = seq(0, 5, 1, 0), Transparency = seq(0, 0.35, 1, 1),
			Lifetime = NumberRange.new(0.6), Speed = NumberRange.new(0), LightEmission = 1, LightInfluence = 0 })
		trail.Rate = 40
		local spinSpeed = 30
		local frame = 0
		local spinning = RunService.RenderStepped:Connect(function(dt)
			frame = (frame + dt * spinSpeed) % 64
			local index = math.floor(frame)
			image.ImageRectOffset = Vector2.new((index % 8) * 128, math.floor(index / 8) * 128)
		end)
		local land = floor + 4.5
		local fall = TweenService:Create(holder, TweenInfo.new(1.5, Enum.EasingStyle.Quad, Enum.EasingDirection.In),
			{ CFrame = CFrame.new(target.X, land, target.Z) })
		fall:Play()
		fall.Completed:Wait()
		glow.Rate = 0
		local spot = anchorPart(Vector3.new(16, 1, 16))
		spot.CFrame = CFrame.new(impact)
		emitter(spot, { Texture = A.GoldRing, Orientation = Enum.ParticleOrientation.VelocityPerpendicular,
			EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(0.01), Size = seq(0, 3, 1, 34),
			Transparency = seq(0, 0.05, 1, 1), Lifetime = NumberRange.new(1.1), LightEmission = 1, LightInfluence = 0 }):Emit(1)
		-- the splash and the fountain lean 30 degrees away from the player: nothing flies up to the camera
		local point = anchorPart(Vector3.new(1, 1, 1))
		point.CFrame = CFrame.new(impact) * CFrame.fromAxisAngle(Vector3.new(0, 1, 0):Cross(flat), math.rad(30))
		emitter(point, coinProps({ EmissionDirection = Enum.NormalId.Top, SpreadAngle = Vector2.new(55, 55),
			Speed = NumberRange.new(30, 46), Acceleration = Vector3.new(0, -34, 0), Drag = 0.35, Size = seq(0, 1.7, 1, 1.7),
			Transparency = seq(0, 0, 0.88, 0, 1, 1), Lifetime = NumberRange.new(2.4, 3.0) })):Emit(math.floor(55 * scale))
		local sparks = emitter(point, { Texture = A.CoinGlint, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, EmissionDirection = Enum.NormalId.Top,
			SpreadAngle = Vector2.new(70, 70), Speed = NumberRange.new(12, 34), Drag = 2.5, Size = seq(0, 4, 1, 4),
			Lifetime = NumberRange.new(0.7, 0.9), LightEmission = 1, LightInfluence = 0 })
		sparks:Emit(20)
		local fountain = emitter(point, coinProps({ EmissionDirection = Enum.NormalId.Top, SpreadAngle = Vector2.new(18, 18),
			Speed = NumberRange.new(24, 32), Acceleration = Vector3.new(0, -40, 0), Size = seq(0, 1.4, 1, 1.4),
			Transparency = seq(0, 0, 0.85, 0, 1, 1), Lifetime = NumberRange.new(1.4, 1.7) }))
		fountain.Rate = 28 * scale
		TweenService:Create(fountain, TweenInfo.new(2.5, Enum.EasingStyle.Quad, Enum.EasingDirection.In), { Rate = 0 }):Play()
		sparks.Rate = 6
		TweenService:Create(sparks, TweenInfo.new(2.5), { Rate = 0 }):Play()
		emitter(spot, coinProps({ Shape = Enum.ParticleEmitterShape.Disc, ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume,
			FlipbookFramerate = NumberRange.new(8, 16), Speed = NumberRange.new(0), RotSpeed = NumberRange.new(0),
			Rotation = NumberRange.new(-15, 15), Size = seq(0, 1.3, 1, 1.3), Transparency = seq(0, 1, 0.08, 0, 0.82, 0, 1, 1),
			Lifetime = NumberRange.new(3.5, 4.5), ZOffset = 0.5 })):Emit(math.floor(26 * scale))
		local twinkle = emitter(spot, { Texture = A.CoinGlint, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Shape = Enum.ParticleEmitterShape.Disc,
			Speed = NumberRange.new(0), Size = seq(0, 2.6, 1, 2.6), Lifetime = NumberRange.new(0.6, 0.8), LightEmission = 1,
			LightInfluence = 0, ZOffset = 1 })
		twinkle.Rate = 7
		task.delay(3.6, function()
			twinkle.Enabled = false
		end)
		TweenService:Create(holder, TweenInfo.new(0.45, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
			{ CFrame = CFrame.new(target.X, land + 7, target.Z) }):Play()
		TweenService:Create(board, TweenInfo.new(1.2, Enum.EasingStyle.Back, Enum.EasingDirection.Out),
			{ Size = UDim2.fromScale(12, 12) }):Play()
		local speedUp = 0
		while speedUp < 1.2 do
			speedUp = speedUp + task.wait()
			spinSpeed = 30 + speedUp * 70
		end
		local pillar = Instance.new("Part")
		pillar.Shape = Enum.PartType.Cylinder
		pillar.Anchored, pillar.CanCollide, pillar.CanQuery, pillar.CanTouch, pillar.CastShadow = true, false, false, false, false
		pillar.Material = Enum.Material.Neon
		pillar.Color = Color3.fromRGB(255, 205, 90)
		pillar.Size = Vector3.new(90, 0.5, 0.5)
		pillar.CFrame = CFrame.new(target.X, floor + 45, target.Z) * CFrame.Angles(0, 0, math.rad(90))
		pillar.Transparency = 0.25
		pillar.Parent = holderFolder()
		TweenService:Create(pillar, TweenInfo.new(0.25, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
			{ Size = Vector3.new(90, 5, 5) }):Play()
		TweenService:Create(pillar, TweenInfo.new(1.6, Enum.EasingStyle.Quad, Enum.EasingDirection.In),
			{ Transparency = 1, Size = Vector3.new(90, 1, 1) }):Play()
		emitter(holder, coinProps({ EmissionDirection = Enum.NormalId.Top, SpreadAngle = Vector2.new(180, 180),
			Speed = NumberRange.new(18, 30), Acceleration = Vector3.new(0, -24, 0), Drag = 0.6, Size = seq(0, 1.6, 1, 1.6),
			Transparency = seq(0, 0, 0.85, 0, 1, 1), Lifetime = NumberRange.new(1.8, 2.3) })):Emit(math.floor(36 * scale))
		local rise = emitter(point, { Texture = A.CoinGlint, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Shape = Enum.ParticleEmitterShape.Cylinder,
			EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(14, 24), Size = seq(0, 3, 1, 3),
			Lifetime = NumberRange.new(0.8, 1.2), LightEmission = 1, LightInfluence = 0 })
		rise.Rate = 30 * scale
		TweenService:Create(rise, TweenInfo.new(1.6), { Rate = 0 }):Play()
		board.Enabled = false
		trail.Rate = 0
		spinning:Disconnect()
		task.delay(5, function()
			for _, part in ipairs({ mark, holder, spot, point, pillar }) do
				part:Destroy()
			end
		end)
	end

	-- the last minute: more coins, and now and then a golden shower far away
	local finalLoop = nil
	local function final()
		setRates(1.5)
		finalLoop = task.spawn(function()
			while true do
				task.wait(6)
				local root = rootPart()
				if root then
					local angle = math.random() * math.pi * 2
					local spot = root.Position + Vector3.new(math.cos(angle) * 70, 0, math.sin(angle) * 70)
					local y = groundY(spot, root.Position.Y - 3)
					local shower = anchorPart(Vector3.new(14, 1, 14))
					shower.CFrame = CFrame.new(spot.X, y + 36, spot.Z)
					local burst = emitter(shower, coinProps({ EmissionDirection = Enum.NormalId.Bottom, Speed = NumberRange.new(8, 14),
						Acceleration = Vector3.new(0, -30, 0), Size = seq(0, 2, 1, 2), Transparency = seq(0, 0, 0.85, 0, 1, 1),
						Lifetime = NumberRange.new(1.8, 2.1) }))
					burst.Rate = 40 * scale
					task.delay(1.2, function()
						burst.Rate = 0
					end)
					task.delay(4, function()
						shower:Destroy()
					end)
				end
			end
		end)
	end

	local function stop()
		if finalLoop then
			task.cancel(finalLoop)
		end
		setRates(0)
		restoreLight()
		task.delay(2.5, function()
			follow:Disconnect()
			for _, zone in ipairs(zones) do
				zone.sky:Destroy()
				zone.ground:Destroy()
			end
		end)
	end

	return { intro = intro, final = final, stop = stop }
end

-- ---------- Aurora (an EXP boost) ----------

-- One ribbon of aurora high in the sky: a chain of beams through points that wave and drift slowly over the sky,
-- standing upright like a curtain (its bright lower edge at the bottom), with waves of light flowing along it. Each
-- beam shows one of the texture's variants (they join without a seam): no pattern repeats along the ribbon. It keeps
-- its place around the player, like a sky far away.
local function auroraRibbon(def)
	local anchor = anchorPart(Vector3.new(1, 1, 1))
	anchor.CFrame = CFrame.new()
	local points, beams = {}, {}
	for i = 1, def.points do
		local attachment = Instance.new("Attachment")
		attachment.Parent = anchor
		points[i] = attachment
	end
	local last = nil
	for i = 1, def.points - 1 do
		local beam = Instance.new("Beam")
		beam.Attachment0, beam.Attachment1 = points[i], points[i + 1]
		local pick = math.random(#def.textures) -- a random variant, never the same twice in a row
		if pick == last then
			pick = pick % #def.textures + 1
		end
		last = pick
		beam.Texture = def.textures[pick]
		beam.TextureMode = Enum.TextureMode.Stretch
		beam.TextureLength = 1
		beam.TextureSpeed = 0 -- a moving texture would open the joins between the variants
		beam.LightEmission = 0.9 -- added light: it glows on the night sky
		beam.LightInfluence = 0
		beam.Brightness = def.brightness or 1.6
		beam.FaceCamera = false
		beam.Segments = 14
		beam.ZOffset = def.z or 0
		beam.Transparency = NumberSequence.new(1)
		beam.Parent = anchor
		beams[i] = beam
	end
	local ribbon = { anchor = anchor, reveal = 0, opacity = 0, shown = nil }

	-- where point k is (s from -0.5 to 0.5 along the ribbon) at time t: the whole ribbon drifts around the sky, comes
	-- closer and goes away, rises and sinks, and waves run along it
	local function spot(center, s, t)
		local p = def.phase
		local angle = def.angle + 0.22 * math.sin(t * 0.025 + p * 7) + 0.08 * math.sin(t * 0.061 + p * 3)
		local distance = def.distance * (1 + 0.08 * math.sin(t * 0.03 + p * 5))
		local out = Vector3.new(math.cos(angle), 0, math.sin(angle))
		local side = Vector3.new(-math.sin(angle), 0, math.cos(angle))
		local depth = 30 * math.sin(2 * math.pi * (s * 1.2 + t * 0.055 + p))
			+ 12 * math.sin(2 * math.pi * (s * 2.6 - t * 0.085 + p * 2))
		local lift = 18 * math.sin(2 * math.pi * (s * 1.6 + t * 0.06 + p))
			+ 7 * math.sin(2 * math.pi * (s * 3.4 - t * 0.095 + p * 3))
			+ 12 * math.sin(t * 0.035 + p * 4)
		return center + out * (distance + depth) + side * (s * def.length) + Vector3.new(0, def.height + lift, 0)
	end

	-- the light flows along the ribbon: brighter waves travel slowly from one end to the other
	local function flow(s, t)
		local wave = 0.5 + 0.5 * math.sin(2 * math.pi * (s * 1.3 - t * 0.07 + def.phase))
		local slow = 0.5 + 0.5 * math.sin(2 * math.pi * (s * 0.6 + t * 0.03 + def.phase * 2))
		return 0.45 + 0.4 * wave + 0.15 * slow
	end

	-- 0 at the ribbon's ends, 1 in its middle; the reveal opens it from one end to the other
	local function visible(s)
		local body = math.sin(math.pi * (s + 0.5)) ^ 0.7
		local open = math.clamp((ribbon.reveal * 1.35 - (s + 0.5)) / 0.35, 0, 1)
		return body * open
	end

	function ribbon.update(center, t)
		local count = def.points
		local positions = {}
		for k = 1, count do
			positions[k] = spot(center, (k - 1) / (count - 1) - 0.5, t)
		end
		-- each point's X axis runs along the ribbon (the beams curve smoothly through it), Y points up (the width)
		for k = 1, count do
			local here = positions[k]
			local before = positions[math.max(k - 1, 1)]
			local after = positions[math.min(k + 1, count)]
			local along = after - before
			along = along.Magnitude > 0.01 and along.Unit or Vector3.xAxis
			local up = Vector3.yAxis - along * along.Y
			up = up.Magnitude > 0.01 and up.Unit or Vector3.zAxis
			points[k].CFrame = CFrame.fromMatrix(here, along, up)
		end
		local opening = ribbon.shown ~= ribbon.reveal -- the widths change only while the ribbon opens or rolls up
		ribbon.shown = ribbon.reveal
		for i, beam in ipairs(beams) do
			local length = (positions[i + 1] - positions[i]).Magnitude
			beam.CurveSize0 = length / 3
			beam.CurveSize1 = length / 3
			local s0 = (i - 1) / (count - 1) - 0.5
			local s1 = i / (count - 1) - 0.5
			local v0, v1 = visible(s0), visible(s1)
			if opening then
				beam.Width0 = def.width * (0.35 + 0.65 * v0) * (0.4 + 0.6 * ribbon.reveal)
				beam.Width1 = def.width * (0.35 + 0.65 * v1) * (0.4 + 0.6 * ribbon.reveal)
			end
			beam.Transparency = NumberSequence.new(1 - v0 * flow(s0, t) * ribbon.opacity, 1 - v1 * flow(s1, t) * ribbon.opacity)
		end
	end

	return ribbon
end

animations.aurora = function()
	local A = Effects.Assets.aurora
	local light = quality == "light"
	local scale = amount()
	local TEAL = ColorSequence.new(Color3.fromRGB(110, 255, 214))
	local alive = true
	local speed = 1 -- the waves: faster in the last minute
	local glow = 1 -- how bright the aurora is (the last minute: brighter)

	-- the ribbons: around the player at the start, the first ones in front of the camera, at three heights that cross
	-- each other: low over the horizon (the usual camera looks a little down, it must still be on the screen), higher,
	-- and nearly overhead
	local look = camera.CFrame.LookVector
	local front = math.atan2(look.Z, look.X)
	local layout = {
		{ angle = 0, distance = 250, height = 56, length = 420, width = 110, phase = 0.1 },
		{ angle = 0.45, distance = 210, height = 125, length = 460, width = 130, phase = 0.55 },
		{ angle = -0.35, distance = 150, height = 210, length = 520, width = 150, phase = 0.85 },
		{ angle = 1.25, distance = 285, height = 62, length = 380, width = 100, phase = 0.45 },
		{ angle = -1.4, distance = 270, height = 60, length = 360, width = 104, phase = 0.7 },
		{ angle = math.pi, distance = 295, height = 64, length = 430, width = 112, phase = 0.25 },
		{ angle = math.pi - 0.5, distance = 190, height = 160, length = 460, width = 130, phase = 0.35 },
	}
	local ribbons = {}
	for n, def in ipairs(layout) do
		if not light or n <= 3 then
			local pair = {}
			for layer, textures in ipairs({ A.CurtainA, A.CurtainB }) do
				if not light or layer == 1 then
					table.insert(pair, auroraRibbon({ angle = front + def.angle, distance = def.distance + (layer - 1) * 14,
						height = def.height + (layer - 1) * 12, length = def.length, width = def.width * (layer == 1 and 1 or 0.85),
						phase = def.phase + (layer - 1) * 0.13, points = light and 7 or 9, textures = textures, z = layer,
						brightness = layer == 1 and 2.3 or 2 }))
				end
			end
			-- soft glows around the curtains: the aurora spreads into the sky and its colors mix with it, instead of
			-- ending at a line (a wide glow, and a much wider faint wash of color behind it)
			local glows = {}
			for g, size in ipairs(light and { 2.3 } or { 2.3, 3.6 }) do
				table.insert(glows, auroraRibbon({ angle = front + def.angle, distance = def.distance + 25 * g,
					height = def.height + def.width * 0.2 * g, length = def.length * (1 + 0.15 * g), width = def.width * size,
					phase = def.phase, points = light and 7 or 9, textures = A.Haze, z = 0, brightness = 1.5 }))
			end
			local entry = { layers = pair, glows = glows, phase = def.phase * 6, reveal = 0, opening = Instance.new("NumberValue") }
			entry.opening.Changed:Connect(function(v)
				entry.reveal = v
			end)
			table.insert(ribbons, entry)
		end
	end

	-- the stars of the night, high above (they twinkle in and out)
	local starField = anchorPart(Vector3.new(560, 150, 560))
	local stars = emitter(starField, { Texture = A.StarTwinkle, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
		FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Shape = Enum.ParticleEmitterShape.Box,
		Speed = NumberRange.new(0), Size = seq(0, 7, 1, 7), Lifetime = NumberRange.new(2.5, 4.5),
		Rotation = NumberRange.new(-20, 20), LightEmission = 1, LightInfluence = 0, Brightness = 2 })

	-- small orbs of EXP rise from the ground around the player now and then
	local rings = { { radius = 30, zones = 5, size = 14 }, { radius = 52, zones = 7, size = 20 } }
	local orbEmitters = {}
	local zones, follow = followRing(rings, function(ring)
		local ground = anchorPart(Vector3.new(ring.size, 1, ring.size))
		local orbs = emitter(ground, { Texture = A.ExpOrb, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(10, 16), FlipbookStartRandom = true,
			Shape = Enum.ParticleEmitterShape.Box, EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(3, 5),
			Acceleration = Vector3.new(0, 2.5, 0), Lifetime = NumberRange.new(3.5, 5),
			Size = seq(0, 0, 0.15, 1.7, 0.75, 1.5, 1, 0), Transparency = seq(0, 0.2, 0.7, 0.2, 1, 1),
			Rotation = NumberRange.new(-30, 30), RotSpeed = NumberRange.new(-20, 20), LightEmission = 0.7, LightInfluence = 0 })
		table.insert(orbEmitters, orbs)
		return { ground = ground }
	end)
	local function setRates(factor)
		stars.Rate = (light and 20 or 40) * factor
		for _, orbs in ipairs(orbEmitters) do
			orbs.Rate = 0.35 * scale * factor
		end
	end

	-- the night: the sky goes dark (the game's own clock, for this player only), a cool tint, the aurora glows
	local dusk = skyMood({ clock = 0, clearSky = true,
		air = { Color = Color3.fromRGB(28, 34, 70), Decay = Color3.fromRGB(40, 30, 80), Haze = 0.3, Glare = 0, hazeDown = true } })
	local restoreLight = lightEffects(light
		and { ColorCorrectionEffect = { TintColor = Color3.fromRGB(220, 228, 255), Saturation = 0.08 } }
		or { ColorCorrectionEffect = { TintColor = Color3.fromRGB(215, 225, 255), Contrast = 0.05, Saturation = 0.1 },
			BloomEffect = { Intensity = 0.12, Size = 28, Threshold = 2.3 } })

	-- the sky follows the player (like a real sky far away); its height follows only slowly (jumps don't move it)
	local root = rootPart()
	local base = root and root.Position or camera.CFrame.Position
	local clock, waiting, frame = 0, 0, 0
	local stepping = RunService.RenderStepped:Connect(function(dt)
		clock = clock + dt * speed
		if light then -- phones: 30 times a second (the time left over counts for the next one: an even pace)
			waiting = waiting + dt
			if waiting < 1 / 30 then
				return
			end
			waiting = math.min(waiting - 1 / 30, 1 / 30)
		end
		frame = frame + 1
		local r = rootPart()
		if r then
			local y = base.Y + (r.Position.Y - base.Y) * math.min(1, dt * 1.5)
			base = Vector3.new(r.Position.X, y, r.Position.Z)
		end
		starField.CFrame = CFrame.new(base + Vector3.new(0, 115, 0))
		for _, ribbon in ipairs(ribbons) do
			if light or frame % 2 == 0 then -- the soft glows move slowly: every second frame is enough
				for g, part in ipairs(ribbon.glows) do
					part.reveal = ribbon.reveal
					part.opacity = math.clamp((g == 1 and 0.75 or 0.35) * glow, 0, 1)
					part.update(base, clock)
				end
			end
			local swing = 0.5 + 0.5 * math.cos(clock * 0.16 + ribbon.phase) -- the two colors take turns
			for layer, part in ipairs(ribbon.layers) do
				part.reveal = ribbon.reveal
				local share = #ribbon.layers == 1 and 1 or (layer == 1 and 0.45 + 0.55 * swing or 0.35 + 0.55 * (1 - swing))
				part.opacity = math.clamp(0.95 * glow * share, 0, 1)
				part.update(base, clock)
			end
		end
	end)

	-- a new tween replaces the one running (the end rolls the ribbons up even while they still open)
	local function unfold(ribbon, to, seconds)
		TweenService:Create(ribbon.opening, TweenInfo.new(seconds, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut),
			{ Value = to }):Play()
	end

	-- a falling star now and then, far away in front of the camera
	local function shootingStar()
		local r = rootPart()
		if not r then
			return
		end
		local view = camera.CFrame.LookVector
		local angle = math.atan2(view.Z, view.X) + (math.random() - 0.5) * 1.6
		local from = base + Vector3.new(math.cos(angle) * 240, 85 + math.random() * 30, math.sin(angle) * 240)
		local side = Vector3.new(-math.sin(angle), 0, math.cos(angle)) * (math.random() < 0.5 and -1 or 1)
		local to = from + side * 130 + Vector3.new(0, -45, 0)
		local head = anchorPart(Vector3.new(1, 1, 1))
		head.CFrame = CFrame.new(from)
		local a0, a1 = Instance.new("Attachment"), Instance.new("Attachment")
		a0.Position, a1.Position = Vector3.new(0, 1.2, 0), Vector3.new(0, -1.2, 0)
		a0.Parent, a1.Parent = head, head
		local trail = Instance.new("Trail")
		trail.Attachment0, trail.Attachment1 = a0, a1
		trail.Texture = A.Glow
		trail.LightEmission = 1
		trail.LightInfluence = 0
		trail.Brightness = 2
		trail.Lifetime = 0.5
		trail.WidthScale = NumberSequence.new(1, 0)
		trail.Transparency = NumberSequence.new(0, 1)
		trail.Color = ColorSequence.new(Color3.fromRGB(235, 250, 255), Color3.fromRGB(110, 255, 214))
		trail.Parent = head
		local spark = emitter(head, { Texture = A.StarTwinkle, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Speed = NumberRange.new(0), Size = seq(0, 6, 1, 6),
			Lifetime = NumberRange.new(0.35), LightEmission = 1, LightInfluence = 0, LockedToPart = true })
		spark.Rate = 20
		local move = TweenService:Create(head, TweenInfo.new(1.1, Enum.EasingStyle.Quad, Enum.EasingDirection.In), { CFrame = CFrame.new(to) })
		move:Play()
		move.Completed:Connect(function()
			spark.Rate = 0
			task.delay(0.8, function()
				head:Destroy()
			end)
		end)
	end
	local skyLoop = task.spawn(function()
		while alive do
			task.wait(speed > 1 and 4 + math.random() * 3 or 10 + math.random() * 7)
			if alive then
				shootingStar()
			end
		end
	end)

	-- the start (about 6 s): night falls (3 s), the stars come out, the ribbons unfold one by one, and a wave of
	-- light on the ground in front of the player sends a fountain of EXP orbs up into the aurora
	local function intro()
		setRates(0)
		task.delay(0.3, function()
			if alive then
				setRates(1)
			end
		end)
		for n, ribbon in ipairs(ribbons) do
			task.delay(0.6 + (n - 1) * 0.8, function()
				if alive then
					unfold(ribbon, 1, 2.8)
				end
			end)
		end
		local r = rootPart()
		if not r then
			return
		end
		local flat = Vector3.new(look.X, 0, look.Z)
		flat = flat.Magnitude > 0.01 and flat.Unit or Vector3.new(0, 0, -1)
		local target = r.Position + flat * 28
		local floor = groundY(target, r.Position.Y - 3)
		local spot = anchorPart(Vector3.new(12, 1, 12))
		spot.CFrame = CFrame.new(target.X, floor + 0.3, target.Z)
		local wave = emitter(spot, { Texture = A.Ring, Orientation = Enum.ParticleOrientation.VelocityPerpendicular,
			EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(0.01), Size = seq(0, 2, 1, 40),
			Transparency = seq(0, 0.1, 0.6, 0.35, 1, 1), Lifetime = NumberRange.new(1.6), LightEmission = 1, LightInfluence = 0 })
		task.wait(0.9)
		if not alive then
			spot:Destroy()
			return
		end
		wave:Emit(1)
		task.delay(0.4, function()
			wave:Emit(1)
		end)
		-- the fountain leans 25 degrees away from the player: nothing comes up to the camera
		local point = anchorPart(Vector3.new(10, 1, 10))
		point.CFrame = CFrame.new(target.X, floor + 0.5, target.Z) * CFrame.fromAxisAngle(Vector3.new(0, 1, 0):Cross(flat), math.rad(25))
		local fountain = emitter(point, { Texture = A.ExpOrb, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(12, 18), FlipbookStartRandom = true,
			Shape = Enum.ParticleEmitterShape.Disc, EmissionDirection = Enum.NormalId.Top, SpreadAngle = Vector2.new(12, 12),
			Speed = NumberRange.new(16, 26), Drag = 0.5, Lifetime = NumberRange.new(2.2, 2.8),
			Size = seq(0, 0, 0.1, 2.2, 0.8, 1.8, 1, 0), Transparency = seq(0, 0, 0.75, 0.1, 1, 1),
			RotSpeed = NumberRange.new(-30, 30), LightEmission = 0.8, LightInfluence = 0 })
		fountain.Rate = 26 * scale
		TweenService:Create(fountain, TweenInfo.new(1.8, Enum.EasingStyle.Quad, Enum.EasingDirection.In), { Rate = 0 }):Play()
		local sparkles = emitter(point, { Texture = A.StarTwinkle, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Shape = Enum.ParticleEmitterShape.Disc,
			EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(6, 20), Size = seq(0, 3, 1, 3),
			Lifetime = NumberRange.new(0.8, 1.2), LightEmission = 1, LightInfluence = 0 })
		sparkles.Rate = 20 * scale
		TweenService:Create(sparkles, TweenInfo.new(2), { Rate = 0 }):Play()
		task.wait(1.4)
		if not alive then
			spot:Destroy()
			point:Destroy()
			return
		end
		-- bright motes shoot from the wave up into the sky
		local motes = emitter(point, { Texture = A.Glow, Color = TEAL, EmissionDirection = Enum.NormalId.Top,
			SpreadAngle = Vector2.new(8, 8), Speed = NumberRange.new(60, 80), Lifetime = NumberRange.new(2.2, 2.6),
			Size = seq(0, 3.5, 1, 1.5), Transparency = seq(0, 0, 0.8, 0.2, 1, 1), LightEmission = 1, LightInfluence = 0 })
		motes:Emit(math.floor(8 * scale))
		local trailSparks = emitter(point, { Texture = A.StarTwinkle, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, EmissionDirection = Enum.NormalId.Top, SpreadAngle = Vector2.new(6, 6),
			Speed = NumberRange.new(40, 75), Size = seq(0, 4, 1, 4), Lifetime = NumberRange.new(1.4, 2), LightEmission = 1,
			LightInfluence = 0 })
		trailSparks:Emit(math.floor(16 * scale))
		task.delay(5, function()
			spot:Destroy()
			point:Destroy()
		end)
	end

	-- the last minute: the aurora brightens and waves faster, falling stars come more often
	local function final()
		speed = 1.8
		glow = 1.2
		setRates(1.5)
	end

	-- the end: the ribbons roll up, the stars go out, the day comes back
	local function stop()
		alive = false
		task.cancel(skyLoop)
		setRates(0)
		for _, ribbon in ipairs(ribbons) do
			unfold(ribbon, 0, 2)
		end
		restoreLight()
		dusk.stop(2.5)
		task.delay(2.6, function()
			stepping:Disconnect()
			follow:Disconnect()
			for _, ribbon in ipairs(ribbons) do
				for _, part in ipairs(ribbon.layers) do
					part.anchor:Destroy()
				end
				for _, part in ipairs(ribbon.glows) do
					part.anchor:Destroy()
				end
				ribbon.opening:Destroy()
			end
			starField:Destroy()
			for _, zone in ipairs(zones) do
				zone.ground:Destroy()
			end
		end)
	end

	setRates(1)
	-- a player who joins later sees the night and the aurora already there
	dusk.go(1, 0)
	for _, ribbon in ipairs(ribbons) do
		ribbon.opening.Value = 1
	end
	return {
		intro = function()
			dusk.go(0, 0)
			dusk.go(1, 3)
			for _, ribbon in ipairs(ribbons) do
				ribbon.opening.Value = 0
			end
			intro()
		end,
		final = final,
		stop = stop,
	}
end

-- ---------- Lucky Breeze (a luck boost) ----------

-- A rainbow far away over the horizon: a chain of beams along an arc standing upright (red outside; flip: red inside, the
-- second rainbow), across the view of the player at the start; it keeps its place around the player, like the sky
local function rainbowArc(def)
	local anchor = anchorPart(Vector3.new(1, 1, 1))
	anchor.CFrame = CFrame.new()
	local points, beams = {}, {}
	for i = 1, def.points do
		local attachment = Instance.new("Attachment")
		attachment.Parent = anchor
		points[i] = attachment
	end
	for i = 1, def.points - 1 do
		local beam = Instance.new("Beam")
		beam.Attachment0, beam.Attachment1 = points[i], points[i + 1]
		beam.Texture = def.texture
		beam.TextureMode = Enum.TextureMode.Stretch
		beam.LightEmission = def.emission or 0.55 -- partly added light: the colors stay bright on a blue sky
		beam.LightInfluence = 0
		beam.FaceCamera = false
		beam.Segments = 16
		beam.Transparency = NumberSequence.new(1)
		beam.Parent = anchor
		beams[i] = beam
	end
	-- reveal: how much of the arc is open (from its left foot); drain: how much is gone (the last minute, like an
	-- hourglass); blur: how much wider and softer; flash: a short brightening (a rare pet)
	local arc = { anchor = anchor, reveal = 0, drain = 0, blur = 0, flash = 0 }
	local step = (def.to - def.from) / (def.points - 1)
	local curve = 4 / 3 * math.tan(step / 4) * def.radius -- the beams follow the circle exactly
	local middle, side = Vector3.zero, Vector3.xAxis
	local function visible(s)
		local feet = math.clamp(math.sin(math.pi * s) / 0.45, 0, 1) -- the feet fade into the horizon
		local open = math.clamp((arc.reveal * 1.3 - s) / 0.3, 0, 1)
		local left = math.clamp((s - arc.drain) / 0.15, 0, 1)
		return feet * open * left
	end
	-- the point of the arc at s (0 its left foot, 1 its right one)
	function arc.at(s)
		local a = def.from + (def.to - def.from) * s
		return middle + (side * math.cos(a) + Vector3.yAxis * math.sin(a)) * def.radius
	end
	local shown = nil
	function arc.update(center)
		local state = string.format("%.1f %.1f %.1f %.3f %.3f %.3f %.3f", center.X, center.Y, center.Z, arc.reveal, arc.drain,
			arc.blur, arc.flash)
		if state == shown then
			return -- the player stands and nothing changes
		end
		shown = state
		local out = Vector3.new(math.cos(def.angle), 0, math.sin(def.angle))
		side = Vector3.new(-out.Z, 0, out.X)
		middle = center + out * def.distance + Vector3.new(0, -def.drop, 0) -- the circle's middle, under the horizon
		for k = 1, def.points do
			local a = def.from + step * (k - 1)
			local radial = side * math.cos(a) + Vector3.yAxis * math.sin(a)
			local along = -side * math.sin(a) + Vector3.yAxis * math.cos(a)
			points[k].CFrame = CFrame.fromMatrix(middle + radial * def.radius, along, def.flip and -radial or radial)
		end
		local strength = math.clamp(def.opacity * (1 - 0.55 * arc.blur) + def.opacity * 0.35 * arc.flash, 0, 1)
		for i, beam in ipairs(beams) do
			beam.CurveSize0, beam.CurveSize1 = curve, curve
			beam.Width0 = def.width * (1 + arc.blur)
			beam.Width1 = def.width * (1 + arc.blur)
			local s0, s1 = (i - 1) / (def.points - 1), i / (def.points - 1)
			beam.Transparency = NumberSequence.new(1 - visible(s0) * strength, 1 - visible(s1) * strength)
		end
	end
	return arc
end

-- A ribbon of wind: a bright wisp that flies along a path (path(t) is its place for t from 0 to 1) in `duration`
-- seconds, leaving a soft trail and shedding clover leaves and gold glints
local function windRibbon(path, duration, leafRate, A, C)
	local head = anchorPart(Vector3.new(1, 1, 1))
	head.CFrame = CFrame.new(path(0))
	local a0, a1 = Instance.new("Attachment"), Instance.new("Attachment")
	a0.Position, a1.Position = Vector3.new(0, 2.6, 0), Vector3.new(0, -2.6, 0)
	a0.Parent, a1.Parent = head, head
	local trail = Instance.new("Trail")
	trail.Attachment0, trail.Attachment1 = a0, a1
	trail.Texture = A.Wisp
	trail.TextureMode = Enum.TextureMode.Stretch
	trail.FaceCamera = true
	trail.LightEmission = 0.8
	trail.LightInfluence = 0
	trail.Brightness = 1.6
	trail.Lifetime = 1.1
	trail.WidthScale = seq(0, 1, 0.3, 0.8, 1, 0)
	trail.Transparency = seq(0, 0.05, 0.6, 0.35, 1, 1)
	trail.Color = ColorSequence.new(Color3.fromRGB(255, 250, 215), Color3.fromRGB(150, 255, 170))
	trail.Parent = head
	local leaves = emitter(head, { Texture = A.CloverTumble, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
		FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(10, 18), FlipbookStartRandom = true,
		Speed = NumberRange.new(2, 5), SpreadAngle = Vector2.new(180, 180), Lifetime = NumberRange.new(2, 3),
		Acceleration = Vector3.new(0, -3, 0), Drag = 0.6, Size = seq(0, 2.2, 1, 2.2), Transparency = seq(0, 0, 0.8, 0, 1, 1),
		RotSpeed = NumberRange.new(-140, 140), Brightness = 1.15, LightInfluence = 0.4 })
	leaves.Rate = leafRate
	local glints = emitter(head, { Texture = C.CoinGlint, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
		FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Speed = NumberRange.new(0.5, 2), SpreadAngle = Vector2.new(180, 180),
		Lifetime = NumberRange.new(0.7, 1), Size = seq(0, 1.4, 1, 1.4), LightEmission = 1, LightInfluence = 0 })
	glints.Rate = leafRate * 2
	local started = os.clock()
	local moving
	moving = RunService.RenderStepped:Connect(function()
		local t = (os.clock() - started) / duration
		if t >= 1 then
			moving:Disconnect()
			leaves.Rate, glints.Rate = 0, 0
			task.delay(3, function()
				head:Destroy()
			end)
			return
		end
		local here, ahead = path(t), path(math.min(t + 0.01, 1))
		head.CFrame = (ahead - here).Magnitude > 0.01 and CFrame.lookAt(here, ahead) or CFrame.new(here)
	end)
end

-- Points evenly over a sphere (for a burst in every direction)
local function sphereDirections(count)
	local directions = {}
	for i = 0, count - 1 do
		local y = 1 - (i + 0.5) / count * 2
		local r = math.sqrt(1 - y * y)
		local a = i * 2.39996 -- the golden angle
		table.insert(directions, Vector3.new(math.cos(a) * r, y, math.sin(a) * r))
	end
	return directions
end

animations.lucky_breeze = function()
	local A = Effects.Assets.lucky_breeze
	local C = Effects.Assets.coin_storm -- the gold glints, glow and ring: the same look as Coin Storm
	local S = Effects.Assets.aurora -- its twinkling stars sparkle along the rainbow
	local light = quality == "light"
	local scale = amount()
	local alive = true
	local windy = 1 -- the last minute: the gusts come more often

	-- the golden hour: the sun goes low and warm, the air turns gold (the game's own clock, for this player only)
	local mood = skyMood({ clock = 16.9,
		air = { Color = Color3.fromRGB(255, 222, 160), Decay = Color3.fromRGB(255, 172, 95), Haze = 1.3, Glare = 0.55 } })
	local restoreLight = lightEffects(light
		and { ColorCorrectionEffect = { TintColor = Color3.fromRGB(255, 248, 232), Saturation = 0.12 } }
		or { ColorCorrectionEffect = { TintColor = Color3.fromRGB(255, 246, 228), Brightness = 0.02, Saturation = 0.15 },
			BloomEffect = { Intensity = 0.15, Size = 28, Threshold = 2.2 } })

	-- the rainbows: in front of the camera at the start, low enough to be on the screen of the usual camera; a second,
	-- fainter one outside it with its colors the other way round, and a soft glow around the first (not on phones)
	local look = camera.CFrame.LookVector
	local front = math.atan2(look.Z, look.X)
	local function arcDef(extra)
		local def = { angle = front, distance = 420, drop = 160, radius = 262, from = math.rad(28), to = math.rad(152),
			width = 30, opacity = 0.7, points = light and 9 or 13, texture = A.Rainbow }
		for key, value in pairs(extra) do
			def[key] = value
		end
		return def
	end
	local arcs = { rainbowArc(arcDef({})) }
	if not light then
		table.insert(arcs, rainbowArc(arcDef({ radius = 318, from = math.rad(32), to = math.rad(148), width = 24,
			opacity = 0.3, flip = true })))
		table.insert(arcs, rainbowArc(arcDef({ width = 90, opacity = 0.16, emission = 1 })))
	end
	local rainbow = arcs[1]
	-- one value per key: a new tween replaces the one running (the end fades even while the start still opens)
	local values = {}
	local function tweenArcs(key, to, seconds, style)
		local value = values[key]
		if not value then
			value = Instance.new("NumberValue")
			value.Value = rainbow[key]
			value.Changed:Connect(function(v)
				for _, arc in ipairs(arcs) do
					arc[key] = v
				end
			end)
			values[key] = value
		end
		TweenService:Create(value, TweenInfo.new(seconds, style or Enum.EasingStyle.Sine), { Value = to }):Play()
	end

	-- golden rays of sun come down from the clouds far away
	local shaftHolder = anchorPart(Vector3.new(1, 1, 1))
	shaftHolder.CFrame = CFrame.new()
	local shafts = {}
	for n, offset in ipairs(light and { 0.2 } or { -0.55, 0.2, 0.75 }) do
		local top, bottom = Instance.new("Attachment"), Instance.new("Attachment")
		top.Parent, bottom.Parent = shaftHolder, shaftHolder
		local beam = Instance.new("Beam")
		beam.Attachment0, beam.Attachment1 = top, bottom
		beam.Texture = A.LightShafts
		beam.TextureMode = Enum.TextureMode.Stretch
		beam.FaceCamera = true
		beam.LightEmission = 1
		beam.LightInfluence = 0
		beam.Width0, beam.Width1 = 60, 110
		beam.Transparency = NumberSequence.new(1)
		beam.Parent = shaftHolder
		table.insert(shafts, { top = top, bottom = bottom, beam = beam, angle = front + offset, distance = 250 + n * 25 })
	end
	local shine = 0 -- how much the rays show (they come with the golden hour)

	-- glitter floats in the air above the eggs' chances, carried slowly by the wind
	local rings = light and { { radius = 34, zones = 4, size = 20, height = 17 } }
		or { { radius = 34, zones = 5, size = 20, height = 17 }, { radius = 58, zones = 7, size = 26, height = 24 } }
	local motes = {}
	local zones, follow = followRing(rings, function(ring)
		local sky = anchorPart(Vector3.new(ring.size, 8, ring.size))
		local glitter = emitter(sky, { Texture = C.CoinGlint, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Shape = Enum.ParticleEmitterShape.Box,
			Speed = NumberRange.new(0.3, 1), SpreadAngle = Vector2.new(180, 180), Acceleration = Vector3.new(0.6, 0.3, 0),
			Lifetime = NumberRange.new(2.5, 4), Size = seq(0, 1, 1, 1), LightEmission = 1, LightInfluence = 0 })
		table.insert(motes, glitter)
		return { sky = sky }
	end)
	local function setGlitter(factor)
		for _, glitter in ipairs(motes) do
			glitter.Rate = 2.5 * scale * factor
		end
	end

	-- the sky follows the player (like a real sky far away); the rainbow twinkles here and there
	local root = rootPart()
	local base = root and root.Position or camera.CFrame.Position
	local twinkle = anchorPart(Vector3.new(1, 1, 1))
	local twinkles = emitter(twinkle, { Texture = S.StarTwinkle, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
		FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Speed = NumberRange.new(0), Lifetime = NumberRange.new(0.9, 1.4),
		Size = seq(0, 9, 1, 9), Rotation = NumberRange.new(-20, 20), LightEmission = 1, LightInfluence = 0, Brightness = 1.6 })
	local pen = anchorPart(Vector3.new(6, 6, 6)) -- the sparkles that paint the rainbow while it opens
	local penSparks = emitter(pen, { Texture = C.CoinGlint, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
		FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Shape = Enum.ParticleEmitterShape.Sphere,
		Speed = NumberRange.new(2, 6), SpreadAngle = Vector2.new(180, 180), Acceleration = Vector3.new(0, -8, 0),
		Lifetime = NumberRange.new(0.8, 1.4), Size = seq(0, 9, 1, 6), LightEmission = 1, LightInfluence = 0 })
	local clock, waiting, nextTwinkle = 0, 0, 0
	local stepping = RunService.Heartbeat:Connect(function(dt)
		clock = clock + dt
		waiting = waiting + dt
		if waiting < 1 / 30 then
			return
		end
		waiting = math.min(waiting - 1 / 30, 1 / 30)
		local r = rootPart()
		if r then
			local y = base.Y + (r.Position.Y - base.Y) * math.min(1, dt * 1.5)
			base = Vector3.new(r.Position.X, y, r.Position.Z)
		end
		for _, arc in ipairs(arcs) do
			arc.update(base)
		end
		for n, shaft in ipairs(shafts) do
			local out = Vector3.new(math.cos(shaft.angle), 0, math.sin(shaft.angle))
			local side = Vector3.new(-out.Z, 0, out.X)
			shaft.top.WorldPosition = base + out * shaft.distance + Vector3.new(0, 190, 0)
			shaft.bottom.WorldPosition = base + out * shaft.distance + side * 45 + Vector3.new(0, -12, 0)
			local breathe = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(clock * 0.35 + n * 2))
			shaft.beam.Transparency = NumberSequence.new(1 - 0.32 * shine * breathe)
		end
		pen.CFrame = CFrame.new(rainbow.at(math.clamp(rainbow.reveal * 1.3 - 0.15, 0, 1)))
		if alive and rainbow.reveal > 0.95 and clock >= nextTwinkle then
			nextTwinkle = clock + (light and 0.5 or 0.25)
			local s = rainbow.drain + math.random() * (1 - rainbow.drain)
			twinkle.CFrame = CFrame.new(rainbow.at(math.clamp(s, 0.08, 0.92)))
			twinkles:Emit(1)
		end
	end)
	local shining = Instance.new("NumberValue") -- one value: a new tween replaces the one running
	shining.Changed:Connect(function(v)
		shine = v
	end)
	local function shineTo(to, seconds)
		TweenService:Create(shining, TweenInfo.new(seconds), { Value = to }):Play()
	end

	-- the view at this moment: where the camera looks (flat) and its side, from the player
	local function view()
		local direction = camera.CFrame.LookVector
		local flat = Vector3.new(direction.X, 0, direction.Z)
		flat = flat.Magnitude > 0.01 and flat.Unit or Vector3.new(0, 0, -1)
		return flat, Vector3.new(-flat.Z, 0, flat.X)
	end

	-- a gust of wind: ribbons of wind with a stream of clover leaves fly across the view, far in front of the player and
	-- higher than the eggs' chances (they never cover them), from one side to the other (never toward the camera)
	local function gust(ribbons, leafCount)
		local r = rootPart()
		if not r then
			return
		end
		local flat, side = view()
		side = side * (math.random() < 0.5 and 1 or -1)
		local origin = r.Position
		for n = 1, ribbons do
			local distance = 40 + math.random() * 22
			local height = 16 + math.random() * 10 + (n - 1) * 5
			local phase, loopAt = math.random(), 0.3 + math.random() * 0.4
			windRibbon(function(t)
				local p = origin + flat * (distance + 10 * math.sin(2 * math.pi * (0.9 * t + phase)))
					+ side * ((t - 0.5) * 170) + Vector3.new(0, height + 5 * math.sin(2 * math.pi * (1.3 * t + phase)), 0)
				local loop = math.clamp((t - loopAt) / 0.18, 0, 1) -- a curl of the wind
				if loop > 0 and loop < 1 then
					local a = 2 * math.pi * loop
					p = p + side * (7 * math.sin(a)) + Vector3.new(0, 7 * (1 - math.cos(a)), 0)
				end
				return p
			end, 4.2 + math.random(), (light and 7 or 12), A, C)
			task.wait(0.35)
		end
		-- the stream of leaves under the ribbons
		local distance = 44 + math.random() * 16
		local start = origin + flat * distance - side * 80 + Vector3.new(0, 15 + math.random() * 6, 0)
		local part = anchorPart(Vector3.new(36, 8, 1)) -- 36 deep along the view, 8 high; its front looks across
		part.CFrame = CFrame.lookAt(start, start + side)
		local leaves = emitter(part, { Texture = A.CloverTumble, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(10, 18), FlipbookStartRandom = true,
			Shape = Enum.ParticleEmitterShape.Box, EmissionDirection = Enum.NormalId.Front, Speed = NumberRange.new(30, 40),
			SpreadAngle = Vector2.new(4, 10), Acceleration = Vector3.new(0, -1.2, 0), Lifetime = NumberRange.new(4.2, 5),
			Size = seq(0, 3.4, 1, 3.4), Transparency = seq(0, 1, 0.08, 0, 0.85, 0, 1, 1), Rotation = NumberRange.new(0, 360),
			RotSpeed = NumberRange.new(-140, 140), Brightness = 1.15, LightInfluence = 0.4 })
		local streaks = emitter(part, { Texture = A.WindStreak, Orientation = Enum.ParticleOrientation.VelocityParallel,
			Shape = Enum.ParticleEmitterShape.Box, EmissionDirection = Enum.NormalId.Front, Speed = NumberRange.new(48, 60),
			SpreadAngle = Vector2.new(2, 4), Lifetime = NumberRange.new(2.4, 3), Size = seq(0, 4, 1, 4),
			Rotation = NumberRange.new(90), Transparency = seq(0, 1, 0.2, 0.45, 0.8, 0.45, 1, 1), LightEmission = 0.6,
			LightInfluence = 0 })
		local blow = 1.6 -- the leaves come over 1.6 s: a stream, not a wall
		leaves.Rate = math.max(1, leafCount * scale) / blow
		streaks.Rate = math.max(1, leafCount * 0.4 * scale) / blow
		task.delay(blow, function()
			leaves.Rate, streaks.Rate = 0, 0
		end)
		task.delay(blow + 6, function()
			part:Destroy()
		end)
	end
	local windLoop = task.spawn(function()
		while alive do
			task.wait((5 + math.random() * 3) / windy)
			if alive then
				task.spawn(gust, light and 1 or 2, 8 + math.random(0, 5))
			end
		end
	end)

	-- the eggs: a gold glow at each egg and a little clover turning above its chances (never in front of the chances:
	-- the glints rise only along the lower half of the egg)
	local decorated = {}
	local owner = tostring(math.random(1, 1e9)) -- marks this animation's things on the stands
	local function removeOwn(stand)
		for _, thing in ipairs(stand:GetDescendants()) do
			if (thing.Name == "LuckGlow" or thing.Name == "LuckClover") and thing:GetAttribute("LuckOwner") == owner then
				thing:Destroy()
			end
		end
	end
	local function decorate(stand)
		if not alive or decorated[stand] or not stand:IsA("Model") then
			return
		end
		local primary = stand.PrimaryPart
		if not primary then
			return
		end
		removeOwn(stand) -- a stand that streamed out and back still has the old ones
		for _, thing in ipairs(stand:GetDescendants()) do
			if thing.Name == "LuckGlow" then
				return -- another Lucky Breeze (a preview during the event) already decorates it
			end
		end
		local made = {}
		decorated[stand] = made
		local width = math.max(primary.Size.X, primary.Size.Z)
		local glow = Instance.new("Part")
		glow.Name = "LuckGlow"
		glow:SetAttribute("LuckOwner", owner)
		glow.Anchored, glow.CanCollide, glow.CanQuery, glow.CanTouch = true, false, false, false
		glow.CastShadow = false
		glow.Transparency = 1
		glow.Size = Vector3.new(width * 0.9, primary.Size.Y * 0.45, width * 0.9)
		glow.CFrame = CFrame.new(primary.Position - Vector3.new(0, primary.Size.Y * 0.2, 0))
		glow.Parent = stand
		made.glints = emitter(glow, { Texture = C.CoinGlint, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Shape = Enum.ParticleEmitterShape.Box,
			EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(0.3, 0.7), Lifetime = NumberRange.new(1, 1.4),
			Size = seq(0, 1.1, 1, 1.1), LightEmission = 1, LightInfluence = 0 })
		made.glints.Rate = 6 * scale
		-- a soft gold light behind the egg (only as high as the egg: the chances above stay clear)
		made.halo = emitter(glow, { Texture = C.GoldDust, Speed = NumberRange.new(0), Lifetime = NumberRange.new(1.6),
			Size = seq(0, width * 1.1, 0.5, width * 1.25, 1, width * 1.1), Transparency = seq(0, 1, 0.3, 0.45, 0.7, 0.45, 1, 1),
			LightEmission = 1, LightInfluence = 0, ZOffset = -2, LockedToPart = true })
		made.halo.Rate = 1.2
		made.ring = emitter(glow, { Texture = C.GoldRing, Orientation = Enum.ParticleOrientation.VelocityPerpendicular,
			EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(0.01), Lifetime = NumberRange.new(2.2),
			Size = seq(0, width * 0.5, 1, width * 1.3), Transparency = seq(0, 1, 0.3, 0.55, 1, 1), LightEmission = 1,
			LightInfluence = 0 })
		made.ring.Rate = 0.5
		if not light then
			made.light = Instance.new("PointLight")
			made.light.Color = Color3.fromRGB(255, 205, 110)
			made.light.Brightness = 0
			made.light.Range = 8 + width
			made.light.Parent = glow
			TweenService:Create(made.light, TweenInfo.new(1.5), { Brightness = 1.2 }):Play()
		end
		made.glow = glow
		-- the clover over the chances: on the same point as the chances (it stays still while the egg floats)
		local info = primary:FindFirstChild("EggInfo")
		local holder, top = primary, primary.Position + Vector3.new(0, primary.Size.Y / 2 + 2, 0)
		if info and info:IsA("BillboardGui") then
			local adornee = info.Adornee or primary
			local at = adornee:IsA("Attachment") and adornee.WorldPosition or adornee.Position
			holder = adornee:IsA("Attachment") and adornee.Parent or adornee
			top = at + info.StudsOffsetWorldSpace + Vector3.new(0, info.Size.Y.Scale / 2 + 1.6, 0)
		end
		local point = Instance.new("Attachment")
		point.Name = "LuckClover"
		point:SetAttribute("LuckOwner", owner)
		point.Parent = holder
		point.WorldPosition = top
		local board = Instance.new("BillboardGui")
		board.Size = UDim2.fromScale(3.2, 3.2)
		board.LightInfluence = 0
		board.MaxDistance = info and info:IsA("BillboardGui") and info.MaxDistance or 70 -- seen as far as the chances
		board.Parent = point
		local image = Instance.new("ImageLabel")
		image.BackgroundTransparency = 1
		image.Size = UDim2.fromScale(1, 1)
		image.Image = A.CloverTurn
		image.ImageRectSize = Vector2.new(256, 256)
		image.ImageTransparency = 1
		image.Parent = board
		TweenService:Create(image, TweenInfo.new(1.5), { ImageTransparency = 0 }):Play()
		made.point, made.image, made.frame = point, image, math.random(0, 15)
	end
	local stands = nil
	local watchers = {}
	local function watchStands(found)
		stands = found
		for _, stand in ipairs(found:GetChildren()) do
			decorate(stand)
		end
		table.insert(watchers, found.ChildAdded:Connect(function(stand)
			task.defer(decorate, stand) -- the stand is complete when it arrives
		end))
		table.insert(watchers, found.ChildRemoved:Connect(function(stand)
			decorated[stand] = nil
		end))
	end
	if Workspace:FindFirstChild("DiscordEggStands") then
		watchStands(Workspace.DiscordEggStands)
	else
		table.insert(watchers, Workspace.ChildAdded:Connect(function(child)
			if child.Name == "DiscordEggStands" and not stands then
				watchStands(child)
			end
		end))
	end
	-- the clovers turn (16 frames, 12 a second); so does the big clover of the start
	local turned, lastFrame = 0, -1
	local spinning = {} -- [image] = first frame
	local turning = RunService.Heartbeat:Connect(function(dt)
		turned = turned + dt * 12
		if math.floor(turned) == lastFrame and not next(spinning) then
			return -- the same frame as before
		end
		lastFrame = math.floor(turned)
		for _, made in pairs(decorated) do
			local frame = (math.floor(turned) + made.frame) % 16
			made.image.ImageRectOffset = Vector2.new(frame % 4 * 256, math.floor(frame / 4) * 256)
		end
		for image, first in pairs(spinning) do
			local frame = (math.floor(turned * 1.3) + first) % 16
			image.ImageRectOffset = Vector2.new(frame % 4 * 256, math.floor(frame / 4) * 256)
		end
	end)

	-- leaves and glints burst from a point to all sides (each point of a part looks one way: a real burst)
	local function burst(where, count, speed)
		local part = anchorPart(Vector3.new(1, 1, 1))
		part.CFrame = CFrame.new(where)
		for _, direction in ipairs(sphereDirections(count)) do
			local point = Instance.new("Attachment")
			point.CFrame = CFrame.lookAt(Vector3.zero, direction)
			point.Parent = part
			emitter(point, { Texture = A.CloverTumble, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
				FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(14, 22),
				FlipbookStartRandom = true, EmissionDirection = Enum.NormalId.Front, Speed = NumberRange.new(speed * 0.85, speed),
				Drag = 1.3, SpreadAngle = Vector2.new(8, 8), Acceleration = Vector3.new(0, -4, 0), Lifetime = NumberRange.new(2, 2.6),
				Size = seq(0, 1.5, 0.15, 3, 1, 2.6), Transparency = seq(0, 0, 0.75, 0, 1, 1), RotSpeed = NumberRange.new(-160, 160),
				Brightness = 1.2, LightInfluence = 0.3 }):Emit(1)
			emitter(point, { Texture = C.CoinGlint, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
				FlipbookMode = Enum.ParticleFlipbookMode.OneShot, EmissionDirection = Enum.NormalId.Front,
				Speed = NumberRange.new(speed * 0.6, speed * 0.9), Drag = 1.5, Lifetime = NumberRange.new(1, 1.4),
				Size = seq(0, 2.4, 1, 2.4), LightEmission = 1, LightInfluence = 0 }):Emit(1)
		end
		task.delay(3, function()
			part:Destroy()
		end)
	end

	-- a rare pet from an egg (on this player's screen): a ring of clovers bursts around the egg, a pillar of gold light
	-- rises behind it, the rainbow shines
	local function hatch(eggId)
		local r = rootPart()
		if not r or not alive then
			return
		end
		local stand = stands and eggId ~= nil and stands:FindFirstChild("DiscordEgg_" .. tostring(eggId))
		if not stand and stands then -- no number (an older server): the nearest egg
			local best = 30
			for _, other in ipairs(stands:GetChildren()) do
				local primary = other:IsA("Model") and other.PrimaryPart
				if primary and (primary.Position - r.Position).Magnitude < best then
					stand, best = other, (primary.Position - r.Position).Magnitude
				end
			end
		end
		local where = stand and stand.PrimaryPart and stand.PrimaryPart.Position or r.Position
		local part = anchorPart(Vector3.new(1, 1, 1))
		part.CFrame = CFrame.new(where)
		local away = (where - camera.CFrame.Position) * Vector3.new(1, 0, 1)
		away = away.Magnitude > 0.01 and away.Unit or Vector3.zAxis
		local count = light and 12 or 20
		for i = 1, count do -- each point looks outward from the egg: a ring around it, open toward the camera
			local point = Instance.new("Attachment")
			point.CFrame = CFrame.lookAt(Vector3.zero, away) * CFrame.Angles(0, math.rad(-110 + 220 * (i - 1) / (count - 1)), 0)
			point.Parent = part
			emitter(point, { Texture = A.CloverTumble, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
				FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(14, 22),
				FlipbookStartRandom = true, EmissionDirection = Enum.NormalId.Front, Speed = NumberRange.new(12, 14), Drag = 2,
				SpreadAngle = Vector2.new(0, 6), Acceleration = Vector3.new(0, 1.5, 0), Lifetime = NumberRange.new(1.5, 1.9),
				Size = seq(0, 0.6, 0.15, 1.3, 1, 1.1), Transparency = seq(0, 0, 0.75, 0, 1, 1),
				RotSpeed = NumberRange.new(-160, 160), Brightness = 1.2, LightInfluence = 0.3 }):Emit(1)
			emitter(point, { Texture = C.CoinGlint, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
				FlipbookMode = Enum.ParticleFlipbookMode.OneShot, EmissionDirection = Enum.NormalId.Front,
				Speed = NumberRange.new(9, 12), Drag = 2, Lifetime = NumberRange.new(0.9, 1.2), Size = seq(0, 1.2, 1, 1.2),
				LightEmission = 1, LightInfluence = 0 }):Emit(1)
		end
		local floor = groundY(where, where.Y - 3)
		local spot = anchorPart(Vector3.new(4, 1, 4))
		spot.CFrame = CFrame.new(where.X, floor + 0.3, where.Z)
		local wave = emitter(spot, { Texture = C.GoldRing, Orientation = Enum.ParticleOrientation.VelocityPerpendicular,
			EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(0.01), Size = seq(0, 1, 1, 14),
			Transparency = seq(0, 0.1, 1, 1), Lifetime = NumberRange.new(1.1), LightEmission = 1, LightInfluence = 0 })
		wave:Emit(1)
		-- a soft pillar of gold behind the egg, only up to the egg's top (the chances above stay on their own background)
		local top = stand and stand.PrimaryPart and stand.PrimaryPart.Position.Y + stand.PrimaryPart.Size.Y / 2 or where.Y + 2
		local foot = Vector3.new(where.X, floor, where.Z) + away * 2
		local low, high = Instance.new("Attachment"), Instance.new("Attachment")
		low.Parent, high.Parent = spot, spot
		low.WorldPosition, high.WorldPosition = foot, Vector3.new(foot.X, top, foot.Z)
		local pillar = Instance.new("Beam")
		pillar.Attachment0, pillar.Attachment1 = low, high
		pillar.Texture = A.LightShafts
		pillar.FaceCamera = true
		pillar.LightEmission = 1
		pillar.LightInfluence = 0
		pillar.Width0, pillar.Width1 = 7, 3
		pillar.Color = ColorSequence.new(Color3.fromRGB(255, 225, 140))
		pillar.Parent = spot
		pillar.Transparency = NumberSequence.new(1)
		local lit = Instance.new("NumberValue") -- in over 0.4 s, out over 1.4 s: a glow, never a flash
		lit.Changed:Connect(function(v)
			pillar.Transparency = NumberSequence.new(1 - v * 0.75, 1 - v * 0.2)
		end)
		local rise = TweenService:Create(lit, TweenInfo.new(0.4, Enum.EasingStyle.Sine), { Value = 1 })
		rise.Completed:Connect(function()
			TweenService:Create(lit, TweenInfo.new(1.4, Enum.EasingStyle.Sine), { Value = 0 }):Play()
		end)
		rise:Play()
		tweenArcs("flash", 1, 0.5)
		task.delay(0.5, function()
			tweenArcs("flash", 0, 2)
		end)
		task.delay(3, function()
			part:Destroy()
			spot:Destroy()
			lit:Destroy()
		end)
	end

	-- the start (about 7 s): the golden hour comes, ribbons of wind whirl leaves into a big turning clover in the sky,
	-- it bursts into leaves and glints, and a brush of sparkles paints the rainbow over the horizon
	local function intro()
		local r = rootPart()
		if not r then -- no character yet: the golden hour and the rainbow come without the show
			mood.go(1, 3)
			shineTo(1, 4)
			tweenArcs("reveal", 1, 2.8)
			return
		end
		local flat, side = view()
		local center = r.Position + flat * 58 + Vector3.new(0, 13, 0) -- in the upper half of the usual camera's view
		for n = 1, light and 2 or 3 do
			local start = 2 * math.pi * n / 3
			windRibbon(function(t)
				local a = start + 2 * math.pi * 2.2 * t
				local radius = 22 * (1 - t) ^ 0.8 + 2
				return center + side * (math.cos(a) * radius) + Vector3.new(0, math.sin(a) * radius * 0.75, 0)
					+ flat * (math.sin(a * 0.5) * 4)
			end, 1.9, light and 10 or 18, A, C)
		end
		task.wait(1.4)
		if not alive then
			return
		end
		-- the big clover grows out of the whirl, turns and shines
		local holder = anchorPart(Vector3.new(12, 12, 12))
		holder.CFrame = CFrame.new(center)
		local board = Instance.new("BillboardGui")
		board.Size = UDim2.fromScale(0.5, 0.5)
		board.LightInfluence = 0
		board.Brightness = 1.4
		board.MaxDistance = 1000
		board.Parent = holder
		local image = Instance.new("ImageLabel")
		image.BackgroundTransparency = 1
		image.Size = UDim2.fromScale(1, 1)
		image.Image = A.CloverTurn
		image.ImageRectSize = Vector2.new(256, 256)
		image.Parent = board
		spinning[image] = 0
		local glow = emitter(holder, { Texture = C.GoldDust, Speed = NumberRange.new(0), Lifetime = NumberRange.new(1),
			Size = seq(0, 24, 1, 28), Transparency = seq(0, 0.6, 0.5, 0.35, 1, 1), LightEmission = 1, LightInfluence = 0,
			ZOffset = -2, LockedToPart = true })
		glow.Rate = 4
		local sparkle = emitter(holder, { Texture = C.CoinGlint, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Shape = Enum.ParticleEmitterShape.Sphere,
			Speed = NumberRange.new(0.5, 2), Lifetime = NumberRange.new(0.6, 1), Size = seq(0, 2.2, 1, 2.2), LightEmission = 1,
			LightInfluence = 0 })
		sparkle.Rate = 40 * scale
		TweenService:Create(board, TweenInfo.new(1.1, Enum.EasingStyle.Back, Enum.EasingDirection.Out),
			{ Size = UDim2.fromScale(14, 14) }):Play()
		mood.go(1, 3)
		shineTo(1, 4)
		task.wait(1.7)
		spinning[image] = nil
		if not alive then
			holder:Destroy()
			return
		end
		-- the burst
		glow.Rate, sparkle.Rate = 0, 0
		TweenService:Create(board, TweenInfo.new(0.3), { Size = UDim2.fromScale(24, 24) }):Play()
		TweenService:Create(image, TweenInfo.new(0.3), { ImageTransparency = 1 }):Play()
		burst(center, light and 20 or 40, 30)
		local wave = emitter(holder, { Texture = C.GoldRing, Speed = NumberRange.new(0), Size = seq(0, 4, 1, 56),
			Transparency = seq(0, 0.2, 1, 1), Lifetime = NumberRange.new(0.9), LightEmission = 1, LightInfluence = 0 })
		wave:Emit(1)
		task.delay(3, function()
			holder:Destroy()
		end)
		task.wait(0.3)
		if not alive then
			return
		end
		-- the rainbow is painted from its left foot to its right one
		penSparks.Rate = 70 * scale
		tweenArcs("reveal", 1, 2.8)
		task.delay(2.8, function()
			penSparks.Rate = 0
		end)
		task.wait(0.6)
		if alive then
			gust(light and 1 or 2, 18)
		end
	end

	-- the last minute: the rainbow runs out like an hourglass, wider and softer, and the wind blows more often
	local function final(secondsLeft)
		local seconds = math.max(5, (tonumber(secondsLeft) or 60) - 3)
		tweenArcs("drain", 0.85, seconds, Enum.EasingStyle.Linear)
		tweenArcs("blur", 0.6, seconds, Enum.EasingStyle.Linear)
		windy = 1.6
	end

	-- the end: a last gust takes the leaves, the rainbow, the rays and the gold fade, the afternoon comes back
	local function stop()
		alive = false
		task.cancel(windLoop)
		task.spawn(gust, light and 1 or 2, 14)
		tweenArcs("reveal", 0, 2)
		shineTo(0, 2)
		setGlitter(0)
		penSparks.Rate = 0
		for _, made in pairs(decorated) do
			made.glints.Rate, made.ring.Rate, made.halo.Rate = 0, 0, 0
			TweenService:Create(made.image, TweenInfo.new(1.5), { ImageTransparency = 1 }):Play()
			if made.light then
				TweenService:Create(made.light, TweenInfo.new(1.5), { Brightness = 0 }):Play()
			end
		end
		restoreLight()
		mood.stop(2.5)
		task.delay(2.6, function()
			stepping:Disconnect()
			turning:Disconnect()
			follow:Disconnect()
			for _, connection in ipairs(watchers) do
				connection:Disconnect()
			end
			for _, made in pairs(decorated) do
				made.glow:Destroy()
				made.point:Destroy()
			end
			if stands then
				for _, stand in ipairs(stands:GetChildren()) do
					removeOwn(stand)
				end
			end
			for _, value in pairs(values) do
				value:Destroy()
			end
			shining:Destroy()
			for _, arc in ipairs(arcs) do
				arc.anchor:Destroy()
			end
			for _, zone in ipairs(zones) do
				zone.sky:Destroy()
			end
			shaftHolder:Destroy()
			twinkle:Destroy()
			pen:Destroy()
		end)
	end

	-- a player who joins later sees the golden hour and the rainbow already there
	setGlitter(1)
	mood.go(1, 0)
	shine = 1
	for _, arc in ipairs(arcs) do
		arc.reveal = 1
	end
	return {
		intro = function()
			mood.go(0, 0)
			shine = 0
			for _, arc in ipairs(arcs) do
				arc.reveal = 0
			end
			intro()
		end,
		final = final,
		stop = stop,
		hatch = hatch,
	}
end

-- ---------- Meteor Shower (a big currency or a big event) ----------

animations.meteor_shower = function()
	local A = Effects.Assets.meteor_shower
	local S = Effects.Assets.aurora -- its twinkling stars: the stars of the dusk and the sparkles of the crystals
	local L = Effects.Assets.lucky_breeze -- its streak of wind: the tiny shooting stars
	local light = quality == "light"
	local scale = amount()
	local alive = true
	local rainbow = false -- the last minute: the trails in the colors of the rainbow
	local busy = 1 -- the last minute: more meteors
	local preview = previewing

	-- the dusk: a violet evening with the first stars (the game's own clock, for this player only)
	local mood = skyMood({ clock = 20.3, clearSky = true,
		air = { Color = Color3.fromRGB(96, 74, 160), Decay = Color3.fromRGB(150, 92, 210), Haze = 0.6, Glare = 0,
			hazeDown = true } })
	local restoreLight = lightEffects(light
		and { ColorCorrectionEffect = { TintColor = Color3.fromRGB(232, 224, 255), Saturation = 0.08 } }
		or { ColorCorrectionEffect = { TintColor = Color3.fromRGB(226, 218, 255), Contrast = 0.05, Saturation = 0.1 },
			BloomEffect = { Intensity = 0.18, Size = 28, Threshold = 2.2 } })

	-- the stars, high above (they twinkle in and out)
	local starField = anchorPart(Vector3.new(560, 150, 560))
	local stars = emitter(starField, { Texture = S.StarTwinkle, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
		FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Shape = Enum.ParticleEmitterShape.Box,
		Speed = NumberRange.new(0), Size = seq(0, 6, 1, 6), Lifetime = NumberRange.new(2.5, 4.5),
		Rotation = NumberRange.new(-20, 20), LightEmission = 1, LightInfluence = 0, Brightness = 2 })
	-- tiny shooting stars rain all the time far above, all one way (a real shower comes from one point of the sky)
	local look = camera.CFrame.LookVector
	local front = math.atan2(look.Z, look.X)
	local flatLook = Vector3.new(look.X, 0, look.Z)
	flatLook = flatLook.Magnitude > 0.01 and flatLook.Unit or Vector3.new(0, 0, -1)
	local rainWay = (Vector3.new(-flatLook.Z, 0, flatLook.X) + Vector3.new(0, -0.45, 0)).Unit
	local rainField = anchorPart(Vector3.new(480, 50, 480))
	local rain = emitter(rainField, { Texture = L.WindStreak, Orientation = Enum.ParticleOrientation.VelocityParallel,
		Shape = Enum.ParticleEmitterShape.Box, EmissionDirection = Enum.NormalId.Front, Speed = NumberRange.new(130, 170),
		Lifetime = NumberRange.new(0.5, 0.8), Size = seq(0, 14, 1, 14), Rotation = NumberRange.new(90),
		Transparency = seq(0, 1, 0.15, 0.2, 0.8, 0.3, 1, 1), LightEmission = 1, LightInfluence = 0,
		Color = ColorSequence.new(Color3.fromRGB(255, 255, 255), Color3.fromRGB(180, 160, 255)) })
	local function setRain(factor)
		rain.Rate = (light and 3 or 8) * factor
	end
	-- pictures far away in the sky: a ringed planet that rises over the horizon and an arch of big glowing clouds of
	-- nebula across the sky, like the Milky Way. Each is a flat part with the picture on it, turned to the camera every
	-- frame: drawn in 3D, so it drifts smoothly (a BillboardGui moves by whole pixels and jumps when slow). They keep
	-- their place around the player like a sky and are far behind everything in the game.
	local skyPictures = {}
	local me = {} -- this animation, as the owner of the sky
	local function skyPicture(image, size, angle, elevation, distance, transparency, brightness)
		local holder = anchorPart(Vector3.new(size, size, 0.05))
		local board = Instance.new("SurfaceGui")
		board.Face = Enum.NormalId.Front
		board.SizingMode = Enum.SurfaceGuiSizingMode.FixedSize
		board.CanvasSize = Vector2.new(512, 512)
		board.LightInfluence = 0
		board.Brightness = brightness or 1
		board.MaxDistance = 100000
		board.Parent = holder
		local picture = Instance.new("ImageLabel")
		picture.BackgroundTransparency = 1
		picture.Size = UDim2.fromScale(1, 1)
		picture.Image = image
		picture.ImageTransparency = 1
		picture.Parent = board
		local item = { holder = holder, picture = picture, angle = angle, elevation = elevation, distance = distance,
			shown = transparency, drift = (math.random() - 0.5) * 0.004 }
		table.insert(skyPictures, item)
		return item
	end
	-- near the middle of the view at the start (a phone held upright sees only a narrow part of the sky); the clouds'
	-- glowing middles stand over the horizon, behind the paths of the meteors (those stay closer than 330 studs), and
	-- not farther than about 370 studs: the air of the game hides parts farther away
	local planet = nil
	local function buildSky()
		meteorSkyOwner = me
		local arch = light and { { -0.55, 20, 1 }, { 0, 28, 2 }, { 0.6, 22, 1 } }
			or { { -1.3, 17, 2 }, { -0.8, 22, 1 }, { -0.3, 28, 2 }, { 0.2, 31, 1 }, { 0.7, 26, 2 }, { 1.2, 19, 1 } }
		for n, cloud in ipairs(arch) do -- offset from the view, height in degrees, which picture
			skyPicture(A.NebulaCloud[cloud[3]], 250 + (n % 2) * 40, front + cloud[1], math.rad(cloud[2]), 352 + n * 3, 0.05, 2.2)
		end
		-- the planet: in front of the clouds (closer), right of the middle (the game's HUD is mostly left)
		planet = skyPicture(A.Planet, 112, front + 0.2, math.rad(11), 300, 0)
	end
	if not meteorSkyOwner then
		buildSky()
	end
	local function showPictures(seconds)
		for _, item in ipairs(skyPictures) do
			TweenService:Create(item.picture, TweenInfo.new(seconds, Enum.EasingStyle.Sine), { ImageTransparency = item.shown }):Play()
		end
	end
	local function hideSkyPictures(seconds)
		for _, item in ipairs(skyPictures) do
			TweenService:Create(item.picture, TweenInfo.new(seconds, Enum.EasingStyle.Sine), { ImageTransparency = 1 }):Play()
		end
	end
	local root = rootPart()
	local base = root and root.Position or camera.CFrame.Position
	-- every frame, right before the picture is drawn: the sky moves smoothly (the planet rising, the drift)
	local following = RunService.RenderStepped:Connect(function(dt)
		local r = rootPart()
		if r then
			base = r.Position
		end
		starField.CFrame = CFrame.new(base + Vector3.new(0, 140, 0))
		local middle = base + Vector3.new(0, 95, 0)
		rainField.CFrame = CFrame.lookAt(middle, middle + rainWay)
		if alive and not meteorSkyOwner and #skyPictures == 0 then -- the other one's sky went away: this one shows it now
			buildSky()
			showPictures(2)
		end
		local eye = camera.CFrame.Position
		for _, item in ipairs(skyPictures) do
			item.angle = item.angle + item.drift * dt
			local flat = Vector3.new(math.cos(item.angle), 0, math.sin(item.angle))
			local at = base + flat * item.distance + Vector3.new(0, math.tan(item.elevation) * item.distance, 0)
			item.holder.CFrame = CFrame.lookAt(at, Vector3.new(eye.X, at.Y, eye.Z)) -- upright, its face to the camera
		end
	end)

	local WHITE_VIOLET = ColorSequence.new({ ColorSequenceKeypoint.new(0, Color3.fromRGB(255, 255, 255)),
		ColorSequenceKeypoint.new(0.35, Color3.fromRGB(190, 160, 255)), ColorSequenceKeypoint.new(1, Color3.fromRGB(110, 150, 255)) })
	local function trailColors()
		if not rainbow then
			return WHITE_VIOLET
		end
		local start = math.random()
		local points = {}
		for i = 0, 5 do
			table.insert(points, ColorSequenceKeypoint.new(i / 5, Color3.fromHSV((start + i / 6) % 1, 0.55, 1)))
		end
		return ColorSequence.new(points)
	end

	-- the view at this moment: where the camera looks (flat) and its side
	local function view()
		local direction = camera.CFrame.LookVector
		local flat = Vector3.new(direction.X, 0, direction.Z)
		flat = flat.Magnitude > 0.01 and flat.Unit or Vector3.new(0, 0, -1)
		return flat, Vector3.new(-flat.Z, 0, flat.X)
	end

	-- a meteor: a white-hot head with a long trail and falling sparks, from one point to another in `seconds`;
	-- breakAt (0..1): it breaks up into dust on the way; done(point) is called where it ends
	-- gentle: a meteor that comes close (a smaller glow and a softer core: never a flash on the screen)
	local function meteor(from, to, seconds, size, trailSeconds, done, breakAt, gentle)
		local head = anchorPart(Vector3.new(1, 1, 1))
		head.CFrame = CFrame.lookAt(from, to)
		local core = emitter(head, { Texture = A.MeteorCore, LockedToPart = true, Speed = NumberRange.new(0),
			Lifetime = NumberRange.new(0.12), Size = seq(0, size, 1, size), LightEmission = 1, LightInfluence = 0,
			Brightness = gentle and 1.1 or 2 })
		core.Rate = gentle and 30 or 60
		local glow = size * (gentle and 1.5 or 3)
		local aura = emitter(head, { Texture = A.MeteorCore, LockedToPart = true, Speed = NumberRange.new(0),
			Lifetime = NumberRange.new(0.2), Size = seq(0, glow, 1, glow), Transparency = seq(0, gentle and 0.8 or 0.55, 1, gentle and 0.8 or 0.55),
			LightEmission = 1, LightInfluence = 0, Color = ColorSequence.new(Color3.fromRGB(175, 150, 255)) })
		aura.Rate = gentle and 15 or 30
		local g0, g1 = Instance.new("Attachment"), Instance.new("Attachment")
		g0.Position, g1.Position = Vector3.new(0, size * 1.3, 0), Vector3.new(0, -size * 1.3, 0)
		g0.Parent, g1.Parent = head, head
		local halo = Instance.new("Trail")
		halo.Attachment0, halo.Attachment1 = g0, g1
		halo.Texture = A.MeteorTrail
		halo.TextureMode = Enum.TextureMode.Stretch
		halo.FaceCamera = true
		halo.LightEmission = 1
		halo.LightInfluence = 0
		halo.Lifetime = trailSeconds * 0.7
		halo.WidthScale = seq(0, 1, 1, 0.1)
		halo.Transparency = seq(0, 0.72, 1, 1)
		halo.Color = ColorSequence.new(Color3.fromRGB(160, 120, 255), Color3.fromRGB(90, 130, 255))
		halo.Parent = head
		local a0, a1 = Instance.new("Attachment"), Instance.new("Attachment")
		a0.Position, a1.Position = Vector3.new(0, size * 0.45, 0), Vector3.new(0, -size * 0.45, 0)
		a0.Parent, a1.Parent = head, head
		local trail = Instance.new("Trail")
		trail.Attachment0, trail.Attachment1 = a0, a1
		trail.Texture = A.MeteorTrail
		trail.TextureMode = Enum.TextureMode.Stretch
		trail.FaceCamera = true
		trail.LightEmission = 1
		trail.LightInfluence = 0
		trail.Brightness = 2
		trail.Lifetime = trailSeconds
		trail.WidthScale = seq(0, 1, 0.4, 0.55, 1, 0)
		trail.Transparency = seq(0, 0, 0.5, 0.35, 1, 1)
		trail.Color = trailColors()
		trail.Parent = head
		local sparks = emitter(head, { Texture = S.StarTwinkle, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Speed = NumberRange.new(2, 7), SpreadAngle = Vector2.new(180, 180),
			Acceleration = Vector3.new(0, -6, 0), Lifetime = NumberRange.new(0.6, 1.2), Size = seq(0, size * 0.3, 1, size * 0.15),
			LightEmission = 1, LightInfluence = 0 })
		sparks.Rate = light and 15 or 35
		local move = TweenService:Create(head, TweenInfo.new(seconds, Enum.EasingStyle.Linear), { CFrame = CFrame.lookAt(to, to + (to - from)) })
		move:Play()
		local function finish(point)
			core.Rate, sparks.Rate, aura.Rate = 0, 0, 0
			task.delay(trailSeconds + 0.5, function()
				head:Destroy()
			end)
			if done and alive then -- after the end a meteor only fades: no new impact
				done(point)
			end
		end
		if breakAt then
			task.delay(seconds * breakAt, function()
				move:Cancel()
				local point = head.Position
				-- the meteor breaks up: a cloud of glowing dust and a spray of sparks
				local dust = emitter(head, { Texture = A.Dust, Color = ColorSequence.new(Color3.fromRGB(190, 170, 255)),
					Speed = NumberRange.new(4, 10), SpreadAngle = Vector2.new(180, 180), Drag = 1, Lifetime = NumberRange.new(2, 3),
					Size = seq(0, size * 0.8, 1, size * 2.6), Transparency = seq(0, 0.3, 1, 1), Rotation = NumberRange.new(0, 360),
					LightEmission = 0.6, LightInfluence = 0 })
				dust:Emit(light and 5 or 10)
				local spray = emitter(head, { Texture = S.StarTwinkle, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
					FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Speed = NumberRange.new(14, 30), SpreadAngle = Vector2.new(180, 180),
					Drag = 1.5, Acceleration = Vector3.new(0, -10, 0), Lifetime = NumberRange.new(1, 1.8),
					Size = seq(0, size * 0.35, 1, size * 0.2), LightEmission = 1, LightInfluence = 0 })
				spray:Emit(light and 20 or 45)
				finish(point)
			end)
		else
			move.Completed:Connect(function(state)
				if state == Enum.PlaybackState.Completed then
					finish(to)
				end
			end)
		end
	end

	-- where a meteor lands far away: a pillar of light with crystals rising in it, a ring and a cloud of dust
	local function impact(point, near)
		local floor = groundY(point + Vector3.new(0, 40, 0), base.Y - 8)
		local ground = Vector3.new(point.X, floor, point.Z)
		local spot = anchorPart(Vector3.new(6, 1, 6))
		spot.CFrame = CFrame.new(ground + Vector3.new(0, 0.5, 0))
		local big = near and 1 or 2.2 -- far away everything is bigger, so it still shows
		local wave = emitter(spot, { Texture = A.ShockRing, Orientation = Enum.ParticleOrientation.VelocityPerpendicular,
			EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(0.01), Size = seq(0, 3, 1, 26 * big),
			Transparency = seq(0, 0, 1, 1), Lifetime = NumberRange.new(1.2), LightEmission = 1, LightInfluence = 0,
			Color = ColorSequence.new(Color3.fromRGB(205, 180, 255)) })
		wave:Emit(1)
		task.delay(0.25, function()
			wave:Emit(1)
		end)
		local crystals = emitter(spot, { Texture = A.CrystalTumble, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(12, 20), FlipbookStartRandom = true,
			EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(near and 24 or 30, near and 38 or 46),
			SpreadAngle = Vector2.new(near and 28 or 22, near and 28 or 22), Acceleration = Vector3.new(0, -50, 0),
			Lifetime = NumberRange.new(1.6, 2.2), Size = seq(0, 1.6 * big, 1, 1.4 * big), RotSpeed = NumberRange.new(-120, 120),
			Brightness = 1.3, LightInfluence = 0.2 })
		crystals:Emit(math.floor((near and 30 or 14) * scale))
		local glints = emitter(spot, { Texture = S.StarTwinkle, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, EmissionDirection = Enum.NormalId.Top,
			Speed = NumberRange.new(10, 30), SpreadAngle = Vector2.new(50, 50), Acceleration = Vector3.new(0, -20, 0),
			Lifetime = NumberRange.new(0.8, 1.4), Size = seq(0, 1.6 * big, 1, 1.6 * big), LightEmission = 1, LightInfluence = 0 })
		glints:Emit(math.floor((near and 40 or 20) * scale))
		local dust = emitter(spot, { Texture = A.Dust, Color = ColorSequence.new(Color3.fromRGB(170, 150, 225)),
			EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(2, 6), SpreadAngle = Vector2.new(70, 70), Drag = 0.8,
			Lifetime = NumberRange.new(2, 3), Size = seq(0, 4 * big, 1, 12 * big), Transparency = seq(0, 0.4, 1, 1),
			Rotation = NumberRange.new(0, 360), LightEmission = 0.3, LightInfluence = 0.5 })
		dust:Emit(light and 4 or 8)
		-- the pillar of light (it comes in softly: no flash) with crystals floating up in it
		local low, high = Instance.new("Attachment"), Instance.new("Attachment")
		low.Parent, high.Parent = spot, spot
		low.WorldPosition, high.WorldPosition = ground, ground + Vector3.new(0, near and 30 or 70, 0)
		local pillar = Instance.new("Beam")
		pillar.Attachment0, pillar.Attachment1 = low, high
		pillar.Texture = A.MeteorTrail -- a white core with blue and violet edges: a bright column of light
		pillar.TextureMode = Enum.TextureMode.Stretch
		pillar.FaceCamera = true
		pillar.LightEmission = 1
		pillar.LightInfluence = 0
		pillar.Brightness = 2.5
		pillar.Width0, pillar.Width1 = 6 * big, 2.5 * big
		pillar.Transparency = NumberSequence.new(1)
		pillar.Parent = spot
		local floating = emitter(spot, { Texture = A.CrystalTumble, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(8, 12), FlipbookStartRandom = true,
			Shape = Enum.ParticleEmitterShape.Disc, EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(3, 6),
			Lifetime = NumberRange.new(2.5, 3.5), Size = seq(0, 0, 0.2, 1.2 * big, 0.8, 1.2 * big, 1, 0), LightInfluence = 0.2,
			Brightness = 1.2 })
		floating.Rate = (light and 3 or 6) * (near and 1 or 0.8)
		local lit = Instance.new("NumberValue")
		lit.Changed:Connect(function(v)
			pillar.Transparency = seq(0, 1 - v * 0.9, 0.6, 1 - v * 0.55, 1, 1)
		end)
		-- the ground where it fell glows (a soft light growing and fading, never a flash of the screen)
		local glow = emitter(spot, { Texture = A.MeteorCore, Speed = NumberRange.new(0), Lifetime = NumberRange.new(1.8),
			Size = seq(0, 6 * big, 0.4, 20 * big, 1, 24 * big), Transparency = seq(0, 1, 0.4, 0.4, 1, 1),
			LightEmission = 1, LightInfluence = 0, Color = ColorSequence.new(Color3.fromRGB(205, 185, 255)) })
		glow:Emit(1)
		local rise = TweenService:Create(lit, TweenInfo.new(0.5, Enum.EasingStyle.Sine), { Value = 1 })
		rise:Play()
		task.delay(3.2, function()
			floating.Rate = 0
			TweenService:Create(lit, TweenInfo.new(1.6, Enum.EasingStyle.Sine), { Value = 0 }):Play()
		end)
		task.delay(7, function()
			spot:Destroy()
			lit:Destroy()
		end)
	end

	-- a cluster of crystals grows out of the ground, shines and pulses, then shatters into a fountain of crystals
	local function crystalCluster(ground, height, life)
		local holder = anchorPart(Vector3.new(1, 1, 1))
		holder.CFrame = CFrame.new(ground)
		local point = Instance.new("Attachment")
		point.Parent = holder
		local board = Instance.new("BillboardGui")
		board.Size = UDim2.fromScale(height, 0)
		board.SizeOffset = Vector2.new(0, 0.5) -- it grows up from the ground
		board.LightInfluence = 0
		board.Brightness = 1.3
		board.MaxDistance = 1000
		board.Parent = point
		local picture = Instance.new("ImageLabel")
		picture.BackgroundTransparency = 1
		picture.Size = UDim2.fromScale(1, 1)
		picture.Image = A.CrystalCluster
		picture.Parent = board
		TweenService:Create(board, TweenInfo.new(0.7, Enum.EasingStyle.Back, Enum.EasingDirection.Out),
			{ Size = UDim2.fromScale(height, height) }):Play()
		local shine = emitter(holder, { Texture = S.StarTwinkle, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Shape = Enum.ParticleEmitterShape.Box, Speed = NumberRange.new(0.5),
			Lifetime = NumberRange.new(0.6, 0.9), Size = seq(0, height * 0.18, 1, height * 0.18), LightEmission = 1,
			LightInfluence = 0 })
		holder.Size = Vector3.new(height * 0.6, height * 0.8, height * 0.6)
		holder.CFrame = CFrame.new(ground + Vector3.new(0, height * 0.4, 0))
		point.WorldPosition = ground
		shine.Rate = 8
		local aura = emitter(holder, { Texture = A.MeteorCore, Speed = NumberRange.new(0), Lifetime = NumberRange.new(1.2),
			Size = seq(0, height * 1.1, 0.5, height * 1.4, 1, height * 1.1), Transparency = seq(0, 1, 0.4, 0.6, 1, 1),
			LightEmission = 1, LightInfluence = 0, ZOffset = -2, LockedToPart = true,
			Color = ColorSequence.new(Color3.fromRGB(170, 140, 255)) })
		aura.Rate = 2
		task.delay(life, function()
			shine.Rate, aura.Rate = 0, 0
			TweenService:Create(board, TweenInfo.new(0.25), { Size = UDim2.fromScale(height * 1.15, height * 1.15) }):Play()
			TweenService:Create(picture, TweenInfo.new(0.25), { ImageTransparency = 1 }):Play()
			local shards = emitter(holder, { Texture = A.CrystalTumble, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
				FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(14, 22), FlipbookStartRandom = true,
				Shape = Enum.ParticleEmitterShape.Box, EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(14, 26),
				SpreadAngle = Vector2.new(55, 55), Acceleration = Vector3.new(0, -40, 0), Lifetime = NumberRange.new(1.4, 2),
				Size = seq(0, height * 0.12, 1, height * 0.1), RotSpeed = NumberRange.new(-160, 160), Brightness = 1.3,
				LightInfluence = 0.2 })
			shards:Emit(math.floor(26 * scale))
			local glints = emitter(holder, { Texture = S.StarTwinkle, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
				FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Shape = Enum.ParticleEmitterShape.Box,
				Speed = NumberRange.new(8, 20), SpreadAngle = Vector2.new(180, 180), Drag = 1.5, Lifetime = NumberRange.new(0.8, 1.3),
				Size = seq(0, height * 0.15, 1, height * 0.1), LightEmission = 1, LightInfluence = 0 })
			glints:Emit(math.floor(30 * scale))
			task.delay(2.5, function()
				holder:Destroy()
			end)
		end)
	end

	-- a meteor of the shower: across the sky (it fades away over the horizon) or down far away (an impact)
	local function shootingMeteor(kind)
		local r = rootPart()
		if not r then
			return
		end
		local flat, side = view()
		local turn = (math.random() - 0.5) * 1.6 -- somewhere in front, never from behind the camera
		local ahead = (flat * math.cos(turn) + side * math.sin(turn)).Unit
		local across = Vector3.new(-ahead.Z, 0, ahead.X) * (math.random() < 0.5 and 1 or -1)
		if kind == "far" then
			local distance = 120 + math.random() * 70
			local point = r.Position + ahead * distance
			local from = point - across * (90 + math.random() * 60) + ahead * 30 + Vector3.new(0, 70 + math.random() * 30, 0)
			meteor(from, point, 1.3 + math.random() * 0.4, 12, 0.9, function(at)
				impact(at, false)
				if not light then
					local floor = groundY(at + Vector3.new(0, 40, 0), base.Y - 8)
					crystalCluster(Vector3.new(at.X, floor, at.Z), 22, 3.5)
				end
			end)
		else
			local distance = 190 + math.random() * 60
			-- low enough to cross the upper part of the usual camera's view, in front of the nebulae
			local from = r.Position + ahead * distance - across * 150 + Vector3.new(0, 50 + math.random() * 25, 0)
			local to = r.Position + ahead * (distance + 40) + across * 150 + Vector3.new(0, 5 + math.random() * 20, 0)
			meteor(from, to, 1.4 + math.random() * 0.6, 11 + math.random() * 4, 0.8)
		end
	end

	-- the treat: now and then a meteor falls closer (about 40 studs in front) and bursts into a fountain of crystals
	local function nearMeteor()
		local r = rootPart()
		if not r then
			return
		end
		local flat, side = view()
		local across = side * (math.random() < 0.5 and 1 or -1)
		local point = r.Position + flat * 42
		local from = point - across * 140 + flat * 25 + Vector3.new(0, 70, 0) -- from the side and above, not at the camera
		meteor(from, point, 1.5, 14, 1.1, function(at)
			impact(at, true)
			local floor = groundY(at + Vector3.new(0, 40, 0), base.Y - 8)
			crystalCluster(Vector3.new(at.X, floor, at.Z), 11, 5)
		end, nil, true)
	end

	local skyLoop = task.spawn(function()
		local nextNear = os.clock() + (preview and 5 or 20 + math.random() * 10) -- a short preview shows it soon
		while alive do
			task.wait((3 + math.random() * 3) / busy)
			if not alive then
				break
			end
			if os.clock() >= nextNear then
				nextNear = os.clock() + 150 + math.random() * 90
				nearMeteor()
			else
				shootingMeteor(math.random() < 0.4 and "far" or "sky")
				if not light and math.random() < 0.35 then -- now and then a few together, like a real shower
					for _ = 1, math.random(2, 4) do
						task.wait(0.15 + math.random() * 0.25)
						shootingMeteor("sky")
					end
				end
			end
		end
	end)

	-- the start: the dusk comes, one big meteor crosses the whole sky with two small ones and sinks behind the
	-- horizon, which glows where it fell
	local function intro()
		stars.Rate = 0
		setRain(0)
		mood.go(1, 2.5)
		showPictures(4)
		-- the planet rises over the horizon
		if planet then
			local rising = Instance.new("NumberValue")
			rising.Value = math.rad(-12)
			rising.Changed:Connect(function(v)
				planet.elevation = v
			end)
			local rise = TweenService:Create(rising, TweenInfo.new(5, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
				{ Value = math.rad(11) })
			rise.Completed:Connect(function()
				rising:Destroy()
			end)
			rise:Play()
		end
		task.delay(0.8, function()
			if alive then
				stars.Rate = light and 15 or 35
				setRain(busy)
			end
		end)
		task.wait(1)
		local r = rootPart()
		if not alive or not r then
			return
		end
		local flat, side = view()
		local from = r.Position + flat * 200 - side * 230 + Vector3.new(0, 75, 0)
		local to = r.Position + flat * 300 + side * 240 + Vector3.new(0, -25, 0)
		-- halfway the big meteor bursts into a fan of meteors that streak down to the horizon
		task.delay(1.9, function()
			if not alive then
				return
			end
			local at = from + (to - from) * (1.9 / 3.4)
			for n = 1, light and 4 or 8 do
				local spread = (n - 0.5) / (light and 4 or 8) - 0.5
				local target = at + flat * 40 + side * (spread * 360) + Vector3.new(0, -110 - math.random() * 25, 0)
				task.delay(math.random() * 0.25, function()
					if alive then
						meteor(at, target, 1.6 + math.random() * 0.6, 12, 1.3)
					end
				end)
			end
			local flash = anchorPart(Vector3.new(1, 1, 1)) -- a soft round glow where it bursts (it grows, no flash)
			flash.CFrame = CFrame.new(at)
			local bloom = emitter(flash, { Texture = A.MeteorCore, Speed = NumberRange.new(0), Lifetime = NumberRange.new(1.6),
				Size = seq(0, 20, 0.3, 90, 1, 110), Transparency = seq(0, 0.5, 0.3, 0.45, 1, 1), LightEmission = 1,
				LightInfluence = 0, Color = ColorSequence.new(Color3.fromRGB(210, 185, 255)) })
			bloom:Emit(1)
			local ring = emitter(flash, { Texture = A.ShockRing, Speed = NumberRange.new(0), Lifetime = NumberRange.new(1.3),
				Size = seq(0, 10, 1, 160), Transparency = seq(0, 0.2, 1, 1), LightEmission = 1, LightInfluence = 0,
				Color = ColorSequence.new(Color3.fromRGB(205, 180, 255)) })
			ring:Emit(1)
			task.delay(2, function()
				flash:Destroy()
			end)
		end)
		meteor(from, to, 3.4, 55, 2.4, function(at)
			-- the horizon glows where it went down
			local glow = anchorPart(Vector3.new(1, 1, 1))
			glow.CFrame = CFrame.new(at + Vector3.new(0, 25, 0))
			local flare = emitter(glow, { Texture = A.MeteorCore, Speed = NumberRange.new(0), Lifetime = NumberRange.new(2.6),
				Size = seq(0, 40, 0.3, 150, 1, 170), Transparency = seq(0, 0.6, 0.3, 0.5, 1, 1), LightEmission = 1,
				LightInfluence = 0, Color = ColorSequence.new(Color3.fromRGB(200, 170, 255)) })
			flare:Emit(1)
			task.delay(3, function()
				glow:Destroy()
			end)
		end)
		if not light then
			for n, offset in ipairs({ 0.5, 0.9 }) do
				task.delay(offset, function()
					if alive then
						local lift = Vector3.new(0, 25 * n, 0)
						meteor(from - side * 40 + lift, to - side * 20 + lift, 3, 9, 1.2)
					end
				end)
			end
		end
	end

	-- the last minute: more meteors, their trails in the colors of the rainbow
	local function final()
		busy = 2
		rainbow = true
		setRain(2)
	end

	-- the end: a last meteor breaks up in the sky into dust, the stars fade, the evening goes back to the game's day
	local function stop()
		alive = false
		task.cancel(skyLoop)
		if meteorSkyOwner == me then
			meteorSkyOwner = nil
		end
		local r = rootPart()
		if r then
			local flat, side = view()
			meteor(r.Position + flat * 200 - side * 160 + Vector3.new(0, 80, 0), r.Position + flat * 260 + side * 160
				+ Vector3.new(0, 30, 0), 1.6, 14, 1, nil, 0.55)
		end
		stars.Rate = 0
		setRain(0)
		hideSkyPictures(2.2)
		restoreLight()
		mood.stop(2.5)
		task.delay(3.5, function()
			following:Disconnect()
			starField:Destroy()
			rainField:Destroy()
			for _, item in ipairs(skyPictures) do
				item.holder:Destroy()
			end
		end)
	end

	-- a player who joins later sees the dusk, the stars, the nebulae and the planet already there
	stars.Rate = light and 15 or 35
	setRain(1)
	mood.go(1, 0)
	showPictures(2)
	return {
		intro = function()
			mood.go(0, 0)
			for _, item in ipairs(skyPictures) do
				item.picture.ImageTransparency = 1
			end
			intro()
		end,
		final = final,
		stop = stop,
	}
end

-- ---------- Sakura Festival ("everything x2", a weekend event) ----------

-- A picture far away in the sky on a flat part turned to the camera every frame (placeBoards): drawn in 3D, so it moves
-- smoothly (a BillboardGui moves by whole pixels). Keep it closer than about 350 studs: the air hides parts farther away.
local function skyBoard(list, image, width, height, place)
	local holder = anchorPart(Vector3.new(width, height, 0.05))
	local board = Instance.new("SurfaceGui")
	board.Face = Enum.NormalId.Front
	board.SizingMode = Enum.SurfaceGuiSizingMode.FixedSize
	board.CanvasSize = Vector2.new(512, math.max(64, math.floor(512 * height / width)))
	board.LightInfluence = 0
	board.Brightness = place.brightness or 1
	board.MaxDistance = 100000
	board.Parent = holder
	local picture = Instance.new("ImageLabel")
	picture.BackgroundTransparency = 1
	picture.Size = UDim2.fromScale(1, 1)
	picture.Image = image
	picture.ImageTransparency = 1
	picture.Parent = board
	-- place: angle (around the player), distance, lift (height over the player's feet), shown (its transparency), drift
	local item = { holder = holder, picture = picture, angle = place.angle, distance = place.distance, lift = place.lift,
		shown = place.shown or 0, drift = place.drift or 0 }
	table.insert(list, item)
	return item
end

local function placeBoards(list, base, dt)
	local eye = camera.CFrame.Position
	for _, item in ipairs(list) do
		item.angle = item.angle + item.drift * dt
		local at = base + Vector3.new(math.cos(item.angle), 0, math.sin(item.angle)) * item.distance + Vector3.new(0, item.lift, 0)
		item.holder.CFrame = CFrame.lookAt(at, Vector3.new(eye.X, at.Y, eye.Z)) -- upright, its face to the camera
	end
end

local function fadeBoards(list, show, seconds)
	for _, item in ipairs(list) do
		if not item.onString then -- a lantern on a string comes and goes with its string
			TweenService:Create(item.picture, TweenInfo.new(seconds, Enum.EasingStyle.Sine),
				{ ImageTransparency = show and item.shown or 1 }):Play()
		end
	end
end

animations.sakura_festival = function()
	local A = Effects.Assets.sakura_festival
	local C = Effects.Assets.coin_storm -- its gold glints sparkle around the lanterns and the blossom
	local light = quality == "light"
	local scale = amount()
	local alive = true

	-- a warm pink sunset (the game's own clock, for this player only)
	local mood = skyMood({ clock = 17.9,
		air = { Color = Color3.fromRGB(255, 188, 200), Decay = Color3.fromRGB(255, 140, 175), Haze = 1.25, Glare = 0.45 } })
	local restoreLight = lightEffects(light
		and { ColorCorrectionEffect = { TintColor = Color3.fromRGB(255, 240, 246), Saturation = 0.12 } }
		or { ColorCorrectionEffect = { TintColor = Color3.fromRGB(255, 236, 244), Brightness = 0.01, Saturation = 0.15 },
			BloomEffect = { Intensity = 0.16, Size = 28, Threshold = 2.2 } })

	-- the sky: cherry trees in bloom all around the horizon, pink mist between them, a pale moon over it all
	local look = camera.CFrame.LookVector
	local front = math.atan2(look.Z, look.X)
	local boards = {}
	local trees = light and 4 or 8
	for n = 1, trees do
		local size = 150 + (n % 3) * 25
		skyBoard(boards, A.SakuraTree, size, size, { angle = front + (n - 0.5) / trees * 2 * math.pi + (n % 2) * 0.15,
			distance = 290 + (n % 3) * 20, lift = size * 0.42 - 22, shown = 0.08, brightness = 1.1 })
	end
	for n, offset in ipairs(light and { 0 } or { -0.9, 0, 0.9, math.pi }) do
		skyBoard(boards, A.Mist, 520, 130, { angle = front + offset, distance = 270 + n * 6, lift = 6, shown = 0.25,
			brightness = 1.2 })
	end
	skyBoard(boards, A.Moon, 80, 80, { angle = front - 0.32, distance = 330, lift = 105, shown = 0, brightness = 1.3,
		drift = 0.002 })
	-- far behind the trees a snowy mountain; between them a pagoda and a red torii gate standing on the horizon
	skyBoard(boards, A.Mountain, 600, 300, { angle = front + 0.08, distance = 345, lift = 88, shown = 0.05, brightness = 1.05 })
	skyBoard(boards, A.Torii, 70, 70, { angle = front - 0.42, distance = 215, lift = 16, shown = 0, brightness = 1.15 })
	if not light then
		skyBoard(boards, A.Pagoda, 120, 120, { angle = front + 0.52, distance = 255, lift = 40, shown = 0, brightness = 1.1 })
	end

	-- strings of paper lanterns hang across the sky above the map, swaying and flickering
	local strings = {}
	for n, offset in ipairs(light and { 0.1 } or { -0.65, 0.12, 0.85 }) do
		local angle = front + offset
		local out = Vector3.new(math.cos(angle), 0, math.sin(angle))
		local side = Vector3.new(-out.Z, 0, out.X)
		local distance, span, count = 95 + n * 12, 64, light and 6 or 8
		local line = { items = {}, beams = {}, hooks = {}, phase = n * 1.7 }
		local holder = anchorPart(Vector3.new(1, 1, 1))
		holder.CFrame = CFrame.new()
		line.holder = holder
		for k = 0, count + 1 do
			local hook = Instance.new("Attachment")
			hook.Parent = holder
			line.hooks[k] = hook
			if k > 0 then
				local beam = Instance.new("Beam")
				beam.Attachment0, beam.Attachment1 = line.hooks[k - 1], hook
				beam.Width0, beam.Width1 = 0.18, 0.18
				beam.Color = ColorSequence.new(Color3.fromRGB(60, 35, 45))
				beam.LightInfluence = 1
				beam.FaceCamera = true
				beam.Transparency = NumberSequence.new(1)
				beam.Parent = holder
				table.insert(line.beams, beam)
			end
		end
		for k = 1, count do
			local t = k / (count + 1)
			local spot = out * distance + side * ((t - 0.5) * span)
			local item = skyBoard(boards, A.Lantern, 4.2, 4.2, { angle = math.atan2(spot.Z, spot.X), distance = spot.Magnitude,
				lift = 0, shown = 0, brightness = 1.7 })
			item.picture.ImageRectSize = Vector2.new(256, 256)
			item.lanternT, item.frame, item.onString = t, math.random(0, 15), true
			table.insert(line.items, item)
		end
		line.out, line.side, line.distance, line.span, line.count = out, side, distance, span, count
		table.insert(strings, line)
	end
	local function updateStrings(base, clock)
		for _, line in ipairs(strings) do
			local sway = math.sin(clock * 0.9 + line.phase) * 0.8
			for k = 0, line.count + 1 do
				local t = k / (line.count + 1)
				local sag = 9 * (1 - (2 * t - 1) ^ 2)
				line.hooks[k].WorldPosition = base + line.out * (line.distance + sway * (1 - (2 * t - 1) ^ 2))
					+ line.side * ((t - 0.5) * line.span) + Vector3.new(0, 40 - sag, 0)
				local item = line.items[k]
				if item then
					item.lift = 40 - sag - 2.6 + math.sin(clock * 1.6 + k + line.phase) * 0.25
					local frame = (math.floor(clock * 8) + item.frame) % 16
					item.picture.ImageRectOffset = Vector2.new(frame % 4 * 256, math.floor(frame / 4) * 256)
				end
			end
		end
	end
	local function showStrings(seen, seconds)
		for _, line in ipairs(strings) do
			for _, beam in ipairs(line.beams) do
				beam.Transparency = NumberSequence.new(seen and 0.15 or 1)
			end
			for _, item in ipairs(line.items) do
				TweenService:Create(item.picture, TweenInfo.new(seconds or 0.6), { ImageTransparency = seen and 0 or 1 }):Play()
			end
		end
	end

	-- lanterns rise slowly far away all around the map, swaying and flickering
	local rings = light and { { radius = 85, zones = 4, size = 22 }, { radius = 150, zones = 4, size = 40 } }
		or { { radius = 70, zones = 5, size = 18 }, { radius = 115, zones = 7, size = 30 }, { radius = 170, zones = 6, size = 45 } }
	local lanterns, petals = {}, {}
	local zones, follow = followRing(rings, function(ring)
		local ground = anchorPart(Vector3.new(ring.size, 1, ring.size))
		local far = ring.radius / 70
		local lantern = emitter(ground, { Texture = A.Lantern, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(6, 10), FlipbookStartRandom = true,
			Shape = Enum.ParticleEmitterShape.Box, EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(2.5, 4),
			SpreadAngle = Vector2.new(8, 8), Acceleration = Vector3.new(0.4, 0.25, 0), Lifetime = NumberRange.new(16, 20),
			Size = seq(0, 0, 0.04, 2.6 * far, 1, 2.2 * far), Transparency = seq(0, 1, 0.05, 0, 0.85, 0, 1, 1),
			Rotation = NumberRange.new(-8, 8), RotSpeed = NumberRange.new(-6, 6), LightEmission = 0.7, LightInfluence = 0,
			Brightness = 1.6 })
		table.insert(lanterns, lantern)
		return { ground = ground }
	end)
	-- petals fall gently in a ring around the player (like light snow; none near the camera)
	local petalRings = light and { { radius = 36, zones = 5, size = 26, height = 26 } }
		or { { radius = 34, zones = 6, size = 24, height = 26 }, { radius = 56, zones = 8, size = 34, height = 30 } }
	local petalZones, petalFollow = followRing(petalRings, function(ring)
		local sky = anchorPart(Vector3.new(ring.size, 2, ring.size))
		local fall = emitter(sky, { Texture = A.PetalTumble, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(8, 14), FlipbookStartRandom = true,
			Shape = Enum.ParticleEmitterShape.Box, EmissionDirection = Enum.NormalId.Bottom, Speed = NumberRange.new(2.5, 3.5),
			Acceleration = Vector3.new(0.35, -0.3, 0.2), Drag = 0.2, Lifetime = NumberRange.new(6, 7.5),
			Size = seq(0, 1.1, 1, 1.1), Transparency = seq(0, 1, 0.1, 0, 0.9, 0, 1, 1), Rotation = NumberRange.new(0, 360),
			RotSpeed = NumberRange.new(-60, 60), Brightness = 1.15, LightInfluence = 0.5 })
		table.insert(petals, fall)
		return { sky = sky, emitters = { fall } }
	end)
	-- fallen petals make a soft pink carpet around the player, and warm pollen glows and floats near the ground
	local groundRings = light and { { radius = 30, zones = 5, size = 22 } }
		or { { radius = 30, zones = 6, size = 22 }, { radius = 48, zones = 8, size = 28 } }
	local carpet, pollen = {}, {}
	local groundZones, groundFollow = followRing(groundRings, function(ring)
		local ground = anchorPart(Vector3.new(ring.size, 1, ring.size))
		local lying = emitter(ground, { Texture = A.PetalTumble, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, FlipbookFramerate = NumberRange.new(0), FlipbookStartRandom = true,
			Shape = Enum.ParticleEmitterShape.Box, Orientation = Enum.ParticleOrientation.VelocityPerpendicular,
			EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(0.01), Lifetime = NumberRange.new(10, 14),
			Size = seq(0, 0.9, 1, 0.9), Transparency = seq(0, 1, 0.08, 0.05, 0.85, 0.05, 1, 1), Rotation = NumberRange.new(0, 360),
			LightInfluence = 1 })
		table.insert(carpet, lying)
		local glow = emitter(ground, { Texture = C.GoldDust, Shape = Enum.ParticleEmitterShape.Box,
			EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(0.4, 1.2), SpreadAngle = Vector2.new(40, 40),
			Acceleration = Vector3.new(0.3, 0.2, 0), Lifetime = NumberRange.new(3, 5), Size = seq(0, 0.35, 1, 0.35),
			Transparency = seq(0, 1, 0.2, 0.1, 0.5, 0.5, 0.8, 0.1, 1, 1), LightEmission = 1, LightInfluence = 0,
			Color = ColorSequence.new(Color3.fromRGB(255, 215, 170)) })
		table.insert(pollen, glow)
		return { ground = ground, emitters = { glow } }
	end)
	local lanternBusy = 1
	local function setRates(factor)
		for _, lantern in ipairs(lanterns) do
			lantern.Rate = 0.1 * scale * factor * lanternBusy
		end
		for _, fall in ipairs(petals) do
			fall.Rate = (light and 1.2 or 2) * factor
		end
		for _, lying in ipairs(carpet) do
			lying.Rate = (light and 1 or 1.6) * factor
		end
		for _, glow in ipairs(pollen) do
			glow.Rate = (light and 1.5 or 3) * factor
		end
	end

	-- a few petals swirl behind a running player (only while running, small, at the feet: never at the camera)
	local feet = anchorPart(Vector3.new(2, 1, 2))
	local swirl = emitter(feet, { Texture = A.PetalTumble, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
		FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(12, 18), FlipbookStartRandom = true,
		Shape = Enum.ParticleEmitterShape.Box, Speed = NumberRange.new(1, 3), SpreadAngle = Vector2.new(180, 40),
		Acceleration = Vector3.new(0, 1, 0), Lifetime = NumberRange.new(0.4, 0.6), Size = seq(0, 0.6, 1, 0.3),
		Transparency = seq(0, 0, 0.8, 0.2, 1, 1), RotSpeed = NumberRange.new(-180, 180), LightInfluence = 0.5 })

	local passing = {} -- the effects of a moment (gusts, whirlwinds, lanterns let go): the end stops them too
	local root = rootPart()
	local base = root and root.Position or camera.CFrame.Position
	local clock = 0
	local following = RunService.RenderStepped:Connect(function(dt)
		clock = clock + dt
		local r = rootPart()
		if r then
			base = r.Position
			local moving = r.AssemblyLinearVelocity * Vector3.new(1, 0, 1)
			local behind = moving.Magnitude > 1 and -moving.Unit * 2.5 or Vector3.zero
			feet.CFrame = CFrame.new(r.Position - Vector3.new(0, 2.6, 0) + behind) -- low, a little behind the feet
			swirl.Rate = (alive and moving.Magnitude > 12) and (light and 6 or 12) or 0
		end
		-- the petals in the air and the pollen stop where they would come near the camera
		local eye = camera.CFrame.Position
		for _, list in ipairs({ petalZones, groundZones }) do
			for _, zone in ipairs(list) do
				local part = zone.sky or zone.ground
				local near = (part.Position - eye).Magnitude < part.Size.X / 2 + 22 -- with the little drift of the wind
				for _, item in ipairs(zone.emitters) do
					item.Enabled = not near
				end
			end
		end
		updateStrings(base, clock)
		placeBoards(boards, base, dt)
	end)

	-- a whirlwind of petals: a few streams spiral up a column far in front, then the wind lets go
	local function whirlwind()
		local r = rootPart()
		if not r then
			return
		end
		local direction = camera.CFrame.LookVector
		local flat = Vector3.new(direction.X, 0, direction.Z)
		flat = flat.Magnitude > 0.01 and flat.Unit or Vector3.new(0, 0, -1)
		local side = Vector3.new(-flat.Z, 0, flat.X)
		local spot = r.Position + flat * (55 + math.random() * 20) + side * ((math.random() - 0.5) * 60)
		local floor = groundY(spot + Vector3.new(0, 30, 0), r.Position.Y - 3)
		local center = Vector3.new(spot.X, floor, spot.Z)
		local streams, started = {}, os.clock()
		for n = 1, light and 2 or 4 do
			local head = anchorPart(Vector3.new(1, 1, 1))
			head.CFrame = CFrame.new(center)
			local stream = emitter(head, { Texture = A.PetalTumble, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
				FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(12, 18), FlipbookStartRandom = true,
				Speed = NumberRange.new(0.5, 1.5), SpreadAngle = Vector2.new(180, 180), Acceleration = Vector3.new(0, 1.2, 0),
				Lifetime = NumberRange.new(2.2, 3), Size = seq(0, 1.6, 1, 1.2), Transparency = seq(0, 0, 0.8, 0.1, 1, 1),
				RotSpeed = NumberRange.new(-150, 150), Brightness = 1.2, LightInfluence = 0.4 })
			stream.Rate = 22 * scale
			table.insert(passing, stream)
			table.insert(streams, { head = head, stream = stream, phase = n * math.pi * 2 / (light and 2 or 4) })
		end
		local spinning
		spinning = RunService.Heartbeat:Connect(function()
			local t = os.clock() - started
			-- the column stops when the camera comes close to it
			local near = (Vector3.new(center.X, camera.CFrame.Position.Y, center.Z) - camera.CFrame.Position).Magnitude < 22
			for _, item in ipairs(streams) do
				local rise = math.min(t / 4.5, 1)
				local a = item.phase + t * 4.2
				local radius = 3 + rise * 7
				item.head.CFrame = CFrame.new(center + Vector3.new(math.cos(a) * radius, 1 + rise * 26, math.sin(a) * radius))
				if t > 5 or not alive or near then
					item.stream.Rate = 0
				end
			end
			if t > 8.5 then
				spinning:Disconnect()
				for _, item in ipairs(streams) do
					item.head:Destroy()
				end
			end
		end)
	end

	-- a gust: a stream of petals across the sky far in front, over the eggs' chances (from side to side)
	local function gust(count)
		local r = rootPart()
		if not r then
			return
		end
		local direction = camera.CFrame.LookVector
		local flat = Vector3.new(direction.X, 0, direction.Z)
		flat = flat.Magnitude > 0.01 and flat.Unit or Vector3.new(0, 0, -1)
		local side = Vector3.new(-flat.Z, 0, flat.X) * (math.random() < 0.5 and 1 or -1)
		local start = r.Position + flat * (45 + math.random() * 20) - side * 85 + Vector3.new(0, 16 + math.random() * 8, 0)
		local part = anchorPart(Vector3.new(36, 10, 1))
		part.CFrame = CFrame.lookAt(start, start + side)
		local stream = emitter(part, { Texture = A.PetalTumble, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(10, 16), FlipbookStartRandom = true,
			Shape = Enum.ParticleEmitterShape.Box, EmissionDirection = Enum.NormalId.Front, Speed = NumberRange.new(26, 36),
			SpreadAngle = Vector2.new(6, 12), Acceleration = Vector3.new(0, -1.5, 0), Lifetime = NumberRange.new(5, 6),
			Size = seq(0, 2.2, 1, 2.2), Transparency = seq(0, 1, 0.08, 0, 0.85, 0, 1, 1), Rotation = NumberRange.new(0, 360),
			RotSpeed = NumberRange.new(-120, 120), Brightness = 1.2, LightInfluence = 0.4 })
		stream.Rate = math.max(1, count * scale) / 2
		table.insert(passing, stream)
		task.delay(2, function()
			stream.Rate = 0
		end)
		task.delay(9, function()
			part:Destroy()
		end)
	end
	local windy = 1 -- the last minute: the wind blows more often
	local windLoop = task.spawn(function()
		local nextWhirl = os.clock() + 8
		while alive do
			task.wait((4 + math.random() * 3) / windy)
			if not alive then
				break
			end
			if os.clock() >= nextWhirl then
				nextWhirl = os.clock() + (14 + math.random() * 8) / windy
				whirlwind()
			else
				gust(light and 16 or 32)
			end
		end
	end)

	-- petals and glints burst from a point to all sides (each point of a part looks one way)
	local function burst(where, count, speed)
		local part = anchorPart(Vector3.new(1, 1, 1))
		part.CFrame = CFrame.new(where)
		for i = 0, count - 1 do
			local y = 1 - (i + 0.5) / count * 2
			local r = math.sqrt(1 - y * y)
			local a = i * 2.39996
			local point = Instance.new("Attachment")
			point.CFrame = CFrame.lookAt(Vector3.zero, Vector3.new(math.cos(a) * r, y, math.sin(a) * r))
			point.Parent = part
			emitter(point, { Texture = A.PetalTumble, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
				FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(12, 20), FlipbookStartRandom = true,
				EmissionDirection = Enum.NormalId.Front, Speed = NumberRange.new(speed * 0.8, speed), Drag = 1.2,
				SpreadAngle = Vector2.new(10, 10), Acceleration = Vector3.new(0.8, -3, 0.4), Lifetime = NumberRange.new(3, 4),
				Size = seq(0, 1.2, 0.15, 2.4, 1, 2), Transparency = seq(0, 0, 0.8, 0, 1, 1), RotSpeed = NumberRange.new(-150, 150),
				Brightness = 1.2, LightInfluence = 0.3 }):Emit(1)
			if i % 2 == 0 then
				emitter(point, { Texture = C.CoinGlint, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
					FlipbookMode = Enum.ParticleFlipbookMode.OneShot, EmissionDirection = Enum.NormalId.Front,
					Speed = NumberRange.new(speed * 0.5, speed * 0.8), Drag = 1.5, Lifetime = NumberRange.new(1, 1.4),
					Size = seq(0, 1.8, 1, 1.8), LightEmission = 1, LightInfluence = 0 }):Emit(1)
			end
		end
		task.delay(4.5, function()
			part:Destroy()
		end)
	end

	-- the start: the sunset comes, a big cherry blossom opens in the sky in front, turns and shines, bursts into a
	-- cloud of petals, and lanterns rise all around the map
	local function intro()
		setRates(0)
		mood.go(1, 3)
		fadeBoards(boards, true, 4)
		local r = rootPart()
		if not r then
			setRates(1)
			showStrings(true, 3)
			return
		end
		local direction = camera.CFrame.LookVector
		local flat = Vector3.new(direction.X, 0, direction.Z)
		flat = flat.Magnitude > 0.01 and flat.Unit or Vector3.new(0, 0, -1)
		local center = r.Position + flat * 60 + Vector3.new(0, 15, 0)
		local flower = {}
		local item = skyBoard(flower, A.Blossom, 1, 1, { angle = 0, distance = 0, lift = 0, shown = 0, brightness = 1.3 })
		item.holder.CFrame = CFrame.lookAt(center, camera.CFrame.Position)
		local glow = emitter(item.holder, { Texture = C.GoldDust, Speed = NumberRange.new(0), Lifetime = NumberRange.new(1),
			Size = seq(0, 20, 1, 24), Transparency = seq(0, 0.7, 0.5, 0.5, 1, 1), LightEmission = 1, LightInfluence = 0,
			ZOffset = -2, LockedToPart = true, Color = ColorSequence.new(Color3.fromRGB(255, 190, 215)) })
		glow.Rate = 4
		local sparkle = emitter(item.holder, { Texture = C.CoinGlint, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
			FlipbookMode = Enum.ParticleFlipbookMode.OneShot, Shape = Enum.ParticleEmitterShape.Sphere,
			Speed = NumberRange.new(0.5, 2), Lifetime = NumberRange.new(0.6, 1), Size = seq(0, 2, 1, 2), LightEmission = 1,
			LightInfluence = 0 })
		local size = Instance.new("NumberValue") -- the flower opens: it grows and turns
		size.Value = 1
		size.Changed:Connect(function(v)
			item.holder.Size = Vector3.new(v, v, 0.05)
			item.picture.Rotation = v * 2
		end)
		task.wait(0.6)
		if not alive then
			item.holder:Destroy()
			size:Destroy()
			return
		end
		item.picture.ImageTransparency = 0
		sparkle.Rate = 30 * scale
		TweenService:Create(size, TweenInfo.new(1.6, Enum.EasingStyle.Back, Enum.EasingDirection.Out), { Value = 22 }):Play()
		task.wait(2.2)
		if not alive then
			item.holder:Destroy()
			size:Destroy()
			return
		end
		-- it bursts into petals; the lanterns rise
		glow.Rate, sparkle.Rate = 0, 0
		TweenService:Create(item.picture, TweenInfo.new(0.35), { ImageTransparency = 1 }):Play()
		TweenService:Create(size, TweenInfo.new(0.35), { Value = 30 }):Play()
		burst(center, light and 24 or 48, 26)
		for _, lantern in ipairs(lanterns) do
			lantern:Emit(light and 2 or 3)
		end
		showStrings(true)
		-- a cluster of lanterns is let go from the ground in front (never close to the camera)
		local side = Vector3.new(-flat.Z, 0, flat.X)
		for n, offset in ipairs(light and { 0 } or { -26, 0, 26 }) do
			local spot = r.Position + flat * (48 + n * 4) + side * offset
			local floor = groundY(spot + Vector3.new(0, 30, 0), r.Position.Y - 3)
			local release = anchorPart(Vector3.new(10, 1, 10))
			release.CFrame = CFrame.new(spot.X, floor + 1, spot.Z)
			local rising = emitter(release, { Texture = A.Lantern, FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
				FlipbookMode = Enum.ParticleFlipbookMode.Loop, FlipbookFramerate = NumberRange.new(6, 10), FlipbookStartRandom = true,
				Shape = Enum.ParticleEmitterShape.Box, EmissionDirection = Enum.NormalId.Top, Speed = NumberRange.new(4, 6.5),
				SpreadAngle = Vector2.new(12, 12), Acceleration = Vector3.new(0.5, 0.3, 0), Lifetime = NumberRange.new(14, 18),
				Size = seq(0, 0, 0.05, 2.3, 1, 1.8), Transparency = seq(0, 1, 0.04, 0, 0.85, 0, 1, 1),
				RotSpeed = NumberRange.new(-8, 8), LightEmission = 0.7, LightInfluence = 0, Brightness = 1.7 })
			rising:Emit(light and 6 or 9)
			table.insert(passing, rising)
			task.delay(19, function()
				release:Destroy()
			end)
		end
		setRates(1)
		task.delay(1.5, function()
			item.holder:Destroy()
			size:Destroy()
			if alive then
				gust(light and 24 or 50)
				task.delay(1.2, function()
					if alive then
						gust(light and 16 or 34)
					end
				end)
			end
		end)
	end

	-- the last minute: many more lanterns fly up
	local function final()
		lanternBusy = 3
		windy = 1.6
		setRates(1)
	end

	-- the end: the petals fall to the ground and fade, the lanterns fade into the sky, the sunset goes back to the day
	local function stop()
		alive = false
		task.cancel(windLoop)
		setRates(0)
		swirl.Rate = 0
		fadeBoards(boards, false, 2.2)
		showStrings(false, 1.2)
		task.delay(1.2, function()
			showStrings(false, 0)
		end)
		for _, item in ipairs(passing) do
			pcall(function()
				item.Rate = 0
			end)
		end
		local fading = Instance.new("NumberValue")
		fading.Changed:Connect(function(v)
			local seqLantern = NumberSequence.new(v)
			for _, lantern in ipairs(lanterns) do
				lantern.Transparency = seqLantern
			end
			for _, fall in ipairs(petals) do
				fall.Transparency = seqLantern
			end
			for _, lying in ipairs(carpet) do
				lying.Transparency = seqLantern
			end
			for _, item in ipairs(passing) do
				pcall(function()
					item.Transparency = seqLantern
				end)
			end
		end)
		TweenService:Create(fading, TweenInfo.new(2.4, Enum.EasingStyle.Sine), { Value = 1 }):Play()
		restoreLight()
		mood.stop(2.5)
		task.delay(2.6, function()
			following:Disconnect()
			follow:Disconnect()
			petalFollow:Disconnect()
			fading:Destroy()
			groundFollow:Disconnect()
			for _, item in ipairs(boards) do
				item.holder:Destroy()
			end
			for _, line in ipairs(strings) do
				line.holder:Destroy()
			end
			for _, zone in ipairs(groundZones) do
				zone.ground:Destroy()
			end
			for _, zone in ipairs(zones) do
				zone.ground:Destroy()
			end
			for _, zone in ipairs(petalZones) do
				zone.sky:Destroy()
			end
			feet:Destroy()
		end)
	end

	-- a player who joins later sees the sunset, the trees, the lanterns and the petals already there
	setRates(1)
	mood.go(1, 0)
	fadeBoards(boards, true, 2)
	showStrings(true, 2)
	return {
		intro = function()
			mood.go(0, 0)
			showStrings(false, 0)
			for _, item in ipairs(boards) do
				item.picture.ImageTransparency = 1
			end
			intro()
		end,
		final = final,
		stop = stop,
	}
end

-- ---------- Which event shows its animation ----------

-- The names of the animations this file has (the panel and the bot offer only these)
function Effects.Names()
	local names = {}
	for name in pairs(animations) do
		table.insert(names, name)
	end
	table.sort(names)
	return names
end

-- The event whose animation runs: the newest started one that has a known animation and hasn't ended
function Effects.Pick(events, now)
	local best = nil
	for _, event in ipairs(type(events) == "table" and events or {}) do
		if type(event) == "table" and animations[event.animation] and (tonumber(event.ends_at) or 0) > now
			and (tonumber(event.starts_at) or 0) <= now then
			if not best or (tonumber(event.starts_at) or 0) > (tonumber(best.starts_at) or 0) then
				best = event
			end
		end
	end
	return best
end

local running = nil -- { key = event id and animation, effect = ..., final = true when the last minute started }
local showing = {} -- every animation on this screen now (the running one and previews): a rare pet reaches them all

local function stopRunning()
	if running then
		local effect = running.effect
		running = nil
		showing[effect] = nil
		pcall(effect.stop)
	end
end

-- The game's quality for animations: "off", "light" (phones, low graphics) or "full"
local function currentQuality(setting)
	if setting == "off" then
		return "off"
	end
	local low = false
	pcall(function()
		low = UserSettings():GetService("UserGameSettings").SavedQualityLevel.Value <= 3
			and UserSettings():GetService("UserGameSettings").SavedQualityLevel ~= Enum.SavedQualitySetting.Automatic
	end)
	local phone = UserInputService.TouchEnabled and not UserInputService.KeyboardEnabled
	return (setting == "light" or phone or low) and "light" or "full"
end

-- Called with the active events and the server's time whenever they change, and every second (for the last minute)
function Effects.Update(events, now, setting)
	quality = currentQuality(setting)
	local event = quality ~= "off" and Effects.Pick(events, now) or nil
	local key = event and (tostring(event.id) .. "|" .. tostring(event.animation)) or nil
	if running and running.key ~= key then
		stopRunning()
	end
	if event and not running then
		local ok, effect = pcall(animations[event.animation])
		if not ok then
			warn("[DiscordLive] The animation " .. tostring(event.animation) .. " could not start: " .. tostring(effect))
			return
		end
		running = { key = key, effect = effect, final = false }
		showing[effect] = true
		local started = tonumber(event.starts_at) or 0
		if now - started <= INTRO_WINDOW and (tonumber(event.ends_at) or 0) - now > 10 then
			task.spawn(effect.intro)
		end
	end
	if running and event and not running.final and (tonumber(event.ends_at) or 0) - now <= FINAL_SECONDS then
		running.final = true
		pcall(running.effect.final, (tonumber(event.ends_at) or 0) - now)
	end
end

-- Shows one animation for a few seconds on this device only (the ⚙️ Manager's preview)
function Effects.Preview(name, seconds)
	if not animations[name] then
		return false
	end
	quality = currentQuality("full")
	previewing = true -- an animation may show its rare parts sooner in a short preview
	local ok, effect = pcall(animations[name])
	previewing = false
	if not ok then
		warn("[DiscordLive] The animation " .. name .. " could not start: " .. tostring(effect))
		return false
	end
	showing[effect] = true
	task.spawn(effect.intro)
	task.delay(seconds or 12, function()
		showing[effect] = nil
		pcall(effect.stop)
	end)
	return true
end

-- A rare pet from an egg on this player's screen (DiscordLiveClient): an animation that answers it does (Lucky Breeze)
function Effects.Hatched(eggId)
	for effect in pairs(showing) do
		if effect.hatch then
			task.spawn(pcall, effect.hatch, eggId)
		end
	end
end

return Effects
