// SPDX-FileCopyrightText: Copyright 2026 Eden Emulator Project
// SPDX-License-Identifier: GPL-3.0-or-later

// SPDX-FileCopyrightText: Copyright 2023 yuzu Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include "common/string_util.h"
#include "core/file_sys/fssrv/fssrv_sf_path.h"
#include "core/hle/service/cmif_serialization.h"
#include "core/hle/service/filesystem/fsp/fs_i_directory.h"
#include "core/hle/service/filesystem/fsp/fs_i_file.h"
#include "core/hle/service/filesystem/fsp/fs_i_filesystem.h"

namespace Service::FileSystem {

IFileSystem::IFileSystem(Core::System& system_, FileSys::VirtualDir dir_, SizeGetter size_getter_)
    : ServiceFramework{system_, "IFileSystem"}, backend{std::make_unique<FileSys::Fsa::IFileSystem>(
                                                    dir_)},
      size_getter{std::move(size_getter_)} {
    LOG_INFO(Service_FS, "V36_DIAG FileSystemOpen fs={} root={}", static_cast<const void*>(this),
             dir_->GetFullPath());
    static const FunctionInfo functions[] = {
        {0, D<&IFileSystem::CreateFile>, "CreateFile"},
        {1, D<&IFileSystem::DeleteFile>, "DeleteFile"},
        {2, D<&IFileSystem::CreateDirectory>, "CreateDirectory"},
        {3, D<&IFileSystem::DeleteDirectory>, "DeleteDirectory"},
        {4, D<&IFileSystem::DeleteDirectoryRecursively>, "DeleteDirectoryRecursively"},
        {5, D<&IFileSystem::RenameFile>, "RenameFile"},
        {6, nullptr, "RenameDirectory"},
        {7, D<&IFileSystem::GetEntryType>, "GetEntryType"},
        {8, D<&IFileSystem::OpenFile>, "OpenFile"},
        {9, D<&IFileSystem::OpenDirectory>, "OpenDirectory"},
        {10, D<&IFileSystem::Commit>, "Commit"},
        {11, D<&IFileSystem::GetFreeSpaceSize>, "GetFreeSpaceSize"},
        {12, D<&IFileSystem::GetTotalSpaceSize>, "GetTotalSpaceSize"},
        {13, D<&IFileSystem::CleanDirectoryRecursively>, "CleanDirectoryRecursively"},
        {14, D<&IFileSystem::GetFileTimeStampRaw>, "GetFileTimeStampRaw"},
        {15, nullptr, "QueryEntry"},
        {16, D<&IFileSystem::GetFileSystemAttribute>, "GetFileSystemAttribute"},
    };
    RegisterHandlers(functions);
}

Result IFileSystem::CreateFile(const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path,
                               s32 option, s64 size) {
    LOG_DEBUG(Service_FS, "called. file={}, option={:#x}, size={:#08x}", path->str, option, size);

    const Result result = backend->CreateFile(FileSys::Path(path->str), size);
    LOG_INFO(Service_FS,
             "V36_DIAG CreateFile fs={} path={} option={:#x} size={:#x} result={:#x}",
             static_cast<const void*>(this), path->str, option, size, result.GetInnerValue());
    R_RETURN(result);
}

Result IFileSystem::DeleteFile(const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path) {
    LOG_DEBUG(Service_FS, "called. file={}", path->str);

    const Result result = backend->DeleteFile(FileSys::Path(path->str));
    LOG_INFO(Service_FS, "V36_DIAG DeleteFile fs={} path={} result={:#x}",
             static_cast<const void*>(this), path->str, result.GetInnerValue());
    R_RETURN(result);
}

Result IFileSystem::CreateDirectory(
    const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path) {
    LOG_DEBUG(Service_FS, "called. directory={}", path->str);

    const Result result = backend->CreateDirectory(FileSys::Path(path->str));
    LOG_INFO(Service_FS, "V36_DIAG CreateDirectory fs={} path={} result={:#x}",
             static_cast<const void*>(this), path->str, result.GetInnerValue());
    R_RETURN(result);
}

Result IFileSystem::DeleteDirectory(
    const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path) {
    LOG_DEBUG(Service_FS, "called. directory={}", path->str);

    const Result result = backend->DeleteDirectory(FileSys::Path(path->str));
    LOG_INFO(Service_FS, "V36_DIAG DeleteDirectory fs={} path={} result={:#x}",
             static_cast<const void*>(this), path->str, result.GetInnerValue());
    R_RETURN(result);
}

Result IFileSystem::DeleteDirectoryRecursively(
    const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path) {
    LOG_DEBUG(Service_FS, "called. directory={}", path->str);

    const Result result = backend->DeleteDirectoryRecursively(FileSys::Path(path->str));
    LOG_INFO(Service_FS, "V36_DIAG DeleteDirectoryRecursively fs={} path={} result={:#x}",
             static_cast<const void*>(this), path->str, result.GetInnerValue());
    R_RETURN(result);
}

Result IFileSystem::CleanDirectoryRecursively(
    const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path) {
    LOG_DEBUG(Service_FS, "called. Directory: {}", path->str);

    const Result result = backend->CleanDirectoryRecursively(FileSys::Path(path->str));
    LOG_INFO(Service_FS, "V36_DIAG CleanDirectoryRecursively fs={} path={} result={:#x}",
             static_cast<const void*>(this), path->str, result.GetInnerValue());
    R_RETURN(result);
}

Result IFileSystem::RenameFile(
    const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> old_path,
    const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> new_path) {
    LOG_DEBUG(Service_FS, "called. file '{}' to file '{}'", old_path->str, new_path->str);

    const Result result =
        backend->RenameFile(FileSys::Path(old_path->str), FileSys::Path(new_path->str));
    LOG_INFO(Service_FS, "V36_DIAG RenameFile fs={} old={} new={} result={:#x}",
             static_cast<const void*>(this), old_path->str, new_path->str,
             result.GetInnerValue());
    R_RETURN(result);
}

Result IFileSystem::OpenFile(OutInterface<IFile> out_interface,
                             const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path,
                             u32 mode) {
    LOG_DEBUG(Service_FS, "called. file={}, mode={}", path->str, mode);

    FileSys::VirtualFile vfs_file{};
    const Result result = backend->OpenFile(&vfs_file, FileSys::Path(path->str),
                                            static_cast<FileSys::OpenMode>(mode));
    LOG_INFO(Service_FS, "V36_DIAG OpenFile fs={} path={} mode={:#x} result={:#x}",
             static_cast<const void*>(this), path->str, mode, result.GetInnerValue());
    R_TRY(result);

    *out_interface = std::make_shared<IFile>(system, vfs_file);
    R_SUCCEED();
}

Result IFileSystem::OpenDirectory(OutInterface<IDirectory> out_interface,
                                  const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path,
                                  u32 mode) {
    LOG_DEBUG(Service_FS, "called. directory={}, mode={}", path->str, mode);

    FileSys::VirtualDir vfs_dir{};
    const Result result = backend->OpenDirectory(&vfs_dir, FileSys::Path(path->str),
                                                 static_cast<FileSys::OpenDirectoryMode>(mode));
    LOG_INFO(Service_FS, "V36_DIAG OpenDirectory fs={} path={} mode={:#x} result={:#x}",
             static_cast<const void*>(this), path->str, mode, result.GetInnerValue());
    R_TRY(result);

    *out_interface = std::make_shared<IDirectory>(system, vfs_dir,
                                                  static_cast<FileSys::OpenDirectoryMode>(mode));
    R_SUCCEED();
}

Result IFileSystem::GetEntryType(
    Out<u32> out_type, const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path) {
    LOG_DEBUG(Service_FS, "called. file={}", path->str);

    FileSys::DirectoryEntryType vfs_entry_type{};
    const Result result = backend->GetEntryType(&vfs_entry_type, FileSys::Path(path->str));
    LOG_INFO(Service_FS, "V36_DIAG GetEntryType fs={} path={} type={} result={:#x}",
             static_cast<const void*>(this), path->str, static_cast<u32>(vfs_entry_type),
             result.GetInnerValue());
    R_TRY(result);

    *out_type = static_cast<u32>(vfs_entry_type);
    R_SUCCEED();
}

Result IFileSystem::Commit() {
    LOG_WARNING(Service_FS, "(STUBBED) called");
    LOG_INFO(Service_FS, "V36_DIAG Commit fs={} result=0x0", static_cast<const void*>(this));

    R_SUCCEED();
}

Result IFileSystem::GetFreeSpaceSize(
    Out<s64> out_size, const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path) {
    *out_size = size_getter.get_free_size();
    LOG_INFO(Service_FS, "V34_DIAG GetFreeSpaceSize fs={} path={} size={:#x}",
             static_cast<const void*>(this), path->str, *out_size);
    R_SUCCEED();
}

Result IFileSystem::GetTotalSpaceSize(
    Out<s64> out_size, const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path) {
    *out_size = size_getter.get_total_size();
    LOG_INFO(Service_FS, "V34_DIAG GetTotalSpaceSize fs={} path={} size={:#x}",
             static_cast<const void*>(this), path->str, *out_size);
    R_SUCCEED();
}

Result IFileSystem::GetFileTimeStampRaw(
    Out<FileSys::FileTimeStampRaw> out_timestamp,
    const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path) {
    LOG_DEBUG(Service_FS, "(Partial Implementation) called. file={}", path->str);

    FileSys::FileTimeStampRaw vfs_timestamp{};
    const Result result =
        backend->GetFileTimeStampRaw(&vfs_timestamp, FileSys::Path(path->str));
    LOG_INFO(Service_FS, "V36_DIAG GetFileTimeStampRaw fs={} path={} result={:#x}",
             static_cast<const void*>(this), path->str, result.GetInnerValue());
    R_TRY(result);

    *out_timestamp = vfs_timestamp;
    R_SUCCEED();
}

Result IFileSystem::GetFileSystemAttribute(Out<FileSys::FileSystemAttribute> out_attribute) {
    LOG_WARNING(Service_FS, "(STUBBED) called");

    constexpr s32 kEntryNameLengthMax = 0x80;
    constexpr s32 kPathLengthMax = 0x300;

    FileSys::FileSystemAttribute savedata_attribute{};

    savedata_attribute.dir_entry_name_length_max_defined = true;
    savedata_attribute.file_entry_name_length_max_defined = true;
    savedata_attribute.dir_path_name_length_max_defined = true;
    savedata_attribute.file_path_name_length_max_defined = true;

    savedata_attribute.utf16_create_dir_path_len_max_defined = true;
    savedata_attribute.utf16_delete_dir_path_len_max_defined = true;
    savedata_attribute.utf16_rename_src_dir_path_len_max_defined = true;
    savedata_attribute.utf16_rename_dest_dir_path_len_max_defined = true;
    savedata_attribute.utf16_open_dir_path_len_max_defined = true;

    savedata_attribute.utf16_dir_entry_name_length_max_defined = true;
    savedata_attribute.utf16_file_entry_name_length_max_defined = true;
    savedata_attribute.utf16_dir_path_name_length_max_defined = true;
    savedata_attribute.utf16_file_path_name_length_max_defined = true;

    savedata_attribute.dir_entry_name_length_max = kEntryNameLengthMax;
    savedata_attribute.file_entry_name_length_max = kEntryNameLengthMax;
    savedata_attribute.dir_path_name_length_max = kPathLengthMax;
    savedata_attribute.file_path_name_length_max = kPathLengthMax;

    savedata_attribute.utf16_create_dir_path_length_max = kPathLengthMax;
    savedata_attribute.utf16_delete_dir_path_length_max = kPathLengthMax;
    savedata_attribute.utf16_rename_src_dir_path_length_max = kPathLengthMax;
    savedata_attribute.utf16_rename_dest_dir_path_length_max = kPathLengthMax;
    savedata_attribute.utf16_open_dir_path_length_max = kPathLengthMax;

    savedata_attribute.utf16_dir_entry_name_length_max = kEntryNameLengthMax;
    savedata_attribute.utf16_file_entry_name_length_max = kEntryNameLengthMax;
    savedata_attribute.utf16_dir_path_name_length_max = kPathLengthMax;
    savedata_attribute.utf16_file_path_name_length_max = kPathLengthMax;

    *out_attribute = savedata_attribute;
    LOG_INFO(Service_FS,
             "V36_DIAG GetFileSystemAttribute fs={} name_max={:#x} path_max={:#x} result=0x0",
             static_cast<const void*>(this), kEntryNameLengthMax, kPathLengthMax);
    R_SUCCEED();
}

} // namespace Service::FileSystem
