# Browser control · GhostOS 1.2

Choose **Chrome** or **Edge** in the AI gear beside Send. Browser actions first
use Playwright over Chrome DevTools Protocol (CDP). With no endpoint configured,
GhostOS starts the installed browser directly with a dedicated GhostOS profile,
a random loopback debugging port and `--no-first-run`. Python, Node and a separate
Chromium download are not needed in the installer. Your ordinary browser profile
is untouched; sign in separately in the GhostOS profile if a task requires it.
Completed tabs remain open when the worker disconnects.

If browser policy, startup or CDP fails, the agent warns, offers **CDP setup help**
in its non-activating task panel, and continues using the visible mouse, current
accessibility tree and keyboard. You can ignore the setup offer. It does not
silently replay a possibly submitted form. The next observation determines a
safe next action. Native navigation opens URLs through the browser executable,
without Windows Search or a shell command string.

For an existing dedicated debugging profile, close that profile's browser first,
then run (adjust the Chrome executable path if necessary):

```powershell
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 "--user-data-dir=$env:LOCALAPPDATA\GhostOS\manual-cdp"
```

Set **Browser CDP** to `http://127.0.0.1:9222`. Never expose this port to Wi-Fi.
Chrome 136+ requires a non-default user data directory for remote debugging:
https://developer.chrome.com/blog/remote-debugging-port . GhostOS supplies one
for its automatic connection. Organization policies can still disable debugging;
use the native fallback when that policy applies.
