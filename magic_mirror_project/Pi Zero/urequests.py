# urequests.py (versão simples)
import usocket as socket
import ujson as json

class Response:
    def __init__(self, sock):
        self.sock = sock
        self._buffer = b""

    def close(self):
        try:
            self.sock.close()
        except:
            pass

    def json(self):
        data = self.read()
        try:
            return json.loads(data)
        except:
            return None

    def read(self):
        # lê todo o socket
        res = b""
        try:
            while True:
                d = self.sock.recv(1024)
                if not d:
                    break
                res += d
        except:
            pass
        # separa headers e body
        parts = res.split(b"\r\n\r\n", 1)
        if len(parts) == 2:
            return parts[1].decode()
        return res.decode()

def request(method, url, data=None, headers=None):
    if headers is None:
        headers = {}
    proto, dummy, host, path = url.split('/', 3)
    host_port = host
    if ':' in host_port:
        host, port = host_port.split(':', 1)
        port = int(port)
    else:
        port = 80
    s = socket.socket()
    ai = socket.getaddrinfo(host, port)[0][-1]
    s.connect(ai)
    req = "{} /{} HTTP/1.0\r\nHost: {}\r\n".format(method, path, host_port)
    for k,v in headers.items():
        req += "{}: {}\r\n".format(k, v)
    if data:
        if isinstance(data, dict):
            body = json.dumps(data)
            req += "Content-Type: application/json\r\n"
        else:
            body = data
        req += "Content-Length: {}\r\n".format(len(body))
    req += "\r\n"
    s.send(req.encode())
    if data:
        s.send(body.encode())
    return Response(s)

def get(url, **kw):
    return request("GET", url, **kw)

def post(url, **kw):
    return request("POST", url, **kw)

def delete(url, **kw):
    return request("DELETE", url, **kw)
