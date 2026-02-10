from flask import Flask, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from pydub import AudioSegment

import os
import speech_recognition as sr
from textblob import TextBlob


# ---------------- APP CONFIG ----------------

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
STATIC_FOLDER = "static"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ---------------- AUDIO CONVERT ----------------

def convert_to_wav(input_path):

    output_path = input_path.rsplit(".", 1)[0] + ".wav"

    audio = AudioSegment.from_file(input_path)
    audio = audio.set_channels(1)
    audio = audio.set_frame_rate(16000)

    audio.export(output_path, format="wav")

    return output_path


# ---------------- EMOTION ----------------

# ---------------- SPEECH ----------------

def recognize_speech(path):

    r = sr.Recognizer()

    with sr.AudioFile(path) as source:
        audio = r.record(source)

    try:
        return r.recognize_google(audio)

    except:
        return "Could not recognize speech"

def detect_emotion(text):
    
    blob = TextBlob(text)

    polarity = blob.sentiment.polarity      # -1 to +1
    subjectivity = blob.sentiment.subjectivity  # 0 to 1

    text = text.lower()

    # Keyword based emotions (strong signals)
    angry_words = ["angry", "hate", "annoyed", "furious", "irritated"]
    fear_words = ["fear", "afraid", "scared", "panic", "worried"]
    sad_words = ["sad", "cry", "upset", "depressed", "lonely"]
    happy_words = ["happy", "great", "love", "excited", "awesome", "good"]

    # Keyword detection
    if any(word in text for word in angry_words):
        return "Angry 😡"

    if any(word in text for word in fear_words):
        return "Fear 😨"

    if any(word in text for word in sad_words):
        return "Sad 😢"

    if any(word in text for word in happy_words):
        return "Happy 😊"

    # Sentiment based detection
    if polarity >= 0.5:
        return "Very Happy 😄"

    elif polarity >= 0.2:
        return "Happy 🙂"

    elif polarity <= -0.5:
        return "Very Sad 😭"

    elif polarity <= -0.2:
        return "Sad 😞"

    elif subjectivity >= 0.6:
        return "Emotional 😔"

    else:
        return "Neutral 😐"

# ---------------- TIMELINE ----------------

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


# ---------------- MAIN ----------------

@app.route("/")
def home():

    return render_template("dashboard.html")


@app.route("/uploads/<filename>")
def uploaded_file(filename):

    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ---------------- UPLOAD ----------------

@app.route("/upload", methods=["POST"])
def upload():

    file = request.files.get("file")

    if not file or file.filename == "":
        return render_template("dashboard.html", error="No file selected")

    try:
        # Save file
        filename = secure_filename(file.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(path)

        # Convert to WAV if needed
        if not path.lower().endswith(".wav"):
            path = convert_to_wav(path)

        # Speech to Text
        text = recognize_speech(path)

        # Emotion
        emotion = detect_emotion(text)

        timeline = split_timeline(text)

        emotion_count = {}

        for t in timeline:
                emo = t["emotion"]
                emotion_count[emo] = emotion_count.get(emo, 0) + 1

        emotion = max(emotion_count, key=emotion_count.get)

        chart_labels = list(emotion_count.keys())
        chart_data = list(emotion_count.values())

        # PDF
        pdf_file = generate_pdf(text, emotion, timeline)

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
            error=f"Error: {str(e)}"
        )


# ---------------- RUN ----------------

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )
