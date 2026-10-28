import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from aiohttp import web
from PIL import Image
from astrbot.core.message.components import At

from astrbot_plugin_apis.api_aggregator.database import SQLiteDatabase
from astrbot_plugin_apis.api_aggregator.entry.api_entry import APIEntry
from astrbot_plugin_apis.api_aggregator.entry.api_mgr import APIEntryManager
from astrbot_plugin_apis.api_aggregator.model import DataResource, DataType
from astrbot_plugin_apis.main import APIPlugin
from astrbot_plugin_apis.sixty import SixtyBridge, BY_NAME, build_payload
from astrbot_plugin_apis.sixty_cards import render_card, render_catalog, wrap


class Event:
    def __init__(self, text="", group="", at=False):
        self.message_str = text
        self.group, self.at = group, at
        self.unified_msg_origin = "test"
        self.sent = []
        self.llm = None

    def get_group_id(self): return self.group
    def get_sender_id(self): return "user"
    def get_self_id(self): return "123"
    def get_messages(self): return [At(qq="123")] if self.at else []
    def is_admin(self): return False
    def should_call_llm(self, value): self.llm = value
    def plain_result(self, value): return value
    def chain_result(self, value): return value
    async def send(self, value): self.sent.append(value)


class SixtyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cfg = SimpleNamespace(data_dir=Path(self.temp.name), sixty_enabled=True,
                                   sixty_base_url="http://127.0.0.1:4399", use_local=True, save_data=True)
        self.manager = APIEntryManager(SQLiteDatabase(self.cfg.data_dir))
        self.core = SimpleNamespace(api_mgr=self.manager)
        self.bridge = SixtyBridge(self.cfg)

    async def asyncTearDown(self): self.temp.cleanup()

    async def test_only_verified_entries_migrate_and_bad_replacement_stays_old(self):
        self.manager.add_entries([{"name":"电影票房", "url":"https://old.example/movie", "type":"text"}])
        self.bridge.migrate(self.core)
        self.assertEqual(self.manager.get_entry("电影票房").url, "https://old.example/movie")
        self.assertIsNone(self.manager.get_entry("小红书热点"))
        self.assertTrue(self.bridge.owns(self.manager.get_entry("抖音热搜")))

    async def test_restart_preserves_admin_changes_and_disable_restores_old(self):
        original = {"name":"今日运势", "url":"https://old.example/luck", "type":"image", "scope":["group"]}
        self.manager.add_entries([original])
        self.bridge.migrate(self.core)
        self.assertEqual(self.manager.get_entry("今日运势").scope, ["group"])
        self.manager.update_entries([{"name":"抖音热搜", "payload":{"enabled":False}}])
        self.bridge.migrate(self.core)
        self.assertFalse(self.manager.get_entry("抖音热搜").enabled)
        self.cfg.sixty_enabled = False
        self.bridge.migrate(self.core)
        self.assertEqual(self.manager.get_entry("今日运势").url, original["url"])
        self.assertIsNone(self.manager.get_entry("抖音热搜"))

    async def test_params_preserve_spaces_and_cannot_override_encoding(self):
        entry = APIEntry(build_payload(BY_NAME["翻译"], self.bridge.base))
        self.assertEqual(self.bridge.params(entry, "hello world"), {"text":"hello world"})
        self.assertEqual(self.bridge.params(entry, "encoding=image"), {"text":"encoding=image"})
        with self.assertRaisesRegex(ValueError, "补充参数"): self.bridge.params(entry, "")
        weather = APIEntry(build_payload(BY_NAME["天气"], self.bridge.base))
        self.assertEqual(self.bridge.params(weather, "上海"), {"query":"上海"})

    async def test_native_names_are_anchored_and_forecast_is_not_current_weather(self):
        self.bridge.migrate(self.core)
        self.assertEqual([e.name for e in self.manager.match_entries("/天气预报")], ["天气预报"])
        self.assertEqual(self.manager.match_entries("天气好热啊"), [])
        self.assertEqual([e.name for e in self.manager.match_entries("/必应壁纸")], ["bing图"])

    async def test_group_gate_native_single_reply_and_ai_reuses_fetch(self):
        self.bridge.migrate(self.core)
        api = APIPlugin.__new__(APIPlugin)
        api.cfg, api.core, api.sixty = self.cfg, self.core, self.bridge
        calls = []
        async def fetch(entry):
            calls.append(entry.updated_params)
            return DataResource(DataType.TEXT, entry.name, text="真实结果")
        api._fetch_data = fetch
        for event in [Event("/天气 上海", "group"), Event("/天气 上海", "group", True), Event("/天气 上海")]:
            results = [r async for r in api.on_message(event)]
            self.assertEqual(len(results), 0 if event.group and not event.at else 1)
            if results: self.assertTrue(event.llm)
        self.assertEqual(calls, [{"query":"上海"}]*2)
        self.assertEqual(await api.call_api_by_name(Event(), "翻译", "hello world"), "真实结果")
        self.assertEqual(calls[-1], {"text":"hello world"})
        before = len(calls)
        self.assertIn("补充参数", await api.call_api_by_name(Event(), "翻译", ""))
        self.assertEqual(before, len(calls))
        self.assertIn("require", await api.call_api_by_name(Event(group="group"), "翻译", "hello"))

    async def test_sixty_outage_does_not_use_random_cached_news(self):
        api = APIPlugin.__new__(APIPlugin)
        api.cfg, api.core, api.sixty = self.cfg, self.core, self.bridge
        async def fail(entry): raise RuntimeError("service offline")
        self.bridge.fetch = fail
        self.bridge.migrate(self.core)
        message = await api.call_api_by_name(Event(), "抖音热搜")
        self.assertIn("暂时不可用", message)

    async def test_non_sixty_entries_keep_original_fetch(self):
        api = APIPlugin.__new__(APIPlugin)
        api.cfg, api.sixty = self.cfg, self.bridge
        async def fetch(entry, use_local): return (entry.name, use_local)
        api.core = SimpleNamespace(data_service=SimpleNamespace(fetch=fetch))
        entry = APIEntry({"name":"旧功能", "url":"https://old.example/api", "type":"text"})
        self.assertEqual(await api._fetch_data(entry), ("旧功能", True))

    async def test_actual_http_args_media_and_empty_hotlist_validation(self):
        requests = []
        async def handler(request):
            requests.append(dict(request.query))
            return web.Response(text="你好世界" if request.path.endswith('fanyi') else "抖音实时热搜")
        app = web.Application()
        app.router.add_get('/v2/{path:.*}', handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        self.bridge.base = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
        try:
            entry = APIEntry(build_payload(BY_NAME["翻译"], self.bridge.base))
            entry.updated_params = {"text":"hello world", "encoding":"json", "extra":"bad"}
            result = await self.bridge.fetch(entry)
            self.assertEqual(result.data_type, DataType.IMAGE)
            Image.open(io.BytesIO(result.binary)).verify()
            self.assertEqual(requests[-1], {"text":"hello world", "encoding":"text"})
            with self.assertRaisesRegex(ValueError, "热榜条目"):
                await self.bridge.fetch(APIEntry(build_payload(BY_NAME["抖音热搜"], self.bridge.base)))
        finally: await runner.cleanup()


class CardTests(unittest.TestCase):
    def test_long_chinese_english_and_all_catalog_render(self):
        content = "1. 中文热榜标题\n" + "a"*200 + "\n" + "长文"*10000
        image = Image.open(io.BytesIO(render_card("抖音热搜", content)))
        self.assertLess(image.height, 5500)
        for category in ["", "工具", "热榜"]:
            rows = [r for r in BY_NAME.values() if not category or r['category'] == category]
            Image.open(io.BytesIO(render_catalog(rows, category))).verify()


if __name__ == '__main__': unittest.main()
