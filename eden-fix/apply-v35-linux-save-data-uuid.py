#!/usr/bin/env python3
from pathlib import Path

# V34 proved that Minecraft receives valid cache sizes and about 26 GiB of free save-space
# capacity. It also exposed an IPC decoding regression in IApplicationFunctions command 26:
# EnsureSaveData receives the correct profile UUID, but GetSaveDataSize receives the same UUID
# shifted right by seven bytes.
#
# Eden's former manual request structure aligned the 16-byte user ID to an 8-byte boundary after
# the one-byte SaveDataType field (request sizes 24 bytes for GetSaveDataSize and 40 bytes for
# ExtendSaveData). The CMIF serializer introduced later uses C++ alignof(), while Common::UUID has
# alignment 1, so it incorrectly reads the UUID at byte 1. Use an AM-local aligned wire wrapper for
# only these two commands. Do not change Common::UUID globally or any graphics/filesystem code.


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


header_path = Path("src/core/hle/service/am/service/application_functions.h")
replace_once(
    header_path,
    '''struct Applet;
class IStorage;

class IApplicationFunctions final : public ServiceFramework<IApplicationFunctions> {
''',
    '''struct Applet;
class IStorage;

// The AM wire ABI aligns user IDs following SaveDataType to eight bytes. Common::UUID itself has
// byte alignment, so using it directly with the automatic CMIF serializer drops seven bytes of
// request padding and decodes the wrong account.
struct alignas(8) SaveDataUserId {
    Common::UUID value;
};
static_assert(sizeof(SaveDataUserId) == 0x10);
static_assert(alignof(SaveDataUserId) == 8);

class IApplicationFunctions final : public ServiceFramework<IApplicationFunctions> {
''',
    "define the correctly aligned AM save-data user ID wire type",
)

replace_once(
    header_path,
    '''    Result ExtendSaveData(Out<u64> out_required_size, FileSys::SaveDataType type,
                          Common::UUID user_id, u64 normal_size, u64 journal_size);
    Result GetSaveDataSize(Out<u64> out_normal_size, Out<u64> out_journal_size,
                           FileSys::SaveDataType type, Common::UUID user_id);
''',
    '''    Result ExtendSaveData(Out<u64> out_required_size, FileSys::SaveDataType type,
                          SaveDataUserId user_id, u64 normal_size, u64 journal_size);
    Result GetSaveDataSize(Out<u64> out_normal_size, Out<u64> out_journal_size,
                           FileSys::SaveDataType type, SaveDataUserId user_id);
''',
    "use the aligned wire type for AM commands 25 and 26",
)

application_path = Path("src/core/hle/service/am/service/application_functions.cpp")
replace_once(
    application_path,
    '''Result IApplicationFunctions::ExtendSaveData(Out<u64> out_required_size, FileSys::SaveDataType type,
                                             Common::UUID user_id, u64 normal_size,
                                             u64 journal_size) {
    LOG_INFO(Service_AM,
             "V34_DIAG ExtendSaveData type={} user_id={} normal={:#x} journal={:#x}",
             static_cast<u8>(type), user_id.FormattedString(), normal_size, journal_size);

    system.GetFileSystemController().OpenSaveDataController()->WriteSaveDataSize(
        type, m_applet->program_id, user_id.AsU128(), {normal_size, journal_size});
''',
    '''Result IApplicationFunctions::ExtendSaveData(Out<u64> out_required_size, FileSys::SaveDataType type,
                                             SaveDataUserId user_id, u64 normal_size,
                                             u64 journal_size) {
    LOG_INFO(Service_AM,
             "V35_FIX ExtendSaveData type={} user_id={} normal={:#x} journal={:#x}",
             static_cast<u8>(type), user_id.value.FormattedString(), normal_size, journal_size);

    system.GetFileSystemController().OpenSaveDataController()->WriteSaveDataSize(
        type, m_applet->program_id, user_id.value.AsU128(), {normal_size, journal_size});
''',
    "decode ExtendSaveData user IDs at their ABI-defined offset",
)

replace_once(
    application_path,
    '''Result IApplicationFunctions::GetSaveDataSize(Out<u64> out_normal_size, Out<u64> out_journal_size,
                                              FileSys::SaveDataType type, Common::UUID user_id) {
    LOG_DEBUG(Service_AM, "called with type={} user_id={}", type, user_id.FormattedString());

    const auto size = system.GetFileSystemController().OpenSaveDataController()->ReadSaveDataSize(
        type, m_applet->program_id, user_id.AsU128());

    *out_normal_size = size.normal;
    *out_journal_size = size.journal;
    LOG_INFO(Service_AM,
             "V34_DIAG GetSaveDataSize type={} user_id={} normal={:#x} journal={:#x}", type,
             user_id.FormattedString(), *out_normal_size, *out_journal_size);
''',
    '''Result IApplicationFunctions::GetSaveDataSize(Out<u64> out_normal_size, Out<u64> out_journal_size,
                                              FileSys::SaveDataType type, SaveDataUserId user_id) {
    const auto& uuid = user_id.value;

    const auto size = system.GetFileSystemController().OpenSaveDataController()->ReadSaveDataSize(
        type, m_applet->program_id, uuid.AsU128());

    *out_normal_size = size.normal;
    *out_journal_size = size.journal;
    LOG_INFO(Service_AM,
             "V35_FIX GetSaveDataSize type={} user_id={} normal={:#x} journal={:#x}", type,
             uuid.FormattedString(), *out_normal_size, *out_journal_size);
''',
    "decode GetSaveDataSize user IDs at their ABI-defined offset",
)
