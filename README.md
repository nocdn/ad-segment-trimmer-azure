# ad-segment-trimmer

> self-hosted REST API (with frontend) to remove ads from audio/video files using OpenAI's Whisper and LLMs

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

### How does it work?

A transcript is made with an API from Fireworks AI, running Whisper (specifically Whisper-v3-large-turbo), an open-source ASR model, which returns an entire transcription, and also word level timestamps, then the entire transcription is sent to an LLM (Gemini 2.0 Flash) to extract the entire advertisement segments, then the start_time and end_time of each segment is used to create an FFmovie command to remove the segments from the original audio file, then return the cleaned audio file to the user.

### How much does it cost?

Whisper is billed at $0.0009 per audio minute (billed per second), and Gemini 2.0 Flash is billed at $0.40 per million output tokens ($0.0000004 per token), so for an hour long podcast, the process is billed at around 0.11 USD.

### How to use it?

1. Make sure you have an Gemini API key, as an environment variable called `GEMINI_API_KEY`.
2. Make sure you have a Fireworks AI API key, as an environment variable called `FIREWORKS_API_KEY`.
3. Install ffmpeg on the system you are running this on
4. Start a new virtual environment with Python 3.10 or higher
5. Install the requirements with `pip install -r requirements.txt` (or my preferred method, with uv: `uv pip install -r requirements.txt`)
6. Run the script with `python api.py` (or any port)

To test the API, you can use the following curl command:

```bash
curl -X POST http://127.0.0.1:7070/process \
  -F "file=@audio.mp3"
```

You should then see it return a summary of the transcript (the feature built in so far).
