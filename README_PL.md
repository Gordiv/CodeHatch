# CodeHatch: steruj grą Roblox z Discorda

🌐 **English:** [README_EN.md](README_EN.md) · **Polski:** README_PL.md · **Español:** [README_ES.md](README_ES.md)

CodeHatch to bot Discord dla twórców gier na Robloxie: sterujesz swoją grą prosto z Discorda. Kody promocyjne, jajka, eventy z mnożnikami, prezenty, ogłoszenia na ekranie i bany trafiają do gry w kilka sekund, bez publikowania jej. Mówi po angielsku, polsku i hiszpańsku. **Nie musisz umieć programować.**

**Twoja gra nie potrzebuje włączonego bota.** Kody, jajka, eventy i prezenty, które już wysłałeś, są zapisane w grze i działają dalej, gdy bot jest wyłączony. ⚙️ Manager w grze tworzy je i usuwa także bez bota; bot jest potrzebny tylko do Discorda, więc trzymanie go online 24/7 to wygoda, nie wymóg.

## 👉 Zacznij tutaj: `DOCS.html`

**`DOCS.html`** pojawia się w folderze bota dopiero po pierwszym uruchomieniu bota (krok 4 poniżej); wcześniej korzystaj z tego README. Potem kliknij ten plik dwa razy, a otworzy się w przeglądarce strona z całą dokumentacją:

- **misje krok po kroku**, np. *Bot online od zera* albo *Pierwszy kod w grze*, z paskiem postępu i odznakami,
- wyszukiwarka (wpisz np. „token” albo „klucz API”),
- trzy języki: polski, angielski i hiszpański,
- te same teksty co `/tutorial` i `/setup-guide` w bocie.

Strona działa bez internetu, a postęp zapisuje się sam w przeglądarce. Bot odświeża ją przy każdym uruchomieniu, więc po aktualizacji instrukcje są zawsze aktualne. Bot stoi na serwerze bez przeglądarki? Skopiuj `DOCS.html` na swój komputer i otwórz go tam.

## 🛠️ Instalacja: od pobrania do pierwszego kodu w grze

### Co musisz mieć

- Komputer z Windows 10/11, Linuxem albo macOS (albo hosting dla botów).
- **Python 3.12, 3.13 albo 3.14** (bot jest testowany na 3.14) z **python.org**, nie ze Sklepu Microsoft.
- Serwer Discord, na którym jesteś administratorem.
- Grę Roblox, którą możesz edytować w Roblox Studio, **i** dla której możesz utworzyć klucz API Open Cloud: Twoją własną grę albo grę grupy, w której Twoja rola pozwala zarządzać kluczami API.
- Internet.

### Ile to trwa?

**Instalacja bota: ok. 10–15 minut. Skonfigurowanie wszystkiego: ok. godziny** (tylko raz; utrzymanie bota 24/7 to osobna sprawa, zobacz *Bot 24/7* w `DOCS.html`). Przechodzisz przez trzy strony (python.org, Discord Developer Portal i Roblox Creator Hub) oraz Roblox Studio. Nie spiesz się i wszystko przetestuj, zanim opublikujesz grę, w którą ktoś już gra. Późniejsze aktualizacje zajmują kilka minut (zobacz *Nowa wersja* niżej).

**Uruchamiaj JEDNĄ kopię bota na jedną grę.** Dwie kopie podłączone do tej samej gry robiłyby każdą zmianę dwa razy.

### Krok po kroku

1. **Pobierz lub sklonuj repozytorium.** Sklonuj je przez `git clone` albo na stronie GitHuba kliknij **Code** → **Download ZIP** i rozpakuj plik (prawy przycisk → **Wyodrębnij wszystko…**). Wybierz folder, który zostanie na stałe, np. `C:\Boty`. Otwórz rozpakowany folder: zobaczysz m.in. `start.bat` i `main.py` (`DOCS.html` pojawi się tam po pierwszym starcie). To jest Twój folder bota.
   - Najpierw rozpakuj ZIP pobrany z GitHuba, a dopiero potem uruchamiaj cokolwiek (nie z podglądu w archiwum).
   - Nie trzymaj folderu bota w OneDrive ani w Dropboxie (często Pulpit i Dokumenty są synchronizowane): blokują jego pliki.
   *Szczegóły: `DOCS.html` → Co musisz mieć i Python.*
2. **Python** (raz na komputerze). **python.org** → **Downloads** → **Windows** → przy Pythonie 3.14 kliknij **Windows installer (64-bit)** → uruchom pobrany plik. Na pierwszym ekranie zaznacz **„Add python.exe to PATH”** → **Install Now**.
   *Szczegóły: `DOCS.html` → Co musisz mieć i Python.*
3. **Konto bota.** **discord.com/developers/applications** → **New Application** → nazwa → **Create**. Zakładka **Bot**: włącz **Server Members Intent** (dwa pozostałe intenty nie są potrzebne) → **Save Changes** → **Reset Token** → **Copy**.
   - Token to hasło bota: nigdy nikomu go nie wysyłaj.
   - Pokazuje się tylko raz. Zgubiłeś go? Kliknij znowu **Reset Token** (Discord może zapytać **Yes, do it!** i poprosić o hasło albo kod 2FA).
   - Ustawienie bota jako prywatnego zrób później, do startu nie jest potrzebne: `DOCS.html` → Konto bota na Discordzie → *Prywatny bot*.
   *Szczegóły: `DOCS.html` → Konto bota na Discordzie.*
4. **Pierwsze uruchomienie.** Kliknij dwa razy `start.bat` (Linux/macOS: `bash start.sh`).
   - Windows pokazuje „System Windows ochronił Twój komputer”? Kliknij **Więcej informacji** → **Uruchom mimo to**.
   - Notatnik otworzy plik `.env` (powstaje z `.env.example`): zamień `your_bot_token_here` na swój token, bez spacji i cudzysłowów (`DISCORD_TOKEN=MTI3NDk…`) → zapisz → zamknij Notatnik.
   - Zamknąłeś Notatnik bez tokenu? `start.bat` to wypisze i otworzy Notatnik jeszcze raz: wklej, zapisz i znowu kliknij dwa razy `start.bat`.
   - Bot instaluje biblioteki (przez kilka minut okno może wyglądać na zawieszone), a potem pokazuje `📦 CodeHatch 1.0.0` i `✅ Synced … commands`. **Nie zamykaj czarnego okna**: jego zamknięcie wyłącza bota. Kliknięcie w okno nie zatrzymuje bota.
   - `⚠️ "Public Bot" is ON…` w oknie to przy pierwszym starcie normalne przypomnienie, a nie błąd.
   - Kliknąłeś `start.bat` dwa razy? Drugie okno samo się zatrzyma z komunikatem „already running”. To normalne.
   - `ROBLOX_API_KEY` zostaw puste: klucz wkleisz na Discordzie w kroku 7.
   - Na Linuxie i macOS nie ma Notatnika: skrypt tworzy `.env` i się zatrzymuje, więc otwórz plik przez `nano .env`, wklej token i uruchom `bash start.sh` jeszcze raz.
   *Szczegóły: `DOCS.html` → Pierwsze uruchomienie, Problemy na starcie.*
5. **Zaproś bota.** Developer Portal → Twoja aplikacja → **OAuth2** → **URL Generator** → zakresy **bot** i **applications.commands**. Lista uprawnień pojawi się dopiero po zaznaczeniu **bot**: zaznacz **View Channels**, **Send Messages**, **Embed Links**, **Read Message History** (tyle bot potrzebuje; nie zaznaczaj **Administrator**) → otwórz link z dołu strony → wybierz swój serwer → **Authorize**. Bot pojawi się na liście członków.
   *Szczegóły: `DOCS.html` → Zaproś bota na serwer.*
6. **Na Discordzie.** Wpisz `/tutorial`: bot pokazuje ✅ albo ⚠️ przy każdym kroku. Na początku bot mówi po angielsku; zmiana języka: `/setup` → **🌐 Language / Język / Idioma**.
   - Nie widzisz `/tutorial`? Poczekaj kilka minut, naciśnij **Ctrl+R** w Discordzie i sprawdź, czy czarne okno jest otwarte.
   - Panele zamykają się same po 5 minutach bez kliknięć (samouczek po 14). Po prostu wpisz komendę jeszcze raz: nic się nie gubi.
   *Szczegóły: `/tutorial` → Bot na serwerze: uprawnienia, Język bota.*
7. **Podłącz grę.** Podczas tworzenia klucza miej otwarty `/tutorial` → *Podłączenie gry Roblox*: jest tam każde kliknięcie.
   - `/setup-roblox` → **🎮 Gra Roblox** → wklej link do swojej gry, np. `https://www.roblox.com/games/123456789/Nazwa` (adres strony Twojej gry w przeglądarce; gra musi być opublikowana przynajmniej raz).
   - **create.roblox.com** → menu po lewej **All tools** → **API Keys** → **Create API Key**. Daj mu tylko te uprawnienia: **universe-datastores** `objects:create`, `objects:read`, `objects:update`, `control:create`; **messaging-service** `universe-messaging-service:publish`. Do banów i rankingu także **user-restrictions** `read`/`write` i **ordered-data-store** `entry:read`. Ograniczenie IP zostaw wyłączone, bez daty wygaśnięcia.
   - Po wybraniu każdego systemu uprawnień kliknij **Add Experience** i wybierz **swoją** grę, inaczej klucz nie zadziała.
   - **Save & Generate Key** → **Copy**. Klucz pokazuje się tylko raz: zgubiłeś go? Utwórz nowy.
   - `/setup-roblox` → **🔑 Połączenie z grą** → **Wklej klucz API** → **Włącz / wyłącz** (ma być włączone) → **Testuj i synchronizuj**. Zobaczysz ✅ albo opis, co poprawić.
   *Szczegóły: `/tutorial` → Podłączenie gry Roblox.*
8. **Plik do Studio.** Z folderu `scripts` potrzebujesz tylko `DiscordCodes.rbxmx` (`DiscordSettings` jest opcjonalny; `DiscordCatalog` i `DiscordCodesWindow` to opcjonalne dodatki, opisane w `DOCS.html`). Plik jest gotowy w repozytorium: nie musisz niczego budować.
   - Otwórz najnowszą wersję gry w Roblox Studio (**File** → **Open from Roblox**).
   - W oknie **Explorer** kliknij prawym przyciskiem **ServerScriptService** → **Insert** → **Import Roblox Model** → `scripts/DiscordCodes.rbxmx` z folderu bota.
   - Nie ma takiej opcji (nowe Studio)? Zrób własną kartę: **+** za kartami → **Add tools** → `model` → zaznacz **Model** → kliknij go i wybierz plik.
   - **DiscordCodes** musi być w środku **ServerScriptService**. Trafił gdzie indziej? Przeciągnij go tam.
   - Opcjonalnie: `DiscordSettings.rbxmx` obok (nie w środku).
   - **File** → **Experience Settings** (w starszym Studio: **Home** → **Game Settings**) → **Security** → włącz **Enable Studio Access to API Services** → **Save**.
   *Szczegóły: `/tutorial` → Plik do Roblox Studio.*
9. **Test w Studio.** Kliknij **Play**. Okno **Output** (nie widzisz go? menu **Window** → **Output**) pokaże `[DiscordCodes] File version …`, a na ekranie zobaczysz fioletowy przycisk **Codes** i przycisk **⚙️ Manager** (w prawym górnym rogu, widzisz go tylko Ty jako właściciel gry).
   *Szczegóły: `/tutorial` → Plik do Roblox Studio; `DOCS.html` → Gra z Discorda: szczegóły.*
10. **Opublikuj.** Dopiero gdy test się udał: **File** → **Publish to Roblox**. Publish wysyła graczom całą grę otwartą w Studio, nie tylko plik bota. Potem wejdź do **opublikowanej** gry (nie przez **Play** w Studio), poczekaj ok. minutę, a `/setup-roblox` pokaże ✅ przy pliku do Studio (panel otwarty wcześniej: kliknij **Odśwież**). Do tego czasu ⚠️ *jest w Studio, ale opublikowana gra jeszcze jej nie używa* jest normalne.
    *Szczegóły: `/tutorial` → Plik do Roblox Studio.*
11. **Pierwszy kod.**
    - Najpierw wybierz nazwy: `/setup-roblox` → **🔍 Co ma Twoja gra** → wybierz z list swoją walutę (np. Coins) i przedmioty. Pochodzą z Twojej gry, więc bot podpowiada tylko nazwy, które istnieją.
    - `/setup-roblox` → **📜 Kody promocyjne** (albo `/code-add`), np. kod `TEST1` dający 10 Coins (kod: litery, cyfry, `_` i `-`, najwyżej 30 znaków).
    - Wejdź do gry → **Codes** → wpisz `TEST1` → dostajesz nagrodę. Gra pobiera nowe kody w ciągu mniej więcej minuty.
    - Czerwony komunikat w okienku na kody oznacza, że nagrody nie dało się dać, a kod **nie** został zużyty (wyjątek: błąd w Twoim `OnReward` – wtedy kod jest zużyty, patrz `DOCS.html`). Okno **Output** podaje powód.
    - **Sprawdź, czy nagroda zostaje:** wyjdź z opublikowanej gry i wejdź ponownie. 10 Coins dalej jest? Nagrody działają same. Zniknęło albo gra używa ProfileStore lub podobnego zapisu? Programista gry dodaje `Core.OnReward` (kody i prezenty), `Core.OnSpend` (ceny jajek) i `Live.OnHatch` (zwierzaki): `DOCS.html` → *Nagrody: dla programisty gry*.
    *Szczegóły: `/tutorial` → Co ma Twoja gra, Kody promocyjne; `DOCS.html` → Nagrody: dla programisty gry.*

**Coś poszło nie tak?** `/setup` → **🩺 Diagnostyka**, `/setup-roblox` → **🧪 Sprawdź wszystko** i `DOCS.html` → *Problemy na starcie*.

## 🧭 Trzy komendy, które musisz znać

| Komenda | Do czego służy |
|---|---|
| `/tutorial` | Samouczek w bocie: co już działa (✅) i czego brakuje (⚠️) |
| `/setup` | Discord: język, kanał zgłoszeń błędów, kanał logów, diagnostyka |
| `/setup-roblox` | Twoja gra: połączenie, plik do Roblox Studio, nazwy z gry, kody promocyjne, jajka, eventy i więcej |

## 🌟 Co potrafi bot

- 📜 Kody promocyjne, które działają w grze kilka sekund po dodaniu (`/setup-roblox` → 📜 Kody promocyjne albo `/code-add`)
- 🥚 Jajka ze zwierzakami i ⚡ eventy z mnożnikami: tworzysz je na Discordzie, a w grze działają po kilku sekundach, bez publikowania gry
- 🎁 Prezenty dla jednego gracza, 📢 ogłoszenia na ekranie, 🔨 bany z kartą gracza i 🏆 ranking (bot czyta ranking, który Twoja gra już ma)
- 🕹️ Panel sterowania na kanale ekipy: administratorzy i wybrane przez nich role obsługują grę przyciskami, a kanał logów zapisuje, kto co zmienił
- 📒 Katalog gry: bot zna dokładne nazwy z Twojej gry i odrzuca literówki
- ⚙️ Panel Manager w grze, który widzisz tylko Ty (właściciel gry): sprawdzasz kody i jajka, tworzysz kody, eventy, jajka, prezenty, ogłoszenia i bany prosto w grze (także przy wyłączonym bocie), zmieniasz ustawienia na żywo, testujesz kod i podglądasz to, co widzą gracze
- 👥 Dla graczy: `/codes`, `/eggs`, `/events` i `/leaderboard`

Pełny opis: `DOCS.html` → *Co potrafi bot*.

## 🛡️ Czy to bezpieczne?

Cały kod źródłowy jest otwarty (licencja MIT), możesz go przejrzeć. Bot nie ma telemetrii i łączy się tylko z Discordem i Robloxem; raporty błędów trafiają wyłącznie na Twój własny kanał na Discordzie. Token bota i klucz API zostają w pliku `.env` na Twoim komputerze. Skrypt w grze nie ma `require(id)` i nie wysyła zapytań do internetu. Bot potrzebuje tylko czterech uprawnień na Discordzie i klucza API ograniczonego do Twojej gry. Szczegóły: `DOCS.html` → *Czy to bezpieczne?*.

## 🆘 Coś nie działa?

- `/setup` → **🩺 Diagnostyka** (Discord) i `/setup-roblox` → **🧪 Sprawdź wszystko** (gra) powiedzą, co poprawić.
- `/setup-guide`: odpowiedzi na częste pytania.
- W `DOCS.html` wpisz problem w wyszukiwarkę albo otwórz *Problemy na starcie*.
- Pomoc: zgłoś problem w **Issues** tego repozytorium na GitHubie. Projekt jest skończony i nie jest aktywnie rozwijany, ale zgłoszenia i pull requesty są mile widziane.

## 🔄 Nowa wersja

Twoją wersję widać w oknie bota (`📦 CodeHatch 1.0.0`) i na dole `/help`. Nową wersję pobierasz z GitHuba (`git pull` albo ponowne pobranie repozytorium); w `CHANGELOG.md` przeczytaj wszystkie wpisy między Twoją wersją a nową. Zamknij bota, skopiuj nowe pliki na stary folder bota, ale **zostaw** `.env`, `config.json` i folder `data` (nigdy ich nie nadpisuj), potem uruchom bota znowu przez `start.bat` / `start.sh`. Jeśli `/setup-roblox` pokaże potem ⚠️ przy pliku DiscordCodes, podmień też ten plik w Studio. Krok po kroku: `DOCS.html` → *Aktualizacje bota*.

## 📁 Co jest w folderze

| Plik / folder | Co to jest |
|---|---|
| `DOCS.html` | Dokumentacja: otwórz ją w przeglądarce |
| `start.bat` / `start.sh` | Uruchamianie bota (Windows / Linux i macOS) |
| `.env` | Token bota i klucz Roblox (powstaje z `.env.example` przy pierwszym starcie, nie ma go w repozytorium). **Nikomu go nie wysyłaj** |
| `config.json`, `data/` | Twoje ustawienia i baza danych. Bot tworzy je przy pierwszym starcie (nie ma ich w repozytorium). Nie nadpisuj ich przy aktualizacji |
| `CHANGELOG.md` | Co się zmieniło w każdej wersji |
| `LICENSE` | Licencja MIT: wolno używać, zmieniać i udostępniać za darmo (po angielsku) |
| `scripts/` | Pliki do wstawienia w Roblox Studio (źródła w `scripts/DiscordCodes/`) |
| `cogs/`, `utils/`, `main.py` | Kod źródłowy bota: mapa w `DOCS.html` → *Dla programisty: kod źródłowy* |
| `locales/` | Teksty bota i dokumentacji (PL, EN, ES) |
