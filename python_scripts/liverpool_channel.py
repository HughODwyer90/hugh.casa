import requests
import re
import time
from secret_manager import SecretsManager  # Import the SecretsManager class
secrets = SecretsManager()
# Path to save only the TV channel names
HOME_ASSISTANT_URL = "http://homeassistant.local:8123"  # Replace with your Home Assistant URL
ENTITY_ID = "input_text.liverpool_tv_channel"  # Replace with your input_text entity ID
ACCESS_TOKEN = secrets['ha_access_token']
# Define channels to exclude
excluded_keywords = {"Viaplay", "Discovery", "Ziggo", "Caliente", "Diema"}
# URL of the main page
base_url = "https://www.livescore.com/football/team/liverpool/3340/fixtures"

def fetch_tv_channel():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # Get the main page
        response = requests.get(base_url, headers=headers, timeout=10)
        response.raise_for_status()

        # Extract the build ID from <script> tags if needed
        build_id = None
        script_tags = re.findall(r'<script.*?>(.*?)</script>', response.text, re.DOTALL)
        for script_content in script_tags:
            match = re.search(r"[\"']([\w\-]+)[\"'],\s*'prod'", script_content)
            if match:
                build_id = match.group(1)
                break

        if not build_id:
            print("No build ID found, skipping.")
            return

        # Construct the API URL
        api_url = f"https://www.livescore.com/_next/data/{build_id}/en/football/team/liverpool/3340/fixtures.json?sport=football&teamName=liverpool&teamId=3340"

        # Fetch the API data
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Extract TV channel information
        if (
            data
            and "pageProps" in data
            and "initialData" in data["pageProps"]
            and "eventsByMatchType" in data["pageProps"]["initialData"]
            and data["pageProps"]["initialData"]["eventsByMatchType"]
        ):
            events = data["pageProps"]["initialData"]["eventsByMatchType"][0]["Events"]
            if events:
                now = time.time() * 1000  # Current time in milliseconds
                next_game = next(
                    (event for event in events if event.get("Esd") > now), None
                )
                if next_game and "Media" in next_game and "112" in next_game["Media"]:
                    tv_channels = [
                        media["eventId"]
                        for media in next_game["Media"]["112"]
                        if media.get("type") == "TV_CHANNEL"
                    ]
                    if tv_channels:
                        # Filter out channels that contain any of the excluded keywords
                        filtered_channels = [
                            channel for channel in tv_channels 
                            if not any(keyword in channel for keyword in excluded_keywords)
                        ]
                        
                        # Join up to 3 remaining channels
                        result = ", ".join(filtered_channels[:3])  

                        # Update the Home Assistant entity with the fetched TV channel info
                        url = f"{HOME_ASSISTANT_URL}/api/states/{ENTITY_ID}"
                        headers = {
                            "Authorization": f"Bearer {ACCESS_TOKEN}",
                            "Content-Type": "application/json",
                        }
                        data = {
                            "state": result,  # Set the state with the filtered TV channels
                        }
                        response = requests.post(url, json=data, headers=headers)
                        response.raise_for_status()  # Ensure the request is successful
                        print(f"TV channels: {result}")
                    else:
                        print("No TV channel listed for the next game.")
                        # Set state as empty or specific fallback value, e.g., "No TV channel listed"
                        url = f"{HOME_ASSISTANT_URL}/api/states/{ENTITY_ID}"
                        headers = {
                            "Authorization": f"Bearer {ACCESS_TOKEN}",
                            "Content-Type": "application/json",
                        }
                        data = {
                            "state": "No TV channel listed",  # Fallback value
                        }
                        response = requests.post(url, json=data, headers=headers)
                        response.raise_for_status()
                        print("No TV channel listed for the next game.")
                else:
                    print("No TV channel information available for the next game.")
                    # Set state to fallback value if no media found
                    url = f"{HOME_ASSISTANT_URL}/api/states/{ENTITY_ID}"
                    headers = {
                        "Authorization": f"Bearer {ACCESS_TOKEN}",
                        "Content-Type": "application/json",
                    }
                    data = {
                        "state": "No TV channel information available",  # Fallback value
                    }
                    response = requests.post(url, json=data, headers=headers)
                    response.raise_for_status()
            else:
                print("No upcoming games found.")
                # Set state to fallback value if no upcoming games found
                url = f"{HOME_ASSISTANT_URL}/api/states/{ENTITY_ID}"
                headers = {
                    "Authorization": f"Bearer {ACCESS_TOKEN}",
                    "Content-Type": "application/json",
                }
                data = {
                    "state": "No upcoming games found",  # Fallback value
                }
                response = requests.post(url, json=data, headers=headers)
                response.raise_for_status()

        else:
            print("API data unavailable.")
            # Set state to fallback value if the API data is unavailable
            url = f"{HOME_ASSISTANT_URL}/api/states/{ENTITY_ID}"
            headers = {
                "Authorization": f"Bearer {ACCESS_TOKEN}",
                "Content-Type": "application/json",
            }
            data = {
                "state": "API data unavailable",  # Fallback value
            }
            response = requests.post(url, json=data, headers=headers)
            response.raise_for_status()

    except Exception as e:
        print(f"Error: {str(e)}")
        # If an error occurs, set a fallback value
        url = f"{HOME_ASSISTANT_URL}/api/states/{ENTITY_ID}"
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        data = {
            "state": f"Error: {str(e)}",  # Fallback error message
        }
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()

# Run the function
fetch_tv_channel()
