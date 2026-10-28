"""Small, fixed-catalog adapter for the locally deployed vikiboss/60s service."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout
from PIL import Image

from .api_aggregator.model import DataResource, DataType
from .sixty_cards import render_card, render_catalog

ROOT = Path(__file__).parent
CATALOG = json.loads((ROOT / "presets/sixty_catalog.json").read_text(encoding="utf-8"))
BY_NAME = {row["name"]: row for row in CATALOG}


def build_payload(row, base):
    names = [row["name"], *row.get("aliases", [])]
    return {"name": row["name"], "url": base + row["path"] + "?encoding=" + row["encoding"],
            "type": ("image" if row["type"] == "text" and (row["category"] in {"热榜", "资讯", "工具"} or row["name"] == "今日运势") else row["type"]), "params": row["params"], "parse": "", "scope": [],
            "keywords": [r"^/?(?:" + "|".join(re.escape(n) for n in names) + r")$"],
            "enabled": True, "valid": True}


class SixtyBridge:
    def __init__(self, cfg):
        self.cfg = cfg
        self.base = cfg.sixty_base_url.rstrip("/")
        parsed = urlsplit(self.base)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("60s 服务地址应为完整 http(s) 地址，不能包含查询参数")
        self.semaphore = asyncio.Semaphore(4)

    def owns(self, entry):
        row = BY_NAME.get(entry.name)
        return bool(row and entry.url == build_payload(row, self.base)["url"])

    def migrate(self, core):
        """Apply only verified entries once; preserve scopes and administrator switches."""
        state_path = self.cfg.data_dir / "sixty_migration.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        if not self.cfg.sixty_enabled:
            if not state.get("active"):
                return
            for name, original in state.get("originals", {}).items():
                current = core.api_mgr.get_entry(name)
                if current and self.owns(current):
                    if original:
                        core.api_mgr.update_entries([{"name": name, "payload": original}])
                    else:
                        core.api_mgr.remove_entries([name])
            state["active"] = False
        else:
            verified_path = ROOT / "presets/sixty_verified.json"
            verified = json.loads(verified_path.read_text(encoding="utf-8"))
            names = verified["names"]
            revision = hashlib.sha256(json.dumps([CATALOG, names, self.base], ensure_ascii=False).encode()).hexdigest()
            if state.get("active") and state.get("revision") == revision:
                return
            originals = state.get("originals", {})
            # Persist rollback data before making any pool changes.
            pending = []
            for name in names:
                row = BY_NAME[name]
                existing = core.api_mgr.get_entry(name)
                if existing and not row.get("replace") and not self.owns(existing):
                    continue
                originals.setdefault(name, existing.to_dict() if existing else None)
                payload = build_payload(row, self.base)
                if existing:
                    payload.update(enabled=existing.enabled, scope=list(existing.scope))
                pending.append((existing, payload))
            state.update(originals=originals, active=True, revision="pending")
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            for existing, payload in pending:
                if existing:
                    core.api_mgr.update_entries([{"name": payload["name"], "payload": payload}])
                else:
                    core.api_mgr.add_entries([payload])
            state["revision"] = revision
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def params(self, entry, args_text):
        row = BY_NAME[entry.name]
        params = dict(row["params"])
        value = str(args_text or "").strip()
        # Each exposed endpoint takes zero or one user parameter. Preserve spaces in it.
        if params and value:
            params[next(iter(params))] = value
        elif not params and value:
            raise ValueError(f"用法：{row['example']}（此功能不需要参数）")
        if any(not str(v).strip() for v in params.values()):
            raise ValueError(f"请补充参数，例如：{row['example']}")
        if any(len(str(v)) > 1500 for v in params.values()):
            raise ValueError("参数过长，请控制在 1500 字以内。")
        return params

    def menu(self, entries, category=""):
        names = {entry.name for entry in entries if self.owns(entry)}
        rows = [r for r in CATALOG if r["name"] in names and (not category or r["category"] == category)]
        return render_catalog(rows, category)

    async def fetch(self, entry):
        row = BY_NAME[entry.name]
        params = dict(row["params"])
        params.update(entry.updated_params)
        # Never let an argument replace fixed encoding or inject additional upstream options.
        params = {key: params[key] for key in row["params"]}
        params["encoding"] = row["encoding"]
        async with self.semaphore:
            async with ClientSession(timeout=ClientTimeout(total=35)) as session:
                async with session.get(self.base + row["path"], params=params) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "").lower()
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        data.extend(chunk)
                        if len(data) > 16 * 1024 * 1024:
                            raise ValueError("接口返回内容过大，请稍后重试。")
        raw = bytes(data)
        if row["type"] == "image":
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
            return DataResource(DataType.IMAGE, entry.name, binary=raw)
        if row["type"] == "audio":
            if len(raw) < 1024 or not ("audio/" in content_type or raw[:4] in (b"RIFF", b"OggS") or raw[:3] == b"ID3"):
                raise ValueError("接口未返回可播放音频。")
            return DataResource(DataType.AUDIO, entry.name, binary=raw)
        text = raw.decode("utf-8").strip()
        if not text or "application/json" in content_type or text.startswith(('{"code"', '<!DOCTYPE', '<html')):
            raise ValueError("接口没有返回有效内容，请稍后重试。")
        if row["category"] == "热榜" and not re.search(r"(?:^|\n)1[.、]", text):
            raise ValueError("该平台当前未返回热榜条目，请稍后重试。")
        if row["category"] in {"热榜", "资讯", "工具"} or entry.name == "今日运势":
            image = await asyncio.to_thread(render_card, entry.name, text)
            return DataResource(DataType.IMAGE, entry.name, binary=image)
        return DataResource(DataType.TEXT, entry.name, text=text)
