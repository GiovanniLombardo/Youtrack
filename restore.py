"""
It allows restoration of backed up YouTrack projects and issues.

Note:
In case of conflict between issues or projects found both on the
target YouTrack server instance and on the given backup folder,
if no overwrite option is given (-op, -oi) the default policy is
to leave them unchanged on the target YouTrack server instance.
"""

from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
from colorama import Fore, Style, init as colorama_init, AnsiToWin32
from timeit import timeit
from logging import NOTSET, INFO, WARNING, ERROR, DEBUG
from logging import getLogRecordFactory, setLogRecordFactory, basicConfig, getLogger, LogRecord
from os.path import basename
from platform import system as system_platform
from signal import signal, SIGINT
from sys import argv, stdout
from typing import Any, Dict, List, Set, Optional as Opt, Tuple, Union
from types import FrameType
from pathlib import Path
from youtrack.connection import Connection as yt
from youtrack import Project, YouTrackException
from zipfile import ZipFile
from os import walk, stat, access, R_OK, W_OK
from stat import S_ISREG, S_ISDIR
from tempfile import mkdtemp
from shutil import rmtree
from re import findall, DOTALL
from json import loads

major = 1
minor = 0
fixes = 0

TPath = Union[Path, str]


class LoggingRecordFactoryColorama:
    """
    It adds the 'color' and 'reset' attributes to the LogRecord instance produced by the existing LogRecord.
    """

    levels_map = {
        INFO: Fore.LIGHTBLUE_EX + Style.DIM,
        DEBUG: Fore.GREEN + Style.BRIGHT,
        WARNING: Fore.YELLOW + Style.DIM,
        ERROR: Fore.RED + Style.DIM,
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
        It adds the color_attr and reset_attr attribute's values  according to the given levels_map, to the kwargs of the
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
    _, _ = frame, signum
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


def guess_issue_id(issue_path: Path) -> Opt[str]:
    """
    Given the path of an issue generated by the backup executable in issue_path it guesses the id of the issue.

    :param issue_path:  The path of the baked up issue.
    :type issue_path:   Path.

    :return: It returns the guessed identifier in case of success, None otherwise.
    :rtype: Opt[str].
    """
    identifier = issue_path.parts[-1]
    return identifier[:-4] if identifier.endswith('.zip') else None


def exists_backed_up_project(project_id: str, projects: Set[Path], backup_path: TPath) -> Opt[Path]:
    """
    It tells whether the definition for the given project_id is available among
    the backed up projects.

    :param project_id:      The project identifier (as obtained from a call to guess_project_id()).
    :type project_id:       str.

    :param projects:        The list of backed up projects found.
    :type projects:         List[Path].

    :param backup_path:     The path where the backup to restore is stored.
    :type backup_path:      TPath.

    :return: It returns the project path if a backed up project with the given project_id exists otherwise None.
    :rtype: Opt[Path].
    """
    path = backup_path / f'{project_id}.zip'
    return path if path in projects else None


def exists_youtrack_project(project_id: str, connection: yt) -> Opt[Project]:
    """
    It checks whether a project with the given project_id exists in the YouTrack server instance
    the connection is bound to. If the projects exists its data is returned otherwise None is
    returned.

    :param project_id:      The identifier of the project.
    :type project_id:       str.

    :param connection:      The Connection instance object.
    :type connection:       yt.

    :return: On success it returns the data corresponding to the given project_id, it returns None otherwise.
    :rtype: Opt[Project].
    """
    try:
        return connection.getProject(projectId=project_id)
    except (YouTrackException, Exception) as e:
        pass

    return


def extract_backed_up_project(project_path: Union[Path, str], dst: Union[Path, str]) -> Union[Path, str, None]:
    """
    Given the path of a project archive it extracts its content in the given dst folder.

    :param project_path:    The path of the archive of the project definition.
    :type project_path:     Union[Path, str].

    :param dst:             The destination folder for the extracted project definition.
    :type dst:              Union[Path, str].

    :return: It returns the path of the extracted content upon success, None otherwise.
    :rtype: Union[Path, str, None].
    """
    logger = getLogger(__name__)
    
    try:
        # Project path
        stat_result = stat(project_path)
        
        if not S_ISREG(stat_result.st_mode):
            logger.error(f'The project path must be a valid regular file: `{project_path}`.')
            return
        
        if not access(project_path, R_OK):
            logger.error(f'You don\'t have permission to read: `{project_path}`.')
            return
            
        # Dst
        stat_result = stat(dst)
        
        if not S_ISDIR(stat_result.st_mode):
            logger.error(f'The dst path must be a valid folder: `{dst}`.')
            return
        
        if not access(project_path, R_OK|W_OK):
            logger.error(f'You don\'t have permission to read/write: `{project_path}`.')
            return

        with ZipFile(project_path) as z:
            # Info: arbitrary location write
            z.extractall(dst)

        return dst

    except (OSError, Exception) as e:
        logger.error(e)
        return


def create_project(connection: yt, project_data: Dict[Any, Any]) -> Opt[Dict[Any, Any]]:
    """
    It creates a new project using the information stored inside the project_data argument on the currently active
    connection to the target YouTrack server instance.

    :param connection:      The youtrack connection instance object.
    :type connection:       Connection.

    :param project_data:    The project definition obtained from the backup.
    :type project_data:     Dict[Any, Any].

    :return: It returns the built project on success, None otherwise.
    :rtype: Dict[Any, Any].
    """
    logger = getLogger(__name__)

    try:
        prj = Project()
        for k, v in project_data.items():
            setattr(prj, k, v)
        # noinspection PyArgumentList
        return connection.createProject(prj)
    except (YouTrackException, Exception) as e:
        logger.error(e)

    return None


def exists_youtrack_issue(connection: yt, issue_id: str) -> Opt[Dict[Any, Any]]:
    """
    It checks whether an issue with the given issue_id exists in the YouTrack server instance pointed by the connection
    object and if it does it returns its data.

    :param connection:      The Connection instance object.
    :type connection:       yt.

    :param issue_id:        The issue identifier.
    :type issue_id:         str.

    :return: It returns the issue data structure when the issue exists, it returns None otherwise.
    :rtype: Opt[Dict[Any, Any]].
    """
    logger = getLogger(__name__)

    try:
        return connection.getIssue(issue_id)
    except (YouTrackException, Exception) as e:
        logger.error(e.__str__().decode('utf-8', errors='ignore'))

    return None


def extract_backed_up_issue(issue_path: Union[Path, str], ) -> Union[Path, str, None]:
    pass


def create_issue(connection: yt, issue_data: Dict[Any, Any]) -> Opt[Dict[Any, Any]]:
    """
    It creates a new issue using the information stored inside the project_data argument on the currently active
    connection to the target YouTrack server instance.

    :param connection:      The youtrack connection instance object.
    :type connection:       Connection.

    :param issue_data:      The project definition obtained from the backup.
    :type issue_data:       Dict[Any, Any].

    :return: It returns the built project on success, None otherwise.
    :rtype: Dict[Any, Any].
    """
    logger = getLogger(__name__)
    issue = None

    try:
        issue = connection.createIssue(
            project=issue_data['projectShortName'],
            assignee=issue_data['assignee'],
            summary=issue_data['summary'],
            description=issue_data['description'],
            priority=issue_data['Priority'],
            state=issue_data['State'],
            type=issue_data['Type']
        )

    except (YouTrackException, Exception) as e:
        logger.error(e)

    if not issue:
        logger.error(f'Issue creation failed for: {issue}')

    return issue


def restore_issue(connection: yt, issue_path: TPath, overwrite_set: Set[str]) -> Opt[Dict[Any, Any]]:
    """
    It restores the issue stored at issue_path on the given connection to the YouTrack target instance keeping account
    of overwrite preferences expressed by the user

    :param connection:      The YouTrack connection instance object.
    :type connection:       Connection.

    :param issue_path:      The path of the issue to be restored.
    :type issue_path:       TPath.

    :param overwrite_set:   The set of identifier of issues to overwrite.
    :type overwrite_set:    Set[str].

    :return: On success it returns the restored issue, on failure None.
    :rtype: Opt[Dict[Any, Any]].
    """
    logger = getLogger(__name__)

    try:
        issue_id = guess_issue_id(issue_path)

        if not issue_id:
            logger.error(f'Cannot guess the issue identifier from `{issue_path}`.')
            return

        target_issue = None

        try:
            target_issue = connection.getIssue(issue_id)
        except YouTrackException as e:
            pass

        if not target_issue or issue_id in overwrite_set:
            with open(issue_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                data = f.read()
                json = loads(data)
                return create_issue(connection, json)

    except (IOError, OSError, Exception) as e:
        logger.error(str(e))

    return None


def restore(connection: yt, issue: TPath, prjs: Set[Path], backup_path: TPath, tempdir: str, args: Namespace) -> bool:
    """

    :param connection:  The YouTrack connection instance object.
    :type connection:   Connection.

    :param issue:       The backed up issue zip file path.
    :type issue:        TPath.

    :param prjs:        The set of backed up projects.
    :type prjs:         Set[Path].

    :param backup_path: The path where the backup to restore is stored.
    :type backup_path:  TPath.

    :param tempdir:     The temporary directory where projects and issues are unzipped.
    :type tempdir:      TPath.

    :param args:        The parsed command line arguments.
    :type args:         Namespace.

    :return: It returns True upon successful issue restoration, False otherwise.
    :rtype: bool.
    """
    logger = getLogger(__name__)

    # Acquire the project_id id
    project_id = guess_project_id(issue)

    # When the project id cannot be guessed the issue is skipped
    if not project_id:
        logger.warning(f'Cannot guess the project identifier for the issue: `{issue}`. Action: Skipped.')
        return False

    # Acquiring the backed up project_id
    project_path = exists_backed_up_project(project_id, prjs, backup_path)

    # No project with the given project_id has been backed up
    if not project_path:
        logger.warning(f'The `{project_id:<12}` project has not been baked up. Issue: `{issue}`')

    # Acquiring the defined project on the target instance
    project = exists_youtrack_project(project_id, connection)

    # Checking if the projects is defined on the target instance
    if not project:
        logger.warning(f'The `{project_id:<12}` project does not exists on the target instance.')

    # Project is not defined on target instance but we have a baked up definition
    if not project and project_path:

        project_extracted = extract_backed_up_project(project_path, tempdir)
        if not project_extracted:
            logger.error(f'The project at `{project_path}` cannot be extracted. Action: skipped.')
            return False

        try:
            with open(Path(project_extracted) / f'{project_id}.json', 'r') as f:
                project_content = loads(f.read())

        except (IOError, OSError, Exception) as e:
            logger.error(e)
            return False

        r = create_project(connection, project_content)
        return True

    # Project is defined on the target instance but we do not have a backed up definition
    if project and not project_path:
        restore_issue(connection, issue_path=issue, overwrite_set=set(args.oi))

    # We have both: the definition of the project on the target instance and a backed up definition
    if project and project_path:
        logger.info(f'The `{project_id:<12}` project already exists on the target instance.')
        restore_issue(connection, issue_path=issue, overwrite_set=set(args.oi))
        return True

    # We miss a definition for the project
    logger.error(f'The `{project_id:<12}` project cannot be restored. Action: Skip.')
    return False


def compare_issues(connection: yt, lh_issue, rh_issue):
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
        overwrite_projects='The projects that will be overwritten.',
        overwrite_issues='The issues that will be overwritten.',
        verbose='It shows more verbose output.',
    )

    logger = getLogger(__name__)
    # noinspection PyTypeChecker
    parser = ArgumentParser(description=helps['description'], formatter_class=RawDescriptionHelpFormatter)

    # Mandatory arguments
    parser.add_argument('url', help=helps['url'])
    parser.add_argument('token', help=helps['token'])
    parser.add_argument('backup', help=helps['backup'])

    # Options
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False, help=helps['verbose'])
    parser.add_argument('-op','--overwrite-projects', dest='op', nargs='+', default=[], help=helps['overwrite_projects'])
    parser.add_argument('-oi','--overwrite-issues', dest='oi', nargs='+', default=[], help=helps['overwrite_issues'])

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

    try:

        tempdir = mkdtemp()
        connection = yt(args.url, token=args.token)
        projects, issues = get_projects_and_issues(args, logger)
        logger.info(f'{"Backed up projects":<20}: {len(projects)}')
        logger.info(f'{"Backed up issues":<20}: {len(issues)}\n')

        for issue in issues:
            restore(connection, issue, projects, args.backup, tempdir, args)

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
