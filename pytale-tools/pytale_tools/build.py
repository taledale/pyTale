"""Plugin builder for PyTale.

Produces a Hytale plugin JAR in the GraalPy Virtual Filesystem (VFS) layout under
``GRAALPY-VFS/<group>/<module>``: the plugin's own code goes into ``src/`` (GraalPy's PYTHONPATH)
and its third-party dependencies into ``venv/``. Both are built by pip-installing the plugin
wheel into a venv, then relocating the plugin's packages from site-packages into ``src/``. At
runtime the PyTale framework mounts this through a ``VirtualFileSystem`` so Python imports
resolve directly from the jar (no temp extraction).

The build must run under GraalPy itself (``sys.executable`` is graalpy) so that the venv and its
``site-packages`` are laid out by graalpy's own pip and match the runtime interpreter version.
"""

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# Must match the resource root used by the Java runtime in PythonContext.buildContext().
VFS_GROUP = "TaleDale"

# Top-level site-packages entries that venv/pip seed but are build-time only; never bundled.
_BUILD_ONLY = {
    "pip",
    "setuptools",
    "pkg_resources",
    "_distutils_hack",
    "wheel",
    "distutils-precedence.pth",
}
_BUILD_ONLY_DISTINFO_PREFIXES = ("pip-", "setuptools-", "wheel-")


class PluginBuilder:
    def __init__(
        self,
        wheel_path: Path,
        requirements_path: Path | None = None,
        additional_wheels: list[Path] | None = None,
    ):
        if sys.implementation.name != "graalpy":
            raise RuntimeError(
                "pytale-tools must run under GraalPy so the bundled venv matches the runtime "
                f"interpreter (current interpreter: {sys.implementation.name}). "
                "Run it from a GraalPy environment, e.g. `uv run pytale-tools ...`."
            )

        self.wheel_path = wheel_path.resolve()
        if not self.wheel_path.exists():
            raise FileNotFoundError(f"Wheel not found: {self.wheel_path}")

        self.requirements_path = (
            requirements_path.resolve() if requirements_path else None
        )
        if self.requirements_path and not self.requirements_path.exists():
            raise FileNotFoundError(
                f"Requirements file not found: {self.requirements_path}"
            )

        self.additional_wheels = []
        if additional_wheels:
            for wheel in additional_wheels:
                wheel_resolved = wheel.resolve()
                if not wheel_resolved.exists():
                    raise FileNotFoundError(f"Additional wheel not found: {wheel}")
                self.additional_wheels.append(wheel_resolved)

        self.metadata = self._read_metadata_from_wheel()
        self.module_name = self.metadata["name"].replace("-", "_")

        # Persistent per-plugin venv lives in the project's .pytale directory; reused across
        # builds and only rebuilt when the inputs change.
        self.venv_dir = self._find_project_dir() / ".pytale" / "venv" / self.module_name

    def _find_project_dir(self) -> Path:
        """Walk up from the wheel to the project root (dir with .pytale or pyproject.toml)."""
        for d in [self.wheel_path.parent, *self.wheel_path.parents]:
            if (d / ".pytale").exists() or (d / "pyproject.toml").exists():
                return d
        return Path.cwd()

    def _read_metadata_from_wheel(self) -> dict[str, str]:
        """Extract metadata from wheel's dist-info/METADATA"""
        with zipfile.ZipFile(self.wheel_path, "r") as whl:
            dist_info_dirs = [n for n in whl.namelist() if ".dist-info/" in n]
            if not dist_info_dirs:
                raise ValueError(f"No dist-info found in wheel {self.wheel_path.name}")

            dist_info_dir = dist_info_dirs[0].split("/")[0]
            metadata_file = f"{dist_info_dir}/METADATA"

            try:
                metadata_content = whl.read(metadata_file).decode("utf-8")
            except KeyError:
                raise FileNotFoundError(f"METADATA not found in {self.wheel_path.name}")

            name = None
            version = None
            description = ""

            for line in metadata_content.split("\n"):
                if line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()
                elif line.startswith("Summary:"):
                    description = line.split(":", 1)[1].strip()

            if not name:
                raise ValueError("Package name not found in wheel metadata")

            return {
                "name": name,
                "version": version or "1.0.0",
                "description": description,
            }

    # ------------------------------------------------------------------ venv

    def _venv_python(self) -> Path:
        return self.venv_dir / "bin" / "python"

    def _inputs_hash(self) -> str:
        """Hash the build inputs so the venv is only rebuilt when something actually changes."""
        h = hashlib.sha256()
        h.update(sys.version.encode())
        for wheel in [self.wheel_path, *self.additional_wheels]:
            h.update(wheel.name.encode())
            h.update(wheel.read_bytes())
        if self.requirements_path:
            h.update(self.requirements_path.read_bytes())
        return h.hexdigest()

    def _find_links_args(self) -> list[str]:
        """Auto --find-links for the dirs holding the input wheels / requirements file so that
        local-only dependencies (e.g. the pytale wheel) resolve without extra flags."""
        dirs: list[Path] = [self.wheel_path.parent]
        dirs.extend(w.parent for w in self.additional_wheels)
        if self.requirements_path:
            dirs.append(self.requirements_path.parent)

        args: list[str] = []
        seen = set()
        for d in dirs:
            key = str(d)
            if key not in seen:
                seen.add(key)
                args += ["--find-links", key]
        return args

    def _sync_venv(self) -> None:
        """Create the venv and install the plugin + dependencies, reusing it if inputs match."""
        marker = self.venv_dir / ".pytale-inputs"
        wanted = self._inputs_hash()
        if marker.exists() and marker.read_text() == wanted:
            print(f"✓ Reusing venv: {self.venv_dir}")
            return

        if self.venv_dir.exists():
            shutil.rmtree(self.venv_dir)
        self.venv_dir.parent.mkdir(parents=True, exist_ok=True)

        print(f"Creating venv: {self.venv_dir}")
        subprocess.run(
            [sys.executable, "-m", "venv", str(self.venv_dir)],
            check=True,
            capture_output=True,
        )

        cmd = [
            str(self._venv_python()),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            *self._find_links_args(),
            str(self.wheel_path),
        ]
        if self.requirements_path:
            cmd += ["-r", str(self.requirements_path)]
        cmd += [str(w) for w in self.additional_wheels]

        print("Installing plugin + dependencies into venv...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"pip install failed:\n{result.stdout}\n{result.stderr}")

        marker.write_text(wanted)

    # ------------------------------------------------------------------ VFS layout

    def _venv_site_packages(self) -> Path:
        matches = sorted(self.venv_dir.glob("lib/python*/site-packages"))
        if not matches:
            raise RuntimeError(f"No site-packages found in venv {self.venv_dir}")
        return matches[0]

    @staticmethod
    def _is_build_only(name: str) -> bool:
        if name in _BUILD_ONLY:
            return True
        if name.endswith(".dist-info") and name.startswith(
            _BUILD_ONLY_DISTINFO_PREFIXES
        ):
            return True
        return False

    def _vfs_root_rel(self) -> str:
        """Resource path of the VFS root inside the jar. Must match the Java runtime."""
        return f"GRAALPY-VFS/{VFS_GROUP}/{self.module_name}"

    def _plugin_wheel_layout(self) -> tuple[set[str], str | None]:
        """Top-level importable names and the dist-info dir name of the plugin wheel."""
        top_level: set[str] = set()
        dist_info: str | None = None
        with zipfile.ZipFile(self.wheel_path) as whl:
            for name in whl.namelist():
                first = name.split("/")[0]
                if first.endswith(".dist-info"):
                    dist_info = first
                elif not first.endswith(".data"):
                    top_level.add(first)
        return top_level, dist_info

    @staticmethod
    def _ignore_pycache(src: str, names: list[str]) -> set[str]:
        return {n for n in names if n == "__pycache__"}

    def _copy_vfs(self, temp_dir: Path) -> str:
        """Lay out the GraalPy VFS under the jar resource root: the plugin's own code goes into
        ``src/`` (on PYTHONPATH) and third-party dependencies stay in ``venv/``. Returns the VFS
        root rel path."""
        vfs_root_rel = self._vfs_root_rel()
        vfs_root = temp_dir / vfs_root_rel
        dest_venv = vfs_root / "venv"
        dest_venv.mkdir(parents=True, exist_ok=True)

        # pyvenv.cfg marks the directory as a venv so GraalPy discovers site-packages from it.
        shutil.copy2(self.venv_dir / "pyvenv.cfg", dest_venv / "pyvenv.cfg")

        # GraalPyResources sets python.Executable to <venv>/bin/python; provide a placeholder so
        # that virtual path resolves inside the read-only VFS.
        bin_dir = dest_venv / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / "python").write_bytes(b"")

        plugin_top_level, plugin_dist_info = self._plugin_wheel_layout()
        site_packages = self._venv_site_packages()
        dest_sp = dest_venv / "lib" / site_packages.parent.name / "site-packages"

        def ignore(src: str, names: list[str]) -> set[str]:
            skip = {n for n in names if n == "__pycache__" or self._is_build_only(n)}
            # The plugin's own package(s) live in src/, not the venv; drop them at the
            # site-packages root only (not from same-named subdirs of dependencies).
            if Path(src) == site_packages:
                skip |= {
                    n for n in names if n in plugin_top_level or n == plugin_dist_info
                }
            return skip

        shutil.copytree(site_packages, dest_sp, ignore=ignore)
        print(f"✓ Bundled dependencies -> {vfs_root_rel}/venv")

        # The plugin's own source goes into src/ (PYTHONPATH), taken from the installed venv copy.
        dest_src = vfs_root / "src"
        dest_src.mkdir(parents=True, exist_ok=True)
        for name in sorted(plugin_top_level):
            installed = site_packages / name
            if installed.is_dir():
                shutil.copytree(installed, dest_src / name, ignore=self._ignore_pycache)
            elif installed.exists():  # single-module plugin, e.g. foo.py
                shutil.copy2(installed, dest_src / name)
            else:
                raise RuntimeError(
                    f"Plugin top-level '{name}' not found in installed venv {site_packages}"
                )
        print(f"✓ Bundled plugin source -> {vfs_root_rel}/src")
        return vfs_root_rel

    def _write_fileslist(self, temp_dir: Path, vfs_root_rel: str) -> None:
        """Write GraalPy's VFS index. Each line is an absolute resource path; directories end
        with '/'. The VirtualFileSystem reads this to enumerate files embedded in the jar.
        """
        vfs_root = temp_dir / vfs_root_rel
        lines = []
        for path in sorted(vfs_root.rglob("*")):
            rel = path.relative_to(temp_dir).as_posix()
            lines.append("/" + rel + ("/" if path.is_dir() else ""))

        (vfs_root / "fileslist.txt").write_text("\n".join(lines) + "\n")
        print(f"✓ Wrote {vfs_root_rel}/fileslist.txt ({len(lines)} entries)")

    # ------------------------------------------------------------------ loader + manifest + jar

    def _copy_loader_class(self, temp_dir: Path) -> str:
        """Copy pre-compiled PythonPlugin.class from resources"""
        class_file = self._find_python_plugin_class()
        if not class_file.exists():
            raise FileNotFoundError(
                f"PythonPlugin.class not found at {class_file}. "
                f"Build PyTale first with: ./gradlew jar"
            )

        pkg_dir = temp_dir / "dev" / "taledale" / "pytale"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(class_file, pkg_dir / "PythonPlugin.class")
        return "dev.taledale.pytale.PythonPlugin"

    def _find_python_plugin_class(self) -> Path:
        """Find pre-extracted PythonPlugin.class in pytale-tools resources"""
        return Path(__file__).parent / "resources" / "PythonPlugin.class"

    def _create_manifest_json(self, temp_dir: Path) -> Path:
        """Create manifest.json for Hytale"""
        manifest_path = temp_dir / "manifest.json"
        manifest = {
            "Group": VFS_GROUP,
            "Name": self.metadata["name"],
            "Version": self.metadata["version"],
            "Authors": [],
            "DisabledByDefault": False,
            "IncludesAssetPack": False,
            "Dependencies": {"TaleDale:PyTale": ">=0.0.1"},
            "OptionalDependencies": {},
            "ServerVersion": "=0.5.6",
            "Main": "dev.taledale.pytale.PythonPlugin",
        }
        manifest_path.write_text(json.dumps(manifest, indent=4))
        return manifest_path

    def _create_jar(self, temp_dir: Path, output_path: Path) -> Path:
        """Create JAR from temp directory"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as jar:
            for item in temp_dir.rglob("*"):
                if item.is_file():
                    jar.write(item, arcname=str(item.relative_to(temp_dir)))
        return output_path

    def build(self, output_path: Path) -> Path:
        """Build plugin JAR"""
        output_path = output_path.resolve()

        self._sync_venv()

        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)

            self._copy_loader_class(temp_dir)
            self._create_manifest_json(temp_dir)
            vfs_root_rel = self._copy_vfs(temp_dir)
            self._write_fileslist(temp_dir, vfs_root_rel)
            self._create_jar(temp_dir, output_path)

            print(f"✓ Plugin JAR created: {output_path}")
            return output_path
