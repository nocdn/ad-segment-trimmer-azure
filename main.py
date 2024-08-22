import os
import requests
import json
from pydub import AudioSegment

# Step 1: Open the file "podcast-transcript.txt" and read it into a string
with open('podcast-transcript.txt', 'r') as f:
    transcript = f.read()

# Step 2: System prompt for the API
systemPrompt = "From the provided podcast transcript, for each ad segment, extract the start time, and end time of the FULL segment (so not just the portions). Put this into a list for each segment, a start time and end time. Remember to look at the start time and end time of each part of the transcript. Take a deep breath, and this is important. Output in only JSON, with no code block or anything."

# Step 3: Read the system environment variable OPENAI_API_KEY
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Step 4: The URL for the OpenAI API endpoint
url = 'https://api.openai.com/v1/chat/completions'

# Step 5: The headers for the HTTP request
headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {OPENAI_API_KEY}'
}

# Step 6: The data payload for the HTTP request
data = {
    "model": "gpt-4o",
    "messages": [
        {
            "role": "system",
            "content": systemPrompt
        },
        {
            "role": "user",
            "content": transcript
        }
    ]
}

# Step 7: Send the POST request to the OpenAI API
response = requests.post(url, headers=headers, json=data)

# Step 8: Parse the response
jsonResponse = response.json()
justOutput = jsonResponse['choices'][0]['message']['content']

# Step 9: Parse the JSON output into a Python list of dictionaries
ad_segments = json.loads(justOutput)

# Step 10: Load the input MP3 file
audio = AudioSegment.from_mp3("input.mp3")

# Step 11: Create a list to hold the non-ad segments
non_ad_segments = []

# Initialize the previous end time
prev_end_time = 0

# Step 12: Process each ad segment and extract non-ad segments
for segment in ad_segments:
    start_time = segment["start"] * 1000  # Convert to milliseconds
    end_time = segment["end"] * 1000  # Convert to milliseconds
    
    # Add the segment before the ad to the non_ad_segments list
    if prev_end_time < start_time:
        non_ad_segments.append(audio[prev_end_time:start_time])
    
    # Update the previous end time to the end of the current ad segment
    prev_end_time = end_time

# Add the final segment after the last ad
if prev_end_time < len(audio):
    non_ad_segments.append(audio[prev_end_time:])

# Step 13: Concatenate all non-ad segments
output_audio = sum(non_ad_segments)

# Step 14: Export the result to a new MP3 file
output_audio.export("output.mp3", format="mp3")

print("The ad segments have been removed, and the resulting audio is saved as 'output.mp3'.")