import argparse
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler


class MyHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        # POST処理の実装
        content_length = int(self.headers["Content-Length"])
        post_data = self.rfile.read(content_length)
        print(f"{len(post_data)} bytes received.")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "POST OK"}')


def run():
    # コマンドライン引数の定義
    parser = argparse.ArgumentParser(description="Custom HTTP Server")
    parser.add_argument("--directory", "-d", default=".", help="Directory to serve")
    parser.add_argument("port", type=int, nargs="?", default=8000, help="Port to listen on")
    args = parser.parse_args()

    server_address = ("", args.port)

    # functools.partial を使用して、directory 引数をあらかじめ渡したハンドラファクトリを作成
    handler_factory = partial(MyHandler, directory=args.directory)

    httpd = HTTPServer(server_address, handler_factory)
    print(f"Serving HTTP on 0.0.0.0 port {args.port} (from {args.directory}) ...")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()


if __name__ == "__main__":
    run()
