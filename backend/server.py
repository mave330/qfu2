from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime
import httpx
import math
import csv
import asyncio
from functools import lru_cache

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    AsyncIOMotorClient = None


ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR.parent / "data" / "ourairports"
load_dotenv(ROOT_DIR / '.env')

# Optional MongoDB connection.
#
# The current runway tracker API is stateless, but the original generated
# project expected MongoDB env vars at import time. Keeping this optional makes
# the webapp boot locally without a database while preserving compatibility if
# persistence is added later.
mongo_url = os.environ.get('MONGO_URL')
db_name = os.environ.get('DB_NAME')
client = AsyncIOMotorClient(mongo_url) if mongo_url and AsyncIOMotorClient else None
db = client[db_name] if client and db_name else None
aircraft_cache: Dict[str, dict] = {}

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# AIRPORT DATABASE WITH RUNWAY INFORMATION
# ============================================

AIRPORT_DATABASE = {
    # Paris Charles de Gaulle
    "LFPG": {
        "name": "Paris Charles de Gaulle",
        "city": "Paris",
        "country": "France",
        "lat": 49.0097,
        "lon": 2.5479,
        "elevation_ft": 392,
        "runways": [
            {"name": "08L/26R", "heading_08": 85, "heading_26": 265, "lat": 49.0180, "lon": 2.5200},
            {"name": "08R/26L", "heading_08": 85, "heading_26": 265, "lat": 49.0130, "lon": 2.5400},
            {"name": "09L/27R", "heading_09": 92, "heading_27": 272, "lat": 49.0050, "lon": 2.5300},
            {"name": "09R/27L", "heading_09": 92, "heading_27": 272, "lat": 49.0000, "lon": 2.5600},
        ]
    },
    # London Heathrow
    "EGLL": {
        "name": "London Heathrow",
        "city": "London",
        "country": "United Kingdom",
        "lat": 51.4700,
        "lon": -0.4543,
        "elevation_ft": 83,
        "runways": [
            {"name": "09L/27R", "heading_09": 92, "heading_27": 272, "lat": 51.4775, "lon": -0.4850},
            {"name": "09R/27L", "heading_09": 92, "heading_27": 272, "lat": 51.4650, "lon": -0.4350},
        ]
    },
    # New York JFK
    "KJFK": {
        "name": "John F. Kennedy International",
        "city": "New York",
        "country": "United States",
        "lat": 40.6413,
        "lon": -73.7781,
        "elevation_ft": 13,
        "runways": [
            {"name": "04L/22R", "heading_04": 43, "heading_22": 223, "lat": 40.6380, "lon": -73.7900},
            {"name": "04R/22L", "heading_04": 43, "heading_22": 223, "lat": 40.6450, "lon": -73.7700},
            {"name": "13L/31R", "heading_13": 134, "heading_31": 314, "lat": 40.6500, "lon": -73.7800},
            {"name": "13R/31L", "heading_13": 134, "heading_31": 314, "lat": 40.6350, "lon": -73.7650},
        ]
    },
    # Los Angeles
    "KLAX": {
        "name": "Los Angeles International",
        "city": "Los Angeles",
        "country": "United States",
        "lat": 33.9425,
        "lon": -118.4081,
        "elevation_ft": 128,
        "runways": [
            {"name": "06L/24R", "heading_06": 70, "heading_24": 250, "lat": 33.9500, "lon": -118.4300},
            {"name": "06R/24L", "heading_06": 70, "heading_24": 250, "lat": 33.9470, "lon": -118.4200},
            {"name": "07L/25R", "heading_07": 70, "heading_25": 250, "lat": 33.9350, "lon": -118.4000},
            {"name": "07R/25L", "heading_07": 70, "heading_25": 250, "lat": 33.9320, "lon": -118.3900},
        ]
    },
    # Frankfurt
    "EDDF": {
        "name": "Frankfurt am Main",
        "city": "Frankfurt",
        "country": "Germany",
        "lat": 50.0379,
        "lon": 8.5622,
        "elevation_ft": 364,
        "runways": [
            {"name": "07L/25R", "heading_07": 72, "heading_25": 252, "lat": 50.0500, "lon": 8.5300},
            {"name": "07R/25L", "heading_07": 72, "heading_25": 252, "lat": 50.0250, "lon": 8.5700},
            {"name": "07C/25C", "heading_07": 72, "heading_25": 252, "lat": 50.0380, "lon": 8.5500},
            {"name": "18/36", "heading_18": 180, "heading_36": 360, "lat": 50.0300, "lon": 8.5400},
        ]
    },
    # Amsterdam Schiphol
    "EHAM": {
        "name": "Amsterdam Schiphol",
        "city": "Amsterdam",
        "country": "Netherlands",
        "lat": 52.3086,
        "lon": 4.7639,
        "elevation_ft": -11,
        "runways": [
            {"name": "06/24", "heading_06": 58, "heading_24": 238, "lat": 52.3200, "lon": 4.7400},
            {"name": "09/27", "heading_09": 87, "heading_27": 267, "lat": 52.3100, "lon": 4.7800},
            {"name": "18L/36R", "heading_18": 183, "heading_36": 3, "lat": 52.3300, "lon": 4.7500},
            {"name": "18R/36L", "heading_18": 183, "heading_36": 3, "lat": 52.2900, "lon": 4.7700},
            {"name": "18C/36C", "heading_18": 183, "heading_36": 3, "lat": 52.3100, "lon": 4.7600},
        ]
    },
    # Dubai
    "OMDB": {
        "name": "Dubai International",
        "city": "Dubai",
        "country": "United Arab Emirates",
        "lat": 25.2528,
        "lon": 55.3644,
        "elevation_ft": 62,
        "runways": [
            {"name": "12L/30R", "heading_12": 119, "heading_30": 299, "lat": 25.2600, "lon": 55.3500},
            {"name": "12R/30L", "heading_12": 119, "heading_30": 299, "lat": 25.2450, "lon": 55.3800},
        ]
    },
    # Singapore Changi
    "WSSS": {
        "name": "Singapore Changi",
        "city": "Singapore",
        "country": "Singapore",
        "lat": 1.3644,
        "lon": 103.9915,
        "elevation_ft": 22,
        "runways": [
            {"name": "02L/20R", "heading_02": 20, "heading_20": 200, "lat": 1.3550, "lon": 103.9850},
            {"name": "02C/20C", "heading_02": 20, "heading_20": 200, "lat": 1.3650, "lon": 103.9950},
            {"name": "02R/20L", "heading_02": 20, "heading_20": 200, "lat": 1.3750, "lon": 104.0050},
        ]
    },
    # Tokyo Narita
    "RJAA": {
        "name": "Narita International",
        "city": "Tokyo",
        "country": "Japan",
        "lat": 35.7720,
        "lon": 140.3929,
        "elevation_ft": 141,
        "runways": [
            {"name": "16L/34R", "heading_16": 160, "heading_34": 340, "lat": 35.7800, "lon": 140.3850},
            {"name": "16R/34L", "heading_16": 160, "heading_34": 340, "lat": 35.7650, "lon": 140.4000},
        ]
    },
    # Sydney
    "YSSY": {
        "name": "Sydney Kingsford Smith",
        "city": "Sydney",
        "country": "Australia",
        "lat": -33.9461,
        "lon": 151.1772,
        "elevation_ft": 21,
        "runways": [
            {"name": "07/25", "heading_07": 70, "heading_25": 250, "lat": -33.9450, "lon": 151.1700},
            {"name": "16L/34R", "heading_16": 165, "heading_34": 345, "lat": -33.9350, "lon": 151.1750},
            {"name": "16R/34L", "heading_16": 165, "heading_34": 345, "lat": -33.9550, "lon": 151.1800},
        ]
    },
    # Chicago O'Hare
    "KORD": {
        "name": "Chicago O'Hare International",
        "city": "Chicago",
        "country": "United States",
        "lat": 41.9742,
        "lon": -87.9073,
        "elevation_ft": 672,
        "runways": [
            {"name": "09L/27R", "heading_09": 90, "heading_27": 270, "lat": 41.9800, "lon": -87.9200},
            {"name": "09R/27L", "heading_09": 90, "heading_27": 270, "lat": 41.9700, "lon": -87.9000},
            {"name": "10L/28R", "heading_10": 100, "heading_28": 280, "lat": 41.9850, "lon": -87.8900},
            {"name": "10C/28C", "heading_10": 100, "heading_28": 280, "lat": 41.9750, "lon": -87.9100},
            {"name": "10R/28L", "heading_10": 100, "heading_28": 280, "lat": 41.9650, "lon": -87.9300},
        ]
    },
    # Madrid Barajas
    "LEMD": {
        "name": "Adolfo Suárez Madrid-Barajas",
        "city": "Madrid",
        "country": "Spain",
        "lat": 40.4983,
        "lon": -3.5676,
        "elevation_ft": 1998,
        "runways": [
            {"name": "14L/32R", "heading_14": 143, "heading_32": 323, "lat": 40.5100, "lon": -3.5800},
            {"name": "14R/32L", "heading_14": 143, "heading_32": 323, "lat": 40.4900, "lon": -3.5600},
            {"name": "18L/36R", "heading_18": 180, "heading_36": 360, "lat": 40.5000, "lon": -3.5500},
            {"name": "18R/36L", "heading_18": 180, "heading_36": 360, "lat": 40.4850, "lon": -3.5900},
        ]
    },
    # Beijing Capital
    "ZBAA": {
        "name": "Beijing Capital International",
        "city": "Beijing",
        "country": "China",
        "lat": 40.0799,
        "lon": 116.6031,
        "elevation_ft": 116,
        "runways": [
            {"name": "01/19", "heading_01": 10, "heading_19": 190, "lat": 40.0800, "lon": 116.5900},
            {"name": "18L/36R", "heading_18": 180, "heading_36": 360, "lat": 40.0850, "lon": 116.6100},
            {"name": "18R/36L", "heading_18": 180, "heading_36": 360, "lat": 40.0750, "lon": 116.6200},
        ]
    },
    # Hong Kong
    "VHHH": {
        "name": "Hong Kong International",
        "city": "Hong Kong",
        "country": "Hong Kong",
        "lat": 22.3080,
        "lon": 113.9185,
        "elevation_ft": 28,
        "runways": [
            {"name": "07L/25R", "heading_07": 72, "heading_25": 252, "lat": 22.3150, "lon": 113.9000},
            {"name": "07R/25L", "heading_07": 72, "heading_25": 252, "lat": 22.3000, "lon": 113.9350},
        ]
    },
    # Atlanta
    "KATL": {
        "name": "Hartsfield-Jackson Atlanta International",
        "city": "Atlanta",
        "country": "United States",
        "lat": 33.6407,
        "lon": -84.4277,
        "elevation_ft": 1026,
        "runways": [
            {"name": "08L/26R", "heading_08": 89, "heading_26": 269, "lat": 33.6500, "lon": -84.4400},
            {"name": "08R/26L", "heading_08": 89, "heading_26": 269, "lat": 33.6450, "lon": -84.4300},
            {"name": "09L/27R", "heading_09": 89, "heading_27": 269, "lat": 33.6350, "lon": -84.4200},
            {"name": "09R/27L", "heading_09": 89, "heading_27": 269, "lat": 33.6300, "lon": -84.4100},
            {"name": "10/28", "heading_10": 96, "heading_28": 276, "lat": 33.6250, "lon": -84.4000},
        ]
    },
    # Paris Orly
    "LFPO": {
        "name": "Paris Orly",
        "city": "Paris",
        "country": "France",
        "lat": 48.7262,
        "lon": 2.3652,
        "elevation_ft": 291,
        "runways": [
            {"name": "06/24", "heading_06": 60, "heading_24": 240, "lat": 48.7300, "lon": 2.3500},
            {"name": "07/25", "heading_07": 73, "heading_25": 253, "lat": 48.7230, "lon": 2.3750},
            {"name": "02/20", "heading_02": 20, "heading_20": 200, "lat": 48.7280, "lon": 2.3600},
        ]
    },
    # Munich
    "EDDM": {
        "name": "Munich International",
        "city": "Munich",
        "country": "Germany",
        "lat": 48.3538,
        "lon": 11.7861,
        "elevation_ft": 1487,
        "runways": [
            {"name": "08L/26R", "heading_08": 80, "heading_26": 260, "lat": 48.3600, "lon": 11.7600},
            {"name": "08R/26L", "heading_08": 80, "heading_26": 260, "lat": 48.3480, "lon": 11.8100},
        ]
    },
    # Toronto Pearson
    "CYYZ": {
        "name": "Toronto Pearson International",
        "city": "Toronto",
        "country": "Canada",
        "lat": 43.6777,
        "lon": -79.6248,
        "elevation_ft": 569,
        "runways": [
            {"name": "05/23", "heading_05": 55, "heading_23": 235, "lat": 43.6850, "lon": -79.6400},
            {"name": "06L/24R", "heading_06": 62, "heading_24": 242, "lat": 43.6750, "lon": -79.6200},
            {"name": "06R/24L", "heading_06": 62, "heading_24": 242, "lat": 43.6650, "lon": -79.6100},
            {"name": "15L/33R", "heading_15": 152, "heading_33": 332, "lat": 43.6800, "lon": -79.6300},
            {"name": "15R/33L", "heading_15": 152, "heading_33": 332, "lat": 43.6700, "lon": -79.6150},
        ]
    },
    # Istanbul
    "LTFM": {
        "name": "Istanbul Airport",
        "city": "Istanbul",
        "country": "Turkey",
        "lat": 41.2753,
        "lon": 28.7519,
        "elevation_ft": 325,
        "runways": [
            {"name": "16L/34R", "heading_16": 163, "heading_34": 343, "lat": 41.2900, "lon": 28.7400},
            {"name": "16R/34L", "heading_16": 163, "heading_34": 343, "lat": 41.2800, "lon": 28.7600},
            {"name": "17L/35R", "heading_17": 173, "heading_35": 353, "lat": 41.2700, "lon": 28.7700},
            {"name": "17R/35L", "heading_17": 173, "heading_35": 353, "lat": 41.2600, "lon": 28.7500},
        ]
    },
    # Nice Côte d'Azur
    "LFMN": {
        "name": "Nice Côte d'Azur",
        "city": "Nice",
        "country": "France",
        "lat": 43.6584,
        "lon": 7.2159,
        "elevation_ft": 12,
        "runways": [
            {"name": "04L/22R", "heading_04": 40, "heading_22": 220, "lat": 43.6600, "lon": 7.2000},
            {"name": "04R/22L", "heading_04": 40, "heading_22": 220, "lat": 43.6550, "lon": 7.2300},
        ]
    },
    
    # ============================================
    # ADDITIONAL FRENCH AIRPORTS
    # ============================================
    
    # Lyon-Saint Exupéry
    "LFLL": {
        "name": "Lyon-Saint Exupéry",
        "city": "Lyon",
        "country": "France",
        "lat": 45.7256,
        "lon": 5.0811,
        "elevation_ft": 821,
        "runways": [
            {"name": "17L/35R", "heading_17": 174, "heading_35": 354, "lat": 45.7350, "lon": 5.0750},
            {"name": "17R/35L", "heading_17": 174, "heading_35": 354, "lat": 45.7200, "lon": 5.0900},
        ]
    },
    # Toulouse-Blagnac
    "LFBO": {
        "name": "Toulouse-Blagnac",
        "city": "Toulouse",
        "country": "France",
        "lat": 43.6293,
        "lon": 1.3638,
        "elevation_ft": 499,
        "runways": [
            {"name": "14L/32R", "heading_14": 144, "heading_32": 324, "lat": 43.6400, "lon": 1.3500},
            {"name": "14R/32L", "heading_14": 144, "heading_32": 324, "lat": 43.6200, "lon": 1.3750},
        ]
    },
    # Marseille Provence
    "LFML": {
        "name": "Marseille Provence",
        "city": "Marseille",
        "country": "France",
        "lat": 43.4393,
        "lon": 5.2214,
        "elevation_ft": 74,
        "runways": [
            {"name": "13L/31R", "heading_13": 133, "heading_31": 313, "lat": 43.4450, "lon": 5.2100},
            {"name": "13R/31L", "heading_13": 133, "heading_31": 313, "lat": 43.4350, "lon": 5.2300},
        ]
    },
    # Bordeaux-Mérignac
    "LFBD": {
        "name": "Bordeaux-Mérignac",
        "city": "Bordeaux",
        "country": "France",
        "lat": 44.8283,
        "lon": -0.7156,
        "elevation_ft": 162,
        "runways": [
            {"name": "05/23", "heading_05": 52, "heading_23": 232, "lat": 44.8300, "lon": -0.7200},
            {"name": "11/29", "heading_11": 112, "heading_29": 292, "lat": 44.8250, "lon": -0.7100},
        ]
    },
    # Nantes Atlantique
    "LFRS": {
        "name": "Nantes Atlantique",
        "city": "Nantes",
        "country": "France",
        "lat": 47.1532,
        "lon": -1.6107,
        "elevation_ft": 90,
        "runways": [
            {"name": "03/21", "heading_03": 30, "heading_21": 210, "lat": 47.1550, "lon": -1.6150},
        ]
    },
    # Basel-Mulhouse-Freiburg (EuroAirport)
    "LFSB": {
        "name": "EuroAirport Basel-Mulhouse-Freiburg",
        "city": "Basel/Mulhouse",
        "country": "France/Switzerland",
        "lat": 47.5896,
        "lon": 7.5299,
        "elevation_ft": 885,
        "runways": [
            {"name": "15/33", "heading_15": 153, "heading_33": 333, "lat": 47.5950, "lon": 7.5250},
            {"name": "08/26", "heading_08": 82, "heading_26": 262, "lat": 47.5850, "lon": 7.5350},
        ]
    },
    # Strasbourg
    "LFST": {
        "name": "Strasbourg",
        "city": "Strasbourg",
        "country": "France",
        "lat": 48.5383,
        "lon": 7.6281,
        "elevation_ft": 505,
        "runways": [
            {"name": "05/23", "heading_05": 52, "heading_23": 232, "lat": 48.5400, "lon": 7.6200},
        ]
    },
    # Lille
    "LFQQ": {
        "name": "Lille-Lesquin",
        "city": "Lille",
        "country": "France",
        "lat": 50.5617,
        "lon": 3.0894,
        "elevation_ft": 157,
        "runways": [
            {"name": "08/26", "heading_08": 79, "heading_26": 259, "lat": 50.5600, "lon": 3.0850},
            {"name": "01/19", "heading_01": 14, "heading_19": 194, "lat": 50.5650, "lon": 3.0950},
        ]
    },
    # Montpellier
    "LFMT": {
        "name": "Montpellier-Méditerranée",
        "city": "Montpellier",
        "country": "France",
        "lat": 43.5762,
        "lon": 3.9630,
        "elevation_ft": 17,
        "runways": [
            {"name": "12L/30R", "heading_12": 122, "heading_30": 302, "lat": 43.5800, "lon": 3.9550},
            {"name": "12R/30L", "heading_12": 122, "heading_30": 302, "lat": 43.5720, "lon": 3.9700},
        ]
    },
    # Rennes
    "LFRN": {
        "name": "Rennes-Saint-Jacques",
        "city": "Rennes",
        "country": "France",
        "lat": 48.0695,
        "lon": -1.7348,
        "elevation_ft": 124,
        "runways": [
            {"name": "10/28", "heading_10": 100, "heading_28": 280, "lat": 48.0700, "lon": -1.7400},
        ]
    },
    # Biarritz
    "LFBZ": {
        "name": "Biarritz-Pays Basque",
        "city": "Biarritz",
        "country": "France",
        "lat": 43.4684,
        "lon": -1.5311,
        "elevation_ft": 245,
        "runways": [
            {"name": "09/27", "heading_09": 93, "heading_27": 273, "lat": 43.4700, "lon": -1.5350},
        ]
    },
    # Ajaccio (Corsica)
    "LFKJ": {
        "name": "Ajaccio Napoléon Bonaparte",
        "city": "Ajaccio",
        "country": "France",
        "lat": 41.9236,
        "lon": 8.8029,
        "elevation_ft": 18,
        "runways": [
            {"name": "02/20", "heading_02": 20, "heading_20": 200, "lat": 41.9250, "lon": 8.8000},
        ]
    },
    # Bastia (Corsica)
    "LFKB": {
        "name": "Bastia-Poretta",
        "city": "Bastia",
        "country": "France",
        "lat": 42.5527,
        "lon": 9.4837,
        "elevation_ft": 26,
        "runways": [
            {"name": "16/34", "heading_16": 160, "heading_34": 340, "lat": 42.5550, "lon": 9.4800},
        ]
    },
    
    # ============================================
    # ADDITIONAL UK AIRPORTS
    # ============================================
    
    # London Gatwick
    "EGKK": {
        "name": "London Gatwick",
        "city": "London",
        "country": "United Kingdom",
        "lat": 51.1481,
        "lon": -0.1903,
        "elevation_ft": 202,
        "runways": [
            {"name": "08L/26R", "heading_08": 79, "heading_26": 259, "lat": 51.1550, "lon": -0.2000},
            {"name": "08R/26L", "heading_08": 79, "heading_26": 259, "lat": 51.1420, "lon": -0.1800},
        ]
    },
    # London Stansted
    "EGSS": {
        "name": "London Stansted",
        "city": "London",
        "country": "United Kingdom",
        "lat": 51.8850,
        "lon": 0.2350,
        "elevation_ft": 348,
        "runways": [
            {"name": "04/22", "heading_04": 41, "heading_22": 221, "lat": 51.8900, "lon": 0.2300},
        ]
    },
    # London Luton
    "EGGW": {
        "name": "London Luton",
        "city": "London",
        "country": "United Kingdom",
        "lat": 51.8747,
        "lon": -0.3683,
        "elevation_ft": 526,
        "runways": [
            {"name": "07/25", "heading_07": 79, "heading_25": 259, "lat": 51.8750, "lon": -0.3700},
        ]
    },
    # London City
    "EGLC": {
        "name": "London City",
        "city": "London",
        "country": "United Kingdom",
        "lat": 51.5053,
        "lon": 0.0553,
        "elevation_ft": 19,
        "runways": [
            {"name": "09/27", "heading_09": 93, "heading_27": 273, "lat": 51.5050, "lon": 0.0550},
        ]
    },
    # Manchester
    "EGCC": {
        "name": "Manchester",
        "city": "Manchester",
        "country": "United Kingdom",
        "lat": 53.3537,
        "lon": -2.2750,
        "elevation_ft": 257,
        "runways": [
            {"name": "05L/23R", "heading_05": 51, "heading_23": 231, "lat": 53.3600, "lon": -2.2850},
            {"name": "05R/23L", "heading_05": 51, "heading_23": 231, "lat": 53.3480, "lon": -2.2650},
        ]
    },
    # Birmingham
    "EGBB": {
        "name": "Birmingham",
        "city": "Birmingham",
        "country": "United Kingdom",
        "lat": 52.4539,
        "lon": -1.7480,
        "elevation_ft": 327,
        "runways": [
            {"name": "15/33", "heading_15": 150, "heading_33": 330, "lat": 52.4550, "lon": -1.7500},
        ]
    },
    # Edinburgh
    "EGPH": {
        "name": "Edinburgh",
        "city": "Edinburgh",
        "country": "United Kingdom",
        "lat": 55.9500,
        "lon": -3.3725,
        "elevation_ft": 135,
        "runways": [
            {"name": "06/24", "heading_06": 62, "heading_24": 242, "lat": 55.9520, "lon": -3.3800},
        ]
    },
    # Glasgow
    "EGPF": {
        "name": "Glasgow",
        "city": "Glasgow",
        "country": "United Kingdom",
        "lat": 55.8719,
        "lon": -4.4331,
        "elevation_ft": 26,
        "runways": [
            {"name": "05/23", "heading_05": 52, "heading_23": 232, "lat": 55.8750, "lon": -4.4400},
        ]
    },
    # Bristol
    "EGGD": {
        "name": "Bristol",
        "city": "Bristol",
        "country": "United Kingdom",
        "lat": 51.3827,
        "lon": -2.7190,
        "elevation_ft": 622,
        "runways": [
            {"name": "09/27", "heading_09": 93, "heading_27": 273, "lat": 51.3830, "lon": -2.7200},
        ]
    },
    # Liverpool
    "EGGP": {
        "name": "Liverpool John Lennon",
        "city": "Liverpool",
        "country": "United Kingdom",
        "lat": 53.3336,
        "lon": -2.8497,
        "elevation_ft": 80,
        "runways": [
            {"name": "09/27", "heading_09": 93, "heading_27": 273, "lat": 53.3340, "lon": -2.8500},
        ]
    },
    # Newcastle
    "EGNT": {
        "name": "Newcastle",
        "city": "Newcastle",
        "country": "United Kingdom",
        "lat": 55.0375,
        "lon": -1.6917,
        "elevation_ft": 266,
        "runways": [
            {"name": "07/25", "heading_07": 71, "heading_25": 251, "lat": 55.0380, "lon": -1.6920},
        ]
    },
    # Belfast International
    "EGAA": {
        "name": "Belfast International",
        "city": "Belfast",
        "country": "United Kingdom",
        "lat": 54.6575,
        "lon": -6.2158,
        "elevation_ft": 268,
        "runways": [
            {"name": "07/25", "heading_07": 71, "heading_25": 251, "lat": 54.6580, "lon": -6.2160},
            {"name": "17/35", "heading_17": 173, "heading_35": 353, "lat": 54.6600, "lon": -6.2200},
        ]
    },
    
    # ============================================
    # ADDITIONAL GERMAN AIRPORTS
    # ============================================
    
    # Berlin Brandenburg
    "EDDB": {
        "name": "Berlin Brandenburg",
        "city": "Berlin",
        "country": "Germany",
        "lat": 52.3514,
        "lon": 13.4939,
        "elevation_ft": 157,
        "runways": [
            {"name": "07L/25R", "heading_07": 70, "heading_25": 250, "lat": 52.3600, "lon": 13.4800},
            {"name": "07R/25L", "heading_07": 70, "heading_25": 250, "lat": 52.3450, "lon": 13.5100},
        ]
    },
    # Düsseldorf
    "EDDL": {
        "name": "Düsseldorf",
        "city": "Düsseldorf",
        "country": "Germany",
        "lat": 51.2895,
        "lon": 6.7668,
        "elevation_ft": 147,
        "runways": [
            {"name": "05L/23R", "heading_05": 50, "heading_23": 230, "lat": 51.2950, "lon": 6.7600},
            {"name": "05R/23L", "heading_05": 50, "heading_23": 230, "lat": 51.2850, "lon": 6.7750},
        ]
    },
    # Hamburg
    "EDDH": {
        "name": "Hamburg",
        "city": "Hamburg",
        "country": "Germany",
        "lat": 53.6304,
        "lon": 9.9882,
        "elevation_ft": 53,
        "runways": [
            {"name": "05/23", "heading_05": 50, "heading_23": 230, "lat": 53.6350, "lon": 9.9800},
            {"name": "15/33", "heading_15": 152, "heading_33": 332, "lat": 53.6280, "lon": 9.9950},
        ]
    },
    # Cologne Bonn
    "EDDK": {
        "name": "Cologne Bonn",
        "city": "Cologne",
        "country": "Germany",
        "lat": 50.8659,
        "lon": 7.1427,
        "elevation_ft": 302,
        "runways": [
            {"name": "06/24", "heading_06": 60, "heading_24": 240, "lat": 50.8700, "lon": 7.1350},
            {"name": "14L/32R", "heading_14": 140, "heading_32": 320, "lat": 50.8620, "lon": 7.1500},
            {"name": "14R/32L", "heading_14": 140, "heading_32": 320, "lat": 50.8580, "lon": 7.1550},
        ]
    },
    # Stuttgart
    "EDDS": {
        "name": "Stuttgart",
        "city": "Stuttgart",
        "country": "Germany",
        "lat": 48.6899,
        "lon": 9.2220,
        "elevation_ft": 1276,
        "runways": [
            {"name": "07/25", "heading_07": 70, "heading_25": 250, "lat": 48.6900, "lon": 9.2200},
        ]
    },
    # Hanover
    "EDDV": {
        "name": "Hanover",
        "city": "Hanover",
        "country": "Germany",
        "lat": 52.4611,
        "lon": 9.6850,
        "elevation_ft": 183,
        "runways": [
            {"name": "09L/27R", "heading_09": 92, "heading_27": 272, "lat": 52.4650, "lon": 9.6750},
            {"name": "09R/27L", "heading_09": 92, "heading_27": 272, "lat": 52.4580, "lon": 9.6950},
        ]
    },
    # Nuremberg
    "EDDN": {
        "name": "Nuremberg",
        "city": "Nuremberg",
        "country": "Germany",
        "lat": 49.4987,
        "lon": 11.0669,
        "elevation_ft": 1046,
        "runways": [
            {"name": "10/28", "heading_10": 100, "heading_28": 280, "lat": 49.4990, "lon": 11.0650},
        ]
    },
    # Leipzig/Halle
    "EDDP": {
        "name": "Leipzig/Halle",
        "city": "Leipzig",
        "country": "Germany",
        "lat": 51.4324,
        "lon": 12.2416,
        "elevation_ft": 465,
        "runways": [
            {"name": "08L/26R", "heading_08": 82, "heading_26": 262, "lat": 51.4380, "lon": 12.2300},
            {"name": "08R/26L", "heading_08": 82, "heading_26": 262, "lat": 51.4280, "lon": 12.2550},
        ]
    },
    # Bremen
    "EDDW": {
        "name": "Bremen",
        "city": "Bremen",
        "country": "Germany",
        "lat": 53.0475,
        "lon": 8.7867,
        "elevation_ft": 14,
        "runways": [
            {"name": "09/27", "heading_09": 91, "heading_27": 271, "lat": 53.0480, "lon": 8.7850},
        ]
    },
    
    # ============================================
    # ADDITIONAL SPANISH AIRPORTS
    # ============================================
    
    # Barcelona El Prat
    "LEBL": {
        "name": "Barcelona El Prat",
        "city": "Barcelona",
        "country": "Spain",
        "lat": 41.2971,
        "lon": 2.0785,
        "elevation_ft": 12,
        "runways": [
            {"name": "02/20", "heading_02": 20, "heading_20": 200, "lat": 41.3000, "lon": 2.0700},
            {"name": "07L/25R", "heading_07": 70, "heading_25": 250, "lat": 41.2950, "lon": 2.0850},
            {"name": "07R/25L", "heading_07": 70, "heading_25": 250, "lat": 41.2850, "lon": 2.1000},
        ]
    },
    # Palma de Mallorca
    "LEPA": {
        "name": "Palma de Mallorca",
        "city": "Palma",
        "country": "Spain",
        "lat": 39.5517,
        "lon": 2.7388,
        "elevation_ft": 27,
        "runways": [
            {"name": "06L/24R", "heading_06": 61, "heading_24": 241, "lat": 39.5600, "lon": 2.7250},
            {"name": "06R/24L", "heading_06": 61, "heading_24": 241, "lat": 39.5450, "lon": 2.7500},
        ]
    },
    # Malaga
    "LEMG": {
        "name": "Málaga-Costa del Sol",
        "city": "Málaga",
        "country": "Spain",
        "lat": 36.6749,
        "lon": -4.4991,
        "elevation_ft": 53,
        "runways": [
            {"name": "12/30", "heading_12": 124, "heading_30": 304, "lat": 36.6780, "lon": -4.5050},
            {"name": "13/31", "heading_13": 130, "heading_31": 310, "lat": 36.6720, "lon": -4.4930},
        ]
    },
    # Alicante
    "LEAL": {
        "name": "Alicante-Elche",
        "city": "Alicante",
        "country": "Spain",
        "lat": 38.2822,
        "lon": -0.5582,
        "elevation_ft": 142,
        "runways": [
            {"name": "10/28", "heading_10": 100, "heading_28": 280, "lat": 38.2830, "lon": -0.5600},
        ]
    },
    # Valencia
    "LEVC": {
        "name": "Valencia",
        "city": "Valencia",
        "country": "Spain",
        "lat": 39.4893,
        "lon": -0.4816,
        "elevation_ft": 228,
        "runways": [
            {"name": "12/30", "heading_12": 120, "heading_30": 300, "lat": 39.4900, "lon": -0.4820},
        ]
    },
    # Seville
    "LEZL": {
        "name": "Seville",
        "city": "Seville",
        "country": "Spain",
        "lat": 37.4180,
        "lon": -5.8931,
        "elevation_ft": 112,
        "runways": [
            {"name": "09/27", "heading_09": 93, "heading_27": 273, "lat": 37.4185, "lon": -5.8940},
        ]
    },
    # Bilbao
    "LEBB": {
        "name": "Bilbao",
        "city": "Bilbao",
        "country": "Spain",
        "lat": 43.3011,
        "lon": -2.9106,
        "elevation_ft": 138,
        "runways": [
            {"name": "10/28", "heading_10": 103, "heading_28": 283, "lat": 43.3020, "lon": -2.9120},
        ]
    },
    # Ibiza
    "LEIB": {
        "name": "Ibiza",
        "city": "Ibiza",
        "country": "Spain",
        "lat": 38.8729,
        "lon": 1.3731,
        "elevation_ft": 24,
        "runways": [
            {"name": "06/24", "heading_06": 60, "heading_24": 240, "lat": 38.8735, "lon": 1.3720},
        ]
    },
    # Tenerife South
    "GCTS": {
        "name": "Tenerife South",
        "city": "Tenerife",
        "country": "Spain",
        "lat": 28.0445,
        "lon": -16.5725,
        "elevation_ft": 209,
        "runways": [
            {"name": "07/25", "heading_07": 75, "heading_25": 255, "lat": 28.0450, "lon": -16.5730},
        ]
    },
    # Gran Canaria
    "GCLP": {
        "name": "Gran Canaria",
        "city": "Las Palmas",
        "country": "Spain",
        "lat": 27.9319,
        "lon": -15.3866,
        "elevation_ft": 78,
        "runways": [
            {"name": "03L/21R", "heading_03": 30, "heading_21": 210, "lat": 27.9380, "lon": -15.3900},
            {"name": "03R/21L", "heading_03": 30, "heading_21": 210, "lat": 27.9260, "lon": -15.3830},
        ]
    },
    
    # ============================================
    # ADDITIONAL ITALIAN AIRPORTS
    # ============================================
    
    # Rome Fiumicino
    "LIRF": {
        "name": "Rome Fiumicino",
        "city": "Rome",
        "country": "Italy",
        "lat": 41.8003,
        "lon": 12.2389,
        "elevation_ft": 15,
        "runways": [
            {"name": "07/25", "heading_07": 70, "heading_25": 250, "lat": 41.8050, "lon": 12.2300},
            {"name": "16L/34R", "heading_16": 163, "heading_34": 343, "lat": 41.8100, "lon": 12.2450},
            {"name": "16R/34L", "heading_16": 163, "heading_34": 343, "lat": 41.7950, "lon": 12.2500},
        ]
    },
    # Milan Malpensa
    "LIMC": {
        "name": "Milan Malpensa",
        "city": "Milan",
        "country": "Italy",
        "lat": 45.6306,
        "lon": 8.7231,
        "elevation_ft": 768,
        "runways": [
            {"name": "17L/35R", "heading_17": 173, "heading_35": 353, "lat": 45.6400, "lon": 8.7150},
            {"name": "17R/35L", "heading_17": 173, "heading_35": 353, "lat": 45.6220, "lon": 8.7300},
        ]
    },
    # Milan Linate
    "LIML": {
        "name": "Milan Linate",
        "city": "Milan",
        "country": "Italy",
        "lat": 45.4454,
        "lon": 9.2778,
        "elevation_ft": 353,
        "runways": [
            {"name": "17/35", "heading_17": 173, "heading_35": 353, "lat": 45.4480, "lon": 9.2760},
        ]
    },
    # Venice Marco Polo
    "LIPZ": {
        "name": "Venice Marco Polo",
        "city": "Venice",
        "country": "Italy",
        "lat": 45.5053,
        "lon": 12.3519,
        "elevation_ft": 7,
        "runways": [
            {"name": "04L/22R", "heading_04": 40, "heading_22": 220, "lat": 45.5100, "lon": 12.3450},
            {"name": "04R/22L", "heading_04": 40, "heading_22": 220, "lat": 45.5010, "lon": 12.3580},
        ]
    },
    # Naples
    "LIRN": {
        "name": "Naples International",
        "city": "Naples",
        "country": "Italy",
        "lat": 40.8860,
        "lon": 14.2908,
        "elevation_ft": 294,
        "runways": [
            {"name": "06/24", "heading_06": 60, "heading_24": 240, "lat": 40.8870, "lon": 14.2900},
        ]
    },
    # Bologna
    "LIPE": {
        "name": "Bologna Guglielmo Marconi",
        "city": "Bologna",
        "country": "Italy",
        "lat": 44.5354,
        "lon": 11.2887,
        "elevation_ft": 123,
        "runways": [
            {"name": "12/30", "heading_12": 123, "heading_30": 303, "lat": 44.5360, "lon": 11.2880},
        ]
    },
    # Florence
    "LIRQ": {
        "name": "Florence Peretola",
        "city": "Florence",
        "country": "Italy",
        "lat": 43.8100,
        "lon": 11.2051,
        "elevation_ft": 142,
        "runways": [
            {"name": "05/23", "heading_05": 50, "heading_23": 230, "lat": 43.8110, "lon": 11.2040},
        ]
    },
    # Pisa
    "LIRP": {
        "name": "Pisa International",
        "city": "Pisa",
        "country": "Italy",
        "lat": 43.6839,
        "lon": 10.3927,
        "elevation_ft": 6,
        "runways": [
            {"name": "04L/22R", "heading_04": 40, "heading_22": 220, "lat": 43.6870, "lon": 10.3880},
            {"name": "04R/22L", "heading_04": 40, "heading_22": 220, "lat": 43.6810, "lon": 10.3970},
        ]
    },
    # Turin
    "LIMF": {
        "name": "Turin Caselle",
        "city": "Turin",
        "country": "Italy",
        "lat": 45.2008,
        "lon": 7.6497,
        "elevation_ft": 989,
        "runways": [
            {"name": "18/36", "heading_18": 180, "heading_36": 360, "lat": 45.2020, "lon": 7.6490},
        ]
    },
    # Catania (Sicily)
    "LICC": {
        "name": "Catania-Fontanarossa",
        "city": "Catania",
        "country": "Italy",
        "lat": 37.4668,
        "lon": 15.0664,
        "elevation_ft": 39,
        "runways": [
            {"name": "08/26", "heading_08": 80, "heading_26": 260, "lat": 37.4675, "lon": 15.0650},
        ]
    },
    # Palermo (Sicily)
    "LICJ": {
        "name": "Palermo Falcone-Borsellino",
        "city": "Palermo",
        "country": "Italy",
        "lat": 38.1760,
        "lon": 13.0910,
        "elevation_ft": 65,
        "runways": [
            {"name": "07/25", "heading_07": 70, "heading_25": 250, "lat": 38.1765, "lon": 13.0900},
        ]
    },
    
    # ============================================
    # BENELUX AIRPORTS
    # ============================================
    
    # Brussels
    "EBBR": {
        "name": "Brussels Airport",
        "city": "Brussels",
        "country": "Belgium",
        "lat": 50.9014,
        "lon": 4.4844,
        "elevation_ft": 184,
        "runways": [
            {"name": "01/19", "heading_01": 12, "heading_19": 192, "lat": 50.9100, "lon": 4.4800},
            {"name": "07L/25R", "heading_07": 72, "heading_25": 252, "lat": 50.9050, "lon": 4.4750},
            {"name": "07R/25L", "heading_07": 72, "heading_25": 252, "lat": 50.8980, "lon": 4.4900},
        ]
    },
    # Brussels South Charleroi
    "EBCI": {
        "name": "Brussels South Charleroi",
        "city": "Charleroi",
        "country": "Belgium",
        "lat": 50.4592,
        "lon": 4.4538,
        "elevation_ft": 614,
        "runways": [
            {"name": "07/25", "heading_07": 70, "heading_25": 250, "lat": 50.4600, "lon": 4.4530},
        ]
    },
    # Luxembourg
    "ELLX": {
        "name": "Luxembourg Findel",
        "city": "Luxembourg",
        "country": "Luxembourg",
        "lat": 49.6233,
        "lon": 6.2044,
        "elevation_ft": 1234,
        "runways": [
            {"name": "06/24", "heading_06": 60, "heading_24": 240, "lat": 49.6240, "lon": 6.2030},
        ]
    },
    # Rotterdam The Hague
    "EHRD": {
        "name": "Rotterdam The Hague",
        "city": "Rotterdam",
        "country": "Netherlands",
        "lat": 51.9569,
        "lon": 4.4372,
        "elevation_ft": -15,
        "runways": [
            {"name": "06/24", "heading_06": 60, "heading_24": 240, "lat": 51.9575, "lon": 4.4360},
        ]
    },
    # Eindhoven
    "EHEH": {
        "name": "Eindhoven",
        "city": "Eindhoven",
        "country": "Netherlands",
        "lat": 51.4501,
        "lon": 5.3745,
        "elevation_ft": 74,
        "runways": [
            {"name": "04/22", "heading_04": 40, "heading_22": 220, "lat": 51.4510, "lon": 5.3730},
        ]
    },
    
    # ============================================
    # SWISS AIRPORTS
    # ============================================
    
    # Zurich
    "LSZH": {
        "name": "Zurich",
        "city": "Zurich",
        "country": "Switzerland",
        "lat": 47.4647,
        "lon": 8.5492,
        "elevation_ft": 1416,
        "runways": [
            {"name": "10/28", "heading_10": 100, "heading_28": 280, "lat": 47.4680, "lon": 8.5400},
            {"name": "14/32", "heading_14": 140, "heading_32": 320, "lat": 47.4620, "lon": 8.5550},
            {"name": "16/34", "heading_16": 160, "heading_34": 340, "lat": 47.4700, "lon": 8.5500},
        ]
    },
    # Geneva
    "LSGG": {
        "name": "Geneva",
        "city": "Geneva",
        "country": "Switzerland",
        "lat": 46.2381,
        "lon": 6.1089,
        "elevation_ft": 1411,
        "runways": [
            {"name": "04/22", "heading_04": 41, "heading_22": 221, "lat": 46.2400, "lon": 6.1050},
        ]
    },
    
    # ============================================
    # AUSTRIAN AIRPORTS
    # ============================================
    
    # Vienna
    "LOWW": {
        "name": "Vienna International",
        "city": "Vienna",
        "country": "Austria",
        "lat": 48.1103,
        "lon": 16.5697,
        "elevation_ft": 600,
        "runways": [
            {"name": "11/29", "heading_11": 110, "heading_29": 290, "lat": 48.1150, "lon": 16.5600},
            {"name": "16/34", "heading_16": 160, "heading_34": 340, "lat": 48.1080, "lon": 16.5750},
        ]
    },
    # Salzburg
    "LOWS": {
        "name": "Salzburg",
        "city": "Salzburg",
        "country": "Austria",
        "lat": 47.7933,
        "lon": 13.0043,
        "elevation_ft": 1411,
        "runways": [
            {"name": "15/33", "heading_15": 150, "heading_33": 330, "lat": 47.7940, "lon": 13.0030},
        ]
    },
    # Innsbruck
    "LOWI": {
        "name": "Innsbruck",
        "city": "Innsbruck",
        "country": "Austria",
        "lat": 47.2602,
        "lon": 11.3439,
        "elevation_ft": 1906,
        "runways": [
            {"name": "08/26", "heading_08": 80, "heading_26": 260, "lat": 47.2610, "lon": 11.3420},
        ]
    },
    
    # ============================================
    # SCANDINAVIAN AIRPORTS
    # ============================================
    
    # Copenhagen
    "EKCH": {
        "name": "Copenhagen Kastrup",
        "city": "Copenhagen",
        "country": "Denmark",
        "lat": 55.6181,
        "lon": 12.6560,
        "elevation_ft": 17,
        "runways": [
            {"name": "04L/22R", "heading_04": 40, "heading_22": 220, "lat": 55.6250, "lon": 12.6450},
            {"name": "04R/22L", "heading_04": 40, "heading_22": 220, "lat": 55.6120, "lon": 12.6650},
            {"name": "12/30", "heading_12": 120, "heading_30": 300, "lat": 55.6200, "lon": 12.6600},
        ]
    },
    # Oslo Gardermoen
    "ENGM": {
        "name": "Oslo Gardermoen",
        "city": "Oslo",
        "country": "Norway",
        "lat": 60.1939,
        "lon": 11.1004,
        "elevation_ft": 681,
        "runways": [
            {"name": "01L/19R", "heading_01": 13, "heading_19": 193, "lat": 60.2050, "lon": 11.0950},
            {"name": "01R/19L", "heading_01": 13, "heading_19": 193, "lat": 60.1850, "lon": 11.1050},
        ]
    },
    # Stockholm Arlanda
    "ESSA": {
        "name": "Stockholm Arlanda",
        "city": "Stockholm",
        "country": "Sweden",
        "lat": 59.6519,
        "lon": 17.9186,
        "elevation_ft": 137,
        "runways": [
            {"name": "01L/19R", "heading_01": 13, "heading_19": 193, "lat": 59.6600, "lon": 17.9100},
            {"name": "01R/19L", "heading_01": 13, "heading_19": 193, "lat": 59.6450, "lon": 17.9250},
            {"name": "08/26", "heading_08": 82, "heading_26": 262, "lat": 59.6550, "lon": 17.9200},
        ]
    },
    # Helsinki Vantaa
    "EFHK": {
        "name": "Helsinki Vantaa",
        "city": "Helsinki",
        "country": "Finland",
        "lat": 60.3172,
        "lon": 24.9633,
        "elevation_ft": 179,
        "runways": [
            {"name": "04L/22R", "heading_04": 43, "heading_22": 223, "lat": 60.3250, "lon": 24.9550},
            {"name": "04R/22L", "heading_04": 43, "heading_22": 223, "lat": 60.3100, "lon": 24.9700},
            {"name": "15/33", "heading_15": 150, "heading_33": 330, "lat": 60.3200, "lon": 24.9650},
        ]
    },
    # Bergen
    "ENBR": {
        "name": "Bergen Flesland",
        "city": "Bergen",
        "country": "Norway",
        "lat": 60.2934,
        "lon": 5.2181,
        "elevation_ft": 170,
        "runways": [
            {"name": "17/35", "heading_17": 173, "heading_35": 353, "lat": 60.2950, "lon": 5.2170},
        ]
    },
    # Gothenburg Landvetter
    "ESGG": {
        "name": "Gothenburg Landvetter",
        "city": "Gothenburg",
        "country": "Sweden",
        "lat": 57.6628,
        "lon": 12.2798,
        "elevation_ft": 506,
        "runways": [
            {"name": "03/21", "heading_03": 30, "heading_21": 210, "lat": 57.6650, "lon": 12.2750},
        ]
    },
    # Reykjavik Keflavik
    "BIKF": {
        "name": "Keflavik International",
        "city": "Reykjavik",
        "country": "Iceland",
        "lat": 63.9850,
        "lon": -22.6056,
        "elevation_ft": 171,
        "runways": [
            {"name": "01/19", "heading_01": 10, "heading_19": 190, "lat": 63.9900, "lon": -22.6100},
            {"name": "10/28", "heading_10": 100, "heading_28": 280, "lat": 63.9820, "lon": -22.6000},
        ]
    },
    
    # ============================================
    # PORTUGUESE AIRPORTS
    # ============================================
    
    # Lisbon
    "LPPT": {
        "name": "Lisbon Humberto Delgado",
        "city": "Lisbon",
        "country": "Portugal",
        "lat": 38.7813,
        "lon": -9.1359,
        "elevation_ft": 374,
        "runways": [
            {"name": "03/21", "heading_03": 30, "heading_21": 210, "lat": 38.7850, "lon": -9.1400},
            {"name": "17/35", "heading_17": 173, "heading_35": 353, "lat": 38.7780, "lon": -9.1300},
        ]
    },
    # Porto
    "LPPR": {
        "name": "Porto Francisco Sá Carneiro",
        "city": "Porto",
        "country": "Portugal",
        "lat": 41.2481,
        "lon": -8.6814,
        "elevation_ft": 228,
        "runways": [
            {"name": "17/35", "heading_17": 173, "heading_35": 353, "lat": 41.2500, "lon": -8.6800},
        ]
    },
    # Faro
    "LPFR": {
        "name": "Faro",
        "city": "Faro",
        "country": "Portugal",
        "lat": 37.0144,
        "lon": -7.9659,
        "elevation_ft": 24,
        "runways": [
            {"name": "10/28", "heading_10": 100, "heading_28": 280, "lat": 37.0150, "lon": -7.9670},
        ]
    },
    # Funchal (Madeira)
    "LPMA": {
        "name": "Funchal Cristiano Ronaldo",
        "city": "Funchal",
        "country": "Portugal",
        "lat": 32.6979,
        "lon": -16.7745,
        "elevation_ft": 192,
        "runways": [
            {"name": "05/23", "heading_05": 50, "heading_23": 230, "lat": 32.6990, "lon": -16.7760},
        ]
    },
    
    # ============================================
    # GREEK AIRPORTS
    # ============================================
    
    # Athens
    "LGAV": {
        "name": "Athens Eleftherios Venizelos",
        "city": "Athens",
        "country": "Greece",
        "lat": 37.9364,
        "lon": 23.9445,
        "elevation_ft": 308,
        "runways": [
            {"name": "03L/21R", "heading_03": 35, "heading_21": 215, "lat": 37.9450, "lon": 23.9350},
            {"name": "03R/21L", "heading_03": 35, "heading_21": 215, "lat": 37.9300, "lon": 23.9550},
        ]
    },
    # Thessaloniki
    "LGTS": {
        "name": "Thessaloniki Macedonia",
        "city": "Thessaloniki",
        "country": "Greece",
        "lat": 40.5197,
        "lon": 22.9709,
        "elevation_ft": 22,
        "runways": [
            {"name": "10/28", "heading_10": 100, "heading_28": 280, "lat": 40.5200, "lon": 22.9700},
        ]
    },
    # Heraklion (Crete)
    "LGIR": {
        "name": "Heraklion Nikos Kazantzakis",
        "city": "Heraklion",
        "country": "Greece",
        "lat": 35.3396,
        "lon": 25.1803,
        "elevation_ft": 115,
        "runways": [
            {"name": "09/27", "heading_09": 90, "heading_27": 270, "lat": 35.3400, "lon": 25.1790},
        ]
    },
    # Rhodes
    "LGRP": {
        "name": "Rhodes Diagoras",
        "city": "Rhodes",
        "country": "Greece",
        "lat": 36.4054,
        "lon": 28.0862,
        "elevation_ft": 17,
        "runways": [
            {"name": "07/25", "heading_07": 70, "heading_25": 250, "lat": 36.4060, "lon": 28.0850},
        ]
    },
    # Corfu
    "LGKR": {
        "name": "Corfu Ioannis Kapodistrias",
        "city": "Corfu",
        "country": "Greece",
        "lat": 39.6019,
        "lon": 19.9117,
        "elevation_ft": 6,
        "runways": [
            {"name": "17/35", "heading_17": 173, "heading_35": 353, "lat": 39.6030, "lon": 19.9110},
        ]
    },
    
    # ============================================
    # EASTERN EUROPEAN AIRPORTS
    # ============================================
    
    # Prague
    "LKPR": {
        "name": "Prague Václav Havel",
        "city": "Prague",
        "country": "Czech Republic",
        "lat": 50.1008,
        "lon": 14.2600,
        "elevation_ft": 1247,
        "runways": [
            {"name": "06/24", "heading_06": 60, "heading_24": 240, "lat": 50.1050, "lon": 14.2500},
            {"name": "12/30", "heading_12": 120, "heading_30": 300, "lat": 50.0980, "lon": 14.2700},
        ]
    },
    # Warsaw Chopin
    "EPWA": {
        "name": "Warsaw Chopin",
        "city": "Warsaw",
        "country": "Poland",
        "lat": 52.1657,
        "lon": 20.9671,
        "elevation_ft": 362,
        "runways": [
            {"name": "11/29", "heading_11": 110, "heading_29": 290, "lat": 52.1680, "lon": 20.9600},
            {"name": "15/33", "heading_15": 150, "heading_33": 330, "lat": 52.1630, "lon": 20.9750},
        ]
    },
    # Krakow
    "EPKK": {
        "name": "Krakow John Paul II",
        "city": "Krakow",
        "country": "Poland",
        "lat": 50.0777,
        "lon": 19.7848,
        "elevation_ft": 791,
        "runways": [
            {"name": "07/25", "heading_07": 70, "heading_25": 250, "lat": 50.0780, "lon": 19.7840},
        ]
    },
    # Budapest
    "LHBP": {
        "name": "Budapest Ferenc Liszt",
        "city": "Budapest",
        "country": "Hungary",
        "lat": 47.4298,
        "lon": 19.2611,
        "elevation_ft": 495,
        "runways": [
            {"name": "13L/31R", "heading_13": 130, "heading_31": 310, "lat": 47.4350, "lon": 19.2550},
            {"name": "13R/31L", "heading_13": 130, "heading_31": 310, "lat": 47.4250, "lon": 19.2680},
        ]
    },
    # Bucharest Henri Coandă
    "LROP": {
        "name": "Bucharest Henri Coandă",
        "city": "Bucharest",
        "country": "Romania",
        "lat": 44.5711,
        "lon": 26.0850,
        "elevation_ft": 314,
        "runways": [
            {"name": "08L/26R", "heading_08": 82, "heading_26": 262, "lat": 44.5750, "lon": 26.0750},
            {"name": "08R/26L", "heading_08": 82, "heading_26": 262, "lat": 44.5680, "lon": 26.0950},
        ]
    },
    # Sofia
    "LBSF": {
        "name": "Sofia",
        "city": "Sofia",
        "country": "Bulgaria",
        "lat": 42.6952,
        "lon": 23.4062,
        "elevation_ft": 1742,
        "runways": [
            {"name": "09/27", "heading_09": 90, "heading_27": 270, "lat": 42.6960, "lon": 23.4050},
        ]
    },
    # Zagreb
    "LDZA": {
        "name": "Zagreb Franjo Tuđman",
        "city": "Zagreb",
        "country": "Croatia",
        "lat": 45.7429,
        "lon": 16.0688,
        "elevation_ft": 353,
        "runways": [
            {"name": "05/23", "heading_05": 50, "heading_23": 230, "lat": 45.7450, "lon": 16.0650},
        ]
    },
    # Split
    "LDSP": {
        "name": "Split",
        "city": "Split",
        "country": "Croatia",
        "lat": 43.5389,
        "lon": 16.2980,
        "elevation_ft": 79,
        "runways": [
            {"name": "05/23", "heading_05": 50, "heading_23": 230, "lat": 43.5400, "lon": 16.2960},
        ]
    },
    # Dubrovnik
    "LDDU": {
        "name": "Dubrovnik",
        "city": "Dubrovnik",
        "country": "Croatia",
        "lat": 42.5614,
        "lon": 18.2681,
        "elevation_ft": 527,
        "runways": [
            {"name": "11/29", "heading_11": 110, "heading_29": 290, "lat": 42.5620, "lon": 18.2670},
        ]
    },
    # Belgrade
    "LYBE": {
        "name": "Belgrade Nikola Tesla",
        "city": "Belgrade",
        "country": "Serbia",
        "lat": 44.8184,
        "lon": 20.3091,
        "elevation_ft": 335,
        "runways": [
            {"name": "12/30", "heading_12": 120, "heading_30": 300, "lat": 44.8200, "lon": 20.3070},
        ]
    },
    # Bratislava
    "LZIB": {
        "name": "Bratislava M. R. Štefánik",
        "city": "Bratislava",
        "country": "Slovakia",
        "lat": 48.1702,
        "lon": 17.2127,
        "elevation_ft": 436,
        "runways": [
            {"name": "04/22", "heading_04": 40, "heading_22": 220, "lat": 48.1720, "lon": 17.2100},
            {"name": "13/31", "heading_13": 130, "heading_31": 310, "lat": 48.1680, "lon": 17.2160},
        ]
    },
    # Ljubljana
    "LJLJ": {
        "name": "Ljubljana Jože Pučnik",
        "city": "Ljubljana",
        "country": "Slovenia",
        "lat": 46.2237,
        "lon": 14.4576,
        "elevation_ft": 1273,
        "runways": [
            {"name": "12/30", "heading_12": 120, "heading_30": 300, "lat": 46.2250, "lon": 14.4560},
        ]
    },
    # Tallinn
    "EETN": {
        "name": "Tallinn Lennart Meri",
        "city": "Tallinn",
        "country": "Estonia",
        "lat": 59.4133,
        "lon": 24.8328,
        "elevation_ft": 131,
        "runways": [
            {"name": "08/26", "heading_08": 80, "heading_26": 260, "lat": 59.4140, "lon": 24.8310},
        ]
    },
    # Riga
    "EVRA": {
        "name": "Riga International",
        "city": "Riga",
        "country": "Latvia",
        "lat": 56.9236,
        "lon": 23.9711,
        "elevation_ft": 36,
        "runways": [
            {"name": "18/36", "heading_18": 180, "heading_36": 360, "lat": 56.9280, "lon": 23.9700},
        ]
    },
    # Vilnius
    "EYVI": {
        "name": "Vilnius International",
        "city": "Vilnius",
        "country": "Lithuania",
        "lat": 54.6341,
        "lon": 25.2858,
        "elevation_ft": 646,
        "runways": [
            {"name": "02/20", "heading_02": 20, "heading_20": 200, "lat": 54.6380, "lon": 25.2830},
        ]
    },
    
    # ============================================
    # IRISH AIRPORTS
    # ============================================
    
    # Dublin
    "EIDW": {
        "name": "Dublin",
        "city": "Dublin",
        "country": "Ireland",
        "lat": 53.4213,
        "lon": -6.2701,
        "elevation_ft": 242,
        "runways": [
            {"name": "10L/28R", "heading_10": 100, "heading_28": 280, "lat": 53.4250, "lon": -6.2800},
            {"name": "10R/28L", "heading_10": 100, "heading_28": 280, "lat": 53.4180, "lon": -6.2600},
            {"name": "16/34", "heading_16": 160, "heading_34": 340, "lat": 53.4230, "lon": -6.2750},
        ]
    },
    # Cork
    "EICK": {
        "name": "Cork",
        "city": "Cork",
        "country": "Ireland",
        "lat": 51.8413,
        "lon": -8.4911,
        "elevation_ft": 502,
        "runways": [
            {"name": "07/25", "heading_07": 70, "heading_25": 250, "lat": 51.8420, "lon": -8.4920},
            {"name": "16/34", "heading_16": 160, "heading_34": 340, "lat": 51.8400, "lon": -8.4900},
        ]
    },
    # Shannon
    "EINN": {
        "name": "Shannon",
        "city": "Shannon",
        "country": "Ireland",
        "lat": 52.7020,
        "lon": -8.9248,
        "elevation_ft": 46,
        "runways": [
            {"name": "06/24", "heading_06": 60, "heading_24": 240, "lat": 52.7030, "lon": -8.9260},
        ]
    },
    
    # ============================================
    # MALTA & CYPRUS
    # ============================================
    
    # Malta
    "LMML": {
        "name": "Malta International",
        "city": "Valletta",
        "country": "Malta",
        "lat": 35.8575,
        "lon": 14.4775,
        "elevation_ft": 300,
        "runways": [
            {"name": "13/31", "heading_13": 130, "heading_31": 310, "lat": 35.8590, "lon": 14.4760},
        ]
    },
    # Larnaca
    "LCLK": {
        "name": "Larnaca International",
        "city": "Larnaca",
        "country": "Cyprus",
        "lat": 34.8754,
        "lon": 33.6249,
        "elevation_ft": 8,
        "runways": [
            {"name": "04/22", "heading_04": 40, "heading_22": 220, "lat": 34.8780, "lon": 33.6200},
        ]
    },
    # Paphos
    "LCPH": {
        "name": "Paphos International",
        "city": "Paphos",
        "country": "Cyprus",
        "lat": 34.7180,
        "lon": 32.4857,
        "elevation_ft": 41,
        "runways": [
            {"name": "11/29", "heading_11": 110, "heading_29": 290, "lat": 34.7185, "lon": 32.4840},
        ]
    },
}

# ============================================
# PYDANTIC MODELS
# ============================================

class Aircraft(BaseModel):
    icao24: str
    callsign: Optional[str] = None
    latitude: float
    longitude: float
    altitude_ft: float
    velocity_knots: Optional[float] = None
    heading: Optional[float] = None
    vertical_rate: Optional[float] = None
    on_ground: bool = False
    distance_km: Optional[float] = None
    matched_runway: Optional[str] = None
    matched_direction: Optional[str] = None
    runway_lateral_distance_km: Optional[float] = None
    runway_threshold_distance_km: Optional[float] = None
    runway_match_score: Optional[float] = None
    data_source: Optional[str] = None

class RunwayStatus(BaseModel):
    runway_name: str
    direction: str  # e.g., "27R" or "09L"
    heading: int
    aircraft_count: int
    aircraft: List[Aircraft] = []

class AirportInfo(BaseModel):
    icao: str
    name: str
    city: str
    country: str
    lat: float
    lon: float
    elevation_ft: int
    iata: Optional[str] = None
    type: Optional[str] = None

class MetarData(BaseModel):
    raw: str
    wind_direction: Optional[int] = None
    wind_speed: Optional[int] = None
    wind_gust: Optional[int] = None
    wind_unit: str = "kt"
    visibility: Optional[str] = None
    temperature: Optional[float] = None  # Changed from int to float
    dewpoint: Optional[float] = None  # Changed from int to float
    altimeter: Optional[float] = None
    flight_category: Optional[str] = None
    clouds: Optional[str] = None
    weather: Optional[str] = None
    expected_runway_from_wind: Optional[str] = None

class RunwayDefinition(BaseModel):
    name: str
    headings: Dict[str, int]
    lat: float
    lon: float
    length_ft: Optional[int] = None
    width_ft: Optional[int] = None
    surface: Optional[str] = None
    lighted: Optional[bool] = None
    closed: Optional[bool] = None
    le_ident: Optional[str] = None
    he_ident: Optional[str] = None
    le_lat: Optional[float] = None
    le_lon: Optional[float] = None
    he_lat: Optional[float] = None
    he_lon: Optional[float] = None

class RunwayAnalysisResponse(BaseModel):
    airport: AirportInfo
    timestamp: datetime
    active_runways: List[RunwayStatus]
    total_landing_aircraft: int
    all_aircraft_nearby: List[Aircraft]
    message: str
    metar: Optional[MetarData] = None
    all_runways: List[RunwayDefinition] = []

# ============================================
# OURAIRPORTS PUBLIC-DOMAIN DATA LOADER
# ============================================

def _to_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _to_int(value: Any) -> Optional[int]:
    parsed = _to_float(value)
    return int(round(parsed)) if parsed is not None else None

def _heading_from_ident(ident: Optional[str]) -> Optional[int]:
    if not ident:
        return None
    digits = "".join(ch for ch in ident if ch.isdigit())
    if not digits:
        return None
    runway_number = int(digits)
    return 360 if runway_number == 36 else runway_number * 10

def _heading_key(ident: Optional[str], fallback: str) -> str:
    digits = "".join(ch for ch in ident or "" if ch.isdigit())
    return f"heading_{digits.zfill(2)}" if digits else f"heading_{fallback}"

def _runway_midpoint(runway: dict, airport: dict) -> tuple[float, float]:
    le_lat = runway.get("le_lat")
    le_lon = runway.get("le_lon")
    he_lat = runway.get("he_lat")
    he_lon = runway.get("he_lon")
    if all(v is not None for v in [le_lat, le_lon, he_lat, he_lon]):
        return ((le_lat + he_lat) / 2, (le_lon + he_lon) / 2)
    return (airport["lat"], airport["lon"])

def _build_fallback_airports() -> Dict[str, dict]:
    return AIRPORT_DATABASE

@lru_cache(maxsize=1)
def get_airport_database() -> Dict[str, dict]:
    """Load worldwide airport/runway data from OurAirports CSV, falling back to bundled sample data."""
    airports_path = DATA_DIR / "airports.csv"
    runways_path = DATA_DIR / "runways.csv"
    countries_path = DATA_DIR / "countries.csv"

    if not airports_path.exists() or not runways_path.exists():
        logger.warning("OurAirports CSV files not found; using bundled sample airport database.")
        return _build_fallback_airports()

    countries: Dict[str, str] = {}
    if countries_path.exists():
        with countries_path.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                countries[row["code"]] = row["name"]

    runway_rows_by_airport: Dict[str, List[dict]] = {}
    with runways_path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            if row.get("closed") == "1":
                continue

            le_ident = row.get("le_ident") or ""
            he_ident = row.get("he_ident") or ""
            if not le_ident and not he_ident:
                continue

            le_heading = _to_int(row.get("le_heading_degT")) or _heading_from_ident(le_ident)
            he_heading = _to_int(row.get("he_heading_degT")) or _heading_from_ident(he_ident)
            headings = {}
            if le_heading is not None:
                headings[_heading_key(le_ident, "le")] = le_heading
            if he_heading is not None:
                headings[_heading_key(he_ident, "he")] = he_heading

            runway = {
                "name": f"{le_ident}/{he_ident}".strip("/"),
                **headings,
                "length_ft": _to_int(row.get("length_ft")),
                "width_ft": _to_int(row.get("width_ft")),
                "surface": row.get("surface") or None,
                "lighted": row.get("lighted") == "1",
                "closed": False,
                "le_ident": le_ident or None,
                "he_ident": he_ident or None,
                "le_lat": _to_float(row.get("le_latitude_deg")),
                "le_lon": _to_float(row.get("le_longitude_deg")),
                "he_lat": _to_float(row.get("he_latitude_deg")),
                "he_lon": _to_float(row.get("he_longitude_deg")),
            }
            runway_rows_by_airport.setdefault(row["airport_ident"], []).append(runway)

    airports: Dict[str, dict] = {}
    with airports_path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            ident = row["ident"]
            runways = runway_rows_by_airport.get(ident, [])
            lat = _to_float(row.get("latitude_deg"))
            lon = _to_float(row.get("longitude_deg"))
            if not runways or lat is None or lon is None or row.get("type") == "closed_airport":
                continue

            airports[ident.upper()] = {
                "name": row.get("name") or ident,
                "city": row.get("municipality") or "",
                "country": countries.get(row.get("iso_country"), row.get("iso_country") or ""),
                "lat": lat,
                "lon": lon,
                "elevation_ft": _to_int(row.get("elevation_ft")) or 0,
                "iata": row.get("iata_code") or None,
                "type": row.get("type") or None,
                "runways": runways,
                "search_tokens": " ".join(
                    token for token in [
                        ident,
                        row.get("icao_code") or "",
                        row.get("iata_code") or "",
                        row.get("gps_code") or "",
                        row.get("local_code") or "",
                        row.get("name") or "",
                        row.get("municipality") or "",
                        countries.get(row.get("iso_country"), row.get("iso_country") or ""),
                        row.get("keywords") or "",
                    ]
                    if token
                ).upper(),
            }

    logger.info("Loaded %s airports with runway data from OurAirports.", len(airports))
    return airports or _build_fallback_airports()

def get_airport_by_ident(ident: str) -> Optional[dict]:
    return get_airport_database().get(ident.upper())

def build_airport_info(ident: str, data: dict) -> AirportInfo:
    return AirportInfo(
        icao=ident,
        name=data["name"],
        city=data.get("city") or "",
        country=data.get("country") or "",
        lat=data["lat"],
        lon=data["lon"],
        elevation_ft=data.get("elevation_ft", 0),
        iata=data.get("iata"),
        type=data.get("type"),
    )

# ============================================
# UTILITY FUNCTIONS
# ============================================

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in kilometers"""
    R = 6371  # Earth's radius in km
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

def normalize_heading(heading: float) -> float:
    """Normalize heading to 0-360 range"""
    while heading < 0:
        heading += 360
    while heading >= 360:
        heading -= 360
    return heading

def heading_difference(h1: float, h2: float) -> float:
    """Calculate smallest difference between two headings"""
    diff = abs(normalize_heading(h1) - normalize_heading(h2))
    return min(diff, 360 - diff)

def _local_xy_km(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    """Project lat/lon to a local tangent plane in kilometers."""
    cos_lat = math.cos(math.radians(origin_lat))
    return (
        (lon - origin_lon) * 111.320 * cos_lat,
        (lat - origin_lat) * 110.574,
    )

def _runway_endpoints(runway: dict) -> Optional[dict]:
    required = ["le_lat", "le_lon", "he_lat", "he_lon"]
    if not all(runway.get(key) is not None for key in required):
        return None
    return {
        "le": {
            "ident": runway.get("le_ident"),
            "lat": runway["le_lat"],
            "lon": runway["le_lon"],
        },
        "he": {
            "ident": runway.get("he_ident"),
            "lat": runway["he_lat"],
            "lon": runway["he_lon"],
        },
    }

def _runway_heading_for_ident(runway: dict, direction: Optional[str]) -> Optional[int]:
    if not direction:
        return None
    direction_digits = "".join(filter(str.isdigit, direction))
    for key, value in runway.items():
        if not key.startswith("heading_"):
            continue
        key_digits = key.replace("heading_", "")
        if direction_digits and int(direction_digits) == int(key_digits):
            return value
    return _heading_from_ident(direction)

def _score_runway_approach(aircraft: dict, runway: dict, direction: str, runway_heading: int) -> Optional[dict]:
    """Score how well an aircraft position aligns with a specific runway end."""
    endpoints = _runway_endpoints(runway)
    if not endpoints:
        return None

    if direction == runway.get("le_ident"):
        threshold = endpoints["le"]
        opposite = endpoints["he"]
    elif direction == runway.get("he_ident"):
        threshold = endpoints["he"]
        opposite = endpoints["le"]
    else:
        return None

    origin_lat = threshold["lat"]
    origin_lon = threshold["lon"]
    ac_x, ac_y = _local_xy_km(aircraft["latitude"], aircraft["longitude"], origin_lat, origin_lon)
    opposite_x, opposite_y = _local_xy_km(opposite["lat"], opposite["lon"], origin_lat, origin_lon)
    runway_length_km = math.hypot(opposite_x, opposite_y)
    if runway_length_km <= 0:
        return None

    # Unit vector points from landing threshold down the runway. Aircraft on final
    # should usually be on the negative side, approaching that threshold.
    unit_x = opposite_x / runway_length_km
    unit_y = opposite_y / runway_length_km
    along_km = ac_x * unit_x + ac_y * unit_y
    lateral_km = abs(ac_x * unit_y - ac_y * unit_x)
    threshold_distance_km = math.hypot(ac_x, ac_y)
    heading_diff = heading_difference(aircraft["heading"], runway_heading)

    if heading_diff > 25:
        return None
    if lateral_km > 2.5:
        return None
    if threshold_distance_km > 25:
        return None
    # Allow a little past-threshold tolerance because live ADS-B can lag, but
    # strongly prefer aircraft before the landing threshold.
    if along_km > min(1.2, runway_length_km * 0.45):
        return None

    score = (heading_diff * 0.12) + (lateral_km * 4.0) + (max(along_km, 0) * 2.0) + (threshold_distance_km * 0.015)
    return {
        "score": round(score, 3),
        "lateral_km": round(lateral_km, 3),
        "threshold_distance_km": round(threshold_distance_km, 3),
        "along_km": round(along_km, 3),
        "heading_diff": round(heading_diff, 1),
    }

def get_runway_direction_from_heading(runway: dict, aircraft_heading: float) -> Optional[str]:
    """Determine which runway direction based on aircraft heading"""
    runway_name = runway["name"]
    parts = runway_name.split("/")
    
    if len(parts) != 2:
        return None
    
    dir1, dir2 = parts
    
    # Extract headings from runway dict
    heading_keys = [k for k in runway.keys() if k.startswith("heading_")]
    
    best_match = None
    best_diff = 180
    
    for key in heading_keys:
        rwy_heading = runway[key]
        diff = heading_difference(aircraft_heading, rwy_heading)
        
        if diff < best_diff:
            best_diff = diff
            # Match the direction based on heading key
            dir_num = key.replace("heading_", "")
            # Find matching direction
            for d in [dir1, dir2]:
                # Extract numeric part
                num_part = ''.join(filter(str.isdigit, d))
                if num_part and int(num_part) == int(dir_num):
                    best_match = d
                    break
                # Check if heading matches approximately
                if int(dir_num) * 10 == int(round(rwy_heading / 10) * 10) % 360 or \
                   abs(int(dir_num) * 10 - rwy_heading) < 15:
                    if dir_num in d.lower() or str(int(dir_num)) in d:
                        best_match = d
                        break
    
    # Fallback: match based on heading value
    if best_match is None:
        for key in heading_keys:
            rwy_heading = runway[key]
            diff = heading_difference(aircraft_heading, rwy_heading)
            if diff < 30:  # Within 30 degrees
                dir_num = key.replace("heading_", "")
                for d in [dir1, dir2]:
                    num_only = ''.join(filter(str.isdigit, d))
                    if num_only == dir_num or (num_only and abs(int(num_only) - int(dir_num)) <= 1):
                        best_match = d
                        break
                if best_match:
                    break
    
    return best_match if best_diff < 30 else None

def build_airplanes_live_url(lat: float, lon: float, radius_km: float = 30) -> str:
    """Build Airplanes.live point-radius URL. Radius is in nautical miles."""
    radius_nm = max(1, min(250, round(radius_km / 1.852)))
    return f"https://api.airplanes.live/v2/point/{lat}/{lon}/{radius_nm}"

async def fetch_aircraft_from_airplanes_live(lat: float, lon: float, radius_km: float = 30) -> Optional[List[dict]]:
    """Fetch aircraft from Airplanes.live."""
    url = build_airplanes_live_url(lat, lon, radius_km)

    async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": "FlightQFUTracker/1.0"}) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            aircraft_rows = data.get("ac") or data.get("aircraft") or []
            aircraft_list = []

            for row in aircraft_rows:
                ac_lat = row.get("lat")
                ac_lon = row.get("lon")
                if ac_lat is None or ac_lon is None:
                    continue

                altitude_ft = row.get("alt_geom")
                if altitude_ft is None:
                    altitude_ft = row.get("alt_baro")
                if altitude_ft == "ground":
                    altitude_ft = 0
                altitude_ft = float(altitude_ft) if altitude_ft is not None else 0

                distance_nm = row.get("dst")
                distance_km = (float(distance_nm) * 1.852) if distance_nm is not None else haversine_distance(lat, lon, ac_lat, ac_lon)

                aircraft_list.append({
                    "icao24": row.get("hex") or "unknown",
                    "callsign": row.get("flight").strip() if row.get("flight") else None,
                    "latitude": ac_lat,
                    "longitude": ac_lon,
                    "altitude_ft": altitude_ft,
                    "velocity_knots": row.get("gs"),
                    "heading": row.get("track") or row.get("true_heading") or row.get("mag_heading"),
                    "vertical_rate": row.get("geom_rate") if row.get("geom_rate") is not None else row.get("baro_rate"),
                    "on_ground": altitude_ft == 0,
                    "distance_km": round(distance_km, 2),
                    "data_source": "Airplanes.live",
                })

            return aircraft_list
        except Exception as e:
            logger.warning(f"Error fetching aircraft data from Airplanes.live: {type(e).__name__}: {e!r}")
            return None

async def fetch_aircraft(lat: float, lon: float, radius_km: float = 30) -> List[dict]:
    """Fetch aircraft from Airplanes.live only."""
    cache_key = f"{round(lat, 3)}:{round(lon, 3)}:{round(radius_km)}"
    now = datetime.utcnow()
    cached = aircraft_cache.get(cache_key)
    if cached and (now - cached["timestamp"]).total_seconds() < 25:
        logger.info("Using cached Airplanes.live aircraft data.")
        return cached["aircraft"]

    airplanes_live_aircraft = await fetch_aircraft_from_airplanes_live(lat, lon, radius_km)
    if airplanes_live_aircraft is not None:
        aircraft_cache[cache_key] = {
            "timestamp": now,
            "aircraft": airplanes_live_aircraft,
        }
        return airplanes_live_aircraft
    return cached["aircraft"] if cached else []

async def fetch_metar(icao: str) -> Optional[dict]:
    """Fetch METAR weather data from aviationweather.gov"""
    url = f"https://aviationweather.gov/api/data/metar?ids={icao}&format=json"
    
    async with httpx.AsyncClient(timeout=15.0) as http_client:
        try:
            response = await http_client.get(url, headers={"User-Agent": "FlightQFUTracker/1.0"})
            if response.status_code == 204:
                return None
            response.raise_for_status()
            data = response.json()
            
            if not data or len(data) == 0:
                return None
            
            metar = data[0]
            
            # Parse wind direction and speed
            wind_dir = metar.get("wdir")
            wind_speed = metar.get("wspd")
            wind_gust = metar.get("wgst")
            
            # Parse clouds
            clouds_list = metar.get("clouds", [])
            cloud_str = ""
            if clouds_list:
                cloud_parts = []
                for c in clouds_list:
                    cover = c.get("cover", "")
                    base = c.get("base")
                    if base:
                        cloud_parts.append(f"{cover} {base}ft")
                    else:
                        cloud_parts.append(cover)
                cloud_str = ", ".join(cloud_parts)
            
            # Parse visibility
            visib = metar.get("visib")
            vis_str = f"{visib} SM" if visib is not None else None
            
            # Flight category
            flt_cat = metar.get("fltcat")
            
            # Raw METAR text
            raw_text = metar.get("rawOb", "")
            
            return {
                "raw": raw_text,
                "wind_direction": int(wind_dir) if wind_dir is not None and str(wind_dir).isdigit() else None,
                "wind_speed": int(wind_speed) if wind_speed is not None else None,
                "wind_gust": int(wind_gust) if wind_gust is not None else None,
                "wind_unit": "kt",
                "visibility": vis_str,
                "temperature": metar.get("temp"),
                "dewpoint": metar.get("dewp"),
                "altimeter": metar.get("altim"),
                "flight_category": flt_cat,
                "clouds": cloud_str if cloud_str else None,
                "weather": metar.get("wxString"),
            }
        except Exception as e:
            logger.warning(f"Failed to fetch METAR for {icao}: {e}")
            return None

def get_expected_runway_from_wind(wind_direction: Optional[int], runways: List[dict]) -> Optional[str]:
    """Determine expected landing runway based on wind direction (land INTO the wind)"""
    if wind_direction is None:
        return None
    
    # Aircraft land into the wind, so the runway heading should be close to wind direction
    best_direction = None
    best_diff = 180
    
    for runway in runways:
        heading_keys = [k for k in runway.keys() if k.startswith("heading_")]
        for key in heading_keys:
            rwy_heading = runway[key]
            diff = heading_difference(wind_direction, rwy_heading)
            if diff < best_diff:
                best_diff = diff
                direction = get_runway_direction_from_heading(runway, wind_direction)
                if direction:
                    best_direction = direction
    
    return best_direction

def analyze_landing_aircraft(aircraft_list: List[dict], airport: dict, max_altitude_agl_ft: float = 2000) -> List[dict]:
    """Filter aircraft that are likely landing"""
    landing_aircraft = []
    airport_elevation = airport.get("elevation_ft", 0)
    
    for ac in aircraft_list:
        # Skip aircraft on ground
        if ac.get("on_ground", False):
            continue
        
        # Calculate altitude above ground level
        agl = ac["altitude_ft"] - airport_elevation
        
        # Criteria for landing aircraft:
        # 1. Below 2000ft AGL
        # 2. Descending (negative vertical rate) OR very low and slow
        # 3. Has valid heading
        # 4. Reasonable distance from airport (within 20km for approach)
        
        is_low = agl > 0 and agl < max_altitude_agl_ft
        is_descending = ac.get("vertical_rate") is not None and ac["vertical_rate"] < 0
        has_heading = ac.get("heading") is not None
        is_close = ac.get("distance_km", 100) < 20
        is_slow = ac.get("velocity_knots") is not None and ac["velocity_knots"] < 200
        
        # Landing if: low altitude AND (descending OR very low and slow) AND has heading
        if is_low and has_heading and is_close and (is_descending or (agl < 500 and is_slow)):
            landing_aircraft.append(ac)
    
    return landing_aircraft

def match_aircraft_to_runways(landing_aircraft: List[dict], runways: List[dict]) -> Dict[str, List[dict]]:
    """Match landing aircraft to runways using heading plus lat/lon geometry."""
    runway_matches = {}
    
    for ac in landing_aircraft:
        if ac.get("heading") is None:
            continue
        
        best_match = None
        
        for runway in runways:
            heading_keys = [k for k in runway.keys() if k.startswith("heading_")]
            
            for key in heading_keys:
                rwy_heading = runway[key]
                direction = None
                dir_num = key.replace("heading_", "")
                for candidate in [runway.get("le_ident"), runway.get("he_ident")]:
                    candidate_digits = "".join(filter(str.isdigit, candidate or ""))
                    if candidate_digits and int(candidate_digits) == int(dir_num):
                        direction = candidate
                        break
                if not direction:
                    direction = get_runway_direction_from_heading(runway, ac["heading"])
                if not direction:
                    continue

                geometry_score = _score_runway_approach(ac, runway, direction, rwy_heading)
                if geometry_score is None:
                    continue

                match = {
                    "runway": runway,
                    "direction": direction,
                    "heading": rwy_heading,
                    **geometry_score,
                }
                if best_match is None or match["score"] < best_match["score"]:
                    best_match = match
        
        if best_match:
            matched_ac = {
                **ac,
                "matched_runway": best_match["runway"]["name"],
                "matched_direction": best_match["direction"],
                "runway_lateral_distance_km": best_match["lateral_km"],
                "runway_threshold_distance_km": best_match["threshold_distance_km"],
                "runway_match_score": best_match["score"],
            }
            key = f"{best_match['runway']['name']}_{best_match['direction']}"
            if key not in runway_matches:
                runway_matches[key] = {
                    "runway": best_match["runway"],
                    "direction": best_match["direction"],
                    "heading": best_match["heading"],
                    "aircraft": []
                }
            runway_matches[key]["aircraft"].append(matched_ac)
    
    return runway_matches

# ============================================
# API ROUTES
# ============================================

@api_router.get("/")
async def root():
    return {
        "message": "Flight QFU Tracker API",
        "version": "1.0.0",
        "data_source": "OurAirports public-domain CSV" if (DATA_DIR / "airports.csv").exists() else "bundled sample data",
        "airport_count": len(get_airport_database()),
    }

@api_router.get("/airports")
async def get_airports() -> List[AirportInfo]:
    """Get list of all airports with runway data"""
    airports = []
    for icao, data in get_airport_database().items():
        airports.append(build_airport_info(icao, data))
    return sorted(airports, key=lambda x: x.icao)

@api_router.get("/airports/{icao}")
async def get_airport(icao: str) -> dict:
    """Get detailed information about a specific airport"""
    icao = icao.upper()
    airport = get_airport_by_ident(icao)
    if not airport:
        raise HTTPException(status_code=404, detail=f"Airport {icao} not found in database")
    
    return {
        "icao": icao,
        **airport
    }

@api_router.get("/debug/aircraft/{icao}")
async def debug_aircraft(icao: str) -> dict:
    """Check whether the deployed server can reach Airplanes.live for an airport."""
    icao = icao.upper()
    airport = get_airport_by_ident(icao)
    if not airport:
        raise HTTPException(status_code=404, detail=f"Airport {icao} not found in database")

    url = build_airplanes_live_url(airport["lat"], airport["lon"], radius_km=30)
    started_at = datetime.utcnow()
    try:
        timeout = httpx.Timeout(connect=3.0, read=4.0, write=3.0, pool=3.0)
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "FlightQFUTracker/1.0"}) as client:
            response = await client.get(url)
        elapsed_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        state_count = None
        parse_error = None
        try:
            payload = response.json()
            rows = payload.get("ac") or payload.get("aircraft") or []
            state_count = len(rows)
        except Exception as exc:
            parse_error = str(exc)

        return {
            "airport": icao,
            "source": "Airplanes.live",
            "ok": response.is_success,
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
            "state_count": state_count,
            "parse_error": parse_error,
            "body_preview": response.text[:500],
        }
    except Exception as exc:
        elapsed_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        return {
            "airport": icao,
            "source": "Airplanes.live",
            "ok": False,
            "status_code": None,
            "elapsed_ms": elapsed_ms,
            "state_count": None,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

@api_router.get("/runway-status/{icao}")
async def get_runway_status(icao: str) -> RunwayAnalysisResponse:
    """Get current landing runway directions for an airport"""
    icao = icao.upper()
    
    airport = get_airport_by_ident(icao)
    if not airport:
        raise HTTPException(status_code=404, detail=f"Airport {icao} not found. Use /api/airports to see available airports.")
    
    # Fetch aircraft and METAR in parallel so weather does not wait behind
    # a slow ADS-B provider timeout.
    logger.info(f"Fetching aircraft near {icao}...")
    aircraft_task = fetch_aircraft(airport["lat"], airport["lon"], radius_km=30)
    metar_task = fetch_metar(icao)
    all_aircraft, metar_data = await asyncio.gather(aircraft_task, metar_task)
    logger.info(f"Found {len(all_aircraft)} aircraft near {icao}")
    
    logger.info(f"METAR for {icao}: {'found' if metar_data else 'not available'}")
    
    # Analyze landing aircraft (now with 2000ft AGL threshold)
    landing_aircraft = analyze_landing_aircraft(all_aircraft, airport)
    logger.info(f"Found {len(landing_aircraft)} landing aircraft")
    
    # Match to runways
    runway_matches = match_aircraft_to_runways(landing_aircraft, airport["runways"])
    
    # Build response
    active_runways = []
    for key, match in runway_matches.items():
        rwy_heading = match.get("heading") or _runway_heading_for_ident(match["runway"], match["direction"])
        
        active_runways.append(RunwayStatus(
            runway_name=match["runway"]["name"],
            direction=match["direction"],
            heading=rwy_heading or 0,
            aircraft_count=len(match["aircraft"]),
            aircraft=[Aircraft(**ac) for ac in match["aircraft"]]
        ))
    
    # Sort by aircraft count
    active_runways.sort(key=lambda x: x.aircraft_count, reverse=True)
    matched_aircraft_by_icao24 = {
        aircraft.icao24: aircraft.model_dump()
        for runway in active_runways
        for aircraft in runway.aircraft
    }
    
    # Build METAR response
    metar_response = None
    if metar_data:
        expected_rwy = get_expected_runway_from_wind(metar_data.get("wind_direction"), airport["runways"])
        metar_response = MetarData(
            **metar_data,
            expected_runway_from_wind=expected_rwy
        )
    
    # Build message
    if active_runways:
        directions = [f"{r.direction}" for r in active_runways]
        message = f"Active landing runways: {', '.join(directions)}"
    else:
        if landing_aircraft:
            message = "Aircraft detected but no clear runway alignment"
        elif all_aircraft:
            message = "No landing aircraft detected at this time (aircraft in area but not on final approach)"
        else:
            message = "No aircraft detected near the airport"
    
    # Build all_runways list for diagram
    all_runways_list = []
    for rwy in airport["runways"]:
        headings = {k: v for k, v in rwy.items() if k.startswith("heading_")}
        lat, lon = _runway_midpoint(rwy, airport)
        all_runways_list.append(RunwayDefinition(
            name=rwy["name"],
            headings=headings,
            lat=rwy.get("lat", lat),
            lon=rwy.get("lon", lon),
            length_ft=rwy.get("length_ft"),
            width_ft=rwy.get("width_ft"),
            surface=rwy.get("surface"),
            lighted=rwy.get("lighted"),
            closed=rwy.get("closed"),
            le_ident=rwy.get("le_ident"),
            he_ident=rwy.get("he_ident"),
            le_lat=rwy.get("le_lat"),
            le_lon=rwy.get("le_lon"),
            he_lat=rwy.get("he_lat"),
            he_lon=rwy.get("he_lon"),
        ))
    
    return RunwayAnalysisResponse(
        airport=AirportInfo(
            icao=icao,
            name=airport["name"],
            city=airport.get("city") or "",
            country=airport.get("country") or "",
            lat=airport["lat"],
            lon=airport["lon"],
            elevation_ft=airport["elevation_ft"],
            iata=airport.get("iata"),
            type=airport.get("type"),
        ),
        timestamp=datetime.utcnow(),
        active_runways=active_runways,
        total_landing_aircraft=len(landing_aircraft),
        all_aircraft_nearby=[
            Aircraft(**{**ac, **matched_aircraft_by_icao24.get(ac["icao24"], {})})
            for ac in sorted(all_aircraft, key=lambda x: x.get("distance_km", 100))[:50]
        ],
        message=message,
        metar=metar_response,
        all_runways=all_runways_list
    )

@api_router.get("/search-airports/{query}")
async def search_airports(query: str) -> List[AirportInfo]:
    """Search airports by ICAO code, name, or city"""
    query = query.upper()
    results = []
    
    for icao, data in get_airport_database().items():
        haystack = data.get("search_tokens") or f"{icao} {data['name']} {data.get('city', '')} {data.get('country', '')}".upper()
        if query in haystack:
            results.append(build_airport_info(icao, data))
            if len(results) >= 25:
                break
    
    return sorted(results, key=lambda x: x.icao)

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = ROOT_DIR.parent / "web"
FRONTEND_DIST = ROOT_DIR.parent / "frontend" / "dist"
STATIC_FRONTEND = WEB_DIR if WEB_DIR.exists() else FRONTEND_DIST

if STATIC_FRONTEND.exists():
    if (STATIC_FRONTEND / "_expo").exists():
        app.mount("/_expo", StaticFiles(directory=STATIC_FRONTEND / "_expo"), name="expo-assets")
    if (STATIC_FRONTEND / "assets").exists():
        app.mount("/assets", StaticFiles(directory=STATIC_FRONTEND / "assets"), name="assets")
    if (STATIC_FRONTEND / "styles.css").exists():
        app.mount("/static", StaticFiles(directory=STATIC_FRONTEND), name="static")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_webapp(full_path: str):
        requested = STATIC_FRONTEND / full_path
        if requested.is_file():
            return FileResponse(requested)
        return FileResponse(STATIC_FRONTEND / "index.html")

@app.on_event("shutdown")
async def shutdown_db_client():
    if client:
        client.close()
