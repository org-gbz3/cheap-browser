import html
import random
import socket
import urllib.parse

SESSIONS: dict[str, dict[str, str]] = {}
LOGINS = {"crashoverride": "0cool", "cerealkiller": "emmanuel"}
ENTRIES = [
    ("No names. We are nameless!", "cerealkiller"),
    ("HACK THE PLANET!!!", "crashoverride"),
]


def show_comments(session: dict[str, str]):
    out = "<!doctype html>"
    out += "<link rel=stylesheet href=/comment.css>"
    for entry, who in ENTRIES:
        out += f"<p>{html.escape(entry)}\n"
        out += f"<i>by {html.escape(who)}</i></p>"

    if "user" in session:
        nonce = str(random.random())[2:]
        session["nonce"] = nonce
        out += "<script src=/comment.js></script>"
        out += f"<h1>Hello, {session['user']}</h1>"
        out += "<form action=add method=post>"
        out += "<p><input name=guest></p>"
        out += "<p><button>Sign the book!</button></p>"
        out += f"<input name=nonce type=hidden value={nonce}>"
        out += "</form>"
        out += "<script src=https://example.com/evil.js></script>"
    else:
        out += "<a href=/login>Sign in to write in the guest book</a>"
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
    if "nonce" not in session or "nonce" not in params:
        print(f"## NG1 session={session} params={params}")
        return
    if session["nonce"] != params["nonce"]:
        print(f"## NG2 session={session} params={params}")
        return
    if "user" not in session:
        return
    if "guest" in params and len(params["guest"]) <= 100:
        ENTRIES.append((params["guest"], session["user"]))
    return show_comments(session)


def not_found(url: str, method: str):
    out = "<!doctype html>"
    out += f"<h1>{method} {url} not found!</h1>"
    return out


def login_form(session: dict[str, str]):
    body = "<!doctype html>"
    body += "<form action=/ method=post>"
    body += "<p>Username: <input name=username></p>"
    body += "<p>Password: <input name=password type=password></p>"
    body += "<p><button>Log in</button></p>"
    body += "</form>"
    return body


def do_login(session: dict[str, str], params: dict[str, str]):
    username = params.get("username")
    password = params.get("password")
    if username in LOGINS and LOGINS[username] == password:
        session["user"] = username
        return "200 OK", show_comments(session)
    else:
        out = "<!doctype html>"
        out += f"<h1>Invalid password for {username}</h1>"
        return "401 Unauthorized", out


def show_count():
    out = "<!doctype html>"
    out += "<div>"
    out += " Let's count up to 99!"
    out += "</div>"
    out += "<div>Output</div>"
    out += "<script src=/eventloop.js></script>"
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
    elif method == "GET" and url == "/login":
        return "200 OK", login_form(session)

    elif method == "GET" and url == "/count":
        return "200 OK", show_count()
    elif method == "GET" and url == "/eventloop.js":
        with open("eventloop.js") as f:
            return "200 OK", f.read()

    elif method == "POST" and url == "/add":
        params = form_decode(body)
        add_entry(session, params)
        return "200 OK", show_comments(session)
    elif method == "POST" and url == "/":
        params = form_decode(body)
        return do_login(session, params)
    else:
        return "404 Not Found", not_found(url, method)


def handle_connection(conx: socket.socket):
    req = conx.makefile("b", 0)
    reqline = req.readline().decode("utf8")
    print(f"reqline=[{reqline}]")
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
    response += "Content-Security-Policy: default-src http://localhost:8000\r\n"
    if "cookie" not in headers:
        response += f"Set-Cookie: token={token}; SameSite=Lax\r\n"
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
