"""Finite, auditable navigation fallbacks. No replay of submissions or scripts."""
from dataclasses import dataclass
from agent.models import Action
from agent.windows_apps import requested_app

@dataclass(frozen=True)
class RecoveryStep:
    label: str
    actions: tuple[Action, ...]

class Recovery:
    def __init__(self, goal, game_mode=False):
        self.app = None if game_mode else requested_app(goal)
        self.game_mode,self.game_recovery_added = game_mode,False
        self.history = []
        self.position = 0
        self.steps = []
        if self.app:
            for strategy in ('focus', 'launch'):
                self.steps.append(RecoveryStep(f'{strategy.title()} {self.app}',
                    (Action(kind='ensure_app', args={'name': self.app, 'strategy': strategy}),)))
        if not game_mode:
            self.steps.append(RecoveryStep('Restore the last external window', (Action(kind='focus'),)))
        self.steps.append(RecoveryStep('Take a fresh observation and reassess the goal',
                                       (Action(kind='wait', args={'seconds': 0.4}),)))

    @property
    def exhausted(self):
        return self.position >= len(self.steps)

    def attempt(self, controller, emit, reason):
        if self.game_mode and getattr(controller,'game',None) is not None and not self.game_recovery_added:
            self.steps.insert(self.position,RecoveryStep('Restore the pinned game window',(Action(kind='focus'),)))
            self.game_recovery_added = True
        if self.exhausted:
            return False
        step = self.steps[self.position]
        self.position += 1  # Each fallback is attempted at most once, including failures.
        emit('RECOVERY', message=f'{step.label}. {str(reason)[:240]}', attempt=self.position, total=len(self.steps))
        try:
            for action in step.actions:
                emit('ACTION', action=action.model_dump(), recovery=True)
                result = controller.execute(action)
                emit('RESULT', message=str(result)[:1000])
            outcome = f'{step.label}: {str(result)[:400]}'
            success = True
        except (InterruptedError, PermissionError):
            raise
        except Exception as exc:
            outcome = f'{step.label}: {type(exc).__name__}: {str(exc)[:400]}'
            emit('RECOVERY_RESULT', message=outcome)
            success = False
        self.history.append(outcome)
        self.history = self.history[-12:]
        return success

    def context(self):
        return '\nRecent recovery outcomes:\n' + '\n'.join(self.history)[-3000:]
