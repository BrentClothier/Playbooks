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


replace_once(
    "src/core/loader/deconstructed_rom_directory.cpp",
    '''        next_load_addr = *tentative_next_load_addr;\n        modules.insert_or_assign(load_addr, module);\n        LOG_DEBUG(Loader, "loaded module {} @ {:#x}", module, load_addr);''',
    '''        next_load_addr = *tentative_next_load_addr;\n        modules.insert_or_assign(load_addr, module);\n        LOG_INFO(Loader, "V14_DIAG module {} range=[{:#x}, {:#x})", module, load_addr,\n                 next_load_addr);''',
)

replace_once(
    "src/core/hle/kernel/svc/svc_exception.cpp",
    '''        system.CurrentPhysicalCore().LogBacktrace(system.Kernel());''',
    '''        LOG_CRITICAL(Debug_Emulated,\n                     "V14_DIAG panic context: current_process_title_id={:#x}",\n                     system.Kernel().CurrentProcess()->GetProgramId());\n        system.CurrentPhysicalCore().LogBacktrace(system.Kernel());''',
)
