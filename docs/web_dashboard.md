# Local web dashboard · GhostOS 1.2.1

Start it in desktop Settings, or launch `python main.py --desktop --web`. For a
server without the GhostOS desktop UI, use `python main.py --web`. By default the
server binds `0.0.0.0:8000`. It remains opt-in; opening the app alone does not start
a network listener. The displayed address is an active private IPv4 interface;
if several adapters exist, choose the PC's actual Wi-Fi address from `ipconfig`.

On the phone, open `http://<PC-Wi-Fi-IP>:8000`. Pair with the per-launch token from
Settings (or `%LOCALAPPDATA%\GhostOS\dashboard-token.txt` for source headless mode).
The token is held only in browser tab memory, never placed in a URL, JS source,
localStorage or server access logs. Restarting GhostOS rotates it.

The mobile page provides a goal form, live screenshot, concise progress/plan/action
feed, exact pending approvals and a Stop button. All clients share one active
worker and approval queue. Approvals use random one-time IDs; duplicate/expired
requests return 409. Slow WebSocket clients are disconnected instead of building
an unlimited screenshot queue. Frames replace previous frames; recent events are
bounded. No screenshot is sent before successful authentication.

## API

All API requests require `Authorization: Bearer TOKEN`. WebSockets authenticate
in their first message (`{"token":"TOKEN"}`) within five seconds. No incoming
WebSocket command execution is supported; mutations go through authenticated
HTTP routes.

| Route | Method | Body / result |
| --- | --- | --- |
| `/` | GET | Static pairing page; no token embedded |
| `/api/state` | GET | Running state, tier, pending approvals, recent logs |
| `/api/goals` | POST | `{"goal":"..."}`; starts a single bounded goal |
| `/api/approvals/{id}` | POST | `{"approved":true}` or `false` |
| `/api/stop` | POST | Stops the current worker and releases held input |
| `/ws` | WebSocket | Auth first, then live frames/events/pending state |

Host validation, same-origin checks, local/private client IP checks and token
comparison apply. CORS is not enabled. Forwarded headers are not trusted. The
server does not accept arbitrary recipe file paths or change permission tiers.
Use desktop Settings to raise or lower permissions while idle.

## Network setup

Keep this on a trusted private LAN. HTTP/WebSocket traffic is not encrypted; a
pairing token does not protect against a network observer. For encryption, deploy
your own properly configured TLS transport and review proxy trust settings.
Do not port-forward or expose this control plane to the public internet.

If Windows Firewall prompts, permit the app only on Private networks. No firewall
rule is created automatically. Guest Wi-Fi/client isolation can block phone-to-PC
connections; use the same normal private network. If port 8000 is occupied, change
`web_port` in the settings file while GhostOS is stopped. `web_host=127.0.0.1`
disables phone access while preserving local browser access. The stop hotkey
continues to work independently of the network.
