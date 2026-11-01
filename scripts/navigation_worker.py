"""JSON-lines navigation process. Stdout is protocol only; diagnostics use stderr."""
import argparse
import contextlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from print_factory.navigation_policy import NavigationPolicies


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='cuda:1')
    parser.add_argument('--weights-dir', default=str(ROOT / 'assets/navigation'))
    parser.add_argument('--models', nargs='+', default=['vint', 'nomad'])
    args = parser.parse_args()
    with contextlib.redirect_stdout(sys.stderr):
        policies = NavigationPolicies(args.weights_dir, args.device, tuple(args.models))
    print(json.dumps({'ready': True, 'models': policies.metadata, 'device': args.device}), flush=True)
    for line in sys.stdin:
        request = {}
        try:
            request = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                result = policies.predict(request)
            if 'id' in request:
                result['id'] = request['id']
        except Exception as exc:
            result = {'error': f'{type(exc).__name__}: {exc}', 'id': request.get('id') if isinstance(request, dict) else None}
        print(json.dumps(result, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
