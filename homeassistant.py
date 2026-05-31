import requests


class HomeAssistant:
    def __init__(self, token: str):
        if not token or token.strip() == "":
            raise ValueError("HA_TOKEN is required for sending notifications.")
        self._token = token
        self._home_assistant_url = "http://homeassistant.local:8123"

    def send_notification(self, title: str, message: str):
        """Send a notification to Home Assistant using the REST API."""
        url = f"{self._home_assistant_url}/api/services/notify/notify"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        payload = {
            "title": title,
            "message": message,
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
