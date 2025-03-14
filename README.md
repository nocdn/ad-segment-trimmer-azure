# ad-segment-trimmer

> self-hosted REST API (with frontend) to remove ads from audio/video files using OpenAI's Whisper and LLMs

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

### How does it work?

A transcript is made with an API from Fireworks AI, running Whisper (specifically Whisper-v3-large-turbo), an open-source ASR model, which returns an entire transcription, and also word level timestamps, then the entire transcription is sent to an LLM (Gemini 2.0 Flash) to extract the entire advertisement segments, then the start_time and end_time of each segment is used to create an FFmovie command to remove the segments from the original audio file, then return the cleaned audio file to the user.

### How much does it cost?

Whisper is billed at $0.0009 per audio minute (billed per second), and Gemini 2.0 Flash is billed at $0.40 per million output tokens ($0.0000004 per token), so for an hour long podcast, the process is billed at around 0.11 USD.

### Usage (with Docker)

1. Make sure you have an Gemini API key, as an environment variable called `GEMINI_API_KEY` in the `.env` file.
2. Make sure you have a Fireworks AI API key, as an environment variable called `FIREWORKS_API_KEY` in the `.env` file.
3. Set any rate limits you want in the `.env` file (optional).
4. Build the and run the Docker image:

```bash
docker compose up -d --build
```

(the `-d` flag runs the container in detached mode, and the `--build` flag rebuilds the image if there are any changes)

There now should be a frontend running at port `6030`, and the API running at port `7070`.

To access the API, you can use the following curl command:

```bash
curl -F "file=@audio.mp3" -OJ http://localhost:7070/process
```

(replace `audio.mp3` with the path to your audio file, the -OJ flag will save the file with the returned name with the \_edited suffix)
