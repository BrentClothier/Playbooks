#!/usr/bin/env python3
from pathlib import Path

# Minecraft's split-screen transition can submit a shader region without a recognized terminator.
# Eden's fallback CFG decoder then treats invalid instructions as NOPs and walks into unmapped GPU
# memory indefinitely. Stop the bounded size scan at an unmapped block and, for Minecraft only,
# reject an unterminated shader so the renderer skips that draw instead of freezing.


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


shader_environment_h = Path("src/video_core/shader_environment.h")
shader_environment_cpp = Path("src/video_core/shader_environment.cpp")
shader_cache = Path("src/video_core/shader_cache.cpp")

replace_once(
    shader_environment_h,
    '''    [[nodiscard]] std::optional<u64> Analyze();

    void SetCachedSize(size_t size_bytes);
''',
    '''    [[nodiscard]] std::optional<u64> Analyze();

    [[nodiscard]] GPUVAddr ProgramBase() const noexcept {
        return program_base;
    }

    [[nodiscard]] GPUVAddr AnalysisFailureAddress() const noexcept {
        return analysis_failure_address;
    }

    [[nodiscard]] bool AnalysisStoppedAtUnmappedMemory() const noexcept {
        return analysis_stopped_at_unmapped_memory;
    }

    void SetCachedSize(size_t size_bytes);
''',
    "expose bounded shader-analysis failure details",
)

replace_once(
    shader_environment_h,
    '''    bool has_unbound_instructions = false;
    bool has_hle_engine_state = false;
};
''',
    '''    bool has_unbound_instructions = false;
    bool has_hle_engine_state = false;
    GPUVAddr analysis_failure_address{};
    bool analysis_stopped_at_unmapped_memory = false;
};
''',
    "store shader-analysis failure details",
)

replace_once(
    shader_environment_cpp,
    '''std::optional<u64> GenericEnvironment::Analyze() {
    const std::optional<u64> size{TryFindSize()};
''',
    '''std::optional<u64> GenericEnvironment::Analyze() {
    analysis_failure_address = 0;
    analysis_stopped_at_unmapped_memory = false;
    const std::optional<u64> size{TryFindSize()};
''',
    "reset shader-analysis failure state",
)

replace_once(
    shader_environment_cpp,
    '''    size_t size{BLOCK_SIZE};
    while (size <= MAXIMUM_SIZE) {
        u64* const data = code.data() + offset / INST_SIZE;
''',
    '''    size_t size{BLOCK_SIZE};
    while (size <= MAXIMUM_SIZE) {
        if (!gpu_memory->IsFullyMappedRange(guest_addr, BLOCK_SIZE)) {
            analysis_failure_address = guest_addr;
            analysis_stopped_at_unmapped_memory = true;
            return std::nullopt;
        }
        u64* const data = code.data() + offset / INST_SIZE;
''',
    "stop shader-size scan at unmapped GPU memory",
)

replace_once(
    shader_environment_cpp,
    '''        offset += BLOCK_SIZE;
    }
    return std::nullopt;
}

Tegra::Texture::TICEntry GenericEnvironment::ReadTextureInfo''',
    '''        offset += BLOCK_SIZE;
    }
    analysis_failure_address = guest_addr;
    return std::nullopt;
}

Tegra::Texture::TICEntry GenericEnvironment::ReadTextureInfo''',
    "record a shader that exceeded the bounded scan",
)

replace_once(
    shader_cache,
    '''            GraphicsEnvironment env{*maxwell3d, *gpu_memory, program, base_addr, start_address};
            shader_info = MakeShaderInfo(env, *cpu_shader_addr);
        }
        shader_infos[index] = shader_info;
''',
    '''            GraphicsEnvironment env{*maxwell3d, *gpu_memory, program, base_addr, start_address};
            shader_info = MakeShaderInfo(env, *cpu_shader_addr);
        }
        if (!shader_info) {
            shader_infos[index] = nullptr;
            unique_hashes[index] = 0;
            last_shaders_valid = false;
            return false;
        }
        shader_infos[index] = shader_info;
''',
    "let the renderer skip a rejected graphics shader",
)

replace_once(
    shader_cache,
    '''    if (const std::optional<u64> cached_hash{env.Analyze()}) {
        info->unique_hash = *cached_hash;
        info->size_bytes = env.CachedSizeBytes();
    } else {
        // Slow path, not really hit on commercial games
''',
    '''    if (const std::optional<u64> cached_hash{env.Analyze()}) {
        info->unique_hash = *cached_hash;
        info->size_bytes = env.CachedSizeBytes();
    } else if (program_id == 0x0100D71004694000ULL) {
        static u32 rejected_shader_count{};
        if (rejected_shader_count < 32) {
            LOG_ERROR(HW_GPU,
                      "V42_FIX RejectUnterminatedShader count={} program_id={:#018x} stage={} "
                      "program_base={:#x} start={:#x} failure_address={:#x} unmapped={}",
                      rejected_shader_count, program_id, static_cast<u32>(env.ShaderStage()),
                      env.ProgramBase(), env.StartAddress(), env.AnalysisFailureAddress(),
                      env.AnalysisStoppedAtUnmappedMemory());
        }
        ++rejected_shader_count;
        return nullptr;
    } else {
        // Slow path, not really hit on commercial games
''',
    "reject Minecraft's unterminated shader instead of entering the unbounded CFG fallback",
)

print("applied v42 Linux Minecraft shader-analysis guard")
