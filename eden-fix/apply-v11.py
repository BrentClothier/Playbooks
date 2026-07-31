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


# Track whether a socket has been connected. Linux auto-binds an unconnected
# UDP socket even when send() fails with EDESTADDRREQ. Horizon's behavior used
# by Minecraft leaves the socket unbound, allowing the following bind() call.
replace_once(
    "src/core/hle/service/sockets/bsd.h",
    '''        s32 flags = 0;\n        bool is_connection_based = false;\n    };''',
    '''        s32 flags = 0;\n        bool is_connection_based = false;\n        bool is_connected = false;\n    };''',
)

# Accepted stream sockets are already connected.
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''    new_descriptor.socket = std::move(result.socket);\n    new_descriptor.is_connection_based = descriptor.is_connection_based;\n\n    const SockAddrIn guest_addr_in = Translate(result.sockaddr_in);''',
    '''    new_descriptor.socket = std::move(result.socket);\n    new_descriptor.is_connection_based = descriptor.is_connection_based;\n    new_descriptor.is_connected = true;\n\n    const SockAddrIn guest_addr_in = Translate(result.sockaddr_in);''',
)

# Mark sockets connected after a successful connect (including ISCONN, which
# this implementation normalizes to success).
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''    const Errno result = Translate(file_descriptors[fd]->socket->Connect(Translate(addr_in)));\n\n    if (result == Errno::ISCONN) {\n        LOG_DEBUG(Service, "returned ISCONN - socket already connected");\n        return Errno::SUCCESS;\n    }\n\n    return result;''',
    '''    const Errno result = Translate(file_descriptors[fd]->socket->Connect(Translate(addr_in)));\n\n    if (result == Errno::ISCONN) {\n        LOG_DEBUG(Service, "returned ISCONN - socket already connected");\n        file_descriptors[fd]->is_connected = true;\n        return Errno::SUCCESS;\n    }\n    if (result == Errno::SUCCESS) {\n        file_descriptors[fd]->is_connected = true;\n    }\n\n    return result;''',
)

# Do not call the Linux host send() for an unconnected datagram socket. The
# host call auto-binds the socket before returning EDESTADDRREQ, which makes
# Minecraft's subsequent explicit bind fail with EINVAL.
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''    if (!file_descriptors[fd]->socket) {\n        LOG_WARNING(Service, "Uninitialized socket");\n        return {-1, Errno::BADF};\n    }\n    return Translate(file_descriptors[fd]->socket->Send(message, flags));\n}\n\nstd::pair<s32, Errno> BSD::SendToImpl''',
    '''    if (!file_descriptors[fd]->socket) {\n        LOG_WARNING(Service, "Uninitialized socket");\n        return {-1, Errno::BADF};\n    }\n    const FileDescriptor& descriptor = *file_descriptors[fd];\n    if (!descriptor.is_connection_based && !descriptor.is_connected) {\n        LOG_WARNING(Service,\n                    "Returning DESTADDRREQ for unconnected datagram fd={} without host send",\n                    fd);\n        return {-1, Errno::DESTADDRREQ};\n    }\n    return Translate(descriptor.socket->Send(message, flags));\n}\n\nstd::pair<s32, Errno> BSD::SendToImpl''',
)

# Preserve connection state when duplicating a descriptor.
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''        .flags = file_descriptors[fd]->flags,\n        .is_connection_based = file_descriptors[fd]->is_connection_based,\n    };''',
    '''        .flags = file_descriptors[fd]->flags,\n        .is_connection_based = file_descriptors[fd]->is_connection_based,\n        .is_connected = file_descriptors[fd]->is_connected,\n    };''',
)
