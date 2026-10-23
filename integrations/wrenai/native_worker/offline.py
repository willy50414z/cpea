from contextlib import contextmanager
import ipaddress
import socket


@contextmanager
def loopback_only():
    original_connect=socket.socket.connect
    original_connect_ex=socket.socket.connect_ex
    original_resolve=socket.getaddrinfo
    def allowed(host):
        if host in ('localhost',None): return
        try:
            if ipaddress.ip_address(host).is_loopback: return
        except ValueError: pass
        raise OSError('offline_network_forbidden')
    def connect(sock,address):
        if isinstance(address,tuple): allowed(address[0])
        return original_connect(sock,address)
    def connect_ex(sock,address):
        if isinstance(address,tuple): allowed(address[0])
        return original_connect_ex(sock,address)
    def resolve(host,*args,**kwargs):
        allowed(host)
        return original_resolve(host,*args,**kwargs)
    socket.socket.connect=connect; socket.socket.connect_ex=connect_ex; socket.getaddrinfo=resolve
    try: yield
    finally:
        socket.socket.connect=original_connect; socket.socket.connect_ex=original_connect_ex; socket.getaddrinfo=original_resolve
