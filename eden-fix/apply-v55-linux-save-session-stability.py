#!/usr/bin/env python3
from pathlib import Path
import re


def replace_once(path, old, new, label):
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match in {path}, found {count}")
    p.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


replace_once(
    "src/core/file_sys/errors.h",
    """constexpr Result ResultPathAlreadyExists{ErrorModule::FS, 2};
constexpr Result ResultUnsupportedSdkVersion{ErrorModule::FS, 50};
""",
    """constexpr Result ResultPathAlreadyExists{ErrorModule::FS, 2};
constexpr Result ResultUsableSpaceNotEnough{ErrorModule::FS, 39};
constexpr Result ResultUnsupportedSdkVersion{ErrorModule::FS, 50};
""",
    "add standard write/flush failure result",
)

replace_once(
    "src/core/file_sys/vfs/vfs.h",
    """    // The primary method of writing to the file. Writes length bytes from data starting at offset
    // into file. Returns number of bytes successfully written.
    virtual std::size_t Write(const u8* data, std::size_t length, std::size_t offset = 0) = 0;

    // Reads exactly one byte at the offset provided, returning std::nullopt on error.
""",
    """    // The primary method of writing to the file. Writes length bytes from data starting at offset
    // into file. Returns number of bytes successfully written.
    virtual std::size_t Write(const u8* data, std::size_t length, std::size_t offset = 0) = 0;
    // Flushes buffered host data when the backing implementation supports it. Implementations
    // without buffered host state may keep the default no-op success behavior.
    virtual bool Flush();

    // Reads exactly one byte at the offset provided, returning std::nullopt on error.
""",
    "declare VfsFile Flush",
)

replace_once(
    "src/core/file_sys/vfs/vfs.cpp",
    """VfsFile::~VfsFile() = default;

std::string VfsFile::GetExtension() const {
""",
    """VfsFile::~VfsFile() = default;

bool VfsFile::Flush() {
    return true;
}

std::string VfsFile::GetExtension() const {
""",
    "default VfsFile Flush",
)

replace_once(
    "src/core/file_sys/vfs/vfs_real.h",
    """    std::size_t Read(u8* data, std::size_t length, std::size_t offset) const override;
    std::size_t Write(const u8* data, std::size_t length, std::size_t offset) override;
    bool Rename(std::string_view name) override;
""",
    """    std::size_t Read(u8* data, std::size_t length, std::size_t offset) const override;
    std::size_t Write(const u8* data, std::size_t length, std::size_t offset) override;
    bool Flush() override;
    bool Rename(std::string_view name) override;
""",
    "declare RealVfsFile Flush",
)

replace_once(
    "src/core/file_sys/vfs/vfs_real.cpp",
    """std::size_t RealVfsFile::Write(const u8* data, std::size_t length, std::size_t offset) {
    size.reset();
    auto lk = base.RefreshReference(path, perms, *reference);
    if (!reference->file || !reference->file->Seek(static_cast<s64>(offset))) {
        return 0;
    }
    return reference->file->WriteSpan(std::span{data, length});
}

bool RealVfsFile::Rename(std::string_view name) {
""",
    """std::size_t RealVfsFile::Write(const u8* data, std::size_t length, std::size_t offset) {
    size.reset();
    auto lk = base.RefreshReference(path, perms, *reference);
    if (!reference->file || !reference->file->Seek(static_cast<s64>(offset))) {
        return 0;
    }
    return reference->file->WriteSpan(std::span{data, length});
}

bool RealVfsFile::Flush() {
    auto lk = base.RefreshReference(path, perms, *reference);
    return reference->file && reference->file->Flush();
}

bool RealVfsFile::Rename(std::string_view name) {
""",
    "flush RealVfsFile host buffer",
)

replace_once(
    "src/core/file_sys/fsa/fs_i_file.h",
    """    Result DoFlush() {
        // Exists for SDK compatibiltity -- No need to flush file.
        R_SUCCEED();
    }
""",
    """    Result DoFlush() {
        R_UNLESS(backend->Flush(), ResultUsableSpaceNotEnough);
        R_SUCCEED();
    }
""",
    "honor guest file Flush",
)

replace_once(
    "src/core/hle/service/am/frontend/applet_profile_select.cpp",
    """    LOG_INFO(Service_AM,
             "V40_FIX ProfileSelectConfig version={} mode={} purpose={} additional_select={} "
             "registration_permitted={} open_count={}",
             static_cast<u32>(profile_select_version), static_cast<u32>(parameters.mode),
             static_cast<u32>(parameters.purpose), parameters.display_options.additional_select,
             parameters.display_options.is_registration_permitted,
             system.GetProfileManager().GetOpenUserCount());

    frontend.SelectProfile([this](std::optional<Common::UUID> uuid) { SelectionComplete(uuid); },
                           parameters);
""",
    """    auto& profile_manager = system.GetProfileManager();
    if (system.GetApplicationProcessProgramID() == 0x0100D71004694000ULL &&
        parameters.display_options.additional_select && profile_manager.GetOpenUserCount() >= 2) {
        Common::UUID primary_user{};
        if (const auto configured_user =
                profile_manager.GetUser(Settings::values.current_user.GetValue())) {
            primary_user = *configured_user;
            for (const auto& open_user : profile_manager.GetOpenUsers()) {
                if (open_user.IsValid() && open_user != primary_user) {
                    profile_manager.CloseUser(open_user);
                }
            }
            if (primary_user.IsValid()) {
                profile_manager.OpenUser(primary_user);
            }
        }
        LOG_WARNING(Service_AM,
                    "V55_FIX ResetAdditionalUserSession primary_uuid={} open_count_after={}",
                    primary_user.FormattedString(), profile_manager.GetOpenUserCount());
    }

    LOG_INFO(Service_AM,
             "V40_FIX ProfileSelectConfig version={} mode={} purpose={} additional_select={} "
             "registration_permitted={} open_count={}",
             static_cast<u32>(profile_select_version), static_cast<u32>(parameters.mode),
             static_cast<u32>(parameters.purpose), parameters.display_options.additional_select,
             parameters.display_options.is_registration_permitted,
             profile_manager.GetOpenUserCount());

    frontend.SelectProfile([this](std::optional<Common::UUID> uuid) { SelectionComplete(uuid); },
                           parameters);
""",
    "reset stale Minecraft additional-user session",
)

marker = re.compile(r"V\d+_(?:DIAG|FIX|COMPAT)")
for path in Path("src").rglob("*"):
    if not path.is_file() or path.suffix not in {".cpp", ".h", ".inl"}:
        continue
    lines = path.read_text().splitlines(True)
    out = []
    i = 0
    changed = False
    while i < len(lines):
        line = lines[i]
        if ("LOG_INFO(" in line or "LOG_WARNING(" in line) and "V55_" not in line:
            block = [line]
            j = i + 1
            while j < len(lines) and j < i + 20 and ");" not in "".join(block):
                block.append(lines[j])
                j += 1
            block_text = "".join(block)
            if marker.search(block_text) and "V55_" not in block_text:
                block_text = block_text.replace("LOG_INFO(", "LOG_DEBUG(", 1).replace(
                    "LOG_WARNING(", "LOG_DEBUG(", 1
                )
                out.append(block_text)
                i = j
                changed = True
                continue
        out.append(line)
        i += 1
    if changed:
        path.write_text("".join(out))

print("applied v55 save durability, split-screen session reset, and corrected log cleanup")
