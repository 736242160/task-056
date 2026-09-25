#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wiki2html.py — 简易 wiki 标记转 HTML（纯标准库，单文件）。

用法：
    python3 wiki2html.py 输入.wiki              # HTML 输出到标准输出
    python3 wiki2html.py 输入.wiki -o 输出.html # 写入文件
    python3 wiki2html.py --selftest             # 运行内置自测（含示例与错误样例）

支持的标记：
    '''粗体'''                可嵌套 ''斜体'' 和 [[地址|链接]]
    ''斜体''
    [[链接地址|显示文字]]      （"|显示文字" 可省略）
    = 一级标题 =  ～  ===== 五级标题 =====
    行首四个空格               代码块，原样输出，不解析任何格式
    行首 *                    无序列表，条目内可用行内格式

错误报告（输出到 stderr，退出码为 1）：
    粗体/斜体/链接标记未闭合、标题等号不成对、代码块未收尾，
    均会报告行号与对应标记。
"""

import html
import re
import sys

HEADING_RE = re.compile(r"^(=+)\s*(.*?)\s*(=+)\s*$")
MAX_HEADING_LEVEL = 5

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
</head>
<body>
{body}
</body>
</html>
"""


# ---------------------------------------------------------------- 行内解析

def _find_italic_close(text, start):
    """从 start 起寻找斜体结束标记 ''（跳过属于 ''' 的三连引号）。"""
    i = start
    while True:
        j = text.find("''", i)
        if j == -1:
            return -1
        before_ok = j == 0 or text[j - 1] != "'"
        after_ok = j + 2 >= len(text) or text[j + 2] != "'"
        if before_ok and after_ok:
            return j
        i = j + 2


def parse_inline(text, line_no, errors):
    """解析行内格式，返回 HTML；错误追加到 errors。"""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("'''", i):
            end = text.find("'''", i + 3)
            if end == -1:
                errors.append("第 %d 行：粗体标记 ''' 未闭合" % line_no)
                out.append(html.escape(text[i:]))
                break
            inner = parse_inline(text[i + 3:end], line_no, errors)
            out.append("<strong>%s</strong>" % inner)
            i = end + 3
        elif text.startswith("''", i):
            end = _find_italic_close(text, i + 2)
            if end == -1:
                errors.append("第 %d 行：斜体标记 '' 未闭合" % line_no)
                out.append(html.escape(text[i:]))
                break
            inner = parse_inline(text[i + 2:end], line_no, errors)
            out.append("<em>%s</em>" % inner)
            i = end + 2
        elif text.startswith("[[", i):
            end = text.find("]]", i + 2)
            if end == -1:
                errors.append("第 %d 行：链接标记 [[ 未闭合" % line_no)
                out.append(html.escape(text[i:]))
                break
            body = text[i + 2:end]
            url, sep, label = body.partition("|")
            if not sep:
                label = url
            out.append('<a href="%s">%s</a>'
                       % (html.escape(url, quote=True), html.escape(label)))
            i = end + 2
        else:
            out.append(html.escape(text[i]))
            i += 1
    return "".join(out)


# ---------------------------------------------------------------- 块级解析

def convert(text):
    """把 wiki 文本转换为 HTML 片段，返回 (html, errors)。"""
    lines = text.splitlines()
    errors = []
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        line_no = i + 1

        if not line.strip():
            i += 1
            continue

        # 代码块：行首四个空格，原样输出；须由非缩进行（或空行）收尾
        if line.startswith("    "):
            start_no = line_no
            code = []
            while i < n and lines[i].startswith("    "):
                code.append(lines[i][4:])
                i += 1
            if i >= n:
                errors.append(
                    "第 %d 行：代码块未闭合（文件结束时仍在代码块内）" % start_no)
            out.append("<pre><code>%s</code></pre>"
                       % html.escape("\n".join(code)))
            continue

        # 标题：= 标题 = ～ ===== 标题 =====
        if line.startswith("="):
            m = HEADING_RE.match(line)
            if not m:
                errors.append("第 %d 行：标题等号不成对" % line_no)
                i += 1
                continue
            open_eq, title, close_eq = m.groups()
            if len(open_eq) != len(close_eq):
                errors.append(
                    "第 %d 行：标题等号不成对（左侧 %d 个，右侧 %d 个）"
                    % (line_no, len(open_eq), len(close_eq)))
                i += 1
                continue
            level = len(open_eq)
            if level > MAX_HEADING_LEVEL:
                errors.append(
                    "第 %d 行：标题层级 %d 超出范围（仅支持 1-%d 级）"
                    % (line_no, level, MAX_HEADING_LEVEL))
                i += 1
                continue
            if not title.strip():
                errors.append("第 %d 行：标题内容为空" % line_no)
                i += 1
                continue
            out.append("<h%d>%s</h%d>"
                       % (level, parse_inline(title, line_no, errors), level))
            i += 1
            continue

        # 无序列表：行首 *
        if line.startswith("*"):
            items = []
            while i < n and lines[i].startswith("*"):
                items.append((i + 1, lines[i][1:].strip()))
                i += 1
            lis = "\n".join(
                "  <li>%s</li>" % parse_inline(t, ln, errors)
                for ln, t in items)
            out.append("<ul>\n%s\n</ul>" % lis)
            continue

        # 普通段落：连续的非空行合并为一个段落
        para = []
        while (i < n and lines[i].strip()
               and not lines[i].startswith(("    ", "=", "*"))):
            para.append((i + 1, lines[i]))
            i += 1
        inner = "\n".join(parse_inline(t, ln, errors) for ln, t in para)
        out.append("<p>%s</p>" % inner)

    return "\n".join(out), errors


# ---------------------------------------------------------------- 自测样例

SAMPLE_DOC = """\
= 示例文档 =

这是一段'''粗体'''和''斜体''，还有[[https://example.com|示例链接]]。

'''粗体里有''斜体''和[[https://a.b/c|链接]]'''

== 列表示例 ==
* 第一项
* 第二项带'''粗体'''
* 第三项带[[https://example.com|链接]]

    def hello():
        print("代码块原样输出：'''不解析''' <b>标签</b>")

===== 五级标题 =====
"""

ERROR_SAMPLES = [
    ("粗体未闭合", "正常行\n这是'''没闭合的粗体\n"),
    ("斜体未闭合", "这是''没闭合的斜体\n"),
    ("链接未闭合", "这是[[https://example.com|没闭合的链接\n"),
    ("标题等号不成对", "== 标题 =\n"),
    ("代码块未收尾", "前文\n\n    代码行（文件到此结束，没有收尾行）"),
]


def selftest():
    print("=" * 60)
    print("1. 示例文档")
    print("=" * 60)
    print(SAMPLE_DOC)
    html_out, errors = convert(SAMPLE_DOC)
    print("=" * 60)
    print("2. 示例文档转换后的 HTML")
    print("=" * 60)
    print(html_out)
    assert not errors, errors

    print()
    print("=" * 60)
    print("3. 错误样例")
    print("=" * 60)
    for name, doc in ERROR_SAMPLES:
        _, errs = convert(doc)
        print("【%s】输入：%r" % (name, doc))
        for e in errs:
            print("    错误：%s" % e)
        assert errs, "应报告错误：%s" % name

    # ---- 断言检查 ----
    # 嵌套：粗体里有斜体和链接
    out, errs = convert("'''粗体里有''斜体''和[[https://a.b/c|链接]]'''")
    assert not errs
    assert out == ('<p><strong>粗体里有<em>斜体</em>和'
                   '<a href="https://a.b/c">链接</a></strong></p>'), out

    # 斜体里嵌粗体
    out, errs = convert("''斜体里有'''粗体'''结束''")
    assert not errs
    assert out == "<p><em>斜体里有<strong>粗体</strong>结束</em></p>", out

    # 列表里放粗体
    out, errs = convert("* 第一项\n* 第二项带'''粗体'''\n")
    assert not errs
    assert out == ("<ul>\n  <li>第一项</li>\n"
                   "  <li>第二项带<strong>粗体</strong></li>\n</ul>"), out

    # 代码块原样输出，不解析格式
    out, errs = convert("    '''不解析''' <b>标签</b>\n\n")
    assert not errs
    assert out == ("<pre><code>&#x27;&#x27;&#x27;不解析&#x27;&#x27;&#x27; "
                   "&lt;b&gt;标签&lt;/b&gt;</code></pre>"), out

    # 一级到五级标题
    out, errs = convert("= 一 =\n\n== 二 ==\n\n=== 三 ===\n\n"
                        "==== 四 ====\n\n===== 五 =====\n")
    assert not errs
    assert out == ("<h1>一</h1>\n<h2>二</h2>\n<h3>三</h3>\n"
                   "<h4>四</h4>\n<h5>五</h5>"), out

    # 错误定位
    _, errs = convert("正常行\n这是'''没闭合的粗体\n")
    assert errs == ["第 2 行：粗体标记 ''' 未闭合"], errs
    _, errs = convert("== 标题 =\n")
    assert "第 1 行：标题等号不成对" in errs[0], errs
    _, errs = convert("    代码行（文件结束）")
    assert errs == ["第 1 行：代码块未闭合（文件结束时仍在代码块内）"], errs

    print()
    print("全部自测通过 ✔")
    return 0


# ---------------------------------------------------------------- 命令行

def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    if argv[0] == "--selftest":
        return selftest()

    src_path = argv[0]
    out_path = None
    if "-o" in argv[1:]:
        idx = argv.index("-o")
        try:
            out_path = argv[idx + 1]
        except IndexError:
            print("错误：-o 后面需要跟输出文件路径", file=sys.stderr)
            return 2

    with open(src_path, encoding="utf-8") as f:
        text = f.read()
    body, errors = convert(text)
    page = PAGE_TEMPLATE.format(title=html.escape(src_path), body=body)

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(page + "\n")
        print("已写入 %s" % out_path)
    else:
        print(page)

    for e in errors:
        print("错误：%s" % e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
