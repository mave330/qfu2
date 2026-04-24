# QFU Webapp

Flight QFU Tracker is a browser-ready webapp for estimating active landing runways at supported airports. It combines a FastAPI backend with a dependency-free static web UI, plus the original Expo React frontend for teams that want to continue mobile/web development there.

The backend serves airport/runway data, current nearby aircraft from OpenSky Network, and METAR weather from aviationweather.gov. The frontend provides airport search, runway status, weather context, aircraft lists, a runway diagram, and refresh controls.

## Airport And Runway Data

The app uses [OurAirports](https://ourairports.com/data/) for worldwide airport and runway data. OurAirports publishes public-domain CSV downloads that are updated nightly, including `airports.csv`, `runways.csv`, and `countries.csv`.

The current CSV snapshot lives in:

```text
data/ourairports/
```

Refresh it any time with:

```bash
scripts/download_ourairports.sh
```

If those CSV files are missing, the backend falls back to the original bundled sample airport database.

## Project Layout

```text
backend/   FastAPI API and runway analysis logic
data/      OurAirports public-domain CSV snapshot
scripts/   Utility scripts for refreshing public data
web/       Static browser app served by FastAPI
frontend/  Original Expo React app with web support
```

## Local Development

Install backend dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Install frontend dependencies:

```bash
npm --prefix frontend install
```

Run the webapp:

```bash
.venv/bin/uvicorn backend.server:app --host 0.0.0.0 --port 8000 --reload
```

Open:

```text
http://127.0.0.1:8000/
```

The static app and API are served from the same FastAPI process.

## Optional Expo Frontend

If you want to run the original Expo app, install frontend dependencies:

```bash
npm --prefix frontend install
cp frontend/.env.example frontend/.env
npm run dev:web
```

The Expo frontend will call `http://127.0.0.1:8000` by default when `frontend/.env` is present.

## Production-Style Build

The `web/` directory is served automatically. If you prefer to serve an Expo export instead, remove or rename `web/`, then build the Expo frontend:

```bash
npm run build:web
```

Start FastAPI:

```bash
npm start
```

When `frontend/dist` exists, FastAPI serves the webapp and API from the same origin:

```text
http://127.0.0.1:8000/      Webapp
http://127.0.0.1:8000/api   API
```

## Environment

MongoDB is optional for the current app because the QFU API is stateless. `backend/.env.example` is included for future persistence compatibility.

OpenSky OAuth is optional but recommended on Render because anonymous OpenSky calls can time out or be rate-limited from cloud IPs:

```text
OPENSKY_CLIENT_ID=your-opensky-client-id
OPENSKY_CLIENT_SECRET=your-opensky-client-secret
```

When those variables are present, the backend requests an OpenSky bearer token and uses authenticated `/states/all` calls. If OpenSky still fails, the app falls back to Airplanes.live.

For Expo development, set:

```text
EXPO_PUBLIC_BACKEND_URL=http://127.0.0.1:8000
```

For same-origin production serving, leave `EXPO_PUBLIC_BACKEND_URL` unset before building.
