#!/usr/bin/env python3
"""Public weather dashboard and seven-day regional newsletter. Python 3.7+."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CITIES = {
    'Americas': [('New York',40.71,-74.01),('São Paulo',-23.55,-46.63),('Mexico City',19.43,-99.13)],
    'EMEA': [('London',51.51,-0.13),('Dubai',25.20,55.27),('Johannesburg',-26.20,28.04)],
    'India': [('New Delhi',28.61,77.21),('Mumbai',19.08,72.88),('Bengaluru',12.97,77.59)],
    'Asia Pacific & Japan': [('Tokyo',35.68,139.69),('Singapore',1.35,103.82),('Sydney',-33.87,151.21)],
}
CHANNELS = {
    'Americas': [('US National Weather Service','https://www.weather.gov/'),('NOAA National Hurricane Center','https://www.nhc.noaa.gov/')],
    'EMEA': [('UK Met Office','https://www.metoffice.gov.uk/'),('Meteoalarm Europe','https://www.meteoalarm.org/')],
    'India': [('India Meteorological Department','https://mausam.imd.gov.in/')],
    'Asia Pacific & Japan': [('Japan Meteorological Agency','https://www.jma.go.jp/jma/indexe.html'),('Australian Bureau of Meteorology','https://www.bom.gov.au/')],
}
CACHE = None
LOCK = threading.Lock()
TTL = 1800


def fetch_city(item):
    region, (name, lat, lon) = item
    query = urlencode({'latitude':lat,'longitude':lon,'current':'temperature_2m,weather_code,wind_speed_10m',
        'daily':'temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max',
        'timezone':'auto','forecast_days':7})
    result = {'region':region,'city':name}
    try:
        request = Request('https://api.open-meteo.com/v1/forecast?' + query, headers={'User-Agent':'RegionalWeatherDashboard/1.0'})
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
        daily = data['daily']
        days = []
        for index, date in enumerate(daily['time']):
            days.append({'date':date,'high':daily['temperature_2m_max'][index],
                'low':daily['temperature_2m_min'][index], 'rain':daily['precipitation_sum'][index],
                'wind':daily['wind_speed_10m_max'][index]})
        if len(days) != 7 or any(day[key] is None for day in days for key in ('high','low','rain','wind')):
            raise ValueError('Incomplete seven-day forecast')
        result.update(current=data['current'], days=days, timezone=data['timezone'], error=None)
    except Exception:
        result.update(error='Forecast unavailable. Try again after the next refresh.')
    return result


def collect():
    global CACHE
    with LOCK:
        if CACHE is not None and time.time() - CACHE['fetched_epoch'] < TTL:
            return CACHE
        items = [(region, city) for region, cities in CITIES.items() for city in cities]
        with ThreadPoolExecutor(max_workers=6) as pool:
            cities = list(pool.map(fetch_city, items))
        CACHE = {'fetched_epoch':time.time(), 'generated_at':datetime.now(timezone.utc).isoformat(),
                 'cities':cities,'channels':CHANNELS,'source':'Open-Meteo','refresh_seconds':TTL}
        return CACHE


def newsletter(data):
    lines = ['# Weekly Weather Brief', '', 'Generated (UTC): ' + data['generated_at'],
        '', 'Seven-day outlook • °C • rain in mm • wind in km/h',
        'Selected city snapshots, not region-wide forecasts. Dates use each city’s local timezone.', '']
    for region in CITIES:
        lines += ['## ' + region, '']
        for city in (c for c in data['cities'] if c['region'] == region):
            if city.get('error'):
                lines += ['- ' + city['city'] + ': data unavailable; no forecast summary generated.']
                continue
            days = city['days']
            wettest = max(days, key=lambda day:day['rain'])
            lines += ['- **{}** ({} to {}): lows {:.1f}–highs {:.1f} °C; total forecast rain {:.1f} mm; peak wind {:.1f} km/h. Wettest day: {} ({:.1f} mm).'.format(
                city['city'],days[0]['date'],days[-1]['date'],min(d['low'] for d in days),
                max(d['high'] for d in days),sum(d['rain'] for d in days),max(d['wind'] for d in days),wettest['date'],wettest['rain'])]
        lines += ['', 'Official weather channels (links; their feeds are not ingested):']
        lines += ['- [{}]({})'.format(name,url) for name,url in CHANNELS[region]]
        lines += ['']
    lines += ['Forecast data: [Open-Meteo](https://open-meteo.com/) — [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).',
        'Forecasts can change. Consult local authorities for warnings; this brief does not collect official alerts.']
    return '\n'.join(lines) + '\n'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?',1)[0]
        if path == '/':
            body = Path(__file__).with_name('index.html').read_bytes()
            kind = 'text/html; charset=utf-8'
        elif path in ('/api/weather','/newsletter.md'):
            data = collect()
            body = (json.dumps(data) if path == '/api/weather' else newsletter(data)).encode()
            kind = 'application/json' if path == '/api/weather' else 'text/markdown; charset=utf-8'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        if path == '/newsletter.md':
            self.send_header('Content-Disposition','attachment; filename="weekly-weather.md"')
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8080)
    parser.add_argument('--newsletter',metavar='FILE',help='Write a Markdown brief and exit; returns 1 if any city failed')
    args = parser.parse_args()
    if args.newsletter:
        data = collect()
        Path(args.newsletter).write_text(newsletter(data),encoding='utf-8')
        return int(any(c.get('error') for c in data['cities']))
    server = ThreadingHTTPServer((args.host,args.port),Handler)
    print('Weather dashboard listening on {}:{}'.format(args.host,args.port),flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
