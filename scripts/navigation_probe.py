"""Run both public models on actual supplied camera images and save evidence."""
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from print_factory.navigation_policy import NavigationPolicies


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--observation', required=True, nargs='+')
    parser.add_argument('--goal', required=True)
    parser.add_argument('--device', default='cuda:1')
    parser.add_argument('--output', default=str(ROOT / 'output/jeff_factory/navigation_probe.json'))
    args = parser.parse_args()
    started = time.perf_counter()
    policies = NavigationPolicies(device=args.device)
    results = []
    for model in ('vint', 'nomad'):
        request = dict(model=model, observation_paths=args.observation, goal_path=args.goal, seed=0)
        policies.predict(request)  # warmup
        result = policies.predict(request)
        assert np.isfinite(result['waypoints']).all()
        assert len(result['waypoints']) == (5 if model == 'vint' else 8)
        results.append(result)
    import torch
    output = dict(observation_paths=args.observation, goal_path=args.goal, results=results, total_seconds=time.perf_counter()-started, gpu_name=torch.cuda.get_device_name(torch.device(args.device)), torch=torch.__version__, numpy=np.__version__, transfer_success='not assessed; inference probe only')
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2), encoding='utf8')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
