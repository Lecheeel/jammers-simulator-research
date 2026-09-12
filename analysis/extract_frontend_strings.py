from pathlib import Path
import re
import argparse

parser = argparse.ArgumentParser(description="Extract UI strings from an extracted frontend bundle.")
parser.add_argument("bundle", type=Path, nargs="?", default=Path(__file__).parent / "embedded" / "index-BYdydaNq.js")
args = parser.parse_args()
p = args.bundle.resolve()
s = p.read_text(encoding="utf-8", errors="ignore")
patterns = [r"`([^`]{2,160})`", r'"([^"\\]{2,160})"', r"'([^'\\]{2,160})'"]
needles = ("干扰", "测试", "端口", "登录", "队", "场景", "问题", "机器狗", "全向", "定向", "频率", "半径", "方向", "噪声", "开始", "正式", "演练", "清除", "测量", "移动", "账号", "密码", "行为日志")
seen = set()
for pat in patterns:
    for value in re.findall(pat, s):
        if any(n in value for n in needles) and value not in seen:
            seen.add(value)
print("\n".join(sorted(seen)))
