"""C/C++ spec."""

from __future__ import annotations

from yoink.lang import LangSpec

LANG_SPEC = LangSpec(
    id="cpp",
    extensions=(".c", ".h", ".cpp", ".hpp", ".cc", ".cxx"),
    import_re=(
        r"#\s*include\s*\"(?P<mod>[^\"]+)\"",
        r"#\s*include\s*<(?P<mod>[^>]+)>",
    ),
    namespace_re=r"\bnamespace\s+(?P<ns>[A-Za-z_][\w:]*)",
    defn_res=(
        r"\b(?:class|struct|enum(?:\s+class)?|union)\s+{sym}\b",
        r"\btypedef\b[^;]*\b{sym}\s*;",
        r"\busing\s+{sym}\s*=",
        r"(?:void|int|char|bool|auto|double|float|long|short|unsigned|signed|static|inline|virtual|constexpr|friend|explicit|extern|template[^>]*>|[\w:<>*&]+)\s+{sym}\s*\(",
    ),
    stdlib_prefixes=("std",),
    stdlib_names=frozenset({
        "algorithm", "array", "atomic", "bit", "bitset", "cassert", "cctype",
        "cerrno", "cfenv", "cfloat", "chrono", "cinttypes", "ciso646", "climits",
        "clocale", "cmath", "codecvt", "compare", "complex", "concepts",
        "condition_variable", "coroutine", "csetjmp", "csignal", "cstdarg",
        "cstdbool", "cstddef", "cstdint", "cstdio", "cstdlib", "cstring",
        "ctgmath", "ctime", "cuchar", "cwchar", "cwctype", "deque",
        "exception", "execution", "filesystem", "format", "forward_list",
        "fstream", "functional", "future", "initializer_list", "iomanip",
        "ios", "iosfwd", "iostream", "istream", "iterator", "latch", "limits",
        "list", "locale", "map", "memory", "memory_resource", "mutex", "new",
        "numbers", "numeric", "optional", "ostream", "queue", "random",
        "ranges", "ratio", "regex", "scoped_allocator", "semaphore", "set",
        "shared_mutex", "source_location", "span", "sstream", "stack",
        "stdexcept", "stop_token", "streambuf", "string", "string_view",
        "strstream", "syncstream", "system_error", "thread", "tuple",
        "typeindex", "typeinfo", "type_traits", "unordered_map",
        "unordered_set", "utility", "valarray", "variant", "vector",
        "version",
    }),
    comment_res=(r"//.*$", r"/\*.*?\*/"),
    flat_sep="//",
    flat_import_first=True,
    init_file=None,
    marker_files=("CMakeLists.txt", "*.vcxproj", "Makefile"),
)
