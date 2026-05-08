#!/usr/bin/env python
"""
Test script for the Settings API endpoints.
This script tests the API endpoints via HTTP requests.
"""

import asyncio
import json
import sys
import sqlite3
from pathlib import Path
import subprocess
import time
import httpx

# Database path
DB_PATH = Path("E:/git/subvision-studio/subvision.db")
API_BASE_URL = "http://localhost:8000"

async def wait_for_server(max_attempts=30, delay=1):
    """Wait for the server to be running."""
    async with httpx.AsyncClient() as client:
        for attempt in range(max_attempts):
            try:
                response = await client.get(f"{API_BASE_URL}/api/settings", timeout=2)
                if response.status_code in (200, 404):
                    print("✓ Server is running")
                    return True
            except Exception:
                pass
            print(f"Waiting for server... ({attempt + 1}/{max_attempts})")
            await asyncio.sleep(delay)
    
    print("✗ Server did not start in time")
    return False


async def test_api():
    """Test all API endpoints."""
    results = {
        "endpoints_tested": [],
        "passed": 0,
        "failed": 0,
        "errors": []
    }
    
    async with httpx.AsyncClient() as client:
        # Test 1: GET /api/settings - get all settings
        print("\n1. Testing GET /api/settings")
        try:
            response = await client.get(f"{API_BASE_URL}/api/settings")
            status = response.status_code
            print(f"   Status: {status}")
            if status == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
                results["endpoints_tested"].append({
                    "endpoint": "GET /api/settings",
                    "status": status,
                    "result": "PASS"
                })
                results["passed"] += 1
            else:
                results["endpoints_tested"].append({
                    "endpoint": "GET /api/settings",
                    "status": status,
                    "result": "FAIL"
                })
                results["failed"] += 1
        except Exception as e:
            print(f"   Error: {e}")
            results["endpoints_tested"].append({
                "endpoint": "GET /api/settings",
                "status": "ERROR",
                "result": f"FAIL: {str(e)}"
            })
            results["failed"] += 1
            results["errors"].append(str(e))

        # Test 2: GET /api/settings/obs_websocket_url
        print("\n2. Testing GET /api/settings/obs_websocket_url")
        try:
            response = await client.get(f"{API_BASE_URL}/api/settings/obs_websocket_url")
            status = response.status_code
            print(f"   Status: {status}")
            if status == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
                results["endpoints_tested"].append({
                    "endpoint": "GET /api/settings/obs_websocket_url",
                    "status": status,
                    "result": "PASS"
                })
                results["passed"] += 1
            else:
                results["endpoints_tested"].append({
                    "endpoint": "GET /api/settings/obs_websocket_url",
                    "status": status,
                    "result": "FAIL"
                })
                results["failed"] += 1
        except Exception as e:
            print(f"   Error: {e}")
            results["endpoints_tested"].append({
                "endpoint": "GET /api/settings/obs_websocket_url",
                "status": "ERROR",
                "result": f"FAIL: {str(e)}"
            })
            results["failed"] += 1
            results["errors"].append(str(e))

        # Test 3: PUT /api/settings/obs_websocket_url
        print("\n3. Testing PUT /api/settings/obs_websocket_url")
        try:
            payload = {"value": "ws://test:4455", "value_type": "string"}
            response = await client.put(
                f"{API_BASE_URL}/api/settings/obs_websocket_url",
                json=payload
            )
            status = response.status_code
            print(f"   Status: {status}")
            if status == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
                results["endpoints_tested"].append({
                    "endpoint": "PUT /api/settings/obs_websocket_url",
                    "status": status,
                    "result": "PASS"
                })
                results["passed"] += 1
            else:
                print(f"   Response: {response.text}")
                results["endpoints_tested"].append({
                    "endpoint": "PUT /api/settings/obs_websocket_url",
                    "status": status,
                    "result": "FAIL"
                })
                results["failed"] += 1
        except Exception as e:
            print(f"   Error: {e}")
            results["endpoints_tested"].append({
                "endpoint": "PUT /api/settings/obs_websocket_url",
                "status": "ERROR",
                "result": f"FAIL: {str(e)}"
            })
            results["failed"] += 1
            results["errors"].append(str(e))

        # Test 4: PUT /api/settings (bulk update)
        print("\n4. Testing PUT /api/settings (bulk update)")
        try:
            payload = {
                "obs_websocket_url": {
                    "value": "ws://bulk:4455",
                    "value_type": "string"
                }
            }
            response = await client.put(
                f"{API_BASE_URL}/api/settings",
                json=payload
            )
            status = response.status_code
            print(f"   Status: {status}")
            if status == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
                results["endpoints_tested"].append({
                    "endpoint": "PUT /api/settings (bulk)",
                    "status": status,
                    "result": "PASS"
                })
                results["passed"] += 1
            else:
                print(f"   Response: {response.text[:200]}")
                results["endpoints_tested"].append({
                    "endpoint": "PUT /api/settings (bulk)",
                    "status": status,
                    "result": "FAIL"
                })
                results["failed"] += 1
        except Exception as e:
            print(f"   Error: {e}")
            results["endpoints_tested"].append({
                "endpoint": "PUT /api/settings (bulk)",
                "status": "ERROR",
                "result": f"FAIL: {str(e)}"
            })
            results["failed"] += 1
            results["errors"].append(str(e))

        # Test 5: GET nonexistent_key (should return 404)
        print("\n5. Testing GET /api/settings/nonexistent_key (expect 404)")
        try:
            response = await client.get(f"{API_BASE_URL}/api/settings/nonexistent_key")
            status = response.status_code
            print(f"   Status: {status}")
            if status == 404:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
                results["endpoints_tested"].append({
                    "endpoint": "GET /api/settings/nonexistent_key (404 expected)",
                    "status": status,
                    "result": "PASS"
                })
                results["passed"] += 1
            else:
                results["endpoints_tested"].append({
                    "endpoint": "GET /api/settings/nonexistent_key (404 expected)",
                    "status": status,
                    "result": f"FAIL (expected 404, got {status})"
                })
                results["failed"] += 1
        except Exception as e:
            print(f"   Error: {e}")
            results["endpoints_tested"].append({
                "endpoint": "GET /api/settings/nonexistent_key",
                "status": "ERROR",
                "result": f"FAIL: {str(e)}"
            })
            results["failed"] += 1
            results["errors"].append(str(e))

        # Test 6: PUT with missing value field (should return 400)
        print("\n6. Testing PUT /api/settings/obs_websocket_url with missing value (expect 400)")
        try:
            payload = {"value_type": "string"}  # Missing value field
            response = await client.put(
                f"{API_BASE_URL}/api/settings/obs_websocket_url",
                json=payload
            )
            status = response.status_code
            print(f"   Status: {status}")
            if status == 422:  # FastAPI returns 422 for validation errors
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
                results["endpoints_tested"].append({
                    "endpoint": "PUT /api/settings/obs_websocket_url (missing value, 422 expected)",
                    "status": status,
                    "result": "PASS"
                })
                results["passed"] += 1
            else:
                results["endpoints_tested"].append({
                    "endpoint": "PUT /api/settings/obs_websocket_url (missing value, 422 expected)",
                    "status": status,
                    "result": f"FAIL (expected 422, got {status})"
                })
                results["failed"] += 1
        except Exception as e:
            print(f"   Error: {e}")
            results["endpoints_tested"].append({
                "endpoint": "PUT /api/settings/obs_websocket_url (missing value)",
                "status": "ERROR",
                "result": f"FAIL: {str(e)}"
            })
            results["failed"] += 1
            results["errors"].append(str(e))

    return results


def check_database():
    """Check if application_settings table exists and has data."""
    db_check = {
        "table_exists": False,
        "record_count": 0,
        "sample_records": []
    }
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='application_settings';")
        result = cursor.fetchone()
        
        if result:
            db_check["table_exists"] = True
            print("✓ application_settings table exists")
            
            # Get record count
            cursor.execute("SELECT COUNT(*) FROM application_settings;")
            count = cursor.fetchone()[0]
            db_check["record_count"] = count
            print(f"✓ Found {count} settings in table")
            
            # Get sample records
            cursor.execute("SELECT key, value, value_type FROM application_settings LIMIT 5;")
            rows = cursor.fetchall()
            for row in rows:
                db_check["sample_records"].append({
                    "key": row[0],
                    "value": row[1],
                    "value_type": row[2]
                })
                print(f"  - {row[0]}: {row[1]} ({row[2]})")
        else:
            print("✗ application_settings table does not exist")
        
        conn.close()
    except Exception as e:
        print(f"✗ Database check error: {e}")
        db_check["error"] = str(e)
    
    return db_check


async def main():
    """Main test runner."""
    print("=" * 60)
    print("SUBVISION STUDIO - SETTINGS API TEST")
    print("=" * 60)
    
    # Wait for server
    print("\nWaiting for server to start...")
    if not await wait_for_server():
        print("\n✗ Test failed: Server not running")
        return
    
    # Run API tests
    print("\n" + "=" * 60)
    print("TESTING API ENDPOINTS")
    print("=" * 60)
    api_results = await test_api()
    
    # Check database
    print("\n" + "=" * 60)
    print("CHECKING DATABASE")
    print("=" * 60)
    db_results = check_database()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"\nAPI Tests: {api_results['passed']} passed, {api_results['failed']} failed")
    print(f"Database: {'EXISTS' if db_results['table_exists'] else 'NOT FOUND'}")
    print(f"Records: {db_results['record_count']}")
    
    print("\nEndpoints Tested:")
    for endpoint in api_results["endpoints_tested"]:
        status_str = f"[{endpoint['status']}]" if isinstance(endpoint['status'], int) else "[ERROR]"
        print(f"  {endpoint['result']:<8} {endpoint['endpoint']:<50} {status_str}")
    
    if api_results["errors"]:
        print("\nErrors:")
        for error in api_results["errors"]:
            print(f"  - {error}")
    
    overall_status = "PASS" if (api_results["failed"] == 0 and db_results["table_exists"]) else "FAIL"
    print(f"\nOverall Status: {overall_status}")
    
    return overall_status == "PASS"


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
