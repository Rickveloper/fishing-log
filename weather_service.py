import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class WeatherService:
    def __init__(self):
        self.api_key = os.getenv('OPENWEATHERMAP_API_KEY')
        if not self.api_key:
            print("Warning: OPENWEATHERMAP_API_KEY not found in environment variables")
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"
        self.historical_url = "https://api.openweathermap.org/data/2.5/onecall/timemachine"

    def get_current_weather(self, lat, lon):
        """Get current weather for a location"""
        if not self.api_key:
            print("Error: No API key available")
            return None

        params = {
            'lat': lat,
            'lon': lon,
            'appid': self.api_key,
            'units': 'imperial'  # Use Fahrenheit
        }
        try:
            print(f"Fetching weather data for coordinates: {lat}, {lon}")
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()
            print(f"Weather data received: {data['weather'][0]['description']}")
            return {
                'temperature': data['main']['temp'],
                'feels_like': data['main']['feels_like'],
                'humidity': data['main']['humidity'],
                'pressure': data['main']['pressure'],
                'wind_speed': data['wind']['speed'],
                'wind_direction': data['wind'].get('deg', 0),
                'weather_description': data['weather'][0]['description'],
                'weather_icon': data['weather'][0]['icon'],
                'clouds': data['clouds']['all'],
                'timestamp': datetime.fromtimestamp(data['dt']).isoformat()
            }
        except Exception as e:
            print(f"Error fetching weather data: {e}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status_code}")
                print(f"Response body: {e.response.text}")
            return None

    def get_historical_weather(self, lat, lon, timestamp):
        """Get historical weather for a specific timestamp"""
        params = {
            'lat': lat,
            'lon': lon,
            'dt': int(timestamp.timestamp()),
            'appid': self.api_key,
            'units': 'imperial'
        }
        try:
            response = requests.get(self.historical_url, params=params)
            response.raise_for_status()
            data = response.json()
            current = data['current']
            return {
                'temperature': current['temp'],
                'feels_like': current['feels_like'],
                'humidity': current['humidity'],
                'pressure': current['pressure'],
                'wind_speed': current['wind_speed'],
                'wind_direction': current.get('wind_deg', 0),
                'weather_description': current['weather'][0]['description'],
                'weather_icon': current['weather'][0]['icon'],
                'clouds': current['clouds'],
                'timestamp': datetime.fromtimestamp(current['dt']).isoformat()
            }
        except Exception as e:
            print(f"Error fetching historical weather data: {e}")
            return None 
