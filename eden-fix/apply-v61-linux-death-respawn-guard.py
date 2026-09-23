#!/usr/bin/env python3
from pathlib import Path

p = Path("src/core/arm/dynarmic/arm_dynarmic_64.cpp")
s = p.read_text()

old = """    case Dynarmic::A64::Exception::NoExecuteFault:
        LOG_CRITICAL(Core_ARM, "Cannot execute instruction at unmapped address {:#016x}", pc);
        ReturnException(pc, PrefetchAbort);
        return;
"""

new = """    case Dynarmic::A64::Exception::NoExecuteFault: {
        // Minecraft Bedrock split-screen can destroy a secondary-player HUD callback during
        // death/respawn, then immediately dispatch through the cleared function pointer. The v60
        // crash signature is unusually specific: a branch to address 0 with X28 carrying the
        // Bedrock poison sentinel 0xDEADC0DE. Treat only that exact Minecraft signature as a
        // no-op callback and resume at LR. All other execute faults keep the normal fatal path.
        const u64 lr = m_parent.m_jit->GetRegister(30);
        const u64 x28 = m_parent.m_jit->GetRegister(28);
        const bool v61_minecraft_dead_callback =
            m_process != nullptr && m_process->GetProgramId() == 0x0100D71004694000ULL &&
            pc <= 4 && x28 == 0xDEADC0DEULL &&
            m_memory.IsValidVirtualAddressRange(lr, sizeof(u32));

        if (v61_minecraft_dead_callback) {
            static u32 v61_dead_callback_count{};
            if (v61_dead_callback_count < 8) {
                LOG_WARNING(Core_ARM,
                            "V61_FIX MinecraftDeadCallback count={} pc={:#x} lr={:#x} "
                            "x0={:#x} x1={:#x} x28={:#x}",
                            v61_dead_callback_count, pc, lr,
                            m_parent.m_jit->GetRegister(0),
                            m_parent.m_jit->GetRegister(1), x28);
                ++v61_dead_callback_count;
            }
            m_parent.m_jit->SetPC(lr);
            m_parent.m_jit->HaltExecution(BreakLoop);
            return;
        }

        LOG_CRITICAL(Core_ARM, "Cannot execute instruction at unmapped address {:#016x}", pc);
        ReturnException(pc, PrefetchAbort);
        return;
    }
"""

count=s.count(old)
if count != 1:
    raise RuntimeError(f"v61 NoExecuteFault anchor: expected 1 match, found {count}")
p.write_text(s.replace(old,new,1))
print("applied v61 Minecraft split-screen death/respawn null-callback guard")
