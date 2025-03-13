import requests
import os
from openai import OpenAI
from dotenv import load_dotenv
import json

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FIREWORKS_API_KEY = os.environ.get("FIREWORKS_API_KEY")

print("GEMINI_API_KEY from .env ", GEMINI_API_KEY)
print("FIREWORKS_API_KEY from .env ", FIREWORKS_API_KEY)

client = OpenAI(
    api_key="AIzaSyAS6cTzjhTN4SArysE3bFxch7ZJn4hGxg8",
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

input_file = "openai.mp3"
# output file should be the same as input file but with _edited appended to the name before the extension
output_file = input_file.split(".")[0] + "_edited." + input_file.split(".")[1]

def transcribe(filePath):
    with open(filePath, "rb") as file:
        response = requests.post(
            "https://audio-prod.us-virginia-1.direct.fireworks.ai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer fw_3Zf2eWpWZ5ayYuZG6R7UTcvR"},
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

    if response.status_code == 200:
        dict_response = response.json()
        text = dict_response["text"]
        segments = dict_response["segments"]

        # cleaning the transcript json data by removing keys like "confidence" and "language" and "hallucination_score"
        words = dict_response["words"]
        cleaned_words = []
        for word in words:
            cleaned_word = {
                "word": word["word"],
                "start": word["start"],
                "end": word["end"]
            }
            cleaned_words.append(cleaned_word)

        return text, segments, cleaned_words
    else:
        return (f"Error: {response.status_code}", response.text)


singleSegmentPrompt = "From the provided podcast transcript, please output the entire first advertisement segment. Output it verbatim. DO NOT OUTPUT IT IN ANY CODEBLOCKS OR BACKTICKS OR ANYTHING, JUST THE SEGMENT AS YOUR RESPONSE. This is going into a safety-critical system so it cannot have any code blocks or backticks. Do not change the segment case, punctuation or capitalization."
multipleSegmentsPrompt = "From the provided podcast transcript, please output all of the advertisement segments. Output them verbatim. Output them as an array of strings with each string being a segment. If a segment is repeated exactly in another part of the transcript, only output it once. DO NOT OUTPUT THEM IN ANY CODEBLOCKS OR BACKTICKS OR ANYTHING, JUST THE ARRAY OF SEGMENTS AS YOUR RESPONSE. This is going into a safety-critical system so it cannot have any code blocks or backticks. Do not change the segments' case, punctuation or capitalization."
def geminiGetSegments(transcriptionText):
    """
    Get the first advertisement segment from the transcription using Gemini API.

    Args:
        transcriptionText (str): The transcription text to extract the advertisement segment from.

    Returns:
        str: The extracted advertisement segment.
    """

    response = client.chat.completions.create(
        model="gemini-2.0-flash",
        n=1,
        messages=[
            {"role": "system", "content": multipleSegmentsPrompt},
            {"role": "user", "content": transcriptionText}
        ]
    )
    return response.choices[0].message.content



def generate_ffmpeg_trim_command(input_file, output_file, segments_to_remove):
    """
    Generate an FFmpeg command to remove multiple segments from an audio file.
    
    Args:
        input_file (str): Path to the input audio file.
        output_file (str): Path to the output audio file.
        segments_to_remove (list): List of tuples (start_time, end_time) in seconds
                                   representing segments to remove.
        
    Returns:
        str: FFmpeg command string ready to be executed.
    """

    # Validate inputs
    if not input_file or not output_file:
        raise ValueError("Input and output file paths must be provided")

    if not segments_to_remove or not isinstance(segments_to_remove, list):
        raise ValueError("segments_to_remove must be a non-empty list of (start, end) tuples")

    # Sort segments by start time to ensure proper processing
    segments_to_remove.sort(key=lambda x: x[0])

    # Validate each segment
    for i, (start, end) in enumerate(segments_to_remove):
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            raise ValueError(f"Segment {i}: Start and end times must be numbers")

        if start >= end:
            raise ValueError(f"Segment {i}: Start time ({start}) must be less than end time ({end})")

        # Check for overlapping segments
        if i > 0 and start < segments_to_remove[i-1][1]:
            raise ValueError(f"Segments {i-1} and {i} overlap or are not in ascending order")

    # Generate filter_complex parts
    filter_parts = []
    segment_labels = []

    # First segment (from 0 to first cut)
    filter_parts.append(f"[0:a]atrim=0:{segments_to_remove[0][0]}[s0]")
    segment_labels.append("[s0]")

    # Middle segments (between cuts)
    for i in range(len(segments_to_remove) - 1):
        current_end = segments_to_remove[i][1]
        next_start = segments_to_remove[i+1][0]
        if current_end < next_start:  # Only add if there's content between segments
            filter_parts.append(f"[0:a]atrim={current_end}:{next_start}[s{i+1}]")
            segment_labels.append(f"[s{i+1}]")

    # Last segment (from last cut to end)
    filter_parts.append(f"[0:a]atrim=start={segments_to_remove[-1][1]}[s{len(segments_to_remove)}]")
    segment_labels.append(f"[s{len(segments_to_remove)}]")
    # Concat filter
    concat_filter = f"{''.join(segment_labels)}concat=n={len(segment_labels)}:v=0:a=1[out]"
    # Build the complete filter_complex
    filter_complex = ";".join(filter_parts) + ";" + concat_filter
    # Create the FFmpeg command
    command = f'ffmpeg -i "{input_file}" -filter_complex "{filter_complex}" -map "[out]" "{output_file}"'
    return command



def find_phrases_timestamps(transcript_data, phrases):
    """
    Find the start and end timestamps for all occurrences of each phrase.
    
    Args:
        transcript_data (list): List of dictionaries containing word-level transcript data
                                with 'word', 'start', and 'end' keys.
        phrases (str or list): A single phrase or a list of phrases to search for.
        
    Returns:
        list: A list of tuples (start_time, end_time) for each matched occurrence.
              If no matches are found, returns an empty list.
    """
    if not transcript_data or not phrases:
        return []
    
    # Ensure phrases is a list
    if isinstance(phrases, str):
        phrases = [phrases]
    
    # Prepare the transcript words with normalized text
    transcript_words = []
    for item in transcript_data:
        cleaned_word = item['word'].strip().lower().rstrip('.,:;!?')
        transcript_words.append({
            'word': cleaned_word,
            'start': item['start'],
            'end': item['end']
        })
    
    results = []
    total_words = len(transcript_words)
    
    # For each phrase, find all occurrences in the transcript
    for phrase in phrases:
        if not phrase:
            continue
        
        target_words = [w.strip().lower().rstrip('.,:;!?') for w in phrase.split()]
        target_length = len(target_words)
        
        # Slide over transcript_words to search for the sequence
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
    
    return results


# getting actual transcription to pass the full text to gemini to extract the advertisement segments
# and pass just the words to find the timestamps of the segments extracted by gemini
transcription = transcribe(input_file)
transcript_words = transcription[2]

# gemini returning the extracted advertisement segments as a string
# need to parse it with json.loads so it becomes an actual python list
phrases_str = geminiGetSegments(transcription[0])
try:
    phrases = json.loads(phrases_str)
except json.JSONDecodeError as e:
    print("Error parsing the Gemini response:", e)
    phrases = [] # Fallback to empty list if parsing fails


print("phrases: ", phrases)
print("type(phrases): ", type(phrases))


# phrases array of segments is passed to find_phrases_timestamps to find the start and end timestamps of the segments
matches = find_phrases_timestamps(transcript_words, phrases)
print("matches: ", matches)

if matches:
    for start_time, end_time in matches:
        print(f"Found phrase from {start_time}s to {end_time}s")
else:
    print("No provided phrases were found in transcript.")

# Remove all found segments
segments_to_remove = matches  # matches is a list of (start, end) tuples.


# generating the ffmpeg command to remove the segments from the audio file
cmd = generate_ffmpeg_trim_command(input_file, output_file, segments_to_remove)
print("Generated FFmpeg command:")
print(cmd)

print("Executing FFmpeg command:")
os.system(cmd)