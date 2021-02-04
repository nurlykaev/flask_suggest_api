from app2 import app
import unittest


class SuggestTestCase(unittest.TestCase):

    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.requests = [
            {'phrase': 'rbhg', 'count': 10, 'status': 200},
            {'phrase': 'рейк нап', 'count': 8, 'status': 200},
            {'phrase': 'гипскор', 'count': '', 'status': 200},
            {'phrase': '', 'count': 2, 'status': 400},
            {'phrase': 'кирп шам огн', 'count': 0, 'status': 200},
        ]

    def test_get_response(self):
        for request in self.requests:
            phrase, count, status = request['phrase'], request['count'], request['status']
            response = self.client.get(f'/suggest?phrase={phrase}')
            self.assertEqual(response.status_code, status)
            if status == 200:
                self.assertLessEqual(len(response.get_json()['response']), count or 10)


if __name__ == "__main__":
    unittest.main()
