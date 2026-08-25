// SPDX-FileCopyrightText: Copyright 2023 yuzu Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include "core/file_sys/fs_filesystem.h"
#include "core/file_sys/savedata_factory.h"
#include "core/hle/service/cmif_serialization.h"
#include "core/hle/service/filesystem/fsp/fs_i_directory.h"

namespace Service::FileSystem {

IDirectory::IDirectory(Core::System& system_, FileSys::VirtualDir directory_,
                       FileSys::OpenDirectoryMode mode)
    : ServiceFramework{system_, "IDirectory"},
      backend(std::make_unique<FileSys::Fsa::IDirectory>(directory_, mode)) {
    LOG_INFO(Service_FS, "V36_DIAG DirectoryOpen directory={} path={} mode={:#x}",
             static_cast<const void*>(this), directory_->GetFullPath(), static_cast<u32>(mode));
    static const FunctionInfo functions[] = {
        {0, D<&IDirectory::Read>, "Read"},
        {1, D<&IDirectory::GetEntryCount>, "GetEntryCount"},
    };
    RegisterHandlers(functions);
}

Result IDirectory::Read(
    Out<s64> out_count,
    const OutArray<FileSys::DirectoryEntry, BufferAttr_HipcMapAlias> out_entries) {
    LOG_DEBUG(Service_FS, "called.");

    const Result result = backend->Read(out_count, out_entries.data(), out_entries.size());
    LOG_INFO(Service_FS, "V36_DIAG DirectoryRead directory={} capacity={} count={} result={:#x}",
             static_cast<const void*>(this), out_entries.size(), *out_count,
             result.GetInnerValue());
    R_RETURN(result);
}

Result IDirectory::GetEntryCount(Out<s64> out_count) {
    LOG_DEBUG(Service_FS, "called");

    const Result result = backend->GetEntryCount(out_count);
    LOG_INFO(Service_FS, "V36_DIAG DirectoryGetEntryCount directory={} count={} result={:#x}",
             static_cast<const void*>(this), *out_count, result.GetInnerValue());
    R_RETURN(result);
}

} // namespace Service::FileSystem
