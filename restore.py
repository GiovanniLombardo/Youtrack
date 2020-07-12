"""
It allows restoration of backed up youtrack issues.
"""

from argparse import ArgumentParser, Namespace
from colorama import Fore, Style, init as colorama_init, AnsiToWin32
from timeit import timeit
from logging import NOTSET, INFO, WARNING, ERROR, DEBUG
from logging import getLogRecordFactory, setLogRecordFactory, basicConfig, getLogger, LogRecord
from os.path import basename
from platform import system as system_platform
from signal import signal, SIGINT
from sys import argv, stdout
from typing import Any, Dict, List, Set, Optional as Opt, Tuple
from types import FrameType
from pathlib import Path
from youtrack.connection import Connection as yt
from youtrack import Project
from zipfile import ZipFile
from os import walk
from tempfile import mkdtemp
from shutil import rmtree
from re import findall, DOTALL

major = 1
minor = 0
fixes = 0


class LoggingRecordFactoryColorama:
    """
    It adds the 'color' and 'reset' attributes to the LogRecord instance produced by the existing LogRecord.
    """

    levels_map = {
        INFO: Fore.LIGHTBLUE_EX + Style.DIM,
        DEBUG: Fore.GREEN + Style.BRIGHT,
        WARNING: Fore.MAGENTA + Style.DIM,
        ERROR: Fore.LIGHTRED_EX + Style.DIM,
        NOTSET: Fore.RESET
    }

    color_attr = 'color'
    reset_attr = 'reset'

    def __init__(self, level_map: Opt[Dict[int, str]] = None, existing_factory: Any = getLogRecordFactory()) -> None:
        """
        It creates an instance of the LoggingRecordFactoryColorama class with the given level_map and existing_factory.

        :param level_map:           The dictionary mapping levels to colors.
        :type level_map:            Opt[Dict[int, str]].
        
        :param existing_factory:    The default LogRecordFactory to be used.
        :type existing_factory:     Any.
        """
        self.levels_map = level_map if level_map else self.__class__.levels_map
        self.existing_factory = existing_factory
        setLogRecordFactory(self)

    def __call__(self, *args: Any, **kwargs: Any) -> LogRecord:
        """
        It adds the color_attr and reset_attr attribute'values  according to the given levels_map, to the kwargs of the
        record built and returned by the existing_factory, and returns it to the caller.

        :param args:    The positional args to pass to the existing_factory.
        :type args:     Any.
        
        :param kwargs:  The keyword arguments to pass to the existing_factory.
        :type kwargs:   Any.

        :return: The record with the new arguments added.
        :rtype: LogRecord.
        """
        record = self.existing_factory(*args, **kwargs)
        setattr(record, self.__class__.color_attr, self.levels_map[record.levelno])
        setattr(record, self.__class__.reset_attr, self.levels_map[NOTSET])
        return record


def logging_console_init(level: int = INFO) -> None:
    """
    It initializes the default logging configuration.
    
    :param level:   The wanted logging level.
    :type level:    int.

    :return: None.
    :rtype: None.
    """

    color_attr = LoggingRecordFactoryColorama.color_attr
    reset_attr = LoggingRecordFactoryColorama.reset_attr
    stream = stdout if 'Windows' not in system_platform() else AnsiToWin32(stdout).stream
    colorama_init()

    # Removed from the format key of config for efficiency in space and time:
    #   [%(asctime)s.%(msecs)03d]         --> date and time in the given datefmt
    #   [%(processName)s.%(process)d]     --> process name dot process id
    #   [%(levelname)s]                   --> level name

    # Removed from the datefmt key of config for efficiency in space and time:
    #   %Y/%m/%d %H:%M:%S'                --> the format of the date in asctime when given

    config = dict(
        level=level,
        stream=stream,
        format=f'%({color_attr})s%(message)s%({reset_attr})s',
    )

    basicConfig(**config)
    LoggingRecordFactoryColorama()


def author() -> str:
    """
    It returns a brief string giving credits to the authors.

    :return: See description.
    :rtype: str.
    """
    return '(c) 2020 Giovanni Lombardo mailto://g.lombardo@protonmail.com'


def version() -> str:
    """
    It returns a version string for the current program.

    :return: See description.
    :rtype: str.
    """
    global major, minor, fixes
    return '{0} version {1}\n'.format(basename(argv[0]), '.'.join(map(str, [major, minor, fixes])))


def sigint_handler(signum: int, frame: FrameType) -> None:
    """
    The handler registered for SIGINT signal handling. It terminates the application.

    :param signum:  The signal.
    :type signum:   int.
    
    :param frame:   The frame.
    :type frame:    FrameType.

    :return: None.
    :rtype: None.
    """

    signum, frame = frame, signum
    getLogger(__name__).warning('Interrupt received..')
    exit(0)


def get_projects_and_issues(args: Namespace, logger: Any) -> Tuple[Set[Path], Set[Path]]:
    """
    It tries to figure out what files in the given backup folder should be considered as
    issues and which ones should instead be considered projects. Then it returns the two
    sets of paths: project_id's paths and  issue's paths. Note that sets may also be empty.

    :param args:        The command line arguments.
    :type args:         Namespace.

    :param logger:      The logger.
    :type logger:       Any.

    :return: It returns the two sets containing respectively found projects and issues.
    :rtype: Tuple[Set[Path], Set[Path]].
    """

    is_issue = lambda x: True if findall(r'^.*-\d+\.zip$', x, DOTALL) else False
    is_project = lambda x: True if findall(r'[^\d]\.zip$', x, DOTALL) else False

    projects = set()
    issues = set()

    # Collects issues and projects
    for idx, (root, _, files) in enumerate(walk(args.backup)):

        # Shallow search
        if 0 > idx:
            break

        root = Path(root)
        for f in files:
            if is_issue(f):
                logger.debug(f'Issue found: `{f}`')
                issues.add(root / f)
                continue
            elif is_project(f):
                logger.debug(f'Project found: `{f}`')
                projects.add(root / f)
                continue
            else:
                logger.warning(f'Unrecognized: `{f}`')

    return projects, issues


def guess_project_id(issue_path: Path) -> Opt[str]:
    """
    It tries to guess the the project_id id the given issue belongs to.

    :param issue_path:   The issue identifier.
    :type issue_path:    Path.

    :return: It returns the project_id identifier or None in case of failure.
    :rtype:
    """
    if not isinstance(issue_path, Path):
        return None

    project = findall(r'^(.*?)-\d+\.zip$', issue_path.parts[-1], DOTALL)
    return project[-1] if project else None


def exists_backed_up_project(project_id: str, projects: Set[Path], args: Namespace) -> Opt[Path]:
    """
    It tells whether the definition for the given project_id is available among
    the backed up projects.

    :param project_id:      The project identifier (as obtained from a call to
                            guess_project_id()).
    :type project_id:       str.

    :param projects:        The list of backed up projects found.
    :type projects:         List[Path].

    :param args:            The parsed command line arguments.
    :type args:             Namespace.

    :return:    It returns the project path if a backed up project with the given
                project_id exists otherwise None.
    :rtype: Opt[Path].
    """
    path = args.backup / f'{project_id}.zip'
    return path if path in projects else None


def exists_youtrack_project(project_id: str, connection: yt, args: Namespace) -> Opt[Project]:
    """
    It checks whether a project with the given project_id exists in the youtrack server instance
    pointed by the given connection. If the projects exists its Project instance is returned else
    None is returned.

    :param project_id:      The identifier of the project.
    :type project_id:       str.

    :param connection:      The Connection instance object.
    :type connection:       yt.

    :param args:            The command line parsed arguments.
    :type args:             Namespace.

    :return: It returns the Project instance corresponding to the given project_id or None.
    :rtype: Opt[Project].
    """
    return connection.getProject(projectId=project_id) or None


def clone_project(connection, project):

    return connection.createProject(project)


def clone_issue(connection, issue):
    pass


def has_issue(connection, issue):
    pass


def compare_issues(connection, lh_issue, rh_issue):
    pass


def usage(args: List[str]) -> Namespace:
    """
    It parses the given args (usually from sys.argv) and checks they conform to the rules of the application. It then
    returns a namedtuple with a field for a any given or defaulted argument.

    :param args:    The command line arguments to be parsed.
    :type args:     List[str].

    :return: See description.
    :rtype: NamedTuple.
    """
    helps = dict(
        description=__doc__,
        url='The URL of the YouTrack instance.',
        token='The to use with the given instance.',
        backup='The folder where backed up issues are located.',
        verbose='It shows more verbose output.',
    )

    logger = getLogger(__name__)
    parser = ArgumentParser(description=helps['description'])

    # Mandatory arguments
    parser.add_argument('url', help=helps['url'])
    parser.add_argument('token', help=helps['token'])
    parser.add_argument('backup', help=helps['backup'])

    # Options
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False, help=helps['verbose'])

    # Parsing
    args = parser.parse_args(args)

    # Converts backup to path
    args.backup = Path(args.backup)

    # Checks backup exists
    if not args.backup.exists():
        logger.error(f'The given backup folder does not exists: `{str(args.backup.absolute())}`')
        parser.print_usage()
        exit(1)

    # Checks backup is a folder
    if not args.backup.is_dir():
        logger.error(f'The given backup path must be folder: `{str(args.backup.absolute())}`')
        parser.print_usage()
        exit(1)

    return args


def main(args: Namespace) -> None:
    """
    It starts the application.

    :param args:    The parsed command line arguments as returned by usage();
    :type args:     Namespace.

    :return: None.
    :rtype: None.
    """
    logger = getLogger(__name__)
    logger.setLevel(INFO if not args.verbose else DEBUG)

    logger.info(f'TARGET: `{args.url}`')
    logger.debug(f'TOKEN:  `{args.token}`')
    logger.info(f'BACKUP: `{args.backup}`\n')

    tempdir = mkdtemp()

    PRJ_NOT_FOUND = 0
    PRJ_BACKED_UP = 1
    PRJ_DEFINED_ON_TARGET = 2
    PRJ_DEFINED_AND_BACKED_UP = 3

    try:

        prjs, issues = get_projects_and_issues(args, logger)
        logger.info(f'{"Backed up projects":<20}: {len(prjs)}')
        logger.info(f'{"Backed up issues":<20}: {len(issues)}\n')

        connection = yt(args.url, token=args.token)

        for issue in issues:

            # Acquire the project_id id
            project_id = guess_project_id(issue)

            # When the project id cannot be guessed the issue is skipped
            if not project_id:
                logger.warning(f'Cannot guess the project identifier for the issue: `{issue}`. Action: Skipped.')
                continue

            prj_found = PRJ_NOT_FOUND

            # Acquiring the backed up project_id
            project_path = exists_backed_up_project(project_id, prjs, args)

            # No project_id with the found id has been backed up
            if not project_path:
                logger.warning(f'No backed up `{project_id}` project found for the issue `{issue}`')

            prj_found = PRJ_BACKED_UP if project_path else prj_found

            # Acquiring the defined project on the target instance
            prj = exists_youtrack_project(project_id, connection, args)

            # Checking if the projects is defined on the target instance
            if not prj:
                logger.info(f'The project `{project_id}` does not exists on the target instance.')

            if prj:
                if prj_found == PRJ_NOT_FOUND:
                    prj_found = PRJ_DEFINED_ON_TARGET
                else:
                    prj_found = PRJ_DEFINED_AND_BACKED_UP

            r = clone_project(connection, prj)


    except Exception as e:
        logger.error(str(e))
        exit(1)


def external_main(args: List[str]) -> None:
    """
    The procedure that allows realization of standalone applications.

    :param args:    The command line arguments to be parsed by the application.
    :type args:     List[str].

    :return: None.
    :rtype: None.
    """
    logging_console_init()
    logger = getLogger(__name__)
    signal(SIGINT, sigint_handler)
    print(author())
    print(version())
    elapsed = timeit(lambda: main(usage(args)), number=1)
    logger.info(f'\nElapsed time: {elapsed:.4f} seconds.')


if __name__ == '__main__':
    external_main(argv[1:])
