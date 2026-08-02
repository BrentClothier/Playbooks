#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


def insert_after(path: Path, needle: str, insertion: str, label: str) -> None:
    text = path.read_text()
    count = text.count(needle)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(needle, needle + insertion, 1))
    print(f"updated {path}: {label}")


# Log whether Minecraft is actually queueing frames to Nvnflinger.
producer = Path("src/core/hle/service/nvnflinger/buffer_queue_producer.cpp")
insert_after(
    producer,
    '''Status BufferQueueProducer::QueueBuffer(s32 slot, const QueueBufferInput& input, QueueBufferOutput* output) {\n''',
    '''    static u32 v19_queue_buffer_count{};\n    if (v19_queue_buffer_count < 120) {\n        LOG_WARNING(Service_Nvnflinger,\n                    "V19_DIAG QueueBuffer count={} slot={}",\n                    v19_queue_buffer_count, slot);\n    }\n    ++v19_queue_buffer_count;\n\n''',
    "instrument producer QueueBuffer",
)


# Log successful acquisitions by the compositor-side consumer.
consumer = Path("src/core/hle/service/nvnflinger/buffer_queue_consumer.cpp")
insert_after(
    consumer,
    '''    const auto slot = front->slot;\n''',
    '''    static u32 v19_acquire_buffer_count{};\n    if (v19_acquire_buffer_count < 120) {\n        LOG_WARNING(Service_Nvnflinger,\n                    "V19_DIAG AcquireBuffer count={} slot={} frame={} queued_before_pop={}",\n                    v19_acquire_buffer_count, slot, front->frame_number, core->queue.size());\n    }\n    ++v19_acquire_buffer_count;\n''',
    "instrument consumer AcquireBuffer",
)


# Log whether HardwareComposer reaches nvdisp and what it is trying to present.
hwc = Path("src/core/hle/service/nvnflinger/hardware_composer.cpp")
insert_after(
    hwc,
    '''u32 HardwareComposer::ComposeLocked(f32* out_speed_scale, Display& display,\n                                    Nvidia::Devices::nvdisp_disp0& nvdisp) {\n''',
    '''    static u64 v19_compose_call_count{};\n    ++v19_compose_call_count;\n''',
    "count HardwareComposer calls",
)

replace_once(
    hwc,
    '''    if (!any_visible) {\n        *out_speed_scale = 1.0f;\n        return 1;\n    }\n''',
    '''    if (!any_visible) {\n        if (v19_compose_call_count <= 120) {\n            LOG_WARNING(Service_Nvnflinger,\n                        "V19_DIAG ComposeLocked call={} has no visible layers",\n                        v19_compose_call_count);\n        }\n        *out_speed_scale = 1.0f;\n        return 1;\n    }\n''',
    "log missing visible layers",
)

replace_once(
    hwc,
    '''    if (has_acquired_buffer && !composition_stack.empty()) {\n        // Sort back-to-front: lower z first, higher z last so top-most draws last (on top).\n        std::stable_sort(composition_stack.begin(), composition_stack.end(),\n                         [&](const HwcLayer& l, const HwcLayer& r) { return l.z_index < r.z_index; });\n\n        // Composite.\n        nvdisp.Composite(composition_stack);\n    }\n''',
    '''    if (has_acquired_buffer && !composition_stack.empty()) {\n        // Sort back-to-front: lower z first, higher z last so top-most draws last (on top).\n        std::stable_sort(composition_stack.begin(), composition_stack.end(),\n                         [&](const HwcLayer& l, const HwcLayer& r) { return l.z_index < r.z_index; });\n\n        if (v19_compose_call_count <= 240) {\n            const auto& first = composition_stack.front();\n            LOG_WARNING(Service_Nvnflinger,\n                        "V19_DIAG Composite call={} layers={} first_handle={} offset={:#x} size={}x{} stride={} format={:#x}",\n                        v19_compose_call_count, composition_stack.size(), first.buffer_handle,\n                        first.offset, first.width, first.height, first.stride,\n                        static_cast<u32>(first.format));\n        }\n\n        // Composite.\n        nvdisp.Composite(composition_stack);\n    } else if (v19_compose_call_count <= 120) {\n        LOG_WARNING(Service_Nvnflinger,\n                    "V19_DIAG ComposeLocked call={} did not present acquired={} stack_size={}",\n                    v19_compose_call_count, has_acquired_buffer, composition_stack.size());\n    }\n''',
    "instrument HardwareComposer presentation",
)


# A zero nvmap address produces a black framebuffer. Log every early composite and, when the
# address is zero, repin the handle once through the normal nvmap path before presenting it.
nvdisp = Path("src/core/hle/service/nvdrv/devices/nvdisp_disp0.cpp")
replace_once(
    nvdisp,
    '''    for (auto& layer : sorted_layers) {\n        output_layers.emplace_back(Tegra::FramebufferConfig{\n            .address = nvmap.GetHandleAddress(layer.buffer_handle),\n''',
    '''    static u32 v19_composite_layer_count{};\n    for (auto& layer : sorted_layers) {\n        DAddr framebuffer_address = nvmap.GetHandleAddress(layer.buffer_handle);\n        if (framebuffer_address == 0) {\n            const DAddr repinned_address = nvmap.PinHandle(layer.buffer_handle, false);\n            LOG_WARNING(Service_NVDRV,\n                        "V19_COMPAT framebuffer handle={} had zero address; repin returned {:#x}",\n                        layer.buffer_handle, repinned_address);\n            framebuffer_address = repinned_address;\n        }\n\n        if (v19_composite_layer_count < 240) {\n            LOG_WARNING(Service_NVDRV,\n                        "V19_DIAG nvdisp layer={} handle={} address={:#x} offset={:#x} size={}x{} stride={} format={:#x}",\n                        v19_composite_layer_count, layer.buffer_handle, framebuffer_address,\n                        layer.offset, layer.width, layer.height, layer.stride,\n                        static_cast<u32>(layer.format));\n        }\n        ++v19_composite_layer_count;\n\n        output_layers.emplace_back(Tegra::FramebufferConfig{\n            .address = framebuffer_address,\n''',
    "diagnose and repin zero-address framebuffers",
)
