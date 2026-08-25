// SPDX-FileCopyrightText: Copyright 2026 Eden Emulator Project
// SPDX-License-Identifier: GPL-3.0-or-later

// SPDX-FileCopyrightText: Copyright 2023 yuzu Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include "core/file_sys/errors.h"
#include "core/hle/service/cmif_serialization.h"
#include "core/hle/service/filesystem/fsp/fs_i_file.h"

namespace Service::FileSystem {

IFile::IFile(Core::System& system_, FileSys::VirtualFile file_)
    : ServiceFramework{system_, "IFile"}, backend{std::make_unique<FileSys::Fsa::IFile>(file_)} {
    LOG_INFO(Service_FS, "V36_DIAG FileOpen file={} path={}", static_cast<const void*>(this),
             file_->GetFullPath());
    // clang-format off
    static const FunctionInfo functions[] = {
        {0, D<&IFile::Read>, "Read"},
        {1, D<&IFile::Write>, "Write"},
        {2, D<&IFile::Flush>, "Flush"},
        {3, D<&IFile::SetSize>, "SetSize"},
        {4, D<&IFile::GetSize>, "GetSize"},
        {5, nullptr, "OperateRange"},
        {6, nullptr, "OperateRangeWithBuffer"},
    };
    // clang-format on
    RegisterHandlers(functions);
}

Result IFile::Read(
    FileSys::ReadOption option, Out<s64> out_size, s64 offset,
    const OutBuffer<BufferAttr_HipcMapAlias | BufferAttr_HipcMapTransferAllowsNonSecure> out_buffer,
    s64 size) {
    LOG_DEBUG(Service_FS, "called, option={}, offset={:#x}, length={}", option.value, offset,
              size);

    // Read the data from the Storage backend
    R_RETURN(
        backend->Read(reinterpret_cast<size_t*>(out_size.Get()), offset, out_buffer.data(), size));
}

Result IFile::Write(
    const InBuffer<BufferAttr_HipcMapAlias | BufferAttr_HipcMapTransferAllowsNonSecure> buffer,
    FileSys::WriteOption option, s64 offset, s64 size) {
    LOG_DEBUG(Service_FS, "called, option={}, offset={:#x}, length={}", option.value, offset,
              size);

    const Result result = backend->Write(offset, buffer.data(), size, option);
    LOG_INFO(Service_FS,
             "V36_DIAG FileWrite file={} option={:#x} offset={:#x} size={:#x} result={:#x}",
             static_cast<const void*>(this), option.value, offset, size, result.GetInnerValue());
    R_RETURN(result);
}

Result IFile::Flush() {
    LOG_DEBUG(Service_FS, "called");

    const Result result = backend->Flush();
    LOG_INFO(Service_FS, "V36_DIAG FileFlush file={} result={:#x}",
             static_cast<const void*>(this), result.GetInnerValue());
    R_RETURN(result);
}

Result IFile::SetSize(s64 size) {
    LOG_DEBUG(Service_FS, "called, size={}", size);

    const Result result = backend->SetSize(size);
    LOG_INFO(Service_FS, "V36_DIAG FileSetSize file={} size={:#x} result={:#x}",
             static_cast<const void*>(this), size, result.GetInnerValue());
    R_RETURN(result);
}

Result IFile::GetSize(Out<s64> out_size) {
    LOG_DEBUG(Service_FS, "called");

    const Result result = backend->GetSize(out_size);
    LOG_INFO(Service_FS, "V36_DIAG FileGetSize file={} size={:#x} result={:#x}",
             static_cast<const void*>(this), *out_size, result.GetInnerValue());
    R_RETURN(result);
}

} // namespace Service::FileSystem
