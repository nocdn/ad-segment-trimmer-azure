import requests
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FIREWORKS_API_KEY = os.environ.get("FIREWORKS_API_KEY")

client = OpenAI(api_key=GEMINI_API_KEY, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")

def transcribe(filePath):
    with open(filePath, "rb") as file:
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

    if response.status_code == 200:
        dict_response = response.json()
        text = dict_response["text"]
        segments = dict_response["segments"]
        
        # Clean the words data by removing unwanted fields
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
        return(f"Error: {response.status_code}", response.text)

# transcription = transcribe("archer.mp3")
# print(transcription[2])

def processGemini(transcriptionText):
    response = client.chat.completions.create(
        model="gemini-2.0-flash",
        n=1,
        messages=[
            {"role": "system", "content": "From the provided podcast transcript, please extract the entire ad segments, and put each of the segments into a text array - but only the segment. If there are multiple ad segments, then there should be multiple array items. Output just the array of this text, no codeblocks or backticks."},
            {
                "role": "user",
                "content": transcriptionText
            }
        ]
    )
    return response.choices[0].message.content


def generate_ffmpeg_trim_command(input_file, output_file, segments_to_remove):
    """
    Generate an FFmpeg command to remove multiple segments from an audio file.
    
    Args:
        input_file (str): Path to the input audio file
        output_file (str): Path to the output audio file
        segments_to_remove (list): List of tuples (start_time, end_time) in seconds
                                 representing segments to remove
        
    Returns:
        str: FFmpeg command string ready to be executed
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


# Example usage
input_file = "archer.mp3"
output_file = "archerClean.mp3"

segments_to_remove = [
    (4.813, 9.407),
    (9.867, 10.226),
    (11.864, 12.464)
]

# cmd = generate_ffmpeg_trim_command(input_file, output_file, segments_to_remove)
# print(cmd)


def find_phrase_timestamps(transcript_data, phrase):
    """
    Find the start and end timestamps for a specific phrase in a transcript.
    
    Args:
        transcript_data (list): List of dictionaries containing word-level transcript data
                               with 'word', 'start', and 'end' keys
        phrase (str): The phrase to search for
        
    Returns:
        tuple: (start_time, end_time) of the matched phrase, or (None, None) if not found
    """
    if not transcript_data or not phrase:
        return None, None
    
    # Clean and normalize the phrase for better matching
    target_words = [word.strip().lower().rstrip('.,:;!?') for word in phrase.split()]
    if not target_words:
        return None, None
    
    # Prepare the transcript words
    transcript_words = []
    for item in transcript_data:
        # Clean each transcript word similar to how we cleaned the target phrase
        cleaned_word = item['word'].strip().lower().rstrip('.,:;!?')
        transcript_words.append({
            'word': cleaned_word,
            'start': item['start'],
            'end': item['end'],
            'original': item
        })
    
    # Search for the sequence
    for i in range(len(transcript_words) - len(target_words) + 1):
        match = True
        for j, target_word in enumerate(target_words):
            if i + j >= len(transcript_words) or transcript_words[i + j]['word'] != target_word:
                match = False
                break
        
        if match:
            # Found the sequence
            start_time = transcript_words[i]['start']
            end_time = transcript_words[i + len(target_words) - 1]['end']
            return start_time, end_time
    
    # Phrase not found
    return None, None


# Example usage
transcript_data = [
  {
    "word": "People",
    "start": 0.098,
    "end": 0.378
  },
  {
    "word": "sometimes",
    "start": 0.378,
    "end": 0.917
  },
  {
    "word": "strategically",
    "start": 0.917,
    "end": 1.696
  },
  {
    "word": "modify",
    "start": 1.696,
    "end": 2.216
  },
  {
    "word": "their",
    "start": 2.216,
    "end": 2.375
  },
  {
    "word": "behaviour",
    "start": 2.375,
    "end": 2.855
  },
  {
    "word": "to",
    "start": 2.855,
    "end": 2.975
  },
  {
    "word": "please",
    "start": 2.975,
    "end": 3.374
  },
  {
    "word": "evaluators.",
    "start": 3.374,
    "end": 4.193
  },
  {
    "word": "Consider",
    "start": 4.813,
    "end": 5.292
  },
  {
    "word": "a",
    "start": 5.292,
    "end": 5.332
  },
  {
    "word": "politician",
    "start": 5.332,
    "end": 5.971
  },
  {
    "word": "who",
    "start": 5.971,
    "end": 6.111
  },
  {
    "word": "pretends",
    "start": 6.111,
    "end": 6.551
  },
  {
    "word": "to",
    "start": 6.551,
    "end": 6.67
  },
  {
    "word": "be",
    "start": 6.67,
    "end": 6.81
  },
  {
    "word": "aligned",
    "start": 6.81,
    "end": 7.19
  },
  {
    "word": "with",
    "start": 7.19,
    "end": 7.33
  },
  {
    "word": "constituents",
    "start": 7.33,
    "end": 8.129
  },
  {
    "word": "to",
    "start": 8.129,
    "end": 8.269
  },
  {
    "word": "secure",
    "start": 8.269,
    "end": 8.728
  },
  {
    "word": "their",
    "start": 8.728,
    "end": 8.888
  },
  {
    "word": "votes,",
    "start": 8.888,
    "end": 9.407
  },
  {
    "word": "or",
    "start": 9.707,
    "end": 9.827
  },
  {
    "word": "a",
    "start": 9.827,
    "end": 9.867
  },
  {
    "word": "job",
    "start": 9.867,
    "end": 10.226
  },
  {
    "word": "applicant",
    "start": 10.226,
    "end": 10.686
  },
  {
    "word": "who",
    "start": 10.686,
    "end": 10.746
  },
  {
    "word": "fakes",
    "start": 10.746,
    "end": 11.085
  },
  {
    "word": "passion",
    "start": 11.085,
    "end": 11.525
  },
  {
    "word": "about",
    "start": 11.525,
    "end": 11.824
  },
  {
    "word": "a",
    "start": 11.824,
    "end": 11.864
  },
  {
    "word": "potential",
    "start": 11.864,
    "end": 12.464
  },
  {
    "word": "employer",
    "start": 12.464,
    "end": 12.963
  },
  {
    "word": "to",
    "start": 12.963,
    "end": 13.163
  },
  {
    "word": "get",
    "start": 13.163,
    "end": 13.463
  },
  {
    "word": "a",
    "start": 13.463,
    "end": 13.502
  },
  {
    "word": "job.",
    "start": 13.502,
    "end": 13.942
  }
]

phrase = "to please evaluators."
start_time, end_time = find_phrase_timestamps(transcript_data, phrase)

if start_time is not None and end_time is not None:
    print(f"Phrase '{phrase}' found from {start_time}s to {end_time}s")
else:
    print(f"Phrase '{phrase}' not found in transcript")