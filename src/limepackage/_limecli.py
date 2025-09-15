"""Command line interface framework."""
import inspect
import sys
from collections.abc import Callable
from collections.abc import Collection
from collections.abc import Generator
from collections.abc import Iterable
from functools import partial
from itertools import chain
from itertools import repeat
from types import EllipsisType
from types import FunctionType
from types import GenericAlias
from types import ModuleType
from types import UnionType
from typing import Any
from typing import cast
from typing import Protocol
from typing import Sequence
from typing import TypeAlias
from typing import TypeGuard

if sys.version_info >= (3, 11):
    from typing import Self
    from enum import EnumType
else:
    Self = Any
    from enum import EnumMeta as EnumType
# ======================================================================
Parameter = inspect.Parameter
# ======================================================================
def _quotestrip(arg: str) -> str:
    """Removes quotes from the beginning and the end of the argument if.

    they.

    match.
    """
    return (arg[1:-1] if (len(arg) >= 2
                          and (arg[0], arg[-1]) in (("'", "'"), ('"', '"')))
            else arg)
# ----------------------------------------------------------------------
def _argumentsplit(args_in: Sequence[str]) -> tuple[list[str], dict[str, str]]:
    """Separates arguments into positional and keyword arguments."""
    args = []
    kwargs = {}
    for arg in args_in:
        if arg.startswith('--'):
            keyword, _, value = arg[2:].partition('=')
            kwargs[keyword] = _quotestrip(value)
        else:
            args.append(arg)
    return args, kwargs
# ----------------------------------------------------------------------
class FromStrType(type):
    """Type instantiable from str."""
    def __call__(cls, _: str) -> Any:
        ...
ArgType = GenericAlias | UnionType | type | FromStrType
# ----------------------------------------------------------------------
class TypeConversionError(ValueError):
    """Merker for error in converting str to specified type."""
# ----------------------------------------------------------------------
class NamedTupleLike(Protocol):
    """NamedTuple Protocol."""
    __annotations__: dict[str, ArgType]

    @classmethod
    def _make(cls, items: Iterable) -> Self:
        ...
# ----------------------------------------------------------------------
def _typename(argtype: str | ArgType) -> str:
    """Gives a more readable name of the type if available."""

    return (argtype.__name__
            if (hasattr(argtype, '__name__')
                and not isinstance(argtype, GenericAlias))
            else str(argtype))
# ----------------------------------------------------------------------
def _format_error(arg: str, argtype: str | ArgType, exc: str | Exception
                  ) -> str:
    """Formats the error message."""
    errormessage = str(exc).replace('\n', '\n  ') # indenting
    return f"'{arg}' --X-> {_typename(argtype)}\n  {errormessage}"
# ----------------------------------------------------------------------
def _is_NamedTuple(item: Any) -> TypeGuard[NamedTupleLike]:
    """A heuristic for whether the item is NamedTuple class."""
    return (hasattr(item, '_make') and issubclass(item, tuple))
# ======================================================================
# Converters
def _namedtuple(arg: str, argtype: NamedTupleLike) -> NamedTupleLike:
    """Handles a NamedTuple."""
    return argtype._make(_convert_type(_arg, _argtype) for _arg, _argtype
                         in zip(arg.split(','),
                                argtype.__annotations__.values()))
# ----------------------------------------------------------------------
def _tuple(args: list[str],
           argtypes: tuple[ArgType, ...] | tuple[ArgType, EllipsisType],
           tuplelike: type
           ) -> tuple[Any]:
    """Handles a tuple."""
    if len(argtypes) == 2 and argtypes[1] is Ellipsis:
        return _collection(args, argtypes[0], tuplelike)

    if len(argtypes) != len(args):
        raise TypeConversionError(f"length of '{args!r}' not {len(argtypes)}")

    return tuplelike(_convert_type(arg, argtype)
                     for arg, argtype in zip(args, argtypes))
# ----------------------------------------------------------------------
def _collection(args: list[str], argtype: ArgType,
             collectionlike: Callable[[Iterable], Any]
             ) -> Any:
    """Converts list of arguments into same type."""
    return collectionlike(_convert_type(arg, argtype) for arg in args)
# ----------------------------------------------------------------------
def _is_parenthesis(arg:  str) -> bool | None:
    """Checks if the argument has parenthesis and they are around.

    correctly.

    True -> Parenthesise are and they are correct False -> No
    parenthesis None -> Incorrect parenthesis
    """
    if not arg:
        return False
    if (is_paren := arg[0] == '(') ^ (arg[-1] == ')'):
        return None
    return is_paren
# ----------------------------------------------------------------------
def _convert_pair(arg: str, keytype: ArgType, valuetype: ArgType
                  ) -> tuple[object, object] | tuple[None, list[str]]:
    """Handles single key: value -pair."""
    errormessages = []
    keyarg = ''
    while (partitioning := arg.partition(':'))[1]:
        new_keyarg, _, arg = partitioning
        if (is_valueparens := _is_parenthesis(arg)) is None:
            errormessages.append(f"parenthesis not valid for value '{arg}'")
            continue

        keyarg = f'{keyarg}:{new_keyarg}' if keyarg else new_keyarg

        if (is_keyparens := _is_parenthesis(keyarg)) is None:
            errormessages.append(f"parenthesis not valid for key '{keyarg}'")
            continue

        try:
            return (_convert_type(keyarg[1:-1] if is_keyparens else keyarg,
                                  keytype),
                    _convert_type(arg[1:-1] if is_valueparens else arg,
                                  valuetype))
        except TypeConversionError as exc:
            errormessages.append(str(exc))
    errormessages.append(f"Unable to split '{partitioning[0]}'")
    return None, errormessages
# ----------------------------------------------------------------------
def _dict(arg: str, keytype: ArgType, valuetype: ArgType, dictlike: type
          ) -> dict[Any, Any]:
    """Handles a dictionary."""
    if not _is_parenthesis(arg):
        raise TypeConversionError(f"argument '{arg}' must start with"
                                  "'(' and end with ')'")
    pairs = []
    errormessages = []
    subargs = arg[1:-1].split('),(')
    subarg = ''
    while subargs:
        new_subarg = subargs.pop(0)
        subarg = f'{subarg}),({new_subarg}' if subarg else new_subarg
        pair = _convert_pair(subarg, keytype, valuetype)
        if pair[0] is None:
            errormessages.append(
                _format_error(subarg,
                              f'{_typename(keytype)}: {_typename(valuetype)}',
                              '\n'.join(cast(list[str], pair[1]))))
            continue

        pairs.append(pair)
        errormessages.append(f'{subarg} --> {_typename(keytype)}: {_typename(valuetype)}')
        subarg = ''
    if pairs and not subarg:
        return dictlike(pairs)
    raise TypeConversionError('\n'.join(errormessages))
# ----------------------------------------------------------------------
def _generic_alias(arg: str, argtype: GenericAlias) -> Any:
    """Handles GenericAlias types, like tuple[int]."""
    basetype = argtype.__origin__
    if issubclass(basetype, tuple): # type: ignore[arg-type]
        return _tuple(arg.split(','), argtype.__args__, basetype) # type: ignore[arg-type]
    if issubclass(basetype, dict): # type: ignore[arg-type]
        keytype, valuetype = argtype.__args__
        return _dict(arg, keytype, valuetype, basetype) # type: ignore[arg-type]
    if issubclass(basetype, Collection): # type: ignore[arg-type]
        return _collection(arg.split(','), argtype.__args__[0], basetype) # type: ignore[arg-type]
    raise TypeError(f'Type of {argtype}, {type(argtype)}, not supported')
# ----------------------------------------------------------------------
def _union(arg: str , argtype: UnionType):
    """Handles an union of types."""
    errormessages = []
    for subtype in argtype.__args__:
        try:
            return _convert_type(arg, subtype)
        except TypeConversionError as exc:
            errormessages.append(str(exc))
    raise TypeConversionError('\n'.join(errormessages))
# ----------------------------------------------------------------------
def _enum(arg: str, argtype: EnumType) -> EnumType:
    """Handles a Enum.

    Tries to be case insensitive
    """
    try:
        return argtype.__members__[arg]
    except KeyError:
        # Casefolding
        arg_cf = arg.casefold()
        member: EnumType
        for member_name, member in argtype.__members__.items():
            if member_name.casefold() == arg_cf:
                return member
    raise TypeConversionError(f'{arg} not in members of {argtype.__name__} '
                              f'({", ".join(argtype.__members__)})')
# ----------------------------------------------------------------------
def _bool(arg: str) -> bool:
    if arg == '':
        return True
    if (arg_cf := arg.casefold()) == 'false':
        return False
    if arg_cf == 'true':
        return True
    raise TypeConversionError(f"'{arg}' not convertable to bool")
# ----------------------------------------------------------------------
def _convert_type(arg: str, argtype: ArgType) -> object:
    """Converts argument to annotated type."""
    try:
        if argtype in (Parameter.empty, Any, str):
            return arg
        if isinstance(argtype, GenericAlias):
            return _generic_alias(arg, argtype)
        if isinstance(argtype, UnionType):
            #Converts to first of the unioned types
            return _union(arg, argtype)
        if isinstance(argtype, EnumType):
            return _enum(arg, argtype)
        if argtype is bool:
            return _bool(arg)
        if issubclass(argtype, dict):
            return _dict(arg, str, str, argtype)
        if _is_NamedTuple(argtype):
            return _namedtuple(arg, argtype)
        if issubclass(argtype, Collection):
            return _collection(arg.split(','), str, argtype)
    except TypeConversionError as exc:
        raise TypeConversionError(_format_error(arg, argtype, exc))  # pylint: disable=raise-missing-from
    try: # Direct conversion
        return cast(FromStrType, argtype)(arg)
    except (TypeError, ValueError) as exc:
        raise TypeConversionError(_format_error(arg, argtype, exc))  # pylint: disable=raise-missing-from
# ----------------------------------------------------------------------
def cli_hooks(module: ModuleType
               ) -> Generator[tuple[str, FunctionType], None, None]:
    """Generator for valid cli hook functions from module."""
    for name, attribute in module.__dict__.items():
        if (isinstance(attribute, FunctionType)
            and not name.startswith('_')
            and attribute.__annotations__.get('return') is int
            and name != 'main'
            and attribute is not function_cli):
            yield name, attribute
# ----------------------------------------------------------------------
def _make_function_helpstring(name: str, function: FunctionType):
    _signature = inspect.signature(function)
    helptext = f'{name}'

    # Adding parameters
    for parameter_name, parameter in _signature.parameters.items():
        helptext += f' {parameter_name}'
        if parameter.default is not parameter.empty:
            helptext += f'={parameter.default}'

    # Adding docstring
    if function.__doc__ is not None:
        helptext += f"\n    '''{function.__doc__}'''"
    return helptext
# ----------------------------------------------------------------------
def _make_helpstring(module: ModuleType) -> str:
    """Builds the helpstring by inpecting the module."""
    # Generating helptext
    return f'Functions available: {'\n\n'.join([_make_function_helpstring(name, function) for name, function in cli_hooks(module)])}'
# ----------------------------------------------------------------------
ArgsKwargs: TypeAlias = tuple[list, dict[str, Any]]
# ----------------------------------------------------------------------
def _convert_parameter(arg: str, parameter: Parameter):
    """Convertest argument according to parameter."""
    try:
        return _convert_type(arg, parameter.annotation)
    except TypeConversionError as exc:
        raise TypeConversionError(f"Converting input for '{parameter.name}'"# pylint: disable=raise-missing-from
                                  f' failed.\n{exc}')
# ----------------------------------------------------------------------
def _convert_args(args: Sequence[str], function: FunctionType
                  ) -> ArgsKwargs:
    """Parses command line arguments and convertes them according to the.

    function signature.
    """
    cli_args, cli_kwargs = _argumentsplit(args)

    function_signature = inspect.signature(function)

    var_pos_not_found = True
    parameter_var_pos = Parameter('args', Parameter.VAR_POSITIONAL)
    parameter_var_kw = Parameter('kwargs', Parameter.VAR_KEYWORD)

    parameters = {}

    for parameter in function_signature.parameters.values():
        if (var_pos_not_found
            and parameter.kind == Parameter.VAR_POSITIONAL):
            parameter_var_pos = parameter
            var_pos_not_found = False
        elif parameter.kind == Parameter.VAR_KEYWORD:
            parameter_var_kw = parameter
        else:
            parameters[parameter.name] = parameter

    converted_kwargs = {}

    for parameter_name, cli_arg in cli_kwargs.items():
        parameter_name = parameter_name.replace('-', '_')
        parameter = parameters.pop(parameter_name, parameter_var_kw)
        converted_kwargs[parameter_name] = _convert_parameter(cli_arg,
                                                              parameter)
        # print(parameter_name, converted_kwargs[parameter_name])
    converted_args = [_convert_parameter(cli_arg, parameter)
                      for cli_arg, parameter
                      in zip(cli_args, chain(parameters.values(),
                                             repeat(parameter_var_pos)))]

    return converted_args, converted_kwargs
# ----------------------------------------------------------------------
def function_cli(args: list[str] | None,
                 function: FunctionType | None = None,
                 module: str | ModuleType = '__main__',
                 package: str = '') -> int:
    """Functions as main able to run functions matching signature and.

    generate.

    helptext.

    Syntax
    ------

    Lists, tuples, sets, etc single value iterables
        Values separate by comma.
        E.g. tuple[int, int, int] -> 1,2,3
    Dictionary and other mappings
        Pairs of parenthesised values separated by comma.
        E.g. dict[str, int] -> (a:1),(b:2)
    Boolean flags.
        - `--flag` -> flag = True
        - `--flag=True` -> flag = True
        - `--flag=False` -> flag = False
    """
    if isinstance(module, str):
        module = sys.modules[module]

    if args is None:
        from sys import argv
        args = argv[1:]


    if (function is None and not args) or '--help' in args:
        print(_make_helpstring(module) if function is None else _make_function_helpstring(function.__name__, function))
        return 0

    if args[0] == '--version':

        if module.__package__:
            _package = sys.modules[module.__package__]
            name = package if package else module.__package__
        else:
            _package = module
            name = package if package else module.__name__

        print(name, _package.__version__)
        return 0


    if function is None:
        try:
            function = getattr(module, args[0])
        except AttributeError:
            print(f"{str(module)[1:-1].capitalize()} does not have a function '{args[0]}'")
            return 2

    # Parsing the arguments
    converted_args, converted_kwargs = _convert_args(args[1:], function)

    try:
        output = function(*converted_args, **converted_kwargs)
    except BaseException as exc:
        print(f'{exc.__class__.__name__}: {exc}', file = sys.stderr)
        return 1
    if isinstance(output, int):
        return output

    if output is not None:
        print(output)
    return 0
# ======================================================================
def get_main(module: str | ModuleType = '__main__', package: str = '', function: FunctionType | None = None):
    """Generating main function from module or module name."""
    return partial(function_cli, function = function, module = module, package = package)
