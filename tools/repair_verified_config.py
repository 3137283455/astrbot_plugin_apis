"""Apply the explicitly verified 2026-10-20 source/config fixes, with backup.

Run while AstrBot is stopped: python repair_verified_config.py --data-dir ...
No site credentials or user data are read into the report or repository.
"""
import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

FIXES = {
    "看看小姐姐": {"url": "https://api.yuafeng.cn/API/ly/cqng.php", "params": {}, "parse": "", "valid": True},
    "短剧搜索": {"parse": "data[0].cover", "valid": True},
}
UNAVAILABLE = {
    **dict.fromkeys(["安慰", "嘲讽", "KFC", "qq估价", "QQ签名"], "源站返回 403，当前接口授权不可用。"),
    **dict.fromkeys(["高铁大屏", "看看甜妹", "看看腿", "三角洲密码"], "源站域名无法解析，等待源站恢复或更换接口。"),
    "倒数日": "源站返回业务错误，未取得可用数据。",
    "起个网名": "源站返回空内容。",
    "搜表情": "源站明确返回接口已失效。",
    "看看emo": "源站提供的视频链接已失效（404）。",
}
EXPECTED_HOSTS = {
    **dict.fromkeys(["安慰", "嘲讽", "KFC", "qq估价", "QQ签名"], "api.317ak.cn"),
    **dict.fromkeys(["高铁大屏", "看看甜妹", "看看腿", "三角洲密码"], "115exuq280928.vicp.fun"),
    "倒数日": "api.pearapi.ai", "起个网名": "free.wqwlkj.cn",
    "搜表情": "api.tangdouz.com", "看看emo": "api.yuafeng.cn",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    database = args.data_dir / "api_aggregator.db"
    if not database.is_file():
        raise SystemExit("Database does not exist")
    backup = args.data_dir / ("api-before-repair-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".db")
    health = {}
    with sqlite3.connect(database) as conn:
        with sqlite3.connect(backup) as target:
            conn.backup(target)
        for name, raw in conn.execute("SELECT name,payload FROM api_pool").fetchall():
            entry = json.loads(raw)
            source = urlsplit(entry["url"])
            # Do not replace an administrator's separately configured source.
            expected = (
                name == "看看小姐姐" and source.hostname == "115exuq280928.vicp.fun"
                or name == "短剧搜索" and source.hostname == "api-v2.yuafeng.cn"
            )
            if name in FIXES and expected:
                entry.update(FIXES[name])
            if name in UNAVAILABLE:
                if source.hostname == EXPECTED_HOSTS[name]:
                    entry["valid"] = False
                    health[name] = {"reason": UNAVAILABLE[name]}
            conn.execute("UPDATE api_pool SET payload=? WHERE name=?", (json.dumps(entry, ensure_ascii=False), name))
        conn.commit()
    (args.data_dir / "api_health.json").write_text(json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"backup": str(backup), "marked_unavailable": sorted(health)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
