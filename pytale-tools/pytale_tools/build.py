"""Plugin builder for PyTale"""

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict


class PluginBuilder:
    def __init__(self, wheel_path: Path):
        self.wheel_path = wheel_path.resolve()
        if not self.wheel_path.exists():
            raise FileNotFoundError(f"Wheel not found: {self.wheel_path}")
        self.metadata = self._read_metadata_from_wheel()

    def _read_metadata_from_wheel(self) -> Dict:
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
        import shutil
        shutil.copy2(class_file, pkg_dir / "PythonPlugin.class")

        return "dev.taledale.pytale.PythonPlugin"

    def _find_python_plugin_class(self) -> Path:
        """Find pre-extracted PythonPlugin.class in pytale-tools resources"""
        pytale_tools_dir = Path(__file__).parent
        return pytale_tools_dir / "resources" / "PythonPlugin.class"

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

    def _copy_wheel_file(self, temp_dir: Path):
        """Copy wheel file to JAR root"""
        wheel_name = self.wheel_path.name
        dest_wheel = temp_dir / wheel_name
        shutil.copy2(self.wheel_path, dest_wheel)
        print(f"✓ Copied wheel: {wheel_name}")

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

            # Copy wheel file
            self._copy_wheel_file(temp_dir)

            # Create JAR
            self._create_jar(temp_dir, output_path)

            print(f"✓ Plugin JAR created: {output_path}")
            return output_path
