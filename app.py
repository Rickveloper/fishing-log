from flask import Flask, render_template, request, redirect, url_for
import os
import json
from datetime import datetime
from werkzeug.utils import secure_filename
import uuid
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

app = Flask(__name__)
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
LOG_PATH = 'catches.json'

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
        catches = [c for c in all_catches if c["location"] == location and c["date"] == date]
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
    lat = request.args.get("lat")
    lon = request.args.get("lon")

    species = request.form.get("species")
    length = request.form.get("length")
    weight = request.form.get("custom_weight") or request.form.get("weight")
    bait = request.form.get("bait")
    photo = request.files["photo"]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = secure_filename(photo.filename)
    photo_path = os.path.join(UPLOAD_FOLDER, filename)
    photo.save(photo_path)
    gps = [float(lat), float(lon)] if lat and lon else None

    entry = {
        "id": str(uuid.uuid4()),
        "location": location,
        "date": date,
        "timestamp": timestamp,
        "species": species,
        "length": length,
        "weight": weight,
        "bait": bait,
        "photo": filename,
        "gps": gps
    }

    try:
        with open(LOG_PATH, "r") as f:
            data = json.load(f)
    except:
        data = []

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

        with open(LOG_PATH, "w") as f:
            json.dump(data, f, indent=2)

        return redirect(url_for("log", location=catch["location"], date=catch["date"]))

    return render_template("edit.html", catch=catch)

@app.route("/trips")
def trips():
    try:
        with open(LOG_PATH, "r") as f:
            data = json.load(f)
    except:
        data = []

    trips_by_lake = {}
    for entry in data:
        lake = entry["location"]
        date = entry["date"]
        if lake not in trips_by_lake:
            trips_by_lake[lake] = set()
        trips_by_lake[lake].add(date)

    for k in trips_by_lake:
        trips_by_lake[k] = sorted(list(trips_by_lake[k]))

    return render_template("trips.html", trips=trips_by_lake)

@app.route("/upload_photo", methods=["POST"])
def upload_photo():
    print("Received photo upload request")
    
    if "photo" not in request.files:
        print("No photo in request")
        return "No photo uploaded", 400
    
    photo = request.files["photo"]
    if photo.filename == "":
        print("Empty filename")
        return "No selected file", 400

    # Save the photo
    filename = secure_filename(photo.filename)
    photo_path = os.path.join(UPLOAD_FOLDER, filename)
    print(f"Saving photo to: {photo_path}")
    photo.save(photo_path)

    # Extract GPS data from EXIF
    gps_data = None
    try:
        print("Attempting to extract EXIF data")
        with Image.open(photo_path) as img:
            exif = img._getexif()
            if exif:
                print("Found EXIF data")
                for tag_id in exif:
                    tag = TAGS.get(tag_id, tag_id)
                    if tag == "GPSInfo":
                        print("Found GPS info in EXIF")
                        gps_info = exif[tag_id]
                        gps_data = {}
                        for key in gps_info.keys():
                            sub_tag = GPSTAGS.get(key, key)
                            gps_data[sub_tag] = gps_info[key]
                        
                        # Convert GPS coordinates to decimal degrees
                        if "GPSLatitude" in gps_data and "GPSLongitude" in gps_data:
                            print("Converting GPS coordinates")
                            lat = gps_data["GPSLatitude"]
                            lon = gps_data["GPSLongitude"]
                            
                            # Convert to decimal degrees
                            lat = lat[0] + lat[1]/60 + lat[2]/3600
                            lon = lon[0] + lon[1]/60 + lon[2]/3600
                            
                            # Adjust for South/West
                            if gps_data.get("GPSLatitudeRef") == "S":
                                lat = -lat
                            if gps_data.get("GPSLongitudeRef") == "W":
                                lon = -lon
                            
                            gps_data = [lat, lon]
                            print(f"Extracted GPS coordinates: {gps_data}")
    except Exception as e:
        print(f"Error extracting EXIF data: {e}")
        gps_data = None

    # Create entry
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "photo": filename,
        "gps": gps_data
    }
    print(f"Created entry: {entry}")

    # Save to catches.json
    try:
        with open(LOG_PATH, "r") as f:
            data = json.load(f)
    except:
        data = []

    data.append(entry)
    with open(LOG_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print("Saved entry to catches.json")

    return redirect(url_for("log"))

@app.route("/upload_test")
def upload_test():
    return render_template("upload_test.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
