"""Official pretrained ViNT/NoMaD inference, without ROS or training.

Robot frame: +x forward, +y left; xy are cumulative positions relative to
current camera. Network xy are dimensionless waypoint-spacing units. As in
upstream deployment/navigate.py, multiply by max_v / frame_rate for meters.
Distance is learned temporal distance, not meters and not a reach guarantee.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def prepare_history(paths, count):
    if not paths:
        raise ValueError('observation_paths must contain at least one RGB image')
    return ([paths[0]] * max(0, count - len(paths)) + list(paths))[-count:]


def decode_nomad_actions(raw):
    # Official train_utils.get_action: [-1,1] deltas -> dataset ranges -> cumsum.
    raw = np.asarray(raw)
    lo, hi = np.array([-2.5, -4.]), np.array([5., 4.])
    return np.cumsum((raw + 1) / 2 * (hi - lo) + lo, axis=1)


def transform_images(paths, image_size):
    import torch
    from PIL import Image
    from torchvision.transforms import functional as TF
    images = []
    for path in paths:
        with Image.open(path) as source:
            image = source.convert('RGB').resize(tuple(image_size))
            tensor = TF.to_tensor(image)
            images.append(TF.normalize(tensor, [.485, .456, .406], [.229, .224, .225]))
    return torch.cat(images, dim=0).unsqueeze(0)


class NavigationPolicies:
    """Two distinct public navigation policies, both loaded strictly from weights."""
    def __init__(self, weights_dir=None, device='cuda:1', models=('vint', 'nomad')):
        import torch
        import yaml
        self.device = torch.device(device)
        self.weights_dir = Path(weights_dir or ROOT / 'assets/navigation')
        for name in models:
            if name not in ('vint', 'nomad'):
                raise ValueError(f'Unknown navigation model: {name}')
            if not (self.weights_dir / f'{name}.pth').is_file():
                raise FileNotFoundError(self.weights_dir / f'{name}.pth')
        for directory in (ROOT / 'vendor/visualnav-transformer/train', ROOT / 'vendor/diffusion_policy'):
            sys.path.insert(0, str(directory))
        self.models, self.configs, self.metadata = {}, {}, {}
        for name in models:
            config = yaml.safe_load((ROOT / f'vendor/visualnav-transformer/train/config/{name}.yaml').read_text())
            model = self._build(name, config)
            # Official ViNT checkpoint serializes a full nn.Module. Trusted public
            # upstream checkpoint only; newer PyTorch defaults to weights_only=True.
            checkpoint = torch.load(self.weights_dir / f'{name}.pth', map_location='cpu', weights_only=False)
            if name == 'vint':
                loaded = checkpoint['model']
                state = (loaded.module if hasattr(loaded, 'module') else loaded).state_dict()
            else:
                state = checkpoint
            model.load_state_dict(state, strict=True)
            model.to(self.device).eval()
            self.models[name], self.configs[name] = model, config
            self.metadata[name] = {'checkpoint_sha256': hashlib.sha256((self.weights_dir / f'{name}.pth').read_bytes()).hexdigest(), 'parameters': sum(p.numel() for p in model.parameters()), 'strict_weights': True}
        if 'nomad' in models:
            from diffusers.schedulers.scheduling_ddpm import DDPMScheduler
            self.scheduler = DDPMScheduler(num_train_timesteps=self.configs['nomad']['num_diffusion_iters'], beta_schedule='squaredcos_cap_v2', clip_sample=True, prediction_type='epsilon')

    @staticmethod
    def _build(name, c):
        if name == 'vint':
            from vint_train.models.vint.vint import ViNT
            return ViNT(**{key: c[key] for key in ('context_size', 'len_traj_pred', 'learn_angle', 'obs_encoder', 'obs_encoding_size', 'late_fusion', 'mha_num_attention_heads', 'mha_num_attention_layers', 'mha_ff_dim_factor')})
        from vint_train.models.nomad.nomad import NoMaD, DenseNetwork
        from vint_train.models.nomad.nomad_vint import NoMaD_ViNT, replace_bn_with_gn
        from diffusion_policy.model.diffusion.conditional_unet1d import ConditionalUnet1D
        vision = replace_bn_with_gn(NoMaD_ViNT(obs_encoding_size=c['encoding_size'], context_size=c['context_size'], mha_num_attention_heads=c['mha_num_attention_heads'], mha_num_attention_layers=c['mha_num_attention_layers'], mha_ff_dim_factor=c['mha_ff_dim_factor']))
        return NoMaD(vision, ConditionalUnet1D(input_dim=2, global_cond_dim=c['encoding_size'], down_dims=c['down_dims'], cond_predict_scale=c['cond_predict_scale']), DenseNetwork(c['encoding_size']))

    def predict(self, request):
        import torch
        name = request['model']
        if name not in self.models:
            raise ValueError(f'Model not loaded: {name}')
        c, model = self.configs[name], self.models[name]
        paths = prepare_history(request['observation_paths'], c['context_size'] + 1)
        max_v, frame_rate = float(request.get('max_v', .2)), float(request.get('frame_rate', 4.))
        if not np.isfinite([max_v, frame_rate]).all() or max_v <= 0 or frame_rate <= 0:
            raise ValueError('max_v and frame_rate must be finite and positive')
        start = time.perf_counter()
        obs = transform_images(paths, c['image_size']).to(self.device)
        goal = transform_images([request['goal_path']], c['image_size']).to(self.device)
        with torch.inference_mode():
            if name == 'vint':
                distances, actions = model(obs, goal)
                actions = actions[0, :, :2].cpu().numpy()
            else:
                cond = model('vision_encoder', obs_img=obs, goal_img=goal, input_goal_mask=torch.zeros(1, dtype=torch.long, device=self.device))
                distances = model('dist_pred_net', obsgoal_cond=cond)
                generator = torch.Generator(device=self.device).manual_seed(int(request.get('seed', 0)))
                sample = torch.randn((1, c['len_traj_pred'], 2), device=self.device, generator=generator)
                self.scheduler.set_timesteps(c['num_diffusion_iters'])
                for k in self.scheduler.timesteps:
                    noise = model('noise_pred_net', sample=sample, timestep=k, global_cond=cond)
                    sample = self.scheduler.step(noise, k, sample, generator=generator).prev_sample
                actions = decode_nomad_actions(sample.cpu().numpy())[0]
        distance = float(distances.flatten()[0].cpu())
        if not np.isfinite(actions).all() or not np.isfinite(distance):
            raise RuntimeError('Navigation model produced non-finite output')
        return {'model': name, 'waypoints': (actions * max_v / frame_rate).tolist(), 'normalized_waypoints': actions.tolist(), 'distance': distance, 'distance_units': 'learned_temporal_steps', 'waypoint_units': 'meters', 'coordinate_frame': 'robot_x_forward_y_left', 'meters_per_waypoint_unit': max_v / frame_rate, 'latency_ms': (time.perf_counter()-start)*1000, 'history_frames': len(paths), 'device': str(self.device), **self.metadata[name]}
