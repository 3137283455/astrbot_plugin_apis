import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from astrbot_plugin_apis.api_aggregator.entry.api_entry import APIEntry
from astrbot_plugin_apis.api_aggregator.data_service.remote_data import RemoteDataService
from astrbot_plugin_apis.api_aggregator.data_service.request_result import RequestResult
from astrbot_plugin_apis.api_aggregator.model import DataResource, DataType
from astrbot_plugin_apis.main import APIPlugin


class RemoteTests(unittest.IsolatedAsyncioTestCase):
    async def test_media_url_keeps_signature_and_never_receives_api_secrets(self):
        service = RemoteDataService(None, None)
        service._build_request_args = lambda entry: ({"Authorization": "secret"}, {"ckey": "secret"}, 5)
        calls = []
        url = "https://cdn.example/photo?transform=a,b&signature=abc%26def"
        async def request(target, **kwargs):
            calls.append((target, kwargs))
            if len(calls) == 1:
                return RequestResult(status=200, raw_text=json.dumps({"code": 200, "data": url}), content_type="application/json")
            return RequestResult(status=200, raw_content=b"media", content_type="image/jpeg")
        service._request = request
        entry = APIEntry({"name": "photo", "url": "https://api.example/photo", "type": "image", "parse": "data"})
        result = await service.get_data(entry)
        self.assertEqual(result.raw_content, b"media")
        self.assertEqual(calls[1][0], url)
        self.assertEqual(calls[1][1]["params"], {})
        self.assertNotIn("Authorization", calls[1][1]["headers"])

    async def test_error_json_is_rejected_before_parse_discards_status(self):
        service = RemoteDataService(None, None)
        service._build_request_args = lambda entry: ({}, {}, 5)
        async def request(*args, **kwargs):
            return RequestResult(status=200, raw_text='{"code":500,"data":"looks successful"}', content_type="application/json")
        service._request = request
        result = await service.get_data(APIEntry({"name": "bad", "url": "https://api.example", "type": "text", "parse": "data"}))
        self.assertFalse(result.ok)

    async def test_text_api_does_not_replace_text_with_linked_image(self):
        service = RemoteDataService(None, None)
        service._build_request_args = lambda entry: ({}, {}, 5)
        calls = []
        async def request(*args, **kwargs):
            calls.append(args)
            return RequestResult(status=200, raw_text="Article https://cdn.example/image.jpg", content_type="text/plain")
        service._request = request
        result = await service.get_data(APIEntry({"name": "article", "url": "https://api.example", "type": "text"}))
        self.assertEqual(len(calls), 1)
        self.assertIn("Article", result.raw_text)

    async def test_complete_url_and_json_arrays_preserve_encoded_query(self):
        url = "https://cdn.example/image?format=auto,webp&sign=a%26b"
        for text in (url, json.dumps({"data": [{"cover": url}]})):
            self.assertEqual(RequestResult(raw_text=text).extract_urls(), [url])


class APIEntryTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_tool_name_uses_permissions_without_requiring_regex_match(self):
        with tempfile.TemporaryDirectory() as d:
            api = APIPlugin.__new__(APIPlugin)
            entry = APIEntry({"name": "原有功能", "url": "https://api.example", "type": "text", "keywords": ["^/别名$"]})
            async def fetch(*args, **kwargs):
                return DataResource(data_type=DataType.TEXT, name=entry.name, text="真实文字")
            manager = SimpleNamespace(get_entry=lambda name: entry, list_enabled_entries=lambda: [entry])
            api.cfg = SimpleNamespace(data_dir=Path(d), use_local=False, save_data=True)
            api.core = SimpleNamespace(api_mgr=manager, data_service=SimpleNamespace(fetch=fetch))
            event = SimpleNamespace(get_group_id=lambda: "", get_sender_id=lambda: "user", is_admin=lambda: False,
                                    unified_msg_origin="test", get_messages=lambda: [])
            self.assertEqual(await api.call_api_by_name(event, entry.name), "真实文字")
            entry.scope = ["admin"]
            self.assertIn("not accessible", await api.call_api_by_name(event, entry.name))
            entry.scope = []
            entry.valid = False
            (Path(d) / "api_health.json").write_text(json.dumps({entry.name: {"reason": "源站域名已失效。"}}))
            self.assertIn("源站域名已失效", await api.call_api_by_name(event, entry.name))


if __name__ == "__main__":
    unittest.main()
