#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}")
    file.write_text(text.replace(old, new, 1))
    print(f"updated {path}")


replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''    type = static_cast<Type>(static_cast<u32>(type) & ~0x20000000);\n\n    const s32 fd = FindFreeFileDescriptorHandle();''',
    '''    type = static_cast<Type>(static_cast<u32>(type) & ~0x20000000);\n\n    if (domain != Domain::Unspecified && domain != Domain::INET) {\n        LOG_WARNING(Service, "Unsupported socket domain={}, returning AFNOSUPPORT",\n                    static_cast<u32>(domain));\n        return {-1, Errno::AFNOSUPPORT};\n    }\n\n    const s32 fd = FindFreeFileDescriptorHandle();''',
)

replace_once(
    "src/core/hle/service/sockets/sockets.h",
    '''    PIPE = 32,\n    MSGSIZE = 90,\n    CONNABORTED = 103,''',
    '''    PIPE = 32,\n    DESTADDRREQ = 89,\n    MSGSIZE = 90,\n    AFNOSUPPORT = 97,\n    CONNABORTED = 103,''',
)

replace_once(
    "src/core/hle/service/sockets/sockets_translate.cpp",
    '''    case Network::Errno::PIPE:\n        return Errno::PIPE;\n    case Network::Errno::CONNREFUSED:''',
    '''    case Network::Errno::PIPE:\n        return Errno::PIPE;\n    case Network::Errno::DESTADDRREQ:\n        return Errno::DESTADDRREQ;\n    case Network::Errno::AFNOSUPPORT:\n        return Errno::AFNOSUPPORT;\n    case Network::Errno::CONNREFUSED:''',
)

replace_once(
    "src/core/internal_network/network.h",
    '''    INPROGRESS,\n    ISCONN,\n    OTHER,''',
    '''    INPROGRESS,\n    ISCONN,\n    DESTADDRREQ,\n    AFNOSUPPORT,\n    OTHER,''',
)

replace_once(
    "src/core/internal_network/network.cpp",
    '''    case WSAENOTCONN:\n        return Errno::NOTCONN;\n    case WSAEWOULDBLOCK:''',
    '''    case WSAENOTCONN:\n        return Errno::NOTCONN;\n    case WSAEDESTADDRREQ:\n        return Errno::DESTADDRREQ;\n    case WSAEAFNOSUPPORT:\n        return Errno::AFNOSUPPORT;\n    case WSAEWOULDBLOCK:''',
)

replace_once(
    "src/core/internal_network/network.cpp",
    '''    case ENOTCONN:\n        return Errno::NOTCONN;\n    case EAGAIN:''',
    '''    case ENOTCONN:\n        return Errno::NOTCONN;\n    case EDESTADDRREQ:\n        return Errno::DESTADDRREQ;\n    case EAFNOSUPPORT:\n        return Errno::AFNOSUPPORT;\n    case EAGAIN:''',
)
