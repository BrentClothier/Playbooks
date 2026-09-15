#!/usr/bin/env python3
from pathlib import Path

# V39 lets Player 2 operate the Linux HLE profile selector and returns the selected UUID correctly.
# Minecraft then opens Player 2's save but immediately asks for another profile because Eden's
# account service still reports only the configured primary user as open. ProfileManager documents
# profile selection as an operation which opens a user, but the HLE profile applet currently only
# returns the UUID. Open every valid game-requested selection before returning it, and log the
# selector flags plus the before/after application user counts.


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


profile_select = Path("src/core/hle/service/am/frontend/applet_profile_select.cpp")

replace_once(
    profile_select,
    '''#include "core/hle/service/acc/errors.h"
''',
    '''#include "core/hle/service/acc/errors.h"
#include "core/hle/service/acc/profile_manager.h"
''',
    "make ProfileManager available to the profile applet",
)

replace_once(
    profile_select,
    '''    frontend.SelectProfile([this](std::optional<Common::UUID> uuid) { SelectionComplete(uuid); },
                           parameters);
''',
    '''    LOG_INFO(Service_AM,
             "V40_FIX ProfileSelectConfig version={} mode={} purpose={} additional_select={} "
             "registration_permitted={} open_count={}",
             static_cast<u32>(profile_select_version), static_cast<u32>(parameters.mode),
             static_cast<u32>(parameters.purpose), parameters.display_options.additional_select,
             parameters.display_options.is_registration_permitted,
             system.GetProfileManager().GetOpenUserCount());

    frontend.SelectProfile([this](std::optional<Common::UUID> uuid) { SelectionComplete(uuid); },
                           parameters);
''',
    "log selector purpose and application open-user state",
)

replace_once(
    profile_select,
    '''    if (uuid.has_value() && uuid->IsValid()) {
        output.result = 0;
        output.uuid_selected = *uuid;
''',
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
        output.uuid_selected = *uuid;
''',
    "open the selected application user before returning it to Minecraft",
)

print("applied v40 Linux additional profile open-user fix")
