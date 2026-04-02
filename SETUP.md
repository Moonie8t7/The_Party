# The Dungeon Arcade - Party Orchestrator Setup

## Folder Structure

```
dungeon_arcade/
├── orchestrator.py              # Main orchestrator
├── requirements.txt             # Python dependencies
├── streamerbot_trigger_sender.cs  # Streamer.bot action
├── prompts/
│   ├── clauven.txt
│   ├── geptima.txt
│   ├── gemaux.txt
│   ├── grokthar.txt
│   └── deepwilla.txt
```

## Step 1 - Create the prompts folder

Create a `prompts/` folder next to `orchestrator.py`.
Save each character's system prompt as a `.txt` file with the filename matching the character name exactly.

## Step 2 - Install dependencies

```bash
pip install -r requirements.txt
```

## Step 3 - Add your API keys

Open `orchestrator.py` and fill in the `CONFIG` block at the top:

```python
CONFIG = {
    "anthropic_api_key":  "sk-ant-...",
    "openai_api_key":     "sk-...",
    "gemini_api_key":     "AIza...",
    "grok_api_key":       "xai-...",
    "deepseek_api_key":   "sk-...",
    ...
}
```

## Step 4 - Run the orchestrator

```bash
python orchestrator.py
```

You should see:
```
[Server] Starting Dungeon Arcade Orchestrator...
[Server] Listening on ws://localhost:8765
```

Keep this running in the background while streaming.

## Step 5 - Set up Streamer.bot

1. In Streamer.bot, create a new Action
2. Add an "Execute C# Code" sub-action
3. Paste the contents of `streamerbot_trigger_sender.cs`
4. Attach this action to any trigger:
   - Chat command (e.g. `!party`)
   - Hotkey
   - Channel point redemption
   - Timer

### Sending custom game event text

For hotkeys tied to game events, set `triggerText` manually in the C# action:

```csharp
string triggerText = "DM Moonie just died to a zombie horde in 7 Days to Die.";
```

### Passing chat message content

For chat-based triggers, `rawInput` will automatically capture the message:

```csharp
string triggerText = args["rawInput"].ToString();
```

## Step 6 - Test without Streamer.bot

You can test the orchestrator directly by sending a WebSocket message.
Use a tool like `wscat`:

```bash
npm install -g wscat
wscat -c ws://localhost:8765
> {"type": "hotkey", "text": "DM Moonie just died to a zombie horde."}
```

## Trigger Types

| Type | Source | When to use |
|------|--------|-------------|
| `hotkey` | Streamer.bot hotkey | Manual game moments |
| `chat_trigger` | Chat command or keyword | Viewer interactions |
| `timed` | Streamer.bot timer | Regular commentary intervals |
| `stt` | Whisper STT output | Reacting to what you say on mic |

## Routing Rules

The orchestrator uses keyword matching first, then falls back to a fast LLM call.
To add new rules, edit the `ROUTING_RULES` list in `orchestrator.py`:

```python
{
    "keywords": ["your", "keywords", "here"],
    "characters": ["character1", "character2"],
},
```

## Adding ElevenLabs TTS

When ready, replace the `speak()` function in `orchestrator.py`:

```python
async def speak(display_name: str, text: str, voice_id: str):
    from elevenlabs.client import ElevenLabs
    client = ElevenLabs(api_key="YOUR_ELEVENLABS_KEY")
    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id="eleven_turbo_v2",
    )
    # Play audio - use pygame or sounddevice
    play(audio)
```

## OBS Overlay

The orchestrator sends WebSocket messages to the OBS browser source overlay:

```json
{"event": "speaking_start", "character": "grokthar"}
{"event": "speaking_end",   "character": "grokthar"}
{"event": "idle",           "character": null}
```

The overlay listens for these and animates the correct character sprite.
Overlay build is a separate step.
