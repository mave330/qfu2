# Flight QFU Tracker - Product Requirements Document

## Overview
Real-time flight app that shows runway landing directions (QFU) for airports using live ADS-B data from OpenSky Network, with METAR weather data integration.

## Features
1. **Real-time ADS-B tracking** via OpenSky Network API (free, no API key)
2. **122 airports** with comprehensive European coverage (France, UK, Germany, Italy, Spain, Netherlands, Belgium, Switzerland, Austria, Scandinavia, Portugal, Greece, Eastern Europe, Ireland, Cyprus, Malta + US, Asia, Middle East)
3. **Landing detection**: Aircraft below 2000ft AGL, descending, within 20km radius
4. **METAR weather data** from aviationweather.gov API (free, no API key)
   - Wind direction and speed
   - Expected runway from wind direction
   - Visibility, temperature, dewpoint
   - Cloud cover, flight category
   - Raw METAR text
5. **Text view**: Detailed airport info, active runways with aircraft list, weather card
6. **Map view**: Visual aircraft positions around airport with compass, range circles
7. **Toggle** between text and map views
8. **Auto-refresh** every 30 seconds (optional)
9. **Airport search** with autocomplete by ICAO code, name, or city

## Tech Stack
- Backend: FastAPI + Python
- Frontend: React Native / Expo
- Data Sources: OpenSky Network API, aviationweather.gov METAR API
- Database: MongoDB (for future features)

## API Endpoints
- `GET /api/airports` - List all 122 supported airports
- `GET /api/airports/{icao}` - Airport details with runway data
- `GET /api/search-airports/{query}` - Search airports
- `GET /api/runway-status/{icao}` - Main feature: active landing runways + METAR weather
