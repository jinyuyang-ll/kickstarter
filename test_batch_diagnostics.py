"""Selected batch preservation, safe diagnostics and local HTTP session comparison."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch
from urllib.parse import urlparse
from urllib.request import urlopen

import request_diagnostics as d
import url_collector as c
import web_app as web
from test_url_collector import project
from test_request_control import response


class DiagnosticsTests(unittest.TestCase):
    def test_response_only_exports_allowlisted_headers_and_redacted_title(self):
        r = response(403, text='<html><title>Access denied alice@example.com 192.168.1.10 pass123 cookieABC</title><script>secret raw-body-value</script><p>Request blocked password=pass123</p></html>', headers={"server":"edge","cf-ray":"abcdef1234567890-SIN","set-cookie":"auth=cookieABC","authorization":"Bearer tokenXYZ"})
        result = d.response_details(r, ["pass123", "cookieABC"])
        encoded = json.dumps(result)
        for secret in ("pass123", "cookieABC", "alice@example.com", "192.168.1.10", "raw-body-value", "tokenXYZ", "set-cookie", "authorization"):
            self.assertNotIn(secret, encoded)
        self.assertEqual(result["response_headers"]["cf-ray"], "abcdef1234567890-SIN")
        self.assertIn("request blocked", result["error_hints"])

    def test_urls_keep_filter_but_hide_unknown_and_sensitive_parameters(self):
        url = d.safe_url('https://user:password@www.kickstarter.com/discover/advanced.json?page=2&goal_max=500&token=private-token&term=private-term#fragment')
        self.assertIn('page=2', url)
        self.assertIn('goal_max=500', url)
        for secret in ('user:', 'password', 'private-token', 'private-term', 'fragment'):
            self.assertNotIn(secret, url)

    def test_body_hint_does_not_include_script_or_arbitrary_body(self):
        result = d.response_details(response(403, text='<title>Forbidden</title><script>captcha</script><p>client-personal-data</p>'))
        self.assertNotIn('captcha', result['error_hints'])
        self.assertNotIn('client-personal-data', json.dumps(result))

    def test_network_metadata_only_includes_proxy_flags(self):
        with patch.dict('os.environ', {'HTTPS_PROXY': 'http://user:password@proxy.invalid'}, clear=True):
            result = d.network_context('http://another:secret@proxy.invalid')
        self.assertTrue(result['configured_proxy'])
        self.assertEqual(result['proxy_environment_variables'], ['HTTPS_PROXY'])
        self.assertNotIn('password', json.dumps(result))
        self.assertNotIn('secret', json.dumps(result))

    def test_actual_request_emits_time_duration_session_and_response_id(self):
        session = Mock()
        session._diagnostic_session_id = 'test-session'
        session._diagnostic_secrets = []
        records = []
        session._diagnostic_sink = records.append
        session.get.return_value = response(403, text='<title>Forbidden</title>', headers={'server':'edge','x-request-id':'test-id'})
        session.get.return_value.url = c.BASE_URL + '?page=2'
        with self.assertRaises(c.CollectionError) as caught:
            c.request_page(session, c.BASE_URL + '?page=2', None, 1, 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['http_status'], 403)
        self.assertIn('requested_at', records[0])
        self.assertGreaterEqual(records[0]['elapsed_ms'], 0)
        self.assertEqual(records[0]['session_id'], 'test-session')
        self.assertEqual(caught.exception.details['response_headers']['x-request-id'], 'test-id')


class PersistentSessionTests(unittest.TestCase):
    def test_successful_listing_persists_site_cookies_for_next_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = c.CollectionTransport({}, cookie_store_dir=tmp)
            session = first.acquire()
            session.cookies.set("fixture_session", "secret-cookie-value", domain=".kickstarter.com", path="/")
            session.cookies.set("foreign_session", "foreign-secret", domain=".example.com", path="/")
            session.get = Mock(return_value=response(payload={"projects": [], "has_more": False}))
            records = []
            session._diagnostic_sink = records.append
            c.request_page(session, c.BASE_URL, None, 1, 1)
            first.close()

            self.assertEqual(records[0]["cookie_state_save"], {"status": "saved", "cookie_count": 1})
            self.assertNotIn("secret-cookie-value", json.dumps(records))
            self.assertNotIn("foreign-secret", first.cookie_path.read_text(encoding="utf-8"))
            second = c.CollectionTransport({}, cookie_store_dir=tmp)
            restored = second.acquire()
            self.assertEqual(second.cookie_state_status, "restored")
            self.assertEqual(second.restored_cookie_count, 1)
            self.assertEqual(restored.cookies.get("fixture_session", domain=".kickstarter.com"), "secret-cookie-value")
            self.assertIsNone(restored.cookies.get("foreign_session", domain=".example.com"))
            second.close()

    def test_per_batch_comparison_mode_does_not_persist_cookie_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = c.CollectionTransport({}, mode="per_batch", cookie_store_dir=tmp)
            transport.acquire().cookies.set("fixture_session", "secret", domain=".kickstarter.com", path="/")
            self.assertEqual(transport.persist_cookies()["status"], "disabled")
            transport.close()
            self.assertEqual(list(Path(tmp).iterdir()), [])

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(web, 'ROOT', self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def plan(self):
        return web.make_plan({'output':'merged.csv','max_pages':1,'groups':[{'states':['successful'],'goal_min':i*100,'goal_max':(i+1)*100,'label':f'G{i+1}'} for i in range(3)]})

    def test_select_one_preserves_other_checkpoints_and_all_existing_urls(self):
        plan = self.plan()
        directory = self.root / 'merged.batches'
        untouched = []
        for i,item in enumerate(plan['batches']):
            part = directory / (item['id']+'.csv')
            c.write_csv_atomic(part,[c.project_to_row(project(i+1,2025),c.BASE_URL,1,'test')])
            cp = Path(str(part)+'.checkpoint.json')
            c.write_json_atomic(cp,{'query_signature':item['id'],'next_page':2,'rows':1,'complete':False})
            if i!=1:untouched.append((cp,cp.read_bytes()))
        # Historical aggregate entries outside this particular plan must also remain.
        c.write_csv_atomic(Path(plan['output']),[c.project_to_row(project(99,2025),c.BASE_URL,1,'test')])
        plan['selected_batch_ids']=[plan['batches'][1]['id']]
        path=self.root/'plan.json';c.write_json_atomic(path,plan)
        with patch('url_collector.request_page',return_value={'projects':[project(50,2025)],'has_more':False}) as request:
            result=c.collect_plan(path,lambda _:None)
        self.assertEqual(request.call_count,1)
        self.assertIn('page=2',request.call_args.args[1])
        self.assertEqual(result['total_urls'],5)
        self.assertTrue(result['selected_complete'])
        self.assertFalse(result['complete'])
        self.assertEqual(result['batches'][0]['stop_reason'],'not_selected')
        for path,original in untouched:self.assertEqual(path.read_bytes(),original)

    def test_bad_selection_rejected_before_creating_outputs(self):
        plan=self.plan();plan['selected_batch_ids']=['missing']
        path=self.root/'plan.json';c.write_json_atomic(path,plan)
        with self.assertRaises(ValueError):c.collect_plan(path)
        self.assertFalse(Path(plan['output']).exists())

    def test_web_rejects_empty_unknown_and_non_list_selection(self):
        for selected in ([],['missing'],'all'):
            with self.subTest(selected=selected),self.assertRaises(ValueError):
                web.make_plan({'selected_batch_ids':selected})

    def test_request_failure_still_halts_later_selected_batches(self):
        plan=self.plan();plan['selected_batch_ids']=[b['id'] for b in plan['batches'][1:]]
        path=self.root/'plan.json';c.write_json_atomic(path,plan)
        with patch('url_collector.request_page',side_effect=c.CollectionError('http_403',http_status=403)) as request:
            result=c.collect_plan(path,lambda _:None)
        self.assertEqual(request.call_count,1)
        self.assertEqual(result['batches'][2]['stop_reason'],'not_run')
        self.assertTrue(result['failed'])

    def test_session_mode_does_not_change_query_identity(self):
        shared=web.make_plan({'states':['successful'],'session_mode':'shared'})
        separate=web.make_plan({'states':['successful'],'session_mode':'per_batch'})
        self.assertEqual(shared['batches'][0]['id'],separate['batches'][0]['id'])
        with self.assertRaises(ValueError):web.make_plan({'session_mode':'invalid'})


class LocalSessionComparison(unittest.TestCase):
    def test_shared_and_per_batch_modes_against_local_http_server(self):
        observations=[]
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def do_GET(self):
                observations.append({'cookie':self.headers.get('Cookie',''),'port':self.client_address[1]})
                payload=json.dumps({'projects':[project(len(observations),2025)],'has_more':False}).encode()
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(payload)))
                self.send_header('Set-Cookie','fixture_session=secret-fixture; Path=/; HttpOnly')
                self.end_headers();self.wfile.write(payload)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        original_get=c.requests.Session.get
        def local_get(session,url,**kwargs):
            kwargs['proxies']=None
            return original_get(session,f'http://127.0.0.1:{server.server_port}/?'+urlparse(url).query,**kwargs)
        try:
            with tempfile.TemporaryDirectory() as tmp,patch.object(web,'ROOT',Path(tmp)),patch('url_collector.load_config',return_value={}),patch('url_collector.requests.Session.get',new=local_get),patch('request_control.RequestGate.before_request'):
                for mode in ('shared','per_batch'):
                    observations.clear()
                    plan=web.make_plan({'output':mode+'.csv','states':['successful','failed'],'max_pages':1,'session_mode':mode})
                    path=Path(tmp)/(mode+'.json');c.write_json_atomic(path,plan)
                    lines=[]
                    result=c.collect_plan(path,lines.append)
                    self.assertTrue(result['complete'])
                    self.assertEqual(len(observations),2)
                    self.assertEqual(observations[0]['cookie'],'')
                    records=[json.loads(line.split(' ',1)[1]) for line in lines if line.startswith('REQUEST_DIAGNOSTIC ')]
                    self.assertEqual(len(records),2)
                    if mode=='shared':
                        self.assertIn('fixture_session=',observations[1]['cookie'])
                        self.assertEqual(records[0]['session_id'],records[1]['session_id'])
                        self.assertEqual(observations[0]['port'],observations[1]['port'])
                    else:
                        self.assertEqual(observations[1]['cookie'],'')
                        self.assertNotEqual(records[0]['session_id'],records[1]['session_id'])
                    self.assertNotIn('secret-fixture','\n'.join(lines))
        finally:
            server.shutdown();server.server_close();thread.join()


class DownloadTests(unittest.TestCase):
    def test_disk_log_keeps_lines_beyond_ui_limit(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(web,'ROOT',Path(tmp)),patch.dict(web.JOBS,clear=True):
            identity='abcdef1234'
            web.JOBS[identity]={'id':identity,'kind':'collect','log':[]}
            process=Mock()
            process.stdout=[f'LINE {i}\n' for i in range(1005)]
            process.wait.return_value=2
            with patch('web_app.subprocess.Popen',return_value=process):
                web.run_job(identity,['unused'])
            job=web.JOBS[identity]
            self.assertEqual(len(job['log']),1000)
            disk=Path(job['log_path']).read_text(encoding='utf-8')
            self.assertIn('LINE 0\n',disk)
            self.assertIn('LINE 1004\n',disk)
            self.assertIn('JOB_FINISHED',disk)
            self.assertEqual(job['status'],'failed')

    def test_full_log_available_after_in_memory_job_is_gone(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(web,'ROOT',Path(tmp)):
            path=Path(tmp)/'.collection'/'job_logs'/'abcdef1234.txt'
            path.parent.mkdir(parents=True);path.write_text('REQUEST_DIAGNOSTIC test',encoding='utf-8')
            server=ThreadingHTTPServer(('127.0.0.1',0),web.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with urlopen(f'http://127.0.0.1:{server.server_port}/api/jobs/abcdef1234/diagnostics') as response:
                    self.assertEqual(response.read(),b'REQUEST_DIAGNOSTIC test')
                    self.assertIn('attachment',response.headers['Content-Disposition'])
            finally:
                server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
