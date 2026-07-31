#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}")
    file.write_text(text.replace(old, new, 1))
    print(f"updated {path}")


path = "src/video_core/engines/maxwell_dma.cpp"

# Eden's mixed-layout single-line fallback always copied 16 bytes per iteration,
# even when the requested DMA length was only 1 or 8 bytes. That overran the
# requested destination range. Copy the final partial chunk at its real size.
replace_once(
    path,
    '''            if (!is_src_pitch && is_dst_pitch) {\n                UNIMPLEMENTED_IF(regs.line_length_in % 16 != 0);\n                UNIMPLEMENTED_IF(regs.offset_in % 16 != 0);\n                UNIMPLEMENTED_IF(regs.offset_out % 16 != 0);\n                read_buffer.resize_destructive(16);\n                for (u32 offset = 0; offset < regs.line_length_in; offset += 16) {\n                    Tegra::Memory::GpuGuestMemoryScoped<\n                        u8, Tegra::Memory::GuestMemoryFlags::SafeReadCachedWrite>\n                        tmp_write_buffer(memory_manager,\n                                         convert_linear_2_blocklinear_addr(regs.offset_in + offset),\n                                         16, &read_buffer);\n                    tmp_write_buffer.SetAddressAndSize(regs.offset_out + offset, 16);\n                }\n            } else if (is_src_pitch && !is_dst_pitch) {\n                UNIMPLEMENTED_IF(regs.line_length_in % 16 != 0);\n                UNIMPLEMENTED_IF(regs.offset_in % 16 != 0);\n                UNIMPLEMENTED_IF(regs.offset_out % 16 != 0);\n                read_buffer.resize_destructive(16);\n                for (u32 offset = 0; offset < regs.line_length_in; offset += 16) {\n                    Tegra::Memory::GpuGuestMemoryScoped<\n                        u8, Tegra::Memory::GuestMemoryFlags::SafeReadCachedWrite>\n                        tmp_write_buffer(memory_manager, regs.offset_in + offset, 16, &read_buffer);\n                    tmp_write_buffer.SetAddressAndSize(\n                        convert_linear_2_blocklinear_addr(regs.offset_out + offset), 16);\n                }\n            } else {''',
    '''            if (!is_src_pitch && is_dst_pitch) {\n                UNIMPLEMENTED_IF(regs.offset_in % 16 != 0);\n                UNIMPLEMENTED_IF(regs.offset_out % 16 != 0);\n                read_buffer.resize_destructive(16);\n                for (u32 offset = 0; offset < regs.line_length_in; offset += 16) {\n                    const u32 chunk_size =\n                        (std::min)(16U, regs.line_length_in - offset);\n                    Tegra::Memory::GpuGuestMemoryScoped<\n                        u8, Tegra::Memory::GuestMemoryFlags::SafeReadCachedWrite>\n                        tmp_write_buffer(memory_manager,\n                                         convert_linear_2_blocklinear_addr(regs.offset_in + offset),\n                                         chunk_size, &read_buffer);\n                    tmp_write_buffer.SetAddressAndSize(regs.offset_out + offset, chunk_size);\n                }\n            } else if (is_src_pitch && !is_dst_pitch) {\n                UNIMPLEMENTED_IF(regs.offset_in % 16 != 0);\n                UNIMPLEMENTED_IF(regs.offset_out % 16 != 0);\n                read_buffer.resize_destructive(16);\n                for (u32 offset = 0; offset < regs.line_length_in; offset += 16) {\n                    const u32 chunk_size =\n                        (std::min)(16U, regs.line_length_in - offset);\n                    Tegra::Memory::GpuGuestMemoryScoped<\n                        u8, Tegra::Memory::GuestMemoryFlags::SafeReadCachedWrite>\n                        tmp_write_buffer(memory_manager, regs.offset_in + offset, chunk_size,\n                                         &read_buffer);\n                    tmp_write_buffer.SetAddressAndSize(\n                        convert_linear_2_blocklinear_addr(regs.offset_out + offset), chunk_size);\n                }\n            } else {''',
)
