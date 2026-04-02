# 🗡️ The Party - Setup Guide

## 1. Environment Requirements
- **Python**: 3.10 or higher
- **OBS Studio**: With WebSockets enabled (standard in v28+)
- **ElevenLabs**: An active API Key for high-quality TTS

## 2. Installation

```bash
git clone https://github.com/Moonie8t7/The_Party.git
cd The_Party
pip install -r requirements.txt
```

## 3. Configuration

### .env Setup
Copy `.env.example` to `.env` and configure your credentials:

```ini
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
GROK_API_KEY=...
DEEPSEEK_API_KEY=...
ELEVENLABS_API_KEY=...

# OBS WebSocket (Tools -> WebSocket Server Settings)
VISION_OBS_HOST=localhost
VISION_OBS_PORT=4455
VISION_OBS_PASSWORD=your_password
```

### Character Voices
Find your preferred Voice IDs in the ElevenLabs Library and add them to your `.env`:
- `VOICE_CLAUVEN`
- `VOICE_GEPTIMA`
- `VOICE_GEMAUX`
- `VOICE_GROKHTAR`
- `VOICE_DEEPWILLA`

## 4. OBS Integration

### The Visual Overlay
1. Add a new **Browser Source** in OBS.
2. Set the URL to the local path of `overlay/overlay.html`.
3. Set Dimensions to **1920 x 1080**.
4. Enable "Shutdown source when not visible" and "Refresh browser when scene becomes active".

### Scene Awareness
The orchestrator automatically detects your active scene name. To ensure the party reacts correctly, name your OBS scenes as follows (or similar):
- `Startup` (Starting Soon)
- `Gaming` (Active Play)
- `BRB` (Break)
- `Chat` (Just Chatting)
- `Post Game` (Stream Ending)

## 5. Launching the System

```bash
python -m party.main
```

You should see the system initialize, populate the Twitch context, and start listening on:
- **ws://localhost:8765**: Orchestrator (Connected to Streamer.bot)
- **ws://localhost:8766**: Overlay (Connected to OBS Browser Source)

## 6. Streamer.bot Wiring

1. Create an Action in Streamer.bot.
2. Add an **Execute C# Code** sub-action.
3. Paste the contents of `streamerbot_trigger_sender.cs` from the root directory.
4. Set the `triggerText` in the code or via global variables to initiate a reaction.

---
*For development details, see [README.md](README.md).*
