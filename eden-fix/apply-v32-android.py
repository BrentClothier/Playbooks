#!/usr/bin/env python3
from pathlib import Path

# Android v31 included several earlier Linux experiments in addition to the fixes that were proven
# necessary. This minimal Android comparison build deliberately omits the speculative MSAA
# depth/stencil clear (v18b/v18c) and the disproven viewport pipeline-key experiment (v27). It keeps
# the boot/IPC fixes, Minecraft-scoped transfer-memory compatibility, framebuffer extent clamp, and
# the v29/v30 sample-alias fix that restored Linux video.
#
# Keep the same package ID as v31 so this APK updates the already-configured test installation.

path = Path("src/android/app/build.gradle.kts")
text = path.read_text()

old = '''            if (isNightly) {
                applicationIdSuffix = ".nightly"
                manifestPlaceholders += mapOf("appNameSuffix" to " Nightly")
            } else {
                manifestPlaceholders += mapOf("appNameSuffix" to "")
            }
'''
new = '''            if (isNightly) {
                applicationIdSuffix = ".nightly"
                manifestPlaceholders += mapOf("appNameSuffix" to " Nightly")
            } else {
                applicationIdSuffix = ".minecraftfix"
                versionNameSuffix = "-minecraftfix-v32-minimal"
                manifestPlaceholders += mapOf("appNameSuffix" to " Minecraft Fix Minimal")
            }
'''

count = text.count(old)
if count != 1:
    raise RuntimeError(f"brand minimal Android build: expected one match, found {count}")

path.write_text(text.replace(old, new, 1))
print(f"updated {path}: brand minimal Android comparison build")
