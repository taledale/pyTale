"""Plugin builder for PyTale"""

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


class PluginBuilder:
    def __init__(
        self,
        wheel_path: Path,
        requirements_path: Path | None = None,
        cache_dir: Path | None = None,
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

        # Set cache directory: explicit > project .pytale > user home
        if cache_dir:
            self.cache_dir = cache_dir.resolve()
        elif (self.wheel_path.parent / ".pytale" / "wheels").exists() or (
            self.wheel_path.parent.parent / ".pytale" / "wheels"
        ).exists():
            # Look for .pytale in wheel's parent or grandparent (project root)
            project_cache = self.wheel_path.parent / ".pytale" / "wheels"
            if not project_cache.exists():
                project_cache = self.wheel_path.parent.parent / ".pytale" / "wheels"
            self.cache_dir = project_cache
        else:
            # Default to user home cache
            self.cache_dir = Path.home() / ".cache" / "pytale" / "wheels"

        self.metadata = self._read_metadata_from_wheel()

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
                raise ValueError(f"Package name not found in wheel metadata")

            return {
                "name": name,
                "version": version or "1.0.0",
                "description": description,
            }

    def _copy_loader_class(self, temp_dir: Path) -> str:
        """Copy pre-compiled PythonPlugin.class from resources"""
        class_file = self._find_python_plugin_class()
        if not class_file.exists():
            raise FileNotFoundError(
                f"PythonPlugin.class not found at {class_file}. "
                f"Build PyTale first with: ./gradlew jar"
            )

        # Create package directory structure
        pkg_dir = temp_dir / "dev" / "taledale" / "pytale"
        pkg_dir.mkdir(parents=True, exist_ok=True)

        # Copy class file to temp directory
        shutil.copy2(class_file, pkg_dir / "PythonPlugin.class")

        return "dev.taledale.pytale.PythonPlugin"

    def _find_python_plugin_class(self) -> Path:
        """Find pre-extracted PythonPlugin.class in pytale-tools resources"""
        pytale_tools_dir = Path(__file__).parent
        return pytale_tools_dir / "resources" / "PythonPlugin.class"

    def _ensure_cache_dir(self) -> None:
        """Ensure cache directory exists"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _parse_requirements(self) -> list[str]:
        """Parse requirements.txt and return list of package specs"""
        if not self.requirements_path:
            return []

        requirements = []
        with open(self.requirements_path, "r") as f:
            content = f.read()

        # Handle line continuations (backslash at end of line)
        lines: list[str] = []
        current_line = ""
        for line in content.split("\n"):
            # Remove inline comments
            if "#" in line and not line.strip().startswith("#"):
                line = line.split("#")[0]

            line = line.rstrip()
            if line.endswith("\\"):
                current_line += line[:-1].strip() + " "
            else:
                current_line += line
                if current_line.strip() and not current_line.strip().startswith("#"):
                    requirements.append(current_line.strip())
                current_line = ""

        return requirements

    def _get_cached_wheel(self, package_spec: str) -> Path | None:
        """Check if wheel for package spec exists in cache"""
        self._ensure_cache_dir()

        # Extract package name from spec (e.g., "tomli==2.0.1" -> "tomli")
        package_name = (
            package_spec.split("==")[0]
            .split(">")[0]
            .split("<")[0]
            .split("!")[0]
            .split("~")[0]
            .strip()
        )

        # Look for any wheel matching this package name
        for wheel_file in self.cache_dir.glob("*.whl"):
            if wheel_file.name.startswith(package_name.replace("-", "_")):
                print(f"✓ Using cached wheel: {wheel_file.name}")
                return wheel_file
        return None

    def _cache_wheel(self, wheel_path: Path) -> None:
        """Copy wheel to cache directory"""
        self._ensure_cache_dir()
        dest = self.cache_dir / wheel_path.name
        shutil.copy2(wheel_path, dest)

    def _download_dependencies(self) -> list[Path]:
        """Download wheels for all dependencies from requirements.txt"""
        if not self.requirements_path:
            return []

        self._ensure_cache_dir()
        print(f"Downloading dependencies from {self.requirements_path.name}...")

        try:
            import sys

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "download",
                    "-r",
                    str(self.requirements_path),
                    "--only-binary=:all:",
                    "--no-deps",
                    "-d",
                    str(self.cache_dir),
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to download dependencies: {e.stderr.decode() if e.stderr else str(e)}"
            )

        # Collect all downloaded wheels
        wheel_paths = list(self.cache_dir.glob("*.whl"))
        if not wheel_paths:
            raise FileNotFoundError(
                f"No wheels downloaded from {self.requirements_path.name}"
            )

        for wheel_path in wheel_paths:
            print(f"✓ Downloaded: {wheel_path.name}")

        return wheel_paths

    def _copy_all_wheels(
        self, additional_wheel_paths: list[Path], temp_dir: Path
    ) -> None:
        """Copy main wheel and all dependency wheels to JAR root"""
        # Copy main wheel
        wheel_name = self.wheel_path.name
        dest_wheel = temp_dir / wheel_name
        shutil.copy2(self.wheel_path, dest_wheel)
        print(f"✓ Copied wheel: {wheel_name}")

        # Copy dependency wheels
        for wheel_path in additional_wheel_paths:
            dest = temp_dir / wheel_path.name
            shutil.copy2(wheel_path, dest)
            print(f"✓ Copied wheel: {wheel_path.name}")

    def _create_manifest_json(self, temp_dir: Path) -> Path:
        """Create manifest.json for Hytale"""
        import json

        manifest_path = temp_dir / "manifest.json"
        manifest = {
            "Group": "TaleDale",
            "Name": self.metadata["name"],
            "Version": self.metadata["version"],
            "Authors": [],
            "DisabledByDefault": False,
            "IncludesAssetPack": False,
            "Dependencies": {"TaleDale:PyTale": ">=0.0.1"},
            "OptionalDependencies": {},
            "ServerVersion": "=0.5.3",
            "Main": "dev.taledale.pytale.PythonPlugin",
        }
        manifest_path.write_text(json.dumps(manifest, indent=4))
        return manifest_path

    def _create_jar(self, temp_dir: Path, output_path: Path) -> Path:
        """Create JAR from temp directory, excluding build artifacts"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Directories to exclude from JAR
        exclude_dirs = {"src", "classes"}

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as jar:
            for item in temp_dir.rglob("*"):
                if item.is_file():
                    # Skip files in excluded directories
                    parts = item.relative_to(temp_dir).parts
                    if parts and parts[0] in exclude_dirs:
                        continue
                    arcname = str(item.relative_to(temp_dir))
                    jar.write(item, arcname=arcname)

        return output_path

    def build(self, output_path: Path) -> Path:
        """Build plugin JAR"""
        output_path = output_path.resolve()

        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)

            # Copy universal PythonPlugin loader class
            self._copy_loader_class(temp_dir)

            # Create manifest.json
            self._create_manifest_json(temp_dir)

            # Download and copy wheels
            dependency_wheels = (
                self._download_dependencies() if self.requirements_path else []
            )
            self._copy_all_wheels(dependency_wheels, temp_dir)

            # Create JAR
            self._create_jar(temp_dir, output_path)

            print(f"✓ Plugin JAR created: {output_path}")
            return output_path
