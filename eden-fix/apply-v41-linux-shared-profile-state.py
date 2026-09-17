#!/usr/bin/env python3
from pathlib import Path

# V40 opens the selected UUID in Core::System's ProfileManager, but the acc:* services create a
# separate ProfileManager and therefore cannot see that state. Profile editing can also reload the
# system manager with every profile marked closed. Share the system-owned manager with acc:* and,
# for an additional-user selection, explicitly retain the configured primary user before opening
# the selected second user.


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


account_service = Path("src/core/hle/service/acc/acc.cpp")
profile_select = Path("src/core/hle/service/am/frontend/applet_profile_select.cpp")

replace_once(
    account_service,
    '''void Module::Interface::ListOpenUsers(HLERequestContext& ctx) {
    LOG_DEBUG(Service_ACC, "called");
    ctx.WriteBuffer(profile_manager->GetOpenUsers());
    IPC::ResponseBuilder rb{ctx, 2};
''',
    '''void Module::Interface::ListOpenUsers(HLERequestContext& ctx) {
    const auto open_users = profile_manager->GetOpenUsers();
    LOG_INFO(Service_ACC, "V41_FIX ListOpenUsers count={} last_opened={}",
             profile_manager->GetOpenUserCount(),
             profile_manager->GetLastOpenedUser().FormattedString());
    ctx.WriteBuffer(open_users);
    IPC::ResponseBuilder rb{ctx, 2};
''',
    "make Minecraft's observed open-user state visible",
)

replace_once(
    account_service,
    '''void LoopProcess(Core::System& system) {
    auto module = std::make_shared<Module>();
    auto profile_manager = std::make_shared<ProfileManager>();
    auto server_manager = std::make_unique<ServerManager>(system);
''',
    '''void LoopProcess(Core::System& system) {
    auto module = std::make_shared<Module>();
    auto profile_manager = std::shared_ptr<ProfileManager>{
        &system.GetProfileManager(), [](ProfileManager*) {}};
    LOG_INFO(Service_ACC, "V41_FIX SharedProfileManager users={} open_count={} last_opened={}",
             profile_manager->GetUserCount(), profile_manager->GetOpenUserCount(),
             profile_manager->GetLastOpenedUser().FormattedString());
    auto server_manager = std::make_unique<ServerManager>(system);
''',
    "share profile state between account services and the profile applet",
)

replace_once(
    profile_select,
    '''    if (uuid.has_value() && uuid->IsValid()) {
        auto& profile_manager = system.GetProfileManager();
        const auto open_count_before = profile_manager.GetOpenUserCount();
        profile_manager.OpenUser(*uuid);
        const auto open_count_after = profile_manager.GetOpenUserCount();

        const bool additional_select =
            profile_select_version == ProfileSelectAppletVersion::Version1
                ? config_old.display_options.additional_select
                : config.display_options.additional_select;
        LOG_INFO(Service_AM,
                 "V40_FIX OpenSelectedUser uuid={} additional_select={} open_count_before={} "
                 "open_count_after={} last_opened={}",
                 uuid->FormattedString(), additional_select, open_count_before, open_count_after,
                 profile_manager.GetLastOpenedUser().FormattedString());

        output.result = 0;
''',
    '''    if (uuid.has_value() && uuid->IsValid()) {
        auto& profile_manager = system.GetProfileManager();
        const auto open_count_before = profile_manager.GetOpenUserCount();
        const bool additional_select =
            profile_select_version == ProfileSelectAppletVersion::Version1
                ? config_old.display_options.additional_select
                : config.display_options.additional_select;

        Common::UUID primary_user{};
        if (const auto configured_user =
                profile_manager.GetUser(Settings::values.current_user.GetValue())) {
            primary_user = *configured_user;
            if (additional_select && primary_user.IsValid()) {
                profile_manager.OpenUser(primary_user);
            }
        }
        profile_manager.OpenUser(*uuid);
        const auto open_count_after = profile_manager.GetOpenUserCount();

        LOG_INFO(Service_AM,
                 "V41_FIX OpenSelectedUsers primary_uuid={} selected_uuid={} "
                 "additional_select={} open_count_before={} open_count_after={} last_opened={}",
                 primary_user.FormattedString(), uuid->FormattedString(), additional_select,
                 open_count_before, open_count_after,
                 profile_manager.GetLastOpenedUser().FormattedString());

        output.result = 0;
''',
    "retain the configured primary profile when adding a second player",
)

replace_once(
    profile_select,
    '''#include "common/assert.h"
#include "common/string_util.h"
''',
    '''#include "common/assert.h"
#include "common/settings.h"
#include "common/string_util.h"
''',
    "read the configured primary user",
)

print("applied v41 Linux shared profile-state fix")
