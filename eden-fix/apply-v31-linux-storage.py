#!/usr/bin/env python3
import re
from pathlib import Path

# Eden commit 54046ac already contains the upstream SaveDataSpaceId mapping fix in both
# FSP_SRV save-opening paths:
#   Temporary                 -> NandUser
#   ProperSystem / SafeMode   -> NandSystem
#
# Minecraft's remaining failure is narrower. SaveDataFactory intentionally clears temporary
# storage at startup, but it deletes the /temp directory itself. The cache-only info reader then
# enumerates SaveDataSpaceId::Temporary (03) before a cache exists and receives a null root.
# Recreate the now-empty root after cleanup so enumeration succeeds without changing the existing
# CreateCacheStorage or GetCacheStorageSize stub behavior.


def verify_mapping(text: str, label: str) -> None:
    temporary = re.findall(
        r"case FileSys::SaveDataSpaceId::Temporary:.*?"
        r"id = FileSys::StorageId::NandUser;\s*break;",
        text,
        flags=re.DOTALL,
    )
    system = re.findall(
        r"case FileSys::SaveDataSpaceId::ProperSystem:\s*"
        r"case FileSys::SaveDataSpaceId::SafeMode:.*?"
        r"id = FileSys::StorageId::NandSystem;\s*break;",
        text,
        flags=re.DOTALL,
    )
    if len(temporary) != 2 or len(system) != 2:
        raise RuntimeError(
            f"{label}: expected the upstream storage mappings in both FSP_SRV switches; "
            f"found Temporary={len(temporary)}, system={len(system)}"
        )


fsp_path = Path("src/core/hle/service/filesystem/fsp/fsp_srv.cpp")
verify_mapping(fsp_path.read_text(), str(fsp_path))
print(f"verified {fsp_path}: upstream SaveDataSpaceId storage mappings are present")

factory_path = Path("src/core/file_sys/savedata_factory.cpp")
factory_text = factory_path.read_text()

old_cleanup = '''    // Delete all temporary storages
    // On hardware, it is expected that temporary storage be empty at first use.
    dir->DeleteSubdirectoryRecursive("temp");
'''

new_cleanup = '''    // Delete all temporary storages.
    // On hardware, it is expected that temporary storage be empty at first use. Keep the empty
    // root itself available: cache-only save enumeration opens SaveDataSpaceId::Temporary before
    // any title has created a cache and treats a missing root as invalid storage.
    dir->DeleteSubdirectoryRecursive("temp");
    const auto temporary_root = dir->CreateDirectoryRelative("temp");
    if (temporary_root == nullptr) {
        LOG_ERROR(Service_FS, "V31_FIX FailedToCreateTemporarySaveRoot");
    } else {
        LOG_INFO(Service_FS, "V31_FIX RecreatedTemporarySaveRoot");
    }
'''

count = factory_text.count(old_cleanup)
if count != 1:
    raise RuntimeError(f"recreate temporary save root: expected one match, found {count}")

factory_path.write_text(factory_text.replace(old_cleanup, new_cleanup, 1))
print(f"updated {factory_path}: recreate the empty Temporary save-data root after cleanup")
