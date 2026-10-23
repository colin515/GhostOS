"""Opt-in, request-scoped voice approval. Never listen during TTS playback."""
import re
import threading
import time


def approval_answer(text):
    cleaned = re.sub(r'[^a-z ]', '', text.lower()).strip()
    if cleaned in ('yes', 'approve', 'yes approve'):
        return True
    if cleaned in ('no', 'decline', 'deny'):
        return False
    return None


class VoiceApproval:
    def __init__(self, runtime, request_id):
        self.runtime, self.request_id = runtime, request_id
        self.cancel = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name='GhostOS-voice-approval')

    def start(self):
        self.thread.start()

    def active(self):
        return not self.cancel.is_set() and not self.runtime.emergency_stopped and any(
            r['id'] == self.request_id for r in self.runtime.approvals.pending())

    def run(self):
        try:
            ticket = self.runtime.speech.say('I need your permission for the action shown.', priority=True)
            while not ticket.done.wait(0.05):
                if not self.active():
                    return
            if ticket.cancelled or not self.active() or self.cancel.wait(0.6):
                return
            from agent.voice import record_and_transcribe
            if not self.active():
                return
            self.runtime.bus.publish('VOICE_APPROVAL', request_id=self.request_id, message='Listening: say Yes or Approve, or No to decline.')
            text = record_and_transcribe(self.runtime.settings, progress=lambda value: None,
                level=lambda value: self.runtime.bus.publish('AUDIO_LEVEL', level=value), cancel=self.cancel)
            answer = approval_answer(text)
            if answer is not None and self.active():
                self.runtime.approve(self.request_id, answer, source='voice')
            elif self.active():
                self.runtime.bus.publish('WARNING', message='Voice answer was unclear. Use the approval buttons or retry the task.')
        except InterruptedError:
            pass
        except Exception as exc:
            if self.active():
                self.runtime.bus.publish('WARNING', message=f'Voice approval unavailable; use buttons: {exc}')
        finally:
            self.runtime.bus.publish('AUDIO_LEVEL', level=0.0)
