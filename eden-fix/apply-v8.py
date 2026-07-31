#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}")
    file.write_text(text.replace(old, new, 1))
    print(f"instrumented {path}")


# Log every socket creation request and the resulting host socket configuration.
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''std::pair<s32, Errno> BSD::SocketImpl(Domain domain, Type type, Protocol protocol) {\n\n    if (type == Type::SEQPACKET) {''',
    '''std::pair<s32, Errno> BSD::SocketImpl(Domain domain, Type type, Protocol protocol) {\n    LOG_WARNING(Service,\n                "V8_DIAG Socket request domain={} type={:#x} protocol={} airplane_mode={}",\n                static_cast<u32>(domain), static_cast<u32>(type), static_cast<u32>(protocol),\n                Settings::values.airplane_mode.GetValue());\n\n    if (type == Type::SEQPACKET) {''',
)

replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''    descriptor.socket->Initialize(Translate(domain), Translate(type), Translate(protocol));\n    descriptor.is_connection_based = IsConnectionBased(type);''',
    '''    descriptor.socket->Initialize(Translate(domain), Translate(type), Translate(protocol));\n    descriptor.is_connection_based = IsConnectionBased(type);\n    LOG_WARNING(Service,\n                "V8_DIAG Socket initialized fd={} domain={} type={:#x} protocol={} connection_based={}",\n                fd, static_cast<u32>(domain), static_cast<u32>(type),\n                static_cast<u32>(protocol), descriptor.is_connection_based);''',
)

# Bind diagnostics.
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''    auto addr_in = GetValue<SockAddrIn>(addr);\n\n    return Translate(file_descriptors[fd]->socket->Bind(Translate(addr_in)));\n}\n\nErrno BSD::ConnectImpl''',
    '''    auto addr_in = GetValue<SockAddrIn>(addr);\n    LOG_WARNING(Service,\n                "V8_DIAG Bind fd={} addr_size={} len={} family={} port_raw={:#x} ip={}.{}.{}.{}",\n                fd, addr.size(), addr_in.len, addr_in.family, addr_in.portno, addr_in.ip[0],\n                addr_in.ip[1], addr_in.ip[2], addr_in.ip[3]);\n    const Errno result = Translate(file_descriptors[fd]->socket->Bind(Translate(addr_in)));\n    LOG_WARNING(Service, "V8_DIAG Bind result fd={} errno={}", fd, static_cast<u32>(result));\n    return result;\n}\n\nErrno BSD::ConnectImpl''',
)

# Connect diagnostics.
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''    auto addr_in = GetValue<SockAddrIn>(addr);\n\n    const Errno result = Translate(file_descriptors[fd]->socket->Connect(Translate(addr_in)));''',
    '''    auto addr_in = GetValue<SockAddrIn>(addr);\n    LOG_WARNING(Service,\n                "V8_DIAG Connect fd={} addr_size={} len={} family={} port_raw={:#x} ip={}.{}.{}.{}",\n                fd, addr.size(), addr_in.len, addr_in.family, addr_in.portno, addr_in.ip[0],\n                addr_in.ip[1], addr_in.ip[2], addr_in.ip[3]);\n\n    const Errno result = Translate(file_descriptors[fd]->socket->Connect(Translate(addr_in)));\n    LOG_WARNING(Service, "V8_DIAG Connect result fd={} errno={}", fd, static_cast<u32>(result));''',
)

# GetPeerName and GetSockName diagnostics. These run after the v7 bounded-buffer fix.
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''    const auto [addr_in, bsd_errno] = file_descriptors[fd]->socket->GetPeerName();\n    if (bsd_errno != Network::Errno::SUCCESS) {''',
    '''    LOG_WARNING(Service, "V8_DIAG GetPeerName fd={} requested_size={}", fd,\n                write_buffer.size());\n    const auto [addr_in, bsd_errno] = file_descriptors[fd]->socket->GetPeerName();\n    LOG_WARNING(Service, "V8_DIAG GetPeerName host_errno={}", static_cast<u32>(bsd_errno));\n    if (bsd_errno != Network::Errno::SUCCESS) {''',
)

replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''    const auto [addr_in, bsd_errno] = file_descriptors[fd]->socket->GetSockName();\n    if (bsd_errno != Network::Errno::SUCCESS) {''',
    '''    LOG_WARNING(Service, "V8_DIAG GetSockName fd={} requested_size={}", fd,\n                write_buffer.size());\n    const auto [addr_in, bsd_errno] = file_descriptors[fd]->socket->GetSockName();\n    LOG_WARNING(Service, "V8_DIAG GetSockName host_errno={}", static_cast<u32>(bsd_errno));\n    if (bsd_errno != Network::Errno::SUCCESS) {''',
)

# Send diagnostics, including whether SendTo was called without a destination.
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''    return Translate(file_descriptors[fd]->socket->Send(message, flags));\n}\n\nstd::pair<s32, Errno> BSD::SendToImpl''',
    '''    LOG_WARNING(Service, "V8_DIAG Send fd={} flags={:#x} bytes={}", fd, flags,\n                message.size());\n    const auto result = Translate(file_descriptors[fd]->socket->Send(message, flags));\n    LOG_WARNING(Service, "V8_DIAG Send result fd={} ret={} errno={}", fd, result.first,\n                static_cast<u32>(result.second));\n    return result;\n}\n\nstd::pair<s32, Errno> BSD::SendToImpl''',
)

replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''    Network::SockAddrIn addr_in;\n    Network::SockAddrIn* p_addr_in = nullptr;\n    if (!addr.empty()) {\n        ASSERT(addr.size() >= 16);\n        auto guest_addr_in = GetValue<SockAddrIn>(addr);\n        addr_in = Translate(guest_addr_in);\n        p_addr_in = &addr_in;\n    }\n\n    return Translate(file_descriptors[fd]->socket->SendTo(flags, message, p_addr_in));''',
    '''    Network::SockAddrIn addr_in;\n    Network::SockAddrIn* p_addr_in = nullptr;\n    if (!addr.empty()) {\n        ASSERT(addr.size() >= 16);\n        auto guest_addr_in = GetValue<SockAddrIn>(addr);\n        LOG_WARNING(Service,\n                    "V8_DIAG SendTo fd={} flags={:#x} bytes={} addr_size={} len={} family={} "\n                    "port_raw={:#x} ip={}.{}.{}.{}",\n                    fd, flags, message.size(), addr.size(), guest_addr_in.len,\n                    guest_addr_in.family, guest_addr_in.portno, guest_addr_in.ip[0],\n                    guest_addr_in.ip[1], guest_addr_in.ip[2], guest_addr_in.ip[3]);\n        addr_in = Translate(guest_addr_in);\n        p_addr_in = &addr_in;\n    } else {\n        LOG_WARNING(Service, "V8_DIAG SendTo fd={} flags={:#x} bytes={} destination=none",\n                    fd, flags, message.size());\n    }\n\n    const auto result =\n        Translate(file_descriptors[fd]->socket->SendTo(flags, message, p_addr_in));\n    LOG_WARNING(Service, "V8_DIAG SendTo result fd={} ret={} errno={}", fd, result.first,\n                static_cast<u32>(result.second));\n    return result;''',
)

# Record the exact misaligned mixed-layout DMA request without changing its behavior.
replace_once(
    "src/video_core/engines/maxwell_dma.cpp",
    '''            const bool is_src_pitch = IsPitchKind(src_kind);\n            const bool is_dst_pitch = IsPitchKind(dst_kind);\n            if (!is_src_pitch && is_dst_pitch) {''',
    '''            const bool is_src_pitch = IsPitchKind(src_kind);\n            const bool is_dst_pitch = IsPitchKind(dst_kind);\n            if (is_src_pitch != is_dst_pitch &&\n                ((regs.line_length_in % 16) != 0 || (regs.offset_in % 16) != 0 ||\n                 (regs.offset_out % 16) != 0)) {\n                LOG_WARNING(HW_GPU,\n                            "V8_DIAG MaxwellDMA mixed-layout src_pitch={} dst_pitch={} "\n                            "line_length={} line_count={} pitch_in={} pitch_out={} "\n                            "offset_in={:#x} offset_out={:#x} src_kind={} dst_kind={} remap={}",\n                            is_src_pitch, is_dst_pitch, regs.line_length_in, regs.line_count,\n                            regs.pitch_in, regs.pitch_out, static_cast<GPUVAddr>(regs.offset_in),\n                            static_cast<GPUVAddr>(regs.offset_out), static_cast<u32>(src_kind),\n                            static_cast<u32>(dst_kind), regs.launch_dma.remap_enable);\n            }\n            if (!is_src_pitch && is_dst_pitch) {''',
)
