import numpy as np
import pytest
from PIL import Image


def test_navigation_history_uses_latest_frames_and_pads_oldest():
    from print_factory.navigation_policy import prepare_history
    assert prepare_history(['a', 'b'], 4) == ['a', 'a', 'a', 'b']
    assert prepare_history(['a', 'b', 'c'], 2) == ['b', 'c']
    with pytest.raises(ValueError, match='observation'):
        prepare_history([], 4)


def test_nomad_actions_undo_training_delta_normalization():
    from print_factory.navigation_policy import decode_nomad_actions
    raw = np.array([[[-1., 0.], [1., 1.]]])
    np.testing.assert_allclose(decode_nomad_actions(raw), [[[-2.5, 0.], [2.5, 4.]]])


def test_navigation_preprocessing_matches_official_rgb_channel_order(tmp_path):
    from print_factory.navigation_policy import transform_images
    path = tmp_path / 'red.png'
    Image.new('RGB', (20, 10), (255, 0, 0)).save(path)
    tensor = transform_images([path, path], [8, 6])
    assert tuple(tensor.shape) == (1, 6, 6, 8)
    np.testing.assert_allclose(tensor[0, :, 0, 0].numpy(), [(1-.485)/.229, -.456/.224, -.406/.225]*2, rtol=1e-6)


def test_navigation_policy_requires_actual_checkpoint(tmp_path):
    from print_factory.navigation_policy import NavigationPolicies
    with pytest.raises(FileNotFoundError, match='vint.pth'):
        NavigationPolicies(weights_dir=tmp_path, models=('vint',), device='cpu')
