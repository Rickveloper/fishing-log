import sys
import os
print("app.py started")
print("sys.argv:", sys.argv)
print("sys.executable:", sys.executable)
print("sys.path:", sys.path)

# Always use user data directory for data storage
user_data_dir = os.path.expanduser('~/fishing-log-data')
print("Using user data directory:", user_data_dir)
os.makedirs(user_data_dir, exist_ok=True)
LOG_PATH = os.path.join(user_data_dir, 'catches.json')
UPLOAD_FOLDER = os.path.join(user_data_dir, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
    if sys.platform == 'darwin':
        base_dir = os.path.join(base_dir, '..', 'Resources')
    template_folder = os.path.join(base_dir, 'templates')
    static_folder = os.path.join(base_dir, 'static')
    # Copy initial catches.json if it doesn't exist
    initial_log_path = os.path.join(base_dir, 'catches.json')
    print("Initial log path:", initial_log_path)
    print("Final log path:", LOG_PATH)
    if not os.path.exists(LOG_PATH) and os.path.exists(initial_log_path):
        print("Copying initial catches.json")
        import shutil
        shutil.copy(initial_log_path, LOG_PATH)
    # Copy initial uploads if not present
    initial_uploads = os.path.join(base_dir, 'static', 'uploads')
    if os.path.exists(initial_uploads) and not os.listdir(UPLOAD_FOLDER):
        print("Copying initial uploads")
        import shutil
        for f in os.listdir(initial_uploads):
            shutil.copy(os.path.join(initial_uploads, f), UPLOAD_FOLDER)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_folder = os.path.join(base_dir, 'templates')
    static_folder = os.path.join(base_dir, 'static')

print("STATIC FOLDER:", static_folder)
try:
    print("STATIC FILES:", os.listdir(static_folder))
except Exception as e:
    print("Could not list static files:", e)

print(">>> FINAL LOG_PATH:", LOG_PATH)

from flask import Flask, render_template, request, redirect, url_for, jsonify
import json
from datetime import datetime
from werkzeug.utils import secure_filename
import uuid
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from fractions import Fraction
from weather_service import WeatherService
import requests

app = Flask(
    __name__,
    template_folder=template_folder,
    static_folder=static_folder,
    static_url_path='/static'
)
app.debug = True  # Enable debug mode

weather_service = WeatherService()

@app.route("/")
def splash():
    return render_template("splash.html")

@app.route("/home", methods=["GET", "POST"])
def landing():
    if request.method == "POST":
        location = request.form["location"]
        date = request.form["date"]
        lat = request.form.get("lat")
        lon = request.form.get("lon")
        return redirect(url_for("log", location=location, date=date, lat=lat, lon=lon))
    return render_template("landing.html")

@app.route("/log")
def log():
    location = request.args.get("location")
    date = request.args.get("date")
    lat = request.args.get("lat")
    lon = request.args.get("lon")

    try:
        with open(LOG_PATH, "r") as f:
            all_catches = json.load(f)
    except:
        all_catches = []

    # Filter catches only if location and date are provided
    if location and date:
        catches = [c for c in all_catches if c.get("location") == location and c.get("date") == date]
    else:
        catches = all_catches

    # Only consider valid catches (not plans, and with required fields)
    valid_catches = [
        c for c in catches
        if c.get('type') != 'plan' and c.get('species') and c.get('length') and c.get('bait')
    ]

    # Map center logic: use URL lat/lon, first valid GPS, or fallback
    if lat and lon:
        map_center = [float(lat), float(lon)]
    else:
        first_with_gps = next((c for c in catches if c.get("gps") and len(c["gps"]) == 2), None)
        map_center = first_with_gps["gps"] if first_with_gps else [43.0362, -72.1147]

    # Trip summary stats (use only valid catches)
    trip_stats = {
        'total_catches': len(valid_catches),
        'biggest_fish': None,
        'most_common_species': None,
        'total_weight': 0
    }
    # Find biggest fish and most common species
    max_length = 0
    species_count = {}
    for c in valid_catches:
        # Biggest fish by length
        try:
            l = float(c.get('length', 0))
            if l > max_length:
                max_length = l
                trip_stats['biggest_fish'] = {
                    'species': c.get('species'),
                    'length': c.get('length'),
                    'weight': c.get('weight')
                }
        except:
            pass
        # Most common species
        s = c.get('species')
        if s:
            species_count[s] = species_count.get(s, 0) + 1
        # Total weight
        try:
            w = float(c.get('weight', 0) or 0)
            trip_stats['total_weight'] += w
        except:
            pass
    if species_count:
        trip_stats['most_common_species'] = max(species_count, key=species_count.get)

    return render_template("log.html", location=location, date=date, catches=catches, valid_catches=valid_catches, map_center=map_center, trip_stats=trip_stats, all_catches=all_catches)

@app.route("/add-catch", methods=["POST"])
def add_catch():
    print("ADD CATCH: LOG_PATH =", LOG_PATH)
    location = request.args.get("location")
    date = request.args.get("date")
    lat = request.form.get("lat")
    lon = request.form.get("lon")

    species = request.form.get("species")
    length = request.form.get("length")
    weight = request.form.get("custom_weight") or request.form.get("weight")
    bait = request.form.get("bait")
    weather = request.form.get("weather")
    notes = request.form.get("notes")
    photo = request.files["photo"]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = secure_filename(photo.filename)
    photo_path = os.path.join(UPLOAD_FOLDER, filename)
    photo.save(photo_path)

    # Get weather data if coordinates are available
    weather_data = None
    if lat and lon:
        print(f"Requesting weather for lat={lat}, lon={lon}")
        weather_data = weather_service.get_current_weather(float(lat), float(lon))
        print(f"Weather data returned: {weather_data}")

    # Extract GPS data from EXIF
    gps_data = None
    gps_fallback = False
    try:
        with Image.open(photo_path) as img:
            exif = img._getexif()
            if exif:
                for tag_id in exif:
                    tag = TAGS.get(tag_id, tag_id)
                    if tag == "GPSInfo":
                        gps_info = exif[tag_id]
                        gps_data = {}
                        for key in gps_info.keys():
                            sub_tag = GPSTAGS.get(key, key)
                            gps_data[sub_tag] = gps_info[key]
                        # Convert GPS coordinates to decimal degrees
                        if "GPSLatitude" in gps_data and "GPSLongitude" in gps_data:
                            def _fraction_to_float(frac):
                                if isinstance(frac, Fraction):
                                    return float(frac)
                                return frac
                            lat_gps = [_fraction_to_float(x) for x in gps_data["GPSLatitude"]]
                            lon_gps = [_fraction_to_float(x) for x in gps_data["GPSLongitude"]]
                            lat_val = lat_gps[0] + lat_gps[1]/60 + lat_gps[2]/3600
                            lon_val = lon_gps[0] + lon_gps[1]/60 + lon_gps[2]/3600
                            if gps_data.get("GPSLatitudeRef") == "S":
                                lat_val = -lat_val
                            if gps_data.get("GPSLongitudeRef") == "W":
                                lon_val = -lon_val
                            gps_data = [lat_val, lon_val]
                        else:
                            gps_data = None
    except Exception as e:
        print(f"Error extracting EXIF data: {e}")
        gps_data = None

    # Only use fallback if photo has NO GPS
    if not gps_data and lat and lon:
        gps_data = [float(lat), float(lon)]
        gps_fallback = True

    angler = request.form.get("angler")
    entry = {
        "id": str(uuid.uuid4()),
        "location": location,
        "date": date,
        "timestamp": timestamp,
        "species": species,
        "length": length,
        "weight": weight,
        "bait": bait,
        "weather": weather,
        "weather_data": weather_data,
        "notes": notes,
        "photo": filename,
        "gps": gps_data,
        "gps_fallback": gps_fallback,
        "angler": angler
    }

    try:
        with open(LOG_PATH, "r") as f:
            data = json.load(f)
    except:
        data = []

    entry = convert_fractions(entry)
    data.append(entry)
    with open(LOG_PATH, "w") as f:
        json.dump(data, f, indent=2)

    return redirect(url_for("log", location=location, date=date, lat=lat, lon=lon))

@app.route("/edit-catch/<catch_id>", methods=["GET", "POST"])
def edit_catch(catch_id):
    with open(LOG_PATH, "r") as f:
        data = json.load(f)

    catch = next((c for c in data if c["id"] == catch_id), None)
    if not catch:
        return "Catch not found", 404

    if request.method == "POST":
        catch["species"] = request.form.get("species")
        catch["length"] = request.form.get("length")
        catch["weight"] = request.form.get("custom_weight") or request.form.get("weight")
        catch["bait"] = request.form.get("bait")
        catch["weather"] = request.form.get("weather")
        catch["notes"] = request.form.get("notes")
        catch["angler"] = request.form.get("angler")
        # Save rotation value
        rotation = request.form.get("rotation")
        if rotation is not None:
            try:
                catch["rotation"] = int(rotation)
            except Exception:
                catch["rotation"] = 0

        with open(LOG_PATH, "w") as f:
            json.dump(data, f, indent=2)

        return redirect(url_for("log", location=catch["location"], date=catch["date"]))

    return render_template("edit.html", catch=catch)

@app.route("/delete-catch/<catch_id>", methods=["POST"])
def delete_catch(catch_id):
    try:
        with open(LOG_PATH, "r") as f:
            data = json.load(f)
    except:
        data = []
    new_data = [c for c in data if c["id"] != catch_id]
    with open(LOG_PATH, "w") as f:
        json.dump(new_data, f, indent=2)
    return redirect(request.referrer or url_for("log"))

@app.route("/trips")
def trips():
    from datetime import datetime
    try:
        with open(LOG_PATH, "r") as f:
            data = json.load(f)
    except:
        data = []

    today = datetime.now().date()
    trips_by_lake = {}
    for entry in data:
        # Only consider entries that are catches (not plans), have a photo, and are in the past
        if entry.get("photo") and entry.get("date") and entry.get("date") != "None":
            try:
                entry_date = datetime.strptime(entry["date"], "%Y-%m-%d").date()
                if entry_date < today:
                    lake = entry.get("location")
                    date = entry.get("date")
                    if lake not in trips_by_lake:
                        trips_by_lake[lake] = set()
                    trips_by_lake[lake].add(date)
            except:
                continue

    for k in trips_by_lake:
        trips_by_lake[k] = sorted(list(trips_by_lake[k]))

    return render_template("trips.html", trips=trips_by_lake)

@app.route("/upload_test")
def upload_test():
    print("Upload test route accessed")  # Debug log
    return render_template("upload_test.html")

@app.route("/statistics")
def statistics():
    try:
        with open(LOG_PATH, "r") as f:
            catches = json.load(f)
    except:
        catches = []

    # Only consider valid catches (not plans, and with required fields)
    valid_catches = [c for c in catches if c.get('type') != 'plan' and c.get('species') and c.get('weight') and c.get('bait')]

    # Initialize statistics
    stats = {
        'total_catches': len(valid_catches),
        'species_count': {},
        'time_of_day': {
            'morning': 0,    # 5-11
            'afternoon': 0,  # 11-17
            'evening': 0,    # 17-23
            'night': 0       # 23-5
        },
        'weather_patterns': {},
        'bait_effectiveness': {},
        'average_size': {},
        'total_weight': 0
    }

    for catch in valid_catches:
        # Count species
        species = catch.get('species')
        if species:
            stats['species_count'][species] = stats['species_count'].get(species, 0) + 1

        # Time of day analysis
        if 'timestamp' in catch:
            try:
                hour = datetime.strptime(catch['timestamp'], "%Y-%m-%d %H:%M:%S").hour
                if 5 <= hour < 11:
                    stats['time_of_day']['morning'] += 1
                elif 11 <= hour < 17:
                    stats['time_of_day']['afternoon'] += 1
                elif 17 <= hour < 23:
                    stats['time_of_day']['evening'] += 1
                else:
                    stats['time_of_day']['night'] += 1
            except:
                pass

        # Weather patterns
        if catch.get('weather_data', {}).get('weather_description'):
            weather = catch['weather_data']['weather_description']
            stats['weather_patterns'][weather] = stats['weather_patterns'].get(weather, 0) + 1

        # Bait effectiveness
        bait = catch.get('bait')
        if bait:
            if bait not in stats['bait_effectiveness']:
                stats['bait_effectiveness'][bait] = {'count': 0, 'total_weight': 0}
            stats['bait_effectiveness'][bait]['count'] += 1
            if catch.get('weight'):
                try:
                    weight = float(catch['weight'])
                    stats['bait_effectiveness'][bait]['total_weight'] += weight
                except:
                    pass

        # Size statistics
        if species and catch.get('length'):
            try:
                length = float(catch['length'])
                if species not in stats['average_size']:
                    stats['average_size'][species] = {'total': 0, 'count': 0}
                stats['average_size'][species]['total'] += length
                stats['average_size'][species]['count'] += 1
            except:
                pass

        # Total weight
        if catch.get('weight'):
            try:
                stats['total_weight'] += float(catch['weight'])
            except:
                pass

    # Calculate averages
    for species in stats['average_size']:
        if stats['average_size'][species]['count'] > 0:
            stats['average_size'][species]['average'] = round(
                stats['average_size'][species]['total'] / stats['average_size'][species]['count'], 2
            )

    return render_template("statistics.html", stats=stats)

@app.route("/gallery")
def gallery():
    try:
        with open(LOG_PATH, "r") as f:
            catches = json.load(f)
    except:
        catches = []
    return render_template("gallery.html", catches=catches)

@app.route("/calendar")
def calendar():
    try:
        with open(LOG_PATH, "r") as f:
            catches = json.load(f)
    except:
        catches = []
    
    # Get unique locations from catches
    locations = list(set(c.get("location") for c in catches if c.get("location")))
    
    return render_template("calendar.html", locations=locations)

@app.route("/add-fishing-plan", methods=["POST"])
def add_fishing_plan():
    location = request.form.get("location")
    date = request.form.get("date")
    notes = request.form.get("notes")
    
    try:
        with open(LOG_PATH, "r") as f:
            data = json.load(f)
    except:
        data = []
    
    # Add the plan to the data
    plan = {
        "id": str(uuid.uuid4()),
        "type": "plan",
        "location": location,
        "date": date,
        "notes": notes,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    data.append(plan)
    with open(LOG_PATH, "w") as f:
        json.dump(data, f, indent=2)
    
    return redirect(url_for("calendar"))

@app.route("/get-lake-info/<location>")
def get_lake_info(location):
    # This would be where we'd integrate with various APIs
    # For now, return mock data and user's own catch history
    try:
        with open(LOG_PATH, "r") as f:
            data = json.load(f)
    except:
        data = []
    # Normalize location for matching (strip NH, etc)
    norm_loc = location.split('(')[0].strip().lower()
    user_catches = [
        {
            "species": c.get("species"),
            "length": c.get("length"),
            "weight": c.get("weight"),
            "date": c.get("date")
        }
        for c in data
        if c.get("location") and norm_loc in c.get("location", "").lower() and c.get("species") and c.get("date") and c.get("photo")
    ]
    return jsonify({
        "name": location,
        "water_temp": "65°F",
        "water_level": "Normal",
        "fishing_conditions": "Good",
        "recent_catches": [
            {"species": "Bass", "count": 5},
            {"species": "Trout", "count": 3}
        ],
        "best_times": ["Early morning", "Evening"],
        "regulations": {
            "season": "Open year-round",
            "limits": "5 fish per day",
            "size_limit": "12 inches minimum"
        },
        "user_catches": user_catches
    })

def get_gps_for_location(location):
    # Try to get GPS from existing plans/catches first
    try:
        with open(LOG_PATH, "r") as f:
            data = json.load(f)
    except:
        data = []
    for entry in data:
        if entry.get("location") == location and entry.get("gps") and len(entry["gps"]) == 2:
            return entry["gps"]
    # Otherwise, use Nominatim
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": location + ", New Hampshire, USA", "format": "json", "limit": 1}
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": "fishing-log-app"})
        resp.raise_for_status()
        results = resp.json()
        if results:
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])
            return [lat, lon]
    except Exception as e:
        print(f"Error geocoding {location}: {e}")
    return None

@app.route("/get-events")
def get_events():
    try:
        with open("fishing-log-data/plans.json", "r") as f:
            data = json.load(f)
    except:
        data = []
    events = []
    for item in data:
        if item.get("type") == "plan":
            gps = item.get("gps")
            events.append({
                "title": f"Fishing at {item['location']}",
                "start": item["date"],
                "extendedProps": {
                    "type": "plan",
                    "location": item["location"],
                    "notes": item.get("notes", ""),
                    "gps": gps,
                    "details": item.get("details", {})
                }
            })
    return jsonify(events)

def convert_fractions(obj):
    if isinstance(obj, Fraction):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_fractions(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_fractions(x) for x in obj]
    else:
        return obj

if __name__ == "__main__":
    print("Starting Flask application...")
    print(f"Upload folder: {UPLOAD_FOLDER}")
    print(f"Log path: {LOG_PATH}")
    app.run(host="0.0.0.0", port=5051, debug=True)
