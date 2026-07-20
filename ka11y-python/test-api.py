import requests

url = "http://localhost:3000/api/v1/analyse-url-wcag"

headers = {
    "accept": "*/*",
    "Content-Type": "application/json"
}

payload = {
    "url": "https://www.kao.com/global/en/",
    "wcagVersion": "2.2",
    "lang": "en"
}

try:
    response = requests.post(
        url,
        headers=headers,
        json=payload,  # Automatically converts the payload to JSON
        timeout=300    # Optional: Increase timeout if analysis takes longer
    )

    print("Status Code:", response.status_code)

    # Print JSON response if available
    try:
        print("Response JSON:")
        print(response.json())
    except ValueError:
        print("Response Text:")
        print(response.text)

except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")