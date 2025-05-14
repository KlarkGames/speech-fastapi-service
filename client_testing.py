#!/usr/bin/env python3
import base64
import os
import sys
import time

import requests

# Configuration
API_URL = "http://localhost:8000"  # Change if running on different host/port
AUDIO_FILE_PATH = "tests/data/41601__noisecollector__mysterysnippets.wav"  # Change to your audio file path
USERNAME = "demo_user"
PASSWORD = "demo_password"


# Helper function for basic auth
def get_auth_header(username, password):
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def main():
    if not os.path.exists(AUDIO_FILE_PATH):
        print(f"Error: Audio file not found at {AUDIO_FILE_PATH}")
        print("Please specify a valid audio file path")
        sys.exit(1)

    print("=== FastAPI Audio Enhancement Demo ===")

    # 1. Create a new user
    print("\n1. Creating a new user...")
    user_data = {"username": USERNAME, "password": PASSWORD}

    try:
        response = requests.post(f"{API_URL}/users/", data=user_data)
        response.raise_for_status()
        print(f"  ✅ User created successfully: {response.json()}")
    except requests.exceptions.HTTPError as e:
        if response.status_code == 400 and "Username already exists" in response.text:
            print("  ℹ️ User already exists, continuing...")
        else:
            print(f"  ❌ Error creating user: {e}")
            sys.exit(1)

    # Auth header for subsequent requests
    auth_header = get_auth_header(USERNAME, PASSWORD)

    # 2. Add tokens to user account
    print("\n2. Adding tokens to account...")
    token_data = {"amount": 100.0}
    response = requests.post(f"{API_URL}/tokens/add/", data=token_data, headers=auth_header)
    if response.status_code == 200:
        print(f"  ✅ {response.json()['message']}")
    else:
        print(f"  ❌ Error adding tokens: {response.text}")
        sys.exit(1)

    # 3. Check token balance
    print("\n3. Checking token balance...")
    response = requests.get(f"{API_URL}/tokens/balance/", headers=auth_header)
    if response.status_code == 200:
        print(f"  ✅ Current balance: {response.json()['balance']} tokens")
    else:
        print(f"  ❌ Error getting balance: {response.text}")
        sys.exit(1)

    # 4. List available models
    print("\n4. Listing available models...")
    response = requests.get(f"{API_URL}/models/", headers=auth_header)
    if response.status_code == 200:
        models = response.json()
        for model in models:
            print(f"  - {model['name']} (Price: {model['price']} tokens)")
    else:
        print(f"  ❌ Error listing models: {response.text}")
        sys.exit(1)

    # 5. Upload audio file for enhancement
    print("\n5. Uploading audio file for enhancement...")
    with open(AUDIO_FILE_PATH, "rb") as audio_file:
        files = {"audio_file": (os.path.basename(AUDIO_FILE_PATH), audio_file, "audio/wav")}
        data = {"model_name": "audio_enhancer"}
        response = requests.post(f"{API_URL}/models/use/", data=data, files=files, headers=auth_header)

    if response.status_code == 200:
        task_id = response.json()["task_id"]
        print(f"  ✅ Task created with ID: {task_id}")
    else:
        print(f"  ❌ Error uploading audio: {response.text}")
        sys.exit(1)

    # 6. Check task status until completion
    print("\n6. Waiting for audio enhancement to complete...")
    status = "processing"
    result_path = None

    while status != "completed":
        response = requests.get(f"{API_URL}/tasks/{task_id}", headers=auth_header)
        if response.status_code == 200:
            status = response.json()["status"]
            print(f"  📊 Task status: {status}")
            if status == "completed":
                result_url = response.json()["result_url"]
                break
        else:
            print(f"  ❌ Error checking task status: {response.text}")
            sys.exit(1)
        time.sleep(2)

    # 7. Get result
    print("\n7. Audio enhancement completed!")
    if result_url:
        print(f"  🔊 Enhanced audio result path: {result_url}")

    # 8. Check updated token balance
    print("\n8. Checking updated token balance...")
    response = requests.get(f"{API_URL}/tokens/balance/", headers=auth_header)
    if response.status_code == 200:
        print(f"  ✅ Updated balance: {response.json()['balance']} tokens")
    else:
        print(f"  ❌ Error getting balance: {response.text}")

    # 9. Check usage history
    print("\n9. Checking usage history...")
    response = requests.get(f"{API_URL}/usage/history/", headers=auth_header)
    if response.status_code == 200:
        history = response.json()
        print(f"  ✅ Found {len(history)} usage records:")
        for i, entry in enumerate(history, 1):
            print(f"    [{i}] Model: {entry['model']}, Tokens: {entry['tokens_spent']}")
            if entry.get("result_url"):
                print(f"        Download URL: {entry['result_url']}")
    else:
        print(f"  ❌ Error getting usage history: {response.text}")

    print("\n=== Demo completed successfully! ===")


if __name__ == "__main__":
    main()
