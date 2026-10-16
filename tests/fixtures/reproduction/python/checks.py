import json
import unittest

from pricing import total


class PricingTest(unittest.TestCase):
    def test_standard_price(self):
        self.assertEqual(total(2), 20)

    def test_empty_order(self):
        self.assertEqual(total(0), 0)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PricingTest)
    result = unittest.TextTestRunner().run(suite)
    print(
        json.dumps(
            {
                "executed_count": result.testsRun - len(result.skipped),
                "failed_count": len(result.failures) + len(result.errors),
                "skipped_count": len(result.skipped),
            }
        )
    )
    raise SystemExit(0 if result.wasSuccessful() else 1)
