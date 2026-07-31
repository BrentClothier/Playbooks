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


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    file = Path(path)
    text = file.read_text()
    start_count = text.count(start)
    end_count = text.count(end)
    if start_count != 1 or end_count != 1:
        raise RuntimeError(
            f"{path}: expected one start/end marker, found {start_count}/{end_count}"
        )
    begin = text.index(start)
    finish = text.index(end, begin)
    file.write_text(text[:begin] + replacement + text[finish:])
    print(f"updated function block in {path}")


# Add shared eventfd state. Duplicated descriptors reference the same counter.
replace_once(
    "src/core/hle/service/sockets/bsd.h",
    '''#include <memory>\n#include <span>''',
    '''#include <memory>\n#include <mutex>\n#include <span>''',
)

replace_once(
    "src/core/hle/service/sockets/bsd.h",
    '''    struct FileDescriptor {\n        std::shared_ptr<Network::SocketBase> socket;\n        s32 flags = 0;\n        bool is_connection_based = false;\n        bool is_connected = false;\n    };''',
    '''    struct EventFdState {\n        std::mutex mutex;\n        u64 counter{};\n        u32 flags{};\n    };\n\n    struct FileDescriptor {\n        std::shared_ptr<Network::SocketBase> socket;\n        std::shared_ptr<EventFdState> eventfd;\n        s32 flags = 0;\n        bool is_connection_based = false;\n        bool is_connected = false;\n    };''',
)

replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''#include <array>\n#include <memory>''',
    '''#include <array>\n#include <limits>\n#include <memory>''',
)

# Write to an eventfd increments its 64-bit counter. Other descriptors retain
# the existing socket Write behavior.
replace_between(
    "src/core/hle/service/sockets/bsd.cpp",
    "void BSD::Write(HLERequestContext& ctx) {",
    "void BSD::Read(HLERequestContext& ctx) {",
    '''void BSD::Write(HLERequestContext& ctx) {\n    IPC::RequestParser rp{ctx};\n    const s32 fd = rp.Pop<s32>();\n    const auto message = ctx.ReadBuffer();\n\n    LOG_DEBUG(Service, "called. fd={} len={}", fd, message.size());\n\n    if (IsFileDescriptorValid(fd) && file_descriptors[fd]->eventfd) {\n        s32 ret = -1;\n        Errno bsd_errno = Errno::SUCCESS;\n        if (message.size() < sizeof(u64)) {\n            bsd_errno = Errno::INVAL;\n        } else {\n            u64 value{};\n            std::memcpy(&value, message.data(), sizeof(value));\n            auto& state = *file_descriptors[fd]->eventfd;\n            std::scoped_lock lock{state.mutex};\n            constexpr u64 max_counter = std::numeric_limits<u64>::max() - 1;\n            if (value == std::numeric_limits<u64>::max()) {\n                bsd_errno = Errno::INVAL;\n            } else if (state.counter > max_counter - value) {\n                bsd_errno = Errno::AGAIN;\n            } else {\n                state.counter += value;\n                ret = sizeof(u64);\n                LOG_DEBUG(Service, "eventfd write fd={} value={} counter={}", fd, value,\n                          state.counter);\n            }\n        }\n\n        IPC::ResponseBuilder rb{ctx, 4};\n        rb.Push(ResultSuccess);\n        rb.Push<s32>(bsd_errno == Errno::SUCCESS ? ret : -1);\n        rb.PushEnum(bsd_errno);\n        return;\n    }\n\n    ExecuteWork(ctx, SendWork{\n                         .fd = fd,\n                         .flags = 0,\n                         .message = message,\n                     });\n}\n\n''',
)

# Read returns and clears the eventfd counter. A zero counter is surfaced as
# EAGAIN rather than falsely reporting an empty successful read.
replace_between(
    "src/core/hle/service/sockets/bsd.cpp",
    "void BSD::Read(HLERequestContext& ctx) {",
    "void BSD::Close(HLERequestContext& ctx) {",
    '''void BSD::Read(HLERequestContext& ctx) {\n    IPC::RequestParser rp{ctx};\n    const s32 fd = rp.Pop<s32>();\n    std::vector<u8> message(ctx.GetWriteBufferSize());\n\n    LOG_DEBUG(Service, "called. fd={} len={}", fd, message.size());\n\n    s32 ret = -1;\n    Errno bsd_errno = Errno::BADF;\n    if (IsFileDescriptorValid(fd)) {\n        FileDescriptor& descriptor = *file_descriptors[fd];\n        if (descriptor.eventfd) {\n            if (message.size() < sizeof(u64)) {\n                bsd_errno = Errno::INVAL;\n            } else {\n                auto& state = *descriptor.eventfd;\n                std::scoped_lock lock{state.mutex};\n                if (state.counter == 0) {\n                    bsd_errno = Errno::AGAIN;\n                } else {\n                    const u64 value = state.counter;\n                    state.counter = 0;\n                    std::memcpy(message.data(), &value, sizeof(value));\n                    ret = sizeof(u64);\n                    bsd_errno = Errno::SUCCESS;\n                    LOG_DEBUG(Service, "eventfd read fd={} value={}", fd, value);\n                }\n            }\n        } else {\n            LOG_WARNING(Service, "(STUBBED socket read) called. fd={} len={}", fd,\n                        message.size());\n            ret = 0;\n            bsd_errno = Errno::SUCCESS;\n        }\n    }\n\n    if (bsd_errno == Errno::SUCCESS) {\n        ctx.WriteBuffer(message);\n    }\n\n    IPC::ResponseBuilder rb{ctx, 4};\n    rb.Push(ResultSuccess);\n    rb.Push<s32>(bsd_errno == Errno::SUCCESS ? ret : -1);\n    rb.PushEnum(bsd_errno);\n}\n\n''',
)

# EventFd must allocate and return a real guest descriptor. The old stub always
# returned success/0 without reserving fd 0, causing descriptor aliasing.
replace_between(
    "src/core/hle/service/sockets/bsd.cpp",
    "void BSD::EventFd(HLERequestContext& ctx) {",
    "template <typename Work>",
    '''void BSD::EventFd(HLERequestContext& ctx) {\n    IPC::RequestParser rp{ctx};\n    const u64 initval = rp.Pop<u64>();\n    const u32 flags = rp.Pop<u32>();\n\n    const s32 fd = FindFreeFileDescriptorHandle();\n    Errno bsd_errno = Errno::SUCCESS;\n    if (fd < 0) {\n        bsd_errno = Errno::MFILE;\n    } else {\n        file_descriptors[fd] = FileDescriptor{};\n        auto& descriptor = *file_descriptors[fd];\n        descriptor.eventfd = std::make_shared<EventFdState>();\n        descriptor.eventfd->counter = initval;\n        descriptor.eventfd->flags = flags;\n        descriptor.flags = static_cast<s32>(flags);\n        LOG_INFO(Service, "New eventfd fd={} initval={} flags={:#x}", fd, initval, flags);\n    }\n\n    IPC::ResponseBuilder rb{ctx, 4};\n    rb.Push(ResultSuccess);\n    rb.Push<s32>(bsd_errno == Errno::SUCCESS ? fd : -1);\n    rb.PushEnum(bsd_errno);\n}\n\n''',
)

# Poll eventfds locally and send only actual sockets to the host poll backend.
# When eventfds are present, use a nonblocking host poll so guest code can
# observe event-counter changes without blocking inside the socket backend.
replace_between(
    "src/core/hle/service/sockets/bsd.cpp",
    "std::pair<s32, Errno> BSD::PollImpl(",
    "std::pair<s32, Errno> BSD::AcceptImpl(",
    '''std::pair<s32, Errno> BSD::PollImpl(std::vector<u8>& write_buffer,\n                                    std::span<const u8> read_buffer, s32 nfds, s32 timeout) {\n    if (nfds <= 0) {\n        return {-1, Errno::SUCCESS};\n    }\n    if (read_buffer.size() < static_cast<size_t>(nfds) * sizeof(PollFD) ||\n        write_buffer.size() < static_cast<size_t>(nfds) * sizeof(PollFD)) {\n        return {-1, Errno::INVAL};\n    }\n    if (timeout < -1) {\n        return {-1, Errno::INVAL};\n    }\n\n    std::vector<PollFD> fds(nfds);\n    std::memcpy(fds.data(), read_buffer.data(), fds.size() * sizeof(PollFD));\n\n    std::vector<Network::PollFD> host_pollfds;\n    std::vector<size_t> host_indices;\n    host_pollfds.reserve(fds.size());\n    host_indices.reserve(fds.size());\n\n    s32 ready_count = 0;\n    bool has_eventfd = false;\n    for (size_t i = 0; i < fds.size(); ++i) {\n        PollFD& pollfd = fds[i];\n        pollfd.revents = PollEvents{};\n        if (pollfd.fd < 0 || pollfd.fd >= static_cast<s32>(MAX_FD) ||\n            !file_descriptors[pollfd.fd]) {\n            pollfd.revents = PollEvents::Nval;\n            ++ready_count;\n            continue;\n        }\n\n        FileDescriptor& descriptor = *file_descriptors[pollfd.fd];\n        if (descriptor.eventfd) {\n            has_eventfd = true;\n            auto& state = *descriptor.eventfd;\n            std::scoped_lock lock{state.mutex};\n            if (True(pollfd.events & PollEvents::In) && state.counter > 0) {\n                pollfd.revents |= PollEvents::In;\n            }\n            if (True(pollfd.events & PollEvents::Out) &&\n                state.counter < std::numeric_limits<u64>::max() - 1) {\n                pollfd.revents |= PollEvents::Out;\n            }\n            if (pollfd.revents != PollEvents{}) {\n                ++ready_count;\n            }\n            continue;\n        }\n\n        if (!descriptor.socket) {\n            pollfd.revents = PollEvents::Nval;\n            ++ready_count;\n            continue;\n        }\n\n        host_indices.push_back(i);\n        host_pollfds.push_back(Network::PollFD{\n            .socket = descriptor.socket.get(),\n            .events = Translate(pollfd.events),\n            .revents = Network::PollEvents{},\n        });\n    }\n\n    if (!host_pollfds.empty()) {\n        const s32 host_timeout = (ready_count > 0 || has_eventfd) ? 0 : timeout;\n        const auto [host_ready, host_errno] = Network::Poll(host_pollfds, host_timeout);\n        if (host_errno != Network::Errno::SUCCESS) {\n            return {-1, Translate(host_errno)};\n        }\n        ready_count += host_ready;\n        for (size_t i = 0; i < host_pollfds.size(); ++i) {\n            fds[host_indices[i]].revents = Translate(host_pollfds[i].revents);\n        }\n    }\n\n    std::memcpy(write_buffer.data(), fds.data(), fds.size() * sizeof(PollFD));\n    return {ready_count, Errno::SUCCESS};\n}\n\n''',
)

# Fcntl GETFL/SETFL applies to eventfds too; it must not reject them for having
# no Network::Socket object.
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''std::pair<s32, Errno> BSD::FcntlImpl(s32 fd, FcntlCmd cmd, s32 arg) {\n    if (!IsFileDescriptorValid(fd)) {\n        return {-1, Errno::BADF};\n    }\n    if (!file_descriptors[fd]->socket) {\n        LOG_WARNING(Service, "Uninitialized socket");\n        return {-1, Errno::BADF};\n    }\n\n    FileDescriptor& descriptor = *file_descriptors[fd];\n\n    switch (cmd) {''',
    '''std::pair<s32, Errno> BSD::FcntlImpl(s32 fd, FcntlCmd cmd, s32 arg) {\n    if (!IsFileDescriptorValid(fd)) {\n        return {-1, Errno::BADF};\n    }\n\n    FileDescriptor& descriptor = *file_descriptors[fd];\n    if (descriptor.eventfd) {\n        switch (cmd) {\n        case FcntlCmd::GETFL:\n            return {descriptor.flags, Errno::SUCCESS};\n        case FcntlCmd::SETFL:\n            descriptor.flags = arg;\n            return {0, Errno::SUCCESS};\n        default:\n            return {-1, Errno::INVAL};\n        }\n    }\n    if (!descriptor.socket) {\n        LOG_WARNING(Service, "Uninitialized socket");\n        return {-1, Errno::BADF};\n    }\n\n    switch (cmd) {''',
)

# Eventfds close cleanly without attempting a socket close.
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''Errno BSD::CloseImpl(s32 fd) {\n    if (!IsFileDescriptorValid(fd)) {\n        return Errno::BADF;\n    }\n    if (!file_descriptors[fd]->socket) {\n        LOG_WARNING(Service, "Uninitialized socket");\n        return Errno::BADF;\n    }\n\n    const Errno bsd_errno = Translate(file_descriptors[fd]->socket->Close());''',
    '''Errno BSD::CloseImpl(s32 fd) {\n    if (!IsFileDescriptorValid(fd)) {\n        return Errno::BADF;\n    }\n    if (file_descriptors[fd]->eventfd) {\n        LOG_INFO(Service, "Close eventfd fd={}", fd);\n        file_descriptors[fd].reset();\n        return Errno::SUCCESS;\n    }\n    if (!file_descriptors[fd]->socket) {\n        LOG_WARNING(Service, "Uninitialized socket");\n        return Errno::BADF;\n    }\n\n    const Errno bsd_errno = Translate(file_descriptors[fd]->socket->Close());''',
)

# Duplicated event descriptors share their underlying counter.
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''        .socket = file_descriptors[fd]->socket,\n        .flags = file_descriptors[fd]->flags,\n        .is_connection_based = file_descriptors[fd]->is_connection_based,\n        .is_connected = file_descriptors[fd]->is_connected,\n    };''',
    '''        .socket = file_descriptors[fd]->socket,\n        .eventfd = file_descriptors[fd]->eventfd,\n        .flags = file_descriptors[fd]->flags,\n        .is_connection_based = file_descriptors[fd]->is_connection_based,\n        .is_connected = file_descriptors[fd]->is_connected,\n    };''',
)

# Proxy packets are relevant only to socket descriptors.
replace_once(
    "src/core/hle/service/sockets/bsd.cpp",
    '''        FileDescriptor& descriptor = *optional_descriptor;\n        descriptor.socket.get()->HandleProxyPacket(packet);''',
    '''        FileDescriptor& descriptor = *optional_descriptor;\n        if (descriptor.socket) {\n            descriptor.socket->HandleProxyPacket(packet);\n        }''',
)
