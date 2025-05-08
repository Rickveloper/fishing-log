from flask import Flask, render_template, request, redirect, url_for
import os
import json
from datetime import datetime
from werkzeug.utils import secure_filename
import uuid
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from fractions import Fraction
from weather_service import WeatherService

app = Flask(__name__)
app.debug = True  # Enable debug mode
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
LOG_PATH = 'catches.json'
weather_service = WeatherService()

@app.route("/", methods=["GET", "POST"])
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

    # Map center logic: use URL lat/lon, first valid GPS, or fallback
    if lat and lon:
        map_center = [float(lat), float(lon)]
    else:
        first_with_gps = next((c for c in catches if c.get("gps") and len(c["gps"]) == 2), None)
        map_center = first_with_gps["gps"] if first_with_gps else [43.0362, -72.1147]

    return render_template("log.html", location=location, date=date, catches=catches, map_center=map_center)

@app.route("/add-catch", methods=["POST"])
def add_catch():
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
        weather_data = weather_service.get_current_weather(float(lat), float(lon))

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
        "gps_fallback": gps_fallback
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
    try:
        with open(LOG_PATH, "r") as f:
            data = json.load(f)
    except:
        data = []

    trips_by_lake = {}
    for entry in data:
        lake = entry.get("location")
        date = entry.get("date")
        if lake not in trips_by_lake:
            trips_by_lake[lake] = set()
        trips_by_lake[lake].add(date)

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

    # Calculate statistics
    stats = {
        "total_catches": len(catches),
        "species_count": {},
        "weather_patterns": {},
        "bait_effectiveness": {},
        "time_of_day": {
            "morning": 0,  # 5-11
            "afternoon": 0,  # 11-17
            "evening": 0,  # 17-23
            "night": 0,  # 23-5
        }
    }

    for catch in catches:
        # Species count
        species = catch.get("species", "Unknown")
        stats["species_count"][species] = stats["species_count"].get(species, 0) + 1

        # Weather patterns
        if catch.get("weather_data"):
            weather_desc = catch["weather_data"].get("weather_description", "Unknown")
            stats["weather_patterns"][weather_desc] = stats["weather_patterns"].get(weather_desc, 0) + 1

        # Bait effectiveness
        bait = catch.get("bait", "Unknown")
        if bait not in stats["bait_effectiveness"]:
            stats["bait_effectiveness"][bait] = {
                "count": 0,
                "total_weight": 0,
                "species": set()
            }
        stats["bait_effectiveness"][bait]["count"] += 1
        stats["bait_effectiveness"][bait]["total_weight"] += float(catch.get("weight", 0))
        stats["bait_effectiveness"][bait]["species"].add(species)

        # Time of day
        try:
            catch_time = datetime.strptime(catch["timestamp"], "%Y-%m-%d %H:%M:%S")
            hour = catch_time.hour
            if 5 <= hour < 11:
                stats["time_of_day"]["morning"] += 1
            elif 11 <= hour < 17:
                stats["time_of_day"]["afternoon"] += 1
            elif 17 <= hour < 23:
                stats["time_of_day"]["evening"] += 1
            else:
                stats["time_of_day"]["night"] += 1
        except:
            pass

    # Convert sets to lists for JSON serialization
    for bait in stats["bait_effectiveness"]:
        stats["bait_effectiveness"][bait]["species"] = list(stats["bait_effectiveness"][bait]["species"])

    return render_template("statistics.html", stats=stats)

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
