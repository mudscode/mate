import base64
import unittest

from mate.config import bot_id_from_token


class TokenTests(unittest.TestCase):
    def test_decodes_user_id(self):
        uid = 1548223486407876610
        head = base64.urlsafe_b64encode(str(uid).encode()).decode().rstrip("=")
        self.assertEqual(bot_id_from_token(f"{head}.abc.def"), uid)

    def test_garbage_is_none(self):
        self.assertIsNone(bot_id_from_token(None))
        self.assertIsNone(bot_id_from_token("nope"))
        self.assertIsNone(bot_id_from_token("!!!.a.b"))


if __name__ == "__main__":
    unittest.main()
