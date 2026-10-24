#!/usr/bin/env python3
"""Public weather dashboard and seven-day regional newsletter. Python 3.7+."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlencode, urljoin, urlsplit
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


FEEDS_FILE = Path(__file__).with_name('feeds.json')


def safe_url(value):
    return urlsplit(value).scheme in ('http', 'https') and bool(urlsplit(value).hostname)


def plain_text(value):
    # Titles are treated as text in the browser, never inserted as HTML.
    return re.sub(r'<[^>]*>', '', value or '').strip()[:500]


def parse_feed(payload, base_url):
    if b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
        raise ValueError('XML declarations with entities are unsupported')
    root = ET.fromstring(payload)
    atom = '{http://www.w3.org/2005/Atom}'
    entries = root.findall('./channel/item') if root.tag == 'rss' else root.findall(atom + 'entry')
    if root.tag not in ('rss', atom + 'feed'):
        raise ValueError('Expected RSS 2.0 or Atom')
    articles, seen = [], set()
    cutoff = datetime.now(timezone.utc).timestamp() - 7 * 86400
    for entry in entries:
        is_atom = entry.tag == atom + 'entry'
        prefix = atom if is_atom else ''
        title = plain_text(entry.findtext(prefix + 'title'))
        if is_atom:
            link = next((n.get('href','') for n in entry.findall(atom + 'link')
                         if n.get('rel','alternate') == 'alternate'), '')
            date = entry.findtext(atom + 'published') or entry.findtext(atom + 'updated')
        else:
            link = entry.findtext('link', '')
            date = entry.findtext('pubDate')
        link = urljoin(base_url, link.strip()) if link.strip() else ''
        if not title or not safe_url(link) or link in seen:
            continue
        published = None
        if date:
            try:
                stamp = (datetime.fromisoformat(date.replace('Z','+00:00')) if is_atom
                         else parsedate_to_datetime(date))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                if stamp.timestamp() < cutoff:
                    continue
                published = stamp.isoformat()
            except (ValueError, TypeError, OverflowError):
                pass
        seen.add(link)
        articles.append({'title':title,'url':link,'published':published})
    articles.sort(key=lambda a:a['published'] or '', reverse=True)
    return articles[:5]


def fetch_feed(config):
    result = dict(region=config['region'], source=config['name'], url=config['url'], articles=[])
    try:
        if not safe_url(config['url']):
            raise ValueError('Invalid feed URL')
        request = Request(config['url'], headers={'User-Agent':'WeatherAtlas/1.0 (RSS reader)'})
        with urlopen(request, timeout=12) as response:
            payload = response.read(1024 * 1024 + 1)
        if len(payload) > 1024 * 1024:
            raise ValueError('Feed exceeds 1 MiB')
        result.update(articles=parse_feed(payload, config['url']), error=None)
    except Exception:
        result['error'] = 'Feed unavailable or unsupported; no headlines collected.'
    return result


def collect_feeds():
    configs = json.loads(FEEDS_FILE.read_text(encoding='utf-8'))
    if not isinstance(configs, list) or len(configs) > 20:
        raise ValueError('feeds.json must contain at most 20 feed entries')
    for config in configs:
        if config.get('region') not in CITIES or not config.get('name') or not safe_url(config.get('url','')):
            raise ValueError('Each feed needs a known region, name, and HTTP(S) URL')
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(fetch_feed, configs))


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
                 'feeds':collect_feeds(),'cities':cities,'channels':CHANNELS,'source':'Open-Meteo','refresh_seconds':TTL}
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
        lines += ['', '### RSS / Atom headlines (past seven days where dated)', '']
        feeds = [f for f in data.get('feeds', []) if f['region'] == region]
        for feed in feeds:
            lines += ['Source: ' + feed['source']]
            if feed.get('error'):
                lines += ['- ' + feed['error']]
            elif not feed['articles']:
                lines += ['- No recent entries returned.']
            for article in feed['articles']:
                title = re.sub(r'[\[\]<>`*]', '', article['title']).replace('\n', ' ')
                lines += ['- {} — {} — {}'.format(title, article['published'] or 'Date unavailable', article['url'])]
        if not feeds:
            lines += ['No feeds configured for this region.']
        lines += ['', 'Official weather channels (reference links):']
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
    parser.add_argument('--newsletter',metavar='FILE',help='Write a Markdown brief and exit; returns 1 if any city or feed failed')
    args = parser.parse_args()
    if args.newsletter:
        data = collect()
        Path(args.newsletter).write_text(newsletter(data),encoding='utf-8')
        return int(any(c.get('error') for c in data['cities'] + data['feeds']))
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
