--!nonstrict
--[[
	DiscordManagerClient  (LocalScript inside the ScreenGui "DiscordManager")

	The ⚙️ Manager window for the game's owner. The server gives this ScreenGui only to people allowed to use it (see the
	Manager module) and checks every action again. Language: English by default, English / Español / Polski in the
	list at the top right of the window. Hover a row (or tap its title on a phone) to see what it does.
]]

local GuiService = game:GetService("GuiService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local TweenService = game:GetService("TweenService")
local UserInputService = game:GetService("UserInputService")

local gui = script.Parent
local player = Players.LocalPlayer

local remote = nil
for _ = 1, 60 do
	for _, child in ipairs(ReplicatedStorage:GetChildren()) do
		if child.Name == "DiscordManager" and child:IsA("RemoteFunction") then
			remote = child
		end
	end
	if remote then
		break
	end
	task.wait(0.5)
end
if not remote then
	return
end

-- ---------- Texts ----------
local TEXTS = {
	en = {
		open = "Manager",
		owner = "OWNER",
		tabs = { "Start", "Promo codes", "Events", "Eggs", "Gifts & news", "Players", "Settings", "Test tools", "Log",
			"Manager access" },
		subtitles = { "this server right now", "from Discord", "running now", "on the stands", "from Discord",
			"your player data", "live on this server", "only you see them", "the kit's messages", "who may use this panel" },
		ownerOnly = "Only the game's owner can do this.",
		noPermission = "You may not do this. The game's owner gives permissions in the 🛡️ tab or on Discord (/setup → 🛡️ Permissions).",
		accessFind = "Find a player",
		accessFindDesc = "Their Roblox username (not the display name)",
		tipAccessFind = "Type the name and press Enter or Find. Then tick what they may do and click Save. They get the ⚙️ Manager button at once, with only those tabs.",
		accessNameBox = "username",
		find = "Find",
		accessEdit = "What %s may do",
		accessEditDesc = "Ticked = they see that tab and may use it. Start is always there.",
		accessSave = "Save",
		cancel = "Cancel",
		accessRemove = "Take access away",
		accessSaved = "Saved: %s has the Manager with what you ticked.",
		accessRemoved = "%s no longer has the Manager.",
		accessListTitle = "Who has the Manager (%d of %d)",
		accessNone = "Only you",
		accessNoneHint = "Find a player above to give them the Manager.",
		accessNothing = "only Start",
		accessNotFound = "No Roblox account with that name. Check the spelling (username, not the display name).",
		accessOwner = "That's you (the owner): you always have everything.",
		accessFull = "At most 25 players. Remove someone first.",
		accessFailed = "Roblox did not save it. Try again in a moment.",
		accessStudio = "In Studio this needs: Game Settings → Security → Enable Studio Access to API Services.",
		accessDiscordNote = "The same list as on Discord (/setup → 🛡️ Permissions → Manager in the game): a change here shows there too.",
		edit = "Edit",
		perms = { codes = "Promo codes", events = "Events", eggs = "Eggs", gifts = "Gifts", announce = "Announcements", bans = "Bans",
			settings = "Settings" },
		giftSelf = "You can't send a gift to yourself.",
		changed = "%s changed on this server. To keep it after a restart, copy it into DiscordSettings.",
		reset = "Reset",
		tipReset = "Back to the values from DiscordSettings, on this server.",
		resetDone = "Back to the values from DiscordSettings.",
		copy = "Copy for DiscordSettings",
		tipCopy = "Shows the lines to paste into ServerScriptService → DiscordSettings, so your changes stay after a restart.",
		copyTitle = "Replace these lines in DiscordSettings (click the box, Ctrl+A, Ctrl+C):",
		limitBox = "0 = no limit, Enter saves",
		notNumber = "Type a whole number (0 = no limit).",
		codeTest = "Test a code",
		codeTestDesc = "What redeeming it would do for you now. Nothing is used up.",
		tipCodeTest = "Checks the code like the real window does (exists, not ended, fits the limit, your player data has a place for the reward, not redeemed yet) without using it up.",
		codeBox = "CODE",
		test = "Test",
		resOk = "✅ Works: %s",
		resInvalid = "❌ No active code with this name.",
		resExpired = "⌛ This code has ended.",
		resAlready = "🔁 You already redeemed it.",
		resUnsupported = "⚠️ Can't be given: %s",
		resUnknown = "❓ Couldn't check if you redeemed it (DataStore didn't answer). Otherwise fine: %s",
		resCustom = " (your OnReward gives it)",
		previews = "Preview what players see",
		tipPreviews = "Only you see it. Nothing is given, saved or sent to other players.",
		showMe = "Show me",
		prevAnnounce = "Announcement",
		prevAnnounceDesc = "A message at the top of the screen",
		announceBox = "Text of the announcement",
		sampleAnnounce = "Double coins weekend starts now!",
		prevGift = "Gift",
		prevGiftDesc = "What a player sees after /give",
		sampleGift = "Thanks for playing!",
		prevHatch = "Hatch",
		prevHatchDesc = "Opening this egg with today's chances",
		prevEvent = "Event icon",
		prevEventDesc = "2x on every currency for 30 s",
		sampleEvent = "Preview event",
		shown = "Shown on your screen only.",
		myCurrency = "My currency",
		tipMyCurrency = "Studio only: adds to or takes from your own values, to test eggs and prices. If your game saves data in Studio, it is saved too.",
		-- creating things through the bot
		ownerForms = "Only the game's owner creates things here.",
		tipBotForms = "The game does it at once, by itself: the Discord bot doesn't have to run. The same checks as on Discord. When the bot runs, it writes every change to your Discord log channel.",
		saving = "Saving in the game…",
		factorBox = "or type e.g. 2.5",
		animation = "Animation",
		noAnimation = "— none —",
		anim_coin_storm = "💰 Coin Storm",
		anim_aurora = "🌌 Aurora",
		anim_lucky_breeze = "🍀 Lucky Breeze",
		anim_meteor_shower = "☄️ Meteor Shower",
		anim_sakura_festival = "🌸 Sakura Festival",
		previewAnimation = "Preview",
		tipPreviewAnimation = "Shows the animation for a few seconds, only on your screen. Nothing starts for the players.",
		pickAnimation = "Pick an animation first.",
		previewAnimationShown = "The preview runs on your screen for a few seconds.",
		scope = "Where",
		allServers = "All servers",
		thisServer = "This server",
		tipThisServer = "Only on this server, until it ends or the server stops. Other servers and the bot don't see it.",
		eventStartedHere = "Event %s starts in 10 s on this server for %s.",
		badMultiplier = "The multiplier must be a number from 1.1 to %s (e.g. 2 or 2.5).",
		setEffects = "Event animations",
		setEffectsDesc = "Full, light or off",
		tipSetEffects = "How much of the event animations players see. Phones and low graphics always get the light version.",
		effectsFull = "Full",
		effectsLight = "Light",
		effectsOff = "Off",
		stillSending = "Wait a moment: the previous change is still being saved.",
		saveFailed = "Couldn't save it in the game (%s). Try again in a moment.",
		studioApi = "DataStore is off in Studio: Game Settings → Security → Enable Studio Access to API Services, then try again.",
		madeInGame = "🎮 %s",
		madeInGameAnon = "🎮 Panel",
		madeOnDiscord = "💬 Discord",
		tipMadeIn = "Where it was made: 🎮 in this panel (and by whom) or 💬 on Discord. Both show here and on Discord.",
		codeAdded = "Code %s works now: %s · valid %s.",
		codeRemoved = "Code %s removed: players can't redeem it any more.",
		eventStarted = "Event %s starts in 10 s for %s.",
		eventStopped = "Event %s stopped.",
		eggCreated = "Egg %s is in the game: %s %s.",
		eggMoved = "Egg %s moved: %s.",
		eggRemoved = "Egg %s removed.",
		giftSent = "Gift for %s: %s. They get it now, or when they join next time.",
		announced = "The announcement is on every server.",
		announcedHere = "The announcement is on this server.",
		found = "Account: %s (ID %s). Check it, then click Ban to ban exactly this account.",
		banned = "%s is banned: %s.",
		unbanned = "%s can play again.",
		permanentBan = "for good",
		badCode = "A code may have only letters A–Z, digits, - and _ (at most 30).",
		badValue = "Something in the form is missing or wrong. Fill it in again.",
		codeExists = "Code %s is already active. Remove it first or pick another name.",
		noReward = "Pick at least one reward: a currency with an amount, EXP or an item.",
		currencyAmount = "Pick the currency and type its amount (both, or neither).",
		tooMuch = "%s is more than the game allows (MaxCurrencyPerCode in DiscordSettings: %s).",
		unknownName = "%s is not in DiscordCatalog. Pick a name from the list.",
		notFound = "It isn't in the game any more (removed or ended). The tab shows the current list.",
		tooManyEvents = "%s events already run (the most). Stop one first.",
		tooManyEggs = "There are already %s eggs (the most). Remove one first.",
		eggExists = "There is already an egg named %s.",
		badPets = "Write the pets like this: Cat:60, Dog:35, Dragon:5 (wrong: %s).",
		petTwice = "%s is in the list twice.",
		tooManyPets = "At most %s pets in one egg.",
		unknownPets = "Not in DiscordCatalog: %s. Use the exact names from the catalog.",
		badSpot = "This game has no egg spot named %s.",
		noPlayer = "Couldn't find the Roblox account %s. Check the spelling (if it's right, Roblox may not have answered: try again).",
		ambiguous = "%s is the ID of one account and the name of another. Type the username.",
		hasLink = "The text has a link: Roblox shows such a text as #### to every player. Write it without the link.",
		banSelf = "You can't ban yourself or the game's owner.",
		banOff = "Bans are off in this game: in Studio select Players in the Explorer, turn on BanningEnabled in Properties, then publish.",
		robloxBusy = "Roblox didn't answer (%s). Try again in a moment.",
		longText = "%s: at most %s characters.",
		changeError = "Something went wrong (the details are in the Log tab). Nothing was changed.",
		warnRobux = "⚠️ %s can be bought with Robux: Roblox doesn't allow it in codes posted outside Roblox (e.g. on Discord).",
		warnRobuxGift = "⚠️ %s can be bought with Robux: fine as a compensation, but not as a prize of a contest outside Roblox.",
		warnLink = "⚠️ The message looks like a link: Roblox may show it as ####.",
		warnStudioBan = "ℹ️ In Studio a ban is only checked: it works in the published game.",
		warnNoSpots = "⚠️ The game has no egg spots yet: the egg shows when a part gets the tag DiscordEggSpot.",
		warnNotTold = "⚠️ The other servers couldn't be told (%s).",
		fillIn = "Fill in: %s",
		create = "Create",
		send = "Send",
		remove = "Remove",
		sure = "Sure?",
		noneOption = "— none —",
		noEnd = "No end",
		day = "day",
		days = "days",
		permanent = "Permanent",
		newCode = "New code",
		codeName = "Code",
		codeNameBox = "SUMMER24",
		currency = "Currency",
		amount = "Amount",
		exp = "EXP",
		item = "Item",
		validFor = "Valid for",
		newEvent = "New event",
		name = "Name",
		eventNameBox = "Weekend Boost",
		boost = "Boost",
		allCurrencies = "All currencies",
		luck = "Luck (rare pets)",
		howLong = "How long",
		startEvent = "Start event",
		stop = "Stop",
		newEgg = "New egg",
		eggNameBox = "Lava Egg",
		priceLabel = "Price",
		pets = "Pets : chance",
		petsBox = "Cat:60, Dog:35, Dragon:5",
		spot = "Spot",
		anySpot = "Any free spot",
		lasts = "Lasts",
		moveTo = "Move",
		giftForm = "Gift to a player",
		player = "Player",
		playerBox = "Name or ID",
		message = "Message",
		messageBox = "Thanks for playing!",
		announceForm = "Announcement",
		announceText = "Text",
		onScreen = "On screen",
		banForm = "Ban a player",
		banFor = "For",
		reason = "Reason",
		reasonBox = "Exploiting",
		banButton = "Ban",
		checkAccount = "Check account",
		banAccount = "Ban %s",
		itemTime = "Item for",
		unbanButton = "Unban",
		tipTitle = "ⓘ What does it do?",
		loading = "Loading...",
		failed = "No answer from the server. Try again.",
		denied = "This panel is only for the game's owner.",
		wait = "Wait %d s and try again.",
		studioOnly = "Only in Studio: in the published game it would let you redeem one code again and again.",
		kitLine = "Kit v%s · %s",
		inStudio = "Studio",
		inLive = "Live server",
		tileCodes = "Active codes",
		tileEvents = "Events now",
		tileEggs = "Eggs on stands",
		tileVersion = "Studio file",
		tipTiles = "What this server has right now. Codes, events and eggs come from Discord and change in a few seconds after the bot saves them.",
		whereTitle = "Where it runs",
		whereStudio = "In Studio: only you play here",
		whereLive = "In the published game",
		tipWhere = "In Studio you also get the test buttons that the published game blocks (e.g. Forget a redeemed code).",
		hooksTitle = "Your own functions",
		hooksDesc = "Set in your own scripts",
		tipHooks = "OnReward, OnSpend, OnHatch and OnAnnouncement are functions your scripts may set, so the kit uses your own data or windows. ✅ = set.",
		limitTitle = "Most currency per code",
		limitDesc = "A bigger code or gift is refused",
		noLimit = "no limit",
		tipLimit = "A promo code or gift from Discord that gives more currency than this is refused and not used up. 0 = no limit. Set in DiscordSettings.",
		refresh = "Refresh from Discord",
		reload = "Refresh",
		more = "More",
		tipRefresh = "Reads codes, events and eggs from the bot right now, instead of waiting for the next update.",
		refreshed = "Refreshed: %s codes, %s events, %s eggs.",
		noCodes = "No active codes yet.",
		noCodesHint = "Add one on Discord: /setup-roblox → Promo codes.",
		canGive = "✅ Works for you",
		cantGive = "⚠️ Blocked",
		tipCant = "It can't be given to you now: %s",
		tipCan = "Your player data has everything this code gives, so redeeming it works.",
		tipCustom = "Your own OnReward function gives the rewards, so the kit doesn't check your player data here.",
		expires = "ends in %s",
		forever = "no end",
		expiredCode = "expired",
		forget = "Forget",
		tipForget = "Studio only: forgets that you redeemed this code, so you can test it again.",
		forgotten = "Done: you can redeem %s again.",
		noEvents = "No events running.",
		noEventsHint = "Start one on Discord: /event-start.",
		left = "%s left",
		startsIn = "starts in %d s (the players' countdown)",
		event = "Event",
		yourCode = "What your code gets now",
		tipYourCode = "Live.GetMultiplier(name) in your scripts returns this number now.",
		noUsed = "Your code hasn't asked Live.GetMultiplier yet (it asks when it gives currency or EXP).",
		noEggs = "No eggs on the stands.",
		noEggsHint = "Add one on Discord: /egg-create.",
		price = "Price %s %s",
		simulate = "Simulate %d",
		tipSimulate = "Rolls the egg many times with the chances players get now and only counts the results. Nothing is given.",
		openEgg = "Open",
		tipOpen = "A normal purchase for the egg's price, like any player. The result shows at the bottom of the screen.",
		opened = "Opening... the result shows at the bottom of the screen.",
		simulation = "%d openings (nothing was given):",
		giftsTitle = "Waiting gifts",
		giftsDesc = "Gifts from /give wait until the player joins",
		tipGifts = "Waiting gifts arrive a few seconds after joining. This button gives yours right away.",
		deliver = "Deliver mine now",
		delivered = "Asked for your waiting gifts: if there are any, they arrive in a moment.",
		values = "Values in your player data",
		tipValues = "Only these values can be changed by codes and gifts. The names come from your game.",
		attributes = "Attributes on your player",
		noValues = "Nothing found. The game creates player data a moment after joining: open this tab again.",
		setButton = "Codes button",
		setButtonDesc = "Show the Codes button on the screen",
		tipSetButton = "Off = hidden, e.g. when you open the code window from your own menu.",
		on = "ON",
		off = "OFF",
		setPosition = "Button position",
		setPositionDesc = "Where the Codes button sits",
		setManagerPos = "Manager button",
		setManagerPosDesc = "Where this ⚙️ Manager button sits",
		setEventPos = "Event icons",
		setEventPosDesc = "Where the round event icons are",
		setAnnouncePos = "Announcements",
		setAnnouncePosDesc = "Where announcements from Discord show",
		setNotifyPos = "Notifications",
		setNotifyPosDesc = "Where gift and pet messages show",
		offsetBox = "x, y",
		tipPlace = "Pick a place, then move it by pixels in the box: first right (+) or left (-), then down (+) or up (-), e.g. 0, -80 = 80 px higher. Enter saves.",
		badOffset = "Type two whole numbers, e.g. 0, -80.",
		filterHidden = "🔒 Roblox's text filter hid this line",
		refused = "The server refused it (the value is not allowed here).",
		studioOnlyCurrency = "Only in Studio: in the published game it would be free currency.",
		tipSetPosition = "Left, Right, Top, Bottom or a corner like TopLeft. A window from your own template in StarterGui keeps its own place for the button.",
		setLanguage = "Players' language",
		setLanguageDesc = "Window, events and messages",
		tipSetLanguage = "Auto = each player gets the language of their Roblox settings (English, Polish or Spanish).",
		auto = "Auto (player)",
		setHelpers = "Manager for helpers",
		setHelpersDesc = "Who may open this panel besides you",
		tipSetHelpers = "Set it in the 🛡️ tab (find a player by name, tick what they may do) or on Discord: /setup → 🛡️ Permissions. The game's owner always has everything.",
		helpers = "%d more",
		onlyYou = "Only you",
		settingsNote = "Changes work at once on this server only. To keep them after a restart, copy them into DiscordSettings.",
		noLog = "No messages from the kit yet.",
		logInfo = "The kit's lines from the Output window, newest at the bottom",
	},
	es = {
		open = "Manager",
		owner = "DUEÑO",
		tabs = { "Inicio", "Códigos", "Eventos", "Huevos", "Regalos y avisos", "Jugadores", "Ajustes", "Pruebas", "Registro",
			"Acceso al Manager" },
		subtitles = { "este servidor ahora", "desde Discord", "activos ahora", "en los soportes", "desde Discord",
			"tus datos de jugador", "en vivo en este servidor", "solo los ves tú", "mensajes del kit", "quién puede usar este panel" },
		ownerOnly = "Solo el dueño del juego puede hacer esto.",
		noPermission = "No puedes hacer esto. El dueño del juego da permisos en la pestaña 🛡️ o en Discord (/setup → 🛡️ Permisos).",
		accessFind = "Buscar un jugador",
		accessFindDesc = "Su nombre de usuario de Roblox (no el visible)",
		tipAccessFind = "Escribe el nombre y pulsa Enter o Buscar. Luego marca lo que puede hacer y pulsa Guardar. Recibe el botón ⚙️ Manager al momento, solo con esas pestañas.",
		accessNameBox = "usuario",
		find = "Buscar",
		accessEdit = "Qué puede hacer %s",
		accessEditDesc = "Marcado = ve esa pestaña y puede usarla. Inicio está siempre.",
		accessSave = "Guardar",
		cancel = "Cancelar",
		accessRemove = "Quitar el acceso",
		accessSaved = "Guardado: %s tiene el Manager con lo que marcaste.",
		accessRemoved = "%s ya no tiene el Manager.",
		accessListTitle = "Quién tiene el Manager (%d de %d)",
		accessNone = "Solo tú",
		accessNoneHint = "Busca un jugador arriba para darle el Manager.",
		accessNothing = "solo Inicio",
		accessNotFound = "No hay una cuenta de Roblox con ese nombre. Revisa cómo se escribe (usuario, no el nombre visible).",
		accessOwner = "Eres tú (el dueño): siempre lo tienes todo.",
		accessFull = "Como máximo 25 jugadores. Quita a alguien primero.",
		accessFailed = "Roblox no lo guardó. Inténtalo en un momento.",
		accessStudio = "En Studio hace falta: Game Settings → Security → Enable Studio Access to API Services.",
		accessDiscordNote = "La misma lista que en Discord (/setup → 🛡️ Permisos → Manager en el juego): un cambio aquí se ve también allí.",
		edit = "Cambiar",
		perms = { codes = "Códigos", events = "Eventos", eggs = "Huevos", gifts = "Regalos", announce = "Avisos", bans = "Baneos",
			settings = "Ajustes" },
		giftSelf = "No puedes enviarte un regalo a ti mismo.",
		changed = "%s cambiado en este servidor. Para conservarlo tras un reinicio, cópialo en DiscordSettings.",
		reset = "Restablecer",
		tipReset = "Vuelve a los valores de DiscordSettings en este servidor.",
		resetDone = "De vuelta a los valores de DiscordSettings.",
		copy = "Copiar para DiscordSettings",
		tipCopy = "Muestra las líneas para pegar en ServerScriptService → DiscordSettings, para que tus cambios sigan tras un reinicio.",
		copyTitle = "Sustituye estas líneas en DiscordSettings (clic en el cuadro, Ctrl+A, Ctrl+C):",
		limitBox = "0 = sin límite, Enter guarda",
		notNumber = "Escribe un número entero (0 = sin límite).",
		codeTest = "Probar un código",
		codeTestDesc = "Lo que haría canjearlo ahora. No se gasta.",
		tipCodeTest = "Revisa el código como la ventana real (existe, no terminó, cabe en el límite, tus datos tienen dónde guardar la recompensa, aún no canjeado) sin gastarlo.",
		codeBox = "CÓDIGO",
		test = "Probar",
		resOk = "✅ Funciona: %s",
		resInvalid = "❌ No hay un código activo con este nombre.",
		resExpired = "⌛ Este código terminó.",
		resAlready = "🔁 Ya lo canjeaste.",
		resUnsupported = "⚠️ No se puede dar: %s",
		resUnknown = "❓ No se pudo revisar si lo canjeaste (DataStore no respondió). Lo demás bien: %s",
		resCustom = " (lo da tu OnReward)",
		previews = "Vista previa de lo que ven los jugadores",
		tipPreviews = "Solo lo ves tú. No se da, guarda ni envía nada a otros jugadores.",
		showMe = "Muéstramelo",
		prevAnnounce = "Anuncio",
		prevAnnounceDesc = "Un mensaje arriba en la pantalla",
		announceBox = "Texto del anuncio",
		sampleAnnounce = "¡Empieza el fin de semana de monedas dobles!",
		prevGift = "Regalo",
		prevGiftDesc = "Lo que ve un jugador tras /give",
		sampleGift = "¡Gracias por jugar!",
		prevHatch = "Eclosión",
		prevHatchDesc = "Abrir este huevo con las probabilidades de hoy",
		prevEvent = "Icono de evento",
		prevEventDesc = "2x en todas las monedas durante 30 s",
		sampleEvent = "Evento de prueba",
		shown = "Mostrado solo en tu pantalla.",
		myCurrency = "Mi moneda",
		tipMyCurrency = "Solo en Studio: suma o resta a tus propios valores para probar huevos y precios. Si tu juego guarda datos en Studio, también se guarda.",
		ownerForms = "Solo el dueño del juego crea cosas aquí.",
		tipBotForms = "El juego lo hace al momento, solo: el bot de Discord no tiene que estar encendido. Las mismas comprobaciones que en Discord. Si el bot está encendido, escribe cada cambio en tu canal de registro de Discord.",
		saving = "Guardando en el juego…",
		factorBox = "o escribe p. ej. 2.5",
		animation = "Animación",
		noAnimation = "— ninguna —",
		anim_coin_storm = "💰 Coin Storm (tormenta de monedas)",
		anim_aurora = "🌌 Aurora (aurora boreal)",
		anim_lucky_breeze = "🍀 Lucky Breeze (brisa de la suerte)",
		anim_meteor_shower = "☄️ Meteor Shower (lluvia de meteoros)",
		anim_sakura_festival = "🌸 Sakura Festival (festival del cerezo)",
		previewAnimation = "Vista previa",
		tipPreviewAnimation = "Muestra la animación unos segundos, solo en tu pantalla. Para los jugadores no empieza nada.",
		pickAnimation = "Elige primero una animación.",
		previewAnimationShown = "La vista previa se ve unos segundos en tu pantalla.",
		scope = "Dónde",
		allServers = "Todos los servidores",
		thisServer = "Este servidor",
		tipThisServer = "Solo en este servidor, hasta que termine o el servidor se cierre. Los otros servidores y el bot no lo ven.",
		eventStartedHere = "El evento %s empieza en 10 s en este servidor por %s.",
		badMultiplier = "El multiplicador debe ser un número de 1.1 a %s (p. ej. 2 o 2.5).",
		setEffects = "Animaciones de eventos",
		setEffectsDesc = "Completas, ligeras o apagadas",
		tipSetEffects = "Cuánto ven los jugadores de las animaciones de eventos. Los móviles y los gráficos bajos siempre tienen la versión ligera.",
		effectsFull = "Completas",
		effectsLight = "Ligeras",
		effectsOff = "Apagadas",
		stillSending = "Un momento: el cambio anterior aún se está guardando.",
		saveFailed = "No se pudo guardar en el juego (%s). Inténtalo en un momento.",
		studioApi = "DataStore está apagado en Studio: Game Settings → Security → Enable Studio Access to API Services, luego inténtalo de nuevo.",
		madeInGame = "🎮 %s",
		madeInGameAnon = "🎮 Panel",
		madeOnDiscord = "💬 Discord",
		tipMadeIn = "Dónde se hizo: 🎮 en este panel (y quién) o 💬 en Discord. Ambos se ven aquí y en Discord.",
		codeAdded = "El código %s ya funciona: %s · válido %s.",
		codeRemoved = "Código %s eliminado: los jugadores ya no pueden canjearlo.",
		eventStarted = "El evento %s empieza en 10 s por %s.",
		eventStopped = "Evento %s detenido.",
		eggCreated = "El huevo %s está en el juego: %s %s.",
		eggMoved = "Huevo %s movido: %s.",
		eggRemoved = "Huevo %s eliminado.",
		giftSent = "Regalo para %s: %s. Lo recibe ahora o cuando vuelva a entrar.",
		announced = "El anuncio está en todos los servidores.",
		announcedHere = "El anuncio está en este servidor.",
		found = "Cuenta: %s (ID %s). Revísala y luego pulsa Banear para banear exactamente esta cuenta.",
		banned = "%s está baneado: %s.",
		unbanned = "%s puede jugar de nuevo.",
		permanentBan = "para siempre",
		badCode = "Un código solo puede tener letras A–Z, dígitos, - y _ (máximo 30).",
		badValue = "Falta algo en el formulario o algo está mal. Rellénalo de nuevo.",
		codeExists = "El código %s ya está activo. Elimínalo primero o elige otro nombre.",
		noReward = "Elige al menos una recompensa: una moneda con cantidad, EXP o un objeto.",
		currencyAmount = "Elige la moneda y escribe su cantidad (las dos cosas o ninguna).",
		tooMuch = "%s es más de lo que el juego permite (MaxCurrencyPerCode en DiscordSettings: %s).",
		unknownName = "%s no está en DiscordCatalog. Elige un nombre de la lista.",
		notFound = "Ya no está en el juego (eliminado o terminado). La pestaña muestra la lista actual.",
		tooManyEvents = "Ya hay %s eventos activos (el máximo). Detén uno primero.",
		tooManyEggs = "Ya hay %s huevos (el máximo). Elimina uno primero.",
		eggExists = "Ya hay un huevo llamado %s.",
		badPets = "Escribe las mascotas así: Cat:60, Dog:35, Dragon:5 (mal: %s).",
		petTwice = "%s está dos veces en la lista.",
		tooManyPets = "Como máximo %s mascotas en un huevo.",
		unknownPets = "No están en DiscordCatalog: %s. Usa los nombres exactos del catálogo.",
		badSpot = "Este juego no tiene un sitio para huevos llamado %s.",
		noPlayer = "No se encontró la cuenta de Roblox %s. Revisa cómo está escrita (si está bien, puede que Roblox no respondiera: inténtalo de nuevo).",
		ambiguous = "%s es el ID de una cuenta y el nombre de otra. Escribe el nombre de usuario.",
		hasLink = "El texto tiene un enlace: Roblox lo muestra como #### a todos los jugadores. Escríbelo sin el enlace.",
		banSelf = "No puedes banearte a ti mismo ni al dueño del juego.",
		banOff = "Los baneos están apagados en este juego: en Studio selecciona Players en el Explorer, activa BanningEnabled en Properties y publica el juego.",
		robloxBusy = "Roblox no respondió (%s). Inténtalo en un momento.",
		longText = "%s: como máximo %s caracteres.",
		changeError = "Algo salió mal (los detalles están en la pestaña Log). No se cambió nada.",
		warnRobux = "⚠️ %s se puede comprar con Robux: Roblox no permite darlo en códigos publicados fuera de Roblox (por ejemplo en Discord).",
		warnRobuxGift = "⚠️ %s se puede comprar con Robux: está bien como compensación, pero no como premio de un concurso fuera de Roblox.",
		warnLink = "⚠️ El mensaje parece un enlace: Roblox puede mostrarlo como ####.",
		warnStudioBan = "ℹ️ En Studio un baneo solo se comprueba: funciona en el juego publicado.",
		warnNoSpots = "⚠️ El juego aún no tiene sitios para huevos: el huevo aparece cuando una pieza recibe la etiqueta DiscordEggSpot.",
		warnNotTold = "⚠️ No se pudo avisar a los otros servidores (%s).",
		fillIn = "Rellena: %s",
		create = "Crear",
		send = "Enviar",
		remove = "Quitar",
		sure = "¿Seguro?",
		noneOption = "— ninguna —",
		noEnd = "Sin final",
		day = "día",
		days = "días",
		permanent = "Permanente",
		newCode = "Nuevo código",
		codeName = "Código",
		codeNameBox = "VERANO24",
		currency = "Moneda",
		amount = "Cantidad",
		exp = "EXP",
		item = "Objeto",
		validFor = "Válido",
		newEvent = "Nuevo evento",
		name = "Nombre",
		eventNameBox = "Fin de semana x2",
		boost = "Aumento",
		allCurrencies = "Todas las monedas",
		luck = "Suerte (mascotas raras)",
		howLong = "Duración",
		startEvent = "Iniciar evento",
		stop = "Parar",
		newEgg = "Nuevo huevo",
		eggNameBox = "Huevo de lava",
		priceLabel = "Precio",
		pets = "Mascotas : prob.",
		petsBox = "Cat:60, Dog:35, Dragon:5",
		spot = "Lugar",
		anySpot = "Cualquier lugar libre",
		lasts = "Dura",
		moveTo = "Mover",
		giftForm = "Regalo a un jugador",
		player = "Jugador",
		playerBox = "Nombre o ID",
		message = "Mensaje",
		messageBox = "¡Gracias por jugar!",
		announceForm = "Anuncio",
		announceText = "Texto",
		onScreen = "En pantalla",
		banForm = "Banear a un jugador",
		banFor = "Durante",
		reason = "Motivo",
		reasonBox = "Usar exploits",
		banButton = "Banear",
		checkAccount = "Comprobar cuenta",
		banAccount = "Banear a %s",
		itemTime = "Objeto por",
		unbanButton = "Quitar ban",
		tipTitle = "ⓘ ¿Qué hace?",
		loading = "Cargando...",
		failed = "El servidor no respondió. Inténtalo otra vez.",
		denied = "Este panel es solo para el dueño del juego.",
		wait = "Espera %d s e inténtalo otra vez.",
		studioOnly = "Solo en Studio: en el juego publicado permitiría canjear un código una y otra vez.",
		kitLine = "Kit v%s · %s",
		inStudio = "Studio",
		inLive = "Servidor real",
		tileCodes = "Códigos activos",
		tileEvents = "Eventos ahora",
		tileEggs = "Huevos",
		tileVersion = "Archivo de Studio",
		tipTiles = "Lo que tiene este servidor ahora. Códigos, eventos y huevos llegan de Discord unos segundos después de que el bot los guarda.",
		whereTitle = "Dónde funciona",
		whereStudio = "En Studio: aquí solo juegas tú",
		whereLive = "En el juego publicado",
		tipWhere = "En Studio también tienes los botones de prueba que el juego publicado bloquea (p. ej. Olvidar un código canjeado).",
		hooksTitle = "Tus propias funciones",
		hooksDesc = "Definidas en tus scripts",
		tipHooks = "OnReward, OnSpend, OnHatch y OnAnnouncement son funciones que tus scripts pueden definir para que el kit use tus datos o ventanas. ✅ = definida.",
		limitTitle = "Máximo de moneda por código",
		limitDesc = "Un código o regalo mayor se rechaza",
		noLimit = "sin límite",
		tipLimit = "Un código o regalo de Discord que da más moneda que esto se rechaza y no se gasta. 0 = sin límite. Se cambia en DiscordSettings.",
		refresh = "Actualizar desde Discord",
		reload = "Actualizar",
		more = "Más",
		tipRefresh = "Lee ahora mismo los códigos, eventos y huevos del bot, sin esperar la próxima actualización.",
		refreshed = "Actualizado: %s códigos, %s eventos, %s huevos.",
		noCodes = "Aún no hay códigos activos.",
		noCodesHint = "Añade uno en Discord: /setup-roblox → Códigos promocionales.",
		canGive = "✅ Te funciona",
		cantGive = "⚠️ Bloqueado",
		tipCant = "Ahora no se te puede dar: %s",
		tipCan = "Tus datos de jugador tienen todo lo que da este código, así que canjearlo funciona.",
		tipCustom = "Tu propia función OnReward da las recompensas, así que el kit no revisa aquí tus datos de jugador.",
		expires = "termina en %s",
		forever = "sin final",
		expiredCode = "caducado",
		forget = "Olvidar",
		tipForget = "Solo en Studio: olvida que canjeaste este código para que puedas probarlo otra vez.",
		forgotten = "Listo: puedes canjear %s otra vez.",
		noEvents = "No hay eventos activos.",
		noEventsHint = "Inicia uno en Discord: /event-start.",
		left = "quedan %s",
		startsIn = "empieza en %d s (cuenta atrás de los jugadores)",
		event = "Evento",
		yourCode = "Lo que tu código recibe ahora",
		tipYourCode = "Live.GetMultiplier(nombre) en tus scripts devuelve ahora este número.",
		noUsed = "Tu código aún no ha llamado a Live.GetMultiplier (lo hace al dar moneda o EXP).",
		noEggs = "No hay huevos en los soportes.",
		noEggsHint = "Añade uno en Discord: /egg-create.",
		price = "Precio %s %s",
		simulate = "Simular %d",
		tipSimulate = "Abre el huevo muchas veces con las probabilidades actuales y solo cuenta los resultados. No se da nada.",
		openEgg = "Abrir",
		tipOpen = "Una compra normal por el precio del huevo, como cualquier jugador. El resultado aparece abajo en la pantalla.",
		opened = "Abriendo... el resultado aparece abajo en la pantalla.",
		simulation = "%d aperturas (no se dio nada):",
		giftsTitle = "Regalos pendientes",
		giftsDesc = "Los regalos de /give esperan a que el jugador entre",
		tipGifts = "Los regalos pendientes llegan unos segundos después de entrar. Este botón te da los tuyos al momento.",
		deliver = "Entregar los míos",
		delivered = "Se pidieron tus regalos pendientes: si hay, llegan en un momento.",
		values = "Valores en tus datos de jugador",
		tipValues = "Solo estos valores pueden cambiar los códigos y regalos. Los nombres vienen de tu juego.",
		attributes = "Atributos de tu jugador",
		noValues = "No se encontró nada. El juego crea los datos un momento después de entrar: abre esta pestaña otra vez.",
		setButton = "Botón de códigos",
		setButtonDesc = "Muestra el botón Códigos en la pantalla",
		tipSetButton = "Apagado = oculto, p. ej. si abres la ventana de códigos desde tu propio menú.",
		on = "SÍ",
		off = "NO",
		setPosition = "Posición del botón",
		setPositionDesc = "Dónde está el botón Códigos",
		setManagerPos = "Botón Manager",
		setManagerPosDesc = "Dónde está este botón ⚙️ Manager",
		setEventPos = "Iconos de eventos",
		setEventPosDesc = "Dónde están los iconos redondos de los eventos",
		setAnnouncePos = "Anuncios",
		setAnnouncePosDesc = "Dónde salen los anuncios de Discord",
		setNotifyPos = "Avisos",
		setNotifyPosDesc = "Dónde salen los mensajes de regalos y mascotas",
		offsetBox = "x, y",
		tipPlace = "Elige un lugar y muévelo con píxeles en el cuadro: primero a la derecha (+) o a la izquierda (-), luego abajo (+) o arriba (-); p. ej. 0, -80 = 80 px más arriba. Enter guarda.",
		badOffset = "Escribe dos números enteros, p. ej. 0, -80.",
		filterHidden = "🔒 El filtro de texto de Roblox ocultó esta línea",
		refused = "El servidor lo rechazó (ese valor no se permite aquí).",
		studioOnlyCurrency = "Solo en Studio: en el juego publicado sería moneda gratis.",
		tipSetPosition = "Left, Right, Top, Bottom o una esquina como TopLeft. Una ventana de tu propia plantilla en StarterGui mantiene su propio lugar para el botón.",
		setLanguage = "Idioma de los jugadores",
		setLanguageDesc = "Ventana, eventos y mensajes",
		tipSetLanguage = "Auto = cada jugador recibe el idioma de su configuración de Roblox (inglés, polaco o español).",
		auto = "Auto (jugador)",
		setHelpers = "Manager para ayudantes",
		setHelpersDesc = "Quién más puede abrir este panel",
		tipSetHelpers = "Se elige en la pestaña 🛡️ (busca un jugador por su nombre y marca lo que puede hacer) o en Discord: /setup → 🛡️ Permisos. El dueño del juego siempre lo tiene todo.",
		helpers = "%d más",
		onlyYou = "Solo tú",
		settingsNote = "Los cambios funcionan al momento solo en este servidor. Para conservarlos tras un reinicio, cópialos en DiscordSettings.",
		noLog = "Aún no hay mensajes del kit.",
		logInfo = "Líneas del kit de la ventana Output, las más nuevas abajo",
	},
	pl = {
		open = "Manager",
		owner = "WŁAŚCICIEL",
		tabs = { "Start", "Kody", "Eventy", "Jajka", "Prezenty i ogłoszenia", "Gracze", "Ustawienia", "Testy", "Log",
			"Dostęp do Managera" },
		subtitles = { "ten serwer teraz", "z Discorda", "trwają teraz", "na stojakach", "z Discorda",
			"Twoje dane gracza", "na żywo na tym serwerze", "widzisz je tylko Ty", "komunikaty zestawu", "kto może używać tego panelu" },
		ownerOnly = "To może zrobić tylko właściciel gry.",
		noPermission = "Nie możesz tego zrobić. Właściciel gry nadaje uprawnienia w zakładce 🛡️ albo na Discordzie (/setup → 🛡️ Uprawnienia).",
		accessFind = "Znajdź gracza",
		accessFindDesc = "Jego nazwa użytkownika Roblox (nie wyświetlana)",
		tipAccessFind = "Wpisz nazwę i naciśnij Enter albo Znajdź. Potem zaznacz, co może robić, i kliknij Zapisz. Od razu dostaje przycisk ⚙️ Manager, tylko z tymi zakładkami.",
		accessNameBox = "nazwa",
		find = "Znajdź",
		accessEdit = "Co może %s",
		accessEditDesc = "Zaznaczone = widzi tę zakładkę i może jej używać. Start jest zawsze.",
		accessSave = "Zapisz",
		cancel = "Anuluj",
		accessRemove = "Odbierz dostęp",
		accessSaved = "Zapisano: %s ma Managera z tym, co zaznaczyłeś.",
		accessRemoved = "%s nie ma już Managera.",
		accessListTitle = "Kto ma Managera (%d z %d)",
		accessNone = "Tylko Ty",
		accessNoneHint = "Znajdź gracza wyżej, żeby dać mu Managera.",
		accessNothing = "tylko Start",
		accessNotFound = "Nie ma konta Roblox o tej nazwie. Sprawdź pisownię (nazwa użytkownika, nie wyświetlana).",
		accessOwner = "To Ty (właściciel): zawsze masz wszystko.",
		accessFull = "Najwyżej 25 graczy. Najpierw kogoś usuń.",
		accessFailed = "Roblox tego nie zapisał. Spróbuj za chwilę.",
		accessStudio = "W Studio potrzebne jest: Game Settings → Security → Enable Studio Access to API Services.",
		accessDiscordNote = "Ta sama lista co na Discordzie (/setup → 🛡️ Uprawnienia → Manager w grze): zmiana tutaj pokaże się też tam.",
		edit = "Zmień",
		perms = { codes = "Kody", events = "Eventy", eggs = "Jajka", gifts = "Prezenty", announce = "Ogłoszenia", bans = "Bany",
			settings = "Ustawienia" },
		giftSelf = "Nie możesz wysłać prezentu samemu sobie.",
		changed = "%s zmienione na tym serwerze. Żeby zostało po restarcie, skopiuj to do DiscordSettings.",
		reset = "Przywróć",
		tipReset = "Wraca do wartości z DiscordSettings na tym serwerze.",
		resetDone = "Przywrócone wartości z DiscordSettings.",
		copy = "Kopiuj do DiscordSettings",
		tipCopy = "Pokazuje linie do wklejenia w ServerScriptService → DiscordSettings, żeby zmiany zostały po restarcie.",
		copyTitle = "Podmień te linie w DiscordSettings (kliknij w pole, Ctrl+A, Ctrl+C):",
		limitBox = "0 = bez limitu, Enter zapisuje",
		notNumber = "Wpisz liczbę całkowitą (0 = bez limitu).",
		codeTest = "Sprawdź kod",
		codeTestDesc = "Co dałoby odebranie go teraz. Kod się nie zużywa.",
		tipCodeTest = "Sprawdza kod jak prawdziwe okienko (istnieje, nie wygasł, mieści się w limicie, Twoje dane mają miejsce na nagrodę, jeszcze nieodebrany), ale go nie zużywa.",
		codeBox = "KOD",
		test = "Sprawdź",
		resOk = "✅ Działa: %s",
		resInvalid = "❌ Nie ma aktywnego kodu o tej nazwie.",
		resExpired = "⌛ Ten kod już wygasł.",
		resAlready = "🔁 Już go odebrałeś.",
		resUnsupported = "⚠️ Nie da się go dać: %s",
		resUnknown = "❓ Nie udało się sprawdzić, czy go odebrałeś (DataStore nie odpowiedział). Reszta w porządku: %s",
		resCustom = " (daje go Twoje OnReward)",
		previews = "Podgląd tego, co widzą gracze",
		tipPreviews = "Widzisz to tylko Ty. Nic nie jest dawane, zapisywane ani wysyłane innym graczom.",
		showMe = "Pokaż mi",
		prevAnnounce = "Ogłoszenie",
		prevAnnounceDesc = "Wiadomość u góry ekranu",
		announceBox = "Tekst ogłoszenia",
		sampleAnnounce = "Weekend z podwójnymi monetami właśnie się zaczyna!",
		prevGift = "Prezent",
		prevGiftDesc = "Co gracz widzi po /give",
		sampleGift = "Dzięki za grę!",
		prevHatch = "Wyklucie",
		prevHatchDesc = "Otwarcie tego jajka z dzisiejszymi szansami",
		prevEvent = "Ikona eventu",
		prevEventDesc = "2x na każdą walutę przez 30 s",
		sampleEvent = "Testowy event",
		shown = "Pokazane tylko na Twoim ekranie.",
		myCurrency = "Moja waluta",
		tipMyCurrency = "Tylko w Studio: dodaje albo odejmuje z Twoich wartości, żeby testować jajka i ceny. Jeśli Twoja gra zapisuje dane w Studio, to też się zapisze.",
		ownerForms = "Tworzyć rzeczy może tu tylko właściciel gry.",
		tipBotForms = "Gra robi to od razu, sama: bot na Discordzie nie musi działać. Te same sprawdzenia co na Discordzie. Gdy bot działa, zapisuje każdą zmianę na kanale logów na Discordzie.",
		saving = "Zapisuję w grze…",
		factorBox = "albo wpisz np. 2.5",
		animation = "Animacja",
		noAnimation = "— brak —",
		anim_coin_storm = "💰 Coin Storm (burza monet)",
		anim_aurora = "🌌 Aurora (zorza polarna)",
		anim_lucky_breeze = "🍀 Lucky Breeze (wiatr szczęścia)",
		anim_meteor_shower = "☄️ Meteor Shower (deszcz meteorów)",
		anim_sakura_festival = "🌸 Sakura Festival (święto kwitnącej wiśni)",
		previewAnimation = "Podgląd",
		tipPreviewAnimation = "Pokazuje animację przez kilka sekund, tylko na Twoim ekranie. Graczom nic się nie włącza.",
		pickAnimation = "Najpierw wybierz animację.",
		previewAnimationShown = "Podgląd leci przez kilka sekund na Twoim ekranie.",
		scope = "Gdzie",
		allServers = "Wszystkie serwery",
		thisServer = "Ten serwer",
		tipThisServer = "Tylko na tym serwerze, do końca eventu albo wyłączenia serwera. Inne serwery i bot go nie widzą.",
		eventStartedHere = "Event %s rusza za 10 s na tym serwerze na %s.",
		badMultiplier = "Mnożnik musi być liczbą od 1.1 do %s (np. 2 albo 2.5).",
		setEffects = "Animacje eventów",
		setEffectsDesc = "Pełne, lekkie albo wyłączone",
		tipSetEffects = "Ile animacji eventów widzą gracze. Telefony i słaba grafika zawsze dostają lekką wersję.",
		effectsFull = "Pełne",
		effectsLight = "Lekkie",
		effectsOff = "Wyłączone",
		stillSending = "Chwila: poprzednia zmiana jeszcze się zapisuje.",
		saveFailed = "Nie udało się zapisać w grze (%s). Spróbuj za moment.",
		studioApi = "DataStore jest wyłączony w Studio: Game Settings → Security → Enable Studio Access to API Services, potem spróbuj jeszcze raz.",
		madeInGame = "🎮 %s",
		madeInGameAnon = "🎮 Panel",
		madeOnDiscord = "💬 Discord",
		tipMadeIn = "Gdzie to powstało: 🎮 w tym panelu (i kto) albo 💬 na Discordzie. Jedno i drugie widać tutaj i na Discordzie.",
		codeAdded = "Kod %s działa: %s · ważny %s.",
		codeRemoved = "Kod %s usunięty: gracze już go nie wpiszą.",
		eventStarted = "Event %s rusza za 10 s na %s.",
		eventStopped = "Event %s zatrzymany.",
		eggCreated = "Jajko %s jest w grze: %s %s.",
		eggMoved = "Jajko %s przeniesione: %s.",
		eggRemoved = "Jajko %s usunięte.",
		giftSent = "Prezent dla %s: %s. Dostanie go teraz albo przy następnym wejściu.",
		announced = "Ogłoszenie jest na wszystkich serwerach.",
		announcedHere = "Ogłoszenie jest na tym serwerze.",
		found = "Konto: %s (ID %s). Sprawdź je, potem kliknij Zbanuj, żeby zbanować dokładnie to konto.",
		banned = "%s zbanowany: %s.",
		unbanned = "%s może znowu grać.",
		permanentBan = "na zawsze",
		badCode = "Kod może mieć tylko litery A–Z, cyfry, - i _ (najwyżej 30).",
		badValue = "Czegoś w formularzu brakuje albo jest źle. Wypełnij go jeszcze raz.",
		codeExists = "Kod %s już działa. Najpierw go usuń albo wybierz inną nazwę.",
		noReward = "Wybierz chociaż jedną nagrodę: walutę z ilością, EXP albo przedmiot.",
		currencyAmount = "Wybierz walutę i wpisz jej ilość (oba albo żadne).",
		tooMuch = "%s to więcej, niż gra pozwala (MaxCurrencyPerCode w DiscordSettings: %s).",
		unknownName = "%s nie ma w DiscordCatalog. Wybierz nazwę z listy.",
		notFound = "Tego już nie ma w grze (usunięte albo skończone). Zakładka pokazuje aktualną listę.",
		tooManyEvents = "Działa już %s eventów (najwięcej). Najpierw zatrzymaj jeden.",
		tooManyEggs = "Jest już %s jajek (najwięcej). Najpierw usuń jedno.",
		eggExists = "Jest już jajko o nazwie %s.",
		badPets = "Wpisz zwierzaki tak: Cat:60, Dog:35, Dragon:5 (źle: %s).",
		petTwice = "%s jest na liście dwa razy.",
		tooManyPets = "Najwyżej %s zwierzaków w jednym jajku.",
		unknownPets = "Nie ma w DiscordCatalog: %s. Użyj dokładnych nazw z katalogu.",
		badSpot = "Ta gra nie ma miejsca na jajko o nazwie %s.",
		noPlayer = "Nie znaleziono konta Roblox %s. Sprawdź pisownię (jeśli jest dobra, Roblox mógł nie odpowiedzieć: spróbuj jeszcze raz).",
		ambiguous = "%s to ID jednego konta i nazwa innego. Wpisz nazwę użytkownika.",
		hasLink = "Tekst ma link: Roblox pokaże go każdemu graczowi jako ####. Napisz go bez linku.",
		banSelf = "Nie możesz zbanować siebie ani właściciela gry.",
		banOff = "Bany są wyłączone w tej grze: w Studio zaznacz Players w Explorerze, włącz BanningEnabled we właściwościach (Properties) i opublikuj grę.",
		robloxBusy = "Roblox nie odpowiedział (%s). Spróbuj za moment.",
		longText = "%s: najwyżej %s znaków.",
		changeError = "Coś poszło nie tak (szczegóły w zakładce Log). Nic nie zostało zmienione.",
		warnRobux = "⚠️ %s można kupić za Robux: Roblox nie pozwala dawać tego w kodach publikowanych poza Robloxem (np. na Discordzie).",
		warnRobuxGift = "⚠️ %s można kupić za Robux: w porządku jako rekompensata, ale nie jako nagroda w konkursie poza Robloxem.",
		warnLink = "⚠️ Wiadomość wygląda na link: Roblox może pokazać ją jako ####.",
		warnStudioBan = "ℹ️ W Studio ban jest tylko sprawdzany: działa w opublikowanej grze.",
		warnNoSpots = "⚠️ Gra nie ma jeszcze miejsc na jajka: jajko pojawi się, gdy jakaś część dostanie tag DiscordEggSpot.",
		warnNotTold = "⚠️ Nie udało się powiadomić innych serwerów (%s).",
		fillIn = "Uzupełnij: %s",
		create = "Utwórz",
		send = "Wyślij",
		remove = "Usuń",
		sure = "Na pewno?",
		noneOption = "— brak —",
		noEnd = "Bez końca",
		day = "dzień",
		days = "dni",
		permanent = "Na stałe",
		newCode = "Nowy kod",
		codeName = "Kod",
		codeNameBox = "LATO24",
		currency = "Waluta",
		amount = "Ilość",
		exp = "EXP",
		item = "Przedmiot",
		validFor = "Ważny",
		newEvent = "Nowy event",
		name = "Nazwa",
		eventNameBox = "Weekend x2",
		boost = "Bonus",
		allCurrencies = "Wszystkie waluty",
		luck = "Szczęście (rzadkie zwierzaki)",
		howLong = "Jak długo",
		startEvent = "Włącz event",
		stop = "Zatrzymaj",
		newEgg = "Nowe jajko",
		eggNameBox = "Lawowe jajko",
		priceLabel = "Cena",
		pets = "Zwierzaki : szansa",
		petsBox = "Cat:60, Dog:35, Dragon:5",
		spot = "Miejsce",
		anySpot = "Dowolne wolne miejsce",
		lasts = "Trwa",
		moveTo = "Przenieś",
		giftForm = "Prezent dla gracza",
		player = "Gracz",
		playerBox = "Nick albo ID",
		message = "Wiadomość",
		messageBox = "Dzięki za grę!",
		announceForm = "Ogłoszenie",
		announceText = "Tekst",
		onScreen = "Na ekranie",
		banForm = "Zbanuj gracza",
		banFor = "Na",
		reason = "Powód",
		reasonBox = "Oszukiwanie",
		banButton = "Zbanuj",
		checkAccount = "Sprawdź konto",
		banAccount = "Zbanuj %s",
		itemTime = "Przedmiot na",
		unbanButton = "Odbanuj",
		tipTitle = "ⓘ Co to robi?",
		loading = "Wczytuję...",
		failed = "Serwer nie odpowiedział. Spróbuj jeszcze raz.",
		denied = "Ten panel jest tylko dla właściciela gry.",
		wait = "Poczekaj %d s i spróbuj jeszcze raz.",
		studioOnly = "Tylko w Studio: w opublikowanej grze pozwalałoby odbierać jeden kod w kółko.",
		kitLine = "Zestaw v%s · %s",
		inStudio = "Studio",
		inLive = "Serwer gry",
		tileCodes = "Aktywne kody",
		tileEvents = "Eventy teraz",
		tileEggs = "Jajka",
		tileVersion = "Plik do Studio",
		tipTiles = "To, co ten serwer ma teraz. Kody, eventy i jajka przychodzą z Discorda kilka sekund po tym, jak bot je zapisze.",
		whereTitle = "Gdzie działa",
		whereStudio = "W Studio: grasz tu tylko Ty",
		whereLive = "W opublikowanej grze",
		tipWhere = "W Studio masz też przyciski testowe, które opublikowana gra blokuje (np. Zapomnij odebrany kod).",
		hooksTitle = "Twoje własne funkcje",
		hooksDesc = "Ustawiane w Twoich skryptach",
		tipHooks = "OnReward, OnSpend, OnHatch i OnAnnouncement to funkcje, które Twoje skrypty mogą ustawić, żeby zestaw używał Twoich danych albo okienek. ✅ = ustawiona.",
		limitTitle = "Najwięcej waluty z kodu",
		limitDesc = "Większy kod albo prezent jest odrzucany",
		noLimit = "bez limitu",
		tipLimit = "Kod albo prezent z Discorda, który daje więcej waluty, jest odrzucany i się nie zużywa. 0 = bez limitu. Zmienia się w DiscordSettings.",
		refresh = "Odśwież z Discorda",
		reload = "Odśwież",
		more = "Więcej",
		tipRefresh = "Czyta od bota kody, eventy i jajka od razu, zamiast czekać na następną aktualizację.",
		refreshed = "Odświeżone: kody %s, eventy %s, jajka %s.",
		noCodes = "Na razie brak aktywnych kodów.",
		noCodesHint = "Dodaj kod na Discordzie: /setup-roblox → Kody promocyjne.",
		canGive = "✅ Działa u Ciebie",
		cantGive = "⚠️ Zablokowany",
		tipCant = "Teraz nie da się go Tobie dać: %s",
		tipCan = "Twoje dane gracza mają wszystko, co daje ten kod, więc odebranie działa.",
		tipCustom = "Nagrody daje Twoja własna funkcja OnReward, więc zestaw nie sprawdza tu Twoich danych gracza.",
		expires = "kończy się za %s",
		forever = "bez końca",
		expiredCode = "wygasł",
		forget = "Zapomnij",
		tipForget = "Tylko w Studio: zapomina, że odebrałeś ten kod, żebyś mógł go przetestować jeszcze raz.",
		forgotten = "Gotowe: możesz znowu odebrać %s.",
		noEvents = "Żaden event nie trwa.",
		noEventsHint = "Włącz event na Discordzie: /event-start.",
		left = "zostało %s",
		startsIn = "start za %d s (odliczanie u graczy)",
		event = "Event",
		yourCode = "Co Twój kod dostaje teraz",
		tipYourCode = "Live.GetMultiplier(nazwa) w Twoich skryptach zwraca teraz tę liczbę.",
		noUsed = "Twój kod jeszcze nie pytał Live.GetMultiplier (pyta, gdy daje walutę albo EXP).",
		noEggs = "Brak jajek na stojakach.",
		noEggsHint = "Dodaj jajko na Discordzie: /egg-create.",
		price = "Cena %s %s",
		simulate = "Symuluj %d",
		tipSimulate = "Otwiera jajko wiele razy z szansami, jakie gracze mają teraz, i tylko liczy wyniki. Nic nie jest dawane.",
		openEgg = "Otwórz",
		tipOpen = "Zwykły zakup za cenę jajka, jak u każdego gracza. Wynik pojawi się na dole ekranu.",
		opened = "Otwieram... wynik pojawi się na dole ekranu.",
		simulation = "%d otwarć (nic nie zostało dane):",
		giftsTitle = "Czekające prezenty",
		giftsDesc = "Prezenty z /give czekają, aż gracz wejdzie",
		tipGifts = "Czekające prezenty przychodzą kilka sekund po wejściu. Ten przycisk daje Twoje od razu.",
		deliver = "Dostarcz moje teraz",
		delivered = "Poproszono o Twoje czekające prezenty: jeśli są, przyjdą za chwilę.",
		values = "Wartości w Twoich danych gracza",
		tipValues = "Kody i prezenty mogą zmienić tylko te wartości. Nazwy pochodzą z Twojej gry.",
		attributes = "Atrybuty Twojego gracza",
		noValues = "Nic nie znaleziono. Gra tworzy dane gracza chwilę po wejściu: otwórz tę zakładkę jeszcze raz.",
		setButton = "Przycisk kodów",
		setButtonDesc = "Pokazuje przycisk Kody na ekranie",
		tipSetButton = "Wyłączony = ukryty, np. gdy otwierasz okno kodów z własnego menu.",
		on = "WŁ.",
		off = "WYŁ.",
		setPosition = "Miejsce przycisku",
		setPositionDesc = "Gdzie stoi przycisk Kody",
		setManagerPos = "Przycisk Managera",
		setManagerPosDesc = "Gdzie stoi ten przycisk ⚙️ Manager",
		setEventPos = "Ikony eventów",
		setEventPosDesc = "Gdzie są okrągłe ikony eventów",
		setAnnouncePos = "Ogłoszenia",
		setAnnouncePosDesc = "Gdzie pokazują się ogłoszenia z Discorda",
		setNotifyPos = "Powiadomienia",
		setNotifyPosDesc = "Gdzie pokazują się wiadomości o prezentach i zwierzakach",
		offsetBox = "x, y",
		tipPlace = "Wybierz miejsce, a potem przesuń je o piksele w polu: najpierw w prawo (+) lub w lewo (-), potem w dół (+) lub w górę (-), np. 0, -80 = 80 px wyżej. Enter zapisuje.",
		badOffset = "Wpisz dwie liczby całkowite, np. 0, -80.",
		filterHidden = "🔒 Filtr tekstu Robloxa ukrył tę linię",
		refused = "Serwer tego nie przyjął (ta wartość jest tu niedozwolona).",
		studioOnlyCurrency = "Tylko w Studio: w opublikowanej grze byłaby to darmowa waluta.",
		tipSetPosition = "Left, Right, Top, Bottom albo róg, np. TopLeft. Okienko z Twojego szablonu w StarterGui ma swoje własne miejsce na przycisk.",
		setLanguage = "Język graczy",
		setLanguageDesc = "Okno, eventy i wiadomości",
		tipSetLanguage = "Auto = każdy gracz dostaje język ze swoich ustawień Roblox (angielski, polski albo hiszpański).",
		auto = "Auto (gracz)",
		setHelpers = "Manager dla pomocników",
		setHelpersDesc = "Kto poza Tobą może otworzyć ten panel",
		tipSetHelpers = "Ustawiasz to w zakładce 🛡️ (znajdź gracza po nazwie i zaznacz, co może) albo na Discordzie: /setup → 🛡️ Uprawnienia. Właściciel gry ma zawsze wszystko.",
		helpers = "jeszcze %d",
		onlyYou = "Tylko Ty",
		settingsNote = "Zmiany działają od razu, tylko na tym serwerze. Żeby zostały po restarcie, skopiuj je do DiscordSettings.",
		noLog = "Na razie brak komunikatów zestawu.",
		logInfo = "Linie zestawu z okna Output, najnowsze na dole",
	},
}
local LANGUAGES = { { code = "en", name = "English" }, { code = "es", name = "Español" }, { code = "pl", name = "Polski" } }
local ICONS = { "🏠", "🎟️", "⚡", "🥚", "🎁", "👤", "⚙️", "🧪", "📜", "🛡️" }
local POSITIONS = { "Left", "Right", "Top", "Bottom", "Center", "TopLeft", "TopRight", "BottomLeft", "BottomRight" }

local language = "en"
local T = TEXTS.en

-- ---------- Look: purple game-style settings window ----------
local WINDOW = Color3.fromRGB(26, 15, 44)
local CARD = Color3.fromRGB(34, 20, 58)
local CARD_EDGE = Color3.fromRGB(92, 56, 168)
local TAB = Color3.fromRGB(34, 20, 58)
local TAB_EDGE = Color3.fromRGB(86, 54, 156)
local FIELD = Color3.fromRGB(18, 10, 32)
local GLOW = Color3.fromRGB(170, 100, 255)
local PINK = Color3.fromRGB(224, 107, 255)
local VIOLET = Color3.fromRGB(138, 68, 255)
local LIGHT_EDGE = Color3.fromRGB(245, 214, 255)
local INK = Color3.fromRGB(255, 255, 255)
local SOFT = Color3.fromRGB(201, 184, 255) -- second line of a row
local MUTED = Color3.fromRGB(168, 151, 214)
local GOLD = Color3.fromRGB(255, 200, 61)
local GREEN = Color3.fromRGB(70, 209, 106)
local RED = Color3.fromRGB(255, 107, 138)
local GRADIENTS = {
	primary = { Color3.fromRGB(198, 136, 255), Color3.fromRGB(126, 68, 236) },
	pink = { Color3.fromRGB(255, 130, 172), Color3.fromRGB(228, 60, 118) },
	green = { Color3.fromRGB(70, 209, 106), Color3.fromRGB(35, 160, 71) },
	red = { Color3.fromRGB(255, 107, 138), Color3.fromRGB(224, 51, 90) },
	gold = { Color3.fromRGB(255, 200, 61), Color3.fromRGB(232, 162, 26) },
}
local HEAVY = Font.new("rbxasset://fonts/families/Nunito.json", Enum.FontWeight.Heavy)
local BOLD = Font.new("rbxasset://fonts/families/Nunito.json", Enum.FontWeight.Bold)
local CODE_FONT = Font.new("rbxasset://fonts/families/RobotoMono.json", Enum.FontWeight.Medium)
local TITLE_FONT = Font.fromEnum(Enum.Font.FredokaOne) -- only for "MANAGER" (it has no Polish letters)
local WIDTH, HEIGHT = 900, 600

-- Capital letters also for Polish and Spanish letters (string.upper changes only a-z: "Tęczowe" would be "TęCZOWE")
local CAPITALS = { ["ą"] = "Ą", ["ć"] = "Ć", ["ę"] = "Ę", ["ł"] = "Ł", ["ń"] = "Ń", ["ó"] = "Ó", ["ś"] = "Ś", ["ź"] = "Ź", ["ż"] = "Ż",
	["á"] = "Á", ["é"] = "É", ["í"] = "Í", ["ú"] = "Ú", ["ü"] = "Ü", ["ñ"] = "Ñ" }
local function upper(text)
	return (string.gsub(string.upper(tostring(text)), "[\195\196\197][\128-\191]", function(letter)
		return CAPITALS[letter] or letter
	end))
end

local function make(class, props, parent)
	local instance = Instance.new(class)
	for key, value in pairs(props) do
		instance[key] = value
	end
	instance.Parent = parent
	return instance
end

local function rounded(instance, radius)
	make("UICorner", { CornerRadius = UDim.new(0, radius) }, instance)
end

local function outline(instance, color, thickness)
	return make("UIStroke", { Color = color or CARD_EDGE, Thickness = thickness or 1, ApplyStrokeMode = Enum.ApplyStrokeMode.Border }, instance)
end

-- A UIGradient colors the object's own text too, so only frames without text get one; a button or label gets the middle color
local function shade(instance, colors)
	if not instance:IsA("Frame") then
		instance.BackgroundColor3 = colors[1]:Lerp(colors[2], 0.45)
		return
	end
	instance.BackgroundColor3 = INK
	make("UIGradient", { Color = ColorSequence.new(colors[1], colors[2]), Rotation = 90 }, instance)
end

local function padding(instance, vertical, horizontal)
	make("UIPadding", { PaddingTop = UDim.new(0, vertical), PaddingBottom = UDim.new(0, vertical),
		PaddingLeft = UDim.new(0, horizontal), PaddingRight = UDim.new(0, horizontal) }, instance)
end

local function list(instance, direction, gap, align)
	return make("UIListLayout", { FillDirection = direction or Enum.FillDirection.Vertical, Padding = UDim.new(0, gap or 0),
		SortOrder = Enum.SortOrder.LayoutOrder, VerticalAlignment = align or Enum.VerticalAlignment.Top }, instance)
end

local function text(parent, value, size, color, font, props)
	local label = make("TextLabel", {
		BackgroundTransparency = 1,
		Size = UDim2.fromScale(0, 0),
		AutomaticSize = Enum.AutomaticSize.XY,
		FontFace = font or BOLD,
		TextSize = size,
		TextColor3 = color or INK,
		TextXAlignment = Enum.TextXAlignment.Left,
		Text = value,
	}, parent)
	for key, prop in pairs(props or {}) do
		label[key] = prop
	end
	return label
end

gui.ResetOnSpawn = false
gui.DisplayOrder = 70
gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
local ownSettings = gui:FindFirstChild("Settings") -- a copy of the kit's settings, from the server


-- ---------- The look of the MANAGER game button (drawn in Figma) for every violet part of the window ----------
-- left to right from blue to violet, a shine on the top, a darker bottom and a light rim
local MANAGER_LOOK = { Color3.fromRGB(64, 138, 240), Color3.fromRGB(98, 100, 232), Color3.fromRGB(118, 56, 204) }
local RIM = Color3.fromRGB(176, 186, 255)

local function lookColors(colors)
	if #colors >= 3 then
		return ColorSequence.new({ ColorSequenceKeypoint.new(0, colors[1]), ColorSequenceKeypoint.new(0.45, colors[2]),
			ColorSequenceKeypoint.new(1, colors[3]) })
	end
	return ColorSequence.new(colors[1], colors[2])
end

-- the shine and the darker bottom: two layers inside `host`, under its own children (ZIndex 0); returns them
local function glossLayers(host, radius)
	local function layer(name, color, keys)
		local item = make("Frame", { Name = name, Size = UDim2.fromScale(1, 1), BackgroundColor3 = color, BorderSizePixel = 0,
			ZIndex = 0 }, host)
		rounded(item, radius)
		make("UIGradient", { Rotation = 90, Transparency = NumberSequence.new(keys) }, item)
		return item
	end
	local dark = layer("Shade", Color3.fromRGB(24, 8, 86), { NumberSequenceKeypoint.new(0, 1), NumberSequenceKeypoint.new(0.4, 1),
		NumberSequenceKeypoint.new(1, 0.3) })
	local shine = layer("Shine", INK, { NumberSequenceKeypoint.new(0, 0.6), NumberSequenceKeypoint.new(0.18, 0.75),
		NumberSequenceKeypoint.new(0.42, 1), NumberSequenceKeypoint.new(1, 1) })
	return { dark, shine }
end

-- the light rim: white on the top, light lavender below (a UIStroke, its gradient is returned)
local function rim(host, thickness)
	for _, child in ipairs(host:GetChildren()) do
		if child:IsA("UIStroke") then
			child:Destroy()
		end
	end
	local stroke = make("UIStroke", { Color = INK, Thickness = thickness or 2, ApplyStrokeMode = Enum.ApplyStrokeMode.Border }, host)
	local shade = make("UIGradient", { Rotation = 90, Color = ColorSequence.new({ ColorSequenceKeypoint.new(0, INK),
		ColorSequenceKeypoint.new(0.3, RIM), ColorSequenceKeypoint.new(1, RIM) }) }, stroke)
	return stroke, shade
end

-- A frame (without its own text) in the button's look; returns its color gradient
local function glossyFrame(frame, colors, radius)
	frame.BackgroundColor3 = INK
	frame.BackgroundTransparency = 0
	local shade = make("UIGradient", { Color = lookColors(colors) }, frame)
	glossLayers(frame, radius)
	rim(frame)
	return shade
end

-- A button or label with text in the button's look: a UIGradient would tint its text, so the look is a frame under
-- it and the text is shown by a label above it (it follows the button's Text when that changes)
local function glossyText(object, colors, radius)
	object.BackgroundTransparency = 1
	for _, child in ipairs(object:GetChildren()) do
		if child:IsA("UIStroke") then
			child:Destroy()
		end
	end
	-- the layers would make an automatic size grow: the width follows the text instead (and its padding, now removed)
	local pad = object:FindFirstChildOfClass("UIPadding")
	local px = pad and pad.PaddingLeft.Offset or 0
	if pad then
		pad:Destroy()
	end
	if object.AutomaticSize ~= Enum.AutomaticSize.None then
		object.AutomaticSize = Enum.AutomaticSize.None
		local function fit()
			object.Size = UDim2.new(0, math.ceil(object.TextBounds.X) + 2 * px, object.Size.Y.Scale, object.Size.Y.Offset)
		end
		object:GetPropertyChangedSignal("TextBounds"):Connect(fit)
		fit()
	end
	local skin = make("Frame", { Name = "Skin", Size = UDim2.fromScale(1, 1), ZIndex = object.ZIndex }, object)
	rounded(skin, radius)
	glossyFrame(skin, colors, radius)
	local caption = make("TextLabel", { Name = "Caption", BackgroundTransparency = 1, Size = UDim2.fromScale(1, 1),
		FontFace = object.FontFace, TextSize = object.TextSize, TextColor3 = object.TextColor3, Text = object.Text,
		TextXAlignment = object.TextXAlignment, TextYAlignment = object.TextYAlignment, TextWrapped = object.TextWrapped,
		TextScaled = object.TextScaled, TextStrokeColor3 = Color3.fromRGB(30, 22, 90), TextStrokeTransparency = 0.55,
		ZIndex = object.ZIndex + 1 }, object)
	object.TextTransparency = 1
	object:GetPropertyChangedSignal("Text"):Connect(function()
		caption.Text = object.Text
	end)
	return skin
end

-- ---------- Tooltip (hover a row, or tap its title on a phone) ----------
local openMenu = nil -- the list of a dropdown in a row (no tooltips over it), closed with the tab
local tip = make("Frame", {
	Name = "Tooltip",
	BackgroundColor3 = INK,
	Size = UDim2.fromOffset(300, 0),
	AutomaticSize = Enum.AutomaticSize.Y,
	ZIndex = 50,
	Visible = false,
}, gui)
rounded(tip, 10)
outline(tip, GLOW, 2)
padding(tip, 10, 12)
list(tip, nil, 4)
local tipTitle = text(tip, "", 14, VIOLET, HEAVY, { ZIndex = 51 })
local tipBody = text(tip, "", 14, Color3.fromRGB(40, 24, 70), BOLD, {
	ZIndex = 51, AutomaticSize = Enum.AutomaticSize.Y, Size = UDim2.fromScale(1, 0), TextWrapped = true, LayoutOrder = 2 })
local tipOwner = nil

local function placeTip(x, y)
	local screen = gui.AbsoluteSize
	local size = tip.AbsoluteSize
	tip.Position = UDim2.fromOffset(math.clamp(x + 18, 4, screen.X - size.X - 4), math.clamp(y + 18, 4, screen.Y - size.Y - 4))
end

local function showTip(owner, value)
	if openMenu then
		return
	end
	tipOwner = owner
	tipTitle.Text = T.tipTitle
	tipBody.Text = value
	tip.Visible = true
	local mouse = UserInputService:GetMouseLocation() - GuiService:GetGuiInset()
	placeTip(mouse.X, mouse.Y)
end

local function hideTip(owner)
	if owner == nil or tipOwner == owner then
		tip.Visible = false
		tipOwner = nil
	end
end

UserInputService.InputChanged:Connect(function(input)
	if tip.Visible and input.UserInputType == Enum.UserInputType.MouseMovement then
		local mouse = UserInputService:GetMouseLocation() - GuiService:GetGuiInset()
		placeTip(mouse.X, mouse.Y)
	end
end)

-- A touch fires MouseEnter but never MouseLeave: on a phone tips come only from a tap on a row's title, and any new
-- touch hides the open one (the title's tap shows it again right after)
local function byMouse()
	return UserInputService:GetLastInputType() ~= Enum.UserInputType.Touch
end
UserInputService.InputBegan:Connect(function(input)
	if input.UserInputType == Enum.UserInputType.Touch then
		hideTip()
	end
end)

local function attachTip(object, value)
	if not value or value == "" then
		return
	end
	object.MouseEnter:Connect(function()
		if byMouse() then
			showTip(object, value)
		end
	end)
	object.MouseLeave:Connect(function()
		hideTip(object)
	end)
	object.Destroying:Connect(function()
		hideTip(object)
	end)
end

-- ---------- Buttons and chips ----------
-- kind: "primary", "green", "red", "gold" (colored) or "ghost" (dark with an outline)
local function button(parent, label, kind, tipText, height)
	local item = make("TextButton", {
		Size = UDim2.fromOffset(0, height or 34),
		AutomaticSize = Enum.AutomaticSize.X,
		AutoButtonColor = true,
		BackgroundColor3 = FIELD,
		FontFace = HEAVY,
		TextSize = 14,
		TextColor3 = INK,
		Text = label,
	}, parent)
	rounded(item, 10)
	padding(item, 0, 14)
	if kind == "primary" then
		glossyText(item, MANAGER_LOOK, 10)
	elseif GRADIENTS[kind] then
		shade(item, GRADIENTS[kind])
		outline(item, LIGHT_EDGE, 1).Transparency = 0.3
	else
		item.TextColor3 = SOFT
		outline(item, Color3.fromRGB(74, 51, 128))
	end
	attachTip(item, tipText)
	return item
end

local function chip(parent, label, color, tipText)
	local item = make("TextLabel", {
		Size = UDim2.fromOffset(0, 26),
		AutomaticSize = Enum.AutomaticSize.X,
		BackgroundColor3 = color or FIELD,
		BackgroundTransparency = color and 0.78 or 0,
		FontFace = HEAVY,
		TextSize = 13,
		TextColor3 = color or SOFT,
		Text = label,
	}, parent)
	rounded(item, 13)
	padding(item, 0, 11)
	outline(item, color or Color3.fromRGB(74, 51, 128)).Transparency = color and 0.35 or 0
	attachTip(item, tipText)
	return item
end

-- ---------- Window ----------
-- The same look as the players' Codes button: a gradient with a light edge, a shine, an icon and the text in a Label
-- (a UIGradient tints the text of its own object, so the button itself has none)
-- The button drawn in Figma (the file "CodeHatch - przyciski gry", PNGs in tools/ui_assets): one finished picture (the
-- body, the gear and the word) made at the size the game shows it, so no stripes at any size. In Figma units the body
-- is 440 x 150 with a margin of 30 around it for the glow.
local MANAGER_PICTURE = "rbxassetid://82248486872081"
local openButton = make("TextButton", {
	Name = "OpenManager",
	AnchorPoint = Vector2.new(1, 0),
	Size = UDim2.fromOffset(158, 54),
	AutoButtonColor = false,
	BackgroundTransparency = 1,
	Text = "",
}, gui)
do
	local k = 54 / 150
	make("ImageLabel", { Name = "Skin", BackgroundTransparency = 1, Image = MANAGER_PICTURE, ScaleType = Enum.ScaleType.Stretch,
		Position = UDim2.fromOffset(-30 * k, -30 * k), Size = UDim2.new(1, 60 * k, 1, 60 * k) }, openButton)
end
-- the word is in the picture ("Manager" in every language); the hidden Label keeps the text
local openLabel = make("TextLabel", { Name = "Label", BackgroundTransparency = 1, Size = UDim2.fromScale(1, 1), FontFace = TITLE_FONT,
	TextSize = 22, TextColor3 = INK, Text = upper(T.open), TextTransparency = 1 }, openButton)
local openScale = make("UIScale", {}, openButton)
openButton.MouseEnter:Connect(function()
	TweenService:Create(openScale, TweenInfo.new(0.08), { Scale = 1.05 }):Play()
end)
openButton.MouseLeave:Connect(function()
	TweenService:Create(openScale, TweenInfo.new(0.08), { Scale = 1 }):Play()
end)

-- ManagerPosition (a place, optionally moved by pixels: "TopRight", "TopRight 0,40"); next to the Codes button when
-- both are in the same place. A change in the Settings tab comes as an attribute on the code remote.
local OPEN_PLACES = {
	left = { UDim2.new(0, 10, 0.5, 0), Vector2.new(0, 0.5) },
	right = { UDim2.new(1, -10, 0.5, 0), Vector2.new(1, 0.5) },
	top = { UDim2.new(0.5, 0, 0, 10), Vector2.new(0.5, 0) },
	bottom = { UDim2.new(0.5, 0, 1, -10), Vector2.new(0.5, 1) },
	center = { UDim2.fromScale(0.5, 0.5), Vector2.new(0.5, 0.5) },
	topleft = { UDim2.fromOffset(10, 10), Vector2.new(0, 0) },
	topright = { UDim2.new(1, -10, 0, 10), Vector2.new(1, 0) },
	bottomleft = { UDim2.new(0, 10, 1, -10), Vector2.new(0, 1) },
	bottomright = { UDim2.new(1, -10, 1, -10), Vector2.new(1, 1) },
}
local function readPlace(value)
	local name, x, y = string.match(tostring(value or ""), "^%s*(%a+)%s*([%+%-]?%d*)%s*,?%s*([%+%-]?%d*)%s*$")
	local function pixels(text)
		return math.clamp(tonumber(text) or 0, -2000, 2000)
	end
	return name and string.lower(name) or "", pixels(x), pixels(y)
end
local codesRemote = ReplicatedStorage:FindFirstChild("DiscordCodesRedeem")
local function current(name, default)
	local live = codesRemote and codesRemote:GetAttribute(name)
	if live ~= nil then
		return live
	end
	local own = ownSettings and ownSettings:FindFirstChild(name)
	return own and own.Value or default
end
local function placeOpenButton()
	local key, x, y = readPlace(current("ManagerPosition", "TopRight"))
	local place = OPEN_PLACES[key] or OPEN_PLACES.topright
	local push = 0
	if readPlace(current("ButtonPosition", "Left")) == key then -- the Codes button stands there: go next to it
		push = place[2].Y == 1 and -64 or 70
	end
	openButton.AnchorPoint = place[2]
	openButton.Position = place[1] + UDim2.fromOffset(x, y + push)
end
placeOpenButton()
if codesRemote then
	codesRemote:GetAttributeChangedSignal("ButtonPosition"):Connect(placeOpenButton)
	codesRemote:GetAttributeChangedSignal("ManagerPosition"):Connect(placeOpenButton)
end

-- The window: a dark violet panel with a glowing violet edge. The tabs stick out of its left edge like bookmarks (drawn
-- under the panel), the MANAGER plate sits on the top edge, the profile and Refresh are at the bottom.
local window = make("Frame", {
	Name = "Window",
	AnchorPoint = Vector2.new(0.5, 0.5),
	Position = UDim2.fromScale(0.5, 0.5),
	Size = UDim2.fromOffset(WIDTH, HEIGHT),
	BackgroundTransparency = 1,
	Visible = false,
}, gui)
local scale = make("UIScale", {}, window)
local rail = make("Frame", { Name = "Tabs", BackgroundTransparency = 1, Position = UDim2.fromOffset(-50, 74),
	Size = UDim2.fromOffset(100, HEIGHT - 150) }, window)
local panel = make("Frame", { Name = "Panel", Size = UDim2.fromScale(1, 1), BackgroundColor3 = INK }, window)
make("UIGradient", { Color = ColorSequence.new(Color3.fromRGB(34, 20, 58), Color3.fromRGB(16, 9, 30)), Rotation = 90 }, panel)
rounded(panel, 22)
outline(panel, GLOW, 2.5)

local function fit()
	local screen = gui.AbsoluteSize
	if screen.X > 0 and screen.Y > 0 then
		scale.Scale = math.min(1, (screen.X - 16) / (WIDTH + 110), (screen.Y - 40) / (HEIGHT + 40))
	end
end
gui:GetPropertyChangedSignal("AbsoluteSize"):Connect(fit)
fit()

-- the MANAGER plate on the top edge, the pink OWNER tag next to it
local banner = make("Frame", {
	AnchorPoint = Vector2.new(0.5, 0.5),
	Position = UDim2.fromScale(0.5, 0),
	Size = UDim2.fromOffset(300, 56),
	ZIndex = 3,
}, window)
rounded(banner, 16)
glossyFrame(banner, MANAGER_LOOK, 16)
text(banner, "⚙️ MANAGER", 32, INK, TITLE_FONT, {
	AutomaticSize = Enum.AutomaticSize.None, Size = UDim2.fromScale(1, 1), TextXAlignment = Enum.TextXAlignment.Center, ZIndex = 4,
	TextStrokeColor3 = Color3.fromRGB(70, 24, 120), TextStrokeTransparency = 0.6 })
local ownerBadge = text(banner, T.owner, 13, INK, HEAVY, {
	AnchorPoint = Vector2.new(0, 0.5), Position = UDim2.new(1, -30, 0, -8), Rotation = 8, BackgroundTransparency = 0,
	BackgroundColor3 = Color3.fromRGB(255, 96, 150), ZIndex = 5, TextXAlignment = Enum.TextXAlignment.Center })
rounded(ownerBadge, 9)
padding(ownerBadge, 3, 10)
outline(ownerBadge, INK, 1.5)

-- the pink-red close button on the top right corner
local closeButton = make("TextButton", {
	AnchorPoint = Vector2.new(1, 0),
	Position = UDim2.new(1, 10, 0, -10),
	Size = UDim2.fromOffset(46, 46),
	FontFace = HEAVY,
	TextSize = 22,
	TextColor3 = INK,
	Text = "X",
	ZIndex = 6,
}, window)
shade(closeButton, GRADIENTS.red)
rounded(closeButton, 13)
outline(closeButton, LIGHT_EDGE, 2)

-- the section: a header card (big colored icon, name, one line of what it is for, the language on the right), the
-- content under it and the status line
local main = make("Frame", { BackgroundTransparency = 1, Position = UDim2.fromOffset(28, 50), Size = UDim2.new(1, -56, 1, -50 - 86) }, window)
local heading = make("Frame", { Name = "Heading", Size = UDim2.new(1, 0, 0, 80), BackgroundColor3 = INK }, main)
make("UIGradient", { Color = ColorSequence.new(Color3.fromRGB(48, 28, 84), Color3.fromRGB(30, 17, 52)), Rotation = 90 }, heading)
rounded(heading, 16)
outline(heading, CARD_EDGE, 1.5)
local headingIcon = make("Frame", { Name = "Icon", Position = UDim2.fromOffset(12, 11), Size = UDim2.fromOffset(58, 58), BackgroundColor3 = INK }, heading)
rounded(headingIcon, 14)
local headingShade = glossyFrame(headingIcon, MANAGER_LOOK, 14)
local headingIconText = text(headingIcon, "", 28, INK, HEAVY, { AutomaticSize = Enum.AutomaticSize.None, Size = UDim2.fromScale(1, 1),
	TextXAlignment = Enum.TextXAlignment.Center })
local headingTitle = text(heading, "", 26, INK, HEAVY, { Position = UDim2.fromOffset(86, 12) })
local headingSub = text(heading, "", 15, SOFT, BOLD, { Position = UDim2.fromOffset(86, 46) })

local languageButton = button(heading, "", "ghost", nil, 36)
languageButton.AnchorPoint = Vector2.new(1, 0.5)
languageButton.Position = UDim2.new(1, -16, 0.5, 0)
languageButton.ZIndex = 6
local languageMenu = make("Frame", { AnchorPoint = Vector2.new(1, 0), Position = UDim2.new(1, -16, 0, 66), Size = UDim2.fromOffset(150, 0),
	AutomaticSize = Enum.AutomaticSize.Y, BackgroundColor3 = FIELD, Visible = false, ZIndex = 20 }, main)
rounded(languageMenu, 10)
outline(languageMenu, GLOW, 2)
padding(languageMenu, 6, 6)
list(languageMenu, nil, 4)

local content = make("ScrollingFrame", {
	BackgroundTransparency = 1,
	Position = UDim2.fromOffset(0, 92),
	Size = UDim2.new(1, 14, 1, -104),
	CanvasSize = UDim2.new(),
	AutomaticCanvasSize = Enum.AutomaticSize.Y,
	ScrollBarThickness = 6,
	ScrollBarImageColor3 = GLOW,
	BorderSizePixel = 0,
}, main)
list(content, nil, 10)
-- the cards' edges are drawn just outside them: a small inset on every side keeps them from being cut
make("UIPadding", { PaddingLeft = UDim.new(0, 2), PaddingRight = UDim.new(0, 16), PaddingBottom = UDim.new(0, 6), PaddingTop = UDim.new(0, 3) },
	content)
-- what scrolls under the bottom edge fades into the window instead of being cut off
local fade = make("Frame", { Name = "Fade", AnchorPoint = Vector2.new(0, 1), Position = UDim2.new(0, 0, 1, -12), Size = UDim2.new(1, 0, 0, 30),
	BackgroundColor3 = Color3.fromRGB(18, 10, 33), BorderSizePixel = 0, Active = false }, main)
make("UIGradient", { Rotation = 90, Transparency = NumberSequence.new(1, 0) }, fade)

-- the bottom: a line, your avatar, name and "Kit vNN · Studio", the Refresh button (draws the section again)
local footer = make("Frame", { Name = "Footer", AnchorPoint = Vector2.new(0, 1), Position = UDim2.fromScale(0, 1),
	Size = UDim2.new(1, 0, 0, 80), BackgroundTransparency = 1 }, window)
make("Frame", { Name = "Line", Position = UDim2.fromOffset(3, 0), Size = UDim2.new(1, -6, 0, 1), BackgroundColor3 = CARD_EDGE,
	BorderSizePixel = 0 }, footer)
local avatar = make("ImageLabel", { Position = UDim2.fromOffset(28, 15), Size = UDim2.fromOffset(50, 50), BackgroundColor3 = VIOLET,
	Image = "" }, footer)
rounded(avatar, 25)
outline(avatar, LIGHT_EDGE, 2)
text(footer, player.DisplayName, 17, INK, HEAVY, { Position = UDim2.fromOffset(90, 17), AutomaticSize = Enum.AutomaticSize.Y,
	Size = UDim2.new(0.5, 0, 0, 0), TextTruncate = Enum.TextTruncate.AtEnd })
local kitLabel = text(footer, "", 14, GREEN, BOLD, { Position = UDim2.fromOffset(90, 42) })
task.spawn(function()
	local ok, image = pcall(function()
		return Players:GetUserThumbnailAsync(player.UserId, Enum.ThumbnailType.HeadShot, Enum.ThumbnailSize.Size100x100)
	end)
	if ok then
		avatar.Image = image
	end
end)
local reloadButton = button(footer, "🔄  " .. T.reload, "primary", nil, 42)
reloadButton.AnchorPoint = Vector2.new(1, 0.5)
reloadButton.Position = UDim2.new(1, -28, 0.5, 0)

local statusBox = make("Frame", { AnchorPoint = Vector2.new(0, 1), Position = UDim2.fromScale(0, 1), Size = UDim2.fromOffset(0, 34),
	AutomaticSize = Enum.AutomaticSize.XY, BackgroundColor3 = Color3.fromRGB(18, 58, 36), Visible = false, ZIndex = 5 }, main)
rounded(statusBox, 10)
local statusEdge = outline(statusBox, GREEN)
padding(statusBox, 8, 14)
-- a long answer of the bot wraps instead of running out of the window
local statusLabel = text(statusBox, "", 14, INK, BOLD, { TextWrapped = true, ZIndex = 5 })
make("UISizeConstraint", { MaxSize = Vector2.new(WIDTH - 300, 400) }, statusLabel)

local statusToken = 0
local function status(value, color, seconds)
	statusToken += 1
	local mine = statusToken
	statusLabel.Text = value or ""
	statusBox.Visible = value ~= nil and value ~= ""
	color = color or SOFT
	statusEdge.Color = color
	statusLabel.TextColor3 = color:Lerp(INK, 0.55)
	statusBox.BackgroundColor3 = color:Lerp(Color3.new(0, 0, 0), 0.75)
	task.delay(seconds or 8, function()
		if statusToken == mine then
			statusBox.Visible = false
		end
	end)
end

-- ---------- Content helpers ----------
local order = 0
local function nextOrder()
	order += 1
	return order
end

local function closeMenu()
	if openMenu then
		openMenu:Destroy()
		openMenu = nil
	end
end
content:GetPropertyChangedSignal("CanvasPosition"):Connect(closeMenu) -- the list would stay where its row was
local function clear()
	hideTip()
	closeMenu()
	for _, child in ipairs(content:GetChildren()) do
		if child:IsA("GuiObject") then
			child:Destroy()
		end
	end
	order = 0
end

-- a rounded box in the content, its children one under another
local function card(edge)
	local box = make("Frame", { LayoutOrder = nextOrder(), BackgroundColor3 = CARD, Size = UDim2.fromScale(1, 0),
		AutomaticSize = Enum.AutomaticSize.Y }, content)
	rounded(box, 14)
	outline(box, edge or CARD_EDGE, edge and 2 or 1)
	padding(box, 12, 16)
	list(box, nil, 8)
	return box
end

-- a line of things side by side that wraps when it doesn't fit
local function flow(parent, gap)
	local line = make("Frame", { LayoutOrder = nextOrder(), BackgroundTransparency = 1, Size = UDim2.fromScale(1, 0),
		AutomaticSize = Enum.AutomaticSize.Y }, parent or content)
	local layout = list(line, Enum.FillDirection.Horizontal, gap or 8, Enum.VerticalAlignment.Center)
	layout.Wraps = true
	return line
end

local function paragraph(parent, value, color, mono)
	return text(parent, value, mono and 13 or 14, color or SOFT, mono and CODE_FONT or BOLD, {
		LayoutOrder = nextOrder(), AutomaticSize = Enum.AutomaticSize.Y, Size = UDim2.fromScale(1, 0), TextWrapped = true })
end

local function sectionTitle(value, tipText)
	local label = text(content, value, 15, MUTED, HEAVY, { LayoutOrder = nextOrder() })
	label.Text = upper(value) .. (tipText and "  ⓘ" or "")
	attachTip(label, tipText)
	return label
end

-- A settings-style row: icon, title, a line under it, things on the right (returned). Hover shows what it does.
-- below = true puts the things under the line instead (many chips that would squeeze the title)
local function row(icon, title, description, tipText, edge, below)
	local box = make("Frame", { LayoutOrder = nextOrder(), BackgroundColor3 = CARD, Size = UDim2.new(1, 0, 0, 64),
		AutomaticSize = Enum.AutomaticSize.Y }, content)
	rounded(box, 14)
	local edgeStroke = outline(box, edge or CARD_EDGE, edge and 2 or 1)
	padding(box, 12, 14)
	local iconBox = text(box, icon, 20, INK, HEAVY, { AutomaticSize = Enum.AutomaticSize.None, Size = UDim2.fromOffset(40, 40),
		BackgroundTransparency = 0, TextXAlignment = Enum.TextXAlignment.Center })
	rounded(iconBox, 10)
	glossyText(iconBox, MANAGER_LOOK, 10)
	local texts = make("Frame", { BackgroundTransparency = 1, Position = UDim2.fromOffset(54, 0), Size = UDim2.new(1, -54, 0, 0),
		AutomaticSize = Enum.AutomaticSize.Y }, box)
	list(texts, nil, 2)
	local titleLabel = text(texts, title .. (tipText and "  ⓘ" or ""), 17, INK, HEAVY, {
		AutomaticSize = Enum.AutomaticSize.Y, Size = UDim2.fromScale(1, 0), TextWrapped = true })
	if description and description ~= "" then
		text(texts, description, 15, SOFT, BOLD, { LayoutOrder = 2, AutomaticSize = Enum.AutomaticSize.Y, Size = UDim2.fromScale(1, 0),
			TextWrapped = true })
	end
	local controls
	if below then
		controls = make("Frame", { LayoutOrder = 3, BackgroundTransparency = 1, Size = UDim2.fromScale(1, 0),
			AutomaticSize = Enum.AutomaticSize.Y }, texts)
		make("UIPadding", { PaddingTop = UDim.new(0, 6) }, controls)
		list(controls, Enum.FillDirection.Horizontal, 6, Enum.VerticalAlignment.Center).Wraps = true
	else
		controls = make("Frame", { AnchorPoint = Vector2.new(1, 0), Position = UDim2.fromScale(1, 0), Size = UDim2.fromOffset(0, 40),
			AutomaticSize = Enum.AutomaticSize.X, BackgroundTransparency = 1 }, box)
		local layout = list(controls, Enum.FillDirection.Horizontal, 8, Enum.VerticalAlignment.Center)
		layout.HorizontalAlignment = Enum.HorizontalAlignment.Right
		-- the texts take what the things on the right leave
		controls:GetPropertyChangedSignal("AbsoluteSize"):Connect(function()
			local width = controls.AbsoluteSize.X / math.max(scale.Scale, 0.01)
			texts.Size = UDim2.new(1, -54 - (width > 0 and width + 12 or 0), 0, 0)
		end)
	end
	if tipText then
		box.MouseEnter:Connect(function()
			edgeStroke.Color = GLOW
			if byMouse() then
				showTip(box, tipText)
			end
		end)
		box.MouseLeave:Connect(function()
			edgeStroke.Color = edge or CARD_EDGE
			hideTip(box)
		end)
		box.Destroying:Connect(function()
			hideTip(box)
		end)
		-- phones have no hover: a tap on the title shows the same text
		local tap = make("TextButton", { BackgroundTransparency = 1, Text = "", Size = UDim2.fromScale(1, 1), ZIndex = 2 }, titleLabel)
		tap.Activated:Connect(function()
			showTip(box, tipText)
			local at = titleLabel.AbsolutePosition
			placeTip(at.X, at.Y + titleLabel.AbsoluteSize.Y)
		end)
	end
	return controls, box
end

-- the friendly "nothing here yet" box with a hint where to add it
local function empty(icon, title, hint)
	local controls = row(icon, title, hint)
	return controls
end

local showing = 0 -- a newer tab load wins over an older one that answers later

local function ask(action, arg)
	local token = showing
	local ok, result
	for _ = 1, 12 do -- the server answers one question at a time (a refresh takes seconds): a busy answer is asked again
		ok, result = pcall(function()
			return remote:InvokeServer(action, arg)
		end)
		if not (ok and type(result) == "table" and result.busy) then
			break
		end
		task.wait(0.5)
	end
	if token ~= showing then
		return nil -- another tab is open now: this answer is not needed anymore
	end
	if not ok or type(result) ~= "table" or result.busy or result.error then
		status(T.failed, RED)
		return nil
	end
	if result.denied then
		status(T.denied, RED)
		return nil
	end
	if result.wait then
		status(string.format(T.wait, result.wait), GOLD)
		return nil
	end
	if result.ownerOnly then
		status(T.ownerOnly, GOLD)
		return nil
	end
	if result.noPermission then
		status(T.noPermission, GOLD)
		return nil
	end
	if result.studioOnly then
		status(result.what == "currency" and T.studioOnlyCurrency or T.studioOnly, GOLD)
		return nil
	end
	return result
end

local function timeLeft(seconds)
	seconds = math.max(0, math.floor(seconds))
	if seconds >= 86400 then
		return math.floor(seconds / 86400) .. "d " .. math.floor(seconds % 86400 / 3600) .. "h"
	elseif seconds >= 3600 then
		return math.floor(seconds / 3600) .. "h " .. math.floor(seconds % 3600 / 60) .. "m"
	end
	return math.floor(seconds / 60) .. "m " .. seconds % 60 .. "s"
end

-- The same precision as the egg's stand (Roblox: rounded only to four decimal places below the first non-zero digit)
local function percent(value)
	value = tonumber(value) or 0
	if value <= 0 then
		return "0%"
	end
	local decimals = math.max(0, 4 - math.floor(math.log(value, 10)))
	local text = string.format("%." .. decimals .. "f", value)
	if string.find(text, ".", 1, true) then
		text = string.gsub(text, "0+$", "")
		text = string.gsub(text, "%.$", "")
	end
	return text .. "%"
end

local function number(value)
	local formatted = tostring(math.floor(tonumber(value) or 0))
	local result
	repeat
		formatted, result = string.gsub(formatted, "^(-?%d+)(%d%d%d)", "%1,%2")
	until result == 0
	return formatted
end

local function updateKitLine(state)
	ownerBadge.Visible = state.owner ~= false -- the people in ManagerUsers are helpers, not the owner
	kitLabel.Text = string.format(T.kitLine, tostring(state.version), state.studio and T.inStudio or T.inLive)
end

-- ---------- Tabs ----------
local pages = {}
local showTab -- defined under the tabs (Overview calls it after a refresh)
local tabButtons = {} -- the bookmark tabs on the window's left edge (made under the pages)
local function setDot(index, on) -- the gold dot on a tab: something runs in that section
	local entry = tabButtons[index]
	if entry then
		entry.dot.Visible = on and true or false
	end
end
local currentTab = 1 -- the open tab (the forms draw it again after the bot answered)
-- what you may do ({ owner, can = { codes = true, ... } } from the server): only those tabs show; nil until it answered
local myAccess = nil
local setAccess -- set with the tabs below
local editing = nil -- the 🛡️ tab: the player whose permissions are being ticked ({ id, name, permissions })

-- ---------- Controls (switch, list, text box) ----------
-- An ON/OFF switch
local function switch(parent, on, changed)
	local track = make("TextButton", { Size = UDim2.fromOffset(64, 32), BackgroundColor3 = on and GREEN or FIELD, Text = "",
		AutoButtonColor = false }, parent)
	rounded(track, 16)
	outline(track, on and LIGHT_EDGE or Color3.fromRGB(74, 51, 128))
	local knob = make("Frame", { AnchorPoint = Vector2.new(0, 0.5), Position = on and UDim2.new(1, -29, 0.5, 0) or UDim2.new(0, 3, 0.5, 0),
		Size = UDim2.fromOffset(26, 26), BackgroundColor3 = INK }, track)
	rounded(knob, 13)
	track.Activated:Connect(function()
		changed(not on)
	end)
	return track
end

-- A button that opens a list under it; options = { { value, label } }
local function dropdown(parent, options, current, picked)
	local label = tostring(current)
	for _, option in ipairs(options) do
		if option[1] == current then
			label = option[2]
		end
	end
	local opener = button(parent, label .. "  🔽", "ghost", nil, 34)
	opener.Activated:Connect(function()
		if openMenu then
			closeMenu()
			return
		end
		hideTip()
		local at = (opener.AbsolutePosition - window.AbsolutePosition) / math.max(scale.Scale, 0.01)
		local width = opener.AbsoluteSize.X / math.max(scale.Scale, 0.01)
		local long = #options > 8 -- a long list scrolls instead of running out of the window
		local menu = make(long and "ScrollingFrame" or "Frame", { Position = UDim2.fromOffset(at.X, at.Y + opener.AbsoluteSize.Y / math.max(scale.Scale, 0.01) + 4),
			Size = UDim2.fromOffset(math.max(width, 150), long and 8 * 34 + 12 or 0), AutomaticSize = long and Enum.AutomaticSize.None or Enum.AutomaticSize.Y,
			BackgroundColor3 = FIELD, ZIndex = 30 }, window)
		if long then
			menu.CanvasSize = UDim2.new()
			menu.AutomaticCanvasSize = Enum.AutomaticSize.Y
			menu.ScrollBarThickness = 5
			menu.BorderSizePixel = 0
		end
		rounded(menu, 10)
		outline(menu, GLOW, 2)
		padding(menu, 6, 6)
		list(menu, nil, 4)
		for i, option in ipairs(options) do
			local item = make("TextButton", { LayoutOrder = i, Size = UDim2.new(1, 0, 0, 30), BackgroundColor3 = option[1] == current and VIOLET or CARD,
				AutoButtonColor = true, FontFace = HEAVY, TextSize = 14, TextColor3 = INK, Text = option[2], ZIndex = 31 }, menu)
			rounded(item, 8)
			item.Activated:Connect(function()
				closeMenu()
				picked(option[1])
			end)
		end
		-- a list too long for the window opens upwards (its height counted from the options: the layout may not be done yet)
		local height = math.min(#options, 8) * 34 + 12
		local top = at.Y + opener.AbsoluteSize.Y / math.max(scale.Scale, 0.01) + 4
		if top + height > HEIGHT - 10 then
			menu.Position = UDim2.fromOffset(at.X, math.max(10, at.Y - height - 4))
		end
		openMenu = menu
	end)
	return opener
end

-- "⋯" in a row: the less used things in a small list under it (build(menu) puts them in)
local function moreButton(parent, build)
	local opener = button(parent, "⋯", "ghost", T.more, 30)
	opener.Activated:Connect(function()
		if openMenu then
			closeMenu()
			return
		end
		hideTip()
		local at = (opener.AbsolutePosition - window.AbsolutePosition) / math.max(scale.Scale, 0.01)
		local size = opener.AbsoluteSize / math.max(scale.Scale, 0.01)
		local menu = make("Frame", { AnchorPoint = Vector2.new(1, 0), Position = UDim2.fromOffset(at.X + size.X, at.Y + size.Y + 4),
			Size = UDim2.fromOffset(0, 0), AutomaticSize = Enum.AutomaticSize.XY, BackgroundColor3 = FIELD, ZIndex = 30 }, window)
		rounded(menu, 10)
		outline(menu, GLOW, 2)
		padding(menu, 8, 8)
		list(menu, nil, 6)
		build(menu)
		for _, child in ipairs(menu:GetDescendants()) do
			if child:IsA("GuiObject") then
				child.ZIndex = 31
			end
		end
		openMenu = menu
	end)
	return opener
end

-- A text box in a row (Enter or leaving it sends the text)
local function field(parent, value, placeholder, width, sent)
	local box = make("TextBox", { Size = UDim2.fromOffset(width, 34), BackgroundColor3 = FIELD, FontFace = HEAVY, TextSize = 14, TextColor3 = INK,
		PlaceholderText = placeholder, PlaceholderColor3 = MUTED, Text = value, ClearTextOnFocus = false, TextTruncate = Enum.TextTruncate.AtEnd }, parent)
	rounded(box, 10)
	local edge = outline(box, Color3.fromRGB(74, 51, 128))
	padding(box, 0, 10)
	box.Focused:Connect(function()
		edge.Color = GLOW
	end)
	box.FocusLost:Connect(function(enter)
		edge.Color = Color3.fromRGB(74, 51, 128)
		if sent then
			sent(box.Text, enter)
		end
	end)
	return box
end


-- A list that remembers what was picked: :get() gives the value
local function choice(parent, options, initial)
	local holder = make("Frame", { BackgroundTransparency = 1, Size = UDim2.fromOffset(0, 34), AutomaticSize = Enum.AutomaticSize.X }, parent)
	local current = initial
	local function build()
		for _, child in ipairs(holder:GetChildren()) do
			child:Destroy()
		end
		dropdown(holder, options, current, function(value)
			current = value
			build()
		end)
	end
	build()
	return { get = function()
		return current
	end }
end

-- A button that asks "Sure?" first (removing, stopping, banning)
local function confirmButton(parent, label, kind, tipText, action)
	local item = button(parent, label, kind, tipText, 30)
	local armed = false
	item.Activated:Connect(function()
		if not armed then
			armed = true
			item.Text = "⚠️ " .. T.sure
			task.delay(4, function()
				if item.Parent then
					armed = false
					item.Text = label
				end
			end)
			return
		end
		armed = false
		item.Text = label
		action()
	end)
	return item
end

-- "24h" -> "24 h", "3d" -> "3 days", "unlimited" -> "No end"
local function durationLabel(key)
	if key == "unlimited" then
		return T.noEnd
	elseif key == "permanent" then
		return T.permanent
	end
	local amount, unit = string.match(key, "^(%d+)(%a)$")
	if unit == "d" then
		return amount .. " " .. (amount == "1" and T.day or T.days)
	end
	return (amount or key) .. (unit == "m" and " min" or unit == "h" and " h" or "")
end

local function durations(keys)
	local options = {}
	for _, key in ipairs(keys) do
		table.insert(options, { key, durationLabel(key) })
	end
	return options
end

local CODE_VALIDITY = { "24h", "3d", "7d", "14d", "30d", "unlimited" } -- the same keys as the bot's
local EGG_DURATIONS = { "unlimited", "24h", "3d", "7d", "14d", "30d" }
local EVENT_DURATIONS = { "1m", "5m", "10m", "20m", "1h", "3h", "6h", "12h", "24h", "3d", "7d" }
local BAN_DURATIONS = { "1h", "24h", "7d", "30d", "permanent" }
local MULTIPLIERS = { "1.5", "2", "3", "5", "10" }
local ITEM_DURATIONS = { "permanent", "1h", "3h", "6h", "12h", "24h", "3d", "7d", "14d", "30d" }

-- A whole number typed in a box (spaces and separators allowed), or nil
local function whole(typed)
	local value = tonumber((string.gsub(typed or "", "[%s,%.']", "")))
	return value and value >= 0 and value == math.floor(value) and value or nil
end

-- What the forms offer (currencies, items, egg spots), asked again at most every 30 s
local formsCache, formsAt = nil, 0
local function forms()
	if formsCache and os.clock() - formsAt < 30 then
		return formsCache
	end
	local answer = ask("forms")
	if answer then
		formsCache, formsAt = answer, os.clock()
		setAccess(answer)
	end
	return answer
end

local function nameOptions(list, withNone)
	local options = withNone and { { "", T.noneOption } } or {}
	for _, entry in ipairs(list or {}) do
		table.insert(options, { entry.value, entry.label })
	end
	return options
end

-- A form in a card: its title, then labelled lines; line(label) gives the line to put the fields in
local function form(icon, title)
	local box = card(Color3.fromRGB(110, 70, 190))
	local head = text(box, icon .. "  " .. upper(title) .. "  ⓘ", 15, INK, HEAVY, { LayoutOrder = nextOrder() })
	attachTip(head, T.tipBotForms)
	local grid = flow(box, 12)
	local function line(label)
		local cell = make("Frame", { LayoutOrder = nextOrder(), BackgroundTransparency = 1, Size = UDim2.new(0.5, -6, 0, 0),
			AutomaticSize = Enum.AutomaticSize.Y }, grid)
		list(cell, nil, 5)
		text(cell, label or " ", 13, MUTED, BOLD, { LayoutOrder = 1, AutomaticSize = Enum.AutomaticSize.Y, Size = UDim2.fromScale(1, 0),
			TextWrapped = true })
		local holder = make("Frame", { LayoutOrder = 2, BackgroundTransparency = 1, Size = UDim2.fromScale(1, 0),
			AutomaticSize = Enum.AutomaticSize.Y }, cell)
		list(holder, Enum.FillDirection.Horizontal, 8, Enum.VerticalAlignment.Center).Wraps = true
		return holder
	end
	return box, line
end

-- A line Roblox's text filter hid whole comes from the server as [filtered]: said in the panel's language
local function readable(text)
	return (string.gsub(tostring(text), "%[filtered%]", T.filterHidden))
end

-- A value of the server's answer in the panel's language: a time ({ duration = "7d" }), one of the panel's words
-- ({ text = "anySpot" }) or a text the server already filtered
local function answerValue(value)
	if type(value) == "table" then
		if value.duration then
			return durationLabel(value.duration)
		end
		return T[value.text] or tostring(value.text or "")
	end
	return readable(value)
end

-- One of the panel's messages with the server's values in it
local function answerText(key, args)
	local template = T[key] or T.failed
	local values = {}
	for i, value in ipairs(type(args) == "table" and args or {}) do
		values[i] = answerValue(value)
	end
	local ok, text = pcall(string.format, template, table.unpack(values))
	return ok and text or template
end

-- Makes a change in the game: the server checks it like Discord does and saves it at once (the bot doesn't have to
-- run). Shows the answer and draws the tab again. answered(answer): called instead after a change that worked (the
-- account found for a ban).
local sending = false
local function change(kind, data, answered)
	if sending then
		status(T.stillSending, GOLD)
		return
	end
	sending = true
	status(T.saving, SOFT, 30)
	local tab = currentTab
	local answer = ask("change", { kind = kind, data = data })
	sending = false
	if not answer then
		return
	end
	if not answer.ok then -- the server refused the form itself (e.g. a code that isn't on the list any more)
		status(T.refused, RED, 12)
		return
	end
	local lines = { (answer.done and "✅ " or "⚠️ ") .. answerText(answer.key, answer.args) }
	for _, warning in ipairs(answer.warns or {}) do
		table.insert(lines, answerText(warning.key, warning.args))
	end
	local shown = table.concat(lines, "\n")
	status(shown, answer.done and GREEN or RED, 20)
	if not answer.done then
		return
	end
	if answered then
		answered(answer)
		return
	end
	formsAt = 0
	-- the tab is drawn again with the change in it; the answer stays under it
	task.delay(0.3, function()
		if window.Visible and currentTab == tab then
			showTab(tab)
			status(shown, GREEN, 18)
		end
	end)
end

-- Where a code, event or egg was made: 🎮 in this panel (by whom) or 💬 on Discord
local function originChip(parent, item)
	if item.origin == "game" then
		chip(parent, item.by and string.format(T.madeInGame, item.by) or T.madeInGameAnon, nil, T.tipMadeIn)
	else
		chip(parent, T.madeOnDiscord, nil, T.tipMadeIn)
	end
end

-- Checks that the fields are filled in; names the missing ones
local function missing(list)
	local names = {}
	for _, entry in ipairs(list) do
		if not entry[1] then
			table.insert(names, entry[2])
		end
	end
	if #names > 0 then
		status(string.format(T.fillIn, table.concat(names, ", ")), GOLD)
		return true
	end
	return false
end

-- What this person may do (Discord -> /setup -> 🛡️ Permissions); an older server sends only "owner"
local function may(info, permission)
	if not info then
		return false
	end
	if type(info.can) == "table" then
		return info.can[permission] == true
	end
	return info.owner == true
end

local function codeForm(info)
	local _, line = form("🎟️", T.newCode)
	local nameBox = field(line(T.codeName), "", T.codeNameBox, 220)
	local rewardLine = line(T.currency)
	local currency = choice(rewardLine, nameOptions(info.currencies, true), "")
	local amountBox = field(rewardLine, "", T.amount, 120)
	local expBox = field(line(T.exp), "", "0", 120)
	local itemLine = #info.items > 0 and line(T.item) or nil
	local item = itemLine and choice(itemLine, nameOptions(info.items, true), "") or nil
	local itemTime = itemLine and choice(itemLine, durations(ITEM_DURATIONS), "permanent") or nil
	local validity = choice(line(T.validFor), durations(CODE_VALIDITY), "7d")
	button(line(), "＋ " .. T.create, "green").Activated:Connect(function()
		local code = string.upper((string.gsub(nameBox.Text, "%s+", "")))
		if missing({ { code ~= "" or nil, T.codeName } }) then
			return
		end
		change("code_add", { code = code, currency = currency.get(), amount = whole(amountBox.Text) or 0,
			exp = whole(expBox.Text) or 0, item = item and item.get() or "", item_duration = itemTime and itemTime.get() or "permanent",
			validity = validity.get() })
	end)
end

local function eventForm(info)
	local _, line = form("⚡", T.newEvent)
	local nameBox = field(line(T.name), "", T.eventNameBox, 220)
	local boosts = { { "*", T.allCurrencies } }
	for _, entry in ipairs(info.currencies) do
		table.insert(boosts, { entry.value, entry.label })
	end
	table.insert(boosts, { "exp", T.exp })
	table.insert(boosts, { "luck", T.luck })
	local boostLine = line(T.boost)
	local what = choice(boostLine, boosts, "*")
	local times = {}
	for _, value in ipairs(MULTIPLIERS) do
		table.insert(times, { value, "×" .. value })
	end
	-- the list's multipliers, or any number from 1.1 to 100 typed in the box
	local factor = choice(boostLine, times, "2")
	local factorBox = field(boostLine, "", T.factorBox, 90)
	local duration = choice(line(T.howLong), durations(EVENT_DURATIONS), "1h")
	-- the animation every player sees during the event (the newest event with one shows it)
	local animationLine = line(T.animation)
	local animations = { { "", T.noAnimation } }
	for _, name in ipairs(info.animations or {}) do
		table.insert(animations, { name, T["anim_" .. name] or name })
	end
	local animation = choice(animationLine, animations, "")
	button(animationLine, "👁 " .. T.previewAnimation, "ghost", T.tipPreviewAnimation, 30).Activated:Connect(function()
		if animation.get() == "" then
			status(T.pickAnimation, GOLD)
			return
		end
		local answer = ask("preview", { kind = "animation", animation = animation.get() })
		if answer and answer.ok then
			status(T.previewAnimationShown, GREEN)
		end
	end)
	local scope = choice(line(T.scope), { { "all", T.allServers }, { "server", T.thisServer } }, "all")
	button(line(), "▶ " .. T.startEvent, "green").Activated:Connect(function()
		local name = nameBox.Text
		if missing({ { string.gsub(name, "%s+", "") ~= "" or nil, T.name } }) then
			return
		end
		local typed = string.gsub(factorBox.Text, "%s", "")
		local data = { name = name, duration = duration.get(), animation = animation.get(), scope = scope.get() }
		local multiplier = typed ~= "" and typed or factor.get()
		local picked = what.get()
		if picked == "exp" then
			data.exp_x = multiplier
		elseif picked == "luck" then
			data.luck_x = multiplier
		else
			data.currency = picked == "*" and "" or picked
			data.currency_x = multiplier
		end
		change("event_start", data)
	end)
end

local function spotOptions(info)
	local options = { { "", T.anySpot } }
	for _, name in ipairs(info.spots or {}) do
		table.insert(options, { name, name })
	end
	return options
end

local function eggForm(info)
	local _, line = form("🥚", T.newEgg)
	local nameBox = field(line(T.name), "", T.eggNameBox, 220)
	local priceLine = line(T.priceLabel)
	local priceBox = field(priceLine, "", "100", 120)
	local currency = choice(priceLine, nameOptions(info.currencies, false), info.currencies[1] and info.currencies[1].value or "")
	local petsBox = field(line(T.pets), "", T.petsBox, 320)
	petsBox.TextTruncate = Enum.TextTruncate.None
	local spot = choice(line(T.spot), spotOptions(info), "")
	local duration = choice(line(T.lasts), durations(EGG_DURATIONS), "unlimited")
	button(line(), "＋ " .. T.create, "green").Activated:Connect(function()
		local price = whole(priceBox.Text)
		if missing({ { string.gsub(nameBox.Text, "%s+", "") ~= "" or nil, T.name }, { price and price > 0 or nil, T.priceLabel },
			{ currency.get() ~= "" or nil, T.currency }, { string.gsub(petsBox.Text, "%s+", "") ~= "" or nil, T.pets } }) then
			return
		end
		change("egg_create", { name = nameBox.Text, price = price, currency = currency.get(), pets = petsBox.Text,
			spot = spot.get(), duration = duration.get() })
	end)
end

local function giftForm(info)
	local _, line = form("🎁", T.giftForm)
	local playerBox = field(line(T.player), "", T.playerBox, 220)
	local rewardLine = line(T.currency)
	local currency = choice(rewardLine, nameOptions(info.currencies, true), "")
	local amountBox = field(rewardLine, "", T.amount, 120)
	local expBox = field(line(T.exp), "", "0", 120)
	local itemLine = #info.items > 0 and line(T.item) or nil
	local item = itemLine and choice(itemLine, nameOptions(info.items, true), "") or nil
	local itemTime = itemLine and choice(itemLine, durations(ITEM_DURATIONS), "permanent") or nil
	local messageBox = field(line(T.message), "", T.messageBox, 320)
	button(line(), "🎁 " .. T.send, "green").Activated:Connect(function()
		if missing({ { string.gsub(playerBox.Text, "%s+", "") ~= "" or nil, T.player } }) then
			return
		end
		change("gift", { player = playerBox.Text, currency = currency.get(), amount = whole(amountBox.Text) or 0,
			exp = whole(expBox.Text) or 0, item = item and item.get() or "", item_duration = itemTime and itemTime.get() or "permanent",
			message = messageBox.Text })
	end)
end

local function announceForm()
	local _, line = form("📣", T.announceForm)
	local textBox = field(line(T.announceText), "", T.announceBox, 360)
	local seconds = choice(line(T.onScreen), { { 5, "5 s" }, { 10, "10 s" }, { 15, "15 s" }, { 30, "30 s" }, { 60, "60 s" } }, 10)
	button(line(), "📣 " .. T.send, "green").Activated:Connect(function()
		if missing({ { string.gsub(textBox.Text, "%s+", "") ~= "" or nil, T.announceText } }) then
			return
		end
		change("announce", { text = textBox.Text, seconds = seconds.get() })
	end)
end

local function banForm()
	local _, line = form("🔨", T.banForm)
	local playerBox = field(line(T.player), "", T.playerBox, 220)
	local duration = choice(line(T.banFor), durations(BAN_DURATIONS), "24h")
	local reasonBox = field(line(T.reason), "", T.reasonBox, 320)
	local actions = line()
	local function player()
		return not missing({ { string.gsub(playerBox.Text, "%s+", "") ~= "" or nil, T.player } })
	end
	-- like on Discord, the ban goes only to an account you saw first (a typo must never ban someone else)
	local banButton = nil
	button(actions, "🔍 " .. T.checkAccount, "primary", nil, 30).Activated:Connect(function()
		if not player() then
			return
		end
		change("find_player", { player = playerBox.Text }, function(result)
			if banButton then
				banButton:Destroy()
				banButton = nil
			end
			local found = result.extra
			if not (found and found.user_id) or not actions.Parent then
				return
			end
			local label = "🔨 " .. string.format(T.banAccount, found.username .. " (" .. found.user_id .. ")")
			banButton = confirmButton(actions, label, "red", nil, function()
				change("ban", { user_id = found.user_id, duration = duration.get(), reason = reasonBox.Text })
			end)
		end)
	end)
	button(actions, T.unbanButton, "ghost", nil, 30).Activated:Connect(function()
		if player() then
			change("unban", { player = playerBox.Text })
		end
	end)
end

pages[1] = function() -- Overview
	local state = ask("state")
	if not state then
		return
	end
	updateKitLine(state)
	setAccess(state)
	setDot(3, (tonumber(state.events) or 0) > 0)
	local tiles = make("Frame", { LayoutOrder = nextOrder(), BackgroundTransparency = 1, Size = UDim2.new(1, 0, 0, 86) }, content)
	make("UIGridLayout", { CellSize = UDim2.new(0.25, -9, 1, 0), CellPadding = UDim2.fromOffset(12, 0), SortOrder = Enum.SortOrder.LayoutOrder }, tiles)
	local values = {
		{ "🎟️", state.codes, T.tileCodes },
		{ "⚡", state.events or "-", T.tileEvents },
		{ "🥚", state.eggs or "-", T.tileEggs },
		{ "📦", "v" .. tostring(state.version), T.tileVersion },
	}
	for i, entry in ipairs(values) do
		local tile = make("Frame", { LayoutOrder = i, BackgroundColor3 = CARD }, tiles)
		rounded(tile, 14)
		outline(tile)
		padding(tile, 10, 14)
		local tileLayout = list(tile, nil, 2, Enum.VerticalAlignment.Center) -- the number and its name in the middle of the tile
		tileLayout.HorizontalAlignment = Enum.HorizontalAlignment.Center
		text(tile, entry[1] .. "  " .. tostring(entry[2]), 26, INK, HEAVY)
		text(tile, entry[3], 14, SOFT, BOLD, { LayoutOrder = 2 })
		attachTip(tile, T.tipTiles)
	end
	local where = row("🛠️", T.whereTitle, state.studio and T.whereStudio or T.whereLive, T.tipWhere)
	chip(where, upper(state.studio and T.inStudio or T.inLive), state.studio and GOLD or GREEN)
	local hooks = row("🧩", T.hooksTitle, T.hooksDesc, T.tipHooks, nil, true)
	for _, name in ipairs({ "OnReward", "OnSpend", "OnHatch", "OnAnnouncement" }) do
		if state.hooks[name] ~= nil then
			chip(hooks, (state.hooks[name] and "✅ " or "❌ ") .. name, state.hooks[name] and GREEN or nil)
		end
	end
	local limit = row("💰", T.limitTitle, T.limitDesc, T.tipLimit)
	chip(limit, (tonumber(state.maxCurrency) or 0) > 0 and number(state.maxCurrency) or T.noLimit)
	local actions = flow()
	button(actions, "🔄  " .. T.refresh, "primary", T.tipRefresh).Activated:Connect(function()
		status(T.loading)
		local result = ask("refresh")
		if result then
			showTab(1) -- the tiles show the new numbers
			status(string.format(T.refreshed, tostring(result.codes), tostring(result.events or "-"), tostring(result.eggs or "-")), GREEN)
		end
	end)
end

pages[2] = function() -- Promo codes
	local result = ask("codes")
	if not result then
		return
	end
	local info = forms()
	if may(info, "codes") then
		codeForm(info)
	end
	if #result.list == 0 then
		empty("🎟️", T.noCodes, T.noCodesHint)
	end
	for index, code in ipairs(result.list) do
		local ends = T.forever
		if code.expires > 0 then
			ends = code.expires - result.now > 0 and string.format(T.expires, timeLeft(code.expires - result.now)) or T.expiredCode
		end
		local controls = row("🎟️", code.code, code.reward .. "  ·  " .. ends, nil, code.ok and nil or RED)
		if code.ok then
			chip(controls, T.canGive, GREEN, result.custom and T.tipCustom or T.tipCan)
		else
			chip(controls, T.cantGive, RED, string.format(T.tipCant, tostring(code.why)))
		end
		if may(info, "codes") then
			confirmButton(controls, "🗑️", "red", T.remove, function()
				change("code_remove", { index = index })
			end)
		end
		-- where it was made and (in Studio) "forget that I redeemed it" under ⋯
		moreButton(controls, function(menu)
			originChip(menu, code)
			if result.studio then -- in the published game the server refuses it (a way to redeem one code again and again)
				button(menu, "🔁 " .. T.forget, "gold", T.tipForget, 30).Activated:Connect(function()
					closeMenu()
					local answer = ask("forget", index)
					if answer and answer.ok then
						status(string.format(T.forgotten, code.code), GREEN)
					elseif answer then
						status(tostring(answer.err or T.failed), RED)
					end
				end)
			end
		end)
	end
end

pages[3] = function() -- Events
	local result = ask("events")
	if not result then
		return
	end
	local info = forms()
	if #result.list == 0 then
		empty("⚡", T.noEvents, T.noEventsHint)
	end
	local running = false
	for _, event in ipairs(result.list) do
		running = running or (event.starts or 0) <= result.now
	end
	setDot(3, running)
	for _, event in ipairs(result.list) do
		local waiting = (event.starts or 0) > result.now
		local controls, box = row("⚡", event.name ~= "" and event.name or T.event, waiting
			and ("⏱️ " .. string.format(T.startsIn, event.starts - result.now))
			or ("⏳ " .. string.format(T.left, timeLeft(event.ends - result.now))), nil, GOLD, true)
		box.BackgroundColor3 = Color3.fromRGB(46, 30, 52)
		for _, multiplier in ipairs(event.multipliers) do
			chip(controls, multiplier.value .. "x " .. (multiplier.name == "*" and "💰" or multiplier.name), GOLD)
		end
		if event.animation then
			chip(controls, "✨ " .. (T["anim_" .. event.animation] or event.animation))
		end
		if event.scope == "server" then
			chip(controls, "📍 " .. T.thisServer, nil, T.tipThisServer)
		end
		originChip(controls, event)
		if may(info, "events") and event.id then
			confirmButton(controls, "■ " .. T.stop, "red", nil, function()
				change("event_stop", { id = event.id })
			end)
		end
	end
	if may(info, "events") then
		eventForm(info)
	end
	sectionTitle(T.yourCode, T.tipYourCode)
	if #result.used == 0 then
		paragraph(card(), T.noUsed, MUTED)
	else
		local box = card()
		local line = flow(box)
		for _, entry in ipairs(result.used) do
			chip(line, entry.name .. " = " .. tostring(entry.value) .. "x", (tonumber(entry.value) or 1) > 1 and GOLD or nil)
		end
	end
end

pages[4] = function() -- Eggs
	local result = ask("eggs")
	if not result then
		return
	end
	local info = forms()
	if may(info, "eggs") then
		eggForm(info)
	end
	if #result.list == 0 then
		empty("🥚", T.noEggs, T.noEggsHint)
	end
	for _, egg in ipairs(result.list) do
		local box = card()
		local top = flow(box, 10)
		text(top, "🥚 " .. egg.name, 18, INK, HEAVY)
		chip(top, string.format(T.price, number(egg.price), egg.currency), GOLD)
		if egg.ends > 0 then
			chip(top, "⏳ " .. string.format(T.left, timeLeft(egg.ends - result.now)))
		end
		originChip(top, egg)
		local pets = flow(box, 6)
		for _, pet in ipairs(egg.pets) do
			chip(pets, pet.name .. "  " .. percent(pet.chance))
		end
		local actions = flow(box)
		local output = paragraph(box, "", SOFT, true)
		output.Visible = false
		local function simulate(times)
			local answer = ask("simulate", { id = egg.id, times = times })
			if not answer or not answer.ok then
				return
			end
			local lines = { string.format(T.simulation, answer.times) }
			for _, pet in ipairs(answer.list) do
				table.insert(lines, string.format("%s: %d (%s)  ·  %s", pet.name, pet.got, percent(pet.got / answer.times * 100), percent(pet.chance)))
			end
			output.Text = table.concat(lines, "\n")
			output.Visible = true
		end
		button(actions, "🎲 " .. string.format(T.simulate, 100), "ghost", T.tipSimulate).Activated:Connect(function()
			simulate(100)
		end)
		button(actions, "🎲 " .. string.format(T.simulate, 1000), "ghost", T.tipSimulate).Activated:Connect(function()
			simulate(1000)
		end)
		button(actions, "🥚 " .. T.openEgg, "green", T.tipOpen).Activated:Connect(function()
			if ask("open", egg.id) then
				status(T.opened, GREEN)
			end
		end)
		if may(info, "eggs") then
			local place = flow(box)
			text(place, "📍 " .. T.spot, 13, MUTED, BOLD)
			local spot = choice(place, spotOptions(info), egg.spot or "")
			button(place, T.moveTo, "primary", nil, 30).Activated:Connect(function()
				change("egg_move", { id = egg.id, spot = spot.get() })
			end)
			confirmButton(place, "🗑️ " .. T.remove, "red", nil, function()
				change("egg_remove", { id = egg.id })
			end)
		end
	end
end

pages[5] = function() -- Gifts & news
	local info = forms()
	if may(info, "gifts") then
		giftForm(info)
	end
	if may(info, "announce") then
		announceForm()
	end
	if not may(info, "gifts") then
		return -- delivering your own gifts belongs to "gifts" (the server refuses it otherwise)
	end
	local controls = row("🎁", T.giftsTitle, T.giftsDesc, T.tipGifts)
	button(controls, T.deliver, "green", nil, 34).Activated:Connect(function()
		local answer = ask("gifts")
		if answer and answer.ok then
			status(T.delivered, GREEN)
		end
	end)
end

pages[6] = function() -- Players
	local result = ask("player")
	if not result then
		return
	end
	local info = forms()
	if may(info, "bans") then
		banForm()
	end
	sectionTitle(T.values, T.tipValues)
	local box = card()
	if #result.values == 0 then
		paragraph(box, T.noValues, MUTED)
	end
	for index, entry in ipairs(result.values) do
		local line = flow(box)
		text(line, entry.path, 14, INK, CODE_FONT)
		chip(line, entry.value ~= "" and entry.value or "—", GOLD)
		text(line, entry.class, 12, MUTED, BOLD)
		if result.studio and entry.currency then -- the server refuses it in the published game (free currency)
			for _, delta in ipairs({ 1000, -1000 }) do
				button(line, (delta > 0 and "+" or "−") .. number(math.abs(delta)), delta > 0 and "green" or "red", T.tipMyCurrency, 28)
					.Activated:Connect(function()
						local answer = ask("currency", { index = index, delta = delta })
						if answer and answer.ok == false then
							status(T.refused, RED)
						elseif answer then
							showTab(6)
						end
					end)
			end
		end
	end
	if #result.attributes > 0 then
		sectionTitle(T.attributes)
		local attributes = card()
		for _, entry in ipairs(result.attributes) do
			local line = flow(attributes)
			text(line, entry.name, 14, INK, CODE_FONT)
			chip(line, entry.value, GOLD)
		end
	end
end

pages[7] = function() -- Settings
	local state = ask("state")
	if not state then
		return
	end
	updateKitLine(state)
	local values = state.settings or {}
	local function change(name, value, label)
		local answer = ask("setting", { name = name, value = value })
		if answer and answer.ok == false then
			status(T.refused, RED)
		elseif answer then
			showTab(7)
			status(string.format(T.changed, label), GREEN)
		end
	end
	local languages = { { "auto", T.auto } }
	for _, entry in ipairs(LANGUAGES) do
		table.insert(languages, { entry.code, entry.name })
	end
	local limit = tonumber(values.MaxCurrencyPerCode) or 0
	local controls = row("🔘", T.setButton, T.setButtonDesc, T.tipSetButton)
	if may(state, "settings") then
		switch(controls, values.ShowButton == true, function(on)
			change("ShowButton", on, T.setButton)
		end)
	else
		chip(controls, values.ShowButton and T.on or T.off, values.ShowButton and GREEN or nil)
	end
	-- a place on the screen: the list of places and a box for pixels ("0, -80" = 80 px higher; Enter saves)
	local effectChoices = { { "full", T.effectsFull }, { "light", T.effectsLight }, { "off", T.effectsOff } }
	local places = {}
	for _, name in ipairs(POSITIONS) do
		table.insert(places, { name, name })
	end
	local function placeRow(icon, title, desc, tip, settingName, fallback)
		local value = tostring(values[settingName] or fallback)
		local key, x, y = readPlace(value)
		local shown = fallback
		for _, option in ipairs(POSITIONS) do
			if string.lower(option) == key then
				shown = option
			end
		end
		local holder = row(icon, title, desc, tip)
		if not may(state, "settings") then
			chip(holder, value)
			return
		end
		local function save(name, newX, newY)
			change(settingName, name .. ((newX ~= 0 or newY ~= 0) and (" " .. newX .. "," .. newY) or ""), title)
		end
		dropdown(holder, places, shown, function(picked)
			save(picked, x, y)
		end)
		local box
		box = field(holder, x .. ", " .. y, T.offsetBox, 90, function(typed, enter)
			local newX, newY = string.match(typed, "^%s*([%+%-]?%d+)%s*[,;%s]%s*([%+%-]?%d+)%s*$")
			newX, newY = tonumber(newX), tonumber(newY)
			if not enter then -- only Enter saves: clicking away puts the value back
				box.Text = x .. ", " .. y
			elseif not newX or not newY or math.abs(newX) > 2000 or math.abs(newY) > 2000 then
				status(T.badOffset, GOLD)
				box.Text = x .. ", " .. y
			elseif newX ~= x or newY ~= y then
				save(shown, newX, newY)
			end
		end)
	end
	placeRow("📍", T.setPosition, T.setPositionDesc, T.tipSetPosition, "ButtonPosition", "Left")
	placeRow("⚙️", T.setManagerPos, T.setManagerPosDesc, T.tipPlace, "ManagerPosition", "TopRight")
	placeRow("⚡", T.setEventPos, T.setEventPosDesc, T.tipPlace, "EventPosition", "BottomRight")
	placeRow("📢", T.setAnnouncePos, T.setAnnouncePosDesc, T.tipPlace, "AnnouncementPosition", "Top")
	placeRow("🔔", T.setNotifyPos, T.setNotifyPosDesc, T.tipPlace, "NotificationPosition", "Bottom")
	if may(state, "settings") then
		dropdown(row("🌐", T.setLanguage, T.setLanguageDesc, T.tipSetLanguage), languages, values.Language, function(value)
			change("Language", value, T.setLanguage)
		end)
		dropdown(row("✨", T.setEffects, T.setEffectsDesc, T.tipSetEffects), effectChoices, values.EventEffects or "full",
			function(value)
				change("EventEffects", value, T.setEffects)
			end)
		local limitRow = row("💰", T.limitTitle, T.limitDesc, T.tipLimit)
		local limitBox
		limitBox = field(limitRow, tostring(limit), T.limitBox, 130, function(typed, enter)
			if not enter then -- only Enter saves: clicking away puts the value back
				limitBox.Text = tostring(limit)
				return
			end
			local wanted = tonumber((string.gsub(typed, "[%s,%.]", "")))
			if wanted == limit then
				return
			end
			if not wanted or wanted < 0 or wanted ~= math.floor(wanted) then
				status(T.notNumber, GOLD)
				return
			end
			change("MaxCurrencyPerCode", wanted, T.limitTitle)
		end)
		chip(limitRow, limit > 0 and number(limit) or T.noLimit)
	else
		-- the people in ManagerUsers see the settings; only the owner changes them
		local languageName = T.auto
		for _, entry in ipairs(languages) do
			if entry[1] == values.Language then
				languageName = entry[2]
			end
		end
		chip(row("🌐", T.setLanguage, T.setLanguageDesc, T.tipSetLanguage), languageName)
		for _, entry in ipairs(effectChoices) do
			if entry[1] == (values.EventEffects or "full") then
				chip(row("✨", T.setEffects, T.setEffectsDesc, T.tipSetEffects), entry[2])
			end
		end
		chip(row("💰", T.limitTitle, T.limitDesc, T.tipLimit), limit > 0 and number(limit) or T.noLimit)
	end
	local helpers = tonumber(state.discordHelpers) or 0 -- added on Discord (/setup → 🛡️ Permissions)
	for _ in string.gmatch(tostring(values.ManagerUsers or ""), "%d+") do
		helpers += 1
	end
	local helpersRow = row("⚙️", T.setHelpers, T.setHelpersDesc, T.tipSetHelpers)
	chip(helpersRow, helpers > 0 and string.format(T.helpers, helpers) or T.onlyYou)
	if state.owner then
		button(helpersRow, "🛡️ " .. T.edit, "primary", nil, 30).Activated:Connect(function()
			showTab(8)
		end)
	end
	paragraph(content, "✨ " .. T.settingsNote, MUTED)
	if not may(state, "settings") then
		return
	end
	local actions = flow()
	button(actions, "↩️  " .. T.reset, "ghost", T.tipReset).Activated:Connect(function()
		local answer = ask("resetSettings")
		if answer and answer.ok ~= false then
			showTab(7)
			status(T.resetDone, GREEN)
		end
	end)
	local copyBox
	button(actions, "📋  " .. T.copy, "primary", T.tipCopy).Activated:Connect(function()
		if copyBox then
			copyBox.Parent.Visible = not copyBox.Parent.Visible
			return
		end
		local box = card()
		paragraph(box, T.copyTitle, SOFT)
		local lines = {
			"\tShowButton = " .. tostring(values.ShowButton == true) .. ",",
			"\tButtonPosition = \"" .. tostring(values.ButtonPosition) .. "\",",
			"\tLanguage = \"" .. tostring(values.Language) .. "\",",
			"\tEventPosition = \"" .. tostring(values.EventPosition) .. "\",",
			"\tEventEffects = \"" .. tostring(values.EventEffects or "full") .. "\",",
			"\tAnnouncementPosition = \"" .. tostring(values.AnnouncementPosition) .. "\",",
			"\tNotificationPosition = \"" .. tostring(values.NotificationPosition) .. "\",",
			"\tManagerPosition = \"" .. tostring(values.ManagerPosition) .. "\",",
			"\tMaxCurrencyPerCode = " .. tostring(limit) .. ",",
		}
		copyBox = make("TextBox", { LayoutOrder = nextOrder(), Size = UDim2.fromScale(1, 0), AutomaticSize = Enum.AutomaticSize.Y,
			BackgroundColor3 = FIELD, FontFace = CODE_FONT, TextSize = 14, TextColor3 = GOLD, MultiLine = true, TextEditable = false,
			ClearTextOnFocus = false, TextXAlignment = Enum.TextXAlignment.Left, Text = table.concat(lines, "\n") }, box)
		rounded(copyBox, 8)
		padding(copyBox, 10, 12)
		task.defer(function()
			content.CanvasPosition = Vector2.new(0, content.AbsoluteCanvasSize.Y)
		end)
	end)
end

local function codeTest()
	-- a code, checked without using it up
	local codeRow = row("🎟️", T.codeTest, T.codeTestDesc, T.tipCodeTest)
	local result = paragraph(content, "", SOFT)
	result.Visible = false
	local codeBox
	local function testCode()
		if string.gsub(codeBox.Text, "%s+", "") == "" then
			return
		end
		local answer = ask("testCode", codeBox.Text)
		if not answer then
			return
		end
		local reward = tostring(answer.reward or "") .. (answer.custom and T.resCustom or "")
		local texts = {
			ok = string.format(T.resOk, reward),
			invalid = T.resInvalid,
			expired = T.resExpired,
			already = T.resAlready,
			unsupported = string.format(T.resUnsupported, tostring(answer.reason or "")),
			unknown = string.format(T.resUnknown, reward),
		}
		result.Text = texts[answer.key] or tostring(answer.key)
		result.TextColor3 = answer.key == "ok" and GREEN or (answer.key == "already" or answer.key == "unknown") and GOLD or RED
		result.Visible = true
	end
	codeBox = field(codeRow, "", T.codeBox, 150, function(_, enter)
		if enter then
			testCode()
		end
	end)
	button(codeRow, T.test, "primary").Activated:Connect(testCode)
end

pages[8] = function() -- Test tools
	if may(myAccess, "codes") then -- checking codes needs "codes" (it tells what a code gives)
		codeTest()
	end
	sectionTitle(T.previews, T.tipPreviews)
	local function preview(arg)
		local answer = ask("preview", arg)
		if answer and answer.ok then
			status(T.shown, GREEN)
		end
	end
	local announceRow = row("📣", T.prevAnnounce, T.prevAnnounceDesc, T.tipPreviews)
	local announceBox = field(announceRow, T.sampleAnnounce, T.announceBox, 220)
	button(announceRow, T.showMe, "green").Activated:Connect(function()
		preview({ kind = "announce", text = announceBox.Text })
	end)
	button(row("🎁", T.prevGift, T.prevGiftDesc, T.tipPreviews), T.showMe, "green").Activated:Connect(function()
		preview({ kind = "gift", message = T.sampleGift })
	end)
	button(row("⚡", T.prevEvent, T.prevEventDesc, T.tipPreviews), T.showMe, "green").Activated:Connect(function()
		preview({ kind = "event", name = T.sampleEvent })
	end)
	local eggs = may(myAccess, "eggs") and ask("eggs") or nil -- the eggs list needs "eggs"
	if eggs and #eggs.list > 0 then
		local hatchRow = row("🥚", T.prevHatch, T.prevHatchDesc, T.tipPreviews)
		local options = {}
		for _, egg in ipairs(eggs.list) do
			table.insert(options, { egg.id, egg.name })
		end
		local chosen = options[1][1]
		local picker
		local function makePicker()
			if picker then
				picker:Destroy()
			end
			picker = dropdown(hatchRow, options, chosen, function(value)
				chosen = value
				makePicker()
			end)
			picker.LayoutOrder = 1
		end
		makePicker()
		local show = button(hatchRow, T.showMe, "green")
		show.LayoutOrder = 2
		show.Activated:Connect(function()
			preview({ kind = "hatch", egg = chosen })
		end)
	end
end

pages[9] = function() -- Log
	local result = ask("log")
	if not result then
		return
	end
	if #result.list == 0 then
		empty("📜", T.noLog, "")
		return
	end
	sectionTitle(T.logInfo)
	local box = card()
	box.BackgroundColor3 = FIELD
	for _, entry in ipairs(result.list) do
		local color = entry.kind == "error" and RED or entry.kind == "warn" and GOLD or SOFT
		paragraph(box, readable(entry.text), color, true)
	end
end

-- A tick button: ✅ / ⬜ and its name; changed(on) after each click
local function tick(parent, label, on, changed)
	local item = make("TextButton", { Size = UDim2.fromOffset(0, 34), AutomaticSize = Enum.AutomaticSize.X, AutoButtonColor = false,
		FontFace = HEAVY, TextSize = 14, TextColor3 = INK, Text = "" }, parent)
	rounded(item, 10)
	padding(item, 0, 12)
	local edge = outline(item, Color3.fromRGB(74, 51, 128), 1.5)
	local function paint()
		item.Text = (on and "✅  " or "⬜  ") .. label
		item.BackgroundColor3 = on and Color3.fromRGB(30, 92, 62) or FIELD
		edge.Color = on and GREEN or Color3.fromRGB(74, 51, 128)
	end
	paint()
	item.Activated:Connect(function()
		on = not on
		paint()
		changed(on)
	end)
	return item
end

local function permissionNames(list)
	local names = {}
	for _, name in ipairs(list or {}) do
		table.insert(names, T.perms[name] or name)
	end
	return #names > 0 and table.concat(names, ", ") or T.accessNothing
end

-- The answer of a save: the new list, or the reason in the status line
local function accessAnswer(answer, done)
	if not answer then
		return false
	end
	if answer.ok == false then
		status(T[answer.key or ""] or T.failed, GOLD, 12)
		return false
	end
	status(done, GREEN)
	return true
end

pages[10] = function() -- 🛡️ Manager access (only the owner)
	local result = ask("access", { op = "list" })
	if not result then
		return
	end
	-- find a player by their Roblox name
	local findRow = row("🔎", T.accessFind, T.accessFindDesc, T.tipAccessFind)
	local nameBox
	local function find()
		local typed = string.gsub(nameBox.Text, "%s+", "")
		if typed == "" then
			return
		end
		status(T.loading)
		local answer = ask("access", { op = "find", name = typed })
		if not answer then
			return
		end
		if answer.ok == false then
			status(T[answer.key or ""] or T.failed, GOLD, 12)
			return
		end
		editing = answer.user
		showTab(currentTab)
	end
	nameBox = field(findRow, "", T.accessNameBox, 170, function(_, enter)
		if enter then
			find()
		end
	end)
	button(findRow, "🔎 " .. T.find, "primary", nil, 34).Activated:Connect(find)

	-- what the found (or picked) player may do: a tick for each tab
	if editing then
		local user = editing
		local chosen = {}
		for _, name in ipairs(user.permissions or {}) do
			chosen[name] = true
		end
		local box = card(GLOW)
		text(box, "🛡️  " .. string.format(T.accessEdit, user.name), 17, INK, HEAVY, { LayoutOrder = nextOrder() })
		paragraph(box, T.accessEditDesc, SOFT)
		local ticks = flow(box, 8)
		for _, name in ipairs(result.permissions or {}) do
			tick(ticks, (ICONS[({ codes = 2, events = 3, eggs = 4, gifts = 5, announce = 5, bans = 6, settings = 7 })[name] or 1] or "")
				.. " " .. (T.perms[name] or name), chosen[name] == true, function(on)
				chosen[name] = on or nil
			end)
		end
		local actions = flow(box)
		button(actions, "💾 " .. T.accessSave, "green", nil, 36).Activated:Connect(function()
			local list = {}
			for _, name in ipairs(result.permissions or {}) do
				if chosen[name] then
					table.insert(list, name)
				end
			end
			local answer = ask("access", { op = "save", userId = user.id, name = user.name, permissions = list })
			if accessAnswer(answer, string.format(T.accessSaved, user.name)) then
				editing = nil
				showTab(currentTab)
				status(string.format(T.accessSaved, user.name), GREEN)
			end
		end)
		button(actions, T.cancel, "ghost", nil, 36).Activated:Connect(function()
			editing = nil
			showTab(currentTab)
		end)
	end

	-- who has it now
	sectionTitle(string.format(T.accessListTitle, #result.users, result.max or 25))
	if #result.users == 0 then
		empty("🛡️", T.accessNone, T.accessNoneHint)
	end
	for _, user in ipairs(result.users) do
		local controls = row("👤", user.name ~= "" and user.name or tostring(user.id), permissionNames(user.permissions))
		button(controls, "✏️ " .. T.edit, "ghost", nil, 30).Activated:Connect(function()
			editing = user
			showTab(currentTab)
		end)
		confirmButton(controls, "🗑️", "red", T.accessRemove, function()
			local answer = ask("access", { op = "remove", userId = user.id })
			if accessAnswer(answer, string.format(T.accessRemoved, user.name)) then
				if editing and editing.id == user.id then
					editing = nil
				end
				showTab(currentTab)
				status(string.format(T.accessRemoved, user.name), GREEN)
			end
		end)
	end
	paragraph(content, "💬 " .. T.accessDiscordNote, MUTED)
end

-- Start shows the log under the overview, Settings the test tools under the settings: 7 tabs instead of 9
local overviewPage, settingsPage, testPage, logPage = pages[1], pages[7], pages[8], pages[9]
pages[1] = function()
	overviewPage()
	logPage()
end
pages[7] = function()
	settingsPage()
	sectionTitle(T.tabs[8])
	testPage()
end

local TAB_COUNT = 8
-- the page each tab opens (the 8th, 🛡️ access, is page 10: 8 and 9 are drawn inside Settings and Start)
local TAB_PAGE = { 1, 2, 3, 4, 5, 6, 7, 10 }
-- what a tab needs (any one of them); nil = everyone (Start), "owner" = only the game's owner
local TAB_NEEDS = { nil, { "codes" }, { "events" }, { "eggs" }, { "gifts", "announce" }, { "bans", "players" }, { "settings" },
	"owner" }

local function tabAllowed(index)
	local needs = TAB_NEEDS[index]
	if needs == nil then
		return true
	end
	if not myAccess then
		return false -- not known yet: only Start
	end
	if needs == "owner" then
		return myAccess.owner == true
	end
	for _, permission in ipairs(needs) do
		if may(myAccess, permission) then
			return true
		end
	end
	return false
end

-- the color of each section's big icon in its header
local TAB_SHADES = {
	MANAGER_LOOK,
	GRADIENTS.pink,
	{ Color3.fromRGB(150, 96, 255), Color3.fromRGB(84, 40, 196) },
	{ Color3.fromRGB(110, 226, 206), Color3.fromRGB(32, 150, 160) },
	{ Color3.fromRGB(120, 176, 255), Color3.fromRGB(64, 98, 228) },
	{ Color3.fromRGB(255, 150, 120), Color3.fromRGB(226, 76, 96) },
	{ Color3.fromRGB(184, 172, 222), Color3.fromRGB(104, 90, 156) },
	{ Color3.fromRGB(255, 214, 110), Color3.fromRGB(226, 136, 34) },
}

-- the open tab is violet, bigger and sticks out further; the others are dark. Only the tabs you may use show, one
-- under another without gaps (8 tabs sit a little closer).
local function paintTabs()
	local shown = 0
	for i in ipairs(tabButtons) do
		if tabAllowed(i) then
			shown += 1
		end
	end
	local step = shown > 7 and 60 or 66
	local small, big = step - 10, step - 2
	local slot = 0
	for i, entry in ipairs(tabButtons) do
		local active = i == currentTab
		local visible = tabAllowed(i)
		entry.button.Visible = visible
		entry.gradient.Enabled = active
		entry.rimShade.Enabled = active
		for _, layer in ipairs(entry.layers) do
			layer.Visible = active
		end
		entry.button.BackgroundColor3 = active and INK or TAB
		entry.button.Size = active and UDim2.fromOffset(94, big) or UDim2.fromOffset(84, small)
		entry.button.Position = UDim2.fromOffset(active and 0 or 12, slot * step + (active and -(big - small) / 2 or 0))
		entry.stroke.Color = active and INK or TAB_EDGE
		entry.stroke.Thickness = active and 2 or 1.5
		entry.icon.Position = UDim2.new(0, active and 25 or 19, 0.5, 0)
		if visible then
			slot += 1
		end
	end
end

function showTab(index)
	if not tabAllowed(index) then
		index = 1
	end
	currentTab = index
	showing += 1
	local mine = showing
	paintTabs()
	local page = TAB_PAGE[index] or index
	headingTitle.Text = upper(T.tabs[page])
	headingSub.Text = T.subtitles[page]
	headingIconText.Text = ICONS[page]
	local colors = TAB_SHADES[index] or GRADIENTS.primary
	headingShade.Color = lookColors(colors)
	clear()
	status("")
	content.CanvasPosition = Vector2.zero
	local loading = paragraph(content, T.loading, MUTED)
	task.spawn(function()
		pages[page]()
		if mine == showing and loading.Parent then
			loading:Destroy()
		end
	end)
end

-- What you may do came from the server: the tabs follow it (a tab taken away while open goes back to Start)
setAccess = function(info)
	if type(info) ~= "table" then
		return
	end
	myAccess = { owner = info.owner == true, can = type(info.can) == "table" and info.can or nil }
	paintTabs()
	if not tabAllowed(currentTab) then
		showTab(1)
	end
end

-- asked when the window opens and on Refresh (not through ask: an older tab load must not throw it away)
local function fetchAccess()
	task.spawn(function()
		for _ = 1, 12 do
			local ok, result = pcall(function()
				return remote:InvokeServer("state")
			end)
			if ok and type(result) == "table" and result.busy then
				task.wait(0.5)
			else
				if ok and type(result) == "table" and not result.denied and result.ok ~= false then
					setAccess(result)
				end
				return
			end
		end
	end)
end

for i = 1, TAB_COUNT do
	local item = make("TextButton", { Name = "Tab" .. i, LayoutOrder = i, BackgroundColor3 = TAB, AutoButtonColor = false, Text = "" }, rail)
	rounded(item, 14)
	-- the open tab has the look of the MANAGER button (its gradient, layers and rim show only then)
	local gradient = make("UIGradient", { Color = lookColors(MANAGER_LOOK), Enabled = false }, item)
	local layers = glossLayers(item, 14)
	local stroke, rimShade = rim(item, 1.5)
	rimShade.Enabled = false
	local icon = text(item, ICONS[TAB_PAGE[i]], 22, INK, HEAVY, { AnchorPoint = Vector2.new(0.5, 0.5), AutomaticSize = Enum.AutomaticSize.None,
		Size = UDim2.fromOffset(32, 32), TextXAlignment = Enum.TextXAlignment.Center })
	-- a gold dot: something runs in this section (an event)
	local dot = make("Frame", { Name = "Dot", Position = UDim2.fromOffset(6, 6), Size = UDim2.fromOffset(11, 11), BackgroundColor3 = GOLD,
		Visible = false }, item)
	rounded(dot, 6)
	outline(dot, Color3.fromRGB(110, 64, 6), 1)
	-- the section's name shows when the mouse is on the tab
	local name = text(item, "", 14, INK, HEAVY, { AnchorPoint = Vector2.new(1, 0.5), Position = UDim2.new(0, -8, 0.5, 0),
		BackgroundTransparency = 0, BackgroundColor3 = FIELD, Visible = false, ZIndex = 8 })
	rounded(name, 8)
	padding(name, 5, 10)
	outline(name, GLOW, 1.5)
	item.MouseEnter:Connect(function()
		name.Visible = byMouse()
		if i ~= currentTab then
			item.BackgroundColor3 = Color3.fromRGB(52, 32, 88)
		end
	end)
	item.MouseLeave:Connect(function()
		name.Visible = false
		paintTabs()
	end)
	item.Activated:Connect(function()
		name.Visible = false
		showTab(i)
	end)
	tabButtons[i] = { button = item, gradient = gradient, stroke = stroke, rimShade = rimShade, layers = layers, icon = icon, dot = dot,
		name = name }
end
paintTabs()

reloadButton.Activated:Connect(function()
	formsAt = 0
	fetchAccess()
	showTab(currentTab)
end)

local function setLanguage(code)
	language = TEXTS[code] and code or "en"
	T = TEXTS[language]
	for i, entry in ipairs(tabButtons) do
		entry.name.Text = T.tabs[TAB_PAGE[i]]
	end
	ownerBadge.Text = T.owner
	openLabel.Text = upper(T.open)
	reloadButton.Text = "🔄  " .. T.reload
	for _, entry in ipairs(LANGUAGES) do
		if entry.code == language then
			languageButton.Text = "🌐  " .. entry.name
		end
	end
	if window.Visible then
		showTab(currentTab)
	end
end

for i, entry in ipairs(LANGUAGES) do
	local option = make("TextButton", { LayoutOrder = i, Size = UDim2.new(1, 0, 0, 32), BackgroundColor3 = CARD, AutoButtonColor = true,
		FontFace = HEAVY, TextSize = 14, TextColor3 = INK, Text = entry.name, ZIndex = 21 }, languageMenu)
	rounded(option, 8)
	option.Activated:Connect(function()
		languageMenu.Visible = false
		setLanguage(entry.code)
	end)
end
languageButton.Activated:Connect(function()
	languageMenu.Visible = not languageMenu.Visible
end)

local open = false
local slide = 0
local function setOpen(visible)
	open = visible
	slide += 1
	local mine = slide
	languageMenu.Visible = false
	hideTip()
	closeMenu()
	if visible then
		window.Position = UDim2.fromScale(0.5, 0.56)
		window.Visible = true
		TweenService:Create(window, TweenInfo.new(0.22, Enum.EasingStyle.Back, Enum.EasingDirection.Out), { Position = UDim2.fromScale(0.5, 0.5) }):Play()
		fetchAccess()
		showTab(currentTab)
	else
		local tween = TweenService:Create(window, TweenInfo.new(0.15, Enum.EasingStyle.Quad, Enum.EasingDirection.In), { Position = UDim2.fromScale(0.5, 0.56) })
		tween.Completed:Connect(function()
			if slide == mine then
				window.Visible = false
			end
		end)
		tween:Play()
	end
end

openButton.Activated:Connect(function()
	setOpen(not open)
end)
closeButton.Activated:Connect(function()
	setOpen(false)
end)

setLanguage("en")
