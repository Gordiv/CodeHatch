# CodeHatch: run your Roblox game from Discord

🌐 **English:** README_EN.md · **Polski:** [README_PL.md](README_PL.md) · **Español:** [README_ES.md](README_ES.md)

CodeHatch is a Discord bot for Roblox game creators: you run your game straight from Discord. Promo codes, eggs, multiplier events, gifts, on-screen announcements and bans reach the game within seconds, without publishing it. It speaks English, Polish and Spanish. **You don't need to know how to code.**

**Your game doesn't need the bot running.** Codes, eggs, events and gifts you already sent are saved in your game and keep working when the bot is off. The game's ⚙️ Manager creates and removes them without the bot too; the bot is needed only for Discord, so keeping it online 24/7 is a convenience, not a must.

## 👉 Start here: `DOCS.html`

The bot folder has a file called **`DOCS.html`**. Double-click it and the whole documentation opens in your browser:

- **step-by-step quests**, e.g. *Bot online from zero* or *Your first code in the game*, with a progress bar and badges,
- search (type e.g. “token” or “API key”),
- three languages: English, Polish and Spanish,
- the same texts as `/tutorial` and `/setup-guide` in the bot.

The page works offline and saves your progress in the browser by itself. The bot refreshes it at every start, so after an update the instructions are always current. Is the bot on a server without a browser? Copy `DOCS.html` to your computer and open it there.

## 🛠️ Installation: from the zip to your first code in the game

### What you need

- A computer with Windows 10/11, Linux or macOS (or a bot hosting service).
- **Python 3.12, 3.13 or 3.14** (the bot is tested on 3.14) from **python.org**, not from the Microsoft Store.
- A Discord server where you are an administrator.
- A Roblox game that you can edit in Roblox Studio **and** for which you can create an Open Cloud API key: your own game, or a group game where your group role allows managing API keys.
- An internet connection.

### How long does it take?

**Installing the bot: about 10–15 minutes. Setting everything up: about an hour** (once; keeping the bot online 24/7 is extra, see *Bot 24/7* in `DOCS.html`). You go through three websites (python.org, the Discord Developer Portal and the Roblox Creator Hub) and Roblox Studio. Take your time, and test everything before you publish to a game that already has players. Later updates take a few minutes (see *A new version* below).

**Run ONE copy of the bot per game.** Two copies connected to the same game would do every change twice.

### Step by step

1. **Unzip.** Right-click `CodeHatch-1.0.0.zip` → **Extract All…** → pick a folder that stays, e.g. `C:\Bots`. Open the `CodeHatch-1.0.0` folder inside: you'll see `start.bat`, `main.py` and `DOCS.html`. That's your bot folder.
   - Don't run anything from the zip preview.
   - Don't keep the bot folder in OneDrive or Dropbox (often the Desktop and Documents are synced): they lock its files.
   *Details: `DOCS.html` → What you need and Python.*
2. **Python** (once per computer). **python.org** → **Downloads** → **Windows** → under Python 3.14 click **Windows installer (64-bit)** → run it. On the first screen tick **“Add python.exe to PATH”** → **Install Now**.
   *Details: `DOCS.html` → What you need and Python.*
3. **Bot account.** **discord.com/developers/applications** → **New Application** → name → **Create**. **Bot** tab: turn on **Server Members Intent** (the other two intents are not needed) → **Save Changes** → **Reset Token** → **Copy**.
   - The token is the bot's password: never send it to anyone.
   - It is shown only once. Lost it? Click **Reset Token** again (Discord may ask **Yes, do it!** and your password or 2FA code).
   - Making the bot private comes later and isn't needed to start: `DOCS.html` → The bot account on Discord → *Private bot*.
   *Details: `DOCS.html` → The bot account on Discord.*
4. **First start.** Double-click `start.bat` (Linux/macOS: `bash start.sh`).
   - Windows shows “Windows protected your PC”? Click **More info** → **Run anyway**.
   - Notepad opens the `.env` file (made from `.env.example`): replace `your_bot_token_here` with your token, with no spaces or quotes (`DISCORD_TOKEN=MTI3NDk…`) → save → close Notepad.
   - Closed Notepad without the token? `start.bat` says so and opens Notepad again: paste, save, then double-click `start.bat` again.
   - The bot installs its libraries (the window may look frozen for a few minutes) and then shows `📦 CodeHatch 1.0.0` and `✅ Synced … commands`. **Keep this black window open**: closing it turns the bot off. Clicking into it doesn't pause the bot.
   - `⚠️ "Public Bot" is ON…` in the window is a normal reminder on the first start, not an error.
   - Double-clicked `start.bat` twice? The second window stops by itself with “already running”. That's normal.
   - Leave `ROBLOX_API_KEY` empty: you paste the key on Discord in step 7.
   - Linux/macOS has no Notepad: the script creates `.env` and stops, so edit it with `nano .env` and run `bash start.sh` again.
   *Details: `DOCS.html` → First start, Problems at the start.*
5. **Invite the bot.** Developer Portal → your app → **OAuth2** → **URL Generator** → scopes **bot** and **applications.commands**. The permission list appears after you tick **bot**: tick **View Channels**, **Send Messages**, **Embed Links**, **Read Message History** (that's all it needs; don't tick **Administrator**) → open the link at the bottom → pick your server → **Authorize**. The bot appears in the member list.
   *Details: `DOCS.html` → Invite the bot to your server.*
6. **On Discord.** Type `/tutorial`: the bot shows ✅ or ⚠️ for every step. The bot starts in English; to change it: `/setup` → **🌐 Language / Język / Idioma**.
   - Don't see `/tutorial`? Wait a few minutes, press **Ctrl+R** in Discord and check that the black window is open.
   - Panels close by themselves after 5 minutes without clicks (the tutorial after 14). Just type the command again: nothing is lost.
   *Details: `/tutorial` → The bot on your server: permissions, Bot language.*
7. **Connect the game.** Keep `/tutorial` → *Connecting your Roblox game* open while you do this: it has every click.
   - `/setup-roblox` → **🎮 Roblox game** → paste your game link, e.g. `https://www.roblox.com/games/123456789/Name` (the address of your game's page in the browser; the game must have been published at least once).
   - **create.roblox.com** → left menu **All tools** → **API Keys** → **Create API Key**. Give it only these permissions: **universe-datastores** `objects:create`, `objects:read`, `objects:update`, `control:create`; **messaging-service** `universe-messaging-service:publish`. For bans and the leaderboard also **user-restrictions** `read`/`write` and **ordered-data-store** `entry:read`. Leave the IP restriction off and set no expiration.
   - After choosing each permission system click **Add Experience** and pick **your** game, otherwise the key won't work.
   - **Save & Generate Key** → **Copy**. The key is shown only once: lost it? Create a new one.
   - `/setup-roblox` → **🔑 Game connection** → **Paste API key** → **On / off** (it must be on) → **Test & sync**. You'll see ✅ or what to fix.
   *Details: `/tutorial` → Connecting your Roblox game.*
8. **The Studio file.** From the `scripts` folder you need only `DiscordCodes.rbxmx` (`DiscordSettings` is optional; `DiscordCatalog` and `DiscordCodesWindow` are optional extras explained later).
   - Open the newest version of your game in Roblox Studio (**File** → **Open from Roblox**).
   - In the **Explorer** window right-click **ServerScriptService** → **Insert** → **Import Roblox Model** → `scripts/DiscordCodes.rbxmx` from the bot folder.
   - No such option (new Studio)? Make your own tab: **+** after the tabs → **Add tools** → `model` → tick **Model** → click it, pick the file.
   - **DiscordCodes** must be inside **ServerScriptService**. Landed somewhere else? Drag it there.
   - Optional: `DiscordSettings.rbxmx` next to it (not inside).
   - **File** → **Experience Settings** (older Studio: **Home** → **Game Settings**) → **Security** → turn on **Enable Studio Access to API Services** → **Save**.
   *Details: `/tutorial` → The Roblox Studio file.*
9. **Test in Studio.** Click **Play**. The **Output** window (don't see it? **Window** menu → **Output**) shows `[DiscordCodes] File version …`, and you see the purple **Codes** button and the **⚙️ Manager** button (top right, only you as the game's owner see it).
   *Details: `/tutorial` → The Roblox Studio file; `DOCS.html` → Your game from Discord: details.*
10. **Publish.** Only when the test worked: **File** → **Publish to Roblox**. Publish sends players the whole game open in Studio, not only the bot's file. Then join the **published** game (not **Play** in Studio), wait about a minute, and `/setup-roblox` shows ✅ next to the Studio file (a panel opened earlier: press **Refresh**). Until then ⚠️ *is in Studio, but the published game doesn't run it yet* is normal.
    *Details: `/tutorial` → The Roblox Studio file.*
11. **Your first code.**
    - Pick your names first: `/setup-roblox` → **🔍 What your game has** → choose your currency (e.g. Coins) and items from the lists. They come from your game, so the bot suggests only names that exist.
    - `/setup-roblox` → **📜 Promo codes** (or `/code-add`), e.g. the code `TEST1` giving 10 Coins (codes: letters, digits, `_` and `-`, up to 30 characters).
    - Join the game → **Codes** → type `TEST1` → you get the reward. The game picks up new codes within about a minute.
    - A red message in the code window means the reward couldn't be given and the code was **not** used up (except an error in your own `OnReward`: then the code is used up, see `DOCS.html`). The **Output** window says why.
    - **Check that it stays:** leave the published game and join again. Are the 10 Coins still there? Then rewards work by themselves. Gone, or the game uses ProfileStore or similar? The game's developer adds `Core.OnReward` (codes and gifts), `Core.OnSpend` (egg prices) and `Live.OnHatch` (pets): `DOCS.html` → *Rewards: for the game's developer*.
    *Details: `/tutorial` → What your game has, Promo codes; `DOCS.html` → Rewards: for the game's developer.*

**If something goes wrong:** `/setup` → **🩺 Diagnostics**, `/setup-roblox` → **🧪 Check everything**, and `DOCS.html` → *Problems at the start*.

## 🧭 Three commands to remember

| Command | What it's for |
|---|---|
| `/tutorial` | The tutorial inside the bot: what already works (✅) and what's missing (⚠️) |
| `/setup` | Discord: language, the bug report channel, the log channel, diagnostics |
| `/setup-roblox` | Your game: connection, the Roblox Studio file, names from the game, promo codes, eggs, events and more |

## 🌟 What the bot can do

- 📜 Promo codes that work in the game a few seconds after you add them (`/setup-roblox` → 📜 Promo codes or `/code-add`)
- 🥚 Eggs with pets and ⚡ multiplier events: you create them on Discord and they work in the game within seconds, without publishing the game
- 🎁 Gifts for one player, 📢 on-screen announcements, 🔨 bans with a player card and the 🏆 leaderboard (it reads your game's existing leaderboard)
- 🕹️ A control panel in your team's channel: administrators and the roles they choose run the game with buttons, and the log channel records who changed what
- 📒 The game catalog: the bot knows your game's exact names and refuses typos
- ⚙️ A Manager panel inside your game that only you (the game's owner) see: check codes and eggs, create codes, events, eggs, gifts, announcements and bans right in the game (also with the bot off), change settings live, test a code and preview what players see
- 👥 For players: `/codes`, `/eggs`, `/events` and `/leaderboard`

Full description: `DOCS.html` → *What the bot can do*.

## 🛡️ Is it safe?

You get the full source code. The bot has no telemetry and connects only to Discord and Roblox; its error reports go only to your own Discord channel. Your bot token and API key stay in the `.env` file on your computer. The script in your game has no `require(id)` and makes no web requests. The bot needs only four Discord permissions and an API key limited to your game. Details: `DOCS.html` → *Is it safe?*.

## 🆘 Something doesn't work?

- `/setup` → **🩺 Diagnostics** (Discord) and `/setup-roblox` → **🧪 Check everything** (game) tell you what to fix.
- `/setup-guide`: answers to common questions.
- In `DOCS.html` type the problem into the search or open *Problems at the start*.

## 🔄 A new version

Your version is shown in the bot window (`📦 CodeHatch 1.0.0`) and at the bottom of `/help`. Download a new version from the #buyers channel on the CodeHatch HQ Discord server (you get the 💎 Buyer role when you buy) and read in `CHANGELOG.md` every entry between your version and the new one. Close the bot, copy the new files over the old bot folder, but **keep** `.env`, `config.json` and the `data` folder (never overwrite them), then start the bot again with `start.bat` / `start.sh`. If `/setup-roblox` then shows ⚠️ next to the DiscordCodes file, replace that file in Studio too. Step by step: `DOCS.html` → *Bot updates*.

## 📁 What's in the folder

| File / folder | What it is |
|---|---|
| `DOCS.html` | The documentation: open it in your browser |
| `start.bat` / `start.sh` | Starting the bot (Windows / Linux and macOS) |
| `.env` | Your bot token and Roblox key (made from `.env.example` on the first start, not in the zip). **Never send it to anyone** |
| `config.json`, `data/` | Your settings and database. The bot creates them on the first start (they are not in the zip). Never overwrite them when you update |
| `CHANGELOG.md` | What changed in each version |
| `LICENSE.md` | What you may and may not do with the code (license) |
| `scripts/` | Files to insert in Roblox Studio (sources in `scripts/DiscordCodes/`) |
| `cogs/`, `utils/`, `main.py` | The bot's source code: map in `DOCS.html` → *For programmers: the source code* |
| `locales/` | Texts of the bot and the documentation (EN, PL, ES) |
