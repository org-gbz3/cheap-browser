import socket
import ssl


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
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "quot": '"',
    "apos": "'",
    "nbsp": " ",
    "ndash": "–",
    "mdash": "—",
    "copy": "©",
    "reg": "®",
    "trade": "™",
    "asymp": "≈",
    "ne": "≠",
    "pound": "£",
    "euro": "€",
    "deg": "°",
}


def show(body: str):
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
                ett_name = ""
            elif c == ";":
                in_ett = False
                if ett_name in HTML_ENTITIES:
                    print(f"{HTML_ENTITIES[ett_name]}")
                else:
                    print(f"[entity is {ett_name}]")
            elif in_ett:
                ett_name += c
            else:
                print(c, end="")


def load(url: URL):
    body = url.request()
    show(body)


if __name__ == "__main__":
    import sys

    load(URL(sys.argv[1]))
