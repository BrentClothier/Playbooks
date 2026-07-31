#!/usr/bin/env python3
from pathlib import Path


def replace_exact(path: str, old: str, new: str, expected: int) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{path}: expected {expected} matches, found {count}")
    file.write_text(text.replace(old, new))
    print(f"updated {path}: {count} replacements")


def replace_once(path: str, old: str, new: str) -> None:
    replace_exact(path, old, new, 1)


# network.cpp contains separate Windows and POSIX implementations of this
# helper. V10 incorrectly expected only one match and stopped during patching.
# Zero-initialize both native sockaddr_in structures.
replace_exact(
    "src/core/internal_network/network.cpp",
    '''sockaddr TranslateFromSockAddrIn(SockAddrIn input) {\n    sockaddr_in result;''',
    '''sockaddr TranslateFromSockAddrIn(SockAddrIn input) {\n    sockaddr_in result{};''',
    2,
)

# Some Minecraft builds submit an IPv4 sockaddr with len=0. Normalize it for
# consistency. If a wildcard IPv4 bind to the requested port returns EINVAL,
# retry once using an ephemeral host port. The retry is narrowly scoped.
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''    auto addr_in = GetValue<SockAddrIn>(addr);\n\n    return Translate(file_descriptors[fd]->socket->Bind(Translate(addr_in)));\n}\n\nErrno BSD::ConnectImpl''',
    '''    auto addr_in = GetValue<SockAddrIn>(addr);\n    if (addr_in.len == 0 && addr_in.family == static_cast<u8>(Domain::INET)) {\n        LOG_WARNING(Service, "Normalizing IPv4 sockaddr length from 0 to 16 for bind fd={}",\n                    fd);\n        addr_in.len = 16;\n    }\n\n    Errno result = Translate(file_descriptors[fd]->socket->Bind(Translate(addr_in)));\n    const bool is_wildcard_ipv4 =\n        addr_in.family == static_cast<u8>(Domain::INET) && addr_in.ip[0] == 0 &&\n        addr_in.ip[1] == 0 && addr_in.ip[2] == 0 && addr_in.ip[3] == 0;\n    if (result == Errno::INVAL && is_wildcard_ipv4 && addr_in.portno != 0) {\n        const u16 requested_port = addr_in.portno;\n        addr_in.portno = 0;\n        LOG_WARNING(Service,\n                    "IPv4 wildcard bind fd={} returned EINVAL for port_raw={:#x}; "\n                    "retrying with an ephemeral port",\n                    fd, requested_port);\n        result = Translate(file_descriptors[fd]->socket->Bind(Translate(addr_in)));\n        LOG_WARNING(Service, "Ephemeral bind retry fd={} result={}", fd,\n                    static_cast<u32>(result));\n    }\n    return result;\n}\n\nErrno BSD::ConnectImpl''',
)
