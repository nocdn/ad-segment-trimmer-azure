import os
import json
import uuid
import subprocess
import requests
import logging
from io import BytesIO
from flask import Flask, request, send_file, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from openai import AzureOpenAI
from werkzeug.utils import secure_filename
from flask_cors import CORS

# setup logging - detailed & verbose logs
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

load_dotenv()

app = Flask(__name__)
CORS(app)

# azure keys from .env
AI_SPEECH_RESOURCE_ENDPOINT = os.environ.get("AI_SPEECH_RESOURCE_ENDPOINT")
AI_SPEECH_PRIMARY_KEY = os.environ.get("AI_SPEECH_PRIMARY_KEY")
AZURE_API_ENDPOINT = os.environ.get("AZURE_API_ENDPOINT")
AZURE_OPENAI_KEY = os.environ.get("AZURE_OPENAI_KEY")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
AZURE_API_VERSION = os.environ.get("AZURE_API_VERSION")
logging.debug("ai_speech_resource_endpoint from .env: %s", AI_SPEECH_RESOURCE_ENDPOINT)
logging.debug("ai_speech_primary_key from .env: %s", AI_SPEECH_PRIMARY_KEY)

# getting rate limiting from .env
RATE_LIMITING_ENABLED = os.environ.get("RATE_LIMITING_ENABLED")
logging.debug("rate_limiting_enabled from .env: %s", RATE_LIMITING_ENABLED)

if RATE_LIMITING_ENABLED == "true":
    RATE_LIMIT = os.environ.get("RATE_LIMIT")
    logging.debug("rate_limit from .env: %s", RATE_LIMIT)
else:
    RATE_LIMIT = None
    logging.debug("rate limiting is disabled")

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["5 per day"],
    storage_uri="memory://",
)

# create Azure openai client
client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    azure_endpoint=AZURE_API_ENDPOINT,
    api_version=AZURE_API_VERSION,
)
logging.debug("initialized Azure OpenAI client")
    """
    calls the fireworks transcription api and returns a tuple (transcription_text, segments, word-level transcript)
    """
    logging.debug("starting fireworks transcription on file: %s", filePath)
    try:
        with open(filePath, "rb") as file:
            logging.debug("opened file for fireworks transcription: %s", filePath)
            response = requests.post(
                "https://audio-prod.us-virginia-1.direct.fireworks.ai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {FIREWORKS_API_KEY}"},
                files={"file": file},
                data={
                    "vad_model": "silero",
                    "alignment_model": "tdnn_ffn",
                    "preprocessing": "none",
                    "temperature": "0",
                    "timestamp_granularities": "word,segment",
                    "audio_window_seconds": "5",
                    "speculation_window_words": "4",
                    "response_format": "verbose_json"
                },
            )
        logging.debug("fireworks transcription response received with status code: %s", response.status_code)
    except Exception as e:
        logging.error("exception occurred while sending fireworks transcription request: %s", str(e))
        raise

    if response.status_code == 200:
        dict_response = response.json()
        logging.debug("fireworks transcription response json parsed")
        text = dict_response["text"]
        segments = dict_response["segments"]
        words = dict_response["words"]
        logging.debug("transcription text length: %d, segments count: %d, words count: %d", len(text), len(segments), len(words))
        # clean each word, keeping only "word", "start", and "end"
        cleaned_words = []
        for idx, word in enumerate(words):
            cleaned_word = {
                "word": word["word"],
                "start": word["start"],
                "end": word["end"]
            }
            cleaned_words.append(cleaned_word)
            logging.debug("cleaned word %d: %s", idx, cleaned_word)
        return text, segments, cleaned_words
    else:
        error_msg = f"transcription api error: {response.status_code}, {response.text}"
        logging.error(error_msg)
        raise Exception(error_msg)

def transcribe_azure(filePath):
    """
    calls the azure transcription api and returns a tuple (transcription_text, segments, word-level transcript)
    """
    logging.debug("starting azure transcription on file: %s", filePath)
    try:
        with open(filePath, "rb") as file:
            logging.debug("opened file for azure transcription: %s", filePath)
            azure_response = requests.post(
                AI_SPEECH_RESOURCE_ENDPOINT,
                headers={
                    "Ocp-Apim-Subscription-Key": AI_SPEECH_PRIMARY_KEY,
                    # remove content-type header - requests will set it correctly with boundary
                },
                files={"audio": file},
                data={"definition": json.dumps({"locales": ["en-US"]})}
            )
        logging.debug("azure transcription response received with status code: %s", azure_response.status_code)
    except Exception as e:
        logging.error("exception occurred while sending azure transcription request: %s", str(e))
        raise

    if azure_response.status_code == 200:
        dict_response = azure_response.json()
        logging.debug("azure transcription response json parsed")
        # extract full transcript from combinedPhrases
        full_text = " ".join([phrase["text"] for phrase in dict_response["combinedPhrases"]])
        logging.debug("full transcription text extracted with length: %d", len(full_text))
        # use phrases as segments
        segments = dict_response["phrases"]
        logging.debug("transcription segments count: %d", len(segments))
        # extract and format word-level transcript
        cleaned_words = []
        for p_index, phrase in enumerate(dict_response["phrases"]):
            for w_index, word in enumerate(phrase["words"]):
                # convert milliseconds to seconds for consistency with fireworks api
                start_time = word["offsetMilliseconds"] / 1000
                end_time = start_time + (word["durationMilliseconds"] / 1000)
                word_entry = {
                    "word": word["text"],
                    "start": start_time,
                    "end": end_time
                }
                cleaned_words.append(word_entry)
                logging.debug("phrase %d, word %d: %s", p_index, w_index, word_entry)
        return full_text, segments, cleaned_words
    else:
        error_msg = f"azure transcription api error: {azure_response.status_code}, {azure_response.text}"
        logging.error(error_msg)
        raise Exception(error_msg)

def GetSegments(transcriptionText):
    """
    uses the azure openai api to extract advertisement segments from the transcript.
    the response is expected to be an array of segments in json text.
    """
    logging.debug("calling azure openai api with transcription text of length: %d", len(transcriptionText))
    try:
        result = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": "You are an AI assistant that helps people find information."
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": message
                    }
                ]
            }
        ],
        max_tokens=800,
        temperature=0.7,
        top_p=0.95,
        frequency_penalty=0,
        presence_penalty=0,
        stop=None
        )

        return result.choices[0].message.content or ""
    except Exception as e:
        logging.error("error calling azure openai api: %s", str(e))
        raise

def generate_ffmpeg_trim_command(input_file, output_file, segments_to_remove):
    """
    generate an ffmpeg command to remove segments from an audio file.
    segments_to_remove should be a list of (start_time, end_time) tuples (in seconds).
    """
    logging.debug("generating ffmpeg trim command for input_file: %s, output_file: %s", input_file, output_file)
    if not input_file or not output_file:
        error_msg = "input and output file paths must be provided"
        logging.error(error_msg)
        raise ValueError(error_msg)
    if not segments_to_remove or not isinstance(segments_to_remove, list):
        error_msg = "segments_to_remove must be a non-empty list of (start, end) tuples"
        logging.error(error_msg)
        raise ValueError(error_msg)

    segments_to_remove.sort(key=lambda x: x[0])
    for i, (start, end) in enumerate(segments_to_remove):
        logging.debug("validating segment %d: start=%s, end=%s", i, start, end)
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            error_msg = f"segment {i}: start and end times must be numbers"
            logging.error(error_msg)
            raise ValueError(error_msg)
        if start >= end:
            error_msg = f"segment {i}: start time ({start}) must be less than end time ({end})"
            logging.error(error_msg)
            raise ValueError(error_msg)
        if i > 0 and start < segments_to_remove[i-1][1]:
            error_msg = f"segments {i-1} and {i} overlap or are not in ascending order"
            logging.error(error_msg)
            raise ValueError(error_msg)

    # build ffmpeg filter_complex string
    filter_parts = []
    segment_labels = []
    # extract audio from beginning to start of the first segment
    filter_parts.append(f"[0:a]atrim=0:{segments_to_remove[0][0]}[s0]")
    segment_labels.append("[s0]")
    logging.debug("added trim from 0 to %s", segments_to_remove[0][0])
    # extract audio between segments
    for i in range(len(segments_to_remove) - 1):
        current_end = segments_to_remove[i][1]
        next_start = segments_to_remove[i+1][0]
        if current_end < next_start:
            filter_parts.append(f"[0:a]atrim={current_end}:{next_start}[s{i+1}]")
            segment_labels.append(f"[s{i+1}]")
            logging.debug("added trim from %s to %s", current_end, next_start)
    # extract audio from the end of the last segment to the end of the file
    filter_parts.append(f"[0:a]atrim=start={segments_to_remove[-1][1]}[s{len(segments_to_remove)}]")
    segment_labels.append(f"[s{len(segments_to_remove)}]")
    logging.debug("added trim from %s to end of file", segments_to_remove[-1][1])
    concat_filter = f"{''.join(segment_labels)}concat=n={len(segment_labels)}:v=0:a=1[out]"

    filter_complex = ";".join(filter_parts) + ";" + concat_filter
    command = f'ffmpeg -i "{input_file}" -filter_complex "{filter_complex}" -map "[out]" "{output_file}"'
    logging.debug("generated ffmpeg command: %s", command)
    return command

def find_phrases_timestamps(transcript_data, phrases):
    """
    for each phrase from the azure openai response (either a string or list of strings),
    find its occurrences in the transcript data (a list of words with timestamps)
    and return a list of (start_time, end_time) tuples.
    """
    logging.debug("starting phrase matching; transcript_data length: %d, phrases type: %s", len(transcript_data) if transcript_data else 0, type(phrases))
    if not transcript_data or not phrases:
        logging.debug("no transcript data or phrases provided, returning empty list")
        return []
    
    if isinstance(phrases, str):
        phrases = [phrases]
    
    # normalise transcript words
    transcript_words = []
    for idx, item in enumerate(transcript_data):
        cleaned_word = item['word'].strip().lower().rstrip('.,:;!?')
        transcript_words.append({
            'word': cleaned_word,
            'start': item['start'],
            'end': item['end']
        })
    logging.debug("normalized %d transcript words", len(transcript_words))
    
    results = []
    total_words = len(transcript_words)
    
    # look for each phrase as a sequence of words
    for phrase in phrases:
        if not phrase:
            continue
        target_words = [w.strip().lower().rstrip('.,:;!?') for w in phrase.split()]
        target_length = len(target_words)
        logging.debug("searching for phrase: '%s' (normalized: %s) with %d words", phrase, target_words, target_length)
        for i in range(total_words - target_length + 1):
            match = True
            for j in range(target_length):
                if transcript_words[i+j]['word'] != target_words[j]:
                    match = False
                    break
            if match:
                start_time = transcript_words[i]['start']
                end_time = transcript_words[i+target_length-1]['end']
                results.append((start_time, end_time))
                logging.debug("found phrase '%s' at time interval (%s, %s)", phrase, start_time, end_time)
    logging.debug("total matches found: %d", len(results))
    return results

@app.route("/process", methods=["POST"])
@limiter.limit(RATE_LIMIT)
def process_audio():
    """
    expects a multipart/form-data post with an audio file attached under the key "file".
    it will process the file (transcribe -> extract ad segments -> find those segments' timestamps -> remove those segments via ffmpeg)
    and send back the cleaned audio file. both input and output files are deleted afterward.
    """
    logging.debug("received request at /process")
    if "file" not in request.files:
        logging.error("no file provided in request")
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if file.filename == "":
        logging.error("empty filename provided in request")
        return jsonify({"error": "No selected file"}), 400

    logging.debug("processing file: %s", file.filename)
    # save the incoming file with a uuid to prevent conflics/overwrites
    uploads_dir = "uploads"
    os.makedirs(uploads_dir, exist_ok=True)
    logging.debug("ensured uploads dir exists: %s", uploads_dir)
    filename = secure_filename(file.filename)
    unique_id = uuid.uuid4().hex
    logging.debug("generated uuid: %s for file: %s", unique_id, filename)
    input_file = os.path.join(uploads_dir, unique_id + "_" + filename)
    try:
        file.save(input_file)
        logging.debug("saved uploaded file as: %s", input_file)
    except Exception as e:
        logging.error("error saving uploaded file: %s", str(e))
        return jsonify({"error": f"Error saving file: {str(e)}"}), 500

    # define the output file name (appending _edited before the extension)
    base, ext = os.path.splitext(input_file)
    output_file = base + "_edited" + ext
    logging.debug("output_file defined as: %s", output_file)

    try:
        # first, transcribe the audio file using azure
        logging.debug("starting azure transcription process")
        transcription_text, _, transcript_words = transcribe_azure(input_file)
        logging.debug("azure transcription succeeded; transcript text length: %d, transcript_words count: %d", len(transcription_text), len(transcript_words))
    except Exception as e:
        logging.error("error during azure transcription: %s", str(e))
        if os.path.exists(input_file):
            os.remove(input_file)
            logging.debug("removed input file due to error: %s", input_file)
        return jsonify({"error": str(e)}), 500

    try:
        # using azure openai to extract advertisement segments
        logging.debug("calling azure openai to extract advertisement segments")
        phrases_str = GetSegments(transcription_text)
        try:
            phrases = json.loads(phrases_str)
            logging.debug("gpt-4o found phrases: %s", phrases)
        except json.JSONDecodeError as je:
            logging.error("json decode error for azure openai response: %s", str(je))
            phrases = []
    except Exception as e:
        logging.error("error calling azure openai service: %s", str(e))
        if os.path.exists(input_file):
            os.remove(input_file)
            logging.debug("removed input file due to azure openai error: %s", input_file)
        return jsonify({"error": f"Error from Azure OpenAI: {str(e)}"}), 500

    # find the timestamps of the phrases in the transcript
    matches = find_phrases_timestamps(transcript_words, phrases)
    logging.debug("matches found: %s", matches)
    
    # if no matches found, simply copy the file (i.e. nothing to remove)
    if not matches:
        logging.debug("no matches found; copying file without trimming")
        cmd = f'cp "{input_file}" "{output_file}"'
    else:
        try:
            cmd = generate_ffmpeg_trim_command(input_file, output_file, matches)
            logging.debug("ffmpeg command generated: %s", cmd)
        except Exception as e:
            logging.error("error generating ffmpeg command: %s", str(e))
            if os.path.exists(input_file):
                os.remove(input_file)
                logging.debug("removed input file due to command generation error: %s", input_file)
            return jsonify({"error": f"Error generating FFmpeg command: {str(e)}"}), 500

    try:
        # execute the ffmpeg command to trim the segments
        logging.debug("executing ffmpeg command: %s", cmd)
        result = subprocess.run(cmd, shell=True, capture_output=True)
        if result.returncode != 0:
            error_str = result.stderr.decode()
            logging.error("ffmpeg command failed with error: %s", error_str)
            if os.path.exists(input_file):
                os.remove(input_file)
                logging.debug("removed input file due to ffmpeg error: %s", input_file)
            return jsonify({"error": f"FFmpeg command failed: {error_str}"}), 500
        else:
            logging.debug("ffmpeg command executed successfully")
    except Exception as e:
        logging.error("exception executing ffmpeg command: %s", str(e))
        if os.path.exists(input_file):
            os.remove(input_file)
            logging.debug("removed input file due to exception running ffmpeg: %s", input_file)
        return jsonify({"error": f"Error executing FFmpeg command: {str(e)}"}), 500

    try:
        # read the processed output file
        logging.debug("reading processed output file: %s", output_file)
        with open(output_file, "rb") as f:
            audio_data = f.read()
        logging.debug("successfully read processed file, size: %d bytes", len(audio_data))
    except Exception as e:
        logging.error("error reading output file: %s", str(e))
        if os.path.exists(input_file):
            os.remove(input_file)
            logging.debug("removed input file during output file read error: %s", input_file)
        if os.path.exists(output_file):
            os.remove(output_file)
            logging.debug("removed output file during output file read error: %s", output_file)
        return jsonify({"error": f"Error reading output file: {str(e)}"}), 500

    # cleanup: deleting both the input and output files from the working dir
    if os.path.exists(input_file):
        os.remove(input_file)
        logging.debug("cleaned up input file: %s", input_file)
    if os.path.exists(output_file):
        os.remove(output_file)
        logging.debug("cleaned up output file: %s", output_file)

    # extract the original filename to then create a new filename from it (without uuid)
    original_base, _ = os.path.splitext(filename)
    download_filename = original_base + "_edited.mp3"
    logging.debug("final download filename set as: %s", download_filename)

    # return the cleaned audio file
    logging.debug("returning the processed audio file")
    return send_file(
        BytesIO(audio_data),
        download_name=download_filename,
        as_attachment=True,
        mimetype="audio/mpeg"
    )

if __name__ == "__main__":
    logging.debug("starting flask app on 0.0.0.0:7070")
    app.run(debug=True, host="0.0.0.0", port=7070)