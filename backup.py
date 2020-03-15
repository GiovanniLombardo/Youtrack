"""
It allows custom selective youtrack project's issue backup.
"""

from argparse import ArgumentParser, Namespace
from colorama import Fore, Style, init as colorama_init, AnsiToWin32
from timeit import timeit
from logging import NOTSET, INFO, WARNING, ERROR, DEBUG
from logging import getLogRecordFactory, setLogRecordFactory, basicConfig, getLogger, LogRecord
from os.path import basename
from platform import system as system_platform
from signal import signal, SIGINT, SIG_IGN
from sys import argv, stdout
from typing import Any, Dict, List, Optional as Opt
from types import FrameType
from youtrack.connection import Connection as yt
from zipfile import ZipFile, ZIP_DEFLATED
from tempfile import mkdtemp
from shutil import move, rmtree
from os import unlink, makedirs
from json import dumps
from pathlib import Path


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
        WARNING: Fore.LIGHTYELLOW_EX + Style.DIM,
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


def backup(args, connection, logger):
    """
    It performs issues backup according to the given arguments.

    :param args:        The namespace with parsed command line arguments.
    :type args:         Namespace.

    :param connection:  The youtrack connection instance object.
    :type connection:   Connection.

    :param logger:      The logger instance object.
    :type logger:       Logger.

    :return: None.
    :rtype: None.
    """

    # Generates a temporary directory
    tempdir = Path(mkdtemp())

    # Iterates over projects
    for prj in connection.getProjectIds():

        # Filters on project names
        if args.prjs and prj not in args.prjs:
            logger.debug(f'Skipped project: {prj}')
            continue

        # Gets the number of issue [otherwise only 10 are downloaded by default]
        no_issue = connection.getNumberOfIssues(filter=prj)

        # Iterates over issues
        for issue in connection.getIssues(prj, '', '', max=no_issue):

            # Filters on issue ids
            if args.iid and issue.id not in args.iid:
                logger.debug(f'Skipped issue: {issue.id}')
                continue

            # Acquires some issue metadata
            description = issue.description[:issue.description.find(chr(10))].replace("#", "")
            logger.info(f'Processing: {issue.id} {description}')

            names = []

            # Iterates over attachments
            for idx, attachment in enumerate(issue.getAttachments()):
                # Acquires some attachment metadata
                filename = '_'.join([issue.id, attachment.name])
                logger.info(f'Processing #{idx} attachment: {filename}')

                # Write the attachment on disk
                names.append(str(tempdir / filename))
                with open(names[-1], 'wb') as f:
                    logger.info(f'Writing content: {Path(f.name).parts[-1]}')
                    f.write(attachment.getContent().read())

                # Writes attachment metadata on disk
                names.append(str(tempdir / f'{filename}.json'))
                with open(names[-1], 'w') as f:
                    logger.info(f'Writing metadata: {Path(f.name).parts[-1]}')
                    f.write(dumps(attachment.to_dict()))

            # Writes the issue data on disk
            names.append(str(tempdir / f'{issue.id}.json'))
            with open(names[-1], 'w') as f:
                logger.info(f'Writing issue: {Path(f.name).parts[-1]}')
                f.write(dumps(issue.to_dict()))

            z_name = str(tempdir / f'{issue.id}.zip')
            with ZipFile(z_name, 'w', ZIP_DEFLATED, compresslevel=9) as z:
                logger.info(f'Created archive: {Path(z_name).parts[-1]}')
                for name in names:
                    z.write(name)
                    unlink(name)

            # Moves the zip in the output folder
            move(z_name, str(args.output / f'{issue.id}.zip'))

    # Removes the empty temporary folder
    rmtree(tempdir)


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
        output='The destination folder.',
        verbose='It shows more verbose output.',
        projects='When given only the issue of the given projects are considered.',
        issueids='When given only the issues with the given id are considered.',
    )

    logger = getLogger(__name__)
    parser = ArgumentParser(description=helps['description'])

    # Mandatory arguments
    parser.add_argument('url', help=helps['url'])
    parser.add_argument('token', help=helps['token'])
    parser.add_argument('output', help=helps['output'])

    # Options
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False, help=helps['verbose'])
    parser.add_argument('-p', '--projects', dest='prjs', nargs='+', default=[], help=helps['projects'])
    parser.add_argument('-i', '--issue-ids', dest='iid', nargs='+', default=[], help=helps['issueids'])

    # Parsing
    args = parser.parse_args(args)

    # Checking the output directory
    args.output = Path(args.output)
    if not args.output.exists():
        makedirs(str(args.output), exist_ok=True)

    # Making sets for faster belonging check
    args.prjs = set(args.prjs) if args.prjs else args.prjs
    args.iid = set(args.iid) if args.iid else args.iid

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

    try:
        connection = yt(args.url, token=args.token)
        backup(args, connection, logger)
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
    logger.info(f'\nElapsed: {timeit(lambda: main(usage(args)), number=1):.4f} seconds')


if __name__ == '__main__':
    external_main(argv[1:])
    exit(0)
