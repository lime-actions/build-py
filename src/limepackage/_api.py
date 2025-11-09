#!/usr/bin/env python
"""Updating the pyproject.toml metadata and packaging into wheel and.

source.

distributions.
"""
# ======================================================================
# IMPORT
import tomllib
from importlib import util
from pathlib import Path
from time import time_ns
from typing import TYPE_CHECKING

import tomli_w

# ======================================================================
__all__ = ('package',)
# ======================================================================
# Hinting types
if TYPE_CHECKING:
    from collections.abc import Iterable
    from types import ModuleType
    from typing import Any
    from typing import TypeAlias

    from pip._vendor.packaging.version import Version

    OptionTree: TypeAlias = dict[str, 'OptionTree | str']
else:
    Iterable = tuple
    ModuleType = OptionTree = object
# ======================================================================
DEFAULT_DEPENDENCIES_PREFIX = 'requiremements_'
DEFAULT_DEPENDENCIES_PATH = 'dependencies'
DEFAULT_README_GENERATOR_PATH = 'readme/readme.py'


# ======================================================================
def upsearch(
    patterns: str | Iterable[str],
    path_search: Path | None = None,
    deep: bool = False,
    path_stop: Path | None = None,
) -> Path | None:
    """Searches for pattern gradually going up the path."""

    if path_search is None:
        path_search = Path.cwd()

    if path_stop is None:
        path_stop = Path(path_search.root)
    elif path_search.root != path_stop.root:
        raise ValueError(
            f"Start path {path_search} does not share root with stop path {path_stop}"
        )

    if isinstance(patterns, str):
        patterns = (patterns,)

    for path in (path_search, *path_search.parents):
        for pattern in patterns:
            try:
                return next((path.rglob if deep else path.glob)(pattern))
            except StopIteration:
                pass
        if path == path_stop:
            break
    return None


# ======================================================================
def import_from_path(path: Path) -> ModuleType:
    """Imports python module from a path."""
    spec = util.spec_from_file_location(path.stem, path)

    try:
        # creates a new module based on spec
        module = util.module_from_spec(spec)  # type: ignore[arg-type]
    except Exception as exc:
        raise FileNotFoundError(f"Spec not found from {path}") from exc

    # executes the module in its own namespace
    # when a module is imported or reloaded.
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except AttributeError as exc:
        raise TypeError('Loader was None') from exc
    return module


# ======================================================================
def _insert_option(
    option_tree: dict[str, OptionTree | str], option_name: str
) -> None:
    options = [option_name]
    while (split := option_name.rpartition('-'))[1]:
        option_name = split[0]
        options.append(option_name)

    options.reverse()
    options_iter = iter(options)
    for option in options_iter:

        if (suboption_tree := option_tree.get(option)) is None:
            suboption_tree = {}
            option_tree[option] = suboption_tree
            option_tree = suboption_tree

            for option in options_iter:
                suboption_tree = {}
                option_tree[option] = suboption_tree
                option_tree = suboption_tree

            break
        option_tree = suboption_tree  # type: ignore[assignment]


# ======================================================================
def construct_options(
    project_name: str,
    path_dependencies: Path,
    option_tree: dict[str, OptionTree | str],
    all_options: dict[str, Path],
    prefix: str = 'requirements_',
) -> dict[str, Path]:

    for option, suboption_tree in option_tree.items():

        dependencies = {f"{project_name}[{req}]\n" for req in suboption_tree}

        # Fill in the dependencies
        path = path_dependencies / f"{prefix}{option}.txt"

        all_options[option] = path

        path.touch()
        prefix = f"{project_name}[{option}"
        with open(path, 'r+') as file:
            dependencies.update(
                line
                for line in file.readlines()
                if not (line in dependencies or line.startswith(prefix))
            )
            file.seek(0)
            file.truncate()
            file.writelines(sorted(dependencies))

        construct_options(
            project_name,
            path_dependencies,
            suboption_tree,  # type: ignore[arg-type]
            all_options,
            prefix,
        )
    return all_options


# ======================================================================
def search_versions(pypi_name: str) -> Version | None:
    from pip._internal.commands.index import IndexCommand

    command = IndexCommand('index', '')

    options, _ = command.parse_args(['index', 'versions', pypi_name, '--pre'])

    with command._build_session(options) as session:
        finder = command._build_package_finder(
            options=options,
            session=session,
            target_python=None,
            ignore_requires_python=True,
        )
        latest = None
        for latest in finder.find_all_candidates(pypi_name):
            pass
        return None if latest is None else latest.version

    #     versions_unique = {candidate.version: None for candidate in
    #                 finder.find_all_candidates(pypi_name) if candidate.version.startswith(pattern)}
    # versions = [*versions_unique]
    # versions.reverse()
    # return versions


# ======================================================================
def _package_dependencies(
    path_project: Path, limepackage_info: dict[str, Any], pypi_name: str
):
    meta = limepackage_info.get('dependencies', {})

    path_dependencies = path_project / Path(
        meta.get('path', DEFAULT_DEPENDENCIES_PATH)
    )
    prefix = meta.get('prefix', DEFAULT_DEPENDENCIES_PREFIX)

    # read all

    option_tree: OptionTree = {}

    # Read current option files

    for path in path_dependencies.rglob(f"{prefix}*.txt"):
        option_name = path.stem.removeprefix(prefix)
        if option_name != 'all':
            _insert_option(option_tree, option_name)

    # Build option groups
    all_options = construct_options(
        pypi_name, path_dependencies, {'all': option_tree}, {}
    )

    # Sort and convert to posix paths
    return {
        option: {'file': _path.relative_to(path_project).as_posix()}
        for option, _path in sorted(
            all_options.items(), key=lambda item: item[0]
        )
    }


# ----------------------------------------------------------------------
def _package_readme(
    path_project: Path,
    pyproject: dict[str, Any],
    project_info: dict[str, Any],
    limepackage_info: dict[str, Any],
    ref: str,
):
    urls: dict[str, Any] = _get(project_info, 'urls', default_factory=dict)
    source_url = _get(
        urls, 'Source Code', default_factory=lambda: urls.get('Homepage', '')
    )
    path_readme_text: Path = path_project / _get(
        project_info, 'readme', 'README.md'
    )

    path_readme_generator = path_project / _get(
        limepackage_info, 'readme', DEFAULT_README_GENERATOR_PATH
    )
    try:
        readme_text = (
            str(import_from_path(path_readme_generator).main(pyproject)) + '\n'
        )
    except FileNotFoundError:
        readme_text = path_readme_text.read_text()

    if source_url.startswith('https://github.com'):
        readme_text_pypi = readme_text.replace(
            '(./', f"({source_url}/blob/{ref}/"
        )
    else:
        readme_text_pypi = readme_text
    return path_readme_text, readme_text, readme_text_pypi


# ----------------------------------------------------------------------
_MISSING = object()


# ----------------------------------------------------------------------
def _get(
    _dict: dict,
    key: Any,
    /,
    default: Any = None,
    default_factory: Any = _MISSING,
):
    if (value := _dict.get(key, _MISSING)) is _MISSING:
        value = default if default_factory is _MISSING else default_factory()
        _dict[value] = value
    return value


# ======================================================================
def package(
    path: Path | None = None,
    *,
    build: bool = False,
    pre_release: str | None = None,
    dev_release: int | str | None = None,
    ref: str = 'main',
) -> int:
    """Command line interface entry point.

    Builds README and the package
    """
    path_pyproject: Path
    if path is None:
        path_pyproject = upsearch('pyproject.toml')  # type: ignore[assignment]
        try:
            path = path_pyproject.parent
        except AttributeError as exc:
            raise FileNotFoundError('pyproject.toml not found') from exc
    else:
        path_pyproject = path / 'pyproject.toml'

    # ------------------------------------------------------------------
    # BUILD INFO

    # Loading the pyproject TOML file
    pyproject = tomllib.loads(path.read_text(encoding='utf8'))
    project_info: dict[str, Any] = pyproject['project']
    tool_info: dict[str, Any] = _get(pyproject, 'tool', default_factory=dict)
    limepackage_info: dict[str, Any] = _get(
        tool_info, 'limepackage', default_factory=dict
    )

    pypi_name: str = project_info['name']

    path_dist = path / 'dist'
    # ------------------------------------------------------------------
    # optional-dependencies

    _get(
        _get(tool_info, 'setuptools', default_factory=dict),
        'dynamic',
        default_factory=dict,
    )['optional-dependencies'] = _package_dependencies(
        path, limepackage_info, pypi_name
    )
    # ------------------------------------------------------------------
    # Readme
    (path_readme_text, readme_text, readme_text_pypi) = _package_readme(
        path, pyproject, project_info, limepackage_info, ref
    )
    # ------------------------------------------------------------------
    if pre_release is not None:  # Pre-release
        if pre_release[-1].isdigit():
            project_info['version'] += pre_release
        else:
            latest = search_versions(pypi_name)
            if (
                latest is None
                or latest.base_version != project_info['version']
                or latest.pre is None
                or latest.pre[0] != pre_release
            ):
                project_info['version'] = (
                    f"{project_info['version']}{pre_release}1"
                )
            else:
                project_info['version'] = (
                    f"{project_info['version']}{pre_release}{latest.pre[1]}"
                )

    # ------------------------------------------------------------------
    if dev_release is not None:  # Developmental release
        project_info[
            'version'
        ] += f".dev{time_ns() >> 30 if dev_release == '' else dev_release}"
    # ------------------------------------------------------------------
    # RUNNING THE BUILD

    pyproject['project'] = project_info
    path_pyproject.write_text(tomli_w.dumps(pyproject))

    for path in path_dist.iterdir():
        path.unlink()

    try:
        path_readme_text.write_text(readme_text_pypi)

        if build:
            from build.__main__ import main as _build

            _build([], prog=pypi_name)
            # run(('uv', 'build'))
    finally:
        path_readme_text.write_text(readme_text, encoding='utf8')
    return 0
