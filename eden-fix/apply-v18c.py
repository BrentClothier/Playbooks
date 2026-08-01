#!/usr/bin/env python3
from pathlib import Path

path = Path("src/video_core/renderer_vulkan/vk_texture_cache.cpp")
text = path.read_text()

old = '''                    .srcAccessMask = was_initialized
                                         ? VK_ACCESS_MEMORY_READ_BIT |
                                               VK_ACCESS_MEMORY_WRITE_BIT
                                         : 0,
'''
new = '''                    .srcAccessMask = was_initialized
                                         ? static_cast<VkAccessFlags>(
                                               VK_ACCESS_MEMORY_READ_BIT |
                                               VK_ACCESS_MEMORY_WRITE_BIT)
                                         : VkAccessFlags{},
'''

count = text.count(old)
if count != 1:
    raise RuntimeError(f"expected one narrowing srcAccessMask expression, found {count}")

path.write_text(text.replace(old, new, 1))
print(f"updated {path}: fix VkAccessFlags narrowing conversion")
