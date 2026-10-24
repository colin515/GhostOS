# Local model setup and multi-step control · 1.4.0

For an 8 GB GPU, update [Ollama for Windows](https://ollama.com/download/windows),
then use the AI gear beside Send → **Check / upgrade local model and voice**.
Select `qwen3.5:4b`, press **Download selected model**, then **Save and continue**.
`qwen3-vl:4b` is a smaller vision/tool alternative. Existing model choices are
preserved by app updates; installing GhostOS does not silently replace them or
bundle several GB of model weights.

Save runs the selected GhostOS planner against a synthetic test image and asks
for an inert wait action. The response must pass the same action validation used
at runtime. No desktop is captured, and no tool is executed. The dialog also has
**Verify agent model** and **Benchmark selected model** buttons. Verification
reports observed model VRAM use when Ollama supplies it. A running Ollama window
alone does not prove a model is installed, vision capable, GPU accelerated, or
able to follow the action protocol.

The 4B recommendation leaves headroom for Windows, the vision projector and
context on 8 GB cards. It is a fit estimate, not a measured speed or accuracy
guarantee for your PC. Check actual offload with the benchmark and `ollama ps`.
The app requests optional thinking to be disabled so it does not consume the
short action-output budget. No private reasoning is shown.

Explicit sequential clauses are kept as pending steps. The original request and
completed steps remain in context; only the active step can finish. Opening
YouTube does not complete “play the current video.” CDP playback checks the media
state and advancing playback time. Normal YouTube control reads the accessible
Play/Pause button and uses actual mouse input when needed. Unsupported/localized
controls, consent, login, ads or buffering require observation and further action.
The agent rejects a model's playback success claim when player state disagrees.

Structured generation now requires a typed action for `CONTINUE` and `null` for
terminal states, including the arguments for each action kind. A malformed reply
is never executed. GhostOS requests a corrected reply once, preserving the goal
and single screenshot; persistent errors return to the cancellable observation
loop with a short diagnostic. Large UI trees and older outcomes are trimmed
before they crowd the goal and latest result out of the context window.

Runtime permissions apply to all steps. Strict mode confirms media controls;
Balanced mode permits the bounded Play/Pause/state actions. Forms and arbitrary
scripts retain their existing approval rules. Step/runtime limits still default
to unlimited. The desktop reopens only after the entire run has ended.

Model capabilities and download sizes are published by
[Ollama Qwen3.5](https://ollama.com/library/qwen3.5:4b) and
[Ollama Qwen3-VL](https://ollama.com/library/qwen3-vl:4b).
See Ollama's [structured output](https://docs.ollama.com/capabilities/structured-outputs)
and [thinking controls](https://docs.ollama.com/capabilities/thinking) documentation.

Automated tests use loopback model fixtures and local silent media. A separate
release job also runs real local `qwen3.5:4b` weights through both planner protocols
on CPU and asks the SDK planner to choose the named Play accessibility target in
a synthetic image. Its model digest and results accompany the release. These
checks validate those specific tasks, not general reasoning or speed on your GPU.
The AI gear includes an inference timeout (90 seconds by default); raise it for
slow CPU offload while testing. The on-device verification and benchmark test
your actual Ollama installation. Arbitrary multi-step tasks still depend on
model quality and observable evidence.
