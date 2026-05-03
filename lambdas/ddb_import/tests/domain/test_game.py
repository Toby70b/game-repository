from domain.game import Game


class TestGame:

    def test_game_is_frozen(self):
        g = Game(steam_game_id="1", game_title="Half-Life")
        try:
            g.steam_game_id = "2"
            assert False, "Expected FrozenInstanceError"
        except AttributeError:
            pass

    def test_equality(self):
        a = Game(steam_game_id="1", game_title="Half-Life")
        b = Game(steam_game_id="1", game_title="Half-Life")
        assert a == b

    def test_inequality_different_id(self):
        a = Game(steam_game_id="1", game_title="Half-Life")
        b = Game(steam_game_id="2", game_title="Half-Life")
        assert a != b

