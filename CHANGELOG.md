# Changelog

What changed in each version of the bot. The newest version is at the top.

**How to update** (details: `DOCS.html` → *Bot updates*):
0. Download the new version from the project GitHub page. Your current version is shown in the bot window (`📦 CodeHatch …`) and at the bottom of `/help`. Read **every** entry between your version and the new one, not only the newest: a skipped version can still ask you to replace the Studio file.
1. Close the bot window.
2. Unzip the new version and copy its files over your bot folder. The zip never contains `.env`, `config.json` or the `data` folder, so your token, settings and database stay as they are.
3. Start the bot again with `start.bat` (Windows) or `bash start.sh` (Linux). It installs new libraries by itself and posts *The bot was updated…* on your log channel.
4. Look at the **Studio file** line of the version below: when it says *replace it*, put the new `scripts/DiscordCodes.rbxmx` into your game (`/setup-guide` → *Updating the Studio file*), test with **Play** and publish.

---

## 1.0.0 (first release)

**Studio file:** version 83 (`scripts/DiscordCodes.rbxmx`). First install: insert it as described in `/tutorial`. To ban players from the ⚙️ Manager, turn on **BanningEnabled** once: in Studio click **Players** in the Explorer, tick it in Properties, then publish.

- Promo codes from Discord to the game in seconds: `/setup-roblox` → Promo codes, `/code-add`, `/codes`, limits, expiry, checks against your game's names.
- Eggs on stands with a pedestal, exact chances (also during a luck event), Roblox's paid random item rules (PolicyService).
- Events: 2x currency, 2x EXP, more luck for rare pets, with a timer on the players' screens.
- Event animations every player sees: **💰 Coin Storm** (a big gold coin bursts into a coin fountain, then coins rain around each player) and **🌌 Aurora** (night falls on the players' screens, aurora ribbons drift over a clear starry sky, EXP orbs rise around each player, then the day comes back) and **🍀 Lucky Breeze** (the golden hour, a burst of clovers, a double rainbow, gusts of clovers, gold eggs, a ring of clovers around the egg of a rare pet) and **☄️ Meteor Shower** (a violet dusk with nebulae and a rising ringed planet, a huge meteor that bursts into a fan, volleys of meteors, pillars of light and crystal clusters) and **🌸 Sakura Festival** (a pink sunset with cherry trees, a snowy mountain, a pagoda and a torii on the horizon, a big blossom bursting into petals, rising and hanging lanterns, petal whirlwinds and a carpet of petals); textures made in Blender. Every new event starts with a 10-second countdown: a small card next to the event icons with its own icon, then a big 3-2-1 at the top of the screen. `EventEffects` in DiscordSettings (full, light, off; phones get the light version). In the ⚙️ Manager: any multiplier from 1.1 to 100, an animation with a private preview, and events for all servers or this server only.
- Gifts to one player (also offline), on-screen announcements, bans and the player card, the leaderboard.
- The game control panel for your staff, with the roles you choose.
- 🛡️ Permissions (`/setup` → **🛡️ Permissions**): choose per Discord role what it may do (codes, events, eggs, gifts, announcements, player card, bans) for the commands and the control panel buttons, and choose players who get the ⚙️ Manager in the game with their own permissions (up to 25), on Discord or in the game itself (⚙️ Manager → 🛡️ tab: find a player by name, tick, save; one shared list). Each helper sees only Start and the tabs of what they may do, and the game refuses the rest; admins and the game's owner can always do everything.
- The log channel (`/setup`) gets every change to the game with who made it: codes, eggs, events, gifts, announcements and bans, from Discord and from the ⚙️ Manager.
- In the game: the code window (a red line after a wrong code) and the **Codes** button, the event bar, announcements and messages in one dark violet style with thin edges (a hatched pet on a blue card, a rare one in a gold frame); event icons are medallions with a gold ring that shows the time left (red in the last seconds), egg stands have a navy sign with a crown, the price in Coins or Gems, each pet's chance in its rarity color and the old chances struck through during a luck event; the ⚙️ Manager panel with bookmark tabs on its left edge (Start with the kit's log, codes, events, eggs, gifts and announcements, player data, settings with the test tools, and 🛡️ Manager access for the game's owner), in English, Spanish or Polish.
- ⚙️ Manager → Settings: the game's owner changes the Codes button, its position, the players' language and the currency limit per code live on a server; **Copy for DiscordSettings** gives the lines to keep them, **Reset** goes back to DiscordSettings.
- ⚙️ Manager → Test tools: test a code without using it up, and private previews of an announcement, a gift, the event bar and a hatch that give and send nothing.
- ⚙️ Manager forms for the game's owner: create codes, start and stop events, create, move and remove eggs, send a gift or an announcement, ban and unban a player. The game does each change by itself, at once, also when the bot is off, with the same checks as on Discord; the bot writes every change to the log channel (also the ones made while it was off) and adds the codes, events and eggs to its lists. Codes, events and eggs show where they were made (🎮 the game's Manager or 💬 Discord), and a change on Discord never overwrites one made in the game at the same moment.
- ⚙️ Manager → Players in Studio: +1,000 / −1,000 buttons next to your currencies to test eggs and prices.
- Your settings live in DiscordSettings.rbxmx (insert once), so a Studio file update keeps them.
- `/tutorial`, `/setup-guide` and `DOCS.html` in English, Polish and Spanish.
- Install guides (README, `/tutorial`, `/setup-guide`, `/setup-roblox`) now say what to do when the new Roblox Studio has no **Import Roblox Model** option: make your own tab and add the **Model** tool.
