"""C and C++ language specification."""

from __future__ import annotations

import re
from yoink.lang import LangSpec

CPP_STDLIB = frozenset({
    "algorithm", "any", "array", "atomic", "barrier", "bit", "bitset",
    "cassert", "cctype", "cerrno", "cfenv", "cfloat", "charconv", "chrono",
    "cinttypes", "climits", "clocale", "cmath", "codecvt", "compare",
    "complex", "concepts", "condition_variable", "coroutine", "csetjmp",
    "csignal", "cstdarg", "cstddef", "cstdint", "cstdio", "cstdlib",
    "cstring", "ctime", "cuchar", "cwchar", "cwctype", "deque", "exception",
    "execution", "expected", "filesystem", "format", "forward_list",
    "fstream", "functional", "future", "generator", "initializer_list",
    "iomanip", "ios", "iosfwd", "iostream", "istream", "iterator", "latch",
    "limits", "list", "locale", "map", "mdspan", "memory", "memory_resource",
    "mutex", "new", "numbers", "numeric", "optional", "ostream", "print",
    "queue", "random", "ranges", "ratio", "regex", "scoped_allocator",
    "semaphore", "set", "shared_mutex", "source_location", "span", "spanstream",
    "sstream", "stack", "stacktrace", "stdexcept", "stdfloat", "stop_token",
    "streambuf", "string", "string_view", "strstream", "syncstream",
    "system_error", "thread", "tuple", "type_traits", "typeindex", "typeinfo",
    "unordered_map", "unordered_set", "utility", "valarray", "variant",
    "vector", "version",
    # C standard headers
    "assert.h", "ctype.h", "errno.h", "fenv.h", "float.h", "inttypes.h",
    "limits.h", "locale.h", "math.h", "setjmp.h", "signal.h", "stdarg.h",
    "stdbool.h", "stddef.h", "stdint.h", "stdio.h", "stdlib.h", "string.h",
    "time.h", "threads.h", "uchar.h", "wchar.h", "wctype.h", "unistd.h",
    "pthread.h", "sys/types.h", "sys/stat.h", "sys/socket.h", "netinet/in.h",
    "arpa/inet.h", "fcntl.h", "dlfcn.h",
})

CPP_SPEC = LangSpec(
    id="cpp",
    name="C/C++",
    extensions=(".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl"),
    std_libs=CPP_STDLIB,
    entry_files=("main.cpp", "main.c", "src/main.cpp", "src/main.c"),
    package_manifests=("CMakeLists.txt", "vcpkg.json", "conanfile.txt", "conanfile.py", "Makefile", "meson.build"),
    license_files=("LICENSE", "COPYING", "LICENSE.txt"),
    import_res=(
        re.compile(r"""^\s*#\s*include\s*[<"]([^>"]+)[>"]""", re.MULTILINE),
    ),
    comment_res=(r"//[^\n]*", r"/\*[\s\S]*?\*/"),
    package_manager="cmake",
)
