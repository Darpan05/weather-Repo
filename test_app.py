import json
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen
import app


class WeatherTests(unittest.TestCase):
    def setUp(self):
        app.CACHE = None
        self.forecast = {'current':{'temperature_2m':20,'time':'2026-10-24T12:00'},'timezone':'UTC',
            'daily':{'time':['2026-10-{:02}'.format(i) for i in range(24,31)],
                'temperature_2m_max':[25]*7,'temperature_2m_min':[10]*7,
                'precipitation_sum':[2]*7,'wind_speed_10m_max':[30]*7}}

    def fake_response(self, *args, **kwargs):
        from io import BytesIO
        return BytesIO(json.dumps(self.forecast).encode())

    def test_collection_cache_and_newsletter(self):
        with patch.object(app,'urlopen',side_effect=self.fake_response) as request:
            data = app.collect()
            self.assertEqual(len(data['cities']),12)
            self.assertFalse(any(c.get('error') for c in data['cities']))
            self.assertIs(app.collect(),data)
            self.assertEqual(request.call_count,12)
            brief = app.newsletter(data)
            self.assertIn('total forecast rain 14.0 mm',brief)
            for region in app.CITIES:
                self.assertIn('## '+region,brief)

    def test_outage_is_not_fabricated(self):
        with patch.object(app,'urlopen',side_effect=OSError('offline')):
            data = app.collect()
        self.assertTrue(all(c.get('error') for c in data['cities']))
        self.assertIn('no forecast summary generated',app.newsletter(data))
        self.assertNotIn('total forecast rain',app.newsletter(data))

    def test_incomplete_forecast(self):
        self.forecast['daily']['precipitation_sum'][0] = None
        with patch.object(app,'urlopen',side_effect=self.fake_response):
            self.assertTrue(app.fetch_city(('India',app.CITIES['India'][0]))['error'])

    def test_http(self):
        with patch.object(app,'urlopen',side_effect=self.fake_response):
            data = app.collect()
        server = app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            base = 'http://127.0.0.1:'+str(server.server_port)
            with urlopen(base) as response:
                self.assertIn(b'Weather Atlas',response.read())
            with urlopen(base+'/api/weather') as response:
                self.assertEqual(len(json.load(response)['cities']),12)
            with urlopen(base+'/newsletter.md') as response:
                self.assertIn('attachment',response.headers['Content-Disposition'])
                self.assertIn(b'Weekly Weather Brief',response.read())
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
