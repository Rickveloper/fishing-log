from flask import Flask, render_template, request, redirect, url_for, session
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image
import piexif

app = Flask(__name__)
app.secret_key = 'your-secret-key'  # change this to something strong
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

log = []

def extract_gps(file_path):
    try:
        img = Image.open(file_path)
        exif_data = img.info.get('exif')
        if not exif_data:
            return None
        exif_dict = piexif.load(exif_data)
        gps = exif_dict.get('GPS')
        if not gps:
            return None
        def convert(value): return value[0][0]/value[0][1], value[1][0]/value[1][1], value[2][0]/value[2][1]
        d, m, s = convert(gps[2])
        lat = d + (m / 60.0) + (s / 3600.0)
        if gps[1] == b'S':
            lat = -lat
        d, m, s = convert(gps[4])
        lon = d + (m / 60.0) + (s / 3600.0)
        if gps[3] == b'W':
            lon = -lon
        return (lat, lon)
    except:
        return None

@app.route('/', methods=['GET', 'POST'])
def landing():
    if request.method == 'POST':
        session['location'] = request.form['location']
        session['date'] = request.form['date']
        return redirect(url_for('log_view'))
    return render_template('landing.html')

@app.route('/log', methods=['GET'])
def log_view():
    location = session.get('location')
    date = session.get('date')
    catches = [c for c in log if c['location'] == location and c['date'] == date]
    return render_template('log.html', location=location, date=date, catches=catches)

@app.route('/add-catch', methods=['POST'])
def add_catch():
    location = session.get('location')
    date = session.get('date')
    species = request.form['species']
    bait = request.form['bait']
    photo = request.files['photo']
    photo_filename = secure_filename(photo.filename)
    path = os.path.join(UPLOAD_FOLDER, photo_filename)
    photo.save(path)
    gps = extract_gps(path)
    entry = {
    'date': date,
    'location': location,
    'species': species,
    'bait': bait,
    'length': request.form.get('length', 'Unknown'),
    'weight': request.form.get('custom_weight') or request.form.get('weight', 'Unknown'),
    'photo': photo_filename,
    'gps': gps
}
    log.append(entry)
    return redirect(url_for('log_view'))

@app.route('/trips')
def trips():
    grouped = {}
    for entry in log:
        lake = entry['location']
        date = entry['date']
        if lake not in grouped:
            grouped[lake] = set()
        grouped[lake].add(date)
    # Convert date sets to sorted lists
    grouped_sorted = {k: sorted(list(v)) for k, v in grouped.items()}
    return render_template('trips.html', trips=grouped_sorted)


@app.route('/set-trip')
def set_trip():
    location = request.args.get('location')
    date = request.args.get('date')
    session['location'] = location
    session['date'] = date
    return '', 204



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050, debug=True)
