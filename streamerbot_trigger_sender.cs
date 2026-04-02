// Streamer.bot C# Action — Dungeon Arcade Trigger Sender
// Add this as an Execute C# Code action in Streamer.bot
// Attach to: chat commands, hotkeys, timers, or channel point redemptions

using System;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;

public class CPHInline
{
    public bool Execute()
    {
        // --------------------------------------------------------
        // CONFIGURE THESE PER ACTION
        // --------------------------------------------------------

        // Type options: "chat_trigger" | "hotkey" | "timed" | "stt"
        string triggerType = "chat_trigger";

        // The text content — for chat triggers use the message,
        // for hotkeys describe what just happened in the game
        string triggerText = args.ContainsKey("rawInput")
            ? args["rawInput"].ToString()
            : args.ContainsKey("triggerText")
                ? args["triggerText"].ToString()
                : "Something happened in the stream.";

        // --------------------------------------------------------

        var payload = JsonConvert.SerializeObject(new {
            type = triggerType,
            text = triggerText
        });

        SendToOrchestrator(payload);
        return true;
    }

    private void SendToOrchestrator(string payload)
    {
        Task.Run(async () =>
        {
            using var client = new ClientWebSocket();
            var uri = new Uri("ws://localhost:8765");

            try
            {
                await client.ConnectAsync(uri, CancellationToken.None);
                var bytes = Encoding.UTF8.GetBytes(payload);
                await client.SendAsync(
                    new ArraySegment<byte>(bytes),
                    WebSocketMessageType.Text,
                    true,
                    CancellationToken.None
                );
                CPH.LogInfo($"[Dungeon Arcade] Sent trigger: {payload}");
            }
            catch (Exception ex)
            {
                CPH.LogError($"[Dungeon Arcade] Failed to send trigger: {ex.Message}");
            }
        }).Wait(2000); // 2 second timeout
    }
}
