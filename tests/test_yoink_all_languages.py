"""Comprehensive test suite verifying yoink 2.0 across all 15 languages, modes, manifest parsers, slicers, and security checks.
Compatible with both `pytest` and standalone `python3 tests/test_yoink_all_languages.py` / `python3 -m unittest`.
"""

from __future__ import annotations

import contextlib
import inspect
import subprocess
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

try:
    import pytest
except ImportError:
    pytest = types.ModuleType("pytest")  # type: ignore[assignment]

    class _ExcInfo:
        def __init__(self) -> None:
            self.value: BaseException | None = None

    @contextlib.contextmanager
    def _raises(exc_type: type[BaseException]):
        info = _ExcInfo()
        try:
            yield info
        except exc_type as e:
            info.value = e
            return
        raise AssertionError(f"Expected {exc_type.__name__} to be raised")

    pytest.raises = _raises  # type: ignore[attr-defined]

from yoink import __version__, analyze, extract, yoink
from yoink.acquire.git import parse_source
from yoink.acquire.license import detect_license
from yoink.config import load_config
from yoink.errors import EmitError, SafetyError, StrictModeError, SymbolNotFoundError
from yoink.lang import get_spec, list_specs
from yoink.lang.detect import detect_language
from yoink.manifest import load_manifest
from yoink.util import ensure_safe_write_path


def test_version_and_specs_registry():
    assert __version__ == "2.0.0"
    specs = list_specs()
    spec_ids = {s.id for s in specs}
    expected = {
        "jsts", "go", "rust", "cpp", "csharp", "java", "php", "ruby",
        "kotlin", "swift", "dart", "scala", "lua", "elixir",
    }
    assert expected.issubset(spec_ids)
    assert get_spec("typescript").id == "jsts"
    assert get_spec("golang").id == "go"
    assert get_spec("c++").id == "cpp"
    assert get_spec("c#").id == "csharp"
    assert get_spec("kt").id == "kotlin"


# ---------------------------------------------------------------------------
# 1. PYTHON (AST graph, relative imports, PyPI alias mapping, AST flat slice)
# ---------------------------------------------------------------------------
def test_python_ast_closure_and_executable_flat_slice(tmp_path: Path):
    repo = tmp_path / "py_repo"
    pkg = repo / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (repo / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = [
    "Pillow>=10.0.0",
    "PyYAML==6.0.1",
    "scikit-learn~=1.4.0",
]
""",
        encoding="utf-8",
    )
    (pkg / "__init__.py").write_text("from .service import compute_score\n", encoding="utf-8")
    (pkg / "math_utils.py").write_text(
        """
import math

SCALE_FACTOR = 10

def _internal_round(val: float) -> int:
    return int(math.floor(val * SCALE_FACTOR))

def unused_helper() -> str:
    return "should_be_sliced_out_in_flat_mode"
""",
        encoding="utf-8",
    )
    (pkg / "service.py").write_text(
        """
import json
import yaml
from PIL import Image
from .math_utils import _internal_round

def compute_score(x: float) -> int:
    return _internal_round(x + 1.5)

def unrelated_feature():
    return Image, yaml, json
""",
        encoding="utf-8",
    )
    (pkg / "orphan.py").write_text("def never_called(): pass\n", encoding="utf-8")

    assert detect_language(repo) == "python"

    closure = analyze("compute_score", repo=repo)
    assert closure.language == "python"
    assert closure.modules == {"mypkg.service", "mypkg.math_utils"}
    assert "mypkg.orphan" not in closure.modules
    assert {"math", "json"}.issubset(closure.stdlib)
    ext_map = {d.name: d.version for d in closure.external}
    assert ext_map.get("Pillow") == ">=10.0.0"
    assert ext_map.get("PyYAML") == "==6.0.1"

    bundle_out = tmp_path / "py_bundle"
    manifest, emit_res, _ = extract("compute_score", repo=repo, out=bundle_out, mode="bundle")
    assert (bundle_out / "mypkg" / "service.py").is_file()
    assert (bundle_out / "mypkg" / "math_utils.py").is_file()
    assert (bundle_out / "mypkg" / "__init__.py").is_file()
    assert not (bundle_out / "mypkg" / "orphan.py").exists()
    loaded = load_manifest(bundle_out / "yoink.manifest.json")
    assert loaded.source.language == "python"

    flat_dir = tmp_path / "py_flat"
    _, flat_res, _ = extract("compute_score", repo=repo, out=flat_dir, mode="flat")
    flat_file = flat_res.files[0]
    flat_code = flat_file.read_text(encoding="utf-8")
    assert "def _internal_round" in flat_code
    assert "SCALE_FACTOR = 10" in flat_code
    assert "def compute_score" in flat_code
    assert "unused_helper" not in flat_code
    assert "unrelated_feature" not in flat_code
    assert flat_code.index("def _internal_round") < flat_code.index("def compute_score")

    namespace: dict = {}
    exec(flat_code, namespace)
    assert namespace["compute_score"](2.0) == 35


# ---------------------------------------------------------------------------
# 2. JAVASCRIPT / TYPESCRIPT (tsconfig paths, multi-line imports, .js->.ts)
# ---------------------------------------------------------------------------
def test_jsts_tsconfig_aliases_multiline_and_comments(tmp_path: Path):
    repo = tmp_path / "ts_repo"
    repo.mkdir()
    (repo / "package.json").write_text(
        '{"name": "app", "dependencies": {"zod": "^3.22.0", "@tanstack/query-core": "5.0.0"}}',
        encoding="utf-8",
    )
    (repo / "tsconfig.json").write_text(
        """
        {
          // JSONC comment in tsconfig
          "compilerOptions": {
            "baseUrl": ".",
            "paths": {
              "@/*": ["src/*"],
            }
          }
        }
        """,
        encoding="utf-8",
    )
    src = repo / "src"
    (src / "utils").mkdir(parents=True)
    (src / "utils" / "crypto.ts").write_text(
        """
        import crypto from "node:crypto";
        export function hashToken(raw: string): string {
            return crypto.createHash("sha256").update(raw).digest("hex");
        }
        """,
        encoding="utf-8",
    )
    (src / "models.ts").write_text(
        """
        import { z } from "zod";
        export interface User { id: string; }
        export const UserSchema = z.object({ id: z.string() });
        """,
        encoding="utf-8",
    )
    (src / "auth.ts").write_text(
        """
        /*
         * import { fake } from "commented-out-pkg";
         */
        // import { alsoFake } from "./nonexistent";
        import {
            User,
            UserSchema as Schema
        } from "@/models";
        import { hashToken } from "./utils/crypto.js";
        import { QueryClient } from "@tanstack/query-core/build/lib";

        export async function authenticate(token: string): Promise<User> {
            const h = hashToken(token);
            return Schema.parse({ id: h });
        }
        """,
        encoding="utf-8",
    )

    assert detect_language(repo) == "jsts"
    closure = analyze("authenticate", repo=repo)
    assert closure.language == "jsts"
    assert closure.modules == {"auth", "models", "utils/crypto"}
    assert "node:crypto" in closure.stdlib
    ext_map = {d.name: d.version for d in closure.external}
    assert ext_map == {"@tanstack/query-core": "5.0.0", "zod": "^3.22.0"}
    assert "commented-out-pkg" not in ext_map


# ---------------------------------------------------------------------------
# 3. GO (grouped imports, go.mod local packages, same-package sibling symbol)
# ---------------------------------------------------------------------------
def test_go_grouped_imports_and_implicit_same_package_linking(tmp_path: Path):
    repo = tmp_path / "go_repo"
    repo.mkdir()
    (repo / "go.mod").write_text(
        """
module github.com/acme/payments

go 1.22

require (
    github.com/google/uuid v1.6.0
)
""",
        encoding="utf-8",
    )
    (repo / "internal" / "tax").mkdir(parents=True)
    (repo / "internal" / "tax" / "rate.go").write_text(
        """
package tax

import "math"

func ComputeTax(amount float64) float64 {
    return math.Round(amount * 0.08 * 100) / 100
}
""",
        encoding="utf-8",
    )
    (repo / "pkg" / "billing").mkdir(parents=True)
    (repo / "pkg" / "billing" / "currency.go").write_text(
        """
package billing

import "fmt"

func FormatCurrency(cents int64) string {
    return fmt.Sprintf("$%.2f", float64(cents)/100.0)
}
""",
        encoding="utf-8",
    )
    (repo / "pkg" / "billing" / "invoice.go").write_text(
        """
package billing

import (
    "context"
    "github.com/acme/payments/internal/tax"
    "github.com/google/uuid"
)

func CreateInvoice(ctx context.Context, amount float64) string {
    _ = uuid.NewString()
    total := amount + tax.ComputeTax(amount)
    return FormatCurrency(int64(total * 100))
}
""",
        encoding="utf-8",
    )

    assert detect_language(repo) == "go"
    closure = analyze("CreateInvoice", repo=repo)
    assert closure.modules == {
        "pkg/billing/invoice.go",
        "pkg/billing/currency.go",
        "internal/tax/rate.go",
    }
    assert {"context", "fmt", "math"}.issubset(closure.stdlib)
    assert any(d.name == "github.com/google/uuid" and d.version == "v1.6.0" for d in closure.external)


# ---------------------------------------------------------------------------
# 4. RUST (use crate::{...}, super::, mod declarations, Cargo.toml)
# ---------------------------------------------------------------------------
def test_rust_grouped_use_mod_and_cargo_manifest(tmp_path: Path):
    repo = tmp_path / "rust_repo"
    (repo / "src" / "engine").mkdir(parents=True)
    (repo / "Cargo.toml").write_text(
        """
[package]
name = "demo-rs"
version = "0.1.0"
edition = "2021"

[dependencies]
serde_json = "1.0.114"
tokio = { version = "1.36.0", features = ["full"] }
""",
        encoding="utf-8",
    )
    (repo / "src" / "util.rs").write_text(
        "pub fn clamp(x: i32) -> i32 { x.max(0) }\n",
        encoding="utf-8",
    )
    (repo / "src" / "engine" / "mod.rs").write_text(
        """
use std::collections::HashMap;
use serde_json::Value;
use crate::{util::clamp, engine::worker::run_job};

pub mod worker;

pub fn execute(input: i32) -> i32 {
    let _map: HashMap<String, Value> = HashMap::new();
    run_job(clamp(input))
}
""",
        encoding="utf-8",
    )
    (repo / "src" / "engine" / "worker.rs").write_text(
        """
pub fn run_job(val: i32) -> i32 {
    val * 2
}
""",
        encoding="utf-8",
    )

    assert detect_language(repo) == "rust"
    closure = analyze("execute", repo=repo)
    assert closure.modules == {"crate::engine", "crate::util", "crate::engine::worker"}
    assert "std" in closure.stdlib
    ext_map = {d.name: d.version for d in closure.external}
    assert ext_map.get("serde_json") == "1.0.114"


# ---------------------------------------------------------------------------
# 5. C / C++ (header + implementation automatic pairing & flat deduplication)
# ---------------------------------------------------------------------------
def test_cpp_header_impl_pairing_and_flat_dedup(tmp_path: Path):
    repo = tmp_path / "cpp_repo"
    (repo / "include").mkdir(parents=True)
    (repo / "src").mkdir(parents=True)
    (repo / "CMakeLists.txt").write_text("project(DemoCPP)\n", encoding="utf-8")
    (repo / "include" / "vec3.hpp").write_text(
        """
#pragma once
#include <cmath>

struct Vec3 {
    double x, y, z;
    double norm() const;
};
""",
        encoding="utf-8",
    )
    (repo / "src" / "vec3.cpp").write_text(
        """
#include "vec3.hpp"

double Vec3::norm() const {
    return std::sqrt(x*x + y*y + z*z);
}
""",
        encoding="utf-8",
    )
    (repo / "src" / "physics.cpp").write_text(
        """
#include <vector>
#include "vec3.hpp"

double compute_energy(const Vec3& v) {
    return 0.5 * v.norm() * v.norm();
}
""",
        encoding="utf-8",
    )

    assert detect_language(repo) == "cpp"
    closure = analyze("compute_energy", repo=repo)
    assert closure.modules == {"src/physics.cpp", "include/vec3.hpp", "src/vec3.cpp"}
    assert {"cmath", "vector"}.issubset(closure.stdlib)

    flat_out = tmp_path / "cpp_flat" / "single.cpp"
    _, flat_res, _ = yoink(repo, symbol="compute_energy", out=flat_out, mode="flat")
    flat_txt = flat_res.files[0].read_text(encoding="utf-8")
    assert "#pragma once" not in flat_txt
    assert '#include "vec3.hpp"' not in flat_txt
    assert flat_txt.index("struct Vec3") < flat_txt.index("double Vec3::norm()")
    assert flat_txt.index("struct Vec3") < flat_txt.index("double compute_energy")


# ---------------------------------------------------------------------------
# 6. C# (file-scoped namespaces, .csproj NuGet packages, implicit same-ns)
# ---------------------------------------------------------------------------
def test_csharp_namespaces_and_csproj(tmp_path: Path):
    repo = tmp_path / "cs_repo"
    repo.mkdir()
    (repo / "App.csproj").write_text(
        """
<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
  </ItemGroup>
</Project>
""",
        encoding="utf-8",
    )
    (repo / "Domain" / "Order.cs").parent.mkdir(parents=True)
    (repo / "Domain" / "Order.cs").write_text(
        """
namespace Acme.Domain;

public record Order(string Id, decimal Total);
""",
        encoding="utf-8",
    )
    (repo / "Services" / "Serializer.cs").parent.mkdir(parents=True)
    (repo / "Services" / "Serializer.cs").write_text(
        """
using System;
using Newtonsoft.Json;
using Acme.Domain;

namespace Acme.Services;

public class OrderSerializer {
    public string Dump(Order o) {
        return JsonConvert.SerializeObject(o);
    }
}
""",
        encoding="utf-8",
    )

    assert detect_language(repo) == "csharp"
    closure = analyze("OrderSerializer", repo=repo)
    assert closure.modules == {"Services/Serializer.cs", "Domain/Order.cs"}
    assert "System" in closure.stdlib
    assert any(d.name == "Newtonsoft.Json" and d.version == "13.0.3" for d in closure.external)


# ---------------------------------------------------------------------------
# 7. JAVA (Maven layout, same-package implicit class linking, pom.xml)
# ---------------------------------------------------------------------------
def test_java_maven_same_package_and_pom(tmp_path: Path):
    repo = tmp_path / "java_repo"
    pkg_dir = repo / "src" / "main" / "java" / "com" / "acme" / "billing"
    pkg_dir.mkdir(parents=True)
    (repo / "pom.xml").write_text(
        """
<project>
  <dependencies>
    <dependency>
      <groupId>com.google.guava</groupId>
      <artifactId>guava</artifactId>
      <version>33.0.0-jre</version>
    </dependency>
  </dependencies>
</project>
""",
        encoding="utf-8",
    )
    (pkg_dir / "TaxRules.java").write_text(
        """
package com.acme.billing;

public class TaxRules {
    public static double rate() { return 0.10; }
}
""",
        encoding="utf-8",
    )
    (pkg_dir / "BillingEngine.java").write_text(
        """
package com.acme.billing;

import java.util.List;
import com.google.common.collect.ImmutableList;

public class BillingEngine {
    public double calculate(double subtotal) {
        return subtotal * (1.0 + TaxRules.rate());
    }
}
""",
        encoding="utf-8",
    )

    assert detect_language(repo) == "java"
    closure = analyze("BillingEngine", repo=repo)
    assert closure.modules == {"com.acme.billing.BillingEngine", "com.acme.billing.TaxRules"}
    assert "java.util.List" in closure.stdlib


# ---------------------------------------------------------------------------
# 8. PHP (composer.json PSR-4 autoload + grouped use imports)
# ---------------------------------------------------------------------------
def test_php_psr4_and_grouped_use(tmp_path: Path):
    repo = tmp_path / "php_repo"
    (repo / "src" / "Support").mkdir(parents=True)
    (repo / "composer.json").write_text(
        """
{
  "require": {
    "monolog/monolog": "^3.5"
  },
  "autoload": {
    "psr-4": {
      "Acme\\\\App\\\\": "src/"
    }
  }
}
""",
        encoding="utf-8",
    )
    (repo / "src" / "Support" / "Hasher.php").write_text(
        """<?php
namespace Acme\\App\\Support;

class Hasher {
    public static function make(string $v): string { return sha1($v); }
}
""",
        encoding="utf-8",
    )
    (repo / "src" / "AuthManager.php").write_text(
        """<?php
namespace Acme\\App;

use Acme\\App\\Support\\{Hasher};
use Monolog\\Logger;

class AuthManager {
    public function verify(string $pw): string {
        return Hasher::make($pw);
    }
}
""",
        encoding="utf-8",
    )

    assert detect_language(repo) == "php"
    closure = analyze("AuthManager", repo=repo)
    assert closure.modules == {"src/AuthManager.php", "src/Support/Hasher.php"}


# ---------------------------------------------------------------------------
# 9. RUBY (require_relative, lib/ resolution, Gemfile)
# ---------------------------------------------------------------------------
def test_ruby_require_and_gemfile(tmp_path: Path):
    repo = tmp_path / "rb_repo"
    (repo / "lib" / "billing").mkdir(parents=True)
    (repo / "Gemfile").write_text("source 'https://rubygems.org'\ngem 'oj', '~> 3.16'\n", encoding="utf-8")
    (repo / "lib" / "billing" / "discount.rb").write_text(
        """
module Discount
  def self.apply(x)
    x * 0.9
  end
end
""",
        encoding="utf-8",
    )
    (repo / "lib" / "checkout.rb").write_text(
        """
require 'json'
require 'oj'
require_relative 'billing/discount'

class Checkout
  def process(total)
    Discount.apply(total)
  end
end
""",
        encoding="utf-8",
    )

    assert detect_language(repo) == "ruby"
    closure = analyze("Checkout", repo=repo)
    assert closure.modules == {"checkout.rb", "billing/discount.rb"}
    assert "json" in closure.stdlib
    assert any(d.name == "oj" and d.version == "~> 3.16" for d in closure.external)


# ---------------------------------------------------------------------------
# 10. KOTLIN (new language: same-package symbol linking, build.gradle.kts)
# ---------------------------------------------------------------------------
def test_kotlin_gradle_and_same_package_resolution(tmp_path: Path):
    repo = tmp_path / "kt_repo"
    pkg = repo / "src" / "main" / "kotlin" / "io" / "acme"
    pkg.mkdir(parents=True)
    (repo / "build.gradle.kts").write_text(
        """
dependencies {
    implementation("io.ktor:ktor-client-core:2.3.8")
}
""",
        encoding="utf-8",
    )
    (pkg / "Validator.kt").write_text(
        """
package io.acme

fun isValidEmail(s: String): Boolean = s.contains("@")
""",
        encoding="utf-8",
    )
    (pkg / "RegistrationService.kt").write_text(
        """
package io.acme

import io.ktor.client.*

class RegistrationService {
    fun register(email: String): Boolean = isValidEmail(email)
}
""",
        encoding="utf-8",
    )

    assert detect_language(repo) == "kotlin"
    closure = analyze("RegistrationService", repo=repo)
    assert closure.modules == {"io.acme.RegistrationService", "io.acme.Validator"}
    assert any("ktor" in d.name for d in closure.external)


# ---------------------------------------------------------------------------
# 11. SWIFT (new language: Sources/<Target> cross-file resolution, Package.swift)
# ---------------------------------------------------------------------------
def test_swift_package_and_cross_file_target_resolution(tmp_path: Path):
    repo = tmp_path / "swift_repo"
    target_dir = repo / "Sources" / "CoreKit"
    target_dir.mkdir(parents=True)
    (repo / "Package.swift").write_text(
        """
// swift-tools-version: 5.9
import PackageDescription
let package = Package(
    name: "CoreKit",
    dependencies: [
        .package(url: "https://github.com/apple/swift-log.git", from: "1.5.0")
    ]
)
""",
        encoding="utf-8",
    )
    (target_dir / "Signer.swift").write_text(
        """
import Foundation

public struct Signer {
    public static func sign(_ msg: String) -> String { "sig:" + msg }
}
""",
        encoding="utf-8",
    )
    (target_dir / "Session.swift").write_text(
        """
import Foundation

public final class SessionManager {
    public func open(token: String) -> String {
        return Signer.sign(token)
    }
}
""",
        encoding="utf-8",
    )

    assert detect_language(repo) == "swift"
    closure = analyze("SessionManager", repo=repo)
    assert closure.modules == {"CoreKit/Session.swift", "CoreKit/Signer.swift"}
    assert "Foundation" in closure.stdlib


# ---------------------------------------------------------------------------
# 12. DART (new language: pubspec.yaml self-package `package:my_app/...`)
# ---------------------------------------------------------------------------
def test_dart_pubspec_and_self_package_imports(tmp_path: Path):
    repo = tmp_path / "dart_repo"
    (repo / "lib" / "src").mkdir(parents=True)
    (repo / "pubspec.yaml").write_text(
        """
name: shop_app
version: 1.0.0
dependencies:
  http: ^1.2.0
""",
        encoding="utf-8",
    )
    (repo / "lib" / "src" / "formatter.dart").write_text(
        """
String formatPrice(double v) => '\\$${v.toStringAsFixed(2)}';
""",
        encoding="utf-8",
    )
    (repo / "lib" / "cart.dart").write_text(
        """
import 'dart:math';
import 'package:http/http.dart';
import 'package:shop_app/src/formatter.dart';

class ShoppingCart {
  String renderTotal(double amount) => formatPrice(max(0.0, amount));
}
""",
        encoding="utf-8",
    )

    assert detect_language(repo) == "dart"
    closure = analyze("ShoppingCart", repo=repo)
    assert closure.modules == {"cart.dart", "src/formatter.dart"}
    assert "dart:math" in closure.stdlib
    assert any(d.name == "http" and d.version == "^1.2.0" for d in closure.external)


# ---------------------------------------------------------------------------
# 13. SCALA (new language: grouped imports `import pkg.{A, B => C}`, build.sbt)
# ---------------------------------------------------------------------------
def test_scala_grouped_imports_and_sbt(tmp_path: Path):
    repo = tmp_path / "scala_repo"
    pkg = repo / "src" / "main" / "scala" / "com" / "acme"
    pkg.mkdir(parents=True)
    (repo / "build.sbt").write_text(
        'libraryDependencies += "org.typelevel" %% "cats-core" % "2.10.0"\n',
        encoding="utf-8",
    )
    (pkg / "Codec.scala").write_text(
        """
package com.acme

object Codec {
  def encode(s: String): String = s.reverse
}
""",
        encoding="utf-8",
    )
    (pkg / "Pipeline.scala").write_text(
        """
package com.acme

import scala.util.Try
import cats.syntax.all._

class Pipeline {
  def run(input: String): Try[String] = Try(Codec.encode(input))
}
""",
        encoding="utf-8",
    )

    assert detect_language(repo) == "scala"
    closure = analyze("Pipeline", repo=repo)
    assert closure.modules == {"com.acme.Pipeline", "com.acme.Codec"}
    assert "scala.util.Try" in closure.stdlib


# ---------------------------------------------------------------------------
# 14. LUA (new language: require("pkg.mod"), init.lua resolution)
# ---------------------------------------------------------------------------
def test_lua_require_and_init_resolution(tmp_path: Path):
    repo = tmp_path / "lua_repo"
    (repo / "core").mkdir(parents=True)
    (repo / "core" / "vec.lua").write_text(
        """
local M = {}
function M.add(a, b) return a + b end
return M
""",
        encoding="utf-8",
    )
    (repo / "game.lua").write_text(
        """
local math = require("math")
local vec = require("core.vec")

function step_simulation(x, y)
    return vec.add(x, y)
end
""",
        encoding="utf-8",
    )

    assert detect_language(repo) == "lua"
    closure = analyze("step_simulation", repo=repo)
    assert closure.modules == {"game", "core.vec"}
    assert "math" in closure.stdlib


# ---------------------------------------------------------------------------
# 15. ELIXIR (new language: defmodule, multi-alias `alias App.{A, B}`, mix.exs)
# ---------------------------------------------------------------------------
def test_elixir_defmodule_multi_alias_and_mix(tmp_path: Path):
    repo = tmp_path / "ex_repo"
    (repo / "lib" / "accounts").mkdir(parents=True)
    (repo / "mix.exs").write_text(
        """
defmodule MyApp.MixProject do
  defp deps do
    [
      {:jason, "~> 1.4"}
    ]
  end
end
""",
        encoding="utf-8",
    )
    (repo / "lib" / "accounts" / "token.ex").write_text(
        """
defmodule MyApp.Accounts.Token do
  def generate(user_id), do: "tok_#{user_id}"
end
""",
        encoding="utf-8",
    )
    (repo / "lib" / "accounts" / "auth.ex").write_text(
        """
defmodule MyApp.Accounts.Auth do
  alias MyApp.Accounts.{Token}

  def issue_session(user_id) do
    Token.generate(user_id)
  end
end
""",
        encoding="utf-8",
    )

    assert detect_language(repo) == "elixir"
    closure = analyze("issue_session", repo=repo)
    assert closure.modules == {"accounts/auth.ex", "accounts/token.ex"}


# ---------------------------------------------------------------------------
# 16. SECURITY, CONFIG, ZIP EMISSION, GPL POLICY, AND CLI TESTS
# ---------------------------------------------------------------------------
def test_security_git_ref_and_path_traversal_guards(tmp_path: Path):
    with pytest.raises(SafetyError):
        parse_source("https://github.com/owner/repo@--upload-pack=evil")
    with pytest.raises(SafetyError):
        parse_source("--upload-pack=evil")
    with pytest.raises(EmitError):
        ensure_safe_write_path(tmp_path / ".." / "escaped.py", tmp_path)


def test_gpl_license_detection_and_guard(tmp_path: Path):
    repo = tmp_path / "gpl_repo"
    repo.mkdir()
    (repo / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE Version 3", encoding="utf-8")
    (repo / "mod.py").write_text("def run(): return 42\n", encoding="utf-8")

    assert detect_license(repo) == "GPL-3.0"
    with pytest.raises(SafetyError):
        yoink(repo, symbol="run", out=tmp_path / "out_denied", allow_gpl=False)

    manifest, res, _ = yoink(
        repo,
        symbol="run",
        out=tmp_path / "out_allowed",
        allow_gpl=True,
        as_zip=True,
        test="python3 -c 'import mod; assert mod.run() == 42'",
    )
    assert manifest.source.license == "GPL-3.0"
    assert manifest.verified.status == "passed"
    zip_files = [f for f in res.files if f.suffix == ".zip"]
    assert len(zip_files) == 1
    with zipfile.ZipFile(zip_files[0]) as zf:
        assert "mod.py" in zf.namelist()
        assert "LICENSE" in zf.namelist()


def test_config_and_strict_mode_and_ambiguous_symbol(tmp_path: Path):
    repo = tmp_path / "strict_repo"
    repo.mkdir()
    (repo / "yoink.toml").write_text(
        '[extract]\nmax_depth = 5\n[safety]\nexecute = "ask"\n',
        encoding="utf-8",
    )
    cfg = load_config(repo)
    assert cfg.max_depth == 5

    (repo / "a.py").write_text("from .missing_mod import something\ndef target_fn(): pass\ndef dup(): pass\n", encoding="utf-8")
    (repo / "b.py").write_text("def dup(): pass\n", encoding="utf-8")

    with pytest.raises(SymbolNotFoundError) as exc_info:
        analyze("dup", repo=repo)
    assert set(exc_info.value.candidates) == {"a", "b"}

    with pytest.raises(StrictModeError):
        yoink(repo, symbol="target_fn", out=tmp_path / "strict_out", strict=True)


def test_cli_extract_and_analyze_subcommands(tmp_path: Path):
    repo = tmp_path / "cli_repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def double(x: int) -> int:\n    return x * 2\n", encoding="utf-8")
    out_dir = tmp_path / "cli_out"

    proc_an = subprocess.run(
        [sys.executable, "-m", "yoink.cli", "analyze", "double", "--repo", str(repo), "--json"],
        capture_output=True,
        text=True,
        cwd="/working_dir/c_aebafd5fd74db7fc/yoink",
    )
    assert proc_an.returncode == 0
    assert '"target": "calc:double"' in proc_an.stdout

    proc_ex = subprocess.run(
        [sys.executable, "-m", "yoink.cli", "extract", str(repo), "--grab", "double", "--out", str(out_dir), "--force", "--json"],
        capture_output=True,
        text=True,
        cwd="/working_dir/c_aebafd5fd74db7fc/yoink",
    )
    assert proc_ex.returncode == 0
    assert (out_dir / "calc.py").is_file()


class YoinkAllLanguagesTestCase(unittest.TestCase):
    """Unittest wrapper so `python3 -m unittest` runs all test functions."""


def _attach_unittest_methods() -> None:
    g = globals()
    for name in sorted(g):
        fn = g[name]
        if name.startswith("test_") and callable(fn):
            def _make_method(f):
                def _method(self):
                    with tempfile.TemporaryDirectory() as td:
                        sig = inspect.signature(f)
                        if "tmp_path" in sig.parameters:
                            f(Path(td))
                        else:
                            f()
                return _method
            setattr(YoinkAllLanguagesTestCase, name, _make_method(fn))


_attach_unittest_methods()


if __name__ == "__main__":
    unittest.main(verbosity=2)
