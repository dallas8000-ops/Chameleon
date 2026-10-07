from django.test import TestCase

class HealthEndpointTest(TestCase):
    def test_health_endpoint_returns_ok(self):
        res = self.client.get('/api/health/')
        # Expect 200 with JSON {"status": "ok"}
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get('status'), 'ok')
