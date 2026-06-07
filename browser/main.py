from __future__ import annotations

import argparse
import logging
import socket
import ssl
import tkinter
import tkinter.font
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

type DisplayItem = tuple[int, int, str, tkinter.font.Font, str]
type DrawItem = DrawText | DrawRect
type CssRule = tuple[TagSelector | DescendantSelector, dict[str, str]]
type Node = Element | Text


# JST タイムゾーンの設定
def jst_converter(*args: float | None):
    return datetime.now(ZoneInfo("Asia/Tokyo")).timetuple()


# コンバーターを JST に差し替える
logging.Formatter.converter = jst_converter
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class URL:
    def __init__(self, url: str) -> None:
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

    def request(self) -> str:
        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        s.connect((self.host, self.port))

        if self.scheme == "https":
            ctx = ssl.create_default_context()
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            s = ctx.wrap_socket(s, server_hostname=self.host)

        request = f"GET {self.path} HTTP/1.0\r\n"
        request += f"Host: {self.host}\r\n"
        request += "\r\n"
        s.send(request.encode("utf8"))

        response = s.makefile("r", encoding="utf8", newline="\r\n")
        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)
        print(f"ver={version} stat={status} exp={explanation}")

        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        content = response.read()
        s.close()

        return content

    def resolve(self, url: str):
        if "://" in url:
            return URL(url)
        if not url.startswith("/"):
            dir, _ = self.path.rsplit("/", 1)
            while url.startswith("../"):
                _, url = url.split("/", 1)
                if "/" in dir:
                    dir, _ = dir.rsplit("/", 1)
            url = dir + "/" + url
        if url.startswith("//"):
            return URL(self.scheme + ":" + url)
        else:
            return URL(self.scheme + "://" + self.host + ":" + str(self.port) + url)

    def __repr__(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}{self.path}"


class Text:
    def __init__(self, text: str, parent: Element) -> None:
        self.text = text
        self.children = []
        self.parent = parent
        self.style: dict[str, str]

    def __repr__(self) -> str:
        return repr(self.text)


class Element:
    def __init__(self, tag: str, attributes: dict[str, str], parent: Element | None) -> None:
        self.tag = tag
        self.attributes = attributes
        self.children: list[Node] = []
        self.parent = parent
        self.style: dict[str, str]

    def __repr__(self) -> str:
        return "<" + self.tag + ">"


def print_html_tree(node: Node, indent: int = 0):
    print(" " * indent, node)
    for child in node.children:
        print_html_tree(child, indent + 2)


def print_layout_tree(node: DocumentLayout | BlockLayout, indent: int = 0):
    print(" " * indent, node)
    for child in node.children:
        print_layout_tree(child, indent + 2)


def tree_to_list(tree: Node, list: list[Node]):
    list.append(tree)
    for child in tree.children:
        tree_to_list(child, list)
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


FONTS: dict[
    tuple[int, Literal["normal", "bold"], str], tuple[tkinter.font.Font, tkinter.Label]
] = {}


def get_font(
    size: int, weight: Literal["normal", "bold"], style: Literal["roman", "italic"]
) -> tkinter.font.Font:
    key = (size, weight, style)
    if key not in FONTS:
        font = tkinter.font.Font(
            size=size,
            weight=weight,
            slant=style,
        )
        # パフォーマンス向上のためのLabelオブジェクト（Tkinter推奨）
        label = tkinter.Label(font=font)
        FONTS[key] = (font, label)
    return FONTS[key][0]


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
        self.children: list[BlockLayout] = []
        self.display_list: list[DisplayItem] = []
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0

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
            self.cursor_x = 0
            self.cursor_y = 0
            self.weight: Literal["normal", "bold"] = "normal"
            self.style: Literal["roman", "italic"] = "roman"
            self.size = 12

            self.line: list[tuple[int, str, tkinter.font.Font, str]] = []
            self.recurse(self.node)
            self.flush()
        for child in self.children:
            child.layout()
        if mode == "block":
            self.height = sum([child.height for child in self.children])
        else:
            self.height = self.cursor_y

    def recurse(self, node: Node):
        if isinstance(node, Text):
            for word in node.text.split():
                self.word(node, word)
        else:
            if node.tag == "br":
                self.flush()
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
        color = node.style["color"]
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
        w = font.measure(word)

        if self.cursor_x + w > self.width:
            self.flush()

        self.line.append((self.cursor_x, word, font, color))
        self.cursor_x += w + font.measure(" ")

    def flush(self):
        if not self.line:
            return

        # 各単語をベースラインに配置し、ディスプレイリストに追加
        max_ascent = max([font.metrics("ascent") for _, _, font, _ in self.line])
        baseline = int(self.cursor_y + 1.25 * max_ascent)
        for rel_x, word, font, color in self.line:
            x = self.x + rel_x
            y = self.y + baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font, color))

        # 次の行のy座標を更新
        metrics = [font.metrics() for _, _, font, _ in self.line]
        max_descent = max([metric["descent"] for metric in metrics])
        self.cursor_y = int(baseline + 1.25 * max_descent)

        self.cursor_x = 0
        self.line = []

    def paint(self):
        cmds: list[DrawItem] = []

        if self.node.style:
            bgcolor = self.node.style.get("background-color", "transparent")
            if bgcolor != "transparent":
                x2, y2 = self.x + self.width, self.y + self.height
                rect = DrawRect(self.x, self.y, x2, y2, bgcolor)
                cmds.append(rect)

        if self.layout_mode() == "inline":
            for x, y, word, font, color in self.display_list:
                cmds.append(DrawText(x, y, word, font, color))
        return cmds


class DrawText:
    def __init__(self, x1: int, y1: int, text: str, font: tkinter.font.Font, color: str):
        self.top = y1
        self.left = x1
        self.text = text
        self.font = font
        self.bottom = y1 + font.metrics("linespace")
        self.color = color

    def execute(self, scroll: int, canvas: tkinter.Canvas):
        canvas.create_text(
            self.left,
            self.top - scroll,
            text=self.text,
            font=self.font,
            anchor="nw",
            fill=self.color,
        )


class DrawRect:
    def __init__(self, x1: int, y1: int, x2: int, y2: int, color: str):
        self.top = y1
        self.left = x1
        self.bottom = y2
        self.right = x2
        self.color = color

    def execute(self, scroll: int, canvas: tkinter.Canvas):
        canvas.create_rectangle(
            self.left,
            self.top - scroll,
            self.right,
            self.bottom - scroll,
            width=0,
            fill=self.color,
        )


def paint_tree(layout_object: DocumentLayout | BlockLayout, display_list: list[DrawItem]):
    display_list.extend(layout_object.paint())
    for child in layout_object.children:
        paint_tree(child, display_list)


SCROLL_STEP = 100


class Browser:
    def __init__(self, html_tree: bool, layout_tree: bool) -> None:
        self.html_tree = html_tree
        self.layout_tree = layout_tree
        self.width = WIDTH
        self.height = HEIGHT
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window,
            width=self.width,
            height=self.height,
            bg="white",
        )
        self.canvas.pack(
            fill=tkinter.BOTH,  # BOTH: 水平方向と垂直方向に拡張、 X: 水平方向のみ、 Y: 垂直方向のみ
            expand=True,  # 余剰スペースを割り当てる？
        )
        self.scroll = 0
        self.window.bind("<Down>", self.scrolldown)
        self.window.bind("<Button-5>", self.scrolldown)
        self.window.bind("<Up>", self.scrollup)
        self.window.bind("<Button-4>", self.scrollup)
        # self.window.bind("<Configure>", self.window_resize)

    def draw(self):
        self.canvas.delete("all")
        for cmd in self.display_list:
            if cmd.top > self.scroll + self.height:
                continue
            if cmd.bottom < self.scroll:
                continue
            cmd.execute(self.scroll, self.canvas)

    def load(self, url: URL):
        body = url.request()
        self.nodes = HTMLParser(body).parse()
        if self.html_tree:
            print_html_tree(self.nodes)

        css_rules = DEFAULT_STYLE_SHEET.copy()
        links = [
            node.attributes["href"]
            for node in tree_to_list(self.nodes, [])
            if isinstance(node, Element)
            and node.tag == "link"
            and node.attributes.get("rel") == "stylesheet"
            and "href" in node.attributes
        ]
        for link in links:
            style_url = url.resolve(link)
            logging.info(f"css found. [{style_url}]")
            try:
                body = style_url.request()
            except Exception:
                continue
            css_rules.extend(CSSParser(body).parse())
        style(self.nodes, sorted(css_rules, key=cascade_priority))

        self.document = DocumentLayout(self.nodes)
        self.document.layout()
        if self.layout_tree:
            print_layout_tree(self.document)

        self.display_list: list[DrawItem] = []
        paint_tree(self.document, self.display_list)
        self.draw()

    def scrolldown(self, e: tkinter.Event):
        max_y = max(self.document.height + 2 * VSTEP - HEIGHT, 0)
        self.scroll = min(self.scroll + SCROLL_STEP, max_y)
        logging.info(f"scroll={self.scroll}")
        self.draw()

    def scrollup(self, e: tkinter.Event):
        self.scroll -= min(SCROLL_STEP, self.scroll)
        logging.info(f"scroll={self.scroll}")
        self.draw()

    # def window_resize(self, e: tkinter.Event):
    #     logging.info(f"window resize: {e}")
    #     if self.width != e.width or self.height != e.height:
    #         self.width = e.width
    #         self.height = e.height
    #         self.document.layout()
    #         self.draw()


def parse_args() -> argparse.Namespace:
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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    browser = Browser(
        args.html_tree,
        args.layout_tree,
    )
    browser.load(URL(args.url))
    tkinter.mainloop()
