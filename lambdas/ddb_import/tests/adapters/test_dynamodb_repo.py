from domain.game import Game
from adapters.dynamodb_repo import GameItem


class TestGameItem:

    def test_from_game_maps_fields(self):
        g = Game(steam_game_id="42", game_title="Portal")
        item = GameItem.from_game(g)

        assert item.steam_game_id == "42"
        assert item.game_title == "Portal"
        assert item.game_id  # UUID should be generated

    def test_from_game_generates_unique_ids(self):
        g = Game(steam_game_id="42", game_title="Portal")
        item_a = GameItem.from_game(g)
        item_b = GameItem.from_game(g)

        assert item_a.game_id != item_b.game_id

    def test_to_item_returns_dict(self):
        g = Game(steam_game_id="42", game_title="Portal")
        item = GameItem.from_game(g)
        d = item.to_item()

        assert d == {
            "game_id": item.game_id,
            "steam_game_id": "42",
            "game_title": "Portal",
        }

