# Browser and desktop click grounding

## Failure reproduced from the user's task log

The reported request opened YouTube in a managed CDP tab, then attempted
`click {"x":538,"y":769,"coordinate_space":"screenshot"}` repeatedly.
GhostOS rejected it as `ValueError: Coordinate outside latest screenshot`.
Later, `click (378,239)` became a Win32 physical click at `(945,598)`
even though the browser's page was already managed by CDP.
A successful Windows pointer press did not verify the requested video click.

These are evidence of *incompatible screenshot/input coordinate spaces* and
a lack of element-level target grounding, not evidence that the model
simply needs more thinking tokens.

The same log shows YouTube's German home page stating its watch history is
disabled, alongside a cookie-consent dialog. In that state a first video
may not be available at all. GhostOS must distinguish an absent target from
a coordinate problem and must not claim a video was selected.

## New managed-browser path

1. Capture `page.screenshot(scale="css",full_page=False)`.
2. Resize for inference while retaining the original CSS viewport size.
3. Extract visible actionable DOM nodes with names, element href and page-relative
   coordinates; prioritize video links and expose numbered ephemeral IDs.
4. Use `browser_click_target(target_id=N)` for precise, identity-checked Playwright
   locator clicks, or `browser_click(selector=...)` for a unique accessible
   selector. Both use Playwright's actionability checks.
5. If the model selects a pixel, convert only from resized screenshot pixels
   to CSS viewport pixels and call `page.mouse.click()`. Refuse points outside
   the capture, points without a clickable element, or invalid browser buttons.
6. Observe the browser again; dispatching an input is not evidence that the
   requested result happened.

The old native Win32 mouse driver and UI Automation hit tests remain active for
non-browser desktop apps. The systems are kept separate, avoiding DPI
virtualization, OS capture origin and Chromium viewport offsets.

## Open-source references evaluated

- [Playwright Python](https://github.com/microsoft/playwright-python) —
  existing GhostOS dependency, supports browser viewport screenshot with
  `scale="css"`, semantic DOM locator clicks and actionability checks.
  **Adopted directly**, no extra runtime/model download.
- [browser-use](https://github.com/browser-use/browser-use) — uses
  browser accessibility/DOM inspection and viewport-grounded clicking with
  post-action verification. The numbered-target design follows this pattern
  without vendoring another agent framework.
- [Microsoft UFO](https://github.com/microsoft/UFO) — Windows UIA/Win32
  plus API-backed desktop interactions, consistent with GhostOS's native path.
  Too broad to replace the existing Windows action safety boundary in this fix.
- [pywinauto](https://github.com/pywinauto/pywinauto) — established Win32/UIA
  automation library, useful for later native-app enhancements; a new
  dependency cannot fix browser CSS viewport coordinate mismatch.
- [Microsoft OmniParser](https://github.com/microsoft/OmniParser) —
  screenshot-based interactable-region detection. It requires extra models and
  does not eliminate the need for correct screenshot-to-input transforms,
  so not introduced into this lightweight local build.

## Regression checks

`tests/test_browser_viewport.py` verifies CSS viewport capture,
resizing, click routing, out-of-bounds failures, element hit tests,
revalidation of DOM link identity, and strict separation from the Windows
mouse driver. The disposable local `--browser-smoke-test` now opens a
synthetic first-video link using a live CDP DOM target.

## Limits

CDP cannot control arbitrary tabs from Chrome's normal profile without its
debugging connection; existing personal tabs still use native controls.
Browser consent and authentication prompts may block the requested target.
Native games and non-accessible canvas controls may still need different
visual grounding. Automated tests cannot establish real-world operation on
the user's monitor configuration; validate with the installed Windows build.
