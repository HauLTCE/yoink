"""Ruby language specification."""

from __future__ import annotations

import re
from yoink.lang import LangSpec

RUBY_STDLIB = frozenset({
    "abbrev", "base64", "benchmark", "bigdecimal", "cgi", "csv", "date",
    "delegate", "digest", "drb", "english", "erb", "etc", "fcntl", "fiddle",
    "fileutils", "find", "forwardable", "getoptlong", "io/console", "io/nonblock",
    "io/wait", "ipaddr", "irb", "json", "logger", "matrix", "monitor",
    "mutex_m", "net/ftp", "net/http", "net/imap", "net/pop", "net/protocol",
    "net/smtp", "nkf", "objspace", "observer", "open-uri", "open3", "openssl",
    "optparse", "ostruct", "pathname", "pp", "prettyprint", "prime", "pstore",
    "psych", "pty", "rdoc", "readline", "reline", "resolv", "ripper", "rss",
    "rubygems", "securerandom", "set", "shellwords", "singleton", "socket",
    "stringio", "strscan", "syslog", "tempfile", "time", "timeout", "tmpdir",
    "tracer", "tsort", "un", "uri", "weakref", "webrick", "yaml", "zlib",
})

RUBY_SPEC = LangSpec(
    id="ruby",
    name="Ruby",
    extensions=(".rb",),
    std_libs=RUBY_STDLIB,
    entry_files=("lib/main.rb", "main.rb", "app.rb", "config.ru"),
    package_manifests=("Gemfile",),
    license_files=("LICENSE", "LICENSE.txt", "MIT-LICENSE"),
    import_res=(
        re.compile(r"""\b(?P<kind>require_relative|require|load)\s*(?:\(\s*)?['"]([^'"]+)['"]""", re.MULTILINE),
        re.compile(r"""\bautoload\s+:[A-Za-z0-9_]+\s*,\s*['"]([^'"]+)['"]""", re.MULTILINE),
    ),
    comment_res=(r"#[^\n]*", r"=begin[\s\S]*?=end"),
    package_manager="bundler",
    verify_command="ruby -c",
    lockfiles=("Gemfile.lock",),
)
