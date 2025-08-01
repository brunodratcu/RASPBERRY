import usocket

def request(method, url, data=None, json=None, headers={}, stream=None):
    try:
        proto, dummy, host, path = url.split('/', 3)
    except ValueError:
        proto, dummy, host = url.split('/', 2)
        path = ''
    if proto == 'http:':
        port = 80
    else:
        raise ValueError('Unsupported protocol: ' + proto)

    if ':' in host:
        host, port = host.split(':', 1)
        port = int(port)

    ai = usocket.getaddrinfo(host, port)[0]
    s = usocket.socket()
    s.connect(ai[-1])
    s.send(bytes('%s /%s HTTP/1.0\r\n' % (method, path), 'utf8'))
    s.send(bytes('Host: %s\r\n' % host, 'utf8'))
    for k in headers:
        s.send(bytes('%s: %s\r\n' % (k, headers[k]), 'utf8'))
    if json is not None:
        import ujson
        data = ujson.dumps(json)
        s.send(b'Content-Type: application/json\r\n')
    if data:
        s.send(bytes('Content-Length: %d\r\n' % len(data), 'utf8'))
    s.send(b'\r\n')
    if data:
        s.send(data)

    l = s.readline()
    protover, status, msg = l.split(None, 2)
    while True:
        l = s.readline()
        if not l or l == b'\r\n':
            break

    return s

def get(url, **kw):
    return request("GET", url, **kw)

def post(url, **kw):
    return request("POST", url, **kw)
