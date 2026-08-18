#!/usr/bin/env python3
from pathlib import Path

# V31 proved that SaveDataSpaceId::Temporary now has a valid root, but Minecraft still reports
# full storage. Its startup sequence is explicit: CreateCacheStorage requests 0x8000000 bytes of
# data and 0x2000000 bytes of journal, then FSP_SRV::GetCacheStorageSize returns literal zeroes.
#
# Eden already persists per-title save sizes through SaveDataController. Use that existing path to
# carry the requested cache size from the AM service to the FSP service. This deliberately leaves
# cache creation, filesystem layout, and all graphics fixes unchanged.


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


application_path = Path("src/core/hle/service/am/service/application_functions.cpp")
replace_once(
    application_path,
    '''Result IApplicationFunctions::CreateCacheStorage(Out<u32> out_target_media,
                                                 Out<u64> out_required_size, u16 index,
                                                 u64 normal_size, u64 journal_size) {
    LOG_WARNING(Service_AM, "(STUBBED) called with index={} size={:#x} journal_size={:#x}", index,
                normal_size, journal_size);

    *out_target_media = 1; // Nand
    *out_required_size = 0;

    R_SUCCEED();
}
''',
    '''Result IApplicationFunctions::CreateCacheStorage(Out<u32> out_target_media,
                                                 Out<u64> out_required_size, u16 index,
                                                 u64 normal_size, u64 journal_size) {
    LOG_INFO(Service_AM,
             "V32_FIX StoreCacheStorageSize index={} size={:#x} journal_size={:#x}", index,
             normal_size, journal_size);

    // Cache index 0 is the path used by Minecraft. Eden's existing save-size metadata is
    // per-title and persistent, allowing fsp-srv to read the values from its own controller.
    system.GetFileSystemController().OpenSaveDataController()->WriteSaveDataSize(
        FileSys::SaveDataType::Cache, m_applet->program_id, u128{},
        {normal_size, journal_size});

    *out_target_media = 1; // Nand
    *out_required_size = 0;

    R_SUCCEED();
}
''',
    "persist the requested cache-storage size",
)

fsp_path = Path("src/core/hle/service/filesystem/fsp/fsp_srv.cpp")
replace_once(
    fsp_path,
    '''Result FSP_SRV::GetCacheStorageSize(s32 index, Out<s64> out_data_size, Out<s64> out_journal_size) {
    LOG_WARNING(Service_FS, "(STUBBED) called with index={}", index);

    *out_data_size = 0;
    *out_journal_size = 0;

    R_SUCCEED();
}
''',
    '''Result FSP_SRV::GetCacheStorageSize(s32 index, Out<s64> out_data_size, Out<s64> out_journal_size) {
    const auto size = save_data_controller->ReadSaveDataSize(
        FileSys::SaveDataType::Cache, program_id, u128{});

    *out_data_size = static_cast<s64>(size.normal);
    *out_journal_size = static_cast<s64>(size.journal);

    LOG_INFO(Service_FS,
             "V32_FIX GetCacheStorageSize index={} size={:#x} journal_size={:#x}", index,
             *out_data_size, *out_journal_size);
    R_SUCCEED();
}
''',
    "return the persisted cache-storage size",
)
