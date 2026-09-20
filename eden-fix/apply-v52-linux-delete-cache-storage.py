#!/usr/bin/env python3
from pathlib import Path

# Minecraft 1.26.45 now calls fsp-srv command 33 (DeleteCacheStorage) during startup.
# Eden's pinned baseline leaves the command unimplemented, causing ServiceFramework to assert and
# Minecraft to terminate with 2010-0212. Register the real IPC signature used by Horizon (u16
# cache index) and use the same safe compatibility behavior as current Switch-emulator code:
# acknowledge the deletion request without deleting the persistent cache directory.
#
# This deliberately preserves the v31-v38 cache metadata and filesystem contents. The goal is only
# to stop the unimplemented-command abort and let Minecraft continue far enough to reveal whether
# any subsequent 1.26.45 filesystem behavior needs emulation.

def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")

cpp = Path("src/core/hle/service/filesystem/fsp/fsp_srv.cpp")
hdr = Path("src/core/hle/service/filesystem/fsp/fsp_srv.h")

replace_once(
    cpp,
    '        {33, nullptr, "DeleteCacheStorage"},\n',
    '        {33, D<&FSP_SRV::DeleteCacheStorage>, "DeleteCacheStorage"},\n',
    "register DeleteCacheStorage command 33",
)

replace_once(
    hdr,
    '''    Result ExtendSaveDataFileSystem(FileSys::SaveDataSpaceId space_id, u64 save_data_id,
                                    s64 available_size, s64 journal_size);
    Result GetCacheStorageSize(s32 index, Out<s64> out_data_size, Out<s64> out_journal_size);
''',
    '''    Result ExtendSaveDataFileSystem(FileSys::SaveDataSpaceId space_id, u64 save_data_id,
                                    s64 available_size, s64 journal_size);
    Result DeleteCacheStorage(u16 index);
    Result GetCacheStorageSize(s32 index, Out<s64> out_data_size, Out<s64> out_journal_size);
''',
    "declare DeleteCacheStorage IPC handler",
)

replace_once(
    cpp,
    '''Result FSP_SRV::GetCacheStorageSize(s32 index, Out<s64> out_data_size, Out<s64> out_journal_size) {
''',
    '''Result FSP_SRV::DeleteCacheStorage(u16 index) {
    LOG_WARNING(Service_FS,
                "V52_FIX DeleteCacheStorage index={} program_id={:016X} action=acknowledge_only",
                index, program_id);

    // Preserve Eden's v31-v38 persistent cache directory and metadata. Minecraft only needs this
    // IPC request to complete successfully here; actual cache deletion is intentionally deferred.
    R_SUCCEED();
}

Result FSP_SRV::GetCacheStorageSize(s32 index, Out<s64> out_data_size, Out<s64> out_journal_size) {
''',
    "implement safe DeleteCacheStorage compatibility handler",
)

print("applied v52 Linux Minecraft DeleteCacheStorage compatibility fix")
