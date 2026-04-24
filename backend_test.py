#!/usr/bin/env python3
"""
Comprehensive Backend API Tests for Flight QFU Tracker
Tests all endpoints and verifies OpenSky Network integration
"""

import requests
import json
import time
from datetime import datetime
from typing import Dict, List, Any

# Get backend URL from frontend env
BACKEND_URL = "https://adsb-runway-finder.preview.emergentagent.com/api"

class FlightTrackerAPITester:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 30
        self.test_results = []
        
    def log_test(self, test_name: str, success: bool, details: str = "", response_data: Any = None):
        """Log test results"""
        result = {
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat(),
            "response_data": response_data
        }
        self.test_results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {details}")
        
    def test_airports_endpoint(self):
        """Test GET /api/airports - List all supported airports"""
        try:
            response = self.session.get(f"{self.base_url}/airports")
            
            if response.status_code != 200:
                self.log_test("GET /api/airports", False, f"Status code: {response.status_code}")
                return False
                
            data = response.json()
            
            # Verify it's a list
            if not isinstance(data, list):
                self.log_test("GET /api/airports", False, "Response is not a list")
                return False
                
            # Verify we have airports
            if len(data) == 0:
                self.log_test("GET /api/airports", False, "No airports returned")
                return False
                
            # Verify structure of first airport
            airport = data[0]
            required_fields = ["icao", "name", "city", "country", "lat", "lon", "elevation_ft"]
            
            for field in required_fields:
                if field not in airport:
                    self.log_test("GET /api/airports", False, f"Missing field: {field}")
                    return False
                    
            # Verify specific airports exist
            icao_codes = [a["icao"] for a in data]
            expected_airports = ["LFPG", "EGLL", "KJFK", "KLAX"]
            
            for expected in expected_airports:
                if expected not in icao_codes:
                    self.log_test("GET /api/airports", False, f"Missing expected airport: {expected}")
                    return False
                    
            self.log_test("GET /api/airports", True, f"Returned {len(data)} airports with correct structure")
            return True
            
        except Exception as e:
            self.log_test("GET /api/airports", False, f"Exception: {str(e)}")
            return False
            
    def test_specific_airport_endpoint(self):
        """Test GET /api/airports/{icao} - Get specific airport info"""
        # Test valid airport (LFPG - Paris Charles de Gaulle)
        try:
            response = self.session.get(f"{self.base_url}/airports/LFPG")
            
            if response.status_code != 200:
                self.log_test("GET /api/airports/LFPG", False, f"Status code: {response.status_code}")
                return False
                
            data = response.json()
            
            # Verify required fields
            required_fields = ["icao", "name", "city", "country", "lat", "lon", "elevation_ft", "runways"]
            for field in required_fields:
                if field not in data:
                    self.log_test("GET /api/airports/LFPG", False, f"Missing field: {field}")
                    return False
                    
            # Verify it's LFPG
            if data["icao"] != "LFPG":
                self.log_test("GET /api/airports/LFPG", False, f"Wrong ICAO returned: {data['icao']}")
                return False
                
            # Verify runways exist
            if not isinstance(data["runways"], list) or len(data["runways"]) == 0:
                self.log_test("GET /api/airports/LFPG", False, "No runways data")
                return False
                
            self.log_test("GET /api/airports/LFPG", True, f"Returned {data['name']} with {len(data['runways'])} runways")
            
        except Exception as e:
            self.log_test("GET /api/airports/LFPG", False, f"Exception: {str(e)}")
            return False
            
        # Test invalid airport code
        try:
            response = self.session.get(f"{self.base_url}/airports/XXXX")
            
            if response.status_code != 404:
                self.log_test("GET /api/airports/XXXX (invalid)", False, f"Expected 404, got {response.status_code}")
                return False
                
            self.log_test("GET /api/airports/XXXX (invalid)", True, "Correctly returned 404 for invalid airport")
            return True
            
        except Exception as e:
            self.log_test("GET /api/airports/XXXX (invalid)", False, f"Exception: {str(e)}")
            return False
            
    def test_search_airports_endpoint(self):
        """Test GET /api/search-airports/{query} - Search airports"""
        # Test search for "PARIS"
        try:
            response = self.session.get(f"{self.base_url}/search-airports/PARIS")
            
            if response.status_code != 200:
                self.log_test("GET /api/search-airports/PARIS", False, f"Status code: {response.status_code}")
                return False
                
            data = response.json()
            
            if not isinstance(data, list):
                self.log_test("GET /api/search-airports/PARIS", False, "Response is not a list")
                return False
                
            # Should find LFPG and LFPO
            icao_codes = [a["icao"] for a in data]
            expected = ["LFPG", "LFPO"]
            
            for exp in expected:
                if exp not in icao_codes:
                    self.log_test("GET /api/search-airports/PARIS", False, f"Missing expected airport: {exp}")
                    return False
                    
            self.log_test("GET /api/search-airports/PARIS", True, f"Found {len(data)} Paris airports: {icao_codes}")
            
        except Exception as e:
            self.log_test("GET /api/search-airports/PARIS", False, f"Exception: {str(e)}")
            return False
            
        # Test search for "JFK"
        try:
            response = self.session.get(f"{self.base_url}/search-airports/JFK")
            
            if response.status_code != 200:
                self.log_test("GET /api/search-airports/JFK", False, f"Status code: {response.status_code}")
                return False
                
            data = response.json()
            
            # Should find KJFK
            icao_codes = [a["icao"] for a in data]
            if "KJFK" not in icao_codes:
                self.log_test("GET /api/search-airports/JFK", False, "KJFK not found in JFK search")
                return False
                
            self.log_test("GET /api/search-airports/JFK", True, f"Found JFK airport: {icao_codes}")
            return True
            
        except Exception as e:
            self.log_test("GET /api/search-airports/JFK", False, f"Exception: {str(e)}")
            return False
            
    def test_runway_status_endpoint(self):
        """Test GET /api/runway-status/{icao} - Main feature with OpenSky integration"""
        # Test with LFPG (Paris Charles de Gaulle)
        try:
            print("Testing runway status for LFPG (this may take 30+ seconds due to OpenSky API)...")
            response = self.session.get(f"{self.base_url}/runway-status/LFPG")
            
            if response.status_code != 200:
                self.log_test("GET /api/runway-status/LFPG", False, f"Status code: {response.status_code}")
                return False
                
            data = response.json()
            
            # Verify required fields in response
            required_fields = ["airport", "timestamp", "active_runways", "total_landing_aircraft", "all_aircraft_nearby", "message"]
            for field in required_fields:
                if field not in data:
                    self.log_test("GET /api/runway-status/LFPG", False, f"Missing field: {field}")
                    return False
                    
            # Verify airport info
            airport = data["airport"]
            if airport["icao"] != "LFPG":
                self.log_test("GET /api/runway-status/LFPG", False, f"Wrong airport ICAO: {airport['icao']}")
                return False
                
            # Verify timestamp is recent
            timestamp = datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00'))
            time_diff = abs((datetime.now() - timestamp.replace(tzinfo=None)).total_seconds())
            if time_diff > 300:  # 5 minutes
                self.log_test("GET /api/runway-status/LFPG", False, f"Timestamp too old: {time_diff} seconds")
                return False
                
            # Verify aircraft data structure
            if not isinstance(data["all_aircraft_nearby"], list):
                self.log_test("GET /api/runway-status/LFPG", False, "all_aircraft_nearby is not a list")
                return False
                
            # Check if we got aircraft data (OpenSky integration working)
            aircraft_count = len(data["all_aircraft_nearby"])
            landing_count = data["total_landing_aircraft"]
            
            details = f"Found {aircraft_count} nearby aircraft, {landing_count} landing, {len(data['active_runways'])} active runways"
            
            if aircraft_count == 0:
                # This might be normal if no aircraft in area, but let's check the message
                if "No aircraft detected" not in data["message"]:
                    self.log_test("GET /api/runway-status/LFPG", False, f"No aircraft but unexpected message: {data['message']}")
                    return False
                else:
                    self.log_test("GET /api/runway-status/LFPG", True, f"OpenSky integration working - {details}")
            else:
                # Verify aircraft structure
                aircraft = data["all_aircraft_nearby"][0]
                required_aircraft_fields = ["icao24", "latitude", "longitude", "altitude_ft", "distance_km"]
                for field in required_aircraft_fields:
                    if field not in aircraft:
                        self.log_test("GET /api/runway-status/LFPG", False, f"Aircraft missing field: {field}")
                        return False
                        
                self.log_test("GET /api/runway-status/LFPG", True, f"OpenSky integration working - {details}")
                
        except Exception as e:
            self.log_test("GET /api/runway-status/LFPG", False, f"Exception: {str(e)}")
            return False
            
        # Test with EGLL (London Heathrow)
        try:
            print("Testing runway status for EGLL (this may take 30+ seconds due to OpenSky API)...")
            response = self.session.get(f"{self.base_url}/runway-status/EGLL")
            
            if response.status_code != 200:
                self.log_test("GET /api/runway-status/EGLL", False, f"Status code: {response.status_code}")
                return False
                
            data = response.json()
            
            if data["airport"]["icao"] != "EGLL":
                self.log_test("GET /api/runway-status/EGLL", False, f"Wrong airport ICAO: {data['airport']['icao']}")
                return False
                
            aircraft_count = len(data["all_aircraft_nearby"])
            details = f"EGLL: {aircraft_count} nearby aircraft, {data['total_landing_aircraft']} landing"
            self.log_test("GET /api/runway-status/EGLL", True, details)
            
        except Exception as e:
            self.log_test("GET /api/runway-status/EGLL", False, f"Exception: {str(e)}")
            return False
            
        # Test with invalid airport code
        try:
            response = self.session.get(f"{self.base_url}/runway-status/XXXX")
            
            if response.status_code != 404:
                self.log_test("GET /api/runway-status/XXXX (invalid)", False, f"Expected 404, got {response.status_code}")
                return False
                
            self.log_test("GET /api/runway-status/XXXX (invalid)", True, "Correctly returned 404 for invalid airport")
            return True
            
        except Exception as e:
            self.log_test("GET /api/runway-status/XXXX (invalid)", False, f"Exception: {str(e)}")
            return False
            
    def test_opensky_integration(self):
        """Verify OpenSky Network API integration is working"""
        try:
            # Test a busy airport to ensure we get aircraft data
            print("Testing OpenSky integration with KJFK (busy airport)...")
            response = self.session.get(f"{self.base_url}/runway-status/KJFK")
            
            if response.status_code != 200:
                self.log_test("OpenSky Network Integration", False, f"Status code: {response.status_code}")
                return False
                
            data = response.json()
            aircraft_count = len(data["all_aircraft_nearby"])
            
            # JFK is usually busy, so we should see some aircraft
            if aircraft_count > 0:
                # Verify aircraft have required OpenSky data
                aircraft = data["all_aircraft_nearby"][0]
                if "icao24" in aircraft and "latitude" in aircraft and "longitude" in aircraft:
                    self.log_test("OpenSky Network Integration", True, f"Successfully fetched {aircraft_count} aircraft from OpenSky API")
                    return True
                else:
                    self.log_test("OpenSky Network Integration", False, "Aircraft data missing required OpenSky fields")
                    return False
            else:
                # Even if no aircraft, the API call worked if we got a proper response
                self.log_test("OpenSky Network Integration", True, "OpenSky API responding (no aircraft in area at this time)")
                return True
                
        except Exception as e:
            self.log_test("OpenSky Network Integration", False, f"Exception: {str(e)}")
            return False
            
    def test_landing_detection_logic(self):
        """Test landing detection logic by examining response data"""
        try:
            # Use a busy airport to get aircraft data
            response = self.session.get(f"{self.base_url}/runway-status/KLAX")
            
            if response.status_code != 200:
                self.log_test("Landing Detection Logic", False, f"Status code: {response.status_code}")
                return False
                
            data = response.json()
            
            # Check if landing detection is working
            total_aircraft = len(data["all_aircraft_nearby"])
            landing_aircraft = data["total_landing_aircraft"]
            
            if total_aircraft > 0:
                # Verify landing aircraft count is reasonable (should be <= total)
                if landing_aircraft > total_aircraft:
                    self.log_test("Landing Detection Logic", False, f"Landing count ({landing_aircraft}) > total count ({total_aircraft})")
                    return False
                    
                # Check if any active runways have aircraft assigned
                active_runways = data["active_runways"]
                runway_aircraft_count = sum(r["aircraft_count"] for r in active_runways)
                
                if landing_aircraft > 0 and runway_aircraft_count == 0:
                    self.log_test("Landing Detection Logic", False, "Landing aircraft detected but none assigned to runways")
                    return False
                    
                details = f"Detected {landing_aircraft}/{total_aircraft} aircraft as landing, assigned to {len(active_runways)} runways"
                self.log_test("Landing Detection Logic", True, details)
                return True
            else:
                self.log_test("Landing Detection Logic", True, "No aircraft to test landing detection (logic appears implemented)")
                return True
                
        except Exception as e:
            self.log_test("Landing Detection Logic", False, f"Exception: {str(e)}")
            return False
            
    def test_runway_matching_logic(self):
        """Test runway matching based on aircraft heading"""
        try:
            # Test with an airport that has multiple runways
            response = self.session.get(f"{self.base_url}/runway-status/LFPG")
            
            if response.status_code != 200:
                self.log_test("Runway Matching Logic", False, f"Status code: {response.status_code}")
                return False
                
            data = response.json()
            
            # Check active runways structure
            active_runways = data["active_runways"]
            
            if not isinstance(active_runways, list):
                self.log_test("Runway Matching Logic", False, "active_runways is not a list")
                return False
                
            # If we have active runways, verify their structure
            if len(active_runways) > 0:
                runway = active_runways[0]
                required_fields = ["runway_name", "direction", "heading", "aircraft_count", "aircraft"]
                
                for field in required_fields:
                    if field not in runway:
                        self.log_test("Runway Matching Logic", False, f"Runway missing field: {field}")
                        return False
                        
                # Verify direction format (should be like "26R", "09L", etc.)
                direction = runway["direction"]
                if not isinstance(direction, str) or len(direction) < 2:
                    self.log_test("Runway Matching Logic", False, f"Invalid direction format: {direction}")
                    return False
                    
                # Verify heading is reasonable (0-360)
                heading = runway["heading"]
                if not isinstance(heading, (int, float)) or heading < 0 or heading >= 360:
                    self.log_test("Runway Matching Logic", False, f"Invalid heading: {heading}")
                    return False
                    
                details = f"Runway matching working - {len(active_runways)} active runways with proper direction/heading data"
                self.log_test("Runway Matching Logic", True, details)
                return True
            else:
                self.log_test("Runway Matching Logic", True, "No active runways to test (logic appears implemented)")
                return True
                
        except Exception as e:
            self.log_test("Runway Matching Logic", False, f"Exception: {str(e)}")
            return False
            
    def run_all_tests(self):
        """Run all tests and return summary"""
        print(f"🚀 Starting Flight QFU Tracker API Tests")
        print(f"Backend URL: {self.base_url}")
        print("=" * 80)
        
        # Run all tests
        tests = [
            self.test_airports_endpoint,
            self.test_specific_airport_endpoint,
            self.test_search_airports_endpoint,
            self.test_runway_status_endpoint,
            self.test_opensky_integration,
            self.test_landing_detection_logic,
            self.test_runway_matching_logic
        ]
        
        for test in tests:
            try:
                test()
            except Exception as e:
                print(f"❌ CRITICAL ERROR in {test.__name__}: {str(e)}")
            print("-" * 40)
            
        # Summary
        passed = sum(1 for r in self.test_results if r["success"])
        total = len(self.test_results)
        
        print("=" * 80)
        print(f"📊 TEST SUMMARY: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED! Flight QFU Tracker API is working correctly.")
        else:
            print("⚠️  Some tests failed. See details above.")
            
        # Show failed tests
        failed_tests = [r for r in self.test_results if not r["success"]]
        if failed_tests:
            print("\n❌ FAILED TESTS:")
            for test in failed_tests:
                print(f"  - {test['test']}: {test['details']}")
                
        return passed, total, self.test_results

def main():
    """Main test execution"""
    tester = FlightTrackerAPITester(BACKEND_URL)
    passed, total, results = tester.run_all_tests()
    
    # Save detailed results
    with open("/app/test_results_detailed.json", "w") as f:
        json.dump({
            "summary": {"passed": passed, "total": total, "success_rate": passed/total},
            "timestamp": datetime.now().isoformat(),
            "backend_url": BACKEND_URL,
            "results": results
        }, f, indent=2)
    
    print(f"\n📄 Detailed results saved to /app/test_results_detailed.json")
    
    # Return exit code
    return 0 if passed == total else 1

if __name__ == "__main__":
    exit(main())