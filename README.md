# ad-segment-trimmer-azure

> REST API (with frontend) to remove ad segments from audio/video files using Azure hosted LLMs and Text-To-Speech (TTS).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

### How does it work?

A transcript is made with azure AI Speech, which returns an entire transcription, and also word level timestamps, then the entire transcription is sent to an LLM from Azure AI Foundry to extract the entire advertisement segments, then the start_time and end_time of each segment is used alongside Azure Media Services to remove those segments from the original audio file, then return the cleaned audio file to the user.

### License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
