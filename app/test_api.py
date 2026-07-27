#!/usr/bin/env python
import requests
import json
from database.session import SessionLocal
from database.models import AppUser

db = SessionLocal()
users = db.query(AppUser).limit(1).all()
db.close()

if not users:
    print("No users found in database")
    exit(1)

user = users[0]
print(f"Found user: {user.initials} ({user.name})")

# Try to login with a test password
try:
    response = requests.post(
        "http://localhost:8000/api/auth/login",
        json={"initials": user.initials, "password": "test123"}
    )
    print(f"Login attempt status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        token = data.get('access_token')
        print(f"Got token: {token[:50] if token else 'NO TOKEN'}")

        # Now test the activities endpoint with the token
        headers = {"Authorization": f"Bearer {token}"}
        activities_response = requests.get(
            "http://localhost:8000/api/activities",
            headers=headers
        )
        print(f"\nActivities response status: {activities_response.status_code}")

        if activities_response.status_code == 200:
            data = activities_response.json()
            if data:
                first_activity = data[0]
                print(f"\nFirst activity fields:")
                for key in sorted(first_activity.keys()):
                    print(f"  {key}: {type(first_activity[key]).__name__}")

                # Check for the new fields
                if 'auto_approved' in first_activity:
                    print(f"\n✓ auto_approved field found: {first_activity['auto_approved']}")
                else:
                    print("\n✗ auto_approved field NOT found")

                if 'auto_approval_flags' in first_activity:
                    print(f"✓ auto_approval_flags field found: {first_activity['auto_approval_flags']}")
                else:
                    print("✗ auto_approval_flags field NOT found")
            else:
                print("No activities in response")
        else:
            print(f"Error: {activities_response.text[:200]}")
    else:
        print(f"Login failed: {response.text[:200]}")
except Exception as e:
    print(f"Error: {e}")
