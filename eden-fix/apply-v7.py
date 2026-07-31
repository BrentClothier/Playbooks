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


# Preserve the v6 socket-domain and errno fixes.
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

# The guest SockAddrIn storage type is 0x100 bytes, but its `len` field is 16
# for IPv4. Return only the actual sockaddr length and never enlarge the IPC
# output beyond the buffer supplied by the guest.
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''Errno BSD::GetPeerNameImpl(s32 fd, std::vector<u8>& write_buffer) {\n    if (!IsFileDescriptorValid(fd)) {\n        return Errno::BADF;\n    }\n\n    if (!file_descriptors[fd]->socket) {\n        LOG_WARNING(Service, "Uninitialized socket");\n        return Errno::BADF;\n    }\n\n    const auto [addr_in, bsd_errno] = file_descriptors[fd]->socket->GetPeerName();\n    if (bsd_errno != Network::Errno::SUCCESS) {\n        return Translate(bsd_errno);\n    }\n    const SockAddrIn guest_addrin = Translate(addr_in);\n\n    ASSERT(write_buffer.size() >= sizeof(guest_addrin));\n    write_buffer.resize(sizeof(guest_addrin));\n    PutValue(write_buffer, guest_addrin);\n    return Translate(bsd_errno);\n}''',
    '''Errno BSD::GetPeerNameImpl(s32 fd, std::vector<u8>& write_buffer) {\n    if (!IsFileDescriptorValid(fd)) {\n        return Errno::BADF;\n    }\n\n    if (!file_descriptors[fd]->socket) {\n        LOG_WARNING(Service, "Uninitialized socket");\n        return Errno::BADF;\n    }\n\n    const auto [addr_in, bsd_errno] = file_descriptors[fd]->socket->GetPeerName();\n    if (bsd_errno != Network::Errno::SUCCESS) {\n        return Translate(bsd_errno);\n    }\n    const SockAddrIn guest_addrin = Translate(addr_in);\n\n    const size_t output_size =\n        (std::min)(write_buffer.size(), static_cast<size_t>(guest_addrin.len));\n    write_buffer.resize(output_size);\n    PutValue(write_buffer, guest_addrin);\n    return Translate(bsd_errno);\n}''',
)

replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''Errno BSD::GetSockNameImpl(s32 fd, std::vector<u8>& write_buffer) {\n    if (!IsFileDescriptorValid(fd)) {\n        return Errno::BADF;\n    }\n\n    if (!file_descriptors[fd]->socket) {\n        LOG_WARNING(Service, "Uninitialized socket");\n        return Errno::BADF;\n    }\n\n    const auto [addr_in, bsd_errno] = file_descriptors[fd]->socket->GetSockName();\n    if (bsd_errno != Network::Errno::SUCCESS) {\n        return Translate(bsd_errno);\n    }\n    const SockAddrIn guest_addrin = Translate(addr_in);\n\n    ASSERT(write_buffer.size() >= sizeof(guest_addrin));\n    write_buffer.resize(sizeof(guest_addrin));\n    PutValue(write_buffer, guest_addrin);\n    return Translate(bsd_errno);\n}''',
    '''Errno BSD::GetSockNameImpl(s32 fd, std::vector<u8>& write_buffer) {\n    if (!IsFileDescriptorValid(fd)) {\n        return Errno::BADF;\n    }\n\n    if (!file_descriptors[fd]->socket) {\n        LOG_WARNING(Service, "Uninitialized socket");\n        return Errno::BADF;\n    }\n\n    const auto [addr_in, bsd_errno] = file_descriptors[fd]->socket->GetSockName();\n    if (bsd_errno != Network::Errno::SUCCESS) {\n        return Translate(bsd_errno);\n    }\n    const SockAddrIn guest_addrin = Translate(addr_in);\n\n    const size_t output_size =\n        (std::min)(write_buffer.size(), static_cast<size_t>(guest_addrin.len));\n    write_buffer.resize(output_size);\n    PutValue(write_buffer, guest_addrin);\n    return Translate(bsd_errno);\n}''',
)
