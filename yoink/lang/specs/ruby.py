"""Ruby spec."""

from __future__ import annotations

from yoink.lang import LangSpec

LANG_SPEC = LangSpec(
    id="ruby",
    extensions=(".rb",),
    import_re=(
        r"\brequire_relative\s+['\"](?P<mod>[^'\"]+)",
        r"\brequire\s+['\"](?P<mod>[^'\"]+)",
        r"\bload\s+['\"](?P<mod>[^'\"]+)",
    ),
    namespace_re=None,
    defn_res=(
        r"^\s*def\s+(?:self\.)?{sym}\b",
        r"^\s*(?:class|module)\s+{sym}\b",
        r"^\s*{sym}\s*=",
        r"^\s*attr_(?:reader|writer|accessor)\s+:{sym}\b",
    ),
    stdlib_prefixes=(),
    stdlib_names=frozenset({
        "json", "set", "date", "time", "uri", "net", "http", "fileutils",
        "pathname", "logger", "optparse", "ostruct", "securerandom", "digest",
        "base64", "yaml", "csv", "erb", "minitest", "test", "benchmark",
        "bigdecimal", "cgi", "coverage", "csv", "date", "debug", "delegate",
        "did_you_mean", "digest", "drb", "English", "erb", "etc", "fcntl",
        "fiddle", "fileutils", "find", "forwardable", "getoptlong", "io",
        "ipaddr", "irb", "json", "logger", "matrix", "minitest", "mutex_m",
        "net", "nkf", "observer", "open-uri", "open3", "openssl", "optparse",
        "ostruct", "pathname", "pp", "prettyprint", "prime", "pstore",
        "psych", "racc", "rake", "rational", "rbconfig", "rdoc", "readline",
        "reline", "resolv", "rexml", "rinda", "ripper", "rss", "scanf",
        "securerandom", "set", "shellwords", "singleton", "socket", "stringio",
        "strscan", "syslog", "tempfile", "time", "timeout", "tmpdir", "tsort",
        "un", "uri", "weakref", "yaml", "zlib",
    }),
    comment_res=(r"#.*$", r"=begin.*?=end"),
    flat_sep="#",
    flat_import_first=True,
    init_file=None,
    marker_files=("Gemfile", "*.gemspec", "Rakefile"),
)
