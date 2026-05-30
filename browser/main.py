import logging
import socket
import ssl
import tkinter
import tkinter.font
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo


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


class Text:
    def __init__(self, text: str) -> None:
        self.text = text


class Tag:
    def __init__(self, tag: str) -> None:
        self.tag = tag


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


def lex(body: str) -> list[Text | Tag]:
    out: list[Text | Tag] = []
    buffer = ""
    in_tag = False
    in_ett = False
    ett_name = ""
    for c in body:
        if c == "<":
            in_tag = True
            if buffer:
                out.append(Text(buffer))
                buffer = ""
        elif c == ">":
            in_tag = False
            out.append(Tag(buffer))
            buffer = ""
        elif not in_tag:
            if c == "&":
                in_ett = True
                ett_name = c
            elif c == ";":
                ett_name += c
                in_ett = False
                if ett_name in HTML_ENTITIES:
                    buffer += HTML_ENTITIES[ett_name]
                else:
                    buffer += ett_name
            elif in_ett:
                ett_name += c
            else:
                buffer += c
        else:
            buffer += c
    return out


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


WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18


class Layout:
    def __init__(self, tokens: list[Text | Tag], width: int) -> None:
        self.width = width
        self.line: list[tuple[int, str, tkinter.font.Font]] = []
        self.display_list: list[tuple[int, int, str, tkinter.font.Font]] = []
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.weight: Literal["normal", "bold"] = "normal"
        self.style: Literal["roman", "italic"] = "roman"
        self.size = 12
        self.in_pre = False

        for tok in tokens:
            self.token(tok)
        self.flush()

    def token(self, tok: Text | Tag):
        if isinstance(tok, Text):
            if self.in_pre:
                for line in tok.text.split("\n"):
                    logging.info(f"pre>{line}</pre")
                    if line:
                        self.word(line)
                    else:
                        self.flush()
            else:
                for word in tok.text.split():
                    self.word(word)
        elif tok.tag == "i":
            self.style = "italic"
        elif tok.tag == "/i":
            self.style = "roman"
        elif tok.tag == "b":
            self.weight = "bold"
        elif tok.tag == "/b":
            self.weight = "normal"
        elif tok.tag == "small":
            self.size -= 2
        elif tok.tag == "/small":
            self.size += 2
        elif tok.tag == "big":
            self.size += 4
        elif tok.tag == "/big":
            self.size -= 4
        elif tok.tag == "br":
            self.flush()
        elif tok.tag == "/p":
            self.flush()
            self.cursor_y += VSTEP
        elif tok.tag == 'pre\nclass="sourceCode python"':
            self.in_pre = True
        elif tok.tag == 'pre\nclass="sourceCode python example"':
            self.in_pre = True
        elif tok.tag == 'pre\nclass="sourceCode python output"':
            self.in_pre = True
        elif tok.tag == "/pre":
            self.in_pre = False
            self.flush()

    def word(self, word: str):
        font = get_font(self.size, self.weight, self.style)
        w = font.measure(word)

        if self.cursor_x + w >= self.width - HSTEP:
            self.flush()

        self.line.append((self.cursor_x, word, font))
        self.cursor_x += w + font.measure(" ")

    def flush(self):
        if not self.line:
            return

        # 各単語をベースラインに配置し、ディスプレイリストに追加
        max_ascent = max([font.metrics("ascent") for _, _, font in self.line])
        baseline = self.cursor_y + 1.25 * max_ascent
        for x, word, font in self.line:
            y = int(baseline - font.metrics("ascent"))
            self.display_list.append((x, y, word, font))

        # 次の行のy座標を更新
        metrics = [font.metrics() for _, _, font in self.line]
        max_descent = max([metric["descent"] for metric in metrics])
        self.cursor_y = baseline + 1.25 * max_descent

        self.cursor_x = HSTEP
        self.line = []


SCROLL_STEP = 100


class Browser:
    def __init__(self) -> None:
        self.width = WIDTH
        self.height = HEIGHT
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window,
            width=self.width,
            height=self.height,
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
        self.window.bind("<Configure>", self.window_resize)

    def draw(self):
        self.canvas.delete("all")
        for x, y, word, font in self.display_list:
            if y > self.scroll + self.height:
                continue
            if y + VSTEP < self.scroll:
                continue
            self.canvas.create_text(x, y - self.scroll, text=word, font=font, anchor="nw")

    def load(self, url: URL):
        body = url.request()
        self.tokens = lex(body)
        self.display_list = Layout(self.tokens, self.width).display_list
        self.draw()

    def scrolldown(self, e: tkinter.Event):
        self.scroll += SCROLL_STEP
        logging.info(f"scroll={self.scroll}")
        self.draw()

    def scrollup(self, e: tkinter.Event):
        self.scroll -= min(SCROLL_STEP, self.scroll)
        logging.info(f"scroll={self.scroll}")
        self.draw()

    def window_resize(self, e: tkinter.Event):
        logging.info(f"window resize: {e}")
        if self.width != e.width or self.height != e.height:
            self.width = e.width
            self.height = e.height
            self.display_list = Layout(self.tokens, self.width).display_list
            self.draw()


if __name__ == "__main__":
    import sys

    Browser().load(URL(sys.argv[1]))
    tkinter.mainloop()
