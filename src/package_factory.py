from typing import Final
from pathlib import Path

import os
import subprocess

from src.version import get_package_version, get_compatibility_level
from src.module import get_module_name
from src.package import PackageMetadata, Package

DEPENDS_ATTR: Final = "Depends"
HTTP_ARCHIVE_PREFIX: Final = "_main~_repo_rules~"


def _is_acceptable_error(err: str):
    for e in [
        "not an ELF executable",
        "missing ELF header",
        "Permission denied",
        ]:
        if e in err:
            return True
    return False


def _is_patchable_elf_file(file: Path) -> bool:
    "Tries to print rpath in order to tell if file is ELF or not"
    try:
        old_rpath = subprocess.run(
            ["patchelf", "--print-rpath", file.resolve()],
            check=True,
            capture_output=True,
            encoding="utf-8",
        ).stdout
        old_rpath = old_rpath.strip("\n")
        if not old_rpath:
            old_rpath = "$ORIGIN"

        _ = subprocess.run(
            ["patchelf", "--remove-rpath", file.resolve()],
            check=True,
            capture_output=True,
            encoding="utf-8",
        ).stdout
        _ = subprocess.run(
            ["patchelf", "--force-rpath", "--set-rpath", old_rpath, file.resolve()],
            check=True,
            capture_output=True,
            encoding="utf-8",
        ).stdout
        return True
    except subprocess.CalledProcessError as error:
        if _is_acceptable_error(error.stderr):
            # Non-patchable file
            return False
        raise error


def _get_deb_pinned_name(name: str, arch: str = "", version: str = ""):
    package = name
    if arch:
        package += f":{arch}"
    if version:
        package += f"={version}"

    return package


def _download_package_dot_debian(
    name: str, arch: str, version: str, pinned_name: str
) -> Path:
    subprocess.check_call(
        ["apt-get", "download", pinned_name], stdout=subprocess.DEVNULL
    )

    files = [file for file in os.listdir() if os.path.isfile(file)]
    for file in files:
        modified_file = file.replace("%3a", ":")
        if (
            modified_file == f"{name}_{version}_{arch}.deb"
            or modified_file == f"{name}_{version}_all.deb"
        ):
            return Path(file).resolve()

    current_dir = str(Path.cwd())
    raise ValueError(
        f"could not find the downloaded debian package for {pinned_name} in dir: {current_dir}"
    )


def _extract_attribute(
    package_info: str, attribute: str, must_exist: bool = True
) -> str:
    "Extracts a specific attribute from the info listed using 'apt-cache' or 'dpkg-deb'."
    prefix = attribute + ": "
    lines = package_info.splitlines()

    for line in lines:
        line = line.lstrip()
        if line.startswith(attribute):
            return line[len(prefix) :]

    if not must_exist:
        return ""

    raise ValueError(
        f"{attribute} could not be extracted from package_info: {package_info}"
    )


def _get_package_deps(archive_path: Path, arch: str):
    deps_str = _extract_attribute(
        subprocess.check_output(["dpkg-deb", "-I", archive_path], encoding="utf-8"),
        DEPENDS_ATTR,
        False,
    )

    deps = set()
    if not deps_str:
        return deps

    # TODO: use a lib that does the parsing for you. I was too lazy to leave the code and search =D
    polluted_deps = deps_str.split(", ")
    for dep_name in polluted_deps:
        # imagine a case where the following is returned: debconf (>= 0.5) | debconf-2.0,
        # we want the left hand side, since it is not a virtual dep. The way to do that, is to search for brackets
        # not too smart but works for now :)
        alternative_deps = dep_name.split(" | ")
        dep_name = alternative_deps[0]
        for alternative_dep in alternative_deps:
            if "(" in alternative_deps and ")" in alternative_deps:
                dep_name = alternative_dep
                break

        # with the not-so-clever check above, we may still end up with something like: dep-1.0
        # for now we ignore deps without version spec.
        if "(" not in dep_name:
            continue

        # now it is of the pattern dep (>= 0.1)
        dep_name, version_spec = dep_name.split(maxsplit=1)
        dep_name = dep_name.split(":")[0]
        is_strict_version = "=" in version_spec and ">=" not in version_spec and "<=" not in version_spec and "~= " not in version_spec

        # Another workaround: tzdata accesses files from system, it needs more investigation to handle it properly.
        # TODO: find a general way to handle deps accessing files from system.
        if dep_name == "tzdata":
            continue

        dep_version = get_package_version(
            name=dep_name,
            arch=arch,
        ) if not is_strict_version else version_spec.split()[1][:-1]

        deps.add(PackageMetadata(name=dep_name, arch=arch, version=dep_version))

    return deps


def create_deb_package(metadata: PackageMetadata, delimiter: str = "~") -> Package:
    """Factory function to create deb packages."""
    if not metadata.name or not metadata.arch or not metadata.version:
        raise ValueError(
            f"name, arch and version must all be provided and not empty, in order to create a debian package. Provided values are: name={metadata.name}, version={metadata.version}, arch={metadata.arch}"
        )

    package = Package()
    package.name = metadata.name
    package.arch = metadata.arch
    package.version = metadata.version
    package.module_name = get_module_name(name=package.name, arch=package.arch)
    package.pinned_name = _get_deb_pinned_name(
        name=metadata.name, arch=metadata.arch, version=metadata.version
    )
    package.prefix = f"{HTTP_ARCHIVE_PREFIX}{get_module_name(name=metadata.name, arch=metadata.arch)}"
    package.prefix_version = f"{get_module_name(name=metadata.name, arch=metadata.arch)}{delimiter}{metadata.version}"
    package.compatibility_level = get_compatibility_level(metadata.version)
    # path to package.deb
    archive_path = _download_package_dot_debian(
        name=metadata.name,
        arch=metadata.arch,
        version=metadata.version,
        pinned_name=package.pinned_name,
    )
    package_dir = archive_path.parent / Path(package.prefix)
    package_dir.mkdir(exist_ok=True)
    package.package_dir = package_dir.resolve()
    # the following fills the files-related attributes of the deb package
    files_str = subprocess.check_output(
        ["dpkg", "-X", archive_path, package.package_dir],
        encoding="utf-8",
        stderr=subprocess.STDOUT,
    )

    for file in files_str.split("\n"):
        # the ":" part is a workaround some files having unacceptable names for bazel targets
        if ":" in file:
            continue

        file_path = Path(file)
        if not Path(package.package_dir / file_path).is_file():
            continue

        if not _is_patchable_elf_file(Path(package.package_dir / file_path)):
            package.nonelf_files.add(file_path)
            continue

        package.elf_files.add(file_path)
        # register the parent of the ELF file as an rpath
        package.rpaths[file_path.name] = os.fspath(package.prefix / file_path.parent)

    # The next check is needed since libc6 is cyclic with libcrypt1.
    # I assume libc6 does not have deps in this case :D
    if package.name == "libc6":
        archive_path.unlink()
        return package

    # now fillup the transitive deps
    package.deps = _get_package_deps(archive_path=archive_path, arch=package.arch)
    archive_path.unlink()

    return package
