"""Build-time voice provisioning. Never downloads at application runtime."""
from pathlib import Path
import hashlib
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'bae641dcb5a608cff81ccaf7ff018baaca1a33e1'
BASE = f'https://huggingface.co/rhasspy/piper-voices/resolve/{REVISION}/'
VOICE = 'en/en_US/ljspeech/medium/'
MODEL = 'en_US-ljspeech-medium.onnx'
MODEL_SHA256 = '6f52a751e2349abe7a76735eb09dc1875298c77ea2342ffd2fef79ff81b87f22'


def main():
    target = ROOT / 'assets' / 'voice'
    target.mkdir(parents=True, exist_ok=True)
    for remote, local in [(VOICE + MODEL, MODEL), (VOICE + MODEL + '.json', MODEL + '.json'),
                          (VOICE + 'MODEL_CARD', 'MODEL_CARD'), ('README.md', 'VOICE_REPOSITORY.md')]:
        path = target / local
        if not path.exists():
            temporary = path.with_suffix(path.suffix + '.download')
            with urllib.request.urlopen(BASE + remote, timeout=180) as response, temporary.open('wb') as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
            temporary.replace(path)
        if local == MODEL and hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
            path.unlink()
            raise RuntimeError('Bundled voice checksum does not match the pinned model')
    print('Pinned Piper voice verified')


if __name__ == '__main__':
    main()
