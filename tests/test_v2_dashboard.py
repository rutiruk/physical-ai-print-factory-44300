"""Dashboard contracts use synthetic data, never an asserted simulation result."""
import numpy as np
from PIL import Image
from print_factory.v2_dashboard import dashboard_content, render_v2_dashboard


def test_capture_times_are_distinct_from_current_sim_time_and_future_events_hidden():
    data = {'now': 12.5, 'robots': [{'input_time_s': 9.2}],
            'jeff': {'input_time_s': 10.1},
            'events': [{'time_s': 13, 'event': 'FUTURE'},
                       {'time_s': 11, 'event': 'YIELD', 'detail': '退避開始'}]}
    content = dashboard_content(data)
    assert content['current'] == '現在SIM 12.50 s'
    assert content['robots'][0]['capture'] == '入力SIM 9.20 s'
    assert content['jeff_capture'] == '入力SIM 10.10 s'
    assert len(content['events']) == 1 and '退避開始' in content['events'][0]


def test_permission_and_emergency_stop_are_separate_and_candidates_use_supplied_labels():
    content = dashboard_content({'traffic': {'winner': 'B', 'granted': False},
        'jeff': {'choice': 'yield_a', 'labels': {'yield_a': 'Aを退避'},
                 'probabilities': {'yield_a': .8, 'wait': .2}},
        'robots': [{'stop_reason': '接触予防'}]})
    assert content['jeff_choice'] == 'Aを退避'
    assert content['candidates'][0] == ('Aを退避', .8)
    assert content['robots'][0]['stop'] == '非常停止：接触予防'
    assert '許可待ち' in content['traffic']
    assert content['robots'][1]['stop'] == '非常停止なし'


def test_renderer_preserves_source_rgb_and_handles_missing_telemetry():
    rgb = np.full((100, 160, 3), [35, 70, 110], dtype=np.uint8)
    before = rgb.copy()
    image = render_v2_dashboard(rgb, rgb, {})
    assert image.size == (1800, 1100) and image.mode == 'RGB'
    assert np.array_equal(rgb, before)
    assert image.getpixel((500, 400)) == (35, 70, 110)


def test_playback_claim_only_uses_requested_speed():
    assert '2倍' not in dashboard_content({})['footer']
    assert '2倍' in dashboard_content({'playback_speed': 2})['footer']


def test_zero_based_traffic_permissions_do_not_claim_both_robots_have_crossed():
    content = dashboard_content({'traffic': {'winner': 0, 'granted': [0], 'crossed': [0]}})
    assert content['traffic'] == '優先 AMR1 / 許可 AMR1 / 通過 AMR1'


def test_visible_mechanics_reports_actual_y_force_saturation_and_clearance_bound():
    content = dashboard_content({'min_clearance': .043, 'min_distance': .8,
        'gantry': {'pose': [0, .4, 0, 0], 'target': [0, .7, 0, 0],
                   'force': [0, 125, 0, 0], 'force_limit': [150, 125, 120, 12],
                   'force_saturated': [False, True, False, False]}})
    assert content['clearance'] == '車体間余裕 ≥ 0.043 m'
    assert content['gantry_y'] == 'Y 実測0.400 → 目標0.700 m / 駆動125.0 / 125 N 飽和'


def test_navigation_event_labels_distinguish_model_prediction_from_conventional_docking():
    content = dashboard_content({'now': 5, 'events': [
        {'time_s': 3, 'event': 'LEARNED_NAV_START', 'amr': 0, 'model': 'ViNT'},
        {'time_s': 4, 'event': 'CONVENTIONAL_PRECISION_START', 'amr': 1}]})
    assert content['events'] == ['3.0s  AMR1 ViNTによる局所経路予測を開始',
                                '4.0s  AMR2 従来制御で精密な着岸を開始']
    assert dashboard_content({'min_distance': .8})['clearance'] == '中心間距離 0.80 m'


def test_retained_prediction_is_explicitly_historical_when_policy_is_not_active():
    content = dashboard_content({'robots': [{'policy_active': False}, {'policy_active': True}]})
    assert content['robots'][0]['policy_usage'] == '直前のAI予測（現在は従来制御/待機）'
    assert content['robots'][1]['policy_usage'] == 'AI予測を走行に使用中'
    assert dashboard_content({})['robots'][0]['policy_usage'] == '直前のAI予測（現在は従来制御/待機）'


def test_printing_jobs_and_start_conditions_replace_old_initial_wip_claim():
    content = dashboard_content({'process_summary': 'A：白紙 → 印刷 → 折り / B：折り済 → 断裁',
        'initial_condition': 'Aは白紙から印刷 / Bは折り済の初期仕掛品',
        'robots': [{'job': 'A'}],
        'jobs': [{'id': 'A', 'state': 'printing', 'source': '印刷機', 'destination': '折り機'}]})
    assert content['process_summary'] == 'A：白紙 → 印刷 → 折り / B：折り済 → 断裁'
    assert content['robots'][0]['job_status'] == 'A：印刷中 / 印刷機 → 折り機'
    assert 'Aは白紙から印刷 / Bは折り済の初期仕掛品' in content['footer']
    assert '初期WIPから開始' not in content['footer']
    assert '初期WIPから開始' not in dashboard_content({'process_summary': 'Aは白紙から'})['footer']


def test_jeff_thumbnail_is_explicitly_actual_input_or_waiting_not_current_camera():
    assert dashboard_content({})['jeff_image_label'] == 'Jeff入力待ち'
    content = dashboard_content({'now': 12, 'jeff': {'image_path': 'capture.png', 'input_time_s': 9}})
    assert content['jeff_image_label'] == 'Jeffの入力画像'
    assert content['jeff_capture'] == '入力SIM 9.00 s'


def test_jeff_panel_renders_captured_input_instead_of_current_overhead(tmp_path):
    current = np.full((100, 160, 3), [35, 70, 110], dtype=np.uint8)
    capture = tmp_path / 'jeff_capture.png'
    Image.new('RGB', (160, 100), (120, 25, 70)).save(capture)
    image = render_v2_dashboard(current, current, {'jeff': {'image_path': str(capture)}})
    assert image.getpixel((1200, 270)) == (120, 25, 70)
    waiting = render_v2_dashboard(current, current, {})
    assert waiting.getpixel((1200, 230)) != (35, 70, 110)
