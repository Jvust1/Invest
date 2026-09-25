import unittest

from invest import opening


class OpeningModuleTests(unittest.TestCase):
    def test_pair_validator_is_exposed(self):
        self.assertTrue(callable(opening.validate_opening_pair))


if __name__ == "__main__":
    unittest.main()
