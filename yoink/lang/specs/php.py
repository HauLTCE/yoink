"""PHP language specification."""

from __future__ import annotations

import re
from yoink.lang import LangSpec

PHP_STDLIB = frozenset({
    "Exception", "ErrorException", "Error", "Throwable", "PDO", "PDOException",
    "DateTime", "DateTimeImmutable", "DateTimeZone", "DateInterval", "DatePeriod",
    "SplFileInfo", "SplFileObject", "ArrayObject", "ArrayIterator", "Iterator",
    "IteratorAggregate", "Countable", "Serializable", "JsonSerializable",
    "Closure", "Generator", "WeakReference", "WeakMap", "Fiber", " stdClass",
})

PHP_SPEC = LangSpec(
    id="php",
    name="PHP",
    extensions=(".php",),
    std_libs=PHP_STDLIB,
    entry_files=("index.php", "public/index.php", "src/index.php"),
    package_manifests=("composer.json",),
    license_files=("LICENSE", "LICENSE.md"),
    import_res=(
        # `use Foo\Bar;` or `use function Foo\Bar;` or grouped `use Foo\{Bar, Baz};`
        re.compile(r"""^\s*use\s+(?:function\s+|const\s+)?([A-Za-z0-9_\\{},\s]+?)\s*;""", re.MULTILINE),
        # `require_once __DIR__ . '/foo.php'` or `require 'foo.php'`
        re.compile(
            r"""\b(?:require|require_once|include|include_once)\s*(?:\(\s*)?(?:__DIR__\s*\.\s*)?['"]([^'"]+)['"]""",
            re.MULTILINE,
        ),
    ),
    comment_res=(r"//[^\n]*", r"#[^\n\[]*", r"/\*[\s\S]*?\*/"),
    package_manager="composer",
    verify_command="php -l",
    lockfiles=("composer.lock",),
)
