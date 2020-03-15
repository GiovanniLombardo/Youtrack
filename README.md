## Youtrack-Exchange

### Aim of the project
This project main aim is to generate tooling for custom selective backup and restore of issues 
hosted on youtrack servers. With those tooling users is empowered to transfer the issue knowledge 
between different systems on different work domains. My case for example is to share the knowledge 
acquired on some of my personal projects on my laptop with the computer I have at work and vice 
versa. 

The youtrack web interface already offers features to backup the issues and the projects but, in 
my humble opinion with huge lack of granularity. It can either make a backup or not make it. It 
cannot, as far as i know, backup only some issue and restore their content on a different youtrack
instance keeping account of duplication etc.. Basically the restore of a backup overwrite the
data currently in use. 

### Components
At the time of this writing the idea is two have to command line executables, one for backing
up selectively issues of projects of a youtrack server instance and another to perform content 
wise restoration of issue on the same or other youtrack instance. 

### Backup component: how does it work?
The backup components expects to get from command line the `URL` of the youtrack instance, the 
access token of the youtrack instance and the output folder where the issues and their data will
be stored. As additions to the basic `backup all` behaviour, the user can request some filtering
behaviour on projects or issues by giving specific command line option and arguments. 

The backup utility will then download all the selected issues in the selected projects, along
with their metadata (actually unused), attachments, `[todo]` comments and comments attachments; 
and will put them in a compressed not encrypted archive in the given `output` folder. 

### Backup component: usage
Here is what's looks like the output of the backup utility invocation with the `--help` or 
`-h` option at the command line. 

```shell script
user@host# ./backup.py --help
(c) 2020 Giovanni Lombardo mailto://g.lombardo@protonmail.com
backup.py version 1.0.0

usage: backup.py [-h] [-v] [-p PRJS [PRJS ...]] [-i IID [IID ...]]
                 url token output

It allows custom selective youtrack project's issue backup.

positional arguments:
  url                   The URL of the YouTrack instance.
  token                 The to use with the given instance.
  output                The destination folder.

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         It shows more verbose output.
  -p PRJS [PRJS ...], --projects PRJS [PRJS ...]
                        When given only the issue of the given projects are
                        considered.
  -i IID [IID ...], --issue-ids IID [IID ...]
                        When given only the issues with the given id are
                        considered.
```