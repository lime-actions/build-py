"""Defining the readme.md."""
import limepackage
from limedev import readme
#=======================================================================
def main(pyproject: readme.Pyproject):
    """This gets called by the limedev."""

    name: str = pyproject['tool']['limedev']['full_name'] # type: ignore[assignment]
    semi_description = f'''
    {name} is collection tools for Python development.
    These tools are more or less thin wrappers around other packages.'''
    return readme.make(limepackage, semi_description,
                       name = name)
#=======================================================================
