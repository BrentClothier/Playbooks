#!/usr/bin/env python3
from pathlib import Path

# Minecraft's second local player opens Eden's HLE profile selector. The Linux selector currently
# has two independent problems: ControllerNavigation listens only to Player 1/Handheld, and the
# selected sorted row is later interpreted as an index into ProfileManager's unsorted user list.
# It also displays UUIDs supplied by the game as invalid/already active.
#
# Keep the change local to this dialog: opt it into Player 2 navigation, store the UUID directly on
# each Qt row, filter invalid UUIDs, and return that UUID rather than re-resolving a row number.


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


navigation_h = Path("src/yuzu/util/controller_navigation.h")
replace_once(
    navigation_h,
    """    explicit ControllerNavigation(Core::HID::HIDCore& hid_core, QWidget* parent = nullptr);
""",
    """    explicit ControllerNavigation(Core::HID::HIDCore& hid_core, QWidget* parent = nullptr,
                                  bool enable_player2 = false);
""",
    "allow an individual dialog to opt into Player 2 navigation",
)
replace_once(
    navigation_h,
    """    int player1_callback_key{};
    int handheld_callback_key{};
    bool is_controller_set{};
    mutable std::mutex mutex;
    Core::HID::EmulatedController* player1_controller;
    Core::HID::EmulatedController* handheld_controller;
""",
    """    int player1_callback_key{};
    int player2_callback_key{};
    int handheld_callback_key{};
    bool is_controller_set{};
    bool is_player2_enabled{};
    mutable std::mutex mutex;
    Core::HID::EmulatedController* player1_controller;
    Core::HID::EmulatedController* player2_controller{};
    Core::HID::EmulatedController* handheld_controller;
""",
    "store the optional Player 2 controller and callback",
)

navigation_cpp = Path("src/yuzu/util/controller_navigation.cpp")
replace_once(
    navigation_cpp,
    """#include "common/settings_input.h"
""",
    """#include "common/logging.h"
#include "common/settings_input.h"
""",
    "add profile-navigation diagnostics logging",
)
replace_once(
    navigation_cpp,
    """ControllerNavigation::ControllerNavigation(Core::HID::HIDCore& hid_core, QWidget* parent) {
    player1_controller = hid_core.GetEmulatedController(Core::HID::NpadIdType::Player1);
    handheld_controller = hid_core.GetEmulatedController(Core::HID::NpadIdType::Handheld);
    Core::HID::ControllerUpdateCallback engine_callback{
        .on_change = [this](Core::HID::ControllerTriggerType type) { ControllerUpdateEvent(type); },
        .is_npad_service = false,
    };
    player1_callback_key = player1_controller->SetCallback(engine_callback);
    handheld_callback_key = handheld_controller->SetCallback(engine_callback);
    is_controller_set = true;
}
""",
    """ControllerNavigation::ControllerNavigation(Core::HID::HIDCore& hid_core, QWidget* parent,
                                           bool enable_player2)
    : is_player2_enabled{enable_player2} {
    player1_controller = hid_core.GetEmulatedController(Core::HID::NpadIdType::Player1);
    player2_controller = hid_core.GetEmulatedController(Core::HID::NpadIdType::Player2);
    handheld_controller = hid_core.GetEmulatedController(Core::HID::NpadIdType::Handheld);
    Core::HID::ControllerUpdateCallback engine_callback{
        .on_change = [this](Core::HID::ControllerTriggerType type) { ControllerUpdateEvent(type); },
        .is_npad_service = false,
    };
    player1_callback_key = player1_controller->SetCallback(engine_callback);
    if (is_player2_enabled) {
        player2_callback_key = player2_controller->SetCallback(engine_callback);
    }
    handheld_callback_key = handheld_controller->SetCallback(engine_callback);
    is_controller_set = true;

    if (is_player2_enabled) {
        LOG_INFO(Frontend,
                 "V39_FIX ProfileNavigation p1_connected={} p1_style={} p2_connected={} "
                 "p2_style={} handheld_connected={}",
                 player1_controller->IsConnected(),
                 static_cast<u32>(player1_controller->GetNpadStyleIndex()),
                 player2_controller->IsConnected(),
                 static_cast<u32>(player2_controller->GetNpadStyleIndex()),
                 handheld_controller->IsConnected());
    }
}
""",
    "register Player 2 only for opted-in dialogs",
)
replace_once(
    navigation_cpp,
    """        player1_controller->DeleteCallback(player1_callback_key);
        handheld_controller->DeleteCallback(handheld_callback_key);
        is_controller_set = false;
""",
    """        player1_controller->DeleteCallback(player1_callback_key);
        if (is_player2_enabled) {
            player2_controller->DeleteCallback(player2_callback_key);
        }
        handheld_controller->DeleteCallback(handheld_callback_key);
        is_controller_set = false;
""",
    "unregister the optional Player 2 callback",
)
replace_once(
    navigation_cpp,
    """    const auto controller_type = player1_controller->GetNpadStyleIndex();
    const auto& player1_buttons = player1_controller->GetButtonsValues();
    const auto& handheld_buttons = handheld_controller->GetButtonsValues();

    for (std::size_t i = 0; i < player1_buttons.size(); ++i) {
        const bool button = player1_buttons[i].value || handheld_buttons[i].value;
""",
    """    const auto controller_type =
        player1_controller->IsConnected()
            ? player1_controller->GetNpadStyleIndex()
            : (is_player2_enabled && player2_controller->IsConnected()
                   ? player2_controller->GetNpadStyleIndex()
                   : handheld_controller->GetNpadStyleIndex());
    const auto& player1_buttons = player1_controller->GetButtonsValues();
    const auto& player2_buttons = player2_controller->GetButtonsValues();
    const auto& handheld_buttons = handheld_controller->GetButtonsValues();

    for (std::size_t i = 0; i < player1_buttons.size(); ++i) {
        const bool button = player1_buttons[i].value || handheld_buttons[i].value ||
                            (is_player2_enabled && player2_buttons[i].value);
""",
    "merge Player 2 buttons into opted-in navigation",
)
replace_once(
    navigation_cpp,
    """    const auto controller_type = player1_controller->GetNpadStyleIndex();
    const auto& player1_sticks = player1_controller->GetSticksValues();
    const auto& handheld_sticks = player1_controller->GetSticksValues();
    bool update = false;

    for (std::size_t i = 0; i < player1_sticks.size(); ++i) {
        const Common::Input::StickStatus stick{
            .left = player1_sticks[i].left || handheld_sticks[i].left,
            .right = player1_sticks[i].right || handheld_sticks[i].right,
            .up = player1_sticks[i].up || handheld_sticks[i].up,
            .down = player1_sticks[i].down || handheld_sticks[i].down,
        };
""",
    """    const auto controller_type =
        player1_controller->IsConnected()
            ? player1_controller->GetNpadStyleIndex()
            : (is_player2_enabled && player2_controller->IsConnected()
                   ? player2_controller->GetNpadStyleIndex()
                   : handheld_controller->GetNpadStyleIndex());
    const auto& player1_sticks = player1_controller->GetSticksValues();
    const auto& player2_sticks = player2_controller->GetSticksValues();
    const auto& handheld_sticks = handheld_controller->GetSticksValues();
    bool update = false;

    for (std::size_t i = 0; i < player1_sticks.size(); ++i) {
        const Common::Input::StickStatus stick{
            .left = player1_sticks[i].left || handheld_sticks[i].left ||
                    (is_player2_enabled && player2_sticks[i].left),
            .right = player1_sticks[i].right || handheld_sticks[i].right ||
                     (is_player2_enabled && player2_sticks[i].right),
            .up = player1_sticks[i].up || handheld_sticks[i].up ||
                  (is_player2_enabled && player2_sticks[i].up),
            .down = player1_sticks[i].down || handheld_sticks[i].down ||
                    (is_player2_enabled && player2_sticks[i].down),
        };
""",
    "merge Player 2 sticks and use the actual handheld stick state",
)

profile_h = Path("src/yuzu/applets/qt_profile_select.h")
replace_once(
    profile_h,
    """    int GetIndex() const;
""",
    """    std::optional<Common::UUID> GetUUID() const;
""",
    "return the UUID stored on the selected Qt row",
)
replace_once(
    profile_h,
    """    int user_index = 0;
""",
    """    std::optional<Common::UUID> selected_user;
""",
    "store the selected UUID instead of a model row number",
)

profile_cpp = Path("src/yuzu/applets/qt_profile_select.cpp")
replace_once(
    profile_cpp,
    """#include <mutex>
""",
    """#include <algorithm>
#include <mutex>
""",
    "add invalid UUID filtering support",
)
replace_once(
    profile_cpp,
    """#include "common/fs/path_util.h"
#include "common/string_util.h"
""",
    """#include "common/fs/path_util.h"
#include "common/logging.h"
#include "common/string_util.h"
""",
    "add profile-selector diagnostics logging",
)
replace_once(
    profile_cpp,
    """    controller_navigation = new ControllerNavigation(system.HIDCore(), this);
""",
    """    controller_navigation = new ControllerNavigation(system.HIDCore(), this, true);
""",
    "enable Player 2 navigation only in the profile selector",
)
replace_once(
    profile_cpp,
    """    const auto& profiles = profile_manager.GetAllUsers();
    for (const auto& user : profiles) {
        Service::Account::ProfileBase profile{};
        if (!profile_manager.GetProfileBase(user, profile))
            continue;

        const auto username = Common::StringFromFixedZeroTerminatedBuffer(
            reinterpret_cast<const char*>(profile.username.data()), profile.username.size());

        list_items.push_back(QList<QStandardItem*>{new QStandardItem{
            GetIcon(user), FormatUserEntryText(QString::fromStdString(username), user)}});
    }

    for (const auto& item : list_items)
        item_model->appendRow(item);
""",
    """    const auto& profiles = profile_manager.GetAllUsers();
    for (const auto& user : profiles) {
        const bool is_invalid = std::find(parameters.invalid_uid_list.begin(),
                                          parameters.invalid_uid_list.end(),
                                          user) != parameters.invalid_uid_list.end();
        if (is_invalid) {
            LOG_INFO(Frontend, "V39_FIX ProfileFiltered uuid={}", user.FormattedString());
            continue;
        }

        Service::Account::ProfileBase profile{};
        if (!profile_manager.GetProfileBase(user, profile))
            continue;

        const auto username = Common::StringFromFixedZeroTerminatedBuffer(
            reinterpret_cast<const char*>(profile.username.data()), profile.username.size());

        auto* item = new QStandardItem{
            GetIcon(user), FormatUserEntryText(QString::fromStdString(username), user)};
        item->setData(QString::fromStdString(user.RawString()), Qt::UserRole);
        list_items.push_back(QList<QStandardItem*>{item});
        LOG_INFO(Frontend, "V39_FIX ProfileVisible uuid={}", user.FormattedString());
    }

    for (const auto& item : list_items)
        item_model->appendRow(item);

    if (item_model->rowCount() > 0) {
        const auto first_index = item_model->index(0, 0);
        tree_view->setCurrentIndex(first_index);
        SelectUser(first_index);
    }
""",
    "filter invalid profiles and bind UUIDs to their displayed rows",
)
replace_once(
    profile_cpp,
    """int QtProfileSelectionDialog::exec() {
    // Skip profile selection when there's only one.
    if (profile_manager.GetUserCount() == 1) {
        user_index = 0;
        return QDialog::Accepted;
    }
    return QDialog::exec();
}

void QtProfileSelectionDialog::accept() {
    QDialog::accept();
}

void QtProfileSelectionDialog::reject() {
    user_index = 0;
    QDialog::reject();
}

int QtProfileSelectionDialog::GetIndex() const {
    return user_index;
}

void QtProfileSelectionDialog::SelectUser(const QModelIndex& index) {
    user_index = index.row();
}
""",
    """int QtProfileSelectionDialog::exec() {
    // Skip profile selection when there's exactly one valid choice.
    if (item_model->rowCount() == 1 && selected_user.has_value()) {
        LOG_INFO(Frontend, "V39_FIX ProfileAutoSelect uuid={}",
                 selected_user->FormattedString());
        return QDialog::Accepted;
    }
    if (item_model->rowCount() == 0) {
        LOG_WARNING(Frontend, "V39_FIX ProfileSelect has no valid users");
        return QDialog::Rejected;
    }
    return QDialog::exec();
}

void QtProfileSelectionDialog::accept() {
    if (!selected_user.has_value()) {
        return;
    }
    LOG_INFO(Frontend, "V39_FIX ProfileAccepted uuid={}", selected_user->FormattedString());
    QDialog::accept();
}

void QtProfileSelectionDialog::reject() {
    selected_user.reset();
    QDialog::reject();
}

std::optional<Common::UUID> QtProfileSelectionDialog::GetUUID() const {
    return selected_user;
}

void QtProfileSelectionDialog::SelectUser(const QModelIndex& index) {
    if (!index.isValid()) {
        selected_user.reset();
        return;
    }

    const auto* item = item_model->itemFromIndex(index);
    const auto raw_uuid = item->data(Qt::UserRole).toString().toStdString();
    selected_user = Common::UUID{raw_uuid};
    LOG_INFO(Frontend, "V39_FIX ProfileHighlighted row={} uuid={}", index.row(),
             selected_user->FormattedString());
}
""",
    "select and return the UUID attached to the sorted row",
)

main_window = Path("src/yuzu/main_window.cpp")
replace_once(
    main_window,
    """    const auto uuid = QtCommon::system->GetProfileManager().GetUser(
        static_cast<std::size_t>(profile_select_applet->GetIndex()));
    if (!uuid.has_value()) {
        emit ProfileSelectorFinishedSelection(std::nullopt);
        return;
    }

    emit ProfileSelectorFinishedSelection(uuid);
""",
    """    const auto uuid = profile_select_applet->GetUUID();
    if (!uuid.has_value()) {
        emit ProfileSelectorFinishedSelection(std::nullopt);
        return;
    }

    LOG_INFO(Frontend, "V39_FIX ProfileSelectorFinished uuid={}", uuid->FormattedString());
    emit ProfileSelectorFinishedSelection(uuid);
""",
    "return the selected row's UUID without re-indexing the sorted profile list",
)

replace_once(
    main_window,
    """    Settings::values.current_user = dialog.GetIndex();
    return true;
}
""",
    """    const auto uuid = dialog.GetUUID();
    if (!uuid.has_value()) {
        return false;
    }

    const auto user_index = QtCommon::system->GetProfileManager().GetUserIndex(*uuid);
    if (!user_index.has_value()) {
        return false;
    }

    LOG_INFO(Frontend, "V39_FIX CurrentUser uuid={} index={}", uuid->FormattedString(),
             *user_index);
    Settings::values.current_user = static_cast<s32>(*user_index);
    return true;
}
""",
    "translate the selected UUID to the persistent settings index",
)

util_cpp = Path("src/yuzu/util/util.cpp")
replace_once(
    util_cpp,
    """    const auto select_profile = [] {
        const Core::Frontend::ProfileSelectParameters parameters{
            .mode = Service::AM::Frontend::UiMode::UserSelector,
            .invalid_uid_list = {},
            .display_options = {},
            .purpose = Service::AM::Frontend::UserSelectionPurpose::General,
        };
        QtProfileSelectionDialog dialog(*QtCommon::system, QtCommon::rootObject, parameters);
        dialog.setWindowFlags(Qt::Dialog | Qt::CustomizeWindowHint | Qt::WindowTitleHint |
                              Qt::WindowSystemMenuHint | Qt::WindowCloseButtonHint);
        dialog.setWindowModality(Qt::WindowModal);

        if (dialog.exec() == QDialog::Rejected) {
            return -1;
        }

        return dialog.GetIndex();
    };

    const auto index = select_profile();
    if (index == -1) {
        return std::nullopt;
    }

    const auto uuid =
        QtCommon::system->GetProfileManager().GetUser(static_cast<std::size_t>(index));
    ASSERT(uuid);

    return uuid;
""",
    """    const auto select_profile = []() -> std::optional<Common::UUID> {
        const Core::Frontend::ProfileSelectParameters parameters{
            .mode = Service::AM::Frontend::UiMode::UserSelector,
            .invalid_uid_list = {},
            .display_options = {},
            .purpose = Service::AM::Frontend::UserSelectionPurpose::General,
        };
        QtProfileSelectionDialog dialog(*QtCommon::system, QtCommon::rootObject, parameters);
        dialog.setWindowFlags(Qt::Dialog | Qt::CustomizeWindowHint | Qt::WindowTitleHint |
                              Qt::WindowSystemMenuHint | Qt::WindowCloseButtonHint);
        dialog.setWindowModality(Qt::WindowModal);

        if (dialog.exec() == QDialog::Rejected) {
            return std::nullopt;
        }

        return dialog.GetUUID();
    };

    return select_profile();
""",
    "use the selected UUID in the general profile utility",
)

print("applied v39 Linux Player 2 profile-selector fix")
