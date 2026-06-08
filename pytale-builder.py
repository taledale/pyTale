#!/usr/bin/env python3
"""
pytale-builder: Generate Hytale Python plugin JARs from pyproject.toml
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Dict

JAVA_LOADER_TEMPLATE = """package {package_name};

import dev.taledale.pytale.AbstractPythonPlugin;
import com.hypixel.hytale.server.core.plugin.JavaPluginInit;
import javax.annotation.Nonnull;

public class {class_name} extends AbstractPythonPlugin {{
    public {class_name}(@Nonnull JavaPluginInit init) {{
        super(init);
    }}
}}
"""


class PluginBuilder:
    def __init__(self, plugin_dir: Path):
        self.plugin_dir = plugin_dir.resolve()
        self.pyproject_path = self.plugin_dir / "pyproject.toml"
        self.metadata = self._read_metadata()

    def _read_metadata(self) -> Dict:
        if not self.pyproject_path.exists():
            raise FileNotFoundError(f"pyproject.toml not found in {self.plugin_dir}")

        with open(self.pyproject_path, "rb") as f:
            data = tomllib.load(f)

        project = data.get("project", {})
        return {
            "name": project.get("name", self.plugin_dir.name),
            "version": project.get("version", "1.0.0"),
            "description": project.get("description", ""),
        }

    def _normalize_class_name(self, name: str) -> str:
        """Convert plugin name to valid Java class name"""
        parts = name.replace("-", " ").replace("_", " ").split()
        return "".join(part.capitalize() for part in parts if part) + "Loader"

    def _get_package_name(self, name: str) -> str:
        """Convert plugin name to package name (e.g., test-hello -> test_hello)"""
        return name.replace("-", "_").lower()

    def _get_full_class_name(self, name: str) -> tuple[str, str]:
        """Get (package_name, class_name) for plugin"""
        pkg_name = self._get_package_name(name)
        cls_name = self._normalize_class_name(name)
        return pkg_name, cls_name

    def _get_classpath_from_jar(self, pytale_jar: Path) -> str:
        """Extract classpath from pytale.jar and add pytale.jar itself"""
        try:
            with zipfile.ZipFile(pytale_jar, "r") as jar:
                classpath_content = jar.read("META-INF/javac-classpath.txt").decode("utf-8")
                # Add pytale.jar itself to classpath so AbstractPythonPlugin can be found
                classpath = f"{pytale_jar}:{classpath_content.strip()}"
                return classpath
        except KeyError:
            raise RuntimeError(
                f"Classpath file not found in {pytale_jar}. "
                f"Make sure you built PyTale with: ./gradlew clean jar"
            )

    def _generate_loader_class(self, temp_dir: Path) -> str:
        """Generate and compile Java loader class using javac"""
        pkg_name, cls_name = self._get_full_class_name(self.metadata["name"])

        # Create source directory
        src_dir = temp_dir / "src"
        src_dir.mkdir(exist_ok=True)

        # Generate Java source code from template
        java_source = JAVA_LOADER_TEMPLATE.format(package_name=pkg_name, class_name=cls_name)

        # Create package directories in src
        pkg_dir = src_dir / pkg_name
        pkg_dir.mkdir(parents=True, exist_ok=True)

        source_file = pkg_dir / f"{cls_name}.java"
        source_file.write_text(java_source)

        # Find pytale.jar and get classpath
        pytale_root = Path(__file__).parent
        pytale_jar = pytale_root / "build" / "libs" / "pytale.jar"

        if not pytale_jar.exists():
            raise RuntimeError(
                f"pytale.jar not found. Build pyTale first with: ./gradlew jar\n"
                f"Expected at: {pytale_jar}"
            )

        # Extract classpath from jar
        classpath = self._get_classpath_from_jar(pytale_jar)

        # Compile with javac
        output_dir = temp_dir / "classes"
        output_dir.mkdir(exist_ok=True)

        try:
            subprocess.run(
                ["javac", "-d", str(output_dir), "-cp", classpath, str(source_file)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"javac compilation failed: {e.stderr}")
        except FileNotFoundError:
            raise RuntimeError(
                "javac not found. Make sure JDK is installed and javac is in PATH"
            )

        # Copy compiled class to plugin JAR structure
        class_file = output_dir / pkg_name / f"{cls_name}.class"
        if not class_file.exists():
            raise RuntimeError(f"Compiled class file not found: {class_file}")

        jar_pkg_dir = temp_dir / pkg_name
        jar_pkg_dir.mkdir(parents=True, exist_ok=True)

        jar_class_file = jar_pkg_dir / f"{cls_name}.class"
        shutil.copy2(class_file, jar_class_file)

        # Return fully qualified class name for plugin.yml
        return f"{pkg_name}.{cls_name}"

    def _create_plugin_yml(self, temp_dir: Path, class_name: str) -> Path:
        """Create plugin.yml"""
        plugin_yml = temp_dir / "plugin.yml"
        yaml_content = f"""main: {class_name}
name: {self.metadata['name']}
version: {self.metadata['version']}
description: {self.metadata['description']}
dependencies:
  TaleDale.PyTale: ">=0.0.0"
"""
        plugin_yml.write_text(yaml_content)
        return plugin_yml

    def _copy_python_code(self, temp_dir: Path):
        """Copy Python code to python/ directory"""
        python_dir = temp_dir / "python"
        python_dir.mkdir(parents=True, exist_ok=True)

        plugin_name = self.metadata["name"].replace("-", "_")
        plugin_pkg = self.plugin_dir / plugin_name

        if plugin_pkg.exists() and (plugin_pkg / "__init__.py").exists():
            for item in plugin_pkg.rglob("*"):
                relative = item.relative_to(plugin_pkg)
                dest = python_dir / relative
                if item.is_file():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest)
        else:
            raise FileNotFoundError(
                f"Python package not found. Expected: {plugin_pkg} with __init__.py"
            )

        if not list(python_dir.rglob("*.py")):
            raise FileNotFoundError(f"No .py files found in {plugin_pkg}")

    def _copy_venv(self, temp_dir: Path):
        """Copy .venv if it exists"""
        venv_src = self.plugin_dir / ".venv"
        if venv_src.exists():
            venv_dst = temp_dir / ".venv"
            shutil.copytree(venv_src, venv_dst)

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

            # Generate and compile Java loader class
            class_name = self._generate_loader_class(temp_dir)

            # Create plugin.yml
            self._create_plugin_yml(temp_dir, class_name)

            # Copy Python code
            self._copy_python_code(temp_dir)

            # Copy .venv if exists
            self._copy_venv(temp_dir)

            # Create JAR
            self._create_jar(temp_dir, output_path)

            print(f"✓ Plugin JAR created: {output_path}")
            return output_path


def main():
    parser = argparse.ArgumentParser(description="Build Hytale Python plugin JARs")
    parser.add_argument("command", choices=["build"], help="Command to run")
    parser.add_argument("plugin_dir", type=Path, help="Plugin directory path")
    parser.add_argument(
        "-o", "--output", type=Path, help="Output JAR path (default: plugin-name.jar)"
    )

    args = parser.parse_args()

    try:
        builder = PluginBuilder(args.plugin_dir)
        output = args.output or Path(f"{builder.metadata['name']}.jar")
        builder.build(output)
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
