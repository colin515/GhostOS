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
        self.history = []
        self.position = 0
        self.steps = []
        if self.app:
            for strategy in ('focus', 'launch', 'search'):
                self.steps.append(RecoveryStep(f'{strategy.title()} {self.app}',
                    (Action(kind='ensure_app', args={'name': self.app, 'strategy': strategy}),)))
        if not game_mode:
            self.steps += [RecoveryStep('Switch to another window', (Action(kind='hotkey', args={'keys': ['alt', 'tab']}),)),
                           RecoveryStep('Refresh focus and try keyboard navigation',
                                        (Action(kind='focus'), Action(kind='hotkey', args={'keys': ['tab']})))]
        self.steps.append(RecoveryStep('Take a fresh observation and reassess the goal',
                                       (Action(kind='wait', args={'seconds': 0.4}),)))

    @property
    def exhausted(self):
        return self.position >= len(self.steps)

    def attempt(self, controller, emit, reason):
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
        return success

    def context(self):
        return '\nRecovery attempts (do not repeat):\n' + '\n'.join(self.history)[-3000:]
