#!/usr/bin/env python3
from pathlib import Path

# V36 proved that Minecraft's filesystem writes, commits, free-space queries, and metadata
# operations all succeed. It also exposed that OpenSaveDataFileSystem receives a zero program ID
# for the cache attribute and consequently opens /save/cache/0000000000000000, while every other
# Minecraft save/cache service path uses 0100D71004694000.
#
# Nintendo's user-save open path resolves a zero program ID to the caller before handling cache
# storage. Eden already performs that resolution for system-save command 52, but omitted it from
# command 51. Restore the same behavior locally in command 51 without changing cache sizes,
# filesystem capacity, save allocation, rendering, or any other filesystem operation.


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


fsp_srv_path = Path("src/core/hle/service/filesystem/fsp/fsp_srv.cpp")
replace_once(
    fsp_srv_path,
    '''Result FSP_SRV::OpenSaveDataFileSystem(OutInterface<IFileSystem> out_interface,
                                       FileSys::SaveDataSpaceId space_id,
                                       FileSys::SaveDataAttribute attribute) {
    LOG_INFO(Service_FS, "V34_DIAG OpenSaveDataFileSystem space_id={:02X} attribute={}",
             space_id, attribute.DebugInfo());

    FileSys::VirtualDir dir{};
''',
    '''Result FSP_SRV::OpenSaveDataFileSystem(OutInterface<IFileSystem> out_interface,
                                       FileSys::SaveDataSpaceId space_id,
                                       FileSys::SaveDataAttribute attribute) {
    const u64 requested_program_id = attribute.program_id;
    if (attribute.program_id == 0) {
        attribute.program_id = program_id;
    }

    LOG_INFO(Service_FS,
             "V37_FIX OpenSaveDataFileSystem space_id={:02X} requested_program_id={:016X} "
             "resolved_program_id={:016X} attribute={}",
             space_id, requested_program_id, attribute.program_id, attribute.DebugInfo());

    FileSys::VirtualDir dir{};
''',
    "resolve command-51 zero program IDs to the current caller",
)

print("applied v37 cache filesystem program-ID resolution")
