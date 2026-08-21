#!/usr/bin/env python3
from pathlib import Path

# The two v32 test logs both show the cache being created, including on the second launch.
# Command 62 still constructs a Temporary-space reader, while Eden stores cache data under
# /user/save/cache/<program id>. The generic User-space enumerator cannot recognize that layout.
#
# Add a cache-only reader path matching command 62's contract: inspect (without creating) the
# current program's cache directory in NandUser and return one Cache SaveDataInfo entry when it
# already exists. The entry's image size comes from v32's persistent size metadata.


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


header_path = Path("src/core/hle/service/filesystem/fsp/fs_i_save_data_info_reader.h")
replace_once(
    header_path,
    '''#pragma once

#include <vector>
''',
    '''#pragma once

#include <optional>
#include <vector>
''',
    "include optional cache-program selector",
)

replace_once(
    header_path,
    '''    explicit ISaveDataInfoReader(Core::System& system_,
                                 std::shared_ptr<SaveDataController> save_data_controller_,
                                 FileSys::SaveDataSpaceId space);
''',
    '''    explicit ISaveDataInfoReader(Core::System& system_,
                                 std::shared_ptr<SaveDataController> save_data_controller_,
                                 FileSys::SaveDataSpaceId space,
                                 std::optional<u64> cache_program_id = std::nullopt);
''',
    "accept an optional current-program cache filter",
)

replace_once(
    header_path,
    '''private:
    void FindAllSaves(FileSys::SaveDataSpaceId space);
    void FindNormalSaves(FileSys::SaveDataSpaceId space, const FileSys::VirtualDir& type);
    void FindTemporaryStorageSaves(FileSys::SaveDataSpaceId space, const FileSys::VirtualDir& type);

    std::shared_ptr<SaveDataController> save_data_controller;
    std::vector<SaveDataInfo> info;
    u64 next_entry_index = 0;
''',
    '''private:
    void FindAllSaves(FileSys::SaveDataSpaceId space);
    void FindCacheStorageSave(FileSys::SaveDataSpaceId space, u64 cache_program_id);
    void FindNormalSaves(FileSys::SaveDataSpaceId space, const FileSys::VirtualDir& type);
    void FindTemporaryStorageSaves(FileSys::SaveDataSpaceId space, const FileSys::VirtualDir& type);

    std::shared_ptr<SaveDataController> save_data_controller;
    std::vector<SaveDataInfo> info;
    u64 next_entry_index = 0;
    bool cache_only_reader = false;
''',
    "declare the cache-only enumerator and trace state",
)

reader_path = Path("src/core/hle/service/filesystem/fsp/fs_i_save_data_info_reader.cpp")
replace_once(
    reader_path,
    '''ISaveDataInfoReader::ISaveDataInfoReader(Core::System& system_,
                                         std::shared_ptr<SaveDataController> save_data_controller_,
                                         FileSys::SaveDataSpaceId space)
    : ServiceFramework{system_, "ISaveDataInfoReader"}, save_data_controller{
                                                            save_data_controller_} {
''',
    '''ISaveDataInfoReader::ISaveDataInfoReader(Core::System& system_,
                                         std::shared_ptr<SaveDataController> save_data_controller_,
                                         FileSys::SaveDataSpaceId space,
                                         std::optional<u64> cache_program_id)
    : ServiceFramework{system_, "ISaveDataInfoReader"}, save_data_controller{
                                                            save_data_controller_},
      cache_only_reader{cache_program_id.has_value()} {
''',
    "select cache-only reader construction",
)

replace_once(
    reader_path,
    '''    FindAllSaves(space);
}
''',
    '''    if (cache_program_id.has_value()) {
        FindCacheStorageSave(space, *cache_program_id);
    } else {
        FindAllSaves(space);
    }
}
''',
    "enumerate only the current program cache when requested",
)

replace_once(
    reader_path,
    '''    *out_count = actual_entries;

    R_SUCCEED();
}

void ISaveDataInfoReader::FindAllSaves(FileSys::SaveDataSpaceId space) {
''',
    '''    *out_count = actual_entries;

    if (cache_only_reader) {
        LOG_INFO(Service_FS, "V33_FIX ReadCacheStorageInfo count={} total={}", actual_entries,
                 info.size());
    }

    R_SUCCEED();
}

void ISaveDataInfoReader::FindCacheStorageSave(FileSys::SaveDataSpaceId space,
                                               u64 cache_program_id) {
    FileSys::VirtualDir save_root{};
    const auto result = save_data_controller->OpenSaveDataSpace(&save_root, space);
    if (result != ResultSuccess || save_root == nullptr) {
        LOG_ERROR(Service_FS,
                  "V33_FIX CacheStorageInfo program_id={:016X} space_id={:02X} root_valid=false",
                  cache_program_id, space);
        return;
    }

    const auto cache =
        save_root->GetDirectoryRelative(fmt::format("save/cache/{:016X}", cache_program_id));
    if (cache == nullptr) {
        LOG_INFO(Service_FS,
                 "V33_FIX CacheStorageInfo program_id={:016X} space_id={:02X} found=false",
                 cache_program_id, space);
        return;
    }

    const auto size = save_data_controller->ReadSaveDataSize(
        FileSys::SaveDataType::Cache, cache_program_id, u128{});
    info.emplace_back(SaveDataInfo{
        0,
        space,
        FileSys::SaveDataType::Cache,
        {},
        {},
        0,
        cache_program_id,
        size.normal,
        0,
        FileSys::SaveDataRank::Primary,
        {},
    });

    LOG_INFO(Service_FS,
             "V33_FIX CacheStorageInfo program_id={:016X} space_id={:02X} found=true size={:#x}",
             cache_program_id, space, size.normal);
}

void ISaveDataInfoReader::FindAllSaves(FileSys::SaveDataSpaceId space) {
''',
    "enumerate an existing current-program cache entry without creating it",
)

fsp_path = Path("src/core/hle/service/filesystem/fsp/fsp_srv.cpp")
replace_once(
    fsp_path,
    '''Result FSP_SRV::OpenSaveDataInfoReaderOnlyCacheStorage(
    OutInterface<ISaveDataInfoReader> out_interface) {
    LOG_WARNING(Service_FS, "(STUBBED) called");

    *out_interface = std::make_shared<ISaveDataInfoReader>(system, save_data_controller,
                                                           FileSys::SaveDataSpaceId::Temporary);

    R_SUCCEED();
}
''',
    '''Result FSP_SRV::OpenSaveDataInfoReaderOnlyCacheStorage(
    OutInterface<ISaveDataInfoReader> out_interface) {
    LOG_INFO(Service_FS, "V33_FIX OpenCacheStorageInfoReader program_id={:016X}", program_id);

    // Cache storage is persistent user-NAND data. Filter the reader to this process so it does
    // not expose another title's cache and so the operation remains read-only when none exists.
    *out_interface = std::make_shared<ISaveDataInfoReader>(
        system, save_data_controller, FileSys::SaveDataSpaceId::User, program_id);

    R_SUCCEED();
}
''',
    "open command 62 on the current program's NandUser cache",
)
