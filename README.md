# ad-segment-trimmer-azure

> REST API (with frontend) to remove ad segments from audio/video files using Azure hosted LLMs and Text-To-Speech (TTS).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

### How does it work?

A transcript is made with azure AI Speech, which returns an entire transcription, and also word level timestamps, then the entire transcription is sent to an LLM from Azure AI Foundry to extract the entire advertisement segments, then the start_time and end_time of each segment is used alongside Azure Media Services to remove those segments from the original audio file, then return the cleaned audio file to the user.

#### How to run for development

1. Clone the repository

```bash
git clone https://github.com/nocdn/ad-segment-trimmer-azure.git
```

2. Copy the `.env.example` file to `.env` and fill in the required values

```bash
cp .env.example .env
```

3. To run the backend, navigate to the `backend` directory and run the following commands:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 api.py
```

(the api should now be running on `localhost:7070`)

To use the API you can use the following curl command:

```bash
curl -F "file=@audio.mp3" -OJ http://localhost:7070/process
```

(the -OJ flag will save the file with the name returned by the API, in this case, with a \_edited suffix)

4. To run the frontend, navigate to the `frontend` directory and run the following commands:

```bash
cd frontend
npm install
npm run dev --open
```

### License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
