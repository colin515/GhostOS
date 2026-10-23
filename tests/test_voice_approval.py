from types import SimpleNamespace
import pytest
from agent.voice_approval import approval_answer, VoiceApproval
from agent.voice import SpeechTicket


@pytest.mark.parametrize('text,expected', [('Yes.', True), ('Approve!', True), ('No', False),
    ('Do not approve', None), ('yes but no', None), ('', None), ('yesterday', None)])
def test_only_explicit_voice_answers_authorize(text, expected):
    assert approval_answer(text) is expected


def test_stale_voice_request_never_records_or_approves():
    ticket = SpeechTicket()
    ticket.done.set()
    runtime = SimpleNamespace(emergency_stopped=False, approvals=SimpleNamespace(pending=lambda: []),
        speech=SimpleNamespace(say=lambda *a, **kw: ticket),
        bus=SimpleNamespace(publish=lambda *a, **kw: None))
    listener = VoiceApproval(runtime, 'old')
    listener.run()  # No microphone import or authorization when the request has expired.
    assert not listener.active()
