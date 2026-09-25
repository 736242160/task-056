#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wiki2html.py — 单文件 wiki 标记转 HTML 工具（仅依赖 Python 标准库）。

支持的标记：
    '''粗体'''                -> <strong>
    ''斜体''                  -> <em>
    [[链接地址|显示文字]]      -> <a href="链接地址">显示文字</a>
    = 一级标题 =  ...  ===== 五级标题 =====   （等号与文字之间需有空格，左右等号数量必须一致）
    行首四个空格              -> 代码块 <pre><code>，块内不解析任何格式，原样输出（仅做 HTML 转义）
    行首 *                    -> 无序列表 <ul><li>，连续的 * 行合并为一个列表

行内标记可嵌套组合，例如：
    '''粗体里有''斜体''和[[地址|链接]]'''

代码块规则：由行首四个空格开始，遇到不足四格缩进的行（空行或普通行）结束；
如果代码块一直持续到文件末尾，视为"代码块未闭合"错误。

错误报告：所有标记错误都会抛出 WikiError，包含行号和未闭合的标记。

用法：
    python3 wiki2html.py 文档.wiki      # 转换文件，HTML 输出到 stdout
    python3 wiki2html.py < 文档.wiki    # 从标准输入读取
    python3 wiki2html.py --demo         # 运行内置自测 + 示例文档 + 错误样例
"""

import html
import re
import sys


class WikiError(Exception):
    """标记解析错误，携带行号信息。"""

    def __init__(self, lineno, message):
        self.lineno = lineno
        self.message = message
        super().__init__("第 %d 行: %s" % (lineno, message))


# ----------------------------------------------------------------------
# 行内解析
# ----------------------------------------------------------------------

def _find_italic_close(text, start):
    """从 start 起寻找斜体结束标记 ''（跳过属于粗体 ''' 的引号）。"""
    pos = start
    while True:
        pos = text.find("''", pos)
        if pos == -1:
            return -1
        prev_ch = text[pos - 1] if pos > 0 else ""
        next_ch = text[pos + 2] if pos + 2 < len(text) else ""
        if prev_ch != "'" and next_ch != "'":
            return pos
        pos += 1


def parse_inline(text, lineno):
    """解析一行内的行内标记，返回 HTML。出错抛 WikiError。"""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("'''", i):
            end = text.find("'''", i + 3)
            if end == -1:
                raise WikiError(lineno, "粗体标记 ''' 未闭合")
            out.append("<strong>%s</strong>" % parse_inline(text[i + 3:end], lineno))
            i = end + 3
        elif text.startswith("''", i):
            end = _find_italic_close(text, i + 2)
            if end == -1:
                raise WikiError(lineno, "斜体标记 '' 未闭合")
            out.append("<em>%s</em>" % parse_inline(text[i + 2:end], lineno))
            i = end + 2
        elif text.startswith("[[", i):
            end = text.find("]]", i + 2)
            if end == -1:
                raise WikiError(lineno, "链接标记 [[ 未闭合")
            inner = text[i + 2:end]
            url, sep, label = inner.partition("|")
            if not sep:
                label = url
            out.append('<a href="%s">%s</a>' % (
                html.escape(url.strip(), quote=True),
                parse_inline(label, lineno),
            ))
            i = end + 2
        else:
            j = i
            while j < n and not text.startswith("''", j) and not text.startswith("[[", j):
                j += 1
            out.append(html.escape(text[i:j]))
            i = j
    return "".join(out)


# ----------------------------------------------------------------------
# 块级解析
# ----------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(={1,5})\s+(.*?)\s+(={1,5})\s*$")
_CODE_INDENT = "    "  # 四个空格


def convert(text):
    """把 wiki 源文本转成 HTML 字符串。出错抛 WikiError（含行号）。"""
    text = text.replace("\r\n", "\n")
    out = []
    list_open = False
    code_open = False
    code_start = 0
    code_lines = []

    def flush_list():
        nonlocal list_open
        if list_open:
            out.append("</ul>")
            list_open = False

    def flush_code():
        nonlocal code_open
        out.append("<pre><code>%s</code></pre>" % html.escape("\n".join(code_lines)))
        code_lines.clear()
        code_open = False

    # splitlines()：文件末尾的换行符不会产生幻影空行，
    # 这样"代码块一直延续到文件末尾"才能被正确判定为未闭合。
    for index, line in enumerate(text.splitlines()):
        lineno = index + 1

        if code_open:
            if line.startswith(_CODE_INDENT):
                code_lines.append(line[len(_CODE_INDENT):])
                continue
            flush_code()  # 代码块结束，当前行落到下面按普通规则处理

        if line.startswith(_CODE_INDENT):
            flush_list()
            code_open = True
            code_start = lineno
            code_lines.append(line[len(_CODE_INDENT):])
        elif not line.strip():
            flush_list()
        elif line.startswith("="):
            flush_list()
            m = _HEADING_RE.match(line)
            if m is None or m.group(1) != m.group(3):
                raise WikiError(
                    lineno,
                    "标题等号不成对（左右 = 数量需一致，且等号与文字之间需有空格）",
                )
            level = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (level, parse_inline(m.group(2), lineno), level))
        elif line.startswith("*"):
            if not list_open:
                out.append("<ul>")
                list_open = True
            out.append("<li>%s</li>" % parse_inline(line[1:].strip(), lineno))
        else:
            flush_list()
            out.append("<p>%s</p>" % parse_inline(line.strip(), lineno))

    flush_list()
    if code_open:
        raise WikiError(
            code_start,
            "代码块未闭合（行首四个空格的代码块一直持续到文件末尾）",
        )
    return "\n".join(out)


# ----------------------------------------------------------------------
# 自测
# ----------------------------------------------------------------------

def _self_test():
    # 行内基础
    assert convert("'''粗体'''") == "<p><strong>粗体</strong></p>"
    assert convert("''斜体''") == "<p><em>斜体</em></p>"
    assert convert("[[https://a.b|文字]]") == '<p><a href="https://a.b">文字</a></p>'
    # 嵌套组合：粗体里有斜体和链接
    assert convert("'''粗体里有''斜体''和[[地址|链接]]'''") == (
        '<p><strong>粗体里有<em>斜体</em>和<a href="地址">链接</a></strong></p>'
    )
    # 标题一到五级
    assert convert("= 一 =") == "<h1>一</h1>"
    assert convert("===== 五 =====") == "<h5>五</h5>"
    # 列表里放粗体
    assert convert("* 甲\n* 有'''粗体'''") == (
        "<ul>\n<li>甲</li>\n<li>有<strong>粗体</strong></li>\n</ul>"
    )
    # 代码块不解析格式，且做 HTML 转义
    assert convert("    <b>'''x'''</b>\n\n后续") == (
        "<pre><code>&lt;b&gt;&#x27;&#x27;&#x27;x&#x27;&#x27;&#x27;&lt;/b&gt;</code></pre>\n"
        "<p>后续</p>"
    )
    # 各类错误都必须抛 WikiError 且带行号
    bad_cases = [
        "'''没闭合的粗体",
        "''没闭合的斜体",
        "[[没闭合的链接",
        "== 标题 =",
        "= 没右等号",
        "普通行\n    代码块到文件末尾",
    ]
    for bad in bad_cases:
        try:
            convert(bad)
        except WikiError as exc:
            assert exc.lineno >= 1
        else:
            raise AssertionError("应当报错却没有报错: %r" % bad)
    # 行号定位：错误在第二行
    try:
        convert("第一行没问题\n第二行'''粗体没闭合")
    except WikiError as exc:
        assert exc.lineno == 2, exc.lineno
    else:
        raise AssertionError("应当报错")
    print("[自测] 全部断言通过")


# ----------------------------------------------------------------------
# 示例与演示
# ----------------------------------------------------------------------

SAMPLE_DOC = """\
= wiki 示例文档 =

普通段落：'''粗体'''、''斜体''、[[https://example.com|示例链接]]。

'''粗体里有''斜体''和[[https://example.com|链接]]'''

== 列表 ==
* 第一项
* 第二项里有'''粗体'''
* 第三项

== 代码块 ==
    def hello():
        # 代码块里 '''不解析''' 任何格式，<tag> 原样输出
        print("hello")

代码块之后的段落。
"""

ERROR_SAMPLES = [
    ("粗体未闭合", "这一行的'''粗体没有收尾"),
    ("斜体未闭合", "这一行的''斜体没有收尾"),
    ("链接未闭合", "这一行的[[https://example.com|链接没有收尾"),
    ("标题等号不成对", "== 标题 ="),
    ("代码块未闭合", "普通行\n    代码行一\n    代码行二（文件到此结束，没有后续行收尾）"),
]


def run_demo():
    _self_test()
    print("=" * 60)
    print("【示例文档 wiki 源文】")
    print("=" * 60)
    print(SAMPLE_DOC)
    print("=" * 60)
    print("【转换后的 HTML】")
    print("=" * 60)
    print(convert(SAMPLE_DOC))
    print()
    print("=" * 60)
    print("【错误样例】")
    print("=" * 60)
    for title, src in ERROR_SAMPLES:
        try:
            convert(src)
            print("· %s: 未报错（不应该发生）" % title)
        except WikiError as exc:
            print("· %s -> 转换失败: %s" % (title, exc))


def main(argv):
    if "--demo" in argv:
        run_demo()
        return 0
    if len(argv) > 1:
        with open(argv[1], encoding="utf-8") as f:
            source = f.read()
    else:
        source = sys.stdin.read()
    try:
        print(convert(source))
    except WikiError as exc:
        print("转换失败: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
