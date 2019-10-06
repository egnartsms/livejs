from http.server import HTTPServer, BaseHTTPRequestHandler


class LiveJsHttpServer(HTTPServer):
    def process_request(self, request, client_address):
        # print("request:", request, "client_address:", client_address)
        return super(LiveJsHttpServer, self).process_request(request, client_address)


class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200, "OK")
        text = 'Got this: ' + self.path.replace('/', ':')
        resp = '''
        <html>
        <head>
          <title>Test server running directly inside Sublime</title>
        </head>
        <body>
          <p>{text}</p>
        </body>
        </html>
        '''.format(text=text)
        resp = resp.encode('utf8')
        self.send_header('Content-Length', len(resp))
        self.end_headers()
        self.wfile.write(resp)
