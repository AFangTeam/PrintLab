import sys
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS Studio adapter")

import copy
import json
import os
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from printlab import core, studio_bridge as bridge


class StudioBridgeTests(unittest.TestCase):
    def setUp(self):
        configured_name = patch.object(bridge, "display_name", return_value="PrintLab Test Printer")
        configured_name.start()
        self.addCleanup(configured_name.stop)
        self.shot=json.loads((Path(__file__).parent/'fixtures/studio-single-petg-unsent.json').read_text())
        self.job={'id':'J20261107-141042-93f972','plate':1,'mapping':{'transport':'bambu_studio','use_ams':True,'ams_mapping':[4], 'extruder_mapping':[1],'filament_types':['PETG']},'curr_bed_type':'Textured PEI Plate','sliced_printer_model':'Bambu Lab X2D'}

    def test_real_unsent_observation_passes(self):
        self.assertEqual(bridge.validate_snapshot(self.shot,self.job)['slot'],'B1')
        self.assertEqual(bridge._job_supported(self.job),[])

    def test_wrong_job_slot_nozzle_or_material_fails(self):
        mutations=[lambda j:j.update(id='J20261107-000000-ffffff'),lambda j:j['mapping'].update(ams_mapping=[0]),lambda j:j['mapping'].update(filament_types=['PLA'])]
        for mutate in mutations:
            job=copy.deepcopy(self.job);mutate(job)
            with self.assertRaises(core.WorkflowError):bridge.validate_snapshot(self.shot,job)
        shot=copy.deepcopy(self.shot)
        next(t for t in shot['tokens'] if t['text'].startswith('B1'))['x']=.65
        with self.assertRaises(core.WorkflowError):bridge.validate_snapshot(shot,self.job)

    def test_multi_material_and_aux_routes_not_available(self):
        for field,value in [('ams_mapping',[4,0]),('extruder_mapping',[0]),('transport','bambu_native'),('use_ams',False)]:
            job=copy.deepcopy(self.job);job['mapping'][field]=value
            self.assertTrue(bridge._job_supported(job))

    def test_background_window_and_bad_capture_geometry_fail(self):
        for field,value in [('active',False),('width',3840),('title','other')]:
            shot=copy.deepcopy(self.shot);shot[field]=value
            with self.assertRaises(core.WorkflowError):bridge.validate_snapshot(shot,self.job)

    def test_selected_option_border_is_not_selection(self):
        self.assertFalse(bridge._green({'green_pixels':28,'green_center_x':0}))
        shot=copy.deepcopy(self.shot)
        for token in shot['tokens']:
            if token['text']=='关闭' and token['x']<.5 and token['y']<.79:token['green_pixels']=0
        with self.assertRaisesRegex(core.WorkflowError,'延时摄影'):bridge.validate_snapshot(shot,self.job)

    def test_system_permission_overlay_is_reported(self):
        for text in ['允许', '不允许', '打开系统设置']:
            shot = copy.deepcopy(self.shot)
            shot['tokens'].append({'text': text})
            with self.assertRaisesRegex(core.WorkflowError, '系统弹窗'):
                bridge.validate_snapshot(shot, self.job)

    def test_unresolved_combined_timelapse_token_does_not_pass(self):
        for text in ['打开关闭', '打开｜关闭']:
            shot = copy.deepcopy(self.shot)
            token = next(t for t in shot['tokens'] if t['text'] == '关闭' and t['x'] < .5 and t['y'] < .79)
            token.update(text=text, confidence=.3, green_center_x=.77, green_pixels=191)
            with self.assertRaisesRegex(core.WorkflowError, '延时摄影'):
                bridge.validate_snapshot(shot, self.job)

    def test_prepare_inspects_before_changing_options(self):
        for scenario in ['already_correct', 'timelapse_on', 'wrong_job', 'overlay']:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                job = dict(self.job, artifact='test.gcode.3mf', artifact_sha256='expected')
                (directory / 'job.json').write_text(json.dumps(job))
                (directory / job['artifact']).write_bytes(b'test-only artifact')
                shot = copy.deepcopy(self.shot)
                if scenario == 'timelapse_on':
                    token = next(t for t in shot['tokens'] if t['text'] == '关闭' and t['x'] < .5 and t['y'] < .79)
                    token['green_pixels'] = 0
                if scenario == 'wrong_job':
                    next(t for t in shot['tokens'] if t['text'].startswith(job['id']))['text'] = 'J20261107-000000-ffffff.gcode'
                if scenario == 'overlay':
                    shot['tokens'].append({'text': '打开系统设置'})
                def helper(mode, *args):
                    if mode == 'probe':
                        return {'instances': [{'pid': 123, 'windows': [{'title': job['id'] + '.gcode'}]}]}
                    if mode == 'inspect-panel':
                        return shot
                    if mode == 'prepare-options':
                        self.assertEqual(args, (123, job['id'] + '.gcode'))
                        return self.shot
                    self.assertEqual(mode, 'open-panel')
                    return {'ok': True, 'sent': False}
                with patch.object(bridge.core, 'job_path', return_value=directory), patch.object(bridge.core, 'digest', return_value='expected'), patch.object(bridge, 'capability', return_value={'available': True, 'observation': {'instances': []}}), patch.object(bridge.subprocess, 'run') as launch, patch.object(bridge.time, 'sleep'), patch.object(bridge, '_run', side_effect=helper) as run:
                    if scenario in ['wrong_job', 'overlay']:
                        expected_error = '任务名' if scenario == 'wrong_job' else '系统弹窗'
                        with self.assertRaisesRegex(core.WorkflowError, expected_error):
                            bridge._open_prepared('P000', job['id'])
                    else:
                        self.assertTrue(bridge._open_prepared('P000', job['id'])[2]['options_verified'])
                    modes = [call.args[0] for call in run.call_args_list]
                    self.assertEqual(modes.count('prepare-options'), int(scenario == 'timelapse_on'))
                    self.assertNotIn('send-once', modes)
                    self.assertIn('--args', launch.call_args.args[0])

    def test_duplicate_button_or_material_fails(self):
        for name in ['发送','PETG']:
            shot=copy.deepcopy(self.shot);shot['tokens'].append(copy.deepcopy(next(t for t in shot['tokens'] if t['text']==name)))
            with self.assertRaises(core.WorkflowError):bridge.validate_snapshot(shot,self.job)

    def test_capability_is_read_only_and_process_specific(self):
        observed={'studio_version':bridge.STUDIO_VERSION,'accessibility':False,'screen_capture':True,'session_on_console':True,'screen_locked':False}
        with patch.object(bridge,'_run',return_value=observed) as run:
            result=bridge.capability()
            self.assertFalse(result['available']);self.assertIn('辅助功能',result['message']);run.assert_called_once_with('probe',timeout=10)

    def test_permission_setup_is_explicit_and_never_prints(self):
        with patch.object(bridge,'_verify_bundle'),patch.object(bridge.subprocess,'run') as run:
            result=bridge.setup_permissions()
            self.assertTrue(result['requested']);self.assertFalse(result['printed'])
            self.assertIn('request-permissions',run.call_args.args[0])
            self.assertNotIn('send-once',run.call_args.args[0])

    def test_launchservices_ipc_is_private_and_bound(self):
        with tempfile.TemporaryDirectory() as root:
            def reply(command,**kwargs):
                request=Path(command[-2]);response=Path(command[-1])
                data=json.loads(request.read_text())
                self.assertEqual(data['args'],['probe'])
                self.assertEqual(request.stat().st_mode & 0o777,0o600)
                self.assertEqual(request.parent.stat().st_mode & 0o777,0o700)
                self.assertIn('-W',command)
                response.write_text(json.dumps({'ok':True,'request_id':data['request_id']}))
                return subprocess.CompletedProcess(command, 0, '', '')
            with patch.object(bridge.core,'ROOT',Path(root)),patch.object(bridge,'_verify_bundle'),patch.object(bridge.subprocess,'run',side_effect=reply):
                self.assertTrue(bridge._run('probe')['ok'])
                self.assertEqual(list((Path(root)/'Runtime/studio-bridge-ipc').iterdir()),[])

    def test_launchservices_rejects_another_requests_response(self):
        with tempfile.TemporaryDirectory() as root:
            def reply(command,**kwargs):
                Path(command[-1]).write_text(json.dumps({'ok':True,'request_id':'wrong'}))
            with patch.object(bridge.core,'ROOT',Path(root)),patch.object(bridge,'_verify_bundle'),patch.object(bridge.subprocess,'run',side_effect=reply):
                with self.assertRaisesRegex(core.WorkflowError,'不属于本次请求'):bridge._run('probe')

    def test_nonzero_exit_preserves_bound_helper_error(self):
        with tempfile.TemporaryDirectory() as root:
            def reply(command, **kwargs):
                request = json.loads(Path(command[-2]).read_text())
                Path(command[-1]).write_text(json.dumps({
                    'ok': False, 'request_id': request['request_id'],
                    'error': 'Exact accessible window is absent or ambiguous'}))
                return subprocess.CompletedProcess(command, 1, '', 'application exited')
            with patch.object(bridge.core, 'ROOT', Path(root)), patch.object(bridge, '_verify_bundle'), patch.object(bridge.subprocess, 'run', side_effect=reply):
                with self.assertRaisesRegex(core.WorkflowError, 'Exact accessible window'):
                    bridge._run('inspect-panel', 123, 'example.gcode')

    def test_nonzero_exit_with_success_receipt_stays_unconfirmed(self):
        with tempfile.TemporaryDirectory() as root:
            def reply(command, **kwargs):
                request = json.loads(Path(command[-2]).read_text())
                Path(command[-1]).write_text(json.dumps({'ok': True, 'request_id': request['request_id']}))
                return subprocess.CompletedProcess(command, 1, '', '')
            with patch.object(bridge.core, 'ROOT', Path(root)), patch.object(bridge, '_verify_bundle'), patch.object(bridge.subprocess, 'run', side_effect=reply):
                with self.assertRaisesRegex(core.WorkflowError, '执行结果仍需核实'):
                    bridge._run('send-once', 'bound-request.json')

    def test_launch_failure_exposes_diagnostic_without_retry(self):
        with tempfile.TemporaryDirectory() as root:
            failed = subprocess.CompletedProcess([], 1, '', 'LaunchServices could not open the application')
            with patch.object(bridge.core, 'ROOT', Path(root)), patch.object(bridge, '_verify_bundle'), patch.object(bridge.subprocess, 'run', return_value=failed) as run:
                with self.assertRaisesRegex(core.WorkflowError, 'LaunchServices could not open'):
                    bridge._run('probe')
                run.assert_called_once()

    def test_prepare_error_is_proven_not_sent(self):
        with patch.object(bridge,'_dispatch_impl',side_effect=core.WorkflowError('prepare failed')):
            with self.assertRaises(bridge.BeforeSendError) as caught:bridge.dispatch('P009','job')
            self.assertTrue(caught.exception.verified_not_sent)

    def test_after_reservation_entered_is_not_reclassified_as_safe(self):
        def fail(pid,jid,phase):
            phase['reservation_entered']=True
            raise RuntimeError('reservation failed after persistence may have begun')
        with patch.object(bridge,'_dispatch_impl',side_effect=fail):
            with self.assertRaises(RuntimeError):bridge.dispatch('P009','job')

    def test_after_helper_entered_is_not_reclassified_as_safe(self):
        def fail(pid,jid,phase):
            phase['final_helper_invoked']=True
            raise RuntimeError('helper timeout')
        with patch.object(bridge,'_dispatch_impl',side_effect=fail):
            with self.assertRaises(RuntimeError):bridge.dispatch('P009','job')


if __name__=='__main__':unittest.main()
