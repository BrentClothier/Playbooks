#!/usr/bin/env python3
from pathlib import Path

path = Path("src/core/hle/kernel/svc.cpp")
text = path.read_text()

old = '''    std::array<uint64_t, 8> args;\n    kernel.CurrentPhysicalCore().SaveSvcArguments(process, args);\n    LOG_TRACE(Kernel_SVC, "{} [0]={:#x} [1]={:#x} [2]={:#x} [3]={:#x} [4]={:#x} [5]={:#x} [6]={:#x}",\n        imm, GetArg32(args, 0), GetArg32(args, 1), GetArg32(args, 2),\n        GetArg32(args, 3), GetArg32(args, 4), GetArg32(args, 5), GetArg32(args, 6));\n    //kernel.EnterSVCProfile();\n    if (process.Is64Bit())\n        Call64(system, imm, args);\n    else\n        Call32(system, imm, args);\n    //kernel.ExitSVCProfile();\n    kernel.CurrentPhysicalCore().LoadSvcArguments(process, args);\n'''

new = '''    std::array<uint64_t, 8> args;\n    kernel.CurrentPhysicalCore().SaveSvcArguments(process, args);\n    const auto input_args = args;\n    LOG_TRACE(Kernel_SVC, "{} [0]={:#x} [1]={:#x} [2]={:#x} [3]={:#x} [4]={:#x} [5]={:#x} [6]={:#x}",\n        imm, GetArg32(args, 0), GetArg32(args, 1), GetArg32(args, 2),\n        GetArg32(args, 3), GetArg32(args, 4), GetArg32(args, 5), GetArg32(args, 6));\n    //kernel.EnterSVCProfile();\n    if (process.Is64Bit())\n        Call64(system, imm, args);\n    else\n        Call32(system, imm, args);\n    //kernel.ExitSVCProfile();\n    if (process.GetProgramId() == 0x0100D71004694000ULL &&\n        static_cast<u32>(args[0]) == 0xD401) {\n        LOG_CRITICAL(Kernel_SVC,\n                     "V15_DIAG SVC returned D401 imm={:#x} input=[{:#x}, {:#x}, {:#x}, {:#x}, {:#x}, {:#x}, {:#x}, {:#x}] output_x0={:#x}",\n                     imm, input_args[0], input_args[1], input_args[2], input_args[3],\n                     input_args[4], input_args[5], input_args[6], input_args[7], args[0]);\n    }\n    kernel.CurrentPhysicalCore().LoadSvcArguments(process, args);\n'''

count = text.count(old)
if count != 1:
    raise RuntimeError(f"expected one SVC dispatch block, found {count}")

path.write_text(text.replace(old, new, 1))
print(f"updated {path}")
