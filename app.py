# ---------------- IMPORTS ----------------

from flask import Flask, render_template, request, send_from_directory, redirect
from werkzeug.utils import secure_filename

from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required,
    logout_user, current_user
)

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

import sqlite3
import os
import speech_recognition as sr
from textblob import TextBlob


# ---------------- APP CONFIG ----------------

app = Flask(__name__)
app.secret_key = "voice_emotion_secret"

UPLOAD_FOLDER = "uploads"
STATIC_FOLDER = "static"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ---------------- LOGIN MANAGER ----------------

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# ---------------- DATABASE ----------------

def init_db():

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS reports(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        text TEXT,
        emotion TEXT,
        pdf_file TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


init_db()


# ---------------- USER CLASS ----------------

class User(UserMixin):

    def __init__(self, id, username):
        self.id = id
        self.username = username


@login_manager.user_loader
def load_user(user_id):

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = c.fetchone()

    conn.close()

    if user:
        return User(user[0], user[1])

    return None


# ---------------- AUTH ROUTES ----------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("users.db")
        c = conn.cursor()

        try:
            c.execute(
                "INSERT INTO users (username,password) VALUES (?,?)",
                (username, password)
            )
            conn.commit()
        except:
            conn.close()
            return "Username already exists"

        conn.close()

        return redirect("/login")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("users.db")
        c = conn.cursor()

        c.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        )

        user = c.fetchone()
        conn.close()

        if user:
            login_user(User(user[0], user[1]))
            return redirect("/")

        return "Invalid Login"

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():

    logout_user()
    return redirect("/login")


# ---------------- PDF ----------------

def generate_pdf(text, emotion, timeline):

    filename = "report.pdf"
    filepath = os.path.join(STATIC_FOLDER, filename)

    c = canvas.Canvas(filepath, pagesize=A4)

    width, height = A4
    y = height - 50

    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, y, "Voice Emotion Analysis Report")

    y -= 40
    c.setFont("Helvetica", 12)

    c.drawString(50, y, f"Text: {text}")
    y -= 25

    c.drawString(50, y, f"Emotion: {emotion}")
    y -= 40

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Timeline")

    y -= 25
    c.setFont("Helvetica", 11)

    for t in timeline:

        line = f"{t['start']} - {t['end']} : {t['text']} ({t['emotion']})"
        c.drawString(50, y, line)

        y -= 20

        if y < 50:
            c.showPage()
            y = height - 50

    c.save()

    return filename


# ---------------- AI FUNCTIONS ----------------

def detect_emotion(text):

    blob = TextBlob(text)
    polarity = blob.sentiment.polarity

    if polarity > 0.2:
        return "Happy 😊"

    elif polarity < -0.2:
        return "Sad 😢"

    else:
        return "Neutral 🙂"


def recognize_speech(path):

    r = sr.Recognizer()

    with sr.AudioFile(path) as source:
        audio = r.record(source)

    try:
        return r.recognize_google(audio)

    except:
        return "Could not recognize speech"


def split_timeline(text):

    words = text.split()
    timeline = []

    start = 0
    step = 3

    for i in range(0, len(words), 5):

        part = " ".join(words[i:i+5])
        emo = detect_emotion(part)

        timeline.append({
            "start": start,
            "end": start + step,
            "text": part,
            "emotion": emo
        })

        start += step

    return timeline


# ---------------- MAIN ROUTES ----------------

@app.route("/")
@login_required
def home():

    return render_template("dashboard.html")


@app.route("/uploads/<filename>")
def uploaded_file(filename):

    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/upload", methods=["POST"])
@login_required
def upload():

    file = request.files.get("file")

    if not file or file.filename == "":
        return render_template("dashboard.html", error="No file selected")

    try:

        # Save file
        filename = secure_filename(file.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(path)

        # AI
        text = recognize_speech(path)
        emotion = detect_emotion(text)
        timeline = split_timeline(text)

        # Chart
        emotion_count = {}

        for t in timeline:
            emo = t["emotion"].split()[0]
            emotion_count[emo] = emotion_count.get(emo, 0) + 1

        chart_labels = list(emotion_count.keys())
        chart_data = list(emotion_count.values())

        # PDF
        pdf_file = generate_pdf(text, emotion, timeline)

        # Save to DB
        conn = sqlite3.connect("users.db")
        c = conn.cursor()

        c.execute("""
        INSERT INTO reports (user_id, text, emotion, pdf_file)
        VALUES (?,?,?,?)
        """, (current_user.id, text, emotion, pdf_file))

        conn.commit()
        conn.close()

        return render_template(
            "dashboard.html",
            text=text,
            emotion=emotion,
            timeline=timeline,
            chart_labels=chart_labels,
            chart_data=chart_data,
            pdf_file=pdf_file,
            filename=filename
        )

    except Exception as e:

        return render_template(
            "dashboard.html",
            error=str(e)
        )


# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

