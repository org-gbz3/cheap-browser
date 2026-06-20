import random
import socket
import urllib.parse

ENTRIES = ["Pavel was here"]
SESSIONS: dict[str, dict[str, str]] = {}


def show_comments(session: dict[str, str]):
    out = "<!doctype html>"
    out += "<link rel=stylesheet href=/comment.css>"
    out += "<script src=/comment.js></script>"
    for entry in ENTRIES:
        out += f"<p>{entry}</p>"
    out += "<form action=add method=post>"
    out += "<p><input name=guest></p>"
    out += "<p><button>Sign the book!</button></p>"
    out += "<strong></strong>"
    out += "</form>"
    return out


def form_decode(body: str | None):
    params: dict[str, str] = {}
    if body is None:
        return params
    for field in body.split("&"):
        name, value = field.split("=", 1)
        name = urllib.parse.unquote_plus(name)
        value = urllib.parse.unquote_plus(value)
        params[name] = value
    return params


def add_entry(session: dict[str, str], params: dict[str, str]):
    if "guest" in params and len(params["guest"]) <= 100:
        ENTRIES.append(params["guest"])
    return show_comments(session)


def not_found(url: str, method: str):
    out = "<!doctype html>"
    out += f"<h1>{method} {url} not found!</h1>"
    return out


def do_request(
    session: dict[str, str], method: str, url: str, headers: dict[str, str], body: str | None
):
    if method == "GET" and url == "/":
        return "200 OK", show_comments(session)
    elif method == "GET" and url == "/comment.js":
        with open("comment.js") as f:
            return "200 OK", f.read()
    elif method == "GET" and url == "/comment.css":
        with open("comment.css") as f:
            return "200 OK", f.read()

    elif method == "POST" and url == "/add":
        params = form_decode(body)
        add_entry(session, params)
        return "200 OK", show_comments(session)
    else:
        return "404 Not Found", not_found(url, method)


def handle_connection(conx: socket.socket):
    req = conx.makefile("b", 0)
    reqline = req.readline().decode("utf8")
    method, url, _ = reqline.split(" ", 2)
    assert method in ["GET", "POST"]
    headers: dict[str, str] = {}
    while True:
        line = req.readline().decode("utf8")
        if line == "\r\n":
            break
        header, value = line.split(":", 1)
        headers[header.casefold()] = value.strip()

    if "content-length" in headers:
        length = int(headers["content-length"])
        bbody: bytes = req.read(length)
        body = bbody.decode("utf8")
    else:
        body = None
    if "cookie" in headers:
        token = headers["cookie"][len("token=") :]
    else:
        token = str(random.random())[2:]
    session = SESSIONS.setdefault(token, {})
    status, body = do_request(session, method, url, headers, body)
    response = f"HTTP/1.0 {status}\r\n"
    response += "Content-Length: {}\r\n".format(len(body.encode("utf8")))
    if "cookie" not in headers:
        response += f"Set-Cookie: token={token}\r\n"
    response += "\r\n" + body
    conx.send(response.encode("utf8"))
    conx.close()


s = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

s.bind(("127.0.0.1", 8000))
s.listen()

while True:
    conx, addr = s.accept()
    handle_connection(conx)
