from __future__ import annotations

import argparse
import ctypes
import logging
import math
import socket
import ssl
import sys
import threading
import time
import urllib.parse
from collections.abc import Callable
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import dukpy
import sdl2
import skia

type DisplayItem = tuple[int, int, str, skia.Typeface, str]
type DrawItem = DrawText | DrawRect | DrawRRect | DrawOutline | DrawLine | DrawText | Blend
type CssRule = tuple[TagSelector | DescendantSelector, dict[str, str]]
type Node = Element | Text
type Layout = DocumentLayout | BlockLayout | LineLayout | InputLayout | TextLayout
type Focusable = Literal["address bar", "content"] | None


# JST タイムゾーンの設定
def jst_converter(*args: float | None):
    return datetime.now(ZoneInfo("Asia/Tokyo")).timetuple()


# コンバーターを JST に差し替える
logging.Formatter.converter = jst_converter
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

COOKIE_JAR: dict[str, tuple[str, dict[str, str]]] = {}


class URL:
    def __init__(self, url: str, skip_ssl_verify: bool) -> None:
        self.skip_ssl_verify = skip_ssl_verify
        self.scheme, url = url.split("://", 1)
        assert self.scheme in ["http", "https"]

        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443
        if "/" not in url:
            url = url + "/"
        self.host, url = url.split("/", 1)
        self.path = "/" + url

        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

    def request(self, referrer: URL | None, payload: str | None = None):
        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        s.connect((self.host, self.port))

        if self.scheme == "https":
            ctx = ssl.create_default_context()
            if self.skip_ssl_verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            s = ctx.wrap_socket(s, server_hostname=self.host)

        method = "POST" if payload else "GET"
        request = f"{method} {self.path} HTTP/1.0\r\n"
        request += f"Host: {self.host}\r\n"
        if payload:
            length = len(payload.encode("utf8"))
            request += f"Content-Length: {length}\r\n"
        if self.host in COOKIE_JAR:
            cookie, params = COOKIE_JAR[self.host]
            allow_cookie = True
            if referrer and params.get("samesite", "none") == "lax":
                if method != "GET":
                    allow_cookie = self.host == referrer.host
            if allow_cookie:
                request += f"Cookie: {cookie}\r\n"
        request += "\r\n"
        if payload:
            request += payload
        s.send(request.encode("utf8"))

        response = s.makefile("r", encoding="utf8", newline="\r\n")
        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)
        print(f"ver={version} stat={status} exp={explanation}")

        response_headers: dict[str, str] = {}
        while True:
            line = response.readline()
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        if "set-cookie" in response_headers:
            cookie = response_headers["set-cookie"]
            params: dict[str, str] = {}
            if ";" in cookie:
                cookie, rest = cookie.split(";", 1)
                for param in rest.split(";"):
                    if "=" in param:
                        param, value = param.split("=", 1)
                    else:
                        value = "true"
                    params[param.strip().casefold()] = value.casefold()
            COOKIE_JAR[self.host] = (cookie, params)
        content = response.read()
        s.close()

        return response_headers, content

    def resolve(self, url: str):
        if "://" in url:
            return URL(url, self.skip_ssl_verify)
        if not url.startswith("/"):
            dir, _ = self.path.rsplit("/", 1)
            while url.startswith("../"):
                _, url = url.split("/", 1)
                if "/" in dir:
                    dir, _ = dir.rsplit("/", 1)
            url = dir + "/" + url
        if url.startswith("//"):
            return URL(self.scheme + ":" + url, self.skip_ssl_verify)
        else:
            return URL(
                self.scheme + "://" + self.host + ":" + str(self.port) + url, self.skip_ssl_verify
            )

    def origin(self):
        return f"{self.scheme}://{self.host}:{str(self.port)}"

    def __repr__(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}{self.path}"

    def __str__(self):
        port_part = ":" + str(self.port)
        if self.scheme == "https" and self.port == 443:
            port_part = ""
        if self.scheme == "http" and self.port == 80:
            port_part = ""
        return self.scheme + "://" + self.host + port_part + self.path


class Text:
    def __init__(self, text: str, parent: Element) -> None:
        self.text = text
        self.children = []
        self.parent = parent
        self.style: dict[str, str]
        self.is_focused: bool = False

    def __repr__(self) -> str:
        return repr(self.text)


class Element:
    def __init__(self, tag: str, attributes: dict[str, str], parent: Element | None) -> None:
        self.tag = tag
        self.attributes = attributes
        self.children: list[Node] = []
        self.parent = parent
        self.style: dict[str, str]
        self.is_focused: bool = False

    def __repr__(self) -> str:
        return "<" + self.tag + ">"


def print_html_tree(node: Node, indent: int = 0):
    print(" " * indent, node)
    for child in node.children:
        print_html_tree(child, indent + 2)


def print_layout_tree(node: Layout, indent: int = 0):
    print(" " * indent, node)
    for child in node.children:
        print_layout_tree(child, indent + 2)


def node_tree_to_list(tree: Node, list: list[Node]):
    list.append(tree)
    for child in tree.children:
        node_tree_to_list(child, list)
    return list


def layout_tree_to_list(tree: Layout, list: list[Layout]):
    list.append(tree)
    for child in tree.children:
        layout_tree_to_list(child, list)
    return list


class HTMLParser:
    SELF_CLOSING_TAGS = [
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    ]
    HTML_ENTITIES = {
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&apos;": "'",
        "&nbsp;": " ",
        "&ndash;": "–",
        "&mdash;": "—",
        "&copy;": "©",
        "&reg;": "®",
        "&trade;": "™",
        "&asymp;": "≈",
        "&ne;": "≠",
        "&pound;": "£",
        "&euro;": "€",
        "&deg;": "°",
        "&#39;": '"',
    }
    HEAD_TAGS = [
        "base",
        "basefont",
        "bgsound",
        "noscript",
        "link",
        "meta",
        "title",
        "style",
        "script",
    ]

    def __init__(self, body: str) -> None:
        self.body = body
        self.unfinished: list[Element] = []

    def parse(self):
        text = ""
        in_tag = False
        for c in self.body:
            if c == "<":
                in_tag = True
                if text:
                    self.add_text(text)
                text = ""
            elif c == ">":
                in_tag = False
                self.add_tag(text)
                text = ""
            else:
                text += c
                if c == ";":
                    # HTMLエンティティを文字列に変換
                    for k, v in self.HTML_ENTITIES.items():
                        if text.endswith(k):
                            text = text[: -(len(k))] + v
        if not in_tag and text:
            self.add_text(text)
        return self.finish()

    def add_text(self, text: str):
        if text.isspace():
            return
        self.implicit_tags(None)
        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)

    def add_tag(self, tag: str):
        tag, attributes = self.get_attributes(tag)
        if tag.startswith("!"):
            return
        self.implicit_tags(tag)
        if tag.startswith("/"):
            if len(self.unfinished) == 1:
                return
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        elif tag in self.SELF_CLOSING_TAGS:
            parent = self.unfinished[-1]
            node = Element(tag, attributes, parent)
            parent.children.append(node)
        else:
            parent = self.unfinished[-1] if self.unfinished else None
            node = Element(tag, attributes, parent)
            self.unfinished.append(node)

    def finish(self):
        if not self.unfinished:
            self.implicit_tags(None)
        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        return self.unfinished.pop()

    def get_attributes(self, text: str) -> tuple[str, dict[str, str]]:
        parts = text.split()
        tag = parts[0].casefold()
        attributes: dict[str, str] = {}
        for attrpair in parts[1:]:
            if "=" in attrpair:
                key, value = attrpair.split("=", 1)
                if len(value) > 2 and value[0] in ["'", '"']:
                    value = value[1:-1]
                attributes[key.casefold()] = value
            else:
                attributes[attrpair.casefold()] = ""
        return tag, attributes

    def implicit_tags(self, tag: str | None):
        while True:
            open_tags = [node.tag for node in self.unfinished]
            if open_tags == [] and tag != "html":
                self.add_tag("html")
            elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
                if tag in self.HEAD_TAGS:
                    self.add_tag("head")
                else:
                    self.add_tag("body")
            elif open_tags == ["html", "head"] and tag not in ["/head"] + self.HEAD_TAGS:
                self.add_tag("/head")
            else:
                break


class CSSParser:
    def __init__(self, s: str):
        self.s = s
        self.i = 0

    def whitespace(self):
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def word(self) -> str:
        start = self.i
        while self.i < len(self.s):
            # プロパティ名として有効な文字の間はiを進める
            if self.s[self.i].isalnum() or self.s[self.i] in "#-.%":
                self.i += 1
            else:
                break
        if not (self.i > start):
            raise Exception("Parsing error")
        return self.s[start : self.i]

    def literal(self, literal: str):
        if not (self.i < len(self.s) and self.s[self.i] == literal):
            raise Exception("Parsing error")
        self.i += 1

    def pair(self) -> tuple[str, str]:
        prop = self.word()
        self.whitespace()
        self.literal(":")
        self.whitespace()
        val = self.word()
        return prop.casefold(), val

    def body(self) -> dict[str, str]:
        pairs: dict[str, str] = {}
        while self.i < len(self.s) and self.s[self.i] != "}":
            try:
                prop, val = self.pair()
                pairs[prop.casefold()] = val
                self.whitespace()
                self.literal(";")
                self.whitespace()
            except Exception:
                why = self.ignore_until([";", "}"])
                if why == ";":
                    self.literal(why)
                    self.whitespace()
                else:
                    break
        return pairs

    def ignore_until(self, chars: list[str]) -> str | None:
        while self.i < len(self.s):
            if self.s[self.i] in chars:
                return self.s[self.i]
            else:
                self.i += 1
        return None

    def selector(self):
        out = TagSelector(self.word().casefold())
        self.whitespace()
        while self.i < len(self.s) and self.s[self.i] != "{":
            tag = self.word()
            descendant = TagSelector(tag.casefold())
            out = DescendantSelector(out, descendant)
            self.whitespace()
        return out

    def parse(self):
        rules: list[CssRule] = []
        while self.i < len(self.s):
            try:
                self.whitespace()
                selector = self.selector()
                self.literal("{")
                self.whitespace()
                body = self.body()
                self.literal("}")
                rules.append((selector, body))
            except Exception:
                why = self.ignore_until(["}"])
                if why == "}":
                    self.literal("}")
                    self.whitespace()
                else:
                    break
        return rules


class TagSelector:
    def __init__(self, tag: str):
        self.tag = tag
        self.priority = 1

    def __repr__(self) -> str:
        return self.tag

    def matches(self, node: Node):
        return isinstance(node, Element) and self.tag == node.tag


class DescendantSelector:
    def __init__(self, ancestor: TagSelector | DescendantSelector, descendant: TagSelector):
        self.ancestor = ancestor  # 先祖
        self.descendant = descendant  # 子孫
        self.priority = ancestor.priority + descendant.priority

    def __repr__(self) -> str:
        return f"{self.ancestor} {self.descendant}"

    def matches(self, node: Node) -> bool:
        # `p a` の a か？
        if not self.descendant.matches(node):
            return False

        while node.parent:
            # root まで親を辿り、一致する先祖を探す
            if self.ancestor.matches(node.parent):
                return True
            node = node.parent

        return False


FONTS: dict[tuple[Literal["normal", "bold"], str], skia.Typeface] = {}


def get_font(size: int, weight: Literal["normal", "bold"], style: Literal["roman", "italic"]):
    key = (weight, style)
    if key not in FONTS:
        if weight == "bold":
            skia_weight = skia.FontStyle.kBold_Weight
        else:
            skia_weight = skia.FontStyle.kNormal_Weight
        if style == "italic":
            skia_style = skia.FontStyle.kItalic_Slant
        else:
            skia_style = skia.FontStyle.kUpright_Slant
        skia_width = skia.FontStyle.kNormal_Width
        style_info = skia.FontStyle(skia_weight, skia_width, skia_style)
        font = skia.Typeface("Arial", style_info)
        FONTS[key] = font
    return skia.Font(FONTS[key], size)


def linespace(font: skia.Font):
    metrics = font.getMetrics()
    return int(metrics.fDescent - metrics.fAscent)


NAMED_COLORS = {
    "black": "#000000",
    "white": "#ffffff",
    "gray": "#808080",
    "red": "#ff0000",
    "green": "#00ff00",
    "blue": "#0000ff",
    "lightblue": "#add8e6",
    "lightgreen": "#90ee90",
    "orange": "#ffa500",
    "orangered": "#ff4500",
}


def parse_color(color: str) -> int:
    if color.startswith("#") and len(color) == 7:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        return skia.Color(r, g, b)
    elif color.startswith("#") and len(color) == 4:
        r = int(color[1] * 2, 16)
        g = int(color[2] * 2, 16)
        b = int(color[3] * 2, 16)
        return skia.Color(r, g, b)
    elif color.startswith("#") and len(color) == 9:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        a = int(color[7:9], 16)
        return skia.Color(r, g, b, a)
    elif color in NAMED_COLORS:
        return parse_color(NAMED_COLORS[color])
    else:
        logging.debug(f"parse_color: unsupported color '{color}'")
        return skia.ColorTRANSPARENT


def parse_blend_mode(blend_mode_str: str | None):
    if blend_mode_str == "multiply":
        return skia.BlendMode.kMultiply
    elif blend_mode_str == "difference":
        return skia.BlendMode.kDifference
    elif blend_mode_str == "destination-in":
        return skia.BlendMode.kDstIn
    elif blend_mode_str == "source-over":
        return skia.BlendMode.kSrcOver
    else:
        return skia.BlendMode.kSrcOver


REFRESH_RATE_SEC = 0.033


class MeasureTime:
    def __init__(self):
        self.file = open("browser.trace", "w")
        self.file.write('{"traceEvents": [')
        ts = time.time() * 1000000
        self.file.write(
            f'{{ "name": "process_name", "ph": "M", "ts": {str(ts)}, "pid": 1, '
            + '"cat": "__metadata", "args": {"name": "Cheap-Browser"}}'
        )
        self.file.flush()

    def time(self, name: str):
        ts = time.time() * 1000000
        self.file.write(
            f', {{ "ph": "B", "cat": "_", "name": "{name}", "ts": {str(ts)}, "pid": 1, "tid": 1}}'
        )
        self.file.flush()
        return MeasureTime.Span(self, name)

    def stop(self, name: str):
        ts = time.time() * 1000000
        self.file.write(
            f', {{ "ph": "E", "cat": "_", "name": "{name}", "ts": {str(ts)}, "pid": 1, "tid": 1}}'
        )
        self.file.flush()

    def finish(self):
        self.file.write("]}")
        self.file.close()

    class Span:
        def __init__(self, measure: MeasureTime, name: str):
            self.measure = measure
            self.name = name

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            self.measure.stop(self.name)


class Task:
    def __init__(self, task_code: Callable[..., None], args: tuple[object, ...]):
        self.task_code = task_code
        self.args = args

    def run(self):
        self.task_code(*self.args)
        del self.task_code
        del self.args


class TaskRunner:
    def __init__(self, tab: Tab):
        self.tab = tab
        self.tasks: list[Task] = []
        self.condition = threading.Condition()

    def schedule_task(self, task: Task):
        with self.condition:
            self.tasks.append(task)
            self.condition.notify_all()

    def run(self):
        task = None
        with self.condition:
            if len(self.tasks) > 0:
                task = self.tasks.pop(0)
        if task:
            task.run()

        with self.condition:
            if len(self.tasks) == 0:
                pass
                # TODO self.condition.wait()


DEFAULT_STYLE_SHEET = CSSParser(open("browser/browser.css").read()).parse()
INHERITED_PROPERTIES = {
    "font-size": "16px",
    "font-style": "normal",
    "font-weight": "normal",
    "color": "black",
}


def style(node: Node, rules: list[CssRule]):
    node.style = {}

    # 継承されるスタイルを適用。
    for prop, default_val in INHERITED_PROPERTIES.items():
        if node.parent and node.parent.style and prop in node.parent.style:
            node.style[prop] = node.parent.style[prop]
        else:
            node.style[prop] = default_val

    # スタイルシートをWebページに適用。
    for selector, body in rules:
        if not selector.matches(node):
            continue
        for prop, val in body.items():
            node.style[prop] = val

    # style属性をパースしWebページに適用。
    # スタイルシートで定義されたスタイルは上書き。
    if isinstance(node, Element) and "style" in node.attributes:
        pairs = CSSParser(node.attributes["style"]).body()
        for property, value in pairs.items():
            node.style[property] = value

    # %指定のフォントサイズは、親のフォントサイズから算出
    if node.style["font-size"].endswith("%"):
        if node.parent and node.parent.style and "font-size" in node.parent.style:
            parent_font_size = node.parent.style["font-size"]
        else:
            parent_font_size = INHERITED_PROPERTIES["font-size"]
        parent_px = float(parent_font_size[:-2])
        node_pct = float(node.style["font-size"][:-1]) / 100
        node.style["font-size"] = str(node_pct * parent_px) + "px"

    for child in node.children:
        style(child, rules)


def cascade_priority(rule: CssRule):
    selector, _ = rule
    return selector.priority


WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18


BLOCK_ELEMENTS = [
    "html",
    "body",
    "article",
    "section",
    "nav",
    "aside",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hgroup",
    "header",
    "footer",
    "address",
    "p",
    "hr",
    "pre",
    "blockquote",
    "ol",
    "ul",
    "menu",
    "li",
    "dl",
    "dt",
    "dd",
    "figure",
    "figcaption",
    "main",
    "div",
    "table",
    "form",
    "fieldset",
    "legend",
    "details",
    "summary",
]


class DocumentLayout:
    def __init__(self, node: Element) -> None:
        self.node = node
        self.parent = None
        self.children: list[BlockLayout] = []
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0

    def layout(self):
        child = BlockLayout(self.node, self, None)
        self.children.append(child)
        self.width = WIDTH - 2 * HSTEP
        self.x = HSTEP
        self.y = VSTEP
        child.layout()
        self.display_list = child.display_list
        self.height = child.height

    def paint(self) -> list[DrawItem]:
        return []

    def should_paint(self):
        return True

    def paint_effects(self, cmds: list[DrawItem]):
        return cmds

    def __repr__(self) -> str:
        return repr(self.node)


class BlockLayout:
    def __init__(
        self,
        node: Node,
        parent: BlockLayout | DocumentLayout,
        previous: BlockLayout | None,
    ) -> None:
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children: list[BlockLayout | LineLayout] = []
        self.display_list: list[DisplayItem] = []
        self.x = 0
        self.y: int = 0
        self.width = 0
        self.height: int = 0

    def __repr__(self) -> str:
        return repr(self.node) + f" >> display_list={self.display_list}"

    def layout_mode(self):
        if isinstance(self.node, Text):
            return "inline"
        elif any(
            [
                isinstance(child, Element) and child.tag in BLOCK_ELEMENTS
                for child in self.node.children
            ]
        ):
            return "block"
        elif self.node.children or self.node.tag == "input":
            return "inline"
        elif self.node.children:
            return "inline"
        else:
            return "block"

    def layout(self):
        self.x = self.parent.x
        self.width = self.parent.width
        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y
        mode = self.layout_mode()
        if mode == "block":
            previous = None
            for child in self.node.children:
                next = BlockLayout(child, self, previous)
                self.children.append(next)
                previous = next
        else:
            self.weight: Literal["normal", "bold"] = "normal"
            self.style: Literal["roman", "italic"] = "roman"
            self.size = 12

            self.new_line()
            self.recurse(self.node)

        for child in self.children:
            child.layout()
        self.height = sum([child.height for child in self.children])

    def recurse(self, node: Node):
        if isinstance(node, Text):
            for word in node.text.split():
                self.word(node, word)
        else:
            if node.tag == "br":
                self.new_line()
            elif node.tag == "input" or node.tag == "button":
                self.input(node)
            else:
                for child in node.children:
                    self.recurse(child)

    # def token(self, tok: Text | Element):
    #     if isinstance(tok, Text):
    #         if self.in_pre:
    #             for line in tok.text.split("\n"):
    #                 if line:
    #                     self.word(line)
    #                 else:
    #                     self.flush()
    #         else:
    #             for word in tok.text.split():
    #                 self.word(word)
    #     elif tok.tag == 'pre\nclass="sourceCode python"':
    #         self.in_pre = True
    #     elif tok.tag == 'pre\nclass="sourceCode python example"':
    #         self.in_pre = True
    #     elif tok.tag == 'pre\nclass="sourceCode python output"':
    #         self.in_pre = True
    #     elif tok.tag == "/pre":
    #         self.in_pre = False
    #         self.flush()

    def word(self, node: Text, word: str):
        weight = node.style["font-weight"]
        if weight not in ("normal", "bold"):
            raise ValueError(f"invalid font-weight: {weight}")

        style = node.style["font-style"]
        if style == "normal":
            style = "roman"
        if style not in ("roman", "italic"):
            raise ValueError(f"invalid font-style: {style}")

        size = int(float(node.style["font-size"][:-2]) * 0.75)
        font = get_font(size, weight, style)
        w = font.measureText(word)

        if self.cursor_x + w > self.width:
            self.new_line()

        assert isinstance(self.children[-1], LineLayout)
        line = self.children[-1]
        previous_word = line.children[-1] if line.children else None
        text = TextLayout(node, word, line, previous_word)
        line.children.append(text)
        self.cursor_x += w + font.measureText(" ")

    def new_line(self):
        self.cursor_x = 0
        last_line = (
            self.children[-1]
            if self.children and isinstance(self.children[-1], LineLayout)
            else None
        )
        new_line = LineLayout(self.node, self, last_line)
        self.children.append(new_line)

    def self_rect(self):
        return skia.Rect.MakeLTRB(self.x, self.y, self.x + self.width, self.y + self.height)

    def paint(self):
        cmds: list[DrawItem] = []

        if isinstance(self.node, Element) and self.node.tag == "pre":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRect(skia.Rect.MakeLTRB(self.x, self.y, x2, y2), "gray")
            cmds.append(rect)

        if self.node.style:
            bgcolor = self.node.style.get("background-color", "transparent")
            if bgcolor != "transparent":
                # rect = DrawRect(self.self_rect(), bgcolor)
                # cmds.append(rect)
                radius = float(self.node.style.get("border-radius", "0px")[:-2])
                cmds.append(DrawRRect(self.self_rect(), radius, bgcolor))

        return cmds

    def input(self, node: Element):
        w = INPUT_WIDTH_PX
        if self.cursor_x + w > self.width:
            self.new_line()

        assert isinstance(self.children[-1], LineLayout)
        line = self.children[-1]
        previous_word = line.children[-1] if line.children else None
        input = InputLayout(node, line, previous_word)
        line.children.append(input)

        weight = node.style["font-weight"]
        if weight not in ("normal", "bold"):
            raise ValueError(f"invalid font-weight: {weight}")

        style = node.style["font-style"]
        if style == "normal":
            style = "roman"
        if style not in ("roman", "italic"):
            raise ValueError(f"invalid font-style: {style}")

        size = int(float(node.style["font-size"][:-2]) * 0.75)
        font = get_font(size, weight, style)

        self.cursor_x += w + font.measureText(" ")

    def should_paint(self):
        return isinstance(self.node, Text) or (
            self.node.tag != "input" and self.node.tag != "button"
        )

    def paint_effects(self, cmds: list[DrawItem]):
        cmds = paint_visual_effects(self.node, cmds, self.self_rect())
        return cmds


def paint_visual_effects(node: Node, cmds: list[DrawItem], rect: skia.Rect) -> list[DrawItem]:
    opacity = float(node.style.get("opacity", "1.0"))
    blend_mode = node.style.get("mix-blend-mode")
    if node.style.get("overflow", "visible") == "clip":
        if not blend_mode:
            blend_mode = "source-over"
        border_radius = float(node.style.get("border-radius", "0px")[:-2])
        cmds.append(Blend(1.0, "destination-in", [DrawRRect(rect, border_radius, "white")]))

    return [Blend(opacity, blend_mode, cmds)]


class LineLayout:
    def __init__(self, node: Node, parent: BlockLayout, previous: LineLayout | None):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children: list[TextLayout | InputLayout] = []

    def layout(self):
        self.width = self.parent.width
        self.x = self.parent.x
        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        for word in self.children:
            word.layout()

        max_ascent = max([-word.font.getMetrics().fAscent for word in self.children], default=0)
        baseline = int(self.y + 1.25 * max_ascent)
        for word in self.children:
            word.y = int(baseline + word.font.getMetrics().fAscent)
        max_descent = max([word.font.getMetrics().fDescent for word in self.children], default=0)
        self.height = int(1.25 * (max_ascent + max_descent))

    def paint(self) -> list[DrawItem]:
        return []

    def paint_effects(self, cmds: list[DrawItem]):
        return cmds

    def should_paint(self):
        return True


class TextLayout:
    def __init__(
        self, node: Text, word: str, parent: LineLayout, previous: TextLayout | InputLayout | None
    ):
        self.node = node
        self.word = word
        self.children = []
        self.parent = parent
        self.previous = previous
        self.y = 0

    def layout(self):
        weight = self.node.style["font-weight"]
        if weight not in ("normal", "bold"):
            raise ValueError(f"invalid font-style: {weight}")

        style = self.node.style["font-style"]
        if style == "normal":
            style = "roman"
        if style not in ("roman", "italic"):
            raise ValueError(f"invalid font-style: {style}")

        size = int(float(self.node.style["font-size"][:-2]) * 0.75)
        self.font = get_font(size, weight, style)

        self.width = self.font.measureText(self.word)
        if self.previous:
            space = self.previous.font.measureText(" ")
            self.x = self.previous.x + self.previous.width + space
        else:
            self.x = self.parent.x

        self.height = linespace(self.font)

    def paint(self) -> list[DrawItem]:
        color = self.node.style["color"]
        return [DrawText(self.x, self.y, self.word, self.font, color)]

    def paint_effects(self, cmds: list[DrawItem]):
        return cmds

    def should_paint(self):
        return True


INPUT_WIDTH_PX = 200


class InputLayout:
    def __init__(
        self,
        node: Element,
        parent: BlockLayout | LineLayout,
        previous: TextLayout | InputLayout | None,
    ):
        self.node = node
        self.children = []
        self.parent = parent
        self.previous = previous
        self.y = 0

    def self_rect(self):
        return skia.Rect.MakeLTRB(self.x, self.y, self.x + self.width, self.y + self.height)

    def layout(self):
        weight = self.node.style["font-weight"]
        if weight not in ("normal", "bold"):
            raise ValueError(f"invalid font-style: {weight}")

        style = self.node.style["font-style"]
        if style == "normal":
            style = "roman"
        if style not in ("roman", "italic"):
            raise ValueError(f"invalid font-style: {style}")

        size = int(float(self.node.style["font-size"][:-2]) * 0.75)
        self.font = get_font(size, weight, style)

        self.width = INPUT_WIDTH_PX
        if self.previous:
            space = self.previous.font.measureText(" ")
            self.x = self.previous.x + self.previous.width + space
        else:
            self.x = self.parent.x

        self.height = linespace(self.font)

    def paint(self):
        cmds: list[DrawItem] = []
        bgcolor = self.node.style.get("background-color", "transparent")
        if bgcolor != "transparent":
            rect = DrawRect(self.self_rect(), bgcolor)
            cmds.append(rect)

        text = ""
        if self.node.tag == "input":
            text = self.node.attributes.get("value", "")
        elif self.node.tag == "button":
            if len(self.node.children) == 1 and isinstance(self.node.children[0], Text):
                text = self.node.children[0].text
            else:
                print("Ignoring HTML contents inside button")

        if self.node.is_focused:
            cx = self.x + self.font.measureText(text)
            cmds.append(DrawLine(cx, self.y, cx, self.y + self.height, "black", 1))

        color = self.node.style["color"]
        cmds.append(DrawText(self.x, self.y, text, self.font, color))
        return cmds

    def paint_effects(self, cmds: list[DrawItem]):
        return cmds

    def should_paint(self):
        return True


class DrawText:
    def __init__(self, x1: int, y1: int, text: str, font: skia.Font, color: str):
        self.text = text
        self.font = font
        self.top = y1
        self.left = x1
        self.right = x1 + font.measureText(text)
        self.bottom = y1 + linespace(font)
        self.rect = skia.Rect.MakeLTRB(x1, y1, self.right, self.bottom)
        self.color = color

    def execute(self, canvas: skia.Canvas):
        paint = skia.Paint(AntiAlias=True, Color=parse_color(self.color))
        baseline = self.top - self.font.getMetrics().fAscent
        canvas.drawString(self.text, float(self.left), baseline, self.font, paint)


class DrawRect:
    def __init__(self, rect: skia.Rect, color: str):
        self.color = color
        self.rect = rect

    def execute(self, canvas: skia.Canvas):
        paint = skia.Paint(Color=parse_color(self.color))
        canvas.drawRect(self.rect, paint)


class DrawRRect:
    def __init__(self, rect: skia.Rect, radius: float, color: str):
        self.rect = rect
        self.rrect = skia.RRect.MakeRectXY(rect, radius, radius)
        self.color = color

    def execute(self, canvas: skia.Canvas):
        sk_color = parse_color(self.color)
        canvas.drawRRect(self.rrect, paint=skia.Paint(Color=sk_color))


class DrawOutline:
    def __init__(self, rect: skia.Rect, color: str, thickness: float):
        self.rect = rect
        self.color = color
        self.thickness = thickness

    def execute(self, canvas: skia.Canvas):
        paint = skia.Paint(
            Color=parse_color(self.color),
            StrokeWidth=self.thickness,
            Style=skia.Paint.kStroke_Style,
        )
        canvas.drawRect(self.rect, paint)


class DrawLine:
    def __init__(self, x1: int, y1: int, x2: int, y2: int, color: str, thickness: float):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.rect = skia.Rect.MakeLTRB(x1, y1, x2, y2)
        self.color = color
        self.thickness = thickness

    def execute(self, canvas: skia.Canvas):
        path = skia.Path().moveTo(self.x1, self.y1).lineTo(self.x2, self.y2)
        paint = skia.Paint(
            Color=parse_color(self.color),
            StrokeWidth=self.thickness,
            Style=skia.Paint.kStroke_Style,
        )
        canvas.drawPath(path, paint)


class Blend:
    def __init__(self, opacity: float, blend_mode: str | None, children: list[DrawItem]):
        self.opacity = opacity
        self.blend_mode = blend_mode
        self.should_save = self.blend_mode or self.opacity < 1
        self.children = children
        self.rect = skia.Rect.MakeEmpty()
        for cmd in self.children:
            self.rect.join(cmd.rect)

    def execute(self, canvas: skia.Canvas):
        paint = skia.Paint(
            Alphaf=self.opacity,
            BlendMode=parse_blend_mode(self.blend_mode),
        )
        if self.should_save:
            canvas.saveLayer(None, paint)
        for cmd in self.children:
            cmd.execute(canvas)
        if self.should_save:
            canvas.restore()


def paint_tree(layout_object: Layout, display_list: list[DrawItem]):
    cmds: list[DrawItem] = []
    if layout_object.should_paint():
        cmds = layout_object.paint()
    for child in layout_object.children:
        paint_tree(child, cmds)

    if layout_object.should_paint():
        cmds = layout_object.paint_effects(cmds)
    display_list.extend(cmds)


EVENT_DISPATCH_JS = "new Node(dukpy.handle).dispatchEvent(new Event(dukpy.type))"
RUNTIME_JS = open("browser/runtime.js").read()
SETTIMEOUT_JS = "__runSetTimeout(dukpy.handle)"
XHR_ONLOAD_JS = "__runXHROnload(dukpy.out, dukpy.handle)"


class JSContext:
    def __init__(self, tab: Tab):
        self.tab = tab
        self.interp = dukpy.JSInterpreter()
        with self.tab.browser.measure.time("js-runtime"):
            self.interp.evaljs(RUNTIME_JS)
        self.interp.export_function("log", print)
        self.interp.export_function("querySelectorAll", self.querySelectorAll)
        self.interp.export_function("getAttribute", self.getAttribute)
        self.interp.export_function("innerHTML_set", self.innerHTML_set)
        self.interp.export_function("XMLHttpRequest_send", self.XMLHttpRequest_send)
        self.interp.export_function("setTimeout", self.setTimeout)
        self.interp.export_function("requestAnimationFrame", self.requestAnimationFrame)
        self.node_to_handle: dict[Element, int] = {}
        self.handle_to_node: dict[int, Element] = {}
        self.discarded = False

    def run(self, script: str, code: str):
        try:
            with self.tab.browser.measure.time("js-load"):
                self.interp.evaljs(code)
        except dukpy.JSRuntimeError as e:
            print(f"Script {script} crashed.", e)

    def querySelectorAll(self, selector_text: str):
        selector = CSSParser(selector_text).selector()
        nodes = [
            node
            for node in node_tree_to_list(self.tab.nodes, [])
            if selector.matches(node) and isinstance(node, Element)
        ]
        return [self.get_handle(node) for node in nodes]

    def get_handle(self, elt: Element):
        if elt not in self.node_to_handle:
            handle = len(self.node_to_handle)
            self.node_to_handle[elt] = handle
            self.handle_to_node[handle] = elt
        else:
            handle = self.node_to_handle[elt]
        return handle

    def getAttribute(self, handle: int, attr: str):
        elt = self.handle_to_node[handle]
        return elt.attributes.get(attr, "")

    def dispatch_event(self, type: str, elt: Element):
        handle = self.node_to_handle.get(elt, -1)
        do_default = self.interp.evaljs(EVENT_DISPATCH_JS, type=type, handle=handle)  # type: ignore[reportUnknownArgumentType]
        return not do_default

    def innerHTML_set(self, handle: int, s: str):
        doc = HTMLParser(f"<html><body>{s}</body></html>").parse()
        new_nodes = doc.children[0].children
        elt = self.handle_to_node[handle]
        elt.children = new_nodes
        for child in elt.children:
            child.parent = elt
        self.tab.set_needs_render()

    def XMLHttpRequest_send(self, method: str, url: str, body: str, isasync: bool, handle: int):
        assert self.tab.url
        full_url = self.tab.url.resolve(url)
        if not self.tab.allowed_request(full_url):
            raise Exception("Cross-origin XHR blocked by CSP")
        if full_url.origin() != self.tab.url.origin():
            raise Exception("Cross-origin XHR request not allowed")

        def run_load():
            _, out = full_url.request(self.tab.url, body)
            task = Task(self.dispatch_xhr_onload, (out, handle))
            self.tab.task_runner.schedule_task(task)
            return out

        if not isasync:
            return run_load()
        else:
            threading.Thread(target=run_load).start()

    def dispatch_xhr_onload(self, out: str, handle: int):
        if self.discarded:
            return
        with self.tab.browser.measure.time("js-xhr"):
            self.interp.evaljs(XHR_ONLOAD_JS, out=out, handle=handle)

    def dispatch_settimeout(self, handle: int):
        if self.discarded:
            return
        with self.tab.browser.measure.time("js-settimeout"):
            self.interp.evaljs(SETTIMEOUT_JS, handle=handle)

    def setTimeout(self, handle: int, time: int):
        def run_callback():
            task = Task(self.dispatch_settimeout, (handle,))
            self.tab.task_runner.schedule_task(task)

        threading.Timer(time / 1000.0, run_callback).start()

    def requestAnimationFrame(self):
        self.tab.browser.set_needs_animation_frame(self.tab)


SCROLL_STEP = 100


class Tab:
    def __init__(
        self, browser: Browser, tab_height: int, html_tree: bool, layout_tree: bool
    ) -> None:
        self.html_tree = html_tree
        self.layout_tree = layout_tree
        self.width = WIDTH
        self.height = HEIGHT
        self.scroll = 0
        self.tab_height = tab_height
        self.history: list[URL] = []
        self.focus: Element | None = None
        self.url: URL | None = None
        self.task_runner = TaskRunner(self)
        self.js: JSContext | None = None
        self.needs_render = False
        self.browser = browser

    def raster(self, canvas: skia.Canvas):
        for cmd in self.display_list:
            cmd.execute(canvas)

    def allowed_request(self, url: URL):
        return self.allowed_origins is None or url.origin() in self.allowed_origins

    def load(self, url: URL, payload: str | None = None):
        self.history.append(url)
        headers, body = url.request(self.url, payload)
        self.url = url

        logging.info(f"loading [{url}]")
        self.nodes = HTMLParser(body).parse()
        if self.html_tree:
            print_html_tree(self.nodes)

        self.allowed_origins: list[str] | None = None
        if "content-security-policy" in headers:
            csp = headers["content-security-policy"].split()
            if len(csp) > 0 and csp[0] == "default-src":
                self.allowed_origins = []
                for origin in csp[1:]:
                    self.allowed_origins.append(URL(origin, url.skip_ssl_verify).origin())

        scripts = [
            node.attributes["src"]
            for node in node_tree_to_list(self.nodes, [])
            if isinstance(node, Element) and node.tag == "script" and "src" in node.attributes
        ]
        if self.js:
            self.js.discarded = True
        self.js = JSContext(self)
        for script in scripts:
            script_url = url.resolve(script)
            if not self.allowed_request(script_url):
                logging.error(f"Blocked script {script_url} due to CSP")
                continue
            logging.info(f"script found. [{script_url}]")
            try:
                _, body = script_url.request(url)
            except Exception:
                continue
            task = Task(self.js.run, (script_url, body))
            self.task_runner.schedule_task(task)

        self.rules = DEFAULT_STYLE_SHEET.copy()
        links = [
            node.attributes["href"]
            for node in node_tree_to_list(self.nodes, [])
            if isinstance(node, Element)
            and node.tag == "link"
            and node.attributes.get("rel") == "stylesheet"
            and "href" in node.attributes
        ]
        for link in links:
            style_url = url.resolve(link)
            if not self.allowed_request(style_url):
                logging.error(f"Blocked stylesheet {style_url} due to CSP")
                continue
            logging.info(f"css found. [{style_url}]")
            try:
                _, body = style_url.request(url)
            except Exception:
                continue
            self.rules.extend(CSSParser(body).parse())
        self.set_needs_render()

    def render(self):
        assert self.js
        self.js.interp.evaljs("__runRAFHandlers()")
        if not self.needs_render:
            return

        with self.browser.measure.time("render"):
            style(self.nodes, sorted(self.rules, key=cascade_priority))

            self.document = DocumentLayout(self.nodes)
            self.document.layout()
            if self.layout_tree:
                print_layout_tree(self.document)

            self.display_list: list[DrawItem] = []
            paint_tree(self.document, self.display_list)
            self.needs_render = False
            self.browser.set_needs_raster_and_draw()

    def scrolldown(self):
        max_y = max(self.document.height + 2 * VSTEP - self.tab_height, 0)
        self.scroll = min(self.scroll + SCROLL_STEP, max_y)
        logging.info(f"scroll={self.scroll}")

    def scrollup(self):
        self.scroll -= min(SCROLL_STEP, self.scroll)
        logging.info(f"scroll={self.scroll}")

    # def window_resize(self, e: tkinter.Event):
    #     logging.info(f"window resize: {e}")
    #     if self.width != e.width or self.height != e.height:
    #         self.width = e.width
    #         self.height = e.height
    #         self.document.layout()
    #         self.draw()

    def click(self, x: int, y: int):
        logging.info(f"clicked. x={x} y={y}")
        self.render()
        self.focus = None
        y += self.scroll
        objs = [
            obj
            for obj in layout_tree_to_list(self.document, [])
            if obj.x <= x < obj.x + obj.width and obj.y <= y < obj.y + obj.height
        ]
        if not objs:
            return

        # 最後（一番手前）の要素をクリックしたと想定
        elt = objs[-1].node
        logging.info(f"clicked. elt=[{elt}]")

        # ルートに向かってリンク要素を探す
        while elt:
            if isinstance(elt, Text):
                pass
            elif elt.tag == "a" and "href" in elt.attributes:
                assert self.js
                if self.js.dispatch_event("click", elt):
                    return
                assert self.url
                url = self.url.resolve(elt.attributes["href"])
                return self.load(url)
            elif elt.tag == "input":
                assert self.js
                if self.js.dispatch_event("click", elt):
                    return
                elt.attributes["value"] = ""
                if self.focus:
                    self.focus.is_focused = False
                self.focus = elt
                elt.is_focused = True
                self.set_needs_render()
                return
            elif elt.tag == "button":
                assert self.js
                if self.js.dispatch_event("click", elt):
                    return
                while elt:
                    if elt.tag == "form" and "action" in elt.attributes:
                        return self.submit_form(elt)
                    elt = elt.parent
            elt = elt.parent

    def go_back(self):
        if len(self.history) > 1:
            self.history.pop()
            back = self.history.pop()
            self.load(back)

    def keypress(self, char: str):
        if self.focus:
            assert self.js
            if self.js.dispatch_event("keydown", self.focus):
                return
            self.focus.attributes["value"] += char
            self.set_needs_render()

    def submit_form(self, elt: Element):
        assert self.js
        if self.js.dispatch_event("submit", elt):
            return
        inputs = [
            node
            for node in node_tree_to_list(elt, [])
            if isinstance(node, Element) and node.tag == "input" and "name" in node.attributes
        ]
        body = ""
        for input in inputs:
            name = input.attributes["name"]
            value = input.attributes.get("value", "")
            name = urllib.parse.quote(name)
            body += f"&{name}={value}"
        body = body[1:]
        assert self.url
        url = self.url.resolve(elt.attributes["action"])
        self.load(url, body)

    def set_needs_render(self):
        self.needs_render = True
        self.browser.set_needs_animation_frame(self)


class Chrome:
    def __init__(self, browser: Browser):
        self.browser = browser
        self.font = get_font(20, "normal", "roman")
        self.font_height = linespace(self.font)
        self.padding = 5
        self.tabbar_top = 0
        self.tabbar_bottom = self.font_height + 2 * self.padding
        plus_width = self.font.measureText("+") + 2 * self.padding
        self.newtab_rect = skia.Rect.MakeLTRB(
            self.padding,
            self.padding,
            self.padding + plus_width,
            self.padding + self.font_height,
        )
        self.urlbar_top = self.tabbar_bottom
        self.urlbar_bottom = self.urlbar_top + self.font_height + 2 * self.padding
        self.bottom = self.urlbar_bottom
        back_width = self.font.measureText("<") + 2 * self.padding
        self.back_rect = skia.Rect.MakeLTRB(
            self.padding,
            self.urlbar_top + self.padding,
            self.padding + back_width,
            self.urlbar_bottom - self.padding,
        )
        self.address_rect = skia.Rect.MakeLTRB(
            self.back_rect.top() + self.padding,
            self.urlbar_top + self.padding,
            WIDTH - self.padding,
            self.urlbar_bottom - self.padding,
        )
        self.focus: Focusable = None
        self.address_bar = ""

    def tab_rect(self, i: int):
        tabs_start = self.newtab_rect.right() + self.padding
        tab_width = self.font.measureText("Tab X") + 2 * self.padding
        return skia.Rect.MakeLTRB(
            tabs_start + tab_width * i,
            self.tabbar_top,
            tabs_start + tab_width * (i + 1),
            self.tabbar_bottom,
        )

    def paint(self):
        cmds: list[DrawItem] = []
        cmds.append(DrawRect(skia.Rect.MakeLTRB(0, 0, WIDTH, self.bottom), "white"))
        cmds.append(DrawLine(0, self.bottom, WIDTH, self.bottom, "black", 1))
        cmds.append(DrawOutline(self.newtab_rect, "black", 1))
        cmds.append(
            DrawText(
                self.newtab_rect.left() + self.padding,
                self.newtab_rect.top(),
                "+",
                self.font,
                "black",
            )
        )
        cmds.append(DrawOutline(self.back_rect, "black", 1))
        cmds.append(
            DrawText(
                self.back_rect.left() + self.padding, self.back_rect.top(), "<", self.font, "black"
            )
        )
        cmds.append(DrawOutline(self.address_rect, "black", 1))
        for i, tab in enumerate(self.browser.tabs):
            bounds = self.tab_rect(i)
            cmds.append(DrawLine(bounds.left(), 0, bounds.left(), bounds.bottom(), "black", 1))
            cmds.append(DrawLine(bounds.right(), 0, bounds.right(), bounds.bottom(), "black", 1))
            cmds.append(
                DrawText(
                    bounds.left() + self.padding,
                    bounds.top() + self.padding,
                    f"Tab {i}",
                    self.font,
                    "black",
                )
            )
            if tab == self.browser.active_tab:
                cmds.append(
                    DrawLine(0, bounds.bottom(), bounds.left(), bounds.bottom(), "black", 1)
                )
                cmds.append(
                    DrawLine(bounds.right(), bounds.bottom(), WIDTH, bounds.bottom(), "black", 1)
                )
        if self.focus == "address bar":
            cmds.append(
                DrawText(
                    self.address_rect.left() + self.padding,
                    self.address_rect.top(),
                    self.address_bar,
                    self.font,
                    "black",
                )
            )
            w = self.font.measureText(self.address_bar)
            cmds.append(
                DrawLine(
                    self.address_rect.left() + self.padding + w,
                    self.address_rect.top(),
                    self.address_rect.left() + self.padding + w,
                    self.address_rect.bottom(),
                    "red",
                    1,
                )
            )
        else:
            url = str(self.browser.active_tab.url)
            cmds.append(
                DrawText(
                    self.address_rect.left() + self.padding,
                    self.address_rect.top(),
                    url,
                    self.font,
                    "black",
                )
            )
        return cmds

    def click(self, x: int, y: int):
        self.focus = None
        if self.newtab_rect.contains(x, y):
            default_url = URL("https://browser.engineering/", self.browser.skip_ssl_verify)
            self.browser.new_tab(default_url, self.browser.html_tree, self.browser.layout_tree)
        elif self.back_rect.contains(x, y):
            self.browser.active_tab.go_back()
        elif self.address_rect.contains(x, y):
            self.focus = "address bar"
            self.address_bar = ""

    def keypress(self, char: str):
        if self.focus == "address bar":
            self.address_bar += char
            return True
        return False

    def enter(self):
        if self.focus == "address bar":
            self.browser.active_tab.load(URL(self.address_bar, self.browser.skip_ssl_verify))
            self.focus = None
            return True
        return False

    def blur(self):
        self.focus = None


class Browser:
    def __init__(self, html_tree: bool, layout_tree: bool, skip_ssl_verify: bool):
        self.measure = MeasureTime()
        self.animation_timer = None
        self.tabs: list[Tab] = []
        self.active_tab: Tab
        self.sdl_window = sdl2.SDL_CreateWindow(
            b"Browser",
            sdl2.SDL_WINDOWPOS_CENTERED,
            sdl2.SDL_WINDOWPOS_CENTERED,
            WIDTH,
            HEIGHT,
            sdl2.SDL_WINDOW_SHOWN,
        )
        self.root_surface = skia.Surface.MakeRaster(
            skia.ImageInfo.Make(
                WIDTH,
                HEIGHT,
                ct=skia.kRGBA_8888_ColorType,
                at=skia.kUnpremul_AlphaType,
            )
        )
        self.url: URL
        self.chrome = Chrome(self)
        self.html_tree = html_tree
        self.layout_tree = layout_tree
        self.skip_ssl_verify = skip_ssl_verify
        self.focus: Focusable = None
        _big_endian = sdl2.SDL_BYTEORDER == sdl2.SDL_BIG_ENDIAN
        self.RED_MASK = 0xFF000000 if _big_endian else 0x000000FF
        self.GREEN_MASK = 0x00FF0000 if _big_endian else 0x0000FF00
        self.BLUE_MASK = 0x0000FF00 if _big_endian else 0x00FF0000
        self.ALPHA_MASK = 0x000000FF if _big_endian else 0xFF000000

        self.chrome_surface = skia.Surface(WIDTH, math.ceil(self.chrome.bottom))
        self.tab_surface: skia.Surface | None = None
        self.needs_raster_and_draw = False
        self.needs_animation_frame = True

    def handle_down(self):
        self.active_tab.scrolldown()
        self.draw()

    def handle_up(self):
        self.active_tab.scrollup()
        self.draw()

    def handle_click(self, e: sdl2.SDL_MouseButtonEvent):
        if e.y < self.chrome.bottom:
            self.focus = None
            self.chrome.click(e.x, e.y)
            self.set_needs_raster_and_draw()
        else:
            self.focus = "content"
            self.chrome.blur()
            url = self.active_tab.url
            tab_y = e.y - self.chrome.bottom
            self.active_tab.click(e.x, tab_y)
            if self.active_tab.url != url:
                self.raster_tab()
        self.draw()

    def handle_key(self, e: sdl2.SDL_KeyboardEvent):
        if len(e.char) == 0:
            return
        if not (0x20 <= ord(e.char) < 0x7F):
            return
        if self.chrome.keypress(e.char):
            self.set_needs_raster_and_draw()
        elif self.focus == "content":
            self.active_tab.keypress(e.char)
            self.draw()

    def handle_enter(self):
        if self.chrome.enter():
            self.set_needs_raster_and_draw()

    def handle_quit(self):
        self.measure.finish()
        sdl2.SDL_DestroyWindow(self.sdl_window)

    def raster_tab(self):
        tab_height = math.ceil(self.active_tab.document.height + 2 * VSTEP)
        if not self.tab_surface or tab_height != self.tab_surface.height():
            self.tab_surface = skia.Surface(WIDTH, tab_height)

        canvas = self.tab_surface.getCanvas()
        canvas.clear(skia.ColorWHITE)
        self.active_tab.raster(canvas)

    def raster_chrome(self):
        canvas = self.chrome_surface.getCanvas()
        canvas.clear(skia.ColorWHITE)
        for cmd in self.chrome.paint():
            cmd.execute(canvas)

    def draw(self):
        canvas = self.root_surface.getCanvas()
        canvas.clear(skia.ColorWHITE)

        tab_rect = skia.Rect.MakeLTRB(0, self.chrome.bottom, WIDTH, HEIGHT)
        tab_offset = self.chrome.bottom - self.active_tab.scroll
        canvas.save()
        canvas.clipRect(tab_rect)
        canvas.translate(0, tab_offset)
        assert self.tab_surface
        self.tab_surface.draw(canvas, 0, 0)
        canvas.restore()

        chrome_rect = skia.Rect.MakeLTRB(0, 0, WIDTH, self.chrome.bottom)
        canvas.save()
        canvas.clipRect(chrome_rect)
        self.chrome_surface.draw(canvas, 0, 0)
        canvas.restore()

        skia_image = self.root_surface.makeImageSnapshot()
        skia_bytes = skia_image.tobytes()
        depth = 32  # ピクセルごとのビット数（４バイト）
        pitch = 4 * WIDTH  # 行ごとのバイト数
        pixel_buffer = (ctypes.c_uint8 * len(skia_bytes)).from_buffer_copy(skia_bytes)
        sdl_surface = sdl2.SDL_CreateRGBSurfaceFrom(
            ctypes.cast(pixel_buffer, ctypes.c_void_p),
            WIDTH,
            HEIGHT,
            depth,
            pitch,
            self.RED_MASK,
            self.GREEN_MASK,
            self.BLUE_MASK,
            self.ALPHA_MASK,
        )
        rect = sdl2.SDL_Rect(0, 0, WIDTH, HEIGHT)
        window_surface = sdl2.SDL_GetWindowSurface(self.sdl_window)
        # 実際にコピーを行っているのは SDL_BlitSurface です
        sdl2.SDL_BlitSurface(sdl_surface, rect, window_surface, rect)
        sdl2.SDL_UpdateWindowSurface(self.sdl_window)

    def set_needs_raster_and_draw(self):
        self.needs_raster_and_draw = True

    def raster_and_draw(self):
        if not self.needs_raster_and_draw:
            return
        with self.measure.time("raster/draw"):
            self.raster_chrome()
            self.raster_tab()
            self.draw()
        self.needs_raster_and_draw = False

    def new_tab(self, url: URL, html_tree: bool, layout_tree: bool):
        canvas = self.root_surface.getCanvas()
        new_tab = Tab(self, HEIGHT - self.chrome.bottom, html_tree, layout_tree)
        self.active_tab = new_tab
        new_tab.load(url)
        self.tabs.append(new_tab)
        new_tab.render()
        self.raster_and_draw()
        for cmd in self.chrome.paint():
            cmd.execute(canvas)

    def schedule_animation_frame(self):
        def callback():
            self.needs_animation_frame = False
            self.animation_timer = None
            active_tab = self.active_tab
            task = Task(active_tab.render, ())
            active_tab.task_runner.schedule_task(task)

        if self.needs_animation_frame and not self.animation_timer:
            self.animation_timer = threading.Timer(REFRESH_RATE_SEC, callback)
            self.animation_timer.start()

    def set_needs_animation_frame(self, tab: Tab):
        if tab == self.active_tab:
            self.needs_animation_frame = True


def mainloop(browser: Browser):
    event = sdl2.SDL_Event()
    while True:
        while sdl2.SDL_PollEvent(ctypes.byref(event)) != 0:
            if event.type == sdl2.SDL_QUIT:
                browser.handle_quit()
                sdl2.SDL_Quit()
                sys.exit()
            elif event.type == sdl2.SDL_MOUSEBUTTONUP:
                browser.handle_click(event.button)
            elif event.type == sdl2.SDL_KEYDOWN:
                if event.key.keysym.sym == sdl2.SDLK_RETURN:
                    browser.handle_enter()
                elif event.key.keysym.sym == sdl2.SDLK_DOWN:
                    browser.handle_down()
                elif event.key.keysym.sym == sdl2.SDLK_UP:
                    browser.handle_up()
            elif event.type == sdl2.SDL_TEXTINPUT:
                browser.handle_key(event.text.text.decode("utf8"))
        browser.active_tab.task_runner.run()
        browser.raster_and_draw()
        browser.schedule_animation_frame()


def parse_args():
    parser = argparse.ArgumentParser(
        prog="cheap-browser",
        description="A tiny educational browser",
    )
    parser.add_argument("url", help="例: https://example.com")
    parser.add_argument(
        "--html-tree",
        action="store_true",
        help="HTMLツリーを出力",
    )
    parser.add_argument(
        "--layout-tree",
        action="store_true",
        help="レイアウトツリーを出力",
    )
    parser.add_argument(
        "--skip-ssl-verify",
        action="store_true",
        help="証明書の検証をスキップ",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sdl2.SDL_Init(sdl2.SDL_INIT_EVENTS)
    browser = Browser(
        args.html_tree,
        args.layout_tree,
        args.skip_ssl_verify,
    )
    browser.new_tab(
        URL(args.url, browser.skip_ssl_verify),
        browser.html_tree,
        browser.layout_tree,
    )
    mainloop(browser)
