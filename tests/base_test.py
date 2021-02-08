from app2 import app
import unittest


class SuggestTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.get_requests = [
            {'phrase': 'rbhg', 'count': 10, 'status': 200},
            {'phrase': 'рейкf нап', 'count': 2, 'status': 200},
            {'phrase': 'гипскор', 'count': '', 'status': 400},
            {'phrase': '', 'count': 2, 'status': 400},
            {'phrase': 'кирп шам огн', 'count': 0, 'status': 200},
        ]
        self.del_requests = [
            {'phrase': 'к', 'status': 200},
            {'phrase': '', 'status': 400},
        ]

    def test_get_response(self):
        for request in self.get_requests:
            phrase, count, status = request['phrase'], request['count'], request['status']
            response = self.client.get(f'/suggest?phrase={phrase}&count={count}')
            self.assertEqual(response.status_code, status)
            if status == 200:
                response = response.get_json()['response']
                self.assertLessEqual(len(response), count or 10)
                self.assertTrue(response)

    def test_del_response(self):
        for request in self.del_requests:
            phrase, status = request['phrase'], request['status']
            response = self.client.delete(f'/suggest?phrase={phrase}')
            self.assertEqual(response.status_code, status)


if __name__ == "__main__":
    unittest.main()
