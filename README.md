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

This command returns exit code 1 if any city is unavailable, while preserving a clearly marked partial brief. This is a rolling seven-day forecast, not a historical report. Weather API data is fetched when generating an edition.

For automatic weekly files on Raspberry Pi OS, create an output folder (`mkdir -p "$HOME/weather-newsletters"`) and add this example with `crontab -e`. Replace `/home/pi/weather-Repo` with your actual absolute checkout path. It runs every Monday at 08:00 in the Pi's configured timezone:

```cron
0 8 * * 1 /usr/bin/python3 /home/pi/weather-Repo/app.py --newsletter "$HOME/weather-newsletters/weekly-$(date +\%F).md" >> "$HOME/weather-newsletters/generation.log" 2>&1
```

The app does not send email or subscribe recipients. You can share the downloaded Markdown yourself. No schedule is installed automatically.

## Public sources and channels

Forecasts: [Open-Meteo Forecast API](https://open-meteo.com/en/docs), attributed under CC BY 4.0. The free endpoint is intended for noncommercial use and subject to provider limits; check its terms before commercial deployment. Only `api.open-meteo.com` needs outbound access for data collection. TLS verification remains enabled.

Regional official channels are linked in the dashboard and newsletter: NWS/NHC, Met Office/Meteoalarm, IMD, JMA, and BOM. Their feeds are **not ingested**; this version collects forecast API data only. It does not supply official warning coverage.

## Validation

```bash
cd weather-Repo
python3 -m unittest -v
python3 app.py --newsletter /tmp/weekly-weather.md
```

The four automated tests use controlled API responses to verify collection, caching, newsletter calculations, missing data handling, and HTTP routes. The second command checks real provider access; verify it exits 0 and contains all cities before relying on live collection. Cloud onboarding's network proxy blocked the provider with HTTP 403 during initial development, so live collection was not verified there.
