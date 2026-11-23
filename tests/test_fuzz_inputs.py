"""Random and hostile text in every new form never raises (an exception in a form is "This interaction failed" for the
admin): codes, EXP, amounts, player names, reasons. A fixed seed keeps the run the same every time."""
import random
import string
import unittest
from unittest import mock

from tests.fakes import Interaction
from tests.helpers import TempBot
from utils import config_store, database, open_cloud, roblox_api

ALPHABET = (string.ascii_letters + string.digits + " _-.,@#$%^&*()[]{}<>\"'/|~`!?:;+=\t²٣éżŁ ​‮"
            "\U0001f600İıßﬁſ\u0000")


def junk(rng, longest=60):
    return "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, longest)))


class Fuzz(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        config_store.write_json("game_economy.json", {"configured": True, "currencies": ["Coins"], "items": ["VIP"]})
        self.rng = random.Random(20261013)

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def test_code_rules_only_raise_code_error(self):
        from cogs import game_codes
        for _ in range(1500):
            code = junk(self.rng, 70)
            try:
                params = game_codes.code_params(code, "7d", self.rng.choice(["none", "Coins", "", "Brak", junk(self.rng, 10)]),
                                                self.rng.choice([0, 1, 5, 10 ** 9]), self.rng.choice([0, 3]),
                                                self.rng.choice(["none", "VIP", junk(self.rng, 10)]), allow_empty=self.rng.random() < .5)
            except game_codes.CodeError:
                continue
            self.assertRegex(params["code"], r"^[A-Z0-9_-]{1,50}$", repr(code))

    async def test_code_form_and_gear_form_never_raise(self):
        from cogs import game_codes, setup_roblox
        cog = game_codes.GameCodes.__new__(game_codes.GameCodes)
        cog.bot = mock.Mock(get_cog=lambda name: None)
        for _ in range(120):
            modal = setup_roblox.CodeModal()
            modal.code._value = junk(self.rng, 50)
            modal.validity._values = [self.rng.choice(list(game_codes.CODE_VALIDITY))]
            modal.currency._values = [self.rng.choice(["none", "Coins"])]
            modal.amount._value = junk(self.rng, 15)
            modal.item._values = [self.rng.choice(["none", "VIP"])]
            inter = Interaction(GameCodes=cog)
            await modal.on_submit(inter)
            self.assertTrue(inter.response.sent)
            view = inter.response.sent[-1][1].get("view")
            if view is None:
                continue
            extras = game_codes.CodeExtrasModal(view)
            extras.exp._value = junk(self.rng, 15)
            if extras.duration is not None:
                extras.duration._values = [self.rng.choice(list(game_codes.ITEM_DURATIONS))]
            await extras.on_submit(Interaction(GameCodes=cog))

    async def test_player_and_gift_forms_never_raise(self):
        from cogs import roblox_admin, setup_roblox

        async def find_users(text):
            if self.rng.random() < .1:
                raise roblox_api.RobloxApiError("busy")
            return self.rng.choice([[], [(1, "One", "name")], [(1, "One", "name"), (2, "Two", "id")]])

        async def get_ban(user_id):
            raise open_cloud.OpenCloudError("no")

        with mock.patch.object(roblox_api, "find_users", find_users), mock.patch.object(open_cloud, "get_ban", get_ban), \
                mock.patch.object(roblox_api, "get_user", mock.AsyncMock(return_value={})), \
                mock.patch.object(roblox_api, "avatar_url", mock.AsyncMock(return_value="")):
            for _ in range(100):
                modal = roblox_admin.PlayerLookupModal()
                modal.player._value = junk(self.rng, 25)
                await modal.on_submit(Interaction())
        for _ in range(100):
            modal = setup_roblox.GiftModal(target=(1, "One"))
            modal.player._value = junk(self.rng, 25)
            modal.currency._values = [self.rng.choice(["none", "Coins"])]
            modal.amount._value = junk(self.rng, 15)
            modal.item._values = [self.rng.choice(["none", "VIP"])]
            modal.message._value = junk(self.rng, 150)
            with mock.patch.object(roblox_api, "find_users", mock.AsyncMock(return_value=[])), \
                    mock.patch.object(roblox_api, "resolve_user", mock.AsyncMock(return_value=None)):
                try:
                    await modal.on_submit(Interaction())
                except ValueError as e:
                    self.fail(f"the gift form raised {e!r} for amount {modal.amount._value!r}")

    async def test_ban_reasons_never_raise(self):
        from cogs import roblox_admin
        calls = []

        async def set_ban(*args, **kwargs):
            calls.append(args)

        async def get_ban(user_id):
            return {}

        with mock.patch.object(open_cloud, "set_ban", set_ban), mock.patch.object(open_cloud, "get_ban", get_ban), \
                mock.patch.object(roblox_api, "get_user", mock.AsyncMock(return_value={})), \
                mock.patch.object(roblox_api, "avatar_url", mock.AsyncMock(return_value="")), \
                mock.patch.object(config_store, "guild_section", return_value={"log_channel_id": 500}):
            card = roblox_admin.PlayerCardView(1, "One", False)
            for _ in range(80):
                modal = roblox_admin.BanModal(card)
                modal.duration._values = [self.rng.choice(list(roblox_admin.BAN_DURATIONS))]
                modal.reason._value = junk(self.rng, 300)
                modal.note._value = junk(self.rng, 300)
                await modal.on_submit(Interaction())
        self.assertTrue(calls)


if __name__ == "__main__":
    unittest.main()
