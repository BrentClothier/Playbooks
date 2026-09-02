#!/usr/bin/env python3
from pathlib import Path

# V37 resolved cache command 51 to Minecraft's correct program ID and proved that the cache and
# account filesystems accept every observed mutation. The remaining popup occurs immediately after
# the account save reports 0x67ff00000 bytes free even though its persisted normal allocation is
# only 0x12000000 bytes. A real save-data filesystem reports capacity inside its own container;
# Eden incorrectly attaches the entire NandUser capacity getter to every opened save directory.
#
# Add a save-specific SizeGetter and select it for command 51 whenever persisted allocation
# metadata exists. Free space remains dynamic, cannot exceed the allocation minus directory usage,
# and cannot exceed the backing storage's free space. Journal allocation is reserved separately and
# therefore is not part of the mounted data filesystem's total size.


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


types_path = Path("src/core/hle/service/filesystem/fsp/fsp_types.h")
replace_once(
    types_path,
    '''    static SizeGetter FromStorageId(const FileSystemController& fsc, FileSys::StorageId id) {
        return {
            [&fsc, id] { return fsc.GetFreeSpaceSize(id); },
            [&fsc, id] { return fsc.GetTotalSpaceSize(id); },
        };
    }
''',
    '''    static SizeGetter FromStorageId(const FileSystemController& fsc, FileSys::StorageId id) {
        return {
            [&fsc, id] { return fsc.GetFreeSpaceSize(id); },
            [&fsc, id] { return fsc.GetTotalSpaceSize(id); },
        };
    }

    static SizeGetter FromSaveData(const FileSystemController& fsc, FileSys::StorageId id,
                                   FileSys::VirtualDir dir, u64 total_size) {
        return {
            [&fsc, id, dir, total_size] {
                const u64 used_size = dir->GetSize();
                const u64 quota_free_size =
                    used_size < total_size ? total_size - used_size : 0;
                const u64 storage_free_size = fsc.GetFreeSpaceSize(id);
                return quota_free_size < storage_free_size ? quota_free_size : storage_free_size;
            },
            [total_size] { return total_size; },
        };
    }
''',
    "add save-container capacity reporting",
)

srv_path = Path("src/core/hle/service/filesystem/fsp/fsp_srv.cpp")
replace_once(
    srv_path,
    '''    *out_interface =
        std::make_shared<IFileSystem>(system, std::move(dir), SizeGetter::FromStorageId(fsc, id));

    R_SUCCEED();
}

Result FSP_SRV::OpenSaveDataFileSystemBySystemSaveDataId''',
    '''    auto size_getter = SizeGetter::FromStorageId(fsc, id);
    if (space_id == FileSys::SaveDataSpaceId::User) {
        const auto allocation = save_data_controller->ReadSaveDataSize(
            attribute.type, attribute.program_id, attribute.user_id);
        if (allocation.normal != 0) {
            const u64 used_size = dir->GetSize();
            const u64 quota_free_size =
                used_size < allocation.normal ? allocation.normal - used_size : 0;
            LOG_INFO(Service_FS,
                     "V38_FIX SaveDataCapacity type={:02X} program_id={:016X} total={:#x} "
                     "used={:#x} free={:#x}",
                     static_cast<u8>(attribute.type), attribute.program_id, allocation.normal,
                     used_size, quota_free_size);
            size_getter = SizeGetter::FromSaveData(fsc, id, dir, allocation.normal);
        }
    }

    *out_interface =
        std::make_shared<IFileSystem>(system, std::move(dir), std::move(size_getter));

    R_SUCCEED();
}

Result FSP_SRV::OpenSaveDataFileSystemBySystemSaveDataId''',
    "use the persisted save allocation for command-51 filesystem capacity",
)

print("applied v38 save-container quota reporting")
