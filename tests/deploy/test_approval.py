import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parents[2] / 'scripts/deploy'))
from approval import validate_approval


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.environment = {'id': 123, 'name': 'production', 'protection_rules': [
            {'type': 'required_reviewers', 'prevent_self_review': True,
             'reviewers': [{'type': 'User', 'reviewer': {'login': 'reviewer'}}]}]}
        self.reviews = [{'state': 'approved', 'user': {'login': 'reviewer'},
                         'environments': [{'id': 123, 'name': 'production'}]}]

    def test_recorded_other_operator_approval(self):
        validate_approval(self.environment, self.reviews, 'operator')

    def test_missing_approval_and_bypass_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Explicit production approval'):
            validate_approval(self.environment, [], 'operator')
        env = dict(self.environment, can_admins_bypass=True)
        with self.assertRaisesRegex(ValueError, 'bypass'):
            validate_approval(env, self.reviews, 'operator')

    def test_self_approval_wrong_environment_and_rejection_rejected(self):
        cases = [dict(self.reviews[0], user={'login': 'operator'}),
                 dict(self.reviews[0], environments=[{'id': 321, 'name': 'development'}]),
                 dict(self.reviews[0], state='rejected')]
        for review in cases:
            with self.subTest(review=review), self.assertRaises(ValueError):
                validate_approval(self.environment, [review], 'operator')

    def test_unprotected_environment_rejected(self):
        with self.assertRaisesRegex(ValueError, 'require reviewers'):
            validate_approval(dict(self.environment, protection_rules=[]), self.reviews, 'operator')


if __name__ == '__main__':
    unittest.main()
