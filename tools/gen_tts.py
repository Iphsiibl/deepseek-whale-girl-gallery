#!/usr/bin/env python3
"""调用 matrix TTS 批量生成口播分段，带指数退避重试。

接口有速率限制，单批 10 段以上、或者连续调用容易吃到 429。
这里按小批次发，失败的段原地重试（提示词不变），直到全部成功或达到重试上限。
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

WORK = Path(__file__).resolve().parent
ARGS = json.loads((WORK / "tts_segments.json").read_text(encoding="utf-8"))
REQUESTS = ARGS["requests"]

BATCH = 2          # 每批几段（限流频繁，小批更稳）
MAX_RETRY = 6      # 每段最多重试次数
BASE_SLEEP = 12    # 首次退避秒数


def call(batch: list[dict]) -> dict:
    path = WORK / "_tts_tmp.json"
    path.write_text(json.dumps({"requests": batch}, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        ["mcode-tools", "connector", "call", "connector__matrix__batch_text_to_audio",
         "--args-file", str(path)],
        capture_output=True, text=True, timeout=900,
    )
    path.unlink(missing_ok=True)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"code": -1, "message": proc.stdout[-400:] + proc.stderr[-400:]}


def main() -> int:
    results: dict[str, str] = {}
    pending = list(REQUESTS)

    for attempt in range(MAX_RETRY):
        if not pending:
            break
        batches = [pending[i:i + BATCH] for i in range(0, len(pending), BATCH)]
        still: list[dict] = []
        for batch in batches:
            resp = call(batch)
            ok = resp.get("success_items", []) or []
            bad = resp.get("failed_items", []) or []
            for item in ok:
                results[item["file_name"]] = item["node_id"]
            for item in bad:
                idx = item.get("index")
                if isinstance(idx, int) and 0 <= idx < len(batch):
                    still.append(batch[idx])
            if not ok and not bad:
                print(f"  ! 批次整体失败: {resp.get('message')}", flush=True)
                still.extend(batch)
            time.sleep(2)
        print(f"  第 {attempt + 1} 轮：成功 {len(results)}/{len(REQUESTS)}，待重试 {len(still)}", flush=True)
        pending = still
        if pending:
            sleep = BASE_SLEEP * (attempt + 1)
            print(f"  退避 {sleep}s…", flush=True)
            time.sleep(sleep)

    if pending:
        print(f"仍有 {len(pending)} 段未生成: {[p['output_file'] for p in pending]}")
        return 1

    (WORK.parent / "docs" / "video" / "tts_nodes.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"全部 {len(results)} 段生成完成 -> docs/video/tts_nodes.json")
    for name, node in results.items():
        print(f"  {name}  {node}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
