# GhostOS 1.3.1

The desktop chat now reopens after a task finishes, is stopped, or encounters a
terminal error. The composer receives focus, and Send and Speak are available
for your next command. Microphone recording still starts only when you press Speak.

The chat remains hidden during execution. Restoration happens only after worker
cleanup and is skipped if another run is active or the application is closing.
The existing installer updates an installed copy in place.

Model inference and agent execution logic are unchanged in this release.
