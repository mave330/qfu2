"""
Backend API tests for Flight QFU Tracker
Tests all endpoints and validates METAR data integration
"""
import pytest
import requests
import os

# Get backend URL from environment - use the public URL for testing
BASE_URL = "https://adsb-runway-finder.preview.emergentagent.com"


class TestAirportsEndpoint:
    """Test /api/airports endpoint"""
    
    def test_get_airports_returns_122_airports(self):
        """Verify that exactly 122 airports are returned"""
        response = requests.get(f"{BASE_URL}/api/airports", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        airports = response.json()
        assert isinstance(airports, list), "Response should be a list"
        assert len(airports) == 122, f"Expected 122 airports, got {len(airports)}"
        print(f"✓ GET /api/airports returned {len(airports)} airports")
    
    def test_airports_have_required_fields(self):
        """Verify each airport has required fields"""
        response = requests.get(f"{BASE_URL}/api/airports", timeout=10)
        assert response.status_code == 200
        
        airports = response.json()
        required_fields = ['icao', 'name', 'city', 'country', 'lat', 'lon', 'elevation_ft']
        
        for airport in airports[:5]:  # Check first 5
            for field in required_fields:
                assert field in airport, f"Airport missing field: {field}"
                assert airport[field] is not None, f"Field {field} is None"
        
        print(f"✓ Airports have all required fields: {required_fields}")
    
    def test_airports_include_lfll_lyon(self):
        """Verify LFLL (Lyon) is in the airport list"""
        response = requests.get(f"{BASE_URL}/api/airports", timeout=10)
        assert response.status_code == 200
        
        airports = response.json()
        icao_codes = [a['icao'] for a in airports]
        
        assert 'LFLL' in icao_codes, "LFLL (Lyon) not found in airport list"
        
        # Find LFLL details
        lfll = next((a for a in airports if a['icao'] == 'LFLL'), None)
        assert lfll is not None
        assert 'Lyon' in lfll['name']
        assert lfll['city'] == 'Lyon'
        print(f"✓ LFLL found: {lfll['name']}, {lfll['city']}")


class TestAirportDetailEndpoint:
    """Test /api/airports/{icao} endpoint"""
    
    def test_get_lfll_airport_details(self):
        """Test GET /api/airports/LFLL returns Lyon airport info"""
        response = requests.get(f"{BASE_URL}/api/airports/LFLL", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        airport = response.json()
        assert airport['icao'] == 'LFLL'
        assert 'Lyon' in airport['name']
        assert airport['city'] == 'Lyon'
        assert airport['country'] == 'France'
        assert 'lat' in airport
        assert 'lon' in airport
        assert 'elevation_ft' in airport
        assert 'runways' in airport
        
        print(f"✓ GET /api/airports/LFLL: {airport['name']}, elevation: {airport['elevation_ft']}ft")
    
    def test_get_lfpg_airport_details(self):
        """Test GET /api/airports/LFPG returns Paris CDG info"""
        response = requests.get(f"{BASE_URL}/api/airports/LFPG", timeout=10)
        assert response.status_code == 200
        
        airport = response.json()
        assert airport['icao'] == 'LFPG'
        assert 'Paris' in airport['name']
        assert len(airport['runways']) > 0
        print(f"✓ GET /api/airports/LFPG: {airport['name']}, {len(airport['runways'])} runways")
    
    def test_get_invalid_airport_returns_404(self):
        """Test that invalid ICAO returns 404"""
        response = requests.get(f"{BASE_URL}/api/airports/XXXX", timeout=10)
        assert response.status_code == 404, f"Expected 404 for invalid airport, got {response.status_code}"
        print("✓ Invalid airport XXXX returns 404")


class TestSearchAirportsEndpoint:
    """Test /api/search-airports/{query} endpoint"""
    
    def test_search_lyon_returns_lfll(self):
        """Test GET /api/search-airports/LYON returns LFLL"""
        response = requests.get(f"{BASE_URL}/api/search-airports/LYON", timeout=10)
        assert response.status_code == 200
        
        results = response.json()
        assert isinstance(results, list)
        assert len(results) > 0, "Search for LYON should return results"
        
        # Check if LFLL is in results
        icao_codes = [r['icao'] for r in results]
        assert 'LFLL' in icao_codes, "LFLL should be in search results for LYON"
        print(f"✓ Search 'LYON' returned {len(results)} results including LFLL")
    
    def test_search_paris_returns_lfpg(self):
        """Test search for PARIS returns LFPG"""
        response = requests.get(f"{BASE_URL}/api/search-airports/PARIS", timeout=10)
        assert response.status_code == 200
        
        results = response.json()
        icao_codes = [r['icao'] for r in results]
        assert 'LFPG' in icao_codes or 'LFPO' in icao_codes, "Paris airports should be in results"
        print(f"✓ Search 'PARIS' returned {len(results)} results")
    
    def test_search_jfk_returns_kjfk(self):
        """Test search for JFK returns KJFK"""
        response = requests.get(f"{BASE_URL}/api/search-airports/JFK", timeout=10)
        assert response.status_code == 200
        
        results = response.json()
        icao_codes = [r['icao'] for r in results]
        assert 'KJFK' in icao_codes
        print(f"✓ Search 'JFK' returned KJFK")


class TestRunwayStatusEndpoint:
    """Test /api/runway-status/{icao} endpoint - Core functionality"""
    
    def test_runway_status_lfpg_structure(self):
        """Test GET /api/runway-status/LFPG returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/runway-status/LFPG", timeout=15)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify top-level structure
        required_fields = ['airport', 'timestamp', 'active_runways', 'total_landing_aircraft', 
                          'all_aircraft_nearby', 'message']
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify airport info
        assert data['airport']['icao'] == 'LFPG'
        assert 'name' in data['airport']
        assert 'elevation_ft' in data['airport']
        
        # Verify aircraft data
        assert isinstance(data['active_runways'], list)
        assert isinstance(data['all_aircraft_nearby'], list)
        assert isinstance(data['total_landing_aircraft'], int)
        
        print(f"✓ Runway status structure valid for LFPG")
        print(f"  - Active runways: {len(data['active_runways'])}")
        print(f"  - Landing aircraft: {data['total_landing_aircraft']}")
        print(f"  - Nearby aircraft: {len(data['all_aircraft_nearby'])}")
    
    def test_runway_status_has_metar_data(self):
        """Test that runway status includes METAR weather data"""
        response = requests.get(f"{BASE_URL}/api/runway-status/LFPG", timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        
        # METAR should be present (may be null if not available)
        assert 'metar' in data, "METAR field missing from response"
        
        if data['metar'] is not None:
            metar = data['metar']
            
            # Check required METAR fields
            assert 'raw' in metar, "METAR missing 'raw' field"
            assert 'wind_direction' in metar, "METAR missing 'wind_direction' field"
            assert 'wind_speed' in metar, "METAR missing 'wind_speed' field"
            assert 'expected_runway_from_wind' in metar, "METAR missing 'expected_runway_from_wind' field"
            
            print(f"✓ METAR data present for LFPG")
            print(f"  - Wind: {metar.get('wind_direction')}° at {metar.get('wind_speed')} kt")
            print(f"  - Expected runway: {metar.get('expected_runway_from_wind')}")
            print(f"  - Visibility: {metar.get('visibility')}")
            print(f"  - Temperature: {metar.get('temperature')}°C")
            print(f"  - Flight category: {metar.get('flight_category')}")
        else:
            print("⚠ METAR data not available for LFPG (may be temporary)")
    
    def test_metar_fields_complete(self):
        """Test that METAR includes all required fields"""
        response = requests.get(f"{BASE_URL}/api/runway-status/LFPG", timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        
        if data.get('metar'):
            metar = data['metar']
            
            # All fields that should be present (even if null)
            expected_fields = [
                'raw', 'wind_direction', 'wind_speed', 'wind_gust', 'wind_unit',
                'visibility', 'temperature', 'dewpoint', 'altimeter',
                'flight_category', 'clouds', 'weather', 'expected_runway_from_wind'
            ]
            
            for field in expected_fields:
                assert field in metar, f"METAR missing field: {field}"
            
            print(f"✓ METAR has all {len(expected_fields)} required fields")
    
    def test_active_runways_have_qfu_directions(self):
        """Test that active runways show QFU directions"""
        response = requests.get(f"{BASE_URL}/api/runway-status/LFPG", timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        
        if len(data['active_runways']) > 0:
            for runway in data['active_runways']:
                assert 'runway_name' in runway
                assert 'direction' in runway, "Missing QFU direction"
                assert 'heading' in runway
                assert 'aircraft_count' in runway
                assert 'aircraft' in runway
                
                # Direction should be like "27R", "09L", etc.
                assert len(runway['direction']) >= 2, f"Invalid direction format: {runway['direction']}"
                
            print(f"✓ Active runways have QFU directions: {[r['direction'] for r in data['active_runways']]}")
        else:
            print("⚠ No active runways at this time (normal if no landing traffic)")
    
    def test_landing_detection_uses_2000ft_threshold(self):
        """Verify landing detection uses 2000ft AGL threshold"""
        # This is implicit in the API behavior - we check that aircraft below 2000ft AGL are detected
        response = requests.get(f"{BASE_URL}/api/runway-status/LFPG", timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        airport_elevation = data['airport']['elevation_ft']
        
        # Check landing aircraft are below 2000ft AGL
        for runway in data['active_runways']:
            for aircraft in runway['aircraft']:
                agl = aircraft['altitude_ft'] - airport_elevation
                assert agl < 2000, f"Landing aircraft should be below 2000ft AGL, got {agl}ft"
        
        print(f"✓ Landing detection threshold verified (2000ft AGL)")
        print(f"  Airport elevation: {airport_elevation}ft")
    
    def test_runway_status_invalid_airport(self):
        """Test that invalid airport returns 404"""
        response = requests.get(f"{BASE_URL}/api/runway-status/XXXX", timeout=10)
        assert response.status_code == 404
        print("✓ Invalid airport returns 404 for runway status")
    
    def test_runway_status_kjfk(self):
        """Test runway status for KJFK (JFK Airport)"""
        response = requests.get(f"{BASE_URL}/api/runway-status/KJFK", timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        assert data['airport']['icao'] == 'KJFK'
        print(f"✓ KJFK runway status: {data['total_landing_aircraft']} landing, {len(data['all_aircraft_nearby'])} nearby")


class TestDataPersistence:
    """Test that data is correctly returned and structured"""
    
    def test_aircraft_data_structure(self):
        """Verify aircraft objects have correct structure"""
        response = requests.get(f"{BASE_URL}/api/runway-status/LFPG", timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        
        if len(data['all_aircraft_nearby']) > 0:
            aircraft = data['all_aircraft_nearby'][0]
            
            required_fields = ['icao24', 'latitude', 'longitude', 'altitude_ft', 
                             'on_ground', 'distance_km']
            for field in required_fields:
                assert field in aircraft, f"Aircraft missing field: {field}"
            
            print(f"✓ Aircraft data structure validated")


# Run summary
if __name__ == "__main__":
    print(f"\nTesting Flight QFU Tracker API at: {BASE_URL}")
    print("=" * 60)
