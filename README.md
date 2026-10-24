# Weather Atlas

A lightweight Python 3.7+ weather dashboard for Raspberry Pi 3 or any computer. No third-party packages or API keys. This repository contains the standalone Weather Atlas project.

## Run

```bash
cd weather-Repo
python3 app.py --host 0.0.0.0 --port 8080
```

Open `http://YOUR_PI_IP:8080` on your trusted local network. Use `hostname -I` on the Pi to find its address. Keep the terminal running; Ctrl+C stops the server. Without `--host`, access is restricted to the same machine. No authentication is provided; do not expose directly to the internet.

Select Americas, EMEA, India, or Asia Pacific & Japan to see current model estimates and seven local forecast days. Data is cached for 30 minutes. Initial collection can take around 24 seconds if requests time out. Failed cities display unavailable, never invented values.

Coverage: New York, São Paulo, Mexico City; London, Dubai, Johannesburg; New Delhi, Mumbai, Bengaluru; Tokyo, Singapore, Sydney. These are representative snapshots, not comprehensive regional coverage. Edit `CITIES` in `app.py` to change coverage.

## Weekly newsletter

The dashboard previews and downloads a Markdown brief covering all four regions. Each city includes its forecast period, temperature range, total rain, strongest wind, and wettest day. Generate a standalone edition:

```bash
python3 app.py --newsletter weekly-weather.md
```

This command returns exit code 1 if any city or configured feed is unavailable, while preserving a clearly marked partial brief. This is a rolling seven-day forecast, not a historical report. Weather API data is fetched when generating an edition.

For automatic weekly files on Raspberry Pi OS, create an output folder (`mkdir -p "$HOME/weather-newsletters"`) and add this example with `crontab -e`. Replace `/home/pi/weather-Repo` with your actual absolute checkout path. It runs every Monday at 08:00 in the Pi's configured timezone:

```cron
0 8 * * 1 /usr/bin/python3 /home/pi/weather-Repo/app.py --newsletter "$HOME/weather-newsletters/weekly-$(date +\%F).md" >> "$HOME/weather-newsletters/generation.log" 2>&1
```

The app does not send email or subscribe recipients. You can share the downloaded Markdown yourself. No schedule is installed automatically.

## Public sources and channels

Forecasts: [Open-Meteo Forecast API](https://open-meteo.com/en/docs), attributed under CC BY 4.0. The free endpoint is intended for noncommercial use and subject to provider limits; check its terms before commercial deployment. Outbound data access requires `api.open-meteo.com`, `www.nhc.noaa.gov`, and `weather-broker-cdn.api.bbci.co.uk` for the default configuration. TLS verification remains enabled.

Regional official channels are linked in the dashboard and newsletter: NWS/NHC, Met Office/Meteoalarm, IMD, JMA, and BOM. Reference links are supplemented by RSS/Atom feeds configured in `feeds.json`. It does not supply official warning coverage.

## Validation

```bash
cd weather-Repo
python3 -m unittest -v
python3 app.py --newsletter /tmp/weekly-weather.md
```

The six automated tests use controlled API responses to verify collection, caching, newsletter calculations, missing data handling, and HTTP routes. The second command checks real provider access; verify it exits 0 and contains all cities before relying on live collection. Cloud onboarding's network proxy blocked the provider with HTTP 403 during initial development, so live collection was not verified there.

## RSS and Atom sources

`feeds.json` defines the region, source name, and feed URL. The defaults are NOAA NHC Atlantic tropical bulletins and BBC Weather city forecast feeds for London, New Delhi, and Tokyo. These are limited regional snapshots, not comprehensive regional news. BBC entries are forecast headlines, not editorial news. You can add official or other publicly available RSS 2.0 / Atom feeds by editing this file and restarting the server; up to 20 feeds are supported. No subscription or API key is required by these configured feeds.

The dashboard and newsletter display up to five entries per source, preserving attribution and original links. Entries dated more than seven days ago are omitted. Undated entries are explicitly marked “Date unavailable” and may be older. Source order is preserved; dates are displayed as supplied by the feed. Full articles are not copied. Follow each publisher’s terms for redistribution.

Feeds share the 30-minute collection cache. Timeouts, invalid XML, oversized feeds, and unavailable sources produce explicit errors without hiding the other data. TLS verification stays enabled. Initial collection can take roughly 36 seconds when both forecasts and feeds time out. Configured feeds were blocked by this cloud environment's network proxy during development, so their live contents remain unverified. Six automated tests validate parsing, deduplication, old-item filtering, unsafe link rejection, RSS/Atom support, newsletter attribution, and graceful outages alongside forecast checks.
