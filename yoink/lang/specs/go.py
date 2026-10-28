"""Go language specification."""

from __future__ import annotations

import re
from yoink.lang import LangSpec

GO_STDLIB = frozenset({
    "archive", "archive/tar", "archive/zip", "bufio", "builtin", "bytes",
    "cmp", "compress", "compress/bzip2", "compress/flate", "compress/gzip",
    "compress/lzw", "compress/zlib", "container", "container/heap",
    "container/list", "container/ring", "context", "crypto", "crypto/aes",
    "crypto/cipher", "crypto/des", "crypto/dsa", "crypto/ecdh", "crypto/ecdsa",
    "crypto/ed25519", "crypto/elliptic", "crypto/hmac", "crypto/md5",
    "crypto/rand", "crypto/rc4", "crypto/rsa", "crypto/sha1", "crypto/sha256",
    "crypto/sha512", "crypto/subtle", "crypto/tls", "crypto/x509", "database",
    "database/sql", "database/sql/driver", "debug", "embed", "encoding",
    "encoding/ascii85", "encoding/asn1", "encoding/base32", "encoding/base64",
    "encoding/binary", "encoding/csv", "encoding/gob", "encoding/hex",
    "encoding/json", "encoding/pem", "encoding/xml", "errors", "expvar",
    "flag", "fmt", "go", "hash", "hash/adler32", "hash/crc32", "hash/crc64",
    "hash/fnv", "hash/maphash", "html", "html/template", "image", "index",
    "io", "io/fs", "io/ioutil", "iter", "log", "log/slog", "log/syslog",
    "maps", "math", "math/big", "math/bits", "math/cmplx", "math/rand",
    "math/rand/v2", "mime", "mime/multipart", "net", "net/http",
    "net/http/httptest", "net/http/httputil", "net/mail", "net/netip",
    "net/rpc", "net/smtp", "net/textproto", "net/url", "os", "os/exec",
    "os/signal", "os/user", "path", "path/filepath", "plugin", "reflect",
    "regexp", "regexp/syntax", "runtime", "runtime/debug", "runtime/pprof",
    "runtime/trace", "slices", "sort", "strconv", "strings", "structs",
    "sync", "sync/atomic", "syscall", "testing", "text", "text/scanner",
    "text/tabwriter", "text/template", "time", "unicode", "unicode/utf16",
    "unicode/utf8", "unique", "unsafe", "weak",
})

GO_SPEC = LangSpec(
    id="go",
    name="Go",
    extensions=(".go",),
    std_libs=GO_STDLIB,
    entry_files=("main.go", "cmd/main.go"),
    package_manifests=("go.mod", "go.work"),
    license_files=("LICENSE", "LICENSE.md", "LICENSE.txt"),
    import_res=(
        re.compile(r"""^\s*import\s+(?:[A-Za-z0-9_.]+\s+)?["`]([^"`]+)["`]""", re.MULTILINE),
    ),
    comment_res=(r"//[^\n]*", r"/\*[\s\S]*?\*/"),
    package_manager="go",
    verify_command="go vet ./...",
    lockfiles=("go.sum",),
)
