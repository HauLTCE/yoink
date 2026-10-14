"""Go spec."""

from __future__ import annotations

from yoink.lang import LangSpec

_GO_STDLIB = (
    "fmt", "strings", "io", "os", "net", "http", "time", "sync", "context",
    "errors", "sort", "math", "strconv", "bytes", "bufio", "path", "filepath",
    "regexp", "json", "xml", "sql", "log", "testing", "runtime", "unicode",
    "utf8", "utf16", "hex", "base64", "md5", "sha1", "sha256", "sha512",
    "crypto", "tls", "rand", "flag", "embed", "html", "template", "zip",
    "tar", "gzip", "csv", "reflect", "unsafe", "atomic", "signal", "syscall",
    "exec", "user", "mime", "url", "mail", "smtp", "imap", "ftp", "ssh",
    "expvar", "pprof", "trace", "big", "cmplx", "hash", "crc32", "crc64",
    "aes", "cipher", "des", "dsa", "ecdsa", "ed25519", "elliptic", "hmac",
    "rsa", "x509", "pkix", "ascii85", "asn1", "binary", "adler32", "fnv",
    "bzip2", "flate", "lzw", "zlib", "gob", "scanner", "elf", "macho",
    "pe", "debug", "constant", "token", "types", "parse", "syntax", "vet",
    "cgi", "fcgi", "httputil", "httptest", "echo", "mux", "cookiejar",
    "multipart", "websocket", "rpc", "text", "iotest", "ioutil", "fset",
    "printer", "ast", "build", "mod", "semver", "sumdb", "zipapi",
    "chrono", "mapfs", "metrics", "poll", "syslog", "num", "pipe", "env",
    "once", "pool", "bufio2", "conntrack", "slog", "slices", "maps",
    "iter", "weak", "unique", "structs", "cmp",
)

LANG_SPEC = LangSpec(
    id="go",
    extensions=(".go",),
    import_re=(
        r"\"(?P<mod>[^\"]+)\"",
        r"import\s+(?:\.\s+|_\s+|\w+\s+)?\"(?P<mod>[^\"]+)\"",
    ),
    namespace_re=r"^\s*package\s+(?P<ns>\w+)",
    defn_res=(
        r"\bfunc\s+(?:\(\s*\w+\s+[\w.*]+\s*\)\s+)?{sym}\s*\(",
        r"\btype\s+{sym}\s+(?:struct|interface|[A-Za-z_])",
        r"\b(?:var|const)\s+{sym}\b",
    ),
    stdlib_prefixes=(),
    stdlib_names=frozenset(_GO_STDLIB),
    comment_res=(r"//.*$", r"/\*.*?\*/"),
    flat_sep="//",
    flat_import_first=True,
    init_file=None,
    marker_files=("go.mod",),
)
