"""Generation schemas encode the same action invariants as runtime validation."""
from __future__ import annotations
import json
import re
from pydantic import ValidationError
from agent.models import ARG_TYPES, Decision


class ModelReplyError(ValueError):
    """Ollama answered, but no executable decision could be validated."""


def decision_schema(action_required=False):
    actions = {'oneOf': [dict(type='object', additionalProperties=False,
        properties={'kind': {'type': 'string', 'const': name}, 'args': model.model_json_schema()},
        required=['kind', 'args']) for name, model in ARG_TYPES.items()]}
    fields = {'status': {'type': 'string', 'const': 'CONTINUE'},
              'summary': {'type': 'string', 'maxLength': 1500},
              'plan': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 5},
              'action': actions}
    continuing = dict(type='object', additionalProperties=False, properties=fields,
                      required=['status', 'summary', 'plan', 'action'])
    if action_required:
        return continuing
    terminal = dict(type='object', additionalProperties=False,
        properties={**fields, 'status': {'type': 'string', 'enum': ['GOAL_SATISFIED', 'GOAL_IMPOSSIBLE']},
                    'action': {'type': 'null'}}, required=['status', 'summary', 'plan', 'action'])
    return {'oneOf': [continuing, terminal]}


class WireDecision(Decision):
    @classmethod
    def model_json_schema(cls, **kwargs):
        return decision_schema()


class ActionDecision(WireDecision):
    @classmethod
    def model_json_schema(cls, **kwargs):
        return decision_schema(action_required=True)


def parse_decision(content, action_required=False):
    # A single fenced JSON object is harmless formatting; never infer an action from prose.
    content = (content or '').strip()
    fenced = re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
    if fenced:
        content = fenced.group(1)
    try:
        decision = Decision.model_validate_json(content)
        if action_required and decision.status != 'CONTINUE':
            raise ModelReplyError('The current step is incomplete; CONTINUE with one action is required.')
        return decision
    except ValidationError as exc:
        try:
            data = json.loads(content)
        except (ValueError, TypeError):
            data = None
        if isinstance(data, dict) and data.get('status') == 'CONTINUE' and not data.get('action'):
            raise ModelReplyError('CONTINUE is missing action. Supply {"kind":"…","args":{…}}; a plan alone cannot execute.') from None
        errors = exc.errors(include_input=False, include_url=False)
        detail = '; '.join('.'.join(map(str, e['loc'])) + ': ' + e['msg'] for e in errors[:3])
        raise ModelReplyError('Invalid decision: ' + detail[:600]) from None


def repair_message(error):
    return ('The previous reply was not executed. Correct its JSON using the supplied schema. '
            'Keep the original goal and current screen. CONTINUE requires exactly one typed action; '
            'terminal states require action:null. Do not repeat an uncertain write. '
            'No prose outside JSON. Validation: ' + str(error)[:650])


def thinking_option(metadata):
    """Do not spend the short action budget on optional thinking tokens."""
    values = (metadata.get('thinking') or {}).get('values', [])
    if False in values or 'thinking' in (metadata.get('capabilities') or []):
        return {'think': False}
    return {}
