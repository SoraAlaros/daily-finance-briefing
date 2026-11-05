"""
validate_briefing.py
检查生成的简报是否完整，拦截"摘要版"坏稿（如 2026-10-27、2026-11-03：
模型只输出各章节一句话概述 + "几点说明"，而非完整简报；或如 2026-06-30 输出被截断），
并提供 strip_chatter() 清理页脚之后的对话式尾巴。

阈值依据：2026-05 ~ 2026-11 共 102 份正常简报的最小值，留出余量。

用法：
  python scripts/validate_briefing.py briefings/zh/2026-11-03.md [更多文件...]
  通过 exit 0，不通过 exit 1。
也可被 generate_briefing.py 导入调用 validate()。
"""
import re
import sys

MIN_TOTAL_BYTES = 7000  # 正常稿最小 8304，坏稿最大 3952

# 章节 emoji 前缀 → (名称, 最小字节数)；正常稿最小值：📊2244 🌍2089 🏦1030
REQUIRED_SECTIONS = {
    "📊": ("美股收盘", 1500),
    "🌍": ("全球市场与今日要闻", 1500),
    "🏦": ("华尔街观点", 700),
    "🔭": ("明日关注", 250),  # 正常稿最小 451；2026-06-30 截断稿仅 55
}

MIN_TABLE_ROWS = 20  # 三大指数 + 11 板块 + 美债美元 + 个股，正常稿最少 26 行

# 页脚首行；缺失说明输出被截断
FOOTER_RE = re.compile(r"^\*简报生成时间", re.M)

# 对话式内容：strip_chatter() 清理后若仍残留则警告
CHATTER_PATTERNS = ["您提供", "需要我", "已导出", "几点说明"]


def strip_chatter(text: str) -> str:
    """删除页脚之后的对话式尾巴（"几点说明"、"需要我导出 PDF 吗？"等）。

    页脚 = "*简报生成时间…*" 行及其后紧接的斜体行（数据来源、注）。
    找不到页脚时原样返回，交给 validate() 报错。
    """
    matches = list(FOOTER_RE.finditer(text))
    if not matches:
        return text
    lines = text[matches[-1].start():].split("\n")
    keep = 1
    for i, line in enumerate(lines[1:], start=1):
        if line.startswith("*"):
            keep = i + 1
        elif line.strip():
            break
    footer = "\n".join(lines[:keep])
    return text[:matches[-1].start()] + footer + "\n"


def validate(text: str):
    """返回 (errors, warnings)。errors 非空即为坏稿。"""
    errors, warnings = [], []

    if not text.lstrip().startswith("# 每日金融市场资讯简报"):
        errors.append("缺少标题行 '# 每日金融市场资讯简报'")

    size = len(text.encode("utf-8"))
    if size < MIN_TOTAL_BYTES:
        errors.append(f"总长度 {size} 字节 < {MIN_TOTAL_BYTES}")

    sections = {}
    for part in re.split(r"^## ", text, flags=re.M)[1:]:
        sections[part[:1]] = len(part.encode("utf-8"))
    for emoji, (name, min_bytes) in REQUIRED_SECTIONS.items():
        if emoji not in sections:
            errors.append(f"缺少章节 {emoji} {name}")
        elif sections[emoji] < min_bytes:
            errors.append(f"章节 {emoji} {name} 仅 {sections[emoji]} 字节 < {min_bytes}（疑似摘要版）")

    rows = len(re.findall(r"^\|", text, flags=re.M))
    if rows < MIN_TABLE_ROWS:
        errors.append(f"表格行数 {rows} < {MIN_TABLE_ROWS}")

    if not FOOTER_RE.search(text):
        errors.append("缺少页脚 '*简报生成时间…*'（疑似输出被截断）")

    found = [p for p in CHATTER_PATTERNS if p in text]
    if found:
        warnings.append(f"含对话式内容：{', '.join(found)}")

    return errors, warnings


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    failed = False
    for path in sys.argv[1:]:
        with open(path, "r", encoding="utf-8") as f:
            errors, warnings = validate(f.read())
        status = "FAIL" if errors else "OK"
        print(f"[{status}] {path}")
        for e in errors:
            print(f"  ERROR: {e}")
        for w in warnings:
            print(f"  WARN:  {w}")
        failed = failed or bool(errors)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
