"""Frozen bootstrap catches missing/broken application imports before hiding failures."""
import multiprocessing as mp


def start():
    from main import main
    return main()


if __name__ == '__main__':
    mp.freeze_support()
    from agent.startup import guarded_main
    raise SystemExit(guarded_main(start))
