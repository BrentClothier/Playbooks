#!/usr/bin/env python3
from pathlib import Path

# V33 proved that Minecraft sees the cache entry and the requested cache data/journal sizes, but
# the same UI error remains. The next storage-capacity candidates are already implemented in Eden:
# IFileSystem::GetFreeSpaceSize and GetTotalSpaceSize. They log only at Debug level, so normal test
# logs cannot show whether Minecraft calls them or which values it receives.
#
# This patch changes logging only. It does not alter save/cache behavior or any graphics code.


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


filesystem_path = Path("src/core/hle/service/filesystem/fsp/fs_i_filesystem.cpp")
replace_once(
    filesystem_path,
    '''Result IFileSystem::GetFreeSpaceSize(
    Out<s64> out_size, const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path) {
    LOG_DEBUG(Service_FS, "called");

    *out_size = size_getter.get_free_size();
    R_SUCCEED();
}
''',
    '''Result IFileSystem::GetFreeSpaceSize(
    Out<s64> out_size, const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path) {
    *out_size = size_getter.get_free_size();
    LOG_INFO(Service_FS, "V34_DIAG GetFreeSpaceSize path={} size={:#x}", path->str, *out_size);
    R_SUCCEED();
}
''',
    "expose save-filesystem free-space queries in normal logs",
)

replace_once(
    filesystem_path,
    '''Result IFileSystem::GetTotalSpaceSize(
    Out<s64> out_size, const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path) {
    LOG_DEBUG(Service_FS, "called");

    *out_size = size_getter.get_total_size();
    R_SUCCEED();
}
''',
    '''Result IFileSystem::GetTotalSpaceSize(
    Out<s64> out_size, const InLargeData<FileSys::Sf::Path, BufferAttr_HipcPointer> path) {
    *out_size = size_getter.get_total_size();
    LOG_INFO(Service_FS, "V34_DIAG GetTotalSpaceSize path={} size={:#x}", path->str, *out_size);
    R_SUCCEED();
}
''',
    "expose save-filesystem total-space queries in normal logs",
)

fsp_path = Path("src/core/hle/service/filesystem/fsp/fsp_srv.cpp")
replace_once(
    fsp_path,
    '''Result FSP_SRV::OpenSaveDataFileSystem(OutInterface<IFileSystem> out_interface,
                                       FileSys::SaveDataSpaceId space_id,
                                       FileSys::SaveDataAttribute attribute) {
    LOG_INFO(Service_FS, "called.");
''',
    '''Result FSP_SRV::OpenSaveDataFileSystem(OutInterface<IFileSystem> out_interface,
                                       FileSys::SaveDataSpaceId space_id,
                                       FileSys::SaveDataAttribute attribute) {
    LOG_INFO(Service_FS, "V34_DIAG OpenSaveDataFileSystem space_id={:02X} attribute={}",
             space_id, attribute.DebugInfo());
''',
    "identify each filesystem whose capacity may be queried",
)

application_path = Path("src/core/hle/service/am/service/application_functions.cpp")
replace_once(
    application_path,
    '''Result IApplicationFunctions::ExtendSaveData(Out<u64> out_required_size, FileSys::SaveDataType type,
                                             Common::UUID user_id, u64 normal_size,
                                             u64 journal_size) {
    LOG_DEBUG(Service_AM, "called with type={} user_id={} normal={:#x} journal={:#x}",
              static_cast<u8>(type), user_id.FormattedString(), normal_size, journal_size);
''',
    '''Result IApplicationFunctions::ExtendSaveData(Out<u64> out_required_size, FileSys::SaveDataType type,
                                             Common::UUID user_id, u64 normal_size,
                                             u64 journal_size) {
    LOG_INFO(Service_AM,
             "V34_DIAG ExtendSaveData type={} user_id={} normal={:#x} journal={:#x}",
             static_cast<u8>(type), user_id.FormattedString(), normal_size, journal_size);
''',
    "expose save-extension requests in normal logs",
)

replace_once(
    application_path,
    '''    *out_normal_size = size.normal;
    *out_journal_size = size.journal;
    R_SUCCEED();
}

Result IApplicationFunctions::CreateCacheStorage''',
    '''    *out_normal_size = size.normal;
    *out_journal_size = size.journal;
    LOG_INFO(Service_AM,
             "V34_DIAG GetSaveDataSize type={} user_id={} normal={:#x} journal={:#x}", type,
             user_id.FormattedString(), *out_normal_size, *out_journal_size);
    R_SUCCEED();
}

Result IApplicationFunctions::CreateCacheStorage''',
    "expose returned save-data sizes in normal logs",
)

replace_once(
    application_path,
    '''    *out_max_normal_size = 0xFFFFFFF;
    *out_max_journal_size = 0xFFFFFFF;

    R_SUCCEED();
}
''',
    '''    *out_max_normal_size = 0xFFFFFFF;
    *out_max_journal_size = 0xFFFFFFF;

    LOG_INFO(Service_AM, "V34_DIAG GetSaveDataSizeMax normal={:#x} journal={:#x}",
             *out_max_normal_size, *out_max_journal_size);
    R_SUCCEED();
}
''',
    "trace the existing save-size maxima without changing them",
)

replace_once(
    application_path,
    '''    *out_cache_storage_index_max = static_cast<u32>(raw_nacp->cache_storage_max_index);
    *out_max_journal_size = static_cast<u64>(raw_nacp->cache_storage_data_and_journal_max_size);

    R_SUCCEED();
}
''',
    '''    *out_cache_storage_index_max = static_cast<u32>(raw_nacp->cache_storage_max_index);
    *out_max_journal_size = static_cast<u64>(raw_nacp->cache_storage_data_and_journal_max_size);

    LOG_INFO(Service_AM, "V34_DIAG GetCacheStorageMax index_max={} size_max={:#x}",
             *out_cache_storage_index_max, *out_max_journal_size);
    R_SUCCEED();
}
''',
    "trace the NACP cache-storage maxima without changing them",
)
