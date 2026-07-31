#!/usr/bin/env python3
from pathlib import Path

path = Path("src/core/hle/service/nim/nim.cpp")
text = path.read_text()
old = '''        LOG_INFO(Service_NIM, "(STUBBED) called, unknown={}", unknown);\n\n        IPC::ResponseBuilder rb{ctx, 3};\n        rb.Push(ResultSuccess);\n        rb.Push(false);\n'''
new = '''        LOG_WARNING(Service_NIM,\n                    "V13_DIAG IsLargeResourceAvailable unknown={} returning true", unknown);\n\n        IPC::ResponseBuilder rb{ctx, 3};\n        rb.Push(ResultSuccess);\n        rb.Push(true);\n'''
count = text.count(old)
if count != 1:
    raise RuntimeError(f"expected one IsLargeResourceAvailable block, found {count}")
path.write_text(text.replace(old, new, 1))
print(f"updated {path}")
