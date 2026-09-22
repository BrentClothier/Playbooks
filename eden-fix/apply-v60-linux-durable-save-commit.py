#!/usr/bin/env python3
from pathlib import Path


def rep(path, old, new, label):
    p = Path(path)
    s = p.read_text()
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match in {path}, found {count}")
    p.write_text(s.replace(old, new, 1))
    print(f"updated {path}: {label}")


rep(
    "src/core/file_sys/vfs/vfs.h",
    """    virtual std::size_t Write(const u8* data, std::size_t length, std::size_t offset = 0) = 0;
    // Flushes buffered host data when the backing implementation supports it. Implementations
    // without buffered host state may keep the default no-op success behavior.
    virtual bool Flush();

    // Reads exactly one byte at the offset provided, returning std::nullopt on error.
""",
    """    virtual std::size_t Write(const u8* data, std::size_t length, std::size_t offset = 0) = 0;
    // Flushes buffered host data when the backing implementation supports it. Implementations
    // without buffered host state may keep the default no-op success behavior.
    virtual bool Flush();
    // Makes prior writes durable when the backing implementation supports it. The default
    // implementation falls back to Flush().
    virtual bool Commit();

    // Reads exactly one byte at the offset provided, returning std::nullopt on error.
""",
    "declare durable VfsFile Commit",
)

rep(
    "src/core/file_sys/vfs/vfs.cpp",
    """bool VfsFile::Flush() {
    return true;
}

std::string VfsFile::GetExtension() const {
""",
    """bool VfsFile::Flush() {
    return true;
}

bool VfsFile::Commit() {
    return Flush();
}

std::string VfsFile::GetExtension() const {
""",
    "default VfsFile Commit",
)

rep(
    "src/core/file_sys/vfs/vfs_real.h",
    """    std::size_t Write(const u8* data, std::size_t length, std::size_t offset) override;
    bool Flush() override;
    bool Rename(std::string_view name) override;
""",
    """    std::size_t Write(const u8* data, std::size_t length, std::size_t offset) override;
    bool Flush() override;
    bool Commit() override;
    bool Rename(std::string_view name) override;
""",
    "declare RealVfsFile Commit",
)

rep(
    "src/core/file_sys/vfs/vfs_real.cpp",
    """bool RealVfsFile::Flush() {
    auto lk = base.RefreshReference(path, perms, *reference);
    return reference->file && reference->file->Flush();
}

bool RealVfsFile::Rename(std::string_view name) {
""",
    """bool RealVfsFile::Flush() {
    auto lk = base.RefreshReference(path, perms, *reference);
    return reference->file && reference->file->Flush();
}

bool RealVfsFile::Commit() {
    auto lk = base.RefreshReference(path, perms, *reference);
    return reference->file && reference->file->Commit();
}

bool RealVfsFile::Rename(std::string_view name) {
""",
    "fsync RealVfsFile on guest filesystem Commit",
)

rep(
    "src/core/hle/service/filesystem/filesystem.h",
    """    std::string GetName() const;

    /**
     * Create a file specified by its path
""",
    """    std::string GetName() const;

    // Commit all files reachable from this mounted directory. RealVfsFile::Commit uses the
    // host IOFile commit path (fflush + fsync on Linux).
    Result Commit() const;

    /**
     * Create a file specified by its path
""",
    "expose VFS directory commit",
)

rep(
    "src/core/hle/service/filesystem/filesystem.cpp",
    """std::string VfsDirectoryServiceWrapper::GetName() const {
    return backing->GetName();
}

Result VfsDirectoryServiceWrapper::CreateFile(const std::string& path_, u64 size) const {
""",
    """std::string VfsDirectoryServiceWrapper::GetName() const {
    return backing->GetName();
}

namespace {
bool CommitDirectoryTree(const FileSys::VirtualDir& directory, u64& committed_files) {
    if (!directory) {
        return false;
    }
    for (const auto& file : directory->GetFiles()) {
        if (!file || !file->Commit()) {
            return false;
        }
        ++committed_files;
    }
    for (const auto& child : directory->GetSubdirectories()) {
        if (!CommitDirectoryTree(child, committed_files)) {
            return false;
        }
    }
    return true;
}
} // namespace

Result VfsDirectoryServiceWrapper::Commit() const {
    u64 committed_files{};
    const bool success = CommitDirectoryTree(backing, committed_files);
    static u32 v60_commit_diag_count{};
    if (v60_commit_diag_count < 160) {
        LOG_WARNING(Service_FS, "V60_FIX FilesystemCommit success={} files={} root={}",
                    success, committed_files, backing ? backing->GetFullPath() : std::string{});
        ++v60_commit_diag_count;
    }
    R_UNLESS(success, FileSys::ResultUsableSpaceNotEnough);
    R_SUCCEED();
}

Result VfsDirectoryServiceWrapper::CreateFile(const std::string& path_, u64 size) const {
""",
    "commit mounted VFS tree durably",
)

rep(
    "src/core/file_sys/fsa/fs_i_filesystem.h",
    """    Result DoCommit() {
        R_THROW(ResultNotImplemented);
    }
""",
    """    Result DoCommit() {
        R_RETURN(backend.Commit());
    }
""",
    "route FSA Commit to mounted VFS",
)

rep(
    "src/core/hle/service/filesystem/fsp/fs_i_filesystem.cpp",
    """Result IFileSystem::Commit() {
    LOG_WARNING(Service_FS, "(STUBBED) called");

    R_SUCCEED();
}
""",
    """Result IFileSystem::Commit() {
    R_RETURN(backend->Commit());
}
""",
    "replace service filesystem Commit stub",
)

rep(
    "src/core/hle/service/am/frontend/applet_profile_select.cpp",
    """        profile_manager.OpenUser(*uuid);
        const auto open_count_after = profile_manager.GetOpenUserCount();

        LOG_DEBUG(Service_AM,
                 "V41_FIX OpenSelectedUsers primary_uuid={} selected_uuid={} "
""",
    """        profile_manager.OpenUser(*uuid);
        const auto open_count_after = profile_manager.GetOpenUserCount();

        static u32 v60_profile_complete_diag_count{};
        if (v60_profile_complete_diag_count < 32) {
            LOG_WARNING(Service_AM,
                        "V60_DIAG AdditionalUserComplete primary_uuid={} selected_uuid={} "
                        "additional_select={} open_before={} open_after={} last_opened={}",
                        primary_user.FormattedString(), uuid->FormattedString(), additional_select,
                        open_count_before, open_count_after,
                        profile_manager.GetLastOpenedUser().FormattedString());
            ++v60_profile_complete_diag_count;
        }

        LOG_DEBUG(Service_AM,
                 "V41_FIX OpenSelectedUsers primary_uuid={} selected_uuid={} "
""",
    "trace additional-user completion after stale-session reset",
)

rep(
    "src/core/hle/service/acc/acc.cpp",
    """    const auto open_users = profile_manager->GetOpenUsers();
    LOG_DEBUG(Service_ACC, "V41_FIX ListOpenUsers count={} last_opened={}",
             profile_manager->GetOpenUserCount(),
             profile_manager->GetLastOpenedUser().FormattedString());
""",
    """    const auto open_users = profile_manager->GetOpenUsers();
    static u32 v60_list_open_users_diag_count{};
    if (v60_list_open_users_diag_count < 64) {
        LOG_WARNING(Service_ACC, "V60_DIAG ListOpenUsers count={} last_opened={}",
                    profile_manager->GetOpenUserCount(),
                    profile_manager->GetLastOpenedUser().FormattedString());
        ++v60_list_open_users_diag_count;
    }
    LOG_DEBUG(Service_ACC, "V41_FIX ListOpenUsers count={} last_opened={}",
             profile_manager->GetOpenUserCount(),
             profile_manager->GetLastOpenedUser().FormattedString());
""",
    "trace Minecraft-visible open-user state",
)

print("applied v60 durable filesystem commit and rejoin diagnostics")
