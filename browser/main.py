import logging
import socket
import ssl
import tkinter
from datetime import datetime
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
}


def lex(body: str) -> str:
    text = ""
    in_tag = False
    in_ett = False
    ett_name = ""
    for c in body:
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            if c == "&":
                in_ett = True
                ett_name = c
            elif c == ";":
                ett_name += c
                in_ett = False
                if ett_name in HTML_ENTITIES:
                    text += HTML_ENTITIES[ett_name]
                else:
                    text += ett_name
            elif in_ett:
                ett_name += c
            else:
                text += c
    return text


WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18


def layout(text: str, width: int) -> list[tuple[int, int, str]]:
    display_list: list[tuple[int, int, str]] = []
    cursor_x, cursor_y = HSTEP, VSTEP
    for c in text:
        display_list.append((cursor_x, cursor_y, c))
        cursor_x += HSTEP
        if cursor_x >= width - HSTEP:
            cursor_y += VSTEP
            cursor_x = HSTEP
    return display_list


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
        for x, y, c in self.display_list:
            if y > self.scroll + self.height:
                continue
            if y + VSTEP < self.scroll:
                continue
            self.canvas.create_text(x, y - self.scroll, text=c)

    def load(self, url: URL):
        body = url.request()
        self.text = lex(body)
        self.display_list = layout(self.text, self.width)
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
            self.display_list = layout(self.text, self.width)
            self.draw()


if __name__ == "__main__":
    import sys

    Browser().load(URL(sys.argv[1]))
    tkinter.mainloop()
