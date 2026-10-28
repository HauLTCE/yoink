"""Swift language specification."""

from __future__ import annotations

import re
from yoink.lang import LangSpec

SWIFT_STDLIB = frozenset({
    "Swift", "Foundation", "Dispatch", "Darwin", "Glibc", "CoreFoundation",
    "CoreGraphics", "UIKit", "AppKit", "SwiftUI", "Combine", "Observation",
    "Concurrency", "os", "simd", "XCTest", "Testing", "Network", "CryptoKit",
})

SWIFT_SPEC = LangSpec(
    id="swift",
    name="Swift",
    extensions=(".swift",),
    std_libs=SWIFT_STDLIB,
    stdlib_prefixes=("Foundation.", "Swift.", "UIKit.", "AppKit.", "SwiftUI."),
    entry_files=("Package.swift", "Sources/main.swift", "main.swift", "App.swift"),
    package_manifests=("Package.swift",),
    license_files=("LICENSE", "LICENSE.txt"),
    import_res=(
        re.compile(
            r"""^\s*(?:@[A-Za-z0-9_]+\s+)?import\s+(?:(?:struct|class|enum|protocol|func|var|let|typealias)\s+)?([A-Za-z_][A-Za-z0-9_.]*)""",
            re.MULTILINE,
        ),
    ),
    comment_res=(r"//[^\n]*", r"/\*[\s\S]*?\*/"),
    package_manager="swiftpm",
    verify_command="swift build",
    lockfiles=("Package.resolved",),
)
