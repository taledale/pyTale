"""Plugin builder for PyTale.

Produces a Hytale plugin JAR in the GraalPy Virtual Filesystem (VFS) layout under
``GRAALPY-VFS/<group>/<module>``: the plugin's own code goes into ``src/`` (GraalPy's PYTHONPATH)
and its third-party dependencies into ``venv/``. Dependencies are downloaded as wheels from PyPI
(or provided locally) and unpacked directly into the VFS layout — no venv creation or pip subprocess
is involved. At runtime the PyTale framework mounts this through a ``VirtualFileSystem`` so Python
imports resolve directly from the jar (no temp extraction).
"""

import json
import zipfile
from pathlib import Path

from pytale_tools.builder.classgen import generate_plugin_class, module_to_class_name
from pytale_tools.builder.pypi import download_wheels_sync
from pytale_tools.builder.req_parser import parse_requirements

VFS_GROUP = "TaleDale"
PYTHON_VERSION = "3.12"


class PluginBuilder:
    def __init__(
        self,
        wheel_path: Path,
        requirements_path: Path | None = None,
        max_workers: int = 10,
    ):
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

        self.max_workers = max_workers
        self.metadata = self._read_metadata_from_wheel()
        self.module_name = self.metadata["name"].replace("-", "_")
        self.cache_dir = self._find_project_dir() / ".pytale" / "wheels"

    def _find_project_dir(self) -> Path:
        for d in [self.wheel_path.parent, *self.wheel_path.parents]:
            if (d / ".pytale").exists() or (d / "pyproject.toml").exists():
                return d
        return Path.cwd()

    def _read_metadata_from_wheel(self) -> dict[str, str]:
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

    # ------------------------------------------------------------------ dependencies

    def _resolve_dependency_wheels(self) -> list[Path]:
        wheels: list[Path] = []

        if self.requirements_path:
            all_reqs = parse_requirements(self.requirements_path)
            local = [r for r in all_reqs if r.path is not None]
            remote = [r for r in all_reqs if r.path is None]

            for r in local:
                assert r.path is not None
                print(f"  Local: {r.path.name}")
                wheels.append(r.path)

            if remote:
                print(f"Downloading {len(remote)} PyPI dependencies...")
                wheels.extend(
                    download_wheels_sync(
                        remote, self.cache_dir, max_workers=self.max_workers
                    )
                )

        return wheels

    # ------------------------------------------------------------------ wheel unpacking

    @staticmethod
    def _unpack_wheel(
        wheel_path: Path,
        jar: zipfile.ZipFile,
        dest_prefix: str,
        *,
        include_dist_info: bool = True,
    ) -> set[str]:
        top_level: set[str] = set()
        with zipfile.ZipFile(wheel_path, "r") as whl:
            for info in whl.infolist():
                if info.is_dir():
                    continue

                first = info.filename.split("/")[0]

                if not include_dist_info and (
                    first.endswith(".dist-info") or first.endswith(".data")
                ):
                    continue

                if "__pycache__" in info.filename:
                    continue

                top_level.add(first)
                jar.writestr(f"{dest_prefix}{info.filename}", whl.read(info))

        return top_level

    # ------------------------------------------------------------------ VFS layout

    def _vfs_root_rel(self) -> str:
        return f"GRAALPY-VFS/{VFS_GROUP}/{self.module_name}"

    @staticmethod
    def _write_pyvenv_cfg(jar: zipfile.ZipFile, venv_prefix: str) -> None:
        cfg = (
            "home = .\n"
            "include-system-site-packages = false\n"
            f"version = {PYTHON_VERSION}\n"
        )
        jar.writestr(f"{venv_prefix}pyvenv.cfg", cfg)

    def _write_vfs(self, jar: zipfile.ZipFile, dependency_wheels: list[Path]) -> str:
        vfs_root_rel = self._vfs_root_rel()
        venv_prefix = f"{vfs_root_rel}/venv/"

        self._write_pyvenv_cfg(jar, venv_prefix)
        jar.writestr(f"{venv_prefix}bin/python", b"")

        site_packages = f"{venv_prefix}lib/python{PYTHON_VERSION}/site-packages/"
        for wheel_path in dependency_wheels:
            self._unpack_wheel(wheel_path, jar, site_packages, include_dist_info=True)
        if dependency_wheels:
            print(
                f"✓ Bundled {len(dependency_wheels)} dependencies -> {vfs_root_rel}/venv"
            )

        src_prefix = f"{vfs_root_rel}/src/"
        plugin_top_level = self._unpack_wheel(
            self.wheel_path, jar, src_prefix, include_dist_info=False
        )
        if not plugin_top_level:
            raise RuntimeError(
                f"No importable code found in plugin wheel {self.wheel_path.name}"
            )
        print(f"✓ Bundled plugin source -> {vfs_root_rel}/src")
        return vfs_root_rel

    def _write_fileslist(self, jar: zipfile.ZipFile, vfs_root_rel: str) -> None:
        vfs_prefix = f"{vfs_root_rel}/"
        entries: set[str] = set()

        for name in jar.namelist():
            if not name.startswith(vfs_prefix):
                continue
            entries.add(f"/{name}")
            parts = name[len(vfs_prefix) :].split("/")
            for i in range(1, len(parts)):
                dir_path = "/".join(parts[:i])
                entries.add(f"/{vfs_prefix}{dir_path}/")

        lines = sorted(entries)
        jar.writestr(f"{vfs_prefix}fileslist.txt", f"{'\n'.join(lines)}\n")
        print(f"✓ Wrote {vfs_root_rel}/fileslist.txt ({len(lines)} entries)")

    # ------------------------------------------------------------------ loader + manifest + jar

    def _plugin_class_internal_name(self) -> str:
        class_name = module_to_class_name(self.module_name)
        return f"{VFS_GROUP.lower()}/{self.module_name}/{class_name}"

    def _write_loader_class(self, jar: zipfile.ZipFile) -> str:
        internal_name = self._plugin_class_internal_name()
        jar.writestr(f"{internal_name}.class", generate_plugin_class(internal_name))
        return internal_name.replace("/", ".")

    def _write_manifest_json(self, jar: zipfile.ZipFile, main_class: str) -> None:
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
            "Main": main_class,
        }
        jar.writestr("manifest.json", json.dumps(manifest, indent=4))

    def build(self, output_path: Path) -> Path:
        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        dependency_wheels = self._resolve_dependency_wheels()

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as jar:
            main_class = self._write_loader_class(jar)
            self._write_manifest_json(jar, main_class)
            vfs_root_rel = self._write_vfs(jar, dependency_wheels)
            self._write_fileslist(jar, vfs_root_rel)

        print(f"✓ Plugin JAR created: {output_path}")
        return output_path
