# Browser control · GhostOS 1.3

Choose **Chrome** or **Edge** in the AI gear beside Send. Browser DOM actions use Playwright over Chrome DevTools Protocol (CDP). With no endpoint configured,
GhostOS starts the installed browser directly with a dedicated GhostOS profile,
a random loopback debugging port and `--no-first-run`. Python, Node and a separate
Chromium download are not needed in the installer. Your ordinary browser profile
is untouched; sign in separately in the GhostOS profile if a task requires it.
Completed tabs remain open when the worker disconnects.

If browser policy, startup or CDP fails, the agent warns, offers **CDP setup help**
in its non-activating task panel, and continues using the visible mouse, current
accessibility tree and keyboard. You can ignore the setup offer. It does not
silently replay a possibly submitted form. The next observation determines a
safe next action. Native navigation focuses the browser and uses Ctrl+L with verified address-bar
ownership, enters the URL and checks the destination through UIA. It never types
a URL into an arbitrary webpage input. No Windows Search or shell string is used.

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


## Tabs and natural-language navigation

**Open Netflix in Chrome** resolves the explicit site name, finds and activates a
matching accessible native tab or CDP tab, or navigates to its URL. YouTube being
visible does not block this operation. **Open a new tab in Chrome** creates a real
tab and checks that the tab count increased. An explicit HTTP(S) domain works for
any website; a small packaged alias map supports Netflix, YouTube, Galaxus,
Google, Wikipedia and GitHub. Other site names need a URL or model resolution.

UIA reuse respects an existing ordinary Chrome/Edge profile. That profile stays
in native mode because CDP cannot safely attach to an ordinary profile that was
not launched with debugging. For precise DOM actions, use the managed GhostOS
profile or configure a loopback CDP endpoint; an explicitly configured endpoint
takes priority. CDP tab snapshots include IDs, titles and URLs. The planner can
use `browser_tabs` and `browser_switch_tab` before acting on a different tab.
UIA may be unavailable under browser policy; the agent tries another transport
and reports unverified outcomes rather than inventing success.
