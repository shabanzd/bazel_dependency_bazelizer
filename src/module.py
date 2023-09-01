from typing import Set
from pathlib import Path
import dataclasses


def get_module_name(name: str, arch: str):
    """Architecture is appended to the module name to accommodate for the case of debian packages
    having the same name and different achitectures since there is no arch attribute in module().
    It also makes sure module name is compliant with bazel module naming rules.
    """

    module_name = f"{name}_{arch}"
    # module name rules:
    # 1) valid names must only contain lowercase letters (a-z), digits (0-9), dots (.), hyphens (-)
    # and underscores (_); 2) begin with a lowercase letter; 3) end with a lowercase letter or digit

    # Deb package names must consist of lower case letters, digits (0-9), (+), (-) and (.)
    # https://www.debian.org/doc/debian-policy/ch-controlfields.html#s-f-source

    # difference is the '+' symbol and that deb package names can start with a digit
    module_name = module_name.replace("+", "plus")
    if module_name[0].isdigit():
        module_name = f"package_{module_name}"

    return module_name


def get_module_version(version: str):
    """Debian versions have all sort of characters.
    This gets rid of the bazel unallowed version characters."""
    filtered_version = version
    filtered_version = filtered_version.split(":")[-1]
    filtered_version = filtered_version.split("+")[0]
    filtered_version = filtered_version.split("~")[0]

    return filtered_version


@dataclasses.dataclass()
class Module:
    """Debian package object."""

    name: str
    arch: str
    version: str
    rpaths: Set[str] = dataclasses.field(default_factory=set)

    def module_name(self):
        """Architecture is appended to the module name to accommodate for the case of debian
        packages having the same name and different achitectures, since there is no arch
        attribute in module(). It also makes sure module name is compliant with bazel module
        naming rules.
        """
        return get_module_name(name=self.name, arch=self.arch)

    def module_version(self):
        """Debian versions have all sort of characters.
        This gets rid of the bazel unallowed version characters."""
        return get_module_version(self.version)
