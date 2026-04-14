import requests
import time
import json

BASE_URL = "http://localhost:8000/api/v1"

def test_health():
    try:
        print("Testing /health...")
        resp = requests.get(f"{BASE_URL}/health")
        print(f"Health: {resp.status_code} - {resp.json()}")
        
        print("\nTesting /system/health...")
        resp = requests.get(f"{BASE_URL}/system/health")
        print(f"System Health: {resp.status_code} - {resp.json()}")
    except Exception as e:
        print(f"Error testing health: {e}")

def test_audit():
    try:
        print("\nSubmitting audit with lang='ja'...")
        payload = {
            "url": "https://example.com",
            "lang": "ja",
            "wcag_level": "AA"
        }
        resp = requests.post(f"{BASE_URL}/combined/", json=payload)
        print(f"Submit: {resp.status_code}")
        data = resp.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        job_id = data.get("job_id")
        if not job_id:
            print("No job_id returned")
            return

        print(f"\nPolling job {job_id}...")
        for _ in range(5):
            time.sleep(2)
            resp = requests.get(f"{BASE_URL}/combined/{job_id}")
            data = resp.json()
            print(f"Status: {data.get('status')} - Lang in job: {data.get('lang')}")
            if data.get("status") in ("completed", "failed"):
                if data.get("result"):
                    print(f"Lang in result: {data['result'].get('lang')}")
                break
    except Exception as e:
        print(f"Error testing audit: {e}")

if __name__ == "__main__":
    # Wait a bit for server to start if run together
    time.sleep(2)
    test_health()
    test_audit()
